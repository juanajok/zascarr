"""OCTA-D3: los borradores de revisión caducados se purgan en mantenimiento."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from zascarr.services.borradores_revision import BorradoresRevision


class _Resultado:
    rowcount = 4


class _Db:
    def __init__(self):
        self.execute = AsyncMock(return_value=_Resultado())


@pytest.mark.asyncio
async def test_purga_caducados_devuelve_filas_borradas():
    db = _Db()
    servicio = BorradoresRevision(db)  # type: ignore[arg-type]
    assert await servicio.purgar_caducados(ahora=datetime(2026, 11, 17, tzinfo=UTC)) == 4
    sentencia = db.execute.await_args.args[0]
    assert "revision_borradores" in str(sentencia)
    assert "caduca" in str(sentencia)
