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

import hashlib

import httpx
import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    crear_cookie_sesion,
)
from zascarr.services.notifier import TIPOS_CONOCIDOS, Notifier, url_valida
from zascarr.services.runtime_settings import SECRET_FIELDS, RuntimeSettingsService
from zascarr.services.seguridad import MODOS, fijar_seguridad
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
        return "No se pudo conectar (conexión rechazada, timeout o nombre sin resolver)." + _PISTA_CONEXION_RECHAZADA
    return "No se pudo conectar (red o timeout)."

router = APIRouter(prefix="/ui/ajustes", tags=["ui"])


def _contexto() -> dict:
    s = get_settings()
    return {
        "comicvine_api_key_configurada": bool(s.comicvine_api_key),
        "comicvine_enabled": s.comicvine_enabled,
        "anilist_enabled": s.anilist_enabled,
        "tebeosfera_enabled": s.tebeosfera_enabled,
        "gcd_enabled": s.gcd_enabled,
        "prowlarr_url": s.prowlarr_url,
        "prowlarr_api_key_configurada": bool(s.prowlarr_api_key),
        "prowlarr_enabled": s.prowlarr_enabled,
        "transmission_url": s.transmission_url,
        "transmission_username": s.transmission_username,
        "transmission_password_configurada": bool(s.transmission_password),
        "transmission_enabled": s.transmission_enabled,
        "amule_url": s.amule_url,
        "amule_password_configurada": bool(s.amule_password),
        "amule_enabled": s.amule_enabled,
        "auth_mode": s.auth_mode,
        "auth_username": s.auth_username,
        "auth_password_configurada": bool(s.auth_password_hash),
        "base_url": s.base_url,
        "webhook_enabled": s.webhook_enabled,
        "webhook_type": s.webhook_type,
        "webhook_url": s.webhook_url,
        "webhook_token_configurado": bool(s.webhook_token),
        "webhook_chat_id": s.webhook_chat_id,
        "webhook_incluir_nombres": s.webhook_incluir_nombres,
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ajustes.html", _contexto())


@router.post("/guardar/comic-vine", response_class=HTMLResponse)
async def guardar_comic_vine(
    request: Request, comicvine_api_key: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({"comicvine_api_key": comicvine_api_key})
    return templates.TemplateResponse(request, "_ajustes_guardado.html", {"nombre": "Comic Vine"})


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


@router.post("/guardar/fuentes", response_class=HTMLResponse)
async def guardar_fuentes(
    request: Request,
    comicvine_enabled: bool = Form(default=False),
    anilist_enabled: bool = Form(default=False),
    tebeosfera_enabled: bool = Form(default=False),
    gcd_enabled: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    await RuntimeSettingsService(db).save({
        "comicvine_enabled": comicvine_enabled,
        "anilist_enabled": anilist_enabled,
        "tebeosfera_enabled": tebeosfera_enabled,
        "gcd_enabled": gcd_enabled,
    })
    return templates.TemplateResponse(
        request, "_ajustes_guardado.html", {"nombre": "Fuentes de metadatos"}
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


@router.post("/guardar/seguridad", response_class=HTMLResponse)
async def guardar_seguridad(
    request: Request, auth_mode: str = Form(...),
    auth_username: str = Form(default=""), auth_password: str = Form(default=""),
    base_url: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    if auth_mode not in MODOS:
        raise HTTPException(status_code=400, detail="Modo de autenticación no reconocido")

    # La regla (longitud, no dejar la app sin forma de entrar, versión de sesión)
    # vive en services/seguridad.py y la comparte el instalador (A11).
    resultado = await fijar_seguridad(
        db, modo=auth_mode, usuario=auth_username, password=auth_password, base_url=base_url,
    )
    if resultado.error:
        return templates.TemplateResponse(request, "_ajustes_guardado.html", {
            "nombre": "Seguridad", "error": resultado.error,
        })

    respuesta = templates.TemplateResponse(
        request, "_ajustes_guardado.html", {"nombre": "Seguridad", "aviso": resultado.aviso})
    if resultado.cambia_credenciales:
        # Re-emite la cookie con la versión nueva: quien cambia la contraseña
        # conserva SU sesión (las demás se cierran). Sin esto, su siguiente clic
        # le llevaría a /login sin explicación.
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
async def probar_comic_vine(request: Request, comicvine_api_key: str = Form(default="")) -> HTMLResponse:
    api_key = _secreto_o_guardado(comicvine_api_key, "comicvine_api_key")
    ok, mensaje = await _test_comic_vine(api_key)
    return templates.TemplateResponse(request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje})


@router.post("/probar/prowlarr", response_class=HTMLResponse)
async def probar_prowlarr(
    request: Request, prowlarr_url: str = Form(...), prowlarr_api_key: str = Form(default=""),
) -> HTMLResponse:
    api_key = _secreto_o_guardado(prowlarr_api_key, "prowlarr_api_key")
    ok, mensaje = await _test_prowlarr(prowlarr_url.rstrip("/"), api_key)
    return templates.TemplateResponse(request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje})


@router.post("/probar/transmission", response_class=HTMLResponse)
async def probar_transmission(
    request: Request, transmission_url: str = Form(...),
    transmission_username: str = Form(default=""), transmission_password: str = Form(default=""),
) -> HTMLResponse:
    password = _secreto_o_guardado(transmission_password, "transmission_password")
    ok, mensaje = await _test_transmission(transmission_url.rstrip("/"), transmission_username, password)
    return templates.TemplateResponse(request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje})


@router.post("/probar/amule", response_class=HTMLResponse)
async def probar_amule(request: Request, amule_url: str = Form(...), amule_password: str = Form(default="")) -> HTMLResponse:
    password = _secreto_o_guardado(amule_password, "amule_password")
    ok, mensaje = await _test_amule(amule_url.rstrip("/"), password)
    return templates.TemplateResponse(request, "_ajustes_prueba.html", {"ok": ok, "mensaje": mensaje})


async def _test_comic_vine(api_key: str) -> tuple[bool, str]:
    if not api_key:
        return False, "Falta la clave de API."
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://comicvine.gamespot.com/api/search/",
                params={"api_key": api_key, "query": "test", "resources": "volume",
                        "format": "json", "limit": 1},
                headers={"User-Agent": "ZascArr/0.1"},
            )
        if r.status_code != 200:
            return False, f"Comic Vine respondió HTTP {r.status_code}."
        data = r.json()
        if data.get("error") == "OK":
            return True, "Conexión correcta."
        return False, f"Comic Vine rechazó la clave: {data.get('error')}"
    except httpx.HTTPError as exc:
        logger.warning("ajustes.test_failed", integracion="comic_vine", error=str(exc))
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
        pw_hash = hashlib.md5(password.encode()).hexdigest()
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            r = await client.post(f"{url}/", data={"p": pw_hash})
        if r.cookies or r.headers.get("set-cookie"):
            return True, "Conexión correcta."
        return False, "aMule no devolvió sesión — revisa la contraseña."
    except httpx.HTTPError as exc:
        logger.warning("ajustes.test_failed", integracion="amule", error=str(exc))
        return False, _mensaje_conexion_fallida(exc)
