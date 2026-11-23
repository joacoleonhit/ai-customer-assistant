import re
import os
import time
import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.checkout import create_order_checkout, merchant_config
from app.api.orders import confirm_conversation_draft, create_conversation_draft
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.business import Business, PaymentProvider
from app.models.conversation import Conversation, ConversationEvent, WhatsAppReply
from app.models.mercado_pago import MercadoPagoConnection
from app.models.order import DeliveryType, Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.order_draft import OrderDraft
from app.models.product import Product
from app.models.user import User
from app.schemas.order import ConversationDraftConfirmation, ConversationDraftRequest
from app.services.payment_settings import has_transfer_destination
from app.services.conversation_ai import interpret_message
from app.services.chat_attention import inspect_incoming, pause_chat, quick_signal

router = APIRouter(prefix="/conversations", tags=["Conversations"])
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}
NUMBER = r"\d+|un|una|uno|dos|tres|cuatro|cinco"


class Turn(BaseModel):
    role: Literal["customer", "assistant"]
    text: str = Field(min_length=1, max_length=3000)


class IncomingMessage(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    customer_phone: str = Field(min_length=7, max_length=32)
    message: str = Field(min_length=1, max_length=3000)
    draft_id: str | None = Field(default=None, max_length=32)
    history: list[Turn] = Field(default_factory=list, max_length=20)


class MessageReply(BaseModel):
    message: str
    draft_id: str | None = None
    order_id: int | None = None
    checkout_url: str | None = None


def normalize(value: str) -> str:
    chars = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in chars if not unicodedata.combining(c))))


def quantity(value: str) -> int:
    return int(value) if value.isdecimal() else NUMBERS[value]


def product_names(product):
    name = normalize(product.name)
    names = {name} if name else set()
    if name in {"pizza muzzarella", "muzzarella", "pizza mozzarella", "mozzarella", "muzza"}:
        names.update({"muzza", "muzzarella", "mozzarella", "pizza muzza"})
    return names


def mentions_product(text, product):
    return any(re.search(rf"\b{re.escape(name)}s?\b", text) for name in product_names(product))


def collect_details(texts, catalog, previous):
    items = {item["product_id"]: item["quantity"] for item in previous.get("items", [])}
    delivery = previous.get("delivery_type")
    payment = previous.get("payment_method")
    address = previous.get("delivery_address")

    available_names = [(product, product_names(product)) for product in catalog]
    for text in texts:
        clean = normalize(text)
        if "?" in text and not re.search(r"\b(quiero|mandame|agrega|pone|mejor)\b", clean):
            continue
        for product, names in available_names:
            for name in sorted(names, key=len, reverse=True):
                if name != normalize(product.name) and sum(name in options for _, options in available_names) > 1:
                    continue
                pattern = re.escape(name).replace(r"\ ", r"s?\s+", 1) if name.startswith("pizza ") else re.escape(name)
                match = re.search(rf"\b({NUMBER})\s+{pattern}s?\b", clean)
                if match:
                    items[product.id] = quantity(match[1])
                    break
        edit = re.fullmatch(rf"mejor ({NUMBER})(?: sol[oa]s?)?", clean)
        if edit and len(items) == 1:
            items[next(iter(items))] = quantity(edit[1])
        if re.search(r"\b(retir[oa]r?|paso a buscar)\b", clean):
            delivery, address = "PICKUP", None
        if re.search(r"\b(envio|delivery|entrega)\b", clean):
            delivery = "DELIVERY"
        address_match = re.search(r"(?:direcci[oó]n\s*:?|env[ií]o a)\s+(.+)$", text, re.IGNORECASE)
        if address_match:
            address = address_match[1].strip()
        if "efectivo" in clean.split():
            payment = "CASH"
        elif "transferencia" in clean.split():
            payment = "TRANSFER"
    return items, delivery, payment, address


def transfer_details(business: Business) -> str:
    lines = []
    if business.alias and business.alias.strip():
        lines.append(f"Alias: {business.alias.strip()}")
    if business.cbu and business.cbu.strip():
        lines.append(f"CBU/CVU: {business.cbu.strip()}")
    return "\n".join(lines)


def payment_reply(db: Session, order: Order, draft_id: str) -> MessageReply:
    received = f"Recibimos tu pedido #{order.id}."
    response = {"order_id": order.id, "draft_id": draft_id}
    if order.status == OrderStatus.CANCELLED:
        return MessageReply(message=f"El pedido #{order.id} está cancelado.", **response)
    if order.payment_status == PaymentStatus.CONFIRMED:
        return MessageReply(message=f"{received} El pago está confirmado.", **response)

    amount = f"${order.total:.2f} ARS"
    if order.payment_method == PaymentMethod.CASH:
        moment = "al recibirlo" if order.delivery_type == DeliveryType.DELIVERY else "al retirarlo"
        return MessageReply(message=f"{received} Pagás {amount} en efectivo {moment}.", **response)

    business = db.get(Business, order.business_id)
    if not transfer_details(business):
        return MessageReply(message=f"{received} El local debe configurar un alias o CBU/CVU antes de recibir transferencias.", **response)
    checkout_enabled = db.get(MercadoPagoConnection, order.business_id) is not None
    if business.payment_provider == PaymentProvider.MERCADO_PAGO and not checkout_enabled:
        try:
            merchant_config(order.business_id)
            checkout_enabled = True
        except HTTPException as error:
            if error.status_code != 503:
                raise
    if business.payment_provider == PaymentProvider.MERCADO_PAGO and checkout_enabled:
        try:
            checkout = create_order_checkout(db, order.business_id, order.id)
        except HTTPException as error:
            if error.status_code not in (409, 502, 503):
                raise
            db.rollback()
            if order.payment_status == PaymentStatus.CONFIRMED:
                return MessageReply(message=f"{received} El pago está confirmado.", **response)
            if order.status == OrderStatus.CANCELLED:
                return MessageReply(message=f"El pedido #{order.id} está cancelado.", **response)
            return MessageReply(
                message=f"{received} No pude obtener el enlace. Volvé a confirmar para pedirlo otra vez.",
                **response,
            )
        return MessageReply(
            message=f"{received} Pagá {amount} con este enlace: {checkout.checkout_url}",
            checkout_url=checkout.checkout_url,
            **response,
        )
    details = transfer_details(business)
    if not details:
        return MessageReply(message=f"{received} El local todavía no tiene datos de transferencia configurados. Consultá con el comercio antes de pagar.", **response)
    return MessageReply(
        message=f"{received}\nTotal a transferir: {amount}\n{details}\nEl pago queda pendiente hasta que el local verifique la acreditación.",
        **response,
    )


@router.post("/messages", response_model=MessageReply)
def handle_message(
    data: IncomingMessage,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _handle_message(data, db, user)


def load_message_context(data, db, user):
    draft = None
    if data.draft_id:
        draft = db.scalar(select(OrderDraft).filter_by(
            id=data.draft_id, business_id=user.business_id, conversation_id=data.conversation_id,
        ))
        if draft is None or draft.payload["customer_phone"] != data.customer_phone:
            raise HTTPException(404, "Borrador no encontrado")

    catalog = db.scalars(select(Product).filter_by(business_id=user.business_id, active=True)).all()
    saved_order = db.get(Order, draft.order_id) if draft is not None and draft.order_id else None
    order_context = {
        "has_pending_summary": draft is not None and saved_order is None,
        "order_exists": saved_order is not None,
        "order_status": saved_order.status.value if saved_order is not None else None,
        "payment_status": saved_order.payment_status.value if saved_order is not None else "PENDING",
        "summary": {key: draft.payload.get(key) for key in (
            "items", "delivery_type", "delivery_address", "payment_method",
        )} if draft is not None else None,
    }
    return draft, catalog, order_context, saved_order


def plan_message(data, db, user):
    draft, catalog, order_context, saved_order = load_message_context(data, db, user)
    return interpret_message(
        data.message,
        [turn.model_dump() for turn in data.history[-16:]],
        [{"id": p.id, "name": p.name, "description": p.description, "price_ars": str(p.price)} for p in catalog],
        order_context=order_context,
        **({"provider_override": os.getenv("DEMO_AI_PROVIDER", "simulated")} if data.conversation_id.startswith("demo:") else {}),
    )



_UNPLANNED = object()


def handle_planned_message(data, db, user, decision):
    return _handle_message(data, db, user, decision)


def _handle_message(data, db, user, decision=_UNPLANNED):
    draft, catalog, order_context, saved_order = load_message_context(data, db, user)
    if decision is _UNPLANNED:
        decision = plan_message(data, db, user)
    if getattr(decision, "attention_reason", None) == "complaint":
        return MessageReply(message="Esta consulta necesita atención de una persona del local.", draft_id=data.draft_id)
    text = normalize(data.message)
    local_confirmation = text in {
        "confirmo", "si confirmo", "confirmo el pedido", "si confirmo el pedido",
        "si", "dale", "si dale", "si por favor", "acepto", "acepto el pedido",
        "si esta bien", "dale mandalo", "mandalo", "dale confirmo", "si perfecto",
    } and "?" not in data.message and "\u00bf" not in data.message
    confirmation = decision.action == "confirm" if decision is not None else local_confirmation
    if confirmation and draft is not None:
        try:
            order = confirm_conversation_draft(
                draft.id, ConversationDraftConfirmation(conversation_id=data.conversation_id), db, user,
            )
        except HTTPException as error:
            if error.status_code != 409:
                raise
            return MessageReply(message="Cambió el resumen. Volvé a pedirme el total antes de confirmar.", draft_id=draft.id)
        return payment_reply(db, order, draft.id)

    active = draft if draft is not None and draft.order_id is None else None
    active_id = draft.id if draft is not None else None
    if decision is None and quick_signal(data.message) == "transfer_claim":
        if saved_order is not None and saved_order.payment_status == PaymentStatus.CONFIRMED:
            message = f"El pago del pedido #{saved_order.id} ya figura confirmado por el local."
        else:
            message = "El local revisará el aviso de transferencia. El pago sigue pendiente hasta verificar la acreditación."
        return MessageReply(message=message, draft_id=active_id, order_id=saved_order.id if saved_order else None)
    if confirmation:
        return MessageReply(message="Primero armemos el pedido. ¿Qué te gustaría pedir?")
    if decision is None and text in {"todo bien", "hola todo bien", "como estas", "como andas"}:
        return MessageReply(message="¡Todo bien, gracias! ¿En qué te puedo ayudar?", draft_id=active_id)
    if decision is None and text in {"hola", "hola como estas", "buenas", "buen dia", "buenas tardes", "buenas noches"}:
        return MessageReply(message="¡Hola! ¿Cómo estás? Contame en qué te puedo ayudar.", draft_id=active_id)

    if decision is not None:
        payment_information = decision.action == "payment_details" or (
            decision.action == "reply" and re.search(
                r"\b(alias|cbu|cvu|transferi)\b", normalize(decision.message),
            )
        )
        if payment_information:
            if saved_order is not None:
                return payment_reply(db, saved_order, draft.id)
            if active is not None and active.payload.get("payment_method") == "CASH":
                return MessageReply(message="Tu resumen figura en efectivo. ¿Querés cambiar el medio de pago a transferencia?", draft_id=active_id)
            business = db.get(Business, user.business_id)
            details = transfer_details(business)
            if not details:
                return MessageReply(message="El local todavía no tiene datos de transferencia configurados. Consultá con el comercio antes de pagar.", draft_id=active_id)
            return MessageReply(message=f"Datos de transferencia del local:\n{details}\nAntes de transferir, confirmá el resumen del pedido. El pago requiere verificación del local.", draft_id=active_id)
        if decision.action == "off_topic":
            return MessageReply(
                message="Puedo ayudarte con consultas del local y con tu pedido.",
                draft_id=active_id,
            )
        if decision.action == "reply":
            # Never send a model-copied order total: regenerate the pending quote
            # from current catalog prices, retaining server-owned order details.
            reply_text = normalize(decision.message)
            if active is not None and (
                re.search(r"\btotal\b", reply_text)
                or "asi quedaria tu pedido" in reply_text
                or "resumen del pedido" in reply_text
            ):
                try:
                    updated = create_conversation_draft(
                        ConversationDraftRequest(
                            conversation_id=data.conversation_id, **active.payload,
                        ), db, user,
                    )
                except (HTTPException, ValueError) as error:
                    if isinstance(error, HTTPException) and error.status_code != 422:
                        raise
                    return MessageReply(message="Cambió el catálogo. Revisemos los productos antes de confirmar.", draft_id=active_id)
                return MessageReply(message=updated.message, draft_id=updated.draft_id)
            return MessageReply(message=decision.message, draft_id=active_id)
        items = {item.product_id: item.quantity for item in decision.items}
        delivery = decision.delivery_type
        address = decision.delivery_address
        payment = decision.payment_method
    else:
        matches = [product for product in catalog if mentions_product(text, product)]
        if not matches and re.search(r"\bpizzas?\b", text):
            matches = [product for product in catalog if "pizza" in normalize(product.name).split()]
        if "?" in data.message and not re.search(r"\b(quiero|mandame|agrega|pone|mejor)\b", text):
            if matches and re.search(r"\b(precio|cuanto|sale|cuesta|tienen|hay)\b", text) and not (active and "total" in text):
                answer = ", ".join(f"{p.name} a ${p.price:.2f} ARS" for p in matches)
                return MessageReply(message=f"Sí, tenemos {answer}.", draft_id=active_id)
            if not (active and re.search(r"\b(total|cuanto|resumen)\b", text)):
                return MessageReply(message="No tengo ese dato ahora. ¿Te puedo ayudar con tu pedido?", draft_id=active_id)

        if re.fullmatch(rf"mejor ({NUMBER})(?: sol[oa]s?)?", text) and active and len(active.payload["items"]) > 1:
            return MessageReply(message="¿De qué producto querés cambiar la cantidad?", draft_id=active_id)
        prior = active.payload if active else {}
        history = [] if active or saved_order else [turn.text for turn in data.history if turn.role == "customer"]
        items, delivery, payment, address = collect_details([*history, data.message], catalog, prior)
        if active and (
            items == {item["product_id"]: item["quantity"] for item in prior["items"]}
            and delivery == prior["delivery_type"]
            and payment == prior["payment_method"]
            and address == prior["delivery_address"]
            and not re.search(r"\b(total|cuanto|resumen)\b", text)
        ):
            return MessageReply(
                message="¿Querés confirmar el pedido o hacer algún cambio?",
                draft_id=active_id,
            )
        if not items:
            return MessageReply(message="¿Qué producto querés y cuántas unidades?", draft_id=active_id)
        if not delivery:
            return MessageReply(message="¿Lo querés para retirar o con envío?", draft_id=active_id)
        if delivery == "DELIVERY" and not address:
            return MessageReply(message="¿Cuál es la dirección de entrega?", draft_id=active_id)
        if not payment:
            return MessageReply(message="¿Vas a pagar en efectivo o por transferencia?", draft_id=active_id)
    if payment == PaymentMethod.TRANSFER:
        business = db.get(Business, user.business_id)
        if business is None or not has_transfer_destination(business):
            return MessageReply(
                message="El local todavía no tiene alias ni CBU/CVU configurado y no puede recibir transferencias. Podés elegir efectivo o consultar con el comercio.",
                draft_id=active_id,
            )
    try:
        updated = create_conversation_draft(
            ConversationDraftRequest(
                conversation_id=data.conversation_id,
                customer_phone=data.customer_phone,
                items=[{"product_id": pid, "quantity": qty} for pid, qty in items.items()],
                delivery_type=delivery,
                delivery_address=address,
                payment_method=payment,
            ),
            db, user,
        )
    except (HTTPException, ValueError) as error:
        if isinstance(error, HTTPException) and error.status_code != 422:
            raise
        return MessageReply(message="No pude armar el resumen. ¿Revisamos los productos y las cantidades?", draft_id=active_id)
    return MessageReply(message=updated.message, draft_id=updated.draft_id)


# These routes are used by the local simulator and can later be called by the
# WhatsApp adapter after it has verified the incoming webhook.


READ_WAIT_SECONDS = 5 * 60


class ClientAttachment(BaseModel):
    media_id: str = Field(pattern=r"^[0-9]{1,64}$")
    phone_number_id: str = Field(pattern=r"^[0-9]{1,32}$")
    kind: Literal["image", "document"]


class QueuedMessage(BaseModel):
    event_id: str = Field(min_length=1, max_length=160)
    customer_phone: str = Field(min_length=7, max_length=32)
    message: str = Field(min_length=1, max_length=3000)
    attachment: ClientAttachment | None = None


class AttentionUpdate(BaseModel):
    action: Literal["read", "takeover", "release", "reply"]
    message: str | None = Field(default=None, min_length=1, max_length=3000)


def locked_conversation(db, business_id, conversation_id):
    return db.scalar(select(Conversation).filter_by(
        business_id=business_id, id=conversation_id,
    ).with_for_update())


def conversation_state(chat):
    return {
        "conversation_id": chat.id,
        "manual": chat.manual,
        "phone": chat.phone,
        "updated_at": chat.updated_at,
        "due_at": chat.due_at,
        "history": chat.history,
        "draft_id": chat.draft_id,
    }


def add_turn(chat, role, text, event_id=None, attachment=None):
    turn = {"role": role, "text": text}
    if event_id: turn["event_id"] = event_id
    if attachment: turn["attachment"] = attachment
    chat.history = [*chat.history, turn][-17:]
    chat.updated_at = int(time.time())


@router.post("/{conversation_id}/incoming")
def queue_message(
    conversation_id: str, data: QueuedMessage,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    if data.attachment is not None:
        raise HTTPException(422, "Los adjuntos deben ingresar por WhatsApp verificado")
    if conversation_id.startswith("whatsapp:"):
        raise HTTPException(422, "Identificador reservado para WhatsApp")
    return queue_incoming_message(conversation_id, data, db, user.business_id)


def queue_incoming_message(conversation_id: str, data: QueuedMessage, db: Session, bid: int):
    if not conversation_id or len(conversation_id) > 128:
        raise HTTPException(422, "Identificador de conversación inválido")
    try:
        with db.begin_nested():
            chat = locked_conversation(db, bid, conversation_id)
            if chat is None:
                chat = Conversation(business_id=bid, id=conversation_id, phone=data.customer_phone)
                db.add(chat)
                db.flush()
            if chat.phone != data.customer_phone:
                raise HTTPException(409, "La conversación pertenece a otro cliente")
            db.add(ConversationEvent(business_id=bid, event_id=data.event_id, conversation_id=chat.id))
            db.flush()
            add_turn(chat, "customer", data.message, data.event_id,
                     data.attachment.model_dump() if data.attachment else None)
            inspect_incoming(db, chat, data.message, data.event_id,
                             data.attachment.model_dump() if data.attachment else None)
            if chat.due_at is None and not chat.manual:
                chat.due_at = int(time.time())
    except IntegrityError:
        if db.get(ConversationEvent, (bid, data.event_id)) is not None:
            return {"queued": False, "duplicate": True}
        # Another worker may have created the first conversation row concurrently.
        chat = locked_conversation(db, bid, conversation_id)
        if chat is None:
            raise
        if chat.phone != data.customer_phone:
            raise HTTPException(409, "La conversación pertenece a otro cliente")
        try:
            with db.begin_nested():
                db.add(ConversationEvent(business_id=bid, event_id=data.event_id, conversation_id=chat.id))
                db.flush()
                add_turn(chat, "customer", data.message, data.event_id,
                         data.attachment.model_dump() if data.attachment else None)
                inspect_incoming(db, chat, data.message, data.event_id,
                                 data.attachment.model_dump() if data.attachment else None)
                if chat.due_at is None and not chat.manual:
                    chat.due_at = int(time.time())
        except IntegrityError:
            if db.get(ConversationEvent, (bid, data.event_id)) is not None:
                return {"queued": False, "duplicate": True}
            raise
    db.commit()
    return {"queued": True, "duplicate": False}


@router.patch("/{conversation_id}/attention")
def update_attention(
    conversation_id: str, data: AttentionUpdate,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    chat = locked_conversation(db, user.business_id, conversation_id)
    if chat is None:
        raise HTTPException(404, "Conversación no encontrada")
    if data.action == "read" and chat.due_at is not None:
        now = int(time.time())
        if chat.due_at <= now:
            chat.due_at = now + READ_WAIT_SECONDS
    elif data.action == "takeover":
        pause_chat(db, chat)
    elif data.action == "release":
        chat.manual = False
        chat.attention_version += 1
        chat.due_at = int(time.time()) if chat.history and chat.history[-1]["role"] == "customer" else None
    elif data.action == "reply":
        if not data.message or not data.message.strip():
            raise HTTPException(422, "Escribí la respuesta del local")
        pause_chat(db, chat)
        db.execute(delete(WhatsAppReply).where(
            WhatsAppReply.business_id == chat.business_id,
            WhatsAppReply.conversation_id == chat.id,
            WhatsAppReply.sent_id.is_(None), WhatsAppReply.manual_reply.is_(False),
        ))
        add_turn(chat, "assistant", data.message)
        if chat.id.startswith("whatsapp:"):
            db.add(WhatsAppReply(business_id=chat.business_id, conversation_id=chat.id,
                                text=data.message, send_after=int(time.time()), manual_reply=True))
        chat.due_at = None
    chat.updated_at = int(time.time())
    response = conversation_state(chat)
    db.commit()
    return response


@router.get("/")
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chats = db.scalars(select(Conversation).where(Conversation.business_id == user.business_id)
                      .order_by(Conversation.updated_at.desc(), Conversation.id).limit(100)).all()
    from app.models.order_draft import OrderDraft
    result = []
    for chat in chats:
        draft = db.get(OrderDraft, chat.draft_id) if chat.draft_id else None
        result.append({**conversation_state(chat), "order_id": draft.order_id if draft and draft.business_id == user.business_id else None})
    return result


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    chat = db.get(Conversation, (user.business_id, conversation_id))
    if chat is None:
        raise HTTPException(404, "Conversación no encontrada")
    draft = db.get(OrderDraft, chat.draft_id) if chat.draft_id else None
    return {**conversation_state(chat), "order_id": draft.order_id if draft and draft.business_id == user.business_id else None}
