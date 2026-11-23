"""Puntuación de una candidata de fuente (aprendizajes 2026-11-23).

Sustituye al título-como-única-señal: normaliza títulos (acentos, artículos,
«Vol.», marcas de edición), trata el número de números como **subconjunto**
(30 de 57 es compatible), compara la editorial por **contención** («Image
Comics» contiene «Image»), tolera ±1 año y usa los nombres de archivo cuando la
serie no tiene año. Es una función pura: no consulta fuentes ni escribe.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

_ARTICULOS = frozenset({"the", "la", "el", "los", "las", "le", "les", "un", "una"})
_MARCAS = frozenset({
    "integral", "omnibus", "tomo", "volumen", "comp", "compendio",
    "deluxe", "absolute", "hardcover", "tpb", "trade", "graphic", "novel", "edic",
})
_VOL = re.compile(r"\bvol(?:umen)?\.?\s*\d+\b", re.IGNORECASE)
_ANIO = re.compile(r"\b(19|20)\d{2}\b")


def normalizar_titulo(titulo: str | None) -> str:
    """Minúsculas, sin acentos ni marcas de edición/volumen; solo palabras."""
    t = unicodedata.normalize("NFKD", titulo or "")
    t = t.encode("ascii", "ignore").decode("ascii").lower()
    t = _VOL.sub(" ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(p for p in t.split() if p not in _MARCAS and p not in _ARTICULOS)


def editorial_compatible(local: str | None, fuente: str | None) -> bool:
    """«Image Comics»/«Image» y «DC»/«DC Comics» son la misma; vacío no contradice."""
    a = normalizar_titulo(local)
    b = normalizar_titulo(fuente)
    if not a or not b:
        return True
    return a in b or b in a


@dataclass(frozen=True)
class Puntuacion:
    total: float
    titulo: float
    anio: float
    numeros: float
    editorial: float
    motivos: list[str] = field(default_factory=list)

    @property
    def nivel(self) -> str:
        if self.total >= 0.85:
            return "aplicable"
        return "revisar" if self.total >= 0.70 else "descartar"


def puntuar(*, titulo_local: str | None, anio_local: int | None, numeros_local: int | None,
            editorial_local: str | None, titulo_fuente: str | None,
            anio_fuente: int | None, numeros_fuente: int | None,
            editorial_fuente: str | None, archivos: list[str] | None = None) -> Puntuacion:
    motivos: list[str] = []
    nl, nf = normalizar_titulo(titulo_local), normalizar_titulo(titulo_fuente)
    titulo = difflib.SequenceMatcher(None, nl, nf).ratio() if nl and nf else 0.0
    if nl and nf and nl == nf:
        motivos.append("título equivalente tras normalizar")

    anio = 0.0
    if anio_local and anio_fuente:
        d = abs(anio_local - anio_fuente)
        anio = 1.0 if d <= 1 else max(0.0, 1 - d / 5)
        if d > 1:
            motivos.append(f"año {anio_local} frente a {anio_fuente}")
    else:
        anio_local_archivo = next((int(m.group()) for a in (archivos or [])
                                   for m in [_ANIO.search(a)] if m), None)
        if anio_local_archivo and anio_fuente and abs(anio_local_archivo - anio_fuente) <= 1:
            anio = 1.0
            motivos.append(f"año tomado del archivo: {anio_local_archivo}")

    numeros = 0.0
    if numeros_local and numeros_fuente:
        if numeros_local <= numeros_fuente:
            numeros = 1.0
            if numeros_local < numeros_fuente:
                motivos.append(f"{numeros_local} de {numeros_fuente}: subconjunto")
        else:
            numeros = max(0.0, 1 - (numeros_local - numeros_fuente) / max(10, numeros_fuente))
            motivos.append(f"{numeros_local} números locales frente a {numeros_fuente}")

    editorial = 0.0
    if editorial_local and editorial_fuente:
        editorial = 1.0 if editorial_compatible(editorial_local, editorial_fuente) else 0.0
        if editorial == 0.0:
            motivos.append(f"editorial {editorial_local} frente a {editorial_fuente}")

    total = round(0.50 * titulo + 0.20 * anio + 0.15 * numeros + 0.15 * editorial, 3)
    return Puntuacion(total, round(titulo, 3), round(anio, 3), round(numeros, 3),
                      round(editorial, 3), motivos)
