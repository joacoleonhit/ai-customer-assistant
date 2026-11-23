import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_admin
from app.models.business import Business, PaymentProvider
from app.models.mercado_pago import MercadoPagoAuthorization, MercadoPagoConnection
from app.models.user import User, UserRole
from app.services.mercado_pago_oauth import credential_cipher, exchange_token, oauth_settings, save_tokens

router = APIRouter(prefix="/businesses/me/mercado-pago", tags=["Mercado Pago"])


@router.get("")
def connection_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return {"connected": db.get(MercadoPagoConnection, admin.business_id) is not None}


@router.post("/connect")
def connect(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    client_id, _, callback = oauth_settings()
    credential_cipher()
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute(delete(MercadoPagoAuthorization).where(MercadoPagoAuthorization.expires_at <= now))
    db.add(MercadoPagoAuthorization(
        state_hash=hashlib.sha256(state.encode()).hexdigest(),
        user_id=admin.id,
        business_id=admin.business_id,
        verifier=verifier,
        expires_at=now + 600,
    ))
    db.commit()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = urlencode({
        "client_id": client_id, "response_type": "code", "platform_id": "mp",
        "redirect_uri": callback, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"authorization_url": "https://auth.mercadopago.com/authorization?" + params}


@router.get("/callback")
def callback(
    state: str = Query(min_length=1, max_length=128),
    code: str | None = Query(default=None, max_length=1024),
    db: Session = Depends(get_db),
):
    now = int(time.time())
    pending = db.execute(
        delete(MercadoPagoAuthorization)
        .where(
            MercadoPagoAuthorization.state_hash == hashlib.sha256(state.encode()).hexdigest(),
            MercadoPagoAuthorization.expires_at > now,
        )
        .returning(MercadoPagoAuthorization.user_id, MercadoPagoAuthorization.business_id,
                   MercadoPagoAuthorization.verifier)
    ).one_or_none()
    if pending is None:
        raise HTTPException(400, "La autorización venció o ya fue utilizada")
    db.commit()
    if not code:
        raise HTTPException(400, "La autorización no fue completada")

    business = db.scalar(select(Business).filter_by(id=pending.business_id).with_for_update())
    admin = db.get(User, pending.user_id)
    if (business is None or not business.active or admin is None or not admin.active
            or admin.role != UserRole.ADMIN or admin.business_id != business.id):
        raise HTTPException(403, "La autorización del negocio ya no es válida")

    credential_cipher()
    _, _, redirect_uri = oauth_settings()
    tokens = exchange_token(grant_type="authorization_code", code=code,
                            redirect_uri=redirect_uri, code_verifier=pending.verifier)
    connection = db.get(MercadoPagoConnection, business.id)
    if connection is None:
        connection = MercadoPagoConnection(business_id=business.id)
        db.add(connection)
    elif connection.seller_id != tokens[0]:
        raise HTTPException(409, "El negocio ya está vinculado a otra cuenta de Mercado Pago")
    save_tokens(connection, tokens)
    business.payment_provider = PaymentProvider.MERCADO_PAGO
    db.commit()
    return {"connected": True, "message": "Mercado Pago conectado. Podés volver al perfil del negocio."}
