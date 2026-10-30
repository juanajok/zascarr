"""Marcador de la portada que falta (U-portada): color e inicial, decididos en el servidor.

La tarjeta lleva SIEMPRE un marcador (color pleno con trama y la inicial de la serie) y, encima, la
`<img>` de la portada. Si la imagen carga, lo tapa; si da 404 se ve el marcador, sin JavaScript.
El servidor no puede saber de antemano si habrá portada (la caché se llena al pedirla), así que el
marcador no «sustituye» a la imagen: espera debajo.

El color no significa nada (no codifica tradición ni estado): solo reparte tres tintas para que una
biblioteca sin portadas no sea una pared gris. Tiene que ser ESTABLE entre peticiones y procesos,
así que nunca `hash()` de Python (cambia con `PYTHONHASHSEED`).
"""
from __future__ import annotations

import unicodedata
import zlib
from dataclasses import dataclass
from uuid import UUID

#: Tintas del marcador, en el orden en que reparte `clave % 3` (clases `.portada-c|m|y`).
COLORES = ("c", "m", "y")
#: Inicial cuando el título no tiene ningún carácter alfanumérico («¡¡¡», «···»).
INICIAL_DE_RESPALDO = "·"


@dataclass(frozen=True)
class MarcaDePortada:
    color: str      # "c" | "m" | "y"
    inicial: str    # un carácter en mayúscula, decorativo (aria-hidden)


def inicial_de_portada(titulo: str | None) -> str:
    """Primer carácter alfanumérico del título, en mayúscula («¡Zas!» → Z, «1984» → 1,
    «Ásterix» → Á). Sin ninguno, un punto medio."""
    for c in unicodedata.normalize("NFC", titulo or ""):
        if c.isalnum():
            return c.upper()
    return INICIAL_DE_RESPALDO


def color_de_portada(clave: UUID | str | None, titulo: str | None = None) -> str:
    """Con identificador (`series.id`), `id % 3`; sin él (candidatas de una búsqueda), un CRC32
    del título sin mayúsculas ni tildes, estable entre procesos y reinicios."""
    if isinstance(clave, UUID):
        return COLORES[clave.int % 3]
    if clave:
        try:
            return COLORES[UUID(str(clave)).int % 3]
        except ValueError:
            titulo = str(clave)
    base = unicodedata.normalize("NFKD", titulo or "").casefold()
    sin_tildes = "".join(c for c in base if not unicodedata.combining(c))
    return COLORES[zlib.crc32(sin_tildes.encode("utf-8")) % 3]


def marca_de_portada(titulo: str | None, clave: UUID | str | None = None) -> MarcaDePortada:
    return MarcaDePortada(color=color_de_portada(clave, titulo), inicial=inicial_de_portada(titulo))
