"""#991 C1: registro global de tareas en memoria (sin BD, sin Redis, un worker).

Solo guarda copy estática y contadores; nunca rutas, nombres, URLs ni `str(exc)`.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

MAX_ACTIVAS = 20
MAX_RECIENTES = 5
RETENCION_S = 8.0
UMBRAL_MS = 400
ATASCADA_S = 600.0
COALESCING_S = 0.25

TITULOS = {
    "importar": "Importando descargas",
    "rescanear": "Revisando la biblioteca",
    "registrar": "Registrando tu biblioteca",
    "convertir": "Convirtiendo tebeos",
    "paquete": "Preparando un paquete",
    "descarga": "Descargando de Deseados",
    "copia": "Copiando y verificando",
}


class TipoTarea(StrEnum):
    IMPORTAR = "importar"
    RESCANEAR = "rescanear"
    REGISTRAR = "registrar"
    CONVERTIR = "convertir"
    PAQUETE = "paquete"
    DESCARGA = "descarga"
    COPIA = "copia"


class EstadoTarea(StrEnum):
    EN_CURSO = "en_curso"
    TERMINADA = "terminada"
    ERROR = "error"
    ATASCADA = "atascada"


@dataclass
class Tarea:
    id: str
    tipo: TipoTarea
    titulo: str
    fase: str | None = None
    hechos: int | None = None
    total: int | None = None
    estado: EstadoTarea = EstadoTarea.EN_CURSO
    iniciada: datetime = field(default_factory=lambda: datetime.now(UTC))
    actualizada: datetime = field(default_factory=lambda: datetime.now(UTC))
    enlace: str | None = None
    detalle: str | None = None
    run_id: str | None = None
    visto: bool = False
    _origen: str = ""
    _fin: float | None = None
    _creada_mono: float = 0.0
    _ultima_superficie: float = 0.0


_lock = threading.RLock()
_tareas: dict[str, Tarea] = {}
_por_origen: dict[str, str] = {}


def _ahora(ahora: float | None = None) -> float:
    return time.monotonic() if ahora is None else ahora


def _podar(ahora: float) -> None:
    for tid, t in list(_tareas.items()):
        if (t.estado in (EstadoTarea.TERMINADA, EstadoTarea.ERROR) and t.visto
                and t._fin is not None and ahora - t._fin >= RETENCION_S):
            _tareas.pop(tid, None)
            _por_origen.pop(t._origen, None)
    recientes = [t for t in _tareas.values()
                 if t.estado in (EstadoTarea.TERMINADA, EstadoTarea.ERROR)]
    for t in sorted(recientes, key=lambda x: x._fin or 0)[:-MAX_RECIENTES]:
        _tareas.pop(t.id, None)
        _por_origen.pop(t._origen, None)


def iniciar(tipo: TipoTarea | str, *, total: int | None = None, fase: str | None = None,
            enlace: str | None = None, run_id: str | None = None,
            origen: str = "manual", ahora: float | None = None) -> Tarea | None:
    tipo = TipoTarea(tipo)
    with _lock:
        _podar(_ahora(ahora))
        if origen in _por_origen:
            t = _tareas.get(_por_origen[origen])
            if t and t.estado is EstadoTarea.EN_CURSO:
                return t
        activas = sum(1 for t in _tareas.values() if t.estado is EstadoTarea.EN_CURSO)
        if activas >= MAX_ACTIVAS:
            return None
        if enlace is not None and not (enlace.startswith("/ui/") or enlace == "/estado"):
            enlace = None
        t = Tarea(id=secrets.token_hex(4), tipo=tipo, titulo=TITULOS[tipo.value],
                  fase=fase, total=total, enlace=enlace, run_id=run_id,
                  _origen=origen, _creada_mono=_ahora(ahora),
                  _ultima_superficie=_ahora(ahora))
        _tareas[t.id] = t
        _por_origen[origen] = t.id
        return t


def actualizar(tid: str, *, fase: str | None = None, hechos: int | None = None,
               total: int | None = None, detalle: str | None = None,
               ahora: float | None = None) -> None:
    with _lock:
        t = _tareas.get(tid)
        if t is None or t.estado is not EstadoTarea.EN_CURSO:
            return
        momento = _ahora(ahora)
        t.actualizada = datetime.now(UTC)
        if fase is not None and momento - t._ultima_superficie >= COALESCING_S:
            t.fase = fase
            t._ultima_superficie = momento
        if total is not None:
            t.total = max(0, total)
        if hechos is not None:
            t.hechos = max(0, hechos if t.total is None else min(hechos, t.total))
        if detalle is not None:
            t.detalle = detalle


def terminar(tid: str, *, resumen: str | None = None, ahora: float | None = None) -> None:
    with _lock:
        t = _tareas.get(tid)
        if t is None:
            return
        t.estado = EstadoTarea.TERMINADA
        t.actualizada = datetime.now(UTC)
        t.detalle = resumen
        t._fin = _ahora(ahora)
        _por_origen.pop(t._origen, None)


def error(tid: str, *, tipo_error: str, fase: str | None = None,
          ahora: float | None = None) -> None:
    with _lock:
        t = _tareas.get(tid)
        if t is None:
            return
        t.estado = EstadoTarea.ERROR
        t.fase = fase or t.fase
        t.detalle = tipo_error
        t.visto = False
        t.actualizada = datetime.now(UTC)
        t._fin = _ahora(ahora)


def marcar_visto(tid: str) -> None:
    with _lock:
        t = _tareas.get(tid)
        if t is not None and t.estado is EstadoTarea.ERROR:
            t.visto = True
            t._fin = _ahora(None)


def _publicable(t: Tarea, ahora: float) -> bool:
    return ahora - t._creada_mono >= UMBRAL_MS / 1000


def snapshot(*, ahora: float | None = None, incluir_recientes: bool = False) -> dict[str, Any]:
    momento = _ahora(ahora)
    with _lock:
        _podar(momento)
        visibles = [t for t in _tareas.values() if _publicable(t, momento)]
        if not incluir_recientes:
            visibles = [t for t in visibles if t.estado is not EstadoTarea.TERMINADA]
        salida = []
        for t in visibles:
            estado = t.estado.value
            if (t.estado is EstadoTarea.EN_CURSO
                    and (datetime.now(UTC) - t.actualizada).total_seconds() >= ATASCADA_S):
                estado = "atascada"
            salida.append({"id": t.id, "tipo": t.tipo.value, "titulo": t.titulo,
                           "fase": t.fase, "hechos": t.hechos, "total": t.total,
                           "estado": estado, "iniciada": t.iniciada.isoformat(),
                           "actualizada": t.actualizada.isoformat(), "enlace": t.enlace,
                           "detalle": t.detalle, "run_id": t.run_id, "visto": t.visto})
        activas = sum(1 for x in salida if x["estado"] in {"en_curso", "atascada"})
        errores = sum(1 for x in salida if x["estado"] == "error")
        return {"version": 1, "tareas": salida, "activas": activas,
                "errores": errores, "hay_tareas": bool(salida)}


def limpiar_al_arrancar() -> None:
    with _lock:
        _tareas.clear()
        _por_origen.clear()


def _reset_para_pruebas() -> None:
    limpiar_al_arrancar()
