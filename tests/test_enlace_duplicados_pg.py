# ruff: noqa: E501
"""BL-DUP2 (#265): unir copias idénticas con enlace duro (PG + FS real)."""
from __future__ import annotations

import errno
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ApartadoEstado, ApartadoOperacion, File, FileFormat
from zascarr.services.apartado_duplicados import GrupoRechazado, TokenApartadoInvalido
from zascarr.services.enlace_duplicados import EnlaceDuplicadosService
from zascarr.services.tokens_revision import (
    GrupoFirmado,
    crear_token_apartar,
    verificar_token_enlazar,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
SECRET = "secreto-de-prueba-enlace"


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
        await c.execute(text("TRUNCATE apartado_grupos, apartado_operaciones CASCADE"))
    yield b
    await b.cerrar()


def _lib(tmp_path: Path) -> Path:
    (tmp_path / "A").mkdir()
    (tmp_path / "B").mkdir()
    (tmp_path / "A" / "uno.cbz").write_bytes(b"contenido-identico")
    (tmp_path / "B" / "dos.cbz").write_bytes(b"contenido-identico")
    return tmp_path


def _servicio(session, library: Path) -> EnlaceDuplicadosService:
    return EnlaceDuplicadosService(
        session, settings=SimpleNamespace(library_path=library, secret_key=SECRET), secret=SECRET)


async def _sha(path: Path) -> str:
    from zascarr.core.importer_triage import sha256_streaming
    return sha256_streaming(path)


@pytest.mark.asyncio
async def test_previsualizar_no_escribe_y_enlaza_sin_duplicar_catalogo(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        assert (await s.execute(select(ApartadoOperacion))).scalars().all() == []
    assert not (library / ".zascarr").exists()
    assert rutas[0].stat().st_ino != rutas[1].stat().st_ino
    assert verificar_token_enlazar(vista.token, SECRET).operacion == vista.operacion

@pytest.mark.asyncio
async def test_confirmar_deja_dos_rutas_con_el_mismo_inodo_y_cuarentena(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        op = await s.get(ApartadoOperacion, UUID(resultado.operacion))
    assert resultado.estado == "confirmada"
    assert resultado.grupos[0].estado == "movido"
    assert op is not None and op.modo == "enlazar"
    assert rutas[0].exists() and rutas[1].exists()
    assert rutas[0].stat().st_ino == rutas[1].stat().st_ino
    quarantine = library / ".zascarr" / "apartados" / resultado.operacion / "B" / "dos.cbz"
    assert quarantine.exists() and quarantine.stat().st_ino != rutas[0].stat().st_ino
    assert not list((library / ".zascarr" / "apartados").glob("**/.zascarr-enlace-*"))


@pytest.mark.asyncio
async def test_con_fila_en_catalogo_no_duplica_registros(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        s.add(File(file_path=str(rutas[1]), file_name=rutas[1].name, file_format=FileFormat.CBZ,
                   file_size_bytes=rutas[1].stat().st_size, sha256_hash=sha,
                   file_mtime_ns=rutas[1].stat().st_mtime_ns))
        await s.commit()
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        filas = (await s.execute(select(File))).scalars().all()
    assert resultado.estado == "confirmada"
    assert len(filas) == 1 and filas[0].file_path == str(rutas[1])
    assert filas[0].file_path and Path(filas[0].file_path).exists()


@pytest.mark.asyncio
async def test_contenido_cambiado_rechaza_sin_tocar(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
    rutas[1].write_bytes(b"otro-contenido")
    async with banco.fabrica() as s:
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
    assert resultado.grupos[0].estado == "rechazado"
    assert resultado.grupos[0].motivo == "contenido_cambiado"
    assert rutas[1].read_bytes() == b"otro-contenido"
    assert not (library / ".zascarr" / "apartados" / resultado.operacion).exists()


@pytest.mark.asyncio
async def test_deshacer_solo_si_el_enlace_sigue_siendo_el_mismo(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        assert rutas[1].stat().st_ino == rutas[0].stat().st_ino
        # Si alguien rompe el enlace, no se pisa a ciegas.
        rutas[1].unlink()
        rutas[1].write_bytes(b"intervenido")
        with pytest.raises(TokenApartadoInvalido):
            await _servicio(s, library).deshacer(resultado.operacion)
    assert rutas[1].read_bytes() == b"intervenido"


@pytest.mark.asyncio
async def test_deshacer_restaura_copia_y_operacion(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        assert rutas[1].stat().st_ino == rutas[0].stat().st_ino
        deshecho = await _servicio(s, library).deshacer(resultado.operacion)
        op = await s.get(ApartadoOperacion, UUID(resultado.operacion))
    assert deshecho.estado == "deshecha"
    assert op.estado == ApartadoEstado.DESHECHA
    assert rutas[0].exists() and rutas[1].exists()
    assert rutas[0].stat().st_ino != rutas[1].stat().st_ino
    assert rutas[1].read_bytes() == b"contenido-identico"


@pytest.mark.asyncio
async def test_idempotente_y_token_de_apartar_no_sirve(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        primero = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        segundo = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        assert segundo.idempotente is True and segundo.operacion == primero.operacion


@pytest.mark.asyncio
async def test_fallo_al_crear_el_enlace_deja_las_dos_copias(banco, tmp_path, monkeypatch):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        def link_exdev(*_a, **_k):
            raise OSError(errno.EXDEV, "cross-device link")
        monkeypatch.setattr("zascarr.services.enlace_duplicados.os.link", link_exdev)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
    assert resultado.grupos[0].estado == "rechazado"
    assert resultado.grupos[0].motivo == "montura_distinta"
    assert rutas[0].exists() and rutas[1].exists()
    assert rutas[0].stat().st_ino != rutas[1].stat().st_ino
    assert not (library / ".zascarr" / "apartados" / resultado.operacion).exists()


@pytest.mark.asyncio
async def test_tres_copias_quedan_enlazadas_y_deshacer_las_restaura(banco, tmp_path):
    library = _lib(tmp_path)
    tercera = library / "C" / "tres.cbz"
    tercera.parent.mkdir()
    tercera.write_bytes(b"contenido-identico")
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz", tercera]
    sha = await _sha(rutas[0])
    async with banco.fabrica() as s:
        vista = await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        resultado = await _servicio(s, library).confirmar(
            vista.token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])
        async with banco.fabrica() as s2:
            from sqlalchemy.orm import selectinload
            op = (await s2.execute(select(ApartadoOperacion).options(
                selectinload(ApartadoOperacion.grupos)).where(
                ApartadoOperacion.id == UUID(resultado.operacion)))).scalar_one()
            print("OPDETAIL", op.grupos[0].detalle)
        deshecho = await _servicio(s, library).deshacer(resultado.operacion)
    assert resultado.estado == "confirmada"
    assert deshecho.estado == "deshecha"
    assert all(p.exists() for p in rutas)
    assert len({p.stat().st_ino for p in rutas}) == 3


@pytest.mark.asyncio
async def test_token_de_apartar_no_sirve_para_enlazar(banco, tmp_path):
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    from zascarr.services.apartado_duplicados import digest_rutas
    grupos = (GrupoFirmado(sha, digest_rutas(["A/uno.cbz", "B/dos.cbz"]), 0, 2),)
    token = crear_token_apartar(uuid4(), grupos, SECRET)
    async with banco.fabrica() as s:
        with pytest.raises(TokenApartadoInvalido):
            await _servicio(s, library).confirmar(
                token, [{"sha256": sha, "rutas": [str(p) for p in rutas], "keep_index": 0}])


@pytest.mark.asyncio
async def test_permiso_de_escritura_se_rechaza_antes_de_tocar(banco, tmp_path):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("como root los permisos no bloquean la escritura")
    library = _lib(tmp_path)
    rutas = [library / "A" / "uno.cbz", library / "B" / "dos.cbz"]
    sha = await _sha(rutas[0])
    rutas[1].parent.chmod(0o500)
    try:
        async with banco.fabrica() as s:
            with pytest.raises(GrupoRechazado) as exc:
                await _servicio(s, library).previsualizar(sha, [str(p) for p in rutas], 0)
        assert exc.value.motivo == "sin_permiso"
        assert rutas[0].exists() and rutas[1].exists()
    finally:
        rutas[1].parent.chmod(0o700)


@pytest.mark.asyncio
async def test_discos_distintos_se_rechazan_con_fs_real(banco, tmp_path):
    shm = Path("/dev/shm")
    if not shm.is_dir():
        pytest.skip("no hay /dev/shm para probar otra montura")
    a = shm / f"zascarr-dup2-{uuid4().hex}.cbz"
    b = tmp_path / f"zascarr-dup2-{uuid4().hex}.cbz"
    a.write_bytes(b"misma-copia")
    b.write_bytes(b"misma-copia")
    try:
        if a.stat().st_dev == b.stat().st_dev:
            pytest.skip("las rutas de prueba están en la misma montura")
        sha = await _sha(a)
        servicio = EnlaceDuplicadosService(
            None, settings=SimpleNamespace(library_path=Path("/"), secret_key=SECRET),
            secret=SECRET)
        with pytest.raises(GrupoRechazado) as exc:
            await servicio.previsualizar(sha, [str(a), str(b)], 0)
        assert exc.value.motivo == "montura_distinta"
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)
