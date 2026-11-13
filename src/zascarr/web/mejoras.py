"""BL-D3 (#154): pantalla de mejoras disponibles y confirmación de descarga."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.orchestrator import (
    Orchestrator,
    crear_token_candidato,
    verificar_token_candidato,
)
from zascarr.services.upgrades import (
    descartar_mejora,
    escanear_mejoras,
    listar_mejoras,
    marcar_descargada,
    obtener_mejora,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/mejoras", tags=["ui"])
templates = crear_templates()


def _respuesta(request: Request, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, "mejoras.html", contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("", response_class=HTMLResponse)
async def mejoras(request: Request, guardado: str = Query(default=""),
                  db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    filas = await listar_mejoras(db)
    secret = get_settings().secret_key
    return _respuesta(request, {
        "mejoras": [
            {"m": m, "token": crear_token_candidato(m.issue.id, m.candidato, secret)}
            for m in filas
        ],
        "aviso": {
            "escaneado": "Búsqueda de mejoras terminada.",
            "descargada": "Descarga enviada. No se ha borrado ni sustituido nada.",
            "descartada": "Propuesta descartada.",
        }.get(guardado, ""),
        "error": "No se pudo enviar la descarga. Revisa el cliente en Ajustes."
        if guardado == "fallo" else "",
    })


@router.post("/escanear", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def escanear(request: Request, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    await escanear_mejoras(db)
    return RedirectResponse("/ui/mejoras?guardado=escaneado", status_code=303)


@router.post("/{propuesta_id}/descargar", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def descargar(propuesta_id: UUID, request: Request, token: str = Form(...),
                    db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    mejora = await obtener_mejora(db, propuesta_id)
    if mejora is None:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    candidato = verificar_token_candidato(
        token, mejora.issue.id, get_settings().secret_key)
    if candidato is None:
        raise HTTPException(status_code=400,
                            detail="Candidato no válido o caducado — vuelve a cargar la lista")
    ok, _mensaje = await Orchestrator(db).enviar_candidato_de_mejora(candidato)
    if ok:
        await marcar_descargada(db, propuesta_id)
        await db.commit()
        return RedirectResponse("/ui/mejoras?guardado=descargada", status_code=303)
    await db.rollback()
    return RedirectResponse("/ui/mejoras?guardado=fallo", status_code=303)


@router.post("/{propuesta_id}/descartar", response_class=HTMLResponse)
async def descartar(propuesta_id: UUID, db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    if not await descartar_mejora(db, propuesta_id):
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    await db.commit()
    return RedirectResponse("/ui/mejoras?guardado=descartada", status_code=303)
