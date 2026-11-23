import json,re,time
from urllib.request import Request,urlopen,build_opener,HTTPRedirectHandler
from urllib.parse import urlparse,urlencode
from urllib.error import URLError
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.conversation import ConversationAlert,Conversation
from app.models.order_draft import OrderDraft
from app.models.user import User
from app.services.whatsapp_service import whatsapp_channels

router=APIRouter(prefix="/alerts",tags=["Alerts"])

def owned_alert(db,user,alert_id):
    alert=db.scalar(select(ConversationAlert).where(ConversationAlert.id==alert_id,ConversationAlert.business_id==user.business_id))
    if alert is None: raise HTTPException(404,"Alerta no encontrada")
    return alert

def alert_payload(db,alert):
    order_id=alert.order_id
    if order_id is None and alert.draft_id:
        draft=db.get(OrderDraft,alert.draft_id)
        if draft and draft.business_id==alert.business_id: order_id=draft.order_id
    return {"id":alert.id,"conversation_id":alert.conversation_id,"kind":alert.kind,
        "message":alert.message,"created_at":alert.created_at,"resolved_at":alert.resolved_at,
        "order_id":order_id,"has_attachment":bool(alert.attachment)}

@router.get("/")
def list_alerts(include_resolved:bool=False,limit:int=Query(50,ge=1,le=100),
                db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    query=select(ConversationAlert).where(ConversationAlert.business_id==user.business_id)
    if not include_resolved: query=query.where(ConversationAlert.resolved_at.is_(None))
    rows=db.scalars(query.order_by(ConversationAlert.created_at.desc(),ConversationAlert.id.desc()).limit(limit)).all()
    count=db.scalar(select(func.count()).select_from(ConversationAlert).where(
        ConversationAlert.business_id==user.business_id,ConversationAlert.resolved_at.is_(None)))
    return {"pending_count":count,"items":[alert_payload(db,a) for a in rows]}

@router.patch("/{alert_id}/resolve")
def resolve_alert(alert_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    alert=owned_alert(db,user,alert_id)
    if alert.resolved_at is None:
        alert.resolved_at=int(time.time());alert.resolved_by=user.id
        db.commit()
    # Resolving a notification does not release a chat or accredit money.
    return alert_payload(db,alert)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def download_attachment(attachment, business_id):
    from os import getenv
    number=attachment.get("phone_number_id","");media=attachment.get("media_id","")
    channel=whatsapp_channels().get(number)
    if not channel or int(channel["business_id"])!=business_id:
        raise HTTPException(409,"El adjunto ya no pertenece a la conexión del negocio")
    if not re.fullmatch(r"[0-9]{1,64}",media): raise HTTPException(422,"Adjunto inválido")
    version=getenv("WHATSAPP_GRAPH_VERSION","")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+",version): raise HTTPException(503,"WhatsApp no configurado")
    headers={"Authorization":"Bearer "+channel["access_token"]}
    opener=build_opener(NoRedirect)
    try:
        # Including phone_number_id binds the media lookup to this channel.
        with opener.open(Request(f"https://graph.facebook.com/{version}/{media}?"+urlencode({"phone_number_id":number}),headers=headers),timeout=12) as r:
            metadata=json.load(r)
        url=metadata["url"];parsed=urlparse(url);host=(parsed.hostname or "").lower()
        if parsed.scheme!="https" or parsed.username or parsed.password or parsed.port not in (None,443) or not (
            host=="lookaside.fbsbx.com" or host.endswith(".fbcdn.net")):
            raise ValueError("Origen de adjunto inválido")
        maximum=20*1024*1024
        if int(metadata.get("file_size",0))>maximum:
            raise HTTPException(413,"El archivo supera los 20 MB permitidos en el panel")
        with opener.open(Request(url,headers=headers),timeout=20) as r:
            data=r.read(maximum+1)
        if len(data)>maximum: raise HTTPException(413,"El archivo supera los 20 MB permitidos en el panel")
        extension={"image/jpeg":".jpg","image/png":".png","application/pdf":".pdf"}.get(metadata.get("mime_type"),".bin")
        return data, "adjunto-cliente"+extension
    except HTTPException: raise
    except (URLError,OSError,ValueError,KeyError,TypeError):
        raise HTTPException(502,"No se pudo descargar el adjunto. Puede haber vencido en WhatsApp; pedí que lo reenvíen.") from None

@router.get("/{alert_id}/attachment")
def get_attachment(alert_id:int,db:Session=Depends(get_db),user:User=Depends(get_current_user)):
    alert=owned_alert(db,user,alert_id)
    if not alert.attachment: raise HTTPException(404,"La alerta no tiene adjunto")
    data,filename=download_attachment(alert.attachment,user.business_id)
    return Response(data,media_type="application/octet-stream",headers={
        "Content-Disposition":f'attachment; filename="{filename}"',
        "X-Content-Type-Options":"nosniff","Cache-Control":"no-store"})
