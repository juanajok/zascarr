"""Un torrent-add rechazado no puede perderse en silencio (2026-11-16)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import structlog

from zascarr.services.transmission import TransmissionClient


@pytest.mark.asyncio
async def test_si_el_rpc_no_anade_nada_se_registra_el_motivo():
    cliente = TransmissionClient()
    cliente._rpc = AsyncMock(return_value={"result": "invalid download dir",
                                           "arguments": {}})
    with structlog.testing.capture_logs() as registros:
        assert await cliente.add_torrent("magnet:?xt=urn:btih:abc") is None

    fallo = [r for r in registros if r["event"] == "transmission.add_failed"]
    assert fallo and fallo[0]["resultado"] == "invalid download dir"
    assert "magnet" not in str(fallo[0])
