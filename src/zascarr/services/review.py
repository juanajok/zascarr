"""
ReviewService — acciones de la bandeja de pendientes (B2).

Archivos que el importer no supo clasificar viven en _Unsorted/ con
issue_id=None. El coleccionista los resuelve a mano desde la UI:
  - asignar a una serie existente, creando el Issue si el número no
    existe todavía (el caso más común: la mayoría de archivos en
    _Unsorted no tienen un Issue esperando ya en la BD).
  - ignorar: se deja de mostrar en la bandeja para siempre.

Una asignación manual confirmada por el coleccionista es EXACTAMENTE el
caso para el que existe la convención metadata_source='manual' (fix C3
del peer review): el File se marca así y el enricher nunca lo toca (los
archivos no son su terreno). El Issue nuevo, en cambio, NO se marca
'manual' — eso bloquearía sinopsis/portada/créditos que el enricher sí
debería poder rellenar más adelante — sino que protege únicamente la
asignación serie+número vía locked_fields (H3, peer review v2).

Cada asignación manual también alimenta el alias local de B13
(`_learn_alias`): el patrón de nombre que llevó a este archivo a
Pendientes queda memorizado → la serie elegida, para que
SeriesMatcher.decide() no vuelva a preguntar la próxima vez.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import DateTime, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import (
    EDITION_KIND_A_FORMAT,
    File,
    Issue,
    IssueFormat,
    LocalAlias,
    MetadataSource,
    Series,
)
from zascarr.services.importer import build_library_path
from zascarr.utils.fs import safe_move_async
from zascarr.utils.naming import parse_comic_filename

# B15 (2026-09-26): el mapa edition_kind → IssueFormat vive en models junto al
# enum (lo comparten el camino manual y el automático; ver EDITION_KIND_A_FORMAT).

# B15 (2026-09-26): motivo que se deja en el File cuando el número pedido ya
# existe en la serie con OTRO Issue.format (grapa #12 vs Omnigold 12). Es la
# señal de que hace falta decidir a mano cuál de las dos ediciones es esa.
MOTIVO_COLISION_EDICION = "número compartido entre ediciones"


class ColisionDeEdicionError(ValueError):
    """Un Issue ya existe para la serie + número con distinto Issue.format.

    Enlazar el archivo a esa fila (o cambiarle el format) reutilizaría una
    grapa para una recopilación, o al revés — se deja en Pendientes."""
    def __init__(self, issue_number: str, formato_existente: str, file_name: str):
        self.issue_number = issue_number
        self.formato_existente = formato_existente
        super().__init__(
            f"El número {issue_number} ya existe en esta serie como otra edición "
            f"({formato_existente}) — {MOTIVO_COLISION_EDICION}. El archivo "
            f"'{file_name}' se queda en Pendientes sin asignar."
        )


#: Pendientes por página en «Por revisar».
POR_PAGINA = 50
#: `imported_at` ADMITE NULL en la BD (la migración inicial no pone NOT NULL, aunque el
#: modelo no declare `Optional`). Una comparación con NULL no es verdadera ni falsa: la fila
#: quedaría fuera de todo cursor. Se trata como la fecha más antigua: va la última y siempre
#: se alcanza.
SIN_FECHA = datetime(1970, 1, 1, tzinfo=UTC)
_MOMENTO = func.coalesce(File.imported_at, literal(SIN_FECHA, DateTime(timezone=True)))
#: Un cursor es `imported_at|id` y cabe de sobra; más es un parámetro manipulado.
MAX_CLAVE = 100


@dataclass(frozen=True)
class ClavePendiente:
    """La posición de un pendiente en la lista: `(imported_at, id)`. Es la CLAVE del cursor."""
    imported_at: datetime
    id: UUID

    def a_texto(self) -> str:
        return f"{self.imported_at.isoformat()}|{self.id}"

    @staticmethod
    def de(archivo: File) -> ClavePendiente:
        return ClavePendiente(archivo.imported_at or SIN_FECHA, archivo.id)

    @staticmethod
    def desde_texto(texto: str | None) -> ClavePendiente | None:
        """None si no tiene la forma exacta. Se lee con desconfianza: viene de la URL."""
        if not texto or len(texto) > MAX_CLAVE or texto.count("|") != 1:
            return None
        ts, _, ident = texto.partition("|")
        try:
            momento = datetime.fromisoformat(ts)
            ident_uuid = UUID(ident)
        except ValueError:
            return None
        if momento.tzinfo is None:
            return None
        return ClavePendiente(momento, ident_uuid)


@dataclass
class PaginaPendientes:
    archivos: list
    total: int
    desde: int
    hasta: int
    hay_anterior: bool
    hay_siguiente: bool


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._library = get_settings().library_path

    @staticmethod
    def _condiciones_pendientes() -> tuple:
        """El filtro de «pendiente», UNO solo: lo usan la lista y el recuento del menú (V3). Si el
        recuento tuviera su propio filtro, el número del menú dejaría de coincidir con la lista."""
        return (
            File.issue_id.is_(None),
            File.review_dismissed.is_(False),
            File.metadata_["match_status"].astext == "unsorted",
        )

    async def count_pending(self) -> int:
        """Cuántos archivos hay por revisar, SIN el tope de 50 de `pending_files`."""
        return (await self.db.execute(
            select(func.count()).select_from(File).where(*self._condiciones_pendientes())
        )).scalar_one()

    async def pending_files(self, limit: int = 50) -> list[File]:
        """Archivos sin match fiable que nadie ha resuelto ni descartado.

        Bug real (reportado, B11): filtraba por vivir bajo `_Unsorted/`
        en disco — un proxy que solo es cierto para el importer de
        descargas (que SÍ mueve ahí lo que no reconoce). LibraryAdopter
        (B11) registra los archivos sin match EN SU SITIO REAL, nunca
        los mueve — con el filtro de ruta, quedaban invisibles en
        Pendientes para siempre, aunque `issue_id` fuera NULL.

        `issue_id IS NULL` por sí solo tampoco vale: una serie SÍ
        identificada pero sin el número exacto (issue_id NULL, hueco del
        enricher, D1) también lo cumple y esa NO es la bandeja de
        Pendientes — se resuelve sola cuando el enricher encuentre el
        número. La señal correcta es `match_status == 'unsorted'`
        (guardado en `metadata_` por Importer/LibraryAdopter, el mismo
        criterio con el que ambos deciden mover/registrar en _Unsorted o
        no), no la ruta ni solo el issue_id.
        """
        return list((await self.db.execute(
            select(File)
            .where(*self._condiciones_pendientes())
            .order_by(File.imported_at.desc())
            .limit(limit)
        )).scalars().all())

    @staticmethod
    def _ref(c: ClavePendiente):
        """La clave como valor tipado para comparar con `(imported_at, id)`."""
        return tuple_(literal(c.imported_at, DateTime(timezone=True)), literal(c.id, File.id.type))

    async def pagina_de_pendientes(
        self, *, despues: ClavePendiente | None = None, antes: ClavePendiente | None = None,
        limite: int = POR_PAGINA,
    ) -> PaginaPendientes:
        """Una página de la cola, por CURSOR sobre `(imported_at DESC, id DESC)` (U12).

        La cola SE VACÍA: asignar o ignorar una tarjeta la saca del conjunto. Con un
        desplazamiento (`OFFSET`) calculado antes de resolver, «Siguiente» omitiría
        pendientes; una CLAVE no se desplaza: «Siguiente» es «lo que va después de ESTA
        fila», exista ya o no. `id` desempata: una adopción registra muchos archivos en
        una transacción y `now()` es el mismo para todos.

        `despues` = lo que sigue a esa clave; `antes` = lo que la precede (se consulta al
        revés y se invierte); ninguno = el principio. Un cursor que ya no lleva a nada
        cae en el principio.

        Presupuesto: una consulta de lista y dos `COUNT` (el total y la posición del
        primero mostrado), sin `OFFSET`."""
        clave = tuple_(_MOMENTO, File.id)
        total = await self.count_pending()
        filas: list[File] = []
        if antes is not None or despues is not None:
            consulta = select(File).where(*self._condiciones_pendientes())
            if antes is not None:
                consulta = (consulta.where(clave > self._ref(antes))
                            .order_by(_MOMENTO.asc(), File.id.asc()).limit(limite))
                filas = list(reversed(list((await self.db.execute(consulta)).scalars().all())))
            else:
                consulta = (consulta.where(clave < self._ref(despues))
                            .order_by(_MOMENTO.desc(), File.id.desc()).limit(limite))
                filas = list((await self.db.execute(consulta)).scalars().all())
        if not filas:                       # sin cursor, o un cursor que ya no lleva a nada
            filas = list((await self.db.execute(
                select(File).where(*self._condiciones_pendientes())
                .order_by(_MOMENTO.desc(), File.id.desc()).limit(limite)
            )).scalars().all())
        if not filas:
            return PaginaPendientes([], total, 0, 0, False, False)
        delante = await self.contar_antes_de(ClavePendiente.de(filas[0]))
        return PaginaPendientes(
            archivos=filas, total=total, desde=delante + 1, hasta=delante + len(filas),
            hay_anterior=delante > 0, hay_siguiente=total - delante - len(filas) > 0)

    async def contar_antes_de(self, c: ClavePendiente) -> int:
        """Cuántos pendientes van ANTES de esa clave en el orden de la lista."""
        return (await self.db.execute(
            select(func.count()).select_from(File)
            .where(*self._condiciones_pendientes(),
                   tuple_(_MOMENTO, File.id) > self._ref(c))
        )).scalar_one()

    async def contar_entre(self, primero: ClavePendiente, ultimo: ClavePendiente) -> int:
        """Cuántos pendientes hay hoy entre dos claves, ambas incluidas: lo que queda de
        una página que ya se mostró."""
        clave = tuple_(_MOMENTO, File.id)
        return (await self.db.execute(
            select(func.count()).select_from(File)
            .where(*self._condiciones_pendientes(),
                   clave <= self._ref(primero), clave >= self._ref(ultimo))
        )).scalar_one()

    async def search_series(self, query: str, limit: int = 20) -> list[Series]:
        """Búsqueda manual para el selector de la bandeja: coincidencia
        parcial de título, no la lógica estricta de SeriesMatcher (esa es
        para decidir sola; aquí decide una persona mirando la pantalla)."""
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(Series)
            .where(Series.title.ilike(f"%{query}%"))
            .order_by(Series.title)
            .limit(limit)
        )).scalars().all())

    async def assign_to_series(self, file_id, series_id, issue_number: str) -> File:
        """CAMINO HEREDADO: mueve el fichero con la sesión de la petición y deja el `commit` a
        `get_db` (auditoría V6a, `docs/design/auditoria-mover-y-sesion.md`: un fallo entre mover y
        confirmar deja el fichero movido y la BD revertida). **Ya no lo usa ninguna ruta**:
        `POST /ui/pendientes/{id}/asignar` va por `services/asignacion.py` (ADR 0006). Se conserva,
        con sus pruebas de B13/B15, hasta retirarlo en una limpieza aparte; **no lo llames desde
        código nuevo**."""
        issue_number = (issue_number or "").strip()
        if not issue_number:
            raise ValueError("El número de issue no puede estar vacío")

        file = await self.db.get(File, file_id)
        if not file:
            raise ValueError("Archivo no encontrado")

        series = await self.db.get(Series, series_id)
        if not series:
            raise ValueError("Serie no encontrada")

        # B15 (2026-09-26): el Issue.format que correspondería a este archivo
        # se decide ANTES de buscar el Issue, para poder compararlo con el que
        # ya exista. Un mismo número puede ser dos ediciones distintas (la
        # grapa #12 y el Omnigold 12): enlazar el recopilatorio a la grapa, o
        # cambiarle el formato, rompe el catálogo. Se re-parsea el nombre
        # original (todavía no reescrito abajo) y no metadata_, que puede
        # faltar en archivos registrados antes de que existiera edition_kind.
        edition_kind = parse_comic_filename(file.file_name).edition_kind
        formato_esperado = EDITION_KIND_A_FORMAT.get(edition_kind, IssueFormat.SINGLE_ISSUE)

        issue = (await self.db.execute(
            select(Issue)
            .where(Issue.series_id == series.id)
            .where(Issue.issue_number == issue_number)
        )).scalar_one_or_none()

        if issue is not None and (issue.format or IssueFormat.SINGLE_ISSUE) != formato_esperado:
            # Colisión de ediciones: mismo número, distinto Issue.format. No se
            # enlaza silenciosamente ni se cambia el format existente; se deja
            # el archivo en Pendientes con un motivo claro para la persona.
            file.metadata_ = {**(file.metadata_ or {}),
                              "review_motivo": MOTIVO_COLISION_EDICION}
            raise ColisionDeEdicionError(
                issue_number, (issue.format or IssueFormat.SINGLE_ISSUE).value, file.file_name
            )

        if not issue:
            # H3 (peer review v2): antes se marcaba metadata_source='manual',
            # lo que bloqueaba TODO el issue para el enricher (sinopsis,
            # portada, créditos incluidos) solo por proteger la asignación
            # serie+número que hizo el coleccionista. locked_fields protege
            # justo eso y deja que el resto se siga rellenando.
            issue = Issue(
                series_id=series.id,
                issue_number=issue_number,
                locked_fields=["series_id", "issue_number"],
                format=formato_esperado,
            )
            self.db.add(issue)
            await self.db.flush()

        orig = Path(file.file_path)
        # capturado antes de reescribirlo abajo (B13: patrón de aprendizaje)
        original_name = file.file_name
        dest = build_library_path(self._library, series, issue_number, orig.suffix)
        # A3: mover a destino verificado — nunca sobreescribe ni borra el
        # original hasta que la copia está completa (ver utils/fs.safe_move).
        final_dest = await safe_move_async(orig, dest)

        file.issue_id = issue.id
        file.file_path = str(final_dest)
        file.file_name = final_dest.name
        file.metadata_source = MetadataSource.MANUAL.value
        await self.db.flush()
        await self._learn_alias(original_name, series.id)
        return file

    async def _learn_alias(self, original_filename: str, series_id) -> None:
        """B13: cada asignación manual desde Pendientes es, por definición,
        una corrección — el matcher ya no supo resolverla solo (esa es la
        única razón por la que el archivo llegó a esta bandeja). Se
        aprende el patrón (título que naming.py extrae del nombre de
        archivo, normalizado) → serie, para que SeriesMatcher.decide()
        no vuelva a preguntar la próxima vez que aparezca. Una corrección
        más reciente sobre el mismo patrón sustituye a la anterior."""
        parsed = parse_comic_filename(original_filename)
        if not parsed.series:
            return
        pattern = normalize_title(parsed.series)
        if not pattern:
            return
        existing = (await self.db.execute(
            select(LocalAlias).where(LocalAlias.pattern_norm == pattern)
        )).scalar_one_or_none()
        if existing:
            existing.series_id = series_id
        else:
            self.db.add(LocalAlias(pattern_norm=pattern, series_id=series_id))
        await self.db.flush()

    async def dismiss(self, file_id) -> None:
        file = await self.db.get(File, file_id)
        if not file:
            raise ValueError("Archivo no encontrado")
        file.review_dismissed = True
        await self.db.flush()
