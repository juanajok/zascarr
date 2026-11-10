# ruff: noqa: E501, F811
"""CNV5-2: servicio de propuestas de solo lectura con dobles de los clientes."""
from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_asociar_fuente_b_pg import entorno_base, url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import serie_de_prueba
from zascarr.core.propuestas_comicinfo import FuenteComicInfo
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.services.estados_fuentes import (
    FUENTE_APAGADA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_OK,
)
from zascarr.services.propuestas_comicinfo import (
    PropuestasComicInfoService,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")


class _Cliente:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False


class _CV(_Cliente):
    def __init__(self):
        self.llamadas = []
        self.volumen = SimpleNamespace(cv_id=1, publisher="Editorial CV", start_year=1980,
                                       site_url="https://cv/volume/1")
        self.detalle = {
            "cover_date": "1981-05-01", "description": "<p>Sinopsis <b>CV</b></p>",
            "person_credits": [{"name": "Ana", "role": "writer"},
                               {"name": "Bob", "role": "penciller"},
                               {"name": "Cora", "role": "cover"}],
        }

    async def get_volume(self, _id):
        self.llamadas.append("volume")
        return self.volumen

    async def get_issue_detail(self, _id):
        self.llamadas.append("issue")
        return self.detalle


class _Tebeosfera(_Cliente):
    def __init__(self, *, falla=False):
        self.llamadas = []
        self.falla = falla
        self.esperas = []
        self.coleccion = SimpleNamespace(editorial="Editorial Tebeo", anio=1970,
                                         url_ficha="https://tebeosfera/col",
                                         numeros_slugs=("coleccion-1",))
        self.numero = SimpleNamespace(anio=1971, paginas=48)

    async def get_collection(self, _slug, *, espera_max_s=None):
        self.llamadas.append("col")
        self.esperas.append(espera_max_s)
        if self.falla:
            raise RuntimeError("caída")
        return self.coleccion

    async def get_numero(self, _slug, *, espera_max_s=None):
        self.llamadas.append("num")
        self.esperas.append(espera_max_s)
        if self.falla:
            raise RuntimeError("caída")
        return self.numero


class _GCD(_Cliente):
    def __init__(self):
        self.llamadas = []
        self.serie = SimpleNamespace(year_began=1960, publisher="https://gcd/pub")

    async def get_series(self, _id):
        self.llamadas.append("serie")
        return self.serie

    async def get_publisher(self, _url):
        self.llamadas.append("publisher")
        return "Editorial GCD"


def _settings(**kw):
    base = dict(comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
                gcd_enabled=False)
    base.update(kw)
    return SimpleNamespace(**base)


async def _montar(entorno_base, tmp_path, *, traicion=ComicTradition.AMERICAN,
                  cv=True, tebeo=False, gcd=False, anilist=False):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1 if cv else None)
    ruta = tmp_path / f"Propuestas {uuid4().hex}.cbz"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("001.jpg", b"pagina")
    sha = hashlib.sha256(ruta.read_bytes()).hexdigest()
    async with entorno_base.banco.fabrica() as s:
        serie = await s.get(Series, sid)
        serie.tradition = traicion
        if tebeo:
            serie.tebeosfera_slug = "coleccion"
        if gcd:
            serie.gcd_id = 77
        if anilist:
            serie.anilist_id = 88
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1,
                      comic_vine_id=2 if cv else None, synopsis="Sinopsis local")
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBZ, file_size_bytes=ruta.stat().st_size,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash=sha, metadata_={})
        s.add(f)
        await s.commit()
    return sid, f.id, ruta


@pytest.mark.asyncio
async def test_cv_construye_propuestas_y_no_escribe(entorno_base, tmp_path):
    sid, fid, ruta = await _montar(entorno_base, tmp_path)
    cv = _CV()
    async with entorno_base.banco.fabrica() as s:
        resultado = await PropuestasComicInfoService(
            s, settings=_settings(comicvine_enabled=True),
            fabricas={FuenteComicInfo.COMIC_VINE: lambda _f: cv},
            actuales={"Publisher": "Editorial vieja", "Year": "1980"}).proponer(fid)
    assert resultado.asociada and resultado.peticiones == 2
    assert cv.llamadas == ["volume", "issue"]
    por_tag = {c.tag: c for c in resultado.campos}
    assert por_tag["Publisher"].opciones[0].valor == "Editorial CV"
    assert por_tag["Summary"].opciones[0].valor == "Sinopsis CV"
    assert por_tag["Writer"].opciones[0].valor == "Ana"
    assert por_tag["Penciller"].opciones[0].valor == "Bob"
    assert por_tag["CoverArtist"].opciones[0].valor == "Cora"
    assert por_tag["Year"].opciones[0].nivel.value == "numero"
    assert por_tag["Year"].estado.value == "proponer_sustitucion"   # 1981 de CV vs 1980
    estado_cv = next(e for e in resultado.estados
                     if e.fuente is FuenteComicInfo.COMIC_VINE)
    assert estado_cv.estado == FUENTE_OK
    assert json.dumps(resultado.to_dict(), ensure_ascii=False)
    async with entorno_base.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        assert f.metadata_ == {}
        assert Path(f.file_path).read_bytes() == ruta.read_bytes()


@pytest.mark.asyncio
async def test_sin_identidad_no_llama_a_clientes(entorno_base, tmp_path):
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, cv=False)
    cv = _CV()
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(comicvine_enabled=True),
            fabricas={FuenteComicInfo.COMIC_VINE: lambda _f: cv},
            actuales={}).proponer(fid)
    assert r.asociada is False and r.campos == () and r.peticiones == 0
    assert cv.llamadas == []
    assert any("asociada" in a.lower() for a in r.avisos)


@pytest.mark.asyncio
async def test_fuente_apagada_o_no_admitida_no_se_consulta(entorno_base, tmp_path):
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, cv=True,
                                    traicion=ComicTradition.MANGA)
    cv = _CV()
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(comicvine_enabled=True),
            fabricas={FuenteComicInfo.COMIC_VINE: lambda _f: cv},
            actuales={}).proponer(fid)
    assert cv.llamadas == []
    assert any(e.fuente is FuenteComicInfo.COMIC_VINE and e.estado == FUENTE_APAGADA
               for e in r.estados)


@pytest.mark.asyncio
async def test_fallo_parcial_no_borra_las_demas_fuentes(entorno_base, tmp_path):
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, cv=False, tebeo=True, gcd=True,
                                    traicion=ComicTradition.FRANCO_BELGIAN)
    tebeo = _Tebeosfera(falla=True)
    gcd = _GCD()
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(tebeosfera_enabled=True, gcd_enabled=True),
            fabricas={FuenteComicInfo.TEBEOSFERA: lambda _f: tebeo,
                      FuenteComicInfo.GCD: lambda _f: gcd},
            actuales={}).proponer(fid)
    estados = {e.fuente: e for e in r.estados}
    assert estados[FuenteComicInfo.TEBEOSFERA].estado == FUENTE_FALLO_TRANSITORIO
    assert estados[FuenteComicInfo.GCD].estado == FUENTE_OK
    assert {c.tag for c in r.campos} >= {"Year", "Publisher"}
    assert "Editorial GCD" in {o.valor for c in r.campos for o in c.opciones}


@pytest.mark.asyncio
async def test_cbr_no_toca_clientes(entorno_base, tmp_path):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1)
    ruta = tmp_path / "CBR.cbr"
    ruta.write_bytes(b"RAR")
    cv = _CV()
    async with entorno_base.banco.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=sid, issue_number="1", volume=1)
        s.add(issue)
        await s.flush()
        f = File(id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
                 file_format=FileFormat.CBR, file_size_bytes=3,
                 file_mtime_ns=ruta.stat().st_mtime_ns, sha256_hash="0" * 64, metadata_={})
        s.add(f)
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(comicvine_enabled=True),
            fabricas={FuenteComicInfo.COMIC_VINE: lambda _f: cv},
            actuales={}).proponer(f.id)
    assert r.campos == () and cv.llamadas == []


@pytest.mark.asyncio
async def test_tebeosfera_hace_dos_peticiones_y_pasa_espera(entorno_base, tmp_path):
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, cv=False, tebeo=True,
                                    traicion=ComicTradition.FRANCO_BELGIAN)
    tebeo = _Tebeosfera()
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(tebeosfera_enabled=True),
            fabricas={FuenteComicInfo.TEBEOSFERA: lambda _f: tebeo},
            actuales={}).proponer(fid)
    assert tebeo.llamadas == ["col", "num"]
    assert tebeo.esperas == [3.0, 3.0]
    assert r.peticiones == 2
    por_tag = {c.tag: c for c in r.campos}
    assert por_tag["PageCount"].opciones[0].valor == "48"


@pytest.mark.asyncio
async def test_anio_de_serie_conserva_nivel_serie_si_el_numero_no_tiene_fecha(entorno_base,
                                                                              tmp_path):
    sid, fid, _ruta = await _montar(entorno_base, tmp_path, cv=True)
    cv = _CV()
    cv.detalle = {"description": "Sin fecha", "person_credits": []}
    async with entorno_base.banco.fabrica() as s:
        r = await PropuestasComicInfoService(
            s, settings=_settings(comicvine_enabled=True),
            fabricas={FuenteComicInfo.COMIC_VINE: lambda _f: cv},
            actuales={}).proponer(fid)
    year = next(c for c in r.campos if c.tag == "Year")
    assert year.opciones[0].valor == "1980"
    assert year.opciones[0].nivel.value == "serie"
