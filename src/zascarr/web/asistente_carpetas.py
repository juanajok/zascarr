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

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.revision import buscar_a_ritmo
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.alta_serie import AltaDeSerie
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
from zascarr.services.review import ReviewService
from zascarr.services.revision_carpetas import RevisionCarpetas
from zascarr.services.tokens_revision import (
    MAX_CLAVE_GRUPO,
    MAX_TITULO,
    MAX_TOKEN_CANDIDATA,
    verificar_token_candidata,
)
from zascarr.web.discovery import preparar_vista_previa
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
#: U19 (ficha §6.4). Volver nunca lanza una búsqueda: lo que no se puede reconstruir sin consultar fuentes se dice.
MENSAJE_ELECCION_CADUCADA = ("Lo que elegiste caducó (se conserva 15 minutos) o no es de esta carpeta. Vuelve a buscar: no se "
                             "hace sola, porque consultaría las fuentes.")
MENSAJE_TRADICION_NO_VALE = "La tradición no es válida: vuelve a elegirla."
MENSAJE_DECISION_YA_NO_VALE = ("Lo que habías decidido sobre las series parecidas ya no vale, porque esas series han cambiado. "
                               "Decide de nuevo.")
MENSAJE_FALTAN_DATOS = "Faltan los datos para preparar el alta: vuelve a elegir la serie."


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


async def _pagina(request: Request, db: AsyncSession, clave: str, *, manual_abierto: bool = False,
                  consulta: str = "") -> HTMLResponse:
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
        "consulta_escrita": consulta,
    }))


@router.get("", response_class=HTMLResponse)
async def abrir(
    request: Request, clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    consulta: str = Query(default="", max_length=200), db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Abre el asistente sobre un grupo. **No consulta ninguna fuente** (ni usa la red). `consulta` (U19, al volver) solo
    rellena el campo de búsqueda: nunca la ejecuta."""
    return await _pagina(request, db, clave, consulta=consulta)


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
    consulta: str = Form(default="", max_length=200),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Anota la elección de una candidata de fuente con la tradición que ELIGE la persona y enseña la VISTA PREVIA del alta
    (U19, D2). **Elegir no crea la serie ni vincula archivos**: la vista previa es de solo lectura y crear es su botón, con su
    propio token; vincular es otro paso con su propia revisión y confirmación. Conserva el grupo de origen."""
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
            "clave": clave, "token": candidata, "sugerida": firmada.tradicion, "consulta": consulta,
            "etiqueta_sugerida": _etiqueta_de_tradicion(firmada.tradicion) if firmada.tradicion else None,
            "procedencia": firmada.procedencia,
            "error": MENSAJE_FALTA_TRADICION, "tradiciones": _tradiciones(), "pista": pista}))
    plantilla, contexto = await preparar_vista_previa(
        request, db, candidata=candidata, titulo=None, anio=None, clave=clave, tradition=tradicion, consulta=consulta)
    if plantilla == "_fragmento_sin_clave":
        return _fragmento_error(request, MENSAJE_SIN_CLAVE)
    return _sin_cache(templates.TemplateResponse(request, "_asistente_eleccion.html", {
        **contexto, "plantilla": plantilla, "clave": clave, "origen": "fuente", "candidata": candidata,
        "tradition": tradicion.value, "consulta": consulta,
        "eleccion_fuente": _NOMBRE_FUENTE.get(firmada.fuente, firmada.fuente), "eleccion_titulo": firmada.titulo,
        "eleccion_anio": firmada.anio, "eleccion_tradicion": _TRADICION_LABEL[tradicion],
        "eleccion_sugerida": _etiqueta_de_tradicion(firmada.tradicion) if firmada.tradicion else None}))


# ── U19: volver sin perder la elección (ficha §6.4) ──────────────────────────────────────────────

def _pagina_alta(request: Request, **ctx) -> HTMLResponse:
    return _sin_cache(templates.TemplateResponse(request, "asistente_alta.html", ctx))


@router.get("/alta", response_class=HTMLResponse)
async def alta_previa(
    request: Request,
    clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    candidata: str | None = Query(default=None, max_length=MAX_TOKEN_CANDIDATA),
    titulo: str | None = Query(default=None, max_length=MAX_TITULO),
    anio: str | None = Query(default=None, max_length=100),
    tradition: str = Query(default="", max_length=40),
    consulta: str = Query(default="", max_length=200),
    decision: str = Query(default="", max_length=20),
    serie_id: str = Query(default="", max_length=64),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Reconstruye la VISTA PREVIA del alta de una elección (candidata firmada o datos a mano). **Solo lectura**: no crea
    nada, no consulta fuentes y se puede recargar. La candidata firmada es la única referencia a lo elegido; si caducó o no es
    de esta carpeta se dice y se ofrece volver a buscar (sin buscar). Crear la serie sigue siendo el botón de la vista previa.

    Conserva también la decisión ya tomada entre series parecidas («es esta» o «crear otra»), **revalidándola**: si las parecidas
    cambiaron y ya no vale, se dice y se vuelve a la pantalla de decidir; nunca se da por buena en silencio."""
    base = {"clave": clave, "consulta": consulta}
    secreto = get_settings().secret_key
    if not secreto:
        return _pagina_alta(request, **base, aviso=MENSAJE_SIN_CLAVE)
    try:
        elegida = ComicTradition(tradition)
    except ValueError:
        return _pagina_alta(request, **base, aviso=MENSAJE_TRADICION_NO_VALE)
    if candidata:
        if verificar_token_candidata(candidata, clave, secreto) is None:
            return _pagina_alta(request, **base, aviso=MENSAJE_ELECCION_CADUCADA)
    elif not (titulo or "").strip():
        return _pagina_alta(request, **base, aviso=MENSAJE_FALTAN_DATOS)
    decidida = decision if decision in ("reutilizar", "crear_igualmente") else None
    elegida_id = _uuid_o_none(serie_id) if decidida == "reutilizar" else None
    if decidida == "reutilizar" and elegida_id is None:
        decidida = None
    plantilla, contexto = await preparar_vista_previa(
        request, db, candidata=candidata, titulo=titulo, anio=anio, clave=clave, tradition=elegida,
        decision=decidida, serie_id=elegida_id, consulta=consulta)
    aviso_decision = None
    if decidida and plantilla == "_alta_error.html" and contexto.get("codigo") == "decision_invalida":
        plantilla, contexto = await preparar_vista_previa(
            request, db, candidata=candidata, titulo=titulo, anio=anio, clave=clave, tradition=elegida, consulta=consulta)
        aviso_decision = MENSAJE_DECISION_YA_NO_VALE
    if plantilla == "_fragmento_sin_clave":
        return _pagina_alta(request, **base, aviso=MENSAJE_SIN_CLAVE)
    return _pagina_alta(request, **{**base, **contexto}, plantilla=plantilla, aviso_decision=aviso_decision)


def _uuid_o_none(texto: str | None) -> UUID | None:
    try:
        return UUID(texto) if texto else None
    except ValueError:
        return None


@router.get("/alta/resultado", response_class=HTMLResponse)
async def alta_resultado(
    request: Request,
    clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    series_id: str = Query(default="", max_length=64),
    operacion: str = Query(default="", max_length=64),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Lo que CONSTA de un alta al volver a ella. **Solo lectura**: no repite el alta ni la deshace, y no ofrece «Deshacer».
    Solo afirma lo comprobable: una fila de `alta_operaciones` existe únicamente si el alta CREÓ la serie (reutilizar no
    escribe nada y el comprobante se purga), así que sin ella solo se dice que la serie existe."""
    secreto = get_settings().secret_key
    sid = _uuid_o_none(series_id)
    hechos = None
    if secreto and sid is not None:
        hechos = await AltaDeSerie(db, secret=secreto).hechos_del_alta(sid, _uuid_o_none(operacion))
    grupo = await RevisionCarpetas(db).archivos_del_grupo(clave)
    pendientes = None if grupo is None else len(grupo[1])
    return _sin_cache(templates.TemplateResponse(request, "asistente_alta_resultado.html", {
        "clave": clave, "series_id": series_id, "hechos": hechos, "pendientes": pendientes}))


@router.get("/locales", response_class=HTMLResponse)
async def locales(
    request: Request,
    clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    q: str = Query(default="", max_length=200),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Series que ya tienes en tu biblioteca y se llaman como `q` (U19, D1). **Solo lectura y solo la base local**: no
    consulta ninguna fuente y no crea nada. Nada llega preseleccionado, ni siquiera con un único resultado: elegir una es un
    enlace a la revisión, que no vincula nada hasta que se confirma. Muestra título, año y tradición, que ya vienen en la misma
    consulta (sin consultas por fila)."""
    texto = q.strip()
    encontradas = await ReviewService(db).search_series(texto) if texto else []
    return _sin_cache(templates.TemplateResponse(request, "_asistente_locales.html", {
        "clave": clave, "q": texto, "series": [
            {"series_id": str(x.id), "titulo": x.title, "anio": x.start_year,
             "tradicion": _TRADICION_LABEL.get(x.tradition, str(x.tradition))} for x in encontradas]}))
