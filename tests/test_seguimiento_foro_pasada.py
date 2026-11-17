"""#993: primera pasada por serie y temas actualizados (regresión QA B2)."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, Series, SeguimientoVisto
from zascarr.services.seguimiento import (
    InformeSeguimiento,
    TemaForo,
    _procesar_foro,
)


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

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


class _Foro:
    def __init__(self, tema, enlaces):
        self._tema = tema
        self._enlaces = enlaces

    async def listar_temas(self, foro_id=5, limite=50):
        return [self._tema]

    async def leer_tema(self, url):
        return self._enlaces


def _serie(titulo: str, since: datetime) -> Series:
    return Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
                  follow_new_issues=True, follow_new_issues_since=since)


@pytest.mark.asyncio
async def test_primera_pasada_no_mezcla_la_frontera_de_otra_serie():
    """QA B2: un tema de junio no puede crear el deseo de una serie seguida en noviembre."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    vieja = _serie("Sandman", datetime(2026, 1, 1, tzinfo=UTC))
    nueva = _serie("Batman", datetime(2026, 11, 17, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="01/06/2026")
    enlaces = type("R", (), {"ed2k_links": ["ed2k://|file|Batman%2012.cbz|1|H|/"],
                             "magnet_links": []})()
    db = _Db(queue=[_Res([]), _Res([])])   # select visto + _marcar_visto
    informe = InformeSeguimiento()

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, enlaces), [vieja, nueva], {}, ahora, informe,
        max_temas=10, limite_deseos=10, desde_cache=0)

    assert hallazgos == []
    assert not [o for o in db.added if o.__class__.__name__ == "Wishlist"]


@pytest.mark.asyncio
async def test_un_tema_actualizado_si_se_procesa():
    """Una huella distinta es una actualización: se abre aunque ya estuviera visto."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    serie = _serie("Batman", datetime(2026, 1, 1, tzinfo=UTC))
    visto = SeguimientoVisto(fuente="foro", clave="tema:1", huella="Ayer, 20:01",
                             visto_en=datetime(2026, 11, 16, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="Hoy, 10:00")
    enlaces = type("R", (), {"ed2k_links": ["ed2k://|file|Batman%2012.cbz|1|H|/"],
                             "magnet_links": []})()
    db = _Db(queue=[_Res([visto]), _Res([visto])])
    informe = InformeSeguimiento()

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, enlaces), [serie], {}, ahora, informe,
        max_temas=10, limite_deseos=10, desde_cache=0)

    assert [(h.serie_id, h.numero) for h in hallazgos] == [(serie.id, 12)]
