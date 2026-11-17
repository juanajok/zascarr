"""Búsqueda/previsualización/importación de sagas de Fandom sin red."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from zascarr.models import Issue, Series, StoryArc, StoryArcIssue
from zascarr.services.arcos_fuentes import (
    importar_arco_fandom,
    previsualizar_arco_fandom,
    url_de_atribucion,
)
from zascarr.services.fandom import FandomArc, FandomSearchPage


class Resultado:
    def __init__(self, filas):
        self._filas = filas

    def scalars(self):
        return self

    def all(self):
        return list(self._filas)

    def first(self):
        return self._filas[0] if self._filas else None


class FakeSession:
    def __init__(self, colas):
        self._colas = list(colas)
        self.added: list = []

    async def execute(self, _stmt):
        return Resultado(self._colas.pop(0))

    def add(self, obj):
        if isinstance(obj, StoryArc) and obj.id is None:
            obj.id = uuid4()
        self.added.append(obj)

    async def flush(self):
        return None


class Cliente:
    def __init__(self, arco):
        self.arco = arco

    async def get_arc(self, _page_title):
        return self.arco


def _series(numero="404"):
    serie = Series(id=uuid4(), title="Batman", tradition="american",
                   fandom_dc_slug="Batman Vol 1")
    issue = Issue(id=uuid4(), series_id=serie.id, issue_number=numero)
    return serie, issue


async def test_previsualizar_mapea_local_y_faltante_sin_crear():
    serie, issue = _series()
    arco = FandomArc(page_title="Batman: Year One", title="Batman: Year One",
                     issues=["Batman Vol 1 404", "Batman Vol 1 405", "sin forma"])
    db = FakeSession([[serie], [issue]])
    previa = await previsualizar_arco_fandom(db, "Batman: Year One", Cliente(arco))
    assert previa is not None
    assert previa.coinciden == 1 and previa.faltan == 1
    assert previa.filas[0].coincide and previa.filas[0].issue_id == str(issue.id)
    assert not db.added  # no crea nada


async def test_importar_crea_arco_y_enlaza_solo_locales():
    serie, issue = _series()
    arco = FandomArc(page_title="Batman: Year One", title="Batman: Year One",
                     issues=["Batman Vol 1 404", "Batman Vol 1 405"])
    # locales (series, issues), arco existente (ninguno), enlaces existentes (ninguno)
    db = FakeSession([[serie], [issue], [], []])
    resultado = await importar_arco_fandom(db, "Batman: Year One", Cliente(arco))
    assert resultado is not None and resultado.creados == 1
    arcos = [o for o in db.added if isinstance(o, StoryArc)]
    enlaces = [o for o in db.added if isinstance(o, StoryArcIssue)]
    assert len(arcos) == 1 and len(enlaces) == 1
    assert arcos[0].metadata_["origen"] == "fandom_dc"
    assert arcos[0].metadata_["fandom_dc"] == "Batman: Year One"
    assert enlaces[0].issue_id == issue.id and enlaces[0].reading_order == 1


async def test_importar_actualiza_arco_existente_sin_borrar_enlaces():
    serie, issue = _series()
    arco = FandomArc(page_title="Batman: Year One", title="Batman: Year One",
                     issues=["Batman Vol 1 404"])
    existente = StoryArc(id=uuid4(), title="Viejo", metadata_={"fandom_dc": "Batman: Year One"})
    otro_enlace = SimpleNamespace(issue_id=uuid4(), reading_order=9)
    db = FakeSession([[serie], [issue], [existente], [otro_enlace]])
    resultado = await importar_arco_fandom(db, "Batman: Year One", Cliente(arco))
    assert resultado is not None and resultado.actualizados == 1
    assert resultado.enlazados == 1
    assert existente.title == "Batman: Year One"
    assert otro_enlace.reading_order == 9
    assert any(o.issue_id == issue.id for o in db.added if isinstance(o, StoryArcIssue))


def test_busqueda_pages_y_atribucion():
    pagina = FandomSearchPage(title="Batman: Year One", snippet="Un arco")
    assert pagina.title == "Batman: Year One"
    assert url_de_atribucion("Batman: Year One") == (
        "https://dc.fandom.com/wiki/Batman:_Year_One")
    assert url_de_atribucion("../fuera") is None
