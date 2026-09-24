"""Retain uploaded PDFs independently of drafts, then bind them to sent mail."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("mail_messages.id")),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
    )
    op.create_index("ix_mail_attachments_message_id", "mail_attachments", ["message_id"])


def downgrade():
    op.drop_table("mail_attachments")
