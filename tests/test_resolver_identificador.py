"""BL-R5 (#234): el servicio resuelve por id con estados de #133 (sin red real)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from zascarr.services import discovery
from zascarr.services.comic_vine import CVVolume
from zascarr.services.discovery import (
    FUENTE_APAGADA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_OK,
    DiscoveryService,
)


class _Resultado:
    def __init__(self, valor):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor


class _Sesion:
    def __init__(self, local=None):
        self._local = local

    async def execute(self, *_a, **_k):
        return _Resultado(self._local)


def _ajustes(**extra):
    base = dict(comicvine_enabled=True, comicvine_api_key="k", anilist_enabled=False,
                tebeosfera_enabled=False, gcd_enabled=False)
    return SimpleNamespace(**{**base, **extra})


def _volumen(cv_id=12345):
    return CVVolume(cv_id=cv_id, name="Superman", start_year=1987,
                    raw={"description": "<p>Una serie.</p>",
                         "image": {"medium_url": "https://cdn.example/portada.jpg"},
                         "site_detail_url": "https://comicvine.gamespot.com/volume/4050-12345/"})


def _servicio(monkeypatch, *, local=None, cliente=None, ajustes=None):
    monkeypatch.setattr(discovery, "get_settings", lambda: ajustes or _ajustes())
    if cliente is not None:
        monkeypatch.setattr(discovery, "ComicVineClient", lambda: cliente)
    return DiscoveryService(_Sesion(local))


@pytest.mark.asyncio
async def test_resuelve_un_volumen_de_comic_vine_por_id(monkeypatch):
    llamadas = []

    class _Cliente:
        async def get_volume(self, volume_id):
            llamadas.append(volume_id)
            return _volumen()

    servicio = _servicio(monkeypatch, cliente=_Cliente())
    r = await servicio.resolver_identificador("cv:12345")
    assert r.camino == "identificador" and llamadas == [12345]
    assert r.resultado.title == "Superman" and r.resultado.start_year == 1987
    assert r.resultado.cover_url == "https://cdn.example/portada.jpg"
    assert r.resultado.site_url == "https://comicvine.gamespot.com/volume/4050-12345/"
    assert r.estado.estado == FUENTE_OK


@pytest.mark.asyncio
async def test_una_fuente_apagada_no_consulta(monkeypatch):
    llamadas = []

    class _Cliente:
        async def get_volume(self, volume_id):
            llamadas.append(volume_id)
            return _volumen()

    servicio = _servicio(monkeypatch, cliente=_Cliente(),
                        ajustes=_ajustes(comicvine_enabled=False))
    r = await servicio.resolver_identificador("cv:12345")
    assert llamadas == []
    assert r.camino == "error" and r.estado.estado == FUENTE_APAGADA


@pytest.mark.asyncio
async def test_un_fallo_de_la_fuente_no_dice_que_no_existe(monkeypatch):
    class _Cliente:
        async def get_volume(self, volume_id):
            raise RuntimeError("caída")

    servicio = _servicio(monkeypatch, cliente=_Cliente())
    r = await servicio.resolver_identificador("cv:12345")
    assert r.camino == "error" and r.estado.estado == FUENTE_FALLO_TRANSITORIO
    assert "no existe" not in (r.motivo or "").lower()


@pytest.mark.asyncio
async def test_si_la_serie_ya_esta_local_no_consulta_la_fuente(monkeypatch):
    llamadas = []

    class _Cliente:
        async def get_volume(self, volume_id):
            llamadas.append(volume_id)
            return _volumen()

    local = SimpleNamespace(id="local-id", title="Superman")
    servicio = _servicio(monkeypatch, local=local, cliente=_Cliente())
    r = await servicio.resolver_identificador("cv:12345")
    assert r.camino == "ya_local" and r.ya_local is local
    assert llamadas == []


@pytest.mark.asyncio
async def test_anilist_no_soporta_resolucion_por_id(monkeypatch):
    servicio = _servicio(monkeypatch, ajustes=_ajustes(anilist_enabled=True))
    r = await servicio.resolver_identificador("al:99")
    assert r.camino == "error" and r.estado.estado == "sin_metodo_autorizado"
    assert "búscala por título" in r.motivo
