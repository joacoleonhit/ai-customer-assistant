from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    CheckConstraint
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class PaymentProvider(str, Enum):
    MERCADO_PAGO = "MERCADO_PAGO"
    NARANJA_X = "NARANJA_X"
    BANCO_NACION = "BANCO_NACION"
    OTHER = "OTHER"


class Business(Base):
    __tablename__ = "businesses"

    __table_args__ = (
        CheckConstraint(
            "cbu IS NOT NULL OR alias IS NOT NULL",
            name="check_business_payment_data"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    cbu = Column(String, nullable=True)
    alias = Column(String, nullable=True)

    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)

    active = Column(Boolean, default=True)
    payment_provider = Column(String(32), nullable=True)

    users = relationship(
        "User",
        back_populates="business"
    )
    products = relationship(
    "Product",
    back_populates="business"
    )
    orders = relationship(
        "Order",
        back_populates="business"
    )