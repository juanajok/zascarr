# ruff: noqa: E501
"""
SeriesService — listado/filtrado de series (C1).

Fuente única de verdad para la rejilla de biblioteca (`web/library.py`)
y la API JSON (`api/series.py`) — mismo motivo que `WishlistService`:
una sola query, no una copia en cada router. Los filtros por personaje y
saga usan JOIN explícito, no `.any()` anidado: `Issue` no tiene una
relationship inversa a `StoryArcIssue` (solo `StoryArc.arc_issues`), así
que el join hace falta de todos modos ahí, y se usa el mismo estilo
también para personaje por consistencia y para evitar dos EXISTS
correlacionados anidados.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Integer, and_, case, cast, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.matcher import normalize_title
from zascarr.models import (
    Character,
    File,
    Issue,
    IssueFormat,
    MetadataSource,
    Publisher,
    ReadingProgress,
    ReadingStatus,
    Series,
    StoryArc,
    StoryArcIssue,
    Tag,
    issue_characters,
    series_tags,
)


def pagina_efectiva(page: int, total: int, page_size: int) -> int:
    """Página que de verdad se sirve: 1..última, o 1 si no hay resultados.

    Función pura para que la URL, la plantilla y el servicio usen el mismo
    cálculo. Permite corregir `page>pages` ANTES del `offset` (sin un segundo
    SELECT), que es el requisito de rendimiento de BL-IT01 (#283, AC-08).
    """
    if total <= 0:
        return 1
    paginas = (total + page_size - 1) // page_size
    return min(max(page, 1), paginas)


class SeriesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _list_series(
        self,
        page: int = 1,
        page_size: int = 20,
        tradition: str | None = None,
        status: str | None = None,
        search: str | None = None,
        publisher_id: UUID | None = None,
        character_id: UUID | None = None,
        story_arc_id: UUID | None = None,
        etiquetas_positivas: tuple[str, ...] = (),
        etiquetas_negativas: tuple[str, ...] = (),
        leido: str | None = None,
        con_issues: bool = False,
        orden: str = "titulo",
        coleccion: str | None = None,
        coleccion_ids: set[UUID] | None = None,
        *,
        corregir_pagina: bool = True,
    ) -> tuple[list[Series], int, int]:
        """Consulta común: `(items, total, página_efectiva)`.

        `corregir_pagina=False` conserva el contrato histórico de la API
        (`page` fuera de rango devuelve items vacíos y el llamador sigue
        informando la página pedida); la biblioteca usa True para no gastar
        un segundo SELECT.
        """
        query = select(Series)
        needs_distinct = False

        if tradition:
            query = query.where(Series.tradition == tradition)
        if status:
            query = query.where(Series.status == status)
        if coleccion:
            condicion = condicion_estado_coleccion(coleccion)
            if condicion is not None:
                query = query.where(condicion)
        if coleccion_ids is not None:
            # Compatibilidad con llamadores antiguos que ya resolvieron los IDs.
            query = query.where(Series.id.in_(coleccion_ids))
        if search:
            # #664: el full-text generaba `plainto_tsquery` con config english
            # (aunque el vector fuera spanish), así que «lobo»/«criminal» no
            # encontraban sus raíces. La búsqueda principal es subcadena sobre
            # la columna normalizada (`f_title_norm`, mismo criterio que
            # `normalize_title`), insensible a tildes/mayúsculas y con parciales.
            normalizado = normalize_title(search)
            if normalizado:
                query = query.where(Series.title_norm.like(f"%{normalizado}%"))
        if publisher_id:
            query = query.where(Series.publisher_id == publisher_id)
        if character_id:
            query = (
                query.join(Issue, Issue.series_id == Series.id)
                .join(issue_characters, issue_characters.c.issue_id == Issue.id)
                .where(issue_characters.c.character_id == character_id)
            )
            needs_distinct = True
        if story_arc_id:
            query = (
                query.join(Issue, Issue.series_id == Series.id)
                .join(StoryArcIssue, StoryArcIssue.issue_id == Issue.id)
                .where(StoryArcIssue.story_arc_id == story_arc_id)
            )
            needs_distinct = True

        # BL-ETQ1b: EXISTS/NOT EXISTS por token; nunca JOIN+DISTINCT.
        for normalizado in etiquetas_positivas:
            query = query.where(Series.id.in_(
                select(series_tags.c.series_id).join(Tag, Tag.id == series_tags.c.tag_id)
                .where(Tag.name_norm == normalizado, series_tags.c.oculta.is_(False))
            ))
        for normalizado in etiquetas_negativas:
            query = query.where(Series.id.not_in(
                select(series_tags.c.series_id).join(Tag, Tag.id == series_tags.c.tag_id)
                .where(Tag.name_norm == normalizado, series_tags.c.oculta.is_(False))
            ))

        if leido in ("si", "leyendo", "no"):
            leidos = select(Issue.series_id).join(ReadingProgress, ReadingProgress.issue_id == Issue.id).where(
                ReadingProgress.status == ReadingStatus.COMPLETED)
            if leido == "si":
                query = query.where(Series.id.in_(leidos))
            elif leido == "leyendo":
                query = query.where(Series.id.in_(select(Issue.series_id).join(
                    ReadingProgress, ReadingProgress.issue_id == Issue.id).where(
                    ReadingProgress.status == ReadingStatus.READING)))
            else:
                query = query.where(Series.id.in_(select(Issue.series_id)))
                query = query.where(Series.id.not_in(leidos))
        if con_issues:
            query = query.where(Series.id.in_(select(Issue.series_id)))
        if needs_distinct:
            query = query.distinct()

        total = (await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )).scalar() or 0

        pagina = pagina_efectiva(page, total, page_size) if corregir_pagina else page
        # BL-INF10: progreso de lectura sin una consulta por tarjeta. Dos subconsultas correladas
        # en la misma SELECT de la página; se guardan como atributos transitorios de la serie.
        leidos_lectura = (
            select(func.count(ReadingProgress.id))
            .join(Issue, Issue.id == ReadingProgress.issue_id)
            .where(Issue.series_id == Series.id,
                   ReadingProgress.status == ReadingStatus.COMPLETED)
            .correlate(Series)
            .scalar_subquery()
        )
        total_numeros = (
            select(func.count(Issue.id))
            .where(Issue.series_id == Series.id)
            .correlate(Series)
            .scalar_subquery()
        )
        orden = (orden or "titulo").strip().lower()
        if orden not in ("titulo", "titulo_desc", "anio_desc", "anio_asc", "reciente"):
            orden = "titulo"
        # #664: `sort_title` puede ser NULL en toda la biblioteca; el título
        # alfabético cae entonces a `title_norm` (norma de `f_title_norm`).
        titulo = func.coalesce(Series.sort_title, Series.title_norm)
        if orden == "titulo":
            ordenes = (titulo.asc().nulls_last(),
                       Series.start_year.asc().nulls_last(), Series.id.asc())
        elif orden == "titulo_desc":
            ordenes = (titulo.desc().nulls_last(),
                       Series.start_year.desc().nulls_last(), Series.id.desc())
        elif orden == "anio_desc":
            ordenes = (Series.start_year.desc().nulls_last(),
                       titulo.asc().nulls_last(), Series.id.asc())
        elif orden == "anio_asc":
            ordenes = (Series.start_year.asc().nulls_last(),
                       titulo.asc().nulls_last(), Series.id.asc())
        else:
            ordenes = (Series.created_at.desc(), titulo.asc().nulls_last(),
                       Series.id.asc())
        query = query.order_by(*ordenes)
        query = query.add_columns(leidos_lectura.label("lectura_leidos"),
                                  total_numeros.label("lectura_total"))
        query = query.offset((pagina - 1) * page_size).limit(page_size)
        resultado = await self.db.execute(query)
        # Los dobles de prueba antiguos solo implementan `.scalars()`.
        filas = (resultado.all() if hasattr(resultado, "all")
                 else list(resultado.scalars().all()))
        items = []
        for fila in filas:
            if isinstance(fila, Series):
                # Dobles de prueba que devuelven la serie suelta: sin agregado.
                serie, leidos_n, total_n = fila, 0, 0
            else:
                serie, leidos_n, total_n = fila[0], fila[1], fila[2]
            serie.lectura_leidos = int(leidos_n or 0)
            serie.lectura_total = int(total_n or 0)
            items.append(serie)
        return items, total, pagina

    async def list_series(
        self,
        page: int = 1,
        page_size: int = 20,
        tradition: str | None = None,
        status: str | None = None,
        search: str | None = None,
        publisher_id: UUID | None = None,
        character_id: UUID | None = None,
        story_arc_id: UUID | None = None,
        etiquetas_positivas: tuple[str, ...] = (),
        etiquetas_negativas: tuple[str, ...] = (),
        leido: str | None = None,
        con_issues: bool = False,
        orden: str = "titulo",
        coleccion: str | None = None,
        coleccion_ids: set[UUID] | None = None,
    ) -> tuple[list[Series], int]:
        """Contrato histórico `(items, total)` para API y tests."""
        items, total, _ = await self._list_series(
            page=page, page_size=page_size, tradition=tradition, status=status,
            search=search, publisher_id=publisher_id, character_id=character_id,
            story_arc_id=story_arc_id,
            etiquetas_positivas=etiquetas_positivas,
            etiquetas_negativas=etiquetas_negativas, leido=leido, con_issues=con_issues,
            orden=orden, coleccion=coleccion, coleccion_ids=coleccion_ids,
            corregir_pagina=False,
        )
        return items, total

    async def list_series_paginado(
        self,
        page: int = 1,
        page_size: int = 20,
        tradition: str | None = None,
        status: str | None = None,
        search: str | None = None,
        publisher_id: UUID | None = None,
        character_id: UUID | None = None,
        story_arc_id: UUID | None = None,
        etiquetas_positivas: tuple[str, ...] = (),
        etiquetas_negativas: tuple[str, ...] = (),
        leido: str | None = None,
        con_issues: bool = False,
        orden: str = "titulo",
        coleccion: str | None = None,
        coleccion_ids: set[UUID] | None = None,
    ) -> tuple[list[Series], int, int]:
        """Como `list_series`, pero devuelve también la página efectiva.

        La biblioteca la necesita para construir la URL canónica sin volver a
        consultar (`page>pages` no cuesta un segundo SELECT).
        """
        return await self._list_series(
            page=page, page_size=page_size, tradition=tradition, status=status,
            search=search, publisher_id=publisher_id, character_id=character_id,
            story_arc_id=story_arc_id,
            etiquetas_positivas=etiquetas_positivas,
            etiquetas_negativas=etiquetas_negativas, leido=leido, con_issues=con_issues,
            orden=orden, coleccion=coleccion, coleccion_ids=coleccion_ids,
        )

    async def list_publishers_with_series(self) -> list[Publisher]:
        """Solo editoriales que de verdad tienen alguna serie — un
        dropdown con publishers vacíos no ayuda a filtrar nada."""
        return list((await self.db.execute(
            select(Publisher)
            .where(Publisher.id.in_(select(Series.publisher_id).where(Series.publisher_id.is_not(None))))
            .order_by(Publisher.name)
        )).scalars().all())

    async def nombres_de_filtros(
        self,
        publisher_id: UUID | None = None,
        character_id: UUID | None = None,
        story_arc_id: UUID | None = None,
    ) -> dict[str, str | None]:
        """Nombres legibles de los filtros activos, para sus chips.

        Una consulta por filtro presente (máximo tres) y ninguna si no hay
        filtros: el recuento de consultas de la biblioteca no depende del
        tamaño del catálogo (#283/BL-IT01).
        """
        nombres: dict[str, str | None] = {}
        if publisher_id is not None:
            nombres["publisher"] = (await self.db.execute(
                select(Publisher.name).where(Publisher.id == publisher_id)
            )).scalar()
        if character_id is not None:
            nombres["character"] = (await self.db.execute(
                select(Character.name).where(Character.id == character_id)
            )).scalar()
        if story_arc_id is not None:
            nombres["story_arc"] = (await self.db.execute(
                select(StoryArc.title).where(StoryArc.id == story_arc_id)
            )).scalar()
        return nombres

    async def search_characters(self, query: str, limit: int = 20) -> list[Character]:
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(Character).where(Character.name.ilike(f"%{query}%")).order_by(Character.name).limit(limit)
        )).scalars().all())

    async def search_story_arcs(self, query: str, limit: int = 20) -> list[StoryArc]:
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(StoryArc).where(StoryArc.title.ilike(f"%{query}%")).order_by(StoryArc.title).limit(limit)
        )).scalars().all())


# Fuentes cuyo `total_issues` está ACREDITADO como recuento de GRAPAS, que es
# la unidad de esta vista (`SINGLE_ISSUE` con número entero).
#
# Se dejan fuera a propósito:
#   - AniList: cuenta CAPÍTULOS. `enricher.py::_find_anilist_match` mapea
#     `chosen.chapters` a `count_of_issues`, y los ficheros de manga son
#     TOMOS (`TRADE_PAPERBACK`). Restar tomos de capítulos daría una lista de
#     huecos enorme y falsa — el mismo error que este cambio viene a evitar,
#     solo que disfrazado de dato.
#   - Tebeosfera: da "números" de una colección que puede ser de tomos o de
#     álbumes; la unidad no está acreditada.
#   - GCD: fuente declarada pero sin implementar todavía.
# Acreditarlas exige reglas por tradición/fuente y datos que hoy no tenemos;
# mientras tanto, decir "no se puede calcular" es más honesto que inventarlo.

UNIDAD_DE_GRAPA = {MetadataSource.COMIC_VINE.value}

def condicion_estado_coleccion(tipo: str):
    """Condición SQL del estado derivado de #340, sin cargar la biblioteca.

    La posesión se cuenta en una subconsulta correlada por serie (grapas con
    archivo disponible); el total y la unidad de la fuente salen de la propia
    fila. Así el filtro entra en la misma query paginada y en su COUNT.
    """
    decidida = (func.coalesce(
        Series.metadata_["coleccion"]["no_completar"].astext, "false") == "true")
    no_decidida = (func.coalesce(
        Series.metadata_["coleccion"]["no_completar"].astext, "false") != "true")
    computable = and_(
        Series.total_issues.isnot(None), Series.total_issues > 0,
        Series.metadata_source.in_(UNIDAD_DE_GRAPA))
    no_computable = or_(
        Series.total_issues.is_(None), Series.total_issues <= 0,
        Series.metadata_source.is_(None),
        Series.metadata_source.not_in(UNIDAD_DE_GRAPA))
    numero = case((Issue.issue_number.op("~")("^[0-9]+$"), Issue.issue_number),
                  else_=None)
    numero_int = cast(numero, Integer)
    poseidos = (
        select(func.count(func.distinct(numero_int)))
        .select_from(Issue)
        .join(File, File.issue_id == Issue.id)
        .where(Issue.series_id == Series.id,
               File.is_missing.is_(False),
               Issue.format == IssueFormat.SINGLE_ISSUE,
               numero_int.isnot(None),
               numero_int.between(1, Series.total_issues))
        .correlate(Series)
        .scalar_subquery()
    )
    faltan = Series.total_issues - func.coalesce(poseidos, 0)
    if tipo == "no_completar":
        return decidida
    if tipo == "no_calculable":
        return and_(no_decidida, no_computable)
    if tipo == "completa":
        return and_(no_decidida, computable, faltan <= 0)
    if tipo == "faltan":
        return and_(no_decidida, computable, faltan > 0)
    return None



@dataclass(frozen=True)
class Huecos:
    """Huecos de una serie y si el cálculo merece confianza.

    `computable=False` significa "no hay con qué calcularlo", NO "no falta
    nada": la UI debe decirlo en vez de enseñar una lista inventada.
    """
    faltantes: list[int]
    computable: bool
    motivo: str | None = None
    #: Valor interno de `metadata_source` (solo si es un `MetadataSource` válido y la causa es la UNIDAD de la fuente);
    #: nunca se imprime fuera del `<details>` «Ver el dato técnico» (C6, FR-11/FR-26).
    fuente: str | None = None


def compute_missing_issues(total_issues: int | None, numeros_poseidos: set[int]) -> list[int]:
    """Números 1..total_issues que la serie NO posee. Función pura.

    C2 (peer review): un Annual/especial no "cubre" el hueco de la grapa con
    el mismo número — eso lo garantiza `numero_de_grapa`, que exige
    `format=SINGLE_ISSUE` y un número entero, en vez de comparar floats.
    """
    if not total_issues:
        return []
    return [i for i in range(1, total_issues + 1) if i not in numeros_poseidos]


def numero_de_grapa(issue_number: str | None, formato) -> int | None:
    """Número entero si la fila ES una grapa numerada; `None` si no lo es.

    Solo una grapa (`SINGLE_ISSUE`) con número entero ocupa el hueco de la
    grapa de ese número. Un ómnibus/tomo #12 **no** es la grapa #12, y un
    `Annual 1` o un `1.5` tampoco tapan el hueco del nº 1 (regla de C2).
    """
    if formato != IssueFormat.SINGLE_ISSUE:
        return None
    if not issue_number or not issue_number.strip().isdigit():
        return None
    return int(issue_number.strip())


async def numeros_poseidos_por_serie(db: AsyncSession) -> dict[UUID, set[int]]:
    """Números de grapa poseídos, para TODAS las series, en una sola consulta.

    Versión agregada de `numeros_poseidos` para el dashboard (no N+1).
    """
    filas = (await db.execute(
        select(Issue.series_id, Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
    )).all()
    por_serie: dict[UUID, set[int]] = {}
    for series_id, numero, formato, disponible in filas:
        if not disponible:
            continue
        n = numero_de_grapa(numero, formato)
        if n is not None:
            por_serie.setdefault(series_id, set()).add(n)
    return por_serie


async def numeros_poseidos(db: AsyncSession, series_id: UUID) -> set[int]:
    """Números de grapa que la serie POSEE de verdad, mirando el DISCO.

    Por qué no `Issue.sort_order` (2026-09-27): **ningún código de `main`
    escribe ese campo** — la única derivación que existió (`_derive_sort_order`)
    se quedó en una rama abandonada. Medido con `scripts/medicion/censo_huecos.py`
    sobre una muestra: 0/18 issues con `sort_order` y **52 huecos inventados**
    en 5 series, porque `compute_missing_issues(N, ∅)` devuelve `[1..N]`.

    Ahora la posesión sale de lo que hay en disco — un `File` con
    `is_missing=false`, el mismo criterio que ya usan los demás consumidores
    de "¿lo tengo?" (B7) — y del formato: solo una grapa cubre una grapa.
    """
    filas = (await db.execute(
        select(Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
        .where(Issue.series_id == series_id)
    )).all()
    poseidos: set[int] = set()
    for numero, formato, disponible in filas:
        if not disponible:
            continue
        n = numero_de_grapa(numero, formato)
        if n is not None:
            poseidos.add(n)
    return poseidos


#: C6 (V-B): cómo se nombra cada fuente en la frase del motivo (RESTRICCIÓN-4: el texto se construye AQUÍ y el valor
#: interno llega aparte). Es un tercer mapa a propósito (los de `web/` no cubren `comicinfo_xml`, `manual` ni «sin
#: fuente»); no se unifican en esta historia.
NOMBRE_PUBLICO_DE_FUENTE = {
    MetadataSource.COMIC_VINE.value: "viene de Comic Vine",
    MetadataSource.ANILIST.value: "viene de AniList",
    MetadataSource.TEBEOSFERA.value: "viene de Tebeosfera",
    MetadataSource.GCD.value: "viene de GCD",
    MetadataSource.COMICINFO_XML.value: "viene del propio archivo",
    MetadataSource.MANUAL.value: "alta a mano",
}
NOMBRE_SIN_FUENTE = "sin fuente"
MOTIVO_SIN_TOTAL = "la serie no tiene un total de números conocido"


def razon_de_no_calculable(series: Series) -> Huecos | None:
    """Puro (sin base de datos): `Huecos` no computable si la serie no se puede calcular por su total o por la unidad
    de su fuente; `None` si la comprobación previa no lo impide. La usa `huecos_de_serie` y la ficha, que necesita saber
    si es calculable también con política `ninguno` (donde el predicado sale antes de calcular huecos)."""
    if not series.total_issues:
        return Huecos([], False, MOTIVO_SIN_TOTAL)
    if series.metadata_source not in UNIDAD_DE_GRAPA:
        valida = series.metadata_source if series.metadata_source in NOMBRE_PUBLICO_DE_FUENTE else None
        nombre = NOMBRE_PUBLICO_DE_FUENTE.get(valida or "", NOMBRE_SIN_FUENTE)
        return Huecos(
            [], False,
            "el total de la serie no consta como número de grapas "
            f"({nombre}), así que no se puede comparar con los números que hay en disco",
            fuente=valida,
        )
    return None


async def huecos_de_serie(db: AsyncSession, series: Series,
                          poseidos: set[int] | None = None) -> Huecos:
    """Huecos de una serie, diciendo — explícitamente — si el cálculo es fiable.

    Antes de restar hay que comprobar que las dos cantidades hablan de lo
    MISMO: `total_issues` lo copia el enricher del catálogo y **no siempre
    cuenta grapas** (AniList cuenta capítulos y sus ficheros son tomos). Si la
    unidad no está acreditada, `computable=False` en vez de una resta inventada.

    `poseidos` permite reutilizar una consulta ya hecha (la ficha de serie
    necesita el conjunto igualmente, para pintar los números presentes).
    """
    no_calculable = razon_de_no_calculable(series)
    if no_calculable is not None:
        return no_calculable
    if poseidos is None:
        poseidos = await numeros_poseidos(db, series.id)
    return Huecos(compute_missing_issues(series.total_issues, poseidos), True, None)
