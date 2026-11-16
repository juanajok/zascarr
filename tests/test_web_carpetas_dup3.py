# ruff: noqa: E501
"""BL-DUP3 (#266): UI de carpetas repetidas (TestClient, sin PG)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_web_duplicados_264 import FakeSession, use_fake_session
from zascarr.services.apartado_duplicados import ResultadoApartado, ResultadoGrupo


def _par(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "A"
    b = tmp_path / "B"
    a.mkdir()
    b.mkdir()
    for c in (a, b):
        (c / "01.cbz").write_bytes(b"uno")
        (c / "02.cbz").write_bytes(b"dos")
    (a / "solo-a.cbz").write_bytes(b"a")
    (b / "solo-b.cbz").write_bytes(b"b")
    (a / "distinto.cbz").write_bytes(b"version-a")
    (b / "distinto.cbz").write_bytes(b"version-b")
    return a, b


@pytest.fixture
def ajustes(tmp_path, monkeypatch):
    monkeypatch.setattr("zascarr.web.auditoria.get_settings", lambda: SimpleNamespace(
        library_path=tmp_path, secret_key="secreto-web-carpetas"))
    return tmp_path


def test_detalle_muestra_hechos_y_no_preselecciona(ajustes):
    a, b = _par(ajustes)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/carpetas",
                   data={"ruta_a": str(a), "ruta_b": str(b)})
    assert r.status_code == 200
    assert "Comunes idénticos" in r.text and "01.cbz" in r.text and "02.cbz" in r.text
    assert "Mismo nombre, contenido distinto" in r.text and "distinto.cbz" in r.text
    assert "solo-a.cbz" in r.text and "solo-b.cbz" in r.text
    assert 'type="radio" name="keep" value="a"' in r.text
    assert 'type="radio" name="keep" value="b"' in r.text
    assert "checked" not in r.text
    assert "Revisar qué sobra" not in r.text  # es el detalle, no la lista
    assert r.headers["cache-control"] == "no-store"


def test_previsualizar_firma_solo_comunes_identicos(ajustes):
    a, b = _par(ajustes)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/carpetas/previsualizar",
                   data={"ruta_a": str(a), "ruta_b": str(b), "keep": "a"})
    assert r.status_code == 200
    assert "Vista previa: apartar lo que sobra" in r.text
    assert "Se apartarán <strong>2</strong> archivos" in r.text
    assert "Confirmar y apartar" in r.text
    assert "distinto.cbz" not in r.text
    assert "solo-b.cbz" not in r.text
    assert 'name="token"' in r.text and 'name="grupos"' in r.text
    assert r.headers["cache-control"] == "no-store"


def test_confirmar_usa_apartado_y_muestra_resultado(ajustes, monkeypatch):
    a, b = _par(ajustes)
    async def confirmar(_self, _token, _grupos):
        return ResultadoApartado("77777777-7777-7777-7777-777777777777", "confirmada",
                                 [ResultadoGrupo("a" * 64, "movido", movidos=1, bytes=4)],
                                 1, 1, 4)
    monkeypatch.setattr("zascarr.services.apartado_duplicados.ApartadoDuplicadosService.confirmar",
                        confirmar)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/carpetas/confirmar",
                   data={"token": "t", "grupos": json.dumps(
                       {"sha256": "a" * 64, "rutas": ["A/01.cbz", "B/01.cbz"],
                        "keep_index": 0})})
    assert r.status_code == 200
    assert "Resultado: carpetas repetidas" in r.text
    assert "Deshacer el apartado" in r.text


def test_confirmar_carpeta_vacia_se_ofrece_y_se_puede_deshacer(ajustes, monkeypatch):
    async def apartar(_db, ruta, **_kw):
        assert ruta == "Parcial"
        return "88888888-8888-8888-8888-888888888888"
    monkeypatch.setattr("zascarr.web.auditoria.apartar_carpeta_vacia", apartar)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/carpetas/confirmar",
                   data={"ruta_apartar": "Parcial", "apartar_vacia": "1"})
    assert r.status_code == 200
    assert "Carpeta vacía" in r.text
    assert "Deshacer el apartado de la carpeta" in r.text
