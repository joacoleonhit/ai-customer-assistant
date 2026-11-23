from pydantic import BaseModel, EmailStr, computed_field
from app.models.user import UserRole

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: UserRole
    business_id: int

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    active: bool
    business_id: int

    @computed_field
    @property
    def is_demo(self) -> bool:
        return self.email.endswith("@demo.example.com")

    model_config = {
        "from_attributes": True
    }

class EmployeeCreate(BaseModel):
    name: str
    email: EmailStr
    password: str