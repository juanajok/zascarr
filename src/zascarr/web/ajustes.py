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
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.runtime_settings import SECRET_FIELDS, RuntimeSettingsService
from zascarr.web.routes import TEMPLATES_DIR

logger = structlog.get_logger()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Bug real, reportado: Prowlarr/Transmission/aMule fallaban con "no se pudo
# conectar" aunque la URL y las credenciales fueran correctas, mientras
# Comic Vine (un host externo real) funcionaba sin problema.
#
# Primera hipótesis (descartada con datos reales del usuario): el servicio
# escucha solo en 127.0.0.1, no en 0.0.0.0. `ss -tlnp` confirmó los tres
# escuchando en 0.0.0.0/* — no era eso.
#
# Causa real, confirmada con los datos del usuario: un cortafuegos (ufw)
# con política DROP por defecto y reglas de "solo LAN" (p.ej.
# 192.168.1.0/24) para esos puertos — el puente de Docker
# (host.docker.internal, la puerta de enlace del contenedor; confirmado
# 172.17.0.1 tanto en sandbox como en la Pi real del usuario) no es una
# de esas subredes "LAN" permitidas, así que ufw bloquea la conexión antes
# de llegar al servicio, aunque el bind sea correcto. La pista cubre las
# dos causas — se avisa solo cuando la excepción es de conexión
# (rechazada/timeout/DNS): un error HTTP real (401, 500...) significa que
# SÍ se llegó al servicio, y esta pista solo confundiría ahí.
_PISTA_CONEXION_RECHAZADA = (
    " Dos causas habituales si el servicio corre en esta misma máquina "
    "(fuera de Docker): (1) un cortafuegos (ufw/iptables) con reglas "
    "limitadas a tu LAN que no incluyen la subred del puente de Docker "
    "— compruébalo con: sudo ufw status, y si hace falta: "
    "sudo ufw allow from <subred-docker> to any port <puerto> proto tcp; "
    "(2) el servicio escucha solo en 127.0.0.1, no en 0.0.0.0 — "
    "compruébalo con: ss -tlnp | grep <puerto>. Un contenedor llega por "
    "la puerta de enlace del puente de Docker (host.docker.internal), "
    "no por loopback ni como si fuera tu LAN."
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
