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
- **Revisar no confirma nada**: ni vincula, ni crea la serie, ni mueve archivos. La salida es la vista revisada y, si el
  servicio la emite, el token del subconjunto ejecutable de la página.
- **Confirmar (#120)** es una acción APARTE y explícita (`POST /confirmar`): envía al servicio el token de esa página, y solo
  ese, muestra el informe que devuelve y, si falla, dice qué se sabe y qué no. Vincula en su sitio: no mueve ni renombra
  archivos, no crea la serie y no resuelve nada por la persona. Reutiliza `ejecutar_vinculacion` (la misma traducción de
  fallos que `POST /api/revision/vinculacion`) y la recuperación ya fusionada (#116/#117): repetir el mismo token devuelve
  el mismo informe.

- **Marcar y desmarcar todos (U20)**: son DOS acciones de `POST /revisar` (`accion=marcar_todos|desmarcar_todos`). El
  servidor evalúa la página, marca SOLO los archivos que el servicio dice que se pueden marcar —nunca los bloqueados, nunca
  los de otras páginas— y no elige entre números repetidos: los que comparten número con otro se dejan sin marcar y se
  cuentan. El recuento sale de ese cálculo, no del navegador. No hay JavaScript propio (ADR 0005, decisión 3).

Los fallos recuperables se pintan dentro de la página con 200 (htmx no sustituye una respuesta 4xx).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.revision import ejecutar_vinculacion
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import Series
from zascarr.services.descubrimiento_grupo import GrupoNoEncontradoError
from zascarr.services.tokens_revision import (
    MAX_CLAVE_GRUPO,
    MAX_TOKEN_VINCULACION,
    verificar_token_vinculacion,
)
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
logger = structlog.get_logger()

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


ACCIONES = ("marcar_todos", "desmarcar_todos")

#: Los impedimentos del servicio (códigos) dichos en llano, para «Otros motivos». Un código que no esté aquí NO se enseña:
#: nunca sale un identificador interno (U20, criterio 4).
MOTIVOS_LEGIBLES: dict[str, str] = {
    "ya_vinculado": "ya está vinculado a una serie",
    "en_curso": "tiene una asignación en curso",
    "origen_no_encontrado": "no hay ningún archivo en su ruta registrada",
    "origen_no_verificable": "no se pudo comprobar el archivo",
    "requiere_numero": "falta el número",
    "numero_repetido_en_el_grupo": "otro archivo marcado tiene el mismo número",
    "colision_de_edicion": "ese número ya existe como otra edición",
    "numero_ambiguo": "la serie tiene más de un número así",
    "numero_ya_existe": "ese número ya tiene un archivo vinculado",
}


def motivos_legibles(codigos: list[str]) -> list[str]:
    return [MOTIVOS_LEGIBLES[c] for c in codigos if c in MOTIVOS_LEGIBLES]


#: El formato de una publicación (`IssueFormat`) dicho como lo dice el coleccionista. El texto del servicio lo cita por
#: su valor interno («otra edición (single_issue)»); aquí se traduce, no se cambia el contrato.
FORMATOS_LEGIBLES: dict[str, str] = {
    "single_issue": "grapa", "trade_paperback": "tomo en rústica", "hardcover": "tomo en tapa dura",
    "omnibus": "ómnibus", "graphic_novel": "novela gráfica", "album": "álbum", "manga_tankobon": "tomo de manga",
    "digital": "digital",
}
_FORMATO_EN_TEXTO = re.compile(r"\b(" + "|".join(FORMATOS_LEGIBLES) + r")\b")


def texto_legible(texto: str | None) -> str:
    """El texto del servicio sin identificadores internos de formato. El resto del texto no se toca."""
    return _FORMATO_EN_TEXTO.sub(lambda m: FORMATOS_LEGIBLES[m.group(1)], texto or "")


def texto_de_la_pagina(pagina) -> str | None:
    """El detalle de la paginación, dicho aquí con los números del servicio. No se usa `pagina.texto` del servicio:
    es un texto del contrato (también lo lee la API) y habla del «token»."""
    if not (pagina.hay_mas or pagina.cursor):
        return None
    return (f"Este grupo tiene {pagina.en_el_grupo} archivos; esta página muestra del {pagina.desde} al "
            f"{pagina.hasta} (máximo {pagina.maximo} por página, por nombre). Lo que marques y los números que "
            "escribas valen solo para esos archivos.")


def elegir_para_marcar_todos(r: RespuestaVinculacion) -> tuple[list[str], int]:
    """(ids que se marcan, cuántos se dejan sin marcar por compartir número). Solo se marca lo que el servicio da por
    `marcable`. Si un archivo comparte número con otro que ya está marcado o que también se marcaría, NO se marca ninguno
    de ellos por la persona: marcar los dos los bloquearía a ambos, y elegir uno sería decidir por ella."""
    ya = {a.id for a in r.archivos if a.marcado}
    candidatos = [a for a in r.archivos if a.marcable and not a.marcado]
    conjunto = ya | {a.id for a in candidatos}
    elegidos: list[str] = []
    repetidos = 0
    for a in candidatos:
        if any(otro in conjunto for otro in a.repetido_con):
            repetidos += 1
        else:
            elegidos.append(a.id)
    return elegidos, repetidos


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


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
                             avisos: list[str], accion: dict | None = None) -> dict:
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
        "motivos_legibles": motivos_legibles, "texto_de_la_pagina": texto_de_la_pagina(r.pagina), "accion": accion,
        "texto_legible": texto_legible,
        "hay_que_marcar": any(a.marcable and not a.marcado for a in r.archivos),
        "hay_marcados": any(a.marcado for a in r.archivos),
    }


async def _revisar(request: Request, db: AsyncSession, clave: str, series_id: str, *, estado: Borrador,
                   cursor: str, otros: dict[str, Borrador], avisos: list[str], pagina_completa: bool,
                   accion: str = "") -> HTMLResponse:
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
    resultado_accion: dict | None = None
    try:
        if accion == "desmarcar_todos":
            quitadas = len(estado.marcados)
            estado.marcados = []
            resultado_accion = {"accion": accion, "n": quitadas, "tipo": "info" if quitadas else "nota", "texto": (
                f"Se quitaron las marcas de {_plural(quitadas, 'archivo', 'archivos')} de esta página."
                if quitadas else "No había ningún archivo marcado en esta página.")}
        elif accion == "marcar_todos":
            # Se evalúa la página como está y se marca solo lo que el servicio da por marcable (ni bloqueados ni otras
            # páginas); después se vuelve a evaluar con esas marcas, que es lo que se pinta.
            antes = await servicio.previsualizar(
                clave, UUID(series_id), numeros=numeros, marcados=set(estado.marcados), cursor=cursor or None)
            elegidos, repetidos = elegir_para_marcar_todos(antes)
            estado.marcados = sorted(set(estado.marcados) | set(elegidos))
        r = await servicio.previsualizar(
            clave, UUID(series_id), numeros=numeros, marcados=set(estado.marcados), cursor=cursor or None)
        if accion == "marcar_todos":
            # El recuento sale de la evaluación FINAL del servicio, no de lo que se pretendía marcar: una marca que
            # acabara bloqueada no se cuenta como «se pueden vincular» ni se deja caer en silencio.
            vinculables = {a.id for a in r.archivos if a.incluido_en_token}
            logradas = [i for i in elegidos if i in vinculables]
            perdidas = len(elegidos) - len(logradas)
            partes = [f"Se marcaron {_plural(len(logradas), 'archivo', 'archivos')} que se pueden vincular."
                      if logradas else "No hay ningún archivo más que se pueda marcar en esta página."]
            if repetidos:
                partes.append(f"{_plural(repetidos, 'archivo comparte', 'archivos comparten')} el número con otro y "
                              "no se marcó: marca tú el que quieras de cada grupo.")
            if perdidas:
                partes.append(f"{_plural(perdidas, 'archivo marcado cambió', 'archivos marcados cambiaron')} al "
                              "revisarlos y ya no se pueden vincular: mira el motivo de cada uno.")
            resultado_accion = {"accion": accion, "n": len(logradas), "repetidos": repetidos,
                                "tipo": "ok" if logradas and not perdidas else "amber" if perdidas else "info",
                                "texto": " ".join(partes)}
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
        resultado_accion = None            # la página que se pidió ya no vale: no se cuenta una acción sobre otra
    ctx = _contexto_de_la_revision(r, cursor, otros, avisos, resultado_accion)
    return _sin_cache(templates.TemplateResponse(request, plantilla, {**base, **ctx, "error": None}))


@router.get("", response_class=HTMLResponse)
async def abrir(
    request: Request,
    clave: str = Query(..., min_length=1, max_length=MAX_CLAVE_GRUPO),
    series_id: str = Query(default="", max_length=64),
    cursor: str = Query(default="", max_length=2000),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Abre la preparación para un grupo y una serie LOCAL. Todo empieza sin marcar; no escribe nada. `cursor` (opcional)
    es la posición de la página a la que se vuelve tras una confirmación: un cursor que no vale da la primera página."""
    return await _revisar(request, db, clave, series_id, estado=Borrador(), cursor=cursor, otros={}, avisos=[],
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

    # Una acción masiva vale para la página que se ve; si a la vez se cambia de página, no se aplica.
    accion = str(f.get("accion", ""))
    accion = accion if accion in ACCIONES and not f.get("ir_a") else ""
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
                          pagina_completa="hx-request" not in request.headers, accion=accion)


def _entero(valor: object) -> int:
    try:
        n = int(str(valor))
    except ValueError:
        return 0
    return n if n >= 0 else 0


# ── Confirmar (#120) ─────────────────────────────────────────────────────────────────────────────

#: Qué pasó con cada archivo omitido y qué se puede hacer con lo que el contrato ofrece (revisar de nuevo). El servicio
#: devuelve solo el CÓDIGO; el texto es presentación. Un código que no esté aquí no se inventa: sale con su código.
TEXTO_DE_MOTIVO: dict[str, str] = {
    "archivo_inexistente": "El registro ya no existe: puede que se haya borrado o vinculado desde otro sitio.",
    "descartado": "Lo descartaste de la bandeja de pendientes, así que no se vincula.",
    "ya_vinculado_a_otro": "Ya estaba vinculado a otro número: no se cambia por ti.",
    "en_curso": "Tiene una asignación en curso: espera a que termine y revísalo de nuevo.",
    "origen_no_encontrado": "En la ruta registrada ya no hay ningún archivo. Si el disco no está montado, no es que haya desaparecido.",
    "origen_no_verificable": "No se pudo comprobar el archivo (permisos, lectura o disco). No significa que haya desaparecido.",
    "cambio_desde_la_vista_previa": "Cambió (tamaño o fecha) mientras revisabas: revísalo de nuevo para ver su estado actual.",
    "colision_de_edicion": "Ese número ya existe en la serie como otra edición: no se elige una por ti.",
    "numero_ambiguo": "La serie tiene más de un número así (volúmenes distintos): no se elige uno por ti.",
    "numero_ya_existe": "Ese número ya tiene un archivo vinculado en la serie: no se pisa.",
}
TEXTO_DE_MOTIVO_DESCONOCIDO = "No se pudo vincular. Revísalo de nuevo para ver su estado actual."

#: El texto de cada fallo de la confirmación, EN LLANO y por código. Los mensajes del contrato (`token`, «operación»…) son
#: de la API y no se enseñan aquí. Cada texto dice qué se sabe y qué no, y no afirma «no se ha cambiado nada» donde
#: no consta. Un código que no esté aquí sale con el texto genérico, sin su identificador.
MENSAJES_DE_FALLO: dict[str, str] = {
    "token_caducado": "La preparación caducó y no llegó a aplicarse: no se ha vinculado nada. Vuelve a revisar los "
                      "archivos y prepárala de nuevo.",
    "token_invalido": "Esta preparación no es válida, así que no se ha vinculado nada. Vuelve a revisar los archivos.",
    "la_serie_ya_no_existe": "La serie ya no existe en tu biblioteca, así que no se ha vinculado nada. Vuelve a "
                             "elegir la serie.",
    "conflicto_de_bloqueo": "Otra operación coincidió con esta y no se ha vinculado nada todavía. Puedes reintentarlo.",
    "resultado_incierto": "No se sabe si se llegó a vincular: no lo des por hecho ni por fallido. Pulsa «Comprobar el "
                          "resultado»: si ya se vinculó, verás el mismo resultado y no se duplica nada; si no, se "
                          "vinculará ahora.",
    "error_inesperado": "No se pudo completar y no se ha cambiado nada. Inténtalo de nuevo.",
}
MENSAJE_DE_FALLO_DESCONOCIDO = "No se pudo vincular. Vuelve a revisar los archivos para ver su estado actual."
MENSAJE_CADUCADO_SIN_INFORME = (
    "La preparación caducó y ya no se conserva su resultado: no se sabe si llegó a vincularse. Vuelve a revisar los "
    "archivos para ver su estado actual antes de decidir nada.")

#: Un fallo de la confirmación → (título, ¿es definitivo?, ¿se puede repetir con el MISMO token sin riesgo?). «Resultado
#: desconocido» (`resultado_incierto`) y «definitivo» se distinguen; nunca se dice que se completó sin que el servicio lo
#: haya confirmado. Repetir el mismo token es seguro: si ya se aplicó devuelve el mismo informe, si no, lo aplica.
FALLOS: dict[str, tuple[str, bool, bool]] = {
    "resultado_incierto": ("No se sabe si se llegó a vincular", False, True),
    "conflicto_de_bloqueo": ("Otra operación coincidió y no se vinculó nada todavía", False, True),
    "error_inesperado": ("No se pudo completar y no se ha cambiado nada", False, True),
    "token_caducado": ("La preparación caducó", True, False),
    "token_invalido": ("La preparación no es válida", True, False),
    "la_serie_ya_no_existe": ("La serie ya no existe", True, False),
}


def _contexto_de_la_confirmacion(token: str) -> dict:
    """Serie y grupo SALEN DEL TOKEN firmado (no de campos que reenvíe el navegador). Con el token inválido no hay nada."""
    secreto = get_settings().secret_key
    firmado = verificar_token_vinculacion(token, secreto, ignorar_caducidad=True) if secreto else None
    if firmado is None:
        return {"clave": "", "series_id": ""}
    return {"clave": firmado.clave, "series_id": firmado.series_id}


async def _titulo_de_la_serie(db: AsyncSession, series_id: str) -> str | None:
    if not _es_uuid(series_id):
        return None
    fila = (await db.execute(select(Series.title, Series.start_year).where(Series.id == UUID(series_id)))).first()
    if fila is None:
        return None
    return f"{fila[0]} ({fila[1]})" if fila[1] else fila[0]


@router.post("/confirmar", response_class=HTMLResponse)
async def confirmar(
    request: Request,
    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_VINCULACION),
    cursor_actual: str = Form(default=INICIO, max_length=2000),
    pagina_desde: str = Form(default="", max_length=10),
    pagina_hasta: str = Form(default="", max_length=10),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Confirma el lote de UNA página con SU token. Es la única acción de este asistente que escribe, y solo ocurre
    aquí: abrir, revisar o paginar no la ejecutan. El token se envía tal cual al servicio: no se reconstruye nada."""
    contexto = _contexto_de_la_confirmacion(token)
    base = {**contexto, "cursor_actual": cursor_actual, "inicio": INICIO,
            "pagina": f"{_entero(pagina_desde)}–{_entero(pagina_hasta)}" if _entero(pagina_hasta) else None}
    plantilla = "asistente_vinculacion.html" if "hx-request" not in request.headers else "_vinculacion_resultado.html"
    base["titulo_serie"] = await _titulo_de_la_serie(db, contexto["series_id"])
    try:
        r = await ejecutar_vinculacion(db, token)
    except HTTPException as e:
        d = e.detail if isinstance(e.detail, dict) else {"codigo": "error_inesperado", "mensaje": str(e.detail)}
        codigo = str(d.get("codigo", "error_inesperado"))
        titulo, definitivo, repetible = FALLOS.get(codigo, ("No se pudo vincular", True, False))
        mensaje = (MENSAJE_CADUCADO_SIN_INFORME if codigo == "token_caducado" and d.get("puede_haberse_aplicado")
                   else MENSAJES_DE_FALLO.get(codigo, MENSAJE_DE_FALLO_DESCONOCIDO))
        if codigo not in MENSAJES_DE_FALLO:
            logger.warning("vinculacion.fallo_sin_texto", codigo=codigo)
        return _sin_cache(templates.TemplateResponse(request, plantilla, {
            **base, "resultado": True, "fallo": {"codigo": codigo, "titulo": titulo, "mensaje": mensaje,
                                                   "definitivo": definitivo, "repetible": repetible}, "token": token,
            "r": None, "error": None}))
    informe = r.resultado
    nombres = r.presentacion.nombres_actuales
    grupos: dict[str, list[dict]] = {"vinculado": [], "ya_estaba_vinculado": [], "omitido": []}
    for a in informe.archivos:
        grupos[a.estado].append({
            "id": a.id, "nombre": nombres.get(a.id, "(archivo que ya no está en la lista)"), "numero": a.numero,
            "motivo": a.motivo, "creado": a.issue_creado,
            "texto": (TEXTO_DE_MOTIVO.get(a.motivo, TEXTO_DE_MOTIVO_DESCONOCIDO)
                      if a.estado == "omitido" and a.motivo else None)})
        if a.estado == "omitido" and a.motivo and a.motivo not in TEXTO_DE_MOTIVO:
            logger.warning("vinculacion.motivo_sin_texto", motivo=a.motivo)
    return _sin_cache(templates.TemplateResponse(request, plantilla, {
        **base, "resultado": True, "fallo": None, "r": r, "informe": informe, "grupos": grupos, "error": None,
        "token": token}))
