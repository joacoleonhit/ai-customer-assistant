"""Isolated portfolio demo. No bank or WhatsApp transport is invoked here."""
import os
import secrets
import time
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, get_current_user, hash_password, is_demo_user
from app.models.business import Business, PaymentProvider
from app.models.conversation import Conversation, ConversationEvent
from app.models.order import Order, OrderItem, DeliveryType, OrderStatus, PaymentMethod, PaymentStatus
from app.models.order_draft import OrderDraft
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.order import OrderResponse
from app.api.conversations import QueuedMessage, queue_incoming_message, conversation_state
from app.services.order_service import confirm_direct_transfer

router = APIRouter(prefix="/demo", tags=["Portfolio demo"])
CHAT_ID = "demo:customer"
PHONE = "12025550100"
MENU = [
    ("Pizza muzzarella", "Pizza con salsa de tomate y muzzarella", "8500"),
    ("Pizza napolitana", "Pizza con tomate, ajo y muzzarella", "9800"),
    ("Pizza fugazzeta", "Pizza con cebolla y muzzarella", "10500"),
    ("Empanada de carne", "Empanada al horno", "1500"),
    ("Empanada de verdura", "Empanada al horno", "1400"),
    ("Hamburguesa clásica", "Hamburguesa con queso", "7200"),
    ("Papas fritas", "Porción individual", "3500"),
    ("Agua mineral", "Botella de 500 ml", "1800"),
    ("Gaseosa cola", "Botella de 1,5 litros", "3200"),
    ("Flan casero", "Porción de flan", "2800"),
]


def demo_enabled():
    return os.getenv("ENABLE_DEMO", "false").lower() == "true"


def require_demo(user: User = Depends(get_current_user)):
    if not demo_enabled() or not is_demo_user(user):
        raise HTTPException(403, "Esta acción está disponible únicamente en la demo")
    return user


@router.get("/config")
def config():
    return {"enabled": demo_enabled(), "provider": os.getenv("DEMO_AI_PROVIDER", "simulated"),
            "payments": "simulated", "whatsapp": "optional",
            "demo_only": os.getenv("DEMO_ONLY", "false").lower() == "true"}


@router.post("/session", status_code=201)
def create_session(db: Session = Depends(get_db)):
    if not demo_enabled():
        raise HTTPException(404, "Demo deshabilitada")
    # Cap persisted workspaces; serialized in PostgreSQL to prevent concurrent bypass.
    db.execute(text("SELECT pg_advisory_xact_lock(284799103)"))
    from app.services.demo_cleanup import cleanup_expired
    cleanup_expired(db)
    count = db.scalar(select(func.count()).select_from(User).where(User.email.like("%@demo.example.com")))
    if count >= 100:
        raise HTTPException(429, "Se alcanzó el límite de demos de esta instalación")
    business = Business(name="La Esquina · Demo", alias="DEMO.NO.TRANSFERIR", payment_provider=PaymentProvider.OTHER.value)
    db.add(business); db.flush()
    user = User(name="Visitante demo", email=f"demo-{int(time.time())}-{uuid4().hex}@demo.example.com",
                password_hash=hash_password(secrets.token_urlsafe(40)), business_id=business.id, role=UserRole.ADMIN)
    db.add(user)
    products = [Product(business_id=business.id, name=name, description=description, price=Decimal(price))
                for name, description, price in MENU]
    db.add_all(products); db.flush()
    for index, (state, paid, method) in enumerate([
        (OrderStatus.PENDING, PaymentStatus.PENDING, PaymentMethod.TRANSFER),
        (OrderStatus.PREPARING, PaymentStatus.PENDING, PaymentMethod.CASH),
        (OrderStatus.DELIVERED, PaymentStatus.CONFIRMED, PaymentMethod.TRANSFER),
    ]):
        product = products[index]
        order = Order(business_id=business.id, customer_phone=f"1202555010{index+1}",
                      customer_name=["Cliente de ejemplo A", "Cliente de ejemplo B", "Cliente de ejemplo C"][index],
                      delivery_type=DeliveryType.PICKUP, payment_method=method, payment_status=paid,
                      status=state, total=product.price*2, notes="Pedido ficticio para explorar el panel")
        db.add(order); db.flush()
        db.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name,
                         quantity=2, unit_price=product.price, subtotal=product.price*2))
    db.add(Conversation(business_id=business.id, id=CHAT_ID, phone=PHONE, history=[{
        "role": "assistant", "text": "¡Hola! Bienvenido a La Esquina. Podés consultar el catálogo o armar tu pedido. Esta es una demostración: no se realizan cobros ni envíos reales."
    }]))
    db.commit(); db.refresh(user)
    return {"access_token": create_access_token(user.id, business.id, user.role.value, demo=True),
            "token_type": "bearer", "expires_in": 3600}


@router.get("/state")
def state(db: Session = Depends(get_db), user: User = Depends(require_demo)):
    chat = db.get(Conversation, (user.business_id, CHAT_ID))
    if chat is None:
        raise HTTPException(404, "Chat de demo no encontrado")
    draft = db.get(OrderDraft, chat.draft_id) if chat.draft_id else None
    return {**conversation_state(chat), "order_id": draft.order_id if draft else None,
            "provider": os.getenv("DEMO_AI_PROVIDER", "simulated")}


class DemoMessage(BaseModel):
    message: str = Field(min_length=1, max_length=3000)
    event_id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,80}$")


@router.post("/messages")
def send_message(data: DemoMessage, db: Session = Depends(get_db), user: User = Depends(require_demo)):
    # One customer turn at a time; history and draft IDs are server-owned.
    chat = db.scalar(select(Conversation).filter_by(business_id=user.business_id, id=CHAT_ID).with_for_update())
    if chat is None:
        raise HTTPException(404, "Chat de demo no encontrado")
    duplicate = db.get(ConversationEvent, (user.business_id, data.event_id))
    if not duplicate:
        if chat.due_at is not None and not chat.manual:
            raise HTTPException(409, "Esperá la respuesta antes de enviar otro mensaje")
        count = db.scalar(select(func.count()).select_from(ConversationEvent).where(ConversationEvent.business_id == user.business_id))
        if count >= 120:
            raise HTTPException(429, "Esta demo admite hasta 120 mensajes. Podés iniciar una nueva.")
    if not duplicate:
        queue_incoming_message(CHAT_ID, QueuedMessage(event_id=data.event_id, customer_phone=PHONE, message=data.message), db, user.business_id)
    # The normal worker applies the same pricing, confirmation and attention rules.
    db.commit()
    from app.services.conversation_worker import process_due
    process_due(bind=db.get_bind(), business_id=user.business_id)
    db.expire_all()
    return state(db, user)


@router.post("/process")
def process(db: Session = Depends(get_db), user: User = Depends(require_demo)):
    chat = db.scalar(select(Conversation).filter_by(business_id=user.business_id, id=CHAT_ID).with_for_update())
    if chat is not None and not chat.manual and chat.due_at is not None:
        chat.due_at = min(chat.due_at, int(time.time()))
    db.commit()
    from app.services.conversation_worker import process_due
    process_due(bind=db.get_bind(), business_id=user.business_id)
    db.expire_all()
    return state(db, user)


class DemoPayment(BaseModel):
    result: Literal["approved", "rejected"]


@router.post("/orders/{order_id}/payment", response_model=OrderResponse)
def payment(order_id: int, data: DemoPayment, db: Session = Depends(get_db), user: User = Depends(require_demo)):
    order = db.scalar(select(Order).filter_by(id=order_id, business_id=user.business_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Pedido no encontrado")
    if order.payment_method != PaymentMethod.TRANSFER or order.status == OrderStatus.CANCELLED:
        raise HTTPException(409, "Este pedido no admite una simulación de transferencia")
    if data.result == "rejected":
        if order.payment_status == PaymentStatus.CONFIRMED:
            raise HTTPException(409, "El pago simulado ya está confirmado")
        return order
    try:
        return confirm_direct_transfer(db, user.business_id, order_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
