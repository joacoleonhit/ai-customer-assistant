from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import EmployeeCreate, UserResponse


router = APIRouter(
    prefix="/employees",
    tags=["Employees"]
)


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def create_employee(
    employee_data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    existing_user = db.query(User).filter(
        User.email == employee_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un usuario con ese email"
        )

    employee = User(
        name=employee_data.name,
        email=employee_data.email,
        password_hash=hash_password(employee_data.password),

        role=UserRole.EMPLOYEE,

        business_id=current_admin.business_id
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    return employee

@router.get(
    "/",
    response_model=list[UserResponse]
)
def get_employees(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    employees = db.query(User).filter(
        User.business_id == current_admin.business_id,
        User.role == UserRole.EMPLOYEE
    ).all()

    return employees
@router.patch(
    "/{employee_id}/status",
    response_model=UserResponse
)
def change_employee_status(
    employee_id: int,
    active: bool,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin)
):
    employee = db.query(User).filter(
        User.id == employee_id,
        User.business_id == current_admin.business_id,
        User.role == UserRole.EMPLOYEE
    ).first()

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Empleado no encontrado"
        )

    employee.active = active

    db.commit()
    db.refresh(employee)

    return employee