"""Health check endpoint (fix C2 del peer review).

Cambio principal: el estado de la VPN ya NO se consulta con subprocess
(`ip link show wg0`), que fallaba dos veces:
  1. Sin network_mode: host, el contenedor no ve las interfaces del host.
  2. La imagen slim no incluye iproute2 → FileNotFoundError → siempre warning.

Ahora health.py LEE UN FICHERO JSON que un script del host escribe
(scripts/vpn-state.sh, vía cron o systemd timer) y que el compose monta
read-only en /run/vpn-state/. El contenedor no necesita iproute2 ni
privilegios de red para saber si el túnel está activo.

Semántica (decisión de diseño documentada en ADR del peer review):
  - VPN caída o fichero ausente/antiguo → WARNING, nunca ERROR.
    El servicio sigue healthy; la advertencia es para el operador.
  - No bloquea descargas: eso sería endurecer antes de tener producto.
    El orchestrator solo loguea warning antes de cada descarga torrent.
  - stale_after_seconds: si el fichero no se ha refrescado recientemente,
    el último escrito podría mentir (cron muerto) → "stale".
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db

router = APIRouter(tags=["health"])

# Transmission/aMule tienen su propio timeout interno de hasta 30s cada uno;
# si ambos están caídos sin devolver RST inmediato (VPN aún no arriba, firewall
# con DROP en vez de REJECT — el caso normal al arrancar una Pi), un health
# check secuencial tardaría hasta ~60s y Docker (HEALTHCHECK --timeout=10s)
# marcaría el contenedor unhealthy aunque la app esté perfectamente sana.
# "Healthcheck observacional, no bloqueante" (CLAUDE.md §4): se acotan y se
# lanzan en paralelo para que /api/health responda siempre en este margen.
_EXTERNAL_CHECK_TIMEOUT_S = 3.0

# Si el fichero de estado no se refresca en este margen, se considera
# "stale": el script del host probablemente ha muerto sin avisar.
VPN_STALE_AFTER_S = 300  # 5 minutos (el timer corre cada minuto)


def _check_vpn() -> tuple[str, str]:
    """Lee el fichero de estado de la VPN. Devuelve (status, detail)."""
    settings = get_settings()
    state_path = Path(settings.vpn_state_file)

    if not state_path.exists():
        return "unknown", (f"fichero {state_path} ausente — el host aún "
                           "no ha escrito el estado (o el timer no corre)")

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return "warning", f"fichero de estado ilegible: {exc}"

    updated = state.get("updated_at_epoch", 0)
    age = time.time() - updated
    if age > VPN_STALE_AFTER_S:
        return "warning", (f"estado stale ({age:.0f}s sin refrescar; "
                           "¿murió el timer del host?)")

    if state.get("vpn_active"):
        return "ok", f"interfaz {state.get('interface', 'wg0')} activa"

    return "warning", (f"túnel {state.get('interface', 'wg0')} NO activo "
                       "— las descargas torrent irán en claro")


async def _check_transmission() -> bool:
    from zascarr.services.transmission import TransmissionClient
    stats = await TransmissionClient().get_session_stats()
    return bool(stats)


async def _check_amule() -> bool:
    from zascarr.services.amule import AMuleClient
    status = await AMuleClient().get_status()
    return status.get("reachable", False)


async def _check_reachable(coro) -> bool:
    try:
        return await asyncio.wait_for(coro, timeout=_EXTERNAL_CHECK_TIMEOUT_S)
    except Exception:
        return False


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    # ── PostgreSQL (crítico) ──
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # ── Servicios baremetal (no críticos para health, pero informativos).
    # En paralelo y con timeout corto: nunca deben convertir un GET
    # /api/health en una espera de hasta 60s (2 × 30s secuenciales). ──
    transmission_ok, amule_ok = await asyncio.gather(
        _check_reachable(_check_transmission()),
        _check_reachable(_check_amule()),
    )

    # ── VPN (vía fichero del host; nunca bloqueante) ──
    vpn_status, vpn_detail = _check_vpn()

    core_ok = db_ok
    all_ok = core_ok and transmission_ok and amule_ok
    status_str = "healthy" if all_ok else ("degraded" if core_ok else "unhealthy")

    # Si la VPN está en warning/stale, no baja el status global pero
    # añade "warnings" al payload para que sea VISIBLE (no silencioso).
    warnings = {}
    if vpn_status != "ok":
        warnings["vpn"] = vpn_detail

    return {
        "status": status_str,
        "version": settings.app_version,
        "checks": {
            "database":     "ok" if db_ok else "error",
            "transmission": "ok" if transmission_ok else "unreachable",
            "amule":        "ok" if amule_ok else "unreachable",
            "vpn":          vpn_status,
        },
        "warnings": warnings,
    }
