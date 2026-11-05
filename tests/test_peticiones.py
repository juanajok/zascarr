# ruff: noqa: E501
"""`utils/peticiones.py`: redirecciones, reintentos, presupuesto y fuente apagada (#134, 1a).

Sin red real: `httpx.MockTransport` registra cada petición y el reloj/la espera son simulados.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from zascarr.utils.cortesia import CortesiaEnEspera, CortesiaProceso, politica_de
from zascarr.utils.peticiones import (
    DemasiadasRedirecciones,
    FuenteApagada,
    RedireccionNoPermitida,
    ReintentosAgotados,
    RespuestaNoTransitoria,
    pedir_con_cortesia,
    retry_after_s,
)


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
    comicvine_api_key = "clave"
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
def ajustes_habilitados(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: Ajustes())
    return Ajustes()


def _politica(**kw):
    base = dict(fuente="comicvine", nombre="Comic Vine", intervalo_min_s=0.0,
                max_intentos=3, max_redirecciones=3)
    base.update(kw)
    from zascarr.utils.cortesia import PoliticaFuente
    return PoliticaFuente(**base)


def _mundo(handler):
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    reloj = Reloj()
    lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
    return cliente, reloj, lim


async def _pedir(cliente, reloj, lim, *, politica=None, url="https://comicvine.gamespot.com/api/",
                 metodo="GET", datos=None, espera_max_s=30.0, hosts_redireccion=None,
                 permitir_apagada=False, cabeceras=None):
    return await pedir_con_cortesia(
        cliente, metodo, url, politica=politica or _politica(), espera_max_s=espera_max_s,
        hosts_redireccion=hosts_redireccion, datos=datos, cabeceras=cabeceras,
        permitir_apagada=permitir_apagada, cortesia=lim, reloj=reloj, dormir=reloj.dormir)


class TestRedirecciones:
    async def test_302_a_get_sin_cuerpo_y_cada_salto_cuenta_en_el_presupuesto(self, ajustes_habilitados):
        peticiones: list[tuple[str, str, bytes]] = []

        def handler(request: httpx.Request):
            peticiones.append((request.method, str(request.url), request.content))
            if len(peticiones) == 1:
                return httpx.Response(302, headers={"location": "/api/siguiente"})
            if len(peticiones) == 2:
                return httpx.Response(303, headers={"location": "/api/final"})
            return httpx.Response(200, json={"ok": True})

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            r = await _pedir(cliente, reloj, lim, metodo="POST", datos={"consulta": "x"},
                             espera_max_s=10.0, politica=_politica(intervalo_min_s=1.0))
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert [(m, u.split("?")[0]) for m, u, _ in peticiones] == [
            ("POST", "https://comicvine.gamespot.com/api/"),
            ("GET", "https://comicvine.gamespot.com/api/siguiente"),
            ("GET", "https://comicvine.gamespot.com/api/final"),
        ]
        assert peticiones[1][2] == b"" and peticiones[2][2] == b""
        # Cada salto se escalona por el nivel host/fuente (1,0 s) con el reloj simulado.
        assert reloj.dormidos[:2] == [pytest.approx(1.0), pytest.approx(1.0)]

    async def test_301_desde_post_pasa_a_get_sin_cuerpo(self, ajustes_habilitados):
        peticiones: list[tuple[str, bytes]] = []

        def handler(request: httpx.Request):
            peticiones.append((request.method, request.content))
            if len(peticiones) == 1:
                return httpx.Response(301, headers={"location": "/api/nuevo"})
            return httpx.Response(200, json={})
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            assert (await _pedir(cliente, reloj, lim, metodo="POST",
                                 datos={"q": "x"})).status_code == 200
        assert peticiones[0][0] == "POST" and peticiones[1][0] == "GET"
        assert peticiones[1][1] == b""

    @pytest.mark.parametrize("codigo", [307, 308])
    async def test_307_y_308_conservan_metodo_y_cuerpo(self, ajustes_habilitados, codigo):
        peticiones: list[tuple[str, bytes]] = []

        def handler(request: httpx.Request):
            peticiones.append((request.method, request.content))
            if len(peticiones) == 1:
                return httpx.Response(codigo, headers={"location": "/api/siguiente"})
            return httpx.Response(200, json={})

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            r = await _pedir(cliente, reloj, lim, metodo="POST", datos={"q": "valor"})
        assert r.status_code == 200
        assert peticiones[0][0] == "POST" and peticiones[1][0] == "POST"
        assert b'"q"' in peticiones[0][1] and peticiones[1][1] == peticiones[0][1]

    @pytest.mark.parametrize("salto", [1, 2, 3])
    async def test_cadenas_de_uno_a_tres_saltos(self, ajustes_habilitados, salto):
        peticiones = []
        restantes = {"n": salto}

        def handler(request: httpx.Request):
            peticiones.append(str(request.url))
            if restantes["n"]:
                restantes["n"] -= 1
                return httpx.Response(301, headers={"location": f"/paso{len(peticiones)}"})
            return httpx.Response(200, json={})
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            assert (await _pedir(cliente, reloj, lim)).status_code == 200
        assert len(peticiones) == salto + 1

    async def test_el_cuarto_salto_falla_sin_enviarlo(self, ajustes_habilitados):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(str(request.url))
            return httpx.Response(302, headers={"location": "/siempre"})
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            with pytest.raises(DemasiadasRedirecciones):
                await _pedir(cliente, reloj, lim)
        assert len(peticiones) == 4, peticiones

    async def test_un_bucle_se_corta_por_el_tope(self, ajustes_habilitados):
        with pytest.raises(DemasiadasRedirecciones):
            cliente, reloj, lim = _mundo(lambda r: httpx.Response(302, headers={"location": str(r.url)}))
            async with cliente:
                await _pedir(cliente, reloj, lim)

    @pytest.mark.parametrize("location,motivo", [
        (None, "location_ausente"),
        ("file:///etc/passwd", "location_invalida"),
        ("https://user:clave@comicvine.gamespot.com/x", "location_con_credenciales"),
        ("https://otro.example/x", "otro_origen"),
        ("http://comicvine.gamespot.com/x", "otro_origen"),
    ])
    async def test_destino_prohibido_falla_antes_de_pedirlo(self, ajustes_habilitados, location, motivo):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(str(request.url))
            return httpx.Response(302, headers={"location": location} if location else {})
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            with pytest.raises(RedireccionNoPermitida) as exc:
                await _pedir(cliente, reloj, lim)
        assert exc.value.motivo == motivo and len(peticiones) == 1
        assert "https://" not in str(exc.value) and "?" not in str(exc.value)

    async def test_la_allowlist_explicita_permite_otro_host(self, ajustes_habilitados):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(str(request.url))
            if len(peticiones) == 1:
                return httpx.Response(302, headers={"location": "https://cdn.example/img.jpg"})
            return httpx.Response(200)
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            r = await _pedir(cliente, reloj, lim,
                             hosts_redireccion=lambda origen: origen.startswith("https://cdn.example:"))
        assert r.status_code == 200 and len(peticiones) == 2


class TestReintentos:
    @pytest.mark.parametrize("codigo", [408, 500, 503])
    async def test_los_transitorios_reintentan_hasta_el_maximo_con_backoff(self, ajustes_habilitados, codigo):
        peticiones = []
        cliente, reloj, lim = _mundo(lambda r: peticiones.append(1) or httpx.Response(codigo))
        async with cliente:
            with pytest.raises(ReintentosAgotados) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=60.0)
        assert exc.value.intentos == 3 and exc.value.ultimo_codigo == codigo
        assert len(peticiones) == 3 and reloj.dormidos == [pytest.approx(2.0), pytest.approx(4.0)]

    async def test_un_timeout_reintenta_y_luego_se_agota(self, ajustes_habilitados):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(1)
            raise httpx.ReadTimeout("timeout")
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            with pytest.raises(ReintentosAgotados) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=60.0,
                             politica=_politica(max_intentos=2))
        assert exc.value.intentos == 2 and exc.value.ultimo_codigo is None
        assert len(peticiones) == 2 and reloj.dormidos == [pytest.approx(2.0)]

    async def test_un_error_de_red_reintenta_y_luego_da_la_respuesta(self, ajustes_habilitados):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(1)
            if len(peticiones) == 1:
                raise httpx.ConnectError("sin red")
            return httpx.Response(200, json={"ok": True})
        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            assert (await _pedir(cliente, reloj, lim)).status_code == 200
        assert reloj.dormidos == [pytest.approx(2.0)]

    @pytest.mark.parametrize("codigo", [400, 401, 404])
    async def test_los_4xx_no_transitorios_no_se_reintentan(self, ajustes_habilitados, codigo):
        peticiones = []
        cliente, reloj, lim = _mundo(lambda r: peticiones.append(1) or httpx.Response(codigo))
        async with cliente:
            with pytest.raises(RespuestaNoTransitoria) as exc:
                await _pedir(cliente, reloj, lim)
        assert exc.value.codigo == codigo and len(peticiones) == 1 and reloj.dormidos == []

    async def test_el_backoff_no_se_acelera_tras_una_espera_larga(self, ajustes_habilitados):
        respuestas = iter([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
        cliente, reloj, lim = _mundo(lambda r: next(respuestas))
        async with cliente:
            await _pedir(cliente, reloj, lim, espera_max_s=60.0)
        assert reloj.dormidos == [pytest.approx(2.0), pytest.approx(4.0)]

    async def test_un_backoff_que_no_cabe_en_el_presupuesto_es_espera_visible(self, ajustes_habilitados):
        peticiones = []
        cliente, reloj, lim = _mundo(lambda r: peticiones.append(1) or httpx.Response(500))
        async with cliente:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=1.0)
        assert exc.value.motivo == "reintento" and len(peticiones) == 1 and reloj.dormidos == []


class TestRetryAfter:
    async def test_429_comparte_el_bloqueo_de_fuente_y_host(self, ajustes_habilitados):
        peticiones = []
        cliente, reloj, lim = _mundo(
            lambda r: peticiones.append(1) or httpx.Response(429, headers={"retry-after": "7"}))
        async with cliente:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=5.0)
        assert exc.value.motivo == "bloqueo_fuente"
        assert exc.value.espera_estimada_s == pytest.approx(7.0)
        assert len(peticiones) == 1 and reloj.dormidos == []
        snapshot = lim.snapshot(Ajustes())
        comicvine = next(f for f in snapshot["fuentes"] if f["fuente"] == "comicvine")
        assert comicvine["bloqueada_hasta_s"] == pytest.approx(7.0)
        assert snapshot["hosts"][0]["bloqueada_hasta_s"] == pytest.approx(7.0)

    async def test_el_segundo_consumidor_no_se_salta_el_bloqueo(self, ajustes_habilitados):
        peticiones = []
        reloj = Reloj()
        lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
        primera = _mundo(lambda r: peticiones.append(1) or httpx.Response(429, headers={"retry-after": "7"}))
        cliente_a = primera[0]

        def handler_b(request: httpx.Request):
            peticiones.append(2)
            return httpx.Response(200, json={})

        cliente_b = httpx.AsyncClient(transport=httpx.MockTransport(handler_b), follow_redirects=False)
        async with cliente_a, cliente_b:
            with pytest.raises(CortesiaEnEspera):
                await _pedir(cliente_a, reloj, lim, espera_max_s=5.0)
            # El segundo cliente de la MISMA fuente espera el bloqueo (7 s) y no se salta la cola.
            await _pedir(cliente_b, reloj, lim, espera_max_s=10.0)
        assert reloj.dormidos == [pytest.approx(7.0)]
        assert lim.snapshot(Ajustes())["fuentes"][0]["bloqueada_hasta_s"] is None

    async def test_retry_after_como_fecha_http_se_comparte_entre_dos_consumidores(self, ajustes_habilitados):
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        reloj = Reloj()
        lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
        futura = format_datetime(datetime.now(UTC) + timedelta(seconds=12))
        cliente_a = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(429, headers={"retry-after": futura})),
            follow_redirects=False)
        cliente_b = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
            follow_redirects=False)
        async with cliente_a, cliente_b:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente_a, reloj, lim, espera_max_s=5.0)
            assert 10.0 <= exc.value.espera_estimada_s <= 13.0
            assert exc.value.motivo == "bloqueo_fuente"
            await _pedir(cliente_b, reloj, lim, espera_max_s=30.0)
        assert len(reloj.dormidos) == 1 and 10.0 <= reloj.dormidos[0] <= 13.0

    async def test_un_retry_after_invalido_cae_al_backoff(self, ajustes_habilitados):
        peticiones = []
        cliente, reloj, lim = _mundo(
            lambda r: peticiones.append(1) or httpx.Response(429, headers={"retry-after": "basura"}))
        async with cliente:
            with pytest.raises(ReintentosAgotados):
                await _pedir(cliente, reloj, lim, espera_max_s=60.0)
        assert len(peticiones) == 3 and reloj.dormidos == [pytest.approx(2.0), pytest.approx(4.0)]

    def test_retry_after_admite_segundos_y_fecha_http(self):
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime
        futura = format_datetime(datetime.now(UTC) + timedelta(seconds=12))
        pasada = format_datetime(datetime.now(UTC) - timedelta(seconds=12))
        assert retry_after_s("12") == 12.0
        assert 10.0 <= retry_after_s(futura) <= 13.0
        assert retry_after_s(pasada) is None
        assert retry_after_s("0") is None and retry_after_s("-2") is None
        assert retry_after_s("no vale") is None and retry_after_s(None) is None
        assert retry_after_s("999999") == 3600.0


class TestFuenteApagada:
    async def test_no_se_reserva_ni_envia(self, monkeypatch):
        class Apagada(Ajustes):
            comicvine_enabled = False
        monkeypatch.setattr("zascarr.config.get_settings", lambda: Apagada())
        peticiones = []
        cliente, reloj, lim = _mundo(lambda r: peticiones.append(1) or httpx.Response(200))
        async with cliente:
            with pytest.raises(FuenteApagada):
                await _pedir(cliente, reloj, lim)
        assert peticiones == [] and lim.snapshot(Apaga).fuentes if False else peticiones == []

    async def test_la_prueba_de_ajustes_es_la_excepcion_explicita(self, monkeypatch):
        class Apagada(Ajustes):
            comicvine_enabled = False
        monkeypatch.setattr("zascarr.config.get_settings", lambda: Apagada())
        cliente, reloj, lim = _mundo(lambda r: httpx.Response(200, json={"error": "OK"}))
        async with cliente:
            r = await _pedir(cliente, reloj, lim, permitir_apagada=True)
        assert r.status_code == 200


class TestPresupuestoDelLlamador:
    async def test_la_espera_de_la_cola_no_cabe_en_el_presupuesto_y_no_envia(self, ajustes_habilitados):
        peticiones = []
        reloj = Reloj()
        lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
        lim.bloquear("comicvine", "comicvine.gamespot.com", 60, motivo="429")
        cliente = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: peticiones.append(1) or httpx.Response(200)), follow_redirects=False)
        async with cliente:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=10.0)
        assert exc.value.espera_estimada_s == pytest.approx(60.0) and peticiones == []

    async def test_dos_clientes_de_la_misma_fuente_comparten_la_cola(self, ajustes_habilitados):
        reloj = Reloj()
        lim = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
        cliente_a = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)),
                                      follow_redirects=False)
        cliente_b = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)),
                                      follow_redirects=False)
        async with cliente_a, cliente_b:
            await _pedir(cliente_a, reloj, lim, politica=_politica(intervalo_min_s=1.0))
            await _pedir(cliente_b, reloj, lim, politica=_politica(intervalo_min_s=1.0))
        assert reloj.dormidos == [pytest.approx(1.0)]


class TestLocalizacionesInvalidas:
    """C1 (Seguridad): un `Location` malformado es fallo de redirección, NUNCA un reintento de red."""

    @pytest.mark.parametrize("location", [
        "https://cdn.example:bad/x",       # puerto no numérico
        "http://[::1/x",                    # IPv6 sin cerrar
        "https://[::1]:bad/x",              # IPv6 con puerto no numérico
    ])
    async def test_un_location_malformado_no_se_reintenta(self, ajustes_habilitados, location):
        peticiones = []
        cliente, reloj, lim = _mundo(
            lambda r: peticiones.append(str(r.url)) or
            httpx.Response(302, headers={"location": location}))
        async with cliente:
            with pytest.raises(RedireccionNoPermitida) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=60.0)
        assert exc.value.motivo == "location_invalida"
        assert len(peticiones) == 1 and reloj.dormidos == []

    async def test_un_error_de_protocolo_no_se_reintenta(self, ajustes_habilitados):
        peticiones = []

        def handler(request: httpx.Request):
            peticiones.append(1)
            raise httpx.RemoteProtocolError("respuesta malformada")

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            with pytest.raises(RedireccionNoPermitida) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=60.0)
        assert exc.value.motivo == "location_invalida"
        assert len(peticiones) == 1 and reloj.dormidos == []


class TestCredencialesEntreOrigenes:
    """C2 (Seguridad): al cambiar de origen no se reenvían cabeceras sensibles ni datos."""

    SENSIBLES = {"authorization", "x-api-key", "cookie", "proxy-authorization"}

    async def test_302_a_otro_origen_sin_credenciales(self, ajustes_habilitados):
        registros: list[httpx.Request] = []

        def handler(request: httpx.Request):
            registros.append(request)
            if len(registros) == 1:
                return httpx.Response(302, headers={"location": "https://cdn.example/x"})
            return httpx.Response(200, json={})

        cliente, reloj, lim = _mundo(handler)
        cabeceras = {"Authorization": "Bearer secreta", "X-Api-Key": "clave",
                     "Cookie": "sesion=1", "Proxy-Authorization": "Basic x", "X-Otra": "vale"}
        async with cliente:
            await _pedir(cliente, reloj, lim, datos={"api_key": "clave"},
                         cabeceras=cabeceras,
                         hosts_redireccion=lambda origen: origen.startswith("https://cdn.example:"))
        segunda = registros[1]
        assert not (set(h.lower() for h in segunda.headers) & self.SENSIBLES)
        assert segunda.headers.get("x-otra") == "vale"
        assert "api_key" not in str(segunda.url) and segunda.method == "GET"

    async def test_307_a_otro_origen_conserva_metodo_pero_no_cuerpo_ni_credenciales(self, ajustes_habilitados):
        registros: list[httpx.Request] = []

        def handler(request: httpx.Request):
            registros.append(request)
            if len(registros) == 1:
                return httpx.Response(307, headers={"location": "https://cdn.example/x"})
            return httpx.Response(200, json={})

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            await _pedir(cliente, reloj, lim, metodo="POST",
                         datos={"q": "x", "api_key": "clave"},
                         cabeceras={"Authorization": "Bearer secreta", "X-Otra": "vale"},
                         hosts_redireccion=lambda origen: origen.startswith("https://cdn.example:"))
        segunda = registros[1]
        assert segunda.method == "POST" and segunda.content == b""
        assert "authorization" not in {h.lower() for h in segunda.headers}
        assert segunda.headers.get("x-otra") == "vale"

    async def test_mismo_origen_307_si_conserva_cuerpo_y_credenciales(self, ajustes_habilitados):
        registros: list[httpx.Request] = []

        def handler(request: httpx.Request):
            registros.append(request)
            if len(registros) == 1:
                return httpx.Response(307, headers={"location": "/api/siguiente"})
            return httpx.Response(200, json={})

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            await _pedir(cliente, reloj, lim, metodo="POST", datos={"q": "x"},
                         cabeceras={"Authorization": "Bearer secreta"})
        segunda = registros[1]
        assert segunda.method == "POST" and b'"q"' in segunda.content
        assert segunda.headers.get("authorization") == "Bearer secreta"


class TestRecomendacionesDeSeguridad:
    def test_retry_after_no_finito_cae_al_backoff(self):
        assert retry_after_s("nan") is None
        assert retry_after_s("inf") is None
        assert retry_after_s("-inf") is None
        assert retry_after_s("5000", maximo=100) == 100.0

    async def test_el_429_tras_un_salto_bloquea_el_host_del_salto_final(self, ajustes_habilitados):
        registros = []

        def handler(request: httpx.Request):
            registros.append(str(request.url))
            if len(registros) == 1:
                return httpx.Response(302, headers={"location": "https://b.example/x"})
            return httpx.Response(429, headers={"retry-after": "30"})

        cliente, reloj, lim = _mundo(handler)
        async with cliente:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente, reloj, lim, espera_max_s=5.0,
                             hosts_redireccion=lambda origen: True)
        assert exc.value.host_efectivo == "https://b.example:443"
        hosts = {h["host"]: h for h in lim.snapshot(Ajustes())["hosts"]}
        assert hosts["https://b.example:443"]["bloqueada_hasta_s"] == pytest.approx(30)
        assert hosts["https://comicvine.gamespot.com:443"]["bloqueada_hasta_s"] is None

    async def test_el_bloqueo_respeta_el_tope_de_la_politica(self, ajustes_habilitados):
        lim = CortesiaProceso(reloj=Reloj(), dormir=asyncio.sleep)
        lim.bloquear("comicvine", "https://a.example", 5000,
                     maximo_s=politica_de("comicvine", Ajustes()).bloqueo_max_s)
        assert lim.snapshot(Ajustes())["fuentes"][0]["bloqueada_hasta_s"] == 3600
