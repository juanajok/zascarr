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


def _par_de_raiz(ruta: str, settings) -> tuple[str, str] | None:
    """Par (ruta de contenedor, host) de la raíz más específica que contiene `ruta`."""
    crudas = [p.strip() for p in (getattr(settings, "library_roots", "") or "").split(",") if p.strip()]
    if not crudas:
        crudas = [str(settings.library_path)]
    hosts = [p.strip() for p in (getattr(settings, "host_library_roots", "") or "").split(",")]
    candidatas = []
    for i, cruda in enumerate(crudas):
        base = cruda.rstrip("/")
        if ruta == base or ruta.startswith(base + "/"):
            candidatas.append((len(base), base, hosts[i] if i < len(hosts) else ""))
    if not candidatas:
        return None
    _, base, host = max(candidatas, key=lambda c: c[0])
    return base, host


def ruta_visible(ruta: str, *, biblioteca: Path | str | None = None, host: str | None = None) -> str:
    """`ruta` con el prefijo de la biblioteca del contenedor cambiado por el del host, o `ruta` sin tocar."""
    s = get_settings()
    if biblioteca is None and host is None:
        par = _par_de_raiz(str(ruta), s)
        if par is not None:
            biblioteca, host = par[0], (par[1] or None)
    base = str(biblioteca if biblioteca is not None else s.library_path).rstrip("/")
    real = (host if host is not None else s.host_library_dir).strip().rstrip("/")
    if not real or not base or real == base:
        return ruta
    if ruta == base:
        return real
    if ruta.startswith(base + "/"):          # con el separador: `/media/library2/x` NO cuelga de `/media/library`
        return real + ruta[len(base):]
    return ruta
