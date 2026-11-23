"""Queue outbound WhatsApp replies."""
from alembic import op
import sqlalchemy as sa

revision = "f81242a6e520"
down_revision = "c902761afd32"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "whatsapp_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("send_after", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("sent_id", sa.String(160)),
        sa.ForeignKeyConstraint(
            ["business_id", "conversation_id"],
            ["customer_conversations.business_id", "customer_conversations.id"],
        ),
    )
    op.create_index("ix_whatsapp_replies_send_after", "whatsapp_replies", ["send_after"])


def downgrade():
    op.drop_table("whatsapp_replies")
