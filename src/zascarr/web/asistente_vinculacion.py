# ruff: noqa: E501
"""Asistente «Elegir la serie de una carpeta», segundo tramo (#119, MIT-M3-US02): revisar la selección y los números.

Es la interfaz de `VistaPreviaDeVinculacion` (2c): **no tiene reglas propias** de numeración ni de deduplicación y no
crea otro asistente. Muestra lo que calcula el servicio —estados, motivos, `marcado` / `marcable` /
`incluido_en_token`, totales, páginas y token— y recoge las decisiones EXPLÍCITAS de la persona (archivos marcados y
números escritos).

Qué hace y qué NO hace:
- **Abrir** exige un grupo y una serie LOCAL que existe; una candidata de búsqueda no la sustituye. Todo empieza sin marcar.
- **Cada cambio** (marcar, escribir un número, cambiar de página) vuelve a pedir la vista previa; el token de la
  vista anterior no se reutiliza (la página muestra la revisión como pendiente mientras se renueva).
- **Páginas:** la selección, los números y el token valen solo para la página evaluada. Lo marcado y escrito en otras
  páginas se conserva como **borrador** en el propio formulario (sin base de datos, sin sesión: no sobrevive a recargar la
  página ni a un reinicio), y solo se vuelve a evaluar cuando se regresa a esa página.
- **No confirma** nada: ni vincula, ni crea la serie, ni mueve archivos. La salida es la vista revisada y, si el servicio la
  emite, el token del subconjunto ejecutable de la página. Confirmarlo es el paso siguiente (#120).

Los fallos recuperables se pintan dentro de la página con 200 (htmx no sustituye una respuesta 4xx).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.descubrimiento_grupo import GrupoNoEncontradoError
from zascarr.services.tokens_revision import MAX_CLAVE_GRUPO
from zascarr.services.vinculacion_previa import (
    LIMITE_ARCHIVOS,
    ArchivoAjenoError,
    CursorNoValidoError,
    NumeroNoValidoError,
    RespuestaVinculacion,
    SerieElegidaNoExisteError,
    VistaPreviaDeVinculacion,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/pendientes/carpetas/asistente/vinculacion", tags=["ui"])

RUTA = "/ui/pendientes/carpetas/asistente/vinculacion"

#: Cursor de la primera página en el formulario (el servicio no tiene cursor para ella). Un cursor real es base64 de un
#: JSON que empieza por «WyI», así que no puede coincidir con esta palabra.
INICIO = "inicio"
MAX_PAGINAS_CON_BORRADOR = 100
MAX_IDS_POR_BORRADOR = 1000

MENSAJE_SIN_CLAVE = "ZascArr no tiene clave para firmar lo que ves: reinícialo e inténtalo de nuevo."
MENSAJE_SERIE_NO_VALIDA = ("Hace falta una serie de tu biblioteca para preparar la vinculación. Elige o crea la serie "
                           "primero: una candidata de búsqueda no basta.")
MENSAJE_SERIE_NO_EXISTE = "La serie elegida ya no existe en tu biblioteca. Vuelve a elegirla."
MENSAJE_GRUPO_NO_EXISTE = "Esa carpeta ya no tiene registros pendientes: puede que se hayan vinculado o descartado."
MENSAJE_BORRADOR_NO_VALE = ("No se ha podido reconstruir lo que habías marcado y escrito en esa página, así que se muestra "
                            "sin ello. Ese borrador no cuenta como una revisión válida.")


@dataclass
class Borrador:
    """Lo que la persona ha marcado y escrito en UNA página. Solo decisiones suyas: el servicio las valida cada vez."""
    marcados: list[str] = field(default_factory=list)
    numeros: dict[str, str] = field(default_factory=dict)
    desde: int = 0
    hasta: int = 0

    def vacio(self) -> bool:
        return not self.marcados and not self.numeros

    def a_json(self) -> dict:
        return {"marcados": self.marcados, "numeros": self.numeros, "desde": self.desde, "hasta": self.hasta}


def _es_uuid(valor: object) -> bool:
    try:
        UUID(str(valor))
        return True
    except ValueError:
        return False


def leer_borradores(crudo: str) -> dict[str, Borrador]:
    """El campo oculto `borradores`. Se lee con desconfianza: lo que no tenga la forma exacta se descarta entero (un
    borrador perdido es preferible a uno inventado), y lo que quede solo son ids y textos que el servicio revalida."""
    if not crudo:
        return {}
    try:
        datos = json.loads(crudo)
    except ValueError:
        return {}
    if not isinstance(datos, dict) or len(datos) > MAX_PAGINAS_CON_BORRADOR:
        return {}
    salida: dict[str, Borrador] = {}
    for clave, b in datos.items():
        if not isinstance(clave, str) or not isinstance(b, dict):
            continue
        marcados, numeros = b.get("marcados"), b.get("numeros")
        desde, hasta = b.get("desde", 0), b.get("hasta", 0)
        if not (isinstance(marcados, list) and isinstance(numeros, dict)):
            continue
        if len(marcados) > MAX_IDS_POR_BORRADOR or len(numeros) > MAX_IDS_POR_BORRADOR:
            continue
        if not all(isinstance(i, str) and _es_uuid(i) for i in marcados):
            continue
        if not all(isinstance(k, str) and _es_uuid(k) and isinstance(v, str) for k, v in numeros.items()):
            continue
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (desde, hasta)):
            continue
        salida[clave] = Borrador(sorted(set(marcados)), dict(numeros), desde, hasta)
    return salida


def leer_estado_de_la_pagina(formulario) -> Borrador:
    """Lo que la persona ha dejado en la página que ve: los archivos marcados y SOLO los números que ha tocado.

    Un número cuenta como suyo si el campo ya venía de ella (`numero_origen = persona`) o si ha cambiado respecto de
    lo que se le propuso (`numero_base`). Lo demás es la propuesta del nombre y no se reenvía como si lo hubiera
    escrito: así no cambia su origen en la vista siguiente. Vaciar el campo lo elimina de la propuesta."""
    marcados = sorted({v for v in formulario.getlist("marcar") if isinstance(v, str) and _es_uuid(v)})
    numeros: dict[str, str] = {}
    for nombre in formulario:
        if not nombre.startswith("numero:"):
            continue
        fid = nombre[len("numero:"):]
        if not _es_uuid(fid):
            continue
        valor = str(formulario.get(nombre, "")).strip()
        base = str(formulario.get(f"numero_base:{fid}", "")).strip()
        origen = str(formulario.get(f"numero_origen:{fid}", ""))
        if origen == "persona" or valor != base:
            numeros[fid] = valor
    return Borrador(marcados, numeros)


def separar_numeros_no_validos(numeros: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """(números que el servicio aceptará, ids con un número que no cumple su regla). Se usa la regla del servicio, no
    una copia: un número demasiado largo o con saltos de línea no se aplica y se avisa, sin perder el resto."""
    buenos: dict[str, str] = {}
    malos: list[str] = []
    for fid, valor in numeros.items():
        try:
            VistaPreviaDeVinculacion._numero_valido(valor)
        except NumeroNoValidoError:
            malos.append(fid)
        else:
            buenos[fid] = valor
    return buenos, malos


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _contexto_de_la_revision(r: RespuestaVinculacion, cursor_actual: str, otros: dict[str, Borrador],
                             avisos: list[str]) -> dict:
    por_id = {a.id: a for a in r.archivos}
    pendientes = [
        {"clave": k, "desde": b.desde, "hasta": b.hasta, "n_marcados": len(b.marcados), "n_numeros": len(b.numeros)}
        for k, b in sorted(otros.items(), key=lambda kv: (kv[1].desde, kv[0])) if not b.vacio()]
    incluidos = [a for a in r.archivos if a.incluido_en_token]
    excluidos = [a for a in r.archivos if a.marcado and not a.marcable]
    return {
        "r": r, "cursor_actual": cursor_actual or INICIO, "inicio": INICIO, "avisos": avisos,
        "nombres_de": lambda ids: [por_id[i].nombre for i in ids if i in por_id],
        "borradores_json": json.dumps({k: b.a_json() for k, b in otros.items() if not b.vacio()}, ensure_ascii=False),
        "pendientes": pendientes, "incluidos": incluidos, "excluidos": excluidos, "limite": LIMITE_ARCHIVOS,
    }


async def _revisar(request: Request, db: AsyncSession, clave: str, series_id: str, *, estado: Borrador,
                   cursor: str, otros: dict[str, Borrador], avisos: list[str], pagina_completa: bool) -> HTMLResponse:
    """Pide la vista previa al servicio y la pinta. Un fallo recuperable se explica; nunca deja un token a la vista."""
    secreto = get_settings().secret_key
    plantilla = "asistente_vinculacion.html" if pagina_completa else "_vinculacion_revision.html"
    base = {"clave": clave, "series_id": series_id}
    if not secreto:
        return _sin_cache(templates.TemplateResponse(request, plantilla, {**base, "r": None, "error": MENSAJE_SIN_CLAVE}))
    if not clave or not _es_uuid(series_id):
        return _sin_cache(templates.TemplateResponse(
            request, plantilla, {**base, "r": None, "error": MENSAJE_SERIE_NO_VALIDA}))
    servicio = VistaPreviaDeVinculacion(db, secret=secreto)
    numeros, malos = separar_numeros_no_validos(estado.numeros)
    avisos = list(avisos)
    if malos:
        avisos.append(f"{len(malos)} número(s) no se han aplicado: tienen más de 20 caracteres o saltos de línea.")
    try:
        r = await servicio.previsualizar(
            clave, UUID(series_id), numeros=numeros, marcados=set(estado.marcados), cursor=cursor or None)
    except GrupoNoEncontradoError:
        return _sin_cache(templates.TemplateResponse(
            request, plantilla, {**base, "r": None, "error": MENSAJE_GRUPO_NO_EXISTE}))
    except SerieElegidaNoExisteError:
        return _sin_cache(templates.TemplateResponse(
            request, plantilla, {**base, "r": None, "error": MENSAJE_SERIE_NO_EXISTE}))
    except (ArchivoAjenoError, CursorNoValidoError):
        # Lo que había en esa página ya no encaja con el grupo (se vinculó, se movió…): se muestra la página limpia y
        # se dice. El borrador no se presenta como una revisión válida.
        try:
            r = await servicio.previsualizar(clave, UUID(series_id))
        except (GrupoNoEncontradoError, SerieElegidaNoExisteError):
            return _sin_cache(templates.TemplateResponse(
                request, plantilla, {**base, "r": None, "error": MENSAJE_GRUPO_NO_EXISTE}))
        avisos.append(MENSAJE_BORRADOR_NO_VALE)
        cursor = ""
    ctx = _contexto_de_la_revision(r, cursor, otros, avisos)
    return _sin_cache(templates.TemplateResponse(request, plantilla, {**base, **ctx, "error": None}))


@router.get("", response_class=HTMLResponse)
async def abrir(
    request: Request,
    clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    series_id: str = Query(default="", max_length=64),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Abre la preparación para un grupo y una serie LOCAL. Todo empieza sin marcar; no escribe nada."""
    return await _revisar(request, db, clave, series_id, estado=Borrador(), cursor="", otros={}, avisos=[],
                          pagina_completa=True)


@router.post("/revisar", response_class=HTMLResponse)
async def revisar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Renueva la vista previa tras un cambio (marcar, escribir un número, cambiar de página). No confirma nada."""
    f = await request.form()
    clave = str(f.get("clave", ""))
    series_id = str(f.get("series_id", ""))
    cursor_actual = str(f.get("cursor_actual", INICIO))
    cursor_actual = "" if cursor_actual == INICIO else cursor_actual
    otros = leer_borradores(str(f.get("borradores", "")))
    estado = leer_estado_de_la_pagina(f)
    estado.desde, estado.hasta = _entero(f.get("pagina_desde")), _entero(f.get("pagina_hasta"))

    destino = str(f.get("ir_a", "")) or (cursor_actual or INICIO)
    destino = "" if destino == INICIO else destino
    if destino != cursor_actual:
        # Se cambia de página: lo de esta queda como borrador y se recupera el de la de destino, si lo hay.
        if not estado.vacio():
            otros[cursor_actual] = estado
        else:
            otros.pop(cursor_actual, None)
        estado = otros.pop(destino, Borrador())
    else:
        otros.pop(cursor_actual, None)
    # Sin htmx (un envío normal del formulario) se devuelve la página entera, no un fragmento suelto.
    return await _revisar(request, db, clave, series_id, estado=estado, cursor=destino, otros=otros, avisos=[],
                          pagina_completa="hx-request" not in request.headers)


def _entero(valor: object) -> int:
    try:
        n = int(str(valor))
    except ValueError:
        return 0
    return n if n >= 0 else 0
