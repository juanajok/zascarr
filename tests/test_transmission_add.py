"""Un torrent-add rechazado no puede perderse en silencio (2026-11-16)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import structlog

from zascarr.services.transmission import TransmissionClient


@pytest.mark.asyncio
async def test_si_la_carpeta_no_existe_reintenta_con_la_de_transmission():
    """Caso real: Ajustes apuntaba a /media/downloads/comics (no existe);
    se reintenta sin download-dir para no dejar el deseo colgado."""
    cliente = TransmissionClient()
    cliente._rpc = AsyncMock(side_effect=[
        {"result": "invalid download dir", "arguments": {}},
        {"result": "success",
         "arguments": {"torrent-added": {"name": "Absolute Wonder Woman #20"}}},
    ])

    with structlog.testing.capture_logs() as registros:
        añadido = await cliente.add_torrent("magnet:?xt=urn:btih:abc")

    assert añadido["name"] == "Absolute Wonder Woman #20"
    assert cliente._rpc.await_count == 2
    assert any(r["event"] == "transmission.download_dir_invalido" for r in registros)
    assert any(r["event"] == "transmission.added_carpeta_por_defecto"
               for r in registros)


@pytest.mark.asyncio
async def test_si_los_dos_intentos_fallan_se_registra_el_motivo_sin_url():
    cliente = TransmissionClient()
    cliente._rpc = AsyncMock(return_value={"result": "auth failed", "arguments": {}})

    with structlog.testing.capture_logs() as registros:
        assert await cliente.add_torrent("magnet:?xt=urn:btih:abc") is None

    fallo = [r for r in registros if r["event"] == "transmission.add_failed"]
    assert fallo and fallo[0]["resultado"] == "auth failed"
    assert "magnet" not in str(fallo[0])
