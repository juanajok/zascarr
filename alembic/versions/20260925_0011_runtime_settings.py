"""runtime_settings — D11: ajustes de integraciones editables desde la UI.

Revision ID: 0011
Revises: 0010

Fila única (id=1, sembrada aquí mismo) con un JSONB de overrides. No es
una segunda fuente de verdad de configuración: config.py/.env siguen
declarando campos/tipos/defaults (CLAUDE.md §2); esto es solo el
override en caliente que aplica services/runtime_settings.py sobre el
Settings ya cacheado por get_settings() — ver su docstring para el
porqué (@lru_cache + --workers 1 hace que mutar la instancia cacheada
sea visible al instante en toda la app, sin reiniciar).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("values", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("INSERT INTO runtime_settings (id, values) VALUES (1, '{}'::jsonb)")


def downgrade() -> None:
    op.drop_table("runtime_settings")
