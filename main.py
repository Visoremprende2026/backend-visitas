# ============================================================
#  main.py — FastAPI app v2
#  Ejecutar: uvicorn main:app --reload --host 0.0.0.0 --port 8000
#  Documentacion: http://localhost:8000/docs
# ============================================================

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from modelos import (
    OTPRequest, OTPVerify, TokenResponse,
    InvitacionCreate, InvitacionResponse, InvitacionUpdate,
    SolicitudAcceso, RespuestaAcceso, LogAcceso,
    PushTokenRequest, UsuarioActual,
)
from auth import (
    get_usuario_actual, solo_propietario, solo_admin,
    generar_otp, enviar_otp_sms, verificar_otp, crear_jwt,
)
from nucleo import procesar_solicitud_acceso
from mqtt_client import mqtt_client
from base_datos import (
    init_db,
    obtener_perfil_usuario,
    obtener_membresia_por_id,
    obtener_membresia_activa,
    crear_invitacion_bd,
    listar_invitaciones_propietario,
    listar_invitaciones_invitado,
    obtener_invitacion,
    actualizar_invitacion_bd,
    cancelar_invitacion_bd,
    listar_log_accesos,
    guardar_push_token,
    obtener_puertas_edificio,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[INICIO] Iniciando tablas PostgreSQL/SQLite...")
    await init_db()
    logger.info("[INICIO] Conectando cliente MQTT...")
    mqtt_client.conectar()
    yield
    logger.info("[CIERRE] Desconectando cliente MQTT...")
    mqtt_client.desconectar()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API Backend para sistema de administracion de visitas con BLE + MQTT",
    lifespan=lifespan,
)

@app.on_event("startup")
async def startup_event():
    mqtt_client.conectar()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
#  AUTENTICACION
# ============================================================

@app.post("/auth/otp/request", tags=["Autenticacion"])
async def solicitar_otp(body: OTPRequest):
    codigo = generar_otp(body.numero_celular)
    enviado = await enviar_otp_sms(body.numero_celular, codigo)
    if not enviado:
        raise HTTPException(status_code=503, detail="No se pudo enviar el SMS.")
    return {"mensaje": "Codigo enviado", "expira_minutos": settings.OTP_EXPIRA_MINUTOS}


@app.post("/auth/otp/verify", response_model=TokenResponse, tags=["Autenticacion"])
async def verificar_otp_endpoint(body: OTPVerify):
    if not verificar_otp(body.numero_celular, body.codigo):
        raise HTTPException(status_code=401, detail="Codigo incorrecto o expirado")

    perfil_data = await obtener_perfil_usuario(body.numero_celular)

    if not perfil_data:
        # Numero sin registro — crear usuario como invitado automaticamente
        from base_datos import AsyncSessionLocal, Usuario
        import uuid as uuid_lib
        async with AsyncSessionLocal() as session:
            nuevo = Usuario(
                id=str(uuid_lib.uuid4()),
                numero_celular=body.numero_celular,
                activo=True,
            )
            session.add(nuevo)
            await session.commit()
        perfil_data = {
            "perfil": "invitado",
            "edificio_id": None,
            "nombre": None,
            "membresias": [],
    }

    token = crear_jwt(
        numero_celular=body.numero_celular,
        perfil=perfil_data["perfil"],
        edificio_id=perfil_data.get("edificio_id"),
        membresias=[m for m in perfil_data.get("membresias", [])],
    )

    return TokenResponse(
        access_token=token,
        perfil=perfil_data["perfil"],
        edificio_id=perfil_data.get("edificio_id"),
        nombre=perfil_data.get("nombre"),
        membresias=perfil_data.get("membresias", []),
    )


@app.post("/auth/refresh", response_model=TokenResponse, tags=["Autenticacion"])
async def refresh_token(usuario: UsuarioActual = Depends(get_usuario_actual)):
    token = crear_jwt(
        numero_celular=usuario.numero_celular,
        perfil=usuario.perfil,
        edificio_id=usuario.edificio_id,
        membresias=[m.dict() for m in usuario.membresias],
    )
    return TokenResponse(
        access_token=token,
        perfil=usuario.perfil,
        edificio_id=usuario.edificio_id,
        membresias=usuario.membresias,
    )

@app.post("/auth/pin/estado-publico", tags=["Autenticacion"])
async def estado_pin_publico(body: dict):
    """Verifica si un numero tiene PIN — sin autenticacion."""
    from base_datos import tiene_pin
    numero = body.get("numero_celular", "").strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Numero requerido")
    return await tiene_pin(numero)


# ============================================================
#  INVITACIONES
# ============================================================

@app.post("/invitaciones", response_model=InvitacionResponse, tags=["Invitaciones"])
async def crear_invitacion(
    body: InvitacionCreate,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    # Verificar que la membresia pertenece al usuario
    membresia = await obtener_membresia_por_id(body.membresia_id)
    if not membresia or membresia["numero_celular"] != usuario.numero_celular:
        raise HTTPException(status_code=403, detail="Membresia no valida")

    invitacion = await crear_invitacion_bd(
        membresia_id=body.membresia_id,
        numero_invitado=body.numero_invitado,
        puerta_id=body.puerta_id,
        edificio_id=membresia["edificio_id"],
        unidad_destino=body.unidad_destino or membresia["unidad"],
        fecha_desde=body.fecha_desde,
        fecha_hasta=body.fecha_hasta,
        todo_el_dia=body.todo_el_dia,
        hora_inicio=body.hora_inicio,
        hora_fin=body.hora_fin,
        dias_permitidos=body.dias_permitidos,
        nota=body.nota,
    )
    if not invitacion:
        raise HTTPException(status_code=400, detail="No se pudo crear la invitacion")

    # Notificar al invitado via webhook n8n (WhatsApp)
    from notificaciones import notificar_invitacion_creada
    invitacion["edificio_nombre"] = membresia["edificio_nombre"]
    await notificar_invitacion_creada(
        invitacion=invitacion,
        nombre_propietario=membresia["nombre"] or "",
    )

    return invitacion


@app.get("/invitaciones", response_model=list[InvitacionResponse], tags=["Invitaciones"])
async def listar_invitaciones(
    estado: str = "todas",
    membresia_id: str = None,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    # Usar membresia_id del query param o la primera del JWT
    mid = membresia_id or usuario.membresia_id
    if not mid:
        return []
    return await listar_invitaciones_propietario(membresia_id=mid, estado=estado)


@app.get("/invitaciones/activas", response_model=list[InvitacionResponse], tags=["Invitaciones"])
async def invitaciones_activas_invitado(
    usuario: UsuarioActual = Depends(get_usuario_actual),
):
    return await listar_invitaciones_invitado(
        numero_invitado=usuario.numero_celular,
        ahora=datetime.now(timezone.utc),
    )


@app.patch("/invitaciones/{invitacion_id}", response_model=InvitacionResponse, tags=["Invitaciones"])
async def actualizar_invitacion(
    invitacion_id: str,
    body: InvitacionUpdate,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    invitacion = await obtener_invitacion(invitacion_id)
    if not invitacion:
        raise HTTPException(status_code=404, detail="Invitacion no encontrada")
    # Verificar que la membresia de la invitacion pertenece al usuario
    membresia = await obtener_membresia_por_id(invitacion["membresia_id"])
    if not membresia or membresia["numero_celular"] != usuario.numero_celular:
        raise HTTPException(status_code=403, detail="No tienes permiso para modificar esta invitacion")
    return await actualizar_invitacion_bd(invitacion_id, body.dict(exclude_none=True))


@app.delete("/invitaciones/{invitacion_id}", tags=["Invitaciones"])
async def cancelar_invitacion(
    invitacion_id: str,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    invitacion = await obtener_invitacion(invitacion_id)
    if not invitacion:
        raise HTTPException(status_code=404, detail="Invitacion no encontrada")
    membresia = await obtener_membresia_por_id(invitacion["membresia_id"])
    if not membresia or membresia["numero_celular"] != usuario.numero_celular:
        raise HTTPException(status_code=403, detail="No tienes permiso para cancelar esta invitacion")
    await cancelar_invitacion_bd(invitacion_id)
    return {"ok": True, "mensaje": "Invitacion cancelada"}


# ============================================================
#  ACCESO
# ============================================================

@app.post("/acceso/solicitar", response_model=RespuestaAcceso, tags=["Acceso"])
async def solicitar_acceso(
    body: SolicitudAcceso,
    usuario: UsuarioActual = Depends(get_usuario_actual),
):
   # Para invitados sin membresia, obtener edificio_id desde la invitacion
    edificio_id = usuario.edificio_id
    if not edificio_id and body.invitacion_id:
        inv_temp = await obtener_invitacion(body.invitacion_id)
        if inv_temp:
            edificio_id = inv_temp["edificio_id"]

    resultado = await procesar_solicitud_acceso(
        numero_invitado=usuario.numero_celular,
        edificio_id=edificio_id,
        uuid_ble=body.uuid_ble,
        invitacion_id=body.invitacion_id,
        lat=body.lat,
        lng=body.lng,
    )

    if not resultado["ok"]:
        mensajes = {
            "sin_invitacion":      "No tienes una invitacion activa.",
            "expirada":            "Tu invitacion ha expirado.",
            "cancelada":           "Tu invitacion fue cancelada.",
            "horario_invalido":    "Fuera del horario permitido.",
            "dia_no_permitido":    "Hoy no es un dia permitido para tu invitacion.",
            "fuera_de_periodo":    "Fuera del periodo de la invitacion.",
            "uuid_invalido":       "Beacon no reconocido.",
            "error_mqtt":          "Error al comunicarse con la barrera.",
            "error_configuracion": "Error de configuracion del sistema.",
        }
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=mensajes.get(resultado["motivo"], "Acceso denegado.")
        )

    return RespuestaAcceso(
        ok=True,
        puerta_nombre=resultado["puerta_nombre"],
        accion=resultado.get("accion", "entrada"),
        unidad_destino=resultado.get("unidad_destino"),
    )


@app.get("/acceso/log", response_model=list[LogAcceso], tags=["Acceso"])
async def log_accesos(
    limite: int = 50,
    membresia_id: str = None,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    mid = membresia_id or usuario.membresia_id
    return await listar_log_accesos(
        edificio_id=usuario.edificio_id,
        membresia_id=mid,
        limite=limite,
    )


@app.get("/acceso/puertas", tags=["Acceso"])
async def listar_puertas(usuario: UsuarioActual = Depends(get_usuario_actual)):
    return await obtener_puertas_edificio(usuario.edificio_id)


# ============================================================
#  DISPOSITIVOS
# ============================================================

@app.post("/dispositivos/push-token", tags=["Dispositivos"])
async def registrar_push_token(
    body: PushTokenRequest,
    usuario: UsuarioActual = Depends(get_usuario_actual),
):
    await guardar_push_token(
        numero_celular=usuario.numero_celular,
        token=body.token,
        plataforma=body.plataforma,
    )
    return {"ok": True}


# ============================================================
#  MEMBRESIAS
# ============================================================

@app.get("/membresias/mias", tags=["Membresias"])
async def mis_membresias(usuario: UsuarioActual = Depends(get_usuario_actual)):
    """Retorna las membresias del usuario actual — para selector de edificio en la app."""
    return usuario.membresias




# ============================================================
#  MI CUENTA
# ============================================================

@app.get("/cuenta/mia", tags=["Cuenta"])
async def mi_cuenta(usuario: UsuarioActual = Depends(get_usuario_actual)):
    from base_datos import obtener_membresias_usuario
    membresias = await obtener_membresias_usuario(usuario.numero_celular)
    return {
        "numero_celular": usuario.numero_celular,
        "nombre": usuario.membresias[0].edificio_nombre if usuario.membresias else None,
        "membresias": membresias,
    }


@app.patch("/cuenta/mia", tags=["Cuenta"])
async def actualizar_mi_cuenta(
    body: dict,
    usuario: UsuarioActual = Depends(get_usuario_actual),
):
    from base_datos import actualizar_nombre_usuario
    await actualizar_nombre_usuario(usuario.numero_celular, body.get("nombre", ""))
    return {"ok": True}


@app.get("/cuenta/cohabitantes", tags=["Cuenta"])
async def mis_cohabitantes(usuario: UsuarioActual = Depends(solo_propietario)):
    from base_datos import listar_cohabitantes
    return await listar_cohabitantes(usuario.numero_celular, usuario.membresia_id)


@app.post("/cuenta/cohabitantes", tags=["Cuenta"])
async def agregar_cohabitante(
    body: dict,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    from base_datos import agregar_cohabitante_bd, obtener_membresia_por_id
    numero = body.get("numero_celular", "").strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Numero de celular requerido")
    if numero == usuario.numero_celular:
        raise HTTPException(status_code=400, detail="No puedes agregarte a ti mismo")
    membresia = await obtener_membresia_por_id(usuario.membresia_id)
    if not membresia:
        raise HTTPException(status_code=400, detail="Membresia no encontrada")
    await agregar_cohabitante_bd(
        numero_celular=numero,
        edificio_id=membresia["edificio_id"],
        unidad=membresia["unidad"],
        nombre=body.get("nombre", ""),
    )
    return {"ok": True, "mensaje": "Cohabitante agregado correctamente"}


@app.delete("/cuenta/cohabitantes/{numero_celular}", tags=["Cuenta"])
async def eliminar_cohabitante(
    numero_celular: str,
    usuario: UsuarioActual = Depends(solo_propietario),
):
    from base_datos import eliminar_cohabitante_bd, obtener_membresia_por_id
    membresia = await obtener_membresia_por_id(usuario.membresia_id)
    if not membresia:
        raise HTTPException(status_code=400, detail="Membresia no encontrada")
    await eliminar_cohabitante_bd(
        numero_celular=numero_celular,
        edificio_id=membresia["edificio_id"],
        unidad=membresia["unidad"],
    )
    return {"ok": True}


# ============================================================
#  PIN DE USUARIO
# ============================================================

@app.post("/auth/pin/crear", tags=["Autenticacion"])
async def crear_pin(
    body: dict,
    usuario: UsuarioActual = Depends(get_usuario_actual),
):
    """Crea o actualiza el PIN del usuario."""
    from base_datos import establecer_pin
    pin = body.get("pin", "").strip()
    if len(pin) < 4 or len(pin) > 6:
        raise HTTPException(status_code=400, detail="El PIN debe tener entre 4 y 6 digitos")
    if not pin.isdigit():
        raise HTTPException(status_code=400, detail="El PIN debe contener solo numeros")
    await establecer_pin(usuario.numero_celular, pin, temporal=False)
    return {"ok": True, "mensaje": "PIN actualizado correctamente"}


@app.post("/auth/pin/verificar", response_model=TokenResponse, tags=["Autenticacion"])
async def login_con_pin(body: dict):
    """Login con numero de celular + PIN."""
    from base_datos import verificar_pin_usuario, obtener_perfil_usuario, tiene_pin
    numero = body.get("numero_celular", "").strip()
    pin = body.get("pin", "").strip()

    if not numero or not pin:
        raise HTTPException(status_code=400, detail="Numero y PIN requeridos")

    # Verificar PIN
    pin_valido = await verificar_pin_usuario(numero, pin)
    if not pin_valido:
        raise HTTPException(status_code=401, detail="Numero o PIN incorrecto")

    perfil_data = await obtener_perfil_usuario(numero)
    if not perfil_data:
        raise HTTPException(status_code=403, detail="Usuario no encontrado")

    # Verificar si PIN es temporal
    info_pin = await tiene_pin(numero)

    token = crear_jwt(
        numero_celular=numero,
        perfil=perfil_data["perfil"],
        edificio_id=perfil_data.get("edificio_id"),
        membresias=perfil_data.get("membresias", []),
    )

    return TokenResponse(
        access_token=token,
        perfil=perfil_data["perfil"],
        edificio_id=perfil_data.get("edificio_id"),
        nombre=perfil_data.get("nombre"),
        membresias=perfil_data.get("membresias", []),
    )


@app.get("/auth/pin/estado", tags=["Autenticacion"])
async def estado_pin(usuario: UsuarioActual = Depends(get_usuario_actual)):
    """Retorna si el usuario tiene PIN y si es temporal."""
    from base_datos import tiene_pin
    return await tiene_pin(usuario.numero_celular)

# ============================================================
#  HEALTHCHECK
# ============================================================

@app.get("/health", tags=["Sistema"])
async def health():
    return {
        "estado": "ok",
        "version": settings.APP_VERSION,
        "mqtt_conectado": mqtt_client._conectado,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
