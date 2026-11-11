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
        SimpleNamespace(role=CreatorRole.WRITER,
                        creator=SimpleNamespace(name="Ana", metadata_source="manual")),
        SimpleNamespace(role=CreatorRole.PENCILER,
                        creator=SimpleNamespace(name="Bea", metadata_source="manual")),
    ], files=[
        SimpleNamespace(id=uuid4(), file_name="Thorgal 03.cbz", file_format=FileFormat.CBZ,
                        file_size_bytes=2 * 1048576, is_missing=False),
    ])
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie]), FakeExecResult([])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert r.status_code == 200
    assert "Número 3" in r.text and "El país Qâ" in r.text
    assert "Portada del número" in r.text
    assert f"/ui/series/{serie.id}/numero/{issue.id}/portada.jpg" in r.text
    assert f"/ui/series/{serie.id}/portada?v=2" not in r.text
    assert "Editorial" in r.text and "Norma" in r.text
    assert "Publicación" in r.text and "1 de junio de 1981" in r.text
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
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie]), FakeExecResult([])])) as client:
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
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie]), FakeExecResult([])])) as client:
        ok = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"


def test_ficha_de_numero_parcial_sin_autores_ni_archivos():
    serie = _serie()
    issue = _issue(series_id=serie.id, credits=[], files=[])
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie]), FakeExecResult([])])) as client:
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
    # La altura de 40 px se comprueba por selector en test_web_css_contraste.


def test_procedencia_de_autores_muestra_nombres_y_origen(monkeypatch):
    from zascarr.services.ficha_numero import AutorPrincipal, FichaSerie
    from zascarr.web import series as web_series
    serie = make_series(total_issues=1)
    ficha = FichaSerie(serie=serie, sinopsis="", autores={
        "writer": [AutorPrincipal(nombre="Ana", papel="writer", numeros=3)]},
        origen_autores="Comic Vine", autores_texto="Guion: Ana")
    monkeypatch.setattr(web_series, "cargar_ficha_serie", AsyncMock(return_value=ficha))
    with use_fake_session(FakeSession([FakeExecResult([serie])]
                                      + [FakeExecResult([])] * 12)) as client:
        r = client.get(f"/ui/series/{serie.id}")
    assert "Guion: Ana" in r.text
    assert "Comic Vine" in r.text


def test_hrefs_de_chip_y_archivo_por_numero(monkeypatch):
    from types import SimpleNamespace

    from zascarr.services.archivos_por_numero import NumeroConArchivos
    from zascarr.services.ficha_numero import FichaSerie, NumeroEnlace
    from zascarr.web import series as web_series
    serie = make_series(total_issues=1)
    ficha = FichaSerie(serie=serie, sinopsis="", numeros=[
        NumeroEnlace(id="issue-1", numero="01", tiene_archivos=True)])
    monkeypatch.setattr(web_series, "cargar_ficha_serie", AsyncMock(return_value=ficha))
    monkeypatch.setattr(web_series, "numeros_poseidos", AsyncMock(return_value={"01"}))
    monkeypatch.setattr(web_series, "huecos_de_serie", AsyncMock(return_value=SimpleNamespace(
        computable=True, faltantes=[], motivo=None)))
    monkeypatch.setattr(web_series, "archivos_por_numero", AsyncMock(return_value=[
        NumeroConArchivos(issue_id="issue-1", numero="01", archivos=[])]))
    with use_fake_session(FakeSession([FakeExecResult([serie])]
                                      + [FakeExecResult([])] * 8)) as client:
        r = client.get(f"/ui/series/{serie.id}")
    assert r.status_code == 200
    assert f'href="/ui/series/{serie.id}/numero/issue-1"' in r.text
    assert "ver información del número 01" in r.text
    assert f'hx-get="/ui/series/{serie.id}/convertir"' in r.text
    assert f'hx-get="/ui/series/{serie.id}/numero/issue-1/previa"' in r.text
    assert 'class="previa-numero"' in r.text
    assert 'id="previa-issue-1"' in r.text
    assert 'aria-hidden="true"' in r.text
    assert 'hx-trigger="mouseenter delay:150ms, focusin delay:150ms"' in r.text


def test_ficha_de_numero_ofrece_convertir_solo_para_cbr():
    serie = _serie()
    cbr = SimpleNamespace(id=uuid4(), file_name="Thorgal 03.cbr", file_format=FileFormat.CBR,
                          file_size_bytes=2 * 1048576, is_missing=False,
                          sha256_hash="a" * 64)
    cbz = SimpleNamespace(id=uuid4(), file_name="Thorgal 04.cbz", file_format=FileFormat.CBZ,
                          file_size_bytes=1, is_missing=False, sha256_hash="a" * 64)
    issue = _issue(series_id=serie.id, files=[cbr, cbz])
    with use_fake_session(FakeSession([FakeExecResult([issue]), FakeExecResult([serie]),
                                       FakeExecResult([]), FakeExecResult([])])) as client:
        r = client.get(f"/ui/series/{serie.id}/numero/{issue.id}")
    assert r.status_code == 200
    assert f"/ui/series/{serie.id}/archivos/{cbr.id}/convertir" in r.text
    assert f'hx-target="#resultado-conversion-{cbr.id}"' in r.text
    assert f"/archivos/{cbz.id}/convertir" not in r.text
    # BL-R6: mismo SHA-256 → copia exacta; se puede separar sin borrar.
    assert "Copia exacta" in r.text
    assert f"/ui/series/{serie.id}/archivos/{cbr.id}/deshacer" in r.text
    assert "Separar del número" in r.text
