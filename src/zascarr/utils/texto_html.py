"""HTML de una fuente → texto plano, para enseñarlo sin interpretarlo.

Las fuentes (Comic Vine, sobre todo) entregan descripciones en HTML. Esto las convierte en
texto: sin etiquetas, sin el contenido de `script`/`style`, con las entidades decodificadas y
los espacios colapsados. Nunca interpreta el HTML. Vive en `utils` porque lo usan la web
(Descubrir, U14) y el servicio del asistente de carpetas (#311), que limpia **antes** de
recortar.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

_BLOQUES = frozenset({
    "p", "br", "div", "li", "ul", "ol", "tr", "td", "th", "table", "blockquote", "section",
    "article", "h1", "h2", "h3", "h4", "h5", "h6"})
_OCULTOS = frozenset({"script", "style"})


class _APlano(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._ocultos = 0

    def handle_starttag(self, tag, attrs):
        if tag in _OCULTOS:
            self._ocultos += 1
        elif tag in _BLOQUES:
            self.partes.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOQUES:
            self.partes.append(" ")

    def handle_endtag(self, tag):
        if tag in _OCULTOS:
            self._ocultos = max(0, self._ocultos - 1)
        elif tag in _BLOQUES:
            self.partes.append(" ")

    def handle_data(self, data):
        if not self._ocultos:
            self.partes.append(data)


_ETIQUETA_CORTADA = re.compile(r"<[^>]*$")
_ETIQUETAS = re.compile(r"<[^>]*>")


def texto_plano(crudo: str | None) -> str:
    """El HTML de la fuente como texto: sin etiquetas, sin el contenido de `script`/`style`, con las
    entidades decodificadas y los espacios colapsados. Nunca interpreta el HTML (se escapa)."""
    if not crudo:
        return ""
    p = _APlano()
    try:
        p.feed(crudo)
        p.close()
        texto = "".join(p.partes)
    except Exception:  # noqa: BLE001 — un HTML que el analizador no admite no puede tumbar la búsqueda
        texto = _ETIQUETAS.sub(" ", crudo)
    texto = " ".join(texto.split())
    return _ETIQUETA_CORTADA.sub("", texto).strip()
