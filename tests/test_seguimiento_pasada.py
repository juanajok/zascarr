"""#993: creación de deseos de seguimiento, dedupe y pasada sin fuentes."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from zascarr.models import (
    ComicTradition,
    IssueFormat,
    MetadataSource,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.politica import Querer, pendientes_de_buscar, querer_de_serie
from zascarr.services.seguimiento import Hallazgo, crear_deseos, ejecutar_pasada


class _Res:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar(self):
        return self._rows[0] if self._rows else None

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


class _CapturaDb(_Db):
    """Como `_Db`, pero guarda el SQL compilado de cada consulta."""

    def __init__(self, queue=None):
        super().__init__(queue)
        self.statements: list = []

    async def execute(self, statement):
        self.statements.append(statement)
        return await super().execute(statement)


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


# ── #1017: aviso único y AC-16 (interacción con la política) ─────────────────


async def test_aviso_una_vez_por_pasada_y_como_mucho_cinco():
    """Aunque la pasada cree más deseos, el webhook recibe UNA llamada y como
    mucho `seguimiento_max_avisos` novedades."""
    serie = _serie()
    hallazgos = [_hallazgo(serie, numero) for numero in range(1, 8)]
    notifier = SimpleNamespace(
        notify_novedades=AsyncMock(return_value=SimpleNamespace(ok=True)))
    ajustes = SimpleNamespace(
        forum_enabled=False, prowlarr_enabled=False, prowlarr_api_key="",
        seguimiento_max_deseos=10, seguimiento_max_avisos=5,
        seguimiento_retencion_dias=90)

    with patch("zascarr.services.seguimiento.is_acknowledged", AsyncMock(return_value=True)), \
            patch("zascarr.services.seguimiento.cargar_series_seguidas",
                  AsyncMock(return_value=([serie], {}))), \
            patch("zascarr.services.seguimiento._procesar_foro",
                  AsyncMock(return_value=(hallazgos, 0, 0))), \
            patch("zascarr.services.seguimiento.crear_deseos",
                  AsyncMock(return_value=hallazgos)), \
            patch("zascarr.services.seguimiento.purgar_vistos", AsyncMock()), \
            patch("zascarr.services.seguimiento.get_settings", lambda: ajustes):
        informe = await ejecutar_pasada(_Db(), foro=object(), notifier=notifier)

    assert informe.deseos == 7
    assert notifier.notify_novedades.await_count == 1
    textos = notifier.notify_novedades.await_args.args[0]
    assert len(textos) == 5
    assert [numero for _, numero in textos] == [1, 2, 3, 4, 5]
    assert informe.avisados == 5


async def test_ac16_un_deseo_de_seguimiento_vivo_ocupa_su_numero():
    """Un `SEGUIMIENTO` vivo del número 7 impide que la política genere un
    `POLICY` para el 7 (misma regla que un deseo manual de número)."""
    serie = _serie()
    serie.total_issues = 10
    serie.metadata_source = MetadataSource.COMIC_VINE.value
    serie.wishlist_policy = WishlistPolicy.ALL
    # (issue_id=None, numero=7) vivo + ningún número poseído.
    db = _Db(queue=[_Res([(None, 7)]), _Res([])])

    querer = await querer_de_serie(db, serie)

    assert querer.computable
    assert querer.numeros == frozenset(set(range(1, 11)) - {7})


async def test_ac16_el_cupo_de_la_politica_no_cuenta_deseos_de_seguimiento():
    """`pendientes_de_buscar` solo mira `origen='politica'`: un deseo de
    seguimiento no consume el cupo por hora de la generación."""
    serie = _serie()
    db = _CapturaDb(queue=[_Res([]), _Res([0])])

    await pendientes_de_buscar(db, serie, Querer(frozenset({1}), True))

    sql = "\n".join(
        str(statement.compile(dialect=postgresql.dialect(),
                              compile_kwargs={"literal_binds": True}))
        for statement in db.statements)
    assert sql.count("origen = 'politica'") == 2
    assert "seguimiento" not in sql
