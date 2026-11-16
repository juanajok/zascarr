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


_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00"
        b"\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


def _cbz(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.png", _PNG)


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
        z.writestr("001.png", _PNG)
    return buf.getvalue()


def test_verificacion_interna_rechaza_firma_y_primera_imagen(tmp_path):
    import zipfile

    from zascarr.services.paquetes_extraccion import PaqueteExtraccionError, _verificar_contenido
    temp = tmp_path / "t"
    temp.mkdir()
    (temp / "0001.cbz").write_bytes(b"Rar!\x1a\x07\x00")
    with pytest.raises(PaqueteExtraccionError, match="ZIP"):
        _verificar_contenido([{"nombre": "0001.cbz", "bytes": 7}], temp)
    (temp / "0001.cbz").unlink()
    with zipfile.ZipFile(temp / "0001.cbz", "w") as z:
        z.writestr("001.jpg", b"no es imagen")
    with pytest.raises(PaqueteExtraccionError, match="no se puede decodificar"):
        _verificar_contenido([{"nombre": "0001.cbz", "bytes": 13}], temp)


def test_extraer_rar_a_fichero_no_carga_en_memoria(tmp_path, monkeypatch):
    from zascarr.utils import lector_rar
    origen = tmp_path / "origen.rar"
    origen.write_bytes(b"Rar!\x1a\x07\x00")
    temporal = tmp_path / "tmp"
    temporal.mkdir()
    destino = tmp_path / "salida.cbz"

    def falso_ejecutar(argv, *, home, timeout, tope_salida, vigilar=None,
                       tope_escrito=None, pass_fds=()):
        carpeta = Path(argv[argv.index("-o") + 1])
        (carpeta / "extraido").write_bytes(b"x" * 1024)
        return 0, b"", b""

    monkeypatch.setattr(lector_rar, "_localizar", lambda _n: "/bin/unar")
    monkeypatch.setattr(lector_rar, "_ejecutar", falso_ejecutar)
    entrada = lector_rar.EntradaRar(0, "a.cbz", 1024, None, False, False)
    total = lector_rar.extraer_entrada_a(origen, entrada, destino, 2048, temporal=temporal)
    assert total == 1024 and destino.read_bytes() == b"x" * 1024
    assert not (temporal / "salida-0").exists() or not any((temporal / "salida-0").iterdir())


@pytest.mark.asyncio
async def test_identidad_duplicado_cambiado_y_huerfanos(tmp_path):
    import os

    from zascarr.config import get_settings
    from zascarr.services.paquetes_extraccion import PaqueteExtraccionError, limpiar_huerfanos
    get_settings.cache_clear()
    os.environ["COVERS_CACHE_PATH"] = str(tmp_path / "config")
    try:
        async with bd_efimera(URL) as url:
            migrar_a_head(url)
            motor = create_async_engine(url_asyncpg(url), poolclass=None)
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            try:
                d = tmp_path / "d"
                d.mkdir()
                p = d / "p.zip"
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("a.cbz", _cbz_bytes())
                ajustes = type("A", (), {})()
                ajustes.transmission_download_dir = str(d)
                ajustes.amule_incoming_dir = ""
                ajustes.downloads_path = ""
                ajustes.secret_key = "k"
                paquete = detectar_paquetes(ajustes=ajustes, secret="k")[0]
                async with fabrica() as s:
                    first = await crear_operacion(s, paquete)
                    again = await crear_operacion(s, paquete)
                    assert first.id == again.id
                    temp = tmp_path / "config" / ".paquetes" / str(first.id)
                    temp.mkdir(parents=True)
                    first.temp_dir = str(temp)
                    s.add(first)
                    await s.commit()
                    assert await limpiar_huerfanos(s) == 1
                    fila = await s.get(PaqueteOperacion, first.id)
                    assert fila.estado is PaqueteEstado.ERROR and fila.temp_dir is None
                    assert not temp.exists()
                p.write_bytes(b"PK\x03\x04cambiado")
                async with fabrica() as s:
                    with pytest.raises(PaqueteExtraccionError, match="cambió"):
                        await crear_operacion(s, paquete)
            finally:
                await motor.dispose()
    finally:
        os.environ.pop("COVERS_CACHE_PATH", None)
        get_settings.cache_clear()
