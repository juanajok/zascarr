"""Fandom (DC/Marvel Database) como fuente: columnas de identidad por wiki.

Revision ID: 0036
Revises: 0035

Fase 2 del estudio `docs/estudio-scraping-fuentes-v2.md`: las dos wikis de Fandom
identifican sus páginas por título («Batman Vol 1», «Batman Vol 1 404»), que es un
slug de texto como el de Tebeosfera. Columnas paralelas por fuente (mismo principio
que `comic_vine_id`/`anilist_id`/`tebeosfera_slug`): una serie o un número de esta
instalación usa, en la práctica, como mucho una de las dos.

Aditiva y reversible: no toca datos existentes ni crea tipos nuevos.
"""
import sqlalchemy as sa

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabla in ("series", "issues"):
        op.add_column(tabla, sa.Column("fandom_dc_slug", sa.String(255)))
        op.add_column(tabla, sa.Column("fandom_marvel_slug", sa.String(255)))
        op.create_unique_constraint(f"uq_{tabla}_fandom_dc_slug", tabla, ["fandom_dc_slug"])
        op.create_unique_constraint(
            f"uq_{tabla}_fandom_marvel_slug", tabla, ["fandom_marvel_slug"])


def downgrade() -> None:
    for tabla in ("issues", "series"):
        op.drop_constraint(f"uq_{tabla}_fandom_marvel_slug", tabla, type_="unique")
        op.drop_constraint(f"uq_{tabla}_fandom_dc_slug", tabla, type_="unique")
        op.drop_column(tabla, "fandom_marvel_slug")
        op.drop_column(tabla, "fandom_dc_slug")
