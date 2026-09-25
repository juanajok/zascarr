"""
Detección de prefijos de orden de lectura por evidencia de cohorte.

Un prefijo numérico suelto al principio del nombre ("42 Dreadstar...",
"65 Dreadstar...") no lleva ningún marcador (ni punto, ni guion) que lo
distinga de un título que empieza por cifra ("100 Balas...", "52...").
Son la MISMA forma — ninguna regla local de naming.py puede
distinguirlos sin inventar (medido en producción, 2026-09-26: 6 de 7
errores del estrato dominante de la biblioteca real son justo esto).

Los propios datos del coleccionista sí distinguen los dos casos:
  - "Dreadstar" aparece con ~70 prefijos DISTINTOS y el resto del
    nombre estable → el prefijo es orden de lectura suyo, no del tebeo.
  - "100 Balas" aparece siempre con el mismo "100" → es parte del
    título.

Este módulo agrupa por "firma" (el nombre sin ningún token numérico) y,
dentro de cada cohorte con evidencia suficiente, decide si el prefijo
VARÍA (orden de lectura, se descarta) o es CONSTANTE (parte del
título, se conserva). Es evidencia sacada de los datos, no una regex
más ajustada a los ejemplos que ya conozco.

Contratos (decisión de producto, 2026-09-26 — ver docs/BACKLOG.md):
  1. NUNCA crea una serie. Solo informa si el primer token es o no
     parte del título; a qué serie pertenece sigue siendo enteramente
     decisión del matcher, contra el catálogo real.
  2. Umbral explícito (`UMBRAL_EVIDENCIA`) y explicación registrada en
     cada pista, para que el ciclo de importación pueda dejar constancia
     ("orden de lectura '42' descartado por cohorte de 71 archivos") —
     es la explicación que alimenta la sugerencia de B12.
  3. No alimenta el alias local de B13 de forma distinta a cualquier
     otro archivo: este módulo no toca esa vía en absoluto — sigue
     siendo el humano, en ReviewService.assign_to_series, quien aprende
     un alias.
  4. Determinista por ejecución: son funciones PURAS sobre la lista de
     nombres que se les pase, sin E/S ni estado oculto. El llamador
     (Importer/LibraryAdopter) las ejecuta UNA VEZ al principio del
     ciclo, sobre la foto fija de esa pasada — añadir un archivo a
     mitad de ciclo no cambia la cohorte ya calculada para los que ya
     se procesaron.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from zascarr.utils.naming import CREDITS_PATTERN

# Con 1-2 archivos no hay evidencia de nada — podría ser coincidencia.
# 3 es el mínimo real observado en la biblioteca (packs de la escena
# suelen venir en tandas de al menos ese tamaño); por debajo, la
# cohorte se descarta entera y esos archivos siguen su camino normal
# por naming.py sin que este módulo los toque.
UMBRAL_EVIDENCIA = 3

_SEPARADORES = re.compile(r"[._\-()'’]+")
_TOKEN_NUMERICO = re.compile(r"^\d{1,4}[a-z]?$")
_EXTENSION = re.compile(r"\.\w{2,4}$")
# El CONTENIDO entre corchetes se descarta entero, no solo los corchetes
# en sí — es donde vive el crédito del traductor/scanner ("[Trad por
# Skullpirates...]", "[Traducido porke yo lo valgo]"), que varía de
# archivo a archivo DENTRO de la misma cohorte real. Dejarlo como texto
# suelto fragmentaba una cohorte de ~70 Dreadstar en decenas de
# cohortes de 1-2 archivos, cada una por debajo del umbral — bug real
# encontrado verificando este módulo contra la biblioteca real antes de
# integrarlo en el pipeline.
_CORCHETES = re.compile(r"\[[^\]]*\]")
# El mismo prefijo "bare" que SORT_PREFIX_PATTERN en naming.py no cubre
# hoy: dígitos al principio seguidos de una PALABRA, sin punto ni guion
# de por medio ("42 Dreadstar", no "42.- Dreadstar" ni "42 - Dreadstar").
_PREFIJO_BARE = re.compile(r"^(\d{1,4}[a-z]?)\s+(?=[^\W\d_])", re.IGNORECASE)


@dataclass(frozen=True)
class PistaDeCohorte:
    """Evidencia de que el prefijo numérico de UN archivo concreto es
    orden de lectura, no parte del título — con la explicación lista
    para dejar constancia en el informe del ciclo (B12)."""
    prefijo: str
    cohorte: str
    evidencia: int
    explicacion: str


def _firma(nombre: str) -> tuple[str | None, str]:
    """(prefijo suelto al principio, o None) y la "firma": el nombre
    entero sin NINGÚN token puramente numérico, para agrupar hermanos
    aunque el número de grapa real también varíe entre ellos."""
    sin_ext = _EXTENSION.sub("", nombre)
    sin_corchetes = _CORCHETES.sub(" ", sin_ext)
    # Créditos sueltos SIN corchetes ("... por Onslaught", sin "[...]"):
    # mismo motivo que arriba, reutilizando el patrón de naming.py en
    # vez de duplicarlo (evita que diverjan si alguien cambia uno).
    sin_credito = CREDITS_PATTERN.sub("", sin_corchetes)
    limpio = _SEPARADORES.sub(" ", sin_credito.lower())
    tokens = limpio.split()
    if not tokens:
        return None, ""
    prefijo = tokens[0] if _TOKEN_NUMERICO.match(tokens[0]) else None
    firma = " ".join(t for t in tokens if not _TOKEN_NUMERICO.match(t))
    return prefijo, firma


def detectar_ordenes_de_lectura(nombres: list[str]) -> dict[str, PistaDeCohorte]:
    """Agrupa por firma y decide, cohorte a cohorte, si el prefijo
    numérico inicial es orden de lectura o parte del título.

    Devuelve pistas SOLO para los archivos donde hay evidencia
    suficiente (≥UMBRAL_EVIDENCIA hermanos) Y el prefijo realmente
    varía entre ellos — si es constante en toda la cohorte, es parte
    del título ("100 Balas") y no se toca."""
    grupos: dict[str, list[tuple[str, str]]] = {}
    for nombre in nombres:
        prefijo, firma = _firma(nombre)
        if prefijo is None or not firma:
            continue
        grupos.setdefault(firma, []).append((nombre, prefijo))

    resultado: dict[str, PistaDeCohorte] = {}
    for firma, miembros in grupos.items():
        if len(miembros) < UMBRAL_EVIDENCIA:
            continue
        if len({p for _, p in miembros}) < 2:
            continue  # prefijo constante en toda la cohorte: es título
        for nombre, prefijo in miembros:
            resultado[nombre] = PistaDeCohorte(
                prefijo=prefijo,
                cohorte=firma,
                evidencia=len(miembros),
                explicacion=(
                    f"orden de lectura {prefijo!r} descartado por cohorte de "
                    f"{len(miembros)} archivos con el mismo patrón"
                ),
            )
    return resultado


def quitar_prefijo_de_cohorte(nombre: str, pista: PistaDeCohorte) -> str:
    """Aplica la pista sobre el nombre ORIGINAL (sin normalizar): quita
    el prefijo bare inicial y deja el resto intacto para que naming.py
    lo parsee con normalidad. Si el nombre ya no empieza por ese
    prefijo (llamada con la pista equivocada), lo devuelve sin tocar —
    nunca corta a ciegas."""
    m = _PREFIJO_BARE.match(nombre)
    if not m or m.group(1).lower() != pista.prefijo:
        return nombre
    return nombre[m.end():]
