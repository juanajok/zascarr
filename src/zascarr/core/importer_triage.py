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
  - SHA256 en streaming y ZipFile abierto desde la ruta: la memoria no depende
    del tamaño del fichero. El diseño original cargaba el CBZ entero en un
    BytesIO para leer el disco una sola vez; con integrales de más de 1 GB
    (biblioteca real, 2026-10-01) y 512 MB por contenedor eso mataba el proceso.
    El ZipFile solo lee el directorio central y las entradas que se piden.
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

from zascarr.core.formato_contenedor import (  # noqa: F401  (IMAGE_EXTS y natural_key se reexportan: otros módulos los importan de aquí)
    AVISO_CLASE,
    IMAGE_EXTS,
    MAX_ENTRADAS,
    EntradaNoLegible,
    aviso_de_formato,
    clasificar_infos,
    firma_de,
    formato_contenido,
    leer_acotado,
    natural_key,
    tratamiento,
    zip_fuera_de_limite,
)
from zascarr.models import ClaseZip, Firma, Tratamiento

# ── Heurística de source_tag ─────────────────────────────────────────────────
# Solo miramos el SUFIJO de release (último bloque entre paréntesis antes de
# la extensión). Así "(Digital)" del equipo no colisiona con "Digital" en el
# título de la obra.
_TAG_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)\b(digital|webrip|web-dl|dcp)\b", "digital"),
    (r"(?i)\b(scan|scanned|c2c)\b", "scan"),
    (r"(?i)\b(hd|uhd|4k)\b", "scan_hq"),
]
_LAST_PAREN = re.compile(r"\(([^)]+)\)\s*$")

# DoS: un ComicInfo.xml real mide pocos KB. Rechazar los enormes ANTES de
# descomprimirlos en memoria (una ZIP bomb no debe reventar una Pi).
MAX_COMICINFO_BYTES = 1 * 1024 * 1024   # 1 MiB
MAX_ZIP_ENTRIES = MAX_ENTRADAS          # entradas máximas por ZIP (antes 1000; el máximo medido en la biblioteca real es 941)
# El tope de 500 MiB descomprimidos EN TOTAL desapareció (#307, D3): dejaba sin ComicInfo ni anchura a los ZIP grandes aunque solo se
# lee una página. Ahora se acota la ENTRADA QUE SE LEE (`formato_contenedor.MAX_ENTRADA_LEIDA` / `MAX_RATIO_LEIDA`).


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

@dataclass
class TriageResult:
    path: Path
    sha256: str | None = None
    file_format: str | None = None          # cbz | cbr | pdf | cb7 (la extensión DECLARADA)
    formato_contenido: dict | None = None   # el formato REAL por contenido (#307); va a files.metadata
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


def sha256_streaming(path: Path) -> str:
    """SHA256 sin cargar el fichero en RAM. Para cuando solo hace falta
    el digest: el CBR del triaje (no se descomprime) y la auditoría de
    biblioteca (B16), que recorre miles de archivos en una Pi."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def triage(path: Path) -> TriageResult:
    """Punto de entrada del importer. Excepciones internas: ninguna sale."""
    result = TriageResult(path=path)
    result.source_tag = guess_source_tag(path.name)
    ext = path.suffix.lower()
    result.file_format = ext.lstrip(".")

    # #307: la decisión de qué hacer con el fichero sale de un único sitio (`formato_contenedor`), por contenido y no solo por extensión.
    firma = firma_de(path)
    trat = tratamiento(ext, firma)
    result.formato_contenido = formato_contenido(firma)

    if trat is Tratamiento.AVISAR and ext in (".cbz", ".zip") and firma is Firma.OTRO:
        # Declarado ZIP, pero el contenido no es ningún contenedor conocido: es un fichero ROTO o una descarga incompleta. Como siempre: sin hash
        # (dos descargas incompletas casi nunca cortan en el mismo byte; un hash sugeriría una identidad de contenido que no existe).
        result.warnings.append("zip ilegible: el contenido no es un ZIP válido")
        return result

    if trat is not Tratamiento.LEER_COMO_ZIP:
        # Bug real encontrado en vivo (2026-09-25, B16): este return salía SIN calcular el sha256, así que ningún .cbr tenía hash y la
        # deduplicación de B3 no funcionaba para ellos. Hashear NO exige descomprimir: son los bytes del fichero. En streaming.
        try:
            result.sha256 = sha256_streaming(path)
        except OSError as exc:
            result.warnings.append(f"ilegible para hash: {exc}")
        result.warnings.append(f"formato {ext}: triaje solo por filename")
        if trat is Tratamiento.AVISAR:
            result.warnings.append(aviso_de_formato(ext, firma))
        return result

    # Hash en streaming y zip abierto DESDE LA RUTA: la memoria no depende del tamaño del fichero (integrales de 1,2 GB, ensayo 2026-10-01).
    # El ZipFile solo lee el directorio central y las pocas entradas que se piden.
    try:
        sha256 = sha256_streaming(path)
        if zip_fuera_de_limite(path):                    # sin abrirlo: `ZipFile()` cargaría el directorio central entero en memoria
            result.sha256 = sha256
            result.formato_contenido = formato_contenido(firma, ClaseZip.LIMITE)
            result.warnings.append(AVISO_CLASE[ClaseZip.LIMITE] + " (ignorado)")
            return result
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        # sha256 sin asignar a propósito: el hash de basura binaria de un zip roto no sirve para dedupe.
        result.warnings.append(f"zip ilegible: {exc}")
        result.formato_contenido = formato_contenido(firma, ClaseZip.INVALIDO)
        return result
    result.sha256 = sha256

    with zf:
        infos = zf.infolist()
        cls = clasificar_infos(infos)
        result.formato_contenido = formato_contenido(firma, cls.clase)
        declarado_tebeo = ext in (".cbz", ".zip")        # el usuario lo declara tebeo: la clase no bloquea la lectura (sí los topes)
        if cls.clase in (ClaseZip.LIMITE, ClaseZip.CIFRADO):
            result.warnings.append(AVISO_CLASE[cls.clase] + " (ignorado)")
            return result
        if not declarado_tebeo and cls.clase is not ClaseZip.TEBEO:
            # Un .cbr/.cb7 que es un ZIP pero no un tebeo comprobado: se queda con hash, sin portada ni ComicInfo, y se dice por qué.
            result.warnings.append(AVISO_CLASE.get(cls.clase, "No se pudo comprobar que sea un tebeo."))
            return result
        # Un .cbz/.zip declarado se lee como siempre y NO recibe aviso por su clase (un especial de 8 páginas o un pack no son un error): la clase
        # queda guardada en `formato_contenido` para quien la necesite.

        names = [i.filename for i in infos]
        por_nombre = {i.filename: i for i in infos}

        # ComicInfo.xml: convención: en la raíz del zip.
        entry = next((n for n in names if n.lower().endswith("comicinfo.xml")), None)
        if entry:
            info = por_nombre[entry]
            if info.file_size > MAX_COMICINFO_BYTES:
                result.warnings.append("ComicInfo.xml demasiado grande (ignorado)")
            else:
                try:
                    result.comic_info = parse_comic_info(leer_acotado(zf, info, tope=MAX_COMICINFO_BYTES))
                except EntradaNoLegible as exc:
                    result.warnings.append(f"ComicInfo.xml {exc} (ignorado)")
                except ElementTree.ParseError as exc:
                    result.warnings.append(f"ComicInfo.xml malformado: {exc}")

        # width_px: primera página en orden natural.
        pages = sorted((n for n in names if Path(n).suffix.lower() in IMAGE_EXTS), key=natural_key)
        if pages:
            try:
                with Image.open(io.BytesIO(leer_acotado(zf, por_nombre[pages[0]]))) as img:
                    result.width_px = img.width
            except EntradaNoLegible as exc:
                result.warnings.append(f"la primera página {exc} (ignorada)")
            except Exception as exc:
                result.warnings.append(f"portada ilegible: {exc}")
        else:
            result.warnings.append("zip sin páginas de imagen")

    return result
