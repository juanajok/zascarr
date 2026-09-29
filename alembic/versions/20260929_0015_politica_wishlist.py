"""D8 — política de búsqueda por serie: `Series.wishlist_policy`,
`Wishlist.origen`/`numero` y el estado `retirado`.

Revision ID: 0015
Revises: 0014

Tres decisiones que conviene no deshacer sin querer:

- **Backfill `manual` + `numero = NULL`** en los items existentes: si alguno
  quedara como `politica`, la retirada de D8 podría tocar lo que el
  coleccionista pidió a mano.
- **Índice único parcial limitado a los items de política con número.** Un
  `UNIQUE` que abarcara también los manuales le devolvería un error de
  integridad crudo a quien añada a mano un número ya generado (lección de
  Kapowarr que recoge el BACKLOG: un único en una tabla gestionada desde la UI
  necesita una reconciliación amable).
  El índice **no** mira el estado a propósito, y eso obliga a un contrato (ficha
  D8): la generación **no inserta a secas**, **reactiva** la fila que ya exista
  para ese número con
  `INSERT ... ON CONFLICT (series_id, numero) WHERE origen='politica' AND numero
  IS NOT NULL DO UPDATE SET status, added_at, download_ref, download_backend,
  last_error`. Si no, una fila `retirado`, `imported` o `failed` del número 4
  seguiría ocupando el hueco y volver a querer el 4 daría error de integridad —
  justo los dos casos que se dieron en la revisión: pasar la serie a `ninguno` y
  volver a `faltantes`, y un número importado cuyo fichero desapareció.
  Reiniciar `added_at` no es cosmético: el cierre compara
  `File.imported_at >= Wishlist.added_at`.
- **`retirado` se añade con `ALTER TYPE ... ADD VALUE`**, que en PostgreSQL
  desde la 12 se permite dentro de una transacción pero **no se puede usar en
  la misma transacción**. Por eso esta migración no escribe ese valor en ningún
  sitio (`wishlist_origen` es un tipo nuevo, que sí se puede usar recién
  creado). Comprobado contra el PostgreSQL real de desarrollo (15).
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE wishlist_policy AS ENUM ('ninguno','faltantes','futuros','todos')")
    op.execute("CREATE TYPE wishlist_origen AS ENUM ('manual','politica')")
    op.execute("ALTER TYPE wishlist_status ADD VALUE IF NOT EXISTS 'retirado'")

    op.add_column("series", sa.Column(
        "wishlist_policy",
        PGEnum("ninguno", "faltantes", "futuros", "todos", name="wishlist_policy",
               create_type=False),
        nullable=False, server_default="ninguno"))
    op.add_column("wishlist", sa.Column(
        "origen",
        PGEnum("manual", "politica", name="wishlist_origen", create_type=False),
        nullable=False, server_default="manual"))
    op.add_column("wishlist", sa.Column("numero", sa.Integer()))

    # El backfill lo hace el `server_default` de la columna, no un UPDATE: en
    # PostgreSQL, `ADD COLUMN ... NOT NULL DEFAULT 'manual'` ya rellena las filas
    # existentes. La prueba de la migración lo comprueba sembrando filas ANTES de
    # aplicarla (no con un UPDATE que no tocaría nada).
    op.create_index(
        "uq_wishlist_politica_numero",
        "wishlist",
        ["series_id", "numero"],
        unique=True,
        postgresql_where=sa.text("origen = 'politica' AND numero IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_wishlist_politica_numero", table_name="wishlist")
    op.drop_column("wishlist", "numero")
    op.drop_column("wishlist", "origen")
    op.drop_column("series", "wishlist_policy")
    op.execute("DROP TYPE wishlist_origen")
    op.execute("DROP TYPE wishlist_policy")
    # OJO: PostgreSQL no permite quitar un valor de un ENUM. `retirado` se queda
    # en el tipo tras el downgrade — es inofensivo (ninguna fila lo usa) y
    # recrear el tipo obligaría a reescribir la columna entera.
