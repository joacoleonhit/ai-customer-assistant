from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.business import Business
from app.schemas.business import BusinessCreate, BusinessPaymentUpdate, BusinessResponse
from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.models.user import User
from app.services.payment_settings import clean_payment_value

router = APIRouter(
    prefix="/businesses",
    tags=["Businesses"]
)


@router.post("/", response_model=BusinessResponse)
def create_business(
    business_data: BusinessCreate,
    db: Session = Depends(get_db)
):
    business = Business(
        name=business_data.name,
        payment_provider=business_data.payment_provider,
        cbu=business_data.cbu,
        alias=business_data.alias,
        phone=business_data.phone,
        address=business_data.address
    )

    db.add(business)
    db.commit()
    db.refresh(business)

    return business

@router.get("/", response_model=list[BusinessResponse])
def get_businesses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    businesses = db.query(Business).filter(Business.id == current_user.business_id).all()

    return businesses



@router.get("/me", response_model=BusinessResponse)
def get_my_business(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = db.get(Business, current_user.business_id)
    if business is None:
        raise HTTPException(404, "Negocio no encontrado")
    return business


@router.patch("/me/payment-settings", response_model=BusinessResponse)
def update_payment_settings(
    data: BusinessPaymentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    business = db.get(Business, admin.business_id)
    if business is None:
        raise HTTPException(404, "Negocio no encontrado")
    values = data.model_dump(exclude_unset=True)
    if not (clean_payment_value(values.get("cbu", business.cbu)) or clean_payment_value(values.get("alias", business.alias))):
        raise HTTPException(422, "La empresa debe tener al menos un CBU/CVU o un alias")
    for key, value in values.items():
        setattr(business, key, value)
    db.commit()
    db.refresh(business)
    return business
