"""Real API/DB tests of the portfolio demo, with external transports forbidden."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.main import app
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models.business import Business
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.order_draft import OrderDraft
from app.models.conversation import Conversation, ConversationEvent, ConversationAlert, WhatsAppReply


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ENABLE_DEMO": "true", "DEMO_AI_PROVIDER": "simulated", "DEMO_ONLY": "true"})
        self.env.start()
        self.client = TestClient(app)
        self.bids = []
        self.headers = self.workspace()

    def workspace(self):
        response = self.client.post("/demo/session")
        self.assertEqual(response.status_code, 201, response.text)
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        user = self.client.get("/auth/me", headers=headers).json()
        self.bids.append(user["business_id"])
        self.assertTrue(user["is_demo"])
        return headers

    def tearDown(self):
        self.client.close()
        with SessionLocal.begin() as db:
            for model in [ConversationAlert, WhatsAppReply, ConversationEvent, OrderDraft, OrderItem, Order, Product, Conversation, User]:
                if hasattr(model, "business_id"):
                    db.execute(delete(model).where(model.business_id.in_(self.bids)))
                elif model is OrderItem:
                    db.execute(delete(model).where(model.order_id.in_(select(Order.id).where(Order.business_id.in_(self.bids)))))
            db.execute(delete(Business).where(Business.id.in_(self.bids)))
        self.env.stop()

    def get(self, path, headers=None):
        return self.client.get(path, headers=headers or self.headers)

    def send(self, message, event=None):
        response = self.client.post("/demo/messages", headers=self.headers, json={"message": message, "event_id": event or str(uuid4())})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def pending(self):
        return next(o for o in self.get("/orders/").json() if o["payment_status"] == "PENDING" and o["payment_method"] == "TRANSFER")

    def test_isolated_seed_and_cross_tenant_access(self):
        other = self.workspace()
        own = self.get("/orders/").json()
        self.assertEqual(len(own), 3)
        self.assertEqual(len(self.get("/products/").json()), 10)
        self.assertEqual(self.get("/orders/" + str(own[0]["id"]), other).status_code, 404)
        self.assertEqual(self.client.post("/demo/orders/" + str(own[0]["id"]) + "/payment", headers=other, json={"result": "approved"}).status_code, 404)

    def test_order_flow_and_event_idempotency_without_external_apis(self):
        with patch("app.services.conversation_ai.interpret_with_ollama", side_effect=AssertionError("Unexpected AI API")), patch("app.services.whatsapp_service.dispatch_reply", side_effect=AssertionError("Unexpected WhatsApp send")):
            quote = self.send("Quiero dos muzzas para retirar y pago por transferencia")
            self.assertIsNotNone(quote["draft_id"])
            accepted = self.send("Sí, confirmo", "same-confirmation")
            self.assertIsNotNone(accepted["order_id"])
            self.send("Sí, confirmo", "same-confirmation")
        self.assertEqual(len(self.get("/orders/").json()), 4)
        order = self.get("/orders/" + str(accepted["order_id"])).json()
        self.assertEqual(str(order["total"]), "17000.00")
        self.assertEqual(order["payment_status"], "PENDING")
        self.assertIn("DEMO.NO.TRANSFERIR", accepted["history"][-1]["text"])

    def test_claim_pending_then_simulated_payment_closes_alert(self):
        self.send("Quiero dos muzzas para retirar y pago por transferencia")
        order_id = self.send("Sí, confirmo")["order_id"]
        claim = self.send("Ya hice la transferencia")
        self.assertEqual(claim["order_id"], order_id)
        self.assertEqual(len(self.get("/orders/").json()), 4)
        self.assertEqual(self.get("/orders/"+str(order_id)).json()["payment_status"], "PENDING")
        self.assertEqual(self.get("/alerts/").json()["pending_count"], 1)
        rejected = self.client.post(f"/demo/orders/{order_id}/payment", headers=self.headers, json={"result": "rejected"})
        self.assertEqual(rejected.json()["payment_status"], "PENDING")
        for _ in range(2):
            response = self.client.post(f"/demo/orders/{order_id}/payment", headers=self.headers, json={"result": "approved"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "CONFIRMED")
        self.assertEqual(self.get("/alerts/").json()["pending_count"], 0)
        self.send("Quiero hablar con una persona")
        self.assertEqual(self.get("/alerts/").json()["items"][0]["order_id"], order_id)

    def test_human_takeover_reply_and_release(self):
        response = self.send("Quiero hablar con una persona")
        self.assertTrue(response["manual"])
        path = "/conversations/demo:customer/attention"
        human = self.client.patch(path, headers=self.headers, json={"action": "reply", "message": "Hola, soy una persona del local."})
        self.assertEqual(human.status_code, 200, human.text)
        self.assertEqual(self.get("/demo/state").json()["history"][-1]["text"], "Hola, soy una persona del local.")
        self.client.patch(path, headers=self.headers, json={"action": "release"})
        self.assertFalse(self.get("/demo/state").json()["manual"])
        with SessionLocal() as db:
            self.assertEqual(len(db.scalars(select(WhatsAppReply).where(WhatsAppReply.business_id == self.bids[0])).all()), 0)

    def test_model_error_can_retry_without_duplicate_turns(self):
        from fastapi import HTTPException
        with patch.dict(os.environ, {"DEMO_AI_PROVIDER": "ollama"}), patch("app.services.conversation_ai.interpret_with_ollama", side_effect=HTTPException(503, "Modelo temporalmente no disponible")):
            response = self.client.post("/demo/messages", headers=self.headers, json={"message": "Hola", "event_id": "retry-once"})
        self.assertEqual(response.status_code, 503)
        retry = self.client.post("/demo/process", headers=self.headers)
        self.assertEqual(retry.status_code, 200, retry.text)
        history = retry.json()["history"]
        self.assertEqual(len([turn for turn in history if turn["role"] == "customer"]), 1)
        self.assertEqual(history[-1]["role"], "assistant")

    def test_optional_ai_provider_is_used_only_when_selected(self):
        from app.services.conversation_ai import Interpretation
        decision = Interpretation(action="reply", message="Hola desde el modelo de prueba", items=[], delivery_type=None, delivery_address=None, payment_method=None)
        with patch.dict(os.environ, {"DEMO_AI_PROVIDER": "ollama"}), patch("app.services.conversation_ai.interpret_with_ollama", return_value=decision) as model:
            response = self.send("Hola, todo bien?")
            model.assert_called_once()
        self.assertEqual(response["history"][-1]["text"], decision.message)

    def test_expired_cleanup_preserves_active_demo(self):
        from app.services.demo_cleanup import cleanup_expired
        import time
        with SessionLocal.begin() as db:
            user = db.scalar(select(User).where(User.business_id == self.bids[0]))
            user.email = f"demo-{int(time.time())-4000}-{uuid4().hex}@demo.example.com"
        other = self.workspace()  # creation prunes the expired fixture
        self.assertEqual(self.get("/demo/state").status_code, 401)
        self.assertEqual(self.get("/demo/state", other).status_code, 200)

    def test_demo_cannot_reach_real_integrations_or_public_business_creation(self):
        for method, path in [("post", "/businesses/me/mercado-pago/connect"), ("post", "/businesses/"), ("post", "/auth/register-business"), ("get", "/businesses/"), ("put", "/businesses/me/whatsapp/simulation"), ("post", "/orders/1/checkout-pro"), ("post", "/orders/1/confirm-transfer")]:
            response = getattr(self.client, method)(path, headers=self.headers)
            self.assertEqual(response.status_code, 403, (path, response.text))
        self.assertIn(self.client.get("/orders/").status_code, (401, 403))

    def test_disabled_entry_and_real_user_cannot_simulate_payment(self):
        with patch.dict(os.environ, {"ENABLE_DEMO": "false"}):
            self.assertEqual(self.client.post("/demo/session").status_code, 404)
        with SessionLocal.begin() as db:
            real_business = Business(name="QA real profile", alias="qa.no-transferir")
            db.add(real_business); db.flush(); self.bids.append(real_business.id)
            from app.models.user import UserRole
            real_user = User(name="QA", email=uuid4().hex+"@example.com", password_hash="not-used", role=UserRole.ADMIN, business_id=real_business.id)
            db.add(real_user); db.flush()
            real_token = create_access_token(real_user.id, real_business.id, real_user.role.value)
        self.assertEqual(self.client.post("/demo/process", headers={"Authorization": "Bearer " + real_token}).status_code, 403)
        with SessionLocal() as db:
            demo_user = db.scalar(select(User).where(User.business_id == self.bids[0]))
            unsigned_demo = create_access_token(demo_user.id, demo_user.business_id, demo_user.role.value)
        response = self.client.post("/demo/process", headers={"Authorization": "Bearer " + unsigned_demo})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
