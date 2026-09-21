"""conftest.py — Configuración de pytest para SecuenciArr."""
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
