"""Audita las clases de `web.css` frente a lo que usan las plantillas y las macros (#750, V14 F1).

Uso:
    python scripts/auditar_css.py            # informa de las dos listas (no falla)
    python scripts/auditar_css.py --strict    # falla si hay reglas de clases que nadie usa

Devuelve dos listas:
  · **sin regla**: clases que aparecen en una plantilla (o en una macro) y no tienen ninguna regla
    CSS. Muchas son ganchos de HTMX o de pruebas; se listan para revisarlas, no bloquean.
  · **sin uso**: clases con regla CSS que ya no aparecen en ninguna plantilla ni macro. Son las
    candidatas a retirar cuando la migración V0–V13 se cierra (V14).

Qué cuenta como «uso»:
  · atributos `class="…"` de todas las plantillas (los tokens con Jinja a medias se ignoran);
  · las clases que emiten las macros: la tabla de `web/componentes.py` (`chip`, `aviso` y sus
    matices) y las que se pasan como argumento a `ui.portada(..., "clase")`;
  · la lista blanca de abajo, para clases que se añaden en runtime.

La lista blanca es una **excepción declarada con motivo**, no un cajón: cualquier entrada nueva
exige justificarla en esta misma lista.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "zascarr"
PLANTILLAS = SRC / "web" / "templates"
CSS = SRC / "static" / "web.css"

#: Clases que no se ven en un `class="…"` estático. Cada una, con su motivo.
LISTA_BLANCA = {
    "htmx-request": "lo añade htmx en la petición en curso (requestClass de su configuración)",
    "htmx-indicator": "clase del indicador que añade htmx (indicatorClass)",
    "htmx-added": "la añade htmx al contenido nuevo",
    "htmx-settling": "la añade htmx durante el asentamiento",
    "htmx-swapping": "la añade htmx durante el intercambio",
    "visible": "la pone y la quita el JS en línea de estado.html",
    "estado-ok": "la construye estado.html: `\"estado-\" + meta.level`",
    "estado-warn": "la construye estado.html: `\"estado-\" + meta.level`",
    "estado-bad": "la construye estado.html: `\"estado-\" + meta.level`",
    "estado-neutral": "la construye estado.html: `\"estado-\" + meta.level`",
    "estado-dot-sm": "la construye estado.html al pintar los avisos",
    "estado-check-row": "la pone estado.html con `row.className`",
    "estado-detalle": "la pone estado.html con `pre.className`",
    "actual": "valor de `p.estado`, que se pinta como clase en `class=\"step {{ p.estado }}\"`",
    "bloqueado": "valor de `p.estado`, que se pinta como clase (dashboard/_asistente_macros)",
    "hecho": "valor de `p.estado`, que se pinta como clase (dashboard/_asistente_macros)",
    "pendiente": "valor de `p.estado`, que se pinta como clase (dashboard/_asistente_macros)",
    "siguiente": "valor de `p.estado`, que se pinta como clase (dashboard/_asistente_macros)",
}

_TOKEN_CLASE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class Auditoria:
    sin_regla: list[str] = field(default_factory=list)
    sin_uso: list[str] = field(default_factory=list)
    usadas: set[str] = field(default_factory=set)
    declaradas: set[str] = field(default_factory=set)


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
#: `class="…"` aunque dentro de las expresiones Jinja haya comillas (`selectattr("clave", …)`).
_ATRIBUTO_CLASE = re.compile(
    r'class="((?:[^"{}]|\{\{.*?\}\}|\{%.*?%\})*)"', re.S)
#: Clases escritas como literal en un ternario Jinja (`{{ 'hecho' if … else 'pendiente' }}`).
#: Solo en `{{ }}`: en un `{% if … selectattr("clave", …) %}` las cadenas son argumentos de filtro.
_LITERAL_JINJA = re.compile(r"""['"]([a-z][a-z0-9-]*)['"]""")
_TERNA_RIO = re.compile(r"\{\{(.*?)\}\}", re.S)


def clases_declaradas(css: str) -> set[str]:
    """Clases que aparecen en algún selector de la hoja (no en `url(...)` ni en valores)."""
    sin_cuerpos = _sin_comentarios(css)
    for _ in range(3):                      # quita cuerpos, también los anidados en @media
        sin_cuerpos = re.sub(r"\{[^{}]*\}", "", sin_cuerpos)
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", sin_cuerpos))


def _clases_de_atributos(html: str) -> tuple[set[str], set[str]]:
    """Clases estáticas de `class="…"` y prefijos de las que se construyen con Jinja.

    Un token como `cortesia-estado-{{ f.clase }}` no se puede resolver aquí: se devuelve su
    prefijo (`cortesia-estado-`) y la auditoría lo usa para no marcar como muertas las clases
    que empiezan por él. Un `{{ t.clase }}` completo no deja prefijo y se cubre con la tabla de
    `web/componentes.py`.
    """
    salida: set[str] = set()
    prefijos: set[str] = set()
    for valor in _ATRIBUTO_CLASE.findall(html):
        # Las clases que van como literal en un ternario (`{{ 'hecho' if … else 'pendiente' }}`).
        for expresion in _TERNA_RIO.findall(valor):
            if " if " in expresion and " else " in expresion:
                salida.update(_LITERAL_JINJA.findall(expresion))
        # Fuera las expresiones Jinja: `class="a{% if x %} b{% endif %}"` son dos clases
        # estáticas, y `class="x-{{ valor }}"` deja el prefijo `x-`.
        limpio_valor = _JINJA.sub(" ", valor)
        for token in limpio_valor.split():
            if token.endswith("-") and len(token) >= 2:
                prefijos.add(token)
            elif _TOKEN_CLASE.match(token):
                salida.add(token)
    return salida, prefijos


def _clases_por_argumento(html: str) -> set[str]:
    """Clases que se pasan como argumento con nombre (`ui.chip(..., clase="chip-falta")`)."""
    return set(re.findall(r'clase=["\']([a-z][a-z0-9-]*)["\']', html))


def _clases_de_ui_portada(html: str) -> set[str]:
    """`ui.portada(titulo, clave, src, "clase", "lazy")`: solo el 4.º argumento es clase."""
    salida: set[str] = set()
    for llamada in re.findall(r"ui\.portada\((?:[^()]|\([^()]*\))*\)", html):
        # Separar los argumentos de primer nivel respetando comas dentro de paréntesis.
        profundidad = 0
        args, actual = [], ""
        for c in llamada[len("ui.portada("):-1]:
            if c in "([":
                profundidad += 1
            elif c in ")]":
                profundidad -= 1
            if c == "," and profundidad == 0:
                args.append(actual.strip())
                actual = ""
            else:
                actual += c
        args.append(actual.strip())
        if len(args) >= 4:
            for literal in re.findall(r'"([^"]+)"', args[3]):
                if _TOKEN_CLASE.match(literal):
                    salida.add(literal)
    return salida


def _clases_de_python() -> set[str]:
    """Clases que se escriben en el HTML generado desde Python (`web/iconos.py`, etc.)."""
    salida: set[str] = set()
    for archivo in SRC.rglob("*.py"):
        if "templates" in archivo.parts:
            continue
        texto = archivo.read_text(encoding="utf-8")
        for valor in re.findall(r'class=[\\]?["\']([^"\']*)["\']', texto):
            for token in valor.split():
                if _TOKEN_CLASE.match(token):
                    salida.add(token)
    return salida


def _clases_de_componentes() -> set[str]:
    """Clases que emiten las macros: `ASPECTOS[*].clase` y `TIPOS_AVISO[*].clase`."""
    sys.path.insert(0, str(RAIZ / "src"))
    try:
        from zascarr.web.componentes import ASPECTOS, TIPOS_AVISO
    finally:
        sys.path.pop(0)
    salida: set[str] = set()
    for aspecto in ASPECTOS.values():
        salida.update(aspecto.clase.split())
    for tipo in TIPOS_AVISO.values():
        salida.update(tipo.clase.split())
    return salida


def auditar(css: str | None = None, html_por_plantilla: dict[str, str] | None = None,
            extras: set[str] | None = None, *, incluir_componentes: bool = True,
            incluir_python: bool = True) -> Auditoria:
    """Núcleo comprobable: recibe la hoja y las plantillas (o las lee del repo)."""
    css = CSS.read_text(encoding="utf-8") if css is None else css
    if html_por_plantilla is None:
        html_por_plantilla = {p.name: p.read_text(encoding="utf-8")
                             for p in sorted(PLANTILLAS.rglob("*.html"))}
    usadas: set[str] = set()
    prefijos: set[str] = set()
    for html in html_por_plantilla.values():
        estaticas, dinamicas = _clases_de_atributos(html)
        usadas.update(estaticas)
        prefijos.update(dinamicas)
        usadas.update(_clases_de_ui_portada(html))
        usadas.update(_clases_por_argumento(html))
    if incluir_componentes:
        usadas.update(_clases_de_componentes())
    if incluir_python:
        usadas.update(_clases_de_python())
    if extras:
        usadas.update(extras)
    declaradas = clases_declaradas(css)
    # Una clase declarada «usada» si es estática o si cae bajo un prefijo dinámico conocido.
    cubiertas = {c for c in declaradas if any(c.startswith(p) for p in prefijos)}
    usadas |= cubiertas
    blanco = set(LISTA_BLANCA)
    return Auditoria(
        sin_regla=sorted(usadas - declaradas - blanco),
        sin_uso=sorted(declaradas - usadas - blanco),
        usadas=usadas,
        declaradas=declaradas,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="falla también si hay reglas de clases sin uso")
    args = parser.parse_args(argv)
    r = auditar()
    print(f"Clases: {len(r.usadas)} usadas · {len(r.declaradas)} con regla · "
          f"{len(LISTA_BLANCA)} en la lista blanca")
    if r.sin_regla:
        print("\nCLASES USADAS SIN REGLA CSS (pueden ser ganchos de HTMX o de pruebas):")
        for c in r.sin_regla:
            print(f"  · .{c}")
    if r.sin_uso:
        print(f"\nREGLAS SIN USO ({len(r.sin_uso)}; candidatas a V14):")
        for c in r.sin_uso:
            print(f"  · .{c}")
    if args.strict and r.sin_uso:
        return 1
    print("\nOK: auditoría completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
