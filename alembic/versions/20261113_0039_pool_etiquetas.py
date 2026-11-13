"""Pool inicial de etiquetas (BL-ETQ, 2026-11-13).

Revision ID: 0039
Revises: 0038

Siembra el vocabulario curado de `services/etiquetas_iniciales.py` en `tags`
(namespace `etiqueta`) de forma idempotente. No asigna etiquetas a ninguna
serie ni toca archivos. El downgrade no borra filas: a esa altura pueden ser
ya etiquetas del coleccionista y un rollback no debe destruir datos.
"""
from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, insert

from alembic import op
from zascarr.services.etiquetas_iniciales import ETIQUETAS_INICIALES

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tags = sa.table(
        "tags",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("namespace", sa.String),
    )
    op.execute(
        insert(tags).values([
            {"id": uuid4(), "name": nombre, "namespace": "etiqueta"}
            for nombre in ETIQUETAS_INICIALES
        ]).on_conflict_do_nothing()
    )


def downgrade() -> None:
    # Dato de arranque, no esquema: se conserva para no borrar etiquetas que
    # el coleccionista ya pueda haber asignado.
    pass
