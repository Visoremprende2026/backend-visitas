# ============================================================
#  seed.py — Datos iniciales de prueba
#  Ejecutar: python seed.py
# ============================================================

import asyncio
import uuid
from base_datos import init_db, AsyncSessionLocal, Edificio, Puerta, Usuario

async def seed():
    await init_db()

    async with AsyncSessionLocal() as session:

        # Edificio
        edificio = Edificio(
            id="edificio-1",
            nombre="Edificio Las Condes",
            direccion="Av. Las Condes 1234",
            lat=-33.4167,
            lng=-70.6062,
        )
        session.add(edificio)

        # Barrera entrada — tiene UUID BLE (el beacon unico esta aqui)
        puerta_entrada = Puerta(
            id="puerta-1",
            edificio_id="edificio-1",
            nombre="Barrera entrada",
            topic_mqtt="puerta/1/open",
            uuid_ble="a1b2c3d4-e5f6-7890-abcd-ef1234567891",
        )

        # Barrera salida — sin UUID BLE propio (la decide el backend por presencia)
        puerta_salida = Puerta(
            id="puerta-2",
            edificio_id="edificio-1",
            nombre="Barrera salida",
            topic_mqtt="puerta/2/open",
            uuid_ble=None,
        )

        session.add(puerta_entrada)
        session.add(puerta_salida)

        # Propietario
        propietario = Usuario(
            id=str(uuid.uuid4()),
            numero_celular="+56912345678",
            nombre="Propietario Prueba",
            perfil="propietario",
            edificio_id="edificio-1",
            unidad="301",
        )
        session.add(propietario)

        # Invitado
        invitado = Usuario(
            id=str(uuid.uuid4()),
            numero_celular="+56987654321",
            nombre="Invitado Prueba",
            perfil="invitado",
            edificio_id="edificio-1",
        )
        session.add(invitado)

        await session.commit()

        print("Datos de prueba creados:")
        print("  Propietario : +56912345678")
        print("  Invitado    : +56987654321")
        print("  Beacon UUID : a1b2c3d4-e5f6-7890-abcd-ef1234567891")
        print("  DO1 topic   : puerta/1/open  (barrera entrada)")
        print("  DO2 topic   : puerta/2/open  (barrera salida)")

asyncio.run(seed())
