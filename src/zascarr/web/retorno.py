"""Contexto de retorno Biblioteca → ficha → Biblioteca (BL-IT03, #286).

La URL es la única fuente de contexto: la tarjeta lleva `volver` con la URL
canónica de la Biblioteca y el ancla de la serie. La ficha valida ese valor y
solo lo usa si es una ruta local de `/ui/biblioteca` con parámetros conocidos.
No hay historial paralelo, estado global, redirección externa ni JavaScript.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, urlsplit
from uuid import UUID

#: Parámetros que la URL de retorno puede llevar. Son los de la Biblioteca;
#: cualquier otro se rechaza en vez de reenviarlo a ciegas.
PARAMETROS_DE_VUELTA = frozenset({
    "q", "tradition", "publisher_id", "character_id", "story_arc_id", "page",
    "vista",
})

_ANCLA_DE_SERIE = re.compile(r"^serie-[0-9a-fA-F-]{36}$")
_RUTA_DE_COLECCION = re.compile(
    r"^/ui/colecciones/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def url_de_ficha(series_id: UUID | str, url_biblioteca: str) -> str:
    """URL de la ficha que recuerda de dónde vino, con ancla para enfocar la tarjeta."""
    destino = f"{url_biblioteca}#serie-{series_id}"
    return f"/ui/series/{series_id}?volver={quote(destino, safe='')}"


def volver_segura(valor: str | None, series_id: UUID | str | None = None) -> str | None:
    """La URL de vuelta si es local y tiene el contrato esperado; si no, `None`.

    Se rechazan URLs absolutas, esquemas (`javascript:`, `https:`), rutas ajenas,
    parámetros desconocidos y anclas que no sean `serie-<uuid>`. Si se pasa
    `series_id`, el ancla debe ser la de ESA ficha: un ancla de otra serie no
    aterrizaría en ninguna tarjeta y se descarta. No se normaliza ni se reescribe
    el valor: se devuelve tal cual para que la Biblioteca aplique su propia
    validación al abrirlo.
    """
    if not valor or len(valor) > 2000:
        return None
    if any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in valor):
        return None
    partes = urlsplit(valor)
    if partes.scheme or partes.netloc:
        return None
    if _RUTA_DE_COLECCION.fullmatch(partes.path):
        # Colección → serie: solo la ficha de la colección, sin query ni ancla.
        return valor if not partes.query and not partes.fragment else None
    if partes.path != "/ui/biblioteca":
        return None
    if partes.fragment:
        if not _ANCLA_DE_SERIE.fullmatch(partes.fragment):
            return None
        if series_id is not None and partes.fragment != f"serie-{series_id}":
            return None
    parametros = parse_qs(partes.query, keep_blank_values=True)
    if set(parametros) - PARAMETROS_DE_VUELTA:
        return None
    return valor
