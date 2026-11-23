import enum

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"

    
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)

    password_hash = Column(String, nullable=False)

    role = Column(
    Enum(UserRole),
    nullable=False
    )

    active = Column(Boolean, default=True)

    business_id = Column(
        Integer,
        ForeignKey("businesses.id"),
        nullable=False
    )

    business = relationship(
        "Business",
        back_populates="users"
    )