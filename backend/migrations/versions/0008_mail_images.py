"""Record media types for image attachments; retain existing PDF uploads."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_attachments",
        sa.Column("media_type", sa.String(40), nullable=False, server_default="application/pdf"),
    )


def downgrade():
    op.drop_column("mail_attachments", "media_type")
