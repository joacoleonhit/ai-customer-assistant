"""add server default to product active

Revision ID: 246d2ab3840b
Revises: 6ca097cbbfdd
Create Date: 2026-09-24 14:14:50.276479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '246d2ab3840b'
down_revision: Union[str, Sequence[str], None] = '6ca097cbbfdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "products",
        "active",
        server_default=sa.text("true")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "products",
        "active",
        server_default=None
    )
