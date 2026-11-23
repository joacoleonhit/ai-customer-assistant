# Integraciones opcionales

La demo funciona sin Meta, Mercado Pago ni una API de IA. No incluye credenciales y no asigna números telefónicos.

## IA real en la demo

Por defecto `.demo.env` contiene `DEMO_AI_PROVIDER=simulated`: reglas locales para explorar el flujo, no un modelo de lenguaje. Para interpretar mensajes libres, configurá uno de estos proveedores en tu propia instalación.

### Ollama

1. Instalá Ollama y descargá un modelo: `ollama pull qwen3:14b`.
2. En `.demo.env`, reemplazá `DEMO_AI_PROVIDER=simulated` por `DEMO_AI_PROVIDER=ollama`.
3. Podés indicar `OLLAMA_CONVERSATION_MODEL=qwen3:14b`.
4. Ejecutá otra vez `python start_demo.py`.

Ollama debe aceptar la conexión desde el contenedor Docker. La dirección usada es `http://host.docker.internal:11434`; según el sistema puede requerir ajustar la escucha y el firewall. No expongas su puerto a Internet. El modelo se ejecuta en la computadora que aloja el backend, no en el navegador del visitante. Qwen3 14B requiere recursos considerables; la velocidad depende del equipo. El cambio de modelo requiere repetir las pruebas de interpretación.

### OpenAI

En `.demo.env`, configurá `DEMO_AI_PROVIDER=openai`, `OPENAI_API_KEY` y `OPENAI_CONVERSATION_MODEL` con tus propios valores. Luego reiniciá con `python start_demo.py`. Requiere saldo de API: quien configura esa clave paga el consumo de esa instalación. No publiques el archivo ni abras una demo con saldo a Internet sin límites adicionales.

No se cambia de proveedor silenciosamente si una API falla. El panel muestra un error y permite reintentar; el pedido se conserva.

## WhatsApp real: desarrollo nativo

La demo aislada bloquea conexiones externas. Para probar la integración real usá el backend de desarrollo con `DEMO_ONLY=false`, una cuenta propia del negocio y tus propias variables en `backend/.env`:

- `WHATSAPP_CHANNELS`: objeto JSON por phone number ID, con `business_id` y `access_token`.
- `WHATSAPP_GRAPH_VERSION`: versión soportada por tu aplicación de Meta, con formato `vXX.0`.
- `WHATSAPP_APP_SECRET`: firma de los eventos recibidos.
- `WHATSAPP_VERIFY_TOKEN`: secreto elegido para validar el webhook.

Necesitás un webhook HTTPS público que apunte a `/webhooks/whatsapp`, suscripción a mensajes y el worker `python -m app.services.conversation_worker`. Publicá solamente el adaptador de WhatsApp, no todo el panel ni los endpoints de creación. El número de prueba de Meta admite destinatarios autorizados; no es una línea comercial propia. El botón de simulación del perfil tampoco genera un número real.

La vinculación autónoma del número de cada cliente mediante Embedded Signup/coexistencia todavía está pendiente de implementación y de la habilitación correspondiente en Meta. Responder desde el celular y sincronizar esa atención requiere procesar los eventos específicos de coexistencia; no se presenta como una función terminada.

## Mercado Pago real: desarrollo nativo

La integración es opcional y no se ejecuta en el modo demo aislado. Para el flujo OAuth se requieren `MERCADO_PAGO_CLIENT_ID`, `MERCADO_PAGO_CLIENT_SECRET`, `MERCADO_PAGO_REDIRECT_URI` y `MERCADO_PAGO_TOKEN_KEY` (una clave Fernet propia). El backend guarda las credenciales cifradas y usa callbacks y verificación del proveedor.

La alternativa de desarrollo `MERCADO_PAGO_SELLERS` contiene credenciales propias por negocio. No debe versionarse. Los endpoints de checkout y notificaciones están implementados; las pruebas con dobles no equivalen a validación financiera en producción. Antes de usarlos con dinero real, verificá las API vigentes del proveedor y probá credenciales de sandbox, firmas, importes, titular y reintentos.

El pago por transferencia directa se confirma únicamente después de verificar su acreditación en la cuenta. Un mensaje o comprobante del cliente genera una alerta; no confirma el pago.
