# ============================================================
#  modelos.py — Schemas Pydantic (request / response)
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


# --- Auth ---

class OTPRequest(BaseModel):
    numero_celular: str = Field(..., example="+56912345678")

class OTPVerify(BaseModel):
    numero_celular: str = Field(..., example="+56912345678")
    codigo: str = Field(..., min_length=6, max_length=6, example="123456")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    perfil: Literal["propietario", "invitado"]
    edificio_id: Optional[str]
    nombre: Optional[str]


# --- Invitaciones ---

class InvitacionCreate(BaseModel):
    numero_invitado: str = Field(..., example="+56987654321")
    puerta_id: str = Field(..., example="puerta_1")
    fecha_desde: datetime
    fecha_hasta: datetime
    nota: Optional[str] = None

class InvitacionResponse(BaseModel):
    id: str
    numero_invitado: str
    puerta_id: str
    puerta_nombre: str
    uuid_ble: Optional[str] = None
    edificio_id: str
    fecha_desde: datetime
    fecha_hasta: datetime
    nota: Optional[str]
    estado: Literal["activa", "usada", "expirada", "cancelada"]
    creada_en: datetime

class InvitacionUpdate(BaseModel):
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    puerta_id: Optional[str] = None
    nota: Optional[str] = None


# --- Acceso ---

class SolicitudAcceso(BaseModel):
    uuid_ble: Optional[str] = Field(None, example="a1b2c3d4-e5f6-7890-abcd-ef1234567891")
    invitacion_id: Optional[str] = None  # Si la app lo conoce, acelera la busqueda
    # GPS opcional — solo para auditoria
    lat: Optional[float] = None
    lng: Optional[float] = None

class RespuestaAcceso(BaseModel):
    ok: bool
    puerta_nombre: Optional[str] = None
    motivo: Optional[str] = None  # Solo cuando ok=False
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class LogAcceso(BaseModel):
    id: str
    numero_invitado: str
    puerta_id: str
    puerta_nombre: str
    timestamp: datetime
    lat: Optional[float]
    lng: Optional[float]


# --- Dispositivos ---

class PushTokenRequest(BaseModel):
    token: str
    plataforma: Literal["ios", "android"]

class BeaconRegistro(BaseModel):
    puerta_id: str
    uuid_ble: str
    nombre: str


# --- Usuario (extraido del JWT) ---

class UsuarioActual(BaseModel):
    numero_celular: str
    perfil: Literal["propietario", "invitado"]
    edificio_id: Optional[str]
