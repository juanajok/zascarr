"""Health check endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.config import get_settings
from secuenciarr.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    settings = get_settings()

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        from secuenciarr.services.transmission import TransmissionClient
        stats = await TransmissionClient().get_session_stats()
        transmission_ok = bool(stats)
    except Exception:
        transmission_ok = False

    try:
        from secuenciarr.services.amule import AMuleClient
        status = await AMuleClient().get_status()
        amule_ok = status.get("reachable", False)
    except Exception:
        amule_ok = False

    # VPN check (WireGuard): warning si wg0 no existe, no error bloqueante
    import subprocess
    try:
        result = subprocess.run(["ip", "link", "show", "wg0"],
                                capture_output=True, timeout=2)
        vpn_ok = result.returncode == 0
    except Exception:
        vpn_ok = False

    core_ok = db_ok
    all_ok  = core_ok and transmission_ok and amule_ok
    status_str = "healthy" if all_ok else ("degraded" if core_ok else "unhealthy")

    return {
        "status": status_str,
        "version": settings.app_version,
        "checks": {
            "database":     "ok" if db_ok else "error",
            "transmission": "ok" if transmission_ok else "unreachable",
            "amule":        "ok" if amule_ok else "unreachable",
            "vpn_wg0":      "ok" if vpn_ok else "warning — sin VPN para torrents",
        },
    }
