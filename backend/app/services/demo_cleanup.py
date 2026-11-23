"""Remove only expired generated demo workspaces; never match real profiles."""
import re
import time
from sqlalchemy import delete, select
from app.models.business import Business
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderItem
from app.models.order_draft import OrderDraft
from app.models.conversation import Conversation, ConversationEvent, ConversationAlert, WhatsAppReply


def cleanup_expired(db, now=None):
    now = int(time.time()) if now is None else now
    candidates = db.execute(select(User.email, Business.id).join(Business, User.business_id == Business.id)
        .where(User.email.like("demo-%@demo.example.com"), Business.name == "La Esquina · Demo", Business.alias == "DEMO.NO.TRANSFERIR")).all()
    bids = []
    for email, bid in candidates:
        match = re.fullmatch(r"demo-([0-9]{10})-[a-f0-9]{32}@demo.example.com", email)
        if match and int(match[1]) + 3660 < now:
            bids.append(bid)
    if not bids:
        return 0
    for model in [ConversationAlert, WhatsAppReply, ConversationEvent, OrderDraft, OrderItem, Order, Product, Conversation, User]:
        if model is OrderItem:
            db.execute(delete(model).where(model.order_id.in_(select(Order.id).where(Order.business_id.in_(bids)))))
        else:
            db.execute(delete(model).where(model.business_id.in_(bids)))
    db.execute(delete(Business).where(Business.id.in_(bids)))
    return len(bids)
