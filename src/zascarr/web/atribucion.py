"""Atribución legal de las wikis de Fandom en las vistas de la biblioteca (SCR2).

DC Database y Marvel Database publican su texto bajo CC-BY-SA 3.0. Toda vista que muestre
datos suyos enlaza **dos** cosas: el artículo original (la página de la wiki, que es la
identidad guardada) y la licencia. La portada NO va bajo esa licencia (*fair use* editorial)
y aquí nunca se enlaza una imagen: solo los dos enlaces de texto, sin hotlinking.

Vive fuera de `web/series.py` para que la ficha de serie, la de número y las sagas usen el
mismo helper sin que los routers web se importen entre sí.
"""
from __future__ import annotations

from urllib.parse import quote

#: Fuente de Fandom → (nombre legible de cara a la persona, base de las URLs de artículo).
FUENTES_DE_FANDOM: dict[str, tuple[str, str]] = {
    "fandom_dc": ("DC Database", "https://dc.fandom.com/wiki/"),
    "fandom_marvel": ("Marvel Database", "https://marvel.fandom.com/wiki/"),
}

#: Fuente → columna de identidad del modelo (una serie o un número usa como mucho una).
COLUMNAS_DE_FANDOM: tuple[tuple[str, str], ...] = (
    ("fandom_dc", "fandom_dc_slug"),
    ("fandom_marvel", "fandom_marvel_slug"),
)

URL_DE_LA_LICENCIA_CC_BY_SA = "https://creativecommons.org/licenses/by-sa/3.0/"


def enlace_de_atribucion(fuente: str | None,
                         pagina: str | None) -> dict[str, str] | None:
    """Datos del doble enlace legal de una página de wiki, o None si no es atribuible.

    El título de la página es el propio slug de identidad; se convierte a la forma de las
    URLs de MediaWiki (espacios como `_`). Solo devuelve texto y URLs: nunca una imagen.
    """
    if not fuente or not pagina or fuente not in FUENTES_DE_FANDOM:
        return None
    titulo = str(pagina).strip()
    if not titulo:
        return None
    nombre, base = FUENTES_DE_FANDOM[fuente]
    return {
        "fuente": fuente,
        "nombre": nombre,
        "titulo": titulo,
        "url_articulo": base + quote(titulo.replace(" ", "_"), safe="/:"),
        "url_licencia": URL_DE_LA_LICENCIA_CC_BY_SA,
    }


def atribucion_fandom(entidad) -> dict[str, str] | None:
    """Atribución de una serie o un número identificado por una wiki de Fandom.

    La identidad vive en las columnas `fandom_dc_slug`/`fandom_marvel_slug` (el enricher
    escribe ahí el título de la página al mismo tiempo que `metadata_source`). Sin esa
    página no hay artículo al que atribuir y no se inventa uno.
    """
    for fuente, columna in COLUMNAS_DE_FANDOM:
        datos = enlace_de_atribucion(fuente, getattr(entidad, columna, None))
        if datos is not None:
            return datos
    return None


def atribucion_de_arco(metadata_: object) -> dict[str, str] | None:
    """Atribución de una saga creada por el enricher.

    El enricher guarda la página del arco en `metadata_["fandom_dc"]` (solo DC declara arcos
    en su plantilla de volumen); las sagas manuales no tienen esa clave y no se atribuyen.
    """
    metadata = metadata_ if isinstance(metadata_, dict) else {}
    return enlace_de_atribucion("fandom_dc", metadata.get("fandom_dc"))
