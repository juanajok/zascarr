# ruff: noqa: E501
"""BL-DUP3 (#266): resolver una carpeta repetida o contenida en otra.

Solo lee para comparar. El apartado de los archivos comunes idénticos usa
la cuarentena, el comprobante y el deshacer de BL-DUP1. La carpeta que
queda vacía se puede apartar como carpeta, sin borrarla.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.importer_triage import sha256_streaming
from zascarr.models import (
    ApartadoEstado,
    ApartadoGrupo,
    ApartadoGrupoEstado,
    ApartadoOperacion,
)
from zascarr.services.apartado_duplicados import (
    ApartadoDuplicadosService,
    GrupoRechazado,
    VistaApartado,
    _fsync_dir,
)

MODO_CARPETA = "carpeta"


@dataclass(frozen=True)
class ArchivoPar:
    nombre: str
    ruta_a: str
    ruta_b: str
    tamano: int
    sha_a: str
    sha_b: str
    identico: bool


@dataclass(frozen=True)
class DetalleCarpetas:
    ruta_a: str
    ruta_b: str
    comunes_identicos: tuple[ArchivoPar, ...]
    comunes_distintos: tuple[ArchivoPar, ...]
    solo_en_a: tuple[str, ...]
    solo_en_b: tuple[str, ...]
    quedara_vacia: bool = False
    a_quedara_vacia: bool = False


@dataclass(frozen=True)
class EntradaCarpeta:
    nombre: str
    ruta_keep: str
    ruta_apartar: str
    bytes: int
    token: str
    keep_index: int
    grupo_json: str


@dataclass(frozen=True)
class VistaCarpetas:
    detalle: DetalleCarpetas
    entradas: tuple[EntradaCarpeta, ...]
    archivos: int
    bytes: int
    quedara_vacia: bool
    carpeta_a_apartar: str | None


def _carpeta(library: Path, ruta: str) -> tuple[Path, str]:
    p = Path(ruta)
    if not p.is_absolute():
        p = library / p
    if p.is_symlink():
        raise GrupoRechazado("no_regular", "La carpeta es un enlace simbólico.")
    try:
        p = p.resolve(strict=False)
        root = library.resolve()
    except OSError as exc:
        raise GrupoRechazado("ruta_invalida", "La ruta no es válida.") from exc
    if root != p and root not in p.parents:
        raise GrupoRechazado("fuera_biblioteca", "La carpeta no está dentro de la biblioteca.")
    if ".zascarr" in p.parts:
        raise GrupoRechazado("zascarr", "La cuarentena no se toca.")
    if not p.is_dir():
        raise GrupoRechazado("no_existe", "La carpeta ya no está.")
    return p, p.relative_to(root).as_posix()


def _analizar(ruta_a: str, ruta_b: str, library: Path) -> DetalleCarpetas:
    a, rel_a = _carpeta(library, ruta_a)
    b, rel_b = _carpeta(library, ruta_b)
    if a == b:
        raise GrupoRechazado("misma_carpeta", "Son la misma carpeta.")
    archivos_a = {p.name: p for p in a.iterdir() if p.is_file() and not p.is_symlink()}
    archivos_b = {p.name: p for p in b.iterdir() if p.is_file() and not p.is_symlink()}
    comunes = sorted(set(archivos_a) & set(archivos_b))
    identicos: list[ArchivoPar] = []
    distintos: list[ArchivoPar] = []
    for nombre in comunes:
        pa, pb = archivos_a[nombre], archivos_b[nombre]
        sha_a = sha256_streaming(pa)
        sha_b = sha256_streaming(pb)
        par = ArchivoPar(nombre, str(pa), str(pb), pa.stat().st_size,
                         sha_a, sha_b, sha_a == sha_b and pa.stat().st_size == pb.stat().st_size)
        (identicos if par.identico else distintos).append(par)
    solo_a = tuple(sorted(set(archivos_a) - set(comunes)))
    solo_b = tuple(sorted(set(archivos_b) - set(comunes)))
    # La carpeta quedará vacía solo si todo lo que tiene se puede apartar:
    # no hay subcarpetas, ni archivos solo en ella, ni comunes distintos.
    a_vacia = not any(p.is_dir() for p in a.iterdir()) and not solo_a and not distintos
    b_vacia = not any(p.is_dir() for p in b.iterdir()) and not solo_b and not distintos
    return DetalleCarpetas(rel_a, rel_b, tuple(identicos), tuple(distintos),
                           solo_a, solo_b, b_vacia, a_vacia)


async def analizar_par(ruta_a: str, ruta_b: str, library: Path) -> DetalleCarpetas:
    return await asyncio.to_thread(_analizar, ruta_a, ruta_b, library)


async def previsualizar_carpetas(
    db: AsyncSession, ruta_a: str, ruta_b: str, keep: str, *,
    library: Path, secret: str,
) -> VistaCarpetas:
    """Elige la carpeta que se queda y firma un grupo DUP1 por común idéntico."""
    if keep not in ("a", "b"):
        raise GrupoRechazado("keep_invalido", "Elige qué carpeta se queda.")
    detalle = await analizar_par(ruta_a, ruta_b, library)
    if keep == "a":
        ruta_apartar = detalle.ruta_b
        quedara_vacia = detalle.quedara_vacia
    else:
        ruta_apartar = detalle.ruta_a
        quedara_vacia = detalle.a_quedara_vacia
    servicio = ApartadoDuplicadosService(
        db, settings=type("_S", (), {"library_path": library, "secret_key": secret})(),
        secret=secret)
    entradas: list[EntradaCarpeta] = []
    for par in detalle.comunes_identicos:
        if keep == "a":
            pa, pb = par.ruta_a, par.ruta_b
        else:
            pa, pb = par.ruta_b, par.ruta_a
        vista: VistaApartado = await servicio.previsualizar(
            par.sha_a, [pa, pb], 0)
        rels = [Path(p).relative_to(library).as_posix() for p in vista.rutas]
        entradas.append(EntradaCarpeta(
            par.nombre, rels[0] if vista.keep_index == 0 else rels[1],
            rels[1] if vista.keep_index == 0 else rels[0], par.tamano,
            vista.token, vista.keep_index,
            __import__("json").dumps(
                {"sha256": par.sha_a, "rutas": rels, "keep_index": vista.keep_index},
                ensure_ascii=False)))
    return VistaCarpetas(detalle, tuple(entradas),
                         sum(1 for _ in detalle.comunes_identicos),
                         sum(e.bytes for e in entradas), quedara_vacia,
                         ruta_apartar if quedara_vacia else None)


def _validar_carpeta_vacia(library: Path, ruta: str) -> tuple[Path, str]:
    p, rel = _carpeta(library, ruta)
    if any(p.iterdir()):
        raise GrupoRechazado("carpeta_no_vacia", "La carpeta todavía tiene contenido.")
    return p, rel


async def apartar_carpeta_vacia(db: AsyncSession, ruta: str, *, library: Path, secret: str) -> str:
    """Mueve una carpeta vacía a la cuarentena; nunca la borra."""
    p, rel = await asyncio.to_thread(_validar_carpeta_vacia, library, ruta)
    operacion = uuid4()
    base = library / ".zascarr" / "apartados" / str(operacion) / rel
    if p.stat().st_dev != (base.parent if base.parent.exists() else library).stat().st_dev:
        raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
    base.parent.mkdir(parents=True, exist_ok=True)
    op = ApartadoOperacion(
        id=operacion, modo=MODO_CARPETA, estado=ApartadoEstado.CONFIRMADA,
        token_hasta=datetime.now(UTC), total_grupos=1, total_archivos=0, total_bytes=0,
        resultado={"estado": "confirmada", "carpeta": rel})
    db.add(op)
    db.add(ApartadoGrupo(
        operacion_id=operacion, grupo_clave="carpeta", sha256="0" * 64, size_bytes=0,
        estado=ApartadoGrupoEstado.MOVIDO,
        detalle={"modo": MODO_CARPETA, "ruta": rel, "destino": str(base)}))
    await db.commit()
    try:
        os.replace(p, base)
        _fsync_dir(base.parent)
        _fsync_dir(p.parent)
    except OSError as exc:
        op.estado = ApartadoEstado.EN_CURSO
        op.resultado = {"estado": "en_curso", "motivo": "rename_fallido"}
        await db.commit()
        raise GrupoRechazado("rename_fallido", "No se pudo apartar la carpeta.") from exc
    return str(operacion)


async def deshacer_carpeta(db: AsyncSession, operacion: str | UUID, *, library: Path) -> str:
    op_id = UUID(str(operacion))
    op = (await db.execute(
        select(ApartadoOperacion).options(selectinload(ApartadoOperacion.grupos))
        .where(ApartadoOperacion.id == op_id))).scalar_one_or_none()
    if op is None or op.modo != MODO_CARPETA:
        raise GrupoRechazado("operacion_invalida", "No existe esa operación de carpeta.")
    if op.estado == ApartadoEstado.DESHECHA:
        return "deshecha"
    if op.estado != ApartadoEstado.CONFIRMADA:
        raise GrupoRechazado("no_confirmada", "La operación no está confirmada.")
    grupo = op.grupos[0]
    detalle = grupo.detalle or {}
    origen = library / detalle["ruta"]
    destino = Path(detalle["destino"])
    if origen.exists():
        raise GrupoRechazado("sitio_ocupado", "El sitio original está ocupado.")
    if not destino.is_dir():
        raise GrupoRechazado("cuarentena_ausente", "La carpeta apartada ya no está.")
    if destino.stat().st_dev != origen.parent.stat().st_dev:
        raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
    os.replace(destino, origen)
    _fsync_dir(origen.parent)
    op.estado = ApartadoEstado.DESHECHA
    grupo.estado = ApartadoGrupoEstado.DESHECHO
    await db.commit()
    return "deshecha"
