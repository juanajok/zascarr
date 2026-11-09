# ruff: noqa: E501, F811
"""#478 sobre PostgreSQL real: misma fila, cuarentena, undo, límite y guardián (lector falso)."""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_asociar_fuente_b_pg import entorno_base, url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import serie_de_prueba
from zascarr.models import File, FileFormat, Issue
from zascarr.services.conversion import ConversionDeArchivo
from zascarr.services.conversion_cbr import MAX_CBR_BYTES

SECRETO = "x" * 32
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")


class _Entrada:
    def __init__(self, nombre: str, datos: bytes):
        self.indice = 0
        self.nombre = nombre
        self.tamano = len(datos)
        self.crc32 = __import__("zlib").crc32(datos) & 0xFFFFFFFF
        self.es_directorio = False
        self.cifrada = False
        self._datos = datos


class _Lector:
    def __init__(self, entradas):
        self.entradas = entradas
        self.datos = {e.nombre: e._datos for e in entradas}

    def disponible(self):
        return True

    def listar(self, _ruta, *, temporal):
        return SimpleNamespace(entradas=tuple(self.entradas))

    def leer_entrada(self, _ruta, entrada, _tope, *, temporal):
        return self.datos[entrada.nombre]


class _EntornoConversion:
    def __init__(self, banco, tmp_path: Path):
        self.banco = banco
        self.tmp = tmp_path
        self.otra = tmp_path / "otra-carpeta"
        self.otra.mkdir()
        self.settings = SimpleNamespace(
            library_path=tmp_path, carpetas_compartidas=[str(self.otra)],
            transmission_enabled=False, amule_enabled=False,
            downloads_path=tmp_path / "descargas", amule_incoming_dir=tmp_path / "amule",
            host_library_dir="", host_downloads_dir="", host_amule_incoming_dir="")


async def _montar(entorno_base, tmp_path, *, contenido=b"RAR-falso", nombre="Tebeo 01.cbr"):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1)
    ruta = tmp_path / nombre
    ruta.write_bytes(contenido)
    lector = _Lector([_Entrada("001.jpg", b"pagina uno"), _Entrada("ComicInfo.xml", b"<ComicInfo/>")])
    async with entorno_base.banco.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1)
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBR, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns,
                 sha256_hash=hashlib.sha256(contenido).hexdigest(), metadata_={},
                 metadata_source="manual")
        s.add(f)
        await s.commit()
    return sid, f.id, ruta, lector


@pytest.mark.asyncio
async def test_limite_duro_150_mib_bloquea_sin_tocar(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    with ruta.open("r+b") as fh:
        fh.truncate(MAX_CBR_BYTES + 1)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        vista = await ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings,
                                          lector=lector).previsualizar(sid, fid)
    assert not vista.puede_convertir and vista.motivo == "demasiado_grande"
    assert ruta.exists() and ruta.stat().st_size > MAX_CBR_BYTES


@pytest.mark.asyncio
async def test_convierte_misma_fila_cuarentena_y_undo(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        assert vista.puede_convertir and not vista.advertencia and vista.token
        r = await servicio.confirmar(vista.token)
        assert r.resultado == "convertida" and r.metodo == "recomprimir"
        assert (await servicio.confirmar(vista.token)).resultado == "ya_convertida"

    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        cbz = Path(f.file_path)
        assert f.file_format is FileFormat.CBZ and cbz.suffix == ".cbz"
        assert f.issue_id is not None and f.metadata_source == "manual"
        assert f.metadata_["conversion"]["estado"] == "convertida"
        assert Path(f.metadata_["conversion"]["original"]["ruta"]).exists()
        assert not ruta.exists()
        with zipfile.ZipFile(cbz) as zf:
            assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
            assert zf.testzip() is None
        original_sha = hashlib.sha256(b"RAR-falso").hexdigest()
        assert f.original_sha256 == original_sha

    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        previa = await servicio.previsualizar_deshacer(sid, fid)
        assert previa.token
        deshecho = await servicio.deshacer(previa.token)
        assert deshecho.resultado == "revertida"

    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        assert f.file_format is FileFormat.CBR
        assert Path(f.file_path).read_bytes() == b"RAR-falso"
        assert not Path(f.metadata_["conversion"]["nuevo"]["ruta"]).exists()


@pytest.mark.asyncio
async def test_compartido_advierte_y_solo_con_forzar_escribe(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    entorno.settings.carpetas_compartidas = [str(tmp_path)]   # todo bajo la raíz es «compartido»
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        assert vista.advertencia and vista.forzable
        sin = await servicio.confirmar(vista.token)
        assert sin.resultado == "omitida" and sin.advertencia
        assert ruta.exists()
        con = await servicio.confirmar(vista.token, forzar_compartido=True)
        assert con.resultado == "convertida" and con.forzado_compartido is True


@pytest.mark.asyncio
async def test_d5_cbr_zip_se_renombra_y_deshace(entorno_base, tmp_path):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1)
    ruta = tmp_path / "Zipeado.cbr"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("001.jpg", b"pagina")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    lector = _Lector([])
    async with entorno_base.banco.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1)
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBR, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash=sha, metadata_={})
        s.add(f)
        await s.commit()
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid := f.id)
        assert vista.metodo == "renombrar_zip"
        r = await servicio.confirmar(vista.token)
        assert r.resultado == "convertida"
        previa = await servicio.previsualizar_deshacer(sid, fid)
        assert (await servicio.deshacer(previa.token)).resultado == "revertida"

    async with entorno_base.banco.fabrica() as s:
        f2 = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        assert f2.file_format is FileFormat.CBR and Path(f2.file_path).suffix == ".cbr"


@pytest.mark.asyncio
async def test_diario_vaciar_y_reconciliar(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        r = await servicio.confirmar(vista.token)
    diario = tmp_path / ".zascarr" / "diario" / str(fid) / f"{r.operacion_id}.json"
    assert diario.exists() and "publicado" in diario.read_text()
    assert any((tmp_path / ".zascarr" / "originales").iterdir())
    assert servicio.vaciar_originales() >= 1
    assert not any((tmp_path / ".zascarr" / "originales").iterdir())

    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        f.file_path = str(tmp_path / "fila-rota.cbz")
        f.sha256_hash = "0" * 64
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar(fid) is True
    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        assert Path(f.file_path).name.endswith(".cbz") and f.sha256_hash != "0" * 64
