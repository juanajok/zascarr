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
        "Year", None, (OpcionPropuesta("<script>alert(1)</script>",
                                      FuenteComicInfo.COMIC_VINE, NivelDato.SERIE,
                                      "javascript:alert(1)"),), EstadoPropuesta.ANADIR),
        PropuestaCampo("Publisher", "Vieja", (OpcionPropuesta(
            "Nueva", FuenteComicInfo.GCD, NivelDato.SERIE),), EstadoPropuesta.PROPONER_SUSTITUCION),
        PropuestaCampo("Summary", "Ya está", (OpcionPropuesta(
            "Ya está", FuenteComicInfo.COMIC_VINE, NivelDato.NUMERO),), EstadoPropuesta.YA_COINCIDE))
    return ResultadoPropuestas(str(file_id), str(serie_id), "Tebeo", "american", True,
                               (ResultadoFuente(FuenteComicInfo.COMIC_VINE, "ok"),),
                               campos, (), 1)


def _cliente(monkeypatch, tmp_path, *, disponibilidad=(True, None, None),
             serie_id_archivo=None):
    serie = SimpleNamespace(id=uuid4(), title="Serie", tradition="american")
    ruta = tmp_path / "Tebeo.cbz"
    ruta.write_bytes(b"CBZ")
    issue_id = uuid4()
    issue = SimpleNamespace(id=issue_id, series_id=serie_id_archivo or serie.id)
    file = SimpleNamespace(id=uuid4(), file_path=str(ruta), issue_id=issue_id,
                           sha256_hash="a" * 64)
    db = _DB(serie, file, issue)
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
    assert "&lt;script&gt;" in r.text              # valor de fuente escapado
    assert 'value="1980"' not in r.text            # las claves son opacas


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
        assert "Has elegido 1 cambio" in r2.text
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


def test_get_rechaza_archivo_de_otra_serie_sin_sesion(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path, serie_id_archivo=uuid4())
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert r.status_code == 404
    assert r.headers.get("cache-control") == "no-store"
    assert not ALMACEN._datos


def test_post_409_con_mismo_tamano_y_mtime_pero_sha_distinto(monkeypatch, tmp_path):
    import os
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
        op = re.search(r'name="operacion_id" value="([0-9a-f]+)"', r.text).group(1)
        sesion = ALMACEN.obtener(op)
        ruta = Path(file.file_path)
        st = ruta.stat()
        ruta.write_bytes(b"XYZ")                  # mismo tamaño
        os.utime(ruta, ns=(st.st_atime_ns, st.st_mtime_ns))
        r2 = c.post(_url(serie, file) + "/comicinfo/fuentes",
                    data={"operacion_id": op, "campo:Year": next(iter(sesion.claves_por_tag["Year"]))})
        assert r2.status_code == 409
        assert r2.headers.get("cache-control") == "no-store"
        assert "cambió" in r2.text
    finally:
        _cerrar()
        ALMACEN.limpiar()


def test_caducidad_a_mitad_del_bucle_es_410(monkeypatch, tmp_path):
    from zascarr.services.propuestas_comicinfo_sesion import SesionCaducadaError
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
        op = re.search(r'name="operacion_id" value="([0-9a-f]+)"', r.text).group(1)
        sesion = ALMACEN.obtener(op)
        clave = next(iter(sesion.claves_por_tag["Year"]))

        def _caduca(*_a, **_k):
            raise SesionCaducadaError("caducó")

        monkeypatch.setattr(web.ALMACEN, "elegir", _caduca)
        r2 = c.post(_url(serie, file) + "/comicinfo/fuentes",
                    data={"operacion_id": op, "campo:Year": clave})
        assert r2.status_code == 410
        assert r2.headers.get("cache-control") == "no-store"
        assert "ha caducado" in r2.text
    finally:
        _cerrar()
        ALMACEN.limpiar()


def test_400_por_opcion_invalida_lleva_no_store(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
        op = re.search(r'name="operacion_id" value="([0-9a-f]+)"', r.text).group(1)
        r2 = c.post(_url(serie, file) + "/comicinfo/fuentes",
                    data={"operacion_id": op, "campo:Year": "clave-inventada"})
        assert r2.status_code == 400
        assert r2.headers.get("cache-control") == "no-store"
    finally:
        _cerrar()
        ALMACEN.limpiar()


def test_valores_y_enlaces_maliciosos_se_escapan(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    assert "<script>alert(1)</script>" not in r.text
    assert "javascript:alert(1)" not in r.text


def test_ux_feedback_live_accessible_names_y_details(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    try:
        preview = c.get(_url(serie, file) + "/comicinfo")
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert "hx-indicator="#comicinfo-fuentes-cargando"" in preview.text
    assert "Consultando las fuentes" in preview.text
    assert 'aria-live="polite"' in preview.text
    assert 'id="comicinfo-fuentes-anuncio"' in preview.text
    assert 'class="sr" aria-live="polite"' in preview.text
    assert "sr-only" not in preview.text
    assert "hx-swap-oob" in r.text
    assert "aria-live" not in r.text        # la región viva no se inserta en el swap
    assert "<fieldset" in r.text and "<legend>Año" in r.text
    assert '<span class="sr">Año: </span>' in r.text
    assert "Comic Vine" in r.text and "GCD" in r.text
    assert "Ya coincide" in r.text
    assert 'name="campo:Summary"' not in r.text
    assert "Sin datos nuevos en las fuentes" in r.text
    assert "Guionista" in r.text
    assert 'method="post"' in r.text and 'action="/ui/series/' in r.text
    assert "Guardando la selección" in r.text


def test_cortesia_muestra_reintento(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)

    class _ConCortesia(_ServicioPropuestas):
        async def proponer(self, _fid):
            base = await super().proponer(_fid)
            from dataclasses import replace
            return replace(base, estados=(ResultadoFuente(
                FuenteComicInfo.COMIC_VINE, "limite_de_cortesia", 1,
                "Hay que esperar unos segundos antes de volver a preguntar."),),
                campos=base.campos)

    monkeypatch.setattr(web, "PropuestasComicInfoService", lambda _db: _ConCortesia(_resultado(file.id, serie.id)))
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert "Reintentar" in r.text and "Hay que esperar unos segundos" in r.text


def test_sin_campos_no_duplica_sin_datos_y_texto_de_fuentes(monkeypatch, tmp_path):
    c, serie, file = _cliente(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "PropuestasComicInfoService", lambda _db: _ServicioPropuestas(
        ResultadoPropuestas(str(file.id), str(serie.id), "Tebeo", "american", True, (), (), (), 0)))
    try:
        r = c.get(_url(serie, file) + "/comicinfo/fuentes")
    finally:
        _cerrar()
    assert r.text.count("Las fuentes no tienen datos nuevos para este tebeo") == 1
    assert "Sin datos nuevos en las fuentes" not in r.text


def test_texto_exacto_de_ninguna_fuente_encendida(monkeypatch):

    serie = SimpleNamespace(id=uuid4(), title="S", tradition="american", comic_vine_id=1)
    settings = SimpleNamespace(comicvine_enabled=False, anilist_enabled=False,
                               tebeosfera_enabled=False, gcd_enabled=False)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: settings)
    disponible, mensaje, enlace = web._fuentes_disponibles(serie)
    assert disponible is False
    assert mensaje == ("No hay fuentes de datos encendidas. Enciéndelas en Ajustes o guarda lo "
                       "que ya tienes.")
    assert enlace == "/ui/ajustes"
