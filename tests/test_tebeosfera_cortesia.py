# ruff: noqa: E501
"""Cortesía con Tebeosfera: 2,5 s como mínimo entre peticiones, COMPARTIDO por todas las instancias y caminos.

Antes cada `TebeosferaClient` llevaba su propio `_last_req` (a 0 al crearse) y cada búsqueda de Descubrir o cada
ciclo del enricher crea uno nuevo: dos búsquedas seguidas llegaban al sitio sin espera entre ellas. Con reloj y
transporte simulados se comprueba, para instancias distintas, caminos distintos y peticiones concurrentes, que
entre el inicio de dos peticiones al sitio pasan al menos 2,5 s. Nada sale a la red y nada duerme de verdad.

La garantía depende de que haya UN SOLO PROCESO (`uvicorn --workers 1`); ver `utils/cortesia.py`.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace

import httpx
import pytest
import structlog

from zascarr.config import get_settings
from zascarr.services import tebeosfera
from zascarr.services.tebeosfera import MINIMO_ENTRE_PETICIONES_S, TebeosferaClient
from zascarr.utils import cortesia
from zascarr.utils.cortesia import LimitadorDeCortesia

HTML = ('<div class="linea_resultados"><a href="/colecciones/thorgal_1981_distrinovel.html">'
        'THORGAL (1981, DISTRINOVEL)</a></div>')


class Reloj:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t

    async def dormir(self, s):
        await asyncio.sleep(0)
        self.t += s


class Sitio:
    """El «sitio»: un transporte simulado que anota CADA petición que le llega (instante del reloj falso,
    método, URL y cuerpo), también las que el cliente emite al seguir una redirección."""

    def __init__(self, reloj: Reloj, falla: bool = False, manejador=None):
        self.reloj, self.falla, self.manejador = reloj, falla, manejador
        self.instantes: list[float] = []
        self.peticiones: list[tuple[str, str, bytes]] = []

    def transporte(self) -> httpx.MockTransport:
        def _h(request: httpx.Request) -> httpx.Response:
            self.instantes.append(self.reloj())
            self.peticiones.append((request.method, str(request.url), request.content))
            if self.falla:
                raise httpx.ConnectError("caído")
            if self.manejador is not None:
                return self.manejador(request)
            return httpx.Response(200, text=HTML)
        return httpx.MockTransport(_h)

    def separaciones(self) -> list[float]:
        return [b - a for a, b in zip(self.instantes, self.instantes[1:], strict=False)]


@pytest.fixture
def mundo(monkeypatch):
    cortesia.reiniciar_para_pruebas()
    reloj = Reloj()
    cortesia._LIMITADORES["tebeosfera"] = LimitadorDeCortesia(reloj=reloj, dormir=reloj.dormir)
    ajustes = {"tebeosfera_rate_limit": 2.5}
    monkeypatch.setattr(tebeosfera, "get_settings", lambda: SimpleNamespace(**ajustes))
    yield SimpleNamespace(reloj=reloj, sitio=Sitio(reloj), ajustes=ajustes)
    cortesia.reiniciar_para_pruebas()


def cliente(mundo) -> TebeosferaClient:
    return TebeosferaClient(transporte=mundo.sitio.transporte())


async def buscar(mundo, consulta="Thorgal"):
    async with cliente(mundo) as c:
        return await c.search_series(consulta)


class TestInstanciasYCaminosDistintos:

    async def test_dos_busquedas_seguidas_con_clientes_distintos_se_espacian(self, mundo):
        """El caso del fallo: cada búsqueda crea un cliente nuevo. Antes, la 1.ª petición de la 2.ª búsqueda no
        esperaba nada."""
        await buscar(mundo)
        await buscar(mundo)
        s = mundo.sitio
        assert len(s.instantes) == 4                          # 2 peticiones por búsqueda (colecciones + sagas)
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()

    async def test_la_primera_peticion_del_proceso_no_espera(self, mundo):
        await buscar(mundo)
        assert mundo.sitio.instantes[0] == pytest.approx(5000.0)

    async def test_busquedas_concurrentes_de_clientes_distintos_se_escalonan(self, mundo):
        await asyncio.gather(*(buscar(mundo, f"t{i}") for i in range(5)))
        s = mundo.sitio
        assert len(s.instantes) == 10
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()
        assert s.instantes[-1] - s.instantes[0] == pytest.approx(9 * 2.5)

    async def test_el_camino_de_descubrir_y_el_del_enricher_comparten_el_limite(self, mundo):
        """Descubrir abre un cliente por búsqueda (`async with`); el enricher uno por ciclo, dentro de un
        `AsyncExitStack`. Concurrentes, comparten el mismo limitador."""
        async def como_descubrir():
            async with cliente(mundo) as c:
                await c.search_series("a")

        async def como_el_enricher():
            async with AsyncExitStack() as pila:
                c = await pila.enter_async_context(cliente(mundo))
                await c.search_series("b")
                await c.search_series("c")
        await asyncio.gather(como_descubrir(), como_el_enricher(), como_descubrir())
        s = mundo.sitio
        assert len(s.instantes) == 8
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()

    async def test_las_dos_peticiones_de_una_misma_busqueda_tambien_se_espacian(self, mundo):
        await buscar(mundo)
        assert mundo.sitio.separaciones() == [pytest.approx(2.5)]

    async def test_una_peticion_que_falla_cuenta_para_el_espaciado(self, mundo):
        mundo.sitio.falla = True
        assert await buscar(mundo) == []                      # el cliente trata el fallo como «sin resultado»
        mundo.sitio.falla = False
        await buscar(mundo)
        assert all(x >= 2.5 - 1e-9 for x in mundo.sitio.separaciones())

    async def test_el_limitador_es_el_compartido_del_sitio_y_no_uno_propio(self, mundo):
        a, b = cliente(mundo), cliente(mundo)
        async with a, b:
            await a._throttle()
            await b._throttle()
        assert mundo.sitio.instantes == []                    # (solo throttle: sin peticiones)
        assert cortesia._LIMITADORES["tebeosfera"]._ultima is not None
        assert not hasattr(a, "_last_req") and not hasattr(b, "_last_req")


class TestElMinimo:

    @pytest.mark.parametrize("configurado", [2.0, 1.0, 0.0, 0.1, -3.0])
    async def test_una_configuracion_por_debajo_del_minimo_se_eleva_a_2_5(self, mundo, configurado):
        mundo.ajustes["tebeosfera_rate_limit"] = configurado
        await buscar(mundo)
        await buscar(mundo)
        assert all(x >= MINIMO_ENTRE_PETICIONES_S - 1e-9 for x in mundo.sitio.separaciones())

    @pytest.mark.parametrize("configurado", [2.5, 3.0, 10.0])
    async def test_una_configuracion_igual_o_superior_se_respeta(self, mundo, configurado):
        mundo.ajustes["tebeosfera_rate_limit"] = configurado
        await buscar(mundo)
        assert all(x == pytest.approx(configurado) for x in mundo.sitio.separaciones())

    def test_el_minimo_del_proyecto_es_2_5_y_el_valor_por_defecto_tambien(self):
        assert MINIMO_ENTRE_PETICIONES_S == 2.5
        assert type(get_settings()).model_fields["tebeosfera_rate_limit"].default == 2.5

    async def test_avisa_en_el_registro_si_la_configuracion_estaba_por_debajo(self, mundo):
        mundo.ajustes["tebeosfera_rate_limit"] = 1.0
        with structlog.testing.capture_logs() as registros:
            cliente(mundo)
        assert [r["event"] for r in registros] == ["tebeosfera.rate_limit_elevado"]
        assert registros[0]["configurado"] == 1.0 and registros[0]["minimo"] == 2.5

    async def test_con_la_configuracion_correcta_no_avisa(self, mundo):
        with structlog.testing.capture_logs() as registros:
            cliente(mundo)
        assert registros == []


class TestCancelacionYBucles:

    async def test_cancelar_una_busqueda_en_espera_no_rompe_el_espaciado_de_las_demas(self, mundo):
        await buscar(mundo)                                   # la 1.ª y la 2.ª petición ya hechas
        tarea = asyncio.create_task(buscar(mundo, "cancelada"))
        await asyncio.sleep(0)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
        await buscar(mundo, "siguiente")
        assert all(x >= 2.5 - 1e-9 for x in mundo.sitio.separaciones())

    def test_funciona_en_bucles_de_eventos_distintos(self, monkeypatch):
        cortesia.reiniciar_para_pruebas()
        reloj = Reloj()
        cortesia._LIMITADORES["tebeosfera"] = LimitadorDeCortesia(reloj=reloj, dormir=reloj.dormir)
        monkeypatch.setattr(tebeosfera, "get_settings", lambda: SimpleNamespace(tebeosfera_rate_limit=2.5))
        sitio = Sitio(reloj)

        async def una():
            async with TebeosferaClient(transporte=sitio.transporte()) as c:
                await c.search_series("x")
        asyncio.run(una())
        asyncio.run(una())
        assert all(x >= 2.5 - 1e-9 for x in sitio.separaciones())
        cortesia.reiniciar_para_pruebas()


def redirige(*destinos, codigo=302):
    """Un manejador que responde con una redirección por cada destino y, al agotarlos, con el HTML bueno."""
    pendientes = list(destinos)

    def _h(request: httpx.Request) -> httpx.Response:
        if pendientes:
            return httpx.Response(codigo, headers={"location": pendientes.pop(0)})
        return httpx.Response(200, text=HTML)
    return _h


SEPARADO = lambda s: all(x >= 2.5 - 1e-9 for x in s.separaciones())   # noqa: E731


class TestRedirecciones:
    """Cada SALTO es una petición más al sitio: también pasa por el limitador. Antes, `follow_redirects=True`
    dejaba que httpx emitiese los saltos sin volver a esperar."""

    async def test_el_cliente_no_sigue_redirecciones_por_su_cuenta(self, mundo):
        async with cliente(mundo) as c:
            assert c._client.follow_redirects is False

    async def test_una_redireccion_del_mismo_origen_se_sigue_y_se_espacia(self, mundo):
        mundo.sitio.manejador = redirige("/neko/otra.php")
        resultado = await buscar(mundo)
        s = mundo.sitio
        assert [r.kind for r in resultado] == ["collection"]   # el HTML bueno llegó tras el salto
        assert len(s.peticiones) == 3                         # POST + salto + POST de la 2.ª tabla
        assert s.peticiones[1][1] == "https://www.tebeosfera.com/neko/otra.php"
        assert SEPARADO(s), s.separaciones()

    async def test_una_cadena_de_redirecciones_espacia_todos_los_saltos(self, mundo):
        mundo.sitio.manejador = redirige("/a", "/b", "https://www.tebeosfera.com/c")
        async with cliente(mundo) as c:
            assert await c._search_table("T3_publicaciones", "collection", "x")
        s = mundo.sitio
        assert [p[1].rsplit("/", 1)[1] for p in s.peticiones[1:]] == ["a", "b", "c"]
        assert len(s.peticiones) == 4 and SEPARADO(s), s.separaciones()
        assert s.instantes[-1] - s.instantes[0] == pytest.approx(3 * 2.5)

    async def test_mas_saltos_de_los_permitidos_se_cortan_y_no_se_siguen_sin_fin(self, mundo):
        mundo.sitio.manejador = lambda r: httpx.Response(302, headers={"location": "/bucle"})
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        s = mundo.sitio
        assert len(s.peticiones) == tebeosfera.MAX_SALTOS + 1
        assert SEPARADO(s)

    @pytest.mark.parametrize("destino", [
        "https://evil.example/x",                             # otro host
        "http://www.tebeosfera.com/x",                        # otro esquema
        "https://www.tebeosfera.com:8443/x",                  # otro puerto
        "//evil.example/x",                                   # mismo esquema, otro host
        "https://www.tebeosfera.com@evil.example/x",          # credenciales que despistan
        "https://user:pw@www.tebeosfera.com/x",               # credenciales
        "https://tebeosfera.com/x",                           # el dominio sin www no es el origen
        "https://cdn.tebeosfera.com/x",                       # un subdominio tampoco
        "ftp://www.tebeosfera.com/x",
        "https://[::1]/x",
        "http://127.0.0.1/x",
    ])
    async def test_un_destino_fuera_del_origen_se_rechaza_sin_enviarle_nada(self, mundo, destino):
        mundo.sitio.manejador = redirige(destino)
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        assert len(mundo.sitio.peticiones) == 1               # solo la inicial: al destino no llegó nada
        assert all("evil" not in p[1] and "127.0.0.1" not in p[1] for p in mundo.sitio.peticiones)

    async def test_un_destino_rechazado_se_registra_solo_con_el_host(self, mundo):
        mundo.sitio.manejador = redirige("https://evil.example/x?busqueda=secreto")
        with structlog.testing.capture_logs() as registros:
            async with cliente(mundo) as c:
                await c._search_table("T3_series", "saga", "secreto")
        rechazo = [r for r in registros if r["event"] == "tebeosfera.redireccion_rechazada"]
        assert rechazo and rechazo[0]["host"] == "evil.example"
        assert "secreto" not in str(rechazo)

    async def test_una_redireccion_sin_location_es_un_fallo_y_no_se_sigue(self, mundo):
        mundo.sitio.manejador = lambda r: httpx.Response(302)
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        assert len(mundo.sitio.peticiones) == 1

    @pytest.mark.parametrize("location", ["http://[::1/x", "https://a\u2100b/x", "https://\uff03.com/"])
    async def test_un_location_malformado_es_un_fallo_y_no_se_sigue(self, mundo, location):
        """httpx ya rechaza varios (RemoteProtocolError); el resultado es el mismo: sin resultados, una petición."""
        mundo.sitio.manejador = lambda r: httpx.Response(302, headers=[(b"location", location.encode())])
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        assert len(mundo.sitio.peticiones) == 1

    async def test_un_location_que_httpx_acepta_pero_urljoin_no_tampoco_escapa(self, mundo):
        """`urljoin` lanza ValueError con un netloc que no sobrevive a NFKC (barra de ancho completo) aunque httpx
        lo deje pasar: esa excepción no debe salir de la búsqueda."""
        malo = "https://www.tebeosfera.com\uff0f@x/y".encode()
        mundo.sitio.manejador = lambda r: httpx.Response(302, headers=[(b"location", malo)])
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        assert len(mundo.sitio.peticiones) == 1

    @pytest.mark.parametrize("codigo", [300, 304, 305])
    async def test_una_3xx_que_no_es_redireccion_no_se_sigue(self, mundo, codigo):
        mundo.sitio.manejador = redirige("/neko/otra.php", codigo=codigo)
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        assert len(mundo.sitio.peticiones) == 1

    @pytest.mark.parametrize("codigo", [301, 302, 303])
    async def test_301_302_303_pasan_a_get_sin_cuerpo(self, mundo, codigo):
        mundo.sitio.manejador = redirige("/neko/otra.php", codigo=codigo)
        async with cliente(mundo) as c:
            await c._search_table("T3_series", "saga", "x")
        (m0, _, b0), (m1, _, b1) = mundo.sitio.peticiones
        assert (m0, m1) == ("POST", "GET") and b0 and b1 == b""

    @pytest.mark.parametrize("codigo", [307, 308])
    async def test_307_y_308_conservan_metodo_y_cuerpo(self, mundo, codigo):
        mundo.sitio.manejador = redirige("/neko/otra.php", codigo=codigo)
        async with cliente(mundo) as c:
            await c._search_table("T3_series", "saga", "x")
        (m0, _, b0), (m1, _, b1) = mundo.sitio.peticiones
        assert (m0, m1) == ("POST", "POST") and b0 == b1 and b0

    async def test_busquedas_concurrentes_con_redirecciones_siguen_separadas(self, mundo):
        """Cuatro clientes a la vez, cada petición con un 302 que se sigue: todas las peticiones del sitio
        (iniciales y saltos) quedan separadas ≥ 2,5 s."""
        mundo.sitio.manejador = lambda r: (
            httpx.Response(302, headers={"location": "/neko/ok.php"}) if r.method == "POST"
            else httpx.Response(200, text=HTML))
        await asyncio.gather(*(buscar(mundo, f"t{i}") for i in range(4)))
        s = mundo.sitio
        assert len(s.peticiones) == 4 * 2 * 2                 # 4 búsquedas × 2 tablas × (petición + salto)
        assert SEPARADO(s), s.separaciones()
        assert s.instantes[-1] - s.instantes[0] == pytest.approx((len(s.instantes) - 1) * 2.5)

    async def test_un_fallo_en_un_salto_cuenta_y_devuelve_sin_resultados(self, mundo):
        mundo.sitio.manejador = lambda r: (
            httpx.Response(302, headers={"location": "/neko/ok.php"}) if r.method == "POST"
            else httpx.Response(500))
        async with cliente(mundo) as c:
            assert await c._search_table("T3_series", "saga", "x") == []
        await buscar(mundo)
        assert SEPARADO(mundo.sitio)

    async def test_cancelar_entre_saltos_no_estropea_el_espaciado_posterior(self, mundo):
        mundo.sitio.manejador = redirige("/a", "/b")
        tarea = asyncio.create_task(buscar(mundo, "cancelada"))
        for _ in range(3):
            await asyncio.sleep(0)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
        mundo.sitio.manejador = None
        await buscar(mundo, "siguiente")
        assert SEPARADO(mundo.sitio), mundo.sitio.separaciones()


class TestDestinoPermitido:

    @pytest.mark.parametrize("url", [
        "https://www.tebeosfera.com/neko/x.php",
        "https://www.tebeosfera.com",
        "https://www.tebeosfera.com:443/x",
        "https://WWW.TEBEOSFERA.COM/x",
    ])
    def test_acepta_el_origen_del_sitio(self, url):
        assert tebeosfera.destino_permitido(url)

    @pytest.mark.parametrize("url", [
        "", "/relativa", "//www.tebeosfera.com/x", "http://www.tebeosfera.com/x",
        "https://www.tebeosfera.com:444/x", "https://tebeosfera.com/x",
        "https://www.tebeosfera.com.evil.example/x", "https://evil.example/www.tebeosfera.com",
        "https://u@www.tebeosfera.com/x", "https://www.tebeosfera.com:abc/x", "https://[::1/x",
    ])
    def test_rechaza_todo_lo_demas_sin_lanzar(self, url):
        assert tebeosfera.destino_permitido(url) is False
