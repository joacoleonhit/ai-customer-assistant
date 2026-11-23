"""Transfer destination checks; synthetic PostgreSQL rows are rolled back."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/".env")
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import select,func
from fastapi import HTTPException
from app.main import app
from app.core.database import engine
from app.models.business import Business
from app.models.product import Product
from app.models.order import Order,PaymentStatus
from app.schemas.business import BusinessCreate,BusinessPaymentUpdate
from app.schemas.order import OrderCreate,ConversationDraftRequest
from app.services.order_service import create_order
from app.api.orders import preview_order,create_conversation_draft
from app.api.businesses import update_payment_settings
from app.api.conversations import payment_reply,handle_message,IncomingMessage
from app.api.checkout import create_order_checkout

try: BusinessCreate(name="bad",alias=" ",cbu=" ")
except ValidationError: print("Perfil sin datos útiles rechazado: OK",flush=True)
else: raise AssertionError("Perfil vacío aceptado")

with engine.connect() as conn:
 tx=conn.begin()
 try:
  with Session(bind=conn,join_transaction_mode="create_savepoint") as db:
   for alias,cbu in [("prueba.alias",None),(None,"0"*22),("prueba.alias","0"*22),(" ",None)]:
    b=Business(name="Prueba pagos",alias=alias,cbu=cbu);db.add(b);db.flush()
    p=Product(name="Pizza muzzarella",price=1250,description="Pizza con queso",business_id=b.id);db.add(p);db.commit()
    user=SimpleNamespace(business_id=b.id)
    data=OrderCreate(customer_phone="12025550100",items=[{"product_id":p.id,"quantity":2}],delivery_type="PICKUP",payment_method="TRANSFER")
    if alias==" ":
     try: preview_order(data,db,user)
     except HTTPException as e: assert e.status_code==422
     else: raise AssertionError("Preview sin cuenta permitido")
     try: create_order(db,data,b.id)
     except ValueError: pass
     else: raise AssertionError("Pedido sin cuenta permitido")
     cash=create_order(db,data.model_copy(update={"payment_method":__import__('app.models.order',fromlist=['PaymentMethod']).PaymentMethod.CASH}),b.id)
     with patch("app.api.checkout.connected_credentials") as credentials:
      try: create_order_checkout(db,b.id,cash.id)
      except HTTPException as e: assert e.status_code==409
      else: raise AssertionError("Checkout sin destino permitido")
      credentials.assert_not_called()
     print("Sin alias/CBU: transferencia bloqueada; efectivo permitido: OK",flush=True)
     continue
    order=create_order(db,data,b.id)
    message=payment_reply(db,order,"test").message
    assert ("Alias:" in message)==bool(alias)
    assert ("CBU/CVU:" in message)==bool(cbu)
    assert "None" not in message
    assert order.payment_status==PaymentStatus.PENDING
    try: update_payment_settings(BusinessPaymentUpdate(payment_provider=None,alias=" ",cbu=" "),db,user)
    except HTTPException as e: assert e.status_code==422
    else: raise AssertionError("Se pudo borrar el último dato de cobro")
    print("Destino",bool(alias),bool(cbu),"mensaje y conservación de datos: OK",flush=True)
   b=Business(name="Prueba IA pagos",alias="prueba.alias",cbu="0"*22);db.add(b);db.flush()
   p=Product(name="Pizza muzzarella",description="Pizza con queso",price=1250,business_id=b.id);db.add(p);db.commit()
   user=SimpleNamespace(business_id=b.id)
   draft=create_conversation_draft(ConversationDraftRequest(conversation_id="payment-live",customer_phone="12025550100",items=[{"product_id":p.id,"quantity":2}],delivery_type="PICKUP",payment_method="TRANSFER"),db,user)
   history=[{"role":"customer","text":"Dos muzzas para retirar, transferencia"},{"role":"assistant","text":draft.message}]
   for text in ["¿Cuál es el alias y el CVU?","Sí, ¿dónde te transfiero?"]:
    reply=handle_message(IncomingMessage(conversation_id="payment-live",customer_phone="12025550100",message=text,history=history,draft_id=draft.draft_id),db,user)
    print(text,"=>",reply.message,flush=True)
    assert "prueba.alias" in reply.message and "0"*22 in reply.message
    if text.startswith("¿"):
     assert reply.order_id is None
     assert db.scalar(select(func.count()).select_from(Order).where(Order.business_id==b.id))==0
    else:
     assert reply.order_id is not None
     assert db.get(Order,reply.order_id).payment_status==PaymentStatus.PENDING
    history.extend([{"role":"customer","text":text},{"role":"assistant","text":reply.message}])
   print("IA: consultar datos no crea pedido; aceptar más consulta sí crea pedido pendiente: OK",flush=True)
 finally: tx.rollback()
print("Datos ficticios revertidos",flush=True)
