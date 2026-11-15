"""
Utilidades de sistema de ficheros con garantías de no-destrucción (A3).

Regla permanente del producto: el instalador y el importador NUNCA borran
archivos originales; solo copian/mueven a destinos verificados. Este módulo
es la implementación de esa regla para todo lo que mueve ficheros:

  - `sanitize_segment`: convierte un título (dato externo no fiable) en un
    segmento de ruta de un solo nivel, truncado al límite del filesystem. Un
    "Batman/Superman" o un ".." en el título de una serie no puede escapar de
    la biblioteca.
  - `safe_move`: mueve un fichero sin arriesgar ni el original ni lo ya
    importado. Nunca sobreescribe un destino ocupado y, cuando origen y
    destino viven en discos distintos (el caso real: descargas en un disco,
    biblioteca en otro), copia y verifica ANTES de borrar el original.
  - `safe_move_async`: el mismo `safe_move` en un hilo aparte, para llamarlo
    desde handlers async sin congelar el event loop (CLAUDE.md §4).
  - `listar_comics`: el recorrido de carpetas que comparten el importador y el
    adoptador. Es **síncrono a propósito** y se llama con `asyncio.to_thread`:
    sobre una biblioteca en red (SMB) cada `stat` es una ida y vuelta, y hacerlo
    en el bucle de eventos congelaba la app durante todo el recorrido.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import re
import shutil
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from zascarr.utils.espacio import comprobar_espacio

# Límite por componente de ruta en ext4 (y la mayoría de filesystems): 255
# bytes. Usamos 240 para dejar margen al sufijo " (NN)" o "#NNN" que se añade
# después del nombre saneado, de modo que la ruta final nunca de ENAMETOOLONG.
_MAX_SEGMENT_BYTES = 240


class DestinoFueraDeRaizError(OSError):
    """El destino o un symlink intermedio se sale de la raíz autorizada."""


def _validar_destino_en_raiz(raiz: str | Path, dest: str | Path) -> Path:
    """Comprueba el destino resuelto y sus componentes existentes contra la raíz.

    No sigue un symlink final (se rechaza) y exige que el padre real esté dentro
    de la raíz real. La comprobación se repite en cada paso de `safe_move`.
    """
    raiz_res = Path(raiz).resolve(strict=False)
    destino = Path(dest)
    if destino.is_symlink():
        raise DestinoFueraDeRaizError(f"El destino es un symlink: {destino.name}")
    try:
        padre_res = destino.parent.resolve(strict=False)
        destino_res = destino.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise DestinoFueraDeRaizError("No se pudo resolver el destino.") from exc
    if not padre_res.is_relative_to(raiz_res) or not destino_res.is_relative_to(raiz_res):
        raise DestinoFueraDeRaizError(
            f"El destino se sale de la raíz autorizada: {destino.name}")
    # Cada componente existente por debajo de la raíz que sea symlink debe resolver dentro.
    actual = raiz_res
    try:
        relativo = destino.relative_to(raiz_res)
    except ValueError:
        raise DestinoFueraDeRaizError(
            f"El destino no cuelga de la raíz autorizada: {destino.name}") from None
    for parte in relativo.parts[:-1]:
        actual = actual / parte
        if actual.is_symlink():
            objetivo = actual.resolve(strict=False)
            if not objetivo.is_relative_to(raiz_res):
                raise DestinoFueraDeRaizError(
                    f"Un symlink intermedio se sale de la raíz: {parte}")
    return raiz_res


def sanear_excepcion(exc: BaseException) -> str:
    """Mensaje de excepción sin rutas absolutas (para informes/logs)."""
    return re.sub(r"(?<![\w.])/(?:[^\n\r\t]+?)(?=\s*(?:$|[.;:)]))", "<ruta>", str(exc))


def safe_move_en_raiz(src: str | Path, dest: str | Path, raiz: str | Path) -> Path:
    """Mueve con descriptores y `dir_fd`, sin seguir symlinks fuera de la raíz.

    Abre la raíz una vez y recorre/crea los componentes con `O_NOFOLLOW |
    O_DIRECTORY`; el temporal se crea en el mismo descriptor de directorio y se
    publica con `os.replace(..., src_dir_fd=..., dst_dir_fd=...)`. No se elimina
    el original si cualquier comprobación falla.
    """
    root_res = Path(raiz).resolve(strict=False)
    source = Path(src)
    destino = Path(dest)
    if not root_res.is_dir():
        raise DestinoFueraDeRaizError("La raíz no existe o no es un directorio.")
    try:
        destino_res = destino.resolve(strict=False)
        relativo = destino_res.relative_to(root_res)
    except (OSError, ValueError):
        raise DestinoFueraDeRaizError("El destino no cuelga de la raíz autorizada.") from None
    if not relativo.parts:
        raise DestinoFueraDeRaizError("El destino no tiene nombre de archivo.")
    if destino.is_symlink():
        raise DestinoFueraDeRaizError("El destino final es un symlink.")
    try:
        root_fd = os.open(root_res, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st_root_fd = os.fstat(root_fd)
        st_root_path = os.stat(root_res, follow_symlinks=False)
        if (st_root_fd.st_dev, st_root_fd.st_ino) != (st_root_path.st_dev, st_root_path.st_ino):
            raise DestinoFueraDeRaizError("La raíz cambió entre la validación y la apertura.")
        try:
            abierto = os.readlink(f"/proc/self/fd/{root_fd}")
        except OSError as exc:
            raise DestinoFueraDeRaizError(
                "No se pudo verificar la ruta canónica de la raíz abierta.") from exc
        if os.path.normpath(abierto) != str(root_res):
            raise DestinoFueraDeRaizError("La raíz abierta no es la ruta canónica esperada.")
    except DestinoFueraDeRaizError:
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise
    except OSError as exc:
        raise DestinoFueraDeRaizError("No se pudo abrir la raíz autorizada.") from exc
    parent_fd = root_fd
    try:
        for parte in relativo.parts[:-1]:
            try:
                fd = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent_fd)
            except FileNotFoundError:
                os.mkdir(parte, 0o755, dir_fd=parent_fd)
                fd = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent_fd)
            if parent_fd != root_fd:
                os.close(parent_fd)
            parent_fd = fd
        final_name = relativo.parts[-1]
        final_name = relativo.parts[-1]
        try:
            st_final = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            st_final = None
        if st_final is not None:
            if stat.S_ISLNK(st_final.st_mode):
                raise DestinoFueraDeRaizError("El destino final es un symlink.")
            # A3: nombre alternativo único en el mismo dir_fd, sin salir de la raíz.
            stem, suffix = os.path.splitext(final_name)
            n = 1
            while True:
                candidato = f"{stem} ({n}){suffix}"
                try:
                    st = os.stat(candidato, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    final_name = candidato
                    break
                if stat.S_ISLNK(st.st_mode):
                    raise DestinoFueraDeRaizError("Un nombre alternativo es un symlink.")
                n += 1
        src_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            src_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=src_parent)
        except OSError as exc:
            os.close(src_parent)
            raise DestinoFueraDeRaizError("El origen es un symlink o no se puede abrir.") from exc
        try:
            st_src = os.fstat(src_fd)
            # Mismo fichero: no hay nada que mover.
            try:
                st_dst = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                st_dst = None
            if (st_dst is not None
                    and (st_dst.st_dev, st_dst.st_ino) == (st_src.st_dev, st_src.st_ino)):
                return root_res / relativo
            comprobar_espacio(root_res, st_src.st_size, "mover a la biblioteca")
            if st_src.st_dev == os.fstat(parent_fd).st_dev:
                try:
                    os.link(source.name, final_name, src_dir_fd=src_parent,
                            dst_dir_fd=parent_fd, follow_symlinks=False)
                    os.unlink(source.name, dir_fd=src_parent)
                    return root_res / relativo.parent / final_name
                except FileExistsError:
                    raise
                except OSError as exc:
                    if exc.errno != errno.EXDEV:
                        raise
            temp_name = f".{final_name}.{os.getpid()}.{uuid.uuid4().hex[:12]}.part"
            temp_fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                              0o600, dir_fd=parent_fd)
            try:
                with os.fdopen(os.dup(src_fd), "rb") as entrada, \
                        os.fdopen(os.dup(temp_fd), "wb") as salida:
                    shutil.copyfileobj(entrada, salida, length=1024 * 1024)
                    salida.flush()
                    os.fsync(salida.fileno())
                if os.fstat(temp_fd).st_size != st_src.st_size:
                    raise OSError("copia incompleta: el tamaño no coincide")
                os.close(temp_fd)
                temp_fd = -1
                os.link(temp_name, final_name, src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd, follow_symlinks=False)
                os.unlink(temp_name, dir_fd=parent_fd)
                os.unlink(source.name, dir_fd=src_parent)
                return root_res / relativo.parent / final_name
            except BaseException:
                if temp_fd >= 0:
                    os.close(temp_fd)
                with contextlib.suppress(OSError):
                    os.unlink(temp_name, dir_fd=parent_fd)
                raise
        finally:
            os.close(src_fd)
            os.close(src_parent)
    finally:
        if parent_fd != root_fd:
            with contextlib.suppress(OSError):
                os.close(parent_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)

async def safe_move_en_raiz_async(src: str | Path, dest: str | Path,
                                 raiz: str | Path) -> Path:
    """`safe_move_en_raiz` fuera del event loop."""
    return await asyncio.to_thread(safe_move_en_raiz, src, dest, raiz)


def sanitize_segment(name: str | None) -> str:
    """Convierte un nombre en un segmento de ruta seguro, de un solo nivel.

    Elimina separadores de ruta ("/" y "\\"), caracteres de control y
    secuencias de escape (".."), y trunca el resultado por debajo del límite
    de 255 bytes del filesystem (M2). El resultado puede usarse como nombre de
    carpeta o de fichero sin salirse del directorio raíz esperado.

    Nunca devuelve una cadena vacía ni "."/"..": si no queda nada útil, cae
    a "_Serie".

    Nota: los nombres reservados de Windows (CON, NUL, PRN…) no se tratan —
    ZascArr corre en Linux/Raspberry Pi; solo se anota por paridad si algún
    día se ejecutan los tests sobre un filesystem Windows.
    """
    if not name:
        return "_Serie"
    s = str(name)
    # Separadores de ruta y caracteres de control (0x00-0x1f) → espacio.
    s = re.sub(r"[/\\\x00-\x1f]+", " ", s)
    # Colapsar espacios y quitar puntos/espacios de los bordes (mata "..").
    s = re.sub(r"\s+", " ", s).strip(" .")
    if s in {"", ".", ".."}:
        return "_Serie"
    s = s.encode("utf-8")[:_MAX_SEGMENT_BYTES].decode("utf-8", errors="ignore")
    return s.rstrip(" .") or "_Serie"


def _unique_path(dest: Path) -> Path:
    """Devuelve `dest` si está libre o un nombre alternativo único si no.

    El sufijo es " (1)", " (2)", … antes de la extensión, nunca se pisa el
    fichero que ya existe. Conserva la extensión compuesta entera
    ("archive.tar.gz" → "archive (1).tar.gz", no "archive.tar (1).gz", que
    confundiría a Glob/ComicTagger), usando `dest.suffixes` completo.
    """
    if not dest.exists():
        return dest
    parent = dest.parent
    suffixes = "".join(dest.suffixes) or dest.suffix
    stem = dest.name[: -len(suffixes)] if suffixes else dest.name
    n = 1
    while (candidate := parent / f"{stem} ({n}){suffixes}").exists():
        n += 1
    return candidate


def _same_filesystem(src: Path, dest: Path) -> bool:
    try:
        return src.stat().st_dev == dest.parent.stat().st_dev
    except OSError:
        return False


def safe_move(src: str | Path, dest: str | Path, *,
              raiz: str | Path | None = None) -> Path:
    """Mueve `src` a `dest` sin arriesgar datos (A3). Devuelve el destino real.

    Garantías:
      - Si `dest` ya existe, no se sobreescribe: se usa un nombre único.
      - El original solo desaparece cuando el destino está completo. Entre
        discos distintos se copia a un temporal en el mismo directorio y se
        hace rename atómico al final; si la copia falla, se limpia el temporal
        y el original queda intacto.

    Alcance de la garantía "nunca sobreescribe": ZascArr es un solo operador
    con importador y review secuenciales (un único proceso uvicorn), así que
    no hay dos escritores compitiendo por el mismo destino. La re-comprobación
    inmediata antes de colocar reduce la ventana teórica al mínimo, pero la
    atomicidad absoluta frente a procesos externos exigiría `renameat2(
    RENAME_NOREPLACE)`, que no hace falta para este modelo de despliegue.

    La verificación entre discos es por tamaño, no por contenido: un SHA256 de
    un CBZ de 200 MB en una Pi sería caro, y el propio pipeline de importación
    ya deduplica por SHA256 aparte (importer_triage.py). Si el día de mañana se
    exige integridad de contenido, añadir `verify="sha256"` como opción.
    """
    src = Path(src)
    dest = Path(dest)
    if raiz is not None:
        return safe_move_en_raiz(src, dest, raiz)

    # Ya está en su sitio (mismo fichero): no hay nada que mover.
    if src.resolve() == dest.resolve():
        return dest

    if not src.exists():
        raise FileNotFoundError(f"Origen inexistente: {src}")

    if raiz is not None:
        _validar_destino_en_raiz(raiz, dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if raiz is not None:
        _validar_destino_en_raiz(raiz, dest)
    dest = _unique_path(dest)  # A3: nunca pisar un destino ya ocupado.
    if raiz is not None:
        _validar_destino_en_raiz(raiz, dest)

    src_size = src.stat().st_size

    if _same_filesystem(src, dest):
        # Mismo disco: renombrado atómico, sin copia que verificar. La
        # re-comprobación acorta la ventana entre "comprobar" y "colocar".
        dest = _unique_path(dest)
        if raiz is not None:
            _validar_destino_en_raiz(raiz, dest)
        try:
            os.replace(src, dest)
            return dest
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            # st_dev puede coincidir entre dos bind mounts distintos del
            # mismo filesystem host (downloads/library montados por
            # separado en docker-compose.yml) y aun así el kernel rechazar
            # rename() por cruzar el límite de mount. Cae al camino de
            # copia entre discos de más abajo con el mismo `dest`.

    # Discos distintos (o el rename anterior cruzó un límite de mount):
    # copiar y verificar ANTES de borrar el original.
    comprobar_espacio(dest.parent, src_size, "copiar el archivo a la biblioteca")
    fd, tmp_name = tempfile.mkstemp(
        dir=str(dest.parent), prefix=f".{dest.name}.", suffix=".part"
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        if tmp.stat().st_size != src_size:
            raise OSError(
                "copia incompleta: el tamaño del destino no coincide con el original"
            )
        dest = _unique_path(dest)  # re-comprobación antes de colocar (ver docstring)
        if raiz is not None:
            _validar_destino_en_raiz(raiz, dest)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    # Sin missing_ok a propósito: si el original ya no está, es una anomalía
    # que debe sonar, no silenciarse (L4).
    src.unlink()
    return dest


async def safe_move_async(src: str | Path, dest: str | Path, *,
                          raiz: str | Path | None = None) -> Path:
    """`safe_move` fuera del event loop (I/O de disco potencialmente grande)."""
    return await asyncio.to_thread(safe_move, src, dest, raiz=raiz)


def listar_comics(dirs, extensiones) -> list[Path]:
    """Cómics bajo `dirs`, sin repetir el mismo fichero.

    Deduplica por `(st_dev, st_ino)`, no por ruta: HOST_DOWNLOADS_DIR y
    HOST_AMULE_INCOMING_DIR pueden apuntar al mismo disco (bootstrap.sh los deja
    iguales cuando se da una sola carpeta), y entonces el mismo fichero aparece
    bajo dos rutas distintas dentro del contenedor — dos bind-mounts del mismo
    inodo, que `Path.resolve()` no detecta. Una carpeta que no existe se salta.

    Bloquea (E/S de disco): llamarla siempre con `asyncio.to_thread` desde
    código async (CLAUDE.md §4).
    """
    vistos: set[tuple[int, int]] = set()
    archivos: list[Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for ext in extensiones:
            for f in d.rglob(f"*{ext}"):
                if ".zascarr" in f.parts:
                    continue
                try:
                    st = f.stat()
                except OSError:
                    continue
                clave = (st.st_dev, st.st_ino)
                if clave not in vistos:
                    vistos.add(clave)
                    archivos.append(f)
    return archivos


@dataclass(frozen=True)
class Recorrido:
    """Resultado de `recorrer_comics`: los cómics vistos y cuántas carpetas o archivos NO se
    pudieron leer. Con `ilegibles > 0` el recorrido no acredita haber visto toda la carpeta."""
    archivos: list[Path]
    ilegibles: int = 0

    @property
    def completo(self) -> bool:
        return self.ilegibles == 0


def recorrer_comics(dirs, extensiones) -> Recorrido:
    """Como `listar_comics` (nombre que acaba en la extensión, sin repetir el inodo, sin seguir
    enlaces a carpetas), pero DICE lo que no pudo mirar. `Path.rglob` salta en silencio una
    subcarpeta sin permisos o un disco que falla a mitad; aquí cada carpeta que no se puede
    listar, cada archivo que no se puede consultar y cada raíz que no existe suman a `ilegibles`.

    Bloquea (E/S de disco): llamarla siempre con `asyncio.to_thread` desde código async
    (CLAUDE.md §4)."""
    exts = tuple(extensiones)
    vistos: set[tuple[int, int]] = set()
    archivos: list[Path] = []
    ilegibles = 0

    def _fallo(_exc: OSError) -> None:
        nonlocal ilegibles
        ilegibles += 1

    for d in dirs:
        if not d.is_dir():
            ilegibles += 1
            continue
        for carpeta, subcarpetas, nombres in os.walk(d, onerror=_fallo):
            # #478/#564: la cuarentena y el diario de conversión viven bajo
            # `.zascarr/` dentro de la biblioteca; no son cómics que registrar.
            subcarpetas[:] = [c for c in subcarpetas if c != ".zascarr"]
            if ".zascarr" in Path(carpeta).parts:
                continue
            for nombre in nombres:
                if not nombre.endswith(exts):
                    continue
                f = Path(carpeta) / nombre
                try:
                    st = f.stat()
                except OSError:
                    ilegibles += 1
                    continue
                clave = (st.st_dev, st.st_ino)
                if clave not in vistos:
                    vistos.add(clave)
                    archivos.append(f)
    return Recorrido(archivos, ilegibles)
