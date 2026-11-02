"""Cómo se ve cada estado de un deseo (Deseados): qué aspecto de `ui.chip` le toca.

`web/componentes.py` define el vocabulario visual (neutro, ok, warn, amber, info) y dice que qué
estado de dominio corresponde a cuál lo decide cada pantalla con una función pura de `services/`.
Esta es la de Deseados. El aspecto lleva siempre palabra e icono (✓ ok, ! warn, i info): el estado
no depende del color.
"""
from __future__ import annotations

from zascarr.models import WishlistStatus

#: estado → aspecto de `ui.chip`. Las claves son las de `web/componentes.py::ASPECTOS`.
ASPECTO_DE_DESEO: dict[WishlistStatus, str] = {
    WishlistStatus.WANTED: "neutro",          # aún no pasa nada
    WishlistStatus.SEARCHING: "info",         # en marcha
    WishlistStatus.DOWNLOADING: "info",
    WishlistStatus.DOWNLOADED: "info",        # dice lo mismo que DOWNLOADING
    WishlistStatus.IMPORTED: "ok",            # ya está en la biblioteca
    WishlistStatus.FAILED: "warn",            # «Sin resultados»: se puede reintentar
    WishlistStatus.RETIRADO: "neutro",        # D8: lo retiró la política, no falló nada
}


def aspecto_de_deseo(estado: WishlistStatus) -> str:
    """Aspecto del chip de un deseo; un estado sin aspecto FALLA, no se pinta neutro en silencio."""
    try:
        return ASPECTO_DE_DESEO[estado]
    except KeyError:
        raise ValueError(f"Estado de deseo sin aspecto: {estado!r}.") from None
