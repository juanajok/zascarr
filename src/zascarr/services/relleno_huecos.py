"""Relleno de huecos por identificador ya guardado (SCR7, #736).

Solo se consulta la ficha **por id exacto** (`gcd_id`/`metron_id`/`open_library_id`): nunca
se busca por título ni se reclama identidad. `aplicar_relleno` es puro (no importa `httpx`):

- rellena **solo campos vacíos** de una lista cerrada por fuente;
- nunca toca `title`, los `*_id`, `metadata_source`, `cover_url`, `total_issues` ni
  `locked_fields`;
- registra la procedencia en `metadata_["relleno"][fuente]` con un **dict nuevo** (SQLAlchemy
  no detecta mutaciones in-place de JSONB): `id`, `campos`, `ultimo_intento` y `url_ficha`.

La caché negativa de 30 días (`ultimo_intento`) vive en el mismo JSONB y la consulta el
enricher; un fallo transitorio no la escribe (se reintenta en el ciclo siguiente).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

#: Lista CERRADA de campos que cada fuente puede rellenar (lo demás se ignora).
CAMPOS_POR_FUENTE: dict[str, tuple[str, ...]] = {
    "gcd": ("start_year", "end_year"),
    "metron": ("description", "start_year", "end_year"),
    "open_library": ("description", "start_year"),
}
FUENTES_CON_RELLENO = ("metron", "open_library", "gcd")
#: Días que no se vuelve a pedir una fuente ya consultada (negativa o ya rellenada).
TTL_RELLENO = timedelta(days=30)
#: Tope de peticiones por fuente y ciclo (protege la cuota anónima de GCD y el 20/min de Metron).
MAX_PETICIONES_FUENTE_POR_CICLO = 5
#: Tradiciones en las que tiene sentido cada fuente (el enricher decide; aquí se reutiliza).
TRADICIONES_DE_FUENTE: dict[str, frozenset[str]] = {
    "metron": frozenset({"american", "fumetti"}),
    "gcd": frozenset({"american", "british"}),
    "open_library": frozenset(),  # obra/tomo: no depende de la tradición
}
#: Nunca se escriben desde el relleno (defensa en profundidad además de la lista cerrada).
CAMPOS_PROHIBIDOS = frozenset({
    "title", "comic_vine_id", "anilist_id", "tebeosfera_slug", "gcd_id", "metron_id",
    "open_library_id", "metadata_source", "cover_url", "total_issues", "locked_fields",
})
#: Campo del modelo → atributo de la ficha de la fuente.
_ATRIBUTOS = {
    "gcd": {"start_year": "year_began", "end_year": "year_ended"},
    "metron": {"description": "descripcion", "start_year": "year_began",
               "end_year": "year_ended"},
    "open_library": {"description": "description", "start_year": "start_year"},
}


def _vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _leer(ficha: object, atributo: str) -> Any:
    if isinstance(ficha, dict):
        return ficha.get(atributo)
    return getattr(ficha, atributo, None)


def _id_y_url(fuente: str, ficha: object | None) -> tuple[str | None, str | None]:
    if ficha is None:
        return None, None
    if fuente == "gcd":
        ident = _leer(ficha, "gcd_id")
        return (str(ident) if ident is not None else None,
                f"https://www.comics.org/series/{ident}/" if ident is not None else None)
    if fuente == "metron":
        ident = _leer(ficha, "metron_id")
        return (str(ident) if ident is not None else None,
                _leer(ficha, "site_url") or (
                    f"https://metron.cloud/series/{ident}/" if ident is not None else None))
    ident = _leer(ficha, "work_id")
    return (str(ident) if ident is not None else None,
            f"https://openlibrary.org/works/{ident}" if ident is not None else None)


def campos_faltantes(serie, fuente: str) -> tuple[str, ...]:
    """Campos de la lista cerrada de `fuente` que la serie tiene vacíos y no bloqueados."""
    campos = CAMPOS_POR_FUENTE.get(fuente)
    if not campos:
        return ()
    locked = set(serie.locked_fields or [])
    return tuple(campo for campo in campos
                 if campo not in locked and campo not in CAMPOS_PROHIBIDOS
                 and _vacio(getattr(serie, campo, None)))


def _registrar(serie, fuente: str, ficha: object | None, campos: list[str],
               ahora: datetime) -> None:
    metadata = dict(serie.metadata_ or {})          # dict NUEVO (JSONB)
    relleno = dict(metadata.get("relleno") or {})
    ident, url = _id_y_url(fuente, ficha)
    relleno[fuente] = {
        "id": ident,
        "campos": list(campos),
        "ultimo_intento": ahora.isoformat(),
        "url_ficha": url,
    }
    metadata["relleno"] = relleno
    serie.metadata_ = metadata


def aplicar_relleno(serie, fuente: str, ficha: object | None,
                    ahora: datetime | None = None) -> list[str]:
    """Rellena los huecos de `serie` con `ficha` (SCR7) y devuelve los campos escritos.

    `ficha=None` (404/respuesta vacía) ⇒ sin cambios y se marca la caché negativa de 30 días
    con `campos=[]`; `aplicar_relleno` no hace red ni conoce excepciones (el enricher decide
    qué hacer con un fallo transitorio antes de llamarla).
    """
    if fuente not in CAMPOS_POR_FUENTE:
        return []
    momento = ahora if ahora is not None else datetime.now(UTC)
    if ficha is None:
        _registrar(serie, fuente, None, [], momento)
        return []
    locked = set(serie.locked_fields or [])
    escritos: list[str] = []
    for campo in CAMPOS_POR_FUENTE[fuente]:
        if campo in locked or campo in CAMPOS_PROHIBIDOS:
            continue
        if not _vacio(getattr(serie, campo, None)):
            continue
        valor = _leer(ficha, _ATRIBUTOS[fuente][campo])
        if _vacio(valor):
            continue
        setattr(serie, campo, valor)
        escritos.append(campo)
    _registrar(serie, fuente, ficha, escritos, momento)
    return escritos


def ttl_vigente(serie, fuente: str, ahora: datetime | None = None) -> bool:
    """¿Se consultó esta fuente hace menos de 30 días? (independiente del primario)."""
    momento = ahora if ahora is not None else datetime.now(UTC)
    entrada = ((serie.metadata_ or {}).get("relleno") or {}).get(fuente)
    if not isinstance(entrada, dict):
        return False
    ultimo = entrada.get("ultimo_intento")
    if not isinstance(ultimo, str) or not ultimo:
        return False
    try:
        fecha = datetime.fromisoformat(ultimo)
    except (TypeError, ValueError):
        return False
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return momento - fecha < TTL_RELLENO


__all__ = [
    "CAMPOS_POR_FUENTE",
    "CAMPOS_PROHIBIDOS",
    "FUENTES_CON_RELLENO",
    "MAX_PETICIONES_FUENTE_POR_CICLO",
    "TRADICIONES_DE_FUENTE",
    "TTL_RELLENO",
    "aplicar_relleno",
    "campos_faltantes",
    "ttl_vigente",
]
