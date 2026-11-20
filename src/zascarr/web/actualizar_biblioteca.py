"""«Actualizar la biblioteca» desde Biblioteca y su cadencia en Ajustes (#1160).

Es el mismo servicio que el bloque de Auditoría (`services/rescan_biblioteca.py`): aquí solo se
pinta un resumen corto y se enlaza al informe completo. Un GET no lanza nada ni escribe.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr import database
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services import rescan_biblioteca
from zascarr.services.primeros_pasos import MESES
from zascarr.web.disponibilidad import registrar_filtros
from zascarr.web.routes import crear_templates

templates = crear_templates()
registrar_filtros(templates)
router = APIRouter(prefix="/ui/biblioteca", tags=["ui"])

#: Nombre de cada cadencia que ofrece Ajustes (minutos → etiqueta).
ETIQUETAS_CADENCIA = {
    0: "Desactivado",
    1440: "Una vez al día",
    10080: "Una vez a la semana",
}


def _local(fecha: datetime) -> datetime:
    return (fecha if fecha.tzinfo else fecha.replace(tzinfo=UTC)).astimezone()


def _dia_y_hora(fecha: datetime, ahora: datetime, *, aproximada: bool) -> str:
    """«hoy, 08:12», «ayer, 08:12», «mañana hacia las 08:12» o «3 de octubre, 08:12»."""
    local, hoy = _local(fecha), _local(ahora).date()
    dias = (local.date() - hoy).days
    hora = local.strftime("%H:%M")
    nombre = {0: "hoy", -1: "ayer", 1: "mañana"}.get(dias)
    if nombre is None:
        nombre = f"el {local.day} de {MESES[local.month - 1]}"
        if local.year != _local(ahora).year:
            nombre += f" de {local.year}"
    return f"{nombre} hacia las {hora}" if aproximada else f"{nombre}, {hora}"


def texto_ultima(ultima: datetime | None, ahora: datetime | None = None) -> str:
    if ultima is None:
        return "Todavía no se ha actualizado."
    return f"Última vez: {_dia_y_hora(ultima, ahora or datetime.now(UTC), aproximada=False)}"


def texto_proxima(minutos: int, *, ahora: datetime | None = None) -> str | None:
    """`None` si está apagada (la plantilla lo dice con su enlace) o si no hay nada que anunciar."""
    proxima = rescan_biblioteca.proxima_ejecucion(minutos)
    if proxima is None:
        return None
    ahora = ahora or datetime.now(UTC)
    if proxima <= ahora + timedelta(minutes=1):
        return "Próxima: en unos minutos"
    return f"Próxima: {_dia_y_hora(proxima, ahora, aproximada=True)}"


def opciones_cadencia(minutos: int) -> list[dict]:
    """Opciones del desplegable de Ajustes. Un valor fijado en la instalación que no es ninguna de
    las tres se muestra como cuarta opción marcada, para que guardar otra cosa no lo pise."""
    opciones = [{"valor": v, "etiqueta": e, "marcada": v == minutos}
                for v, e in ETIQUETAS_CADENCIA.items()]
    if minutos not in ETIQUETAS_CADENCIA:
        if minutos % 1440 == 0:
            cuando = f"Cada {minutos // 1440} días"
        elif minutos % 60 == 0:
            cuando = f"Cada {minutos // 60} horas"
        else:
            cuando = f"Cada {minutos} minutos"
        opciones.append({"valor": minutos, "etiqueta": f"{cuando} (fijado en la instalación)",
                         "marcada": True})
    return opciones


def mensaje_guardado(minutos: int) -> str:
    if minutos <= 0:
        return "Guardado. Ya no se actualiza sola; puedes hacerlo desde Biblioteca."
    proxima = texto_proxima(minutos)
    cuando = (proxima or "").removeprefix("Próxima: ")
    return f"Guardado. La próxima será {cuando}." if cuando else "Guardado."


async def contexto_fragmento(db: AsyncSession, *, ya_en_curso: bool = False,
                             recien_lanzada: bool = False, parcial: bool = False) -> dict:
    """Todo lo que pinta el fragmento; solo lee memoria y el último `ImportRun`."""
    estado = rescan_biblioteca.estado_actual()
    resumen = rescan_biblioteca.resumen_de(estado.informe)
    persistido = None if resumen is not None else await rescan_biblioteca.ultimo_persistido(db)
    if resumen is None:
        resumen = rescan_biblioteca.resumen_de(persistido)
    ultima = rescan_biblioteca.ultima_ejecucion() or (resumen or {}).get("started_at")
    minutos = max(0, int(get_settings().rescan_interval_minutes))
    return {
        "estado_rescan": estado,
        "resumen": resumen,
        "ya_en_curso": ya_en_curso,
        "recien_lanzada": recien_lanzada,
        "parcial": parcial,
        "primera_vez": ultima is None,
        "texto_ultima": texto_ultima(ultima),
        "texto_proxima": None if estado.en_curso else texto_proxima(minutos),
        "apagada": minutos <= 0,
    }


def _no_store(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/actualizar", response_class=HTMLResponse)
async def estado_actualizacion(request: Request,
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """El bloque entero, para cargarlo en Biblioteca. No lanza nada ni escribe."""
    contexto = await contexto_fragmento(db)
    return _no_store(
        templates.TemplateResponse(request, "_actualizar_biblioteca.html", contexto))


@router.get("/actualizar/estado", response_class=HTMLResponse)
async def sondeo_actualizacion(request: Request,
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Solo el contenido, el botón y las líneas (fuera de banda); lo pide el sondeo."""
    contexto = await contexto_fragmento(db, parcial=True)
    return _no_store(
        templates.TemplateResponse(request, "_actualizar_biblioteca.html", contexto))


@router.post("/actualizar", response_class=HTMLResponse)
async def actualizar(request: Request, db: AsyncSession = Depends(get_db)):
    """Lanza la actualización en segundo plano y responde ya (no espera a la operación)."""
    lanzada = rescan_biblioteca.iniciar_manual(database.async_session_factory)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/ui/biblioteca", status_code=303)
    contexto = await contexto_fragmento(
        db, ya_en_curso=not lanzada, recien_lanzada=True, parcial=True)
    return _no_store(
        templates.TemplateResponse(request, "_actualizar_biblioteca.html", contexto))
