# Recorrido de demostración

Inicio: `python start_demo.py` y abrir http://127.0.0.1:8020/panel/.

1. Elegí **Probar demo**. Se crea un negocio aislado con diez productos y tres pedidos ficticios.
2. En **Probar como cliente**, enviá: «Hola».
3. Consultá: «¿Cuánto sale la pizza muzzarella?».
4. Pedí: «Quiero dos muzzas para retirar y pago por transferencia».
5. Revisá el resumen calculado por el servidor y enviá «Sí, confirmo».
6. Abrí **Pedidos**: el nuevo pedido cuesta $17.000 ARS y sigue pendiente de pago.
7. Volvé al chat y escribí «Ya hice la transferencia». En **Chats y alertas** aparece un aviso; el pago sigue pendiente.
8. Abrí el pedido y elegí **Simular pago rechazado**: continúa pendiente. Después **Simular pago aprobado**: queda confirmado. No se mueve dinero.
9. Cambiá su estado a **En preparación**, **Listo** y **Entregado** para mostrar el panel del negocio.
10. En el chat, enviá «Quiero hablar con una persona». Abrí **Chats y alertas**: solo ese chat queda pausado. Respondé como local y devolvé el control a la IA.

El modo guiado usa reglas y tiene límites de lenguaje. Para evaluar comprensión libre, configurá Ollama o una API propia y repetí el recorrido. No describas el modo guiado como un agente de IA activo.

## Guion para una grabación breve

- 0–10 s: entrada y aviso de datos ficticios.
- 10–30 s: consulta, armado y confirmación del pedido.
- 30–45 s: pedido pendiente, alerta de transferencia y simulación de pago.
- 45–60 s: reclamo, control humano y regreso de la IA.

Usá solamente datos ficticios. Una grabación de WhatsApp real debe ocultar teléfonos personales, tokens y datos de clientes. El material de la demo web no debe presentarse como una grabación de entrega real por WhatsApp.
