# ruff: noqa: E501
"""#264 A: apartar copias idénticas con token, cuarentena y deshacer (PG + FS real)."""
from __future__ import annotations

import errno
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import (
    ApartadoEstado,
    ApartadoGrupo,
    ApartadoGrupoEstado,
    ApartadoOperacion,
    File,
    FileFormat,
)
from zascarr.services.apartado_duplicados import (
    ApartadoDuplicadosService,
    GrupoEntrada,
    digest_rutas,
)
from zascarr.services.tokens_revision import (
    GrupoFirmado,
    crear_token_apartar,
    verificar_token_apartar,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
SECRET = "secreto-de-prueba-apartado"


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    async with b.motor.begin() as c:
        await c.execute(text(
            "TRUNCATE apartado_grupos, apartado_operaciones CASCADE"))
    yield b
    await b.cerrar()


def _lib(tmp_path: Path) -> Path:
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    (tmp_path / "A" / "uno.cbz").write_bytes(b"contenido-identico")
    (tmp_path / "B" / "dos.cbz").write_bytes(b"contenido-identico")
    return tmp_path


def _servicio(session, library: Path) -> ApartadoDuplicadosService:
    return ApartadoDuplicadosService(
        session, settings=SimpleNamespace(library_path=library, secret_key=SECRET),
        secret=SECRET)


async def _preparar(banco, library, *, file_movida=False, confirmar=True):
    from zascarr.core.importer_triage import sha256_streaming
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, [str(r) for r in rutas], 0)
        if file_movida:
            s.add(File(file_path=str(rutas[1]), file_name=rutas[1].name,
                       file_format=FileFormat.CBZ, file_size_bytes=rutas[1].stat().st_size,
                       sha256_hash=sha, file_mtime_ns=rutas[1].stat().st_mtime_ns))
            await s.commit()
        resultado = None
        if confirmar:
            resultado = await servicio.confirmar(vista.token, [
                GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    return rutas, sha, vista, resultado


@pytest.mark.asyncio
async def test_previsualizar_no_escribe_y_confirmar_mueve_y_repunta(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library, file_movida=True)
    assert resultado.estado == "confirmada"
    assert resultado.grupos[0].estado == "movido"
    assert not rutas[1].exists()
    apartada = library / ".zascarr" / "apartados" / resultado.operacion / "B" / "dos.cbz"
    assert apartada.exists() and apartada.read_bytes() == rutas[0].read_bytes()
    async with banco.fabrica() as s:
        fila = (await s.execute(select(File))).scalars().one()
        assert fila.file_path == str(rutas[0])
        op = await s.get(ApartadoOperacion, __import__("uuid").UUID(resultado.operacion))
        assert op is not None and op.estado == ApartadoEstado.CONFIRMADA


@pytest.mark.asyncio
async def test_idempotente_y_token_verificado(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library)
    firmada = verificar_token_apartar(vista.token, SECRET)
    assert firmada is not None and firmada.operacion == resultado.operacion
    async with banco.fabrica() as s:
        segundo = await _servicio(s, library).confirmar(vista.token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
        grupos = (await s.execute(select(ApartadoGrupo))).scalars().all()
    assert segundo.idempotente is True
    assert len(grupos) == 1
    assert not rutas[1].exists()


@pytest.mark.asyncio
async def test_contenido_cambiado_rechaza_el_grupo(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, _ = await _preparar(banco, library, confirmar=False)
    rutas[1].write_bytes(b"otro-contenido")
    async with banco.fabrica() as s:
        resultado = await _servicio(s, library).confirmar(vista.token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    assert resultado.grupos[0].estado == "rechazado"
    assert resultado.grupos[0].motivo == "contenido_cambiado"
    assert rutas[1].exists()


@pytest.mark.asyncio
async def test_deshacer_y_sitio_ocupado_no_sobrescribe(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library)
    assert not rutas[1].exists()
    rutas[1].write_bytes(b"archivo-nuevo")
    async with banco.fabrica() as s:
        negado = await _servicio(s, library).deshacer(resultado.operacion)
    assert negado.estado == "confirmada"
    assert rutas[1].read_bytes() == b"archivo-nuevo"
    assert (library / ".zascarr" / "apartados" / resultado.operacion / "B" / "dos.cbz").exists()
    rutas[1].unlink()
    async with banco.fabrica() as s:
        deshecho = await _servicio(s, library).deshacer(resultado.operacion)
    assert deshecho.estado == "deshecha"
    assert rutas[1].read_bytes() == b"contenido-identico"
    async with banco.fabrica() as s:
        op = await s.get(ApartadoOperacion, __import__("uuid").UUID(resultado.operacion))
        assert op.estado == ApartadoEstado.DESHECHA


@pytest.mark.asyncio
async def test_exdev_falla_cerrado_sin_copiar(banco, tmp_path, monkeypatch):
    library = _lib(tmp_path)
    rutas, sha, vista, _ = await _preparar(banco, library, confirmar=False)
    real_replace = os.replace

    def exdev(src, dst):
        raise OSError(errno.EXDEV, "cross-device")

    monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", exdev)
    try:
        async with banco.fabrica() as s:
            resultado = await _servicio(s, library).confirmar(vista.token, [
                GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    finally:
        monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", real_replace)
    assert resultado.grupos[0].estado in ("rechazado", "error")
    assert rutas[0].exists() and rutas[1].exists()


@pytest.mark.asyncio
async def test_reconciliar_en_curso_tras_muerte_entre_mover_y_commit(banco, tmp_path):
    library = _lib(tmp_path)
    from zascarr.core.importer_triage import sha256_streaming
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    operacion = uuid4()
    destino = library / ".zascarr" / "apartados" / str(operacion) / "B" / "dos.cbz"
    destino.parent.mkdir(parents=True)
    os.replace(rutas[1], destino)
    token = crear_token_apartar(str(operacion), (
        GrupoFirmado(sha, digest_rutas(["A/uno.cbz", "B/dos.cbz"]), 0, 2),), SECRET)
    async with banco.fabrica() as s:
        op = ApartadoOperacion(id=operacion, estado=ApartadoEstado.EN_CURSO,
                               token_hasta=datetime.now(UTC), total_grupos=1, total_archivos=1)
        s.add(op)
        s.add(ApartadoGrupo(
            operacion_id=operacion, grupo_clave=sha, sha256=sha,
            size_bytes=rutas[0].stat().st_size, estado=ApartadoGrupoEstado.PENDIENTE,
            detalle={"keep_index": 0, "rutas": ["A/uno.cbz", "B/dos.cbz"], "items": [
                {"ruta": "B/dos.cbz", "estado": "pendiente", "destino": str(destino)}]}))
        await s.commit()
        resultado = await _servicio(s, library).confirmar(token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    assert resultado.estado == "confirmada"
    assert not rutas[1].exists() and destino.exists()


@pytest.mark.asyncio
async def test_previsualizar_no_escribe_bd_ni_disco(banco, tmp_path):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    antes = [(p.stat().st_mtime_ns, p.read_bytes()) for p in rutas]
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, rutas, 0)
        assert await s.get(ApartadoOperacion, __import__("uuid").UUID(vista.operacion)) is None
    assert [(p.stat().st_mtime_ns, p.read_bytes()) for p in rutas] == antes
    assert verificar_token_apartar(vista.token, SECRET) is not None


@pytest.mark.asyncio
async def test_sin_file_no_crea_catalogo(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library)
    async with banco.fabrica() as s:
        assert (await s.execute(select(File))).scalars().all() == []
    assert resultado.grupos[0].estado == "movido"


@pytest.mark.asyncio
async def test_dos_filas_file_es_ambiguo(banco, tmp_path):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        for r in rutas:
            s.add(File(file_path=str(r), file_name=r.name, file_format=FileFormat.CBZ,
                       file_size_bytes=r.stat().st_size, sha256_hash=sha,
                       file_mtime_ns=r.stat().st_mtime_ns))
        await s.commit()
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, rutas, 0)
        resultado = await servicio.confirmar(vista.token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    assert resultado.grupos[0].estado == "rechazado"
    assert resultado.grupos[0].motivo == "catalogo_ambiguo"
    assert rutas[0].exists() and rutas[1].exists()


@pytest.mark.asyncio
async def test_deshacer_es_idempotente(banco, tmp_path):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library)
    async with banco.fabrica() as s:
        primero = await _servicio(s, library).deshacer(resultado.operacion)
    async with banco.fabrica() as s:
        segundo = await _servicio(s, library).deshacer(resultado.operacion)
    assert primero.estado == segundo.estado == "deshecha"
    assert segundo.idempotente is True
    assert rutas[1].exists()


@pytest.mark.asyncio
async def test_fallo_al_mover_compensa_las_ya_movidas(banco, tmp_path, monkeypatch):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    (tmp_path / "C").mkdir()
    (tmp_path / "C" / "tres.cbz").write_bytes(b"contenido-identico")
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz", library / "C" / "tres.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, [str(r) for r in rutas], 0)
    llamadas = {"n": 0}
    real_replace = os.replace

    def falla_en_la_segunda(src, dst):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise OSError(errno.EIO, "fallo simulado")
        return real_replace(src, dst)

    monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", falla_en_la_segunda)
    try:
        async with banco.fabrica() as s:
            resultado = await _servicio(s, library).confirmar(vista.token, [
                GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    finally:
        monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", real_replace)
    assert resultado.grupos[0].estado in ("rechazado", "error")
    assert all(r.exists() for r in rutas)


@pytest.mark.asyncio
async def test_token_de_deshacer_no_sirve_para_confirmar(banco, tmp_path):
    from zascarr.services.apartado_duplicados import TokenApartadoInvalido
    from zascarr.services.tokens_revision import crear_token_apartar
    library = _lib(tmp_path)
    token = crear_token_apartar(uuid4(), (), SECRET, accion="deshacer")
    async with banco.fabrica() as s:
        with pytest.raises(TokenApartadoInvalido):
            await _servicio(s, library).confirmar(token, [])


@pytest.mark.asyncio
async def test_file_original_persistido_antes_de_mover_y_reintento_reconcilia(banco, tmp_path, monkeypatch):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        s.add(File(file_path=str(rutas[1]), file_name=rutas[1].name,
                   file_format=FileFormat.CBZ, file_size_bytes=rutas[1].stat().st_size,
                   sha256_hash=sha, file_mtime_ns=rutas[1].stat().st_mtime_ns))
        await s.commit()
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, rutas, 0)

        async def muere(_self, _op, _grupo):
            raise RuntimeError("proceso muerto antes de mover")

        monkeypatch.setattr(type(servicio), "_procesar_grupo", muere)
        with pytest.raises(RuntimeError):
            await servicio.confirmar(vista.token, [GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
        grupo = (await s.execute(select(ApartadoGrupo))).scalars().one()
        assert grupo.detalle.get("file_original", {}).get("file_path") == str(rutas[1])
        monkeypatch.undo()
    # Reintento real, sin el fallo simulado: debe completarse y repuntar el File.
    from zascarr.services.apartado_duplicados import ApartadoDuplicadosService
    async with banco.fabrica() as s:
        resultado = await ApartadoDuplicadosService(
            s, settings=SimpleNamespace(library_path=library, secret_key=SECRET),
            secret=SECRET).confirmar(vista.token, [GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
        fila = (await s.execute(select(File))).scalars().one()
    assert resultado.estado == "confirmada"
    assert fila.file_path == str(rutas[0])
    assert not rutas[1].exists()


@pytest.mark.asyncio
async def test_st_dev_distinto_rechaza_antes_de_os_replace(banco, tmp_path, monkeypatch):
    library = _lib(tmp_path)
    rutas, sha, vista, _ = await _preparar(banco, library, confirmar=False)
    real_stat = Path.stat
    real_replace = os.replace
    llamadas = {"replace": 0}

    def stat_falso(self, *, follow_symlinks=True):
        st = real_stat(self, follow_symlinks=follow_symlinks)
        if self.name == "dos.cbz":
            campos = list(st)
            campos[2] = st.st_dev + 1
            return os.stat_result(tuple(campos))
        return st

    def replace_espia(src, dst):
        llamadas["replace"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr(Path, "stat", stat_falso)
    monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", replace_espia)
    try:
        async with banco.fabrica() as s:
            resultado = await _servicio(s, library).confirmar(vista.token, [
                GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    finally:
        monkeypatch.setattr(Path, "stat", real_stat)
        monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", real_replace)
    assert resultado.grupos[0].motivo == "montura_distinta"
    assert llamadas["replace"] == 0
    assert rutas[0].exists() and rutas[1].exists()


@pytest.mark.asyncio
async def test_preflight_deshacer_ocupado_no_llama_a_os_replace(banco, tmp_path, monkeypatch):
    library = _lib(tmp_path)
    rutas, sha, vista, resultado = await _preparar(banco, library)
    rutas[1].write_bytes(b"nuevo")
    llamadas = {"n": 0}
    real_replace = os.replace

    def espia(src, dst):
        llamadas["n"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", espia)
    try:
        async with banco.fabrica() as s:
            negado = await _servicio(s, library).deshacer(resultado.operacion)
    finally:
        monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", real_replace)
    assert negado.motivo == "sitio_ocupado"
    assert llamadas["n"] == 0


@pytest.mark.asyncio
async def test_compensacion_fallida_deja_operacion_en_curso(banco, tmp_path, monkeypatch):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    (tmp_path / "C").mkdir()
    (tmp_path / "C" / "tres.cbz").write_bytes(b"contenido-identico")
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz", library / "C" / "tres.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, rutas, 0)
    real_replace = os.replace
    n = {"c": 0}

    def falla_movimiento_y_compensacion(src, dst):
        n["c"] += 1
        if n["c"] == 2:  # segunda copia: falla el move
            raise OSError(errno.EIO, "fallo move")
        if n["c"] == 3:  # compensación de la primera: también falla
            raise OSError(errno.EIO, "fallo compensación")
        return real_replace(src, dst)

    monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", falla_movimiento_y_compensacion)
    try:
        async with banco.fabrica() as s:
            resultado = await _servicio(s, library).confirmar(vista.token, [
                GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
            op = await s.get(ApartadoOperacion, __import__("uuid").UUID(resultado.operacion))
    finally:
        monkeypatch.setattr("zascarr.services.apartado_duplicados.os.replace", real_replace)
    assert resultado.grupos[0].estado == "error"
    assert op.estado == ApartadoEstado.EN_CURSO


@pytest.mark.asyncio
async def test_muerte_tras_mover_una_de_tres_reconcilia_sin_rechazo(banco, tmp_path):
    from zascarr.core.importer_triage import sha256_streaming
    from zascarr.services.tokens_revision import crear_token_apartar
    library = _lib(tmp_path)
    (tmp_path / "C").mkdir()
    (tmp_path / "C" / "tres.cbz").write_bytes(b"contenido-identico")
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz", library / "C" / "tres.cbz"]
    sha = sha256_streaming(rutas[0])
    operacion = uuid4()
    destino = library / ".zascarr" / "apartados" / str(operacion) / "B" / "dos.cbz"
    destino.parent.mkdir(parents=True)
    os.replace(rutas[1], destino)
    token = crear_token_apartar(str(operacion), (
        GrupoFirmado(sha, digest_rutas(["A/uno.cbz", "B/dos.cbz", "C/tres.cbz"]), 0, 3),), SECRET)
    async with banco.fabrica() as s:
        s.add(File(file_path=str(rutas[1]), file_name=rutas[1].name,
                   file_format=FileFormat.CBZ, file_size_bytes=rutas[0].stat().st_size,
                   sha256_hash=sha, file_mtime_ns=rutas[0].stat().st_mtime_ns))
        await s.commit()
        op = ApartadoOperacion(id=operacion, estado=ApartadoEstado.EN_CURSO,
                               token_hasta=datetime.now(UTC), total_grupos=1, total_archivos=2)
        s.add(op)
        s.add(ApartadoGrupo(
            operacion_id=operacion, grupo_clave=sha, sha256=sha,
            size_bytes=rutas[0].stat().st_size, estado=ApartadoGrupoEstado.PENDIENTE,
            detalle={"keep_index": 0, "rutas": ["A/uno.cbz", "B/dos.cbz", "C/tres.cbz"],
                     "items": [], "file_original": {
                         "file_id": str((await s.execute(select(File))).scalars().one().id),
                         "file_path": str(rutas[1]), "file_name": rutas[1].name,
                         "file_size_bytes": rutas[0].stat().st_size, "sha256_hash": sha,
                         "file_mtime_ns": rutas[0].stat().st_mtime_ns}}))
        await s.commit()
        resultado = await _servicio(s, library).confirmar(token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
        fila = (await s.execute(select(File))).scalars().one()
    assert resultado.estado == "confirmada"
    assert not rutas[1].exists() and not rutas[2].exists()
    assert fila.file_path == str(rutas[0])


@pytest.mark.asyncio
async def test_cuarentena_symlink_fuera_falla_cerrado(banco, tmp_path):
    from zascarr.core.importer_triage import sha256_streaming
    library = _lib(tmp_path)
    fuera = tmp_path.parent / f"fuera-{uuid4().hex}"
    fuera.mkdir()
    (library / ".zascarr").symlink_to(fuera, target_is_directory=True)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = sha256_streaming(rutas[0])
    async with banco.fabrica() as s:
        servicio = _servicio(s, library)
        vista = await servicio.previsualizar(sha, rutas, 0)
        resultado = await servicio.confirmar(vista.token, [
            GrupoEntrada(sha, tuple(str(r) for r in rutas), 0)])
    assert resultado.grupos[0].estado in ("rechazado", "error")
    assert resultado.grupos[0].motivo == "cuarentena_fuera"
    assert rutas[0].exists() and rutas[1].exists()
    assert not any(fuera.iterdir())
    fuera.rmdir()
