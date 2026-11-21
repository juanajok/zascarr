"""Contexto de retorno Biblioteca / Colección → ficha (BL-IT03 #286, UATP-02).

La URL es la única fuente de contexto: la tarjeta lleva `volver` con la URL
canónica de la Biblioteca (o de la Colección) y el ancla de la serie. La ficha
valida ese valor y solo lo usa si es un destino local con estado canónico.
No hay historial paralelo, estado global, redirección externa ni JavaScript.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlsplit
from uuid import UUID

#: Tope de longitud del `volver` ya codificado: una `q` canónica de 200
#: caracteres no latinos puede superar 2000 al ir dentro de la query.
MAX_VOLVER = 4096

_UUID = (r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
         r"[0-9a-f]{4}-[0-9a-f]{12}")
_ANCLA_DE_SERIE = re.compile(rf"^serie-({_UUID})$")
_RUTA_DE_COLECCION = re.compile(rf"^/ui/colecciones/({_UUID})$")


def url_de_ficha(series_id: UUID | str, url_biblioteca: str) -> str:
    """URL de la ficha con el destino canónico, `foco` y el ancla de su tarjeta."""
    sid = str(UUID(str(series_id)))
    separador = "&" if "?" in url_biblioteca else "?"
    destino = f"{url_biblioteca}{separador}foco={sid}#serie-{sid}"
    return f"/ui/series/{sid}?volver={quote(destino, safe='')}"


def _controles(valor: str) -> bool:
    return any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in valor)


def _pares(query: str) -> list[tuple[str, str]] | None:
    try:
        pares = parse_qsl(query, keep_blank_values=True)
    except ValueError:
        return None
    nombres = [nombre for nombre, _ in pares]
    if len(set(nombres)) != len(nombres) or any(not nombre for nombre in nombres):
        return None
    if any(_controles(valor) for _, valor in pares):
        return None
    return pares


def _foco_valido(foco: str, fragmento: str | None, series_id: UUID | str | None) -> bool:
    try:
        if str(UUID(foco)) != foco:
            return False
    except (ValueError, TypeError):
        return False
    if fragmento is not None:
        ancla = _ANCLA_DE_SERIE.fullmatch(fragmento)
        if ancla is None or ancla.group(1) != foco:
            return False
    return series_id is None or str(series_id) == foco


def _biblioteca(valor: str, partes, series_id: UUID | str | None) -> str | None:
    from zascarr.web.library import consulta_canonica_de_biblioteca

    fragmento = partes.fragment or None
    if fragmento is not None and _ANCLA_DE_SERIE.fullmatch(fragmento) is None:
        return None
    if _controles(partes.query):
        return None
    pares = _pares(partes.query)
    if pares is None:
        return None
    if "#" in valor and fragmento is None:
        return None
    foco = None
    query_estado = partes.query
    if any(nombre == "foco" for nombre, _ in pares):
        if [nombre for nombre, _ in pares].count("foco") != 1 or pares[-1][0] != "foco":
            return None
        foco = pares[-1][1]
        if not _foco_valido(foco, fragmento, series_id):
            return None
        sufijo = f"foco={foco}"
        if partes.query == sufijo:
            query_estado = ""
        elif partes.query.endswith("&" + sufijo):
            query_estado = partes.query[:-len(sufijo) - 1]
        else:
            return None
    if query_estado:
        if consulta_canonica_de_biblioteca(query_estado) != query_estado:
            return None
    elif "?" in valor and not (foco is not None and partes.query == f"foco={foco}"):
        # `/ui/biblioteca` (sin `?`) es la forma por defecto; `?` vacío no.
        return None
    if (fragmento is not None and series_id is not None
            and fragmento != f"serie-{series_id}"):
        return None
    return valor


def _coleccion(valor: str, partes, coleccion_id: str) -> str | None:
    from zascarr.web.colecciones import consulta_canonica_de_coleccion

    if "#" in valor:
        return None
    if "?" not in valor:
        return valor
    if not partes.query:
        return None
    if consulta_canonica_de_coleccion(coleccion_id, partes.query) != partes.query:
        return None
    return valor


def volver_segura(valor: str | None, series_id: UUID | str | None = None) -> str | None:
    """La URL de vuelta si es local y canónica; `None` en cualquier otro caso.

    No repara ni normaliza: rechaza `//`, `%` en la ruta, controles, espacios,
    barra invertida, `..`, query no canónica, `foco` incoherente, ancla ajena,
    fragmento en Colección y banderas de un solo uso. Mantiene ancla y el
    estado de Biblioteca/Colección.
    """
    if not valor or len(valor) > MAX_VOLVER:
        return None
    if not valor.startswith("/") or valor.startswith("//"):
        return None
    if any(caracter.isspace() or caracter == "\\"
           for caracter in valor):
        return None
    if _controles(valor):
        return None
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    if partes.scheme or partes.netloc:
        return None
    ruta = partes.path
    if ("%" in ruta or "//" in ruta or ".." in ruta.split("/")
            or "." in ruta.split("/")):
        return None
    if partes.path == "/ui/biblioteca":
        return _biblioteca(valor, partes, series_id)
    coleccion = _RUTA_DE_COLECCION.fullmatch(partes.path)
    if coleccion is not None:
        return _coleccion(valor, partes, coleccion.group(1))
    return None
