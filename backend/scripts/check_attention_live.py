"""Live Ollama classification only. No orders or WhatsApp messages are created."""
import sys,time
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/".env")
from app.services.conversation_ai import interpret_message
catalog=[{"id":1,"name":"Pizza muzzarella","description":"Pizza con queso","price_ars":"1250.00"}]
history=[{"role":"assistant","text":"Recibimos tu pedido. El pago por transferencia está pendiente de verificación del local."}]
context={"order_exists":True,"has_pending_summary":False,"payment_status":"PENDING","summary":{"payment_method":"TRANSFER"}}
cases=[("La pizza vino helada y necesito que lo resuelvan","complaint",history),
       ("Ya te pasé la plata, fijate en tu cuenta","transfer_claim",history),
       ("Todavía no transferí",None,history),
       ("Gracias, qué bebidas tienen?",None,[{"role":"customer","text":"Tengo un reclamo"},{"role":"assistant","text":"Una persona atendió tu reclamo."}])]
for message,expected,turns in cases:
 start=time.monotonic();r=interpret_message(message,turns,catalog,order_context=context)
 print(message,"=>",r.attention_reason,round(time.monotonic()-start,1),"s",flush=True)
 assert r.attention_reason==expected
print("4/4 señales semánticas correctas",flush=True)
