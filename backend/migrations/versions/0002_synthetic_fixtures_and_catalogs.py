"""Synthetic fixture identities, evidence facts, and reference catalogs."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "simulation_instances",
        sa.Column("variant", sa.String(40), nullable=False, server_default="base"),
    )
    op.add_column("simulation_instances", sa.Column("seed_key", sa.String(36), nullable=True))
    op.add_column("simulation_instances", sa.Column("seed_hash", sa.String(64), nullable=True))
    op.create_index("uq_simulation_seed_key", "simulation_instances", ["seed_key"], unique=True)
    op.add_column("evidence", sa.Column("details", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "taxonomy_entries",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("work_type", sa.String(200), nullable=False),
        sa.Column("class_name", sa.String(200), nullable=False),
        sa.Column("subclass", sa.String(300), nullable=False),
        sa.Column("source_reference", sa.String(300), nullable=False),
        sa.UniqueConstraint("work_type", "class_name", "subclass"),
    )
    op.create_table(
        "source_manifest_entries",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("row_number", sa.Integer(), nullable=False, unique=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("curated_item_keys", sa.JSON(), nullable=False),
        sa.Column("review_flags", sa.JSON(), nullable=False),
    )
    op.create_table(
        "client_configurations",
        sa.Column("code", sa.String(60), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("client_configurations")
    op.drop_table("source_manifest_entries")
    op.drop_table("taxonomy_entries")
    op.drop_column("evidence", "details")
    op.drop_index("uq_simulation_seed_key", table_name="simulation_instances")
    op.drop_column("simulation_instances", "seed_hash")
    op.drop_column("simulation_instances", "seed_key")
    op.drop_column("simulation_instances", "variant")
