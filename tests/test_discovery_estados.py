# ruff: noqa: E501
"""`DiscoveryService.search_detallada` (rebanada 2a): el estado de CADA fuente, no solo un texto de aviso.

`ok` (se consultó), `apagada` (desactivada en la configuración), `sin_clave` (Comic Vine encendida sin clave: no
se consulta) y `error` (se consultó y falló). Una fuente que falla o está apagada no tumba las demás, y
`search` conserva su contrato de siempre (lo cubre `tests/test_discovery_service.py`).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from zascarr.services.anilist import AniListResult
from zascarr.services.comic_vine import CVResult
from zascarr.services.discovery import (
    FUENTE_APAGADA,
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    ORDEN_DE_FUENTES,
    DiscoveryService,
)
from zascarr.services.gcd import GCDResult
from zascarr.services.tebeosfera import TebeosferaResult


def _ctx(valor):
    cliente = AsyncMock()
    cliente.__aenter__.return_value = cliente
    cliente.search_series = AsyncMock(return_value=valor)
    cliente.search_manga = AsyncMock(return_value=valor)
    return MagicMock(return_value=cliente)


def _roto():
    cliente = AsyncMock()
    cliente.__aenter__.side_effect = RuntimeError("caída")
    return MagicMock(return_value=cliente)


def _ajustes(monkeypatch, **kw):
    base = dict(comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True, gcd_enabled=True,
                comicvine_api_key="clave")
    base.update(kw)
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: MagicMock(**base))


CV = [CVResult(cv_id=1, name="Batman", start_year=2011)]
AL = [AniListResult(anilist_id=2, title_romaji="Naruto")]
TB = [TebeosferaResult(slug="thorgal_1981", title="Thorgal", kind="saga")]
GC = [GCDResult(gcd_id=3, name="Batman", language="en", country="us")]


async def _busca(monkeypatch, cv=None, al=None, tb=None, gc=None, **ajustes):
    _ajustes(monkeypatch, **ajustes)
    with patch("zascarr.services.discovery.ComicVineClient", cv or _ctx(CV)), \
         patch("zascarr.services.discovery.AniListClient", al or _ctx(AL)), \
         patch("zascarr.services.discovery.TebeosferaClient", tb or _ctx(TB)), \
         patch("zascarr.services.discovery.GCDClient", gc or _ctx(GC)):
        return await DiscoveryService(db=MagicMock()).search_detallada("algo")


async def test_todas_ok(monkeypatch):
    b = await _busca(monkeypatch)
    assert b.fuentes == {f.value: FUENTE_OK for f in ORDEN_DE_FUENTES}
    assert len(b.resultados) == 4 and b.avisos == []


async def test_las_cuatro_fuentes_siempre_aparecen_en_el_estado(monkeypatch):
    b = await _busca(monkeypatch, comicvine_enabled=False, anilist_enabled=False,
                     tebeosfera_enabled=False, gcd_enabled=False)
    assert b.fuentes == {f.value: FUENTE_APAGADA for f in ORDEN_DE_FUENTES}
    assert b.resultados == [] and b.avisos == []


async def test_una_fuente_apagada_no_se_consulta_y_las_demas_si(monkeypatch):
    cv = _ctx(CV)
    b = await _busca(monkeypatch, cv=cv, comicvine_enabled=False)
    assert b.fuentes["comic_vine"] == FUENTE_APAGADA
    assert {b.fuentes[k] for k in ("anilist", "tebeosfera", "gcd")} == {FUENTE_OK}
    cv.return_value.search_series.assert_not_called()


async def test_comic_vine_sin_clave_no_se_consulta_y_se_avisa(monkeypatch):
    cv = _ctx(CV)
    b = await _busca(monkeypatch, cv=cv, comicvine_api_key="")
    assert b.fuentes["comic_vine"] == FUENTE_SIN_CLAVE
    cv.return_value.search_series.assert_not_called()
    assert any("Comic Vine" in a and "COMICVINE_API_KEY" in a for a in b.avisos)
    assert b.fuentes["anilist"] == FUENTE_OK and len(b.resultados) == 3


async def test_una_fuente_caida_se_marca_error_y_no_tumba_las_demas(monkeypatch):
    b = await _busca(monkeypatch, tb=_roto())
    assert b.fuentes["tebeosfera"] == FUENTE_ERROR
    assert {b.fuentes[k] for k in ("comic_vine", "anilist", "gcd")} == {FUENTE_OK}
    assert any("Tebeosfera" in a for a in b.avisos) and len(b.resultados) == 3


async def test_comic_vine_sin_clave_no_se_pisa_con_ok(monkeypatch):
    """Sin clave, `search_series` ni se llama; el estado debe seguir siendo `sin_clave` aunque no falle."""
    b = await _busca(monkeypatch, comicvine_api_key="")
    assert b.fuentes["comic_vine"] == FUENTE_SIN_CLAVE != FUENTE_OK


async def test_consulta_vacia_no_busca_y_dice_todo_apagado():
    b = await DiscoveryService(db=MagicMock()).search_detallada("   ")
    assert b.resultados == [] and b.avisos == []
    assert set(b.fuentes.values()) == {FUENTE_APAGADA}


async def test_search_conserva_su_contrato_de_pareja(monkeypatch):
    _ajustes(monkeypatch)
    with patch("zascarr.services.discovery.ComicVineClient", _ctx(CV)), \
         patch("zascarr.services.discovery.AniListClient", _ctx(AL)), \
         patch("zascarr.services.discovery.TebeosferaClient", _ctx(TB)), \
         patch("zascarr.services.discovery.GCDClient", _ctx(GC)):
        r, a = await DiscoveryService(db=MagicMock()).search("algo")
    assert isinstance(r, list) and a == [] and len(r) == 4
