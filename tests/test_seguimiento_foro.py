"""#993: listado de showforum y extracción de enlaces (fixtures sintéticos, sin red)."""
from __future__ import annotations

import httpx

from zascarr.services.forum_scraper import ForumScraper, temas_de_foro

HTML_FORO = """
<table>
<tr class="row1"><td><a href="index.php?showtopic=10&amp;s=xyz">Batman #12</a></td><td>Hoy, 10:32</td></tr>
<tr class="row1"><td><a href="index.php?showtopic=11">Tema viejo</a></td><td>15/11/2026</td></tr>
<tr class="row1"><td><a href="index.php?showtopic=12">Tema actualizado</a></td><td>Ayer, 20:01</td></tr>
</table>
"""


def test_parser_de_temas():
    temas = temas_de_foro(HTML_FORO)
    assert [t[1] for t in temas] == [10, 11, 12]
    assert temas[0][2] == "Batman #12"
    assert temas[0][3] == "Hoy, 10:32"


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
