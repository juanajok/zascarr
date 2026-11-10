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
from zascarr.services import conversion as mod
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


async def _montar(entorno_base, tmp_path, *, contenido=b"RAR-falso", nombre="Tebeo 01.cbr",
                  comic_vine_id=1):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=comic_vine_id)
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
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar_diario() >= 1
    diario = tmp_path / ".zascarr" / "diario" / str(fid)
    assert not list(diario.glob("*.json"))


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
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar_diario() >= 1
    assert not diario.exists()
    assert await servicio.vaciar_originales() >= 1
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


@pytest.mark.asyncio
async def test_token_de_otro_archivo_no_escribe(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    sid2, fid2, ruta2, lector2 = await _montar(
        entorno_base, tmp_path, nombre="Otro.cbr", comic_vine_id=2)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        from zascarr.services.vinculacion import TokenInvalidoError
        with pytest.raises(TokenInvalidoError):
            await servicio.confirmar(vista.token, file_id_esperado=fid2,
                                     serie_id_esperado=sid2)
    assert ruta.exists() and not ruta.with_suffix(".cbz").exists()


@pytest.mark.asyncio
async def test_token_caducado_por_cambio_de_archivo(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        ruta.write_bytes(b"RAR-cambiado")
        resultado = await servicio.confirmar(vista.token)
        assert resultado.resultado == "omitida" and resultado.motivo == "propuesta_desactualizada"
    assert ruta.read_bytes() == b"RAR-cambiado"


@pytest.mark.asyncio
async def test_si_el_destino_aparece_tras_las_comprobaciones_se_restaura(entorno_base, tmp_path, monkeypatch):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    original = ruta.read_bytes()

    real = mod._publicar_sin_sobrescribir
    llamadas = []

    def _existe(origen, destino):
        if not llamadas:
            llamadas.append(1)
            raise FileExistsError("destino apareció")
        return real(origen, destino)

    monkeypatch.setattr(mod, "_publicar_sin_sobrescribir", _existe)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        resultado = await servicio.confirmar(vista.token)
        assert resultado.resultado == "omitida"
    assert ruta.read_bytes() == original
    assert not ruta.with_suffix(".cbz").exists()
    diario = tmp_path / ".zascarr" / "diario" / str(fid)
    assert any("fallo_publicacion" in p.read_text() for p in diario.glob("*.json"))


@pytest.mark.asyncio
async def test_undo_rechaza_operacion_anterior_y_cbz_tocado(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        await servicio.confirmar(vista.token)
        previa = await servicio.previsualizar_deshacer(sid, fid)
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        meta = __import__("copy").deepcopy(f.metadata_)
        meta["conversion"]["operacion_id"] = str(uuid4())
        f.metadata_ = meta
        await s.commit()
        r = await servicio.deshacer(previa.token)
        assert r.resultado == "omitida" and r.motivo == "propuesta_desactualizada"
        assert Path(f.file_path).exists()


@pytest.mark.asyncio
async def test_undo_rechaza_un_cbz_manipulado(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path, comic_vine_id=3)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        vista = await servicio.previsualizar(sid, fid)
        await servicio.confirmar(vista.token)
        previa = await servicio.previsualizar_deshacer(sid, fid)
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        Path(f.file_path).write_bytes(b"CBZ-tocado")
        assert (await servicio.deshacer(previa.token)).resultado == "omitida"


@pytest.mark.asyncio
async def test_diario_write_ahead_restaura_original_y_solo_borra_si_repara(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path, comic_vine_id=4)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    original = ruta.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    cuarentena = tmp_path / ".zascarr" / "originales" / str(fid) / "op-vieja"
    cuarentena.mkdir(parents=True)
    apartado = cuarentena / ruta.name
    apartado.write_bytes(original)
    ruta.unlink()
    (tmp_path / ".zascarr" / "diario" / str(fid)).mkdir(parents=True)
    diario = tmp_path / ".zascarr" / "diario" / str(fid) / "op-vieja.json"
    diario.write_text(__import__("json").dumps({
        "version": 1, "file_id": str(fid), "operacion_id": "op-vieja",
        "estado": "original_apartado", "ruta": str(apartado),
        "ruta_original": str(ruta), "destino": str(ruta.with_suffix(".cbz")),
        "sha_original": sha, "tamano_original": len(original),
        "sha_nuevo": "0" * 64, "tamano_nuevo": 1, "metodo": "recomprimir",
    }))
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar_diario() == 1
    assert ruta.read_bytes() == original
    assert not diario.exists()

    # Un diario que no se puede verificar NO se borra.
    (tmp_path / ".zascarr" / "diario" / str(fid)).mkdir(parents=True)
    diario2 = tmp_path / ".zascarr" / "diario" / str(fid) / "op-rota.json"
    diario2.write_text(__import__("json").dumps({
        "version": 1, "file_id": str(fid), "operacion_id": "op-rota",
        "estado": "original_apartado", "ruta": str(tmp_path / "no-existe"),
        "ruta_original": str(tmp_path / "tampoco"), "destino": str(tmp_path / "nada.cbz"),
        "sha_original": "1" * 64, "tamano_original": 10,
    }))
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar_diario() == 0
    assert diario2.exists()


@pytest.mark.asyncio
async def test_vaciar_y_reconciliar_respetan_el_cerrojo_de_ciclo(entorno_base, tmp_path):
    from sqlalchemy import text

    from zascarr.services.comprobacion_disco import CLAVE_CERROJO_CICLO

    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path, comic_vine_id=5)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    async with entorno_base.banco.fabrica() as ocupada:
        await ocupada.execute(text("SELECT pg_advisory_lock(:c, :o)"),
                              {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})
        await ocupada.commit()
        async with entorno_base.banco.fabrica() as s:
            servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings,
                                           lector=lector)
            assert await servicio.vaciar_originales() == 0
            assert await servicio.reconciliar_diario() == 0
        await ocupada.execute(text("SELECT pg_advisory_unlock(:c, :o)"),
                              {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})
        await ocupada.commit()


@pytest.mark.asyncio
async def test_diario_repara_fila_si_el_commit_no_llego(entorno_base, tmp_path):
    sid, fid, ruta, lector = await _montar(entorno_base, tmp_path, comic_vine_id=6)
    entorno = _EntornoConversion(entorno_base.banco, tmp_path)
    nuevo = ruta.with_suffix(".cbz")
    nuevo.write_bytes(b"CBZ-ya-publicado")
    sha_nuevo = hashlib.sha256(b"CBZ-ya-publicado").hexdigest()
    cuarentena = tmp_path / ".zascarr" / "originales" / str(fid) / "op"
    cuarentena.mkdir(parents=True)
    ruta.rename(cuarentena / ruta.name)
    (tmp_path / ".zascarr" / "diario" / str(fid)).mkdir(parents=True)
    diario = tmp_path / ".zascarr" / "diario" / str(fid) / "op.json"
    diario.write_text(__import__("json").dumps({
        "version": 1, "file_id": str(fid), "operacion_id": str(uuid4()),
        "estado": "publicado", "ruta": str(cuarentena / ruta.name),
        "ruta_original": str(ruta), "destino": str(nuevo),
        "sha_original": hashlib.sha256(b"RAR-falso").hexdigest(),
        "tamano_original": len(b"RAR-falso"), "sha_nuevo": sha_nuevo,
        "tamano_nuevo": len(b"CBZ-ya-publicado"), "metodo": "recomprimir",
    }))
    async with entorno_base.banco.fabrica() as s:
        servicio = ConversionDeArchivo(s, secret=SECRETO, settings=entorno.settings, lector=lector)
        assert await servicio.reconciliar_diario() == 1
    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        assert f.file_format is FileFormat.CBZ and Path(f.file_path) == nuevo
        assert f.sha256_hash == sha_nuevo
    assert not diario.exists()
