"""Store Mercado Pago connections and pending authorizations."""
from alembic import op
import sqlalchemy as sa

revision = "ab2190d45e67"
down_revision = "e0b4c5fa9221"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mercado_pago_connections",
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), primary_key=True),
        sa.Column("seller_id", sa.String(32), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "mercado_pago_authorizations",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )


def downgrade():
    op.drop_table("mercado_pago_authorizations")
    op.drop_table("mercado_pago_connections")
