99# ============================================================
#  mqtt_client.py — Cliente MQTT
#  Publica ordenes de apertura al EG118
# ============================================================

import paho.mqtt.client as mqtt
import logging
import asyncio
from datetime import datetime
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MQTTClient:
    """
    Cliente MQTT singleton que mantiene conexion persistente al broker.
    Usado por nucleo.py para publicar ordenes de apertura.
    """

    def __init__(self):
        self._client = mqtt.Client(client_id=settings.MQTT_CLIENT_ID)
        self._client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_publish    = self._on_publish
        self._conectado = False

    # ----------------------------------------------------------
    #  Callbacks internos
    # ----------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._conectado = True
            logger.info("[MQTT] Conectado al broker %s:%d", settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT)
        else:
            self._conectado = False
            logger.error("[MQTT] Error de conexion. Codigo: %d", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._conectado = False
        if rc != 0:
            logger.warning("[MQTT] Desconexion inesperada. Reconectando...")

    def _on_publish(self, client, userdata, mid):
        logger.info("[MQTT] Mensaje publicado. mid=%d", mid)

    # ----------------------------------------------------------
    #  Conexion
    # ----------------------------------------------------------

    def conectar(self):
        """Conecta al broker central e inicia el loop en hilo separado."""
        try:

            self._client.reconnect_delay_set(min_delay=1, max_delay=10)
            
            self._client.connect(
                settings.MQTT_BROKER_HOST,
                settings.MQTT_BROKER_PORT,
                keepalive=60
            )
            self._client.loop_start()
            logger.info("[MQTT] Cliente iniciado.")

        except Exception as e:
            logger.error("[MQTT] No se pudo conectar al broker %s:%d — %s",
                         settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, e)

    def desconectar(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("[MQTT] Cliente desconectado.")

    # ----------------------------------------------------------
    #  Publicacion
    # ----------------------------------------------------------

    async def publicar_apertura(self, topic: str, puerta_nombre: str) -> bool:
        """
        Publica la orden de apertura en el topic del EG118.
        Retorna True si el mensaje fue enviado, False si hubo error.
        """
        if not self._conectado:
            logger.warning("[MQTT] Sin conexion al broker. Intentando reconectar...")
            try:
                self._client.reconnect()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("[MQTT] Reconexion fallida: %s", e)
                return False

        payload = f'{{"accion":"abrir","puerta":"{puerta_nombre}","timestamp":"{datetime.utcnow().isoformat()}"}}'

        resultado = self._client.publish(
            topic=topic,
            payload=payload,
            qos=1,       # QoS 1: al menos una entrega confirmada
            retain=False # No retener — cada apertura es un evento nuevo
        )

        if resultado.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("[MQTT] Apertura publicada — topic: %s | puerta: %s", topic, puerta_nombre)
            return True
        else:
            logger.error("[MQTT] Error al publicar — rc: %d", resultado.rc)
            return False


# Instancia singleton — importar desde otros modulos
mqtt_client = MQTTClient()
