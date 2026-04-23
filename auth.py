# ============================================================
#  auth.py — Autenticacion JWT + OTP SMS
#  JWT ahora incluye lista de membresias del usuario
# ============================================================

import random
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import get_settings
from modelos import UsuarioActual, MembresiaInfo

logger = logging.getLogger(__name__)
settings = get_settings()
security = HTTPBearer()

_otp_store: dict = {}


# ============================================================
#  OTP
# ============================================================

def generar_otp(numero_celular: str) -> str:
    codigo = str(random.randint(100000, 999999))
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRA_MINUTOS)
    _otp_store[numero_celular] = {"codigo": codigo, "expira": expira}
    logger.info("[OTP] Generado para %s (expira: %s)", numero_celular, expira)
    return codigo


async def enviar_otp_sms(numero_celular: str, codigo: str) -> bool:
    """Envia OTP via WhatsApp (n8n) o SMS (Twilio como fallback)"""
    
    # Intentar WhatsApp via n8n
    if settings.N8N_WEBHOOK_INVITACION:
        try:
            import httpx
            payload = {
                "evento": "otp",
                "numero_destinatario": numero_celular,
                "codigo": codigo,
                "mensaje": f"Tu código de acceso es: {codigo}. Válido por {settings.OTP_EXPIRA_MINUTOS} minutos."
            }
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    settings.N8N_WEBHOOK_INVITACION,
                    json=payload,
                    timeout=10.0
                )
                if response.status_code == 200:
                    logger.info("[OTP] Enviado via WhatsApp a %s", numero_celular)
                    return True
                else:
                    logger.warning("[OTP] Error WhatsApp, status: %s", response.status_code)
        except Exception as e:
            logger.error("[OTP] Error enviando WhatsApp: %s", e)
    
    # Fallback a Twilio SMS
    if settings.TWILIO_ACCOUNT_SID:
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=f"Tu codigo de acceso es: {codigo}. Valido por {settings.OTP_EXPIRA_MINUTOS} minutos.",
                from_=settings.TWILIO_NUMERO_ORIGEN,
                to=numero_celular
            )
            logger.info("[OTP] Enviado via SMS a %s", numero_celular)
            return True
        except Exception as e:
            logger.error("[OTP] Error al enviar SMS: %s", e)
    
    # Sin configuración, solo log
    logger.warning("[OTP] Ni WhatsApp ni Twilio configurados. Codigo para %s: %s", numero_celular, codigo)
    return True


def verificar_otp(numero_celular: str, codigo: str) -> bool:
    entrada = _otp_store.get(numero_celular)
    if not entrada:
        return False
    if datetime.now(timezone.utc) > entrada["expira"]:
        del _otp_store[numero_celular]
        return False
    if entrada["codigo"] != codigo:
        return False
    del _otp_store[numero_celular]
    return True


# ============================================================
#  JWT — ahora incluye membresias
# ============================================================

def crear_jwt(numero_celular: str, perfil: str, edificio_id: Optional[str], membresias: list) -> str:
    payload = {
        "sub": numero_celular,
        "perfil": perfil,
        "edificio_id": edificio_id,
        "membresias": membresias,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRA_HORAS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decodificar_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.warning("[JWT] Token expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("[JWT] Token invalido: %s", e)
        return None


# ============================================================
#  Dependencias FastAPI
# ============================================================

async def get_usuario_actual(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> UsuarioActual:
    payload = decodificar_jwt(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    membresias_raw = payload.get("membresias", [])
    membresias = [MembresiaInfo(**m) for m in membresias_raw] if membresias_raw else []

    # membresia_id activa: la primera de la lista por defecto
    membresia_id = membresias[0].membresia_id if membresias else None

    return UsuarioActual(
        numero_celular=payload["sub"],
        perfil=payload["perfil"],
        edificio_id=payload.get("edificio_id"),
        membresia_id=membresia_id,
        membresias=membresias,
    )


async def solo_propietario(
    usuario: UsuarioActual = Depends(get_usuario_actual)
) -> UsuarioActual:
    if usuario.perfil not in ("propietario", "administrador"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo propietarios o administradores")
    return usuario


async def solo_admin(
    usuario: UsuarioActual = Depends(get_usuario_actual)
) -> UsuarioActual:
    if usuario.perfil != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo administradores")
    return usuario
