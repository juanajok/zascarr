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
    "token_caducado": "Han pasado más de 15 minutos. No se ha cambiado nada; vuelve a buscar la ficha.",
    "procedencia_invalida": "La procedencia guardada de esta serie no es válida. No se ha cambiado nada.",
    "conflicto_de_bloqueo": "Otra operación coincidió con esta. No se ha cambiado nada.",
}


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
    if not isinstance(e, dict) or e.get("version") != 1:
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
        if meta.get(clave) is not None and not isinstance(meta.get(clave), list):
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

    async def confirmar(self, token: str) -> ResultadoAsociacion:
        firmada = verificar_token_asociacion(
            token, self._secret, ahora=self._ahora, ignorar_caducidad=True
        )
        if firmada is None:
            raise TokenInvalidoError("La propuesta no es válida: vuelve a buscarla.")
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
            await db.execute(select(Series).where(Series.id == sid).with_for_update())
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
            if e.get("operacion_id") == firmada.operacion:
                await db.commit()
                return self._ya_retirada(firmada)
        if not vigente:
            await db.commit()
            return self._omitida(firmada, "token_caducado")

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
            return self._omitida(firmada, "conflicto_identificador", otra_serie=otra.title)

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
        await db.commit()
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
        self, firmada: AsociacionFirmada, motivo: str, *, otra_serie: str | None = None
    ) -> ResultadoAsociacion:
        return ResultadoAsociacion(
            version=VERSION_RESULTADO,
            tipo=TIPO_INFORME,
            operacion_id=firmada.operacion,
            series_id=firmada.serie_id,
            resultado="omitida",
            motivo=motivo,
            mensaje=MENSAJES.get(motivo, "No se ha cambiado nada."),
            fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            titulo=firmada.titulo,
            otra_serie=otra_serie,
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
