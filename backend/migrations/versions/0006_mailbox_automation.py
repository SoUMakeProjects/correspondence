"""Durable mailbox messages and automatic run triggers."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def identity():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
    ]


def upgrade():
    op.create_table(
        "mail_threads",
        *identity(),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), unique=True),
        sa.Column("template_key", sa.String(80), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
    )
    op.create_table(
        "mail_messages",
        *identity(),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("mail_threads.id"), nullable=False),
        sa.Column("template_key", sa.String(80), nullable=False),
        sa.Column("sender", sa.String(254), nullable=False),
        sa.Column("recipient", sa.String(254), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
    )
    op.create_index("ix_mail_messages_thread_id", "mail_messages", ["thread_id"])
    op.create_table(
        "automation_signals",
        *identity(),
        sa.Column("event_key", sa.String(120), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("mail_threads.id"), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id")),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("mail_messages.id")),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id")),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
    )
    for column in ("thread_id", "case_id", "status"):
        op.create_index(f"ix_automation_signals_{column}", "automation_signals", [column])


def downgrade():
    op.drop_table("automation_signals")
    op.drop_table("mail_messages")
    op.drop_table("mail_threads")
