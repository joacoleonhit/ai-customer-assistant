from decimal import Decimal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=150
    )

    description: str | None = Field(
        default=None,
        max_length=1000
    )

    price: Decimal = Field(
        gt=0,
        max_digits=10,
        decimal_places=2
    )


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None
    price: Decimal
    active: bool
    business_id: int

    model_config = {
        "from_attributes": True
    }

class ProductUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150
    )

    description: str | None = Field(
        default=None,
        max_length=1000
    )

    price: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=2
    )