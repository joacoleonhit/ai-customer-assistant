from app.core.database import Base
from sqlalchemy import Column, Integer, ForeignKey, String, Enum, Numeric,DateTime,CheckConstraint
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from sqlalchemy import func

class OrderStatus(str, PyEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PREPARING = "PREPARING"
    READY = "READY"
    ON_THE_WAY = "ON_THE_WAY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"

class DeliveryType(str,PyEnum):
    PICKUP = "PICKUP"
    DELIVERY = "DELIVERY"

class PaymentMethod(str,PyEnum):
    TRANSFER="TRANSFER"
    CASH="CASH"

class PaymentStatus(str,PyEnum):
    PENDING="PENDING"
    CONFIRMED="CONFIRMED"



class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    business_id = Column(
        Integer,
        ForeignKey("businesses.id"),
        index=True,
        nullable=False
    )
    business = relationship("Business", back_populates="orders")
    items = relationship("OrderItem",back_populates="order")

    customer_phone = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)

    status = Column(
        Enum(OrderStatus),
        default=OrderStatus.PENDING,
        server_default="PENDING", ## Valor predeterminado directamente en PostgreSQL (migracion)
        nullable=False
    )
    
    delivery_type = Column(
            Enum(DeliveryType),
            nullable=False
        )

    delivery_address = Column(
        String,
        nullable= True,

    )

    notes = Column(
        String,
        nullable=True,

    )

    total = Column(
        Numeric(10, 2),
        nullable= False

    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    payment_method = Column(
        Enum(PaymentMethod),
        nullable=True
        )

    payment_status = Column(
        Enum(PaymentStatus),
        nullable=False,
        default=PaymentStatus.PENDING,
        )

class OrderItem(Base):
    __tablename__ = "order_items" #sql

    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(
        Integer,
        ForeignKey("orders.id"), #foreignkey para bases de datos e Ids para asignar en sql
        index=True,
        nullable=False
    )

    order= relationship("Order", back_populates="items") #hablamos de python con "Order". con back_populate podemos hacer el camino inverso y revisamos todos los items

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        index=True,
        nullable=False,
    
    )

    product = relationship("Product",back_populates="order_items")

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="check_quantity_positive"
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="check_unit_price_non_negative"
        ),
        CheckConstraint(
            "subtotal   >= 0",
            name="check_subtotal_non_negative"
        ),
    )
    quantity = Column(Integer,nullable=False)
    unit_price=Column(Numeric(10,2),nullable=False)
    subtotal= Column(Numeric(10,2) ,nullable=False)

    product_name=Column(String,nullable=False)