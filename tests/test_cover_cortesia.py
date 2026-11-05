# ruff: noqa: E501
"""Portadas externas por la cortesía compartida (#134, PR-1b; AC-12/AC-13).

Sin red real: transporte y resolución simulados, reloj/dormir inyectables. La política de SSRF de
`url_portada` sigue aplicándose en CADA salto; la cortesía es **por host** (nivel host solo) y el
intervalo sale del mapa allowlist→fuente. Un fallo de cortesía no se reintenta ni cachea la ausencia.
"""
from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from zascarr.utils import cover as modulo_cover
from zascarr.utils import url_portada
from zascarr.utils.cortesia import CortesiaEnEspera, CortesiaProceso
from zascarr.utils.cover import fetch_and_cache_cover
from zascarr.utils.url_portada import UrlNoPermitidaError, descargar_imagen

@pytest.fixture(autouse=True)
def _fuentes_encendidas(monkeypatch):
    """Una fuente apagada no recibe portadas (AC-15); el caso apagado tiene su propia prueba."""
    monkeypatch.setattr("zascarr.utils.cover.get_settings", lambda: SimpleNamespace(
        comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True,
        gcd_enabled=True, forum_enabled=False, forum_url=""))


URL_CV = "https://comicvine.gamespot.com/a/uploads/cover.jpg"
URL_CDN = "https://cdn.cbsistatic.com/a/uploads/cover.jpg"


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


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (80, 120), color=(120, 40, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _mundo(handler):
    reloj = Reloj()
    lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
    peticiones: list[str] = []
    resoluciones: list[str] = []

    def _h(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        return handler(request)

    def crear_cliente():
        return httpx.AsyncClient(transport=httpx.MockTransport(_h), follow_redirects=False)

    async def resolutor(host, puerto):
        resoluciones.append(host)
        return ["93.184.216.34"]

    return SimpleNamespace(reloj=reloj, lim=lim, crear_cliente=crear_cliente,
                           resolutor=resolutor, peticiones=peticiones,
                           resoluciones=resoluciones)


async def _descargar(mundo, url=URL_CV, **kw):
    kw.setdefault("cortesia", mundo.lim)
    kw.setdefault("reloj", mundo.reloj)
    kw.setdefault("dormir", mundo.reloj.dormir)
    return await descargar_imagen(url, resolutor=mundo.resolutor,
                                  crear_cliente=mundo.crear_cliente, **kw)


class TestCadaSaltoPorLaColaDelHost:
    async def test_cada_salto_espera_y_consume_el_hueco_del_host(self):
        def handler(request: httpx.Request):
            if len(mundo.peticiones) == 1:
                return httpx.Response(302, headers={"location": "/a/uploads/otra.jpg"})
            if len(mundo.peticiones) == 2:
                return httpx.Response(302, headers={"location": URL_CDN})
            return httpx.Response(200, content=_jpeg())
        mundo = _mundo(handler)
        assert await _descargar(mundo) == _jpeg()
        assert len(mundo.peticiones) == 3
        # El primer salto no espera; el segundo (MISMO host, 1,0 s) sí. El tercero es otro host
        # (CDN), así que su cola es independiente y no añade espera.
        assert mundo.reloj.dormidos == [pytest.approx(1.0)]

    async def test_el_cuarto_salto_falla_sin_enviarlo(self):
        mundo = _mundo(lambda r: httpx.Response(302, headers={"location": "/x"}))
        with pytest.raises(UrlNoPermitidaError) as exc:
            await _descargar(mundo)
        assert "demasiadas_redirecciones" in str(exc.value)
        assert len(mundo.peticiones) == url_portada.MAX_SALTOS + 1

    async def test_un_429_no_se_reintenta(self):
        mundo = _mundo(lambda r: httpx.Response(429))
        with pytest.raises(httpx.HTTPStatusError):
            await _descargar(mundo)
        assert len(mundo.peticiones) == 1 and mundo.reloj.dormidos == []

    async def test_hosts_distintos_no_se_bloquean_y_el_mismo_si(self):
        mundo = _mundo(lambda r: httpx.Response(200, content=_jpeg()))
        await _descargar(mundo, URL_CV)
        await _descargar(mundo, "https://s4.anilist.co/file/cover.jpg")   # otro host: no espera
        await _descargar(mundo, URL_CV)                                    # mismo host: 1,0 s
        assert mundo.reloj.dormidos == [pytest.approx(1.0)]

    async def test_un_bloqueo_mayor_que_el_presupuesto_no_envia(self):
        mundo = _mundo(lambda r: httpx.Response(200, content=_jpeg()))
        mundo.lim.bloquear("portada", "https://comicvine.gamespot.com:443", 10, motivo="429")
        with pytest.raises(CortesiaEnEspera) as exc:
            await _descargar(mundo)
        assert exc.value.espera_estimada_s == pytest.approx(10.0)
        assert mundo.peticiones == [] and mundo.resoluciones == []


class TestCoverFetch:
    async def test_la_fuente_apagada_no_recibe_portadas(self, tmp_path, monkeypatch):
        monkeypatch.setattr("zascarr.utils.cover.get_settings", lambda: SimpleNamespace(
            comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
            gcd_enabled=False, forum_enabled=False, forum_url=""))
        mundo = _mundo(lambda r: httpx.Response(200, content=_jpeg()))
        dest = tmp_path / "cover.jpg"
        ok = await fetch_and_cache_cover(
            URL_CV, dest, cortesia=mundo.lim, reloj=mundo.reloj,
            dormir=mundo.reloj.dormir)
        assert ok is False and mundo.peticiones == [] and not dest.exists()

    async def test_la_espera_mayor_que_el_presupuesto_deja_marcador_sin_cachear(self, tmp_path):
        mundo = _mundo(lambda r: httpx.Response(200, content=_jpeg()))
        mundo.lim.bloquear("portada", "https://comicvine.gamespot.com:443", 10, motivo="429")
        dest = tmp_path / "cover.jpg"
        ok = await fetch_and_cache_cover(
            URL_CV, dest, cortesia=mundo.lim, reloj=mundo.reloj,
            dormir=mundo.reloj.dormir)
        assert ok is False and mundo.peticiones == [] and not dest.exists()

    async def test_la_espera_y_la_peticion_van_en_el_bucle_y_el_trabajo_local_en_un_hilo(
            self, tmp_path, monkeypatch):
        """AC-13: el limitador no se llama desde el hilo; el resize sí sigue en `to_thread`."""
        mundo = _mundo(lambda r: httpx.Response(200, content=_jpeg()))
        hilo_espera: list[threading.Thread] = []
        hilo_resize: list[threading.Thread] = []
        esperar_real = mundo.lim.esperar

        async def esperar_vigilado(*a, **k):
            hilo_espera.append(threading.current_thread())
            return await esperar_real(*a, **k)

        monkeypatch.setattr(mundo.lim, "esperar", esperar_vigilado)
        resize_real = modulo_cover._resize_and_save

        def resize_vigilado(*a, **k):
            hilo_resize.append(threading.current_thread())
            return resize_real(*a, **k)

        monkeypatch.setattr(modulo_cover, "_resize_and_save", resize_vigilado)
        dest = tmp_path / "cover.jpg"
        assert await fetch_and_cache_cover(
            URL_CV, dest, cortesia=mundo.lim, reloj=mundo.reloj,
            dormir=mundo.reloj.dormir, resolutor=mundo.resolutor,
            crear_cliente=mundo.crear_cliente) is True
        assert dest.exists()
        assert hilo_espera and hilo_espera[0] is threading.main_thread()
        assert hilo_resize and hilo_resize[0] is not threading.main_thread()
