import json
import os
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException
from sqlalchemy import select

from app.models.mercado_pago import MercadoPagoConnection


def oauth_settings():
    client_id = os.getenv("MERCADO_PAGO_CLIENT_ID")
    secret = os.getenv("MERCADO_PAGO_CLIENT_SECRET")
    callback = os.getenv("MERCADO_PAGO_REDIRECT_URI")
    if not client_id or not secret or not callback or not callback.startswith("https://"):
        raise HTTPException(503, "OAuth de Mercado Pago no está configurado")
    return client_id, secret, callback


def credential_cipher():
    from cryptography.fernet import Fernet

    try:
        return Fernet(os.environ["MERCADO_PAGO_TOKEN_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(503, "El cifrado de credenciales no está configurado") from None


def exchange_token(**fields):
    client_id, secret, _ = oauth_settings()
    request = Request(
        "https://api.mercadopago.com/oauth/token",
        data=json.dumps({"client_id": client_id, "client_secret": secret, **fields}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            result = json.load(response)
        seller = str(result["user_id"])
        access, refresh = result["access_token"], result["refresh_token"]
        lifetime = int(result["expires_in"])
        if not seller.isascii() or not seller.isdecimal() or len(seller) > 32:
            raise ValueError
        if not all(isinstance(value, str) and value for value in (access, refresh)) or lifetime <= 0:
            raise ValueError
        return seller, access, refresh, int(time.time()) + lifetime
    except (URLError, OSError, ValueError, KeyError, TypeError):
        raise HTTPException(502, "Mercado Pago no completó la autorización") from None


def save_tokens(connection, tokens):
    seller, access, refresh, expiry = tokens
    connection.seller_id = seller
    connection.expires_at = expiry
    connection.credentials = credential_cipher().encrypt(
        json.dumps({"access": access, "refresh": refresh}).encode()
    ).decode()


def connected_credentials(db, business_id):
    connection = db.scalar(
        select(MercadoPagoConnection).filter_by(business_id=business_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if connection is None:
        return None

    from cryptography.fernet import InvalidToken
    try:
        tokens = json.loads(credential_cipher().decrypt(connection.credentials.encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(503, "La cuenta de Mercado Pago requiere revisión") from None
    if connection.expires_at > time.time() + 60:
        return connection.seller_id, tokens["access"]
    refreshed = exchange_token(grant_type="refresh_token", refresh_token=tokens["refresh"])
    if refreshed[0] != connection.seller_id:
        raise HTTPException(502, "Mercado Pago devolvió una cuenta inesperada")
    save_tokens(connection, refreshed)
    db.commit()
    return refreshed[0], refreshed[1]
