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
import shutil
import time
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.seguridad import aviso_de_exposicion, estado_de_seguridad

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

# #334: la copia diaria corre una vez al día. 26 h tolera un ciclo perdido;
# 48 h ya es un fallo visible (dos ciclos sin copia completa).
BACKUP_WARN_AFTER_S = 26 * 3600
BACKUP_FAIL_AFTER_S = 48 * 3600

_BACKUP_ERRORES = {
    "offsite_mount_missing": "el disco de respaldo no está montado",
    "offsite_same_device": "la copia no está en un dispositivo distinto",
    "pg_dump_failed": "el volcado falló",
    "gzip_invalid": "el volcado no pasa gzip -t",
    "header_missing": "el volcado no tiene la cabecera esperada",
    "tables_missing": "al volcado le faltan tablas requeridas",
    "decompress_failed": "el volcado no se puede descomprimir",
    "not_found": "no se encontró el volcado de la copia",
    "empty": "el volcado de la copia salió vacío",
    "verify_failed": "la copia no pasó la comprobación de integridad",
    "manifest_failed": "no se pudo escribir el manifiesto",
    "offsite_copy_failed": "la copia fuera del disco falló",
    "offsite_verify_failed": "la copia fuera del disco no coincide",
    "anchor_sync_failed": "no se pudieron sincronizar las anclas",
    "status_write_failed": "no se pudo escribir el registro de estado",
    "disk_full": "no hay espacio suficiente en el disco",
    "unexpected": "error inesperado",
}

# #334 B2: la restauración de comprobación es mensual. 35 días da margen sobre
# la cadencia; 70 es el doble, para que un fallo no pase desapercibido.
RESTORE_WARN_AFTER_S = 35 * 86400
RESTORE_FAIL_AFTER_S = 70 * 86400

_RESTORE_ERRORES = {
    "manifest_ausente": "no hay manifiesto del dump",
    "manifest_sin_codigo_desplegado": "el manifiesto no acredita el commit desplegado",
    "manifest_no_coincide": "el manifiesto no coincide con el dump",
    "sha256_no_coincide": "el .sha256 no coincide con el dump",
    "gzip_invalid": "el dump no pasa gzip -t",
    "header_missing": "el dump no tiene la cabecera esperada",
    "tables_missing": "al dump le faltan tablas requeridas",
    "createdb_failed": "no se pudo crear la base desechable",
    "restore_failed": "la restauración falló",
    "tabla_ausente": "falta una tabla en la restauración",
    "tablas_distintas": "el número de tablas no coincide",
    "recuento_distinto": "un recuento no coincide",
    "alembic_distinto": "la revisión de Alembic no coincide",
    "disk_full": "no hay espacio suficiente en el disco",
    "unexpected": "error inesperado",
}

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


def _backup_status() -> tuple[str, str]:
    """Lee el estado que escribe scripts/backup.sh. Devuelve (status, detail).

    El fichero lo escribe el host y el compose lo monta read-only; si falta, el
    timer no está instalado o nunca ha corrido. El detalle no lleva rutas ni
    datos de la biblioteca: /api/health es público.
    """
    settings = get_settings()
    state_path = Path(settings.backup_status_file)

    if not state_path.exists():
        return "error", ("No hay registro de copias: el timer no ha corrido "
                         "o no está instalado.")

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return "error", f"Registro de copias ilegible: {type(exc).__name__}."

    status = state.get("status")
    error = state.get("error")
    causa = _BACKUP_ERRORES.get(error, error or "causa desconocida")

    if status == "failed":
        return "error", f"La última copia falló: {causa}."
    if status == "degraded":
        return "warning", ("La copia diaria es correcta, pero hay un aviso: "
                           f"{causa}.")
    if status != "ok":
        return "error", "El registro de copias no tiene un estado reconocible."

    last = state.get("last_success_at_epoch") or 0
    if not last:
        return "error", "El registro de copias no tiene una copia completa."
    try:
        age = time.time() - float(last)
    except (TypeError, ValueError):
        return "error", "El registro de copias no tiene una fecha válida."

    if age > BACKUP_FAIL_AFTER_S:
        return "error", f"Sin copia completa desde hace {age / 3600:.0f} h."
    if age > BACKUP_WARN_AFTER_S:
        return "warning", f"La última copia completa es de hace {age / 3600:.0f} h."
    return "ok", "Copia reciente verificada."


def _restore_status() -> tuple[str, str]:
    """Lee el estado que escribe scripts/probar_restauracion.sh (#334 B2)."""
    settings = get_settings()
    state_path = Path(settings.restore_status_file)

    if not state_path.exists():
        return "error", ("No hay registro de restauración: el timer no ha "
                         "corrido o no está instalado.")

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return "error", f"Registro de restauración ilegible: {type(exc).__name__}."

    status = state.get("status")
    error = state.get("error")
    causa = _RESTORE_ERRORES.get(error, error or "causa desconocida")

    if status == "failed":
        return "error", f"La última restauración falló: {causa}."
    if status == "warning":
        return "warning", f"La restauración se completó con un aviso: {causa}."
    if status != "ok":
        return "error", "El registro de restauración no tiene un estado reconocible."

    last = state.get("last_ok_at_epoch") or 0
    if not last:
        return "error", "El registro de restauración no tiene una restauración correcta."
    try:
        age = time.time() - float(last)
    except (TypeError, ValueError):
        return "error", "El registro de restauración no tiene una fecha válida."

    if age > RESTORE_FAIL_AFTER_S:
        return "error", f"Sin restauración correcta desde hace {age / 86400:.0f} días."
    if age > RESTORE_WARN_AFTER_S:
        return "warning", f"La última restauración correcta es de hace {age / 86400:.0f} días."
    return "ok", "Restauración reciente verificada."


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


async def _estado_cliente(activo: bool, sonda) -> str:
    """`disabled` si está apagado en Ajustes: ni se sondea ni cuenta como fallo. Un cliente que el
    coleccionista no usa ponía el semáforo en «Atención» con un punto rojo (revisión visual,
    2026-10-20); en una instalación nueva, siempre, porque vienen apagados por defecto."""
    if not activo:
        return "disabled"
    return "ok" if await _check_reachable(sonda()) else "unreachable"


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
            "No se puede determinar el head de Alembic "
            "(¿falta alembic/versions o hay varios heads?).",
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
            f"Esquema incompleto: faltan {', '.join(faltantes)} "
            "(¿restauración o rollback a medias?).",
        )
    return "ok", "Conectada y migrada."


def _disco_bytes(mb: int) -> int:
    return max(0, int(mb)) * 1024 * 1024


def _disk_status() -> tuple[str, str]:
    """Espacio libre en rutas locales; no mira la biblioteca de red ni bloquea."""
    settings = get_settings()
    rutas = [Path(p.strip()) for p in (settings.disk_paths or "").split(",") if p.strip()]
    libres: list[int] = []
    for ruta in rutas:
        candidata = ruta
        while not candidata.exists() and candidata != candidata.parent:
            candidata = candidata.parent
        if not candidata.exists() or not candidata.is_dir():
            continue
        try:
            libres.append(shutil.disk_usage(candidata).free)
        except OSError:
            continue
    if not libres:
        return "disabled", "Sin rutas locales accesibles para comprobar el disco."
    libre = min(libres)
    warn = _disco_bytes(settings.disk_warn_free_mb)
    error = _disco_bytes(settings.disk_error_free_mb)
    if libre < error:
        return "error", (
            f"Quedan {libre / 1024 / 1024:.0f} MB libres en el disco de datos, "
            f"por debajo del mínimo de {settings.disk_error_free_mb} MB. "
            "Libera espacio o mueve la biblioteca a otro disco y vuelve a intentarlo. "
            "ZascArr no ha borrado nada."
        )
    if libre < warn:
        return "warning", (
            f"Quedan {libre / 1024 / 1024:.0f} MB libres en el disco de datos. "
            "Libera espacio o mueve la biblioteca a otro disco antes de que se llene. "
            "ZascArr no ha borrado nada."
        )
    return "ok", f"Quedan {libre / 1024 / 1024:.0f} MB libres en el disco de datos."


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    # ── PostgreSQL (crítico): cuatro estados, no un ok/error binario (E6) ──
    db_status, db_detail = await _database_status(db)

    # ── Servicios baremetal (no críticos para health, pero informativos).
    # En paralelo y con timeout corto: nunca deben convertir un GET
    # /api/health en una espera de hasta 60s (2 × 30s secuenciales). ──
    transmission, amule = await asyncio.gather(
        _estado_cliente(settings.transmission_enabled, _check_transmission),
        _estado_cliente(settings.amule_enabled, _check_amule),
    )

    # ── VPN (vía fichero del host; nunca bloqueante) ──
    vpn_status, vpn_detail = _check_vpn()

    # ── Copias de seguridad (fichero del host; no bloqueante) ──
    backup_status, backup_detail = _backup_status()

    # ── Restauración de comprobación (fichero del host; no bloqueante) ──
    restore_status, restore_detail = _restore_status()

    # ── Disco local (no bloqueante; nunca mira la biblioteca de red) ──
    # `shutil.disk_usage` es E/S síncrona: fuera del bucle de eventos (CLAUDE.md §4).
    disk_status, disk_detail = await asyncio.to_thread(_disk_status)

    core_ok = db_status == "ok"
    backup_ok = backup_status == "ok"
    restore_ok = restore_status == "ok"
    disk_ok = disk_status in ("ok", "disabled")
    all_ok = (
        core_ok
        and transmission in ("ok", "disabled")
        and amule in ("ok", "disabled")
        and backup_ok
        and restore_ok
        and disk_ok
    )
    status_str = "healthy" if all_ok else ("degraded" if core_ok else "unhealthy")

    # Si la VPN está en warning/stale, no baja el status global pero
    # añade "warnings" al payload para que sea VISIBLE (no silencioso).
    warnings = {}
    if vpn_status != "ok":
        warnings["vpn"] = vpn_detail
    if db_status != "ok":
        warnings["database"] = db_detail
    if backup_status != "ok":
        warnings["backup"] = backup_detail
    if restore_status != "ok":
        warnings["restore"] = restore_detail
    if disk_status not in ("ok", "disabled"):
        warnings["disk"] = disk_detail
    # A11: puerto abierto (o dirección pública) y ninguna contraseña. Solo avisa:
    # nunca bloquea ni cambia el estado, igual que la VPN.
    exposicion = aviso_de_exposicion(settings)
    if exposicion:
        warnings["exposicion"] = exposicion

    return {
        "status": status_str,
        "version": settings.app_version,
        "checks": {
            "database":     db_status,
            "transmission": transmission,   # ok | unreachable | disabled
            "amule":        amule,
            "vpn":          vpn_status,
            "backup":       backup_status,
            "restore":      restore_status,
            "disk":         disk_status,
        },
        # B8: estado de cada fuente de metadatos (on/off en Ajustes).
        # GCD hoy solo participa en Descubrir (el enricher no lo consulta).
        "fuentes": {
            "comic_vine": "enabled" if settings.comicvine_enabled else "disabled",
            "anilist":    "enabled" if settings.anilist_enabled else "disabled",
            "tebeosfera": "enabled" if settings.tebeosfera_enabled else "disabled",
            "gcd":        "enabled" if settings.gcd_enabled else "disabled",
        },
        # A11: seguridad aparte de la salud técnica (ver estado_de_seguridad).
        "seguridad": estado_de_seguridad(settings),
        "warnings": warnings,
    }
