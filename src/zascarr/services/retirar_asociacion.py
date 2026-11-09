# ruff: noqa: E501
"""Retirar SOLO la identidad de una fuente, con historial y sin tocar nada más (#129 C).

La columna es la autoridad; la entrada activa de `metadata.asociaciones` pasa a
`metadata.asociaciones_historial` con `previo` y `deshecho`. No se consulta ninguna fuente, no se
tocan números, archivos, otras fuentes, `metadata_source` ni `locked_fields`.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import MetadataSource, Series, VinculacionOperacion
from zascarr.services.asociacion_fuente import (
    _columna,
    _metadata,
    _nombre,
)
from zascarr.services.tokens_revision import (
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
    verificar_token_retirar_asociacion,
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
TIPO_INFORME = "retirar_asociacion"
_ESPACIO_OPERACION = "ret_asoc_op:"
MENSAJES = {
    "propuesta_desactualizada": "La asociación cambió desde que abriste la vista previa. No se ha retirado nada; vuelve a revisarla.",
    "serie_inexistente": "Esta serie ya no está en tu biblioteca.",
    "token_caducado": "Han pasado más de 15 minutos. No se ha cambiado nada; vuelve a revisar la ficha.",
    "conflicto_operacion": "El identificador de esta operación ya está ocupado. No se ha cambiado nada.",
    "conflicto_de_bloqueo": "Otra operación coincidió con esta. No se ha cambiado nada.",
}


@dataclass(frozen=True)
class VistaPreviaRetirar:
    serie_id: str
    titulo: str
    fuente: str
    id_externo: str | None
    anio: int | None
    fecha: str | None
    procedencia: str
    estado: str
    mensaje: str
    token: str | None = None


@dataclass
class ResultadoRetirarAsociacion:
    version: int
    tipo: str
    operacion_id: str
    series_id: str
    resultado: Literal["retirada", "ya_retirada", "omitida"]
    motivo: str | None
    mensaje: str
    repetida: bool = False
    fuente: str | None = None
    id_externo: str | None = None
    titulo: str | None = None
    fecha: str | None = None
    efectos: dict = field(default_factory=dict)

    @property
    def codigo(self) -> str:
        return self.motivo or self.resultado

    @property
    def nombre_fuente(self) -> str:
        return _nombre(self.fuente) if self.fuente else "la web"


def huella_de_asociacion_actual(serie: Series, fuente: str) -> str:
    """Huella de SOLO la fuente C: columna + entrada activa válida (o null)."""
    col = _columna(fuente)
    meta = serie.metadata_ if isinstance(serie.metadata_, dict) else {}
    activas = meta.get("asociaciones") if isinstance(meta.get("asociaciones"), list) else []
    activa = None
    for e in activas:
        if isinstance(e, dict) and e.get("fuente") == fuente and not e.get("deshecho"):
            activa = {k: e.get(k) for k in sorted(e)}
            break
    datos = {
        "version": 1, "serie_id": str(serie.id), "fuente": fuente,
        "id_externo": (str(getattr(serie, col)) if getattr(serie, col) is not None else None),
        "activa": activa,
    }
    return hashlib.sha256(json.dumps(
        datos, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _fecha(valor: object) -> str | None:
    if not isinstance(valor, str):
        return None
    try:
        f = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return f.date().isoformat() if f.tzinfo else None


class RetirarAsociacionDeFuente:
    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._ahora = ahora
        self._commit_pedido = False

    def _fecha(self) -> str:
        return datetime.fromtimestamp(self._ahora if self._ahora is not None else time.time(),
                                      UTC).isoformat()

    async def previsualizar(self, series_id: UUID,
                            fuente: MetadataSource) -> VistaPreviaRetirar:
        serie = (await self._db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if serie is None:
            raise LookupError("serie inexistente")
        col = _columna(fuente.value)
        actual = getattr(serie, col)
        active = None
        meta = serie.metadata_ if isinstance(serie.metadata_, dict) else {}
        for e in (meta.get("asociaciones") or []):
            if isinstance(e, dict) and e.get("fuente") == fuente.value:
                active = e
                break
        if actual is None:
            return VistaPreviaRetirar(
                str(serie.id), serie.title, fuente.value, None, serie.start_year, None,
                "no registrada", "ya_retirada",
                "No se ha cambiado nada: esa ficha ya no estaba asociada.")
        token = crear_token_retirar_asociacion(RetirarAsociacionFirmada(
            version=1, entidad="serie", fuente=fuente.value, id_externo=str(actual),
            huella=huella_de_asociacion_actual(serie, fuente.value),
            operacion=str(uuid4()), serie_id=str(serie.id)), self._secret,
            ahora=self._ahora)
        return VistaPreviaRetirar(
            str(serie.id), serie.title, fuente.value, str(actual), serie.start_year,
            _fecha(active.get("fecha")) if isinstance(active, dict) else None,
            "registrada" if active is not None else "no registrada", "ok",
            "Vas a quitar la ficha de esta serie. No se borra nada.", token)

    async def confirmar(self, token: str) -> ResultadoRetirarAsociacion:
        firmada = verificar_token_retirar_asociacion(
            token, self._secret, ahora=self._ahora, ignorar_caducidad=True)
        if firmada is None:
            raise TokenInvalidoError("La propuesta no es válida: vuelve a revisar la ficha.")
        vigente = verificar_token_retirar_asociacion(token, self._secret, ahora=self._ahora) is not None
        try:
            return await self._transaccion(firmada, vigente)
        except BaseException as exc:
            with contextlib.suppress(Exception):
                await self._db.rollback()
            if self._commit_pedido and isinstance(exc, Exception):
                raise ResultadoInciertoError("No se sabe si se retiró la asociación.") from None
            if isinstance(exc, DBAPIError) and _es_interbloqueo(exc):
                raise ConflictoDeBloqueoError(MENSAJES["conflicto_de_bloqueo"]) from None
            raise

    async def _transaccion(self, firmada: RetirarAsociacionFirmada,
                           vigente: bool) -> ResultadoRetirarAsociacion:
        db = self._db
        sid = UUID(firmada.serie_id)
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
                         {"k": _ESPACIO_OPERACION, "o": firmada.operacion})
        previo = (await db.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == UUID(firmada.operacion)))).scalar_one_or_none()
        if previo is not None:
            informe = previo.resultado or {}
            if (informe.get("tipo") == TIPO_INFORME
                    and informe.get("series_id") == firmada.serie_id
                    and informe.get("fuente") == firmada.fuente
                    and informe.get("id_externo") == firmada.id_externo):
                await db.commit()
                return self._repetida(informe)
            await db.commit()
            return self._omitida(firmada, "conflicto_operacion")
        if firmada.entidad != "serie" or firmada.fuente not in {f.value for f in MetadataSource}:
            await db.commit()
            return self._omitida(firmada, "token_invalido")
        serie = (await db.execute(select(Series).where(Series.id == sid).with_for_update())).scalar_one_or_none()
        if serie is None:
            await db.commit()
            return self._omitida(firmada, "serie_inexistente")
        meta = _metadata(serie)
        if meta is None:
            await db.commit()
            return self._omitida(firmada, "propuesta_desactualizada")
        activas = [e for e in (meta.get("asociaciones") or []) if isinstance(e, dict)]
        historial = [e for e in (meta.get("asociaciones_historial") or []) if isinstance(e, dict)]
        for e in historial:
            if e.get("operacion_id") == firmada.operacion or (
                    isinstance(e.get("deshecho"), dict)
                    and e["deshecho"].get("operacion_id") == firmada.operacion):
                await db.commit()
                return self._ya_retirada(firmada, repetida=True)
        if not vigente:
            await db.commit()
            return self._omitida(firmada, "token_caducado")
        col = _columna(firmada.fuente)
        actual = getattr(serie, col)
        if actual is None:
            await db.commit()
            return self._ya_retirada(firmada, repetida=False)
        if str(actual) != firmada.id_externo:
            await db.commit()
            return self._omitida(firmada, "propuesta_desactualizada")
        if huella_de_asociacion_actual(serie, firmada.fuente) != firmada.huella:
            await db.commit()
            return self._omitida(firmada, "propuesta_desactualizada")

        fecha = self._fecha()
        activa = next((e for e in activas if e.get("fuente") == firmada.fuente), None)
        if activa is not None:
            previo_dato = dict(activa)
            entrada = {**activa}
        else:
            previo_dato = {
                "version": 1, "fuente": firmada.fuente, "id_externo": firmada.id_externo,
                "entidad": "serie", "kind": None, "fecha": None,
                "operacion_id": None, "origen": "desconocida", "modo": "busqueda",
                "procedencia": "desconocida",
            }
            entrada = {**previo_dato, "procedencia": "desconocida"}
        entrada["deshecho"] = {"operacion_id": firmada.operacion, "fecha": fecha,
                               "motivo": "retirada"}
        entrada["previo"] = previo_dato
        nueva = copy.deepcopy(meta)
        nueva["asociaciones"] = [e for e in activas if e.get("fuente") != firmada.fuente]
        nueva["asociaciones_historial"] = [*historial, entrada]
        informe = self._informe(firmada, fecha, "retirada", False, activa is not None)
        try:
            resultado = await db.execute(
                update(Series).where(Series.id == sid, getattr(Series, col).is_not(None))
                .values({col: None, "metadata_": nueva})
                .execution_options(synchronize_session=False))
            if resultado.rowcount != 1:
                await db.rollback()
                return self._omitida(firmada, "propuesta_desactualizada")
            db.add(VinculacionOperacion(
                operacion_id=UUID(firmada.operacion), series_id=sid, resultado=informe,
                token_hasta=datetime.fromtimestamp(firmada.caduca, UTC)))
            await db.flush()
            await self._purgar()
        except IntegrityError:
            await db.rollback()
            return self._omitida(firmada, "conflicto_operacion")
        self._commit_pedido = True
        await db.commit()
        return ResultadoRetirarAsociacion(**{k: informe[k] for k in ResultadoRetirarAsociacion.__dataclass_fields__ if k in informe})

    def _informe(self, firmada, fecha, resultado, repetida, tenia_procedencia):
        return {
            "version": VERSION_RESULTADO, "tipo": TIPO_INFORME, "operacion_id": firmada.operacion,
            "series_id": firmada.serie_id, "resultado": resultado, "motivo": None,
            "mensaje": f"{_nombre(firmada.fuente)} ya no está asociada a esta serie. La serie, sus "
                       "números y tus archivos siguen igual.",
            "repetida": repetida, "fuente": firmada.fuente, "id_externo": firmada.id_externo,
            "titulo": None, "fecha": fecha,
            "efectos": {"campos_serie": 1, "asociaciones": 1, "comprobantes": 1,
                        "numeros": 0, "archivos": 0, "metadatos_aplicados": 0},
        }

    def _omitida(self, firmada, motivo):
        return ResultadoRetirarAsociacion(
            version=VERSION_RESULTADO, tipo=TIPO_INFORME, operacion_id=firmada.operacion,
            series_id=firmada.serie_id, resultado="omitida", motivo=motivo,
            mensaje=MENSAJES.get(motivo, "No se ha cambiado nada."), fuente=firmada.fuente,
            id_externo=firmada.id_externo,
            efectos={k: 0 for k in ("campos_serie", "asociaciones", "comprobantes", "numeros", "archivos", "metadatos_aplicados")})

    def _ya_retirada(self, firmada, *, repetida):
        return ResultadoRetirarAsociacion(
            version=VERSION_RESULTADO, tipo=TIPO_INFORME, operacion_id=firmada.operacion,
            series_id=firmada.serie_id, resultado="ya_retirada", motivo=None,
            mensaje="No se ha cambiado nada: esa ficha ya no estaba asociada.", repetida=repetida,
            fuente=firmada.fuente, id_externo=firmada.id_externo,
            efectos={k: 0 for k in ("campos_serie", "asociaciones", "comprobantes", "numeros", "archivos", "metadatos_aplicados")})

    def _repetida(self, informe):
        datos = dict(informe)
        datos["repetida"] = True
        datos["resultado"] = "ya_retirada"
        datos.setdefault("mensaje", "No se ha cambiado nada: esa ficha ya no estaba asociada.")
        return ResultadoRetirarAsociacion(**{k: datos[k] for k in ResultadoRetirarAsociacion.__dataclass_fields__ if k in datos})

    async def _purgar(self):
        await self._db.execute(text(
            "DELETE FROM vinculacion_operaciones WHERE operacion_id IN ("
            " SELECT operacion_id FROM vinculacion_operaciones"
            " WHERE resultado ->> 'tipo' = :tipo"
            "   AND creada < now() - make_interval(hours => :h)"
            "   AND token_hasta < now()"
            " ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)"),
            {"tipo": TIPO_INFORME, "h": RETENCION_HORAS, "n": LOTE_DE_PURGA})
