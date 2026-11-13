"""BL-D3 (#154): pantalla de mejoras disponibles y confirmación de descarga."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
    devolver_mejora,
    escanear_mejoras,
    listar_mejoras,
    marcar_descargada,
    motivo_sin_escaneo,
    obtener_mejora,
    reclamar_mejora,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/mejoras", tags=["ui"])
templates = crear_templates()


def _respuesta(request: Request, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, "mejoras.html", contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def _contexto(db: AsyncSession, *, pagina: int = 1,
                    aviso: str = "", error: str = "") -> dict:
    datos = await listar_mejoras(db, pagina)
    secret = get_settings().secret_key
    return {
        "pagina": datos,
        "mejoras": [
            # El token se liga a la PROPUESTA, no al número (SecOps F-2).
            {"m": m,
             "token": crear_token_candidato(m.propuesta.id, m.candidato, secret)}
            for m in datos.filas
        ],
        "aviso": aviso,
        "error": error,
    }


@router.get("", response_class=HTMLResponse)
async def mejoras(request: Request, guardado: str = Query(default=""),
                  pagina: int = Query(default=1, ge=1),
                  db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    aviso = {
        "escaneado": "Búsqueda de mejoras terminada.",
        "descargada": "Descarga enviada. No se ha borrado ni sustituido nada.",
        "descartada": "Propuesta descartada.",
    }.get(guardado, "")
    error = ""
    if guardado == "fallo":
        error = "No se pudo enviar la descarga. Revisa el cliente en Ajustes."
    return _respuesta(request, await _contexto(
        db, pagina=pagina, aviso=aviso, error=error))


@router.post("/escanear", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def escanear(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    motivo = motivo_sin_escaneo()
    if motivo:
        return _respuesta(request, await _contexto(db, error=motivo))
    informe = await escanear_mejoras(db)
    aviso = (f"Revisados {informe.revisados} números; "
             f"{informe.creadas} propuestas nuevas.")
    if informe.fallidos:
        aviso += f" {informe.fallidos} no se pudieron consultar y se reintentarán."
    return _respuesta(request, await _contexto(db, aviso=aviso))


@router.post("/{propuesta_id}/descargar", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def descargar(propuesta_id: UUID, request: Request, token: str = Form(...),
                    db: AsyncSession = Depends(get_db)) -> Response:
    mejora = await obtener_mejora(db, propuesta_id)
    if mejora is None:
        return _respuesta(request, await _contexto(
            db, error="Esa propuesta ya no está disponible. Vuelve a la lista."))
    candidato = verificar_token_candidato(
        token, propuesta_id, get_settings().secret_key)
    # Doble ligadura (SecOps F-2): además de ser el token de ESTA propuesta, el enlace firmado
    # debe ser el que la fila guarda; lo que se envía nunca sale de otro sitio.
    if candidato is not None and candidato.download_url != mejora.propuesta.candidate_url:
        candidato = None
    if candidato is None:
        return _respuesta(request, await _contexto(
            db, error="La oferta ha caducado. Vuelve a cargar la lista y elige de nuevo."))
    reclamada = await reclamar_mejora(db, propuesta_id)
    if reclamada is None:
        return _respuesta(request, await _contexto(
            db, error="Esa propuesta ya se está enviando o ya no está pendiente."))
    ok, _mensaje = await Orchestrator(db).enviar_candidato_de_mejora(candidato)
    if ok:
        await marcar_descargada(db, propuesta_id)
        await db.commit()
        return RedirectResponse("/ui/mejoras?guardado=descargada", status_code=303)
    await devolver_mejora(db, propuesta_id)
    await db.commit()
    return RedirectResponse("/ui/mejoras?guardado=fallo", status_code=303)


@router.post("/{propuesta_id}/descartar", response_class=HTMLResponse)
async def descartar(propuesta_id: UUID, request: Request,
                    db: AsyncSession = Depends(get_db)) -> Response:
    if not await descartar_mejora(db, propuesta_id):
        return _respuesta(request, await _contexto(
            db, error="Esa propuesta ya no está pendiente. Vuelve a la lista."))
    await db.commit()
    return RedirectResponse("/ui/mejoras?guardado=descartada", status_code=303)
