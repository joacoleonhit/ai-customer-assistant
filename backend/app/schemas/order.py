from pydantic import BaseModel, Field, model_validator, field_validator
from app.models.order import DeliveryType, OrderStatus, PaymentMethod, PaymentStatus
from decimal import Decimal
from datetime import datetime

class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

class OrderCreate(BaseModel):
    customer_phone: str
    customer_name:str | None = None
    delivery_type: DeliveryType
    delivery_address: str | None = None
    notes: str | None = None
    payment_method: PaymentMethod
    items: list[OrderItemCreate] = Field(min_length=1)


@model_validator(mode="after")
def validar_delivery(self):
    if (
        self.delivery_type == DeliveryType.DELIVERY
        and (
            not self.delivery_address
            or not self.delivery_address.strip()
        )
    ):
        raise ValueError("La dirección es obligatoria para delivery")

    return self



@field_validator("customer_phone")
def validar_phone(cls, value):
    permitidos = "+-() "

    value = value.strip()

    

    if not all(
        caracter.isdigit() or caracter in permitidos
        for caracter in value
    ): raise ValueError("El teléfono contiene caracteres no válidos")
        
    if not any(caracter.isdigit() for caracter in value):
        raise ValueError("El teléfono no posee numeros")

    cantidad_digitos = 0

    for caracter in value:
        if caracter.isdigit():
            cantidad_digitos += 1
    if cantidad_digitos < 7: 
        raise ValueError("El teléfono es demasiado corto")
    if cantidad_digitos > 15: 
        raise ValueError("El teléfono es demasiado largo")

    return value

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    business_id: int
    customer_phone: str
    customer_name: str | None = None
    status: OrderStatus
    delivery_type: DeliveryType
    delivery_address: str | None = None
    notes: str | None = None
    items: list[OrderItemResponse]
    total: Decimal
    created_at: datetime
    payment_method: PaymentMethod | None = None
    payment_status: PaymentStatus
    model_config = {"from_attributes": True}

class OrderPreviewRequest(BaseModel):
    items: list[OrderItemCreate] = Field(min_length=1)
    delivery_type: DeliveryType
    delivery_address: str | None = None
    payment_method: PaymentMethod

    @model_validator(mode="after")
    def require_delivery_address(self):
        if self.delivery_type == DeliveryType.DELIVERY and not (self.delivery_address or "").strip():
            raise ValueError("La dirección es obligatoria para delivery")
        return self


class OrderPreviewItem(OrderItemCreate):
    product_name: str
    unit_price: Decimal
    subtotal: Decimal


class OrderPreviewResponse(BaseModel):
    items: list[OrderPreviewItem]
    total: Decimal
    currency: str
    delivery_type: DeliveryType
    delivery_address: str | None
    payment_method: PaymentMethod
    message: str


class ConversationDraftRequest(OrderPreviewRequest):
    conversation_id: str = Field(min_length=1, max_length=128)
    customer_phone: str = Field(min_length=1, max_length=32)
    customer_name: str | None = None
    notes: str | None = None


class ConversationDraftResponse(OrderPreviewResponse):
    draft_id: str


class ConversationDraftConfirmation(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
