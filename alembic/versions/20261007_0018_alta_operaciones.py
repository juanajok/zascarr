"""2b — `alta_operaciones`: el comprobante de una operación de alta de serie (rebanada 2b).

Revision ID: 0018
Revises: 0017

Por qué existe: la idempotencia del alta vivía en la propia fila de `series` (`metadata.alta.operacion_id`), y
**deshacer la borra**: reenviar el token original —aún válido, hasta 15 min— la creaba otra vez y revertía el
deshacer. El comprobante tiene que sobrevivir a la serie.

Decisiones de esquema (cada una con su prueba en `tests/test_migracion_alta_pg.py`):

- **`series_id` NO es clave foránea.** Con `ON DELETE CASCADE` borrar la serie borraría su comprobante (justo lo
  que hay que evitar); con `SET NULL` perdería el dato con el que se reconoce el resultado. Es solo un dato.
- **Estados `creada` y `deshecha`** (tipo `alta_estado`). `deshecha` prevalece: esa operación no vuelve a crear.
- **Datos mínimos**: `operacion_id` (UUID de la vista previa), `series_id`, `estado`, `token_hasta` (la
  caducidad del token que la creó) y dos marcas de tiempo. **Ni token, ni sesión, ni credenciales, ni título.**
- **No es un historial de auditoría.** Se purga (de forma acotada, y sin tocar series) lo que cumpla las DOS
  condiciones: creada hace más de 24 h **y** con el token ya caducado. Mientras pueda existir un token válido
  asociado, la fila se conserva; tras purgarla, un token caducado nunca ejecuta un alta (se rechaza por caducado).
- El índice `ix_alta_operaciones_purga` (por `creada`) acota la purga.

**Downgrade — destructivo.** Elimina la tabla y el tipo: se pierden los comprobantes. Por eso se NIEGA si queda
alguna operación con un token todavía válido (bajar permitiría que un reintento atrasado recreara una serie
deshecha). Toma `ACCESS EXCLUSIVE` ANTES de contar, como la 0017, para que una confirmación ajena no se cuele
entre el recuento y el borrado.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alta_operaciones",
        sa.Column("operacion_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("series_id", UUID(as_uuid=True), nullable=False),
        sa.Column("estado", PGEnum("creada", "deshecha", name="alta_estado"), nullable=False),
        sa.Column("token_hasta", sa.DateTime(timezone=True), nullable=False),
        sa.Column("creada", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actualizada", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alta_operaciones_purga", "alta_operaciones", ["creada"])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE alta_operaciones IN ACCESS EXCLUSIVE MODE"))
    vigentes = bind.execute(sa.text("SELECT count(*) FROM alta_operaciones WHERE token_hasta > now()")).scalar()
    if vigentes:
        raise RuntimeError(
            f"No se puede bajar de la 0018: hay {vigentes} operaciones de alta con un token todavía válido. "
            "Bajar borraría los comprobantes y un reintento atrasado podría recrear una serie "
            "que se deshizo. Espera a que caduquen (15 minutos) y vuelve a intentarlo."
        )
    op.drop_table("alta_operaciones")
    op.execute("DROP TYPE alta_estado")
