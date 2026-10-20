# ruff: noqa: E501
# (los trazados SVG son datos copiados tal cual: partirlos más solo los haría ilegibles)
"""
Iconos de la navegación: SVG de trazo, en línea, sin librería ni petición aparte.

Antes eran caracteres de texto (⌂ ✎ ▤ ⚖ ★ ♥ ⚙): cada sistema los dibujaba con su fuente, con
grosores y tamaños distintos, y alguno ni existía en Android. Un SVG con `stroke="currentColor"`
se ve igual en todas partes y toma el color del enlace (activo, hover, tema oscuro).

Trazados de Lucide (https://lucide.dev), versión lucide-static 1.60.0, copiados a mano solo los
que se usan. Licencia ISC, compatible con la GPL-3.0 del proyecto; su aviso, que debe acompañar
a las copias, es este:

    ISC License

    Copyright (c) 2026 Lucide Icons and Contributors

    Permission to use, copy, modify, and/or distribute this software for any
    purpose with or without fee is hereby granted, provided that the above
    copyright notice and this permission notice appear in all copies.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

Añadir uno: copiar los elementos de `icons/<nombre>.svg` de `npm pack lucide-static` (sin el
`<svg>` exterior) y anotar arriba la versión si cambia.
"""
from __future__ import annotations

from markupsafe import Markup

#: nombre → elementos interiores del SVG (rejilla de 24, trazo de 2). Origen entre paréntesis.
ICONOS: dict[str, str] = {
    "inicio": (  # house
        '<path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/>'
        '<path d="M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2'
        ' 2H5a2 2 0 0 1-2-2z"/>'
    ),
    "revisar": (  # inbox
        '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
        '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24'
        'a2 2 0 0 0-1.79 1.11z"/>'
    ),
    "biblioteca": (  # library
        '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>'
    ),
    "duplicados": (  # copy
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'
    ),
    "descubrir": (  # search
        '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>'
    ),
    "deseados": (  # star
        '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756'
        'a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771'
        '.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122'
        ' 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597'
        '-1.16z"/>'
    ),
    "estado": (  # activity
        '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0'
        '-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/>'
    ),
    "ajustes": (  # settings
        '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33'
        ' 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34'
        ' 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34'
        ' 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "mas": (  # ellipsis
        '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>'
    ),
}


def icono(nombre: str) -> Markup:
    """SVG decorativo de la navegación; un nombre desconocido FALLA (no se pinta un hueco en silencio).

    `aria-hidden` y `focusable="false"`: el nombre lo dice siempre el texto del enlace."""
    try:
        interior = ICONOS[nombre]
    except KeyError:
        raise ValueError(f"Icono desconocido: {nombre!r}. Válidos: {', '.join(ICONOS)}.") from None
    return Markup(
        '<svg class="ico-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
        ' stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        f"{interior}</svg>"
    )
