# ruff: noqa: E501
"""Clientes CV/AniList por la cortesía compartida (#134, PR-1a) y prueba de Ajustes.

Sin red real: `httpx.MockTransport`; la cola usa un reloj simulado. Comprueba que el cliente NO
tiene cadencia propia, que redirige a mano (lee `follow_redirects=False`) y que la prueba de Ajustes
pasa por la cortesía con la excepción explícita de fuente apagada.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

import zascarr.utils.peticiones as peticiones
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.utils.cortesia import CortesiaEnEspera, CortesiaProceso, politica_de
from zascarr.utils.peticiones import RespuestaNoTransitoria


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


class Ajustes:
    comicvine_enabled = True
    comicvine_rate_limit = 1.0
    comicvine_api_key = "clave-prueba"
    anilist_enabled = True
    anilist_rate_limit = 1.5
    tebeosfera_enabled = False
    tebeosfera_rate_limit = 2.5
    gcd_enabled = False
    gcd_rate_limit = 2.0
    forum_enabled = False
    forum_rate_limit = 2.0
    forum_url = ""


@pytest.fixture
def reloj_y_lim(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
    # Los clientes importan `get_settings` en su módulo: se parchea también ahí.
    monkeypatch.setattr("zascarr.services.comic_vine.get_settings", lambda: Ajustes())
    monkeypatch.setattr("zascarr.services.anilist.get_settings", lambda: Ajustes())
    reloj = Reloj()
    lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
    monkeypatch.setattr(peticiones, "cortesia_de_proceso", lambda: lim)
    return reloj, lim


@pytest.fixture
def puente(monkeypatch):
    """Pasa el reloj simulado a la envoltura (el cliente no expone reloj/dormir)."""
    real = peticiones.pedir_con_cortesia

    def _con_reloj(reloj):
        async def _pedir(*args, **kwargs):
            kwargs.setdefault("reloj", reloj)
            kwargs.setdefault("dormir", reloj.dormir)
            return await real(*args, **kwargs)
        return _pedir
    return _con_reloj


def _cliente_cv(handler):
    cliente = ComicVineClient()
    cliente._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                        follow_redirects=False)
    return cliente


def _cliente_anilist(handler):
    cliente = AniListClient()
    cliente._client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                        follow_redirects=False)
    return cliente


async def _cerrar(cliente):
    if cliente._client is not None:
        await cliente._client.aclose()


class TestComicVine:
    async def test_busca_por_la_cola_y_sin_cadencia_propia(self, reloj_y_lim, puente):
        reloj, lim = reloj_y_lim
        peticiones_http = []

        def handler(request: httpx.Request):
            peticiones_http.append(request)
            return httpx.Response(200, json={"error": "OK", "results": [
                {"id": 1, "name": "Batman", "start_year": 2011, "image": {"medium_url": None}},
            ]})

        cliente = _cliente_cv(handler)
        import zascarr.services.comic_vine as cv
        original = cv.pedir_con_cortesia
        cv.pedir_con_cortesia = puente(reloj)
        try:
            resultados = await cliente.search_series("batman", limit=3)
            await cliente.search_series("batman", limit=3)      # segunda: la cola la escala
        finally:
            cv.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert [h.name for h in resultados] == ["Batman"]
        assert len(peticiones_http) == 2
        assert all("api_key=clave-prueba" in str(r.url) for r in peticiones_http)
        assert reloj.dormidos == [pytest.approx(1.0)]
        assert not hasattr(cliente, "_rate_limit") and not hasattr(cliente, "_last_req")

    async def test_sigue_302_a_mano_y_repite_la_clave(self, reloj_y_lim, puente):
        reloj, _ = reloj_y_lim
        peticiones_http = []

        def handler(request: httpx.Request):
            peticiones_http.append(request)
            if len(peticiones_http) == 1:
                return httpx.Response(302, headers={"location": "/api/otra"})
            return httpx.Response(200, json={"error": "OK", "results": []})

        cliente = _cliente_cv(handler)
        import zascarr.services.comic_vine as cv
        original = cv.pedir_con_cortesia
        cv.pedir_con_cortesia = puente(reloj)
        try:
            assert await cliente.search_series("x") == []
        finally:
            cv.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert [str(r.url.path) for r in peticiones_http] == ["/api/search/", "/api/otra"]
        # El salto 302 → GET sin cuerpo: la query la define el `Location` (no se reenvía la clave).
        assert "api_key=clave-prueba" in str(peticiones_http[0].url)
        assert peticiones_http[1].content == b""

    async def test_un_500_se_reintenta_con_backoff(self, reloj_y_lim, puente):
        reloj, _ = reloj_y_lim
        codigos = [500, 200]

        def handler(request: httpx.Request):
            return httpx.Response(codigos.pop(0), json={"error": "OK", "results": []})

        cliente = _cliente_cv(handler)
        import zascarr.services.comic_vine as cv
        original = cv.pedir_con_cortesia
        cv.pedir_con_cortesia = puente(reloj)
        try:
            await cliente.search_series("x")
        finally:
            cv.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert reloj.dormidos == [pytest.approx(2.0)]

    async def test_un_400_no_se_reintenta(self, reloj_y_lim, puente):
        reloj, _ = reloj_y_lim

        def handler(request: httpx.Request):
            return httpx.Response(400, json={})

        cliente = _cliente_cv(handler)
        import zascarr.services.comic_vine as cv
        original = cv.pedir_con_cortesia
        cv.pedir_con_cortesia = puente(reloj)
        try:
            with pytest.raises(RespuestaNoTransitoria):
                await cliente.search_series("x")
        finally:
            cv.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert reloj.dormidos == []

    async def test_el_cliente_se_abre_sin_redirecciones_automaticas(self, monkeypatch):
        monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
        async with ComicVineClient() as cliente:
            assert cliente._client.follow_redirects is False

    async def test_un_error_de_parseo_no_se_reintenta(self, reloj_y_lim, puente):
        """El parseo es del cliente (`r.json()`), no de la envoltura: un 200 ilegible no se reintenta."""
        reloj, _ = reloj_y_lim
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(1)
            return httpx.Response(200, content=b"no es json")

        cliente = _cliente_cv(handler)
        import zascarr.services.comic_vine as cv
        original = cv.pedir_con_cortesia
        cv.pedir_con_cortesia = puente(reloj)
        try:
            with pytest.raises(ValueError):       # json.JSONDecodeError hereda de ValueError
                await cliente.search_series("x")
        finally:
            cv.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert len(peticiones) == 1 and reloj.dormidos == []


class TestAniList:
    async def test_post_por_la_cola_y_307_conserva_cuerpo(self, reloj_y_lim, puente):
        reloj, _ = reloj_y_lim
        peticiones_http = []

        def handler(request: httpx.Request):
            peticiones_http.append(request)
            if len(peticiones_http) == 1:
                return httpx.Response(307, headers={"location": "/graphql"})
            return httpx.Response(200, json={"data": {"Page": {"media": []}}})

        cliente = _cliente_anilist(handler)
        import zascarr.services.anilist as anilist
        original = anilist.pedir_con_cortesia
        anilist.pedir_con_cortesia = puente(reloj)
        try:
            assert await cliente.search_manga("x") == []
        finally:
            anilist.pedir_con_cortesia = original
            await _cerrar(cliente)
        assert [r.method for r in peticiones_http] == ["POST", "POST"]
        assert peticiones_http[0].content == peticiones_http[1].content
        assert str(peticiones_http[0].url) == "https://graphql.anilist.co"
        assert not hasattr(cliente, "_rate_limit") and not hasattr(cliente, "_last_req")

    async def test_los_errores_de_api_se_registran_pero_se_devuelven(self, reloj_y_lim, puente):
        reloj, _ = reloj_y_lim

        def handler(request: httpx.Request):
            return httpx.Response(200, json={"data": {}, "errors": [{"message": "x"}]})

        cliente = _cliente_anilist(handler)
        import zascarr.services.anilist as anilist
        original = anilist.pedir_con_cortesia
        anilist.pedir_con_cortesia = puente(reloj)
        try:
            assert await cliente.search_manga("x") == []
        finally:
            anilist.pedir_con_cortesia = original
            await _cerrar(cliente)

    async def test_el_cliente_se_abre_sin_redirecciones_automaticas(self, monkeypatch):
        monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
        async with AniListClient() as cliente:
            assert cliente._client.follow_redirects is False


class TestPruebaDeAjustes:
    async def test_la_prueba_de_comic_vine_pasa_por_la_cortesia_y_no_reintenta(self, monkeypatch):
        capturado = {}

        async def falsa(cliente, metodo, url, **kwargs):
            capturado.update(kwargs)
            capturado["metodo"] = metodo
            capturado["url"] = url
            return httpx.Response(200, json={"error": "OK"})

        monkeypatch.setattr("zascarr.web.ajustes.pedir_con_cortesia", falsa)
        from zascarr.web.ajustes import _test_comic_vine
        ok, mensaje = await _test_comic_vine("clave")
        assert ok is True and "Conexión correcta" in mensaje
        assert capturado["permitir_apagada"] is True
        assert capturado["espera_max_s"] == 10.0
        assert capturado["politica"].max_intentos == 1
        assert "comicvine.gamespot.com/api/search/" in capturado["url"]

    async def test_si_hay_que_esperar_lo_dice_sin_prometer_recuperacion(self, monkeypatch):
        async def falsa(*_a, **_k):
            raise CortesiaEnEspera("comicvine", "comicvine.gamespot.com", 12.0, "bloqueo_fuente")

        monkeypatch.setattr("zascarr.web.ajustes.pedir_con_cortesia", falsa)
        from zascarr.web.ajustes import _test_comic_vine
        ok, mensaje = await _test_comic_vine("clave")
        assert ok is False
        assert "hay que esperar ~12 s por cortesía" in mensaje
        assert "recuperar" not in mensaje and "volverá" not in mensaje

    async def test_un_http_no_transitorio_conserva_el_codigo(self, monkeypatch):
        async def falsa(*_a, **_k):
            raise RespuestaNoTransitoria(401)

        monkeypatch.setattr("zascarr.web.ajustes.pedir_con_cortesia", falsa)
        from zascarr.web.ajustes import _test_comic_vine
        ok, mensaje = await _test_comic_vine("clave")
        assert ok is False and "HTTP 401" in mensaje

    async def test_un_429_real_en_la_prueba_muestra_la_espera(self, monkeypatch):
        """QA: 429 con `Retry-After: 12` y presupuesto 10 s → espera visible, no «fallo de red»."""
        from zascarr.utils import cortesia as modulo_cortesia
        constructor = httpx.AsyncClient
        monkeypatch.setattr(httpx, "AsyncClient",
                            lambda **kw: constructor(
                                transport=httpx.MockTransport(
                                    lambda r: httpx.Response(429, headers={"retry-after": "12"})),
                                follow_redirects=False))
        modulo_cortesia.reiniciar_para_pruebas()
        try:
            from zascarr.web.ajustes import _test_comic_vine
            ok, mensaje = await _test_comic_vine("clave")
        finally:
            modulo_cortesia.reiniciar_para_pruebas()
        assert ok is False
        assert "hay que esperar ~12 s por cortesía" in mensaje
        assert "No se pudo conectar" not in mensaje
        assert "recuperar" not in mensaje and "volverá" not in mensaje

    async def test_la_prueba_funciona_con_la_fuente_apagada(self, monkeypatch):
        class Apagada(Ajustes):
            comicvine_enabled = False
        monkeypatch.setattr("zascarr.config.get_settings", lambda: Apagada())
        from zascarr.web import ajustes
        llamadas = []

        async def falsa(cliente, metodo, url, **kwargs):
            llamadas.append(kwargs)
            return httpx.Response(200, json={"error": "OK"})
        monkeypatch.setattr(ajustes, "pedir_con_cortesia", falsa)
        ok, _ = await ajustes._test_comic_vine("clave")
        assert ok is True and llamadas and llamadas[0]["permitir_apagada"] is True
