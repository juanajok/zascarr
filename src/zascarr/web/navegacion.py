"""
Fragmento de contadores del menú (V3): `GET /ui/_nav/estado`.

Contrato (cada punto tiene su prueba):
  · Devuelve SOLO intercambios fuera de banda (`hx-swap-oob`) sobre los contadores del menú. La
    plantilla del menú pide con `hx-swap="none"`: este fragmento no puede reemplazar ni borrar un
    enlace, ni siquiera por error.
  · Ante CUALQUIER fallo responde `204 No Content` (htmx no intercambia un 204) y el menú queda como
    estaba. «Cualquier fallo» abarca TODO el ciclo, no solo las consultas: abrir la sesión de BD,
    consultar, liberarla, calcular el estado de seguridad y renderizar la plantilla; y una BD que no
    contesta a tiempo. En `/ui/*` una BD caída con la app en marcha es hoy un `500` de texto plano.
  · La sesión NO viene de la dependencia genérica `get_db`: esa adquiere antes del cuerpo y hace
    `commit` DESPUÉS de la respuesta, ambas fases fuera de cualquier `try` del manejador. Aquí es de
    solo lectura, así que se abre y se cierra dentro de su propia tarea y no hay `commit`.
  · LA RESPUESTA NO ESPERA A LA LIMPIEZA. Con la BD CONGELADA (acepta la conexión y no contesta),
    cancelar una consulta no basta: liberar la sesión hace un `rollback` sobre esa misma conexión
    y también se cuelga, así que un `asyncio.timeout` alrededor de todo no devuelve nunca (medido
    en navegador real: curl cortó a los 20 s con un plazo de 5). Por eso el trabajo va en UNA tarea
    compartida y la petición solo espera `PLAZO_SEGUNDOS`: si no llega, responde 204 y la tarea
    termina su limpieza por su cuenta. Mientras haya una en vuelo las demás se suman a ella
    (no se apilan sondeos, sesiones ni conexiones contra una BD que no responde).
  · Está bajo `/ui/*`, protegido por `AuthMiddleware` como el resto. NO se declara ruta de
    diagnóstico (eso la serviría sin comprobar la sesión). Sin sesión, el middleware responde 204
    vacío (ver `services/auth.py::RUTAS_FRAGMENTO_SILENCIOSO`) ANTES de llegar aquí: ni se abre la
    sesión de BD, ni hay redirección a /login (htmx la seguiría e intercambiaría su página).
"""
from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse

from zascarr.database import async_session_factory
from zascarr.services.navegacion import contadores
from zascarr.services.seguridad import estado_de_seguridad
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()

router = APIRouter(prefix="/ui/_nav", tags=["ui"], include_in_schema=False)

SIN_CONTENIDO = 204
#: sin caché: un contador viejo en una caché intermedia sería peor que no tenerlo
CABECERAS = {"Cache-Control": "no-store"}
#: lo máximo que espera UNA PETICIÓN a la BD; pasado, 204. No acota la limpieza (ver arriba).
PLAZO_SEGUNDOS = 5.0

#: la tarea de BD en vuelo, compartida por las peticiones concurrentes (una por bucle de eventos)
_calculo_en_curso: asyncio.Task | None = None


async def _datos() -> tuple:
    """Lo que se hace con la BD: abrir, consultar, LIBERAR. Si falla al cerrar, no se sirven números
    de una sesión en estado dudoso. Más el estado de seguridad (sin E/S)."""
    async with async_session_factory() as db:
        cuentas = await contadores(db)
    return cuentas, bool(estado_de_seguridad()["atencion"])


def _recoger(tarea: asyncio.Task) -> None:
    """Marca como vista la excepción de una tarea abandonada (si no, asyncio la registra)."""
    if not tarea.cancelled():
        tarea.exception()


def _tarea_de_datos() -> asyncio.Task:
    global _calculo_en_curso
    actual = _calculo_en_curso
    if actual is None or actual.done() or actual.get_loop() is not asyncio.get_running_loop():
        actual = asyncio.create_task(_datos())
        actual.add_done_callback(_recoger)
        _calculo_en_curso = actual
    return actual


@router.get("/estado", response_class=HTMLResponse)
async def contadores_del_menu(request: Request) -> Response:
    try:
        tarea = _tarea_de_datos()
        # `wait` con plazo NO cancela la tarea: la petición se desentiende y la limpieza sigue sola.
        hechas, _ = await asyncio.wait({tarea}, timeout=PLAZO_SEGUNDOS)
        if not hechas:
            raise TimeoutError("la BD no contesta a tiempo")
        cuentas, atencion = tarea.result()
        return templates.TemplateResponse(
            request, "_nav_contadores.html",
            {"pendientes": cuentas.pendientes, "deseados": cuentas.deseados, "atencion": atencion},
            headers=CABECERAS,
        )
    except Exception as exc:  # noqa: BLE001 — cualquier fallo se degrada a «no cambies nada»
        # Solo la clase del error: nunca rutas, consultas ni datos del coleccionista (§5.4).
        logger.warning("nav_contadores_no_disponibles", error=type(exc).__name__)
        return Response(status_code=SIN_CONTENIDO, headers=CABECERAS)
