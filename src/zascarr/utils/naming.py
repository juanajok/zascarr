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
from dataclasses import dataclass, field

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
    # Ediciones de recopilación (CRG y similares): "Omnigold 5", "Integral
    # 01", "Edición Integral 01" — el número que traen no es una grapa
    # #NNN, es el tomo de la recopilación, pero a efectos de matching es
    # lo único que tenemos (naming.py solo pasa (título, número, año) al
    # matcher — no hay un campo "tomo de colección" separado todavía; ver
    # docs/BACKLOG.md, ampliación del parser pendiente en varias capas).
    r"\b(?:Omnigold|Integral|Edici[oó]n\s+Integral)\s+(\d{1,3})\b",
    # "Serie NN - Subtítulo": el idiom más común de la escena en español
    # ("AIDP 05 - La Llama Negra", "Astérix (DI) 01 - Astérix el galo",
    # "Gideon Falls 01 - El Granero Negro"). El número va ANTES del
    # separador de subtítulo, no al final del nombre, así que el patrón
    # de último recurso de abajo no lo veía: el número se quedaba pegado
    # al título ("Astérix 01") y ninguna serie igualaba nunca.
    r"\s(\d{1,3})\s+-\s+",
    # Último recurso: un número suelto de 1-3 cifras pegado al final del
    # nombre (sin "#", sin "T", sin años de 4 cifras que ya cubre el
    # patrón de arriba con \b(\d{3,4})\b). Bug real: "La Patrulla-X
    # Original 1.cbr" no llevaba NINGÚN marcador delante del número.
    r"\s(\d{1,3})\s*$",
]

# Líneas editoriales de reedición que anteponen su propio nombre al de la
# serie real, con " - " como separador ("Marvel Gold - La Patrulla-X
# Original 1.cbr") — al revés que "Serie - Subtítulo". Sin esto, el split
# de subtítulo de más abajo se queda con el nombre de la línea editorial
# en vez de con la serie.
IMPRINT_PREFIX_PATTERN = re.compile(
    r"^(?:Marvel\s+Gold|Marvel\s+Deluxe|Biblioteca\s+Marvel|Panini\s+Cl[aá]sicos)"
    r"\s*-\s*",
    re.IGNORECASE,
)

VOLUME_PATTERNS = [
    r"Vol\.?\s*(\d+)", r"Volume\s*(\d+)",
    r"\bv(\d+)\b", r"Tomo\s*(\d+)",
]

YEAR_PATTERN = re.compile(r"\((\d{4})\)")

# Fecha de publicación "(AAAA-MM)" — idiom de los scans digitales de DCP/
# Novus ("JSA (2004-08) 62"). Bug real de producción (biblioteca del
# coleccionista, 2026-09-25): sin esto, "2004" caía en el patrón genérico
# \b(\d{3,4})\b y se registraba como NÚMERO DE GRAPA. Un JSA #2004 en la
# biblioteca es exactamente la "corrupción silenciosa" que matcher.py se
# propone evitar, y con la sugerencia de un clic (B12) el coleccionista
# la confirmaba sin verla venir. El mes se descarta: el modelo no tiene
# dónde guardarlo y el año ya desambigua la serie.
PUBLICATION_DATE_PATTERN = re.compile(r"\(((?:19|20)\d{2})-(?:0[1-9]|1[0-2])\)")

# Rango de números: "(144-158)", "049-051a", "(26-30)". Es un PACK o una
# recopilación que cubre varios números, no un número. Antes se quedaba
# con el primero del rango ("La Imposible Patrulla X (144-158)" → #144),
# inventando una pertenencia que el archivo no afirma. Sin número, el
# archivo va a Pendientes, que es la respuesta honesta. Va DESPUÉS de
# PUBLICATION_DATE_PATTERN: "(2004-08)" es una fecha, no un rango.
# El guion va pegado a propósito (nunca "\s*-\s*"): con espacios alrededor
# se tragaba el separador de subtítulo de "Serie 01 - 2 parte". Y solo se
# quitan las cifras, no los paréntesis que las rodean — quitar "(" sin
# poder quitar su ")" dejaba huérfano el cierre ("La Patrulla X (122-143
# usa)" → "La Patrulla X usa)"). El catch-all de paréntesis de más abajo
# ya se lleva el "( )" que queda.
NUMBER_RANGE_PATTERN = re.compile(r"\b\d{1,4}-\d{1,4}[a-z]?\b")

# Prefijo de ORDEN DE LECTURA al principio del nombre ("069.- Flash v2
# 62", "247.- Wonder Woman v2 214"): numera la colección/orden del
# coleccionista, no la grapa. Sin esto se llevaba el patrón genérico de
# 3 cifras y "Wonder Woman 214" se registraba como el número 247.
SORT_PREFIX_PATTERN = re.compile(r"^\s*\d{1,3}\s*\.\s*-\s*")
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

    # Tags de release entre corchetes ("[CRG]", "[MQ]", "[DI]", "[ML]"):
    # grupo/calidad/procedencia, nunca parte del título. A diferencia del
    # ruido entre paréntesis (NOISE_PATTERNS, más abajo, curado caso a
    # caso), esto es un corte genérico — en la práctica de la escena en
    # español, TODO corchete es metadata de release, nunca título. Debe
    # ir ANTES de extraer número/volumen: si no, un corchete a mitad de
    # cadena ("... [DI] by The Murdock [CRG]") deja basura pegada al
    # título o esconde un número final ("...Integral 01 [CRG]").
    working = re.sub(r"\[[^\]]*\]", "", working)

    # Líneas editoriales de reedición ANTES del nombre real de la serie
    # ("Marvel Gold - La Patrulla-X Original 1.cbr"): al revés que "Serie
    # - Subtítulo" (el split de subtítulo de más abajo se quedaría con
    # "Marvel Gold", no con la serie). Se descarta el prefijo entero y se
    # sigue procesando el resto como si fuera el nombre completo.
    working = IMPRINT_PREFIX_PATTERN.sub("", working, count=1)

    # Orden de lectura del coleccionista, no el número de la grapa.
    working = SORT_PREFIX_PATTERN.sub("", working, count=1)

    # Fecha de publicación antes que nada: "(2004-08)" es un año, y si se
    # deja pasar hasta la extracción de número se convierte en una grapa
    # #2004 (ver PUBLICATION_DATE_PATTERN).
    fecha_match = PUBLICATION_DATE_PATTERN.search(working)
    if fecha_match:
        result.year = int(fecha_match.group(1))
        working = PUBLICATION_DATE_PATTERN.sub(" ", working, count=1)

    year_match = YEAR_PATTERN.search(working)
    if year_match:
        year = int(year_match.group(1))
        if 1900 <= year <= 2099:
            result.year = year

    # Rangos ("144-158"): un pack no tiene UN número. Se quitan antes de
    # extraer el número para no quedarse con el primero del rango.
    working = NUMBER_RANGE_PATTERN.sub(" ", working)

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
            # Cortar, no empalmar: empalmar los dos lados pegaba el título
            # al subtítulo cuando el número va en medio ("Astérix (DI) 01 -
            # Astérix el galo" → "Astérix (DI)" + "Astérix el galo"). Si el
            # número iba al principio del nombre, cortar dejaría la serie
            # vacía — solo en ese caso se empalma.
            cortado = working[: issue_match.start()]
            working = cortado if cortado.strip() else working[issue_match.end() :]
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
