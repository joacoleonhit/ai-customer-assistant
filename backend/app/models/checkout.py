from sqlalchemy import Column, ForeignKey, Integer, String, Text

from app.core.database import Base


class MercadoPagoCheckout(Base):
    __tablename__ = "mercado_pago_checkouts"

    order_id = Column(Integer, ForeignKey("orders.id"), primary_key=True)
    provider_order_id = Column(String(100), nullable=False, unique=True)
    seller_id = Column(String(32), nullable=False)
    checkout_url = Column(Text, nullable=False)
