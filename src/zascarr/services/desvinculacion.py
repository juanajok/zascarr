# ruff: noqa: E501
"""Deshacer la vinculación de UN archivo (BL-R1a, #253): vista previa de solo lectura y confirmación en una transacción.

Contrato: `docs/design/bl-r1-deshacer-vinculacion.md` (§3) y ADR 0014. Decisiones del PO (2026-10-20): D1 el número que creó la
vinculación **se conserva siempre**; D8 `metadata_source` vuelve a lo que había si consta (vínculos nuevos) y, si no, a `NULL`;
D9 solo se deshacen los vínculos de «vincular en su sitio» (los que llevan procedencia en `metadata.vinculo`).

Qué hace la confirmación (recibe SOLO el token, una transacción): `issue_id` nulo; **quita** `metadata.vinculo` y **añade** su
procedencia íntegra a `metadata.vinculo_historial` con `deshecho:{operacion_id, fecha}`; `match_status='unsorted'` y
`review_dismissed=false` (el contrato actual de «Por revisar»). Todo por fusión JSONB, nunca sustituyendo `metadata`.
El comprobante duradero es esa entrada del historial: no hay tabla nueva ni migración (el informe de la vinculación,
`vinculacion_operaciones`, es inmutable por trigger desde la 0019).

Lo que NO hace: no toca el fichero ni su ruta, nombre, tamaño o hash; no toca el `Issue` (D1); no borra la fila; no usa la red;
no lee el contenido de nada; no vuelve a vincular (es otra operación, con su propia vista previa y confirmación).

Orden de bloqueos (el mismo que el alta y la vinculación): operación › serie (`FOR SHARE`) › archivo (`FOR UPDATE`) › issue
(`FOR SHARE`). Un interbloqueo detectado por Postgres es un fallo inesperado más: rollback completo y `503`.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionOperacion,
    File,
    Issue,
    ReadingProgress,
    Series,
    Wishlist,
    WishlistStatus,
)
from zascarr.services.tokens_revision import (
    DesvinculacionFirmada,
    crear_token_desvinculacion,
    verificar_token_desvinculacion,
)
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
    VinculacionError,
    _es_interbloqueo,
)

VERSION_RESULTADO = 1
_ESPACIO_OPERACION = "desv_op:"

#: Bloqueos de la vista previa y motivos de `omitido` en la confirmación (códigos estables; el texto es para la persona).
MENSAJES = {
    "no_vinculado": "Este archivo no está vinculado a ningún número: no hay nada que deshacer.",
    "en_curso": "Ahora mismo ZascArr está trabajando con este archivo. Prueba de nuevo en unos minutos.",
    "archivo_inexistente": "El archivo ya no está registrado en ZascArr.",
    "sin_procedencia": "Este archivo no se vinculó desde «Pendientes por carpeta» (o fue antes de que ZascArr guardara cómo), así "
                       "que no se puede desvincular desde aquí.",
    "cambio_desde_la_vista_previa": "El archivo ha cambiado desde que lo revisaste. No se ha deshecho nada: abre de nuevo la vista previa.",
}
AVISO_REVINCULAR = (
    "Deshacer solo devuelve el archivo a «Por revisar»: el archivo, su carpeta y el número siguen donde estaban. Volver a "
    "vincularlo es otra operación aparte, con su propia vista previa; puede cancelarse o fallar, y entonces el archivo "
    "seguirá en «Por revisar».")
MENSAJE_CADUCADO = ("El token caducó y esta operación no llegó a aplicarse: no hay cambios. Repite la vista previa.")


# ── Errores (el router los traduce; los comunes se reutilizan de la vinculación) ─────────────────

class ArchivoInexistenteError(VinculacionError):
    codigo = "archivo_inexistente"


# ── Contrato de salida ───────────────────────────────────────────────────────────────────────────

class Bloqueo(BaseModel):
    codigo: str
    mensaje: str


class ArchivoConservado(BaseModel):
    """Lo que NO cambia: la fila no se borra y el fichero no se toca."""
    ruta: str
    nombre: str
    tamano: int | None
    sha256: str | None
    falta_en_disco: bool


class NumeroAfectado(BaseModel):
    serie_id: str
    serie_titulo: str
    numero: str | None
    formato: str
    creado_por_la_vinculacion: bool
    se_queda_sin_archivos: bool
    otros_archivos: int
    lecturas: int
    deseados: int
    deseados_abiertos: int


class VistaPreviaDesvinculacion(BaseModel):
    file_id: str
    puede_deshacer: bool
    bloqueo: Bloqueo | None
    archivo: ArchivoConservado
    numero: NumeroAfectado | None
    vinculado_el: str | None
    aviso: str
    token: str | None


class ResultadoDesvinculacion(BaseModel):
    """`deshecho` | `ya_deshecho` (repetición: el mismo resultado, sin escribir) | `omitido` con su motivo."""
    version: int
    operacion_id: str
    file_id: str
    resultado: Literal["deshecho", "ya_deshecho", "omitido"]
    motivo: str | None
    mensaje: str
    serie_id: str | None
    numero: str | None
    fecha: str | None


# ── Ayudas ───────────────────────────────────────────────────────────────────────────────────────

def huella_de(ruta: str, tamano: int | None, sha256: str | None) -> str:
    """La huella del vínculo `(file_path, file_size_bytes, sha256_hash)`: lo que prueba que es el MISMO archivo que se vio."""
    return hashlib.sha256(json.dumps([ruta, tamano, sha256], ensure_ascii=False).encode()).hexdigest()


def _uuid(v: object) -> str | None:
    if not isinstance(v, str):
        return None
    try:
        return str(UUID(v))
    except ValueError:
        return None


def _vinculo_valido(meta: dict | None) -> dict | None:
    """El `metadata.vinculo` si tiene la procedencia mínima (operación y serie), o `None`: sin él no hay D9."""
    v = (meta or {}).get("vinculo")
    if isinstance(v, dict) and _uuid(v.get("operacion_id")) and _uuid(v.get("serie_id")):
        return v
    return None


def _entrada_de(meta: dict | None, operacion: str) -> dict | None:
    """La entrada de `vinculo_historial` que esta operación dejó (su comprobante), o `None`."""
    historial = (meta or {}).get("vinculo_historial")
    if not isinstance(historial, list):
        return None
    for e in historial:
        d = e.get("deshecho") if isinstance(e, dict) else None
        if isinstance(d, dict) and d.get("operacion_id") == operacion:
            return e
    return None


async def _asignacion_viva(db: AsyncSession, file_id: UUID) -> bool:
    return (await db.execute(select(AsignacionOperacion.id).where(
        AsignacionOperacion.file_id == file_id, AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS)).limit(1))
    ).first() is not None


# ── Servicio ─────────────────────────────────────────────────────────────────────────────────────

class DesvinculacionDeArchivo:
    #: Gancho de PRUEBAS (se asigna como `staticmethod`): se espera con las filas YA bloqueadas. En producción es `None`.
    _gancho_con_filas_bloqueadas = None

    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._ahora = ahora
        self._commit_pedido = False         # tras pedir el `commit` ya no se puede afirmar que no hubo cambios

    # ── Vista previa (solo lectura) ──────────────────────────────────────────────────────────────

    async def previsualizar(self, file_id: UUID) -> VistaPreviaDesvinculacion:
        """Qué pasaría si se deshiciera la vinculación de este archivo, SIN hacerlo: solo `SELECT`, sin candados, sin `commit`,
        sin `stat` ni lectura de ficheros. Emite el token `desvincular` solo si se puede deshacer."""
        db = self._db
        f = (await db.execute(select(
            File.id, File.file_path, File.file_name, File.file_size_bytes, File.sha256_hash, File.issue_id,
            File.is_missing, File.metadata_).where(File.id == file_id))).first()
        if f is None:
            raise ArchivoInexistenteError(MENSAJES["archivo_inexistente"])
        archivo = ArchivoConservado(ruta=f.file_path, nombre=f.file_name, tamano=f.file_size_bytes, sha256=f.sha256_hash,
                                    falta_en_disco=bool(f.is_missing))
        vinculo = _vinculo_valido(f.metadata_)
        numero = None
        bloqueo = None
        issue = None
        if f.issue_id is not None:
            issue = (await db.execute(select(Issue.id, Issue.series_id, Issue.issue_number, Issue.format)
                                      .where(Issue.id == f.issue_id))).first()
            serie = None if issue is None else (await db.execute(
                select(Series.title).where(Series.id == issue.series_id))).scalar_one_or_none()
            if issue is not None and serie is not None:
                numero = await self._numero_afectado(f, issue, serie, vinculo)

        if f.issue_id is None:
            bloqueo = "no_vinculado"
        elif await _asignacion_viva(db, file_id):
            bloqueo = "en_curso"
        elif vinculo is None or issue is None or str(issue.series_id) != _uuid(vinculo["serie_id"]):
            bloqueo = "sin_procedencia"      # D9: sin procedencia verificable (otro camino, antiguo o incoherente)

        token = None
        if bloqueo is None:
            assert issue is not None and vinculo is not None
            token = crear_token_desvinculacion(DesvinculacionFirmada(
                file_id=str(file_id), issue_id=str(issue.id), series_id=str(issue.series_id),
                vinculo_operacion=_uuid(vinculo["operacion_id"]) or "",
                huella=huella_de(f.file_path, f.file_size_bytes, f.sha256_hash), operacion=str(uuid4())),
                self._secret, ahora=self._ahora)
        return VistaPreviaDesvinculacion(
            file_id=str(file_id), puede_deshacer=bloqueo is None,
            bloqueo=None if bloqueo is None else Bloqueo(codigo=bloqueo, mensaje=MENSAJES[bloqueo]),
            archivo=archivo, numero=numero,
            vinculado_el=vinculo.get("fecha") if vinculo and isinstance(vinculo.get("fecha"), str) else None,
            aviso=AVISO_REVINCULAR, token=token)

    async def _numero_afectado(self, f, issue, serie_titulo: str, vinculo: dict | None) -> NumeroAfectado:
        db = self._db
        otros = (await db.execute(select(func.count()).select_from(File).where(
            File.issue_id == issue.id, File.id != f.id))).scalar_one()
        lecturas = (await db.execute(select(func.count()).select_from(ReadingProgress).where(
            ReadingProgress.issue_id == issue.id))).scalar_one()
        deseados = (await db.execute(select(func.count()).select_from(Wishlist).where(
            Wishlist.issue_id == issue.id))).scalar_one()
        abiertos = (await db.execute(select(func.count()).select_from(Wishlist).where(
            Wishlist.issue_id == issue.id,
            Wishlist.status.notin_([WishlistStatus.IMPORTED, WishlistStatus.DOWNLOADED, WishlistStatus.RETIRADO])))).scalar_one()
        return NumeroAfectado(
            serie_id=str(issue.series_id), serie_titulo=serie_titulo, numero=issue.issue_number, formato=issue.format.value,
            creado_por_la_vinculacion=bool(vinculo and vinculo.get("issue_creado") is True),
            se_queda_sin_archivos=otros == 0, otros_archivos=otros, lecturas=lecturas, deseados=deseados,
            deseados_abiertos=abiertos)

    # ── Confirmación ─────────────────────────────────────────────────────────────────────────────

    async def confirmar(self, token: str) -> ResultadoDesvinculacion:
        firmado = verificar_token_desvinculacion(token, self._secret, ahora=self._ahora, ignorar_caducidad=True)
        if firmado is None:
            raise TokenInvalidoError("El token no es válido: repite la vista previa.")
        vigente = verificar_token_desvinculacion(token, self._secret, ahora=self._ahora) is not None
        try:
            return await self._en_transaccion(firmado, vigente)
        except BaseException as e:
            with contextlib.suppress(Exception):
                await self._db.rollback()
            if self._commit_pedido and isinstance(e, Exception):
                raise ResultadoInciertoError("No se pudo confirmar si se deshizo la vinculación.") from None
            if isinstance(e, DBAPIError) and _es_interbloqueo(e):
                raise ConflictoDeBloqueoError("Otra operación coincidió; repite la confirmación.") from None
            raise

    async def _en_transaccion(self, firmado: DesvinculacionFirmada, vigente: bool) -> ResultadoDesvinculacion:
        db = self._db
        file_id = UUID(firmado.file_id)

        # 1. La operación: doble envío, repetición y reintento se serializan aquí.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
                         {"k": _ESPACIO_OPERACION, "o": firmado.operacion})

        # 2. ¿Ya se deshizo con esta operación? El comprobante es la entrada del historial: se devuelve el MISMO resultado,
        #    sin escribir (también con el token caducado: así un fallo incierto se resuelve releyendo la fila).
        previo = (await db.execute(select(File.metadata_).where(File.id == file_id))).first()
        if previo is None:
            return await self._omitir(firmado, "archivo_inexistente")
        entrada = _entrada_de(previo.metadata_, firmado.operacion)
        if entrada is not None:
            return await self._ya_deshecho(firmado, entrada)
        if not vigente:
            raise TokenCaducadoError(MENSAJE_CADUCADO, puede_haberse_aplicado=False)

        # 3. Serie `FOR SHARE` (una serie que ya no existe: el vínculo cambió desde la vista previa).
        if (await db.execute(select(Series.id).where(Series.id == UUID(firmado.series_id)).with_for_update(read=True))).first() is None:
            return await self._omitir(firmado, "cambio_desde_la_vista_previa")

        # 4. Archivo `FOR UPDATE`; con la fila bloqueada se vuelve a comprobar TODO.
        f = (await db.execute(select(
            File.id, File.file_path, File.file_size_bytes, File.sha256_hash, File.issue_id, File.metadata_,
            File.metadata_source).where(File.id == file_id).with_for_update())).first()
        if f is None:
            return await self._omitir(firmado, "archivo_inexistente")
        if self._gancho_con_filas_bloqueadas is not None:
            await self._gancho_con_filas_bloqueadas()
        if f.issue_id is None:
            return await self._omitir(firmado, "no_vinculado")
        if await _asignacion_viva(db, file_id):
            return await self._omitir(firmado, "en_curso")
        vinculo = _vinculo_valido(f.metadata_)
        if (str(f.issue_id) != firmado.issue_id or vinculo is None
                or _uuid(vinculo["operacion_id"]) != firmado.vinculo_operacion
                or huella_de(f.file_path, f.file_size_bytes, f.sha256_hash) != firmado.huella):
            return await self._omitir(firmado, "cambio_desde_la_vista_previa")

        # 5. Issue `FOR SHARE` (no puede desaparecer mientras se desvincula).
        if (await db.execute(select(Issue.id).where(Issue.id == f.issue_id).with_for_update(read=True))).first() is None:
            return await self._omitir(firmado, "cambio_desde_la_vista_previa")

        # 6. Una sola sentencia, con el vínculo comprobado en el WHERE. Todo por fusión JSONB.
        fecha = self._fecha()
        previo_vinculo = vinculo.get("previo")
        fuente = previo_vinculo.get("metadata_source") if isinstance(previo_vinculo, dict) else None      # D8
        comprobante = {**vinculo, "deshecho": {"operacion_id": firmado.operacion, "fecha": fecha}}
        r = await db.execute(text(
            "UPDATE files SET issue_id = NULL, review_dismissed = false, metadata_source = CAST(:src AS varchar), "
            "metadata = (coalesce(metadata, '{}'::jsonb) - 'vinculo') || jsonb_build_object("
            " 'match_status', 'unsorted',"
            " 'vinculo_historial', CASE WHEN jsonb_typeof(metadata -> 'vinculo_historial') = 'array'"
            "   THEN metadata -> 'vinculo_historial' ELSE '[]'::jsonb END || jsonb_build_array(CAST(:e AS jsonb))) "
            "WHERE id = :f AND issue_id = :i AND metadata -> 'vinculo' ->> 'operacion_id' = :vop"),
            {"src": fuente if isinstance(fuente, str) else None, "e": json.dumps(comprobante, ensure_ascii=False),
             "f": file_id, "i": f.issue_id, "vop": firmado.vinculo_operacion})
        if r.rowcount != 1:
            raise RuntimeError("la fila bloqueada no se pudo desvincular")

        resultado = ResultadoDesvinculacion(
            version=VERSION_RESULTADO, operacion_id=firmado.operacion, file_id=firmado.file_id, resultado="deshecho",
            motivo=None, mensaje="Listo: el archivo ha vuelto a «Por revisar».", serie_id=firmado.series_id,
            numero=vinculo.get("numero") if isinstance(vinculo.get("numero"), str) else None, fecha=fecha)
        self._commit_pedido = True
        await db.commit()
        return resultado

    # ── Resultados que no escriben ───────────────────────────────────────────────────────────────

    async def _omitir(self, firmado: DesvinculacionFirmada, motivo: str) -> ResultadoDesvinculacion:
        await self._db.commit()          # (solo suelta los candados: aquí no se escribió nada)
        return ResultadoDesvinculacion(
            version=VERSION_RESULTADO, operacion_id=firmado.operacion, file_id=firmado.file_id, resultado="omitido",
            motivo=motivo, mensaje=MENSAJES[motivo], serie_id=None, numero=None, fecha=None)

    async def _ya_deshecho(self, firmado: DesvinculacionFirmada, entrada: dict) -> ResultadoDesvinculacion:
        await self._db.commit()
        d = entrada["deshecho"]
        return ResultadoDesvinculacion(
            version=VERSION_RESULTADO, operacion_id=firmado.operacion, file_id=firmado.file_id, resultado="ya_deshecho",
            motivo=None, mensaje="Ya estaba deshecho: el archivo está en «Por revisar».", serie_id=firmado.series_id,
            numero=entrada.get("numero") if isinstance(entrada.get("numero"), str) else None,
            fecha=d.get("fecha") if isinstance(d.get("fecha"), str) else None)

    def _fecha(self) -> str:
        t = self._ahora if self._ahora is not None else datetime.now(UTC).timestamp()
        return datetime.fromtimestamp(t, UTC).isoformat()

