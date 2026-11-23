from sqlalchemy import BigInteger, Column, ForeignKey, Integer, String, Text

from app.core.database import Base


class MercadoPagoConnection(Base):
    __tablename__ = "mercado_pago_connections"

    business_id = Column(Integer, ForeignKey("businesses.id"), primary_key=True)
    seller_id = Column(String(32), nullable=False)
    credentials = Column(Text, nullable=False)
    expires_at = Column(BigInteger, nullable=False)


class MercadoPagoAuthorization(Base):
    __tablename__ = "mercado_pago_authorizations"

    state_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    verifier = Column(String(128), nullable=False)
    expires_at = Column(BigInteger, nullable=False)
