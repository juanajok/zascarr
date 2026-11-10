# ruff: noqa: E501
"""MIT-M7 (#131-a): correspondencias locales versionadas carpeta → destino.

Una correspondencia referencia una **versión exacta** de una declaración. Si la
declaración cambia o deja de estar activa, la correspondencia queda
desactualizada y no se aplica. `evaluar` es solo lectura: no crea destinos, no
vincula archivos, no mueve nada y no confirma propuestas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    CorrespondenciaContexto,
    DeclaracionCarpeta,
    EstadoEvaluacion,
    EstadoRegla,
    Issue,
    OrigenRegla,
    Series,
    TipoDestino,
    TipoRegistro,
    TipoSignificadoCarpeta,
)
from zascarr.services.declaraciones_carpeta import normalizar_ruta

MAX_VERSIONES = 10000
_SIN_VALOR = object()


class CorrespondenciaError(Exception):
    """Error de negocio con mensaje en español."""


class TipoInvalidoError(CorrespondenciaError):
    pass


class DestinoInvalidoError(CorrespondenciaError):
    pass


class CorrespondenciaNoEncontradaError(CorrespondenciaError):
    pass


class CorrespondenciaRetiradaError(CorrespondenciaError):
    pass


class EvidenciaIncompatibleError(CorrespondenciaError):
    pass


class RegistroInvalidoError(CorrespondenciaError):
    pass


def _tipo_destino(valor: TipoDestino | str) -> TipoDestino:
    try:
        return TipoDestino(valor)
    except (TypeError, ValueError):
        raise TipoInvalidoError("El destino solo puede ser una serie o una publicación.") from None


def _tipo_registro(valor: TipoRegistro | str | None) -> TipoRegistro | None:
    if valor is None:
        return None
    try:
        return TipoRegistro(valor)
    except (TypeError, ValueError):
        raise TipoInvalidoError("El tipo de registro no es válido.") from None


def _origen(valor: OrigenRegla | str) -> OrigenRegla:
    try:
        return OrigenRegla(valor)
    except (TypeError, ValueError):
        raise TipoInvalidoError("El origen no es válido.") from None


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(UTC)


def cubre(raiz: str, incluir_descendientes: bool, carpeta: str) -> bool:
    """Alcance por segmentos: `A` nunca cubre `AB`; sin descendientes, exacto."""
    if carpeta == raiz:
        return True
    return incluir_descendientes and carpeta.startswith(raiz + "/")


@dataclass(frozen=True)
class CorrespondenciaVista:
    id: UUID
    correspondencia_id: UUID
    version: int
    supersedes_id: UUID | None
    declaracion_version_id: UUID
    contexto_raiz: str
    incluir_descendientes: bool
    tipo_de_registro: TipoRegistro | None
    destino_tipo: TipoDestino
    destino_id: UUID
    origen: OrigenRegla
    estado: EstadoRegla
    vigente_desde: datetime
    vigente_hasta: datetime | None

    @classmethod
    def de(cls, fila: CorrespondenciaContexto) -> CorrespondenciaVista:
        return cls(
            id=fila.id, correspondencia_id=fila.correspondencia_id, version=fila.version,
            supersedes_id=fila.supersedes_id,
            declaracion_version_id=fila.declaracion_version_id,
            contexto_raiz=fila.contexto_raiz,
            incluir_descendientes=fila.incluir_descendientes,
            tipo_de_registro=fila.tipo_de_registro, destino_tipo=fila.destino_tipo,
            destino_id=fila.destino_id, origen=fila.origen, estado=fila.estado,
            vigente_desde=fila.vigente_desde, vigente_hasta=fila.vigente_hasta,
        )


@dataclass(frozen=True)
class RegistroContextual:
    tipo: TipoRegistro | str
    carpeta: str
    ruta: str | None = None
    patron_nombre: str | None = None


@dataclass(frozen=True)
class Propuesta:
    correspondencia_id: UUID
    version_de_regla: int
    declaracion_id: UUID
    version_declaracion: int
    destino_tipo: TipoDestino
    destino_id: UUID
    alcance: dict
    origen: OrigenRegla
    precedencia_aplicada: str | None
    evidencia: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoEvaluacion:
    estado: str
    motivo: str
    propuesta: Propuesta | None = None
    correspondencia_id: UUID | None = None
    version_de_regla: int | None = None
    declaracion_id: UUID | None = None
    version_declaracion: int | None = None
    destino_tipo: TipoDestino | None = None
    destino_id: UUID | None = None
    alcance: dict = field(default_factory=dict)
    reglas_involucradas: tuple[dict, ...] = ()
    precedencia_aplicada: str | None = None
    conflicto_visible: tuple[dict, ...] = ()


async def _declaracion(db: AsyncSession, declaracion_version_id: UUID) -> DeclaracionCarpeta:
    decl = await db.get(DeclaracionCarpeta, declaracion_version_id)
    if decl is None:
        raise EvidenciaIncompatibleError("La declaración de esta correspondencia ya no existe.")
    return decl


async def _exigir_declaracion_vigente(db: AsyncSession, decl: DeclaracionCarpeta) -> None:
    actual = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.declaracion_id == decl.declaracion_id,
            DeclaracionCarpeta.vigente_hasta.is_(None),
            DeclaracionCarpeta.estado == EstadoRegla.ACTIVA))).scalar_one_or_none()
    if actual is None or actual.id != decl.id:
        raise EvidenciaIncompatibleError(
            "La declaración de esta correspondencia ya no es la vigente.")


async def _destino(db: AsyncSession, tipo: TipoDestino, destino_id: UUID):
    modelo = Series if tipo is TipoDestino.SERIE else Issue
    return await db.get(modelo, destino_id)


async def _validar_destino(db: AsyncSession, tipo: TipoDestino, destino_id: UUID) -> None:
    if await _destino(db, tipo, destino_id) is None:
        raise DestinoInvalidoError("El destino elegido no existe. Elige una serie o publicación existente.")


async def _crear_fila(db: AsyncSession, *, correspondencia_id: UUID, version: int,
                      supersedes_id: UUID | None, decl: DeclaracionCarpeta,
                      tipo_registro: TipoRegistro | None, destino_tipo: TipoDestino,
                      destino_id: UUID, origen: OrigenRegla, estado: EstadoRegla,
                      ahora: datetime, procedencia: dict,
                      validar_evidencia: bool = True) -> CorrespondenciaContexto:
    if validar_evidencia and decl.tipo_de_significado is TipoSignificadoCarpeta.AUTOR:
        raise EvidenciaIncompatibleError(
            "Una carpeta «Por autor» no puede tener una correspondencia a un destino único.")
    fila = CorrespondenciaContexto(
        id=uuid4(), correspondencia_id=correspondencia_id, version=version,
        supersedes_id=supersedes_id, declaracion_version_id=decl.id,
        contexto_raiz=decl.contexto_raiz,
        incluir_descendientes=decl.incluir_descendientes,
        tipo_de_registro=tipo_registro, destino_tipo=destino_tipo,
        destino_id=destino_id, origen=origen, estado=estado,
        vigente_desde=ahora, vigente_hasta=None, procedencia=dict(procedencia))
    db.add(fila)
    return fila


async def crear(db: AsyncSession, declaracion_version_id: UUID, *,
                destino_tipo: TipoDestino | str, destino_id: UUID,
                tipo_de_registro: TipoRegistro | str | None = None,
                origen: OrigenRegla | str = OrigenRegla.LOCAL,
                procedencia: dict | None = None,
                ahora: datetime | None = None) -> CorrespondenciaVista:
    decl = await _declaracion(db, declaracion_version_id)
    if decl.estado is not EstadoRegla.ACTIVA:
        raise EvidenciaIncompatibleError("La declaración no está activa; no se puede usar para una correspondencia.")
    await _exigir_declaracion_vigente(db, decl)
    tipo = _tipo_destino(destino_tipo)
    tipo_reg = _tipo_registro(tipo_de_registro)
    await _validar_destino(db, tipo, destino_id)
    fila = await _crear_fila(
        db, correspondencia_id=uuid4(), version=1, supersedes_id=None, decl=decl,
        tipo_registro=tipo_reg, destino_tipo=tipo, destino_id=destino_id,
        origen=_origen(origen), estado=EstadoRegla.ACTIVA, ahora=_ahora(ahora),
        procedencia=dict(procedencia or {}))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise CorrespondenciaError("No se ha podido crear la correspondencia.") from exc
    await db.refresh(fila)
    return CorrespondenciaVista.de(fila)


async def _actual(db: AsyncSession, correspondencia_id: UUID) -> CorrespondenciaContexto:
    fila = (await db.execute(
        select(CorrespondenciaContexto).where(
            CorrespondenciaContexto.correspondencia_id == correspondencia_id,
            CorrespondenciaContexto.vigente_hasta.is_(None)).with_for_update())).scalar_one_or_none()
    if fila is None:
        raise CorrespondenciaNoEncontradaError("Esa correspondencia ya no existe.")
    return fila


async def cambiar(db: AsyncSession, correspondencia_id: UUID, *,
                  declaracion_version_id: UUID | None = None,
                  destino_tipo: TipoDestino | str | None = None,
                  destino_id: UUID | None = None,
                  tipo_de_registro: TipoRegistro | str | None | object = _SIN_VALOR,
                  ahora: datetime | None = None) -> CorrespondenciaVista:
    actual = await _actual(db, correspondencia_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise CorrespondenciaRetiradaError("Una correspondencia retirada no se puede cambiar.")
    decl = await _declaracion(db, declaracion_version_id or actual.declaracion_version_id)
    await _exigir_declaracion_vigente(db, decl)
    decl_actual = await db.get(DeclaracionCarpeta, actual.declaracion_version_id)
    if (decl_actual is not None
            and (decl.declaracion_id != decl_actual.declaracion_id
                 or decl.contexto_raiz != decl_actual.contexto_raiz)):
        raise EvidenciaIncompatibleError(
            "La raíz y la identidad de la declaración no se cambian en una correspondencia; crea otra.")
    tipo = _tipo_destino(destino_tipo) if destino_tipo is not None else actual.destino_tipo
    destino = destino_id if destino_id is not None else actual.destino_id
    if tipo_de_registro is _SIN_VALOR:
        tipo_reg = actual.tipo_de_registro
    else:
        tipo_reg = _tipo_registro(tipo_de_registro)
    await _validar_destino(db, tipo, destino)
    sin_cambios = (decl.id == actual.declaracion_version_id and tipo is actual.destino_tipo
                   and destino == actual.destino_id and tipo_reg is actual.tipo_de_registro)
    if sin_cambios:
        return CorrespondenciaVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = await _crear_fila(
        db, correspondencia_id=actual.correspondencia_id, version=actual.version + 1,
        supersedes_id=actual.id, decl=decl, tipo_registro=tipo_reg, destino_tipo=tipo,
        destino_id=destino, origen=actual.origen,
        estado=actual.estado if actual.estado is not EstadoRegla.RETIRADA else EstadoRegla.DESACTIVADA,
        ahora=momento, procedencia=dict(actual.procedencia or {}),
        validar_evidencia=actual.estado is EstadoRegla.ACTIVA)
    await db.commit()
    await db.refresh(nueva)
    return CorrespondenciaVista.de(nueva)


async def desactivar(db: AsyncSession, correspondencia_id: UUID, *, ahora: datetime | None = None) -> CorrespondenciaVista:
    actual = await _actual(db, correspondencia_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise CorrespondenciaRetiradaError("Una correspondencia retirada no se puede desactivar.")
    if actual.estado is EstadoRegla.DESACTIVADA:
        return CorrespondenciaVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    decl = await _declaracion(db, actual.declaracion_version_id)
    nueva = await _crear_fila(
        db, correspondencia_id=actual.correspondencia_id, version=actual.version + 1,
        supersedes_id=actual.id, decl=decl, tipo_registro=actual.tipo_de_registro,
        destino_tipo=actual.destino_tipo, destino_id=actual.destino_id,
        origen=actual.origen, estado=EstadoRegla.DESACTIVADA, ahora=momento,
        procedencia=dict(actual.procedencia or {}), validar_evidencia=False)
    await db.commit()
    await db.refresh(nueva)
    return CorrespondenciaVista.de(nueva)


async def activar(db: AsyncSession, correspondencia_id: UUID, *, ahora: datetime | None = None) -> CorrespondenciaVista:
    actual = await _actual(db, correspondencia_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise CorrespondenciaRetiradaError("Una correspondencia retirada no se puede reactivar.")
    if actual.estado is EstadoRegla.ACTIVA:
        return CorrespondenciaVista.de(actual)
    decl = await _declaracion(db, actual.declaracion_version_id)
    if decl.estado is not EstadoRegla.ACTIVA:
        raise EvidenciaIncompatibleError("La declaración ya no está activa; no se puede reactivar esta correspondencia.")
    await _exigir_declaracion_vigente(db, decl)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = await _crear_fila(
        db, correspondencia_id=actual.correspondencia_id, version=actual.version + 1,
        supersedes_id=actual.id, decl=decl, tipo_registro=actual.tipo_de_registro,
        destino_tipo=actual.destino_tipo, destino_id=actual.destino_id,
        origen=actual.origen, estado=EstadoRegla.ACTIVA, ahora=momento,
        procedencia=dict(actual.procedencia or {}))
    await db.commit()
    await db.refresh(nueva)
    return CorrespondenciaVista.de(nueva)


async def retirar(db: AsyncSession, correspondencia_id: UUID, *, ahora: datetime | None = None) -> CorrespondenciaVista:
    actual = await _actual(db, correspondencia_id)
    if actual.estado is EstadoRegla.RETIRADA:
        return CorrespondenciaVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    decl = await _declaracion(db, actual.declaracion_version_id)
    nueva = await _crear_fila(
        db, correspondencia_id=actual.correspondencia_id, version=actual.version + 1,
        supersedes_id=actual.id, decl=decl, tipo_registro=actual.tipo_de_registro,
        destino_tipo=actual.destino_tipo, destino_id=actual.destino_id,
        origen=actual.origen, estado=EstadoRegla.RETIRADA, ahora=momento,
        procedencia=dict(actual.procedencia or {}), validar_evidencia=False)
    await db.commit()
    await db.refresh(nueva)
    return CorrespondenciaVista.de(nueva)


async def listar(db: AsyncSession, *, origen: OrigenRegla | str | None = None,
                 estado: EstadoRegla | str | None = None,
                 incluir_historial: bool = False) -> list[CorrespondenciaVista]:
    consulta = select(CorrespondenciaContexto)
    if not incluir_historial:
        consulta = consulta.where(CorrespondenciaContexto.vigente_hasta.is_(None))
    if origen is not None:
        consulta = consulta.where(CorrespondenciaContexto.origen == _origen(origen))
    if estado is not None:
        try:
            e = EstadoRegla(estado)
        except (TypeError, ValueError):
            raise TipoInvalidoError("El estado no es válido.") from None
        consulta = consulta.where(CorrespondenciaContexto.estado == e)
    filas = (await db.execute(
        consulta.order_by(CorrespondenciaContexto.contexto_raiz,
                          CorrespondenciaContexto.correspondencia_id,
                          CorrespondenciaContexto.version))).scalars().all()
    return [CorrespondenciaVista.de(f) for f in filas]


async def historial(db: AsyncSession, correspondencia_id: UUID) -> list[CorrespondenciaVista]:
    filas = (await db.execute(
        select(CorrespondenciaContexto)
        .where(CorrespondenciaContexto.correspondencia_id == correspondencia_id)
        .order_by(CorrespondenciaContexto.version))).scalars().all()
    return [CorrespondenciaVista.de(f) for f in filas]


async def _version_actual_declaracion(db: AsyncSession, version_id: UUID) -> DeclaracionCarpeta | None:
    """Versión vigente (o la última) de la declaración estable de una fila."""
    fila = await db.get(DeclaracionCarpeta, version_id)
    if fila is None:
        return None
    actual = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.declaracion_id == fila.declaracion_id,
            DeclaracionCarpeta.vigente_hasta.is_(None)))).scalar_one_or_none()
    if actual is not None:
        return actual
    return (await db.execute(
        select(DeclaracionCarpeta)
        .where(DeclaracionCarpeta.declaracion_id == fila.declaracion_id)
        .order_by(DeclaracionCarpeta.version.desc()).limit(1))).scalar_one_or_none()


def _regla_dict(c: CorrespondenciaContexto) -> dict:
    return {"correspondencia_id": str(c.correspondencia_id), "version": c.version,
            "origen": c.origen.value, "destino_tipo": c.destino_tipo.value,
            "destino_id": str(c.destino_id)}


async def evaluar(db: AsyncSession, registro: RegistroContextual, *,
                  ahora: datetime | None = None,
                  retenida: Propuesta | None = None) -> ResultadoEvaluacion:
    """Evalúa una sola regla aplicable; no escribe ni crea nada.

    `retenida` valida una propuesta guardada contra la identidad y versión
    actuales; si ya no es la vigente, devuelve `regla_desactualizada`.
    """
    if retenida is not None:
        return await validar_propuesta(db, retenida)
    try:
        tipo = TipoRegistro(registro.tipo)
    except (TypeError, ValueError):
        raise RegistroInvalidoError("El tipo de registro no es válido.") from None
    try:
        carpeta = normalizar_ruta(registro.carpeta)
    except Exception as exc:  # noqa: BLE001 — mensaje de negocio
        raise RegistroInvalidoError("La carpeta del registro no es válida.") from exc

    decl_actuales = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.vigente_hasta.is_(None),
            DeclaracionCarpeta.estado == EstadoRegla.ACTIVA))).scalars().all()
    corr_actuales = (await db.execute(
        select(CorrespondenciaContexto).where(
            CorrespondenciaContexto.vigente_hasta.is_(None)))).scalars().all()

    validas: list[tuple[CorrespondenciaContexto, DeclaracionCarpeta]] = []
    desactualizadas: list[CorrespondenciaContexto] = []
    incompatibles: list[CorrespondenciaContexto] = []
    for c in corr_actuales:
        if not cubre(c.contexto_raiz, c.incluir_descendientes, carpeta):
            continue
        if c.tipo_de_registro is not None and c.tipo_de_registro is not tipo:
            continue
        if c.estado is not EstadoRegla.ACTIVA:
            desactualizadas.append(c)
            continue
        decl = await db.get(DeclaracionCarpeta, c.declaracion_version_id)
        if decl is None:
            incompatibles.append(c)
            continue
        if decl.tipo_de_significado is TipoSignificadoCarpeta.AUTOR:
            incompatibles.append(c)
            continue
        if (c.contexto_raiz != decl.contexto_raiz
                or c.incluir_descendientes != decl.incluir_descendientes):
            incompatibles.append(c)
            continue
        actual = next((d for d in decl_actuales if d.declaracion_id == decl.declaracion_id), None)
        if actual is None or actual.id != decl.id:
            desactualizadas.append(c)
            continue
        validas.append((c, decl))

    if not validas:
        if incompatibles and not desactualizadas:
            c = incompatibles[0]
            return ResultadoEvaluacion(
                EstadoEvaluacion.EVIDENCIA_INCOMPATIBLE,
                "La correspondencia no es coherente con su declaración.",
                correspondencia_id=c.correspondencia_id, version_de_regla=c.version,
                destino_tipo=c.destino_tipo, destino_id=c.destino_id,
                reglas_involucradas=(_regla_dict(c),))
        if desactualizadas:
            c = desactualizadas[0]
            decl_actual = await _version_actual_declaracion(db, c.declaracion_version_id)
            return ResultadoEvaluacion(
                EstadoEvaluacion.REGLA_DESACTUALIZADA,
                "La declaración o la propia correspondencia ya no es la vigente.",
                correspondencia_id=c.correspondencia_id, version_de_regla=c.version,
                declaracion_id=decl_actual.declaracion_id if decl_actual else None,
                version_declaracion=(decl_actual.version if decl_actual else None),
                destino_tipo=c.destino_tipo, destino_id=c.destino_id,
                reglas_involucradas=(_regla_dict(c),))
        return ResultadoEvaluacion(EstadoEvaluacion.FUERA_DE_ALCANCE,
                                   "Ninguna declaración de carpeta cubre este registro.")

    locales = [(c, d) for c, d in validas if c.origen is OrigenRegla.LOCAL]
    importadas = [(c, d) for c, d in validas if c.origen is OrigenRegla.IMPORTACION]
    candidatas = locales if locales else importadas
    if len(candidatas) > 1:
        destinos = {c.destino_id for c, _ in candidatas}
        motivo = ("Hay varias correspondencias vigentes que proponen destinos distintos."
                  if len(destinos) > 1 else
                  "Hay varias correspondencias vigentes para esta carpeta y no se elige ninguna.")
        return ResultadoEvaluacion(
            EstadoEvaluacion.CONFLICTO_DE_CORRESPONDENCIAS, motivo,
            reglas_involucradas=tuple(_regla_dict(c) for c, _ in candidatas),
            conflicto_visible=tuple(_regla_dict(c) for c, _ in validas))
    c, decl = candidatas[0]
    destino = await _destino(db, c.destino_tipo, c.destino_id)
    if destino is None:
        otro_modelo = Issue if c.destino_tipo is TipoDestino.SERIE else Series
        if await db.get(otro_modelo, c.destino_id) is not None:
            return ResultadoEvaluacion(
                EstadoEvaluacion.EVIDENCIA_INCOMPATIBLE,
                "El destino existe, pero no es del tipo que declara la correspondencia.",
                correspondencia_id=c.correspondencia_id, version_de_regla=c.version,
                destino_tipo=c.destino_tipo, destino_id=c.destino_id,
                reglas_involucradas=(_regla_dict(c),))
        return ResultadoEvaluacion(
            EstadoEvaluacion.DESTINO_NO_DISPONIBLE,
            "La correspondencia existe, pero su destino ya no está disponible.",
            correspondencia_id=c.correspondencia_id, version_de_regla=c.version,
            declaracion_id=decl.declaracion_id, version_declaracion=decl.version,
            destino_tipo=c.destino_tipo, destino_id=c.destino_id,
            alcance={"contexto_raiz": c.contexto_raiz,
                     "incluir_descendientes": c.incluir_descendientes,
                     "tipo_de_registro": c.tipo_de_registro.value if c.tipo_de_registro else None},
            reglas_involucradas=(_regla_dict(c),),
            conflicto_visible=tuple(_regla_dict(x) for x, _ in validas if x.id != c.id))
    propuesta = Propuesta(
        correspondencia_id=c.correspondencia_id, version_de_regla=c.version,
        declaracion_id=decl.declaracion_id, version_declaracion=decl.version,
        destino_tipo=c.destino_tipo, destino_id=c.destino_id,
        alcance={"contexto_raiz": c.contexto_raiz,
                 "incluir_descendientes": c.incluir_descendientes,
                 "tipo_de_registro": c.tipo_de_registro.value if c.tipo_de_registro else None},
        origen=c.origen, precedencia_aplicada=c.origen.value,
        evidencia={"declaracion_version_id": str(decl.id), "version_declaracion": decl.version})
    return ResultadoEvaluacion(
        EstadoEvaluacion.PROPUESTA_DISPONIBLE,
        "Hay una correspondencia vigente para esta carpeta.",
        propuesta=propuesta, correspondencia_id=c.correspondencia_id,
        version_de_regla=c.version, declaracion_id=decl.declaracion_id,
        version_declaracion=decl.version, destino_tipo=c.destino_tipo,
        destino_id=c.destino_id, alcance=propuesta.alcance,
        reglas_involucradas=(_regla_dict(c),),
        precedencia_aplicada=c.origen.value,
        conflicto_visible=tuple(_regla_dict(x) for x, _ in importadas) if locales else ())


async def validar_propuesta(db: AsyncSession, propuesta: Propuesta) -> ResultadoEvaluacion:
    """Valida una propuesta retenida contra la correspondencia/declaración actuales."""
    actual = (await db.execute(
        select(CorrespondenciaContexto).where(
            CorrespondenciaContexto.correspondencia_id == propuesta.correspondencia_id,
            CorrespondenciaContexto.vigente_hasta.is_(None)))).scalar_one_or_none()
    decl = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.declaracion_id == propuesta.declaracion_id,
            DeclaracionCarpeta.version == propuesta.version_declaracion))).scalar_one_or_none()
    decl_vigente = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.declaracion_id == propuesta.declaracion_id,
            DeclaracionCarpeta.vigente_hasta.is_(None),
            DeclaracionCarpeta.estado == EstadoRegla.ACTIVA))).scalar_one_or_none()
    if (actual is None or actual.version != propuesta.version_de_regla
            or actual.estado is not EstadoRegla.ACTIVA
            or decl is None or decl_vigente is None or decl_vigente.id != decl.id):
        current = None
        if actual is not None:
            current = await _version_actual_declaracion(db, actual.declaracion_version_id)
        return ResultadoEvaluacion(
            EstadoEvaluacion.REGLA_DESACTUALIZADA,
            "La propuesta ya no corresponde a la versión vigente.",
            correspondencia_id=propuesta.correspondencia_id,
            version_de_regla=propuesta.version_de_regla,
            declaracion_id=current.declaracion_id if current else None,
            version_declaracion=current.version if current else None,
            destino_tipo=propuesta.destino_tipo, destino_id=propuesta.destino_id,
            reglas_involucradas=({"correspondencia_id": str(propuesta.correspondencia_id),
                                  "version": propuesta.version_de_regla},))
    destino = await _destino(db, propuesta.destino_tipo, propuesta.destino_id)
    if destino is None:
        return ResultadoEvaluacion(
            EstadoEvaluacion.DESTINO_NO_DISPONIBLE,
            "La correspondencia existe, pero su destino ya no está disponible.",
            correspondencia_id=propuesta.correspondencia_id,
            version_de_regla=propuesta.version_de_regla,
            declaracion_id=decl.declaracion_id, version_declaracion=decl.version,
            destino_tipo=propuesta.destino_tipo, destino_id=propuesta.destino_id,
            alcance=propuesta.alcance)
    return ResultadoEvaluacion(
        EstadoEvaluacion.PROPUESTA_DISPONIBLE,
        "La propuesta sigue vigente.",
        propuesta=propuesta, correspondencia_id=propuesta.correspondencia_id,
        version_de_regla=propuesta.version_de_regla,
        declaracion_id=decl.declaracion_id, version_declaracion=decl.version,
        destino_tipo=propuesta.destino_tipo, destino_id=propuesta.destino_id,
        alcance=propuesta.alcance, precedencia_aplicada=propuesta.precedencia_aplicada)
