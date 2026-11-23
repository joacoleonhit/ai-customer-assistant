"""Add per-chat alerts and attention revision."""
from alembic import op
import sqlalchemy as sa
revision="b7de921ac830"
down_revision="a613b2c98f44"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("customer_conversations",sa.Column("attention_version",sa.Integer(),nullable=False,server_default="0"))
    op.add_column("customer_conversations",sa.Column("updated_at",sa.BigInteger(),nullable=False,server_default=sa.text("extract(epoch from now())::bigint")))
    op.add_column("whatsapp_replies",sa.Column("manual_reply",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_table("conversation_alerts",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("business_id",sa.Integer(),nullable=False),
        sa.Column("conversation_id",sa.String(128),nullable=False),
        sa.Column("kind",sa.String(24),nullable=False),
        sa.Column("message",sa.Text(),nullable=False),
        sa.Column("event_id",sa.String(160)),sa.Column("draft_id",sa.String(32)),
        sa.Column("order_id",sa.Integer(),sa.ForeignKey("orders.id")),
        sa.Column("attachment",sa.JSON()),
        sa.Column("created_at",sa.BigInteger(),nullable=False),
        sa.Column("resolved_at",sa.BigInteger()),
        sa.Column("resolved_by",sa.Integer(),sa.ForeignKey("users.id")),
        sa.ForeignKeyConstraint(["business_id","conversation_id"],["customer_conversations.business_id","customer_conversations.id"]))
    op.create_index("ix_alert_business","conversation_alerts",["business_id"])
    op.create_index("uq_open_chat_alert","conversation_alerts",["business_id","conversation_id","kind"],unique=True,postgresql_where=sa.text("resolved_at IS NULL"))

def downgrade():
    op.drop_table("conversation_alerts")
    op.drop_column("whatsapp_replies","manual_reply")
    op.drop_column("customer_conversations","updated_at")
    op.drop_column("customer_conversations","attention_version")
