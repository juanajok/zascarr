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
import hashlib
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

#: Lo que ZascArr deja en la biblioteca compartida (Samba, Kavita…) lo escribe el grupo: la
#: umask no basta porque esta capa crea con modos explícitos (#1155).
MODO_CARPETA = 0o775
MODO_ARCHIVO = 0o664


@dataclass(frozen=True)
class CopiaEnRaiz:
    """Temporal copiado dentro de la raíz; el fd se mantiene abierto hasta publicar."""
    path: Path
    fd: int
    st_dev: int
    st_ino: int
    sha256: str

    def cerrar(self) -> None:
        with contextlib.suppress(OSError):
            os.close(self.fd)


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




def _abrir_raiz_verificada(raiz: str | Path) -> tuple[Path, int]:
    """Abre la raíz y verifica que el fd es exactamente su ruta canónica."""
    root_res = Path(raiz).resolve(strict=False)
    if not root_res.is_dir():
        raise DestinoFueraDeRaizError("La raíz no existe o no es un directorio.")
    fd = -1
    try:
        fd = os.open(root_res, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st_fd = os.fstat(fd)
        st_path = os.stat(root_res, follow_symlinks=False)
        if (st_fd.st_dev, st_fd.st_ino) != (st_path.st_dev, st_path.st_ino):
            raise DestinoFueraDeRaizError("La raíz cambió entre la validación y la apertura.")
        abierto = os.readlink(f"/proc/self/fd/{fd}")
        if os.path.normpath(abierto) != str(root_res):
            raise DestinoFueraDeRaizError("La raíz abierta no es la ruta canónica esperada.")
        return root_res, fd
    except BaseException as exc:
        if fd >= 0:
            with contextlib.suppress(OSError):
                os.close(fd)
        if isinstance(exc, DestinoFueraDeRaizError):
            raise
        if isinstance(exc, OSError):
            raise DestinoFueraDeRaizError(
                "No se pudo abrir o verificar la raíz autorizada.") from exc
        raise


def _crear_carpeta(nombre: str, parent_fd: int) -> int:
    """Crea una carpeta con escritura de grupo, con cualquier umask, y devuelve su fd.

    `mkdir` hereda el setgid de la carpeta padre (Linux); `fchmod` fija los bits de permiso
    y por eso se vuelve a poner el setgid que ya tuviera, para no perder el grupo heredado.
    """
    os.mkdir(nombre, MODO_CARPETA, dir_fd=parent_fd)
    fd = os.open(nombre, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        os.fchmod(fd, MODO_CARPETA | (os.fstat(fd).st_mode & stat.S_ISGID))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _abrir_padre_en_raiz(raiz_fd: int, relativo: Path, *, crear: bool = True) -> tuple[int, str]:
    """Recorre/crea los componentes del padre con dir_fd y O_NOFOLLOW."""
    parent_fd = raiz_fd
    for parte in relativo.parts[:-1]:
        try:
            fd = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                         dir_fd=parent_fd)
        except FileNotFoundError:
            if not crear:
                raise
            fd = _crear_carpeta(parte, parent_fd)
        if parent_fd != raiz_fd:
            os.close(parent_fd)
        parent_fd = fd
    return parent_fd, relativo.parts[-1]


def copiar_en_raiz(src: str | Path, temp: str | Path, raiz: str | Path, *,
                   sha256: str | None = None, size: int | None = None) -> CopiaEnRaiz:
    """Copia por descriptores a un temporal dentro de la raíz, sin seguir symlinks."""
    root_res, root_fd = _abrir_raiz_verificada(raiz)
    try:
        size_origen = os.stat(src, follow_symlinks=False).st_size
    except OSError:
        os.close(root_fd)
        raise
    try:
        comprobar_espacio(root_res, size_origen, "copiar el archivo a la biblioteca")
        temp_abs = Path(temp).resolve(strict=False)
    except BaseException:
        os.close(root_fd)
        raise
    try:
        relativo = temp_abs.relative_to(root_res)
    except ValueError:
        os.close(root_fd)
        raise DestinoFueraDeRaizError("El temporal no cuelga de la raíz autorizada.") from None
    parent_fd = root_fd
    try:
        parent_fd, final_name = _abrir_padre_en_raiz(root_fd, relativo)
        try:
            os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError(errno.EEXIST, "El temporal ya existe", final_name)
        temp_fd = os.open(final_name, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
                          0o600, dir_fd=parent_fd)
        source = Path(src)
        try:
            src_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
        except BaseException:
            st_temp = os.fstat(temp_fd)
            with contextlib.suppress(OSError):
                os.close(temp_fd)
            with contextlib.suppress(OSError):
                st_name = os.stat(final_name, dir_fd=parent_fd,
                                  follow_symlinks=False)
                if (st_name.st_dev, st_name.st_ino) == (st_temp.st_dev, st_temp.st_ino):
                    os.unlink(final_name, dir_fd=parent_fd)
            raise
        src_fd = -1
        ok = False
        try:
            src_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=src_parent)
            digest = hashlib.sha256()
            total = 0
            with os.fdopen(os.dup(src_fd), "rb") as entrada, \
                    os.fdopen(os.dup(temp_fd), "wb") as salida:
                while True:
                    bloque = entrada.read(1024 * 1024)
                    if not bloque:
                        break
                    digest.update(bloque)
                    total += len(bloque)
                    salida.write(bloque)
                salida.flush()
                os.fsync(salida.fileno())
            os.close(src_fd)
            os.close(src_parent)
            if size is not None and total != size:
                raise OSError("copia incompleta: el tamaño no coincide")
            if sha256 is not None and digest.hexdigest() != sha256:
                raise OSError("copia incompleta: el sha256 no coincide")
            # El temporal nace 0600 (nadie lo ve a medias); ya verificado, se abre al grupo antes
            # de publicarlo: sin esto el coleccionista no podría mover ni borrar lo asignado.
            os.fchmod(temp_fd, MODO_ARCHIVO)
            ok = True
            st_temp = os.fstat(temp_fd)
            return CopiaEnRaiz(path=root_res / relativo.parent / final_name,
                               fd=temp_fd, st_dev=st_temp.st_dev,
                               st_ino=st_temp.st_ino, sha256=digest.hexdigest())
        finally:
            with contextlib.suppress(OSError):
                os.close(src_parent)
            if src_fd >= 0:
                with contextlib.suppress(OSError):
                    os.close(src_fd)
            if not ok:
                with contextlib.suppress(OSError):
                    st_temp = os.fstat(temp_fd)
                    st_name = os.stat(final_name, dir_fd=parent_fd,
                                      follow_symlinks=False)
                    if (st_name.st_dev, st_name.st_ino) == (st_temp.st_dev, st_temp.st_ino):
                        os.unlink(final_name, dir_fd=parent_fd)
                with contextlib.suppress(OSError):
                    os.close(temp_fd)
    finally:
        if parent_fd != root_fd:
            with contextlib.suppress(OSError):
                os.close(parent_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)



def eliminar_en_raiz(path: str | Path, raiz: str | Path, *,
                     inodo_esperado: tuple[int, int] | None = None) -> bool:
    """Borra un archivo bajo la raíz usando dir_fd; no sigue symlinks. False si no existía."""
    root_res, root_fd = _abrir_raiz_verificada(raiz)
    try:
        relativo = Path(path).resolve(strict=False).relative_to(root_res)
    except ValueError:
        os.close(root_fd)
        raise DestinoFueraDeRaizError("El archivo no cuelga de la raíz autorizada.") from None
    parent_fd = root_fd
    try:
        try:
            parent_fd, nombre = _abrir_padre_en_raiz(root_fd, relativo, crear=False)
        except FileNotFoundError:
            return False
        if inodo_esperado is not None:
            try:
                st = os.stat(nombre, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if (st.st_dev, st.st_ino) != inodo_esperado:
                return False
        try:
            os.unlink(nombre, dir_fd=parent_fd)
        except FileNotFoundError:
            return False
        return True
    finally:
        if parent_fd != root_fd:
            with contextlib.suppress(OSError):
                os.close(parent_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)

def publicar_en_raiz(temp: str | Path, dest: str | Path, raiz: str | Path,
                     *, fd: int | None = None,
                     inodo_esperado: tuple[int, int] | None = None,
                     sha256_esperado: str | None = None) -> Path:
    """Publica con enlaces confinados desde el fd del temporal (sin reabrir por nombre).

    Riesgo residual aceptado (SEC): un proceso con el mismo UID y escritura en la raíz
    puede modificar el temporal entre la verificación y el ``link``. Ese actor ya puede
    escribir directamente en la biblioteca, así que no es una frontera de privilegios;
    A3 protege frente a fallos, no frente a un atacante local con escritura.
    """
    if fd is not None and inodo_esperado is not None:
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != inodo_esperado:
            raise DestinoFueraDeRaizError("El temporal cambió de inodo antes de publicar.")
        if sha256_esperado is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            digest = hashlib.sha256()
            while True:
                bloque = os.read(fd, 1024 * 1024)
                if not bloque:
                    break
                digest.update(bloque)
            if digest.hexdigest() != sha256_esperado:
                raise DestinoFueraDeRaizError(
                    "El contenido del temporal cambió antes de publicar.")
        root_res, root_fd = _abrir_raiz_verificada(raiz)
        try:
            relativo = Path(dest).resolve(strict=False).relative_to(root_res)
            parent_fd, final_name = _abrir_padre_en_raiz(root_fd, relativo)
            try:
                try:
                    st = os.stat(final_name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    st = None
                if st is not None:
                    stem, suffix = os.path.splitext(final_name)
                    n = 1
                    while True:
                        candidato = f"{stem} ({n}){suffix}"
                        try:
                            os.stat(candidato, dir_fd=parent_fd, follow_symlinks=False)
                        except FileNotFoundError:
                            final_name = candidato
                            break
                        n += 1
                try:
                    st_tmp = os.stat(Path(temp).name, dir_fd=parent_fd,
                                     follow_symlinks=False)
                except FileNotFoundError as exc:
                    raise DestinoFueraDeRaizError(
                        "El temporal desapareció antes de publicar.") from exc
                if (st_tmp.st_dev, st_tmp.st_ino) != inodo_esperado:
                    raise DestinoFueraDeRaizError(
                        "El temporal fue sustituido por otro inodo.")
                os.link(f"/proc/self/fd/{fd}", final_name, dst_dir_fd=parent_fd,
                        follow_symlinks=True)
                with contextlib.suppress(OSError):
                    st_tmp = os.stat(Path(temp).name, dir_fd=parent_fd,
                                     follow_symlinks=False)
                    if (st_tmp.st_dev, st_tmp.st_ino) == inodo_esperado:
                        os.unlink(Path(temp).name, dir_fd=parent_fd)
                return root_res / relativo.parent / final_name
            finally:
                if parent_fd != root_fd:
                    with contextlib.suppress(OSError):
                        os.close(parent_fd)
        finally:
            with contextlib.suppress(OSError):
                os.close(root_fd)
    return safe_move_en_raiz(temp, dest, raiz)

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
    root_fd = -1
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
    except BaseException as exc:
        if root_fd >= 0:
            with contextlib.suppress(OSError):
                os.close(root_fd)
        if isinstance(exc, DestinoFueraDeRaizError):
            raise
        if isinstance(exc, OSError):
            raise DestinoFueraDeRaizError("No se pudo abrir la raíz autorizada.") from exc
        raise
    parent_fd = root_fd
    try:
        for parte in relativo.parts[:-1]:
            try:
                fd = os.open(parte, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent_fd)
            except FileNotFoundError:
                fd = _crear_carpeta(parte, parent_fd)
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
                os.fchmod(temp_fd, MODO_ARCHIVO)  # verificado: se abre al grupo antes de publicar
                st_temp = os.fstat(temp_fd)
                # Publica desde el fd: aunque el nombre temporal se sustituya,
                # se enlaza el inodo que se acaba de verificar.
                os.link(f"/proc/self/fd/{temp_fd}", final_name,
                        dst_dir_fd=parent_fd, follow_symlinks=True)
                try:
                    st_name = os.stat(temp_name, dir_fd=parent_fd,
                                      follow_symlinks=False)
                    if (st_name.st_dev, st_name.st_ino) == (st_temp.st_dev, st_temp.st_ino):
                        os.unlink(temp_name, dir_fd=parent_fd)
                finally:
                    os.close(temp_fd)
                    temp_fd = -1
                os.unlink(source.name, dir_fd=src_parent)
                return root_res / relativo.parent / final_name
            except BaseException:
                if temp_fd >= 0:
                    st_temp = os.fstat(temp_fd)
                    os.close(temp_fd)
                    with contextlib.suppress(OSError):
                        st_name = os.stat(temp_name, dir_fd=parent_fd,
                                          follow_symlinks=False)
                        if (st_name.st_dev, st_name.st_ino) == (st_temp.st_dev, st_temp.st_ino):
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
