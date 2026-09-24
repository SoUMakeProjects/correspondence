"""Durable rule evidence and content-bound review groundwork."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rule_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("case_revision", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.UniqueConstraint("case_id", "request_id"),
    )
    op.create_index("ix_rule_evaluations_case_id", "rule_evaluations", ["case_id"])
    op.add_column("review_decisions", sa.Column("content_hash", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("review_decisions", "content_hash")
    op.drop_index("ix_rule_evaluations_case_id", table_name="rule_evaluations")
    op.drop_table("rule_evaluations")
