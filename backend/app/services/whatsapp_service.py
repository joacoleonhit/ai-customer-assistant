import json
import logging
import os
import re
import time
from urllib.request import Request, urlopen

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.conversation import Conversation, WhatsAppReply


def whatsapp_channels():
    config = json.loads(os.getenv("WHATSAPP_CHANNELS", "{}"))
    if not isinstance(config, dict):
        raise ValueError("WHATSAPP_CHANNELS debe ser un objeto JSON")
    return config


def whatsapp_conversation(phone_number_id, customer_phone):
    return f"whatsapp:{phone_number_id}:{customer_phone}"


def outbound_recipient(customer_phone, channel):
    # Meta can whitelist Argentine test recipients without the mobile prefix.
    if channel.get("argentina_test_strip_mobile_prefix") is True and re.fullmatch(r"549[0-9]{10}", customer_phone):
        return "54" + customer_phone[3:]
    return customer_phone


def send_text(phone_number_id, customer_phone, text, token):
    version = os.getenv("WHATSAPP_GRAPH_VERSION", "")
    if not re.fullmatch(r"v[0-9]+[.][0-9]+", version):
        raise ValueError("WHATSAPP_GRAPH_VERSION no configurada")
    if not re.fullmatch(r"[0-9]{1,32}", phone_number_id) or not re.fullmatch(r"[0-9]{7,15}", customer_phone):
        raise ValueError("Identificador de WhatsApp inválido")
    request = Request(
        f"https://graph.facebook.com/{version}/{phone_number_id}/messages",
        data=json.dumps({
            "messaging_product": "whatsapp",
            "to": customer_phone,
            "type": "text",
            "text": {"body": text[:4096]},
        }).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=8) as response:
        message_id = json.load(response)["messages"][0]["id"]
    if not isinstance(message_id, str) or not 1 <= len(message_id) <= 160:
        raise ValueError("Respuesta de WhatsApp inválida")
    return message_id


def dispatch_reply(now=None, bind=engine, business_id=None):
    now = int(time.time()) if now is None else now
    with Session(bind) as db, db.begin():
        due = db.execute(
            select(Conversation, WhatsAppReply)
            .join(WhatsAppReply, (WhatsAppReply.business_id == Conversation.business_id)
                  & (WhatsAppReply.conversation_id == Conversation.id))
            .where(or_(Conversation.manual.is_(False), WhatsAppReply.manual_reply.is_(True)), WhatsAppReply.sent_id.is_(None),
                   WhatsAppReply.send_after <= now,
                   Conversation.business_id == business_id if business_id is not None else True)
            .order_by(WhatsAppReply.id)
            .limit(1).with_for_update(skip_locked=True)
        ).first()
        if due is None:
            return False
        chat, reply = due
        _, number_id, customer_phone = chat.id.split(":")
        try:
            config = whatsapp_channels()[number_id]
            if int(config["business_id"]) != chat.business_id or customer_phone != chat.phone:
                raise ValueError("La conversación ya no pertenece al canal configurado")
            recipient = outbound_recipient(customer_phone, config)
            reply.sent_id = send_text(number_id, recipient, reply.text, config["access_token"])
        except Exception as error:
            reply.attempts += 1
            reply.send_after = now + min(300, 5 * 2 ** min(reply.attempts, 6))
            logging.warning("Envío de WhatsApp pendiente (%s)", type(error).__name__)
        return True
