"""Historia #843: pantalla de importación de guías de lectura (sin red)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.arcos import DetalleArco, PaginaArcos
from zascarr.services.reconciliacion_lecturas import ResultadoReconciliacion
from zascarr.utils.cortesia import CortesiaEnEspera

URL_RO = ("https://comicbookreadingorders.com/dc/events/"
          "crisis-on-infinite-earths-reading-order/")


def _cliente():
    async def _execute(_consulta):
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                              execute=_execute)
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def _resultado(arco_id=None, *, enlazados=3, omitidos=1,
               motivos=(("numero_no_encontrado", 1),)):
    return ResultadoReconciliacion(
        titulo="Crisis on Infinite Earths", origen="reading_orders",
        url=URL_RO, creado=True, enlazados=enlazados, omitidos=omitidos,
        motivos=motivos, arco_id=arco_id or uuid4())


def test_el_formulario_tiene_fuente_url_y_un_solo_boton_principal(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    c = _cliente()
    try:
        r = c.get("/ui/arcos/importar-guia")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'action="/ui/arcos/importar-guia"' in r.text
    assert 'name="fuente"' in r.text and 'name="url"' in r.text
    assert "Reading Orders" in r.text and "Continuity Guide" in r.text
    assert r.text.count('class="btn primary"') == 1
    assert "Ajustes" in r.text


def test_arcos_enlaza_la_pantalla_de_importacion():
    pagina = PaginaArcos([], 1, 1, 0, 0, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)), \
                patch("zascarr.web.arcos._novedades_de_herald", AsyncMock(return_value=[])):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'href="/ui/arcos/importar-guia"' in r.text
    assert "Importar una guía" in r.text


def test_post_ok_redirige_a_la_saga_con_resumen(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    resultado = _resultado()
    leer = AsyncMock(return_value=resultado)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.leer_y_reconciliar", leer):
            r = c.post("/ui/arcos/importar-guia",
                       data={"fuente": "reading_orders", "url": URL_RO},
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303
    destino = r.headers["location"]
    assert destino.startswith(f"/ui/arcos/{resultado.arco_id}?importada=1")
    assert "enlazados=3" in destino and "omitidos=1" in destino
    assert "n%C3%BAmeros+que+no+tienes" in destino or "números que no tienes" in destino
    leer.assert_awaited_once()


def test_post_con_la_fuente_apagada_no_lee_ni_hace_red(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: False)
    leer = AsyncMock()
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.leer_y_reconciliar", leer):
            r = c.post("/ui/arcos/importar-guia",
                       data={"fuente": "reading_orders", "url": URL_RO})
    finally:
        _cerrar()
    assert r.status_code == 200 and "apagada" in r.text
    leer.assert_not_awaited()


def test_post_rechaza_un_host_ajeno(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    leer = AsyncMock()
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.leer_y_reconciliar", leer):
            r = c.post("/ui/arcos/importar-guia",
                       data={"fuente": "reading_orders",
                             "url": "https://atacante.example/guia/"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "no es una guía válida" in r.text
    leer.assert_not_awaited()


def test_post_rechaza_una_fuente_desconocida(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    c = _cliente()
    try:
        r = c.post("/ui/arcos/importar-guia",
                   data={"fuente": "fandom_dc", "url": URL_RO})
    finally:
        _cerrar()
    assert r.status_code == 200 and "Elige una de las dos fuentes" in r.text


def test_post_sin_entradas_no_redirige(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.leer_y_reconciliar", AsyncMock(return_value=None)):
            r = c.post("/ui/arcos/importar-guia",
                       data={"fuente": "reading_orders", "url": URL_RO})
    finally:
        _cerrar()
    assert r.status_code == 200 and "no tiene entradas legibles" in r.text


def test_post_con_cortesia_avisa_de_la_espera_sin_500(monkeypatch):
    monkeypatch.setattr("zascarr.web.arcos.fuente_habilitada", lambda *_a, **_k: True)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.leer_y_reconciliar",
                   AsyncMock(side_effect=CortesiaEnEspera(
                       "reading_orders", "comicbookreadingorders.com", 12.0))):
            r = c.post("/ui/arcos/importar-guia",
                       data={"fuente": "reading_orders", "url": URL_RO})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "pide esperar" in r.text and "12" in r.text


def test_la_saga_muestra_el_resumen_de_la_importacion():
    arco_id = uuid4()
    detalle = DetalleArco(str(arco_id), "Crisis on Infinite Earths", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{arco_id}?importada=1&enlazados=3&omitidos=1"
                      "&motivos=1%20números%20que%20no%20tienes")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Guía importada" in r.text and "3 números enlazados" in r.text
    assert "omitidos" in r.text and "números que no tienes" in r.text
