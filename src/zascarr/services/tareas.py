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
    "rescanear": "Actualizando la biblioteca",
    "registrar": "Registrando tu biblioteca",
    "convertir": "Convirtiendo tebeos",
    "deshacer": "Deshaciendo una conversión",
    "paquete": "Preparando un paquete",
    "descarga": "Descargando de Deseados",
    "copia": "Copiando y verificando",
}


class TipoTarea(StrEnum):
    IMPORTAR = "importar"
    RESCANEAR = "rescanear"
    REGISTRAR = "registrar"
    CONVERTIR = "convertir"
    DESHACER = "deshacer"
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
    unidad: str | None = None
    _origen: str = ""
    _fin: float | None = None
    _creada_mono: float = 0.0
    _ultima_superficie: float = 0.0


_lock = threading.RLock()
_tareas: dict[str, Tarea] = {}
_por_origen: dict[str, str] = {}
_ultimo_anuncio: tuple[int, int, int] | None = None


def _ahora(ahora: float | None = None) -> float:
    return time.monotonic() if ahora is None else ahora


def _podar(ahora: float) -> None:
    for tid, t in list(_tareas.items()):
        # Especificación §1.3: una terminada se ve 8 s y se retira; un error, solo cuando ya se ha
        # visto. Exigir `visto` también a las terminadas las dejaba para siempre (nada las marca) y
        # el chip decía «Listo» en todas las páginas.
        retirable = (t.estado is EstadoTarea.TERMINADA
                     or (t.estado is EstadoTarea.ERROR and t.visto))
        if retirable and t._fin is not None and ahora - t._fin >= RETENCION_S:
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
        unidades = {"importar": "archivos", "registrar": "archivos",
                    "rescanear": "archivos", "descarga": "deseos",
                    "copia": "elementos", "convertir": "tebeos", "deshacer": "tebeos",
                    "paquete": "tebeos"}
        t = Tarea(id=secrets.token_hex(4), tipo=tipo, titulo=TITULOS[tipo.value],
                  fase=fase, total=total, enlace=enlace, run_id=run_id,
                  unidad=unidades.get(tipo.value),
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


def marcar_visto_ultimo() -> str | None:
    """Marca TODOS los errores no vistos (abrir el panel). Devuelve el último id."""
    ultimo = None
    with _lock:
        for t in _tareas.values():
            if t.estado is EstadoTarea.ERROR and not t.visto:
                marcar_visto(t.id)
                ultimo = t.id
    return ultimo


def marcar_visto(tid: str) -> None:
    with _lock:
        t = _tareas.get(tid)
        if t is not None and t.estado is EstadoTarea.ERROR:
            t.visto = True
            t._fin = _ahora(None)


def _publicable(t: Tarea, ahora: float) -> bool:
    return ahora - t._creada_mono >= UMBRAL_MS / 1000


def snapshot(*, ahora: float | None = None, incluir_recientes: bool = False,
             consumir_anuncio: bool = False) -> dict[str, Any]:
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
            atascada = estado == "atascada"
            pct = None
            if t.total and t.hechos is not None and t.total > 0:
                pct = round(t.hechos * 100 / t.total)
            minutos = max(0, int((datetime.now(UTC) - t.iniciada).total_seconds() // 60))
            hace = "ahora" if minutos == 0 else f"hace {minutos} min"
            salida.append({"id": t.id, "tipo": t.tipo.value, "titulo": t.titulo,
                           "iniciada_texto": f"Empezó {hace}",
                           "fase": t.fase, "hechos": t.hechos, "total": t.total,
                           "pct": pct, "unidad": t.unidad if t.total else None,
                           "estado": estado, "atascada": atascada,
                           "iniciada": t.iniciada.isoformat(),
                           "actualizada": t.actualizada.isoformat(), "enlace": t.enlace,
                           "detalle": t.detalle, "run_id": t.run_id, "visto": t.visto})
        activas = sum(1 for x in salida if x["estado"] in {"en_curso", "atascada"})
        errores = sum(1 for x in salida if x["estado"] == "error")
        global _ultimo_anuncio
        terminadas = sum(1 for x in salida if x["estado"] == "terminada")
        firma = (activas, errores, terminadas)
        anuncio = None
        if consumir_anuncio and firma != _ultimo_anuncio:
            _ultimo_anuncio = firma
            if errores:
                anuncio = "Una tarea ha fallado."
            elif activas:
                plural = "" if activas == 1 else "s"
                anuncio = f"ZascArr está trabajando en {activas} tarea{plural}."
            else:
                # UXA-15 (#1132): en reposo se nombra lo que acaba de terminar;
                # solo si la firma cambia, así que no se repite en cada consulta.
                fin = [x["titulo"] for x in salida if x["estado"] == "terminada"]
                if len(fin) == 1:
                    anuncio = f"{fin[0]}: terminado."
                elif fin:
                    anuncio = f"{len(fin)} tareas terminadas."
        return {"version": 1, "generado": datetime.now(UTC).isoformat(),
                "tareas": salida, "activas": activas, "errores": errores,
                "hay_tareas": bool(salida),
                "resumen": {"total": len(salida), "en_curso": activas,
                            "con_error": errores, "hay_tareas": bool(salida)},
                "anuncio": anuncio}


def limpiar_al_arrancar() -> None:
    with _lock:
        _tareas.clear()
        _por_origen.clear()
        global _ultimo_anuncio
        _ultimo_anuncio = None


def _reset_para_pruebas() -> None:
    limpiar_al_arrancar()


def iniciar_descargas(*, total: int | None = None) -> Tarea | None:
    """Adaptador C2 para el ciclo de descargas de Deseados (sin % global)."""
    return iniciar("descarga", total=total, enlace="/ui/wishlist#wishlist-progreso",
                   origen="descargas")


def iniciar_copia() -> Tarea | None:
    """Adaptador C2 para copia/verificación externa (indeterminada)."""
    return iniciar("copia", enlace="/estado#copias", origen="copia")
