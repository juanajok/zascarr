"""V6a — `asignacion_operaciones`: la operación de asignar un archivo, recuperable (ADR 0006).

Revision ID: 0017
Revises: 0016

Persiste lo necesario para que una asignación interrumpida (muerte del proceso, caída de la conexión,
`commit` de resultado desconocido) se reconcilie **sin escanear la biblioteca**: el origen con su identidad
(tamaño, `mtime_ns`, `sha256`), el **destino efectivo** (con sufijo si el canónico estaba ocupado), lo pedido
(serie, número, formato, alias) y la **época** que vallan a un ejecutor que perdió la propiedad.

Decisiones de esquema (cada una con su prueba en `tests/test_migracion_asignacion_pg.py`):

- **Una operación viva por archivo y una reserva viva por destino**: dos índices únicos PARCIALES sobre los
  estados vivos (`preparada`, `confirmada`). Reclamar y reservar son la misma inserción atómica. `confirmada`
  sigue siendo viva: es «asignado, con limpieza pendiente» o «reparación pendiente», y NO libera el destino.
- **Estados persistidos ≠ resultados devueltos al cliente.** Solo hay cuatro estados (`preparada`,
  `confirmada`, `limpiada`, `cancelada`). `asignado_limpieza_pendiente`, `reparacion_pendiente`, `pendiente`…
  son RESULTADOS del servicio y no existen en esta tabla: tras ellos la operación sigue en `confirmada` o
  `preparada`, es decir, viva, con su reserva intacta.
- **Borrado sin cascada sobre lo vivo.** `file_id` y `series_id` son `ON DELETE SET NULL` y un CHECK exige que
  una operación viva los tenga: borrar un archivo o una serie con una asignación en curso FALLA (la operación y
  su información de recuperación no desaparecen); con la operación cerrada, el borrado procede y la fila queda
  como historial (con `file_id`/`series_id` a NULL, conservando origen, destino y hash). Un `CASCADE`
  habría borrado la operación a medias y dejado un fichero publicado sin nadie que lo reclame.
- Sin `issue_id`: la operación guarda `issue_number` y `formato` pedidos; el `Issue` se crea o se reutiliza al
  confirmar (V6a/B15).
- `sha256` en minúsculas y 64 hex (como `files.sha256_hash`); rutas hasta 1000 caracteres (como `file_path`).

**Downgrade — destructivo.** Elimina la tabla y el tipo `asignacion_estado`: se PIERDE el historial de
asignaciones y, sobre todo, la información para recuperar las que estén vivas. Por eso se NIEGA si hay
operaciones vivas: bajar con una asignación a medias dejaría ficheros copiados o publicados que nada reclama.
Con solo operaciones cerradas baja y descarta el historial (no toca archivos, issues ni alias). No es inocuo:
haz copia antes (`scripts/update.sh` ya la hace) y reconcilia lo vivo primero.

**El downgrade toma `ACCESS EXCLUSIVE` ANTES de contar**, en la misma transacción que la comprobación y el
`DROP`. Sin eso, una transacción ajena podría confirmar una operación viva entre el recuento (que vería cero) y el
borrado de la tabla, y se perdería la información de recuperación. Detener los escritores sigue siendo
recomendable, pero no sustituye esta defensa.

Estados y resultados: solo `preparada` y `confirmada` son vivas. Los resultados RECUPERABLES del servicio
(`pendiente`, `reparacion_pendiente`, `asignado_limpieza_pendiente`) no son estados y mantienen la operación viva
con su reserva; `destino_ocupado`, en cambio, CANCELA la operación y libera la reserva (el reintento reserva el
siguiente nombre libre).
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_VIVAS = "estado IN ('preparada', 'confirmada')"


def upgrade() -> None:
    op.execute(
        "CREATE TYPE asignacion_estado AS ENUM ('preparada', 'confirmada', 'limpiada', 'cancelada')"
    )
    op.create_table(
        "asignacion_operaciones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="SET NULL")),
        sa.Column("series_id", UUID(as_uuid=True), sa.ForeignKey("series.id", ondelete="SET NULL")),
        sa.Column("estado",
                  PGEnum("preparada", "confirmada", "limpiada", "cancelada",
                         name="asignacion_estado", create_type=False),
                  nullable=False, server_default="preparada"),
        sa.Column("origen", sa.String(1000), nullable=False),
        sa.Column("destino", sa.String(1000), nullable=False),
        sa.Column("temporal", sa.String(1000), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("issue_number", sa.String(20), nullable=False),
        sa.Column("formato",
                  PGEnum(name="issue_format", create_type=False), nullable=False),
        sa.Column("aprender_alias", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("epoca", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creada", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actualizada", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "estado IN ('limpiada', 'cancelada') OR (file_id IS NOT NULL AND series_id IS NOT NULL)",
            name="ck_asignacion_viva_con_referencias"),
        sa.CheckConstraint(
            "origen <> destino AND temporal <> destino AND temporal <> origen",
            name="ck_asignacion_rutas_distintas"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_asignacion_tamano"),
        sa.CheckConstraint("epoca >= 0", name="ck_asignacion_epoca"),
        sa.CheckConstraint("length(btrim(issue_number)) > 0", name="ck_asignacion_issue_number"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_asignacion_sha256"),
    )
    # Índices únicos PARCIALES: lo cerrado no reserva nada.
    op.create_index("uq_asignacion_viva_por_archivo", "asignacion_operaciones", ["file_id"],
                    unique=True, postgresql_where=sa.text(_VIVAS))
    op.create_index("uq_asignacion_viva_por_destino", "asignacion_operaciones", ["destino"],
                    unique=True, postgresql_where=sa.text(_VIVAS))
    # Reconciliar al arrancar lista SOLO lo vivo, por antigüedad: no depende de cuánto historial haya.
    op.create_index("ix_asignacion_viva_creada", "asignacion_operaciones", ["creada"],
                    postgresql_where=sa.text(_VIVAS))
    # Las acciones `ON DELETE SET NULL` buscan por estas columnas (el historial cerrado no está en los parciales).
    op.create_index("ix_asignacion_file_id", "asignacion_operaciones", ["file_id"])
    op.create_index("ix_asignacion_series_id", "asignacion_operaciones", ["series_id"])


def downgrade() -> None:
    bind = op.get_bind()
    # PRIMERO el bloqueo, en esta misma transacción (se mantiene hasta el commit/rollback, tras el DROP): espera
    # a que terminen las transacciones que hayan tocado la tabla y bloquea las nuevas. Contar sin él deja una
    # ventana en la que otra sesión confirma una operación viva después del recuento y antes del borrado.
    bind.execute(sa.text("LOCK TABLE asignacion_operaciones IN ACCESS EXCLUSIVE MODE"))
    vivas = bind.execute(
        sa.text(f"SELECT count(*) FROM asignacion_operaciones WHERE {_VIVAS}")).scalar()
    if vivas:
        raise RuntimeError(
            f"No se puede bajar de la 0017: hay {vivas} operaciones de asignación vivas (preparada o "
            "confirmada). Bajar eliminaría la información para recuperarlas y dejaría ficheros copiados o "
            "publicados que nada reclama. Reconcílialas primero (o resuélvelas a mano tras revisar el disco) "
            "y vuelve a intentarlo."
        )
    op.drop_table("asignacion_operaciones")
    op.execute("DROP TYPE asignacion_estado")
