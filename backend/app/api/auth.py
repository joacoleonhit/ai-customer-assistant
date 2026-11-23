from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)

from app.models.business import Business
from app.core.permissions import require_admin
from app.models.user import User, UserRole
from app.schemas.business import BusinessCreate
from app.schemas.user import UserCreate, UserResponse
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


class BusinessRegistration(BusinessCreate):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    business_name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    alias: str | None = Field(default=None, min_length=1, max_length=64)
    cbu: str | None = Field(default=None, pattern=r"^[0-9]{22}$")

    @field_validator("name", "business_name", "alias", mode="before")
    @classmethod
    def strip_labels(cls, value):
        return value.strip() if isinstance(value, str) else value



@router.post("/register-business", response_model=UserResponse, status_code=201)
def register_business(data: BusinessRegistration, db: Session = Depends(get_db)):
    email = str(data.email)
    if db.query(User.id).filter(User.email == email).first():
        raise HTTPException(409, "Ya existe un usuario con ese email")

    business = Business(name=data.business_name, alias=data.alias, cbu=data.cbu)
    try:
        db.add(business)
        db.flush()
        user = User(
            name=data.name,
            email=email,
            password_hash=hash_password(data.password),
            role=UserRole.ADMIN,
            business_id=business.id,
        )
        db.add(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.query(User.id).filter(User.email == email).first():
            raise HTTPException(409, "Ya existe un usuario con ese email") from exc
        raise
    db.refresh(user)
    return user


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_data.business_id != admin.business_id:
        raise HTTPException(403, "Solo podés crear usuarios para tu negocio")
    business = db.query(Business).filter(
        Business.id == user_data.business_id
    ).first()

    if business is None:
        raise HTTPException(
            status_code=404,
            detail="La empresa no existe"
        )

    existing_user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un usuario con ese email"
        )

    user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
        business_id=user_data.business_id
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user

@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == login_data.email
    ).first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Email o contraseña incorrectos"
        )

    if not verify_password(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Email o contraseña incorrectos"
        )

    if not user.active:
        raise HTTPException(
            status_code=403,
            detail="Usuario inactivo"
        )

    access_token = create_access_token(
        user_id=user.id,
        business_id=user.business_id,
        role=user.role.value
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get(
    "/me",
    response_model=UserResponse
)
def get_me(
    current_user: User = Depends(get_current_user)
):
    return current_user