# ruff: noqa: E501
"""CNV5-3: sección «Datos de las fuentes» y sesión de elección (sin escrituras)."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.core.propuestas_comicinfo import (
    EstadoPropuesta,
    FuenteComicInfo,
    NivelDato,
    OpcionPropuesta,
    PropuestaCampo,
    ResultadoFuente,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, Issue, Series
from zascarr.services.comicinfo_ficha import VistaComicInfo
from zascarr.services.propuestas_comicinfo import ResultadoPropuestas
from zascarr.services.propuestas_comicinfo_sesion import ALMACEN, AlmacenPropuestas
from zascarr.web import series as web


class _DB:
    def __init__(self, serie, file, issue=None):
        self._map = {Series: serie, File: file, Issue: issue}

    async def get(self, modelo, _id, **_kw):
        return self._map.get(modelo)


class _ServicioFicha:
    def __init__(self, vista):
        self.vista = vista

    async def previsualizar(self, *_a):
        return self.vista


class _ServicioPropuestas:
    def __init__(self, resultado):
        self.resultado = resultado

    async def proponer(self, _fid):
        return self.resultado


def _vista(file_id):
    return VistaComicInfo(str(file_id), str(uuid4()), "Tebeo 01.cbz", False, True, None,
                          "Revisa los cambios.", token="tok")


def _resultado(file_id, serie_id):
    campos = (PropuestaCampo(
        "Year", None, (OpcionPropuesta("1980", FuenteComicInfo.COMIC_VINE, NivelDato.SERIE,
                                      "https://comicvine.example/v"),), EstadoPropuesta.ANADIR),
        PropuestaCampo("Publisher", "Vieja", (OpcionPropuesta(
            "Nueva", FuenteComicInfo.GCD, NivelDato.SERIE),), EstadoPropuesta.PROPONER_SUSTITUCION))
    return ResultadoPropuestas(str(file_id), str(serie_id), "Tebeo", "american", True,
                               (ResultadoFuente(FuenteComicInfo.COMIC_VINE, "ok"),),
                               campos, (), 1)


def _cliente(monkeypatch, tmp_path, *, disponibilidad=(True, None, None)):
    serie = SimpleNamespace(id=uuid4(), title="Serie", tradition="american")
    ruta = tmp_path / "Tebeo.cbz"
    ruta.write_bytes(b"CBZ")
    file = SimpleNamespace(id=uuid4(), file_path=str(ruta), issue_id=uuid4(),
                           sha256_hash="a" * 64)
    db = _DB(serie, file)
    async def _dep():
        yield db
    app.dependency_overrides[get_db] = _dep
    monkeypatch.setattr(web, "ComicInfoFichaService", lambda _db: _ServicioFicha(_vista(file.id)))
    monkeypatch.setattr(web, "PropuestasComicInfoService",
                        lambda _db: _ServicioPropuestas(_resultado(file.id, serie.id)))
    monkeypatch.setattr(web, "_fuentes_disponibles", lambda _s: disponibilidad)
    ALMACEN.limpiar()
    return TestClient(app), serie, file


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def _url(serie, file):
    return f"/ui/series/{serie.id}/archivos/{file.id}"


def test_preview_con_fuentes_muestra_boton_secundario(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Datos de las fuentes" in r.text
    assert "Buscar datos en las fuentes" in r.text
    assert 'hx-get=' in r.text


def test_preview_sin_identidad_muestra_asociar_sin_boton(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path, disponibilidad=(
        False, "Esta serie todavía no está asociada a ninguna fuente.", "/ui/series/x/asociar"))
    try:
        r = c.get(_url(serie, file) + "/comicinfo")
    finally:
        _cerrar()
    assert "todavía no está asociada" in r.text
    assert "Buscar datos en las fuentes" not in r.text


def test_get_fuentes_muestra_tabla_y_no_store(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert "Año" in r.text and "Editorial" in r.text
    assert 'name="campo:Year"' in r.text and 'name="campo:Publisher"' in r.text
    assert "Conservar lo actual" in r.text
    assert "(de la serie" in r.text or "de la serie, no del número" in r.text
    assert "1980" in r.text
    assert 'value="1980"' not in r.text          # las claves son opacas


def test_post_guarda_eleccion_en_sesion_sin_escribir(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
        op = re.search(r'name="operacion_id" value="([0-9a-f]+)"', r.text).group(1)
        sesion = ALMACEN.obtener(op)
        clave = next(iter(sesion.claves_por_tag["Year"]))
        antes = Path(file.file_path).read_bytes()
        r2 = c.post(_url(serie, file) + "/comicinfo/fuentes",
                    data={"operacion_id": op, "campo:Year": clave})
        assert r2.status_code == 200
        assert ALMACEN.obtener(op).elecciones["Year"] == clave
        assert "Has elegido 1 cambios" in r2.text
        assert Path(file.file_path).read_bytes() == antes
        assert file.sha256_hash == "a" * 64
    finally:
        _cerrar()
        ALMACEN.limpiar()


def test_post_sesion_caducada_410_y_sin_escritura(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "ALMACEN", AlmacenPropuestas(reloj=lambda: 1.0))
    try:
        r = c.post(_url(serie, file) + "/comicinfo/fuentes",
                   data={"operacion_id": "no-existe"})
    finally:
        _cerrar()
    assert r.status_code == 410
    assert "ha caducado" in r.text
    assert r.headers.get("cache-control") == "no-store"
