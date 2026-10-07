# ruff: noqa: E501
"""H1 — política de descarga de portadas (`utils/url_portada.py`): SSRF, con red SIMULADA.

La descarga la hace el servidor a partir de una URL que puede venir de un formulario, de la API o de una
fuente. Se prueba cada capa de la política: sintaxis, direcciones resueltas (IPv4 e IPv6, incluidas las que
incrustan una IPv4), conexión a la dirección ya validada (anti *DNS rebinding*), redirecciones a mano,
tamaño, registros ya guardados y los tres puntos de escritura. Nada sale a la red: se inyectan el resolutor
y el transporte. Una prueba levanta además un servidor TLS LOCAL para comprobar que conectar a la IP fijada
sigue verificando el certificado contra el NOMBRE.
"""
from __future__ import annotations

import io
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient
from PIL import Image

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.utils import cover as cover_mod
from zascarr.utils import url_portada
from zascarr.utils.cover import fetch_and_cache_cover
from zascarr.utils.url_portada import (
    MAX_SALTOS,
    UrlNoPermitidaError,
    analizar_url,
    descargar_imagen,
    es_publica,
    es_url_de_portada_permitida,
    resolver_publica,
)

PUBLICA = "93.184.216.34"
OTRA_PUBLICA = "151.101.1.69"
CV = "https://comicvine.gamespot.com/a/uploads/scale_large/1/11/cover.jpg"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="red").save(buf, format="PNG")
    return buf.getvalue()


class Red:
    """Una red falsa: un resolutor con su registro y un transporte con las peticiones que recibe."""

    def __init__(self, dns: dict[str, list[str]] | None = None, handler=None):
        self.dns = dns if dns is not None else {}
        self.resoluciones: list[str] = []
        self.peticiones: list[httpx.Request] = []
        self._handler = handler or (lambda r: httpx.Response(200, content=_png()))

    async def resolutor(self, host: str, puerto: int) -> list[str]:
        self.resoluciones.append(host)
        if host not in self.dns:
            raise OSError("no resuelve")
        return list(self.dns[host])

    def cliente(self) -> httpx.AsyncClient:
        def _h(request: httpx.Request) -> httpx.Response:
            self.peticiones.append(request)
            return self._handler(request)
        return httpx.AsyncClient(transport=httpx.MockTransport(_h), follow_redirects=False)

    async def descargar(self, url: str, **kw) -> bytes:
        return await descargar_imagen(url, resolutor=self.resolutor, crear_cliente=self.cliente, **kw)


# ── 1. Sintaxis ────────────────────────────────────────────────────────────────────────────────

URLS_RECHAZADAS = [
    # esquemas
    "file:///etc/passwd", "ftp://comicvine.gamespot.com/x.jpg", "gopher://comicvine.gamespot.com/",
    "javascript:alert(1)", "data:image/png;base64,AAAA",
    # direcciones escritas a mano
    "http://127.0.0.1/x.jpg", "http://127.0.0.1:9091/transmission/rpc", "http://[::1]/x.jpg",
    "http://169.254.169.254/latest/meta-data/", "https://10.0.0.5/x.jpg", "http://[::ffff:127.0.0.1]/x",
    "http://2130706433/x.jpg", "http://0x7f.0.0.1/x.jpg", "http://localhost/x.jpg",
    # credenciales
    "https://user:clave@comicvine.gamespot.com/x.jpg", "https://comicvine.gamespot.com@evil.example/x.jpg",
    "https://comicvine.gamespot.com:clave@evil.example/x.jpg",
    # puertos
    "https://comicvine.gamespot.com:8443/x.jpg", "http://comicvine.gamespot.com:8080/x.jpg",
    "http://comicvine.gamespot.com:443/x.jpg", "https://comicvine.gamespot.com:80/x.jpg",
    # nombres que parecen de la lista y no lo son
    "https://comicvine.gamespot.com.evil.example/x.jpg", "https://evilcbsistatic.com/x.jpg",
    "https://notanilist.co/x.jpg", "https://anilist.co.evil.example/x.jpg", "https://tebeosfera.com.mx/x.jpg",
    "https://evil.example/comicvine.gamespot.com/x.jpg",
    # caracteres raros
    "https://comicvine.gamespot.com/x y.jpg", "https://comicvine.gamespot.com/x\n.jpg",
    "https://comicvine.gamespot.com/x\t.jpg", "https://comicvine.gamespot.com。evil.example/x.jpg",
    "https://comicvine.gamespot.com/\x00", "",
]

URLS_ACEPTADAS = [
    CV, "http://comicvine.gamespot.com/a/x.jpg", "https://s4.anilist.co/file/anilistcdn/media/manga/cover/large/x.jpg",
    "https://www.tebeosfera.com/imagenes/x.jpg", "https://files1.comics.org/img/x.jpg",
    "https://COMICVINE.gamespot.com/x.jpg", "https://comicvine.gamespot.com./x.jpg",
    "https://comicvine.gamespot.com:443/x.jpg", "http://comicvine.gamespot.com:80/x.jpg",
    "https://static.cbsistatic.com/x.jpg?a=1&b=2",
]


class TestSintaxis:

    @pytest.mark.parametrize("url", URLS_RECHAZADAS)
    def test_se_rechaza(self, url):
        assert es_url_de_portada_permitida(url) is False

    @pytest.mark.parametrize("url", URLS_ACEPTADAS)
    def test_se_acepta_la_portada_legitima(self, url):
        assert es_url_de_portada_permitida(url) is True

    def test_no_str_se_rechaza(self):
        assert es_url_de_portada_permitida(None) is False   # type: ignore[arg-type]
        assert es_url_de_portada_permitida("x" * 501 + ".comicvine.gamespot.com") is False

    def test_en_un_salto_no_se_exige_la_lista_pero_si_el_resto(self):
        # Un CDN al que redirige una fuente legítima puede ser otro nombre…
        assert analizar_url("https://cdn.otro.example/c.jpg", exigir_lista=False)[1] == "cdn.otro.example"
        # …pero NUNCA una dirección escrita, credenciales, otro puerto u otro esquema.
        for malo in ("http://127.0.0.1/x", "https://u:p@cdn.otro.example/x", "https://cdn.otro.example:8443/x",
                     "file:///etc/passwd", "gopher://cdn.otro.example/", "https://café.example/x.jpg",
                     "https://cdn.otro.example\u3002evil.example/x.jpg"):
            with pytest.raises(UrlNoPermitidaError):
                analizar_url(malo, exigir_lista=False)


# ── 2. Direcciones resueltas ──────────────────────────────────────────────────────────────────

NO_PUBLICAS = [
    "127.0.0.1", "127.1.2.3", "10.0.0.1", "172.16.5.4", "172.31.255.255", "192.168.1.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "192.0.2.1", "198.18.0.1", "198.51.100.7",
    "203.0.113.9", "240.0.0.1",
    "::1", "::", "fe80::1", "fc00::1", "fd12:3456::1", "ff02::1", "2001:db8::1", "100::1",
    "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254",
    "::ffff:8.8.8.8",       # mapeada con una IPv4 pública: se rechaza igualmente (ningún CDN legítimo llega así)
    "64:ff9b::808:808",     # NAT64 de una IPv4 pública: ídem
    "2002:7f00:1::1",                                    # 6to4 de 127.0.0.1
    "64:ff9b::7f00:1",                                   # NAT64 de 127.0.0.1
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",              # Teredo con cliente 192.0.2.45
    "no-es-una-ip", "",
]
PUBLICAS = ["93.184.216.34", "8.8.8.8", "1.1.1.1", "151.101.1.69", "2606:4700:4700::1111",
            "2a00:1450:4001:81c::200e", "2001:4860:4860::8888"]


class TestDirecciones:

    @pytest.mark.parametrize("ip", NO_PUBLICAS)
    def test_no_es_publica(self, ip):
        assert es_publica(ip) is False

    @pytest.mark.parametrize("ip", PUBLICAS)
    def test_es_publica(self, ip):
        assert es_publica(ip) is True

    async def test_un_nombre_con_una_direccion_publica_y_otra_interna_se_rechaza(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA, "10.0.0.5"]})
        with pytest.raises(UrlNoPermitidaError, match="direccion_no_publica"):
            await resolver_publica("comicvine.gamespot.com", 443, red.resolutor)

    @pytest.mark.parametrize("respuesta", [[], None])
    async def test_sin_direcciones_o_sin_resolver_se_rechaza(self, respuesta):
        red = Red({} if respuesta is None else {"comicvine.gamespot.com": respuesta})
        with pytest.raises(UrlNoPermitidaError, match="no_resuelve"):
            await resolver_publica("comicvine.gamespot.com", 443, red.resolutor)

    async def test_se_devuelve_la_primera_si_todas_son_publicas(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA, OTRA_PUBLICA]})
        assert await resolver_publica("comicvine.gamespot.com", 443, red.resolutor) == PUBLICA


# ── 3-5. Descarga: sin red para lo rechazado, conexión fijada, redirecciones, tamaño ─────────

class TestDescarga:

    @pytest.mark.parametrize("url", [u for u in URLS_RECHAZADAS if u])
    async def test_lo_rechazado_no_resuelve_ni_hace_ninguna_peticion(self, url):
        red = Red({"comicvine.gamespot.com": [PUBLICA], "localhost": ["127.0.0.1"]})
        with pytest.raises(UrlNoPermitidaError):
            await red.descargar(url)
        assert red.peticiones == [] and red.resoluciones == []

    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254", "100.64.0.9",
                                   "::1", "fe80::1", "fd00::5", "::ffff:127.0.0.1", "2002:7f00:1::1",
                                   "64:ff9b::a00:5"])
    async def test_un_nombre_permitido_que_resuelve_a_una_direccion_interna_no_se_conecta(self, ip):
        """Un nombre de la lista cuyo DNS apunta dentro (o *rebinding*): la lista de nombres sola no basta."""
        red = Red({"comicvine.gamespot.com": [ip]})
        with pytest.raises(UrlNoPermitidaError, match="direccion_no_publica"):
            await red.descargar(CV)
        assert red.peticiones == []

    async def test_se_conecta_a_la_direccion_validada_con_el_nombre_en_host_y_sni(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]})
        datos = await red.descargar(CV)
        assert datos == _png()
        (peticion,) = red.peticiones
        assert peticion.url.host == PUBLICA                                        # no el nombre: sin 2.ª resolución
        assert peticion.headers["host"] == "comicvine.gamespot.com"
        assert peticion.extensions.get("sni_hostname") == "comicvine.gamespot.com"  # TLS verifica el NOMBRE
        assert red.resoluciones == ["comicvine.gamespot.com"]                       # una sola resolución

    async def test_un_cambio_de_dns_entre_la_comprobacion_y_la_conexion_no_influye(self):
        """Rebinding simulado: el DNS «cambia» tras la primera consulta. Como se conecta a la IP validada y no se
        vuelve a resolver, la segunda respuesta (interna) nunca se usa."""
        red = Red({"comicvine.gamespot.com": [PUBLICA]})
        original = red.resolutor
        llamadas = []

        async def rebinding(host, puerto):
            llamadas.append(host)
            return [PUBLICA] if len(llamadas) == 1 else ["127.0.0.1"]
        red.resolutor = rebinding   # type: ignore[method-assign]
        del original
        await red.descargar(CV)
        assert len(llamadas) == 1 and red.peticiones[0].url.host == PUBLICA

    async def test_http_no_lleva_sni_y_la_ipv6_va_entre_corchetes(self):
        red = Red({"comicvine.gamespot.com": ["2606:4700:4700::1111"]})
        await red.descargar("http://comicvine.gamespot.com/a.jpg")
        (peticion,) = red.peticiones
        assert peticion.url.host == "2606:4700:4700::1111" and peticion.url.scheme == "http"
        assert "sni_hostname" not in peticion.extensions

    def test_el_cliente_por_defecto_no_sigue_redirecciones_ni_usa_proxies_del_entorno(self):
        c = url_portada._cliente_por_defecto()
        assert c.follow_redirects is False and c.trust_env is False

    # redirecciones ────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _redirige(destino: str, estado: int = 302):
        return lambda r: httpx.Response(estado, headers={"Location": destino})

    @pytest.mark.parametrize("destino", [
        "http://127.0.0.1:8080/admin", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
        "file:///etc/passwd", "gopher://comicvine.gamespot.com/", "https://u:p@cdn.otro.example/x",
        "https://cdn.otro.example:8443/x", "http://2130706433/",
    ])
    async def test_una_redireccion_a_un_destino_no_permitido_se_corta_sin_segunda_peticion(self, destino):
        red = Red({"comicvine.gamespot.com": [PUBLICA], "cdn.otro.example": [OTRA_PUBLICA]},
                  handler=self._redirige(destino))
        with pytest.raises(UrlNoPermitidaError):
            await red.descargar(CV)
        assert len(red.peticiones) == 1

    async def test_una_redireccion_a_un_nombre_que_resuelve_a_una_direccion_interna_se_corta(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA], "interno.example": ["10.0.0.5"]},
                  handler=self._redirige("https://interno.example/x.jpg"))
        with pytest.raises(UrlNoPermitidaError, match="direccion_no_publica"):
            await red.descargar(CV)
        assert len(red.peticiones) == 1 and red.resoluciones == ["comicvine.gamespot.com", "interno.example"]

    async def test_cada_salto_se_resuelve_y_se_valida_otra_vez(self):
        """Rebinding en el segundo salto: el primer nombre es público y el del salto no."""
        saltos = iter([httpx.Response(302, headers={"Location": "https://cdn.otro.example/c.jpg"}),
                       httpx.Response(200, content=_png())])
        red = Red({"comicvine.gamespot.com": [PUBLICA], "cdn.otro.example": ["192.168.1.1"]},
                  handler=lambda r: next(saltos))
        with pytest.raises(UrlNoPermitidaError, match="direccion_no_publica"):
            await red.descargar(CV)
        assert len(red.peticiones) == 1

    async def test_una_redireccion_legitima_a_otro_cdn_publico_se_sigue(self):
        """Los CDN de portadas redirigen con normalidad: no se rompe la portada legítima."""
        saltos = iter([httpx.Response(302, headers={"Location": "https://cdn.otro.example/c.jpg"}),
                       httpx.Response(200, content=_png())])
        red = Red({"comicvine.gamespot.com": [PUBLICA], "cdn.otro.example": [OTRA_PUBLICA]},
                  handler=lambda r: next(saltos))
        assert await red.descargar(CV) == _png()
        assert [p.url.host for p in red.peticiones] == [PUBLICA, OTRA_PUBLICA]
        assert red.peticiones[1].headers["host"] == "cdn.otro.example"

    async def test_una_redireccion_relativa_se_resuelve_contra_el_nombre_no_contra_la_ip(self):
        saltos = iter([httpx.Response(301, headers={"Location": "/a/otra.jpg"}), httpx.Response(200, content=_png())])
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=lambda r: next(saltos))
        await red.descargar(CV)
        assert red.peticiones[1].url.path == "/a/otra.jpg" and red.peticiones[1].headers["host"] == "comicvine.gamespot.com"

    async def test_un_bucle_de_redirecciones_se_corta_en_el_maximo(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=self._redirige(CV))
        with pytest.raises(UrlNoPermitidaError, match="demasiadas_redirecciones"):
            await red.descargar(CV)
        assert len(red.peticiones) == MAX_SALTOS + 1

    async def test_una_redireccion_sin_destino_es_un_error_no_un_exito_vacio(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=lambda r: httpx.Response(302))
        with pytest.raises(UrlNoPermitidaError, match="redireccion_sin_destino"):
            await red.descargar(CV)

    @pytest.mark.parametrize("estado", [301, 302, 303, 307, 308])
    async def test_todos_los_codigos_de_redireccion_se_tratan_a_mano(self, estado):
        saltos = iter([httpx.Response(estado, headers={"Location": "/b.jpg"}), httpx.Response(200, content=_png())])
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=lambda r: next(saltos))
        await red.descargar(CV)
        assert len(red.peticiones) == 2

    # tamaño y errores ─────────────────────────────────────────────────────────────────────────

    async def test_un_content_length_enorme_se_rechaza(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]},
                  handler=lambda r: httpx.Response(200, headers={"Content-Length": str(10**9)}, content=b"x"))
        with pytest.raises(UrlNoPermitidaError, match="demasiado_grande"):
            await red.descargar(CV)

    @staticmethod
    def _por_trozos(*trozos: bytes):
        """Una respuesta SIN Content-Length (un generador): la única forma de llegar al tope en streaming."""
        async def _gen():
            for t in trozos:
                yield t

        def _h(r):
            respuesta = httpx.Response(200, content=_gen())
            assert "content-length" not in respuesta.headers
            return respuesta
        return _h

    async def test_un_cuerpo_sin_content_length_que_se_pasa_del_maximo_se_corta(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=self._por_trozos(b"x" * 600, b"x" * 600))
        with pytest.raises(UrlNoPermitidaError, match="demasiado_grande"):
            await red.descargar(CV, max_bytes=1024)

    async def test_un_cuerpo_justo_en_el_limite_se_acepta(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=self._por_trozos(b"x" * 512, b"x" * 512))
        assert len(await red.descargar(CV, max_bytes=1024)) == 1024

    async def test_un_content_length_justo_en_el_limite_se_acepta(self):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=lambda r: httpx.Response(200, content=b"x" * 1024))
        assert len(await red.descargar(CV, max_bytes=1024)) == 1024

    @pytest.mark.parametrize("estado", [404, 500])
    async def test_un_error_http_se_propaga(self, estado):
        red = Red({"comicvine.gamespot.com": [PUBLICA]}, handler=lambda r: httpx.Response(estado))
        with pytest.raises(httpx.HTTPStatusError):
            await red.descargar(CV)


# ── El punto común: `fetch_and_cache_cover` (también para los registros ya guardados) ────────────

@pytest.fixture
def red(monkeypatch):
    """Sustituye la red REAL del módulo (resolutor y cliente por defecto) por la falsa."""
    r = Red({"comicvine.gamespot.com": [PUBLICA], "s4.anilist.co": [OTRA_PUBLICA]})
    r.reales = []      # peticiones que NO pasaron por el transporte falso: serían red de verdad
    monkeypatch.setattr(url_portada, "resolver_dns", r.resolutor)
    monkeypatch.setattr(url_portada, "_cliente_por_defecto", r.cliente)

    original = httpx.AsyncClient.send

    async def vigilado(self, request, **kw):
        if not isinstance(self._transport, httpx.MockTransport):
            r.reales.append(request.url.host)
        return await original(self, request, **kw)
    monkeypatch.setattr(httpx.AsyncClient, "send", vigilado)
    return r


class TestPuntoComun:

    async def test_una_portada_legitima_se_descarga_y_se_guarda(self, red, tmp_path):
        dest = tmp_path / "c.jpg"
        assert await fetch_and_cache_cover(CV, dest) is True
        assert red.reales == [] and len(red.peticiones) == 1
        with Image.open(dest) as img:
            assert img.format == "JPEG"

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:9091/transmission/rpc", "http://169.254.169.254/latest/meta-data/",
        "https://evil.example/x.jpg", "file:///etc/passwd", "http://localhost:8989/api/v3/system/status",
        "https://user:clave@comicvine.gamespot.com/x.jpg",
    ])
    async def test_un_registro_ya_guardado_con_una_url_hostil_no_se_descarga(self, red, tmp_path, url):
        """El caso de los registros ANTERIORES a la corrección: la protección está donde se hace la petición."""
        dest = tmp_path / "c.jpg"
        assert await fetch_and_cache_cover(url, dest) is False
        assert not dest.exists() and red.peticiones == [] and red.resoluciones == []
        assert red.reales == [], "se hizo una petición REAL saltándose la política"

    async def test_un_nombre_permitido_que_apunta_dentro_no_se_descarga(self, red, tmp_path):
        red.dns["comicvine.gamespot.com"] = ["127.0.0.1"]
        assert await fetch_and_cache_cover(CV, tmp_path / "c.jpg") is False
        assert red.peticiones == []

    async def test_una_imagen_ilegible_no_se_guarda(self, red, tmp_path):
        red._handler = lambda r: httpx.Response(200, content=b"no es una imagen")
        dest = tmp_path / "c.jpg"
        assert await fetch_and_cache_cover(CV, dest) is False and not dest.exists()

    async def test_un_fallo_de_red_no_lanza_ni_cachea(self, tmp_path, monkeypatch):
        def _mal():
            raise httpx.ConnectTimeout("timeout")
        monkeypatch.setattr(url_portada, "resolver_dns", Red({"comicvine.gamespot.com": [PUBLICA]}).resolutor)
        monkeypatch.setattr(url_portada, "_cliente_por_defecto", _mal)
        dest = tmp_path / "c.jpg"
        assert await fetch_and_cache_cover(CV, dest) is False and not dest.exists()

    async def test_no_se_registra_la_url_entera_solo_el_host(self, red, tmp_path):
        """La URL puede llevar credenciales o claves en la consulta: el registro lleva solo el host y un código."""
        secreta = "https://user:CLAVE_SECRETA@comicvine.gamespot.com/x.jpg?apikey=CLAVE_SECRETA"
        with structlog.testing.capture_logs() as registros:
            await fetch_and_cache_cover(secreta, tmp_path / "c.jpg")
            red.dns["comicvine.gamespot.com"] = ["10.0.0.1"]
            await fetch_and_cache_cover("https://comicvine.gamespot.com/x.jpg?apikey=CLAVE_SECRETA", tmp_path / "d.jpg")
        assert registros, "no se registró nada: la prueba no mide nada"
        assert "CLAVE_SECRETA" not in repr(registros)
        assert all(r.get("host") == "comicvine.gamespot.com" for r in registros)

    async def test_el_semaforo_sigue_acotando_las_descargas(self):
        assert cover_mod._COVER_FETCH_SEMAPHORE._value == 2


# ── Puntos de entrada: se rechaza al ESCRIBIR y se ignora al LEER ────────────────────────────────

class _Sesion:
    def __init__(self, serie=None, existente=None):
        self.serie, self.existente, self.added = serie, existente, []
        self.flush = AsyncMock()

    async def get(self, _modelo, _id):
        return self.serie

    async def execute(self, _sentencia):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=self.existente)
        r.first = MagicMock(return_value=None)
        return r

    def add(self, obj):
        self.added.append(obj)

    async def refresh(self, obj):
        return None


class _Cliente:
    def __init__(self, sesion):
        self.sesion = sesion

    def __enter__(self):
        async def _get_db():
            yield self.sesion
        app.dependency_overrides[get_db] = _get_db
        return TestClient(app)

    def __exit__(self, *exc):
        app.dependency_overrides.pop(get_db, None)


class TestPuntosDeEntrada:

    @pytest.mark.parametrize("url", ["http://127.0.0.1/x.jpg", "https://evil.example/x.jpg", "file:///etc/passwd",
                                    "https://u:p@comicvine.gamespot.com/x.jpg"])
    def test_crear_serie_por_la_api_rechaza_una_portada_no_permitida(self, url):
        sesion = _Sesion()
        with _Cliente(sesion) as client:
            r = client.post("/api/series", json={"title": "Batman", "cover_url": url})
        assert r.status_code == 422 and sesion.added == []

    def test_crear_serie_por_la_api_acepta_una_portada_permitida(self):
        sesion = _Sesion()
        with _Cliente(sesion) as client:
            r = client.post("/api/series", json={"title": "Batman", "cover_url": CV})
        assert r.status_code == 201 and sesion.added[0].cover_url == CV

    def test_crear_serie_sin_portada_sigue_funcionando(self):
        with _Cliente(_Sesion()) as client:
            assert client.post("/api/series", json={"title": "Batman"}).status_code == 201

    @pytest.mark.parametrize("url", ["http://169.254.169.254/x", "https://evil.example/x.jpg"])
    def test_editar_serie_por_la_api_rechaza_una_portada_no_permitida(self, url):
        serie = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        with _Cliente(_Sesion(existente=serie)) as client:
            r = client.patch(f"/api/series/{serie.id}", json={"cover_url": url})
        assert r.status_code == 422 and serie.cover_url is None

    def test_editar_serie_permite_borrar_la_portada(self):
        serie = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, cover_url=CV)
        with _Cliente(_Sesion(existente=serie)) as client:
            r = client.patch(f"/api/series/{serie.id}", json={"cover_url": None})
        assert r.status_code == 200 and serie.cover_url is None

    @pytest.mark.parametrize("url", ["http://127.0.0.1:9091/x.jpg", "https://evil.example/x.jpg"])
    def test_el_alta_de_descubrir_rechaza_una_portada_no_permitida(self, url):
        sesion = _Sesion()
        with _Cliente(sesion) as client:
            r = client.post("/ui/descubrir/crear", data={
                "source": "comic_vine", "external_id": "1234", "title": "Batman",
                "tradition": "american", "cover_url": url})
        assert r.status_code == 400 and sesion.added == []

    def test_el_alta_de_descubrir_acepta_una_portada_permitida(self):
        sesion = _Sesion()
        with _Cliente(sesion) as client:
            r = client.post("/ui/descubrir/crear", data={
                "source": "comic_vine", "external_id": "1234", "title": "Batman",
                "tradition": "american", "cover_url": CV})
        assert r.status_code == 200 and sesion.added[0].cover_url == CV

    def test_un_registro_guardado_con_una_url_hostil_no_dispara_ninguna_peticion_desde_la_cascada(
            self, tmp_path, monkeypatch):
        """GET /ui/series/{id}/portada con un `cover_url` anterior a la corrección: 404 y NINGUNA petición."""
        from zascarr.config import get_settings
        peticiones = []

        def _cliente_que_no_debe_usarse():
            peticiones.append("cliente")
            raise AssertionError("no debía crearse ningún cliente HTTP")
        monkeypatch.setattr(url_portada, "_cliente_por_defecto", _cliente_que_no_debe_usarse)
        monkeypatch.setattr("zascarr.web.series.get_settings",
                            lambda: get_settings().model_copy(update={"covers_cache_path": tmp_path}))
        serie = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                       cover_url="http://169.254.169.254/latest/meta-data/")
        with _Cliente(_Sesion(serie=serie)) as client:
            r = client.get(f"/ui/series/{serie.id}/portada")
        assert r.status_code == 404 and peticiones == []


# ── La verificación del certificado con la IP fijada (servidor TLS LOCAL real) ───────────────────

def _certificado(directorio, nombre: str):
    clave, cert = directorio / f"{nombre}.key", directorio / f"{nombre}.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(clave),
                    "-out", str(cert), "-days", "1", "-subj", f"/CN={nombre}",
                    "-addext", f"subjectAltName=DNS:{nombre}"],
                   check=True, capture_output=True)
    return clave, cert


class _Manejador(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(_png())

    def log_message(self, *a):
        pass


@pytest.mark.skipif(shutil.which("openssl") is None, reason="requiere el binario openssl")
class TestTlsConLaDireccionFijada:
    """El riesgo del diseño: conectar a una IP podría verificar el certificado contra la IP en lugar del nombre
    (y entonces fallarían todas las portadas legítimas) o no verificarlo. Se comprueba con un servidor real."""

    @staticmethod
    def _servidor(clave, cert):
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.load_cert_chain(str(cert), str(clave))
        servidor = HTTPServer(("127.0.0.1", 0), _Manejador)
        servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        return servidor, hilo

    async def test_el_certificado_se_verifica_contra_el_nombre_y_no_contra_la_ip(self, tmp_path):
        clave, cert = _certificado(tmp_path, "comicvine.gamespot.com")
        servidor, hilo = self._servidor(clave, cert)
        try:
            confianza = ssl.create_default_context(cafile=str(cert))
            async with httpx.AsyncClient(verify=confianza, trust_env=False) as cliente:
                estado, destino, cuerpo = await url_portada._pedir(
                    cliente, "https", "comicvine.gamespot.com", "127.0.0.1", servidor.server_port, "/x.png", 1 << 20)
            assert (estado, destino, cuerpo) == (200, None, _png())
        finally:
            servidor.shutdown()
            hilo.join(timeout=5)

    async def test_un_certificado_de_otro_nombre_se_rechaza(self, tmp_path):
        clave, cert = _certificado(tmp_path, "otro.example")
        servidor, hilo = self._servidor(clave, cert)
        try:
            confianza = ssl.create_default_context(cafile=str(cert))
            async with httpx.AsyncClient(verify=confianza, trust_env=False) as cliente:
                with pytest.raises(httpx.ConnectError):
                    await url_portada._pedir(
                        cliente, "https", "comicvine.gamespot.com", "127.0.0.1", servidor.server_port, "/x.png", 1 << 20)
        finally:
            servidor.shutdown()
            hilo.join(timeout=5)
