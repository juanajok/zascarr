"""conftest.py — Configuración de pytest para ZascArr."""
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
