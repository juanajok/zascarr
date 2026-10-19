"""Fuentes de metadatos apagadas por defecto (#239, ADR 0013): conservar activas las de las instalaciones con uso previo.

Revision ID: 0020
Revises: 0019

Por qué existe: `config.py` pasa los cuatro interruptores de fuentes de metadatos (`comicvine_enabled`,
`anilist_enabled`, `tebeosfera_enabled`, `gcd_enabled`) de `default=True` a `default=False`. Una instalación que ya
funcionaba con el valor antiguo —y que nunca guardó esos interruptores en Ajustes— quedaría con las fuentes
APAGADAS al actualizar, sin que nadie se lo dijera. Condición del PO: **una actualización no apaga fuentes en
silencio**. Esta migración de datos escribe, en esas instalaciones, el valor que ya tenían de hecho (activas).

Qué hace (solo datos; no cambia el esquema):

- Una instalación tiene **uso previo** si hay alguna fila en `series`, `files`, `wishlist`, `import_runs` o
  `legal_acknowledgments`, o si `runtime_settings` ya guarda algún ajuste. En ese caso escribe las cuatro claves
  como `true` en `runtime_settings.values`, **sin pisar** las que el coleccionista ya guardó (su valor, activo o
  no, manda: `nuevas || existentes`).
- Tres estados, no dos, y **persistidos** (ADR 0013): si además NINGUNA de las cuatro claves estaba guardada (el
  coleccionista nunca decidió), escribe `fuentes_heredadas = true`: «activas por compatibilidad». Ajustes muestra
  el aviso solo en ese estado y guardar «Fuentes de metadatos» lo pone a `false`. Quien ya había guardado las
  fuentes (activas o no) no recibe el marcador: su decisión es explícita.
- Una instalación nueva (la migración corre sobre tablas vacías, dentro de `bootstrap.sh`) no se toca: nace con el
  nuevo default, apagadas.
- Garantiza la fila `id=1` de `runtime_settings` (la 0011 la siembra; una restauración de un backup anterior puede
  no tenerla).

Límite conocido: una instalación existente **sin ningún dato y sin ningún ajuste** (nunca llegó a funcionar) se
trata como nueva y queda apagada. No hay nada que conservar.

**Downgrade — no hace nada, a propósito.** No puede saber qué claves puso esta migración y cuáles guardó el
coleccionista; borrarlas cambiaría su comportamiento. Con el código antiguo (default activo) las claves a `true`
son inofensivas.
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_USO_PREVIO = """(
    EXISTS (SELECT 1 FROM series)
    OR EXISTS (SELECT 1 FROM files)
    OR EXISTS (SELECT 1 FROM wishlist)
    OR EXISTS (SELECT 1 FROM import_runs)
    OR EXISTS (SELECT 1 FROM legal_acknowledgments)
    OR (SELECT "values" FROM runtime_settings WHERE id = 1) <> '{}'::jsonb
)"""


def upgrade() -> None:
    op.execute(
        """INSERT INTO runtime_settings (id, "values") SELECT 1, '{}'::jsonb
           WHERE NOT EXISTS (SELECT 1 FROM runtime_settings WHERE id = 1)"""
    )
    op.execute(
        f"""UPDATE runtime_settings
            SET "values" = (CASE WHEN jsonb_exists_any("values", ARRAY['comicvine_enabled', 'anilist_enabled',
                                                                      'tebeosfera_enabled', 'gcd_enabled'])
                                 THEN '{{}}'::jsonb
                                 ELSE jsonb_build_object('fuentes_heredadas', true) END)
                || jsonb_build_object(
                    'comicvine_enabled', true, 'anilist_enabled', true,
                    'tebeosfera_enabled', true, 'gcd_enabled', true) || "values",
                updated_at = now()
            WHERE id = 1 AND {_USO_PREVIO}"""
    )


def downgrade() -> None:
    """Sin efecto (ver el docstring del módulo)."""
