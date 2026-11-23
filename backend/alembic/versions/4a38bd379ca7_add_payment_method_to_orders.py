"""add payment method to orders

Revision ID: 4a38bd379ca7
Revises: 6cacbde02ae1
Create Date: 2026-11-11 08:14:12.837822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4a38bd379ca7'
down_revision: Union[str, Sequence[str], None] = '6cacbde02ae1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
payment_method_enum = postgresql.ENUM(
    "TRANSFER", "CASH", name="paymentmethod", create_type=False
)


def upgrade() -> None:
    payment_method_enum.create(op.get_bind())
    op.add_column(
        "orders",
        sa.Column("payment_method", payment_method_enum, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "payment_method")
    payment_method_enum.drop(op.get_bind())
