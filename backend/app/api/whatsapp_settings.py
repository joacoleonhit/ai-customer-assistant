from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin
from app.models.business import Business
from app.models.user import User
from app.models.whatsapp_connection import WhatsAppConnection

router = APIRouter(prefix="/businesses/me/whatsapp", tags=["WhatsApp settings"])
DEMO_PHONE = "+1 202 555 0100"


class ConnectionStatus(BaseModel):
    mode: Literal["disconnected", "simulated"]
    display_phone: str | None = None


def lock_business(db: Session, admin: User):
    business = db.scalar(select(Business).filter_by(id=admin.business_id).with_for_update())
    if not business or not business.active:
        raise HTTPException(404, "Negocio activo no encontrado")


@router.get("", response_model=ConnectionStatus)
def status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    connection = db.get(WhatsAppConnection, admin.business_id)
    if connection and connection.mode == "simulated":
        return ConnectionStatus(mode="simulated", display_phone=connection.display_phone)
    return ConnectionStatus(mode="disconnected")


@router.put("/simulation", response_model=ConnectionStatus)
def connect_simulation(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    lock_business(db, admin)
    connection = db.get(WhatsAppConnection, admin.business_id)
    if connection is None:
        connection = WhatsAppConnection(
            business_id=admin.business_id, display_phone=DEMO_PHONE, mode="simulated",
        )
        db.add(connection)
    elif connection.mode != "simulated":
        raise HTTPException(409, "El local ya tiene otra conexión de WhatsApp")
    result = ConnectionStatus(mode="simulated", display_phone=connection.display_phone)
    db.commit()
    return result


@router.delete("/simulation", response_model=ConnectionStatus)
def disconnect_simulation(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    lock_business(db, admin)
    connection = db.get(WhatsAppConnection, admin.business_id)
    if connection and connection.mode == "simulated":
        db.delete(connection)
    db.commit()
    return ConnectionStatus(mode="disconnected")


@router.post("/simulation/test", response_model=ConnectionStatus)
def test_simulation(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    result = status(db, admin)
    if result.mode != "simulated":
        raise HTTPException(409, "Primero conectá el número de demostración")
    return result
