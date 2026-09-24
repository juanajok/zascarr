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
"""
from __future__ import annotations

import asyncio
import errno
import os
import re
import shutil
import tempfile
from pathlib import Path

# Límite por componente de ruta en ext4 (y la mayoría de filesystems): 255
# bytes. Usamos 240 para dejar margen al sufijo " (NN)" o "#NNN" que se añade
# después del nombre saneado, de modo que la ruta final nunca de ENAMETOOLONG.
_MAX_SEGMENT_BYTES = 240


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


def safe_move(src: str | Path, dest: str | Path) -> Path:
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

    # Ya está en su sitio (mismo fichero): no hay nada que mover.
    if src.resolve() == dest.resolve():
        return dest

    if not src.exists():
        raise FileNotFoundError(f"Origen inexistente: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest = _unique_path(dest)  # A3: nunca pisar un destino ya ocupado.

    src_size = src.stat().st_size

    if _same_filesystem(src, dest):
        # Mismo disco: renombrado atómico, sin copia que verificar. La
        # re-comprobación acorta la ventana entre "comprobar" y "colocar".
        dest = _unique_path(dest)
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
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    # Sin missing_ok a propósito: si el original ya no está, es una anomalía
    # que debe sonar, no silenciarse (L4).
    src.unlink()
    return dest


async def safe_move_async(src: str | Path, dest: str | Path) -> Path:
    """`safe_move` fuera del event loop (I/O de disco potencialmente grande)."""
    return await asyncio.to_thread(safe_move, src, dest)
