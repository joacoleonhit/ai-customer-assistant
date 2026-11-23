from sqlalchemy import Column, ForeignKey, Integer, String

from app.core.database import Base


class WhatsAppConnection(Base):
    """Simulated connection. Live channels are configured separately."""
    __tablename__ = "whatsapp_connections"

    business_id = Column(Integer, ForeignKey("businesses.id"), primary_key=True)
    display_phone = Column(String(32), nullable=False)
    mode = Column(String(16), nullable=False)
