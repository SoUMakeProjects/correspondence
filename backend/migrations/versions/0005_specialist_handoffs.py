"""Persist responsibility and acknowledgment independently from case resolution."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "specialist_handoffs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "action_id",
            sa.String(36),
            sa.ForeignKey("action_receipts.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("route", sa.String(120), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("evidence_versions", sa.JSON(), nullable=False),
        sa.Column("concerns", sa.JSON(), nullable=False),
        sa.Column("restrictions", sa.JSON(), nullable=False),
        sa.Column("acknowledged_by", sa.String(120), nullable=True),
        sa.Column("acknowledged_at", sa.String(32), nullable=True),
    )
    op.create_index("ix_specialist_handoffs_case_id", "specialist_handoffs", ["case_id"])


def downgrade():
    op.drop_table("specialist_handoffs")
