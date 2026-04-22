# ============================================================
#  seed.py — Datos iniciales de prueba v2
#  Usa el nuevo modelo con Membresia
# ============================================================

import asyncio
import uuid
from base_datos import init_db, AsyncSessionLocal, Edificio, Puerta, Usuario, Membresia

async def seed():
    await init_db()

    async with AsyncSessionLocal() as session:

        # Edificio
        edificio = Edificio(
            id="edificio-1",
            nombre="Condominio Las Condes",
            direccion="Av. Las Condes 1234",
            lat=-33.4167,
            lng=-70.6062,
            mqtt_broker_host="localhost",
            mqtt_broker_port=1883,
        )
        session.add(edificio)

        # Puertas
        session.add(Puerta(
            id="puerta-1",
            edificio_id="edificio-1",
            nombre="Barrera entrada",
            topic_mqtt="edificio-1/puerta/1/open",
            uuid_ble="a1b2c3d4-e5f6-7890-abcd-ef1234567891",
        ))
        session.add(Puerta(
            id="puerta-2",
            edificio_id="edificio-1",
            nombre="Barrera salida",
            topic_mqtt="edificio-1/puerta/2/open",
            uuid_ble=None,
        ))

        # Usuario propietario
        u_prop = Usuario(
            id="usuario-prop-1",
            numero_celular="+56912345678",
            nombre="Juan Perez",
        )
        session.add(u_prop)

        # Membresia propietario — Depto 301
        session.add(Membresia(
            id="membresia-1",
            usuario_id="usuario-prop-1",
            edificio_id="edificio-1",
            rol="propietario",
            unidad="Depto 301 Torre A",
        ))

        # Usuario administrador
        u_admin = Usuario(
            id="usuario-admin-1",
            numero_celular="+56911111111",
            nombre="Admin Condominio",
        )
        session.add(u_admin)

        # Membresia administrador
        session.add(Membresia(
            id="membresia-admin-1",
            usuario_id="usuario-admin-1",
            edificio_id="edificio-1",
            rol="administrador",
            unidad=None,
        ))

        # Usuario invitado (sin membresia — puede recibir invitaciones)
        u_inv = Usuario(
            id="usuario-inv-1",
            numero_celular="+56987654321",
            nombre="Maria Gonzalez",
        )
        session.add(u_inv)

        await session.commit()

        print("Datos de prueba creados:")
        print("  Propietario  : +56912345678 (Juan Perez — Depto 301 Torre A)")
        print("  Administrador: +56911111111 (Admin Condominio)")
        print("  Invitado     : +56987654321 (Maria Gonzalez — sin membresia)")
        print("  Beacon UUID  : a1b2c3d4-e5f6-7890-abcd-ef1234567891")
        print("  Membresia ID : membresia-1 (usar al crear invitaciones)")

asyncio.run(seed())
