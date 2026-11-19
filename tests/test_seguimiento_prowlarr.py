"""#1017: rotación y cupo de Prowlarr en el seguimiento (cobertura de #993)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, SeguimientoVisto, Series
from zascarr.services.seguimiento import (
    InformeSeguimiento,
    _procesar_prowlarr,
)


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)
        self.rowcount = 0

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Db:
    def __init__(self, queue=None):
        self.queue = list(queue or [])
        self.added = []

    async def execute(self, _statement):
        return self.queue.pop(0)

    def add(self, obj):
        self.added.append(obj)


class _Prowlarr:
    def __init__(self, resultados=None):
        self.resultados = resultados or {}
        self.llamadas: list[tuple[str, dict]] = []

    async def search(self, titulo, **opciones):
        self.llamadas.append((titulo, opciones))
        return self.resultados.get(titulo, [])


def _serie(titulo: str, since: datetime) -> Series:
    return Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
                  follow_new_issues=True, follow_new_issues_since=since)


def _resultado(titulo: str, publish_date: str | None, size: int = 1024):
    return SimpleNamespace(title=titulo, indexer="indexer", size_bytes=size,
                           publish_date=publish_date, download_url="magnet:?xt=urn:btih:x",
                           seeders=1, category="comics")


def _ajustes():
    return SimpleNamespace(prowlarr_indexer_ids="")


@pytest.mark.asyncio
async def test_rotacion_consulta_las_mas_antiguas_y_respeta_el_cupo():
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    sandman = _serie("Sandman", datetime(2026, 1, 1, tzinfo=UTC))
    batman = _serie("Batman", datetime(2026, 1, 1, tzinfo=UTC))
    daredevil = _serie("Daredevil", datetime(2026, 1, 1, tzinfo=UTC))
    fila_sandman = SeguimientoVisto(fuente="prowlarr", clave=f"serie:{sandman.id}",
                                    visto_en=datetime(2026, 11, 1, tzinfo=UTC))
    fila_batman = SeguimientoVisto(fuente="prowlarr", clave=f"serie:{batman.id}",
                                   visto_en=datetime(2026, 11, 10, tzinfo=UTC))
    db = _Db(queue=[_Res([fila_sandman, fila_batman])])
    prowlarr = _Prowlarr()

    with patch("zascarr.services.seguimiento.get_settings", lambda: _ajustes()):
        hallazgos = await _procesar_prowlarr(
            db, prowlarr, [sandman, batman, daredevil], {}, ahora,
            InformeSeguimiento(), max_series=2, limite_deseos=10)

    assert hallazgos == []
    # Daredevil no tenía fila (la más antigua) y Sandman es la siguiente.
    assert [titulo for titulo, _ in prowlarr.llamadas] == ["Daredevil", "Sandman"]
    assert all("indexer_ids" not in opciones for _, opciones in prowlarr.llamadas)
    assert [o.clave for o in db.added if isinstance(o, SeguimientoVisto)] == [
        f"serie:{daredevil.id}"]
    assert fila_sandman.visto_en == ahora and fila_sandman.procesado_en == ahora
    assert fila_batman.visto_en == datetime(2026, 11, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_descarta_publish_date_anterior_a_la_frontera_o_sin_fecha():
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    serie = _serie("Batman", datetime(2026, 11, 17, 12, 0, tzinfo=UTC))
    prowlarr = _Prowlarr({"Batman": [
        _resultado("Batman 012.cbz", "17/11/2026"),   # ese día, antes de la frontera
        _resultado("Batman 013.cbz", "18/11/2026"),   # posterior: entra
        _resultado("Batman 014.cbz", None),           # sin fecha: no se adivina
        _resultado("Batman 015.cbz", "16/11/2026"),   # anterior: fuera
    ]})
    db = _Db(queue=[_Res([]), _Res([])])  # rotación + release 13

    with patch("zascarr.services.seguimiento.get_settings", lambda: _ajustes()):
        hallazgos = await _procesar_prowlarr(
            db, prowlarr, [serie], {}, ahora, InformeSeguimiento(),
            max_series=1, limite_deseos=10)

    assert [(h.serie_id, h.numero) for h in hallazgos] == [(serie.id, 13)]
    releases = [o.clave for o in db.added if o.clave.startswith("release:")]
    assert len(releases) == 1


@pytest.mark.asyncio
async def test_respeta_el_cupo_de_deseos_de_la_pasada():
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    serie = _serie("Batman", datetime(2026, 1, 1, tzinfo=UTC))
    prowlarr = _Prowlarr({"Batman": [
        _resultado("Batman 012.cbz", "18/11/2026", size=1),
        _resultado("Batman 013.cbz", "18/11/2026", size=2),
        _resultado("Batman 014.cbz", "18/11/2026", size=3),
    ]})
    db = _Db(queue=[_Res([]), _Res([])])  # rotación + un solo release

    with patch("zascarr.services.seguimiento.get_settings", lambda: _ajustes()):
        hallazgos = await _procesar_prowlarr(
            db, prowlarr, [serie], {}, ahora, InformeSeguimiento(),
            max_series=1, limite_deseos=1)

    assert [h.numero for h in hallazgos] == [12]
    assert len(prowlarr.llamadas) == 1


@pytest.mark.asyncio
async def test_una_consulta_por_serie_y_pasada():
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    serie = _serie("Batman", datetime(2026, 1, 1, tzinfo=UTC))
    prowlarr = _Prowlarr({"Batman": [
        _resultado("Batman 012.cbz", "18/11/2026"),
        _resultado("Batman 013.cbz", "18/11/2026"),
    ]})
    db = _Db(queue=[_Res([]), _Res([]), _Res([])])

    with patch("zascarr.services.seguimiento.get_settings", lambda: _ajustes()):
        await _procesar_prowlarr(db, prowlarr, [serie], {}, ahora,
                                 InformeSeguimiento(), max_series=1,
                                 limite_deseos=10)

    assert len(prowlarr.llamadas) == 1
