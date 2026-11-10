#!/usr/bin/env python3
"""BL-ETQ2b (#573): relectura del ComicInfo de la biblioteca registrada (ETQ2).

Uso (dentro del contenedor; desde el host, `scripts/backfill-comicinfo.sh`):

    python - --dry-run     # informe, sin escribir (defecto)
    python - --aplicar     # aplica (idempotente)

- Solo lee `ComicInfo.xml` de los **CBZ (ZIP)** registrados con vínculo a serie. Los CBR no se
  leen (ETQ2 solo lee ComicInfo de ZIP) y se cuentan aparte en el informe.
- **Nunca** escribe en los ficheros y no mueve, renombra ni borra nada.
- Toma el **mismo cerrojo de ciclo** que el importador y el rescan (`CLAVE_CERROJO_CICLO`): si hay
  una pasada en marcha no espera; avisa y sale sin tocar la base.
- La aplicación reutiliza `services/etiquetas_comicinfo.aplicar_comicinfo`: sin pisar `manual`,
  sin resucitar `oculta=true`, géneros solo si la serie no tenía, idempotente.
"""
from __future__ import annotations

import contextlib
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zascarr.core.comicinfo_write import MAX_COMICINFO_BYTES
from zascarr.core.importer_triage import parse_comic_info
from zascarr.database import async_session_factory
from zascarr.models import File, FileFormat, Issue
from zascarr.services.comprobacion_disco import CLAVE_CERROJO_CICLO
from zascarr.services.etiquetas_comicinfo import aplicar_comicinfo

COMICINFO = "comicinfo.xml"
#: Se confirma cada lote para no dejar una transacción abierta durante todo el pase.
LOTE_COMMIT = 50
#: Cuántos ejemplos de error se guardan para el informe (sin rutas completas).
MAX_EJEMPLOS = 5


@dataclass
class Informe:
    """Lo que ha visto (y, si `aplicar`, hecho) el pase."""

    aplicar: bool = False
    cerrojo: bool = False
    mirados: int = 0
    con_comicinfo: int = 0
    con_tags: int = 0
    con_genero: int = 0
    sin_comicinfo: int = 0
    xml_roto: int = 0
    no_zip: int = 0
    ilegible: int = 0
    grande: int = 0
    faltan: int = 0
    cbr_registrados: int = 0
    series_con_datos: int = 0
    etiquetas_vistas: int = 0
    generos_vistos: int = 0
    etiquetas_aplicadas: int = 0
    generos_aplicados: int = 0
    series_tocadas: int = 0
    avisos: int = 0
    ejemplos_error: list[str] = field(default_factory=list)
    avisos_texto: list[str] = field(default_factory=list)


def _comicinfo_de(ruta: Path) -> tuple[bytes | None, str]:
    """`ComicInfo.xml` del CBZ, o (None, causa). Solo lectura y con el tope de ETQ2."""
    try:
        with zipfile.ZipFile(ruta) as z:
            for nombre in z.namelist():
                if nombre.lower() == COMICINFO:
                    if z.getinfo(nombre).file_size > MAX_COMICINFO_BYTES:
                        return None, "grande"
                    return z.read(nombre), "ok"
            return None, "sin_comicinfo"
    except zipfile.BadZipFile:
        return None, "no_zip"
    except (OSError, RuntimeError):
        return None, "ilegible"


@asynccontextmanager
async def _cerrojo_de_ciclo(fabrica: async_sessionmaker) -> AsyncIterator[bool]:
    """Mismo cerrojo de sesión que el ciclo del importador y el rescan (`comprobacion_disco`).

    `try` sin espera: si otra pasada lo tiene, se avisa y no se toca nada. Con dobles de prueba
    sin bind no hay cerrojo real y se comporta como libre.
    """
    async with fabrica() as sesion:
        enlace = getattr(sesion, "bind", None)
        if enlace is None:
            yield True
            return
        conexion = await enlace.connect()
        obtenido = False
        try:
            obtenido = bool((await conexion.execute(
                text("SELECT pg_try_advisory_lock(:c, :o)"),
                {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]},
            )).scalar())
            yield obtenido
        finally:
            try:
                if obtenido:
                    await conexion.execute(
                        text("SELECT pg_advisory_unlock(:c, :o)"),
                        {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]},
                    )
                await conexion.close()
            except Exception:  # noqa: BLE001 — una conexión rota no vuelve al pool con el lock
                with contextlib.suppress(Exception):
                    await conexion.invalidate()


async def _filas_con_serie(db: AsyncSession) -> list[tuple[str, UUID]]:
    """(ruta, series_id) de los CBZ registrados, presentes y con issue→serie."""
    return [
        (ruta, series_id)
        for ruta, series_id in (await db.execute(
            select(File.file_path, Issue.series_id)
            .join(Issue, Issue.id == File.issue_id)
            .where(File.file_format == FileFormat.CBZ,
                   File.is_missing.is_(False),
                   Issue.series_id.is_not(None))
            .order_by(File.file_path)
        )).all()
    ]


def _contar_para(informe: Informe, sitio: str, aviso: str) -> None:
    setattr(informe, sitio, getattr(informe, sitio) + 1)
    if aviso and len(informe.ejemplos_error) < MAX_EJEMPLOS:
        informe.ejemplos_error.append(aviso)


async def _aplicar_fila(db: AsyncSession, informe: Informe, series_id: UUID,
                        tags: list[str], generos: list[str], tocadas: set[UUID]) -> None:
    res = await aplicar_comicinfo(db, series_id, tags=tags, genres=generos)
    informe.etiquetas_aplicadas += res.etiquetas
    informe.generos_aplicados += res.generos
    informe.avisos += len(res.avisos)
    if res.avisos and len(informe.avisos_texto) < MAX_EJEMPLOS:
        informe.avisos_texto.extend(res.avisos)
    if res.etiquetas or res.generos:
        tocadas.add(series_id)


async def ejecutar(*, aplicar: bool, fabrica: async_sessionmaker | None = None,
                   limite: int | None = None) -> Informe:
    """Recorre la biblioteca registrada. Con `aplicar=False` (dry-run) no escribe nada."""
    fabrica = fabrica or async_session_factory
    informe = Informe(aplicar=aplicar)
    async with _cerrojo_de_ciclo(fabrica) as libre:
        informe.cerrojo = libre
        if not libre:
            return informe
        async with fabrica() as db:
            informe.cbr_registrados = int((await db.execute(
                select(func.count()).select_from(File)
                .where(File.file_format == FileFormat.CBR)
            )).scalar() or 0)
            filas = await _filas_con_serie(db)
            if limite is not None:
                filas = filas[:limite]
            series: set[UUID] = set()
            tocadas: set[UUID] = set()
            pendientes = 0
            for ruta, series_id in filas:
                informe.mirados += 1
                fichero = Path(ruta)
                if not fichero.exists():
                    _contar_para(informe, "faltan", f"{fichero.name}: no está en disco")
                    continue
                datos, causa = _comicinfo_de(fichero)
                if causa == "sin_comicinfo":
                    _contar_para(informe, "sin_comicinfo", "")
                    continue
                if causa != "ok":
                    campo = {"grande": "grande", "no_zip": "no_zip",
                             "ilegible": "ilegible"}.get(causa, "ilegible")
                    _contar_para(informe, campo, f"{fichero.name}: {causa}")
                    continue
                try:
                    info = parse_comic_info(datos)
                except ElementTree.ParseError:
                    _contar_para(informe, "xml_roto", f"{fichero.name}: XML roto")
                    continue
                informe.con_comicinfo += 1
                if info.tags:
                    informe.con_tags += 1
                    informe.etiquetas_vistas += len(info.tags)
                    series.add(series_id)
                if info.genres:
                    informe.con_genero += 1
                    informe.generos_vistos += len(info.genres)
                    series.add(series_id)
                if aplicar and (info.tags or info.genres):
                    await _aplicar_fila(db, informe, series_id, info.tags, info.genres, tocadas)
                    pendientes += 1
                    if pendientes % LOTE_COMMIT == 0:
                        await db.commit()
            if aplicar:
                await db.commit()
            informe.series_con_datos = len(series)
            informe.series_tocadas = len(tocadas)
    return informe


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def imprimir(informe: Informe) -> None:
    modo = "APLICAR" if informe.aplicar else "DRY-RUN (no se ha escrito nada)"
    print("=== Relectura de ComicInfo de la biblioteca registrada (BL-ETQ2b) ===")
    print(f"Modo: {modo}")
    if not informe.cerrojo:
        print("Cerrojo de ciclo: OCUPADO — hay un importador o un rescan en marcha;"
              " no se ha tocado nada.")
        return
    print("Cerrojo de ciclo: libre")
    print(f"CBZ registrados con serie: {informe.mirados}")
    print(f"  con ComicInfo: {informe.con_comicinfo}"
          f" · con <Tags>: {informe.con_tags} · con <Genre>: {informe.con_genero}")
    print(f"  sin ComicInfo: {informe.sin_comicinfo} · XML roto: {informe.xml_roto}"
          f" · no es ZIP: {informe.no_zip} · ilegible: {informe.ilegible}"
          f" · ComicInfo > 1 MiB: {informe.grande} · fichero ausente: {informe.faltan}")
    print(f"Series distintas con datos: {informe.series_con_datos}"
          f" · etiquetas encontradas: {informe.etiquetas_vistas}"
          f" · géneros encontrados: {informe.generos_vistos}")
    print(f"CBR registrados (no se leen: ETQ2 solo lee ZIP): {informe.cbr_registrados}")
    if informe.ejemplos_error:
        print(f"Ejemplos de error: {', '.join(informe.ejemplos_error)}")
    if informe.aplicar:
        print("Aplicado: "
              f"{_plural(informe.etiquetas_aplicadas, 'etiqueta', 'etiquetas')} y "
              f"{_plural(informe.generos_aplicados, 'género', 'géneros')} en "
              f"{_plural(informe.series_tocadas, 'serie', 'series')} · avisos: {informe.avisos}")
        if informe.avisos_texto:
            print(f"Avisos: {', '.join(informe.avisos_texto)}")
    else:
        print("No se ha escrito nada. Repite con --aplicar para aplicar los cambios.")


