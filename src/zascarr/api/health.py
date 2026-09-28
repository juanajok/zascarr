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
import re
import time
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db

logger = structlog.get_logger()

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

# Tablas de dominio que deben existir si el esquema está íntegro (E6). Si una
# falta tras haber migrado, es señal de restauración/rollback a medias.
_DOMAIN_TABLES = ("series", "issues", "files", "wishlist")


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


def _alembic_head() -> str | None:
    """Revisión head de Alembic, leída de `alembic/versions` (sin conectar a BD).

    No se importa el paquete `alembic`: el directorio `alembic/` del propio repo
    sombrea al paquete instalado (`import alembic.config` resolvería el directorio
    local, que no tiene `config.py`). Head = la revisión que ninguna otra cita
    como `down_revision`."""
    versions_dir = Path(__file__).resolve().parents[3] / "alembic" / "versions"
    if not versions_dir.is_dir():
        # Fallback: cwd = raíz del repo (docker con el código montado en raíz).
        versions_dir = Path("alembic") / "versions"
    if not versions_dir.is_dir():
        return None

    revision_re = re.compile(r'^\s*revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
    down_re = re.compile(r'^\s*down_revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

    revisiones: set[str] = set()
    padres: set[str] = set()
    for fichero in versions_dir.glob("*.py"):
        texto = fichero.read_text(encoding="utf-8")
        revisiones.update(revision_re.findall(texto))
        padres.update(down_re.findall(texto))

    cabezas = revisiones - padres
    return next(iter(cabezas)) if len(cabezas) == 1 else None


async def _database_status(db: AsyncSession) -> tuple[str, str]:
    """Estado de la BD en cuatro valores (E6): unreachable | migration_required
    | schema_incompatible | ok. Devuelve también un detalle en español."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        # El detalle de la excepción (DSN, SQL, credenciales) se queda en el
        # servidor; /api/health es público y no debe exponerlo.
        logger.exception("health.db_unreachable")
        return "unreachable", "No se puede conectar con PostgreSQL."

    head = _alembic_head()
    try:
        version_num = (
            await db.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one_or_none()
    except Exception:
        version_num = None

    if version_num is None:
        return (
            "migration_required",
            "Conecta con PostgreSQL pero no hay esquema: ejecuta `alembic upgrade head`.",
        )
    if head is None:
        return (
            "schema_incompatible",
            "No se puede determinar el head de Alembic (¿falta alembic/versions o hay varios heads?).",
        )
    if version_num != head:
        return (
            "migration_required",
            f"Migración pendiente: la BD está en {version_num} y el código espera {head} "
            "(`alembic upgrade head`).",
        )

    faltantes = []
    for tabla in _DOMAIN_TABLES:
        existe = (
            await db.execute(text(f"SELECT to_regclass('{tabla}')"))
        ).scalar_one_or_none()
        if not existe:
            faltantes.append(tabla)
    if faltantes:
        return (
            "schema_incompatible",
            f"Esquema incompleto: faltan {', '.join(faltantes)} (¿restauración o rollback a medias?).",
        )
    return "ok", "Conectada y migrada."


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    # ── PostgreSQL (crítico): cuatro estados, no un ok/error binario (E6) ──
    db_status, db_detail = await _database_status(db)

    # ── Servicios baremetal (no críticos para health, pero informativos).
    # En paralelo y con timeout corto: nunca deben convertir un GET
    # /api/health en una espera de hasta 60s (2 × 30s secuenciales). ──
    transmission_ok, amule_ok = await asyncio.gather(
        _check_reachable(_check_transmission()),
        _check_reachable(_check_amule()),
    )

    # ── VPN (vía fichero del host; nunca bloqueante) ──
    vpn_status, vpn_detail = _check_vpn()

    core_ok = db_status == "ok"
    all_ok = core_ok and transmission_ok and amule_ok
    status_str = "healthy" if all_ok else ("degraded" if core_ok else "unhealthy")

    # Si la VPN está en warning/stale, no baja el status global pero
    # añade "warnings" al payload para que sea VISIBLE (no silencioso).
    warnings = {}
    if vpn_status != "ok":
        warnings["vpn"] = vpn_detail
    if db_status != "ok":
        warnings["database"] = db_detail

    return {
        "status": status_str,
        "version": settings.app_version,
        "checks": {
            "database":     db_status,
            "transmission": "ok" if transmission_ok else "unreachable",
            "amule":        "ok" if amule_ok else "unreachable",
            "vpn":          vpn_status,
        },
        "warnings": warnings,
    }
