"""
Blindaje legal — LEGAL.md, aceptación y la dependencia que la exige.

Solo gatea lo que de verdad dispara red/descarga hacia fuentes externas
de contenido: crear/reintentar un item de wishlist y el ciclo del
orquestador (ver orchestrator.py). Biblioteca, pendientes y fichas de
serie NO llevan este gate — el riesgo legal real es "facilitar
descargas", no "ver tu propia biblioteca ya organizada" (ver LEGAL.md).

Sin modelo de usuario (herramienta de un solo operador): el estado de
aceptación es único para todo el sistema, no por persona.

legal_version no es una constante que haya que recordar subir a mano
cada vez que cambie LEGAL.md — es el hash del propio fichero. Editar
LEGAL.md invalida automáticamente cualquier aceptación anterior.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

import markdown
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import LegalAcknowledgment

LEGAL_MD_PATH = Path(__file__).parent.parent / "LEGAL.md"


@lru_cache
def _legal_md_text() -> str:
    return LEGAL_MD_PATH.read_text(encoding="utf-8")


@lru_cache
def current_legal_version() -> str:
    """Hash del LEGAL.md empaquetado con la app — cambia solo si el
    fichero cambia, nunca hay que sincronizarlo a mano con una
    constante. Cacheado: el fichero no cambia sin reiniciar el proceso."""
    return hashlib.sha256(_legal_md_text().encode("utf-8")).hexdigest()[:16]


def render_legal_html() -> str:
    return markdown.markdown(_legal_md_text(), extensions=["tables"])


async def get_acknowledgment(db: AsyncSession) -> LegalAcknowledgment | None:
    return (await db.execute(
        select(LegalAcknowledgment)
        .where(LegalAcknowledgment.legal_version == current_legal_version())
        .order_by(LegalAcknowledgment.accepted_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def is_acknowledged(db: AsyncSession) -> bool:
    return await get_acknowledgment(db) is not None


async def acknowledge(db: AsyncSession) -> LegalAcknowledgment:
    ack = LegalAcknowledgment(
        accepted_at=datetime.now(UTC),
        legal_version=current_legal_version(),
    )
    db.add(ack)
    await db.flush()
    return ack


RETORNO_LEGAL_POR_DEFECTO = "/ui/biblioteca"
_MAX_RETORNO_LEGAL = 2000

#: Páginas que pueden ser destino de vuelta tras aceptar el aviso, con los
#: parámetros de estado de la vista que su ruta GET lee de verdad. Lista
#: CERRADA (benchmark §13, GitLab `Users::TermsController#redirect_path`):
#: solo las páginas que alojan un control gateado o un enlace directo al aviso.
#: Una página nueva añade su entrada y su prueba; mientras no esté, el destino
#: cae al respaldo (nunca se abre una redirección externa). `/ui/biblioteca`
#: NO es una entrada: es la constante de respaldo.
#: No se reutiliza `PARAMETROS_DE_QUERY` (tests/test_log_acceso.py): es el
#: inventario del registro de acceso, no el contrato de este retorno.
_RETORNOS_LEGALES: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    # Deseados: hoy la búsqueda vive en el DOM, no en la URL (`index` no lee `q`).
    (re.compile(r"/ui/wishlist"), frozenset()),
    # Descubrir: ahí se renderiza el «Añadir a deseados» del alta.
    (re.compile(r"/ui/descubrir"), frozenset({"q"})),
    (re.compile(r"/ui/descubrir/identificador"), frozenset({"identificador"})),
    # Mejoras: solo el estado de paginación; `guardado`/`error` son banderas de
    # un solo uso que repintarían un éxito falso al volver.
    (re.compile(r"/ui/mejoras"), frozenset({"pagina"})),
    # Ficha de serie: enlaces directos de seguimiento y política, más el
    # `volver` anidado de BL-IT03 (su valor lo valida la propia ficha).
    (re.compile(
        r"/ui/series/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), frozenset({"volver"})),
    # Ficha de número: ahí está el control «buscar mejor edición».
    (re.compile(
        r"/ui/series/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/numero/"
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), frozenset()),
    # Lector: ahí está «Añadir a deseados» al terminar el número.
    (re.compile(
        r"/ui/leer/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), frozenset()),
)

#: Límites que ya impone la ruta GET del destino. Un valor fuera de rango
#: produciría un 422 al volver: se rechaza antes y se cae al respaldo.
_LIMITES_DE_PARAMETRO = {
    # Solo dígitos ASCII: `str.isdigit()` acepta «²» (y `int` lanza ValueError),
    # «٣» o «１２», que no son el entero canónico que lee la ruta.
    "pagina": lambda valor: bool(re.fullmatch(r"[0-9]+", valor)) and int(valor) >= 1,
    "q": lambda valor: len(valor) <= 200,
    "identificador": lambda valor: len(valor) <= 500,
    "volver": lambda valor: len(valor) <= 2000,
}


def _pares_de_la_query(query: str) -> list[tuple[str, str]] | None:
    """Pares (nombre, valor) ya decodificados; `None` si la query no se puede leer."""
    try:
        return parse_qsl(query, keep_blank_values=True)
    except ValueError:
        return None


def _query_valida(pares: list[tuple[str, str]], permitidos: frozenset[str]) -> bool:
    """Sin nombres repetidos, vacíos ni fuera de la lista, y valores en rango."""
    nombres = [nombre for nombre, _ in pares]
    if len(set(nombres)) != len(nombres) or any(not nombre for nombre in nombres):
        return False
    if set(nombres) - permitidos:
        return False
    for nombre, valor in pares:
        validador = _LIMITES_DE_PARAMETRO.get(nombre)
        if validador is not None:
            try:
                valido = validador(valor)
            except (TypeError, ValueError):
                return False
            if not valido:
                return False
    return True


def volver_legal(valor: str | None) -> str | None:
    """Destino interno permitido para volver tras aceptar el aviso, o `None`.

    Solo páginas de la propia UI de la lista cerrada `_RETORNOS_LEGALES`, con
    sus parámetros de vista conocidos. Se rechaza: vacío, demasiado largo,
    controles, espacios, barra invertida, esquemas y hosts, `//` inicial o
    interno (incluido `///`, que el navegador resuelve como host), fragmentos,
    cualquier segmento codificado o `.`/`..`, y el propio aviso legal.

    Devuelve el valor tal cual (sin normalizar) para no reescribir la URL que
    construyó la app; el llamador decide el respaldo si es `None`. La
    validación se repite al confirmar: el campo oculto no es una autoridad.
    """
    if not valor or len(valor) > _MAX_RETORNO_LEGAL:
        return None
    if valor.startswith("//"):
        # `///ui/...` lo resuelve el navegador como host: urlsplit lo ve como
        # ruta local, así que se descarta sobre el valor original.
        return None
    if any(ord(caracter) < 32 or ord(caracter) == 127
           or caracter.isspace() or caracter == "\\" for caracter in valor):
        return None
    try:
        partes = urlsplit(valor)
    except ValueError:
        return None
    ruta = partes.path
    if (partes.scheme or partes.netloc or partes.fragment
            or not ruta.startswith("/") or ruta.startswith("//")
            or "//" in ruta or "%" in ruta or ".." in ruta.split("/")):
        return None
    pares = _pares_de_la_query(partes.query)
    if pares is None:
        return None
    for patron, permitidos in _RETORNOS_LEGALES:
        if patron.fullmatch(ruta):
            return valor if _query_valida(pares, permitidos) else None
    return None


def _host_de_la_peticion(request: Request) -> str:
    """Nombre de host de la cabecera `Host`, sin puerto ni corchetes de IPv6."""
    cabecera = request.headers.get("host", "")
    try:
        return (urlsplit(f"//{cabecera}").hostname or "").lower()
    except ValueError:
        return ""


def _candidato_local(candidato: str, request: Request) -> str | None:
    """Parte local de un candidato de retorno; `None` si no es de este servidor.

    `HX-Current-URL` y `Referer` llegan como URL absoluta. Se conserva solo
    ruta y query, y solo si el host es el de la propia petición: un `Referer`
    ajeno no aporta contexto y no debe decidir adónde se vuelve.
    """
    try:
        partes = urlsplit(candidato)
    except ValueError:
        return None
    if not partes.scheme and not partes.netloc:
        return candidato
    if partes.scheme.lower() not in ("http", "https"):
        return None
    if not partes.hostname or partes.hostname.lower() != _host_de_la_peticion(request):
        return None
    return partes.path + (f"?{partes.query}" if partes.query else "")


def resolver_destino_legal(
    request: Request | None = None, volver: str | None = None
) -> str | None:
    """Destino de vuelta, con la prioridad de la especificación §3.1.

    1. `volver` explícito (query de `/ui/legal` o campo del formulario);
    2. `HX-Current-URL` de la petición gateada (htmx);
    3. `Referer` de la petición gateada (formulario normal);
    4. `None`: el llamador usa `RETORNO_LEGAL_POR_DEFECTO`.

    Un candidato inválido no aborta: se prueba el siguiente. La URL de la
    propia petición no es candidata: es una acción, no una página.
    """
    destino = volver_legal(volver)
    if destino is not None:
        return destino
    if request is None:
        return None
    for cabecera in ("hx-current-url", "referer"):
        candidato = request.headers.get(cabecera)
        if not candidato:
            continue
        local = _candidato_local(candidato, request)
        if local is None:
            continue
        destino = volver_legal(local)
        if destino is not None:
            return destino
    return None


async def require_legal_acknowledgment(
    request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """Dependencia de FastAPI — aplicar SOLO a rutas que disparen
    búsqueda/descarga (crear o reintentar un item de wishlist).

    - htmx: 403 con `HX-Redirect` a /ui/legal — mecanismo nativo, cero JS nuevo.
    - formulario normal bajo `/ui/` con `Accept: text/html`: 303 con `Location`
      al wizard, para no enseñar el JSON 403 en el navegador.
    - API/JSON: 403 con el mismo `detail` y `HX-Redirect` (compatibilidad).

    Toda respuesta lleva `Cache-Control: no-store`: contiene el destino de
    vuelta de esta petición y no debe reutilizarse desde caché."""
    if not await is_acknowledged(db):
        destino = resolver_destino_legal(request)
        url = "/ui/legal"
        if destino is not None:
            url += f"?volver={quote(destino, safe='')}"
        es_htmx = request.headers.get("hx-request", "").lower() == "true"
        acepta_html = "text/html" in request.headers.get("accept", "").lower()
        if request.url.path.startswith("/ui/") and not es_htmx and acepta_html:
            raise HTTPException(
                status_code=303,
                headers={"Location": url, "Cache-Control": "no-store"},
            )
        raise HTTPException(
            status_code=403,
            detail="legal_acknowledgment_required",
            headers={"HX-Redirect": url, "Cache-Control": "no-store"},
        )
