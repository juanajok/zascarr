"""CCM: barrida inicial (regresión del ID pasado al procesador)."""
from __future__ import annotations

from zascarr.models import Series
from zascarr.services.consolidacion.barrida import _series_con_id


def test_la_barrida_consulta_ids_no_objetos_series():
    """Regresión real: se pasó un `Series` a `db.get` y asyncpg lo trató como UUID."""
    sentencia = _series_con_id()
    columna = sentencia.selected_columns[0]
    assert columna.name == "id" and columna.table.name == Series.__tablename__
    assert "series.id" in str(sentencia)
