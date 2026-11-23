from decimal import Decimal
from app.services.payment_settings import require_transfer_destination

from sqlalchemy.orm import Session

from app.models.checkout import MercadoPagoCheckout
from app.models.product import Product
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus, PaymentMethod
from app.schemas.order import OrderCreate, OrderItemCreate, OrderPreviewItem


def calculate_order_items(
    db: Session,
    items: list[OrderItemCreate],
    business_id: int,
):
    total = Decimal("0.00")
    prepared_items = []

    # Validamos los productos y calculamos los precios
    for item in items:
        db_product = db.query(Product).filter(
            Product.id == item.product_id,
            Product.business_id == business_id,
        ).first()

        if db_product is None:
            raise ValueError("No hay productos con ese ID")

        if not db_product.active:
            raise ValueError("El producto no está activo")

        subtotal = item.quantity * db_product.price
        total = total + subtotal

        prepared_items.append({
            "product_id": db_product.id,
            "quantity": item.quantity,
            "unit_price": db_product.price,
            "subtotal": subtotal,
            "product_name": db_product.name,
        })

    return prepared_items, total


def snapshot_order_items(items):
    return [OrderPreviewItem.model_validate(item).model_dump(mode="json") for item in items]


def create_order(
    db: Session,
    order_data: OrderCreate,
    business_id: int,
    *,
    quoted_items: list[dict] | None = None,
    commit: bool = True,
):
    if order_data.payment_method == PaymentMethod.TRANSFER:
        require_transfer_destination(db, business_id)
    prepared_items, total = calculate_order_items(db, order_data.items, business_id)
    if quoted_items is not None and snapshot_order_items(prepared_items) != quoted_items:
        raise ValueError("El resumen cambió. Pedí una nueva confirmación.")

    # Creamos el pedido
    new_order = Order(
        business_id=business_id,
        customer_phone=order_data.customer_phone,
        customer_name=order_data.customer_name,
        delivery_type=order_data.delivery_type,
        payment_method=order_data.payment_method,
        delivery_address=order_data.delivery_address,
        notes=order_data.notes,
        total=total,
    )

    db.add(new_order)
    db.flush()

    # Creamos los items asociados al pedido
    for prepared_item in prepared_items:
        new_order_item = OrderItem(
            order_id=new_order.id,
            product_id=prepared_item["product_id"],
            quantity=prepared_item["quantity"],
            unit_price=prepared_item["unit_price"],
            subtotal=prepared_item["subtotal"],
            product_name=prepared_item["product_name"],
        )

        db.add(new_order_item)

    if commit:
        db.commit()
        db.refresh(new_order)

    return new_order


def get_orders(
    db: Session,
    business_id: int,
    status: OrderStatus | None = None,
):
    query = db.query(Order).filter(Order.business_id == business_id)

    if status is not None:
        query = query.filter(Order.status == status)

    return query.order_by(Order.created_at.desc()).all()

def get_order_by_id(db:Session,business_id:int,order_id:int):
    order = db.query(Order).filter(
            Order.business_id == business_id, Order.id==order_id).first()
    return order

def lock_order(db: Session, business_id: int, order_id: int):
    return (
        db.query(Order)
        .filter_by(business_id=business_id, id=order_id)
        .populate_existing()
        .with_for_update()
        .first()
    )


def update_order_status(
    db: Session,
    business_id: int,
    order_id: int,
    new_status: OrderStatus,
):
    order = lock_order(db, business_id, order_id)

    if order is None:
        raise ValueError("Pedido no encontrado")

    if (
        order.payment_method == PaymentMethod.TRANSFER
        and order.payment_status != PaymentStatus.CONFIRMED
        and new_status not in {OrderStatus.PENDING, OrderStatus.CANCELLED}
    ):
        raise ValueError("Confirmá la acreditación de la transferencia antes de avanzar el pedido")

    order.status = new_status
    db.commit()
    db.refresh(order)

    return order


def confirm_direct_transfer(db: Session, business_id: int, order_id: int):
    order = lock_order(db, business_id, order_id)
    if order is None:
        raise ValueError("Pedido no encontrado")
    if order.payment_method != PaymentMethod.TRANSFER:
        raise ValueError("El pedido no se paga por transferencia")
    if order.payment_status == PaymentStatus.CONFIRMED:
        return order
    if order.status == OrderStatus.CANCELLED:
        raise ValueError("El pedido está cancelado")
    if db.get(MercadoPagoCheckout, order.id) is not None:
        raise ValueError("Este pedido tiene un enlace de Mercado Pago. Esperá la acreditación de Checkout Pro.")
    return confirm_order_payment(db, business_id, order_id)


def confirm_order_payment(db:Session, business_id:int, order_id:int):
    order = get_order_by_id(db, business_id, order_id)

    if order is None:
        raise ValueError("Pedido no encontrado")

    order.payment_status = PaymentStatus.CONFIRMED

    if (
        order.payment_method == PaymentMethod.TRANSFER
        and order.status == OrderStatus.PENDING
    ):
        order.status = OrderStatus.CONFIRMED


    from app.services.chat_attention import close_payment_alerts
    close_payment_alerts(db, order)

    db.commit()
    db.refresh(order)

    return order