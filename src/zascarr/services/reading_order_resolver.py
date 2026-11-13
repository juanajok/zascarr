"""Normalizador puro de referencias de guías de lectura (SCR3, Anexo D del estudio).

Convierte una línea como «Uncanny X-Men (1963) #141-142» en datos fácticos: serie, volumen,
**dos años distintos** (el de la edición/volumen y el del número) y número o rango. No hay
red, ni BD, ni acceso a configuraciones: el módulo no importa `httpx` ni `sqlalchemy` (solo
reutiliza `core.matcher.normalize_title`, que es puro).

Gramática que entiende (guiones tipográficos normalizados):
`[SERIE] [Vol. N | (AÑO)] # NUM [- NUM] [(AÑO)] [(MARCADOR)]`

- `NUM` admite `1`, `0.1`, `1/2`, `12.NOW`, `1A` y `½` (se normaliza a `0.5`).
- El año **antes** del `#` o junto a `Vol.` es `anio_volumen` (año de la edición); el año
  **después** del `#` es `anio_numero` (año del número). Nunca se mezclan (spec §3).
- `Annual` en la serie → `annual`; `Special|Giant-Size|One-Shot` → `special`;
  `TPB|Trade Paperback|Omnibus|Hardcover|HC|Collected` sin `#` → `tpb`; `Vol. N` sin `#` →
  `volume`; un encabezado o prosa sin `#` → `None`.
- Marcadores reconocidos (`of N`, `limited series`, `one-shot`) se anotan en `avisos`.
  `one-shot` además marca el tipo `special` (caso de la tabla de la spec); el resto no lo
  cambia. Un paréntesis no reconocido deja la confianza en `baja`.

Límites declarados: no se interpretan tomos por ISBN, ni «Vol. 1-3» como rango de volúmenes,
ni fechas exactas; una referencia dudosa no se adivina (confianza baja + aviso). Un `tpb` o
un `volume` **no es una grapa**: nunca cuenta como «falta» en la reconciliación.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from zascarr.core.matcher import normalize_title

#: Techo de expansión de un rango de números (spec §3).
MAX_RANGO = 100

TipoEntrega = Literal["issue", "annual", "special", "tpb", "volume"]
Confianza = Literal["alta", "media", "baja"]

#: Guiones tipográficos → guion ASCII (el resto del repo normaliza igual en las guías).
_RE_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_RE_ESPACIOS = re.compile(r"\s+")
_RE_GRUPO_FINAL = re.compile(r"\(([^()]*)\)\s*$")
_RE_ANIO = re.compile(r"^\d{4}$")
_RE_VOL = re.compile(r"\bVol(?:ume)?\.?\s*(\d+)\b", re.IGNORECASE)
_RE_VOL_RANGO = re.compile(r"\bVol(?:ume)?\.?\s*\d+\s*-\s*\d+", re.IGNORECASE)
_RE_ANUAL = re.compile(r"\bAnnual\b", re.IGNORECASE)
_RE_ESPECIAL = re.compile(r"\b(?:Special|Giant-Size|One-Shot)\b", re.IGNORECASE)
_RE_TPB = re.compile(r"\b(?:TPB|Trade Paperback|Omnibus|Hardcover|HC|Collected)\b",
                     re.IGNORECASE)
_RE_NUMERO = re.compile(
    r"^(\d+(?:\.\w+|/\d+)?[A-Za-z]?)"
    r"(?:\s*-\s*#?\s*(\d+(?:\.\w+|/\d+)?[A-Za-z]?))?$")
_RE_MARCADOR_RECONOCIDO = re.compile(r"^(?:of\s+\d+|limited series|one-shot)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReadingOrderItem:
    """Una referencia normalizada. Solo hechos; no transporta la prosa de la guía."""

    titulo_serie: str
    anio_volumen: int | None = None
    anio_numero: int | None = None
    volumen: int | None = None
    numero_inicio: str | None = None
    numero_fin: str | None = None
    tipo: TipoEntrega = "issue"
    confianza: Confianza = "media"
    avisos: tuple[str, ...] = ()


def _normalizar(texto: str) -> str:
    """Guiones tipográficos, `½` y espacios colapsados (sin tocar acentos ni mayúsculas)."""
    limpio = _RE_DASHES.sub("-", texto).replace("½", "0.5")
    return _RE_ESPACIOS.sub(" ", limpio).strip()


def _grupos_finales(texto: str) -> tuple[str, list[str]]:
    """Parte `texto` en (resto, grupos `(...)` del final en orden de aparición)."""
    grupos: list[str] = []
    resto = texto.strip()
    while True:
        coincidencia = _RE_GRUPO_FINAL.search(resto)
        if coincidencia is None:
            break
        grupos.insert(0, coincidencia.group(1).strip())
        resto = resto[:coincidencia.start()].strip()
    return resto, grupos


def _limpiar_titulo(texto: str) -> str | None:
    """Recorta puntuación de los bordes y colapsa espacios; `None` si queda vacío."""
    limpio = texto.strip(" -:,")
    limpio = _RE_ESPACIOS.sub(" ", limpio).strip()
    return limpio or None


def _anio_y_avisos(grupos: list[str]) -> tuple[int | None, list[str], bool]:
    """(año, avisos, hay_grupo_no_reconocido) de una lista de paréntesis."""
    anio: int | None = None
    avisos: list[str] = []
    no_reconocido = False
    for grupo in grupos:
        if _RE_ANIO.fullmatch(grupo):
            anio = int(grupo)
            continue
        avisos.append(grupo.lower())
        if not _RE_MARCADOR_RECONOCIDO.fullmatch(grupo):
            no_reconocido = True
    return anio, avisos, no_reconocido


def _extraer_volumen(texto: str) -> tuple[str, int | None]:
    """Quita `Vol. N` del texto y lo devuelve (texto, N)."""
    coincidencia = _RE_VOL.search(texto)
    if coincidencia is None:
        return texto, None
    resto = (texto[:coincidencia.start()] + " " + texto[coincidencia.end():]).strip()
    return resto, int(coincidencia.group(1))


def _parsear_numero(texto: str) -> tuple[str, str | None] | None:
    """`1`, `1-6`, `0.1`, `1/2`, `12.NOW`, `1A` → (inicio, fin|None)."""
    coincidencia = _RE_NUMERO.match(texto)
    if coincidencia is None:
        return None
    return coincidencia.group(1), coincidencia.group(2)


def _con_numero(izquierda: str, derecha: str) -> ReadingOrderItem | None:
    """Parte común de las referencias con `#`: número y, si consta, año del número."""
    numero_parte, grupos_derecha = _grupos_finales(derecha)
    numero = _parsear_numero(numero_parte)
    if numero is None:
        return None
    numero_inicio, numero_fin = numero
    anio_numero, avisos, no_reconocido = _anio_y_avisos(grupos_derecha)

    titulo_texto, grupos_izquierda = _grupos_finales(izquierda)
    anio_volumen, avisos_izquierda, no_reconocido_izquierda = _anio_y_avisos(grupos_izquierda)
    titulo_texto, volumen = _extraer_volumen(titulo_texto)
    titulo = _limpiar_titulo(titulo_texto)
    if titulo is None:
        return None

    if _RE_ANUAL.search(titulo):
        titulo = _limpiar_titulo(_RE_ANUAL.sub(" ", titulo)) or titulo
        tipo: TipoEntrega = "annual"
    else:
        tipo = "issue"
        if _RE_ESPECIAL.search(titulo) or any(aviso == "one-shot" for aviso in avisos):
            tipo = "special"

    tiene_referencia_de_edicion = anio_volumen is not None or volumen is not None
    confianza: Confianza = "alta" if tiene_referencia_de_edicion else "media"
    if no_reconocido or no_reconocido_izquierda:
        confianza = "baja"
    return ReadingOrderItem(
        titulo_serie=titulo,
        anio_volumen=anio_volumen,
        anio_numero=anio_numero,
        volumen=volumen,
        numero_inicio=numero_inicio,
        numero_fin=numero_fin,
        tipo=tipo,
        confianza=confianza,
        avisos=tuple(avisos + avisos_izquierda),
    )


def _sin_numero(texto: str) -> ReadingOrderItem | None:
    """`TPB`/`Omnibus` o `Vol. N` sin `#`; encabezado o prosa ⇒ None."""
    if _RE_VOL_RANGO.search(texto):
        return None                       # «Vol. 1-3» no es un rango de volúmenes (límite)
    resto, grupos = _grupos_finales(texto)
    anio_volumen, avisos, no_reconocido = _anio_y_avisos(grupos)
    resto, volumen = _extraer_volumen(resto)
    es_tpb = _RE_TPB.search(resto) is not None
    if es_tpb:
        resto = _RE_TPB.sub(" ", resto)
        tipo: TipoEntrega = "tpb"
    elif volumen is not None:
        tipo = "volume"
    else:
        return None
    titulo = _limpiar_titulo(resto)
    if titulo is None:
        return None
    return ReadingOrderItem(
        titulo_serie=titulo,
        anio_volumen=anio_volumen,
        anio_numero=None,
        volumen=volumen,
        numero_inicio=None,
        numero_fin=None,
        tipo=tipo,
        confianza="baja",                # sin número no se puede afirmar que sea una grapa
        avisos=tuple(avisos),
    )


def parsear_referencia(texto: str) -> ReadingOrderItem | None:
    """Convierte una referencia de guía en `ReadingOrderItem`, o `None` si no es una referencia."""
    if not texto or not texto.strip():
        return None
    normalizado = _normalizar(texto)
    if "#" in normalizado:
        izquierda, derecha = normalizado.split("#", 1)
        return _con_numero(izquierda.strip(), derecha.strip())
    return _sin_numero(normalizado)


def expandir_rango(item: ReadingOrderItem) -> list[str] | None:
    """Números enteros de `numero_inicio..numero_fin` (tope `MAX_RANGO`), o `None`.

    Solo para rangos de enteros: `0.1`, `1A`, `1/2` o `12.NOW` no se expanden (el llamador
    compara el literal). Un tope evita expandir un «#1-9999» vandálico.
    """
    if not item.numero_inicio or not item.numero_fin:
        return None
    if not (item.numero_inicio.isdigit() and item.numero_fin.isdigit()):
        return None
    inicio, fin = int(item.numero_inicio), int(item.numero_fin)
    if fin < inicio or (fin - inicio + 1) > MAX_RANGO:
        return None
    return [str(numero) for numero in range(inicio, fin + 1)]


def clave_de_serie(item: ReadingOrderItem) -> str:
    """Clave de comparación de la serie (reutiliza `normalize_title`, puro).

    La entrega 2 la usará para cruzar con `Series.title_norm`; aquí solo existe para que la
    normalización de títulos sea LA MISMA que la del matcher del proyecto.
    """
    return normalize_title(item.titulo_serie)


__all__ = [
    "MAX_RANGO",
    "Confianza",
    "ReadingOrderItem",
    "TipoEntrega",
    "clave_de_serie",
    "expandir_rango",
    "parsear_referencia",
]
