# Backend — Sistema de Administracion de Visitas

## Estructura del proyecto

```
backend/
├── main.py           # FastAPI app + todos los endpoints
├── config.py         # Configuracion centralizada (editar este archivo)
├── nucleo.py         # Logica de negocio pura (reutilizable por WhatsApp y API)
├── mqtt_client.py    # Cliente MQTT — publica ordenes al EG118
├── modelos.py        # Schemas Pydantic (validacion de request/response)
├── auth.py           # JWT + OTP SMS (Twilio)
├── base_datos.py     # Acceso a BD — implementar segun motor elegido
├── notificaciones.py # Push notifications — implementar con Expo/FCM/APNs
├── requirements.txt  # Dependencias Python
└── .env              # Variables de entorno (NO subir a git)
```

## Instalacion

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar y editar configuracion
cp .env.example .env
# Editar .env con tus credenciales

# Ejecutar en desarrollo
uvicorn main:app --reload --port 8000

# Documentacion interactiva disponible en:
# http://localhost:8000/docs
```

## Archivo .env (crear manualmente)

```env
DEBUG=true
JWT_SECRET=tu_secreto_muy_largo_y_seguro_aqui
MQTT_BROKER_HOST=192.168.1.100
MQTT_BROKER_PORT=1883
MQTT_USERNAME=backend
MQTT_PASSWORD=tu_password_mqtt
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxx
TWILIO_NUMERO_ORIGEN=+56900000000
DATABASE_URL=sqlite:///./visitas.db
```

## Modulos pendientes de implementar

### base_datos.py
Implementar las funciones de acceso a BD segun el motor elegido:
- SQLite para MVP (simple, sin servidor)
- PostgreSQL para produccion (robusto, multi-usuario)

Funciones requeridas:
- crear_invitacion_bd()
- listar_invitaciones_propietario()
- listar_invitaciones_invitado()
- obtener_invitacion()
- actualizar_invitacion_bd()
- cancelar_invitacion_bd()
- buscar_invitacion_por_uuid_ble()
- buscar_invitacion_por_id()
- registrar_acceso_bd()
- obtener_puerta_por_uuid()
- listar_log_accesos()
- guardar_push_token()
- obtener_perfil_usuario()
- obtener_puertas_edificio()

### notificaciones.py
Implementar envio de push notifications:
- Expo Push Notifications (mas simple para React Native)
- O FCM (Android) + APNs (iOS) directamente

Funcion requerida:
- enviar_push_propietario(edificio_id, numero_invitado, puerta_nombre, timestamp)

## Integracion con agente WhatsApp existente

El adaptador WhatsApp llama a nucleo.py directamente:

```python
# En tu adaptador WhatsApp actual
from nucleo import procesar_solicitud_acceso

async def on_mensaje_whatsapp(numero, mensaje, edificio_id):
    # Detectar UUID BLE del mensaje (si el invitado lo envia)
    # O buscar por numero directamente
    resultado = await procesar_solicitud_acceso(
        numero_invitado=numero,
        edificio_id=edificio_id,
        uuid_ble=uuid_detectado,
    )
    if resultado["ok"]:
        return f"Puerta {resultado['puerta_nombre']} abierta."
    else:
        return "Acceso denegado: " + resultado["motivo"]
```

## Flujo de prueba rapida (sin app)

Con el servidor corriendo, abrir http://localhost:8000/docs y:

1. POST /auth/otp/request — ingresar numero de celular
2. Revisar log del servidor para ver el codigo OTP (modo desarrollo)
3. POST /auth/otp/verify — verificar codigo, copiar el access_token
4. Autorizar en Swagger UI con el token (boton "Authorize")
5. POST /acceso/solicitar — enviar uuid_ble de prueba
6. Verificar en el log del EG118 (puerto serial) que recibio el MQTT
