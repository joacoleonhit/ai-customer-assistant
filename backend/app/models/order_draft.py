from sqlalchemy import Column, ForeignKey, Integer, JSON, String

from app.core.database import Base


class OrderDraft(Base):
    __tablename__ = "order_drafts"

    id = Column(String(32), primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    conversation_id = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    quoted_items = Column(JSON, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True)
