"""SCR4 — charset real del foro IPB (fixtures latin-1/cp1252, sin red)."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import structlog

from zascarr.services.forum_scraper import (
    ForumScraper,
    OrigenNoPermitidoError,
    analizar_charset,
    decodificar_respuesta,
    detectar_charset,
)

FIXTURES = Path(__file__).parent / "fixtures" / "foro"
BASE = "http://foro.example/forum"


@pytest.fixture(autouse=True)
def _foro_encendido(monkeypatch):
    """La puerta de fuente apagada lee la configuración real: aquí, foro encendido."""
    from types import SimpleNamespace

    monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
        forum_enabled=True, forum_url=BASE, forum_rate_limit=2.0,
        forum_search_rate_limit=25.0))


def _bytes(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        self.t += segundos


def _scraper(handler, *, reloj=None, **kw):
    reloj = reloj or Reloj()
    return ForumScraper(
        BASE, rate_limit=0,
        crear_cliente=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False),
        reloj=reloj, dormir=reloj.dormir, espera_max_s=kw.pop("espera_max_s", 300.0), **kw)


def _pagina(contenido: bytes, *, content_type: str = "text/html", **kw) -> httpx.Response:
    return httpx.Response(200, content=contenido,
                          headers={"content-type": content_type}, **kw)


def _respuesta(contenido: bytes = b"<html></html>", *, content_type: str = "text/html",
               url: str = f"{BASE}/index.php") -> httpx.Response:
    return httpx.Response(200, content=contenido,
                          headers={"content-type": content_type},
                          request=httpx.Request("GET", url))


# ── AC-CHA-1/2/3: prioridad cabecera → meta → cp1252 ───────────────────────────────────────

def test_ac_cha_1_la_cabecera_manda_si_trae_charset():
    r = _respuesta(b"<html><head><meta charset='cp1252'></head></html>",
                   content_type="text/html; charset=UTF-8")
    assert detectar_charset(r) == "utf-8"


def test_ac_cha_2_sin_charset_en_cabecera_usa_la_meta_latin1():
    cabecera, meta, usado = analizar_charset(_respuesta(
        _bytes("login_latin1.html"), content_type="text/html"))
    assert cabecera is None and meta == "iso8859-1" and usado == "iso8859-1"


def test_ac_cha_3_sin_cabecera_ni_meta_cae_en_cp1252_con_aviso():
    with structlog.testing.capture_logs() as registros:
        usado = detectar_charset(_respuesta(b"<html><body>sin meta</body></html>",
                                            content_type="text/html"))
    assert usado == "cp1252"
    assert any(r["event"] == "forum.charset_no_declarado" for r in registros)


def test_un_charset_desconocido_en_la_fuente_no_se_usa():
    r = _respuesta(b"<html><meta charset='inventado-99'></html>")
    assert detectar_charset(r) == "cp1252"


# ── AC-CHA-4/5: decodificar tildes/ñ y el byte 0x80 de cp1252 ─────────────────────────────

def test_ac_cha_4_los_bytes_latin1_se_decodifican_sin_caracter_de_reemplazo():
    texto, usado = decodificar_respuesta(_respuesta(b"Capit\xe1n A\xf1o"))
    assert usado == "cp1252" or usado.startswith("iso")
    assert "Capitán Año" in texto and "�" not in texto


def test_ac_cha_5_cp1252_decodifica_el_byte_80():
    texto, _ = decodificar_respuesta(_respuesta(b"N\xfamero \x80 de A\xf1o"))
    assert "€" in texto and "Año" in texto


# ── Login: action real, charset del POST y s= conservado ──────────────────────────────────

async def test_ac_cha_6_el_login_usa_la_accion_real_y_el_post_va_en_latin1():
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        if request.method == "GET":
            return _pagina(_bytes("login_latin1.html"), content_type="text/html")
        assert "act=Login" in str(request.url) and "s=SESION123" in str(request.url)
        return httpx.Response(
            302, headers={"location": "/forum/index.php",
                          "set-cookie": "member_id=7; Path=/; HttpOnly"})

    scraper = _scraper(handler)
    assert await scraper.login("Capitán", "Año") is True

    post = next(p for p in peticiones if p.method == "POST")
    assert post.headers["content-type"] == (
        "application/x-www-form-urlencoded; charset=iso8859-1")
    # El cuerpo crudo lleva %E1 (%F1), no la codificación UTF-8 %C3%A1.
    assert b"Capit%E1n" in post.content and b"PassWord=A%F1o" in post.content
    assert b"Capit%C3%A1n" not in post.content
    assert b"s=SESION123" in post.content and b"PassWord=A%F1o" in post.content


async def test_ac_cha_6_una_accion_de_otro_origen_se_rechaza():
    html = _bytes("login_latin1.html").replace(
        b'action="/forum/index.php?act=Login&amp;CODE=01&amp;s=SESION123"',
        b'action="https://atacante.example/login"')

    def handler(_request: httpx.Request) -> httpx.Response:
        return _pagina(html, content_type="text/html")

    with pytest.raises(OrigenNoPermitidoError, match="otro_origen"):
        await _scraper(handler).login("usuario", "clave")


# ── Búsqueda: la query viaja en el charset detectado ──────────────────────────────────────

async def test_la_busqueda_codifica_la_query_en_el_charset_detectado():
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return _pagina(_bytes("cero_resultados.html"), content_type="text/html")

    scraper = _scraper(handler)
    scraper._charset = "iso8859-1"
    assert await scraper.use_ipb_search("Capitán", abrir_temas=False) == []
    assert "keywords=Capit%E1n" in urls[0]


async def test_el_titulo_del_resultado_latin1_se_lee_sin_caracteres_rotos():
    def handler(request: httpx.Request) -> httpx.Response:
        if "act=Search" in str(request.url):
            return _pagina(_bytes("resultados_latin1.html"), content_type="text/html")
        return _pagina(b"<html></html>")

    scraper = _scraper(handler)
    resultados = await scraper.use_ipb_search("Año", abrir_temas=False)
    assert [r.topic_title for r in resultados] == ["Año Uno: Capitán", "Capitán Año"]
    assert all("�" not in r.topic_title for r in resultados)
