"""#344 BL-PACK1, cortes 1-2: paquetes RAR/ZIP de Descargas, sin extraer ni escribir.

Solo lectura: recorre las carpetas de Descargas configuradas, clasifica por firma y lista el
contenido con topes. No toca la biblioteca, no crea temporales de extracción y no importa nada.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
import threading
import time
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

import structlog

from zascarr.config import get_settings
from zascarr.core.formato_contenedor import (
    MAX_DIRECTORIO_CENTRAL,
    MAX_ENTRADAS,
    MAX_RATIO_LEIDA,
    Firma,
    firma_de,
    firma_de_bytes,
    leer_cabecera_zip,
)
from zascarr.utils import lector_rar

logger = structlog.get_logger()

TTL_SEGUNDOS = 15 * 60
PROPOSITO = "paquete_descarga"
MAX_BYTES_TOTAL = 8 * 1024**3
MAX_BYTES_ENTRADA = 2 * 1024**3
RAR_MAX_ENTRADAS = 1000
_EXT_ANIDADO = {".rar", ".zip"}
_MULTIVOLUMEN = re.compile(r"(?i)(?:\.part\d+\.rar|\.r\d{2,3})$")


class PaqueteError(Exception):
    """Causa legible de un paquete que no se puede listar."""

    def __init__(self, causa: str, accion: str = "") -> None:
        super().__init__(causa)
        self.causa = causa
        self.accion = accion


class TokenPaqueteInvalido(Exception):  # noqa: N818
    pass


@dataclass(frozen=True)
class PaquetePendiente:
    ruta: Path
    raiz: Path
    relativa: str
    nombre: str
    tamano: int
    mtime_ns: int
    firma: str
    estado: str
    causa: str
    dev: int
    ino: int
    token: str = ""
    fd: int = -1


@dataclass(frozen=True)
class EntradaPaquete:
    nombre: str
    tamano: int
    tipo: str
    se_importa: bool
    causa: str = ""


@dataclass(frozen=True)
class ListadoPaquete:
    paquete: PaquetePendiente
    formato: str
    entradas: tuple[EntradaPaquete, ...]
    ignoradas: tuple[EntradaPaquete, ...]
    bytes_estimados: int
    tipo_confirmado: bool = True


def _firma_texto(firma: Firma) -> str:
    return {Firma.ZIP: "ZIP", Firma.RAR: "RAR"}.get(firma, "")


def _raices_descargas(ajustes=None) -> list[Path]:
    a = ajustes or get_settings()
    raices: list[Path] = []
    for valor in (
        getattr(a, "transmission_download_dir", None),
        getattr(a, "amule_incoming_dir", None),
        getattr(a, "downloads_path", None),
    ):
        if valor:
            p = Path(valor)
            if p not in raices:
                raices.append(p)
    return raices


def _candidato(
    ruta: Path, raiz: Path, *, secret: str, ahora: float | None = None
) -> PaquetePendiente | None:
    try:
        st = ruta.stat(follow_symlinks=False)
    except OSError:
        return None
    if not ruta.is_file() or ruta.is_symlink():
        return None
    nombre = ruta.name
    extension = ruta.suffix.lower()
    if extension not in {".zip", ".rar"} and not _MULTIVOLUMEN.search(nombre):
        return None
    firma = firma_de(ruta)
    estado = "listo"
    causa = ""
    if _MULTIVOLUMEN.search(nombre):
        estado, causa = "multivolumen", "Está dividido en varios archivos."
    elif firma not in (Firma.ZIP, Firma.RAR):
        estado, causa = "no_legible", "No es un paquete legible."
    try:
        rel = str(ruta.relative_to(raiz))
    except ValueError:
        return None
    p = PaquetePendiente(
        ruta=ruta,
        raiz=raiz,
        relativa=rel,
        nombre=nombre,
        tamano=st.st_size,
        mtime_ns=st.st_mtime_ns,
        firma=_firma_texto(firma),
        estado=estado,
        causa=causa,
        dev=st.st_dev,
        ino=st.st_ino,
    )
    if estado == "listo" and secret:
        p = PaquetePendiente(**{**p.__dict__, "token": crear_token_paquete(p, secret, ahora=ahora)})
    return p


def detectar_paquetes(
    *, ajustes=None, secret: str | None = None, ahora: float | None = None
) -> list[PaquetePendiente]:
    """Candidatos en Descargas, deduplicados por inodo y ordenados por nombre."""
    a = ajustes or get_settings()
    clave = a.secret_key if secret is None else secret
    vistos: set[tuple[int, int]] = set()
    salida: list[PaquetePendiente] = []
    for raiz in _raices_descargas(a):
        if not raiz.is_dir():
            continue
        try:
            recorrido = list(os.walk(raiz, followlinks=False))
        except OSError:
            continue
        for carpeta, dirs, ficheros in recorrido:
            dirs[:] = [d for d in dirs if not (Path(carpeta) / d).is_symlink()]
            for fichero in ficheros:
                p = Path(carpeta) / fichero
                try:
                    st = p.stat(follow_symlinks=False)
                except OSError:
                    continue
                clave_inodo = (st.st_dev, st.st_ino)
                if clave_inodo in vistos:
                    continue
                vistos.add(clave_inodo)
                candidato = _candidato(p, raiz, secret=clave, ahora=ahora)
                if candidato is not None:
                    salida.append(candidato)
    return sorted(salida, key=lambda x: (x.nombre.lower(), str(x.ruta)))


_TOKENS: dict[str, tuple[float, dict]] = {}
_TOKENS_LOCK = threading.Lock()


def _limpiar_tokens(ahora: float) -> None:
    for clave, (_exp, _datos) in list(_TOKENS.items()):
        if _exp < ahora:
            _TOKENS.pop(clave, None)


def crear_token_paquete(p: PaquetePendiente, secret: str = "", *, ahora: float | None = None,
                        ttl: int = TTL_SEGUNDOS) -> str:
    """Token opaco: el estado (ruta e identidad) vive solo en este proceso."""
    token = secrets.token_urlsafe(32)
    exp = (time.time() if ahora is None else ahora) + ttl
    datos = {"ruta": str(p.ruta), "raiz": str(p.raiz), "dev": p.dev, "ino": p.ino,
             "sz": p.tamano, "mt": p.mtime_ns, "f": p.firma}
    with _TOKENS_LOCK:
        _limpiar_tokens(time.time() if ahora is None else ahora)
        _TOKENS[token] = (exp, datos)
    return token


def _abrir_identidad(ruta: Path, esperado: tuple[int, int, int, int]) -> int:
    fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != esperado:
            raise TokenPaqueteInvalido
        return fd
    except BaseException:
        os.close(fd)
        raise


def verificar_token_paquete(token: str, *, ajustes=None, secret: str | None = None,
                            ahora: float | None = None) -> PaquetePendiente:
    a = ajustes or get_settings()
    momento = time.time() if ahora is None else ahora
    if not token or not isinstance(token, str):
        raise TokenPaqueteInvalido
    with _TOKENS_LOCK:
        entrada = _TOKENS.pop(token, None)          # un solo uso: replay rechazado
    if entrada is None or entrada[0] < momento:
        raise TokenPaqueteInvalido
    d = entrada[1]
    try:
        raiz = Path(d["raiz"])
        if raiz not in _raices_descargas(a):
            raise TokenPaqueteInvalido
        ruta = Path(d["ruta"])
        if raiz not in ruta.parents:
            raise TokenPaqueteInvalido
        fd = _abrir_identidad(ruta, (d["dev"], d["ino"], d["sz"], d["mt"]))
        firma = _firma_texto(firma_de(ruta))
        if firma != d["f"]:
            os.close(fd)
            raise TokenPaqueteInvalido
        return PaquetePendiente(ruta=ruta, raiz=raiz, relativa=str(ruta.relative_to(raiz)),
                                nombre=ruta.name, tamano=d["sz"], mtime_ns=d["mt"],
                                firma=firma, estado="listo", causa="", dev=d["dev"],
                                ino=d["ino"], token=token, fd=fd)
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
        raise TokenPaqueteInvalido from exc


def _nombre_zip_seguro(nombre: str) -> bool:
    if "\x00" in nombre or any(ord(c) < 32 for c in nombre):
        return False
    if "\\" in nombre or nombre.startswith("/") or ".." in Path(nombre).parts:
        return False
    return not (len(nombre) >= 2 and nombre[1] == ":")


def listar_paquete(p: PaquetePendiente, *, temporal: Path | None = None) -> ListadoPaquete:
    if p.estado != "listo":
        raise PaqueteError(p.causa or "No se puede leer este paquete.")
    fd = p.fd
    propio = fd < 0
    if propio:
        try:
            fd = _abrir_identidad(p.ruta, (p.dev, p.ino, p.tamano, p.mtime_ns))
        except (OSError, TokenPaqueteInvalido) as exc:
            raise PaqueteError("El paquete cambió o ya no está.") from exc
    try:
        if p.firma == "ZIP":
            return _listar_zip(p, fd)
        if p.firma == "RAR":
            return _listar_rar(p, fd, temporal=temporal)
        raise PaqueteError("No es un paquete legible.")
    finally:
        if propio:
            with __import__("contextlib").suppress(OSError):
                os.close(fd)


def _agrupar(
    p: PaquetePendiente,
    formato: str,
    entradas: list[EntradaPaquete],
    ignoradas: list[EntradaPaquete],
    *,
    tipo_confirmado: bool = True,
) -> ListadoPaquete:
    if not entradas:
        raise PaqueteError("No contiene tebeos.", "Prueba con otro paquete de Descargas.")
    return ListadoPaquete(
        paquete=p,
        formato=formato,
        entradas=tuple(entradas),
        ignoradas=tuple(ignoradas),
        bytes_estimados=sum(e.tamano for e in entradas),
        tipo_confirmado=tipo_confirmado,
    )


def _listar_zip(p: PaquetePendiente, fd: int) -> ListadoPaquete:
    cab = leer_cabecera_zip(Path(f"/proc/self/fd/{fd}"))
    if cab is None:
        raise PaqueteError("El paquete está dañado o truncado.")
    if cab.entradas > MAX_ENTRADAS:
        raise PaqueteError("El paquete tiene demasiados archivos.")
    if cab.tam_directorio > MAX_DIRECTORIO_CENTRAL:
        raise PaqueteError("El paquete tiene un índice demasiado grande.")
    try:
        with zipfile.ZipFile(os.fdopen(os.dup(fd), "rb")) as z:
            infos = z.infolist()
            if len(infos) > MAX_ENTRADAS:
                raise PaqueteError("El paquete tiene demasiados archivos.")
            total = sum(i.file_size for i in infos)
            if total > MAX_BYTES_TOTAL:
                raise PaqueteError("El paquete declara un tamaño excesivo.")
            if any(i.flag_bits & 0x1 for i in infos):
                raise PaqueteError("El paquete tiene contraseña.")
            entradas: list[EntradaPaquete] = []
            ignoradas: list[EntradaPaquete] = []
            for info in infos:
                if info.filename.endswith("/"):
                    continue
                if not _nombre_zip_seguro(info.filename):
                    raise PaqueteError("El paquete contiene nombres de archivo no seguros.")
                if info.file_size > MAX_BYTES_ENTRADA:
                    raise PaqueteError("Un archivo de dentro es demasiado grande.")
                if (
                    info.compress_size
                    and info.file_size / max(info.compress_size, 1) > MAX_RATIO_LEIDA
                ):
                    raise PaqueteError("El paquete está demasiado comprimido.")
                ext = Path(info.filename).suffix.lower()
                if ext in _EXT_ANIDADO:
                    raise PaqueteError(
                        "Contiene otro paquete; ábrelo por separado.",
                        "Guarda el paquete interior como archivo aparte.",
                    )
                if ext not in {".cbz", ".cbr"}:
                    ignoradas.append(
                        EntradaPaquete(
                            info.filename, info.file_size, "otro", False, "no es un tebeo"
                        )
                    )
                    continue
                with z.open(info) as f:
                    firma = firma_de_bytes(f.read(512))
                tipo = _firma_texto(firma)
                if tipo not in {"ZIP", "RAR"}:
                    ignoradas.append(
                        EntradaPaquete(
                            info.filename, info.file_size, "otro", False, "no es un tebeo"
                        )
                    )
                    continue
                entradas.append(EntradaPaquete(info.filename, info.file_size, tipo, True))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError,
            EOFError, ValueError, zlib.error, OSError) as exc:
        raise PaqueteError("El paquete está dañado o truncado.") from exc
    return _agrupar(p, "ZIP", entradas, ignoradas)


def _listar_rar(p: PaquetePendiente, fd: int, *, temporal: Path | None = None) -> ListadoPaquete:
    if not lector_rar.disponible():
        raise PaqueteError(
            "Falta la herramienta para leer RAR.",
            "Instala unar y lsar en el servidor.",
        )
    casa = Path(tempfile.gettempdir()) if temporal is None else temporal
    try:
        listado = lector_rar.listar(
            Path(f"/proc/self/fd/{fd}"), temporal=casa,
            max_bytes_declarados=MAX_BYTES_TOTAL, pass_fds=(fd,),
        )
    except lector_rar.ErrorRar as exc:
        raise PaqueteError(
            "No se pudo leer el paquete RAR.",
            "Comprueba que el paquete está completo y sin contraseña.",
        ) from exc
    if len(listado.entradas) > RAR_MAX_ENTRADAS:
        raise PaqueteError("El paquete tiene demasiados archivos.")
    if sum(e.tamano for e in listado.entradas) > MAX_BYTES_TOTAL:
        raise PaqueteError("El paquete declara un tamaño excesivo.")
    if any(e.cifrada for e in listado.entradas):
        raise PaqueteError("El paquete tiene contraseña.")
    entradas: list[EntradaPaquete] = []
    ignoradas: list[EntradaPaquete] = []
    for e in listado.entradas:
        if e.es_directorio:
            continue
        if e.tamano > MAX_BYTES_ENTRADA:
            raise PaqueteError("Un archivo de dentro es demasiado grande.")
        ext = Path(e.nombre).suffix.lower()
        if ext in _EXT_ANIDADO:
            raise PaqueteError("Contiene otro paquete; ábrelo por separado.")
        if ext not in {".cbz", ".cbr"}:
            ignoradas.append(EntradaPaquete(e.nombre, e.tamano, "otro", False, "no es un tebeo"))
            continue
        entradas.append(EntradaPaquete(e.nombre, e.tamano, ext[1:].upper(), True))
    return _agrupar(p, "RAR", entradas, ignoradas, tipo_confirmado=False)
