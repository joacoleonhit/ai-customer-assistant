"""create products table

Revision ID: 117702b5e57d
Revises: 7f7996122612
Create Date: 2026-09-19 08:44:32.160134
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "117702b5e57d"
down_revision: Union[str, Sequence[str], None] = "7f7996122612"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create products table."""

    op.create_table(
        "products",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False
        ),

        sa.Column(
            "name",
            sa.String(),
            nullable=False
        ),

        sa.Column(
            "description",
            sa.String(),
            nullable=True
        ),

        sa.Column(
            "price",
            sa.Numeric(precision=10, scale=2),
            nullable=False
        ),

        sa.Column(
            "active",
            sa.Boolean(),
            nullable=True
        ),

        sa.Column(
            "business_id",
            sa.Integer(),
            nullable=False
        ),

        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"]
        ),

        sa.PrimaryKeyConstraint("id")
    )

    op.create_index(
        op.f("ix_products_id"),
        "products",
        ["id"],
        unique=False
    )

    op.create_index(
        op.f("ix_products_business_id"),
        "products",
        ["business_id"],
        unique=False
    )


def downgrade() -> None:
    """Remove products table."""

    op.drop_index(
        op.f("ix_products_business_id"),
        table_name="products"
    )

    op.drop_index(
        op.f("ix_products_id"),
        table_name="products"
    )

    op.drop_table("products")