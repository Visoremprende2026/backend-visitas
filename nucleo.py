# ============================================================
#  nucleo.py — Logica de negocio pura v2
#  Beacon unico + control de presencia + restricciones horarias
#  Usa membresia_id en lugar de numero_propietario
# ============================================================

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from config import get_settings
from mqtt_client import mqtt_client
from base_datos import (
    buscar_invitacion_activa_invitado,
    buscar_invitacion_por_id,
    registrar_acceso_bd,
    obtener_puerta_por_id,
    obtener_config_mqtt_edificio,
    actualizar_presencia,
)
from notificaciones import enviar_push_propietario, notificar_acceso

logger = logging.getLogger(__name__)
settings = get_settings()


def _validar_restricciones_horarias(invitacion: dict, ahora: datetime) -> Optional[str]:
    dia_semana = str(ahora.isoweekday())
    if dia_semana not in invitacion["dias_permitidos"]:
        logger.warning("[NUCLEO] Dia no permitido — %s | dia: %s", invitacion["numero_invitado"], dia_semana)
        return "dia_no_permitido"
    if invitacion["todo_el_dia"]:
        return None
    hora_actual = ahora.strftime("%H:%M")
    if not (invitacion["hora_inicio"] <= hora_actual <= invitacion["hora_fin"]):
        logger.warning("[NUCLEO] Fuera de horario — %s | hora: %s", invitacion["numero_invitado"], hora_actual)
        return "horario_invalido"
    return None


async def procesar_solicitud_acceso(
    numero_invitado: str,
    edificio_id: str,
    uuid_ble: Optional[str] = None,
    invitacion_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """
    Beacon unico — decide entrada o salida segun presencia.
    presencia == "fuera"  → abre barrera ENTRADA (puerta_id de la invitacion)
    presencia == "dentro" → abre barrera SALIDA  (segunda puerta del edificio)
    """
    ahora = datetime.now(ZoneInfo("America/Santiago"))
    ahora_naive = ahora.replace(tzinfo=None)

    # 1. Buscar invitacion activa
    if invitacion_id:
        invitacion = await buscar_invitacion_por_id(invitacion_id)
        if invitacion and invitacion["numero_invitado"] != numero_invitado:
            invitacion = None
    else:
        invitacion = await buscar_invitacion_activa_invitado(numero_invitado, edificio_id)

    if not invitacion:
        return {"ok": False, "motivo": "sin_invitacion"}

    if invitacion["estado"] == "cancelada":
        return {"ok": False, "motivo": "cancelada"}
    if invitacion["estado"] == "expirada":
        return {"ok": False, "motivo": "expirada"}

    # 2. Determinar accion segun presencia
    es_entrada = (invitacion["presencia"] == "fuera")

    # 3. Validar restricciones solo para entrada
    if es_entrada:
        fecha_desde = invitacion["fecha_desde"]
        fecha_hasta = invitacion["fecha_hasta"]
        
        tz_chile = ZoneInfo("America/Santiago")
        tz_utc = ZoneInfo("UTC")
        
        # Convertir fechas de BD (UTC) a Chile
        if fecha_desde.tzinfo:
            fd = fecha_desde.astimezone(tz_chile).replace(tzinfo=None)
        else:
            fd = fecha_desde.replace(tzinfo=tz_utc).astimezone(tz_chile).replace(tzinfo=None)
        
        if fecha_hasta.tzinfo:
            fh = fecha_hasta.astimezone(tz_chile).replace(tzinfo=None)
        else:
            fh = fecha_hasta.replace(tzinfo=tz_utc).astimezone(tz_chile).replace(tzinfo=None)
        
        if not (fd <= ahora_naive <= fh):
            logger.warning(f"[NUCLEO] Fuera de periodo — desde: {fd} | hasta: {fh} | ahora: {ahora_naive}")
            return {"ok": False, "motivo": "fuera_de_periodo"}
        
        motivo = _validar_restricciones_horarias(invitacion, ahora)
        if motivo:
            return {"ok": False, "motivo": motivo}
        
    # 4. Determinar puerta
    if es_entrada:
        puerta = await obtener_puerta_por_id(invitacion["puerta_id"])
        accion = "entrada"
        nueva_presencia = "dentro"
    else:
        config_edificio = settings.EDIFICIOS.get(edificio_id, {})
        puerta_salida = config_edificio.get("puertas", {}).get("puerta_2", {})
        puerta = {
            "id": "puerta-2",
            "nombre": puerta_salida.get("nombre", "Barrera salida"),
            "topic_mqtt": puerta_salida.get("topic_mqtt", "puerta/2/open"),
        }
        accion = "salida"
        nueva_presencia = "fuera"

    if not puerta:
        return {"ok": False, "motivo": "error_configuracion"}

    # 5. Publicar MQTT
    publicado = await mqtt_client.publicar_apertura(
        topic=puerta["topic_mqtt"],
        puerta_nombre=puerta["nombre"]
    )
    if not publicado:
        return {"ok": False, "motivo": "error_mqtt"}

    # 6. Actualizar presencia
    await actualizar_presencia(invitacion["id"], nueva_presencia)

    # 7. Registrar acceso
    await registrar_acceso_bd(
        invitacion_id=invitacion["id"],
        numero_invitado=numero_invitado,
        puerta_id=puerta["id"],
        edificio_id=edificio_id,
        accion=accion,
        timestamp=ahora,
        lat=lat,
        lng=lng,
    )

    # 8. Notificar propietario — push + webhook n8n
    if es_entrada:
        await enviar_push_propietario(
            edificio_id=edificio_id,
            numero_invitado=numero_invitado,
            puerta_nombre=puerta["nombre"],
            timestamp=ahora,
        )

    # Webhook n8n para entrada y salida
    await notificar_acceso(
        invitacion=invitacion,
        accion=accion,
        timestamp=ahora,
    )

    logger.info("[NUCLEO] %s — invitado: %s | edificio: %s", accion.upper(), numero_invitado, edificio_id)

    return {
        "ok": True,
        "puerta_nombre": puerta["nombre"],
        "accion": accion,
        "unidad_destino": invitacion.get("unidad_destino"),
    }
