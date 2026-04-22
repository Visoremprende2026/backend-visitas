# ============================================================
#  config.py — Configuracion centralizada v2
# ============================================================

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    # --- API ---
    APP_NAME: str = "Sistema de Visitas"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    APP_LINK: str = "https://tuapp.cl"

    # --- JWT ---
    JWT_SECRET: str = "cambiar_por_secreto_seguro_en_produccion"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRA_HORAS: int = 24 * 7

    # --- OTP SMS (Twilio) ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_NUMERO_ORIGEN: str = "+56900000000"
    OTP_EXPIRA_MINUTOS: int = 5

    # --- Base de datos ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./visitas.db"

    # --- MQTT broker central ---
    MQTT_BROKER_HOST: str = "212.85.21.160"
    MQTT_BROKER_PORT: int = 1883
    MQTT_USERNAME: str = "Mqtt"
    MQTT_PASSWORD: str = "Mqtt.2026"
    MQTT_CLIENT_ID: str = "backend_api_2"

    # --- n8n Webhook para WhatsApp ---
    N8N_WEBHOOK_INVITACION: str = ""   # URL del webhook de n8n

    # --- Edificios (configuracion inicial — en produccion viene de la BD) ---
    EDIFICIOS: dict = {
        "edificio-1": {
            "nombre": "Condominio Las Condes",
            "lat": -33.4167,
            "lng": -70.6062,
            "mqtt_broker_host": "localhost",
            "mqtt_broker_port": 1883,
            "puertas": {
                "puerta_1": {
                    "nombre": "Barrera entrada",
                    "topic_mqtt": "edificio-1/puerta/1/open",
                    "uuid_ble": "01122334-4556-6778-899a-abbccddeeff5",
                },
                "puerta_2": {
                    "nombre": "Barrera salida",
                    "topic_mqtt": "edificio-1/puerta/2/open",
                    "uuid_ble": "01122334-4556-6778-899a-abbccddeeff0",
                },
            },
        }
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
