import time
from sqlalchemy import Index, text, BigInteger, Boolean, Column, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, Text
from app.core.database import Base


class Conversation(Base):
    __tablename__ = "customer_conversations"

    business_id = Column(Integer, ForeignKey("businesses.id"), primary_key=True)
    id = Column(String(128), primary_key=True)
    phone = Column(String(32), nullable=False)
    history = Column(JSON, nullable=False, default=list)
    draft_id = Column(String(32))
    due_at = Column(BigInteger, index=True)
    manual = Column(Boolean, nullable=False, default=False)
    attention_version = Column(Integer, nullable=False, default=0, server_default="0")
    updated_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))


class ConversationEvent(Base):
    __tablename__ = "customer_conversation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["customer_conversations.business_id", "customer_conversations.id"],
        ),
    )

    business_id = Column(Integer, primary_key=True)
    event_id = Column(String(160), primary_key=True)
    conversation_id = Column(String(128), nullable=False)


class WhatsAppReply(Base):
    __tablename__ = "whatsapp_replies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["customer_conversations.business_id", "customer_conversations.id"],
        ),
    )

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, nullable=False)
    conversation_id = Column(String(128), nullable=False)
    text = Column(Text, nullable=False)
    send_after = Column(BigInteger, nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    sent_id = Column(String(160))
    manual_reply = Column(Boolean, nullable=False, default=False, server_default="false")


class ConversationAlert(Base):
    __tablename__ = "conversation_alerts"
    __table_args__ = (
        ForeignKeyConstraint(["business_id", "conversation_id"],
                             ["customer_conversations.business_id", "customer_conversations.id"]),
    )
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, nullable=False)
    conversation_id = Column(String(128), nullable=False)
    kind = Column(String(24), nullable=False)
    message = Column(Text, nullable=False)
    event_id = Column(String(160))
    draft_id = Column(String(32))
    order_id = Column(Integer, ForeignKey("orders.id"))
    attachment = Column(JSON)
    created_at = Column(BigInteger, nullable=False, default=lambda: int(time.time()))
    resolved_at = Column(BigInteger)
    resolved_by = Column(Integer, ForeignKey("users.id"))

Index("ix_alert_business", ConversationAlert.business_id)
Index("uq_open_chat_alert", ConversationAlert.business_id, ConversationAlert.conversation_id,
      ConversationAlert.kind, unique=True, postgresql_where=text("resolved_at IS NULL"))
