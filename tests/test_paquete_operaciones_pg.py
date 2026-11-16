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


def test_base_temporal_rechaza_symlink(tmp_path, monkeypatch):
    from zascarr.config import get_settings
    from zascarr.services.paquetes_extraccion import PaqueteExtraccionError, _base_temporal
    config = tmp_path / "config"
    config.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (config / ".paquetes").symlink_to(fuera, target_is_directory=True)
    monkeypatch.setenv("COVERS_CACHE_PATH", str(config))
    get_settings.cache_clear()
    try:
        with pytest.raises((PaqueteExtraccionError, OSError)):
            _base_temporal()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_disco_lleno_deja_error_y_limpia(tmp_path, monkeypatch):
    from zascarr.config import get_settings
    from zascarr.services import paquetes_extraccion as modulo
    from zascarr.utils.espacio import EspacioInsuficienteError
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
            monkeypatch.setenv("COVERS_CACHE_PATH", str(tmp_path / "config"))
            get_settings.cache_clear()

            def sin_espacio(*_a, **_k):
                raise EspacioInsuficienteError(bytes_libres=0, bytes_necesarios=1, contexto="x")

            monkeypatch.setattr(modulo, "comprobar_espacio", sin_espacio)
            async with fabrica() as s:
                op = await crear_operacion(s, paquete)
                with pytest.raises(EspacioInsuficienteError):
                    await extraer_y_verificar(s, op.id)
                await s.refresh(op)
                assert op.estado is PaqueteEstado.ERROR and op.temp_dir is None
        finally:
            await motor.dispose()
            os.environ.pop("COVERS_CACHE_PATH", None)
            get_settings.cache_clear()


async def _con_paquete(tmp_path, monkeypatch):
    from sqlalchemy import text as _text

    from zascarr.config import get_settings
    motor = create_async_engine(url_asyncpg(URL), poolclass=None)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        await s.execute(_text("TRUNCATE paquete_operaciones"))
        await s.commit()
    d = tmp_path / "d"
    d.mkdir()
    p = d / "p.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.cbz", _cbz_bytes() + b"x" * 200)
    ajustes = type("A", (), {})()
    ajustes.transmission_download_dir = str(d)
    ajustes.amule_incoming_dir = ""
    ajustes.downloads_path = ""
    ajustes.secret_key = "k"
    paquete = detectar_paquetes(ajustes=ajustes, secret="k")[0]
    monkeypatch.setenv("COVERS_CACHE_PATH", str(tmp_path / "config"))
    get_settings.cache_clear()
    return URL, motor, fabrica, paquete


@pytest.mark.asyncio
async def test_bomba_aborta_durante_escritura_y_limpia(tmp_path, monkeypatch):
    from zascarr.config import get_settings
    from zascarr.services import paquetes_extraccion as modulo
    _url, motor, fabrica, paquete = await _con_paquete(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(modulo, "MAX_BYTES_ENTRADA", 5)
        async with fabrica() as s:
            op = await crear_operacion(s, paquete)
            with pytest.raises(modulo.PaqueteExtraccionError):
                await extraer_y_verificar(s, op.id)
            await s.refresh(op)
            assert op.estado is PaqueteEstado.ERROR and op.temp_dir is None
        assert paquete.ruta.exists()
        base = tmp_path / "config" / ".paquetes"
        assert not list(base.glob("*")) if base.exists() else True
    finally:
        await motor.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fallo_a_mitad_limpia_y_conserva_original(tmp_path, monkeypatch):
    from zascarr.config import get_settings
    from zascarr.services import paquetes_extraccion as modulo
    _url, motor, fabrica, paquete = await _con_paquete(tmp_path, monkeypatch)
    try:
        def falla(_items, _temp, _fd=None):
            raise modulo.PaqueteExtraccionError("x", "fallo simulado")
        monkeypatch.setattr(modulo, "_verificar_contenido", falla)
        async with fabrica() as s:
            op = await crear_operacion(s, paquete)
            with pytest.raises(modulo.PaqueteExtraccionError):
                await extraer_y_verificar(s, op.id)
            await s.refresh(op)
            assert op.estado is PaqueteEstado.ERROR and op.temp_dir is None
        assert paquete.ruta.exists()
    finally:
        await motor.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dos_creaciones_concurrentes_misma_identidad(tmp_path, monkeypatch):
    import asyncio as _asyncio

    from zascarr.config import get_settings
    url, motor, fabrica, paquete = await _con_paquete(tmp_path, monkeypatch)
    try:
        async def uno():
            async with fabrica() as s:
                return await crear_operacion(s, paquete)
        resultados = await _asyncio.gather(uno(), uno(), return_exceptions=True)
        assert not any(isinstance(x, BaseException) for x in resultados)
        assert resultados[0].id == resultados[1].id
    finally:
        await motor.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_rar_multi_entrada_mockeado_no_reutiliza_carpeta(tmp_path, monkeypatch):
    from zascarr.services import paquetes_extraccion as modulo
    from zascarr.services.paquetes import EntradaPaquete, ListadoPaquete, PaquetePendiente
    from zascarr.utils import lector_rar
    p = PaquetePendiente(ruta=tmp_path / "x.rar", raiz=tmp_path, relativa="x.rar",
                         nombre="x.rar", tamano=1, mtime_ns=1, firma="RAR",
                         estado="listo", causa="", dev=1, ino=2)
    listado = ListadoPaquete(
        paquete=p, formato="RAR", bytes_estimados=2,
        entradas=(EntradaPaquete("a.cbz", 1, "CBZ", True),
                  EntradaPaquete("b.cbz", 1, "CBZ", True)), ignoradas=())
    monkeypatch.setattr(lector_rar, "disponible", lambda: True)
    llamadas = []

    def falso(ruta, entrada, destino, tope, *, temporal, pass_fds=()):
        llamadas.append(entrada.nombre)
        destino.write_bytes(b"x")
        return 1
    monkeypatch.setattr(lector_rar, "extraer_entrada_a", falso)
    temp = tmp_path / "temp"
    temp.mkdir()
    items = modulo._escribir_rar(p, listado, temp, 10,
                                 os.open(temp, os.O_RDONLY | os.O_DIRECTORY))
    assert llamadas == ["a.cbz", "b.cbz"] and len(items) == 2


@pytest.mark.skipif(not (Path("tests/fixtures/rar/minimo_rar4.cbr").exists()),
                    reason="fixture RAR ausente")
def test_fixture_rar_real_tiene_varias_entradas():
    from zascarr.utils import lector_rar
    if not lector_rar.disponible():
        pytest.skip("sin unar/lsar")
    import tempfile
    with tempfile.TemporaryDirectory() as casa:
        listado = lector_rar.listar(Path("tests/fixtures/rar/minimo_rar4.cbr"),
                                    temporal=Path(casa), max_bytes_declarados=8 * 1024 ** 3)
    assert len(listado.entradas) >= 2
    assert sum(1 for e in listado.entradas if e.nombre.lower().endswith((".cbz", ".cbr"))) == 0
    # El fixture legal solo contiene JPG: multi-entrada RAR de tebeos es NOT RUN
    # (no hay creador de RAR en la imagen legal).


@pytest.mark.asyncio
async def test_timeout_worker_mata_y_limpia(tmp_path, monkeypatch):
    from zascarr.config import get_settings
    from zascarr.services import paquetes_extraccion as modulo
    _url, motor, fabrica, paquete = await _con_paquete(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(modulo, "_ZIP_TIMEOUT", 0.001)
        async with fabrica() as s:
            op = await crear_operacion(s, paquete)
            with pytest.raises(modulo.PaqueteExtraccionError):
                await extraer_y_verificar(s, op.id)
            await s.refresh(op)
            assert op.estado is PaqueteEstado.ERROR and op.temp_dir is None
        assert paquete.ruta.exists()
    finally:
        await motor.dispose()
        get_settings.cache_clear()


def test_rar_real_extraccion_streaming_fixture(tmp_path):
    from zascarr.utils import lector_rar
    if not lector_rar.disponible():
        pytest.skip("sin unar/lsar")
    fixture = Path("tests/fixtures/rar/solido_rar4.cbr")
    import tempfile
    with tempfile.TemporaryDirectory() as casa:
        lista = lector_rar.listar(fixture, temporal=Path(casa),
                                  max_bytes_declarados=8 * 1024 ** 3)
        assert len(lista.entradas) >= 2
        salida = tmp_path / "primera"
        primera = lista.entradas[0]
        lector_rar.extraer_entrada_a(fixture, primera, salida, primera.tamano,
                                     temporal=Path(casa))
        assert salida.stat().st_size == primera.tamano
