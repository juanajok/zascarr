"""
importer_triage.py — Capa 0 del importer: verdad empaquetada.

Antes de cualquier regex, normalización o fuzzy matching, el importer abre el
archivo y pregunta lo que el propio archivo sabe de sí mismo:

  1. SHA256         — identidad física (dedupe entre Transmission y aMule).
  2. ComicInfo.xml  — metadatos estructurados de la release, si los trae.
                      Cuando existen, metadata_source = 'comicinfo_xml' y la
                      capa 0 gana: naming.py solo se invoca para VALIDAR, no
                      para adivinar.
  3. width_px       — ancho de la primera página via Pillow. Mismo open() del
                      zip que ComicInfo: coste marginal cero, alimenta el CASE
                      de quality_tier.
  4. source_tag     — heurística sobre el SUFIJO de release del filename
                      (entre el último paréntesis y la extensión).

Contrato con el resto del pipeline:

  triage(path) -> TriageResult
    - Si TriageResult.comic_info tiene series AND number => CANDIDATO FUERTE.
    - Si falta ComicInfo o le faltan campos clave => Capa 1 (naming.py).
    - NUNCA lanza excepción hacia el caller: zip corrupto, imagen ilegible =>
      campos a None y notas en TriageResult.warnings.

Nota de seguridad: ComicInfo.xml viene de releases de terceros. ElementTree
no resuelve entidades externas (no hay XXE), pero NO uses lxml con
resolve_entities=True aquí. Si se migra a defusedxml, mejor.

Correcciones respecto al diseño original:
  - Un solo open() de disco: SHA256 en streaming al BytesIO, ZipFile sobre
    el buffer. Evita la doble lectura completa del fichero en disco (crítico
    para una Pi con HDD y CBZs de 200MB).
  - guess_source_tag busca solo en el último bloque de paréntesis del
    filename, no en el stem completo (evita falsos positivos en títulos
    como "Digital Conan Vol.01").
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

# ── Heurística de source_tag ─────────────────────────────────────────────────
# Solo miramos el SUFIJO de release (último bloque entre paréntesis antes de
# la extensión). Así "(Digital)" del equipo no colisiona con "Digital" en el
# título de la obra.
_TAG_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)\b(digital|webrip|web-dl|dcp)\b", "digital"),
    (r"(?i)\b(scan|scanned|c2c)\b", "scan"),
    (r"(?i)\b(hd|uhd|4k)\b", "scan_hq"),
]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
_LAST_PAREN = re.compile(r"\(([^)]+)\)\s*$")


def guess_source_tag(filename: str) -> str | None:
    """Extrae el tag de origen del sufijo de release del filename.

    Busca SOLO en el último bloque entre paréntesis antes de la extensión.
    Sin bloque de paréntesis no hay tag: no cae a buscar en el stem completo
    a propósito, para no confundir el título de la obra con un sufijo de
    release ("Digital Conan Vol.01" no es una release digital).
    """
    stem = Path(filename).stem
    match = _LAST_PAREN.search(stem)
    if not match:
        return None
    target = match.group(1)
    for pattern, tag in _TAG_PATTERNS:
        if re.search(pattern, target):
            return tag
    return None


# ── Parseo de ComicInfo.xml ──────────────────────────────────────────────────

_ROLE_MAP = {
    # Claves = nombre del tag TAL CUAL aparece en ComicInfo.xml (PascalCase,
    # como <Series>/<Number>): root.find() es sensible a mayúsculas.
    "Writer": "writer",
    "Penciller": "penciler",   # ComicInfo usa "Penciller" (doble L)
    "Inker": "inker",
    "Colorist": "colorist",
    "Letterer": "letterer",
    "CoverArtist": "cover_artist",
    "Editor": "editor",
    "Translator": "translator",
}
_CREDIT_TAGS = tuple(_ROLE_MAP)


@dataclass
class ComicInfo:
    """Subconjunto del esquema ComicInfo relevante para ZascArr."""
    series: str | None = None
    number: str | None = None
    volume: int | None = None
    year: int | None = None
    publisher: str | None = None
    summary: str | None = None
    genre: str | None = None
    language_iso: str | None = None
    page_count: int | None = None
    credits: dict[str, list[str]] = field(default_factory=dict)  # rol → nombres


def _text(el: ElementTree.Element | None) -> str | None:
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def parse_comic_info(data: bytes) -> ComicInfo:
    """Parsea el XML. Créditos multi-autor separados por coma."""
    root = ElementTree.fromstring(data)  # lanza ParseError: lo captura triage()
    info = ComicInfo()

    scalars = {
        "Series": "series", "Number": "number", "Publisher": "publisher",
        "Summary": "summary", "Genre": "genre", "LanguageISO": "language_iso",
    }
    for tag, attr in scalars.items():
        if v := _text(root.find(tag)):
            setattr(info, attr, v)

    for tag, attr in (("Volume", "volume"), ("Year", "year"),
                      ("PageCount", "page_count")):
        if v := _text(root.find(tag)):
            try:
                setattr(info, attr, int(v))
            except ValueError:
                pass  # Volume/Year no numéricos existen en la escena; ignorar

    for tag in _CREDIT_TAGS:
        if v := _text(root.find(tag)):
            names = [n.strip() for n in v.split(",") if n.strip()]
            if names:
                info.credits[_ROLE_MAP[tag]] = names

    return info


# ── Triaje ───────────────────────────────────────────────────────────────────

def natural_key(name: str) -> list:
    """Orden natural para que página2 < página10."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


@dataclass
class TriageResult:
    path: Path
    sha256: str | None = None
    file_format: str | None = None          # cbz | cbr | pdf | cb7
    comic_info: ComicInfo | None = None
    width_px: int | None = None
    source_tag: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def strong_candidate(self) -> bool:
        """True si la capa 0 aporta lo mínimo para match directo en DB."""
        return bool(
            self.comic_info
            and self.comic_info.series
            and self.comic_info.number
        )


def _hash_and_buffer(path: Path) -> tuple[str, io.BytesIO]:
    """Lee el fichero UNA SOLA VEZ: calcula SHA256 y carga en BytesIO.

    En una Pi con HDD, leer un CBZ de 200MB dos veces (una para el hash y otra
    para el ZipFile) cuesta varios segundos por archivo. Con este approach, una
    sola lectura secuencial llena el buffer y el hash simultáneamente.

    Coste: el CBZ completo en RAM. Aceptable para el rango habitual (30-200MB).
    Para ómnibus de 500MB en una Pi de 4GB habría que perfilar, pero el caso
    del tebeo en grapa no da problemas.
    """
    h = hashlib.sha256()
    buf = io.BytesIO()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):  # chunks de 1MB
            h.update(chunk)
            buf.write(chunk)
    buf.seek(0)
    return h.hexdigest(), buf


def triage(path: Path) -> TriageResult:
    """Punto de entrada del importer. Excepciones internas: ninguna sale."""
    result = TriageResult(path=path)
    result.source_tag = guess_source_tag(path.name)
    ext = path.suffix.lower()
    result.file_format = ext.lstrip(".")

    if ext not in {".cbz", ".zip"}:
        # CBR requeriría rarfile+unrar (dependencia externa opcional).
        # Decisión: NO instalar unrar solo por ComicInfo. CBR → Capa 1.
        result.warnings.append(f"formato {ext}: triaje solo por filename")
        return result

    try:
        sha256, buf = _hash_and_buffer(path)
        zf = zipfile.ZipFile(buf)
    except (OSError, zipfile.BadZipFile) as exc:
        # sha256 se deja sin asignar a propósito: el hash de basura binaria
        # de un zip roto no sirve para dedupe (dos descargas incompletas
        # del mismo origen casi nunca cortan en el mismo byte) y dejarlo
        # puesto sugeriría una identidad de contenido que no existe.
        result.warnings.append(f"zip ilegible: {exc}")
        return result
    result.sha256 = sha256

    with zf:
        names = zf.namelist()

        # ComicInfo.xml: convención: en la raíz del zip.
        entry = next(
            (n for n in names if n.lower().endswith("comicinfo.xml")),
            None,
        )
        if entry:
            try:
                result.comic_info = parse_comic_info(zf.read(entry))
            except ElementTree.ParseError as exc:
                result.warnings.append(f"ComicInfo.xml malformado: {exc}")

        # width_px: primera página en orden natural.
        pages = sorted(
            (n for n in names if Path(n).suffix.lower() in IMAGE_EXTS),
            key=natural_key,
        )
        if pages:
            try:
                with Image.open(io.BytesIO(zf.read(pages[0]))) as img:
                    result.width_px = img.width
            except Exception as exc:
                result.warnings.append(f"portada ilegible: {exc}")
        else:
            result.warnings.append("zip sin páginas de imagen")

    return result
