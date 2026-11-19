"""#1027/ADR 0022: obra autoconclusiva — dominio, política y alta."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from zascarr.models import (
    ComicTradition,
    FileFormat,
    Issue,
    IssueFormat,
    Series,
    SeriesKind,
    WishlistPolicy,
)
from zascarr.services.coleccion import estado_puro
from zascarr.services.obras_autoconclusivas import (
    ObraAutoconclusivaError,
    crear_obra_autoconclusiva,
)
from zascarr.services.politica import MOTIVO_OBRA_AUTOCONCLUSIVA, querer_de_serie
from zascarr.services.series import Huecos, huecos_de_serie, razon_de_no_calculable


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Db:
    def __init__(self, queue=None, get_map=None):
        self.queue = list(queue or [])
        self.get_map = get_map or {}
        self.added = []
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    async def execute(self, _statement):
        return self.queue.pop(0)

    async def get(self, _model, ident):
        return self.get_map.get(ident)

    def add(self, obj):
        self.added.append(obj)


def _one_shot() -> Series:
    return Series(id=uuid4(), title="Una novela gráfica",
                  tradition=ComicTradition.AMERICAN, kind=SeriesKind.ONE_SHOT,
                  wishlist_policy=WishlistPolicy.MISSING, total_issues=1,
                  metadata_source="comic_vine")


def test_razon_pura_no_bloquea_la_obra_unica():
    assert razon_de_no_calculable(_one_shot()) is None
    assert estado_puro(_one_shot(), set(), tiene_publicacion=True).tipo == "completa"
    assert estado_puro(_one_shot(), set()).faltantes == ()
    assert estado_puro(_one_shot(), set(), tiene_publicacion=False).tipo == "no_calculable"


async def test_huecos_obra_unica_completa_con_publicacion():
    serie = _one_shot()
    db = _Db(queue=[_Res([uuid4()])])
    huecos = await huecos_de_serie(db, serie)  # type: ignore[arg-type]
    assert huecos.computable and huecos.faltantes == []


async def test_huecos_obra_unica_sin_archivo_no_se_da_por_completa():
    serie = _one_shot()
    db = _Db(queue=[_Res([])])
    huecos = await huecos_de_serie(db, serie)  # type: ignore[arg-type]
    assert huecos.faltantes == [] and not huecos.computable
    assert "sin publicación con archivo" in (huecos.motivo or "")


async def test_huecos_obra_unica_sin_publicacion_no_inventa_el_numero_uno():
    serie = _one_shot()
    db = _Db(queue=[_Res([])])
    huecos = await huecos_de_serie(db, serie)  # type: ignore[arg-type]
    assert huecos.faltantes == [] and not huecos.computable
    assert "sin publicación" in (huecos.motivo or "")


async def test_politica_no_quiere_numeros_de_una_obra_unica():
    querer = await querer_de_serie(_Db(), _one_shot())  # type: ignore[arg-type]
    assert querer.numeros == frozenset() and querer.computable
    assert querer.motivo == MOTIVO_OBRA_AUTOCONCLUSIVA


async def test_alta_crea_serie_one_shot_sin_numero_y_enlaza_archivo():
    archivo = SimpleNamespace(id=uuid4(), issue_id=None, metadata_={})
    db = _Db(get_map={})
    db.get_map[id(archivo)] = archivo
    # `db.get` recibe el file_id, no el objeto; la clave real es el id.
    db.get_map[archivo.id] = archivo
    serie, issue = await crear_obra_autoconclusiva(
        db, archivo.id, "Una novela gráfica", IssueFormat.GRAPHIC_NOVEL,
        tradicion=ComicTradition.AMERICAN)  # type: ignore[arg-type]
    assert serie.kind == SeriesKind.ONE_SHOT
    assert issue.issue_number is None and issue.format == IssueFormat.GRAPHIC_NOVEL
    assert archivo.issue_id == issue.id
    assert not any(isinstance(o, Issue) and o.issue_number == "1" for o in db.added)


async def test_alta_rechaza_un_archivo_ya_enlazado():
    archivo = SimpleNamespace(id=uuid4(), issue_id=uuid4(), metadata_={})
    db = _Db(get_map={archivo.id: archivo})
    with pytest.raises(ObraAutoconclusivaError):
        await crear_obra_autoconclusiva(db, archivo.id, "Obra", "graphic_novel")  # type: ignore[arg-type]
