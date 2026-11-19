"""#993: primera pasada por serie y temas actualizados (regresión QA B2)."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, Series, SeguimientoVisto
from zascarr.services.seguimiento import (
    InformeSeguimiento,
    TemaForo,
    _fecha_de_actividad,
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


def test_fecha_de_actividad_entiende_el_formato_ingles_del_foro():
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    assert _fecha_de_actividad("5th August 2026 - 18:24", ahora) == datetime(
        2026, 8, 5, 18, 24, tzinfo=UTC)
    assert _fecha_de_actividad("Nov 14 2019, 14:38", ahora) == datetime(
        2019, 11, 14, 14, 38, tzinfo=UTC)
    assert _fecha_de_actividad("Today, 10:32", ahora).day == 17


# ── #1017 (O-2): frontera por serie también en temas ya vistos ──────────────


def _enlaces(*nombres: str):
    return type("R", (), {
        "ed2k_links": [f"ed2k://|file|{nombre.replace(' ', '%20')}|1|H|/" for nombre in nombres],
        "magnet_links": [],
    })()


@pytest.mark.asyncio
async def test_tema_actualizado_no_crea_historico_de_una_serie_nueva():
    """O-2: un tema viejo que se actualiza no puede crear el deseo histórico de
    una serie activada después; la serie vieja sí lo recibe."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    vieja = _serie("Sandman", datetime(2026, 1, 1, tzinfo=UTC))
    nueva = _serie("Batman", datetime(2026, 11, 17, tzinfo=UTC))
    visto = SeguimientoVisto(fuente="foro", clave="tema:1", huella="01/06/2026",
                             visto_en=datetime(2026, 6, 2, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="17/11/2026")
    db = _Db(queue=[_Res([visto]), _Res([visto])])

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, _enlaces("Sandman 5.cbz", "Batman 12.cbz")),
        [vieja, nueva], {}, ahora, InformeSeguimiento(),
        max_temas=10, limite_deseos=10, desde_cache=0)

    assert [(h.serie_id, h.numero) for h in hallazgos] == [(vieja.id, 5)]


@pytest.mark.asyncio
async def test_tema_actualizado_despues_de_la_frontera_si_crea_para_la_nueva():
    """Control: si el tema ya tenía actividad posterior a la activación de la
    serie nueva, la actualización sí cuenta para ella."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    nueva = _serie("Batman", datetime(2026, 11, 1, tzinfo=UTC))
    visto = SeguimientoVisto(fuente="foro", clave="tema:1", huella="10/11/2026",
                             visto_en=datetime(2026, 11, 10, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="17/11/2026")
    db = _Db(queue=[_Res([visto]), _Res([visto])])

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, _enlaces("Batman 12.cbz")), [nueva], {}, ahora,
        InformeSeguimiento(), max_temas=10, limite_deseos=10, desde_cache=0)

    assert [(h.serie_id, h.numero) for h in hallazgos] == [(nueva.id, 12)]


@pytest.mark.asyncio
async def test_huella_relativa_se_resuelve_contra_visto_en_no_contra_hoy():
    """«Hoy/Ayer» se guardó en una pasada anterior: la referencia es ese día,
    no la fecha de la pasada actual (si no, un tema viejo parecería nuevo)."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    nueva = _serie("Batman", datetime(2026, 11, 15, tzinfo=UTC))
    visto = SeguimientoVisto(fuente="foro", clave="tema:1", huella="Hoy, 10:32",
                             visto_en=datetime(2026, 11, 10, 9, 0, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="17/11/2026")
    db = _Db(queue=[_Res([visto]), _Res([visto])])

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, _enlaces("Batman 12.cbz")), [nueva], {}, ahora,
        InformeSeguimiento(), max_temas=10, limite_deseos=10, desde_cache=0)

    assert hallazgos == []


@pytest.mark.asyncio
async def test_sin_actividad_previa_fechable_usa_visto_en_y_falla_cerrado():
    """Si la huella guardada no es una fecha, `visto_en` decide; un tema visto
    antes de activar la serie no crea su histórico."""
    ahora = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    nueva = _serie("Batman", datetime(2026, 11, 17, tzinfo=UTC))
    visto = SeguimientoVisto(fuente="foro", clave="tema:1", huella="sin-fecha",
                             visto_en=datetime(2026, 6, 2, tzinfo=UTC))
    tema = TemaForo(id=1, titulo="E-links del día", url="https://foro.example/1",
                    ultima_actividad="17/11/2026")
    db = _Db(queue=[_Res([visto]), _Res([visto])])

    hallazgos, _, _ = await _procesar_foro(
        db, _Foro(tema, _enlaces("Batman 12.cbz")), [nueva], {}, ahora,
        InformeSeguimiento(), max_temas=10, limite_deseos=10, desde_cache=0)

    assert hallazgos == []

