"""Normalización pura de fichas de serie a `edition_scope`/`work_scope`.

Solo mapea lo que la fuente declara. Un campo ausente no se rellena con una
heurística; `normalizado` es un mapa de datos, no una decisión de aplicación.
Las funciones aceptan objetos de los clientes o mappings equivalentes para que
los tests no necesiten red.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Claves de normalización; deben coincidir con el mapa de la especificación v2.1.
EDITION_FIELDS = (
    "title", "start_year", "end_year", "publisher_name", "imprint_name",
    "country", "language", "edition_kind", "total_issues",
)
WORK_FIELDS = ("description", "genres")


def _leer(ficha: object, nombre: str) -> Any:
    if isinstance(ficha, Mapping):
        return ficha.get(nombre)
    return getattr(ficha, nombre, None)


def _texto(valor: object) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _entero(valor: object) -> int | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _anio(valor: object) -> int | None:
    numero = _entero(valor)
    return numero if numero is not None and 1000 <= numero <= 9999 else None


def _sin_vacios(datos: dict[str, Any]) -> dict[str, Any]:
    return {clave: valor for clave, valor in datos.items() if valor is not None}


def normalizar_comic_vine_serie(ficha: object) -> dict[str, Any]:
    """CVVolume/CVResult → campos. No inventa país/idioma/formato."""
    edition = _sin_vacios({
        "title": _texto(_leer(ficha, "name")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "publisher_name": _texto(_leer(ficha, "publisher")),
        "total_issues": _entero(_leer(ficha, "count_of_issues")),
    })
    raw = _leer(ficha, "raw")
    work: dict[str, Any] = {}
    if isinstance(raw, Mapping):
        work["description"] = _texto(raw.get("description") or raw.get("deck"))
    return {"edition_scope": edition, "work_scope": _sin_vacios(work)}


def normalizar_tebeosfera_serie(ficha: object) -> dict[str, Any]:
    """TebeosferaColeccion → campos de edición; no inventa total ni sinopsis."""
    return {"edition_scope": _sin_vacios({
        "title": _texto(_leer(ficha, "titulo")),
        "start_year": _anio(_leer(ficha, "anio")),
        "end_year": _anio(_leer(ficha, "anio_fin")),
        "publisher_name": _texto(_leer(ficha, "editorial")),
        "imprint_name": _texto(_leer(ficha, "sello")),
        "country": _texto(_leer(ficha, "pais")),
        "language": _texto(_leer(ficha, "idioma")),
    }), "work_scope": {}}


def normalizar_gcd_serie(ficha: object) -> dict[str, Any]:
    """GCDSerie → campos bibliográficos; editorial es URL, no nombre."""
    return {"edition_scope": _sin_vacios({
        "title": _texto(_leer(ficha, "name")),
        "start_year": _anio(_leer(ficha, "year_began")),
        "end_year": _anio(_leer(ficha, "year_ended")),
        "country": _texto(_leer(ficha, "country")),
        "language": _texto(_leer(ficha, "language")),
        "total_issues": _entero(_leer(ficha, "issue_count")),
    }), "work_scope": {}}


def raw_acotado_comic_vine(ficha: object) -> dict[str, Any]:
    raw = _leer(ficha, "raw")
    fuente = raw if isinstance(raw, Mapping) else {}
    return _sin_vacios({
        "id": _entero(_leer(ficha, "cv_id") or fuente.get("id")),
        "name": _texto(_leer(ficha, "name")),
        "publisher": _texto(_leer(ficha, "publisher")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "count_of_issues": _entero(_leer(ficha, "count_of_issues")),
        "site_url": _texto(fuente.get("site_detail_url")),
    })


def raw_acotado_tebeosfera(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "slug": _texto(_leer(ficha, "slug")),
        "titulo": _texto(_leer(ficha, "titulo")),
        "editorial": _texto(_leer(ficha, "editorial")),
        "sello": _texto(_leer(ficha, "sello")),
        "anio": _anio(_leer(ficha, "anio")),
        "anio_fin": _anio(_leer(ficha, "anio_fin")),
        "pais": _texto(_leer(ficha, "pais")),
        "idioma": _texto(_leer(ficha, "idioma")),
        "url_ficha": _texto(_leer(ficha, "url_ficha")),
    })


def raw_acotado_gcd(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "gcd_id": _entero(_leer(ficha, "gcd_id")),
        "name": _texto(_leer(ficha, "name")),
        "year_began": _anio(_leer(ficha, "year_began")),
        "year_ended": _anio(_leer(ficha, "year_ended")),
        "publisher": _texto(_leer(ficha, "publisher")),
        "language": _texto(_leer(ficha, "language")),
        "country": _texto(_leer(ficha, "country")),
        "issue_count": _entero(_leer(ficha, "issue_count")),
        "publishing_format": _texto(_leer(ficha, "publishing_format")),
        "binding": _texto(_leer(ficha, "binding")),
    })


def normalizar_anilist_serie(ficha: object) -> dict[str, Any]:
    """AniList: solo serie manga; no hay número de grapa.

    `chapters` es un recuento de capítulos, no de grapas: se expone como
    `total_issues` únicamente porque es el contador que ya usa el enricher para
    manga; no se usa para huecos de una edición de grapa.
    """
    titulo = _texto(_leer(ficha, "title_english")) or _texto(_leer(ficha, "title_romaji"))
    return {"edition_scope": _sin_vacios({
        "title": titulo,
        "start_year": _anio(_leer(ficha, "start_year")),
        "total_issues": _entero(_leer(ficha, "chapters")),
    }), "work_scope": _sin_vacios({
        "description": _texto(_leer(ficha, "description")),
    })}


def raw_acotado_anilist(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "anilist_id": _entero(_leer(ficha, "anilist_id")),
        "title_romaji": _texto(_leer(ficha, "title_romaji")),
        "title_english": _texto(_leer(ficha, "title_english")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "chapters": _entero(_leer(ficha, "chapters")),
        "volumes": _entero(_leer(ficha, "volumes")),
        "site_url": _texto(_leer(ficha, "site_url")),
    })


def normalizar_metron_serie(ficha: object) -> dict[str, Any]:
    """Metron: serie/edición; el país no viene y no se inventa."""
    return {"edition_scope": _sin_vacios({
        "title": _texto(_leer(ficha, "name")),
        "start_year": _anio(_leer(ficha, "year_began")),
        "end_year": _anio(_leer(ficha, "year_ended")),
        "publisher_name": _texto(_leer(ficha, "publisher")),
        "language": _texto(_leer(ficha, "language")),
        "total_issues": _entero(_leer(ficha, "issue_count")),
    }), "work_scope": _sin_vacios({
        "description": _texto(_leer(ficha, "descripcion")),
    })}


def raw_acotado_metron(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "metron_id": _entero(_leer(ficha, "metron_id")),
        "name": _texto(_leer(ficha, "name")),
        "year_began": _anio(_leer(ficha, "year_began")),
        "year_ended": _anio(_leer(ficha, "year_ended")),
        "issue_count": _entero(_leer(ficha, "issue_count")),
        "publisher": _texto(_leer(ficha, "publisher")),
        "language": _texto(_leer(ficha, "language")),
        "site_url": _texto(_leer(ficha, "site_url")),
    })


def normalizar_open_library_serie(ficha: object) -> dict[str, Any]:
    """Open Library: obra/tomo; nunca una grapa."""
    return {"edition_scope": _sin_vacios({
        "title": _texto(_leer(ficha, "title")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "publisher_name": _texto(_leer(ficha, "editorial")),
        "language": _texto(_leer(ficha, "idioma")),
    }), "work_scope": _sin_vacios({
        "description": _texto(_leer(ficha, "description")),
    })}


def raw_acotado_open_library(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "work_id": _texto(_leer(ficha, "work_id")),
        "title": _texto(_leer(ficha, "title")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "editorial": _texto(_leer(ficha, "editorial")),
        "idioma": _texto(_leer(ficha, "idioma")),
        "site_url": _texto(_leer(ficha, "site_url")),
    })


def normalizar_fandom_serie(ficha: object) -> dict[str, Any]:
    return {"edition_scope": _sin_vacios({
        "title": _texto(_leer(ficha, "title")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "end_year": _anio(_leer(ficha, "end_year")),
        "total_issues": _entero(_leer(ficha, "total_issues")),
    }), "work_scope": _sin_vacios({
        "description": _texto(_leer(ficha, "description")),
    })}


def raw_acotado_fandom(ficha: object) -> dict[str, Any]:
    return _sin_vacios({
        "page_title": _texto(_leer(ficha, "page_title")),
        "title": _texto(_leer(ficha, "title")),
        "start_year": _anio(_leer(ficha, "start_year")),
        "end_year": _anio(_leer(ficha, "end_year")),
        "total_issues": _entero(_leer(ficha, "total_issues")),
        "kind": _texto(_leer(ficha, "kind")),
    })
