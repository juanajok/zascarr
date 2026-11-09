# ruff: noqa: E501
"""Confirmar una asociación de otra fuente, idempotente y sin fusionar (#129 B).

La columna de identidad es la autoridad de unicidad; `metadata.asociaciones` guarda la
procedencia y `vinculacion_operaciones` el comprobante que hace repetible la confirmación.
No se toca `metadata_source`, `locked_fields`, números, archivos ni se consulta ninguna fuente:
si la fuente se apagó entre A y B (D-H16), B guarda igual y avisa.
"""

from __future__ import annotations

import contextlib
import copy
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import MetadataSource, Series, VinculacionOperacion
from zascarr.services.asociar_fuente import CandidataComparada, huella_de_asociacion
from zascarr.services.discovery import CAMPO_ID_EXTERNO
from zascarr.services.tokens_revision import (
    TTL_SEGUNDOS,
    AsociacionFirmada,
    id_canonico,
    verificar_token_asociacion,
)
from zascarr.services.vinculacion import (
    LOTE_DE_PURGA,
    RETENCION_HORAS,
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenInvalidoError,
    _es_interbloqueo,
)

VERSION_RESULTADO = 1
TIPO_INFORME = "asociar_fuente"
_ESPACIO_OPERACION = "asoc_op:"
_MODO = "busqueda"
_NOMBRES = {
    MetadataSource.COMIC_VINE: "Comic Vine",
    MetadataSource.ANILIST: "AniList",
    MetadataSource.TEBEOSFERA: "Tebeosfera",
    MetadataSource.GCD: "GCD",
}
_ATRIBUTOS = {
    MetadataSource.COMIC_VINE: "comicvine_enabled",
    MetadataSource.ANILIST: "anilist_enabled",
    MetadataSource.TEBEOSFERA: "tebeosfera_enabled",
    MetadataSource.GCD: "gcd_enabled",
}
MENSAJES = {
    "propuesta_no_asociable": "Esa ficha no se puede asociar: no es una serie.",
    "propuesta_desactualizada": "Tu serie ha cambiado desde que buscaste. No se ha asociado nada; "
    "vuelve a buscarla.",
    "ya_tiene_identidad_en_esa_fuente": "Esta serie ya tiene otra ficha de esa web. Retírala primero si quieres cambiarla.",
    "conflicto_identificador": "Esa ficha ya está asociada a otra serie. No se ha cambiado nada.",
    "conflicto_operacion": "El identificador de esta operación ya está ocupado. No se ha cambiado nada.",
    "serie_inexistente": "Esta serie ya no está en tu biblioteca.",
    "procedencia_invalida": "La procedencia guardada de esta serie no es válida. No se ha cambiado nada.",
    "conflicto_de_bloqueo": "Otra operación coincidió con esta. No se ha cambiado nada.",
}
#: H2 (#129 B): no se puede afirmar «no se ha cambiado nada» si el comprobante ya pudo purgarse.
MENSAJE_CADUCADO_SIN_APLICAR = (
    "Han pasado más de 15 minutos y esta confirmación no llegó a guardarse: no se ha asociado "
    "nada. Vuelve a buscar la ficha."
)
MENSAJE_CADUCADO_SIN_INFORME = (
    "Han pasado más de 15 minutos y ya no se conserva el registro de esta operación: no se puede "
    "saber si llegó a asociarse. Vuelve a buscar la ficha para ver el estado actual."
)
#: H8: campos admitidos en una entrada activa; uno desconocido invalida la entrada.
_CLAVES_ENTRADA = frozenset({
    "version", "fuente", "id_externo", "entidad", "kind", "fecha", "operacion_id",
    "origen", "modo",
})


@dataclass
class ResultadoAsociacion:
    version: int
    tipo: str
    operacion_id: str
    series_id: str
    resultado: Literal["asociada", "ya_asociada", "omitida", "ya_retirada"]
    motivo: str | None
    mensaje: str
    repetida: bool = False
    fuente: str | None = None
    id_externo: str | None = None
    titulo: str | None = None
    aviso: str | None = None
    otra_serie: str | None = None
    otra_serie_id: str | None = None
    fecha: str | None = None
    efectos: dict = field(default_factory=dict)

    def como_informe(self) -> dict:
        from dataclasses import asdict

        return asdict(self)

    @property
    def codigo(self) -> str:
        return self.motivo or self.resultado

    @property
    def nombre_fuente(self) -> str:
        return _NOMBRES.get(MetadataSource(self.fuente), str(self.fuente)) if self.fuente else "la web"


def _columna(fuente: str) -> str:
    return CAMPO_ID_EXTERNO[MetadataSource(fuente)]


def _valor(fuente: str, id_externo: str) -> int | str:
    campo = _columna(fuente)
    return id_externo if campo == "tebeosfera_slug" else int(id_externo)


def _nombre(fuente: str) -> str:
    return _NOMBRES.get(MetadataSource(fuente), fuente)


def _entrada_valida(e: object) -> bool:
    if not isinstance(e, dict) or set(e) != _CLAVES_ENTRADA or e.get("version") != 1:
        return False
    if e.get("fuente") not in {f.value for f in _NOMBRES}:
        return False
    if e.get("entidad") != "serie" or e.get("kind") not in (None, "collection", "saga"):
        return False
    if e.get("origen") not in ("confirmada", "enriquecimiento"):
        return False
    if e.get("modo") not in ("busqueda", "id_exacto"):
        return False
    if id_canonico(str(e.get("fuente")), e.get("id_externo")) != e.get("id_externo"):
        return False
    try:
        UUID(str(e.get("operacion_id")))
        fecha = datetime.fromisoformat(str(e.get("fecha")))
    except (ValueError, TypeError):
        return False
    return fecha.tzinfo is not None


def _metadata(serie: Series) -> dict | None:
    meta = serie.metadata_ if isinstance(serie.metadata_, dict) else None
    if meta is None:
        return None
    for clave in ("asociaciones", "asociaciones_historial"):
        lista = meta.get(clave)
        if lista is None:
            continue
        if not isinstance(lista, list) or any(not isinstance(e, dict) for e in lista):
            return None
    return meta


def _resultado_repetido(informe: dict) -> ResultadoAsociacion:
    datos = dict(informe)
    datos["repetida"] = True
    datos.setdefault(
        "mensaje", "Es la misma asociación que acabas de guardar. No se ha duplicado nada."
    )
    return ResultadoAsociacion(
        **{k: datos[k] for k in ResultadoAsociacion.__dataclass_fields__ if k in datos}
    )


def _entrada_historial_valida(e: object) -> bool:
    """H3/H8: una entrada de historial solo acredita si cumple el mismo esquema que las activas.

    El historial puede llevar `previo`/`deshecho`, pero un objeto suelto como
    `{"operacion_id": ...}` no es evidencia de nada y se ignora.
    """
    if not isinstance(e, dict):
        return False
    activa = {k: v for k, v in e.items() if k not in ("deshecho", "previo")}
    if not _entrada_valida(activa):
        return False
    deshecho = e.get("deshecho")
    if not isinstance(deshecho, dict):
        return False
    try:
        UUID(str(deshecho.get("operacion_id")))
    except (ValueError, TypeError):
        return False
    return True


class AsociacionDeFuente:
    """Confirma un token de A. Solo escribe si puede probar identidad, unicidad y huella."""

    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._ahora = ahora
        self._commit_pedido = False

    def _fecha(self) -> str:
        return datetime.fromtimestamp(
            self._ahora if self._ahora is not None else time.time(), UTC
        ).isoformat()

    async def confirmar(self, token: str, *, serie_esperada: UUID | str | None = None) -> ResultadoAsociacion:
        firmada = verificar_token_asociacion(
            token, self._secret, ahora=self._ahora, ignorar_caducidad=True
        )
        if firmada is None:
            raise TokenInvalidoError("La propuesta no es válida: vuelve a buscarla.")
        # F2 (#129 B): el contexto de la URL manda; un token de A no se aplica en B.
        if serie_esperada is not None and firmada.serie_id != str(serie_esperada):
            raise TokenInvalidoError(
                "La propuesta pertenece a otra serie; no se ha asociado nada. Vuelve a abrirla "
                "desde su serie.")
        vigente = verificar_token_asociacion(token, self._secret, ahora=self._ahora) is not None
        try:
            return await self._transaccion(firmada, vigente)
        except BaseException as exc:
            with contextlib.suppress(Exception):
                await self._db.rollback()
            if self._commit_pedido and isinstance(exc, Exception):
                raise ResultadoInciertoError("No se sabe si se guardó la asociación.") from None
            if isinstance(exc, DBAPIError) and _es_interbloqueo(exc):
                raise ConflictoDeBloqueoError(MENSAJES["conflicto_de_bloqueo"]) from None
            raise

    async def _transaccion(self, firmada: AsociacionFirmada, vigente: bool) -> ResultadoAsociacion:
        db = self._db
        sid = UUID(firmada.serie_id)
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
            {"k": _ESPACIO_OPERACION, "o": firmada.operacion},
        )
        previo = (
            await db.execute(
                select(VinculacionOperacion).where(
                    VinculacionOperacion.operacion_id == UUID(firmada.operacion)
                )
            )
        ).scalar_one_or_none()
        if previo is not None:
            informe = previo.resultado or {}
            if (
                informe.get("tipo") == TIPO_INFORME
                and informe.get("series_id") == firmada.serie_id
                and informe.get("fuente") == firmada.fuente
                and informe.get("id_externo") == firmada.id_externo
            ):
                await db.commit()
                return _resultado_repetido(informe)
            await db.commit()
            return self._omitida(firmada, "conflicto_operacion")
        if (
            firmada.entidad != "serie"
            or firmada.kind == "saga"
            or firmada.kind not in (None, "collection")
        ):
            await db.commit()
            return self._omitida(firmada, "propuesta_no_asociable")
        if firmada.kind == "saga":
            await db.commit()
            return self._omitida(firmada, "propuesta_no_asociable")

        serie = (
            await db.execute(
                select(Series).where(Series.id == sid).with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if serie is None:
            await db.commit()
            return self._omitida(firmada, "serie_inexistente")
        meta = _metadata(serie)
        if meta is None:
            await db.commit()
            return self._omitida(firmada, "procedencia_invalida")
        activas = (
            [e for e in (meta.get("asociaciones") or []) if isinstance(e, dict)]
            if isinstance(meta.get("asociaciones"), list)
            else []
        )
        historial = (
            [e for e in (meta.get("asociaciones_historial") or []) if isinstance(e, dict)]
            if isinstance(meta.get("asociaciones_historial"), list)
            else []
        )
        for e in activas:
            if e.get("operacion_id") == firmada.operacion:
                if (
                    e.get("fuente") == firmada.fuente
                    and e.get("id_externo") == firmada.id_externo
                    and _entrada_valida(e)
                ):
                    await db.commit()
                    return self._repetida_activa(firmada)
                await db.commit()
                return self._omitida(firmada, "procedencia_invalida")
        for e in historial:
            if e.get("operacion_id") == firmada.operacion and _entrada_historial_valida(e):
                await db.commit()
                return self._ya_retirada(firmada)
        if not vigente:
            ahora = self._ahora if self._ahora is not None else time.time()
            firma = firmada.caduca - TTL_SEGUNDOS
            puede_haberse_aplicado = ahora >= firma + RETENCION_HORAS * 3600
            await db.commit()
            return self._omitida(
                firmada, "token_caducado",
                mensaje=(MENSAJE_CADUCADO_SIN_INFORME if puede_haberse_aplicado
                         else MENSAJE_CADUCADO_SIN_APLICAR),
            )

        col = _columna(firmada.fuente)
        actual = getattr(serie, col)
        if actual is not None:
            await db.commit()
            return (
                self._ya_asociada(firmada)
                if str(actual) == firmada.id_externo
                else self._omitida(firmada, "ya_tiene_identidad_en_esa_fuente")
            )
        otra = (
            await db.execute(
                select(Series.id, Series.title).where(
                    getattr(Series, col) == _valor(firmada.fuente, firmada.id_externo)
                )
            )
        ).first()
        if otra is not None:
            await db.commit()
            return self._omitida(firmada, "conflicto_identificador", otra_serie=otra.title,
                                     otra_serie_id=(str(otra.id) if getattr(otra, "id", None) else None))

        candidata = CandidataComparada(
            titulo=firmada.titulo,
            anio=firmada.anio,
            editorial=None,
            pais=None,
            idioma=None,
            id_externo=firmada.id_externo,
            sitio_url=firmada.sitio_url,
            tradicion=None,
            kind=firmada.kind,
            fuente=firmada.fuente,
        )
        if huella_de_asociacion(serie, candidata) != firmada.huella:
            await db.commit()
            return self._omitida(firmada, "propuesta_desactualizada")
        for e in activas:
            if e.get("fuente") == firmada.fuente:
                await db.commit()
                return self._omitida(firmada, "procedencia_invalida")
        # H8: no se propaga JSONB inválido ni siquiera de otras fuentes; la lista
        # resultante tiene que ser íntegramente válida antes del UPDATE.
        if any(not _entrada_valida(e) for e in activas):
            await db.commit()
            return self._omitida(firmada, "procedencia_invalida")

        fecha = self._fecha()
        entrada = {
            "version": 1,
            "fuente": firmada.fuente,
            "id_externo": firmada.id_externo,
            "entidad": "serie",
            "kind": firmada.kind,
            "fecha": fecha,
            "operacion_id": firmada.operacion,
            "origen": "confirmada",
            "modo": _MODO,
        }
        if not _entrada_valida(entrada):
            await db.commit()
            return self._omitida(firmada, "procedencia_invalida")
        nueva = copy.deepcopy(meta)
        nueva["asociaciones"] = [*activas, entrada]
        if "asociaciones_historial" not in nueva:
            nueva["asociaciones_historial"] = []
        # H16: si la fuente está apagada, se guarda sin red y se avisa.
        settings = get_settings()
        apagada = not bool(getattr(settings, _ATRIBUTOS[MetadataSource(firmada.fuente)]))
        informe = self._informe(
            firmada,
            fecha,
            "asociada",
            repetida=False,
            aviso=(
                "La fuente está apagada en Ajustes; la asociación se guarda porque no se ha "
                "consultado."
                if apagada
                else None
            ),
        )
        try:
            resultado = await db.execute(
                update(Series)
                .where(Series.id == sid, getattr(Series, col).is_(None))
                .values({col: _valor(firmada.fuente, firmada.id_externo), "metadata_": nueva})
                .execution_options(synchronize_session=False)
            )
            if resultado.rowcount != 1:
                await db.rollback()
                return self._omitida(firmada, "conflicto_identificador")
            db.add(
                VinculacionOperacion(
                    operacion_id=UUID(firmada.operacion),
                    series_id=sid,
                    resultado=informe,
                    token_hasta=datetime.fromtimestamp(firmada.caduca, UTC),
                )
            )
            await db.flush()
            await self._purgar()
        except IntegrityError:
            await db.rollback()
            return self._omitida(firmada, "conflicto_identificador")
        self._commit_pedido = True
        try:
            await db.commit()
        except IntegrityError:
            # Un UNIQUE que salta en el commit es definitivo: no es un resultado incierto.
            await db.rollback()
            self._commit_pedido = False
            return self._omitida(firmada, "conflicto_identificador")
        return ResultadoAsociacion(
            **{k: informe[k] for k in ResultadoAsociacion.__dataclass_fields__ if k in informe}
        )

    def _informe(
        self,
        firmada: AsociacionFirmada,
        fecha: str,
        resultado: str,
        *,
        repetida: bool,
        aviso: str | None = None,
    ) -> dict:
        return {
            "version": VERSION_RESULTADO,
            "tipo": TIPO_INFORME,
            "operacion_id": firmada.operacion,
            "series_id": firmada.serie_id,
            "resultado": resultado,
            "motivo": None,
            "mensaje": f"{_nombre(firmada.fuente)} queda asociada a esta serie. Si repites esta "
            "confirmación, no se duplica.",
            "repetida": repetida,
            "fuente": firmada.fuente,
            "id_externo": firmada.id_externo,
            "titulo": firmada.titulo,
            "fecha": fecha,
            "aviso": aviso,
            "efectos": {
                "campos_serie": 1,
                "asociaciones": 1,
                "comprobantes": 1,
                "numeros": 0,
                "archivos": 0,
                "metadatos_aplicados": 0,
            },
        }

    def _omitida(
        self, firmada: AsociacionFirmada, motivo: str, *, otra_serie: str | None = None,
        otra_serie_id: str | None = None, mensaje: str | None = None,
    ) -> ResultadoAsociacion:
        return ResultadoAsociacion(
            version=VERSION_RESULTADO,
            tipo=TIPO_INFORME,
            operacion_id=firmada.operacion,
            series_id=firmada.serie_id,
            resultado="omitida",
            motivo=motivo,
            mensaje=mensaje or MENSAJES.get(motivo, "No se ha cambiado nada."),
            fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            titulo=firmada.titulo,
            otra_serie=otra_serie,
            otra_serie_id=otra_serie_id,
            efectos={
                k: 0
                for k in (
                    "campos_serie",
                    "asociaciones",
                    "comprobantes",
                    "numeros",
                    "archivos",
                    "metadatos_aplicados",
                )
            },
        )

    def _ya_asociada(self, firmada: AsociacionFirmada) -> ResultadoAsociacion:
        return ResultadoAsociacion(
            version=VERSION_RESULTADO,
            tipo=TIPO_INFORME,
            operacion_id=firmada.operacion,
            series_id=firmada.serie_id,
            resultado="ya_asociada",
            motivo=None,
            mensaje="No se ha cambiado nada: esa ficha ya constaba en esta serie.",
            fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            titulo=firmada.titulo,
            efectos={
                k: 0
                for k in (
                    "campos_serie",
                    "asociaciones",
                    "comprobantes",
                    "numeros",
                    "archivos",
                    "metadatos_aplicados",
                )
            },
        )

    def _repetida_activa(self, firmada: AsociacionFirmada) -> ResultadoAsociacion:
        return ResultadoAsociacion(
            version=VERSION_RESULTADO,
            tipo=TIPO_INFORME,
            operacion_id=firmada.operacion,
            series_id=firmada.serie_id,
            resultado="asociada",
            motivo=None,
            mensaje="Es la misma asociación que acabas de guardar. No se ha duplicado nada.",
            repetida=True,
            fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            titulo=firmada.titulo,
            efectos={
                k: 0
                for k in (
                    "campos_serie",
                    "asociaciones",
                    "comprobantes",
                    "numeros",
                    "archivos",
                    "metadatos_aplicados",
                )
            },
        )

    def _ya_retirada(self, firmada: AsociacionFirmada) -> ResultadoAsociacion:
        return ResultadoAsociacion(
            version=VERSION_RESULTADO,
            tipo=TIPO_INFORME,
            operacion_id=firmada.operacion,
            series_id=firmada.serie_id,
            resultado="ya_retirada",
            motivo=None,
            mensaje=(
                "Esa asociación se retiró después de guardarse. No se ha vuelto a asociar nada."
            ),
            repetida=True,
            fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            titulo=firmada.titulo,
            efectos={
                k: 0
                for k in (
                    "campos_serie",
                    "asociaciones",
                    "comprobantes",
                    "numeros",
                    "archivos",
                    "metadatos_aplicados",
                )
            },
        )

    async def _purgar(self) -> None:
        await self._db.execute(
            text(
                "DELETE FROM vinculacion_operaciones WHERE operacion_id IN ("
                " SELECT operacion_id FROM vinculacion_operaciones"
                " WHERE resultado ->> 'tipo' = :tipo"
                "   AND creada < now() - make_interval(hours => :h)"
                "   AND token_hasta < now()"
                " ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)"
            ),
            {"tipo": TIPO_INFORME, "h": RETENCION_HORAS, "n": LOTE_DE_PURGA},
        )


# ── H11: auditoría y reparación de la procedencia JSONB ─────────────────────────────────────────

@dataclass(frozen=True)
class IncidenciaAsociacion:
    tipo: str
    fuente: str | None
    detalle: str


@dataclass(frozen=True)
class ReparacionAsociaciones:
    incidencias: tuple[IncidenciaAsociacion, ...]
    movidas: int
    reparada: bool


def _entradas_activas(meta: dict) -> list[object]:
    return meta.get("asociaciones") if isinstance(meta.get("asociaciones"), list) else []


def auditar_asociaciones(series: Series) -> tuple[IncidenciaAsociacion, ...]:
    """Solo lectura: entradas activas huérfanas, duplicadas o inválidas (H11).

    Una columna con id sin entrada activa es LEGACY, no huérfana; no se repara ni se inventa
    procedencia. La columna sigue siendo la autoridad y no se toca.
    """
    meta = series.metadata_ if isinstance(series.metadata_, dict) else None
    if meta is None:
        return (IncidenciaAsociacion("json_invalido", None, "metadata no es un objeto"),)
    if "asociaciones" in meta and not isinstance(meta.get("asociaciones"), list):
        return (IncidenciaAsociacion("json_invalido", None, "asociaciones no es una lista"),)
    if "asociaciones_historial" in meta and not isinstance(meta.get("asociaciones_historial"), list):
        return (IncidenciaAsociacion("json_invalido", None, "asociaciones_historial no es una lista"),)
    incidencias: list[IncidenciaAsociacion] = []
    vistos: dict[str, int] = {}
    for e in _entradas_activas(meta):
        if not isinstance(e, dict):
            incidencias.append(IncidenciaAsociacion("invalida", None, "entrada no es un objeto"))
            continue
        fuente = e.get("fuente")
        if not _entrada_valida(e):
            incidencias.append(IncidenciaAsociacion(
                "invalida", str(fuente) if fuente is not None else None,
                "no cumple el esquema activo"))
            continue
        vistos[str(fuente)] = vistos.get(str(fuente), 0) + 1
        if vistos[str(fuente)] > 1:
            incidencias.append(IncidenciaAsociacion(
                "duplicada", str(fuente), "más de una entrada activa para la misma fuente"))
            continue
        try:
            col = _columna(str(fuente))
        except (KeyError, ValueError):
            incidencias.append(IncidenciaAsociacion("invalida", str(fuente), "fuente desconocida"))
            continue
        actual = getattr(series, col, None)
        if actual is None or str(actual) != str(e.get("id_externo")):
            incidencias.append(IncidenciaAsociacion(
                "huerfana", str(fuente),
                "la entrada activa no coincide con la columna de la fuente"))
    return tuple(incidencias)


async def reparar_asociaciones(db: AsyncSession, series_id: UUID, *,
                               confirmar: bool = True) -> ReparacionAsociaciones:
    """Explícita e idempotente: mueve huérfanas/duplicadas/inválidas al historial SIN tocar la columna.

    Nunca se ejecuta automáticamente desde B/C y no inventa identidad: la columna manda.
    """
    serie = (await db.execute(
        select(Series).where(Series.id == series_id).with_for_update())).scalar_one_or_none()
    if serie is None:
        raise LookupError("serie inexistente")
    incidencias = auditar_asociaciones(serie)
    if not confirmar or not incidencias:
        return ReparacionAsociaciones(incidencias, 0, False)
    meta = copy.deepcopy(serie.metadata_ if isinstance(serie.metadata_, dict) else {})
    activas = _entradas_activas(meta)
    nuevas: list[object] = []
    historial = meta.get("asociaciones_historial")
    historial = list(historial) if isinstance(historial, list) else []
    movidas = 0
    conservadas: set[str] = set()
    for e in activas:
        if not isinstance(e, dict) or not _entrada_valida(e):
            historial.append({"previo": e, "deshecho": {
                "operacion_id": None, "fecha": datetime.now(UTC).isoformat(), "motivo": "reparacion"}})
            movidas += 1
            continue
        fuente = str(e.get("fuente"))
        try:
            col = _columna(fuente)
        except (KeyError, ValueError):
            historial.append({"previo": e, "deshecho": {
                "operacion_id": None, "fecha": datetime.now(UTC).isoformat(), "motivo": "reparacion"}})
            movidas += 1
            continue
        actual = getattr(serie, col, None)
        if fuente in conservadas or actual is None or str(actual) != str(e.get("id_externo")):
            historial.append({"previo": e, "deshecho": {
                "operacion_id": None, "fecha": datetime.now(UTC).isoformat(), "motivo": "reparacion"}})
            movidas += 1
            continue
        conservadas.add(fuente)
        nuevas.append(e)
    meta["asociaciones"] = nuevas
    meta["asociaciones_historial"] = historial
    await db.execute(update(Series).where(Series.id == series_id)
                     .values({"metadata_": meta}).execution_options(synchronize_session=False))
    await db.commit()
    return ReparacionAsociaciones(incidencias, movidas, True)
