"""BL-D3 (#154): propuestas de edición mejor y última pasada de escaneo.

Revision ID: 0034
Revises: 0033

Aditiva y reversible. No toca archivos ni sustituye nada: crea la tabla de
propuestas y una marca de cadencia en `issues`.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("upgrade_scanned_at", sa.DateTime(timezone=True)))
    op.create_table(
        "upgrade_proposals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("issue_id", UUID(as_uuid=True),
                  sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True),
                  sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("current_tier", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_title", sa.String(500), nullable=False),
        sa.Column("candidate_indexer", sa.String(100), nullable=False),
        sa.Column("candidate_url", sa.Text(), nullable=False),
        sa.Column("candidate_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("candidate_seeders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_tier", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("issue_id", "candidate_url",
                            name="uq_upgrade_proposals_issue_url"),
    )
    op.create_index("ix_upgrade_proposals_issue_status", "upgrade_proposals",
                    ["issue_id", "status"])
    op.create_index("ix_upgrade_proposals_status", "upgrade_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_upgrade_proposals_status", table_name="upgrade_proposals")
    op.drop_index("ix_upgrade_proposals_issue_status", table_name="upgrade_proposals")
    op.drop_table("upgrade_proposals")
    op.drop_column("issues", "upgrade_scanned_at")
