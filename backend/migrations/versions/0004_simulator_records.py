"""Simulator histories and separation of content from workflow revision."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cases", sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.execute("UPDATE cases SET content_revision = revision")
    op.add_column("cases", sa.Column("routing", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column(
        "cases", sa.Column("pending_work", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "final_notes", sa.Column("details", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_table(
        "servicing_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("loan_id", sa.String(36), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("action_receipts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("operation", sa.String(80), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=False),
    )
    op.create_index("ix_servicing_history_case_id", "servicing_history", ["case_id"])
    op.create_index("ix_servicing_history_loan_id", "servicing_history", ["loan_id"])


def downgrade():
    op.drop_table("servicing_history")
    op.drop_column("final_notes", "details")
    op.drop_column("cases", "pending_work")
    op.drop_column("cases", "routing")
    op.drop_column("cases", "content_revision")
