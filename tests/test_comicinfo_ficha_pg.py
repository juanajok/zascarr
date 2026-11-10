# ruff: noqa: E501, F811
"""#480 sobre PostgreSQL real y CBZ real: plan B6, token, aplicar, crear XML, compartido y CBR."""
from __future__ import annotations

import hashlib
import os
import zipfile
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import entorno_base, url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import serie_de_prueba
from zascarr.models import File, FileFormat, Issue
from zascarr.services import comicinfo_ficha as mod
from zascarr.services.comicinfo_ficha import ComicInfoFichaService
from zascarr.services.compartidos import Decision, EstadoComparticion

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")
SECRETO = "x" * 32


async def _no_compartido(_path):
    return Decision(EstadoComparticion.NO_COMPARTIDO, "")


async def _montar(entorno_base, tmp_path, *, formato=FileFormat.CBZ,
                  xml: bytes | None = None):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1)
    ruta = tmp_path / ("Tebeo 01.cbz" if formato is FileFormat.CBZ else "Tebeo 01.cbr")
    if formato is FileFormat.CBZ:
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("001.jpg", b"pagina")
            if xml is not None:
                zf.writestr("ComicInfo.xml", xml)
    else:
        ruta.write_bytes(b"RAR-falso")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    async with entorno_base.banco.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1,
                      synopsis="Sinopsis de prueba", locked_fields=[])
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=formato, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash=sha, metadata_={})
        s.add(f)
        await s.commit()
    return sid, f.id, ruta


def _servicio(s, lector=None):
    return ComicInfoFichaService(s, secret=SECRETO)


@pytest.mark.asyncio
async def test_vista_previa_plan_y_aplicar_crea_xml(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        assert vista.puede_aplicar and vista.token
        assert any(c.tag == "Series" and c.nuevo == "Flash" for c in vista.campos)
        resultado = await servicio.aplicar(vista.token, file_id_esperado=fid,
                                           serie_id_esperado=sid)
        assert resultado.resultado == "guardado"
    with zipfile.ZipFile(ruta) as zf:
        xml = zf.read("ComicInfo.xml")
    assert b"<Series>Flash</Series>" in xml and b"<Number>1</Number>" in xml


@pytest.mark.asyncio
async def test_conserva_manual_y_desconocido(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    manual = (b"<ComicInfo><Series>Manual</Series><Custom>hola</Custom></ComicInfo>")
    sid, fid, ruta = await _montar(entorno_base, tmp_path, xml=manual)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        serie = next(c for c in vista.campos if c.tag == "Series")
        assert serie.accion.value in ("conserva", "ya_coincide")
        assert (await servicio.aplicar(vista.token, file_id_esperado=fid)).resultado == "guardado"
    with zipfile.ZipFile(ruta) as zf:
        xml = zf.read("ComicInfo.xml")
    assert b"<Series>Manual</Series>" in xml and b"<Custom>hola</Custom>" in xml


@pytest.mark.asyncio
async def test_plan_caducado_si_cambia_el_archivo(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        ruta.write_bytes(ruta.read_bytes() + b"cambio")
        resultado = await servicio.aplicar(vista.token, file_id_esperado=fid)
        assert resultado.resultado == "caducado"


@pytest.mark.asyncio
async def test_compartido_advierte_y_no_escribe_sin_confirmacion(entorno_base, tmp_path, monkeypatch):
    async def _compartido(_path):
        return Decision(EstadoComparticion.COMPARTIDO, "lo comparte Transmission")
    monkeypatch.setattr(mod, "estado_de_comparticion", _compartido)
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    antes = ruta.read_bytes()
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        assert vista.advertencia and vista.forzable and vista.token
        sin = await servicio.aplicar(vista.token, file_id_esperado=fid)
        assert sin.resultado == "omitido" and sin.motivo == "compartido"
        assert ruta.read_bytes() == antes
        con = await servicio.aplicar(vista.token, forzar_compartido=True, file_id_esperado=fid)
        assert con.resultado == "guardado" and con.forzado_compartido is True


@pytest.mark.asyncio
async def test_cbr_remite_a_conversion_sin_token(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, formato=FileFormat.CBR)
    async with entorno_base.banco.fabrica() as s:
        vista = await _servicio(s).previsualizar(sid, fid)
        assert vista.es_cbr and not vista.puede_aplicar and vista.token is None
        assert "Conviértelo" in vista.mensaje or "conviértelo" in vista.mensaje


@pytest.mark.asyncio
async def test_campo_bloqueado_no_se_escribe(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid = await serie_de_prueba(entorno_base, comic_vine_id=20)
    ruta = tmp_path / "Bloqueado.cbz"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("001.jpg", b"pagina")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    async with entorno_base.banco.fabrica() as s:
        from zascarr.models import Series
        serie = await s.get(Series, sid)
        serie.locked_fields = ["title"]
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1,
                      synopsis="Sinopsis", locked_fields=[])
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBZ, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash=sha, metadata_={})
        s.add(f)
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, f.id)
        serie = next(c for c in vista.campos if c.tag == "Series")
        assert serie.accion.value == "bloqueado"
        assert (await servicio.aplicar(vista.token, file_id_esperado=f.id)).resultado == "guardado"
    with zipfile.ZipFile(ruta) as zf:
        xml = zf.read("ComicInfo.xml")
    assert b"<Series>" not in xml
