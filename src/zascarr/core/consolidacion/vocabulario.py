"""Canonicalización mínima para comparar valores de fuentes (CCM-2)."""
from __future__ import annotations

import re

_ALIAS_EDITORIAL = {
    "editorial planeta s a": "Planeta Cómic",
    "editorial planeta sa": "Planeta Cómic",
    "planeta deagostini": "Planeta Cómic",
    "planeta comic": "Planeta Cómic",
    "editorial bruguera s a": "Bruguera",
    "editorial bruguera sa": "Bruguera",
    "bruguera": "Bruguera",
    "forum": "Fórum",
    "comics forum": "Fórum",
}
_SUFIJOS = re.compile(r"\b(s\.?\s*a\.?|s\.?\s*l\.?|s\.?\s*c\.?\s*p\.?)\b", re.I)


def _limpio(texto: str) -> str:
    valor = " ".join(str(texto).split())
    valor = _SUFIJOS.sub("", valor).strip(" ,.")
    return valor


def editorial_canonica(nombre: str | None) -> str | None:
    """Nombre de editorial normalizado para comparar; conserva una forma legible."""
    if not nombre:
        return None
    limpio = _limpio(nombre)
    if not limpio:
        return None
    clave = limpio.casefold().replace(".", "")
    return _ALIAS_EDITORIAL.get(clave, limpio)


def idioma_canonico(valor: str | None) -> str | None:
    if not valor:
        return None
    texto = str(valor).strip().lower()
    return {"spa": "es", "spanish": "es", "español": "es", "espanol": "es"}.get(texto, texto)


def valor_comparable(campo: str, valor: object) -> object:
    """Normaliza para comparar, sin decidir todavía qué se aplica."""
    if valor is None:
        return None
    if campo in {"start_year", "end_year", "total_issues", "page_count"}:
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return None
    if campo == "publisher_name":
        return editorial_canonica(str(valor))
    if campo == "language":
        return idioma_canonico(str(valor))
    if campo == "description":
        return " ".join(str(valor).split()) or None
    return " ".join(str(valor).split()) or None
