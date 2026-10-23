"""Formato REAL de un fichero por su contenido (#307). El ÚNICO punto de decisión: `triage`, la portada, la auditoría y el relleno
de los ya registrados deciden aquí, no cada uno por su cuenta. Contrato: `docs/design/contrato-307-formato-por-contenido.md`.

Reglas que no se rompen:
  · Solo LECTURA. Nunca se renombra, mueve, convierte ni escribe el original.
  · La firma se lee de los primeros 512 bytes; clasificar un ZIP lee SOLO el directorio central (nunca descomprime).
  · Sin dependencias: stdlib (`zipfile`).
  · `file_format` (la extensión que dice el nombre) NO cambia: el formato real va aparte, así el tagger (solo CBZ declarado)
    nunca escribe en un ZIP que se llama `.cbr`.

Los umbrales salen de medir la biblioteca real (censo de 366 ZIP en la Pi, 2026-10-23): mínimo 21 imágenes y ≥ 95 % de imágenes en los
ZIP reales, primera página ≤ 7,1 MiB con ratio ≤ 1,77. Son parámetros revisables, no verdades.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from zascarr.models import ClaseZip, Firma, Tratamiento

#: Las imágenes que cuentan como «página» y el orden natural de las páginas (antes en `importer_triage`).
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def natural_key(name: str) -> list:
    """Orden natural para que página2 < página10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


#: Extensiones de contenedor: una entrada así dentro de un ZIP lo hace un «paquete» (idea de Kapowarr). `.pdf` y `.epub` cuentan (D4).
EXT_CONTENEDOR = {".cbz", ".zip", ".cbr", ".rar", ".cb7", ".7z", ".cbt", ".tar", ".gz", ".epub", ".pdf"}
#: Ficheros que no son «contenido» para la fracción de imágenes.
RUIDO = {"thumbs.db", ".ds_store", "desktop.ini", "comicinfo.xml"}

# ── Parámetros (D3, medidos) ─────────────────────────────────────────────────────────────────────────
MAX_ENTRADAS = 2000                      # máx. observado: 941
MIN_IMAGENES = 10                        # mín. observado: 21
FRACCION_IMAGENES = 0.8                  # mín. observado: 0,95
#: Tope de la ENTRADA QUE SE LEE (primera página, ComicInfo.xml), no del total: lo que importa es lo que de verdad se descomprime.
MAX_ENTRADA_LEIDA = 32 * 1024 * 1024     # primera página mayor observada: 7,1 MiB
MAX_RATIO_LEIDA = 100                    # primera página observada: ≤ 1,77

CONTRATO = 1                             # versión de lo que se guarda en `metadata["formato_contenido"]`

_ZIP = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")      # normal, vacío, partido


class EntradaNoLegible(Exception):  # noqa: N818  (nombre de dominio en español, como el resto del proyecto)
    """La entrada que se quería leer supera los topes o está dañada. El mensaje es la causa, en español llano."""


# ── 1. Firma ─────────────────────────────────────────────────────────────────────────────────────────
def firma_de_bytes(b: bytes) -> Firma:
    """Pura. `b` son los primeros bytes del fichero (hasta 512)."""
    if b[:4] in _ZIP:
        return Firma.ZIP
    if b.startswith(b"Rar!\x1a\x07"):
        return Firma.RAR
    if b.startswith(b"7z\xbc\xaf\x27\x1c"):
        return Firma.SIETE_Z
    if b[257:262] == b"ustar":
        return Firma.TAR
    return Firma.OTRO


def firma_de(path: Path) -> Firma:
    """Lee como máximo 512 bytes. Nunca lanza: un fichero que no se puede leer es `ILEGIBLE`."""
    try:
        with open(path, "rb") as fh:
            return firma_de_bytes(fh.read(512))
    except OSError:
        return Firma.ILEGIBLE


# ── 2. Qué hacer con cada combinación extensión × firma (función PURA) ──────────────────────────────
def tratamiento(ext: str, firma: Firma) -> Tratamiento:
    """`ext` es la extensión declarada en minúsculas con punto (`".cbr"`), o `""` si no tiene. Ver la matriz en el contrato (§4)."""
    if ext in (".pdf", ".epub"):
        return Tratamiento.SOLO_HASH
    if firma is Firma.ILEGIBLE:
        return Tratamiento.SOLO_HASH
    if ext in (".cbz", ".zip"):
        return Tratamiento.LEER_COMO_ZIP if firma is Firma.ZIP else Tratamiento.AVISAR
    if ext == ".cbr":
        if firma is Firma.ZIP:
            return Tratamiento.LEER_COMO_ZIP
        return Tratamiento.SOLO_HASH if firma is Firma.RAR else Tratamiento.AVISAR
    if ext == ".cb7":
        if firma is Firma.ZIP:
            return Tratamiento.LEER_COMO_ZIP
        return Tratamiento.SOLO_HASH if firma is Firma.SIETE_Z else Tratamiento.AVISAR
    # Sin extensión, doble extensión o cualquier otra: no se registra (D1); solo se avisa si es un contenedor.
    return Tratamiento.AVISAR if firma in (Firma.ZIP, Firma.RAR, Firma.SIETE_Z, Firma.TAR) else Tratamiento.SOLO_HASH


def se_lee_como_zip(ext: str, firma: Firma) -> bool:
    return tratamiento(ext, firma) is Tratamiento.LEER_COMO_ZIP


# ── 3. Clasificar un ZIP (solo el directorio central) ───────────────────────────────────────────────
@dataclass(frozen=True)
class Clasificacion:
    clase: ClaseZip
    entradas: int = 0
    imagenes: int = 0
    anidados: int = 0
    primera_pagina: str | None = None      # nombre, en orden natural


def clasificar_infos(infos: list[zipfile.ZipInfo], *, min_imagenes: int = MIN_IMAGENES, fraccion: float = FRACCION_IMAGENES,
                     max_entradas: int = MAX_ENTRADAS) -> Clasificacion:
    """Pura sobre el directorio central ya leído. No descomprime."""
    if not infos:
        return Clasificacion(ClaseZip.VACIO)
    ficheros = [i for i in infos if not i.is_dir()]
    nombres = [(i, Path(i.filename)) for i in ficheros]
    imgs = sorted((n.as_posix() for _i, n in nombres if n.suffix.lower() in IMAGE_EXTS), key=natural_key)
    primera = imgs[0] if imgs else None
    anidados = sum(1 for _i, n in nombres if n.suffix.lower() in EXT_CONTENEDOR)
    base = dict(entradas=len(ficheros), imagenes=len(imgs), anidados=anidados, primera_pagina=primera)
    if len(infos) > max_entradas:
        return Clasificacion(ClaseZip.LIMITE, **base)
    if any(i.flag_bits & 0x1 for i in ficheros):
        return Clasificacion(ClaseZip.CIFRADO, **base)
    if anidados:
        return Clasificacion(ClaseZip.PAQUETE, **base)
    contenido = sum(1 for _i, n in nombres if n.name.lower() not in RUIDO)
    if len(imgs) >= min_imagenes and contenido and len(imgs) / contenido >= fraccion:
        return Clasificacion(ClaseZip.TEBEO, **base)
    return Clasificacion(ClaseZip.NO_TEBEO, **base)


def clasificar_zip(path: Path, **kw) -> Clasificacion:
    """Abre el ZIP y lee solo su directorio central. Nunca lanza: lo que no se abre es `INVALIDO`."""
    try:
        with zipfile.ZipFile(path) as zf:
            return clasificar_infos(zf.infolist(), **kw)
    except (OSError, zipfile.BadZipFile, ValueError, NotImplementedError):
        return Clasificacion(ClaseZip.INVALIDO)


# ── 4. Leer UNA entrada con topes ───────────────────────────────────────────────────────────────────
def leer_acotado(zf: zipfile.ZipFile, info: zipfile.ZipInfo, *, tope: int | None = None, ratio: int | None = None) -> bytes:
    """Lee una entrada sin fiarse del tamaño declarado: comprueba el declarado y el ratio y, además, no lee más de `tope` bytes aunque la
    cabecera mienta. Lanza `EntradaNoLegible` con la causa. Los topes se resuelven en cada llamada (así se pueden ajustar en pruebas)."""
    tope = MAX_ENTRADA_LEIDA if tope is None else tope
    ratio = MAX_RATIO_LEIDA if ratio is None else ratio
    if info.flag_bits & 0x1:
        raise EntradaNoLegible("está protegida con contraseña")
    if info.file_size > tope:
        raise EntradaNoLegible(f"es demasiado grande ({info.file_size >> 20} MiB descomprimida; el máximo es {tope >> 20} MiB)")
    if info.compress_size > 0 and info.file_size / info.compress_size > ratio:
        raise EntradaNoLegible("se comprime de forma sospechosa (posible bomba de descompresión)")
    try:
        with zf.open(info) as fh:
            datos = fh.read(tope + 1)
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, ValueError) as exc:
        raise EntradaNoLegible(f"está dañada ({exc})") from exc
    if len(datos) > tope:
        raise EntradaNoLegible("ocupa más de lo que declara (posible bomba de descompresión)")
    return datos


# ── 5. Lo que se guarda y lo que se dice ────────────────────────────────────────────────────────────
def formato_contenido(firma: Firma, clase: ClaseZip | None = None) -> dict:
    """Lo que va a `files.metadata["formato_contenido"]` (JSON plano, sin migración)."""
    d: dict = {"firma": firma.value, "contrato": CONTRATO}
    if clase is not None:
        d["clase"] = clase.value
    return d


def formato_real_de(path: Path) -> dict | None:
    """El `formato_contenido` de un fichero ya registrado (lectura: ≤ 512 B y, si es un ZIP, su directorio central). `None` si no se pudo
    leer (disco desmontado, permisos): quien llama lo reintenta más tarde en vez de marcarlo como «no es nada»."""
    firma = firma_de(path)
    if firma is Firma.ILEGIBLE:
        return None
    return formato_contenido(firma, clasificar_zip(path).clase if firma is Firma.ZIP else None)


def puede_dar_portada(ext: str, fc: dict | None) -> bool | None:
    """¿Lo guardado en `formato_contenido` permite una portada? `None` = no hay nada guardado (decide la extensión). SIN E/S.
    Un `.cbz`/`.zip` declarado se intenta leer siempre que el contenido sea un ZIP (el usuario lo declara tebeo: un tebeo corto o un
    pack siguen dando su primera página, como hoy); un `.cbr`/`.cb7` que resulta ser ZIP solo si es un `TEBEO` comprobado."""
    if not fc:
        return None
    if fc.get("firma") != Firma.ZIP.value:
        return False
    if ext in (".cbz", ".zip"):
        return fc.get("clase") not in (ClaseZip.CIFRADO.value, ClaseZip.INVALIDO.value, ClaseZip.VACIO.value, ClaseZip.LIMITE.value)
    return fc.get("clase") == ClaseZip.TEBEO.value


# Textos revisados por UX (2026-10-23): ≤ 2 frases (qué es + qué hacer, solo si el coleccionista puede hacer algo), empezando por lo que reconoce
# (.cbz/.cbr) y con lo técnico entre paréntesis. La garantía «no cambia, mueve ni borra nada» va UNA vez, en la cabecera de la sección de la auditoría.
# Sin «entradas», «firma», «contenedor» ni nombres de clase. «Pack» es palabra del coleccionista (no confundir con «lote», interno).
AVISO_CLASE = {
    ClaseZip.PAQUETE: "Es un pack con varios tebeos dentro. ZascArr no lo trata como uno solo: descomprímelo si quieres cada número por separado.",
    ClaseZip.NO_TEBEO: "Es un archivo comprimido, pero no parece un tebeo: tiene pocas imágenes o están mezcladas con otros archivos.",
    ClaseZip.CIFRADO: "Tiene contraseña, así que ZascArr no puede abrirlo. Si la conoces, guárdalo de nuevo sin contraseña desde tu ordenador.",
    ClaseZip.INVALIDO: "Está dañado o incompleto; quizá la descarga no terminó. Prueba a descargarlo de nuevo.",
    ClaseZip.VACIO: "Está vacío: no tiene ninguna página. Prueba a descargarlo de nuevo.",
    ClaseZip.LIMITE: f"Tiene demasiados archivos dentro (más de {MAX_ENTRADAS}) y ZascArr no lo abre, por precaución. Si es un pack, descomprímelo.",
}

#: Cómo se llama, para el coleccionista, lo que hay por dentro.
_POR_DENTRO = {Firma.ZIP: "un .cbz (ZIP)", Firma.RAR: "un .cbr (RAR)", Firma.SIETE_Z: "un .cb7 (7z)", Firma.TAR: "un TAR", Firma.OTRO: "otro formato"}
_FINAL_SUGERIDO = {Firma.ZIP: ".cbz", Firma.RAR: ".cbr", Firma.SIETE_Z: ".cb7"}

#: Informativo (no es un aviso): un .cbr que por dentro es un ZIP con imágenes ya se lee. Solo para la auditoría, con chip neutro.
INFO_CBR_ES_ZIP = "Se lee como un .cbz aunque se llame .cbr. Todo bien: no hace falta hacer nada."


def aviso_de_formato(ext: str, firma: Firma) -> str:
    """Causa y acción para un fichero cuyo nombre no concuerda con su contenido, o que es un contenedor sin final de tebeo."""
    if ext in (".cbz", ".zip", ".cbr", ".cb7"):
        return (f"Se llama {ext}, pero por dentro es {_POR_DENTRO.get(firma, 'otro formato')}. "
                "Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.")
    sug = _FINAL_SUGERIDO.get(firma)
    if sug:
        return f"Parece un tebeo, pero su nombre no acaba en {sug}. Para que ZascArr lo tenga en cuenta, cambia el final del nombre a {sug} desde tu ordenador."
    return "Parece un tebeo, pero está guardado en un formato (TAR) que ZascArr no usa. Para conservarlo, conviértelo a .cbz con otro programa."


def aviso_de_extension(ext: str) -> str:
    """Los contenedores que se reconocen solo por el final del nombre (.rar, .7z, .tar, .cbt)."""
    if ext == ".rar":
        return "Es un archivo .rar. Si dentro hay un tebeo, cambia el final del nombre a .cbr; si hay varios, descomprímelo."
    if ext == ".7z":
        return "Es un archivo .7z. Si dentro hay un tebeo, cambia el final del nombre a .cb7; si hay varios, descomprímelo."
    return f"ZascArr no usa este formato ({ext.lstrip('.').upper()}). Para conservarlo como tebeo, conviértelo a .cbz con otro programa."
