"""#854: pasada de UI/UX (Herald perezoso y hallazgos M/B de la auditoría)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.arcos import DetalleArco, FilaArco, PaginaArcos

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")


def _cliente(execute=None):
    async def _exec(_consulta):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                              execute=execute or _exec)

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_el_estado_vacio_de_sagas_tiene_accion_principal():
    pagina = PaginaArcos([], 0, 1, 1, 0, 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'class="arcos-acciones"' in r.text
    assert 'class="empty-state"' in r.text
    assert 'class="btn primary" href="/ui/arcos/nueva"' in r.text
    assert 'class="arcos-acciones-secundarias"' in r.text


def test_la_saga_usa_un_solo_autofocus_con_prioridad_pedido():
    arco_id = uuid4()
    filas = [FilaArco(1, "i1", "s1", "Batman", "1", None, None, True)]
    detalle = DetalleArco(str(arco_id), "Saga", None, False, filas, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{arco_id}?importada=1&enlazados=1&omitidos=0"
                      "&guardado=pedido&anadidos=1&ya_pedidos=0&en_biblioteca=0")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.text.count("autofocus") == 1


def test_los_controles_de_fila_tienen_nombres_accesibles_unicos():
    arco_id = uuid4()
    filas = [FilaArco(1, "i1", "s1", "Batman", "1", None, None, True),
             FilaArco(2, "i2", "s1", "Batman", "2", None, None, True)]
    detalle = DetalleArco(str(arco_id), "Saga", None, False, filas, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{arco_id}")
    finally:
        _cerrar()
    for texto in ("Subir Batman #1 una posición", "Bajar Batman #1 una posición",
                  "Quitar Batman #1 de la saga", "Subir Batman #2 una posición"):
        assert f'aria-label="{texto}"' in r.text
    assert r.text.count('aria-label="Subir ') == 2


def test_el_h1_de_la_saga_solo_usa_titulo_frase_si_es_largo():
    arco_id = uuid4()
    corta = DetalleArco(str(arco_id), "Saga", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=corta)):
            r = c.get(f"/ui/arcos/{arco_id}")
    finally:
        _cerrar()
    assert "<h1>Saga</h1>" in r.text

    larga = DetalleArco(str(arco_id), "Una saga con muchas palabras", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=larga)):
            r = c.get(f"/ui/arcos/{arco_id}")
    finally:
        _cerrar()
    assert '<h1 class="titulo-frase">Una saga con muchas palabras</h1>' in r.text


def test_la_ficha_tiene_una_sola_caja_de_atribucion_y_details_coherente():
    from tests.test_web_series import (
        FakeExecResult,
        FakeSession,
        acuse,
        make_series,
        retirados,
        use_fake_session,
    )

    series = make_series(total_issues=3)
    series.fandom_dc_slug = "Batman"
    series.metadata_ = {"relleno": {"gcd": {"id": "1", "campos": ["start_year"],
                                            "ultimo_intento": "2026-11-14T12:00:00+00:00",
                                            "url_ficha": "https://www.comics.org/series/1/"}}}
    session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(),
                           retirados(), FakeExecResult([])])
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{series.id}")
    assert r.status_code == 200
    assert r.text.count('class="atribucion-fuentes"') == 1
    assert "<summary>Aviso legal</summary>" in r.text
    assert "Grand Comics Database" in r.text and "DC Database" in r.text


def test_el_css_de_las_novedades_y_del_formulario_usa_tokens():
    for clase in (".novedades-lista", ".novedades-esqueleto", ".esqueleto-fila",
                  ".arcos-acciones", ".atribucion-lista"):
        assert clase in CSS
    assert "min-height: calc(5 * 2.75rem" in CSS
    assert ":has(#novedades-herald-contenido:empty)" in CSS
    assert "overflow-wrap: anywhere" in CSS
    assert "font-variant-numeric: tabular-nums" in CSS
    assert "rgb(" not in CSS.split(".novedades-esqueleto", 1)[1].split("}", 1)[0]
