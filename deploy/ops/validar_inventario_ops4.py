"""Utilidad PURA de comparación de inventarios para C-12; no habilita B.

Ni obtiene ni sella los árboles: el llamador debe proporcionar inventarios
completos, verificados y anclados al host y al commit remoto por otros medios.
No hay herramienta de aprobación, despliegue, lectura Git ni acceso al host.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Entrada:
    """Tipo, modo Git y SHA-256 de bytes del objeto inventariado."""

    tipo: str
    modo: int
    digest: str


def _ruta_valida(ruta: object) -> bool:
    if not isinstance(ruta, str):
        return False
    try:
        largo = len(ruta.encode("utf-8"))
    except UnicodeEncodeError:
        return False
    return (
        0 < largo <= 4096
        and not ruta.startswith(("/", "-"))
        and all(p not in ("", ".", "..") for p in ruta.split("/"))
        and not any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in ruta)
    )


def _migracion(ruta: str) -> bool:
    return ruta == "alembic.ini" or ruta == "alembic/env.py" or ruta.startswith("alembic/versions/")


def _valido(arbol: Mapping[str, Entrada]) -> bool:
    return isinstance(arbol, Mapping) and all(
        _ruta_valida(p) and isinstance(e, Entrada)
        and e.tipo == "blob" and e.modo in (0o100644, 0o100755)
        and isinstance(e.digest, str) and _SHA256.fullmatch(e.digest)
        for p, e in arbol.items()
    )


def validar_superficie(
    instalado: Mapping[str, Entrada],
    candidato: Mapping[str, Entrada],
    permitidos: frozenset[str],
) -> str:
    """Rechazar cualquier diferencia fuera de rutas ordinarias preaprobadas.

    ``permitidos`` es una lista positiva ENTREGADA POR EL HOST, no derivada del
    candidato; solo puede incluir .py ya presentes en el inventario instalado.
    Incluso con resultado «conforme», el llamador NO ha demostrado que sus
    inventarios sean completos, sellados, ni que el código sea seguro.
    """
    if not _valido(instalado) or not _valido(candidato):
        return "arbol_inseguro"
    if (not isinstance(permitidos, frozenset)
            or not all(
                _ruta_valida(ruta) and ruta in instalado
                and ruta.startswith("src/zascarr/") and ruta.endswith(".py")
                and instalado[ruta].modo == 0o100644
                for ruta in permitidos
            )):
        return "politica_invalida"
    for ruta in instalado.keys() | candidato.keys():
        anterior = instalado.get(ruta)
        nuevo = candidato.get(ruta)
        if anterior == nuevo:
            continue
        if _migracion(ruta):
            return "migracion_nueva"
        if (anterior is None or nuevo is None or ruta not in permitidos
                or anterior.modo != nuevo.modo or anterior.tipo != nuevo.tipo):
            return "superficie_no_permitida"
    return "conforme"
