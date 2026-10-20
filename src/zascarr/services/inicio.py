"""
Inicio (V4): reúne el estado observado y se lo da a la función pura de primeros pasos.

Cada dato tiene UNA fuente y aquí se dice cuál (la regla de la ficha V4: sin contradicciones entre
pantallas):

- series / huecos / completitud → `services/resumen.py`
- archivos registrados y en qué punto está cada uno → `desglose_registrados` (UNA consulta: las
  partes suman el total por construcción; «por revisar» usa el filtro de la lista, como el menú)
- copias idénticas que el registro dejó fuera → último `ImportRun` con `details.kind == "adoption"`
- series seguidas → `WishlistService.count_active_series` (series DISTINTAS con algún deseo activo;
  el contador del menú sigue contando peticiones, que es lo que lista Deseados)
- adopción → `LibraryAdopter.estado` (marcador explícito de B11, no inferido de que haya filas)
- informe de duplicados → último `ImportRun` con `details.kind == "audit"`
- aviso legal → `services/legal.is_acknowledged`
- fuente de búsqueda → `orchestrator.hay_fuente_de_busqueda` (la misma definición que usa D9)

Solo lee.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, ImportRun
from zascarr.services.legal import is_acknowledged
from zascarr.services.library_adopter import LibraryAdopter
from zascarr.services.orchestrator import hay_fuente_de_busqueda
from zascarr.services.primeros_pasos import (
    EstadoInicio,
    InformeDisco,
    PrimerosPasos,
    calcular_primeros_pasos,
    hace_cuanto,
    informe_antiguo,
)
from zascarr.services.resumen import ResumenBiblioteca, resumen_biblioteca
from zascarr.services.review import ReviewService
from zascarr.services.wishlist import WishlistService


@dataclass(frozen=True)
class Desglose:
    """En qué punto está cada tebeo registrado (presente en el disco, como en `resumen.py`).

    Caso real (2026-10-20): el Inicio decía «encontramos 1542 · registrados 1325», el paso 1
    «Hecho» y el paso 2 «Revisa 1322», sin decir cómo encajaban. Aquí cada registrado cae en UNA
    parte y las partes suman `total`; lo que no está en el total (filas por revisar cuyo archivo ya
    no está donde se registró, que «Por revisar» sigue listando) va aparte, con nombre propio."""
    total: int = 0
    clasificados: int = 0           # con su número (issue_id)
    por_revisar_presentes: int = 0  # el filtro de «Por revisar», con el archivo en su sitio
    descartados: int = 0            # «ignorar» en Por revisar
    #: «Por revisar» los lista aunque el archivo ya no esté donde dice la BD (no son registrados)
    por_revisar_ausentes: int = 0

    @property
    def sin_numero(self) -> int:
        """Con serie sugerida pero sin número: lo que no es ninguna de las otras partes."""
        return self.total - self.clasificados - self.por_revisar_presentes - self.descartados

    @property
    def por_revisar(self) -> int:
        """Lo que cuentan el paso 2 y el menú: la lista entera de «Por revisar»."""
        return self.por_revisar_presentes + self.por_revisar_ausentes

    @property
    def partes(self) -> tuple[tuple[int, str, str | None], ...]:
        """(cuántos, texto, enlace) de cada parte no vacía, en orden de lectura."""
        partes = (
            (self.clasificados, "clasificado" if self.clasificados == 1 else "clasificados",
             "/ui/biblioteca"),
            (self.por_revisar_presentes, "por revisar", "/ui/pendientes"),
            (self.sin_numero, "con serie pero sin número", None),
            (self.descartados, "descartado" if self.descartados == 1 else "descartados", None),
        )
        return tuple(p for p in partes if p[0])


@dataclass(frozen=True)
class VistaInicio:
    resumen: ResumenBiblioteca
    pasos: PrimerosPasos
    informe: InformeDisco | None
    archivos_sin_clasificar: int
    registrados: Desglose = Desglose()
    #: copias idénticas que el último registro de la biblioteca no registró (0 sin registro)
    copias_descartadas: int = 0
    #: «hace 3 semanas»: cuánto hace que se miró el disco (None sin informe).
    informe_hace: str | None = None
    #: Si la mirada es vieja, el Inicio ofrece repetirla junto a la fecha.
    informe_antiguo: bool = False


async def ultimo_informe(db: AsyncSession) -> InformeDisco | None:
    """Solo las cifras del último informe de duplicados, sin cargar las listas del JSON."""
    fila = (await db.execute(
        select(
            ImportRun.started_at,
            ImportRun.files_scanned,
            ImportRun.details["files_hashed"].astext,
        )
        .where(ImportRun.details["kind"].astext == "audit")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).first()
    if fila is None:
        return None
    fecha, leidos, comparados = fila
    return InformeDisco(
        fecha=fecha,
        archivos_leidos=leidos or 0,
        archivos_comparados=int(comparados or 0),
    )


async def desglose_registrados(db: AsyncSession) -> Desglose:
    """Una sola consulta: si fueran varias, un ciclo del importador entre medias la descuadraría."""
    presente = File.is_missing.is_(False)
    pendiente = and_(*ReviewService._condiciones_pendientes())
    total, clasificados, pendientes, descartados, ausentes = (await db.execute(select(
        func.count().filter(presente),
        func.count().filter(presente, File.issue_id.is_not(None)),
        func.count().filter(presente, pendiente),
        func.count().filter(presente, File.issue_id.is_(None), File.review_dismissed.is_(True)),
        func.count().filter(File.is_missing.is_(True), pendiente),
    ).select_from(File))).one()
    return Desglose(total=total or 0, clasificados=clasificados or 0,
                    por_revisar_presentes=pendientes or 0, descartados=descartados or 0,
                    por_revisar_ausentes=ausentes or 0)


async def copias_descartadas(db: AsyncSession) -> int:
    """Repetidos (mismo contenido que un tebeo ya registrado) que el último registro dejó fuera."""
    fila = (await db.execute(
        select(ImportRun.duplicate_count)
        .where(ImportRun.details["kind"].astext == "adoption")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).first()
    return (fila[0] or 0) if fila else 0


async def cargar_inicio(db: AsyncSession) -> VistaInicio:
    resumen = await resumen_biblioteca(db)
    desglose = await desglose_registrados(db)
    # SERIES distintas, no peticiones: «Sigues N series» no puede contar tres peticiones de una.
    seguidas = await WishlistService(db).count_active_series()
    adopcion = await LibraryAdopter(db).estado()
    informe = await ultimo_informe(db)
    copias = await copias_descartadas(db)
    legal = await is_acknowledged(db)
    pasos = calcular_primeros_pasos(EstadoInicio(
        adopcion=adopcion,
        archivos_registrados=desglose.total,
        archivos_sin_clasificar=desglose.por_revisar,
        series_seguidas=seguidas,
        informe=informe,
        aviso_legal_aceptado=legal,
        hay_fuente_de_busqueda=hay_fuente_de_busqueda(get_settings()),
    ))
    ahora = datetime.now(UTC)
    return VistaInicio(resumen=resumen, pasos=pasos, informe=informe,
                       archivos_sin_clasificar=desglose.por_revisar,
                       registrados=desglose, copias_descartadas=copias,
                       informe_hace=hace_cuanto(informe.fecha, ahora) if informe else None,
                       informe_antiguo=bool(informe and informe_antiguo(informe.fecha, ahora)))
