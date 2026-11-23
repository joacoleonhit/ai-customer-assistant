"""Process conversations with a cancellable planning phase."""
import hashlib,logging,time
from copy import deepcopy
from types import SimpleNamespace
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models.conversation import Conversation,WhatsAppReply
from app.services.whatsapp_service import dispatch_reply
from app.services.chat_attention import record_alert

def process_due(now=None,bind=engine,business_id=None):
    from app.api.conversations import IncomingMessage,add_turn,plan_message,handle_planned_message
    from app.main import app
    now=int(time.time()) if now is None else now
    target=None
    try:
        with bind.begin() as connection:
            with Session(bind=connection,join_transaction_mode="create_savepoint") as db:
                # Advisory locks serialize workers without blocking human takeover.
                candidates=db.scalars(select(Conversation).where(Conversation.manual.is_(False),Conversation.due_at<=now,
                    Conversation.business_id==business_id if business_id is not None else True)
                    .order_by(Conversation.due_at).limit(20)).all()
                chat=None
                for candidate in candidates:
                    key=int.from_bytes(hashlib.sha256(f"{candidate.business_id}:{candidate.id}".encode()).digest()[:8],"big",signed=True)
                    if db.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"),{"key":key}):
                        db.refresh(candidate)
                        if candidate.manual or candidate.due_at is None or candidate.due_at>now: continue
                        chat=candidate;break
                if chat is None: return False
                snapshot=(deepcopy(chat.history),chat.draft_id,chat.due_at,chat.attention_version)
                target=(chat.business_id,chat.id)
                turn=chat.history[-1]
                if turn["role"]!="customer": return False
                data=IncomingMessage(conversation_id=chat.id,customer_phone=chat.phone,message=turn["text"],
                    history=chat.history[:-1],draft_id=chat.draft_id)
                decision=plan_message(data,db,SimpleNamespace(business_id=chat.business_id))
                db.expire_all()
                chat=db.scalar(select(Conversation).where(Conversation.business_id==target[0],Conversation.id==target[1]).with_for_update())
                if chat is None or chat.manual or (chat.history,chat.draft_id,chat.due_at,chat.attention_version)!=snapshot:
                    return False
                signal=getattr(decision,"attention_reason",None)
                if signal:
                    record_alert(db,chat,signal,turn["text"],turn.get("event_id"),turn.get("attachment"))
                    if chat.manual:
                        db.commit();return True
                reply=handle_planned_message(data,db,SimpleNamespace(business_id=chat.business_id),decision)
                add_turn(chat,"assistant",reply.message)
                chat.draft_id=reply.draft_id
                chat.due_at=None
                if chat.id.startswith("whatsapp:"):
                    db.add(WhatsAppReply(business_id=chat.business_id,conversation_id=chat.id,text=reply.message,send_after=now))
                db.commit()
        return True
    except Exception:
        # A failing model/chat must not starve the rest of the inbox.
        if target:
            with Session(bind) as db,db.begin():
                chat=db.get(Conversation,target)
                if chat is not None and not chat.manual and chat.due_at is not None and chat.due_at<=now:
                    chat.due_at=now+30
        raise

def run():
    from app.services.conversation_ai import warmup_local_model
    try: warmup_local_model()
    except Exception as error: logging.warning("No se pudo precargar Ollama (%s)",type(error).__name__)
    while True:
        try:
            processed=process_due()
            sent=dispatch_reply()
            if not(processed or sent): time.sleep(2)
        except Exception as error:
            logging.error("No se pudo procesar una conversación: %s",type(error).__name__)
            time.sleep(2)

if __name__=="__main__": run()
