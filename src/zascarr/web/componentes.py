"""
Componentes de la UI (V2): el vocabulario de estados y avisos, definido UNA sola vez.

Las macros de `templates/_componentes.html` (chip, aviso, grupo, estado_vacio, progreso,
region_viva) no deciden aspectos: los piden aquí. Así un mismo estado se ve igual en Pendientes,
Deseados, Estado y Duplicados, y cambiar cómo se ve «advertencia» es tocar una línea, no buscar
en cada plantilla.

Esto es SOLO el vocabulario visual. Qué estado de dominio (`WishlistStatus`, salud del sistema…)
corresponde a qué aspecto lo decide cada pantalla en su momento (V8, V9) con funciones puras en
`services/`; no se adelanta aquí.
"""
from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment


@dataclass(frozen=True)
class Aspecto:
    """Cómo se ve un estado. El icono acompaña al color: el estado no depende solo de él."""

    clase: str      # clase CSS de matiz ('' = neutro)
    icono: str      # carácter decorativo (aria-hidden); '' = sin icono


#: estado → aspecto. Las claves son las del vocabulario de la maqueta.
ASPECTOS: dict[str, Aspecto] = {
    "neutro": Aspecto("", ""),
    "ok": Aspecto("ok", "✓"),
    "warn": Aspecto("warn", "!"),
    "amber": Aspecto("amber", "?"),
    "info": Aspecto("info", "i"),
}


@dataclass(frozen=True)
class TipoAviso:
    clase: str      # clase CSS completa del contenedor
    icono: str
    rol: str        # 'status' (cortés) o 'alert' (asertivo): solo lo grave interrumpe


#: tipo de aviso → presentación. `nota` es la didascalia amarilla de siempre (.caption).
TIPOS_AVISO: dict[str, TipoAviso] = {
    "nota": TipoAviso("caption", "", "status"),
    "info": TipoAviso("aviso info", "i", "status"),
    "ok": TipoAviso("aviso ok", "✓", "status"),
    "amber": TipoAviso("aviso amber", "?", "status"),
    "warn": TipoAviso("aviso warn", "!", "alert"),
}


def aspecto(estado: str) -> Aspecto:
    """Aspecto de un estado; un estado desconocido FALLA (no se pinta neutro en silencio)."""
    try:
        return ASPECTOS[estado]
    except KeyError:
        raise ValueError(
            f"Estado de chip desconocido: {estado!r}. Válidos: {', '.join(ASPECTOS)}."
        ) from None


def tipo_aviso(tipo: str) -> TipoAviso:
    try:
        return TIPOS_AVISO[tipo]
    except KeyError:
        raise ValueError(
            f"Tipo de aviso desconocido: {tipo!r}. Válidos: {', '.join(TIPOS_AVISO)}."
        ) from None


#: macros de `_componentes.html`, disponibles en las plantillas como `ui.<macro>`.
MACROS = ("chip", "aviso", "grupo", "estado_vacio", "progreso", "region_viva")
PLANTILLA = "_componentes.html"
#: ÚNICO nombre que se añade al entorno de Jinja.
ESPACIO_DE_NOMBRES = "ui"


def registrar(env: Environment) -> None:
    """Expone las macros en cualquier plantilla del entorno como `ui.chip(...)`, `ui.aviso(...)`…
    sin tocar ningún `TemplateResponse` ni los contextos de los routers (misma lección que
    `auth_activo`, A6).

    Un solo espacio de nombres, NO una macro global por cada una: Jinja incorpora los globales al
    contexto de TODAS las plantillas, así que un global `aviso` hacía verdadero el `{% if aviso %}`
    de `_ajustes_guardado.html` en cada respuesta que no pasaba esa variable y pintaba
    `<Macro 'aviso'>` como texto de ayuda (reproducido y corregido en la revisión de V2).

    Los ayudantes (`aspecto`, `tipo_aviso`) tampoco son globales del entorno: se pasan como globales
    de ESA plantilla, que es donde las macros los resuelven al ejecutarse."""
    modulo = env.get_template(
        PLANTILLA, globals={"aspecto": aspecto, "tipo_aviso": tipo_aviso}).module
    env.globals[ESPACIO_DE_NOMBRES] = modulo
