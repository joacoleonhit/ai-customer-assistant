from uuid import uuid4
from app.services.payment_settings import require_transfer_destination

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.business import Business
from app.models.order import DeliveryType, PaymentMethod
from app.models.order_draft import OrderDraft
from app.models.user import User
from app.schemas.order import (
    ConversationDraftConfirmation,
    ConversationDraftRequest,
    ConversationDraftResponse,
    OrderCreate,
    OrderPreviewRequest,
    OrderPreviewResponse,
    OrderResponse,
    OrderStatus,
    OrderStatusUpdate,
)
from app.services.order_service import (
    calculate_order_items,
    confirm_direct_transfer,
    create_order,
    get_orders,
    get_order_by_id,
    snapshot_order_items,
    update_order_status,
)



router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)

@router.post(
    "/",
    response_model=OrderResponse,
    status_code=201
)
def create_new_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        new_order = create_order(db, order_data, current_user.business_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    return new_order

@router.post("/preview", response_model=OrderPreviewResponse)
def preview_order(
    draft: OrderPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if draft.payment_method == PaymentMethod.TRANSFER:
            require_transfer_destination(db, current_user.business_id)
        items, total = calculate_order_items(db, draft.items, current_user.business_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    lines = [
        f"{item['quantity']} × {item['product_name']}: ${item['subtotal']:.2f}"
        for item in items
    ]
    address = None
    delivery = "Retiro en el local"
    if draft.delivery_type == DeliveryType.DELIVERY:
        address = (draft.delivery_address or "").strip()
        delivery = f"Envío a {address}"
    payment = "Efectivo" if draft.payment_method == PaymentMethod.CASH else "Transferencia"
    message = "\n".join([
        "Así quedaría tu pedido:",
        *lines,
        f"Total: ${total:.2f} ARS",
        delivery,
        f"Medio de pago: {payment}",
        "¿Confirmás el pedido?",
    ])
    return OrderPreviewResponse(
        items=items,
        total=total,
        currency="ARS",
        delivery_type=draft.delivery_type,
        delivery_address=address,
        payment_method=draft.payment_method,
        message=message,
    )


@router.post("/drafts", response_model=ConversationDraftResponse, status_code=201)
def create_conversation_draft(
    data: ConversationDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preview = preview_order(data, db, current_user)
    db.execute(select(Business.id).where(Business.id == current_user.business_id).with_for_update())
    db.execute(
        delete(OrderDraft).filter_by(
            business_id=current_user.business_id,
            conversation_id=data.conversation_id,
            order_id=None,
        )
    )
    draft = OrderDraft(
        id=uuid4().hex,
        business_id=current_user.business_id,
        conversation_id=data.conversation_id,
        payload=data.model_dump(mode="json", exclude={"conversation_id"}),
        quoted_items=snapshot_order_items(preview.items),
    )
    db.add(draft)
    db.commit()
    return ConversationDraftResponse(draft_id=draft.id, **preview.model_dump())


@router.post("/drafts/{draft_id}/confirm", response_model=OrderResponse)
def confirm_conversation_draft(
    draft_id: str,
    confirmation: ConversationDraftConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    draft = db.scalar(
        select(OrderDraft).filter_by(
            id=draft_id,
            business_id=current_user.business_id,
            conversation_id=confirmation.conversation_id,
        ).with_for_update()
    )
    if draft is None:
        raise HTTPException(404, "Borrador no encontrado")
    if draft.order_id is not None:
        return get_order_by_id(db, current_user.business_id, draft.order_id)

    try:
        order = create_order(
            db,
            OrderCreate.model_validate(draft.payload),
            current_user.business_id,
            quoted_items=draft.quoted_items,
            commit=False,
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    draft.order_id = order.id
    db.commit()
    db.refresh(order)
    return order


@router.get("/", response_model=list[OrderResponse])
def list_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), 
    status: OrderStatus | None = None,
    
):
    return get_orders(db, business_id=current_user.business_id, status=status)

@router.get("/{order_id}", response_model=OrderResponse)
def filt_orders_by_id(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order_filter_id= get_order_by_id(
        db,
        current_user.business_id,
        order_id
    )
    if order_filter_id is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order_filter_id


@router.post("/{order_id}/confirm-transfer", response_model=OrderResponse)
def confirm_transfer(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return confirm_direct_transfer(db, current_user.business_id, order_id)
    except ValueError as error:
        code = 404 if str(error) == "Pedido no encontrado" else 409
        raise HTTPException(status_code=code, detail=str(error)) from error


@router.patch("/{order_id}/status", response_model=OrderResponse)
def statusUpdate(
    order_id:int,
    status_data: OrderStatusUpdate,
    db:Session=Depends(get_db),
    current_user : User = Depends(get_current_user)
):

    try:

        updateStatus= update_order_status( db,
                current_user.business_id,
                order_id,
                status_data.status,)

    except ValueError as error:
        mensaje = str(error)

        if mensaje == "Pedido no encontrado":
            raise HTTPException(status_code=404, detail=mensaje) from error

        raise HTTPException(status_code=409, detail=mensaje) from error

    
    return updateStatus