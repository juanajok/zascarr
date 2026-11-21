"""BL-INF4 (#590): rutas de la vista previa del número (servicio sustituido)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.portada_numero import ANCHO_FICHA
from zascarr.web import series as web


def _cliente(serie_id: UUID, *, previa):
    class _Sesion:
        async def get(self, _modelo, _id):
            return SimpleNamespace(series_id=serie_id, issue_number="1",
                                   title="El Día del Sol Negro")

    async def _db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_fragmento_devuelve_la_miniatura(tmp_path):
    serie, issue = uuid4(), uuid4()
    jpg = tmp_path / "previa.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa")
    finally:
        _cerrar()

    assert r.status_code == 200
    assert f"/ui/series/{serie}/numero/{issue}/previa.jpg" in r.text
    assert 'class="previa-numero-img"' in r.text
    assert "Nº 1" in r.text and "El Día del Sol Negro" in r.text
    # UATP-05 / D-5: el pie no promete una acción que la tarjeta no hace.
    assert "Vista previa · Esc o clic para apartarla" in r.text
    assert "Pulsa para abrir la ficha" not in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_fragmento_sin_portada_queda_vacio():
    serie, issue = uuid4(), uuid4()
    c = _cliente(serie, previa=None)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa")
    finally:
        _cerrar()

    assert r.status_code == 200 and r.text == ""


def test_imagen_sirve_jpeg_con_etag_y_cache(tmp_path):
    serie, issue = uuid4(), uuid4()
    jpg = tmp_path / "previa.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
            r304 = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg",
                         headers={"If-None-Match": r.headers["ETag"]})
    finally:
        _cerrar()

    assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg")
    assert r.headers["Cache-Control"] == "private, max-age=86400"
    assert r.headers["ETag"]
    assert r304.status_code == 304


def test_imagen_sin_portada_da_404_sin_cache():
    serie, issue = uuid4(), uuid4()
    c = _cliente(serie, previa=None)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
    finally:
        _cerrar()

    assert r.status_code == 404
    assert r.headers["Cache-Control"] == "no-store"


def test_un_numero_de_otra_serie_da_404():
    serie, issue = uuid4(), uuid4()
    c = _cliente(uuid4(), previa=None)  # la sesión devuelve otra serie
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
    finally:
        _cerrar()

    assert r.status_code == 404


def test_portada_de_la_ficha_sirve_jpeg_a_600(tmp_path):
    serie, issue = uuid4(), uuid4()
    jpg = tmp_path / "portada.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)) as mock:
            r = c.get(f"/ui/series/{serie}/numero/{issue}/portada.jpg")
    finally:
        _cerrar()

    assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg")
    assert r.headers["Cache-Control"] == "private, max-age=86400"
    assert mock.await_args.kwargs["ancho"] == ANCHO_FICHA


def test_fragmento_en_htmx_con_numero_ajeno_queda_vacio():
    serie, issue = uuid4(), uuid4()
    c = _cliente(uuid4(), previa=None)   # la sesión devuelve otra serie
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa",
                      headers={"HX-Request": "true"})
    finally:
        _cerrar()

    assert r.status_code == 200 and r.text == ""


def test_portada_hd_sirve_1200_con_etag_y_404():
    from zascarr.services.portada_numero import ANCHO_HD

    serie, issue = uuid4(), uuid4()
    jpg = __import__("pathlib").Path("/tmp") / f"hd-{uuid4()}.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)) as mock:
            r = c.get(f"/ui/series/{serie}/numero/{issue}/portada-hd.jpg")
            r304 = c.get(f"/ui/series/{serie}/numero/{issue}/portada-hd.jpg",
                         headers={"If-None-Match": r.headers["ETag"]})
    finally:
        _cerrar()
    assert r.status_code == 200 and r304.status_code == 304
    assert mock.await_args.kwargs["ancho"] == ANCHO_HD
    assert r.headers["Cache-Control"] == "private, max-age=86400"


# --- UATP-05 (#1143): cerrar sin mover el foco -------------------------------------------


def _cliente_sin_tocar_bd():
    """Cliente cuya sesión falla si alguien la consulta: cerrar no necesita saber si existe."""
    class _Sesion:
        async def get(self, *_args, **_kwargs):
            raise AssertionError("cerrar la previa no debe consultar la BD")

    async def _db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_cerrar_numero_devuelve_200_vacio_sin_bd_ni_disco():
    serie, issue = uuid4(), uuid4()
    c = _cliente_sin_tocar_bd()
    try:
        with patch.object(web, "ruta_previa", AsyncMock(
                side_effect=AssertionError("cerrar no busca la previa"))) as mock:
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa?cerrar=1")
    finally:
        _cerrar()

    assert r.status_code == 200
    assert r.text == ""
    assert r.headers["Cache-Control"] == "no-store"
    assert mock.await_count == 0


def test_cerrar_numero_tambien_en_visita_directa():
    """Una visita directa a `?cerrar=1` no enlazada devuelve igualmente el hueco vacío."""
    serie, issue = uuid4(), uuid4()
    c = _cliente_sin_tocar_bd()
    try:
        r = c.get(f"/ui/series/{serie}/numero/{issue}/previa?cerrar=1")
    finally:
        _cerrar()

    assert r.status_code == 200 and r.text == ""
    assert r.headers["Cache-Control"] == "no-store"


def test_la_tarjeta_no_tiene_enfocables_y_su_pie_es_honesto():
    plantillas = Path(__file__).resolve().parents[1] / "src/zascarr/web/templates"
    numero = (plantillas / "_previa_numero.html").read_text()
    serie = (plantillas / "_previa_serie.html").read_text()
    for texto in (numero, serie):
        assert "Vista previa · Esc o clic para apartarla" in texto
        assert "Pulsa para abrir la ficha" not in texto
        # Decorativa y sin trampa: nada enfocable ni roles nuevos dentro de la tarjeta.
        for etiqueta in ("<a ", "<button", "<input", "tabindex=", "role="):
            assert etiqueta not in texto
    assert 'alt=""' in numero
