# ruff: noqa: E501
"""La ruta de un archivo como la ve la PERSONA, no el contenedor.

ZascArr corre en Docker: la biblioteca se monta en `library_path` (`/media/library`) y la base guarda las rutas del contenedor. La
ruta real, la del host, es `HOST_LIBRARY_DIR` del `.env` (la que el instalador preguntó). Esta función **solo traduce para mostrar**:
nada la usa para abrir, mover o comparar ficheros, y una ruta que no cuelga de la biblioteca (o sin
`HOST_LIBRARY_DIR`) se devuelve igual.
"""
from __future__ import annotations

from pathlib import Path

from zascarr.config import get_settings


def ruta_visible(ruta: str, *, biblioteca: Path | str | None = None, host: str | None = None) -> str:
    """`ruta` con el prefijo de la biblioteca del contenedor cambiado por el del host, o `ruta` sin tocar."""
    s = get_settings()
    base = str(biblioteca if biblioteca is not None else s.library_path).rstrip("/")
    real = (host if host is not None else s.host_library_dir).strip().rstrip("/")
    if not real or not base or real == base:
        return ruta
    if ruta == base:
        return real
    if ruta.startswith(base + "/"):          # con el separador: `/media/library2/x` NO cuelga de `/media/library`
        return real + ruta[len(base):]
    return ruta
