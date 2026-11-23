"""Human attention signals never authorize a payment."""
import re,time,unicodedata
from sqlalchemy import delete,select,update,or_
from sqlalchemy.dialects.postgresql import insert
from app.models.conversation import ConversationAlert,WhatsAppReply
from app.models.order_draft import OrderDraft

def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD",text.casefold()) if not unicodedata.combining(c))

def quick_signal(text, attachment=None, transfer_context=False):
    text=normalized(text)
    if re.search(r"\b(reclamo|queja|reembolso|devolucion|estafa)\b|(?:quiero|necesito|puedo).{0,30}(?:hablar|atencion).{0,25}(?:persona|humano|encargado)|(?:pedido|comida).{0,25}(?:llego mal|llego frio|vino mal|equivocado)",text):
        return "complaint"
    for clause in re.split(r"[.!?;]|\bpero\b",text):
        if re.search(r"\b(?:no|nunca|todavia no|aun no)\b.{0,25}(?:transferi|pague|comprobante|hice|mande|envie)",clause):
            continue
        if re.search(r"\btransferi(?:mos)?\b|(?:hice|mande|envie).{0,25}transferencia|(?:adjunto|envio|mando|aca|ahi).{0,25}comprobante|transferencia (?:hecha|realizada|enviada)",clause):
            return "transfer_claim"
        if transfer_context and re.search(r"\b(?:ya pague|hice el pago|pago realizado)\b",clause):
            return "transfer_claim"
    if attachment:
        return "transfer_claim" if transfer_context else "attachment"
    return None

def draft_order(db,chat):
    draft=db.get(OrderDraft,chat.draft_id) if chat.draft_id else None
    if draft is not None and draft.business_id==chat.business_id:
        return draft
    return None

def pause_chat(db,chat):
    chat.manual=True
    chat.attention_version=(chat.attention_version or 0)+1
    chat.due_at=None
    db.execute(delete(WhatsAppReply).where(WhatsAppReply.business_id==chat.business_id,
        WhatsAppReply.conversation_id==chat.id,WhatsAppReply.sent_id.is_(None),WhatsAppReply.manual_reply.is_(False)))

def record_alert(db,chat,kind,text,event_id=None,attachment=None):
    draft=draft_order(db,chat)
    values=dict(business_id=chat.business_id,conversation_id=chat.id,kind=kind,
        message=text[:3000],event_id=event_id,draft_id=chat.draft_id,
        order_id=draft.order_id if draft else None,attachment=attachment,created_at=int(time.time()))
    stmt=insert(ConversationAlert).values(**values)
    changes={"message":stmt.excluded.message,"event_id":stmt.excluded.event_id}
    if attachment: changes["attachment"]=stmt.excluded.attachment
    db.execute(stmt.on_conflict_do_update(index_elements=["business_id","conversation_id","kind"],
        index_where=ConversationAlert.resolved_at.is_(None),set_=changes))
    if kind in {"complaint","attachment"}: pause_chat(db,chat)

def inspect_incoming(db,chat,text,event_id=None,attachment=None):
    draft=draft_order(db,chat)
    signal=quick_signal(text,attachment,bool(draft and draft.payload.get("payment_method")=="TRANSFER"))
    if signal: record_alert(db,chat,signal,text,event_id,attachment)
    return signal

def close_payment_alerts(db,order):
    drafts=select(OrderDraft.id).where(OrderDraft.business_id==order.business_id,OrderDraft.order_id==order.id)
    db.execute(update(ConversationAlert).where(ConversationAlert.business_id==order.business_id,
        ConversationAlert.kind=="transfer_claim",ConversationAlert.resolved_at.is_(None),
        or_(ConversationAlert.order_id==order.id,ConversationAlert.draft_id.in_(drafts)))
        .values(resolved_at=int(time.time())))
