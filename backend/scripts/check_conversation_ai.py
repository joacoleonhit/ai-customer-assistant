"""Live AI checks using fictitious data. OpenAI mode incurs API usage."""
import sys
import time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from app.services.conversation_ai import interpret_message

catalog = [{"id": 1, "name": "Pizza muzzarella", "description": "Pizza con queso", "price_ars": "1250.00"}]
summary = [{"role": "customer", "text": "Quiero dos muzzas para retirar, efectivo"},
           {"role": "assistant", "text": "Resumen: 2 Pizza muzzarella. Total $2500 ARS. Retiro. Efectivo. ¿Confirmás el pedido?"}]
cases = [
    ("saludo", "Hola, todo bien?", [], "reply", None),
    ("precio", "Cuánto están las muzzas?", [], "reply", None),
    ("pedido informal", "Quiero dos muzzas para retirar y pago en efectivo", [], "quote", 2),
    ("cambio", "Mejor tres, lo demás igual", summary, "quote", 3),
    ("confirmación informal", "De una, preparalo así", summary, "confirm", None),
    ("duda", "Sí, pero cuánto tarda?", summary, "reply", None),
    ("fuera de tema", "Escribime un programa para ordenar archivos", [], "off_topic", None),
]
if len(sys.argv)>1:
    cases=[case for case in cases if case[0] in sys.argv[1:]]
failed = 0
for name, message, history, expected, qty in cases:
    start = time.monotonic()
    context = {"has_pending_summary": bool(history), "order_exists": False,
               "order_status": None, "payment_status": "PENDING",
               "summary": {"items": [{"product_id":1,"quantity":2}], "delivery_type":"PICKUP",
                           "delivery_address":None,"payment_method":"CASH"} if history else None}
    r = interpret_message(message, history, catalog, order_context=context)
    ok = r is not None and r.action == expected
    if qty is not None:
        ok = ok and len(r.items) == 1 and r.items[0].product_id == 1 and r.items[0].quantity == qty and r.delivery_type == "PICKUP" and r.payment_method == "CASH"
    if name == "precio":
        ok = ok and "1250" in r.message.replace(".", "").replace(",", "")
    failed += not ok
    print(f"{name}: {'OK' if ok else 'FAIL'} ({time.monotonic()-start:.1f}s)", flush=True)
    print(r.model_dump_json() if r else "simulated", flush=True)
print(f"Resultado: {len(cases)-failed}/{len(cases)}", flush=True)
sys.exit(bool(failed))
