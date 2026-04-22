# ============================================================
#  base_datos.py — Acceso a base de datos
#  Motor: SQLAlchemy 2.0 async + asyncpg (PostgreSQL) o aiosqlite (SQLite)
#  Para desarrollo: sqlite+aiosqlite:///./visitas.db
#  Para produccion: postgresql+asyncpg://user:pass@host/db
# ============================================================

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, String, DateTime, Boolean, Float, Text, ForeignKey, Index
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
#  MODELOS DE TABLAS
# ============================================================

class Edificio(Base):
    __tablename__ = "edificios"
    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre     = Column(String(200), nullable=False)
    direccion  = Column(String(300))
    lat        = Column(Float)
    lng        = Column(Float)
    activo     = Column(Boolean, default=True)
    creado_en  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    puertas    = relationship("Puerta", back_populates="edificio")
    usuarios   = relationship("Usuario", back_populates="edificio")


class Puerta(Base):
    __tablename__ = "puertas"
    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    edificio_id = Column(String, ForeignKey("edificios.id"), nullable=False)
    nombre      = Column(String(100), nullable=False)
    topic_mqtt  = Column(String(200), nullable=False)
    uuid_ble    = Column(String(36), nullable=True)   # NULL en puerta salida
    activa      = Column(Boolean, default=True)
    edificio    = relationship("Edificio", back_populates="puertas")
    invitaciones= relationship("Invitacion", back_populates="puerta")
    __table_args__ = (
        Index("ix_puertas_edificio", "edificio_id"),
    )


class Usuario(Base):
    __tablename__ = "usuarios"
    id             = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    numero_celular = Column(String(20), nullable=False, unique=True)
    nombre         = Column(String(200))
    perfil         = Column(String(20), nullable=False)
    edificio_id    = Column(String, ForeignKey("edificios.id"))
    unidad         = Column(String(20))
    activo         = Column(Boolean, default=True)
    creado_en      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    edificio       = relationship("Edificio", back_populates="usuarios")
    push_tokens    = relationship("PushToken", back_populates="usuario")
    __table_args__ = (
        Index("ix_usuarios_numero", "numero_celular"),
        Index("ix_usuarios_edificio", "edificio_id"),
    )


class Invitacion(Base):
    __tablename__ = "invitaciones"
    id                 = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    numero_propietario = Column(String(20), nullable=False)
    numero_invitado    = Column(String(20), nullable=False)
    puerta_id          = Column(String, ForeignKey("puertas.id"), nullable=False)
    edificio_id        = Column(String, ForeignKey("edificios.id"), nullable=False)
    fecha_desde        = Column(DateTime(timezone=True), nullable=False)
    fecha_hasta        = Column(DateTime(timezone=True), nullable=False)
    # Restricciones horarias
    todo_el_dia        = Column(Boolean, default=False)
    hora_inicio        = Column(String(5), default="00:00")   # HH:MM
    hora_fin           = Column(String(5), default="23:59")   # HH:MM
    dias_permitidos    = Column(String(7), default="1234567") # 1=lun..7=dom
    # Control de presencia
    presencia          = Column(String(10), default="fuera")  # "fuera" | "dentro"
    nota               = Column(Text)
    estado             = Column(String(20), default="activa")
    creada_en          = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    actualizada_en     = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
    puerta             = relationship("Puerta", back_populates="invitaciones")
    __table_args__ = (
        Index("ix_invitaciones_invitado", "numero_invitado"),
        Index("ix_invitaciones_propietario", "numero_propietario"),
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
    accion          = Column(String(10), nullable=False)  # "entrada" | "salida"
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
    numero_celular = Column(String(20), ForeignKey("usuarios.numero_celular"), nullable=False)
    token          = Column(String(500), nullable=False)
    plataforma     = Column(String(10), nullable=False)
    actualizado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    usuario        = relationship("Usuario", back_populates="push_tokens")
    __table_args__ = (Index("ix_push_numero", "numero_celular"),)


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

def _invitacion_a_dict(inv: Invitacion, puerta: Puerta) -> dict:
    return {
        "id": inv.id,
        "numero_propietario": inv.numero_propietario,
        "numero_invitado": inv.numero_invitado,
        "puerta_id": inv.puerta_id,
        "puerta_nombre": puerta.nombre if puerta else "",
        "uuid_ble": puerta.uuid_ble if puerta else None,
        "edificio_id": inv.edificio_id,
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
#  USUARIOS
# ============================================================

async def obtener_perfil_usuario(numero_celular: str) -> Optional[dict]:
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
        return {
            "perfil": usuario.perfil,
            "edificio_id": usuario.edificio_id,
            "nombre": usuario.nombre,
            "unidad": usuario.unidad,
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
        return {
            "id": puerta.id,
            "nombre": puerta.nombre,
            "topic_mqtt": puerta.topic_mqtt,
            "uuid_ble": puerta.uuid_ble,
        }


async def obtener_puertas_edificio(edificio_id: str) -> list:
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Puerta).where(
                Puerta.edificio_id == edificio_id,
                Puerta.activa == True,
            ).order_by(Puerta.nombre)
        )
        return [{"id": p.id, "nombre": p.nombre, "uuid_ble": p.uuid_ble} for p in resultado.scalars().all()]


async def obtener_puerta_por_id(puerta_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        puerta = await session.get(Puerta, puerta_id)
        if not puerta:
            return None
        return {
            "id": puerta.id,
            "nombre": puerta.nombre,
            "topic_mqtt": puerta.topic_mqtt,
            "uuid_ble": puerta.uuid_ble,
        }


# ============================================================
#  INVITACIONES
# ============================================================

async def crear_invitacion_bd(
    numero_propietario, numero_invitado, puerta_id,
    edificio_id, fecha_desde, fecha_hasta,
    todo_el_dia=False, hora_inicio="00:00", hora_fin="23:59",
    dias_permitidos="1234567", nota=None,
) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        invitacion = Invitacion(
            id=str(uuid.uuid4()),
            numero_propietario=numero_propietario,
            numero_invitado=numero_invitado,
            puerta_id=puerta_id,
            edificio_id=edificio_id,
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
        session.add(invitacion)
        await session.commit()
        await session.refresh(invitacion)
        puerta = await session.get(Puerta, puerta_id)
        return _invitacion_a_dict(invitacion, puerta)


async def obtener_invitacion(invitacion_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        inv = await session.get(Invitacion, invitacion_id)
        if not inv:
            return None
        puerta = await session.get(Puerta, inv.puerta_id)
        return _invitacion_a_dict(inv, puerta)


async def listar_invitaciones_propietario(numero_propietario, edificio_id, estado="todas") -> list:
    async with AsyncSessionLocal() as session:
        query = select(Invitacion, Puerta).join(
            Puerta, Invitacion.puerta_id == Puerta.id
        ).where(
            Invitacion.numero_propietario == numero_propietario,
            Invitacion.edificio_id == edificio_id,
        )
        if estado != "todas":
            query = query.where(Invitacion.estado == estado)
        resultado = await session.execute(query.order_by(Invitacion.creada_en.desc()))
        return [_invitacion_a_dict(inv, puerta) for inv, puerta in resultado.all()]


async def listar_invitaciones_invitado(numero_invitado, ahora) -> list:
    ahora_naive = ahora.replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Invitacion, Puerta).join(
                Puerta, Invitacion.puerta_id == Puerta.id
            ).where(
                Invitacion.numero_invitado == numero_invitado,
                Invitacion.estado == "activa",
            ).order_by(Invitacion.fecha_hasta)
        )
        resultado_filtrado = []
        for inv, puerta in resultado.all():
            fd = inv.fecha_desde.replace(tzinfo=None) if inv.fecha_desde.tzinfo else inv.fecha_desde
            fh = inv.fecha_hasta.replace(tzinfo=None) if inv.fecha_hasta.tzinfo else inv.fecha_hasta
            if fd <= ahora_naive <= fh:
                resultado_filtrado.append(_invitacion_a_dict(inv, puerta))
        return resultado_filtrado


async def buscar_invitacion_activa_invitado(numero_invitado, edificio_id) -> Optional[dict]:
    """Busca invitacion activa del invitado en el edificio — para beacon unico."""
    ahora = datetime.now(timezone.utc)
    ahora_naive = ahora.replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(Invitacion, Puerta).join(
                Puerta, Invitacion.puerta_id == Puerta.id
            ).where(
                Invitacion.numero_invitado == numero_invitado,
                Invitacion.edificio_id == edificio_id,
                Invitacion.estado == "activa",
            ).limit(1)
        )
        fila = resultado.first()
        if not fila:
            return None
        inv, puerta = fila
        fd = inv.fecha_desde.replace(tzinfo=None) if inv.fecha_desde.tzinfo else inv.fecha_desde
        fh = inv.fecha_hasta.replace(tzinfo=None) if inv.fecha_hasta.tzinfo else inv.fecha_hasta
        if not (fd <= ahora_naive <= fh):
            return None
        return _invitacion_a_dict(inv, puerta)


async def buscar_invitacion_por_id(invitacion_id: str) -> Optional[dict]:
    return await obtener_invitacion(invitacion_id)


async def actualizar_presencia(invitacion_id: str, presencia: str):
    """Actualiza el estado de presencia: 'fuera' | 'dentro'."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion)
            .where(Invitacion.id == invitacion_id)
            .values(presencia=presencia, actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()


async def actualizar_invitacion_bd(invitacion_id, campos) -> Optional[dict]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion)
            .where(Invitacion.id == invitacion_id)
            .values(**campos, actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()
        return await obtener_invitacion(invitacion_id)


async def cancelar_invitacion_bd(invitacion_id):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion)
            .where(Invitacion.id == invitacion_id)
            .values(estado="cancelada", actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()


async def marcar_invitacion_usada(invitacion_id):
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Invitacion)
            .where(Invitacion.id == invitacion_id)
            .values(estado="usada", actualizada_en=datetime.now(timezone.utc))
        )
        await session.commit()


# ============================================================
#  LOG DE ACCESOS
# ============================================================

async def registrar_acceso_bd(
    invitacion_id, numero_invitado, puerta_id,
    edificio_id, accion, timestamp, lat=None, lng=None,
):
    async with AsyncSessionLocal() as session:
        log = LogAcceso(
            id=str(uuid.uuid4()),
            invitacion_id=invitacion_id,
            numero_invitado=numero_invitado,
            puerta_id=puerta_id,
            edificio_id=edificio_id,
            accion=accion,
            timestamp=timestamp,
            lat=lat,
            lng=lng,
        )
        session.add(log)
        await session.commit()


async def listar_log_accesos(edificio_id, numero_propietario, limite=50) -> list:
    async with AsyncSessionLocal() as session:
        subq = select(Invitacion.id).where(
            Invitacion.numero_propietario == numero_propietario,
            Invitacion.edificio_id == edificio_id,
        ).scalar_subquery()
        resultado = await session.execute(
            select(LogAcceso, Puerta).join(
                Puerta, LogAcceso.puerta_id == Puerta.id
            ).where(
                LogAcceso.invitacion_id.in_(subq)
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


# ============================================================
#  PUSH TOKENS
# ============================================================

async def guardar_push_token(numero_celular, token, plataforma):
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(PushToken).where(
                PushToken.numero_celular == numero_celular,
                PushToken.plataforma == plataforma,
            )
        )
        existente = resultado.scalar_one_or_none()
        if existente:
            existente.token = token
            existente.actualizado_en = datetime.now(timezone.utc)
        else:
            session.add(PushToken(
                numero_celular=numero_celular,
                token=token,
                plataforma=plataforma,
            ))
        await session.commit()


async def obtener_push_tokens_propietario(edificio_id, numero_propietario) -> list:
    async with AsyncSessionLocal() as session:
        resultado = await session.execute(
            select(PushToken.token).where(
                PushToken.numero_celular == numero_propietario
            )
        )
        return [row[0] for row in resultado.all()]
