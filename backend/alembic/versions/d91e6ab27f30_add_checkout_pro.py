"""Add business payment provider and Mercado Pago checkouts."""

from alembic import op
import sqlalchemy as sa

revision = "d91e6ab27f30"
down_revision = "798cf5d94413"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("businesses", sa.Column("payment_provider", sa.String(32), nullable=True))
    op.create_table(
        "mercado_pago_checkouts",
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), primary_key=True),
        sa.Column("provider_order_id", sa.String(100), nullable=False, unique=True),
        sa.Column("seller_id", sa.String(32), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("mercado_pago_checkouts")
    op.drop_column("businesses", "payment_provider")
