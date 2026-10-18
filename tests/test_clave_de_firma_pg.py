"""La clave que firma la cookie de sesión se genera UNA vez, vive en la base de datos y sobrevive a reinicios.

Es la otra credencial «local» del sistema y la razón de que el `.env` solo tenga una obligatoria (`DB_PASSWORD`): no hay
nada que inicializar ni conservar en el `.env` para ella, pero sí tiene que conservarse en la base. Si un reinicio o una
reejecución del instalador la regenerase, todas las sesiones se invalidarían a la vez.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import bd_efimera, migrar_a_head, url_asyncpg
from zascarr.config import get_settings
from zascarr.services.runtime_settings import RuntimeSettingsService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]


async def _arrancar(url: str) -> str:
    """Un «arranque» de la app: motor nuevo, sesión nueva, `ensure_secret_key` y commit (como el lifespan)."""
    motor = create_async_engine(url_asyncpg(url))
    try:
        async with async_sessionmaker(motor, expire_on_commit=False)() as sesion:
            clave = await RuntimeSettingsService(sesion).ensure_secret_key()
            await sesion.commit()
            return clave
    finally:
        await motor.dispose()


async def test_la_clave_de_firma_se_genera_una_vez_y_se_conserva_entre_arranques():
    anterior = get_settings().secret_key
    try:
        async with bd_efimera(URL) as url:
            migrar_a_head(url)
            primera = await _arrancar(url)
            assert re.fullmatch(r"[0-9a-f]{64}", primera)
            for _ in range(3):                                   # reinicios sucesivos: motor y sesión nuevos
                assert await _arrancar(url) == primera
    finally:
        get_settings().secret_key = anterior


async def test_la_clave_de_firma_no_esta_en_el_env_ni_en_su_plantilla():
    """La clave no es una credencial del `.env`: no hay línea que inicializar, proteger ni conservar ahí."""
    plantilla = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"^\s*#?\s*SECRET_KEY=", plantilla, re.M | re.I)
