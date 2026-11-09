# ruff: noqa: E501
"""#478/BL-CNV1: construcción y verificación del CBZ (sin BD, sin publicar).

Extrae el RAR **entrada a entrada** con el lector de #418 y escribe un ZIP **ZIP_STORED** (sin
recomprimir), conservando nombres y orden. Verifica el temporal con un manifiesto (nombre, tamaño,
CRC32 y SHA256) antes de que el servicio lo publique. Sin `unar` real en las pruebas: el lector es
inyectable.

Límite duro del PO: CBR de **≤150 MiB**; los mayores se bloquean con motivo, sin tocar el original.
"""
from __future__ import annotations

import hashlib
import tempfile
import zipfile
import zlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from zascarr.core.formato_contenedor import MAX_ENTRADA_LEIDA, Firma, firma_de
from zascarr.utils import lector_rar

MAX_CBR_BYTES = 150 * 1024 * 1024
MAX_ENTRADAS = 1000
MAX_DECLARADOS = 500 * 1024 * 1024
MAX_ENTRADA = MAX_ENTRADA_LEIDA
_CARPETAS_COMIC = frozenset({".cbr", ".cbz", ".rar", ".zip", ".7z", ".cb7", ".pdf"})


class MotivoConversion(StrEnum):
    ARCHIVO_AUSENTE = "archivo_ausente"
    NO_ES_CBR = "no_es_cbr"
    YA_EXISTE_CBZ = "ya_existe_cbz"
    DEMASIADO_GRANDE = "demasiado_grande"
    SIN_ESPACIO = "sin_espacio"
    OTRO_DISCO = "otro_disco"
    CIFRADO = "cifrado"
    MULTIVOLUMEN = "multivolumen"
    PAQUETE = "paquete"
    ILEGIBLE = "ilegible"
    HERRAMIENTA_AUSENTE = "herramienta_ausente"
    LECTOR_DESACTIVADO = "lector_desactivado"
    NOMBRE_NO_SEGURO = "nombre_no_seguro"
    COMICINFO_DUPLICADO = "comicinfo_duplicado"
    PROPUESTA_DESACTUALIZADA = "propuesta_desactualizada"
    COMPARTIDO = "compartido"
    NO_SE_SABE = "no_se_sabe"
    CONFLICTO_DE_BLOQUEO = "conflicto_de_bloqueo"
    RESULTADO_INCIERTO = "resultado_incierto"


_MENSAJES = {
    MotivoConversion.ARCHIVO_AUSENTE: "El archivo ya no está en el disco; no se toca.",
    MotivoConversion.NO_ES_CBR: "Ese archivo no es un CBR; no se toca.",
    MotivoConversion.YA_EXISTE_CBZ: "Ya existe un CBZ con ese nombre; no se sobrescribe.",
    MotivoConversion.DEMASIADO_GRANDE: "El CBR supera el máximo permitido (150 MB); no se toca.",
    MotivoConversion.SIN_ESPACIO: "No hay espacio suficiente para el CBZ; no se toca.",
    MotivoConversion.OTRO_DISCO: "El temporal y el original estarían en discos distintos; no se toca.",
    MotivoConversion.CIFRADO: "El CBR está cifrado; no se puede convertir.",
    MotivoConversion.MULTIVOLUMEN: "El CBR es multivolumen; no se puede convertir.",
    MotivoConversion.PAQUETE: "El CBR contiene otro archivo de tebeo; no se toca.",
    MotivoConversion.ILEGIBLE: "El CBR está dañado o no se puede leer; no se toca.",
    MotivoConversion.HERRAMIENTA_AUSENTE: "Falta la herramienta para leer RAR; no se toca.",
    MotivoConversion.LECTOR_DESACTIVADO: "El lector de RAR está apagado; no se toca.",
    MotivoConversion.NOMBRE_NO_SEGURO: "El CBR trae un nombre de archivo no seguro; no se toca.",
    MotivoConversion.COMICINFO_DUPLICADO: "El CBR trae más de un ComicInfo.xml; no se toca.",
}


class ConversionBloqueadaError(Exception):
    """La conversión no puede empezar/continuar; `motivo` es de dominio y el mensaje es llano."""

    def __init__(self, motivo: MotivoConversion, mensaje: str) -> None:
        super().__init__(mensaje)
        self.motivo = motivo
        self.mensaje = mensaje


@dataclass(frozen=True)
class EntradaManifiesto:
    nombre: str
    tamano: int
    crc32: int
    sha256: str


@dataclass(frozen=True)
class Analisis:
    metodo: str
    entradas: int
    bytes_declarados: int
    estimado_salida: int


@dataclass(frozen=True)
class Construccion:
    manifiesto: tuple[EntradaManifiesto, ...]
    sha256: str
    tamano: int


def _motivo_de_error(exc: lector_rar.ErrorRar) -> MotivoConversion:
    return {
        "cifrado": MotivoConversion.CIFRADO,
        "multivolumen": MotivoConversion.MULTIVOLUMEN,
        "paquete": MotivoConversion.PAQUETE,
        "ilegible": MotivoConversion.ILEGIBLE,
        "demasiado_grande": MotivoConversion.DEMASIADO_GRANDE,
        "herramienta_ausente": MotivoConversion.HERRAMIENTA_AUSENTE,
    }.get(str(exc.motivo), MotivoConversion.ILEGIBLE)


def _comprobar_lector(lector) -> None:
    if not getattr(lector, "disponible", lambda: True)():
        raise ConversionBloqueadaError(MotivoConversion.HERRAMIENTA_AUSENTE,
                                "Falta la herramienta para leer este RAR; no se ha tocado nada.")


def _nombre_seguro(nombre: str) -> bool:
    if not nombre or "\x00" in nombre or any(ord(c) < 32 for c in nombre):
        return False
    p = Path(nombre.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        return False
    return not any(part in ("", ".") for part in p.parts)


def _es_directorio(entrada) -> bool:
    return bool(getattr(entrada, "es_directorio", False))


def _validar_entradas(entradas) -> list:
    regulares = [e for e in entradas if not _es_directorio(e)]
    if len(regulares) > MAX_ENTRADAS:
        raise ConversionBloqueadaError(MotivoConversion.DEMASIADO_GRANDE,
                                "El CBR tiene demasiadas entradas; no se toca.")
    if sum(e.tamano for e in regulares) > MAX_DECLARADOS:
        raise ConversionBloqueadaError(MotivoConversion.DEMASIADO_GRANDE,
                                "El CBR declara demasiado contenido; no se toca.")
    for e in regulares:
        if not _nombre_seguro(e.nombre):
            raise ConversionBloqueadaError(MotivoConversion.NOMBRE_NO_SEGURO,
                                    "El CBR trae un nombre de archivo no seguro; no se toca.")
        if e.tamano > MAX_ENTRADA:
            raise ConversionBloqueadaError(MotivoConversion.DEMASIADO_GRANDE,
                                    "Una página del CBR es demasiado grande; no se toca.")
        if Path(e.nombre).suffix.lower() in _CARPETAS_COMIC:
            raise ConversionBloqueadaError(MotivoConversion.PAQUETE,
                                    "El CBR contiene otro archivo de tebeo; no se toca.")
    if sum(1 for e in regulares if Path(e.nombre).name.lower() == "comicinfo.xml") > 1:
        raise ConversionBloqueadaError(MotivoConversion.COMICINFO_DUPLICADO,
                                "El CBR trae más de un ComicInfo.xml; no se toca.")
    return regulares


def comprobar_tamano(ruta: Path) -> None:
    try:
        tamano = ruta.stat().st_size
    except OSError as exc:
        raise ConversionBloqueadaError(MotivoConversion.ARCHIVO_AUSENTE,
                                "El archivo ya no está en el disco; no se toca.") from exc
    if tamano > MAX_CBR_BYTES:
        raise ConversionBloqueadaError(
            MotivoConversion.DEMASIADO_GRANDE,
            f"Este CBR ocupa {tamano / (1024 * 1024):.0f} MB y el máximo es 150 MB: "
            "no se ha tocado. Divide el archivo o espera a una fase posterior.")


def analizar(ruta: Path, *, lector=lector_rar) -> Analisis:
    """Clasifica la conversión sin escribir nada (solo lista el RAR o mira la firma)."""
    comprobar_tamano(ruta)
    if firma_de(ruta) is Firma.ZIP:
        return Analisis("renombrar_zip", 0, 0, ruta.stat().st_size)
    if not ruta.suffix.lower() == ".cbr":
        raise ConversionBloqueadaError(MotivoConversion.NO_ES_CBR,
                                "Ese archivo no es un CBR; no se toca.")
    _comprobar_lector(lector)
    try:
        with tempfile.TemporaryDirectory() as home:
            listado = lector.listar(ruta, temporal=Path(home))
    except lector_rar.ErrorRar as exc:
        raise ConversionBloqueadaError(_motivo_de_error(exc), _MENSAJES[_motivo_de_error(exc)]) from exc
    except Exception as exc:  # noqa: BLE001
        raise ConversionBloqueadaError(MotivoConversion.ILEGIBLE,
                                "No se pudo leer el CBR; no se toca.") from exc
    regulares = _validar_entradas(listado.entradas)
    return Analisis(
        "recomprimir", len(regulares), sum(e.tamano for e in regulares),
        sum(e.tamano for e in regulares),
    )


def _manifiesto_de_zip(ruta: Path) -> tuple[EntradaManifiesto, ...]:
    marcas: list[EntradaManifiesto] = []
    with zipfile.ZipFile(ruta) as zf:
        if zf.testzip() is not None:
            raise ConversionBloqueadaError(MotivoConversion.ILEGIBLE,
                                           _MENSAJES[MotivoConversion.ILEGIBLE])
        for info in zf.infolist():
            if info.is_dir():
                continue
            with zf.open(info) as fh:
                datos = fh.read(MAX_ENTRADA + 1)
            if len(datos) > MAX_ENTRADA:
                raise ConversionBloqueadaError(MotivoConversion.DEMASIADO_GRANDE,
                                               _MENSAJES[MotivoConversion.DEMASIADO_GRANDE])
            marcas.append(EntradaManifiesto(
                info.filename, info.file_size, info.CRC, hashlib.sha256(datos).hexdigest()))
    return tuple(marcas)


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def construir_cbz(original: Path, temporal: Path, *, lector=lector_rar) -> Construccion:
    """Extrae el RAR completo y escribe/verifica un CBZ ZIP_STORED en `temporal`."""
    comprobar_tamano(original)
    _comprobar_lector(lector)
    with tempfile.TemporaryDirectory() as home:
        casa = Path(home)
        try:
            listado = lector.listar(original, temporal=casa)
        except lector_rar.ErrorRar as exc:
            motivo = _motivo_de_error(exc)
            raise ConversionBloqueadaError(motivo, _MENSAJES[motivo]) from exc
        regulares = _validar_entradas(listado.entradas)
        manifiesto: list[EntradaManifiesto] = []
        with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_STORED) as zf:
            for entrada in regulares:
                try:
                    datos = lector.leer_entrada(original, entrada, MAX_ENTRADA, temporal=casa)
                except lector_rar.ErrorRar as exc:
                    motivo = _motivo_de_error(exc)
                    raise ConversionBloqueadaError(motivo, _MENSAJES[motivo]) from exc
                if len(datos) != entrada.tamano:
                    raise ConversionBloqueadaError(
                        MotivoConversion.ILEGIBLE, _MENSAJES[MotivoConversion.ILEGIBLE])
                if entrada.crc32 is not None and zlib.crc32(datos) & 0xFFFFFFFF != entrada.crc32:
                    raise ConversionBloqueadaError(
                        MotivoConversion.ILEGIBLE, _MENSAJES[MotivoConversion.ILEGIBLE])
                zf.writestr(entrada.nombre, datos, compress_type=zipfile.ZIP_STORED)
                manifiesto.append(EntradaManifiesto(
                    entrada.nombre, len(datos), zlib.crc32(datos) & 0xFFFFFFFF,
                    hashlib.sha256(datos).hexdigest()))
    verificado = _manifiesto_de_zip(temporal)
    if verificado != tuple(manifiesto):
        raise ConversionBloqueadaError(
            MotivoConversion.ILEGIBLE,
            "La verificación del CBZ nuevo no coincide con el RAR; no se publica.")
    return Construccion(tuple(manifiesto), _sha256(temporal), temporal.stat().st_size)
