from pydantic import BaseModel, model_validator, field_validator

from app.models.business import PaymentProvider
from app.services.payment_settings import clean_payment_value


class BusinessCreate(BaseModel):
    name: str
    payment_provider: PaymentProvider | None = None
    cbu: str | None = None
    alias: str | None = None
    phone: str | None = None
    address: str | None = None

    @field_validator("alias", "cbu", mode="before")
    @classmethod
    def clean_payment_fields(cls, value):
        return clean_payment_value(value)

    @model_validator(mode="after")
    def validate_payment_data(self):
        if not self.cbu and not self.alias:
            raise ValueError(
                "La empresa debe tener al menos un CBU o un alias"
            )

        return self

class BusinessPaymentUpdate(BaseModel):
    payment_provider: PaymentProvider | None
    cbu: str | None = None
    alias: str | None = None


    @field_validator("alias", "cbu", mode="before")
    @classmethod
    def clean_payment_fields(cls, value):
        return clean_payment_value(value)


class BusinessResponse(BaseModel):
    id: int
    name: str
    cbu: str | None = None
    alias: str | None = None
    phone: str | None = None
    address: str | None = None
    active: bool
    payment_provider: PaymentProvider | None = None

    model_config = {
        "from_attributes": True
    }