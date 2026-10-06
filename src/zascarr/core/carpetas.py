# ruff: noqa: E501
"""Lectura del nombre de las carpetas de una biblioteca (rebanada 1, solo lectura).

Módulo PURO: sin E/S, sin base de datos, sin disco. Recibe cadenas y devuelve datos. Lo comparten el
servicio de revisión (`services/revision_carpetas.py`) y la medición (`scripts/medicion/medir_carpetas.py`).

Una carpeta es una PISTA, nunca una decisión: aquí solo se separa lo que lleva el nombre (título, año,
volumen, calificadores) para que quien decide vea de dónde sale cada señal.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

#: Carpetas que agrupan por otra razón que la serie (decisión de revisión 2026-10-06: lista FIJA).
#: Además, cualquier nombre que empiece por «_» es un contenedor (`_Omnibus`, `_Unsorted`).
CONTENEDORES = frozenset({"varios", "revisar", "otros", "specials", "omnibus"})

#: Una carpeta que reúne al menos tantos títulos distintos parece de autor o de contenedor, no de serie.
#: Valor INICIAL (decisión de revisión 2026-10-06), a ajustar con la medición.
UMBRAL_AUTOR_O_CONTENEDOR = 20

_CORCHETES = re.compile(r"\[[^\]]*\]")
_PARENTESIS = re.compile(r"\(([^)]*)\)")
_ANIO = re.compile(r"^(?:19|20)\d{2}(?:\s*-\s*(?:\d{2}|\d{4}))?$")
_VOLUMEN = re.compile(r"\b(?:vol(?:umen)?|v)\.?\s*(\d{1,3})\b", re.IGNORECASE)
_EDICION_EN_PARENTESIS = re.compile(r"^(?:ed\.\s*\S.*|edici[oó]n\b.*)$", re.IGNORECASE)
_EDICION_EN_TITULO = re.compile(r"\b(omnigold|integral|deluxe)\b", re.IGNORECASE)


def sin_acentos(texto: str) -> str:
    """Minúsculas y sin diacríticos: «Gimenez» y «Giménez» comparan igual."""
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).casefold().strip()


def es_contenedor(nombre: str) -> bool:
    """¿La carpeta agrupa por otra cosa que la serie? (`_*` o la lista fija, sin acentos ni mayúsculas)."""
    return nombre.startswith("_") or sin_acentos(nombre) in CONTENEDORES


def limpiar_carpeta(nombre: str) -> tuple[str, int | None, list[str]]:
    """(título, año, etiquetas) de un nombre de carpeta: quita corchetes y paréntesis, que llevan año y
    etiquetas de release («(COMPLETO)(CRG)»), y los separa."""
    anio: int | None = None
    etiquetas: list[str] = [m.group(0) for m in _CORCHETES.finditer(nombre)]
    for m in _PARENTESIS.finditer(nombre):
        dentro = m.group(1).strip()
        if _ANIO.match(dentro):
            anio = anio or int(dentro[:4])
        else:
            etiquetas.append(m.group(0))
    titulo = _PARENTESIS.sub(" ", _CORCHETES.sub(" ", nombre))
    return re.sub(r"\s+", " ", titulo).strip(" -_."), anio, etiquetas


@dataclass(frozen=True)
class CarpetaLimpia:
    """Lo que dice el nombre de una carpeta, separado.

    `titulo` es lo que queda sin año, volumen, calificadores ni etiquetas. `titulo_completo` conserva el
    calificador de saga («Batman - Saga de Scott Snyder»): una serie con ESE título existe a veces, y
    entonces el calificador no es una contradicción.
    """
    titulo: str
    titulo_completo: str
    anio: int | None = None
    volumen: int | None = None
    calificadores: list[str] = field(default_factory=list)
    etiquetas: list[str] = field(default_factory=list)


def analizar_carpeta(nombre: str) -> CarpetaLimpia:
    """Separa título, año, volumen y calificadores («Saga de …», edición) del nombre de una carpeta."""
    completo, anio, etiquetas = limpiar_carpeta(nombre)
    calificadores: list[str] = []

    # Edición en paréntesis: «(Ed.Zinco)», «(Edición de lujo)». No es una etiqueta de release ni un año.
    for etiqueta in list(etiquetas):
        if etiqueta.startswith("(") and _EDICION_EN_PARENTESIS.match(etiqueta[1:-1].strip()):
            calificadores.append(etiqueta[1:-1].strip())
            etiquetas.remove(etiqueta)

    titulo = completo
    volumen: int | None = None
    m = _VOLUMEN.search(titulo)
    if m:
        volumen = int(m.group(1))
        titulo = (titulo[:m.start()] + " " + titulo[m.end():]).strip(" -_.")
        calificadores.append(f"Vol {volumen}")

    # Edición dentro del título («Omnigold», «Integral»).
    for m in _EDICION_EN_TITULO.finditer(titulo):
        calificadores.append(m.group(1).capitalize())
    titulo = _EDICION_EN_TITULO.sub(" ", titulo)

    # Subtítulo tras « - »: «Batman - Saga de Scott Snyder». Todo lo que sigue es calificador.
    if " - " in titulo:
        principal, _, resto = titulo.partition(" - ")
        if principal.strip() and resto.strip():
            titulo = principal
            calificadores.append(resto.strip())

    return CarpetaLimpia(
        titulo=re.sub(r"\s+", " ", titulo).strip(" -_."),
        titulo_completo=completo,
        anio=anio,
        volumen=volumen,
        calificadores=calificadores,
        etiquetas=etiquetas,
    )


@dataclass(frozen=True)
class RutaDividida:
    """Una ruta relativa a la biblioteca, partida en carpetas."""
    carpetas: tuple[str, ...]            # [tradición, c1, …]; vacío si el archivo está en la raíz
    clave: str                           # ruta de la carpeta inmediata («.» si es la raíz)
    contextual: str | None               # primera carpeta, subiendo, que no es la tradición ni contenedor
    ascendentes: tuple[str, ...]         # carpetas por encima de la contextual (todas si no hay contextual)


def dividir_ruta(partes: tuple[str, ...]) -> RutaDividida:
    """Del vector de carpetas (sin el nombre del archivo) a la clave de grupo y la carpeta contextual.

    El primer nivel es la TRADICIÓN («Comics», «BD»…): nunca es contextual. Subiendo desde el archivo se
    salta cualquier contenedor; si todo son contenedores, no hay contexto.
    """
    clave = "/".join(partes) if partes else "."
    contextual_idx: int | None = None
    for i in range(len(partes) - 1, 0, -1):
        if not es_contenedor(partes[i]):
            contextual_idx = i
            break
    if contextual_idx is None:
        return RutaDividida(partes, clave, None, partes)
    return RutaDividida(partes, clave, partes[contextual_idx], partes[:contextual_idx])


def texto_incluye(completo: str, parte: str) -> bool:
    """¿`parte` aparece en `completo`, comparando sin acentos, mayúsculas ni signos?"""
    def limpio(t: str) -> str:
        # «Vol2» y «Vol 2» son lo mismo: se separan letras y dígitos pegados.
        t = re.sub(r"(?<=[a-z])(?=\d)", " ", sin_acentos(t))
        return " ".join(re.sub(r"[^0-9a-z]+", " ", t).split())
    p = limpio(parte)
    # Palabras enteras: «Vol 2» no está en «Vol 22».
    return bool(p) and f" {p} " in f" {limpio(completo)} "
