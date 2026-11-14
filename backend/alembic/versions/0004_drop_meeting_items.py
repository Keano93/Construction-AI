"""drop meeting_items: Notice produces the commercial pack; it does not keep meeting minutes or actions

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("meeting_items")


def downgrade() -> None:
    op.create_table(
        "meeting_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("meeting_date", sa.Date(), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(200)),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), index=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"), index=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_on", sa.Date()),
    )
