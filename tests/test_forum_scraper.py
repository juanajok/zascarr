# ruff: noqa: E501
"""H5 — `ForumScraper`: la frontera es el origen del foro (red SIMULADA).

Los enlaces a temas salen del HTML del foro, que no es de fiar, y las cookies de sesión del foro son
credenciales. Antes de H5: `urljoin(base, href)` dejaba pasar un `href` absoluto, la petición seguía
redirecciones automáticamente y las cookies iban en un `dict` que `httpx` envía a TODOS los hosts. Aquí se
prueba, con un transporte falso que registra cada petición (host y cabecera `Cookie`), que:

- ningún enlace ni redirección hostil provoca una petición a otro origen;
- ninguna cookie viaja a otro host (`127.0.0.1`, un tercero…);
- el caso legítimo (enlaces relativos y absolutos del propio foro) sigue funcionando.
"""
from __future__ import annotations

import httpx
import pytest
import structlog

from zascarr.services.forum_scraper import (
    MAX_SALTOS,
    ForumScraper,
    OrigenNoPermitidoError,
    origen_de,
)

BASE = "https://foro.example"
COOKIE = "member_id=1; pass_hash=SECRETA"
ED2K = "ed2k://|file|Tebeo_01.cbr|1234|ABCDEF0123456789ABCDEF0123456789|/"


def _busqueda(*hrefs: str) -> str:
    return "<html>" + "".join(f'<a href="{h}">Tema {i}</a>' for i, h in enumerate(hrefs)) + "</html>"


def _tema() -> str:
    return f'<html><a href="{ED2K}">enlace</a></html>'


class Foro:
    """Un foro falso: registra TODAS las peticiones y responde según un manejador."""

    def __init__(self, busqueda: str, manejador=None):
        self.busqueda = busqueda
        self.peticiones: list[httpx.Request] = []
        self._manejador = manejador or self._por_defecto

    def _por_defecto(self, request: httpx.Request) -> httpx.Response:
        if "act=Search" in str(request.url):
            return httpx.Response(200, text=self.busqueda)
        return httpx.Response(200, text=_tema())

    def cliente(self) -> httpx.AsyncClient:
        def _h(request: httpx.Request) -> httpx.Response:
            self.peticiones.append(request)
            return self._manejador(request)
        return httpx.AsyncClient(transport=httpx.MockTransport(_h), follow_redirects=False)

    def scraper(self, base: str = BASE) -> ForumScraper:
        s = ForumScraper(base, rate_limit=0, crear_cliente=self.cliente)
        s._cookies = {"member_id": "1", "pass_hash": "SECRETA"}
        return s

    @property
    def hosts(self) -> list[str]:
        return [p.url.host for p in self.peticiones]

    def a_otro_origen(self, base: str = BASE) -> list[httpx.Request]:
        return [p for p in self.peticiones if origen_de(str(p.url)) != origen_de(base)]

    def cookies_fuera_del_foro(self, base: str = BASE) -> list[str]:
        """Peticiones que llevan la cookie y NO son del origen del foro: debe ser siempre vacío."""
        return [str(p.url) for p in self.peticiones
                if p.headers.get("cookie") and origen_de(str(p.url)) != origen_de(base)]


# ── El caso legítimo sigue funcionando ───────────────────────────────────────────────────────

class TestCasoLegitimo:

    @pytest.mark.parametrize("href", [
        "index.php?showtopic=5", "/index.php?showtopic=5", "./index.php?showtopic=5",
        "?showtopic=5",
        f"{BASE}/index.php?showtopic=5",                 # los foros IPB suelen emitir enlaces ABSOLUTOS a sus temas
        "//foro.example/index.php?showtopic=5",
        "HTTPS://FORO.example:443/index.php?showtopic=5",  # mayúsculas y puerto por defecto explícito
    ])
    async def test_un_enlace_del_propio_foro_se_sigue_con_la_cookie(self, href):
        foro = Foro(_busqueda(href))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert len(resultados) == 1 and resultados[0].ed2k_links == [ED2K]
        assert resultados[0].topic_url.startswith(f"{BASE}/")
        assert foro.a_otro_origen() == []
        assert all(p.headers["cookie"] == COOKIE for p in foro.peticiones)   # el foro SÍ recibe su cookie

    async def test_un_foro_con_puerto_propio(self):
        base = "https://foro.example:8443"
        foro = Foro(_busqueda("https://foro.example:8443/x?showtopic=1", "/y?showtopic=2"))
        resultados = await foro.scraper(base).use_ipb_search("tebeo")
        assert len(resultados) == 2 and foro.a_otro_origen(base) == []

    async def test_el_login_sigue_guardando_las_cookies(self):
        foro = Foro("", manejador=lambda r: httpx.Response(200, headers={"Set-Cookie": "member_id=9; Path=/"}))
        s = ForumScraper(BASE, rate_limit=0, crear_cliente=foro.cliente)
        assert await s.login("u", "p") is True and s._cookies == {"member_id": "9"}


# ── Enlaces hostiles en el HTML del foro ─────────────────────────────────────────────────────

HREFS_HOSTILES = [
    "http://127.0.0.1:9091/transmission/rpc?showtopic=1",       # servicio interno
    "https://atacante.example/x?showtopic=2",                    # tercero
    "//atacante.example/x?showtopic=3",                          # sin esquema
    "//127.0.0.1/x?showtopic=4",
    "http://169.254.169.254/latest/meta-data/?showtopic=5",
    "https://[::1]/x?showtopic=6",
    "javascript:alert(1)//showtopic=7", "data:text/html,x?showtopic=8", "ftp://foro.example/x?showtopic=9",
    "file:///etc/passwd?showtopic=10",
    "https://foro.example@atacante.example/x?showtopic=11",      # el «usuario» es el foro; el host, el atacante
    "https://atacante.example\\@foro.example/x?showtopic=12",
    "/\\atacante.example/x?showtopic=13", "\\\\atacante.example\\x?showtopic=14",
    "https://foro.example:8443/x?showtopic=15",                  # mismo host, OTRO puerto
    "http://foro.example/x?showtopic=16",                        # mismo host, OTRO esquema
    "https://foro.example.atacante.example/x?showtopic=17",      # empieza igual, pero es otro host
    "https://FORO.example@127.0.0.1/x?showtopic=18",
    "https://usuario:clave@foro.example/x?showtopic=21",          # el host ES el foro, pero lleva credenciales
    "index.php?showtopic=19\tx", "https://atacante.example/x y?showtopic=20",
]


class TestEnlacesHostiles:

    @pytest.mark.parametrize("href", HREFS_HOSTILES)
    async def test_un_enlace_a_otro_origen_no_provoca_ninguna_peticion_ni_envia_la_cookie(self, href):
        foro = Foro(_busqueda(href))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert resultados == []
        assert foro.hosts == ["foro.example"]               # solo la búsqueda: ni una petición al tema hostil
        assert foro.a_otro_origen() == [] and foro.cookies_fuera_del_foro() == []

    async def test_un_enlace_hostil_no_impide_los_legitimos_de_la_misma_pagina(self):
        foro = Foro(_busqueda("http://127.0.0.1:9091/x?showtopic=1", "index.php?showtopic=2",
                              "https://atacante.example/x?showtopic=3", f"{BASE}/index.php?showtopic=4"))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert len(resultados) == 2
        assert set(foro.hosts) == {"foro.example"} and foro.cookies_fuera_del_foro() == []

    @pytest.mark.parametrize("href", HREFS_HOSTILES)
    def test_el_resolutor_de_enlaces_los_rechaza(self, href):
        with pytest.raises(OrigenNoPermitidoError):
            ForumScraper(BASE)._resolver_enlace(href)

    def test_el_origen_del_resultado_se_comprueba_aunque_urljoin_lo_cambie(self, monkeypatch):
        """Defensa en profundidad: aunque `urljoin` devolviera algo de otro origen, no se acepta."""
        from zascarr.services import forum_scraper
        monkeypatch.setattr(forum_scraper, "urljoin", lambda base, href: "https://atacante.example/x")
        with pytest.raises(OrigenNoPermitidoError, match="otro_origen"):
            ForumScraper(BASE)._resolver_enlace("index.php?showtopic=1")

    @pytest.mark.parametrize("href", ["//..showtopic=1\uff0f", "https://\uff0f/x?showtopic=1",
                                     "https://foro.example\uff0f@x/y?showtopic=1"])
    async def test_un_enlace_que_hace_lanzar_a_urlsplit_no_aborta_la_busqueda(self, href):
        """`urlsplit` lanza `ValueError` con ciertos caracteres Unicode (normalización NFKC): un enlace hostil no
        puede abortar la búsqueda ni impedir los legítimos de la misma página."""
        foro = Foro(_busqueda(href, "index.php?showtopic=2"))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert len(resultados) == 1 and resultados[0].topic_url.endswith("showtopic=2")
        assert foro.a_otro_origen() == []

    @pytest.mark.parametrize("href", [
        "https://foro.example//atacante.example/x?showtopic=1",       # la ruta empieza por //
        "//foro.example//atacante.example/x?showtopic=1",
        "https://foro.example///127.0.0.1:9091/x?showtopic=1",
    ])
    async def test_una_ruta_que_empieza_por_dos_barras_no_cambia_de_host(self, href):
        """Al reducir un absoluto del propio foro a ruta y consulta, `//otro.example/x` se leería como una
        referencia sin esquema y `urljoin` la llevaría a OTRO host: se normaliza a una sola barra inicial."""
        foro = Foro(_busqueda(href))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert len(resultados) == 1 and origen_de(resultados[0].topic_url) == origen_de(BASE)
        assert set(foro.hosts) == {"foro.example"} and foro.cookies_fuera_del_foro() == []

    async def test_un_enlace_relativo_con_caracteres_unicode_inofensivos_se_sigue(self):
        foro = Foro(_busqueda("\uff0f?showtopic=1"))
        assert len(await foro.scraper().use_ipb_search("tebeo")) == 1

    async def test_un_urljoin_que_lanza_se_trata_como_enlace_rechazado(self, monkeypatch):
        from zascarr.services import forum_scraper

        def _lanza(base, href):
            raise ValueError("netloc con caracteres inválidos")
        monkeypatch.setattr(forum_scraper, "urljoin", _lanza)
        foro = Foro(_busqueda("index.php?showtopic=1"))
        assert await foro.scraper().use_ipb_search("tebeo") == []      # y no revienta

    async def test_una_redireccion_con_un_destino_que_hace_lanzar_a_urljoin_se_corta(self, monkeypatch):
        from zascarr.services import forum_scraper
        original = forum_scraper.urljoin

        def _lanza_solo_en_redirecciones(base, href):
            if "bomba" in href:
                raise ValueError("netloc con caracteres inválidos")
            return original(base, href)
        monkeypatch.setattr(forum_scraper, "urljoin", _lanza_solo_en_redirecciones)
        foro = Foro("", manejador=lambda r: httpx.Response(302, headers={"Location": "/bomba"}))
        with pytest.raises(OrigenNoPermitidoError, match="url_mal_formada"):
            await foro.scraper()._get(f"{BASE}/index.php")

    async def test_no_se_registra_el_enlace_hostil_entero_solo_el_host_y_un_codigo(self):
        foro = Foro(_busqueda("https://atacante.example/secreto/CLAVE_SECRETA?apikey=CLAVE_SECRETA&showtopic=1"))
        with structlog.testing.capture_logs() as registros:
            await foro.scraper().use_ipb_search("tebeo")
        assert registros and "CLAVE_SECRETA" not in repr(registros)
        assert any(r.get("host") == "atacante.example" for r in registros)


# ── Redirecciones ────────────────────────────────────────────────────────────────────────────

def _redirige_el_tema_a(destino: str, estado: int = 302):
    def _h(request: httpx.Request) -> httpx.Response:
        if "act=Search" in str(request.url):
            return httpx.Response(200, text=_busqueda("index.php?showtopic=1"))
        if request.url.host == "foro.example":
            return httpx.Response(estado, headers={"Location": destino})
        return httpx.Response(200, text=_tema())            # si llegara a pedirse el destino, respondería
    return _h


class TestRedirecciones:

    @pytest.mark.parametrize("destino", [
        "http://127.0.0.1:9091/transmission/rpc", "https://atacante.example/robar",
        "//atacante.example/x", "http://foro.example/x",    # http -> https: otro origen, también se corta
        "https://foro.example:8443/x", "file:///etc/passwd", "https://foro.example@atacante.example/x",
    ])
    async def test_una_redireccion_hostil_se_corta_sin_segunda_peticion_ni_cookie(self, destino):
        foro = Foro("", manejador=_redirige_el_tema_a(destino))
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert resultados == []
        assert foro.hosts == ["foro.example", "foro.example"]    # la búsqueda y el tema, nada más
        assert foro.a_otro_origen() == [] and foro.cookies_fuera_del_foro() == []

    @pytest.mark.parametrize("estado", [301, 302, 303, 307, 308])
    async def test_una_redireccion_dentro_del_foro_se_sigue_a_mano(self, estado):
        pasos = iter([httpx.Response(estado, headers={"Location": "/otro?showtopic=1"}),
                      httpx.Response(200, text=_tema())])

        def _h(request):
            if "act=Search" in str(request.url):
                return httpx.Response(200, text=_busqueda("index.php?showtopic=1"))
            return next(pasos)
        foro = Foro("", manejador=_h)
        resultados = await foro.scraper().use_ipb_search("tebeo")
        assert len(resultados) == 1 and foro.a_otro_origen() == []
        assert all(p.headers["cookie"] == COOKIE for p in foro.peticiones)

    async def test_la_busqueda_que_redirige_a_otro_origen_devuelve_vacio(self):
        foro = Foro("", manejador=lambda r: httpx.Response(302, headers={"Location": "https://atacante.example/"}))
        assert await foro.scraper().use_ipb_search("tebeo") == []
        assert foro.hosts == ["foro.example"] and foro.cookies_fuera_del_foro() == []

    async def test_un_bucle_de_redirecciones_se_corta_en_el_maximo(self):
        foro = Foro("", manejador=lambda r: httpx.Response(302, headers={"Location": "/bucle"}))
        with pytest.raises(OrigenNoPermitidoError, match="demasiadas_redirecciones"):
            await foro.scraper()._get(f"{BASE}/index.php")
        assert len(foro.peticiones) == MAX_SALTOS + 1

    async def test_una_redireccion_sin_destino_es_un_error(self):
        foro = Foro("", manejador=lambda r: httpx.Response(302))
        with pytest.raises(OrigenNoPermitidoError, match="redireccion_sin_destino"):
            await foro.scraper()._get(f"{BASE}/index.php")

    def test_el_cliente_por_defecto_no_sigue_redirecciones_solo(self):
        import asyncio

        async def _mira():
            async with ForumScraper(BASE)._crear_cliente() as c:
                return c.follow_redirects
        assert asyncio.run(_mira()) is False


# ── Las cookies ──────────────────────────────────────────────────────────────────────────────

class TestCookies:

    def test_las_cookies_solo_acompanan_al_origen_exacto_del_foro(self):
        s = ForumScraper(BASE)
        s._cookies = {"member_id": "1", "pass_hash": "SECRETA"}
        assert s._cabeceras(f"{BASE}/index.php")["Cookie"] == COOKIE
        for otro in ("http://127.0.0.1:9091/x", "https://atacante.example/x", "http://foro.example/x",
                     "https://foro.example:8443/x", "https://foro.example.atacante.example/x", "not-a-url"):
            assert "Cookie" not in s._cabeceras(otro), otro

    async def test_ninguna_peticion_lleva_cookies_a_traves_del_cliente(self):
        """Antes las cookies iban en `httpx.AsyncClient(cookies=dict)`, que las envía a TODOS los hosts. Ahora el
        cliente se crea SIN jar de cookies: solo viaja la cabecera explícita, y solo al foro."""
        foro = Foro(_busqueda("index.php?showtopic=1"))
        creado = []

        def _crea():
            c = foro.cliente()
            creado.append(c)
            return c
        s = ForumScraper(BASE, rate_limit=0, crear_cliente=_crea)
        s._cookies = {"pass_hash": "SECRETA"}
        await s.use_ipb_search("tebeo")
        assert creado and all(len(c.cookies.jar) == 0 for c in creado)

    def test_un_origen_mal_formado_no_comparte_cookies(self):
        s = ForumScraper("esto no es una url")
        s._cookies = {"a": "b"}
        assert "Cookie" not in s._cabeceras("https://foro.example/")


# ── Normalización del origen ─────────────────────────────────────────────────────────────────

class TestOrigen:

    @pytest.mark.parametrize("a,b", [
        ("https://foro.example", "HTTPS://FORO.EXAMPLE:443/x"),
        ("http://foro.example", "http://foro.example:80/"),
        ("https://foro.example.", "https://foro.example/x"),
    ])
    def test_son_el_mismo_origen(self, a, b):
        assert origen_de(a) == origen_de(b) is not None

    @pytest.mark.parametrize("a,b", [
        ("https://foro.example", "http://foro.example"),
        ("https://foro.example", "https://foro.example:8443"),
        ("https://foro.example", "https://otro.example"),
        ("https://foro.example", "https://foro.example.otro.example"),
    ])
    def test_no_son_el_mismo_origen(self, a, b):
        assert origen_de(a) != origen_de(b)

    @pytest.mark.parametrize("url", ["", "file:///x", "javascript:x", "https://", "https://foro.example:99999/"])
    def test_lo_que_no_es_http_valido_no_tiene_origen(self, url):
        assert origen_de(url) is None
