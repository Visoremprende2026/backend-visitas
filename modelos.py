# ============================================================
#  modelos.py — Schemas Pydantic v2
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from datetime import datetime


# --- Auth ---

class OTPRequest(BaseModel):
    numero_celular: str = Field(..., example="+56912345678")

class OTPVerify(BaseModel):
    numero_celular: str = Field(..., example="+56912345678")
    codigo: str = Field(..., min_length=6, max_length=6, example="123456")

class MembresiaInfo(BaseModel):
    membresia_id: str
    edificio_id: str
    edificio_nombre: str
    rol: Literal["propietario", "administrador"]
    unidad: Optional[str]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    perfil: Literal["propietario", "administrador", "invitado"]
    edificio_id: Optional[str]
    nombre: Optional[str]
    membresias: List[MembresiaInfo] = []


# --- Invitaciones ---

class InvitacionCreate(BaseModel):
    membresia_id: str                              # membresia del propietario que crea
    numero_invitado: str = Field(..., example="+56987654321")
    puerta_id: str
    unidad_destino: Optional[str] = None           # depto al que se dirige el invitado
    fecha_desde: datetime
    fecha_hasta: datetime
    todo_el_dia: bool = False
    hora_inicio: str = "00:00"
    hora_fin: str = "23:59"
    dias_permitidos: str = "1234567"
    nota: Optional[str] = None

class InvitacionResponse(BaseModel):
    id: str
    membresia_id: str
    numero_propietario: str
    nombre_propietario: Optional[str]
    unidad_propietario: Optional[str]
    numero_invitado: str
    puerta_id: str
    puerta_nombre: str
    uuid_ble: Optional[str] = None
    edificio_id: str
    edificio_nombre: Optional[str] = None
    unidad_destino: Optional[str]
    fecha_desde: datetime
    fecha_hasta: datetime
    todo_el_dia: bool
    hora_inicio: str
    hora_fin: str
    dias_permitidos: str
    presencia: str
    nota: Optional[str]
    estado: Literal["activa", "usada", "expirada", "cancelada"]
    creada_en: datetime

class InvitacionUpdate(BaseModel):
    fecha_desde: Optional[datetime] = None
    fecha_hasta: Optional[datetime] = None
    puerta_id: Optional[str] = None
    unidad_destino: Optional[str] = None
    todo_el_dia: Optional[bool] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    dias_permitidos: Optional[str] = None
    nota: Optional[str] = None


# --- Acceso ---

class SolicitudAcceso(BaseModel):
    uuid_ble: Optional[str] = Field(None, example="a1b2c3d4-e5f6-7890-abcd-ef1234567891")
    invitacion_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class RespuestaAcceso(BaseModel):
    ok: bool
    puerta_nombre: Optional[str] = None
    accion: Optional[str] = None
    unidad_destino: Optional[str] = None
    motivo: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class LogAcceso(BaseModel):
    id: str
    numero_invitado: str
    puerta_id: str
    puerta_nombre: str
    accion: str
    timestamp: datetime
    lat: Optional[float]
    lng: Optional[float]


# --- Dispositivos ---

class PushTokenRequest(BaseModel):
    token: str
    plataforma: Literal["ios", "android"]


# --- Usuario actual (del JWT) ---

class UsuarioActual(BaseModel):
    numero_celular: str
    perfil: Literal["propietario", "administrador", "invitado"]
    edificio_id: Optional[str]
    membresia_id: Optional[str] = None   # membresia activa seleccionada
    membresias: List[MembresiaInfo] = []
