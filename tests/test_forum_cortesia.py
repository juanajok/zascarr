# ruff: noqa: E501
"""Foro por la cortesía compartida (#134, cierre): cola, redirecciones, 429 y espera visible.

Huecos de evidencia de la matriz (criterios 2, 3, 4 y 5 para el foro). Sin red real: transporte
simulado y reloj/dormir inyectables. La espera por cortesía NO se convierte en «sin resultados».
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import structlog

from zascarr.services import orchestrator as modulo_orchestrator
from zascarr.services.forum_scraper import ForumScraper, OrigenNoPermitidoError
from zascarr.utils.cortesia import CortesiaEnEspera, CortesiaProceso
from zascarr.utils.peticiones import ReintentosAgotados

BASE = "https://foro.example"
HTML = "<html><a href='/index.php?showtopic=1'>Tema</a></html>"


@pytest.fixture(autouse=True)
def _foro_encendido(monkeypatch):
    ajustes = SimpleNamespace(
        forum_enabled=True, forum_url=BASE, forum_rate_limit=2.0,
        forum_username="usuario", forum_password="clave",
        comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
        gcd_enabled=False, comicvine_rate_limit=1.0, anilist_rate_limit=1.5,
        tebeosfera_rate_limit=2.5, gcd_rate_limit=2.0)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
    monkeypatch.setattr(modulo_orchestrator, "get_settings", lambda: ajustes)


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


class Mundo:
    def __init__(self, handler):
        self.reloj = Reloj()
        self.lim = CortesiaProceso(reloj=self.reloj, dormir=self.reloj.dormir)
        self.peticiones: list[httpx.Request] = []
        self._handler = handler

    def cliente(self) -> httpx.AsyncClient:
        def _h(request: httpx.Request) -> httpx.Response:
            self.peticiones.append(request)
            return self._handler(request)
        return httpx.AsyncClient(transport=httpx.MockTransport(_h), follow_redirects=False)

    def scraper(self, *, rate_limit: float = 2.0, espera_max_s: float = 30.0) -> ForumScraper:
        return ForumScraper(BASE, rate_limit=rate_limit, crear_cliente=self.cliente,
                            cortesia=self.lim, reloj=self.reloj,
                            dormir=self.reloj.dormir, espera_max_s=espera_max_s)


class TestForoPorLaCola:

    async def test_dos_instancias_se_escalonan(self):
        """Criterio 2: el foro comparte la cola del proceso (2,0 s), no una por instancia."""
        mundo = Mundo(lambda r: httpx.Response(200, text=HTML))
        a, b = mundo.scraper(), mundo.scraper()
        assert await a._get(f"{BASE}/index.php?showtopic=1") == HTML
        assert await b._get(f"{BASE}/index.php?showtopic=2") == HTML
        assert mundo.reloj.dormidos == [pytest.approx(2.0)]

    @pytest.mark.parametrize("location,motivo", [
        ("https://evil.example/x", "otro_origen"),
        ("http://[::1/x", "url_mal_formada"),
        ("https://foro.example:8443/x", "otro_origen"),
    ])
    async def test_una_redireccion_prohibida_no_se_pide(self, location, motivo):
        mundo = Mundo(lambda r: httpx.Response(302, headers={"location": location}))
        with pytest.raises(OrigenNoPermitidoError) as exc:
            await mundo.scraper()._get(f"{BASE}/index.php")
        assert motivo in str(exc.value)
        assert len(mundo.peticiones) == 1

    async def test_429_con_retry_after_se_espera_y_se_reintenta(self):
        codigos = iter([httpx.Response(429, headers={"retry-after": "5"}),
                        httpx.Response(200, text=HTML)])
        mundo = Mundo(lambda r: next(codigos))
        assert await mundo.scraper()._get(f"{BASE}/index.php") == HTML
        assert len(mundo.peticiones) == 2
        assert mundo.reloj.dormidos == [pytest.approx(5.0)]

    async def test_los_reintentos_se_agotan_con_su_maximo_y_backoff(self):
        mundo = Mundo(lambda r: httpx.Response(500))
        with pytest.raises(ReintentosAgotados):
            await mundo.scraper()._get(f"{BASE}/index.php")
        assert len(mundo.peticiones) == 2                         # política del foro: 2 intentos
        assert mundo.reloj.dormidos == [pytest.approx(2.0)]


class TestForoSinTurno:

    async def test_un_bloqueo_mayor_que_el_presupuesto_no_devuelve_lista_vacia(self):
        """AC-16: la espera no es «sin resultados» y no se registra como fallo."""
        mundo = Mundo(lambda r: httpx.Response(200, text=HTML))
        mundo.lim.bloquear("foro", f"{BASE}:443", 60.0, motivo="429")
        with structlog.testing.capture_logs() as registros, \
                pytest.raises(CortesiaEnEspera) as exc:
            await mundo.scraper(espera_max_s=5.0).use_ipb_search("thorgal")
        assert exc.value.fuente == "foro" and exc.value.motivo == "bloqueo_fuente"
        assert exc.value.espera_estimada_s >= 5.0
        assert mundo.peticiones == []
        assert not any(r["event"] == "forum.search_failed" for r in registros)

    async def test_el_orchestrator_omite_el_ciclo_sin_registrar_fallo(self, monkeypatch):
        from zascarr.services import forum_scraper as modulo_foro

        class ForoQueEspera:
            def __init__(self, **_kw):
                pass

            async def login(self, *_a, **_k):
                raise CortesiaEnEspera("foro", f"{BASE}:443", 60.0, "bloqueo_fuente")

            async def use_ipb_search(self, *_a, **_k):   # pragma: no cover - no llega
                raise AssertionError("no se llama si el login ya esperó")

        monkeypatch.setattr(modulo_foro, "ForumScraper", ForoQueEspera)
        with structlog.testing.capture_logs() as registros:
            resultado = await modulo_orchestrator.Orchestrator(
                db=MagicMock())._forum_fallback("thorgal")
        assert resultado is None
        eventos = [r["event"] for r in registros]
        assert "orchestrator.forum_fallback_error" not in eventos
        assert "orchestrator.forum_sin_turno" in eventos
