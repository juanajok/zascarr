"""Inventario de solo lectura de las operaciones de ZascArr (#123b, criterio 4).

No escanea la biblioteca (`rglob`/`iterdir`/`os.walk`) ni escribe: solo consulta
las tablas de operaciones y los estados en memoria. La clasificación distingue
lo que cada contrato puede distinguir; no inventa «en curso» donde no hay
estado persistido.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    AltaOperacion,
    AsignacionOperacion,
    ImportRun,
    VinculacionOperacion,
)
from zascarr.services import comprobacion_disco, registro_biblioteca
from zascarr.services.asignacion import estado_ultima_reconciliacion

ESTADOS_ASIGNACION = ("completada", "en_curso", "recuperable", "fallida")


def clasificar_asignacion(estado: str, *, en_curso: bool) -> str:
    """Clasifica el estado persistido de una asignación.

    `preparada`/`confirmada` están vivas: solo son «en curso» si su candado
    consultivo está tomado por un ejecutor. Sin candado son recuperables.
    Un valor fuera del enum es un error, no una operación completada.
    """
    if estado == "limpiada":
        return "completada"
    if estado == "cancelada":
        return "fallida"
    if estado in ("preparada", "confirmada"):
        return "en_curso" if en_curso else "recuperable"
    raise ValueError(f"estado de asignación desconocido: {estado!r}")


def clasificar_alta(estado: str) -> str:
    if estado == "creada":
        return "completada"
    if estado == "deshecha":
        return "no_aplica"
    raise ValueError(f"estado de alta desconocido: {estado!r}")


def clasificar_vinculacion(global_: str | None) -> str:
    if global_ == "vinculados_todos":
        return "completada"
    if global_ == "vinculados_parcialmente":
        return "parcial"
    if global_ == "nada_vinculado":
        return "sin_efecto"
    raise ValueError(f"resultado de vinculación desconocido: {global_!r}")


def _clave_candado(operacion_id) -> tuple[int, int]:
    clave = int(operacion_id.int) & 0x7FFF_FFFF_FFFF_FFFF
    return clave >> 32, clave & 0xFFFFFFFF


async def _candados(db: AsyncSession) -> set[tuple[int, int]]:
    filas = (await db.execute(text(
        "SELECT classid, objid FROM pg_locks WHERE locktype = 'advisory' AND granted "
        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    ))).all()
    return {(int(c), int(o)) for c, o in filas}


def _fecha(valor) -> str | None:
    return valor.isoformat() if valor is not None else None


async def resumen_operaciones(db: AsyncSession) -> dict:
    """Recuentos/estados de las cuatro tablas, sin rutas ni nombres."""
    candados = await _candados(db)

    asignacion = {estado: 0 for estado in ESTADOS_ASIGNACION}
    asignacion["desconocida"] = 0
    filas = (await db.execute(
        select(AsignacionOperacion.id, AsignacionOperacion.estado,
               AsignacionOperacion.creada, AsignacionOperacion.actualizada)
        .order_by(AsignacionOperacion.creada)
    )).all()
    for op_id, estado, _creada, _actualizada in filas:
        estado_valor = estado.value if hasattr(estado, "value") else str(estado)
        try:
            cubo = clasificar_asignacion(
                estado_valor, en_curso=_clave_candado(op_id) in candados)
        except ValueError:
            cubo = "desconocida"
        asignacion[cubo] += 1
    asignacion["total"] = sum(v for k, v in asignacion.items() if k != "total")

    alta = {"completada": 0, "no_aplica": 0, "desconocida": 0}
    for (estado,) in (await db.execute(
            select(AltaOperacion.estado).order_by(AltaOperacion.creada))).all():
        valor = estado.value if hasattr(estado, "value") else str(estado)
        try:
            alta[clasificar_alta(valor)] += 1
        except ValueError:
            alta["desconocida"] += 1
    alta["total"] = alta["completada"] + alta["no_aplica"] + alta["desconocida"]

    vinculacion = {"completada": 0, "parcial": 0, "sin_efecto": 0, "desconocida": 0}
    for (resultado,) in (await db.execute(
            select(VinculacionOperacion.resultado)
            .order_by(VinculacionOperacion.creada))).all():
        try:
            vinculacion[clasificar_vinculacion(
                (resultado or {}).get("global"))] += 1
        except ValueError:
            vinculacion["desconocida"] += 1
    vinculacion["total"] = sum(
        v for k, v in vinculacion.items() if k != "total")

    import_runs = {"completada": 0, "con_errores": 0}
    ultimo = (await db.execute(
        select(ImportRun).order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        .limit(1))).scalar_one_or_none()
    for (errores,) in (await db.execute(select(ImportRun.error_count))).all():
        import_runs["con_errores" if (errores or 0) > 0 else "completada"] += 1
    import_runs["total"] = import_runs["completada"] + import_runs["con_errores"]
    import_runs["ultima"] = None if ultimo is None else {
        "iniciada": _fecha(ultimo.started_at),
        "terminada": _fecha(ultimo.finished_at),
        "errores": int(ultimo.error_count or 0),
        "disparador": (ultimo.details or {}).get("disparador"),
    }

    return {
        "generado_en": datetime.now(UTC).isoformat(),
        "asignacion": asignacion,
        "alta": alta,
        "vinculacion": vinculacion,
        "import_runs": import_runs,
        "reconciliacion": estado_ultima_reconciliacion(),
        "no_persistidas": {
            "registro": {
                "fase": registro_biblioteca.estado_actual().fase.value,
                "persistido": False,
            },
            "comprobacion_disco": {
                "fase": comprobacion_disco.estado_actual().fase.value,
                "persistido": False,
            },
        },
    }
