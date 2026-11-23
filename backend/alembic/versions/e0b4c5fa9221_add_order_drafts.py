"""Store order drafts for conversation confirmation."""
from alembic import op
import sqlalchemy as sa

revision = "e0b4c5fa9221"
down_revision = "d91e6ab27f30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_drafts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("quoted_items", sa.JSON(), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), unique=True),
    )


def downgrade():
    op.drop_table("order_drafts")
