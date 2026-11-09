# ruff: noqa: E501
"""#447 web: ficha de serie y de número con TestClient (sin red)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from tests.test_web_series import FakeExecResult, FakeSession, make_series, use_fake_session
from zascarr.models import CreatorRole, FileFormat


def _issue(**extra):
    base = dict(id=uuid4(), series_id=uuid4(), issue_number="3", title="El país Qâ",
                release_date=date(1981, 6, 1), page_count=48,
                synopsis="<p>Thorgal <b>llega</b> a un país.</p>", metadata_source="manual",
                credits=[], files=[])
    base.update(extra)
    return SimpleNamespace(**base)


def _serie(**extra):
    base = dict(id=uuid4(), title="Thorgal", start_year=1977, end_year=2000,
                publisher=SimpleNamespace(name="Norma"), description="<p>Una serie.</p>",
                metadata_source="comic_vine", locked_fields=[], metadata_={},
                total_issues=None, tradition=None)
    base.update(extra)
    return SimpleNamespace(**base)


def test_ficha_de_numero_muestra_texto_plano_autores_y_archivos():
    serie = _serie()
    issue = _issue(series_id=serie.id, credits=[
        SimpleNamespace(role=CreatorRole.WRITER, creator=SimpleNamespace(name="Ana")),
        SimpleNamespace(role=CreatorRole.PENCILER, creator=SimpleNamespace(name="Bea")),
    ], files=[
        SimpleNamespace(id=uuid4(), file_name="Thorgal 03.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=2 * 1048576, is_missing=False),
    ])
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert r.status_code == 200
    assert "Número 3" in r.text and "El país Qâ" in r.text
    assert "Portada de la serie" in r.text
    assert "Thorgal llega a un país." in r.text
    assert "<b>llega</b>" not in r.text
    assert "Guion" in r.text and "Dibujo" in r.text
    assert "Thorgal 03.cbz" in r.text
    assert "De dónde sale cada dato" in r.text
    assert "Puesto a mano" in r.text
    assert "Origen no registrado" not in r.text
    assert "None" not in r.text


def test_ficha_de_numero_sin_datos_dice_que_falta():
    serie = _serie(publisher=None, start_year=None, end_year=None)
    issue = _issue(series_id=serie.id, synopsis=None, release_date=None, page_count=None,
                   title=None, metadata_source=None)
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert r.status_code == 200
    assert "Todavía no hay información de este número" in r.text
    assert "No consta todavía" not in r.text
    assert "None" not in r.text


def test_ficha_de_serie_incluye_bloque_y_ordena_sin_romper():
    serie = make_series(total_issues=3)
    with use_fake_session(FakeSession([FakeExecResult([serie])]
                                      + [FakeExecResult([])] * 12)) as client:
        r = client.get(f"/ui/series/{serie.id}")
    assert r.status_code == 200
    assert "Sobre esta serie" in r.text
    assert "Autores principales" in r.text
    assert "No consta todavía" in r.text
    # La acción principal sigue antes del bloque nuevo (presupuesto #208/#304).
    assert r.text.index("Añadir números del disco") < r.text.index("Sobre esta serie")


def test_ficha_de_numero_404_y_no_store():
    serie = _serie()
    with use_fake_session(FakeSession([FakeExecResult([])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{uuid4()}")
    assert r.status_code == 404
    # La ruta de una ficha existente no-store se comprueba en el caso 200.
    issue = _issue(series_id=serie.id)
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie])])) as client:
        ok = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"


def test_ficha_de_numero_parcial_sin_autores_ni_archivos():
    serie = _serie()
    issue = _issue(series_id=serie.id, credits=[], files=[])
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert r.status_code == 200
    assert "No constan todavía los autores" in r.text
    assert "No hay ningún archivo vinculado" in r.text
    assert "Todavía no hay información de este número" not in r.text


def test_series_fuentes_sigue_dentro_de_la_cabecera_y_chip_con_sr():
    serie = make_series(total_issues=1)
    with use_fake_session(FakeSession([FakeExecResult([serie])]
                                      + [FakeExecResult([])] * 12)) as client:
        r = client.get(f"/ui/series/{serie.id}")
    html = r.text
    assert html.index("Fuentes y atribución") < html.index("Sobre esta serie")
    assert 'class="caption">Los que más números firman' in html
    with open("src/zascarr/static/web.css", encoding="utf-8") as css:
        assert "min-height: 40px" in css.read()


def test_procedencia_de_autores_muestra_nombres_y_origen(monkeypatch):
    from zascarr.services.ficha_numero import AutorPrincipal, FichaSerie
    from zascarr.web import series as web_series
    serie = make_series(total_issues=1)
    ficha = FichaSerie(serie=serie, sinopsis="", autores={
        "writer": [AutorPrincipal(nombre="Ana", papel="writer", numeros=3)]},
        origen_autores="Comic Vine")
    monkeypatch.setattr(web_series, "cargar_ficha_serie", AsyncMock(return_value=ficha))
    with use_fake_session(FakeSession([FakeExecResult([serie])]
                                      + [FakeExecResult([])] * 12)) as client:
        r = client.get(f"/ui/series/{serie.id}")
    assert "Guion: Ana" in r.text
    assert "Comic Vine" in r.text
