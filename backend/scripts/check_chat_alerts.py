"""PostgreSQL tests. Fake fixtures are removed; no external messages are sent."""
import sys,time,uuid,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from io import BytesIO
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/".env")
from sqlalchemy import select,delete,func
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal,engine
from app.core.security import get_current_user
from app.models.business import Business
from app.models.user import User,UserRole
from app.models.conversation import Conversation,ConversationEvent,ConversationAlert,WhatsAppReply
from app.models.product import Product
from app.models.order import Order,OrderItem,PaymentStatus
from app.models.order_draft import OrderDraft
from app.schemas.order import OrderCreate
from app.api.orders import create_conversation_draft
from app.schemas.order import ConversationDraftRequest
from app.api.conversations import queue_incoming_message,QueuedMessage,update_attention,AttentionUpdate
from app.services.chat_attention import quick_signal
from app.services.conversation_ai import Interpretation
from app.services.conversation_worker import process_due
from app.services.whatsapp_service import dispatch_reply
from app.services.order_service import create_order,confirm_order_payment

class ChatTests(unittest.TestCase):
 def setUp(self):
  self.bids=[]
  with SessionLocal.begin() as db:
   for n in range(2):
    b=Business(name="QA alerts "+uuid.uuid4().hex,alias="qa.alerts");db.add(b);db.flush();self.bids.append(b.id)
    u=User(name="QA",email=uuid.uuid4().hex+"@example.com",password_hash="unused",role=UserRole.ADMIN,business_id=b.id)
    db.add(u);db.flush()
    if n==0:self.uid=u.id
  self.user=SimpleNamespace(id=self.uid,business_id=self.bids[0],role=UserRole.ADMIN)
  app.dependency_overrides[get_current_user]=lambda:self.user
  self.client=TestClient(app)
 def tearDown(self):
  app.dependency_overrides.pop(get_current_user,None)
  self.client.close()
  with SessionLocal.begin() as db:
   for model in [ConversationAlert,WhatsAppReply,ConversationEvent,OrderDraft,OrderItem,Order,Product,Conversation,User]:
    if hasattr(model,"business_id"):db.execute(delete(model).where(model.business_id.in_(self.bids)))
    elif model is OrderItem:db.execute(delete(model).where(model.order_id.in_(select(Order.id).where(Order.business_id.in_(self.bids)))))
   db.execute(delete(Business).where(Business.id.in_(self.bids)))
 def queue(self,text="Hola",event=None,chat="test-chat",attachment=None):
  with SessionLocal() as db:
   return queue_incoming_message(chat,QueuedMessage(event_id=event or uuid.uuid4().hex,customer_phone="12025550100",message=text,attachment=attachment),db,self.bids[0])
 def state(self,chat="test-chat"):
  with SessionLocal() as db:
   c=db.get(Conversation,(self.bids[0],chat));return c.manual,c.due_at,c.history,c.attention_version
 def decision(self,attention=None):
  return Interpretation(action="reply",message="Hola",items=[],delivery_type=None,delivery_address=None,payment_method=None,attention_reason=attention)
 def test_complaint_pauses_only_its_chat_and_deduplicates(self):
  self.queue("Tengo un reclamo",event="same")
  self.queue("Hola",chat="other")
  self.assertTrue(self.queue("Tengo un reclamo",event="same")["duplicate"])
  self.queue("Sigue mi queja",event="new")
  self.assertTrue(self.state()[0]);self.assertFalse(self.state("other")[0])
  data=self.client.get("/alerts/").json();self.assertEqual(data["pending_count"],1)
  self.assertEqual(data["items"][0]["kind"],"complaint")
 def test_human_request_and_negative_transfer(self):
  self.assertEqual(quick_signal("Quiero hablar con una persona"),"complaint")
  for text in ["Todavía no transferí","Voy a transferir","¿Cuál es el alias?","¿Dónde transfiero?"]:
   self.assertIsNone(quick_signal(text,transfer_context=True),text)
 def test_transfer_claim_never_marks_paid_and_resolves_after_verification(self):
  self.queue("Hola")
  with SessionLocal() as db:
   p=Product(name="QA product",price=100,business_id=self.bids[0]);db.add(p);db.commit()
   d=create_conversation_draft(ConversationDraftRequest(conversation_id="test-chat",customer_phone="12025550100",items=[{"product_id":p.id,"quantity":1}],delivery_type="PICKUP",payment_method="TRANSFER"),db,self.user)
   from app.api.orders import confirm_conversation_draft
   from app.schemas.order import ConversationDraftConfirmation
   order=confirm_conversation_draft(d.draft_id,ConversationDraftConfirmation(conversation_id="test-chat"),db,self.user)
   order_id=order.id;c=db.get(Conversation,(self.bids[0],"test-chat"));c.draft_id=d.draft_id;db.commit()
  self.queue("Ya te transferí")
  self.assertFalse(self.state()[0])
  data=self.client.get("/alerts/").json();self.assertEqual(data["pending_count"],1)
  self.assertEqual(data["items"][0]["order_id"],order_id)
  with SessionLocal() as db:
   self.assertEqual(db.get(Order,order_id).payment_status,PaymentStatus.PENDING)
   confirm_order_payment(db,self.bids[0],order_id)
  self.assertEqual(self.client.get("/alerts/").json()["pending_count"],0)
 def test_resolve_is_not_release_and_cannot_cross_business(self):
  self.queue("Tengo una queja")
  alert=self.client.get("/alerts/").json()["items"][0]["id"]
  self.user=SimpleNamespace(id=self.uid,business_id=self.bids[1])
  self.assertEqual(self.client.patch(f"/alerts/{alert}/resolve").status_code,404)
  self.assertEqual(self.client.get("/conversations/test-chat").status_code,404)
  self.assertEqual(self.client.get("/alerts/").json()["pending_count"],0)
  self.user=SimpleNamespace(id=self.uid,business_id=self.bids[0])
  self.assertEqual(self.client.patch(f"/alerts/{alert}/resolve").status_code,200)
  self.assertTrue(self.state()[0])
 def test_takeover_during_inference_discards_the_result(self):
  self.queue()
  entered=threading.Event();resume=threading.Event();errors=[]
  def plan(*args):entered.set();resume.wait(10);return self.decision()
  def work():
   try:process_due(business_id=self.bids[0])
   except Exception as e:errors.append(e)
  with patch("app.api.conversations.plan_message",side_effect=plan):
   worker=threading.Thread(target=work);worker.start()
   try:
    self.assertTrue(entered.wait(5))
    started=time.monotonic()
    response=self.client.patch("/conversations/test-chat/attention",json={"action":"takeover"})
    self.assertEqual(response.status_code,200)
    self.assertLess(time.monotonic()-started,2)
   finally:resume.set();worker.join(10)
  self.assertFalse(worker.is_alive());self.assertFalse(errors,errors)
  self.assertTrue(self.state()[0]);self.assertEqual(self.state()[2][-1]["role"],"customer")
  with SessionLocal() as db:self.assertEqual(db.scalar(select(func.count()).select_from(WhatsAppReply).where(WhatsAppReply.business_id==self.bids[0])),0)
 def test_takeover_release_also_invalidates_inflight_generation(self):
  self.queue();entered=threading.Event();resume=threading.Event()
  def plan(*args):entered.set();resume.wait(10);return self.decision()
  with patch("app.api.conversations.plan_message",side_effect=plan):
   worker=threading.Thread(target=lambda:process_due(business_id=self.bids[0]));worker.start()
   try:
    self.assertTrue(entered.wait(5))
    for action in ["takeover","release"]:self.client.patch("/conversations/test-chat/attention",json={"action":action})
   finally:resume.set();worker.join(10)
  self.assertEqual(self.state()[2][-1]["role"],"customer")
  self.assertFalse(self.state()[0]);self.assertIsNotNone(self.state()[1])
 def test_human_reply_sends_while_ai_paused(self):
  chat="whatsapp:123:12025550100";self.queue(chat=chat)
  with SessionLocal() as db:
   db.add(WhatsAppReply(business_id=self.bids[0],conversation_id=chat,text="stale auto",send_after=0));db.commit()
  response=self.client.patch(f"/conversations/{chat}/attention",json={"action":"reply","message":"Una persona te está atendiendo"})
  self.assertEqual(response.status_code,200)
  with patch("app.services.whatsapp_service.whatsapp_channels",return_value={"123":{"business_id":self.bids[0],"access_token":"fake"}}),patch("app.services.whatsapp_service.send_text",return_value="fake-sent") as send:
   self.assertTrue(dispatch_reply(business_id=self.bids[0]));send.assert_called_once()
   self.assertEqual(send.call_args.args[2],"Una persona te está atendiendo")
  self.assertTrue(self.state(chat)[0])
 def test_semantic_complaint_creates_alert_before_any_order(self):
  self.queue("Esto fue una experiencia horrible")
  with patch("app.api.conversations.plan_message",return_value=self.decision("complaint")):
   self.assertTrue(process_due(business_id=self.bids[0]))
  self.assertTrue(self.state()[0]);self.assertEqual(self.client.get("/alerts/").json()["pending_count"],1)
 def test_attachment_is_private_and_requires_review(self):
  self.queue("Adjunto una imagen",attachment={"media_id":"456","phone_number_id":"123","kind":"image"})
  alert=self.client.get("/alerts/").json()["items"][0]
  self.assertTrue(alert["has_attachment"]);self.assertTrue(self.state()[0])
  with patch("app.api.alerts.download_attachment",return_value=(b"fake bytes","adjunto.pdf")):
   response=self.client.get(f"/alerts/{alert['id']}/attachment")
   self.assertEqual(response.content,b"fake bytes");self.assertEqual(response.headers["cache-control"],"no-store")
   self.user=SimpleNamespace(id=self.uid,business_id=self.bids[1])
   self.assertEqual(self.client.get(f"/alerts/{alert['id']}/attachment").status_code,404)
 def test_attachment_download_rejects_external_origins(self):
  from app.api.alerts import download_attachment
  opener=MagicMock()
  opener.open.return_value=BytesIO(json.dumps({"url":"https://evil.example/collect","file_size":1}).encode())
  with patch("app.api.alerts.whatsapp_channels",return_value={"123":{"business_id":self.bids[0],"access_token":"fake"}}),patch("app.api.alerts.build_opener",return_value=opener):
   with self.assertRaises(HTTPException) as rejected:
    download_attachment({"phone_number_id":"123","media_id":"456"},self.bids[0])
   self.assertEqual(rejected.exception.status_code,502)
   self.assertEqual(opener.open.call_count,1)
   self.assertIn("phone_number_id=123",opener.open.call_args.args[0].full_url)
 def test_failed_model_defers_only_its_chat(self):
  self.queue()
  with patch("app.api.conversations.plan_message",side_effect=RuntimeError("offline")):
   with self.assertRaises(RuntimeError):process_due(business_id=self.bids[0])
  self.assertGreater(self.state()[1],int(time.time()))

if __name__=="__main__":unittest.main(verbosity=2)
