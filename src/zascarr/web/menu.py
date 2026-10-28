"""
Menú de navegación (V3): qué entradas hay, cómo se agrupan y cuál está activa.

Datos puros, sin dependencias de la aplicación: lo usan la macro `ui.menu` (plantilla), el router
del fragmento de contadores y las pruebas. Una sola fuente: el menú de escritorio, la barra inferior
del móvil y el panel «Más» salen de esta lista, nunca se escriben a mano en una plantilla.

LAS URL NO CAMBIAN (decisión 2 de la Épica V): solo cambian las etiquetas y qué etiqueta cuelga de
qué ruta. `/estado` se queda en `/estado`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entrada:
    clave: str
    etiqueta: str
    url: str
    grupo: str
    icono: str                      # nombre en `web/iconos.py::ICONOS` (SVG decorativo)
    corta: str | None = None        # etiqueta de la barra inferior, si la larga no cabe
    movil_principal: bool = False   # ¿va en la barra inferior? (si no, en «Más»)
    contador: str | None = None     # id del contador que muestra: pendientes | deseados | estado


GRUPOS = ("Mi colección", "Añadir", "Sistema")

ENTRADAS: tuple[Entrada, ...] = (
    Entrada("inicio", "Inicio", "/ui/", "Mi colección", "inicio", movil_principal=True),
    Entrada("revisar", "Por revisar", "/ui/pendientes", "Mi colección", "revisar",
            corta="Revisar", movil_principal=True, contador="pendientes"),
    Entrada("biblioteca", "Biblioteca", "/ui/biblioteca", "Mi colección", "biblioteca"),
    Entrada("duplicados", "Duplicados", "/ui/auditoria", "Mi colección", "duplicados"),
    Entrada("descubrir", "Descubrir", "/ui/descubrir", "Añadir", "descubrir"),
    Entrada("deseados", "Deseados", "/ui/wishlist", "Añadir", "deseados",
            movil_principal=True, contador="deseados"),
    Entrada("estado", "Estado", "/estado", "Sistema", "estado",
            movil_principal=True, contador="estado"),
    Entrada("ajustes", "Ajustes", "/ui/ajustes", "Sistema", "ajustes"),
)

#: prefijo de ruta → entrada. Se compara por segmentos (`/ui/pendientes` y `/ui/pendientes/x`, no
#: `/ui/pendientes-otra-cosa`). La ficha de serie cuelga de Biblioteca.
_PREFIJOS: tuple[tuple[str, str], ...] = (
    ("/ui/pendientes", "revisar"),
    ("/ui/biblioteca", "biblioteca"),
    ("/ui/series", "biblioteca"),
    ("/ui/auditoria", "duplicados"),
    ("/ui/descubrir", "descubrir"),
    ("/ui/wishlist", "deseados"),
    ("/ui/ajustes", "ajustes"),
    ("/estado", "estado"),
    ("/ui/no-disponibles", "estado"),  # #231: cuelga de Estado
)


def entrada_activa(ruta: str) -> str | None:
    """Clave de la entrada que corresponde a `ruta`, o None (aviso legal, login…)."""
    ruta = (ruta or "").split("?", 1)[0]
    if ruta in ("/ui", "/ui/"):
        return "inicio"
    for prefijo, clave in _PREFIJOS:
        if ruta == prefijo or ruta.startswith(prefijo + "/"):
            return clave
    return None


def etiqueta_de(clave: str) -> str:
    return next(e.etiqueta for e in ENTRADAS if e.clave == clave)
