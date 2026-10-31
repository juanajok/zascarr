"""Inventario de solo lectura de las operaciones de ZascArr (#123b, criterio 4).

No escanea la biblioteca (`rglob`/`iterdir`/`os.walk`) ni escribe: solo consulta
las tablas de operaciones y los estados en memoria. La clasificación distingue
lo que cada contrato puede distinguir; no inventa «en curso» donde no hay
estado persistido.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    AltaOperacion,
    AsignacionEstado,
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


async def _contar_por(db: AsyncSession, columna) -> dict:
    """`{valor: n}` con un GROUP BY en SQL: ninguna fila de operaciones llega a Python, solo un recuento por valor."""
    return {valor: int(n) for valor, n in (await db.execute(
        select(columna, func.count()).group_by(columna))).all()}


async def resumen_operaciones(db: AsyncSession) -> dict:
    """Recuentos/estados de las cuatro tablas, sin rutas ni nombres.

    Todo se cuenta en SQL (`GROUP BY`): con miles de operaciones la petición no carga las filas en memoria. Lo único que
    se lee fila a fila son los ids de las asignaciones VIVAS (`preparada`/`confirmada`), para mirar su candado."""
    candados = await _candados(db)

    asignacion = {estado: 0 for estado in ESTADOS_ASIGNACION}
    asignacion["desconocida"] = 0
    for estado, n in (await _contar_por(db, AsignacionOperacion.estado)).items():
        estado_valor = estado.value if hasattr(estado, "value") else str(estado)
        if estado_valor in ("preparada", "confirmada"):
            continue                                   # las vivas se clasifican una a una, por su candado
        try:
            asignacion[clasificar_asignacion(estado_valor, en_curso=False)] += n
        except ValueError:
            asignacion["desconocida"] += n
    vivas = (await db.execute(
        select(AsignacionOperacion.id).where(AsignacionOperacion.estado.in_(
            [AsignacionEstado.PREPARADA, AsignacionEstado.CONFIRMADA])))).scalars().all()
    for op_id in vivas:
        asignacion[clasificar_asignacion(
            "preparada", en_curso=_clave_candado(op_id) in candados)] += 1
    asignacion["total"] = sum(v for k, v in asignacion.items() if k != "total")

    alta = {"completada": 0, "no_aplica": 0, "desconocida": 0}
    for estado, n in (await _contar_por(db, AltaOperacion.estado)).items():
        valor = estado.value if hasattr(estado, "value") else str(estado)
        try:
            alta[clasificar_alta(valor)] += n
        except ValueError:
            alta["desconocida"] += n
    alta["total"] = alta["completada"] + alta["no_aplica"] + alta["desconocida"]

    vinculacion = {"completada": 0, "parcial": 0, "sin_efecto": 0, "desconocida": 0}
    global_ = VinculacionOperacion.resultado["global"].as_string()
    for valor, n in (await _contar_por(db, global_)).items():
        try:
            vinculacion[clasificar_vinculacion(valor)] += n
        except ValueError:
            vinculacion["desconocida"] += n
    vinculacion["total"] = sum(
        v for k, v in vinculacion.items() if k != "total")

    import_runs = {"completada": 0, "con_errores": 0}
    ultimo = (await db.execute(
        select(ImportRun).order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        .limit(1))).scalar_one_or_none()
    con_errores = func.count().filter(func.coalesce(ImportRun.error_count, 0) > 0)
    total_runs, n_con_errores = (await db.execute(select(func.count(), con_errores))).one()
    import_runs["con_errores"] = int(n_con_errores)
    import_runs["completada"] = int(total_runs) - int(n_con_errores)
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
