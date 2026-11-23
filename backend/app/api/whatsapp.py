import hashlib
import hmac
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.conversations import QueuedMessage, queue_incoming_message
from app.core.database import get_db
from app.models.business import Business
from app.services.whatsapp_service import whatsapp_channels, whatsapp_conversation

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp"])


@router.get("", response_class=PlainTextResponse)
def verify_subscription(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    expected = os.getenv("WHATSAPP_VERIFY_TOKEN")
    if not expected or mode != "subscribe" or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(403, "Verificación de WhatsApp rechazada")
    return challenge


def ingest(db, payload):
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        return {"received": 0}
    channels = whatsapp_channels()
    queued = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            number = value.get("metadata", {}).get("phone_number_id")
            if not isinstance(number, str) or not re.fullmatch(r"[0-9]{1,32}", number) or number not in channels:
                continue
            bid = int(channels[number]["business_id"])
            business = db.get(Business, bid)
            if business is None or not business.active:
                continue
            for message in value.get("messages", []):
                kind = message.get("type")
                if kind not in {"text", "image", "document"}:
                    continue
                customer = message.get("from")
                event_id = message.get("id")
                attachment = None
                if kind == "text":
                    text = message.get("text", {}).get("body")
                else:
                    media = message.get(kind, {})
                    media_id = media.get("id")
                    if not isinstance(media_id, str) or not re.fullmatch(r"[0-9]{1,64}", media_id):
                        continue
                    attachment = {"media_id": media_id, "phone_number_id": number, "kind": kind}
                    caption = media.get("caption", "")
                    caption = caption if isinstance(caption, str) else ""
                    text = (caption + "\n[El cliente adjuntó una imagen/documento para revisión humana]").strip()
                if not isinstance(customer, str) or not re.fullmatch(r"[0-9]{7,15}", customer):
                    continue
                if not isinstance(event_id, str) or not 1 <= len(event_id) <= 160:
                    continue
                if not isinstance(text, str) or not text.strip():
                    continue
                result = queue_incoming_message(
                    whatsapp_conversation(number, customer),
                    QueuedMessage(event_id=event_id, customer_phone=customer, message=text[:3000], attachment=attachment),
                    db, bid,
                )
                queued += int(result["queued"])
    return {"received": queued}


@router.post("")
async def receive_messages(request: Request, db: Session = Depends(get_db)):
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        raise HTTPException(503, "WhatsApp no configurado")
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.encode(), expected.encode()):
        raise HTTPException(401, "Firma de WhatsApp inválida")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Evento de WhatsApp inválido") from None
    return await run_in_threadpool(ingest, db, payload)
