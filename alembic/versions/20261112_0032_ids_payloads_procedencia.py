"""IDs externos por issue, payloads de fuente y procedencia por campo (fase 2).

Migración aditiva. No modifica identidad, archivos ni datos existentes.

- `issues.gcd_id`, `issues.metron_id`, `issues.anilist_id`, `issues.tebeosfera_slug`:
  columnas paralelas por fuente (CLAUDE.md §12), opcionales y únicas.
- `entity_source_records`: payload normalizado de una fuente y su procedencia
  (URL, hash, fecha, licencia), sin clave foránea polimórfica.
- `field_provenance`: origen del último valor de un campo concreto.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col, tipo in (
        ("gcd_id", sa.BigInteger()),
        ("metron_id", sa.BigInteger()),
        ("anilist_id", sa.BigInteger()),
        ("tebeosfera_slug", sa.String(length=255)),
    ):
        op.add_column("issues", sa.Column(col, tipo, nullable=True, unique=True))

    op.create_table(
        "entity_source_records",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(length=10), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500)),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_hash", sa.String(length=64)),
        sa.Column("license", sa.String(length=100)),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.CheckConstraint("entity_type IN ('series','issue')", name="ck_entity_source_type"),
        sa.UniqueConstraint("entity_type", "entity_id", "source", "external_id",
                            name="uq_entity_source_record"),
    )
    op.create_index("ix_entity_source_entity", "entity_source_records",
                    ["entity_type", "entity_id"])
    op.create_index("ix_entity_source_external", "entity_source_records",
                    ["source", "external_id"])

    op.create_table(
        "field_provenance",
        sa.Column("entity_type", sa.String(length=10), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("value", JSONB),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now()),
        sa.Column("locked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("entity_type", "entity_id", "field"),
        sa.CheckConstraint("entity_type IN ('series','issue')", name="ck_field_provenance_type"),
    )


def downgrade() -> None:
    op.drop_table("field_provenance")
    op.drop_index("ix_entity_source_external", table_name="entity_source_records")
    op.drop_index("ix_entity_source_entity", table_name="entity_source_records")
    op.drop_table("entity_source_records")
    op.drop_column("issues", "tebeosfera_slug")
    op.drop_column("issues", "anilist_id")
    op.drop_column("issues", "metron_id")
    op.drop_column("issues", "gcd_id")
