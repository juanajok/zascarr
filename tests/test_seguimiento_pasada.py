"""#993: creación de deseos de seguimiento, dedupe y pasada sin fuentes."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from zascarr.models import (
    ComicTradition,
    IssueFormat,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistStatus,
)
from zascarr.services.seguimiento import Hallazgo, crear_deseos, ejecutar_pasada


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


def _serie() -> Series:
    return Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                  follow_new_issues=True,
                  follow_new_issues_since=datetime(2026, 11, 17, tzinfo=UTC))


def _hallazgo(serie, numero, fuente="foro") -> Hallazgo:
    return Hallazgo(fuente=fuente, clave=f"{fuente}:{numero}", serie_id=serie.id,
                    numero=numero, titulo=serie.title)


async def test_crea_deseo_solo_si_no_esta_en_biblioteca_ni_pedido():
    serie = _serie()
    issue_id = uuid4()
    db = _Db(queue=[
        _Res([(issue_id, "12", IssueFormat.SINGLE_ISSUE)]),
        _Res([(issue_id,)]),
        _Res([]),
    ], get_map={serie.id: serie})
    creados = await crear_deseos(db, [_hallazgo(serie, 12), _hallazgo(serie, 13)])
    assert [h.numero for h in creados] == [13]
    deseo = db.added[0]
    assert deseo.origen == WishlistOrigin.SEGUIMIENTO
    assert deseo.priority == 6 and deseo.numero == 13
    assert deseo.status == WishlistStatus.WANTED


async def test_retirado_y_deseo_vivo_no_se_resucitan():
    serie = _serie()
    db = _Db(queue=[_Res([]), _Res([(uuid4(), None, 14, WishlistStatus.RETIRADO)])],
             get_map={serie.id: serie})
    assert await crear_deseos(db, [_hallazgo(serie, 14)]) == []


async def test_deseo_manual_de_serie_vivo_bloquea_los_nuevos():
    serie = _serie()
    db = _Db(queue=[_Res([]), _Res([(uuid4(), None, None, WishlistStatus.WANTED)])],
             get_map={serie.id: serie})
    assert await crear_deseos(db, [_hallazgo(serie, 15)]) == []


async def test_dos_fuentes_mismo_numero_crean_un_solo_deseo():
    serie = _serie()
    db = _Db(queue=[_Res([]), _Res([])], get_map={serie.id: serie})
    creados = await crear_deseos(db, [_hallazgo(serie, 16), _hallazgo(serie, 16, "prowlarr")])
    assert len(creados) == 1
    assert len([o for o in db.added if isinstance(o, Wishlist)]) == 1


async def test_sin_legal_no_hace_nada():
    with patch("zascarr.services.seguimiento.is_acknowledged", AsyncMock(return_value=False)):
        informe = await ejecutar_pasada(_Db())  # type: ignore[arg-type]
    assert informe.deseos == 0 and informe.hallazgos == 0


async def test_sin_series_seguidas_no_hay_red():
    db = _Db(queue=[_Res([]), _Res([])])
    with patch("zascarr.services.seguimiento.is_acknowledged", AsyncMock(return_value=True)), \
            patch("zascarr.services.seguimiento.get_settings", lambda: SimpleNamespace(
                forum_enabled=False, prowlarr_enabled=False, prowlarr_api_key="")):
        informe = await ejecutar_pasada(db)  # type: ignore[arg-type]
    assert informe.deseos == 0 and informe.hallazgos == 0
