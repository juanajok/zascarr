"""#993: toggle de seguimiento en la ficha, independiente de la política y con puerta legal."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from tests.test_web_series import FakeExecResult, FakeSession, make_series, use_fake_session
from zascarr.models import Series, WishlistPolicy


def _serie() -> Series:
    serie = make_series()
    serie.follow_new_issues = False
    serie.follow_new_issues_since = None
    serie.wishlist_policy = WishlistPolicy.MISSING
    return serie


def test_activar_fija_since_y_no_toca_la_politica(monkeypatch):
    serie = _serie()
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=True))
    with patch("zascarr.web.series.get_settings") as ajustes:
        ajustes.return_value = type("A", (), {
            "forum_enabled": False, "forum_url": "", "forum_username": "",
            "prowlarr_enabled": False, "prowlarr_api_key": ""})()
        with use_fake_session(FakeSession(queue=[FakeExecResult([serie])]), ficha=False) as client:
            r = client.post(f"/ui/series/{serie.id}/seguimiento",
                            data={"follow_new_issues": "true"})
    assert r.status_code == 200
    assert serie.follow_new_issues is True and serie.follow_new_issues_since is not None
    assert serie.wishlist_policy == WishlistPolicy.MISSING
    assert "Seguimiento activo" in r.text
    assert 'aria-label="Secciones de la ficha"' in r.text or "Números nuevos" in r.text


def test_desactivar_conserva_since(monkeypatch):
    from datetime import UTC, datetime
    serie = _serie()
    serie.follow_new_issues = True
    serie.follow_new_issues_since = datetime(2026, 11, 17, tzinfo=UTC)
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=True))
    with patch("zascarr.web.series.get_settings") as ajustes:
        ajustes.return_value = type("A", (), {
            "forum_enabled": False, "forum_url": "", "forum_username": "",
            "prowlarr_enabled": False, "prowlarr_api_key": ""})()
        with use_fake_session(FakeSession(queue=[FakeExecResult([serie])]), ficha=False) as client:
            r = client.post(f"/ui/series/{serie.id}/seguimiento", data={})
    assert r.status_code == 200
    assert serie.follow_new_issues is False
    assert serie.follow_new_issues_since is not None
    assert "no sigues" in r.text


def test_activar_sin_legal_no_cambia_el_flag(monkeypatch):
    serie = _serie()
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=False))
    with patch("zascarr.web.series.get_settings") as ajustes:
        ajustes.return_value = type("A", (), {
            "forum_enabled": False, "forum_url": "", "forum_username": "",
            "prowlarr_enabled": False, "prowlarr_api_key": ""})()
        with use_fake_session(__import__(
                "tests.test_web_series", fromlist=["FakeSession"]).FakeSession(
                queue=[FakeExecResult([serie])]), ficha=False) as client:
            r = client.post(f"/ui/series/{serie.id}/seguimiento",
                            data={"follow_new_issues": "true"})
    assert r.status_code == 200
    assert serie.follow_new_issues is False and serie.follow_new_issues_since is None
    assert "Falta aceptar el aviso legal" in r.text and "/ui/legal" in r.text

def test_activar_sin_legal_conserva_el_volver_anidado(monkeypatch):
    """El re-render HTMX del seguimiento no puede perder el contexto de vuelta."""
    serie = _serie()
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=False))
    with patch("zascarr.web.series.get_settings") as ajustes:
        ajustes.return_value = type("A", (), {
            "forum_enabled": False, "forum_url": "", "forum_username": "",
            "prowlarr_enabled": False, "prowlarr_api_key": ""})()
        with use_fake_session(
                FakeSession(queue=[FakeExecResult([serie])]), ficha=False) as client:
            r = client.post(f"/ui/series/{serie.id}/seguimiento",
                            data={"follow_new_issues": "true",
                                  "volver": f"/ui/biblioteca#serie-{serie.id}"})
    assert r.status_code == 200
    assert (f"/ui/series/{serie.id}%3Fvolver%3D"
            f"/ui/biblioteca%2523serie-{serie.id}") in r.text
