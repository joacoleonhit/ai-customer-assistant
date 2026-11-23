# Validación local del asistente — 2026-11-18

Modelo configurado: Qwen3 14B, ejecutado en Ollama local.

## Resultados

- 27 escenarios distintos aprobados: matriz de 25 casos y cuatro repeticiones
  enfocadas, dos de ellas escenarios adicionales de WhatsApp.
- 10 pruebas rápidas aprobadas, sin modelo ni servicios externos; algunas incluyen
  varios subcasos de salida inválida.
- Flujo en PostgreSQL aprobado con datos ficticios: cotización, condición no
  aceptada, reclamo de pago sin acreditación, aislamiento entre negocios,
  cambio de precio que invalida la cotización anterior, nuevo resumen, aceptación,
  pago pendiente y confirmaciones repetidas sin duplicación.
- Los datos ficticios de PostgreSQL se revirtieron. Las secuencias de IDs pueden
  avanzar durante las pruebas; no se conservaron pedidos de prueba.

Tiempo de interpretación observado con el modelo cargado:
mediana 9.9 s; máximo 36.9 s.
Los intentos de control bloqueados antes del modelo se excluyen de estos tiempos.
La carga inicial del modelo puede tardar más. No es una prueba de carga concurrente.

## Correcciones verificadas

- Historial como turnos nativos y mensaje actual al final.
- Estado real del pedido proporcionado por el servidor.
- Aceptar un resumen crea un pedido pendiente: no confirma la acreditación.
- Formato de salida por acción; una aceptación no lleva cambios de ítems ni pago.
- Productos ajenos, cantidades inválidas, duplicados y respuestas inconsistentes
  no producen acciones de pedido.
- Intentos de suplantar roles/configuración bloqueados antes de consultar el modelo.
- Revisión adicional de la aceptación del pedido. Las validaciones y precios son
  responsabilidad del backend, no de otra respuesta del modelo.
- Resúmenes/totales de pedidos pendientes que aparecen en una respuesta informativa
  se reconstruyen con precios de la base de datos.
- Referencia del pedido conservada tras crearlo, también después de una respuesta
  informativa, para impedir duplicación por confirmaciones repetidas.
- Bloqueo de algunas afirmaciones generadas sobre operaciones o avisos no ejecutados.

## Alcance y límites

Se usaron mensajes ficticios con Ollama real. No se enviaron mensajes por WhatsApp
ni se ejecutaron transferencias, pagos reales u OAuth de Mercado Pago.
Las comprobaciones de diálogo validan las acciones y campos esperados; no prueban
cada posible afirmación del lenguaje natural ni todos los ataques posibles.
Las barreras sobre pagos, precios almacenados e identidad del negocio siguen en
el backend. Los bloqueos de texto son defensa adicional, no autorización.
El sistema puede pedir aclaración o reconfirmación; no se garantiza interpretar
siempre correctamente una conversación nueva. La cancelación automática de pedidos
existentes desde el chat no está implementada.
Hace falta un piloto supervisado por WhatsApp antes de atender sin supervisión.

La prueba de integridad incluye decisiones sintéticas controladas para repetir
respuestas y confirmaciones al final, además del diálogo principal con el modelo real.

## Repetición

Desde `backend`, con las dependencias del proyecto instaladas:

```sh
python -B scripts/check_conversation_guards.py
python -B scripts/check_conversation_adversarial.py
python -B scripts/check_conversation_integrity.py
```

Las últimas dos necesitan Ollama; integridad necesita además PostgreSQL.
El script de mensajes usa el proveedor de `.env`: si elegís OpenAI, consume saldo.

Los reportes detallados se generan localmente en `backend/scripts/adversarial_results.json` y
`backend/scripts/adversarial_focus_results.json`; están excluidos del repositorio.
Estos resultados corresponden a esa evaluación puntual, no garantizan el comportamiento
de otros modelos ni reemplazan las pruebas del estado actual del código.
