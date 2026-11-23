"""Store WhatsApp connections per business."""
from alembic import op
import sqlalchemy as sa

revision = "a613b2c98f44"
down_revision = "f81242a6e520"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_connections",
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), primary_key=True),
        sa.Column("display_phone", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
    )


def downgrade():
    op.drop_table("whatsapp_connections")
