"""Persist conversation history, attention and incoming event identities."""
from alembic import op
import sqlalchemy as sa

revision = "c902761afd32"
down_revision = "ab2190d45e67"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_conversations",
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), primary_key=True),
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("draft_id", sa.String(32)),
        sa.Column("due_at", sa.BigInteger()),
        sa.Column("manual", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_customer_conversations_due_at", "customer_conversations", ["due_at"])
    op.create_table(
        "customer_conversation_events",
        sa.Column("business_id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(160), primary_key=True),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["business_id", "conversation_id"],
                                ["customer_conversations.business_id", "customer_conversations.id"]),
    )


def downgrade():
    op.drop_table("customer_conversation_events")
    op.drop_table("customer_conversations")
