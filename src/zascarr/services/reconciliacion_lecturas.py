"""Reconciliación de guías de lectura con la biblioteca, sobre `story_arcs` (SCR3 entrega 2).

Decisión del PO (2026-11-13): **sin entidad nueva ni migración**. Se reutiliza lo que ya
existe de BL-C4:

- un `StoryArc` por guía, con `metadata_ = {"origen": <sitio>, "url": <guía>}`;
- un `StoryArcIssue` por número local reconciliado, con `reading_order` 1..N en el orden
  declarado por la guía.

Reglas:
- **Solo lectura de la biblioteca** (`Series`, `Issue`): no se crean series ni números, no se
  toca `files`, wishlist ni el disco. Las únicas escrituras son el arco y sus enlaces.
- **Idempotente**: re-ejecutar la misma guía actualiza el orden, añade los enlaces nuevos y
  quita los que ya no declara; nunca duplica. Se busca el arco por título (patrón de
  `enricher._upsert_arc`).
- Match conservador: título normalizado exacto (`Series.title_norm`), desempate por `volumen`
  y por `anio_volumen` (±1). **Nunca** se usa `anio_numero` para desempatar series. Si sigue
  siendo ambiguo, el ítem se descarta con contador y log (no se inventa).
- Un `tpb`/`volume` no es una grapa: no produce enlace (`no_aplica`); no cuenta como falta.
- Los ítems sin serie o sin número local se omiten con contador y log estructurado
  (`lecturas.item_descartado`, sin prosa ni URL); nunca lanzan al orquestador.
- No se persiste prosa: el arco solo guarda título de la guía, enlace y referencias.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Issue, Series, StoryArc, StoryArcIssue
from zascarr.services.reading_order_resolver import (
    MAX_TITULO_SERIE,
    ReadingOrderItem,
    clave_de_serie,
    expandir_rango,
    parsear_referencia,
)
from zascarr.services.reading_orders import ExtractorGuias, GuiaLeida

logger = structlog.get_logger()

#: Orígenes de guía que esta reconciliación reconoce en `StoryArc.metadata_["origen"]`.
ORIGENES_DE_GUIA = frozenset({"reading_orders", "continuity_guide"})
#: Tope de enlaces por guía (una guía real ronda 100; evita un arco con miles de filas).
MAX_ENLACES = 1_000
#: Tope de guías/arcos que se aceptan de una sola lectura (defensa en profundidad).
MAX_ENTRADAS = 5_000
#: Tolerancia de año para desempatar series (spec §4: ±1; el año del número no se usa).
TOLERANCIA_ANIO = 1

TipoMotivo = str


@dataclass(frozen=True, slots=True)
class ResultadoReconciliacion:
    """Informe en memoria de una reconciliación. No se persiste."""

    titulo: str
    origen: str
    url: str
    creado: bool
    enlazados: int
    omitidos: int
    motivos: tuple[tuple[str, int], ...] = ()


def titulo_de_guia(guia: GuiaLeida) -> str:
    """Título del arco: el de la página o, si falta, el slug de la URL (nunca prosa)."""
    titulo = " ".join((guia.titulo or "").split())
    if titulo:
        return titulo[:MAX_TITULO_SERIE]
    try:
        ruta = urlsplit(guia.url).path.rstrip("/")
    except ValueError:
        ruta = ""
    slug = ruta.rsplit("/", 1)[-1]
    legible = " ".join(slug.replace("-", " ").replace("_", " ").split())
    return (legible or "Guía de lectura")[:MAX_TITULO_SERIE]


def _elegir_serie(candidatas: list[Series], item: ReadingOrderItem) -> Series | None:
    """Desempata por volumen y año del volumen (±1); ambiguo ⇒ None (nunca adivinar)."""
    if not candidatas:
        return None
    if item.volumen is not None:
        por_volumen = [serie for serie in candidatas if serie.volume == item.volumen]
        if por_volumen:
            candidatas = por_volumen
    if item.anio_volumen is not None:
        por_anio = [
            serie for serie in candidatas
            if serie.start_year is not None
            and abs(int(serie.start_year) - item.anio_volumen) <= TOLERANCIA_ANIO
        ]
        if por_anio:
            candidatas = por_anio
    return candidatas[0] if len(candidatas) == 1 else None


def _numeros(item: ReadingOrderItem) -> list[str] | None:
    """Números locales que declara el ítem; `None` si no aplica (tpb/volume) o no tiene."""
    if item.tipo in ("tpb", "volume") or item.numero_inicio is None:
        return None
    if item.numero_fin is None or item.numero_fin == item.numero_inicio:
        return [item.numero_inicio]
    expandidos = expandir_rango(item)
    if expandidos is not None:
        return expandidos
    # Rango no entero (p. ej. 1A-2A): se comparan los literales de los extremos.
    return [item.numero_inicio, item.numero_fin]


async def _buscar_serie(db: AsyncSession,
                        item: ReadingOrderItem) -> tuple[Series | None, str]:
    """(serie, motivo si no hay match único): `serie_no_encontrada` o `ambiguo`."""
    candidatas = list((await db.execute(
        select(Series).where(Series.title_norm == clave_de_serie(item))
    )).scalars().all())
    if not candidatas:
        return None, "serie_no_encontrada"
    serie = _elegir_serie(candidatas, item)
    return (serie, "") if serie is not None else (None, "ambiguo")


async def _buscar_issue(db: AsyncSession, serie: Series, numero: str) -> Issue | None:
    return (await db.execute(
        select(Issue).where(Issue.series_id == serie.id, Issue.issue_number == numero)
    )).scalars().first()


async def _upsert_arco(db: AsyncSession, titulo: str,
                       guia: GuiaLeida) -> tuple[StoryArc, bool]:
    """Arco de la guía (lo crea si no existe). Clave: título, como `_upsert_arc` del enricher."""
    metadata = {"origen": guia.sitio, "url": guia.url}
    fila = (await db.execute(
        select(StoryArc).where(StoryArc.title == titulo)
    )).scalars().first()
    if fila is None:
        fila = StoryArc(id=uuid4(), title=titulo, metadata_=metadata)
        db.add(fila)
        return fila, True
    fila.metadata_ = {**(fila.metadata_ or {}), **metadata}
    return fila, False


async def reconciliar_guia(db: AsyncSession,
                           guia: GuiaLeida) -> ResultadoReconciliacion:
    """Cruza una guía leída con la biblioteca y deja el arco y su orden actualizados.

    Orden de consultas (determinista para los dobles de prueba): (1) `StoryArc` por título;
    (2) por entrada, `Series` por `title_norm`; (3) por número, `Issue` de esa serie;
    (4) enlaces actuales de `StoryArcIssue`. No hace `commit` (lo decide el llamador).
    """
    titulo = titulo_de_guia(guia)
    motivo: Counter[str] = Counter()
    arco, creado = await _upsert_arco(db, titulo, guia)

    # (2)-(3) Reconciliar cada entrada, en orden DOM, con enlaces 1..N.
    enlazados: list[tuple[Issue, int]] = []
    omitidos = max(0, len(guia.entradas) - MAX_ENTRADAS)
    if omitidos:
        motivo["tope"] += omitidos
    for entrada in guia.entradas[:MAX_ENTRADAS]:
        item = parsear_referencia(entrada.referencia)
        if item is None:
            omitidos += 1
            motivo["sin_referencia"] += 1
            logger.info("lecturas.item_descartado", sitio=guia.sitio,
                        orden=entrada.orden, motivo="sin_referencia")
            continue
        numeros = _numeros(item)
        if numeros is None:
            omitidos += 1
            motivo["no_aplica"] += 1
            logger.info("lecturas.item_descartado", sitio=guia.sitio,
                        orden=entrada.orden, motivo="no_aplica")
            continue
        serie, motivo_serie = await _buscar_serie(db, item)
        if serie is None:
            omitidos += 1
            motivo[motivo_serie] += 1
            logger.info("lecturas.item_descartado", sitio=guia.sitio,
                        orden=entrada.orden, motivo=motivo_serie)
            continue
        encontrados = 0
        for numero in numeros:
            if len(enlazados) >= MAX_ENLACES:
                motivo["tope"] += 1
                break
            issue = await _buscar_issue(db, serie, numero)
            if issue is None:
                continue
            enlazados.append((issue, entrada.orden))
            encontrados += 1
        if encontrados == 0:
            omitidos += 1
            motivo["numero_no_encontrado"] += 1
            logger.info("lecturas.item_descartado", sitio=guia.sitio,
                        orden=entrada.orden, motivo="numero_no_encontrado")

    # (4) Enlaces actuales: actualizar orden, añadir nuevos y quitar los que ya no constan.
    existentes = {
        enlace.issue_id: enlace
        for enlace in (await db.execute(
            select(StoryArcIssue).where(StoryArcIssue.story_arc_id == arco.id)
        )).scalars().all()
    }
    nuevos: set[str] = set()
    posicion = 0
    for issue, _entrada_orden in enlazados:
        if issue.id in nuevos:
            continue                       # la guía repite el número: un solo enlace
        posicion += 1
        nuevos.add(issue.id)
        enlace = existentes.get(issue.id)
        if enlace is not None:
            if enlace.reading_order != posicion:
                enlace.reading_order = posicion
            continue
        db.add(StoryArcIssue(story_arc_id=arco.id, issue_id=issue.id,
                             reading_order=posicion))
    if nuevos:
        # Solo se retiran enlaces si la nueva lectura enlazó algo: una guía que hoy no casa
        # con la biblioteca no debe vaciar un arco que ya existía (se reintenta más adelante).
        for issue_id, enlace in existentes.items():
            if issue_id not in nuevos:
                await db.delete(enlace)
    await db.flush()

    resultado = ResultadoReconciliacion(
        titulo=titulo, origen=guia.sitio, url=guia.url, creado=creado,
        enlazados=len(nuevos), omitidos=omitidos,
        motivos=tuple(sorted(motivo.items())),
    )
    logger.info("lecturas.guia_reconciliada", sitio=guia.sitio, creado=creado,
                enlazados=resultado.enlazados, omitidos=resultado.omitidos)
    return resultado


async def leer_y_reconciliar(db: AsyncSession, extractor: ExtractorGuias,
                             url: str) -> ResultadoReconciliacion | None:
    """Lee una guía con el extractor y la reconcilia; `None` si la lectura no dio entradas."""
    guia = await extractor.leer_guia(url)
    if guia is None:
        return None
    return await reconciliar_guia(db, guia)


__all__ = [
    "MAX_ENLACES",
    "MAX_ENTRADAS",
    "ORIGENES_DE_GUIA",
    "ResultadoReconciliacion",
    "leer_y_reconciliar",
    "reconciliar_guia",
    "titulo_de_guia",
]
