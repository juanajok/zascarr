# ruff: noqa: E501
"""GCD por la cortesía compartida (#134, cierre): cola, redirecciones, 429 y reintentos.

Huecos de evidencia de la matriz (criterio 2, 3 y 4 para GCD): sin red real, con
`httpx.MockTransport` y reloj/dormir simulados.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from zascarr.services.gcd import GCDClient
from zascarr.utils.cortesia import CortesiaProceso
from zascarr.utils.peticiones import ErrorDePeticion, ReintentosAgotados

BASE = "https://www.comics.org/api"
JSON = {"results": [{"api_url": "https://www.comics.org/api/series/42/",
                     "name": "Batman", "year_began": 2011,
                     "language": "es", "country": "es"}]}


class Reloj:
    def __init__(self, inicio: float = 1000.0):
        self.t = inicio
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        await asyncio.sleep(0)
        self.t += segundos


import asyncio  # noqa: E402


@pytest.fixture
def entorno(monkeypatch):
    ajustes = SimpleNamespace(
        comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
        gcd_enabled=True, forum_enabled=False, forum_url="", gcd_rate_limit=2.0,
        comicvine_rate_limit=1.0, anilist_rate_limit=1.5, tebeosfera_rate_limit=2.5,
        forum_rate_limit=2.0)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.gcd.get_settings", lambda: ajustes)
    reloj = Reloj()
    lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
    return SimpleNamespace(reloj=reloj, lim=lim, ajustes=ajustes)


def _cliente(handler, entorno, *, espera_max_s: float = 30.0) -> GCDClient:
    cliente = GCDClient(cortesia=entorno.lim, reloj=entorno.reloj,
                        dormir=entorno.reloj.dormir, espera_max_s=espera_max_s)
    cliente._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                        follow_redirects=False)
    return cliente


async def _cerrar(cliente):
    await cliente._client.aclose()


class TestGCDPorLaCola:

    async def test_dos_clientes_distintos_se_escalonan(self, entorno):
        """Criterio 2: GCD usa la cola de proceso, no una cadencia por instancia."""
        peticiones = []

        def handler(request):
            peticiones.append(str(request.url))
            return httpx.Response(200, json=JSON)

        a = _cliente(handler, entorno)
        b = _cliente(handler, entorno)
        try:
            assert [r.name for r in await a.search_series("batman")] == ["Batman"]
            # Consulta distinta para el segundo cliente: la caché (#523) es por consulta.
            assert [r.name for r in await b.search_series("robin")] == ["Batman"]
        finally:
            await _cerrar(a)
            await _cerrar(b)
        assert entorno.reloj.dormidos == [pytest.approx(2.0)]
        assert not hasattr(a, "_rate_limit") and not hasattr(a, "_last_req")

    async def test_sigue_una_redireccion_del_mismo_origen(self, entorno):
        peticiones = []

        def handler(request):
            peticiones.append(str(request.url))
            if len(peticiones) == 1:
                return httpx.Response(302, headers={"location": "/api/series/name/batman2/"})
            return httpx.Response(200, json=JSON)

        cliente = _cliente(handler, entorno)
        try:
            assert [r.name for r in await cliente.search_series("batman")] == ["Batman"]
        finally:
            await _cerrar(cliente)
        assert len(peticiones) == 2 and peticiones[1].endswith("/api/series/name/batman2/")

    @pytest.mark.parametrize("location", ["https://evil.example/x", "http://[::1/x"])
    async def test_un_destino_prohibido_no_se_pide(self, entorno, location):
        peticiones = []

        def handler(request):
            peticiones.append(str(request.url))
            return httpx.Response(302, headers={"location": location})

        cliente = _cliente(handler, entorno)
        try:
            with pytest.raises(ErrorDePeticion):
                await cliente.search_series("batman")
        finally:
            await _cerrar(cliente)
        assert len(peticiones) == 1

    async def test_el_cliente_se_abre_sin_redirecciones_automaticas(self, entorno):
        async with GCDClient() as cliente:
            assert cliente._client.follow_redirects is False


class TestGCD429YReintentos:

    async def test_429_con_retry_after_se_espera_y_se_reintenta(self, entorno):
        peticiones = []

        def handler(request):
            peticiones.append(str(request.url))
            if len(peticiones) == 1:
                return httpx.Response(429, headers={"retry-after": "5"})
            return httpx.Response(200, json=JSON)

        cliente = _cliente(handler, entorno)
        try:
            assert [r.name for r in await cliente.search_series("batman")] == ["Batman"]
        finally:
            await _cerrar(cliente)
        assert len(peticiones) == 2
        assert entorno.reloj.dormidos == [pytest.approx(5.0)]

    async def test_los_reintentos_se_agotan_con_su_maximo_y_backoff(self, entorno):
        peticiones = []

        def handler(request):
            peticiones.append(str(request.url))
            return httpx.Response(500)

        cliente = _cliente(handler, entorno)
        try:
            with pytest.raises(ReintentosAgotados):
                await cliente.search_series("batman")   # el fallo técnico se propaga
        finally:
            await _cerrar(cliente)
        assert len(peticiones) == 2                                  # política de GCD: 2 intentos
        assert entorno.reloj.dormidos == [pytest.approx(2.0)]        # backoff 2 s
