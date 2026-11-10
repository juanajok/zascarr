# ruff: noqa: E501, F811
"""#480 sobre PostgreSQL real y CBZ real: plan B6, token, aplicar, crear XML, compartido y CBR."""
from __future__ import annotations

import hashlib
import os
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import select

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
                  xml: bytes | None = None, comic_vine_id: int = 1,
                  nombre: str = "Tebeo 01.cbz"):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=comic_vine_id)
    ruta = tmp_path / (nombre if formato is FileFormat.CBZ else nombre[:-4] + ".cbr")
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


@pytest.mark.asyncio
async def test_locked_field_puesto_despues_de_la_previa_no_se_aplica(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    from zascarr.models import Series
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
    async with entorno_base.banco.fabrica() as s:
        serie = await s.get(Series, sid)
        serie.locked_fields = ["title"]          # bloqueo NUEVO tras la vista previa
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        resultado = await _servicio(s).aplicar(vista.token, file_id_esperado=fid,
                                               serie_id_esperado=sid)
        assert resultado.resultado == "caducado"
        assert resultado.motivo == "propuesta_desactualizada"
    with zipfile.ZipFile(ruta) as zf:
        assert "ComicInfo.xml" not in zf.namelist()


@pytest.mark.asyncio
async def test_fila_deja_de_ser_cbz_o_cambia_de_serie_tras_locks(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        f.is_missing = True                       # deja de ser un CBZ utilizable
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        resultado = await _servicio(s).aplicar(vista.token, file_id_esperado=fid,
                                               serie_id_esperado=sid)
        assert resultado.resultado == "caducado"
        assert resultado.motivo == "propuesta_desactualizada"
    with zipfile.ZipFile(ruta) as zf:
        assert "ComicInfo.xml" not in zf.namelist()

    # Misma prueba cambiando la serie del número (y el File sigue CBZ/no missing).
    sid2, fid2, ruta2 = await _montar(entorno_base, tmp_path, comic_vine_id=2,
                                      nombre="Segundo.cbz")
    async with entorno_base.banco.fabrica() as s:
        vista2 = await _servicio(s).previsualizar(sid2, fid2)
    async with entorno_base.banco.fabrica() as s:
        f2 = (await s.execute(select(File).where(File.id == fid2))).scalar_one()
        issue = (await s.execute(select(Issue).where(Issue.id == f2.issue_id))).scalar_one()
        issue.series_id = await serie_de_prueba(entorno_base, comic_vine_id=30)
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        r2 = await _servicio(s).aplicar(vista2.token, file_id_esperado=fid2,
                                        serie_id_esperado=sid2)
        assert r2.resultado == "caducado" and r2.motivo == "propuesta_desactualizada"
    with zipfile.ZipFile(ruta2) as zf:
        assert "ComicInfo.xml" not in zf.namelist()


async def _montar_autores(entorno_base, tmp_path, *, cv=40, locked=(), page_lock=False,
                          genre_lock=False):
    from zascarr.models import Creator, CreatorRole, Genre, IssueCreator, Series
    sid = await serie_de_prueba(entorno_base, comic_vine_id=cv)
    ruta = tmp_path / f"Autores {cv}.cbz"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("001.jpg", b"pagina")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    async with entorno_base.banco.fabrica() as s:
        serie = await s.get(Series, sid)
        await s.refresh(serie, attribute_names=["genres"])
        serie.genres = [Genre(name=f"Acción {cv}"), Genre(name=f"acción {cv}")]
        if genre_lock:
            serie.locked_fields = ["genres"]
        ana = Creator(name="Ana")
        bob = Creator(name="Bob")
        s.add_all([ana, bob])
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1,
                      synopsis="Sinopsis", page_count=24,
                      locked_fields=list(locked) + (["page_count"] if page_lock else []))
        s.add(issue)
        await s.flush()
        s.add_all([IssueCreator(issue_id=issue.id, creator_id=ana.id, role=CreatorRole.WRITER),
                   IssueCreator(issue_id=issue.id, creator_id=bob.id, role=CreatorRole.WRITER)])
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBZ, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash=sha, metadata_={})
        s.add(f)
        await s.commit()
    return sid, f.id, ruta


@pytest.mark.asyncio
async def test_plan_y_xml_con_autores_genero_y_paginas(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, ruta = await _montar_autores(entorno_base, tmp_path)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        por_tag = {c.tag: c for c in vista.campos}
        assert por_tag["Writer"].nuevo == "Ana, Bob"
        assert por_tag["Writer"].accion.value == "cambia"
        assert por_tag["Genre"].nuevo == "Acción 40"    # dedupe casefold
        assert por_tag["PageCount"].nuevo == "24"
        assert (await servicio.aplicar(vista.token, file_id_esperado=fid)).resultado == "guardado"
    with zipfile.ZipFile(ruta) as zf:
        xml = zf.read("ComicInfo.xml")
    assert b"<Writer>Ana, Bob</Writer>" in xml
    assert b"<Genre>Acci\xc3\xb3n 40</Genre>" in xml
    assert b"<PageCount>24</PageCount>" in xml


@pytest.mark.asyncio
async def test_locked_creators_genres_y_pagecount(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    sid, fid, ruta = await _montar_autores(
        entorno_base, tmp_path, cv=41, locked=("credits",), page_lock=True, genre_lock=True)
    async with entorno_base.banco.fabrica() as s:
        servicio = _servicio(s)
        vista = await servicio.previsualizar(sid, fid)
        por_tag = {c.tag: c.accion for c in vista.campos}
        assert por_tag["Writer"].value == "bloqueado"
        for tag in ("Penciller", "Inker", "Colorist", "Letterer",
                    "CoverArtist", "Editor", "Translator"):
            assert por_tag[tag].value in ("bloqueado", "sin_dato"), tag
        assert por_tag["Genre"].value == "bloqueado"
        assert por_tag["PageCount"].value == "bloqueado"
        await servicio.aplicar(vista.token, file_id_esperado=fid)
    with zipfile.ZipFile(ruta) as zf:
        xml = zf.read("ComicInfo.xml")
    for tag in (b"<Writer>", b"<Genre>", b"<PageCount>"):
        assert tag not in xml


@pytest.mark.asyncio
async def test_la_consulta_de_b6_carga_creditos_y_generos_sin_lazy(entorno_base, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "estado_de_comparticion", _no_compartido)
    from zascarr.services.tagger import TaggerService

    sid, fid, _ruta = await _montar_autores(entorno_base, tmp_path, cv=42)
    async with entorno_base.banco.fabrica() as s:
        informe = await TaggerService(s).run(limit=0, dry_run=True, file_ids=[str(fid)])
        assert informe.errores == 0 and informe.previstos == 1
        campos = {c.tag: c for c in informe.resultados[0].campos}
        assert campos["Writer"].nuevo == "Ana, Bob"
        assert campos["PageCount"].nuevo == "24"
