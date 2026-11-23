from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Numeric,
    ForeignKey
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id= Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    active = Column(Boolean, default=True, server_default="true", nullable=False) #nullbase es para que siempre tenga in valor, y default es para que siempre tenga un valor por defecto
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False, index=True)
    business = relationship("Business", back_populates="products")
    order_items = relationship("OrderItem",back_populates="product")