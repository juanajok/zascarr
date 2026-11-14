"""
Router de ajustes de integraciones (D11) — /ui/ajustes.

Comic Vine, Prowlarr, Transmission y aMule editables desde la UI en vez
de solo por `.env` — ver services/runtime_settings.py para el porqué del
diseño (override en caliente sobre el Settings ya cacheado, sin tocar
config.py como segunda fuente de verdad). "Probar conexión" hace una
petición real con los valores DEL FORMULARIO (aunque no se hayan
guardado todavía), nunca solo con lo ya persistido — para eso está el
botón de probar antes de guardar.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition
from zascarr.services.amule import hash_contrasena_amuleweb
from zascarr.services.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    crear_cookie_sesion,
)
from zascarr.services.cortesia_estado import texto_politica_ajustes
from zascarr.services.notifier import TIPOS_CONOCIDOS, Notifier, url_valida
from zascarr.services.prowlarr import ProwlarrClient
from zascarr.services.runtime_settings import SECRET_FIELDS, RuntimeSettingsService
from zascarr.services.seguridad import (
    MENSAJE_NO_COINCIDEN,
    MODOS,
    fijar_seguridad,
    hay_contrasena,
)
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    FuenteApagada,
    politica_de,
)
from zascarr.utils.nombres_biblioteca import PRESETS, construir_nombre
from zascarr.utils.peticiones import (
    ErrorDePeticion,
    ReintentosAgotados,
    RespuestaNoTransitoria,
    pedir_con_cortesia,
)
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()

# Bug real, reportado: Prowlarr/Transmission/aMule fallaban con "no se pudo
# conectar" aunque la URL y las credenciales fueran correctas, mientras
# Comic Vine (un host externo real) funcionaba sin problema. Tres causas
# investigadas y descartadas/confirmadas en orden, con datos reales del
# usuario en cada paso, no solo plausibilidad:
#
# 1. Descartada: el servicio escucha solo en 127.0.0.1. `ss -tlnp`
#    confirmó los tres en 0.0.0.0/*.
# 2. Confirmada (parcial): ufw con reglas "solo LAN" para esos puertos —
#    corregida por el usuario con `ufw allow`, pero el fallo persistió.
# 3. Confirmada (causa real): `host.docker.internal` (docker-compose.yml)
#    resolvía a la puerta de enlace del puente POR DEFECTO (docker0,
#    172.17.0.1) en vez de a la de la red PERSONALIZADA que de verdad usa
#    el contenedor (docker-compose siempre crea una propia — en este caso
#    172.18.0.1). Confirmado comparando `docker exec ... getent hosts
#    host.docker.internal` contra `docker inspect ... Networks.*.Gateway`:
#    no coincidían. Corregido en docker-entrypoint.sh (autocorrige
#    /etc/hosts en el arranque, sin cambios de código aquí) — este mensaje
#    ahora cubre también ese caso por si alguien sigue en una versión
#    anterior. Se avisa solo cuando la excepción es de conexión
#    (rechazada/timeout/DNS): un error HTTP real (401, 500...) significa
#    que SÍ se llegó al servicio, y esta pista solo confundiría ahí.
# A10: la subred de Docker NO se adivina aquí. Desde dentro del contenedor no
# se puede leer el cortafuegos del host ni con qué subred se creó su red, y una
# regla que parece precisa pero apunta a otra red es peor que no dar ninguna
# (caso real del 2026-09-25: la regla era correcta y aun así no arregló nada,
# porque era de OTRA red de Docker). El comando exacto lo da el diagnóstico,
# que sí corre en el host y lee la subred real.
_PISTA_CONEXION_RECHAZADA = (
    " Tres causas habituales si el servicio corre en esta misma máquina "
    "(fuera de Docker): (1) host.docker.internal resolviendo a la red "
    "Docker equivocada — actualiza a la última versión de ZascArr, que lo "
    "autocorrige; (2) un cortafuegos (ufw/iptables) con reglas limitadas "
    "a tu LAN que no incluyen ninguna red de Docker — la subred exacta no "
    "se puede saber desde aquí: ejecútalo TÚ en la Pi (fuera del "
    "contenedor) con: sudo bash scripts/diagnostico-red.sh ; lee la subred "
    "del propio Docker y te propone el comando, sin aplicarlo; "
    "(3) el servicio escucha solo en 127.0.0.1, no en 0.0.0.0 — "
    "compruébalo con: ss -tlnp | grep <puerto>."
)


def _mensaje_conexion_fallida(exc: httpx.HTTPError) -> str:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return (
            "No se pudo conectar (conexión rechazada, timeout o nombre sin resolver)."
            + _PISTA_CONEXION_RECHAZADA
        )
    return "No se pudo conectar (red o timeout)."

router = APIRouter(prefix="/ui/ajustes", tags=["ui"])


def _sin_cache(respuesta: HTMLResponse) -> HTMLResponse:
    """AC-07/ajustes: ninguna respuesta con datos de acceso se sirve de caché."""
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _ids_prowlarr(settings) -> list[int]:
    crudo = getattr(settings, "prowlarr_indexer_ids", "") or ""
    return [int(t) for t in crudo.replace(";", ",").split(",") if t.strip().isdigit()]


def _contexto() -> dict:
    s = get_settings()
    return {
        "comicvine_api_key_configurada": bool(s.comicvine_api_key),
        "comicvine_enabled": s.comicvine_enabled,
        "anilist_enabled": s.anilist_enabled,
        "tebeosfera_enabled": s.tebeosfera_enabled,
        "gcd_enabled": s.gcd_enabled,
        "metron_enabled": bool(getattr(s, "metron_enabled", False)),
        "open_library_enabled": bool(getattr(s, "open_library_enabled", False)),
        "fandom_dc_enabled": bool(getattr(s, "fandom_dc_enabled", False)),
        "fandom_marvel_enabled": bool(getattr(s, "fandom_marvel_enabled", False)),
        "reading_orders_enabled": bool(getattr(s, "reading_orders_enabled", False)),
        "continuity_guide_enabled": bool(getattr(s, "continuity_guide_enabled", False)),
        "metron_token_configurado": bool(getattr(s, "metron_token", "")),
        "fuentes_heredadas": s.fuentes_heredadas,
        "prowlarr_url": s.prowlarr_url,
        "prowlarr_api_key_configurada": bool(s.prowlarr_api_key),
        "prowlarr_enabled": s.prowlarr_enabled,
        "prowlarr_indexer_ids": getattr(s, "prowlarr_indexer_ids", ""),
        "prowlarr_indexers_elegidos": _ids_prowlarr(s),
        "transmission_url": s.transmission_url,
        "transmission_username": s.transmission_username,
        "transmission_password_configurada": bool(s.transmission_password),
        "transmission_enabled": s.transmission_enabled,
        "amule_url": s.amule_url,
        "amule_password_configurada": bool(s.amule_password),
        "amule_enabled": s.amule_enabled,
        "carpetas_compartidas": list(getattr(s, "carpetas_compartidas", []) or []),
        "carpetas_disponibles": [
            {"ruta": str(ruta), "nombre": nombre}
            for campo, nombre in (
                ("library_path", "Biblioteca"),
                ("downloads_path", "Descargas"),
                ("amule_incoming_dir", "Incoming de aMule"),
            )
            if (ruta := getattr(s, campo, None))
        ],
        "auth_mode": s.auth_mode,
        "auth_username": s.auth_username,
        "auth_password_configurada": bool(s.auth_password_hash),
        "hay_contrasena": hay_contrasena(s),
        "base_url": s.base_url,
        "webhook_enabled": s.webhook_enabled,
        "webhook_type": s.webhook_type,
        "webhook_url": s.webhook_url,
        "webhook_token_configurado": bool(s.webhook_token),
        "webhook_chat_id": s.webhook_chat_id,
        "webhook_incluir_nombres": s.webhook_incluir_nombres,
        "quality_profile": getattr(s, "quality_profile", "equilibrado"),
        "upgrade_scan_interval_minutes": getattr(s, "upgrade_scan_interval_minutes", 360),
        "upgrade_scan_batch": getattr(s, "upgrade_scan_batch", 3),
        "cortesia": texto_politica_ajustes(s),
        "naming_enabled": s.naming_enabled,
        "naming_preset": s.naming_preset,
        "naming_padding": s.naming_padding,
        "nombres_presets": PRESETS,
        "nombres_ejemplo": construir_nombre(
            SimpleNamespace(title="La Patrulla", tradition=ComicTradition.AMERICAN),
            "3", preset=s.naming_preset, padding=s.naming_padding),
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return _sin_cache(templates.TemplateResponse(request, "ajustes.html", _contexto()))


@router.post("/guardar/comic-vine", response_class=HTMLResponse)
async def guardar_comic_vine(
    request: Request, comicvine_api_key: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({"comicvine_api_key": comicvine_api_key})
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Comic Vine"})


@router.post("/guardar/metron", response_class=HTMLResponse)
async def guardar_metron(
    request: Request, metron_token: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({"metron_token": metron_token})
    return templates.TemplateResponse(
        request, "_ajustes_guardado.html", {"nombre": "Metron"})


@router.post("/guardar/avisos", response_class=HTMLResponse)
async def guardar_avisos(
    request: Request,
    webhook_enabled: bool = Form(default=False),
    webhook_type: str = Form(default="generic"),
    webhook_url: str = Form(default=""),
    webhook_token: str = Form(default=""),
    webhook_chat_id: str = Form(default=""),
    webhook_incluir_nombres: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    # Validación en el guardado: el tipo tiene que ser uno conocido y la URL, si
    # se usa, http(s) con host. Un tipo raro ya no cae en «generic» en silencio.
    if webhook_type not in TIPOS_CONOCIDOS:
        return templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Avisos",
            "error": f"Tipo de aviso no reconocido: «{webhook_type}». Elige uno de la lista.",
        })
    url_limpia = webhook_url.rstrip("/")
    if webhook_type != "telegram" and url_limpia and not url_valida(url_limpia):
        return templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Avisos",
            "error": "La URL del aviso tiene que empezar por http:// o https:// y llevar un host.",
        })
    await RuntimeSettingsService(db).save({
        "webhook_enabled": webhook_enabled,
        "webhook_type": webhook_type,
        "webhook_url": url_limpia,
        "webhook_token": webhook_token,
        "webhook_chat_id": webhook_chat_id,
        "webhook_incluir_nombres": webhook_incluir_nombres,
    })
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Avisos"})


@router.post("/probar/avisos", response_class=HTMLResponse)
async def probar_avisos(
    request: Request,
    webhook_type: str = Form(default="generic"),
    webhook_url: str = Form(default=""),
    webhook_token: str = Form(default=""),
    webhook_chat_id: str = Form(default=""),
) -> HTMLResponse:
    """Prueba el aviso con lo que hay EN EL FORMULARIO, guardado o no.

    Misma convención que el resto de «Probar conexión» (D11): si el secreto llega
    vacío se usa el guardado como reserva, porque la UI nunca lo rellena. Si no,
    quien cambia la URL y pulsa «Enviar aviso de prueba» sin guardar probaría la
    configuración vieja y vería un resultado engañoso.
    """
    settings = get_settings()
    if webhook_type not in TIPOS_CONOCIDOS:
        return templates.TemplateResponse(request, "_ajustes_prueba.html", {
            "ok": False, "mensaje": f"Tipo de aviso no reconocido: «{webhook_type}».",
        })
    url = webhook_url.rstrip("/") or settings.webhook_url
    if webhook_type != "telegram" and url and not url_valida(url):
        return templates.TemplateResponse(request, "_ajustes_prueba.html", {
            "ok": False,
            "mensaje": ("La URL del aviso tiene que empezar por http:// o "
                        "https:// y llevar un host."),
        })
    de_prueba = settings.model_copy(update={
        "webhook_type": webhook_type,
        "webhook_url": url,
        "webhook_token": webhook_token or settings.webhook_token,
        "webhook_chat_id": webhook_chat_id or settings.webhook_chat_id,
    })
    resultado = await Notifier(settings=de_prueba).aviso_de_prueba()
    return templates.TemplateResponse(request, "_ajustes_prueba.html", {
        "ok": resultado.ok,
        "mensaje": "Aviso enviado." if resultado.ok else f"No se pudo enviar: {resultado.motivo}.",
    })


@router.post("/guardar/calidad", response_class=HTMLResponse)
async def guardar_calidad(
    request: Request,
    quality_profile: str = Form(default="equilibrado"),
    upgrade_scan_interval_minutes: str = Form(default="360"),
    upgrade_scan_batch: str = Form(default="3"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """BL-D2/D3: perfil legible de calidad y cadencia del escaneo de mejoras."""
    if quality_profile not in ("mejor", "equilibrado", "cualquiera"):
        quality_profile = "equilibrado"
    try:
        intervalo = int(upgrade_scan_interval_minutes)
    except (TypeError, ValueError):
        intervalo = 360
    if intervalo not in (0, 180, 360, 720, 1440):
        intervalo = 360
    try:
        lote = int(upgrade_scan_batch)
    except (TypeError, ValueError):
        lote = 3
    if lote not in (1, 3, 5, 10):
        lote = 3
    await RuntimeSettingsService(db).save({
        "quality_profile": quality_profile,
        "upgrade_scan_interval_minutes": intervalo,
        "upgrade_scan_batch": lote,
    })
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Calidad"})


@router.post("/guardar/nombres", response_class=HTMLResponse)
async def guardar_nombres(
    request: Request,
    naming_enabled: bool = Form(default=False),
    naming_preset: str = Form(default="clasico"),
    naming_padding: str = Form(default="0"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """BL-B9: activa/desactiva nombres nuevos y elige su preset."""
    if naming_preset not in PRESETS:
        return templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Nombres de archivo",
            "error": "Ese estilo de nombre no existe. Elige uno de la lista.",
        })
    try:
        padding = int(naming_padding)
    except (TypeError, ValueError):
        padding = 0
    padding = min(max(0, padding), 12)
    await RuntimeSettingsService(db).save({
        "naming_enabled": bool(naming_enabled),
        "naming_preset": naming_preset,
        "naming_padding": padding,
    })
    nombre = "Nombres de archivo"
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {
        "nombre": nombre,
        "aviso": "Solo afecta a los archivos que se organicen a partir de ahora; "
                 "la biblioteca existente no se renombra.",
    })


@router.post("/guardar/fuentes", response_class=HTMLResponse)
async def guardar_fuentes(
    request: Request,
    comicvine_enabled: bool = Form(default=False),
    anilist_enabled: bool = Form(default=False),
    tebeosfera_enabled: bool = Form(default=False),
    gcd_enabled: bool = Form(default=False),
    metron_enabled: bool = Form(default=False),
    open_library_enabled: bool = Form(default=False),
    fandom_dc_enabled: bool = Form(default=False),
    fandom_marvel_enabled: bool = Form(default=False),
    reading_orders_enabled: bool = Form(default=False),
    continuity_guide_enabled: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({
        "comicvine_enabled": comicvine_enabled,
        "anilist_enabled": anilist_enabled,
        "tebeosfera_enabled": tebeosfera_enabled,
        "gcd_enabled": gcd_enabled,
        "metron_enabled": metron_enabled,
        "open_library_enabled": open_library_enabled,
        "fandom_dc_enabled": fandom_dc_enabled,
        "fandom_marvel_enabled": fandom_marvel_enabled,
        "reading_orders_enabled": reading_orders_enabled,
        "continuity_guide_enabled": continuity_guide_enabled,
        # Guardar es tomar la decisión (aunque sea confirmar el estado actual): deja de ser
        # «heredado».
        "fuentes_heredadas": False,
    })
    return templates.TemplateResponse(
        request, "_ajustes_guardado.html", {"nombre": "Fuentes de datos"}
    )


@router.post("/guardar/prowlarr", response_class=HTMLResponse)
async def guardar_prowlarr(
    request: Request, prowlarr_url: str = Form(...),
    prowlarr_api_key: str = Form(default=""),
    prowlarr_enabled: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({
        "prowlarr_url": prowlarr_url.rstrip("/"),
        "prowlarr_api_key": prowlarr_api_key,
        "prowlarr_enabled": prowlarr_enabled,
    })
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Prowlarr"})


@router.get("/prowlarr/indexers", response_class=HTMLResponse)
async def elegir_indexers_prowlarr(request: Request) -> HTMLResponse:
    """Carga los indexers de Prowlarr solo cuando la persona lo pide."""
    settings = get_settings()
    if not (settings.prowlarr_url.strip() and settings.prowlarr_api_key.strip()):
        return templates.TemplateResponse(
            request, "_ajustes_prowlarr_indexers.html",
            {"error": "Configura primero la URL y la clave de Prowlarr."})
    try:
        indexers = await ProwlarrClient().list_indexers()
    except Exception:  # noqa: BLE001 — la UI explica el fallo, no inventa lista
        logger.warning("ajustes.prowlarr_indexers_failed")
        return templates.TemplateResponse(
            request, "_ajustes_prowlarr_indexers.html",
            {"error": "No se pudo leer la lista de indexers de Prowlarr."})
    return templates.TemplateResponse(
        request, "_ajustes_prowlarr_indexers.html", {
            "indexers": indexers, "seleccionados": _ids_prowlarr(settings), "error": None,
        })


@router.post("/guardar/prowlarr-indexers", response_class=HTMLResponse)
async def guardar_prowlarr_indexers(
    request: Request, db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Guarda los IDs elegidos; vacío significa «todos»."""
    form = await request.form()
    ids = [int(v) for v in form.getlist("indexer_ids") if str(v).strip().isdigit()]
    valor = ",".join(str(i) for i in dict.fromkeys(ids) if i > 0)
    await RuntimeSettingsService(db).save({"prowlarr_indexer_ids": valor})
    return templates.TemplateResponse(
        request, "_ajustes_guardado.html",
        {"nombre": "Indexers de Prowlarr para ZascArr"})


@router.post("/guardar/transmission", response_class=HTMLResponse)
async def guardar_transmission(
    request: Request, transmission_url: str = Form(...),
    transmission_username: str = Form(default=""),
    transmission_password: str = Form(default=""),
    transmission_enabled: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({
        "transmission_url": transmission_url.rstrip("/"),
        "transmission_username": transmission_username,
        "transmission_password": transmission_password,
        "transmission_enabled": transmission_enabled,
    })
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Transmission"})


@router.post("/guardar/amule", response_class=HTMLResponse)
async def guardar_amule(
    request: Request, amule_url: str = Form(...),
    amule_password: str = Form(default=""),
    amule_enabled: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({
        "amule_url": amule_url.rstrip("/"),
        "amule_password": amule_password,
        "amule_enabled": amule_enabled,
    })
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "aMule"})


@router.post("/guardar/compartidos", response_class=HTMLResponse)
async def guardar_compartidos(
    request: Request,
    carpetas_compartidas: list[str] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """#488: carpetas que comparten los programas de descargas.

    Solo se aceptan las raíces conocidas del contenedor: una ruta relativa, con `..` o
    inventada desde el formulario se descarta (y si no queda ninguna, el guardián fallará
    cerrado). Se guarda en la misma fila JSONB de ajustes; sin migración."""
    s = get_settings()
    permitidas = {str(s.library_path), str(s.downloads_path), str(s.amule_incoming_dir)}
    elegidas = []
    for ruta in carpetas_compartidas:
        if ruta in permitidas and ruta not in elegidas:
            elegidas.append(ruta)
    await RuntimeSettingsService(db).save({"carpetas_compartidas": elegidas})
    return _sin_cache(templates.TemplateResponse(
        request, "_ajustes_guardado.html", {"nombre": "Archivos compartidos"}))


def _contexto_seguridad(*, incluir_valores: bool = True) -> dict:
    """Lo que pinta la tarjeta de Seguridad, siempre desde el estado ACTUAL.

    En la respuesta de ÉXITO que sustituye la tarjeta no se repintan `auth_username` ni
    `base_url`: AC-07 exige que ningún valor del request (aunque se haya guardado) se
    refleje en esa respuesta. La página completa, tras recargar, sí los muestra.
    """
    s = get_settings()
    return {
        "auth_mode": s.auth_mode,
        "auth_username": s.auth_username if incluir_valores else "",
        "auth_password_configurada": bool(s.auth_password_hash),
        "hay_contrasena": hay_contrasena(s),
        "base_url": s.base_url if incluir_valores else "",
    }


@router.post("/guardar/seguridad", response_class=HTMLResponse)
async def guardar_seguridad(
    request: Request,
    # BL-OPS3 (#456): todos `str = Form(default="")` y SIN restricciones de campo (`min_length`,
    # `max_length`, `Literal`…): con una restricción incumplida, el 422 de FastAPI devolvería lo
    # escrito (una contraseña). La validación es manual y cada respuesta lleva un texto fijo.
    auth_mode: str = Form(default=""),
    auth_username: str = Form(default=""), auth_password: str = Form(default=""),
    auth_password_actual: str = Form(default=""), auth_password_repetida: str = Form(default=""),
    base_url: str = Form(default=""), conservar_identidad: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if auth_mode not in MODOS:
        raise HTTPException(
            status_code=400, detail="Modo de autenticación no reconocido",
            headers={"Cache-Control": "no-store"},
        )

    # La tarjeta de éxito no repinta usuario/dirección (AC-07), así que un segundo
    # guardado sin recargar los enviaría vacíos. `conservar_identidad` (solo lo pone
    # esa tarjeta) significa «no tocar»: se recuperan los valores guardados. Sin el
    # marcador, un `base_url` vacío sigue significando «vuelve al .env».
    if conservar_identidad:
        actuales = get_settings()
        auth_username = auth_username or actuales.auth_username
        base_url = base_url or actuales.base_url

    # La regla (longitud, no dejar la app sin forma de entrar, versión de sesión y la contraseña
    # ACTUAL para cambiar cómo se entra) vive en services/seguridad.py. El router nunca usa la
    # variante sin contraseña actual: es solo del instalador.
    resultado = await fijar_seguridad(
        db, modo=auth_mode, usuario=auth_username, password=auth_password, base_url=base_url,
        contrasena_actual=auth_password_actual, password_repetida=auth_password_repetida,
    )
    if resultado.error:
        motivo = resultado.motivo_rechazo
        if motivo:
            logger.info("ajustes.seguridad_rechazada", motivo=motivo)
        return _sin_cache(templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Seguridad", "error": resultado.error,
            # la actual se vacía ante falta, incorrecta, cola llena y bloqueo (inválida si falta
            # o es incorrecta); las nuevas, ante bloqueo y si no coinciden
            "vaciar_actual": motivo is not None,
            "actual_invalida": motivo in ("falta_actual", "actual_incorrecta"),
            "vaciar_nuevas": motivo == "bloqueada" or resultado.error == MENSAJE_NO_COINCIDEN,
            "auth_password_configurada": bool(get_settings().auth_password_hash),
        }))

    if resultado.cambios:
        logger.info("ajustes.seguridad_cambiada", cambios=list(resultado.cambios))
    if not resultado.cambia_credenciales:
        # Solo la dirección (o nada): como antes, al hueco del resultado, vaciando lo escrito.
        return _sin_cache(templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Seguridad", "aviso": resultado.aviso,
            "vaciar_actual": True, "vaciar_nuevas": True,
            "auth_password_configurada": bool(get_settings().auth_password_hash),
        }))

    # Cambio de credenciales: se sustituye TODA la tarjeta, pintada desde el estado nuevo (ya trae o
    # quita el campo de la contraseña actual, sin ningún `value`). El `Set-Cookie` viaja en la misma
    # respuesta: quien cambia la contraseña conserva SU sesión (las demás se cierran).
    respuesta = _sin_cache(templates.TemplateResponse(request, "_ajustes_seguridad.html", {
        **_contexto_seguridad(incluir_valores=False), "mensaje_exito": True,
        "cambia_credenciales": True, "aviso": resultado.aviso,
    }))
    respuesta.headers["HX-Retarget"] = "#tarjeta-seguridad"
    respuesta.headers["HX-Reswap"] = "outerHTML"
    settings = get_settings()
    cookie = crear_cookie_sesion(settings.secret_key, settings.auth_session_version)
    respuesta.set_cookie(
        COOKIE_NAME, cookie,
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return respuesta


# ── Probar conexión: valores DEL FORMULARIO, con fallback al secreto ya
# ── guardado si el campo llega vacío (mismo criterio que save()). ──────

def _secreto_o_guardado(valor_form: str, campo: str) -> str:
    if valor_form:
        return valor_form
    if campo not in SECRET_FIELDS:
        return valor_form
    return getattr(get_settings(), campo, "") or ""


@router.post("/probar/comic-vine", response_class=HTMLResponse)
async def probar_comic_vine(
    request: Request, comicvine_api_key: str = Form(default="")
) -> HTMLResponse:
    api_key = _secreto_o_guardado(comicvine_api_key, "comicvine_api_key")
    ok, mensaje = await _test_comic_vine(api_key)
    # §6.5: «no se ha probado por cortesía» es un aviso neutro (warn), no un error en rojo.
    aviso = (not ok) and mensaje.startswith("No se ha probado")
    return templates.TemplateResponse(
        request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje, "aviso": aviso}
    )


@router.post("/probar/metron", response_class=HTMLResponse)
async def probar_metron(
    request: Request, metron_token: str = Form(default="")
) -> HTMLResponse:
    token = _secreto_o_guardado(metron_token, "metron_token")
    ok, mensaje = await _test_metron(token)
    aviso = (not ok) and mensaje.startswith("No se ha probado")
    return templates.TemplateResponse(
        request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje, "aviso": aviso}
    )


@router.post("/probar/prowlarr", response_class=HTMLResponse)
async def probar_prowlarr(
    request: Request, prowlarr_url: str = Form(...), prowlarr_api_key: str = Form(default=""),
) -> HTMLResponse:
    api_key = _secreto_o_guardado(prowlarr_api_key, "prowlarr_api_key")
    ok, mensaje = await _test_prowlarr(prowlarr_url.rstrip("/"), api_key)
    return templates.TemplateResponse(
        request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje}
    )


@router.post("/probar/transmission", response_class=HTMLResponse)
async def probar_transmission(
    request: Request, transmission_url: str = Form(...),
    transmission_username: str = Form(default=""), transmission_password: str = Form(default=""),
) -> HTMLResponse:
    password = _secreto_o_guardado(transmission_password, "transmission_password")
    ok, mensaje = await _test_transmission(
        transmission_url.rstrip("/"), transmission_username, password
    )
    return templates.TemplateResponse(
        request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje}
    )


@router.post("/probar/amule", response_class=HTMLResponse)
async def probar_amule(
    request: Request, amule_url: str = Form(...), amule_password: str = Form(default="")
) -> HTMLResponse:
    password = _secreto_o_guardado(amule_password, "amule_password")
    ok, mensaje = await _test_amule(amule_url.rstrip("/"), password)
    return templates.TemplateResponse(
        request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje}
    )


async def _test_comic_vine(api_key: str) -> tuple[bool, str]:
    """Prueba manual de conexión: pasa por la cortesía compartida (#134).

    Es la excepción explícita a «fuente apagada» (acción del operador) y **no reintenta**: un
    presupuesto de 10 s para una acción interactiva, con la política de Comic Vine a un intento.

    Manda el MISMO `User-Agent` que el cliente real (`services/comic_vine.USER_AGENT`): GameSpot
    bloquea con 403 el genérico de `httpx` (`python-httpx/…`), y sin esto el botón daba «HTTP 403»
    con una clave perfectamente válida (bug real, 2026-11-09). El 401 sí es clave rechazada.
    """
    if not api_key:
        return False, "Falta la clave de API."
    from dataclasses import replace

    from zascarr.services.comic_vine import USER_AGENT
    politica = replace(politica_de("comicvine"), max_intentos=1)
    try:
        async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=False,
                headers={"User-Agent": USER_AGENT}) as client:
            r = await pedir_con_cortesia(
                client, "GET", "https://comicvine.gamespot.com/api/search/",
                politica=politica, espera_max_s=10.0, permitir_apagada=True,
                datos={"api_key": api_key, "query": "test", "resources": "volume",
                       "format": "json", "limit": 1},
            )
        data = r.json()
        if data.get("error") == "OK":
            return True, "Conexión correcta."
        return False, f"Comic Vine rechazó la clave: {data.get('error')}"
    except CortesiaEnEspera as exc:
        segundos = max(1, round(exc.espera_estimada_s))
        return False, ("No se ha probado: hay que esperar ~" f"{segundos} s por cortesía. "
                       "Inténtalo de nuevo en un momento.")
    except RespuestaNoTransitoria as exc:
        if exc.codigo == 401:
            return False, ("Comic Vine rechazó la clave (HTTP 401). Cópiala entera desde tu "
                           "cuenta de Comic Vine (comicvine.gamespot.com/api) y vuelve a probar.")
        if exc.codigo == 403:
            return False, ("Comic Vine bloqueó la conexión (HTTP 403): es su protección contra "
                           "programas, o tu red (VPN/proxy). Si la clave es correcta, prueba sin "
                           "VPN o más tarde.")
        return False, f"Comic Vine respondió HTTP {exc.codigo}."
    except (ReintentosAgotados, FuenteApagada, httpx.HTTPError, ErrorDePeticion) as exc:
        logger.warning("ajustes.test_failed", integracion="comic_vine",
                       error=type(exc).__name__)
        return False, "No se pudo conectar (red o timeout)."


async def _test_metron(
    token: str, transporte: httpx.AsyncBaseTransport | None = None) -> tuple[bool, str]:
    """Prueba manual de Metron: una búsqueda de una página, sin guardar ni escribir.

    Misma excepción explícita que Comic Vine: acción del operador, `permitir_apagada=True` y
    un solo intento. Usa el mismo User-Agent del cliente real.
    """
    if not token:
        return False, "Falta el token de Metron."
    from dataclasses import replace

    from zascarr.services.metron import SITIO, USER_AGENT

    politica = replace(politica_de("metron"), max_intentos=1)
    try:
        async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=False, transport=transporte,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                         "Authorization": f"Bearer {token.strip()}"}) as client:
            r = await pedir_con_cortesia(
                client, "GET", f"{SITIO}/api/series/?q=batman",
                politica=politica, espera_max_s=10.0, permitir_apagada=True,
            )
        data = r.json()
        if isinstance(data, dict) and isinstance(data.get("results"), list):
            return True, "Conexión correcta: Metron respondió."
        return False, "Metron respondió, pero no se pudo leer la respuesta."
    except CortesiaEnEspera as exc:
        segundos = max(1, round(exc.espera_estimada_s))
        return False, ("No se ha probado: hay que esperar ~" f"{segundos} s por cortesía. "
                       "Inténtalo de nuevo en un momento.")
    except RespuestaNoTransitoria as exc:
        if exc.codigo in (401, 403):
            return False, ("Metron rechazó el token (HTTP 401/403). Créalo de nuevo en tu "
                           "cuenta de Metron, en «Tokens», y vuelve a probar.")
        if exc.codigo == 429:
            return False, "Metron ha pedido esperar antes de volver a consultarlo."
        return False, f"Metron respondió HTTP {exc.codigo}."
    except (ReintentosAgotados, FuenteApagada, httpx.HTTPError, ErrorDePeticion, ValueError) as exc:
        logger.warning("ajustes.test_failed", integracion="metron",
                       error=type(exc).__name__)
        return False, "No se pudo conectar (red o timeout)."


async def _test_prowlarr(url: str, api_key: str) -> tuple[bool, str]:
    if not url:
        return False, "Falta la URL de Prowlarr."
    if not api_key:
        return False, "Falta la clave de API."
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{url}/api/v1/indexer", headers={"X-Api-Key": api_key})
        if r.status_code == 200:
            return True, "Conexión correcta."
        if r.status_code in (401, 403):
            return False, "Prowlarr respondió: clave de API rechazada."
        return False, f"Prowlarr respondió HTTP {r.status_code}."
    except httpx.HTTPError as exc:
        logger.warning("ajustes.test_failed", integracion="prowlarr", error=str(exc))
        return False, _mensaje_conexion_fallida(exc)


async def _test_transmission(url: str, username: str, password: str) -> tuple[bool, str]:
    if not url:
        return False, "Falta la URL de Transmission."
    auth = (username, password) if username else None
    rpc_url = f"{url}/transmission/rpc"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(rpc_url, json={"method": "session-get"}, auth=auth)
            if r.status_code == 409:
                # Handshake CSRF habitual de Transmission: reintenta una vez
                # con el token de sesión que acaba de dar.
                session_id = r.headers.get("X-Transmission-Session-Id", "")
                r = await client.post(
                    rpc_url, json={"method": "session-get"}, auth=auth,
                    headers={"X-Transmission-Session-Id": session_id},
                )
        if r.status_code == 401:
            return False, "Transmission respondió: usuario o contraseña rechazados."
        if r.status_code != 200:
            return False, f"Transmission respondió HTTP {r.status_code}."
        if r.json().get("result") == "success":
            return True, "Conexión correcta."
        return False, "Transmission no confirmó la sesión."
    except httpx.HTTPError as exc:
        logger.warning("ajustes.test_failed", integracion="transmission", error=str(exc))
        return False, _mensaje_conexion_fallida(exc)


async def _test_amule(url: str, password: str) -> tuple[bool, str]:
    if not url:
        return False, "Falta la URL de aMule (amuleweb)."
    if not password:
        return False, "Falta la contraseña de amuleweb."
    try:
        pw_hash = hash_contrasena_amuleweb(password)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            r = await client.post(f"{url}/", data={"p": pw_hash})
        if r.cookies or r.headers.get("set-cookie"):
            return True, "Conexión correcta."
        return False, "aMule no devolvió sesión — revisa la contraseña."
    except httpx.HTTPError as exc:
        logger.warning("ajustes.test_failed", integracion="amule", error=str(exc))
        return False, _mensaje_conexion_fallida(exc)
