# ruff: noqa: E501
"""Edición de una serie (I5 de #114, ADR 0010 P-4).

Cambiar el **título, la tradición o el año** de una serie es cambiar su identidad, y por esa puerta se podía evitar la
detección de series parecidas que se exige al alta: renombrar una serie hasta chocar con otra. Ahora, si el cambio
**modifica de verdad** alguno de esos tres campos, se ejecuta la MISMA detección que en el alta (`buscar_parecidas`: título
normalizado, año ±1, misma tradición, excluida la propia serie) bajo el MISMO candado del título normalizado. Si hay
parecidas que el cliente no declaró haber visto (`vistas`), no se cambia nada y se le devuelven; para seguir, repite la
petición con sus identificadores en `vistas` («se rechaza si han aparecido otras que no vio»).

El resto de campos (descripción, portada, estado, política de búsqueda…) **no cambia de comportamiento**: sin tocar la
identidad no hay candado ni consulta extra, y la escritura sigue siendo un `flush`.

**Límite transaccional.** Este servicio NO confirma: la transacción es la de la petición (`get_db` la confirma al terminar,
como en el resto de ediciones), tanto si cambia la identidad como si no. El candado del título dura hasta ese `commit`, así
que otra operación que espere por él ve lo ya escrito. Solo deshace (`rollback`) en el camino de error, para soltar los
candados sin esperar a que `get_db` lo haga. Por eso la sesión que recibe debe ser una **sin cambios pendientes ajenos** (la
de la petición lo es): si se pide cambiar la identidad lo comprueba y se niega si no, en vez de confirmar o descartar trabajo de otro.

Orden de bloqueos, el común: título › serie (`FOR UPDATE`). Como el título que hay que bloquear puede depender del actual
(si el cuerpo no lo trae), se vuelve a comprobar tras tomar la fila y se reintenta unas pocas veces si cambió entre medias.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Series
from zascarr.services.alta_serie import DemasiadasParecidasError, bloquear_titulo, buscar_parecidas
from zascarr.services.borrado_serie import SerieNoEncontradaError
from zascarr.services.descubrimiento_grupo import SerieParecida
from zascarr.services.tokens_revision import MAX_PARECIDAS_FIRMADAS

CAMPOS_DE_IDENTIDAD = ("title", "tradition", "start_year")
INTENTOS = 3


class ParecidasSinVerError(Exception):
    """El cambio de identidad choca con series que el cliente no declaró haber visto. `parecidas` = TODAS las halladas."""

    def __init__(self, parecidas: list[SerieParecida]):
        super().__init__("Hay series que se parecen: revísalas y, si quieres continuar, repite la petición con sus "
                         "identificadores en «vistas».")
        self.parecidas = parecidas


class SesionConTrabajoPendienteError(RuntimeError):
    """Precondición rota: la sesión ya tenía cambios sin confirmar que no son de esta edición."""


class SerieCambiadaError(Exception):
    """La serie cambió mientras se comprobaba; el cliente puede repetir."""


class EdicionDeSerie:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def actualizar(self, series_id: UUID, cambios: dict, vistas: set[str]) -> Series:
        db = self._db
        # ANTES de la primera consulta (que vaciaría —`autoflush`— lo pendiente de otro dentro de esta transacción).
        if any(c in cambios for c in CAMPOS_DE_IDENTIDAD) and (db.new or db.dirty or db.deleted):
            raise SesionConTrabajoPendienteError(
                "EdicionDeSerie necesita una sesión sin cambios pendientes: no confirma ni descarta trabajo ajeno.")
        serie = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if serie is None:
            raise SerieNoEncontradaError(str(series_id))
        if not self._cambia_la_identidad(serie, cambios):
            self._aplicar(serie, cambios)
            await db.flush()
            return serie
        return await self._con_identidad(series_id, cambios, vistas)

    @staticmethod
    def _cambia_la_identidad(serie: Series, cambios: dict) -> bool:
        return any(c in cambios and cambios[c] != getattr(serie, c) for c in CAMPOS_DE_IDENTIDAD)

    @staticmethod
    def _aplicar(serie: Series, cambios: dict) -> None:
        for campo, valor in cambios.items():
            setattr(serie, campo, valor)

    async def _con_identidad(self, series_id: UUID, cambios: dict, vistas: set[str]) -> Series:
        db = self._db
        try:
            for _ in range(INTENTOS):
                actual = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
                if actual is None:
                    raise SerieNoEncontradaError(str(series_id))
                titulo = cambios.get("title", actual.title)
                await bloquear_titulo(db, titulo)
                fila = (await db.execute(select(Series).where(Series.id == series_id).with_for_update()
                                         .execution_options(populate_existing=True))).scalar_one_or_none()
                if fila is None:
                    raise SerieNoEncontradaError(str(series_id))
                if "title" not in cambios and fila.title != titulo:        # su título cambió: el candado era de otro
                    await db.rollback()
                    continue
                anio = cambios.get("start_year", fila.start_year)
                tradicion = cambios.get("tradition", fila.tradition)
                parecidas = await buscar_parecidas(db, titulo, anio, tradicion, excluir=str(series_id))
                if len(parecidas) > MAX_PARECIDAS_FIRMADAS:
                    raise DemasiadasParecidasError(
                        f"Ya hay {len(parecidas)} series con ese título: son demasiadas para decidir desde aquí. "
                        "Revisa los duplicados antes de cambiar esta.")
                if any(p.series_id not in vistas for p in parecidas):
                    raise ParecidasSinVerError(parecidas)
                self._aplicar(fila, cambios)
                await db.flush()
                await db.refresh(fila)                  # `title_norm` es una columna generada: se relee tras el UPDATE
                return fila                             # el `commit` lo hace `get_db`, como en el resto de ediciones
            raise SerieCambiadaError()
        except BaseException:
            await db.rollback()
            raise
