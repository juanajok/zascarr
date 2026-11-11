"""#342: formularios de notas en las fichas (fake session, sin red)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from tests.test_web_series import (
    FakeExecResult,
    FakeSession,
    acuse,
    make_series,
    retirados,
    use_fake_session,
)
from zascarr.models import WishlistPolicy


def test_serie_sin_notas_solo_muestra_anadir_nota():
    series = make_series(total_issues=3)
    session = FakeSession([
        FakeExecResult([series]), FakeExecResult([]),
        acuse(), retirados(), FakeExecResult([]),
    ])
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{series.id}")
    assert r.status_code == 200
    assert "Añadir nota" in r.text
    assert "<h2 id=\"notas-serie-titulo\"" not in r.text


def test_guardar_y_borrar_nota_de_serie():
    series = make_series(total_issues=3)
    series.wishlist_policy = WishlistPolicy.NONE
    session = FakeSession([FakeExecResult([])], series=series)
    with use_fake_session(session, ficha=False) as client:
        r = client.post(f"/ui/series/{series.id}/nota",
                        data={"texto": "  falta el mapa  "}, follow_redirects=False)
    assert r.status_code == 303
    assert "nota=guardada" in r.headers["location"]
    session.flush.assert_awaited()


def test_nota_vacia_no_escribe():
    series = make_series(total_issues=3)
    session = FakeSession([], series=series)
    with use_fake_session(session, ficha=False) as client:
        r = client.post(f"/ui/series/{series.id}/nota",
                        data={"texto": "   "}, follow_redirects=False)
    assert r.status_code == 303
    assert "nota=vacia" in r.headers["location"]
    session.flush.assert_not_awaited()


def test_guardar_nota_de_numero():
    series = make_series(total_issues=3)
    issue = SimpleNamespace(id=uuid4(), series_id=series.id, issue_number="3")
    session = FakeSession([
        FakeExecResult([issue.id]),   # numero_existe
        FakeExecResult([]),           # leer_numero
    ], series=series)
    with use_fake_session(session, ficha=False) as client:
        r = client.post(f"/ui/series/{series.id}/numero/{issue.id}/nota",
                        data={"texto": "páginas 12-13"}, follow_redirects=False)
    assert r.status_code == 303
    assert "#nota-numero" in r.headers["location"]
    assert "nota=guardada" in r.headers["location"]


def test_aviso_de_nota_vacia_se_ve_fuera_del_details():
    series = make_series(total_issues=3)
    session = FakeSession([
        FakeExecResult([series]), FakeExecResult([]),
        acuse(), retirados(), FakeExecResult([]),
    ])
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{series.id}?nota=vacia")
    assert "La nota no puede estar vacía." in r.text
    assert r.text.index("La nota no puede estar vacía.") < r.text.index('<details id="notas-serie"')


def test_borrar_pide_confirmacion_en_plantilla():
    from zascarr.web.routes import crear_templates
    nota = SimpleNamespace(texto="nota")
    html = crear_templates().get_template("_nota_serie.html").render(
        series=SimpleNamespace(id=uuid4()), nota_serie=nota, notas_numeros=[],
        nota_aviso="", ui=None)
    assert "<summary>Borrar nota</summary>" in html
    assert "¿Seguro que quieres borrar esta nota?" in html
    assert 'name="accion" value="borrar"' in html


def test_accion_de_nota_desconocida_es_422():
    series = make_series(total_issues=3)
    session = FakeSession([], series=series)
    with use_fake_session(session, ficha=False) as client:
        r = client.post(f"/ui/series/{series.id}/nota",
                        data={"texto": "x", "accion": "inventada"})
    assert r.status_code == 422
