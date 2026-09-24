"""Internal routing note on specialist handoffs and the recipient's acknowledgment note."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("specialist_handoffs", sa.Column("routing_note", sa.Text(), nullable=True))
    op.add_column("specialist_handoffs", sa.Column("acknowledgment_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("specialist_handoffs", "acknowledgment_note")
    op.drop_column("specialist_handoffs", "routing_note")
