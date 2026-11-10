# ruff: noqa: E501, F811
"""#564: el rescan no registra la cuarentena ni el diario `.zascarr/` de la conversión."""
from __future__ import annotations

import os

import pytest

from tests.test_rescan_biblioteca_pg import _filas, _rescan, mundo, url_bd  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_el_rescan_no_registra_la_cuarentena_zascarr(mundo):
    await _rescan(mundo)
    antes = await _filas(mundo)
    cuarentena = mundo.lib / ".zascarr" / "originales" / "abc" / "op"
    cuarentena.mkdir(parents=True)
    (cuarentena / "original.cbr").write_bytes(b"RAR-en-cuarentena")
    diario = mundo.lib / ".zascarr" / "diario" / "abc"
    diario.mkdir(parents=True)
    (diario / "op.json").write_text("{}")
    await _rescan(mundo)
    despues = await _filas(mundo)
    assert set(despues) == set(antes)
