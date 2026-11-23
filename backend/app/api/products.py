from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.core.security import get_current_user


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED
)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    product = Product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        business_id=current_admin.business_id
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product

@router.get(
    "/",
    response_model=list[ProductResponse]
)
def get_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    products = db.query(Product).filter(
        Product.business_id == current_user.business_id
    ).all()

    return products

@router.patch(
    "/{product_id}",
    response_model=ProductResponse
)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == current_admin.business_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado"
        )

    update_data = product_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product

@router.patch(
    "/{product_id}/status",
    response_model=ProductResponse
)
def change_product_status(
    product_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == current_admin.business_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado"
        )

    product.active = active

    db.commit()
    db.refresh(product)

    return product

@router.get(
    "/{product_id}",
    response_model=ProductResponse
)
def get_product_url(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.business_id == current_user.business_id
    ).first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Producto no encontrado"
        )

    return product
