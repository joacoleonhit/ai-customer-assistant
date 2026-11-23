"""add payment status to orders

Revision ID: 798cf5d94413
Revises: 4a38bd379ca7
Create Date: 2026-11-12 04:36:20.446132

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '798cf5d94413'
down_revision: Union[str, Sequence[str], None] = '4a38bd379ca7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

payment_status_enum = postgresql.ENUM(
    "PENDING", "CONFIRMED", name="paymentstatus", create_type=False
)


def upgrade() -> None:
    payment_status_enum.create(op.get_bind())
    op.add_column(
        "orders",
        sa.Column(
            "payment_status",
            payment_status_enum,
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
    )
    op.alter_column("orders", "payment_status", server_default=None)


def downgrade() -> None:
    op.drop_column("orders", "payment_status")
    payment_status_enum.drop(op.get_bind())