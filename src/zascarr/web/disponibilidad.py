# ruff: noqa: E501
"""Archivos no disponibles (BL-R2, #231) — `/ui/no-disponibles`.

Lista de SOLO LECTURA de los archivos que el ciclo del importador marcó como no encontrados, más lo que comprobó
la última vez (ver `services/disponibilidad.py`). Abrirla o paginarla no toca el disco, no lanza ninguna comprobación
y no modifica nada: lo observado se lee de la base. Lanzar una comprobación a mano pertenece a #232.

Si no puede leerse, dice que no ha podido: nunca una lista vacía que parezca «todo disponible».
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr import database
from zascarr.database import get_db
from zascarr.services import comprobacion_disco, disponibilidad
from zascarr.services.primeros_pasos import fecha_llana, hace_cuanto
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()


def _fecha_con_antiguedad(fecha: datetime) -> str:
    """«3 de octubre de 2026 (hace 5 días)»: la fecha exacta y si es reciente, sin hacer cuentas."""
    return f"{fecha_llana(fecha)} ({hace_cuanto(fecha, datetime.now(UTC))})"


def _hora(fecha: datetime) -> str:
    return fecha.astimezone().strftime("%H:%M")


def _duracion(segundos: float | None) -> str:
    if segundos is None:
        return ""
    if segundos < 1:
        return "Tardó menos de un segundo."
    if segundos < 60:
        return f"Tardó {round(segundos)} segundos."
    minutos, resto = divmod(round(segundos), 60)
    return f"Tardó {minutos} min {resto} s."


def _etiqueta_disparador(valor: str | None) -> str:
    if valor == "manual":
        return "manual"
    if valor == "automatico":
        return "automática"
    return "origen sin dato"


def registrar_filtros(plantillas) -> None:
    """Para las pantallas que enseñan el aviso de la última comprobación (esta y Estado)."""
    plantillas.env.filters["fecha_con_antiguedad"] = _fecha_con_antiguedad
    plantillas.env.filters["hora"] = _hora
    plantillas.env.filters["duracion"] = _duracion
    plantillas.env.filters["etiqueta_disparador"] = _etiqueta_disparador


registrar_filtros(templates)

router = APIRouter(prefix="/ui/no-disponibles", tags=["ui"])


@router.get("", response_class=HTMLResponse)
async def no_disponibles(request: Request, despues: str | None = None,
                         db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        pagina = await disponibilidad.listar_no_disponibles(db, despues)
        contexto = await _contexto_comprobacion(db)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de lectura se dice, no se disfraza de lista vacía
        # Solo la clase del error: nunca rutas, consultas ni datos del coleccionista (CLAUDE.md §5.4).
        logger.warning("no_disponibles.lectura_fallida", error=type(exc).__name__)
        await db.rollback()
        return templates.TemplateResponse(request, "no_disponibles.html", {"error": True}, status_code=503)
    contexto.update({"error": False, "pagina": pagina, "primera": despues is None,
                     "no_disponibles": pagina.total})
    respuesta = templates.TemplateResponse(request, "no_disponibles.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


async def _contexto_comprobacion(db: AsyncSession, *, recien_lanzada: bool = False,
                                 ya_en_curso: bool = False) -> dict:
    """Contexto común de página y fragmento; solo lee."""
    estado = comprobacion_disco.estado_actual()
    ultima = None
    if estado.fase is not comprobacion_disco.FaseCicloDisco.CORRIENDO:
        run_id = estado.run_id if estado.fase is comprobacion_disco.FaseCicloDisco.TERMINADO else None
        ultima = await disponibilidad.ultima_ejecucion_importador(db, run_id)
    return {
        "d": await disponibilidad.ultima_comprobacion(db),
        "estado_ciclo": estado,
        "ultima": ultima,
        "recien_lanzada": recien_lanzada,
        "ya_en_curso": ya_en_curso,
        "recien_terminada": comprobacion_disco.consumir_foco_resultado()
        if estado.fase is comprobacion_disco.FaseCicloDisco.TERMINADO else False,
        "no_disponibles": None,
    }


@router.get("/comprobar", response_class=HTMLResponse)
async def comprobar_estado(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Fragmento de estado. GET no lanza nada ni escribe: solo lee memoria e ImportRun."""
    contexto = await _contexto_comprobacion(db)
    respuesta = templates.TemplateResponse(request, "_comprobacion_disco.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/comprobar", response_class=HTMLResponse)
async def comprobar(request: Request, db: AsyncSession = Depends(get_db)):
    """Lanza el ciclo en segundo plano y responde ya. No espera al ciclo."""
    lanzada = comprobacion_disco.iniciar_manual(database.async_session_factory)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/ui/no-disponibles", status_code=303)
    contexto = await _contexto_comprobacion(db, recien_lanzada=lanzada,
                                            ya_en_curso=not lanzada)
    respuesta = templates.TemplateResponse(request, "_comprobacion_disco.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
