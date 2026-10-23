"""#311 — la imagen de relleno de Comic Vine («Blank!») no es una portada.

Cuando una serie no tiene portada, Comic Vine devuelve en `image.*_url` su imagen de relleno
(`…/6373148-blank.png`, en cualquier tamaño). ZascArr la enseñaba como si fuera la del tebeo y el
coleccionista creía que algo estaba roto. Aquí se fija que el cliente la convierte en «sin portada»,
sin tocar las portadas reales. Sin red: `_get` se sustituye por una respuesta fija.

Evidencia del nombre del fichero (sin consultar la fuente): varios proyectos públicos independientes la
detectan por `6373148-blank.png` en `original`, `scale_medium`, `square_avatar`…, y los datos simulados de
un cliente de la API la llevan en `image.*_url`. Históricamente las imágenes también se sirvieron desde
`comicvine1.cbsistatic.com`: por eso se compara el NOMBRE del fichero, no el servidor.
"""
from __future__ import annotations

import pytest

from zascarr.services.comic_vine import ComicVineClient, _parse_issue, es_portada_de_relleno

RELLENO = "https://comicvine.gamespot.com/a/uploads/{tam}/11122/111222211/6373148-blank.png"
REAL = "https://comicvine.gamespot.com/a/uploads/scale_medium/6/67663/2079617-flash.jpg"


@pytest.mark.parametrize("url", [
    RELLENO.format(tam="scale_medium"), RELLENO.format(tam="original"), RELLENO.format(tam="square_avatar"),
    "https://comicvine1.cbsistatic.com/uploads/scale_medium/11122/111222211/6373148-blank.png",
    RELLENO.format(tam="scale_medium") + "?v=2",
])
def test_la_imagen_de_relleno_se_reconoce_en_cualquier_tamano_y_servidor(url):
    assert es_portada_de_relleno(url)


@pytest.mark.parametrize("url", [
    None, "", REAL, "https://comicvine.gamespot.com/a/uploads/scale_medium/1/2/blank-page.png",
    "https://comicvine.gamespot.com/a/uploads/scale_medium/1/2/16373148-blank.png",
])
def test_una_portada_real_o_ausente_no_es_relleno(url):
    assert not es_portada_de_relleno(url)


def _cliente_con(respuesta: dict) -> ComicVineClient:
    cliente = ComicVineClient.__new__(ComicVineClient)

    async def _get(_ruta, _params):
        return respuesta
    cliente._get = _get                     # type: ignore[method-assign]
    return cliente


async def test_buscar_series_convierte_el_relleno_en_sin_portada_y_conserva_las_reales():
    cliente = _cliente_con({"error": "OK", "results": [
        {"id": 1, "name": "Flash", "image": {"medium_url": RELLENO.format(tam="scale_medium")}},
        {"id": 2, "name": "Flash", "image": {"medium_url": REAL}},
        {"id": 3, "name": "Flash", "image": None},
    ]})
    sin, con, nada = await cliente.search_series("flash")
    assert sin.image_url is None
    assert con.image_url == REAL
    assert nada.image_url is None


def test_un_numero_con_la_imagen_de_relleno_queda_sin_portada():
    assert _parse_issue({"id": 9, "image": {"medium_url": RELLENO.format(tam="scale_medium")}}).image_url is None
    assert _parse_issue({"id": 9, "image": {"medium_url": REAL}}).image_url == REAL
