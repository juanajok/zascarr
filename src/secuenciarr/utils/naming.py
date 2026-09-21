"""
Normalización de nombres de archivos de cómic.

Tres capas:
  1. Regex: extrae serie, número, volumen, año del filename (70% de casos)
  2. Normalización: elimina ruido, artículos, puntuación (20%)
  3. Fuzzy (pg_trgm en DB, ver matcher.py): 10% restante

NOTA: parse_comic_filename es la función principal para la Capa 1.
Los tests en tests/test_naming_core.py cubren los filenames reales
de la escena que debe resolver.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


NOISE_PATTERNS = [
    r"\(Digital\)", r"\(digital\)", r"\(Digital-\w+\)",
    r"\(Minutemen-\w+\)", r"\(Zone-\w+\)", r"\(Empire\)",
    r"\(Glorith-HD\)", r"\(F\)\s*", r"\(c2c\)", r"\(noads\)",
    r"\(HD\)", r"\(SD\)", r"\(Webrip\)", r"\(Scan\)",
    r"\((?:19|20)[0-9]{2}\)",   # año entre paréntesis: cubre 19xx Y 20xx
                                # (antes solo "20xx"; perdía años como 1989)
]

ISSUE_PATTERNS = [
    r"#\s*(\d+\.?\d*)",
    r"c(\d{3,4})\b",                    # One Piece c1054
    r"\bT(\d{2})\b",                     # Astérix T01: BD de tomo único,
                                          # el tomo ES el número de cara
                                          # a catalogación (no un volumen
                                          # de trade paperback americano).
    r"\b(\d{3,4})\b(?!\s*\))",
    r"(?:Issue|No\.?|N[úu]mero)\s*(\d+)",
]

VOLUME_PATTERNS = [
    r"Vol\.?\s*(\d+)", r"Volume\s*(\d+)",
    r"\bv(\d+)\b", r"Tomo\s*(\d+)",
]

YEAR_PATTERN = re.compile(r"\((\d{4})\)")
ANNUAL_PATTERN = re.compile(r"\b(?:Annual|Anual|Especial)\b", re.IGNORECASE)
FILE_EXT_PATTERN = re.compile(r"\.(cbz|cbr|cb7|pdf|epub)$", re.IGNORECASE)


@dataclass
class ParsedComicName:
    series: str = ""
    issue_number: str = ""
    volume: int | None = None
    year: int | None = None
    format: str = ""
    is_annual: bool = False
    extra_info: list[str] = field(default_factory=list)
    original_filename: str = ""
    confidence: float = 0.0


def parse_comic_filename(filename: str) -> ParsedComicName:
    """Parsea un nombre de archivo de cómic y extrae metadatos."""
    result = ParsedComicName(original_filename=filename)

    ext_match = FILE_EXT_PATTERN.search(filename)
    if ext_match:
        result.format = ext_match.group(1).lower()
        working = filename[: ext_match.start()]
    else:
        working = filename

    # "_" es un separador de facto en la escena ("Batman_v2_012"), pero \b
    # no lo trata como frontera de palabra (es \w igual que letras/dígitos):
    # sin este reemplazo, "v2"/"012" pegados a "_" nunca matchean \bv(\d+)\b
    # ni \b(\d{3,4})\b. Convertirlo a espacio antes de todo lo demás arregla
    # volumen/número a la vez que la limpieza de puntuación de más abajo.
    working = working.replace("_", " ")

    year_match = YEAR_PATTERN.search(working)
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2099:
            result.year = year

    if ANNUAL_PATTERN.search(working):
        result.is_annual = True

    for pattern in VOLUME_PATTERNS:
        vol_match = re.search(pattern, working, re.IGNORECASE)
        if vol_match:
            result.volume = int(vol_match.group(1))
            working = re.sub(pattern, "", working, flags=re.IGNORECASE)
            break

    for pattern in ISSUE_PATTERNS:
        issue_match = re.search(pattern, working)
        if issue_match:
            raw = issue_match.group(1)
            result.issue_number = str(raw).lstrip("0") or "0"
            working = working[: issue_match.start()] + working[issue_match.end() :]
            break

    for noise in NOISE_PATTERNS:
        working = re.sub(noise, "", working, flags=re.IGNORECASE)

    # Catch-all: cualquier paréntesis que sobreviva a los patrones curados de
    # arriba es casi siempre metadata de release que no anticipamos ("Batman
    # (New 52) 012" — el reboot no es parte del título de la serie), nunca
    # parte legítima de un título de cómic real.
    working = re.sub(r"\([^)]*\)", "", working)

    # "Serie - Subtítulo" y "Serie #001 - Título del número": todo lo que
    # sigue a un separador " - " (con espacios a los dos lados, a diferencia
    # de un guion pegado como en "Spider-Man") es el título del propio
    # número, no parte del nombre de la serie.
    working = re.split(r"\s+-\s+", working, maxsplit=1)[0]

    series = working.strip()
    series = re.sub(r"[\.\-_]+", " ", series)
    series = re.sub(r"\s+", " ", series)
    series = re.sub(r"\s*[-\u2013\u2014]\s*$", "", series)
    series = series.strip(" -\u2013\u2014()")
    result.series = series
    result.confidence = _confidence(result)
    return result


def normalize_series_name(name: str) -> str:
    """Para comparación fuzzy: sin artículos, sin puntuación, lowercase."""
    name = name.lower()
    name = re.sub(r"^(the|a|an|el|la|los|las|le|les)\s+", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def _confidence(p: ParsedComicName) -> float:
    score = 0.0
    if p.series:        score += 0.4
    if p.issue_number:  score += 0.3
    if p.year:          score += 0.15
    if p.format:        score += 0.1
    if p.volume:        score += 0.05
    return min(score, 1.0)
