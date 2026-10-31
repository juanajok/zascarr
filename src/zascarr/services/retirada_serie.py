# ruff: noqa: E501
"""Retirar una serie de la biblioteca SIN borrar sus archivos (BL-SER1, #303)."""
from __future__ import annotations

import contextlib
import hashlib
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import delete, or_, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionOperacion,
    File,
    Issue,
    LocalAlias,
    Series,
    StoryArcIssue,
    VinculacionOperacion,
    Wishlist,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.asignacion import conflicto_por_operacion_viva
from zascarr.services.borrado_serie import SerieNoEncontradaError
from zascarr.services.desvinculacion import aplicar_desvinculacion, procedencia_de
from zascarr.services.tokens_revision import (
    TTL_SEGUNDOS,
    RetiradaFirmada,
    crear_token_retirada,
    verificar_token_retirada,
)
from zascarr.services.vinculacion import (
    LOTE_DE_PURGA,
    MENSAJE_CADUCADO_SIN_APLICAR,
    MENSAJE_CADUCADO_SIN_INFORME,
    RETENCION_HORAS,
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
    VinculacionError,
    _es_interbloqueo,
)

VERSION_RESULTADO = 1
_ESPACIO_OPERACION = "reti_op:"
TIPO_INFORME = "retirada_serie"
DESEADOS_QUE_BLOQUEAN = (WishlistStatus.SEARCHING.value, WishlistStatus.DOWNLOADING.value)

MENSAJES = {
    "serie_inexistente": "Esta serie ya no está en tu biblioteca: puede que otra pantalla la retirara o borrara. "
                         "No se ha cambiado nada más.",
    "cambio_desde_la_vista_previa": "La serie cambió desde que abriste la vista previa (por ejemplo, se vinculó otro "
                                    "archivo, se añadió un número o empezó una búsqueda). No se ha cambiado nada: "
                                    "ábrela de nuevo para ver cómo está ahora.",
    "en_curso": "Ahora mismo ZascArr está trabajando con esta serie: una asignación de archivos o la búsqueda o "
                "descarga de un deseado. No se ha cambiado nada: espera a que terminen (suele tardar minutos) y "
                "vuelve a abrir la vista previa.",
}
BLOQUEOS = {
    "asignacion_viva": "ZascArr está asignando archivos a esta serie ahora mismo. Espera a que la asignación termine "
                       "(o se recupere) y vuelve a intentarlo.",
    "deseado_en_curso": "Hay deseos de esta serie con una búsqueda o una descarga en marcha. Espera a que terminen "
                        "(puedes verlo en «Deseados») y vuelve a intentarlo.",
}
AVISO_DISCO = "Los archivos del disco no se borrarán, moverán ni renombrarán."
AVISO_DESPUES = ("Los archivos vinculados vuelven a «Por revisar» y se pueden vincular a otra serie con el recorrido "
                 "habitual. La serie no reaparece sola: ZascArr no da de alta series automáticamente.")


class RetiradaError(VinculacionError):
    codigo = "retirada_error"


class Bloqueo(BaseModel):
    codigo: str
    mensaje: str
    detalle: list[str] = []


class SerieARetirar(BaseModel):
    id: str
    titulo: str
    anio: int | None
    total: int | None
    politica: str


class NumeroRetirado(BaseModel):
    id: str
    numero: str | None
    volumen: int
    formato: str
    archivos: int
    lecturas: int
    deseados: int
    sagas: int


class ArchivoPorRevisar(BaseModel):
    id: str
    nombre: str
    ruta: str
    numero: str | None
    formato: str
    falta_en_disco: bool
    procedencia: Literal["registrada", "desconocida"]


class DeseoRetirado(BaseModel):
    id: str
    numero: int | None
    estado: str
    origen: str
    por_numero: bool


class VistaPreviaRetirada(BaseModel):
    series_id: str
    serie: SerieARetirar
    puede_retirar: bool
    bloqueos: list[Bloqueo]
    numeros: list[NumeroRetirado]
    archivos: list[ArchivoPorRevisar]
    deseados: list[DeseoRetirado]
    alias: int
    sagas: int
    aviso_disco: str
    aviso_despues: str
    token: str | None


class ArchivoResultado(BaseModel):
    id: str
    nombre: str | None
    numero: str | None


class ResultadoRetirada(BaseModel):
    version: int
    operacion_id: str
    series_id: str
    titulo: str | None
    resultado: Literal["retirada", "ya_retirada", "omitido"]
    motivo: str | None
    mensaje: str
    fecha: str | None
    totales: dict
    archivos: list[ArchivoResultado]


def _texto(v: object) -> str | None:
    if v is None:
        return None
    return v.value if hasattr(v, "value") else str(v)


def _operacion_del_vinculo(meta: dict | None, series_id: object) -> str | None:
    v = procedencia_de(meta, series_id)
    return v["operacion_id"] if isinstance(v, dict) and isinstance(v.get("operacion_id"), str) else None


def _match_status(meta: dict | None) -> str | None:
    v = (meta or {}).get("match_status")
    return v if isinstance(v, str) else None


def estado_canonico(serie: Series, alias, numeros, archivos, deseados, vivas, sagas) -> dict:
    return {
        "serie": {"titulo": serie.title, "tradicion": _texto(serie.tradition),
                  "anio_inicio": serie.start_year, "anio_fin": serie.end_year,
                  "total": serie.total_issues,
                  "politica": _texto(serie.wishlist_policy or WishlistPolicy.NONE)},
        "alias": sorted([[str(a.id), a.pattern_norm] for a in alias]),
        "numeros": sorted([[str(n.id), n.issue_number, n.volume, _texto(n.format)] for n in numeros]),
        "archivos": sorted([[str(f.id), str(f.issue_id), f.file_path, f.file_size_bytes, f.sha256_hash,
                             bool(f.is_missing), f.metadata_source, bool(f.review_dismissed),
                             _operacion_del_vinculo(f.metadata_, f.series_id_de_issue), _match_status(f.metadata_)]
                            for f in archivos]),
        "deseados": sorted([[str(w.id), str(w.issue_id) if w.issue_id is not None else None, w.numero,
                             _texto(w.status), _texto(w.origen)] for w in deseados]),
        "vivas": sorted([[str(o.id), str(o.file_id) if o.file_id is not None else None,
                          str(o.series_id) if o.series_id is not None else None, _texto(o.estado)] for o in vivas]),
        "sagas": sorted([[str(s.story_arc_id), str(s.issue_id), s.reading_order] for s in sagas]),
    }


def huella_de_estado(estado: dict) -> str:
    return hashlib.sha256(json.dumps(estado, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def bloqueos_de(deseados, vivas) -> list[Bloqueo]:
    out: list[Bloqueo] = []
    if vivas:
        out.append(Bloqueo(codigo="asignacion_viva", mensaje=BLOQUEOS["asignacion_viva"],
                           detalle=[f"{len(vivas)} asignación de archivos en curso"]))
    en_curso = [w for w in deseados if _texto(w.status) in DESEADOS_QUE_BLOQUEAN]
    if en_curso:
        detalle = []
        for w in en_curso:
            que = "descargando" if _texto(w.status) == WishlistStatus.DOWNLOADING.value else "buscando"
            donde = f"el nº {w.numero}" if w.numero is not None else "un deseado de la serie"
            detalle.append(f"{donde} se está {que}")
        out.append(Bloqueo(codigo="deseado_en_curso", mensaje=BLOQUEOS["deseado_en_curso"], detalle=detalle))
    return out


class RetiradaDeSerie:
    _gancho_con_filas_bloqueadas = None

    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._ahora = ahora
        self._commit_pedido = False

    async def _leer_estado(self, serie: Series) -> SimpleNamespace:
        db = self._db
        sid = serie.id
        alias = (await db.execute(
            select(LocalAlias.id, LocalAlias.pattern_norm).where(LocalAlias.series_id == sid)
            .order_by(LocalAlias.pattern_norm))).all()
        numeros = (await db.execute(text(
            "SELECT i.id, i.issue_number, i.volume, i.format, "
            "  (SELECT count(*) FROM files f WHERE f.issue_id = i.id) AS archivos, "
            "  (SELECT count(*) FROM reading_progress rp WHERE rp.issue_id = i.id) AS lecturas, "
            "  (SELECT count(*) FROM wishlist w WHERE w.issue_id = i.id) AS deseados, "
            "  (SELECT count(*) FROM story_arc_issues s WHERE s.issue_id = i.id) AS sagas "
            "FROM issues i WHERE i.series_id = CAST(:s AS uuid) "
            "ORDER BY i.volume, i.issue_number NULLS LAST, i.id"), {"s": str(sid)})).all()
        archivos = (await db.execute(
            select(File.id, File.file_name, File.file_path, File.file_size_bytes, File.sha256_hash, File.is_missing,
                   File.metadata_, File.metadata_source, File.review_dismissed, File.issue_id,
                   Issue.issue_number, Issue.format)
            .join(Issue, File.issue_id == Issue.id).where(Issue.series_id == sid).order_by(File.id))).all()
        deseados = (await db.execute(
            select(Wishlist.id, Wishlist.series_id, Wishlist.issue_id, Wishlist.numero, Wishlist.status, Wishlist.origen)
            .where(or_(Wishlist.series_id == sid,
                       Wishlist.issue_id.in_(select(Issue.id).where(Issue.series_id == sid))))
            .order_by(Wishlist.id))).all()
        vivas = (await db.execute(
            select(AsignacionOperacion.id, AsignacionOperacion.file_id, AsignacionOperacion.series_id,
                   AsignacionOperacion.estado)
            .where(AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS),
                   or_(AsignacionOperacion.series_id == sid,
                       AsignacionOperacion.file_id.in_(
                           select(File.id).join(Issue, File.issue_id == Issue.id).where(Issue.series_id == sid))))
            .order_by(AsignacionOperacion.id))).all()
        sagas = (await db.execute(
            select(StoryArcIssue.story_arc_id, StoryArcIssue.issue_id, StoryArcIssue.reading_order)
            .join(Issue, StoryArcIssue.issue_id == Issue.id).where(Issue.series_id == sid)
            .order_by(StoryArcIssue.issue_id))).all()
        series_de_issue = {str(n.id): str(sid) for n in numeros}
        return SimpleNamespace(serie=serie, alias=alias, numeros=numeros, archivos=[
            SimpleNamespace(**f._mapping, series_id_de_issue=series_de_issue.get(str(f.issue_id), str(sid)))
            for f in archivos], deseados=deseados, vivas=vivas, sagas=sagas)

    async def previsualizar(self, series_id: UUID) -> VistaPreviaRetirada:
        db = self._db
        serie = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if serie is None:
            raise SerieNoEncontradaError(str(series_id))
        e = await self._leer_estado(serie)
        bloqueos = bloqueos_de(e.deseados, e.vivas)
        huella = huella_de_estado(estado_canonico(e.serie, e.alias, e.numeros, e.archivos, e.deseados, e.vivas, e.sagas))
        token = None
        if not bloqueos:
            token = crear_token_retirada(
                RetiradaFirmada(series_id=str(series_id), huella=huella, operacion=str(uuid4())),
                self._secret, ahora=self._ahora)
        return VistaPreviaRetirada(
            series_id=str(series_id),
            serie=SerieARetirar(id=str(serie.id), titulo=serie.title, anio=serie.start_year,
                                total=serie.total_issues,
                                politica=_texto(serie.wishlist_policy or WishlistPolicy.NONE)),
            puede_retirar=not bloqueos, bloqueos=bloqueos,
            numeros=[NumeroRetirado(id=str(n.id), numero=n.issue_number, volumen=n.volume, formato=_texto(n.format),
                                    archivos=n.archivos, lecturas=n.lecturas, deseados=n.deseados, sagas=n.sagas)
                     for n in e.numeros],
            archivos=[ArchivoPorRevisar(
                id=str(f.id), nombre=f.file_name, ruta=f.file_path, numero=f.issue_number, formato=_texto(f.format),
                falta_en_disco=bool(f.is_missing),
                procedencia="registrada" if _operacion_del_vinculo(f.metadata_, f.series_id_de_issue) else "desconocida")
                for f in e.archivos],
            deseados=[DeseoRetirado(id=str(w.id), numero=w.numero, estado=_texto(w.status), origen=_texto(w.origen),
                                    por_numero=w.issue_id is not None) for w in e.deseados],
            alias=len(e.alias), sagas=len(e.sagas),
            aviso_disco=AVISO_DISCO, aviso_despues=AVISO_DESPUES, token=token)

    async def confirmar(self, token: str) -> ResultadoRetirada:
        firmado = verificar_token_retirada(token, self._secret, ahora=self._ahora, ignorar_caducidad=True)
        if firmado is None:
            raise TokenInvalidoError("El token no es válido: repite la vista previa.")
        vigente = verificar_token_retirada(token, self._secret, ahora=self._ahora) is not None
        try:
            return await self._en_transaccion(firmado, vigente)
        except BaseException as e:
            with contextlib.suppress(Exception):
                await self._db.rollback()
            if self._commit_pedido and isinstance(e, Exception):
                raise ResultadoInciertoError("No se pudo confirmar si se retiró la serie.") from None
            if isinstance(e, DBAPIError) and _es_interbloqueo(e):
                raise ConflictoDeBloqueoError("Otra operación coincidió; repite la confirmación.") from None
            raise

    async def _en_transaccion(self, firmado: RetiradaFirmada, vigente: bool) -> ResultadoRetirada:
        db = self._db
        series_id = UUID(firmado.series_id)

        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
                         {"k": _ESPACIO_OPERACION, "o": firmado.operacion})

        previo = (await db.execute(select(VinculacionOperacion.resultado).where(
            VinculacionOperacion.operacion_id == UUID(firmado.operacion)))).scalar_one_or_none()
        if previo is not None:
            if (previo or {}).get("tipo") == TIPO_INFORME:
                return await self._ya_retirada(firmado, previo)
            raise RetiradaError("El identificador de esta operación ya está ocupado por otro informe.")
        if not vigente:
            firma = firmado.caduca - TTL_SEGUNDOS
            ahora = self._ahora if self._ahora is not None else time.time()
            puede = ahora >= firma + RETENCION_HORAS * 3600
            raise TokenCaducadoError(MENSAJE_CADUCADO_SIN_INFORME if puede else MENSAJE_CADUCADO_SIN_APLICAR,
                                     puede_haberse_aplicado=puede)

        serie = (await db.execute(select(Series).where(Series.id == series_id).with_for_update())).scalar_one_or_none()
        if serie is None:
            return await self._omitido(firmado, "serie_inexistente", titulo=None)

        await self._bloquear(series_id)
        if self._gancho_con_filas_bloqueadas is not None:
            await self._gancho_con_filas_bloqueadas()

        e = await self._leer_estado(serie)
        huella = huella_de_estado(estado_canonico(e.serie, e.alias, e.numeros, e.archivos, e.deseados, e.vivas, e.sagas))
        if huella != firmado.huella:
            return await self._omitido(firmado, "cambio_desde_la_vista_previa", titulo=serie.title)
        if bloqueos_de(e.deseados, e.vivas):
            return await self._omitido(firmado, "en_curso", titulo=serie.title)

        fecha = self._fecha()
        informe = self._informe(firmado, fecha, e)
        try:
            for f in e.archivos:
                await aplicar_desvinculacion(
                    db, file_id=f.id, issue_id=f.issue_id, vinculo=procedencia_de(f.metadata_, f.series_id_de_issue),
                    metadata_=f.metadata_, metadata_source=f.metadata_source, issue_numero=f.issue_number,
                    issue_formato=_texto(f.format), serie_id=str(series_id), operacion_id=firmado.operacion, fecha=fecha)
            if e.deseados:
                await db.execute(delete(Wishlist).where(Wishlist.id.in_([w.id for w in e.deseados]))
                                 .execution_options(synchronize_session=False))
            await db.execute(delete(Series).where(Series.id == series_id)
                             .execution_options(synchronize_session=False))
            db.add(VinculacionOperacion(operacion_id=UUID(firmado.operacion), series_id=series_id, resultado=informe,
                                        token_hasta=datetime.fromtimestamp(firmado.caduca, UTC)))
            await db.flush()
            await self._purgar()
        except IntegrityError as exc:
            await db.rollback()
            if conflicto_por_operacion_viva(exc):
                return self._resultado_omitido(firmado, "en_curso", titulo=serie.title)
            raise
        resultado = self._resultado_informe(firmado, informe, [
            ArchivoResultado(id=str(f.id), nombre=f.file_name, numero=f.issue_number) for f in e.archivos])
        self._commit_pedido = True
        await db.commit()
        return resultado

    async def _bloquear(self, series_id: UUID) -> None:
        db = self._db
        numeros = select(Issue.id).where(Issue.series_id == series_id)
        await db.execute(select(File.id).where(File.issue_id.in_(numeros))
                         .with_for_update(of=File).order_by(File.id))
        await db.execute(numeros.with_for_update().order_by(Issue.id))
        await db.execute(
            select(Wishlist.id).where(or_(Wishlist.series_id == series_id, Wishlist.issue_id.in_(numeros)))
            .with_for_update().order_by(Wishlist.id))

    def _informe(self, firmado: RetiradaFirmada, fecha: str, e) -> dict:
        serie = e.serie
        return {
            "version": VERSION_RESULTADO, "tipo": TIPO_INFORME, "operacion_id": firmado.operacion, "fecha": fecha,
            "serie": {"id": str(serie.id), "titulo": serie.title, "tradicion": _texto(serie.tradition),
                      "anio_inicio": serie.start_year, "anio_fin": serie.end_year, "total": serie.total_issues,
                      "politica": _texto(serie.wishlist_policy or WishlistPolicy.NONE)},
            "numeros": [{"id": str(n.id), "numero": n.issue_number, "volumen": n.volume, "formato": _texto(n.format),
                         "archivos": n.archivos, "lecturas": n.lecturas, "deseados": n.deseados, "sagas": n.sagas}
                        for n in e.numeros],
            "archivos": [{"id": str(f.id), "issue_id": str(f.issue_id), "numero": f.issue_number,
                          "formato": _texto(f.format),
                          "procedencia": "registrada" if _operacion_del_vinculo(f.metadata_, f.series_id_de_issue)
                                         else "desconocida"} for f in e.archivos],
            "deseados": [{"id": str(w.id), "issue_id": str(w.issue_id) if w.issue_id is not None else None,
                          "numero": w.numero, "estado": _texto(w.status), "origen": _texto(w.origen)} for w in e.deseados],
            "sagas": [[str(s.story_arc_id), str(s.issue_id)] for s in e.sagas],
            "totales": {"numeros": len(e.numeros), "archivos": len(e.archivos), "deseados": len(e.deseados),
                        "alias": len(e.alias), "sagas": len(e.sagas)},
        }

    def _resultado_informe(self, firmado: RetiradaFirmada, informe: dict, archivos: list[ArchivoResultado],
                           resultado: str = "retirada",
                           mensaje: str | None = None) -> ResultadoRetirada:
        return ResultadoRetirada(
            version=VERSION_RESULTADO, operacion_id=firmado.operacion, series_id=firmado.series_id,
            titulo=(informe.get("serie") or {}).get("titulo"), resultado=resultado, motivo=None,
            mensaje=mensaje or f"Listo: «{(informe.get('serie') or {}).get('titulo')}» ya no está en tu biblioteca. "
                              "Los archivos siguen en el disco, en «Por revisar».",
            fecha=informe.get("fecha"), totales=informe.get("totales", {}), archivos=archivos)

    async def _purgar(self) -> None:
        await self._db.execute(text(
            "DELETE FROM vinculacion_operaciones WHERE operacion_id IN ("
            " SELECT operacion_id FROM vinculacion_operaciones"
            " WHERE resultado ->> 'tipo' = :tipo AND creada < now() - make_interval(hours => :h)"
            "   AND token_hasta < now()"
            " ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)"),
            {"tipo": TIPO_INFORME, "h": RETENCION_HORAS, "n": LOTE_DE_PURGA})

    def _resultado_omitido(self, firmado: RetiradaFirmada, motivo: str, *, titulo: str | None) -> ResultadoRetirada:
        return ResultadoRetirada(
            version=VERSION_RESULTADO, operacion_id=firmado.operacion, series_id=firmado.series_id, titulo=titulo,
            resultado="omitido", motivo=motivo, mensaje=MENSAJES[motivo], fecha=None,
            totales={}, archivos=[])

    async def _omitir(self, firmado: RetiradaFirmada, motivo: str, *, titulo: str | None) -> ResultadoRetirada:
        await self._db.commit()
        return self._resultado_omitido(firmado, motivo, titulo=titulo)

    async def _ya_retirada(self, firmado: RetiradaFirmada, informe: dict) -> ResultadoRetirada:
        ids = [a["id"] for a in (informe.get("archivos") or []) if isinstance(a, dict) and a.get("id")]
        nombres: dict[str, str] = {}
        if ids:
            filas = (await self._db.execute(
                select(File.id, File.file_name).where(File.id.in_([UUID(i) for i in ids])))).all()
            nombres = {str(i): n for i, n in filas}
        await self._db.commit()
        archivos = [ArchivoResultado(id=str(a["id"]), nombre=nombres.get(str(a["id"])),
                                     numero=a.get("numero") if isinstance(a.get("numero"), str) else None)
                    for a in (informe.get("archivos") or []) if isinstance(a, dict) and a.get("id")]
        return self._resultado_informe(
            firmado, informe, archivos, resultado="ya_retirada",
            mensaje="Ya estaba retirada: la serie no está en tu biblioteca. No se ha cambiado nada más.")

    def _fecha(self) -> str:
        t = self._ahora if self._ahora is not None else datetime.now(UTC).timestamp()
        return datetime.fromtimestamp(t, UTC).isoformat()
