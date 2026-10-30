"""Comprobación compartida de espacio libre (criterio 6 de #123).

No borra ni mueve nada: solo mide y, si no cabe, lanza un error con causa,
cifras y una acción segura. El margen (10 % + 64 MiB) cubre cabeceras,
temporales y redondeos del sistema de ficheros; no es una reserva de datos.
"""

from __future__ import annotations

import shutil
from pathlib import Path

MARGEN_FRACCION = 0.10
MARGEN_BYTES = 64 * 1024 * 1024
ACCION = (
    "Libera espacio en ese disco o mueve la biblioteca a otro disco y vuelve "
    "a intentarlo. ZascArr no ha borrado nada."
)


class EspacioInsuficienteError(OSError):
    """Falta espacio para una operación; la colección no se ha tocado."""

    def __init__(
        self, *, bytes_libres: int, bytes_necesarios: int, contexto: str, ruta: Path | None = None
    ):
        self.bytes_libres = int(bytes_libres)
        self.bytes_necesarios = int(bytes_necesarios)
        self.contexto = contexto
        self.ruta = ruta
        self.margen = _margen(self.bytes_necesarios)
        self.total_necesario = self.bytes_necesarios + self.margen
        self.accion = ACCION
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"No hay espacio suficiente en el disco de datos para {self.contexto}: "
            f"quedan {_mb(self.bytes_libres)} y hacen falta {_mb(self.total_necesario)} "
            f"(incluye un margen de seguridad de {_mb(self.margen)}). "
            f"{self.accion}"
        )


def _margen(bytes_necesarios: int) -> int:
    return int(bytes_necesarios * MARGEN_FRACCION) + MARGEN_BYTES


def _mb(bytes_: int) -> str:
    return f"{bytes_ / (1024 * 1024):.0f} MB"


def _ruta_para_medir(ruta: Path) -> Path:
    ruta = Path(ruta)
    if ruta.exists():
        return ruta
    padre = ruta.parent
    while not padre.exists() and padre != padre.parent:
        padre = padre.parent
    return padre


def comprobar_espacio(
    ruta: Path, necesario: int, contexto: str, *, libre: int | None = None
) -> None:
    """Comprueba que `ruta` tiene `necesario` + margen. `libre` es para tests."""
    if necesario < 0:
        raise ValueError("lo necesario no puede ser negativo")
    ruta = Path(ruta)
    if libre is None:
        libre = shutil.disk_usage(_ruta_para_medir(ruta)).free
    if libre < necesario + _margen(necesario):
        raise EspacioInsuficienteError(
            bytes_libres=libre,
            bytes_necesarios=necesario,
            contexto=contexto,
            ruta=ruta,
        )
