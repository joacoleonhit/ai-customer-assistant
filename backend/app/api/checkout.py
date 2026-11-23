from app.services.payment_settings import require_transfer_destination
import hashlib
import hmac
import json
import os
import re
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.business import Business, PaymentProvider
from app.models.checkout import MercadoPagoCheckout
from app.models.order import Order, OrderStatus, PaymentMethod, PaymentStatus
from app.models.user import User
from app.services.mercado_pago_oauth import connected_credentials
from app.services.order_service import confirm_order_payment

router = APIRouter(tags=["Checkout Pro"])


class CheckoutResponse(BaseModel):
    checkout_url: str


def merchant_config(business_id: int) -> tuple[str, str]:
    try:
        config = json.loads(os.environ.get("MERCADO_PAGO_SELLERS", "{}"))[str(business_id)]
        seller_id = str(config["seller_id"])
        token = config["access_token"]
        if seller_id.isdecimal() and isinstance(token, str) and token:
            return seller_id, token
    except (KeyError, ValueError, TypeError):
        pass
    raise HTTPException(503, "Mercado Pago no está conectado para este negocio")


def mercado_pago(path: str, token: str, payload=None, request_key=None) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if request_key:
        headers["X-Idempotency-Key"] = request_key
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    try:
        req = Request("https://api.mercadopago.com" + path, data=data, headers=headers)
        with urlopen(req, timeout=8) as response:
            result = json.load(response)
        if isinstance(result, dict):
            return result
    except (URLError, OSError, ValueError):
        pass
    raise HTTPException(502, "No pudimos verificar la respuesta de Mercado Pago")


def external_reference(order: Order) -> str:
    return f"business-{order.business_id}-order-{order.id}"


def valid_order_id(value: str | None) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9]{1,100}", value) is not None


@router.post("/orders/{order_id}/checkout-pro", response_model=CheckoutResponse)
def create_checkout(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return create_order_checkout(db, user.business_id, order_id)


def create_order_checkout(db: Session, business_id: int, order_id: int) -> CheckoutResponse:
    order = db.scalar(
        select(Order).filter_by(id=order_id, business_id=business_id)
    )
    if order is None:
        raise HTTPException(404, "Pedido no encontrado")
    try:
        business = require_transfer_destination(db, business_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if business.payment_provider != PaymentProvider.MERCADO_PAGO:
        raise HTTPException(409, "El negocio debe seleccionar Mercado Pago")
    seller_id, token = connected_credentials(db, business_id) or merchant_config(business_id)
    # Token renewal may commit, so lock and reload the order after resolving credentials.
    order = db.scalar(
        select(Order).filter_by(id=order_id, business_id=business_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if order is None:
        raise HTTPException(404, "Pedido no encontrado")
    if (
        order.payment_method != PaymentMethod.TRANSFER
        or order.payment_status != PaymentStatus.PENDING
        or order.status == OrderStatus.CANCELLED
        or order.total <= 0
    ):
        raise HTTPException(409, "El pedido no admite un cobro por Checkout Pro")

    checkout = db.get(MercadoPagoCheckout, order.id)
    if checkout is not None:
        if checkout.seller_id != seller_id:
            raise HTTPException(409, "El pedido ya tiene un cobro asociado a otra cuenta")
        return CheckoutResponse(checkout_url=checkout.checkout_url)

    reference = external_reference(order)
    key = str(uuid5(NAMESPACE_URL, f"checkout-pro:{seller_id}:{reference}:{order.created_at.isoformat()}"))
    remote = mercado_pago("/v1/orders", token, {
        "type": "online",
        "processing_mode": "manual",
        "total_amount": str(order.total),
        "external_reference": reference,
        "items": [{"title": f"Pedido {order.id}", "quantity": 1, "unit_price": str(order.total)}],
    }, key)
    provider_id = remote.get("id")
    url = remote.get("checkout_url")
    parsed = urlsplit(url) if isinstance(url, str) else None
    if (
        not valid_order_id(provider_id)
        or str(remote.get("user_id")) != seller_id
        or remote.get("external_reference") != reference
        or not parsed
        or parsed.scheme != "https"
        or parsed.netloc != "www.mercadopago.com.ar"
    ):
        raise HTTPException(502, "Mercado Pago devolvió datos de checkout inesperados")

    checkout = MercadoPagoCheckout(order_id=order.id, provider_order_id=provider_id,
                                   seller_id=seller_id, checkout_url=url)
    db.add(checkout)
    db.commit()
    return CheckoutResponse(checkout_url=url)


def verify_signature(order_id: str, request_id: str | None, signature: str | None) -> None:
    secret = os.environ.get("MERCADO_PAGO_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook de Mercado Pago no configurado")
    parts = dict(part.strip().split("=", 1) for part in (signature or "").split(",") if "=" in part)
    timestamp = parts.get("ts", "")
    supplied = parts.get("v1", "")
    if not request_id or not timestamp.isascii() or not timestamp.isdecimal() or not re.fullmatch(r"[0-9a-f]{64}", supplied):
        raise HTTPException(401, "Firma de Mercado Pago inválida")
    manifest = f"id:{order_id.lower()};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "Firma de Mercado Pago inválida")


@router.post("/webhooks/mercado-pago")
def checkout_notification(
    provider_id: str | None = Query(default=None, alias="data.id"),
    request_id: str | None = Header(default=None, alias="x-request-id"),
    signature: str | None = Header(default=None, alias="x-signature"),
    db: Session = Depends(get_db),
):
    if not valid_order_id(provider_id):
        raise HTTPException(400, "Falta el ID de la orden de Mercado Pago")
    verify_signature(provider_id, request_id, signature)
    checkout = db.scalar(select(MercadoPagoCheckout).filter_by(provider_order_id=provider_id))
    if checkout is None:
        return {"received": True}
    order = db.get(Order, checkout.order_id)
    if order.payment_status == PaymentStatus.CONFIRMED:
        return {"received": True}

    seller_id, token = connected_credentials(db, order.business_id) or merchant_config(order.business_id)
    if seller_id != checkout.seller_id:
        raise HTTPException(503, "La cuenta del cobro requiere revisión")
    remote = mercado_pago(f"/v1/orders/{provider_id}", token)
    if remote.get("status") != "processed" or remote.get("status_detail") != "accredited":
        return {"received": True}
    try:
        paid = Decimal(str(remote.get("total_paid_amount")))
    except InvalidOperation:
        paid = None
    order = db.scalar(select(Order).filter_by(id=checkout.order_id)
                      .with_for_update().execution_options(populate_existing=True))
    if (
        remote.get("id") != provider_id
        or str(remote.get("user_id")) != checkout.seller_id
        or remote.get("external_reference") != external_reference(order)
        or remote.get("currency") != "ARS"
        or paid is None or not paid.is_finite() or paid != order.total
    ):
        raise HTTPException(409, "Los datos del cobro no coinciden con el pedido")
    if order.payment_status == PaymentStatus.PENDING:
        confirm_order_payment(db, order.business_id, order.id)
    return {"received": True}
