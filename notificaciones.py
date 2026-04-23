# ============================================================
#  notificaciones.py — Notificaciones push y webhooks n8n
# ============================================================

import logging
from datetime import datetime
from typing import Optional

import httpx
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================
#  WEBHOOK N8N — dispara para todos los eventos
# ============================================================

async def disparar_webhook_n8n(payload: dict):
    """
    Dispara el webhook de n8n con el payload del evento.
    No falla si el webhook no está configurado o no responde.
    """
    if not settings.N8N_WEBHOOK_INVITACION:
        logger.info("[N8N] Webhook no configurado — saltando notificacion")
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.N8N_WEBHOOK_INVITACION,
                json=payload,
                timeout=10.0,
            )
            logger.info("[N8N] Webhook disparado — evento: %s | status: %s",
                        payload.get("evento"), response.status_code)
    except Exception as e:
        logger.warning("[N8N] Error al disparar webhook: %s", e)


async def notificar_invitacion_creada(invitacion: dict, nombre_propietario: str):
    """
    Notifica al invitado cuando el propietario crea una invitacion.
    n8n envia WhatsApp al numero_invitado con los detalles.
    """
    from base_datos import listar_invitaciones_invitado
    dias_texto = _dias_a_texto(invitacion.get("dias_permitidos", "1234567"))
    horario = "Todo el dia" if invitacion.get("todo_el_dia") else \
              f"{invitacion.get('hora_inicio', '00:00')} - {invitacion.get('hora_fin', '23:59')}"

    await disparar_webhook_n8n({
        "evento":            "invitacion_creada",
        "numero_destinatario": invitacion["numero_invitado"],
        "numero_propietario":  invitacion.get("numero_propietario", ""),
        "nombre_propietario":  nombre_propietario,
        "condominio":          invitacion.get("edificio_nombre", ""),
        "unidad_destino":      invitacion.get("unidad_destino", ""),
        "dias":                dias_texto,
        "horario":             horario,
        "hasta":               invitacion["fecha_hasta"].strftime("%d/%m/%Y")
                               if hasattr(invitacion["fecha_hasta"], "strftime")
                               else str(invitacion["fecha_hasta"])[:10],
        "link_app":            settings.APP_LINK,
    })


async def notificar_acceso(
    invitacion: dict,
    accion: str,
    timestamp: datetime,
):
    """
    Notifica al propietario cuando el invitado entra o sale.
    n8n envia WhatsApp al numero_propietario.
    """
    hora = timestamp.strftime("%H:%M")
    fecha = timestamp.strftime("%d/%m/%Y")

    await disparar_webhook_n8n({
        "evento":              f"invitado_{accion}",  # "invitado_entrada" | "invitado_salida"
        "numero_destinatario": invitacion.get("numero_propietario", ""),
        "numero_invitado":     invitacion["numero_invitado"],
        "unidad_destino":      invitacion.get("unidad_destino", ""),
        "condominio":          invitacion.get("edificio_nombre", ""),
        "accion":              accion,
        "hora":                hora,
        "fecha":               fecha,
        "topic_mqtt":          invitacion.get("topic_mqtt", ""),  # Agregar esta línea
    })


async def enviar_push_propietario(
    edificio_id: str,
    numero_invitado: str,
    puerta_nombre: str,
    timestamp: datetime,
):
    """Envia notificacion push al propietario (requiere build EAS)."""
    from base_datos import obtener_push_tokens_usuario, buscar_invitacion_activa_invitado
    invitacion = await buscar_invitacion_activa_invitado(numero_invitado, edificio_id)
    if not invitacion:
        return
    numero_propietario = invitacion.get("numero_propietario", "")
    if not numero_propietario:
        return
    tokens = await obtener_push_tokens_usuario(numero_propietario)
    if not tokens:
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=[{
                    "to": token,
                    "title": "Visita en puerta",
                    "body": f"{numero_invitado} acaba de ingresar por {puerta_nombre}",
                    "data": {"invitado": numero_invitado},
                } for token in tokens],
                timeout=10.0,
            )
    except Exception as e:
        logger.warning("[PUSH] Error al enviar notificacion: %s", e)


# ============================================================
#  HELPERS
# ============================================================

def _dias_a_texto(dias: str) -> str:
    if dias == "1234567": return "Todos los dias"
    if dias == "12345":   return "Lunes a Viernes"
    if dias == "67":      return "Sabado y Domingo"
    labels = {"1":"Lun","2":"Mar","3":"Mie","4":"Jue","5":"Vie","6":"Sab","7":"Dom"}
    return ", ".join(labels.get(d, d) for d in dias)
