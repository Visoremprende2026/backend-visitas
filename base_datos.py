# ============================================================
#  base_datos.py — Modelo de datos v2
#  Cambios: tabla Membresia, unidad_destino en Invitacion,
#  mqtt_broker por Edificio, roles propietario/administrador
# ============================================================

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, String, DateTime, Boolean, Float, Text, ForeignKey, Index, Integer
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.future import select
from sqlalchemy import update

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    **({} if is_sqlite else {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
    })
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


# ============================================================
#  TABLAS
# ============================================================

class Edificio(Base):
    __tablename__ = "edificios"
    id                = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre            = Column(String(200), nullable=False)
    direccion         = Column(String(300))
    lat               = Column(Float)
    lng               = Column(Float)
    # MQTT por edificio
    mqtt_broker_host  = Column(String(200), default="localhost")
    mqtt_broker_port  = Column(Integer, default=1883)
    mqtt_username     = Column(String(100), default="")
    mqtt_password     = Column(String(100), default="")
    activo            = Column(Boolean, default=True)
    creado_en         = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    puertas           = relationship("Puerta", back_populates="edificio")
    membresias        = relationship("Membresia", back_populates="edificio")


class Puerta(Base):
    __tablename__ = "puertas"
    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    edificio_id = Column(String, ForeignKey("edificios.id"), nullable=False)
    nombre      = Column(String(100), nullable=False)
    topic_mqtt  = Column(String(200), nullable=False)
    uuid_ble    = Column(String(36), nullable=True)
    activa      = Column(Boolean, default=True)
    edificio    = relationship("Edificio", back_populates="puertas")
    __table_args__ = (Index("ix_puertas_edificio", "edificio_id"),)


class Usuario(Base):
    """Identidad global — sin perfil ni edificio fijo."""
    __tablename__ = "usuarios"
    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    numero_celular = Column(String(20), nullable=False, unique=True)
    nombre         = Column(String(200))
    pin            = Column(String(200), nullable=True)  # PIN hasheado
    pin_temporal   = Column(Boolean, default=True)       # True = debe cambiar el PIN
    activo         = Column(Boolean, default=True)
    creado_en      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    membresias     = relationship("Membresia", back_populates="usuario")
    push_tokens    = relationship("PushToken", back_populates="usuario")
    __table_args__ = (Index("ix_usuarios_numero", "numero_celular"),)


class Membresia(Base):
    """Vincula un usuario a un edificio con un rol y unidad especifica."""
    __tablename__ = "membresias"
    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id  = Column(String, ForeignKey("usuarios.id"), nullable=False)
    edificio_id = Column(String, ForeignKey("edificios.id"), nullable=False)
    rol         = Column(String(20), nullable=False)  # "propietario" | "administrador"
    unidad      = Column(String(50))                  # "Depto 301", "Casa 15", etc.
    activa      = Column(Boolean, default=True)
    creado_en   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    usuario     = relationship("Usuario", back_populates="membresias")
    edificio    = relationship("Edificio", back_populates="membresias")
    invitaciones= relationship("Invitacion", back_populates="membresia")
    __table_args__ = (
        Index("ix_membresias_usuario", "usuario_id"),
        Index("ix_membresias_edificio", "edificio_id"),
        Index("ix_membresias_numero_edificio", "usuario_id", "edificio_id"),
    )


class Invitacion(Base):
    __tablename__ = "invitaciones"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    membresia_id    = Column(String, ForeignKey("membresias.id"), nullable=False)  # propietario
    numero_invitado = Column(String(20), nullable=False)
    puerta_id       = Column(String, ForeignKey("puertas.id"), nullable=False)
    edificio_id     = Column(String, ForeignKey("edificios.id"), nullable=False)
    unidad_destino  = Column(String(50))              # depto al que se dirige el invitado
    fecha_desde     = Column(DateTime(timezone=True), nullable=False)
    fecha_hasta     = Column(DateTime(timezone=True), nullable=False)
    todo_el_dia     = Column(Boolean, default=False)
    hora_inicio     = Column(String(5), default="00:00")
    hora_fin        = Column(String(5), default="23:59")
    dias_permitidos = Column(String(7), default="1234567")
    presencia       = Column(String(10), default="fuera")
    nota            = Column(Text)
    estado          = Column(String(20), default="activa")
    creada_en       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actualizada_en  = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    membresia       = relationship("Membresia", back_populates="invitaciones")
    puerta          = relationship("Puerta")
    __table_args__ = (
        Index("ix_invitaciones_invitado", "numero_invitado"),
        Index("ix_invitaciones_membresia", "membresia_id"),
        Index("ix_invitaciones_edificio", "edificio_id"),
        Index("ix_invitaciones_estado", "estado"),
        Index("ix_invitaciones_acceso", "numero_invitado", "edificio_id", "estado"),
    )


class LogAcceso(Base):
    __tablename__ = "log_accesos"
    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    invitacion_id   = Column(String, ForeignKey("invitaciones.id"), nullable=False)
    numero_invitado = Column(String(20), nullable=False)
    puerta_id       = Column(String, ForeignKey("puertas.id"), nullable=False)
    edificio_id     = Column(String, ForeignKey("edificios.id"), nullable=False)
    accion          = Column(String(10), nullable=False)
    timestamp       = Column(DateTime(timezone=True), nullable=False)
    lat             = Column(Float)
    lng             = Column(Float)
    __table_args__ = (
        Index("ix_log_edificio_ts", "edificio_id", "timestamp"),
        Index("ix_log_invitado", "numero_invitado"),
    )


class PushToken(Base):
    __tablename__ = "push_tokens"
    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    usuario_id     = Column(String, ForeignKey("usuarios.id"), nullable=False)
    numero_celular = Column(String(20), nullable=False)
    token          = Column(String(500), nullable=False)
    plataforma     = Column(String(10), nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    usuario        = relationship("Usuario", back_populates="push_tokens")
    __table_args__ = (Index("ix_push_usuario", "usuario_id"),)


# ============================================================
#  INICIALIZACION
# ============================================================

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[BD] Tablas verificadas/creadas")


# ============================================================
#  HELPERS
# ============================================================

def _invitacion_a_dict(inv: Invitacion, puerta: Puerta, membresia: Membresia = None) -> dict:
    return {
        "id": inv.id,
        "membresia_id": inv.membresia_id,
        "numero_propietario": membresia.usuario.numero_celular if membresia and membresia.usuario else "",
        "nombre_propietario": membresia.usuario.nombre if membresia and membresia.usuario else "",
        "unidad_propietario": membresia.unidad if membresia else "",
        "numero_invitado": inv.numero_invitado,
        "puerta_id": inv.puerta_id,
        "puerta_nombre": puerta.nombre if puerta else "",
        "topic_mqtt": puerta.topic_mqtt if puerta else None,  # Agregar esta línea
        "uuid_ble": puerta.uuid_ble if puerta else None,
        "edificio_id": inv.edificio_id,
        "unidad_destino": inv.unidad_destino,
        "fecha_desde": inv.fecha_desde,
        "fecha_hasta": inv.fecha_hasta,
        "todo_el_dia": inv.todo_el_dia,
        "hora_inicio": inv.hora_inicio,
        "hora_fin": inv.hora_fin,
        "dias_permitidos": inv.dias_permitidos,
        "presencia": inv.presencia,
        "nota": inv.nota,
        "estado": inv.estado,
        "creada_en": inv.creada_en,
    }


# ============================================================
#  USUARIOS Y MEMBRESIAS
# ============================================================

async def obtener_usuario_por_numero(numero_celular: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Usuario).where(
                Usuario.numero_celular == numero_celular,
                Usuario.activo == True
            )
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario:
            return None
        return {"id": usuario.id, "nombre": usuario.nombre, "numero_celular": usuario.numero_celular}


async def obtener_membresias_usuario(numero_celular: str) -> list:
    """Retorna todas las membresías activas del usuario con su edificio."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Membresia, Edificio, Usuario)
            .join(Usuario, Membresia.usuario_id == Usuario.id)
            .join(Edificio, Membresia.edificio_id == Edificio.id)
            .where(
                Usuario.numero_celular == numero_celular,
                Usuario.activo == True,
                Membresia.activa == True,
            )
        )
        return [
            {
                "membresia_id": m.id,
                "edificio_id": m.edificio_id,
                "edificio_nombre": e.nombre,
                "rol": m.rol,
                "unidad": m.unidad,
            }
            for m, e, u in resultado.all()
        ]


async def obtener_perfil_usuario(numero_celular: str) -> Optional[dict]:
    """
    Para el JWT: retorna el perfil del usuario.
    Si tiene membresías → propietario/administrador.
    Si no tiene → invitado (puede recibir invitaciones).
    """
    membresias = await obtener_membresias_usuario(numero_celular)

    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular, Usuario.activo == True)
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario:
            return None

    if not membresias:
        # Sin membresías — es invitado
        return {
            "perfil": "invitado",
            "edificio_id": None,
            "nombre": usuario.nombre,
            "membresias": [],
        }

    # Determinar perfil principal (admin tiene prioridad)
    roles = [m["rol"] for m in membresias]
    perfil = "administrador" if "administrador" in roles else "propietario"

    return {
        "perfil": perfil,
        "edificio_id": membresias[0]["edificio_id"],  # edificio principal
        "nombre": usuario.nombre,
        "membresias": membresias,
    }


async def obtener_membresia_por_id(membresia_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        m = await session.get(Membresia, membresia_id)
        if not m:
            return None
        e = await session.get(Edificio, m.edificio_id)
        u = await session.get(Usuario, m.usuario_id)
        return {
            "id": m.id,
            "usuario_id": m.usuario_id,
            "numero_celular": u.numero_celular if u else "",
            "nombre": u.nombre if u else "",
            "edificio_id": m.edificio_id,
            "edificio_nombre": e.nombre if e else "",
            "rol": m.rol,
            "unidad": m.unidad,
        }


async def obtener_membresia_activa(numero_celular: str, edificio_id: str) -> Optional[dict]:
    """Obtiene la membresía de un usuario en un edificio específico."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Membresia, Usuario)
            .join(Usuario, Membresia.usuario_id == Usuario.id)
            .where(
                Usuario.numero_celular == numero_celular,
                Membresia.edificio_id == edificio_id,
                Membresia.activa == True,
            )
        )
        fila = resultado.first()
        if not fila:
            return None
        m, u = fila
        return {
            "id": m.id,
            "usuario_id": m.usuario_id,
            "numero_celular": u.numero_celular,
            "nombre": u.nombre,
            "edificio_id": m.edificio_id,
            "rol": m.rol,
            "unidad": m.unidad,
        }


# ============================================================
#  PUERTAS
# ============================================================

async def obtener_puerta_por_uuid(uuid_ble: Optional[str], edificio_id: str) -> Optional[dict]:
    if not uuid_ble:
        return None
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Puerta).where(
                Puerta.uuid_ble == uuid_ble,
                Puerta.edificio_id == edificio_id,
                Puerta.activa == True,
            )
        )
        puerta = resultado.scalar_one_or_none()
        if not puerta:
            return None
        return {"id": puerta.id, "nombre": puerta.nombre, "topic_mqtt": puerta.topic_mqtt, "uuid_ble": puerta.uuid_ble}


async def obtener_puerta_por_id(puerta_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        puerta = await session.get(Puerta, puerta_id)
        if not puerta:
            return None
        return {"id": puerta.id, "nombre": puerta.nombre, "topic_mqtt": puerta.topic_mqtt, "uuid_ble": puerta.uuid_ble}


async def obtener_puertas_edificio(edificio_id: str) -> list:
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Puerta).where(Puerta.edificio_id == edificio_id, Puerta.activa == True).order_by(Puerta.nombre)
        )
        return [{"id": p.id, "nombre": p.nombre, "uuid_ble": p.uuid_ble} for p in resultado.scalars().all()]


async def obtener_config_mqtt_edificio(edificio_id: str) -> Optional[dict]:
    """Retorna la configuración MQTT específica del edificio."""
    async with AsyncSessionLocal() as session:
        e = await session.get(Edificio, edificio_id)
        if not e:
            return None
        return {
            "host": e.mqtt_broker_host,
            "port": e.mqtt_broker_port,
            "username": e.mqtt_username,
            "password": e.mqtt_password,
        }


# ============================================================
#  INVITACIONES
# ============================================================

async def crear_invitacion_bd(
    membresia_id, numero_invitado, puerta_id, edificio_id,
    unidad_destino, fecha_desde, fecha_hasta,
    todo_el_dia=False, hora_inicio="00:00", hora_fin="23:59",
    dias_permitidos="1234567", nota=None,
) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        inv = Invitacion(
            id=str(uuid.uuid4()),
            membresia_id=membresia_id,
            numero_invitado=numero_invitado,
            puerta_id=puerta_id,
            edificio_id=edificio_id,
            unidad_destino=unidad_destino,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            todo_el_dia=todo_el_dia,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            dias_permitidos=dias_permitidos,
            presencia="fuera",
            nota=nota,
            estado="activa",
        )
        session.add(inv)
        await session.commit()
        await session.refresh(inv)
        puerta = await session.get(Puerta, puerta_id)
        membresia = await session.get(Membresia, membresia_id)
        if membresia:
            await session.refresh(membresia, ["usuario"])
        return _invitacion_a_dict(inv, puerta, membresia)


async def obtener_invitacion(invitacion_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        inv = await session.get(Invitacion, invitacion_id)
        if not inv:
            return None
        puerta = await session.get(Puerta, inv.puerta_id)
        membresia = await session.get(Membresia, inv.membresia_id)
        if membresia:
            await session.refresh(membresia, ["usuario"])
        return _invitacion_a_dict(inv, puerta, membresia)


async def listar_invitaciones_propietario(membresia_id: str, estado="todas") -> list:
    """Lista invitaciones creadas por una membresía específica."""
    async with AsyncSessionLocal() as session:
        query = select(Invitacion, Puerta).join(
            Puerta, Invitacion.puerta_id == Puerta.id
        ).where(Invitacion.membresia_id == membresia_id)
        if estado != "todas":
            query = query.where(Invitacion.estado == estado)
        resultado = await session.execute(query.order_by(Invitacion.creada_en.desc()))
        membresia = await session.get(Membresia, membresia_id)
        if membresia:
            await session.refresh(membresia, ["usuario"])
        return [_invitacion_a_dict(inv, puerta, membresia) for inv, puerta in resultado.all()]


async def listar_invitaciones_invitado(numero_invitado: str, ahora: datetime) -> list:
    """Lista invitaciones vigentes donde este número es el invitado."""
    ahora_naive = ahora.replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Invitacion, Puerta, Membresia, Edificio)
            .join(Puerta, Invitacion.puerta_id == Puerta.id)
            .join(Membresia, Invitacion.membresia_id == Membresia.id)
            .join(Edificio, Invitacion.edificio_id == Edificio.id)
            .where(
                Invitacion.numero_invitado == numero_invitado,
                Invitacion.estado == "activa",
            ).order_by(Invitacion.fecha_hasta)
        )
        resultado_filtrado = []
        for inv, puerta, membresia, edificio in resultado.all():
            fd = inv.fecha_desde.replace(tzinfo=None) if inv.fecha_desde.tzinfo else inv.fecha_desde
            fh = inv.fecha_hasta.replace(tzinfo=None) if inv.fecha_hasta.tzinfo else inv.fecha_hasta
            if fd <= ahora_naive <= fh:
                await session.refresh(membresia, ["usuario"])
                d = _invitacion_a_dict(inv, puerta, membresia)
                d["edificio_nombre"] = edificio.nombre
                resultado_filtrado.append(d)
        return resultado_filtrado


async def buscar_invitacion_activa_invitado(numero_invitado: str, edificio_id: str) -> Optional[dict]:
    ahora = datetime.now(timezone.utc)
    ahora_naive = ahora.replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Invitacion, Puerta, Membresia)
            .join(Puerta, Invitacion.puerta_id == Puerta.id)
            .join(Membresia, Invitacion.membresia_id == Membresia.id)
            .where(
                Invitacion.numero_invitado == numero_invitado,
                Invitacion.edificio_id == edificio_id,
                Invitacion.estado == "activa",
            ).limit(1)
        )
        fila = resultado.first()
        if not fila:
            return None
        inv, puerta, membresia = fila
        fd = inv.fecha_desde.replace(tzinfo=None) if inv.fecha_desde.tzinfo else inv.fecha_desde
        fh = inv.fecha_hasta.replace(tzinfo=None) if inv.fecha_hasta.tzinfo else inv.fecha_hasta
        if not (fd <= ahora_naive <= fh):
            return None
        await session.refresh(membresia, ["usuario"])
        return _invitacion_a_dict(inv, puerta, membresia)


async def buscar_invitacion_por_id(invitacion_id: str) -> Optional[dict]:
    return await obtener_invitacion(invitacion_id)


async def actualizar_presencia(invitacion_id: str, presencia: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion).where(Invitacion.id == invitacion_id)
            .values(presencia=presencia, actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()


async def actualizar_invitacion_bd(invitacion_id, campos) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion).where(Invitacion.id == invitacion_id)
            .values(**campos, actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()
        return await obtener_invitacion(invitacion_id)


async def cancelar_invitacion_bd(invitacion_id):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion).where(Invitacion.id == invitacion_id)
            .values(estado="cancelada", actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()


# ============================================================
#  LOG DE ACCESOS
# ============================================================

async def registrar_acceso_bd(invitacion_id, numero_invitado, puerta_id, edificio_id, accion, timestamp, lat=None, lng=None):
    async with AsyncSessionLocal() as session:
        session.add(LogAcceso(
            id=str(uuid.uuid4()),
            invitacion_id=invitacion_id,
            numero_invitado=numero_invitado,
            puerta_id=puerta_id,
            edificio_id=edificio_id,
            accion=accion,
            timestamp=timestamp,
            lat=lat,
            lng=lng,
        ))
        await session.commit()


async def listar_log_accesos(edificio_id: str, membresia_id: str, limite=50) -> list:
    async with AsyncSessionLocal() as session:
        subq = select(Invitacion.id).where(Invitacion.membresia_id == membresia_id).scalar_subquery()
        resultado = await session.execute(
            select(LogAcceso, Puerta).join(Puerta, LogAcceso.puerta_id == Puerta.id)
            .where(LogAcceso.invitacion_id.in_(subq))
            .order_by(LogAcceso.timestamp.desc()).limit(limite)
        )
        return [
            {
                "id": log.id,
                "numero_invitado": log.numero_invitado,
                "puerta_id": log.puerta_id,
                "puerta_nombre": puerta.nombre,
                "accion": log.accion,
                "timestamp": log.timestamp,
                "lat": log.lat,
                "lng": log.lng,
            }
            for log, puerta in resultado.all()
        ]


# ============================================================
#  PUSH TOKENS
# ============================================================

async def guardar_push_token(numero_celular: str, token: str, plataforma: str):
    async with AsyncSessionLocal() as session:
        usuario_res = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular)
        )
        usuario = usuario_res.scalar_one_or_none()
        if not usuario:
            return

        resultado = await session.execute(
            select(PushToken).where(
                PushToken.usuario_id == usuario.id,
                PushToken.plataforma == plataforma,
            )
        )
        existente = resultado.scalar_one_or_none()
        if existente:
            existente.token = token
            existente.actualizado_en = datetime.now(timezone.utc)
        else:
            session.add(PushToken(
                usuario_id=usuario.id,
                numero_celular=numero_celular,
                token=token,
                plataforma=plataforma,
            ))
        await session.commit()


async def obtener_push_tokens_usuario(numero_celular: str) -> list:
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(PushToken.token).where(PushToken.numero_celular == numero_celular)
        )
        return [row[0] for row in resultado.all()]
    

# ============================================================
#  ADMINISTRADOR
# ============================================================

async def listar_todas_invitaciones_edificio(edificio_id: str, estado: str = "activa") -> list:
    """Lista todas las invitaciones del edificio para el administrador."""
    async with AsyncSessionLocal() as session:
        query = select(Invitacion, Puerta, Membresia).join(
            Puerta, Invitacion.puerta_id == Puerta.id
        ).join(
            Membresia, Invitacion.membresia_id == Membresia.id
        ).where(
            Invitacion.edificio_id == edificio_id,
        )
        if estado != "todas":
            query = query.where(Invitacion.estado == estado)
        query = query.order_by(Invitacion.creada_en.desc())
        resultado = await session.execute(query)
        filas = resultado.all()
        result = []
        for inv, puerta, membresia in filas:
            await session.refresh(membresia, ["usuario"])
            result.append(_invitacion_a_dict(inv, puerta, membresia))
        return result


async def listar_log_edificio_completo(edificio_id: str, limite: int = 100) -> list:
    """Historial completo de accesos del edificio para el administrador."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(LogAcceso, Puerta).join(
                Puerta, LogAcceso.puerta_id == Puerta.id
            ).where(
                LogAcceso.edificio_id == edificio_id
            ).order_by(LogAcceso.timestamp.desc())
            .limit(limite)
        )
        return [
            {
                "id": log.id,
                "numero_invitado": log.numero_invitado,
                "puerta_id": log.puerta_id,
                "puerta_nombre": puerta.nombre,
                "accion": log.accion,
                "timestamp": log.timestamp,
                "lat": log.lat,
                "lng": log.lng,
            }
            for log, puerta in resultado.all()
        ]


async def listar_propietarios_edificio(edificio_id: str) -> list:
    """Lista todos los propietarios activos del edificio con sus unidades."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Membresia, Usuario).join(
                Usuario, Membresia.usuario_id == Usuario.id
            ).where(
                Membresia.edificio_id == edificio_id,
                Membresia.rol == "propietario",
                Membresia.activa == True,
            ).order_by(Membresia.unidad)
        )
        return [
            {
                "membresia_id": m.id,
                "nombre": u.nombre,
                "numero_celular": u.numero_celular,
                "unidad": m.unidad,
                "rol": m.rol,
            }
            for m, u in resultado.all()
        ]

async def actualizar_nombre_usuario(numero_celular: str, nombre: str):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Usuario)
            .where(Usuario.numero_celular == numero_celular)
            .values(nombre=nombre)
        )
        await session.commit()


async def listar_cohabitantes(numero_celular: str, membresia_id: str) -> list:
    """Lista los cohabitantes de la misma unidad, excluyendo al propietario actual."""
    membresia = await obtener_membresia_por_id(membresia_id)
    if not membresia:
        return []
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Membresia, Usuario)
            .join(Usuario, Membresia.usuario_id == Usuario.id)
            .where(
                Membresia.edificio_id == membresia["edificio_id"],
                Membresia.unidad == membresia["unidad"],
                Membresia.rol == "propietario",
                Membresia.activa == True,
                Usuario.numero_celular != numero_celular,
            )
        )
        return [
            {
                "numero_celular": u.numero_celular,
                "nombre": u.nombre,
                "unidad": m.unidad,
                "membresia_id": m.id,
            }
            for m, u in resultado.all()
        ]


async def agregar_cohabitante_bd(numero_celular: str, edificio_id: str, unidad: str, nombre: str = ""):
    """Crea usuario si no existe y le agrega membresía como propietario en la unidad."""
    async with AsyncSessionLocal() as session:
        # Buscar o crear usuario
        resultado = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular)
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario:
            usuario = Usuario(
                id=str(uuid.uuid4()),
                numero_celular=numero_celular,
                nombre=nombre or None,
            )
            session.add(usuario)
            await session.flush()

        # Verificar si ya tiene membresía en esa unidad
        resultado = await session.execute(
            select(Membresia).where(
                Membresia.usuario_id == usuario.id,
                Membresia.edificio_id == edificio_id,
                Membresia.unidad == unidad,
            )
        )
        membresia_existente = resultado.scalar_one_or_none()
        if membresia_existente:
            # Reactivar si estaba inactiva
            membresia_existente.activa = True
        else:
            session.add(Membresia(
                id=str(uuid.uuid4()),
                usuario_id=usuario.id,
                edificio_id=edificio_id,
                rol="propietario",
                unidad=unidad,
                activa=True,
            ))
        await session.commit()


async def eliminar_cohabitante_bd(numero_celular: str, edificio_id: str, unidad: str):
    """Desactiva la membresía del cohabitante en la unidad."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Membresia, Usuario)
            .join(Usuario, Membresia.usuario_id == Usuario.id)
            .where(
                Usuario.numero_celular == numero_celular,
                Membresia.edificio_id == edificio_id,
                Membresia.unidad == unidad,
                Membresia.activa == True,
            )
        )
        fila = resultado.first()
        if fila:
            m, u = fila
            m.activa = False
            await session.commit()

import hashlib

def _hashear_pin(pin: str) -> str:
    """Hashea el PIN con SHA256."""
    return hashlib.sha256(pin.encode()).hexdigest()

def _verificar_pin(pin: str, pin_hasheado: str) -> bool:
    return _hashear_pin(pin) == pin_hasheado

async def establecer_pin(numero_celular: str, pin: str, temporal: bool = False):
    """Establece o actualiza el PIN del usuario."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular)
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario:
            return False
        usuario.pin = _hashear_pin(pin)
        usuario.pin_temporal = temporal
        await session.commit()
        return True

async def verificar_pin_usuario(numero_celular: str, pin: str) -> bool:
    """Verifica el PIN del usuario."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular)
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario or not usuario.pin:
            return False
        return _verificar_pin(pin, usuario.pin)

async def tiene_pin(numero_celular: str) -> dict:
    """Retorna si el usuario tiene PIN y si es temporal."""
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Usuario).where(Usuario.numero_celular == numero_celular)
        )
        usuario = resultado.scalar_one_or_none()
        if not usuario:
            return {"tiene_pin": False, "pin_temporal": False}
        return {
            "tiene_pin": usuario.pin is not None,
            "pin_temporal": usuario.pin_temporal or False,
        }