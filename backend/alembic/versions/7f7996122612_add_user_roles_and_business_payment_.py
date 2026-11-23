"""add user roles and business payment constraint

Revision ID: 7f7996122612
Revises: bf59423b56ec
Create Date: 2026-09-15 09:28:20.540595

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f7996122612'
down_revision: Union[str, Sequence[str], None] = 'bf59423b56ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crear el tipo ENUM en PostgreSQL
    user_role = sa.Enum(
        "ADMIN",
        "EMPLOYEE",
        name="userrole"
    )

    user_role.create(op.get_bind(), checkfirst=True)

    # Cambiar users.role de VARCHAR a userrole
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole
        USING role::userrole
        """
    )

    # La empresa debe tener al menos CBU o alias
    op.create_check_constraint(
        "check_business_payment_data",
        "businesses",
        "cbu IS NOT NULL OR alias IS NOT NULL"
    )


def downgrade() -> None:
    # Eliminar primero el CHECK
    op.drop_constraint(
        "check_business_payment_data",
        "businesses",
        type_="check"
    )

    # Volver users.role a VARCHAR
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE VARCHAR
        USING role::text
        """
    )

    # Eliminar el tipo ENUM de PostgreSQL
    user_role = sa.Enum(
        "ADMIN",
        "EMPLOYEE",
        name="userrole"
    )

    user_role.drop(op.get_bind(), checkfirst=True)