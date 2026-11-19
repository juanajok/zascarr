"""CCM-0 (#999): forma del diagnóstico, sin base de datos ni red."""
from __future__ import annotations

from zascarr.cli.consolidacion import IDS_ISSUE, IDS_SERIE, _ids, _tabla
from zascarr.models import Series


class _Fila(tuple):
    pass


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, filas):
        self._filas = filas

    async def execute(self, _stmt):
        return _Resultado(self._filas)


async def test_ids_distingue_cero_uno_y_varios():
    # La primera columna es comic_vine_id; la segunda, anilist_id.
    db = _Sesion([
        _Fila((1, None)),
        _Fila((None, None)),
        _Fila((2, 3)),
    ])
    datos = await _ids(db, Series, ("comic_vine_id", "anilist_id"))
    assert datos == {
        "por_campo": {"comic_vine_id": 2, "anilist_id": 1},
        "con_alguno": 2,
        "sin_ninguno": 1,
        "con_mas_de_uno": 1,
        "total_filas": 3,
    }


def test_tabla_resume_las_dos_entidades_y_las_tablas_0032():
    informe = {
        "generado_en": "2026-11-17T00:00:00+00:00",
        "totales": {"series": 3, "issues": 4, "archivos": 5, "colecciones": 1},
        "series": {
            "ids": {"por_campo": {c: 0 for c in IDS_SERIE}, "con_alguno": 0,
                    "sin_ninguno": 3, "con_mas_de_uno": 0, "total_filas": 3},
            "campos": {"start_year": 2}, "con_roles": 0, "con_locks": 1,
        },
        "issues": {
            "ids": {"por_campo": {c: 0 for c in IDS_ISSUE}, "con_alguno": 0,
                    "sin_ninguno": 4, "con_mas_de_uno": 0, "total_filas": 4},
            "campos": {"title": 1},
        },
        "tablas_0032": {"entity_source_records": 0, "field_provenance": 0,
                        "por_fuente": {}, "por_entidad": {}},
        "metadata_source_serie": {},
    }
    texto = _tabla(informe)
    assert "CCM · diagnóstico" in texto
    assert "Series: 3" in texto and "issues: 4" in texto
    assert "entity_source_records: 0" in texto
    assert "sin ninguno: 3" in texto
