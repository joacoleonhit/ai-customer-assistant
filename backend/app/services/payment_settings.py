from app.models.business import Business


def clean_payment_value(value):
    return (value.strip() or None) if isinstance(value, str) else value


def has_transfer_destination(business) -> bool:
    return bool(clean_payment_value(business.alias) or clean_payment_value(business.cbu))


def require_transfer_destination(db, business_id: int):
    business = db.get(Business, business_id)
    if business is None:
        raise ValueError("Negocio no encontrado")
    if not has_transfer_destination(business):
        raise ValueError("El negocio debe configurar al menos un alias o CBU/CVU para aceptar transferencias")
    return business
