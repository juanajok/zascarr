# ruff: noqa: E501
"""Vincular en su sitio (rebanada 2d): ejecuta lo que enseñó y firmó la vista previa, SIN mover nada.

Contrato definitivo: `docs/design/rebanada-2-elegir-serie-y-vincular.md` («Contrato técnico de 2d») y ADR 0007.
Recibe SOLO el token. Hace, en UNA transacción: volver a comprobar todo, vincular lo que se pueda, omitir con su
motivo lo que no (impedimentos PREVISTOS) y guardar el informe INMUTABLE de la operación. Cualquier fallo
inesperado revierte todo el intento: ni vínculos, ni `Issue`s, ni informe.

Lo que NO hace: no mueve, copia, renombra ni borra ficheros; no lee su contenido ni calcula hashes (solo `stat`);
no usa la red; no aprende alias; no desvincula; no reasigna jamás un archivo ya vinculado a otra serie o número.

Orden de bloqueos (el mismo que el alta y su deshacer): operación › [título] › serie (`FOR SHARE`) › archivos
(`FOR UPDATE`, por id) › claves `(serie, número)` en orden › filas de `Issue` (`FOR UPDATE`).
Un interbloqueo detectado por Postgres es un fallo inesperado más: rollback completo y `503`.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionOperacion,
    File,
    Issue,
    IssueFormat,
    Series,
    VinculacionOperacion,
)
from zascarr.services.tokens_revision import (
    ArchivoFirmado,
    VinculacionFirmada,
    clave_de_numero,
    verificar_token_vinculacion,
)
from zascarr.services.vinculacion_previa import _comprobar_origenes

VERSION_RESULTADO = 1
#: Retención del informe: 24 h Y token caducado (lo que tarde más). Purga acotada, solo de esta tabla.
RETENCION_HORAS = 24
LOTE_DE_PURGA = 100
_ESPACIO_OPERACION = "vinc_op:"
_ESPACIO_NUMERO = "vinc_num:"

#: Impedimentos PREVISTOS: el archivo se omite con este código y el resto se confirma junto.
MOTIVOS = ("archivo_inexistente", "descartado", "ya_vinculado_a_otro", "en_curso", "origen_no_encontrado",
           "origen_no_verificable", "cambio_desde_la_vista_previa", "colision_de_edicion", "numero_ambiguo",
           "numero_ya_existe")


# ── Errores (el router los traduce) ──────────────────────────────────────────────────────────────

class VinculacionError(Exception):
    codigo = "vinculacion_error"


class TokenInvalidoError(VinculacionError):
    codigo = "token_invalido"


class TokenCaducadoError(VinculacionError):
    codigo = "token_caducado"


class SerieYaNoExisteError(VinculacionError):
    codigo = "la_serie_ya_no_existe"


class ResultadoInciertoError(VinculacionError):
    """Falló algo DESPUÉS de pedir el `commit`: no se sabe si la vinculación se aplicó. Repetir el mismo token lo
    resuelve (si se aplicó, devuelve el mismo informe; si no, la aplica). Nunca se anuncia «no se ha cambiado nada»."""
    codigo = "resultado_incierto"


class ConflictoDeBloqueoError(VinculacionError):
    """Postgres detectó un interbloqueo o un fallo de serialización: esta transacción fue la víctima."""
    codigo = "conflicto_de_bloqueo"


def _es_interbloqueo(e: DBAPIError) -> bool:
    causa = getattr(e.orig, "__cause__", None)
    estado = getattr(causa, "sqlstate", None) or getattr(e.orig, "sqlstate", None) or getattr(e.orig, "pgcode", None)
    return estado in ("40P01", "40001") or "deadlock detected" in str(e.orig).lower()


# ── Contrato de salida ───────────────────────────────────────────────────────────────────────────

class ArchivoResultado(BaseModel):
    id: str
    estado: Literal["vinculado", "ya_estaba_vinculado", "omitido"]
    motivo: str | None
    numero: str
    formato: str
    issue_creado: bool
    conflictos: list[str]


class TotalesResultado(BaseModel):
    vinculados: int
    ya_estaban: int
    omitidos: int
    issues_creados: int
    con_conflicto_incluidos: int


class ResultadoVinculacion(BaseModel):
    """El informe INMUTABLE: es el documento que se guarda y el que devuelve cada repetición."""
    model_config = ConfigDict(populate_by_name=True)

    version: int
    operacion_id: str
    serie_id: str
    fecha: str
    global_: Literal["vinculados_todos", "vinculados_parcialmente", "nada_vinculado"] = Field(alias="global")
    totales: TotalesResultado
    archivos: list[ArchivoResultado]


class Presentacion(BaseModel):
    """Se añade al MOSTRAR el informe; no forma parte de él: puede cambiar sin que cambie el informe."""
    nombres_actuales: dict[str, str]


class RespuestaEjecucion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operacion_id: str
    repetida: bool
    resultado: ResultadoVinculacion
    presentacion: Presentacion


# ── Servicio ─────────────────────────────────────────────────────────────────────────────────────

class VinculacionDeArchivos:
    #: Ganchos de PRUEBAS (se asignan como `staticmethod`): el primero se espera justo después del `stat` y antes de
    #: bloquear nada; el segundo, con las filas de los archivos YA bloqueadas. En producción son `None`.
    _gancho_tras_stat: Callable[[], Awaitable[None]] | None = None
    _gancho_con_filas_bloqueadas: Callable[[], Awaitable[None]] | None = None

    def __init__(self, db: AsyncSession, *, secret: str, biblioteca: Path | str | None = None,
                 estadistica: Callable[[str], os.stat_result] | None = None, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._biblioteca = Path(str(biblioteca or get_settings().library_path))
        self._estadistica = estadistica or (lambda ruta: os.stat(ruta))
        self._ahora = ahora
        self._commit_pedido = False         # tras pedir el `commit` ya no se puede afirmar que no hubo cambios

    async def confirmar(self, token: str) -> RespuestaEjecucion:
        firmado = verificar_token_vinculacion(token, self._secret, ahora=self._ahora, ignorar_caducidad=True)
        if firmado is None:
            raise TokenInvalidoError("El token no es válido: repite la vista previa.")
        vigente = verificar_token_vinculacion(token, self._secret, ahora=self._ahora) is not None
        try:
            return await self._en_transaccion(firmado, vigente)
        except BaseException as e:
            with contextlib.suppress(Exception):
                await self._db.rollback()    # ni vínculos, ni `Issue`s, ni informe a medias (si aún no se confirmó)
            if self._commit_pedido and isinstance(e, Exception):
                raise ResultadoInciertoError("No se pudo confirmar si la vinculación se aplicó.") from None
            if isinstance(e, DBAPIError) and _es_interbloqueo(e):
                raise ConflictoDeBloqueoError("Otra operación coincidió; repite la confirmación.") from None
            raise

    async def _en_transaccion(self, firmado: VinculacionFirmada, vigente: bool) -> RespuestaEjecucion:
        db = self._db
        operacion, serie_id = UUID(firmado.operacion), UUID(firmado.series_id)

        # 1. La operación: doble envío, repetición y reintento se serializan aquí.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :o, 0))"),
                         {"k": _ESPACIO_OPERACION, "o": str(operacion)})

        # 2. Informe ya guardado (token vigente o caducado): se devuelve el MISMO documento, sin ejecutar nada.
        previo = (await db.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == operacion))).scalar_one_or_none()
        if previo is not None:
            doc = previo.resultado
            nombres = await self._nombres([UUID(a["id"]) for a in doc["archivos"]])
            respuesta = self._respuesta(doc, repetida=True, nombres=nombres)
            await db.commit()                      # (solo suelta el candado: aquí no se escribió nada)
            return respuesta
        if not vigente:
            raise TokenCaducadoError("El token caducó: repite la vista previa.")

        # 3. Rutas registradas y `stat` SOBRE ESAS rutas, antes de bloquear filas (sin retener bloqueos durante E/S).
        ids = [UUID(a.id) for a in firmado.archivos]
        rutas_comprobadas = {str(i): r for i, r in (await db.execute(
            select(File.id, File.file_path).where(File.id.in_(ids)))).all()}
        origenes = await asyncio.to_thread(_comprobar_origenes, dict(rutas_comprobadas), self._biblioteca,
                                           self._estadistica)
        if self._gancho_tras_stat is not None:
            await self._gancho_tras_stat()

        # 4. Serie `FOR SHARE` (también al reutilizar números: el deshacer del alta la pide `FOR UPDATE`).
        if (await db.execute(select(Series.id).where(Series.id == serie_id).with_for_update(read=True))).first() is None:
            raise SerieYaNoExisteError("La serie ya no existe: repite la vista previa.")

        # 5. Archivos `FOR UPDATE`, por id; con la fila bloqueada se relee la ruta y se mira la operación viva.
        filas = {str(f.id): f for f in (await db.execute(
            select(File.id, File.file_path, File.issue_id, File.review_dismissed, File.metadata_)
            .where(File.id.in_(ids)).order_by(File.id).with_for_update())).all()}
        en_curso = {str(i) for (i,) in (await db.execute(select(AsignacionOperacion.file_id).where(
            AsignacionOperacion.file_id.in_(ids), AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS)))).all()}

        if self._gancho_con_filas_bloqueadas is not None:
            await self._gancho_con_filas_bloqueadas()

        resultados: dict[str, dict] = {}

        def omitir(a: ArchivoFirmado, motivo: str) -> None:
            resultados[a.id] = self._fila(a, "omitido", motivo)

        pendientes: list[ArchivoFirmado] = []
        for a in firmado.archivos:
            f = filas.get(a.id)
            if f is None:
                omitir(a, "archivo_inexistente")
            elif f.issue_id is not None:
                pendientes.append(a)                    # ya vinculado: se decide con el `Issue` de su número
            elif f.review_dismissed:
                omitir(a, "descartado")
            elif a.id in en_curso:
                omitir(a, "en_curso")
            elif rutas_comprobadas.get(a.id) != f.file_path:
                omitir(a, "cambio_desde_la_vista_previa")       # la ruta cambió tras el `stat`: no vale su huella
            else:
                o = origenes.get(a.id)
                if o is None or o.estado == "no_encontrado":
                    omitir(a, "origen_no_encontrado")
                elif o.estado == "no_verificable":
                    omitir(a, "origen_no_verificable")
                elif (o.tamano, o.mtime_ns) != (a.tamano, a.mtime_ns):
                    omitir(a, "cambio_desde_la_vista_previa")
                else:
                    pendientes.append(a)

        # 6. Cada clave `(serie, número)`, sin distinguir mayúsculas: candado consultivo EN ORDEN, y con él tomado se
        #    consulta el `Issue` (sin filtrar por volumen), se bloquea la fila y se vuelve a contar su ocupación.
        por_clave = {clave_de_numero(a.numero): a for a in pendientes}
        claves = sorted(por_clave)
        for k in claves:
            await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || :s || ':' || :n, 0))"),
                             {"k": _ESPACIO_NUMERO, "s": str(serie_id), "n": k})
        for k in claves:
            await self._decidir(por_clave[k], k, filas, serie_id, operacion, resultados)

        # 7. El informe, inmutable, en la MISMA transacción que los vínculos (y la purga acotada de los viejos).
        doc = self._documento(firmado, operacion, resultados)
        db.add(VinculacionOperacion(operacion_id=operacion, series_id=serie_id, resultado=doc,
                                    token_hasta=datetime.fromtimestamp(firmado.caduca, UTC)))
        await db.flush()
        await self._purgar()
        # La RESPUESTA entera (presentación incluida) se prepara y valida ANTES del commit: si falla, todavía se
        # revierte todo. El `commit` es lo último que se hace; un fallo desde que se pide ya no puede decir «nada».
        nombres = await self._nombres(ids)
        respuesta = self._respuesta(doc, repetida=False, nombres=nombres)
        self._commit_pedido = True
        await db.commit()
        return respuesta

    # ── Decisión por clave ───────────────────────────────────────────────────────────────────────

    async def _decidir(self, a: ArchivoFirmado, clave: str, filas, serie_id: UUID, operacion: UUID,
                       resultados: dict[str, dict]) -> None:
        db = self._db
        f = filas[a.id]
        issues = await self._issues_de(serie_id, clave)
        if len(issues) > 1:
            resultados[a.id] = self._fila(a, "omitido", "numero_ambiguo")       # no se adivina cuál; no se toca ninguno
            return
        creado = False
        if not issues:
            if f.issue_id is not None:
                resultados[a.id] = self._fila(a, "omitido", "ya_vinculado_a_otro")
                return
            nuevo = (await db.execute(
                pg_insert(Issue).values(series_id=serie_id, issue_number=a.numero, volume=1,
                                        format=IssueFormat(a.formato), locked_fields=["series_id", "issue_number"])
                .on_conflict_do_nothing(index_elements=["series_id", "issue_number", "volume"])
                .returning(Issue.id))).scalar_one_or_none()
            if nuevo is None:                              # otro escritor lo creó entre la consulta y el INSERT
                issues = await self._issues_de(serie_id, clave)
                if len(issues) != 1:
                    raise RuntimeError("el Issue debería existir tras el conflicto")
            else:
                issues, creado = [(nuevo, a.numero, IssueFormat(a.formato))], True
        issue_id, _, formato = issues[0]
        if f.issue_id == issue_id:
            resultados[a.id] = self._fila(a, "ya_estaba_vinculado", None)
            return
        if f.issue_id is not None:
            resultados[a.id] = self._fila(a, "omitido", "ya_vinculado_a_otro")    # NUNCA se reasigna
            return
        if (formato or IssueFormat.SINGLE_ISSUE).value != a.formato:
            resultados[a.id] = self._fila(a, "omitido", "colision_de_edicion")
            return
        if not creado:
            ocupacion = (await db.execute(select(func.count()).select_from(File).where(File.issue_id == issue_id))).scalar_one()
            if ocupacion:
                resultados[a.id] = self._fila(a, "omitido", "numero_ya_existe")
                return
        await self._vincular_archivo(a, f, issue_id, creado, serie_id, operacion)
        resultados[a.id] = self._fila(a, "vinculado", None, creado)

    async def _issues_de(self, serie_id: UUID, clave: str) -> list[tuple]:
        """Los `Issue` de `(serie, número)` sin distinguir mayúsculas NI filtrar por volumen (los NULL incluidos),
        con la fila bloqueada. Más de uno = ambiguo."""
        return list((await self._db.execute(
            select(Issue.id, Issue.issue_number, Issue.format)
            .where(Issue.series_id == serie_id, func.lower(Issue.issue_number) == clave)
            .order_by(Issue.id).with_for_update())).all())

    async def _vincular_archivo(self, a: ArchivoFirmado, f, issue_id, creado: bool, serie_id: UUID, operacion: UUID) -> None:
        """Los efectos de BD de `AsignacionService._confirmar` MENOS la ruta: `issue_id`, `metadata_source='manual'`
        y la procedencia en `metadata.vinculo` (fusión JSONB, nunca sustituir el objeto). `file_path` y `file_name`
        no se tocan."""
        meta = f.metadata_ or {}
        vinculo = {
            "version": 1, "operacion_id": str(operacion), "fecha": self._fecha(), "serie_id": str(serie_id),
            "numero": a.numero, "formato": a.formato, "issue_creado": creado, "conflictos": list(a.conflictos),
            "previo": {"match_status": meta.get("match_status"), "review_motivo": meta.get("review_motivo")},
        }
        r = await self._db.execute(text(
            "UPDATE files SET issue_id = :i, metadata_source = 'manual', "
            "metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('vinculo', CAST(:v AS jsonb)) "
            "WHERE id = :f AND issue_id IS NULL"),
            {"i": issue_id, "v": json.dumps(vinculo, ensure_ascii=False), "f": a.id})
        if r.rowcount != 1:
            raise RuntimeError("la fila bloqueada no se pudo vincular")

    # ── Informe ──────────────────────────────────────────────────────────────────────────────────

    def _fecha(self) -> str:
        t = self._ahora if self._ahora is not None else datetime.now(UTC).timestamp()
        return datetime.fromtimestamp(t, UTC).isoformat()

    @staticmethod
    def _fila(a: ArchivoFirmado, estado: str, motivo: str | None, issue_creado: bool = False) -> dict:
        return {"id": a.id, "estado": estado, "motivo": motivo, "numero": a.numero, "formato": a.formato,
                "issue_creado": issue_creado, "conflictos": list(a.conflictos)}

    def _documento(self, firmado: VinculacionFirmada, operacion: UUID, resultados: dict[str, dict]) -> dict:
        archivos = [resultados[a.id] for a in firmado.archivos]
        c = Counter(f["estado"] for f in archivos)
        ok = c["vinculado"] + c["ya_estaba_vinculado"]
        global_ = ("nada_vinculado" if ok == 0 else "vinculados_todos" if c["omitido"] == 0 else "vinculados_parcialmente")
        return {
            "version": VERSION_RESULTADO, "operacion_id": str(operacion), "serie_id": firmado.series_id,
            "fecha": self._fecha(), "global": global_,
            "totales": {"vinculados": c["vinculado"], "ya_estaban": c["ya_estaba_vinculado"], "omitidos": c["omitido"],
                        "issues_creados": sum(1 for f in archivos if f["issue_creado"]),
                        "con_conflicto_incluidos": sum(1 for f in archivos if f["estado"] == "vinculado" and f["conflictos"])},
            "archivos": archivos,
        }

    @staticmethod
    def _respuesta(doc: dict, *, repetida: bool, nombres: dict[str, str]) -> RespuestaEjecucion:
        return RespuestaEjecucion(
            operacion_id=doc["operacion_id"], repetida=repetida, resultado=ResultadoVinculacion.model_validate(doc),
            presentacion=Presentacion(nombres_actuales=nombres))

    async def _nombres(self, ids: list[UUID]) -> dict[str, str]:
        """Presentación: el nombre ACTUAL de cada archivo que aún exista. No forma parte del informe."""
        filas = (await self._db.execute(select(File.id, File.file_name).where(File.id.in_(ids)))).all()
        return {str(i): n for i, n in filas}

    async def _purgar(self) -> None:
        """Borra, de forma ACOTADA, informes con las dos condiciones (creados hace más de 24 h Y con el token ya
        caducado). Solo toca `vinculacion_operaciones`: nunca series, números ni archivos."""
        await self._db.execute(text(
            "DELETE FROM vinculacion_operaciones WHERE operacion_id IN ("
            " SELECT operacion_id FROM vinculacion_operaciones"
            " WHERE creada < now() - make_interval(hours => :h) AND token_hasta < now()"
            " ORDER BY creada LIMIT :n FOR UPDATE SKIP LOCKED)"), {"h": RETENCION_HORAS, "n": LOTE_DE_PURGA})
