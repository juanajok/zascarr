# ruff: noqa: E501
"""Reconciliación de guías con la biblioteca sobre `story_arcs` (SCR3 entrega 2).

Sin Postgres: `FakeSession` determinista (la consulta n-ésima devuelve el resultado n-ésimo).
Se verifica el upsert idempotente, el reordenado, los ítems descartados y que **no se escribe**
en la biblioteca (solo en `story_arcs`/`story_arc_issues`).
"""
from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zascarr.models import StoryArc, StoryArcIssue
from zascarr.services.reading_orders import GuiaLeida, RawReadingEntry
from zascarr.services.reconciliacion_lecturas import (
    ResultadoReconciliacion,
    leer_y_reconciliar,
    reconciliar_guia,
    titulo_de_guia,
)


class Resultado:
    """Doble mínimo de un `Result` de SQLAlchemy."""

    def __init__(self, filas=()):
        self._filas = list(filas)

    def scalars(self):
        return self

    def all(self):
        return list(self._filas)

    def first(self):
        return self._filas[0] if self._filas else None


class SesionFalsa:
    """Sesión con resultados en cola; registra add/delete/flush para comprobar que no escribe."""

    def __init__(self, resultados):
        self.resultados = deque(resultados)
        self.added: list[object] = []
        self.borrados: list[object] = []
        self.flushs = 0

    async def execute(self, _consulta):
        return self.resultados.popleft()

    def add(self, objeto):
        self.added.append(objeto)

    async def delete(self, objeto):
        self.borrados.append(objeto)

    async def flush(self):
        self.flushs += 1


def _serie(ident, title, *, start_year=None, volume=None):
    return SimpleNamespace(id=ident, title=title, title_norm=title.lower(),
                           start_year=start_year, volume=volume)


def _issue(ident, serie_id, numero):
    return SimpleNamespace(id=ident, series_id=serie_id, issue_number=numero)


def _arco(ident, title, metadata):
    return SimpleNamespace(id=ident, title=title, metadata_=dict(metadata))


def _enlace(issue_id, orden, arco_id="arco-1"):
    return SimpleNamespace(story_arc_id=arco_id, issue_id=issue_id, reading_order=orden)


def _guia(*referencias, titulo="Crisis on Infinite Earths", url=None):
    url = url or ("https://comicbookreadingorders.com/dc/events/"
                  "crisis-on-infinite-earths-reading-order/")
    entradas = tuple(RawReadingEntry(orden=indice + 1, referencia=referencia,
                                     seccion=None, item_url=None)
                     for indice, referencia in enumerate(referencias))
    return GuiaLeida(sitio="reading_orders", url=url, titulo=titulo, entradas=entradas)


async def test_crea_arco_con_enlaces_en_orden():
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue1, issue2, issue3 = (_issue("i-1", "s-dd", "1"), _issue("i-2", "s-dd", "2"),
                              _issue("i-3", "s-dd", "3"))
    sesion = SesionFalsa([
        Resultado([]),               # StoryArc por título
        Resultado([serie]),          # Series de «Daredevil (1998) #1-2»
        Resultado([issue1]),         # Issue #1
        Resultado([issue2]),         # Issue #2
        Resultado([serie]),          # Series de «Daredevil (1998) #3»
        Resultado([issue3]),         # Issue #3
        Resultado([]),               # enlaces actuales
    ])
    resultado = await reconciliar_guia(sesion, _guia(
        "Daredevil (1998) #1-2", "Daredevil (1998) #3"))
    assert resultado.creado and resultado.enlazados == 3 and resultado.omitidos == 0
    assert resultado.titulo == "Crisis on Infinite Earths"
    arcos = [objeto for objeto in sesion.added if isinstance(objeto, StoryArc)]
    enlaces = [objeto for objeto in sesion.added if isinstance(objeto, StoryArcIssue)]
    assert len(arcos) == 1 and len(enlaces) == 3
    assert arcos[0].metadata_ == {
        "origen": "reading_orders",
        "url": "https://comicbookreadingorders.com/dc/events/crisis-on-infinite-earths-reading-order/",
    }
    assert [(e.issue_id, e.reading_order) for e in enlaces] == [
        ("i-1", 1), ("i-2", 2), ("i-3", 3)]
    assert sesion.flushs == 1


async def test_reejecutar_actualiza_orden_y_no_duplica():
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue1, issue2, issue3 = (_issue("i-1", "s-dd", "1"),
                              _issue("i-2", "s-dd", "2"),
                              _issue("i-3", "s-dd", "3"))
    arco = _arco("arco-1", "Crisis on Infinite Earths",
                 {"origen": "reading_orders",
                  "url": "https://comicbookreadingorders.com/dc/events/"
                         "crisis-on-infinite-earths-reading-order/"})
    # La guía ahora pide #3 y luego #1-2; el enlace de #9 ya no consta.
    enlaces = [_enlace("i-3", 1), _enlace("i-1", 2), _enlace("i-2", 3),
               _enlace("i-9", 4)]
    sesion = SesionFalsa([
        Resultado([arco]),
        Resultado([serie]), Resultado([issue3]),
        Resultado([serie]), Resultado([issue1]), Resultado([issue2]),
        Resultado(enlaces),
    ])
    resultado = await reconciliar_guia(sesion, _guia(
        "Daredevil (1998) #3", "Daredevil (1998) #1-2"))
    assert not resultado.creado and resultado.enlazados == 3
    assert not [o for o in sesion.added if isinstance(o, StoryArc)]
    assert not [o for o in sesion.added if isinstance(o, StoryArcIssue)]
    assert [enlace.issue_id for enlace in sesion.borrados] == ["i-9"]
    assert [(e.issue_id, e.reading_order) for e in enlaces if e.issue_id != "i-9"] == [
        ("i-3", 1), ("i-1", 2), ("i-2", 3)]
    assert arco.metadata_["origen"] == "reading_orders"


async def test_no_reconciliados_se_omiten_con_motivos():
    serie = _serie("s-x", "X-Men", start_year=1991)
    sesion = SesionFalsa([
        Resultado([]),               # arco nuevo
        Resultado([]),               # «Serie Fantasma #1» → sin serie
        Resultado([serie]),          # «X-Men #99» → serie sí…
        Resultado([]),               # …pero el número no está
        Resultado([]),               # enlaces
    ])
    resultado = await reconciliar_guia(sesion, _guia(
        "Serie Fantasma #1", "Part II: The Dark Phoenix Saga",
        "Batman Vol. 2 TPB", "X-Men #99"))
    assert resultado.enlazados == 0
    assert resultado.omitidos == 4
    assert dict(resultado.motivos) == {
        "no_aplica": 1, "numero_no_encontrado": 1, "serie_no_encontrada": 1,
        "sin_referencia": 1,
    }
    assert [o for o in sesion.added if isinstance(o, StoryArc)]
    assert not [o for o in sesion.added if isinstance(o, StoryArcIssue)]


async def test_ambiguo_no_se_adivina():
    candidata_a = _serie("s-a", "Batman")
    candidata_b = _serie("s-b", "Batman")
    sesion = SesionFalsa([
        Resultado([]),
        Resultado([candidata_a, candidata_b]),   # dos «Batman», sin volumen ni año que desempate
        Resultado([]),
    ])
    resultado = await reconciliar_guia(sesion, _guia("Batman #1"))
    assert resultado.omitidos == 1 and dict(resultado.motivos)["ambiguo"] == 1
    assert not [o for o in sesion.added if isinstance(o, StoryArcIssue)]


async def test_desempate_por_volumen_y_anio_del_volumen():
    batman_v2 = _serie("s-v2", "Batman", start_year=1940, volume=2)
    batman_v3 = _serie("s-v3", "Batman", start_year=2016, volume=3)
    issue = _issue("i-b3-1", "s-v3", "1")
    sesion = SesionFalsa([
        Resultado([]),
        Resultado([batman_v2, batman_v3]),
        Resultado([issue]),
        Resultado([]),
    ])
    resultado = await reconciliar_guia(sesion, _guia("Batman Vol. 3 (2016) #1"))
    assert resultado.enlazados == 1 and resultado.omitidos == 0
    assert [o.issue_id for o in sesion.added if isinstance(o, StoryArcIssue)] == ["i-b3-1"]


async def test_un_numero_repetido_en_la_guia_no_duplica_el_enlace():
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue = _issue("i-1", "s-dd", "1")
    sesion = SesionFalsa([Resultado([]), Resultado([serie]), Resultado([issue]),
                          Resultado([serie]), Resultado([issue]), Resultado([])])
    resultado = await reconciliar_guia(sesion, _guia(
        "Daredevil (1998) #1", "Daredevil (1998) #1"))
    assert resultado.enlazados == 1
    enlaces = [o for o in sesion.added if isinstance(o, StoryArcIssue)]
    assert len(enlaces) == 1 and enlaces[0].reading_order == 1


async def test_solo_escribe_en_arcos_y_enlaces():
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue = _issue("i-1", "s-dd", "1")
    sesion = SesionFalsa([Resultado([]), Resultado([serie]), Resultado([issue]),
                          Resultado([])])
    await reconciliar_guia(sesion, _guia("Daredevil (1998) #1"))
    assert all(isinstance(o, (StoryArc, StoryArcIssue)) for o in sesion.added)
    assert sesion.borrados == []


def test_titulo_de_guia_usa_el_slug_si_falta_titulo():
    guia = GuiaLeida(sitio="continuity_guide",
                     url="https://www.continuityguide.net/planet-x-part-2",
                     titulo=None, entradas=())
    assert titulo_de_guia(guia) == "planet x part 2"


async def test_leer_y_reconciliar_lee_y_reconcilia():
    guia = GuiaLeida(sitio="continuity_guide",
                     url="https://www.continuityguide.net/planetx",
                     titulo="Planet X", entradas=())
    extractor = SimpleNamespace(leer_guia=AsyncMock(return_value=guia))
    sesion = SesionFalsa([Resultado([]), Resultado([])])
    resultado = await leer_y_reconciliar(sesion, extractor,
                                         "https://www.continuityguide.net/planetx")
    assert isinstance(resultado, ResultadoReconciliacion)
    extractor.leer_guia.assert_awaited_once_with(
        "https://www.continuityguide.net/planetx")
    extractor.leer_guia.return_value = None
    assert await leer_y_reconciliar(sesion, extractor, "https://www.continuityguide.net/x") is None


def test_resultado_es_inmutable():
    resultado = ResultadoReconciliacion(titulo="t", origen="reading_orders",
                                        url="https://x/", creado=True,
                                        enlazados=0, omitidos=0)
    with pytest.raises(AttributeError):
        resultado.titulo = "otro"


# ── SecOps C-1/c-2/c-3 (addendum de la entrega 2) ───────────────────────────────────────────

def _url_guia() -> str:
    return ("https://comicbookreadingorders.com/dc/events/"
            "crisis-on-infinite-earths-reading-order/")


async def test_c1_no_adopta_ni_toca_un_arco_de_otra_fuente_con_el_mismo_titulo():
    """C-1: la identidad es metadata origen+URL; un arco Fandom homónimo queda intacto."""
    arco_fandom = _arco("arco-fandom", "Crisis on Infinite Earths",
                        {"origen": "fandom_dc", "fandom_dc": "Crisis on Infinite Earths"})
    metadata_original = dict(arco_fandom.metadata_)
    enlace_fandom = _enlace("i-9", 4, arco_id="arco-fandom")
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue = _issue("i-1", "s-dd", "1")
    sesion = SesionFalsa([
        Resultado([]),                  # no hay arco de ESTA guía (origen+url)
        Resultado([serie]), Resultado([issue]),   # entrada reconciliada
        Resultado([]),                  # enlaces del arco nuevo
    ])
    resultado = await reconciliar_guia(sesion, _guia("Daredevil (1998) #1"))
    assert resultado.creado
    arcos = [objeto for objeto in sesion.added if isinstance(objeto, StoryArc)]
    assert len(arcos) == 1 and arcos[0].metadata_["origen"] == "reading_orders"
    assert arcos[0].metadata_["url"] == _url_guia()
    assert arco_fandom.metadata_ == metadata_original     # intacto, no se le fusiona nada
    assert enlace_fandom.reading_order == 4              # su enlace no se toca
    assert not [objeto for objeto in sesion.borrados]    # no se borran enlaces ajenos


async def test_c1_la_identidad_es_la_url_y_un_titulo_nuevo_no_duplica():
    """C-1: si la guía cambia de título, se actualiza la MISMA fila (identidad = URL)."""
    arco = _arco("arco-guia", "Título viejo", {"origen": "reading_orders", "url": _url_guia()})
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue = _issue("i-1", "s-dd", "1")
    sesion = SesionFalsa([Resultado([arco]), Resultado([serie]), Resultado([issue]),
                          Resultado([])])
    resultado = await reconciliar_guia(sesion, _guia("Daredevil (1998) #1",
                                                     titulo="Título nuevo"))
    assert not resultado.creado
    assert arco.title == "Título nuevo"
    assert not [objeto for objeto in sesion.added if isinstance(objeto, StoryArc)]


async def test_c3_numero_con_varios_volumenes_usa_el_del_item_o_es_ambiguo():
    serie = _serie("s-dd", "Daredevil", start_year=1998)
    issue_v1 = SimpleNamespace(id="i-v1", series_id="s-dd", issue_number="1", volume=1)
    issue_v2 = SimpleNamespace(id="i-v2", series_id="s-dd", issue_number="1", volume=2)
    sesion = SesionFalsa([
        Resultado([]), Resultado([serie]),
        Resultado([issue_v1, issue_v2]), Resultado([]),
    ])
    resultado = await reconciliar_guia(sesion, _guia("Daredevil (1998) #1"))
    assert resultado.omitidos == 1 and dict(resultado.motivos)["ambiguo"] == 1
    assert not [o for o in sesion.added if isinstance(o, StoryArcIssue)]

    # Con el volumen del ítem sí se desempata (Vol. 2).
    sesion = SesionFalsa([
        Resultado([]), Resultado([serie]),
        Resultado([issue_v1, issue_v2]), Resultado([]),
    ])
    resultado = await reconciliar_guia(sesion, _guia("Daredevil Vol. 2 (1998) #1"))
    assert resultado.enlazados == 1 and resultado.omitidos == 0
    assert [o.issue_id for o in sesion.added if isinstance(o, StoryArcIssue)] == ["i-v2"]


def test_c2_texto_para_terminal_quita_controles_y_acota():
    from zascarr.services.reconciliacion_lecturas import texto_para_terminal

    sucio = "Guía \x1b[2J\x1b]52;c;x\x07 normal\tt\u202e"
    limpio = texto_para_terminal(sucio)
    assert "\x1b" not in limpio and "\x07" not in limpio and "\u202e" not in limpio
    assert "\t" not in limpio and len(limpio) <= 200
    assert len(texto_para_terminal("A" * 500)) == 200


def test_c2_el_script_sanea_el_titulo_antes_de_imprimirlo():
    from pathlib import Path as _Path

    fuente = _Path(__file__).resolve().parents[1] / "scripts" / "reconciliar-lecturas.py"
    texto = fuente.read_text(encoding="utf-8")
    assert "texto_para_terminal(resultado.titulo)" in texto
