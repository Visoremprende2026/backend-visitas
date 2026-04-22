# ============================================================
#  nucleo.py — Logica de negocio pura
#  Sin saber nada de HTTP, WhatsApp ni MQTT directamente.
#  Usado tanto por el API (FastAPI) como por el adaptador WhatsApp.
# ============================================================

import logging
from datetime import datetime, timezone
from typing import Optional

from config import get_settings
from mqtt_client import mqtt_client
from base_datos import (
    buscar_invitacion_por_uuid_ble,
    buscar_invitacion_por_id,
    registrar_acceso_bd,
    obtener_puerta_por_uuid,
    marcar_invitacion_usada,
)
from notificaciones import enviar_push_propietario

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================
#  Funcion principal — llamada desde el API y desde WhatsApp
# ============================================================

async def procesar_solicitud_acceso(
    numero_invitado: str,
    edificio_id: str,
    uuid_ble: str,
    invitacion_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """
    Valida la solicitud de acceso y dispara la apertura si todo es correcto.

    Retorna:
        {"ok": True,  "puerta_nombre": "Entrada principal"}
        {"ok": False, "motivo": "sin_invitacion" | "expirada" | "uuid_invalido" | "horario_invalido" | "error_mqtt"}
    """

    ahora = datetime.now(timezone.utc)

    # ----------------------------------------------------------
    # 1. Identificar la puerta por UUID BLE
    # ----------------------------------------------------------
    puerta = await obtener_puerta_por_uuid(uuid_ble, edificio_id)
    if not puerta:
        logger.warning("[NUCLEO] UUID BLE no reconocido: %s | edificio: %s", uuid_ble, edificio_id)
        return {"ok": False, "motivo": "uuid_invalido"}

    # ----------------------------------------------------------
    # 2. Buscar invitacion vigente
    # ----------------------------------------------------------
    if invitacion_id:
        # La app ya conoce el ID — busqueda rapida
        invitacion = await buscar_invitacion_por_id(invitacion_id)
        # Verificar que la invitacion pertenece al invitado correcto
        if invitacion and invitacion["numero_invitado"] != numero_invitado:
            invitacion = None
    else:
        # Buscar por numero de invitado + UUID BLE
        invitacion = await buscar_invitacion_por_uuid_ble(
            numero_invitado=numero_invitado,
            puerta_id=puerta["id"],
            edificio_id=edificio_id,
        )

    if not invitacion:
        logger.warning("[NUCLEO] Sin invitacion — invitado: %s | puerta: %s", numero_invitado, puerta["id"])
        return {"ok": False, "motivo": "sin_invitacion"}

    # ----------------------------------------------------------
    # 3. Validar estado de la invitacion
    # ----------------------------------------------------------
    if invitacion["estado"] == "cancelada":
        return {"ok": False, "motivo": "cancelada"}

    if invitacion["estado"] == "expirada":
        return {"ok": False, "motivo": "expirada"}

    # ----------------------------------------------------------
    # 4. Validar ventana horaria
    # ----------------------------------------------------------
    fecha_desde = invitacion["fecha_desde"]
    fecha_hasta = invitacion["fecha_hasta"]

    # Normalizar fechas a naive (sin timezone) para comparar
    ahora_naive = ahora.replace(tzinfo=None)
    fecha_desde_naive = fecha_desde.replace(tzinfo=None) if fecha_desde.tzinfo else fecha_desde
    fecha_hasta_naive = fecha_hasta.replace(tzinfo=None) if fecha_hasta.tzinfo else fecha_hasta

    if not (fecha_desde_naive <= ahora_naive <= fecha_hasta_naive):
        logger.warning(
           "[NUCLEO] Fuera de horario — invitado: %s | desde: %s | hasta: %s | ahora: %s",
          numero_invitado, fecha_desde, fecha_hasta, ahora
        )
        return {"ok": False, "motivo": "horario_invalido"}
    # ----------------------------------------------------------
    # 5. Publicar MQTT al EG118
    # ----------------------------------------------------------
    topic = puerta["topic_mqtt"]
    publicado = await mqtt_client.publicar_apertura(
        topic=topic,
        puerta_nombre=puerta["nombre"]
    )

    if not publicado:
        logger.error("[NUCLEO] Fallo al publicar MQTT — topic: %s", topic)
        return {"ok": False, "motivo": "error_mqtt"}

    # ----------------------------------------------------------
    # 6. Registrar el acceso en la BD
    # ----------------------------------------------------------
    registrar_acceso_bd(
        invitacion_id=invitacion["id"],
        numero_invitado=numero_invitado,
        puerta_id=puerta["id"],
        edificio_id=edificio_id,
        timestamp=ahora,
        lat=lat,
        lng=lng,
    )

    # Marcar invitacion como usada (opcional — solo si es de un solo uso)
    # marcar_invitacion_usada(invitacion["id"])

    # ----------------------------------------------------------
    # 7. Notificar al propietario via push
    # ----------------------------------------------------------
    await enviar_push_propietario(
        edificio_id=edificio_id,
        numero_invitado=numero_invitado,
        puerta_nombre=puerta["nombre"],
        timestamp=ahora,
    )

    logger.info(
        "[NUCLEO] Acceso autorizado — invitado: %s | puerta: %s | edificio: %s",
        numero_invitado, puerta["nombre"], edificio_id
    )

    return {"ok": True, "puerta_nombre": puerta["nombre"]}
