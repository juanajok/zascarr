"""2d — `vinculacion_operaciones`: el informe INMUTABLE de una vinculación en su sitio (rebanada 2d).

Revision ID: 0019
Revises: 0018

Por qué existe: confirmar una vinculación debe poder devolver **el mismo resultado** —también el de los archivos
omitidos y sus motivos— tras un reinicio, un doble envío o un reintento. La procedencia por archivo
(`files.metadata.vinculo`) no basta: no recoge los fallos. Contrato en `docs/design/rebanada-2-elegir-serie-y-
vincular.md` («Contrato técnico de 2d»).

Decisiones de esquema (cada una con su prueba en `tests/test_migracion_vinculacion_pg.py`):

- **Tabla propia**, separada de `alta_operaciones` (cuyo contrato es el comprobante de un alta de serie).
- **`series_id` NO es clave foránea**: borrar la serie no borra el informe. Es solo un dato.
- **El `resultado` es inmutable.** Un disparador `BEFORE UPDATE` rechaza cualquier `UPDATE`: la aplicación nunca
  actualiza un informe y ni un fallo de programación puede reescribirlo. `DELETE` sí se permite (la purga).
- **Datos mínimos**: `operacion_id`, `series_id`, `resultado` (jsonb versionado: ids, estados, motivos, números,
  ediciones y códigos de conflicto), `token_hasta` (la caducidad del token) y `creada`. **Ni token, ni sesión, ni
  credenciales, ni rutas, ni nombres, ni hash.**
- **No es un historial de auditoría.** Se purga (de forma acotada, sin tocar series, archivos ni números) lo que
  cumpla las DOS condiciones: creado hace más de 24 h **y** con el token ya caducado.

**Downgrade — destructivo.** Retira, en orden, el disparador, su función y la tabla (con su índice). Se NIEGA si queda
alguna fila con un token todavía válido (bajar perdería el informe y permitiría ejecutar otra vez un token vigente).
Toma `ACCESS EXCLUSIVE` ANTES de contar, como la 0018.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vinculacion_operaciones",
        sa.Column("operacion_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("series_id", UUID(as_uuid=True), nullable=False),
        sa.Column("resultado", JSONB, nullable=False),
        sa.Column("token_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creada", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vinculacion_operaciones_purga", "vinculacion_operaciones", ["creada"])
    op.execute("""
        CREATE OR REPLACE FUNCTION vinculacion_operaciones_inmutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'vinculacion_operaciones: el informe es inmutable (no se actualiza)'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_vinculacion_operaciones_inmutable
            BEFORE UPDATE ON vinculacion_operaciones
            FOR EACH ROW EXECUTE FUNCTION vinculacion_operaciones_inmutable()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE vinculacion_operaciones IN ACCESS EXCLUSIVE MODE"))
    vigentes = bind.execute(sa.text("SELECT count(*) FROM vinculacion_operaciones WHERE token_hasta > now()")).scalar()
    if vigentes:
        raise RuntimeError(
            f"No se puede bajar de la 0019: hay {vigentes} informes de vinculación con un token todavía válido. "
            "Bajar los borraría y ese token podría ejecutarse otra vez. Espera a que caduquen (15 minutos) y "
            "vuelve a intentarlo."
        )
    op.execute("DROP TRIGGER IF EXISTS trg_vinculacion_operaciones_inmutable ON vinculacion_operaciones")
    op.execute("DROP FUNCTION IF EXISTS vinculacion_operaciones_inmutable()")
    op.drop_table("vinculacion_operaciones")          # su índice se retira con ella
