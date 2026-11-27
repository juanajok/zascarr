"""BL-VINC1: vínculos dudosos. Esqueleto para las pruebas en rojo; la regla llega en el commit siguiente."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ficha:
    id: str
    titulo: str
    inicio: int | None = None
    volumen: int | None = None
    numeros: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Archivo:
    id: str
    ruta: str
    serie_id: str
    issue_id: str
    numero: str
    orden: float | None = None
    origen: str | None = None
    p_serie: str | None = None
    p_numero: str | None = None
    p_volumen: int | None = None
    p_anual: bool = False
    elegida: str | None = None
    candidatas: tuple[str, ...] = ()
    clave: str = ""


@dataclass
class Motivo:
    senal: str
    texto: str


@dataclass
class Marcado:
    archivo_id: str
    issue_id: str
    nombre: str
    numero: str
    orden: float | None
    motivos: list[Motivo]
    serie_mezcla: bool = False


@dataclass
class Lote:
    carpeta: str
    serie_id: str
    serie_titulo: str
    archivos: list[Marcado]
    destino_id: str | None = None
    destino_titulo: str | None = None
    destino_sin_numeros: bool = False


@dataclass
class EvidenciaMezcla:
    archivo_id: str
    issue_id: str
    nombre: str
    numero: str
    volumen: int
    carpeta: str


@dataclass
class SerieMezclada:
    serie_id: str
    titulo: str
    archivos: list[EvidenciaMezcla] = field(default_factory=list)


@dataclass
class Informe:
    lotes: list[Lote]
    series_mezcladas: list[SerieMezclada]
    revisados: int = 0


def evaluar(archivos: list[Archivo], fichas: dict[str, Ficha]) -> Informe:
    raise NotImplementedError


async def buscar(db) -> Informe:
    raise NotImplementedError


async def ejecutar(fabrica) -> None:
    raise NotImplementedError


async def informe_vigente(db):
    raise NotImplementedError


async def _ejecutar_en_tarea(fabrica) -> None:
    raise NotImplementedError


def reiniciar_para_pruebas() -> None:
    return None
