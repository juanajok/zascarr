# ruff: noqa: E501
"""Asistente «Elegir la serie de una carpeta», primer paso (#118, MIT-M3-US01): descubrir o crear desde un grupo.

Es el primer paso del asistente de la rebanada 2e sobre los servicios 2a–2d: **no hay otro asistente paralelo** y este
módulo no tiene lógica de negocio propia. Pinta lo que ya calculan `DescubrimientoDeGrupo` (2a) y `buscar_a_ritmo`
(el mismo ritmo de cortesía que `POST /api/revision/descubrir`).

Qué hace y qué NO hace (criterios de #118):
- **Abrir** el asistente enseña el grupo y una consulta propuesta editable. No consulta ninguna fuente.
- **Buscar** es a petición, con la consulta que la persona ve (propuesta o editada) y sin crear ni vincular nada.
- **Elegir** una candidata (o dar los datos a mano) exige la tradición explícita, conserva el grupo y **no crea la
  serie**: devuelve el resumen de la elección. La vista previa del alta y la confirmación son #119.
- El camino **a mano** se abre sin consultar fuentes ni necesitar claves.

Los fallos recuperables se pintan dentro de la página con 200 (htmx no sustituye una respuesta 4xx).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.revision import buscar_a_ritmo
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.descubrimiento_grupo import (
    DescubrimientoDeGrupo,
    GrupoNoEncontradoError,
    RespuestaDescubrir,
    tradiciones_de_la_carpeta,
)
from zascarr.services.discovery import (
    FUENTE_APAGADA,
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    ORDEN_DE_FUENTES,
)
from zascarr.services.tokens_revision import (
    MAX_CLAVE_GRUPO,
    MAX_TITULO,
    MAX_TOKEN_CANDIDATA,
    verificar_token_candidata,
)
from zascarr.web.library import _TRADICION_LABEL
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/pendientes/carpetas/asistente", tags=["ui"])

RUTA = "/ui/pendientes/carpetas/asistente"

_NOMBRE_FUENTE = {"comic_vine": "Comic Vine", "anilist": "AniList", "tebeosfera": "Tebeosfera", "gcd": "GCD"}

#: estado de una fuente → (estado del chip, texto para la persona). «error» NO es «sin coincidencias».
_ESTADO_DE_FUENTE = {
    FUENTE_OK: ("ok", "ha respondido"),
    FUENTE_APAGADA: ("neutro", "apagada en los ajustes"),
    FUENTE_SIN_CLAVE: ("amber", "sin clave configurada"),
    FUENTE_ERROR: ("warn", "no ha respondido ahora mismo"),
}

MENSAJE_SIN_CLAVE = "ZascArr no tiene clave para firmar lo que ves: reinícialo e inténtalo de nuevo."
MENSAJE_BUSQUEDA_CADUCADA = ("Esa búsqueda ya no vale (ha caducado o no es de esta carpeta). "
                         "Vuelve a buscar para elegir de nuevo.")
MENSAJE_FALTA_TRADICION = "Elige la tradición antes de continuar: ninguna se da por buena."


def _tradiciones() -> list[tuple[str, str]]:
    return [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]


def _etiqueta_de_tradicion(valor: str) -> str:
    try:
        return _TRADICION_LABEL[ComicTradition(valor)]
    except ValueError:
        return valor


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _fragmento_error(request: Request, texto: str) -> HTMLResponse:
    return _sin_cache(templates.TemplateResponse(request, "_asistente_error.html", {"texto": texto}))


def _pista_de_carpeta(clave: str, tradiciones: list[str]) -> dict | None:
    """«La carpeta X suele guardar: …». Una pista de lectura: no marca ninguna opción."""
    if not tradiciones:
        return None
    return {"carpeta": clave.split("/", 1)[0], "etiquetas": [_etiqueta_de_tradicion(t) for t in tradiciones]}


async def _pagina(request: Request, db: AsyncSession, clave: str, *, manual_abierto: bool = False) -> HTMLResponse:
    try:
        apertura = await DescubrimientoDeGrupo(db, secret=get_settings().secret_key or "").abrir(clave)
    except GrupoNoEncontradoError:
        resp = templates.TemplateResponse(
            request, "asistente_carpeta.html", {"apertura": None, "clave": clave}, status_code=404)
        return _sin_cache(resp)
    return _sin_cache(templates.TemplateResponse(request, "asistente_carpeta.html", {
        "apertura": apertura, "clave": clave,
        "pista": _pista_de_carpeta(clave, apertura.tradiciones_de_la_carpeta),
        "manual_abierto": manual_abierto, "tradiciones": _tradiciones(),
        "titulo": apertura.consulta_propuesta, "anio": "", "error": None, "tradicion_elegida": "",
    }))


@router.get("", response_class=HTMLResponse)
async def abrir(
    request: Request, clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Abre el asistente sobre un grupo. **No consulta ninguna fuente** (ni usa la red)."""
    return await _pagina(request, db, clave)


@router.post("/buscar", response_class=HTMLResponse)
async def buscar(
    request: Request,
    clave: str = Form(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    consulta: str = Form(default="", max_length=200),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Busca en las fuentes, A PETICIÓN y con la consulta que la persona ve. No crea series ni vincula archivos."""
    try:
        r: RespuestaDescubrir = await buscar_a_ritmo(db, clave, consulta)
    except HTTPException as e:
        espera = e.headers.get("Retry-After") if e.headers else None
        return _sin_cache(templates.TemplateResponse(request, "_asistente_resultados.html", {
            "error": str(e.detail), "espera": espera, "clave": clave, "r": None}))
    fuentes = []
    for f in ORDEN_DE_FUENTES:
        estado = r.fuentes.get(f.value, FUENTE_APAGADA)
        chip, texto = _ESTADO_DE_FUENTE.get(estado, ("warn", "estado desconocido"))
        fuentes.append({"nombre": _NOMBRE_FUENTE.get(f.value, f.value), "estado": estado, "chip": chip, "texto": texto})
    consultadas = [f for f in fuentes if f["estado"] in (FUENTE_OK, FUENTE_ERROR)]
    return _sin_cache(templates.TemplateResponse(request, "_asistente_resultados.html", {
        "error": None, "espera": None, "clave": clave, "r": r, "fuentes": fuentes,
        "con_error": [f for f in fuentes if f["estado"] == FUENTE_ERROR],
        "hubo_consulta": bool(consultadas),
        "tradiciones": _tradiciones(),
        "pista": _pista_de_carpeta(clave, tradiciones_de_la_carpeta(clave)),
        "etiqueta_de_tradicion": _etiqueta_de_tradicion,
        "nombre_fuente": lambda v: _NOMBRE_FUENTE.get(v, v),
    }))


@router.get("/manual", response_class=HTMLResponse)
async def manual(
    request: Request, clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    titulo: str = Query(default="", max_length=MAX_TITULO), db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """El formulario a mano. **No consulta fuentes ni necesita sus claves**; solo lee el grupo para precargar el título."""
    if "hx-request" not in request.headers:
        # Un enlace directo (sin htmx): la página completa con el formulario ya abierto, no un fragmento suelto.
        return await _pagina(request, db, clave, manual_abierto=True)
    propuesta = titulo
    try:
        if not propuesta:
            propuesta = (await DescubrimientoDeGrupo(db, secret="").abrir(clave)).consulta_propuesta
    except GrupoNoEncontradoError:
        return _fragmento_error(request, "Esa carpeta ya no tiene registros pendientes.")
    return _sin_cache(templates.TemplateResponse(request, "_asistente_manual.html", {
        "clave": clave, "titulo": propuesta, "anio": "", "error": None, "tradicion_elegida": "",
        "tradiciones": _tradiciones(),
        "pista": _pista_de_carpeta(clave, tradiciones_de_la_carpeta(clave)),
    }))


@router.post("/elegir", response_class=HTMLResponse)
async def elegir(
    request: Request,
    clave: str = Form(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    candidata: str = Form(..., min_length=1, max_length=MAX_TOKEN_CANDIDATA),
    tradition: str | None = Form(default=None, max_length=40),
) -> HTMLResponse:
    """Anota la elección de una candidata de fuente con la tradición que ELIGE la persona. **No crea la serie ni vincula
    archivos**; conserva el grupo de origen. Conectar este camino con el alta es una historia aparte (#189 es solo a mano:
    el formulario a mano envía a la vista previa del alta, no pasa por aquí)."""
    pista = _pista_de_carpeta(clave, tradiciones_de_la_carpeta(clave))
    tradicion = None
    if tradition:
        try:
            tradicion = ComicTradition(tradition)
        except ValueError:
            return _fragmento_error(request, "La tradición elegida no es válida: elige una de la lista.")
    secreto = get_settings().secret_key
    if not secreto:
        return _fragmento_error(request, MENSAJE_SIN_CLAVE)
    firmada = verificar_token_candidata(candidata, clave, secreto)
    if firmada is None:
        return _fragmento_error(request, MENSAJE_BUSQUEDA_CADUCADA)
    if tradicion is None:
        return _sin_cache(templates.TemplateResponse(request, "_asistente_paso.html", {
            "clave": clave, "token": candidata, "sugerida": firmada.tradicion,
            "etiqueta_sugerida": _etiqueta_de_tradicion(firmada.tradicion),
            "error": MENSAJE_FALTA_TRADICION, "tradiciones": _tradiciones(), "pista": pista}))
    return _sin_cache(templates.TemplateResponse(request, "_asistente_eleccion.html", {
        "clave": clave, "origen": "fuente", "fuente": _NOMBRE_FUENTE.get(firmada.fuente, firmada.fuente),
        "titulo": firmada.titulo, "anio": firmada.anio, "tradicion": _TRADICION_LABEL[tradicion],
        "sugerida": _etiqueta_de_tradicion(firmada.tradicion)}))
