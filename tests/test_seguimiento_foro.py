"""#993: listado de showforum y extracción de enlaces (fixtures sintéticos, sin red)."""
from __future__ import annotations

from pathlib import Path

import httpx

from zascarr.services.forum_scraper import ForumScraper, temas_de_foro

FIXTURES = Path(__file__).parent / "fixtures" / "foro"

HTML_FORO = """
<table>
<tr class="row1"><td><a href="index.php?showtopic=10&amp;view=getnewpost"><img src="n.gif"></a><span id="tid-span-10"><a id="tid-link-10" href="index.php?showtopic=10" title="iniciado: Nov 14 2019, 14:38">Batman #12</a></span><span class="minipagelink"><a href="index.php?showtopic=10&amp;st=0">1</a></span><div class="desc">desc</div></td><td><span class="lastaction">Hoy, 10:32</span></td></tr>
<tr class="row1"><td><a href="index.php?showtopic=11">Tema viejo</a></td><td>15/11/2026</td></tr>
<tr class="row1"><td><a href="index.php?showtopic=12">Tema actualizado</a></td><td>Ayer, 20:01</td></tr>
</table>
"""

#: Fila real del foro: el primer `showtopic` es la imagen «nuevo mensaje» y la
#: última actividad viene en inglés («5th August 2026 - 18:24»).
HTML_FORO_REAL = """
<table><tr>
<td class="row1"><a href='http://foro/index.php?showtopic=84784&amp;view=getnewpost'><img src='nuevo.gif'></a>
<span id='tid-span-84784'><a id="tid-link-84784" href="http://foro/index.php?showtopic=84784" title="Este tema fue iniciado: Nov 14 2019, 14:38">Emulecollections de completos</a></span>
<span class="minipagelink"><a href="http://foro/index.php?showtopic=84784&amp;st=0&amp;start=0">1</a></span>
<div class="desc">A dos clics</div></td>
<td align="center" class="row2"><a href='http://foro/index.php?showuser=95657'>Hekutorukun</a><br /><span style="color:#666">Nov 14 2019, 14:38</span></td>
<td class="row2"><span class="lastaction">5th August 2026 - 18:24<br /><a href='http://foro/index.php?showtopic=84784&amp;view=getlastpost'>Último mensaje:</a></span></td>
</tr></table>
"""


def test_parser_de_temas():
    temas = temas_de_foro(HTML_FORO)
    assert [t[1] for t in temas] == [10, 11, 12]
    assert temas[0][2] == "Batman #12"
    assert temas[0][3] == "Hoy, 10:32"


def test_parser_real_prioriza_el_titulo_y_lee_la_fecha_inglesa():
    temas = temas_de_foro(HTML_FORO_REAL)
    assert len(temas) == 1
    href, tema_id, titulo, actividad = temas[0]
    assert tema_id == 84784
    assert titulo == "Emulecollections de completos"
    assert actividad == "5th August 2026 - 18:24"
    assert "view=" not in href


async def test_listar_temas_usa_una_get_de_lectura_y_no_la_busqueda():
    vistas: list[str] = []

    def _transporte(request):
        vistas.append(str(request.url))
        return httpx.Response(200, text=HTML_FORO,
                              headers={"content-type": "text/html"})

    scraper = ForumScraper("https://foro.example", rate_limit=0,
                           permitir_apagada=True,
                           crear_cliente=lambda: httpx.AsyncClient(
                               transport=httpx.MockTransport(_transporte)))
    temas = await scraper.listar_temas(foro_id=5, limite=2)
    assert len(temas) == 2 and temas[0].id == 10
    assert vistas == ["https://foro.example/index.php?showforum=5"]
    assert "Search" not in vistas[0]


async def test_leer_tema_extrae_ed2k_y_magnet():
    html = ('<a href="magnet:?xt=urn:btih:abc&dn=Batman%2012.cbz">m</a>'
            '<a href="ed2k://|file|Batman%2013.cbz|1|H|/">e</a>')
    scraper = ForumScraper("https://foro.example", rate_limit=0,
                           permitir_apagada=True,
                           crear_cliente=lambda: httpx.AsyncClient(
                               transport=httpx.MockTransport(
                                   lambda _r: httpx.Response(200, text=html,
                                                             headers={"content-type": "text/html"}))))
    resultado = await scraper.leer_tema("https://foro.example/index.php?showtopic=10")
    assert resultado.magnet_links and resultado.ed2k_links


# ── #1017: humo del parser contra un showforum real anonimizado ─────────────


def test_humo_parser_showforum_real_anonimizado():
    """Una captura real de IPB, sin red: el parser saca los temas, prefiere el
    `tid-link` (no la imagen «nuevo mensaje») y lee las tres formas de actividad."""
    html = (FIXTURES / "showforum_real_anonimizado.html").read_text(encoding="utf-8")

    temas = temas_de_foro(html)

    assert [tema[1] for tema in temas] == [90001, 90002, 90003]
    assert [tema[2] for tema in temas] == [
        "E-links diarios — 17/11/2026",
        "Cómics & novelas gráficas",
        "Tema con sesión en el enlace",
    ]
    assert [tema[3] for tema in temas] == [
        "Hoy, 10:32",
        "Ayer, 20:01",
        "5th August 2026 - 18:24",
    ]
    assert all("view=" not in tema[0] for tema in temas)


async def test_humo_listar_temas_del_showforum_real_anonimizado():
    """El mismo fixture a través de `listar_temas`: una GET de lectura y el
    límite aplicado sobre las filas reales."""
    html = (FIXTURES / "showforum_real_anonimizado.html").read_text(encoding="utf-8")
    vistas: list[str] = []

    def _transporte(request):
        vistas.append(str(request.url))
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    scraper = ForumScraper("https://foro.example", rate_limit=0,
                           permitir_apagada=True,
                           crear_cliente=lambda: httpx.AsyncClient(
                               transport=httpx.MockTransport(_transporte)))
    temas = await scraper.listar_temas(foro_id=5, limite=2)

    assert [tema.id for tema in temas] == [90001, 90002]
    assert vistas == ["https://foro.example/index.php?showforum=5"]
    assert "Search" not in vistas[0]
