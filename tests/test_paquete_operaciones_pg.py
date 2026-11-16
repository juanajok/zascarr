"""#344 corte 3: migración 0044 y extracción/verificación durable."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import alembic, bd_efimera, bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import PaqueteEstado, PaqueteOperacion
from zascarr.services.paquetes import detectar_paquetes
from zascarr.services.paquetes_extraccion import crear_operacion, extraer_y_verificar

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")


def _cbz(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", b"\xff\xd8\xff\xd9")


def test_migracion_0044_upgrade_downgrade():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        alembic(url, "downgrade", "0043")
        alembic(url, "upgrade", "head")

        async def columnas() -> set[str]:
            motor = create_async_engine(url_asyncpg(url), poolclass=None)
            try:
                async with motor.connect() as c:
                    res = await c.execute(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='paquete_operaciones'"))
                    return {r[0] for r in res}
            finally:
                await motor.dispose()

        import asyncio
        assert {"paquete_clave", "items", "temp_dir", "estado"} <= asyncio.run(columnas())


@pytest.mark.asyncio
async def test_extraer_zip_termina_verificado_y_no_toca_files(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    from zascarr.config import get_settings
    get_settings.cache_clear()
    os.environ["COVERS_CACHE_PATH"] = str(config)
    try:
        async with bd_efimera(URL) as url:
            migrar_a_head(url)
            motor = create_async_engine(url_asyncpg(url), poolclass=None)
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            try:
                d = tmp_path / "descargas"
                d.mkdir()
                p = d / "paquete.zip"
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("01.cbz", _cbz_bytes())
                    z.writestr("leeme.txt", b"x")
                ajustes = type("A", (), {})()
                ajustes.transmission_download_dir = str(d)
                ajustes.amule_incoming_dir = ""
                ajustes.downloads_path = ""
                ajustes.secret_key = "k"
                paquete = detectar_paquetes(ajustes=ajustes, secret="k")[0]
                async with fabrica() as s:
                    op = await crear_operacion(s, paquete)
                    resultado = await extraer_y_verificar(s, op.id)
                    assert resultado.total_bytes > 0 and resultado.items
                async with fabrica() as s:
                    fila = await s.get(PaqueteOperacion, op.id)
                    assert fila.estado is PaqueteEstado.VERIFICADO and fila.temp_dir is None
                    assert (await s.execute(text("SELECT count(*) FROM files"))).scalar() == 0
                assert p.exists()
            finally:
                await motor.dispose()
    finally:
        os.environ.pop("COVERS_CACHE_PATH", None)
        get_settings.cache_clear()


def _cbz_bytes() -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("001.jpg", b"\xff\xd8\xff\xd9")
    return buf.getvalue()
