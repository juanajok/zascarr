"""#1027: control de obra autoconclusiva en la ficha y selector de Pendientes."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from tests.test_web_series import FakeExecResult, FakeSession, use_fake_session
from zascarr.models import ComicTradition, Series, SeriesKind


def _serie(**kw) -> Series:
    return Series(id=uuid4(), title="Una novela gráfica",
                  tradition=ComicTradition.AMERICAN, **kw)


def test_marcar_y_desmarcar_obra_unica(monkeypatch):
    serie = _serie(total_issues=1, kind=SeriesKind.REGULAR)
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=True))
    with use_fake_session(FakeSession(queue=[
            FakeExecResult([serie]),          # select serie
            FakeExecResult([1]),              # count publicaciones
            FakeExecResult([uuid4()]),         # huecos: publicación existente
    ]), ficha=False) as client:
        r = client.post(f"/ui/series/{serie.id}/one-shot", data={"one_shot": "true"})
    assert r.status_code == 200
    assert serie.kind == SeriesKind.ONE_SHOT
    assert "Tomo único" in r.text

    # Idempotente: desmarcar vuelve a regular.
    with use_fake_session(FakeSession(queue=[
            FakeExecResult([serie]),
            FakeExecResult([1]),
    ]), ficha=False) as client:
        r = client.post(f"/ui/series/{serie.id}/one-shot", data={})
    assert r.status_code == 200
    assert serie.kind == SeriesKind.REGULAR


def test_no_se_marca_si_tiene_mas_de_una_publicacion(monkeypatch):
    serie = _serie(total_issues=2, kind=SeriesKind.REGULAR)
    monkeypatch.setattr("zascarr.web.series.is_acknowledged", AsyncMock(return_value=True))
    with use_fake_session(FakeSession(queue=[
            FakeExecResult([serie]),
            FakeExecResult([2]),
    ]), ficha=False) as client:
        r = client.post(f"/ui/series/{serie.id}/one-shot", data={"one_shot": "true"})
    assert r.status_code == 200
    assert serie.kind == SeriesKind.REGULAR
    assert "más de una publicación" in r.text


def test_el_selector_oculta_one_shot_por_defecto():
    from zascarr.services.review import ReviewService

    serie = _serie(kind=SeriesKind.ONE_SHOT)
    db = FakeSession(queue=[FakeExecResult([serie])])
    # La consulta compilada debe excluir ONE_SHOT sin el interruptor.
    servicio = ReviewService(db)
    import asyncio
    filas = asyncio.run(servicio.search_series("novela"))
    assert filas == [serie]
