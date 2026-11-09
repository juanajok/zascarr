# ruff: noqa: E501
"""#233 / BL-R4 en la web: aviso en la ficha, «Mantener lo mío» y «Revisar» (sin BD real).

La ficha solo LEE lo que dejó el rescan; la acción es explícita y con token. El caso de servicio está
en `test_rescan_relacion_confirmada_pg.py`; aquí se prueba el contrato de pantalla y de ruta.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.test_web_series import (
    FakeExecResult,
    FakeSession,
    acuse,
    make_series,
    retirados,
    use_fake_session,
)
from zascarr.models import FileFormat, IssueFormat
from zascarr.services.discrepancias import ResultadoMantener
from zascarr.services.tokens_revision import MantenerFirmada, crear_token_mantener

SECRETO = "secreto-de-prueba-para-mantener"
SERIE = uuid4()
ISSUE = uuid4()
FILE = uuid4()
OPERACION = str(uuid4())
CLAVE = "a" * 64
FECHA = "2026-11-09T00:00:00+00:00"


def _vinculo() -> dict:
    return {"version": 1, "operacion_id": OPERACION, "serie_id": str(SERIE), "fecha": FECHA}


def _discrepancia() -> dict:
    return {
        "version": 1, "clave": CLAVE, "origen": "rescan",
        "propuesta": {"origen": "rescan", "fuente": None, "id_externo": None,
                      "serie_destino_id": str(SERIE), "issue_destino_uuid": str(uuid4()),
                      "numero": "2", "formato": "single_issue", "titulo_norm": "thorgal", "anio": 1980},
        "relacion": {"issue_id": str(ISSUE), "serie_id": str(SERIE), "operacion_id": OPERACION},
        "estado": "pendiente", "observada_en": FECHA,
    }


def _fila_archivo(series_id=None) -> SimpleNamespace:
    serie = series_id or SERIE
    vinculo = _vinculo()
    vinculo["serie_id"] = str(serie)
    d = _discrepancia()
    d["relacion"]["serie_id"] = str(serie)
    return SimpleNamespace(
        id=FILE, file_name="Thorgal 01.cbz", file_format=FileFormat.CBZ, is_missing=False,
        metadata_source="manual", metadata_={"vinculo": vinculo, "discrepancias": [d]},
        issue_id=ISSUE, issue_number="1", sort_order=1.0, series_id=serie, format=IssueFormat.SINGLE_ISSUE,
        formato_publicacion="single_issue",
    )


def _ficha(series=None, *, archivos=None):
    series = series or make_series(total_issues=3)
    filas = [archivos or _fila_archivo(series.id)]
    session = FakeSession([
        FakeExecResult([series]), FakeExecResult([]), acuse(), retirados(), FakeExecResult(filas),
        FakeExecResult([]),                                   # asignaciones vivas (BL-R1b)
    ], series=series)
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{series.id}")
    assert r.status_code == 200
    return r.text, series


@pytest.fixture
def secreto(monkeypatch):
    import zascarr.web.series as web
    monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


def test_la_ficha_avisa_que_la_propuesta_no_se_ha_aplicado_y_ofrece_las_dos_salidas():
    texto, series = _ficha()
    visible = " ".join(texto.split())
    assert "Una actualización propone otra publicación; no se ha aplicado." in visible
    assert "Confirmaste el número #1 (grapa)" in visible
    assert "La actualización propone el número #2 (grapa)" in visible
    assert f'href="/ui/series/{series.id}/archivos/{FILE}/discrepancias/{CLAVE}/mantener"' in texto
    assert f'href="/ui/series/{series.id}/archivos/{FILE}/deshacer"' in texto
    assert "Mantener lo mío" in texto and "Revisar" in texto
    # Un solo botón principal en la ficha (el de «Añadir números»); las salidas de BL-R4 no lo son.
    assert texto.count('class="btn primary"') == 1


def test_una_propuesta_de_otra_serie_manda_revisar_la_identidad_de_la_serie():
    d = _discrepancia()
    d["propuesta"]["serie_destino_id"] = str(uuid4())
    fila = _fila_archivo()
    fila.metadata_ = {"vinculo": _vinculo(), "discrepancias": [d]}
    texto, series = _ficha(archivos=fila)
    assert f'href="/ui/series/{series.id}/asociar"' in texto


def test_sin_discrepancias_la_ficha_no_pinta_el_aviso():
    fila = _fila_archivo()
    fila.metadata_ = {"vinculo": _vinculo()}
    texto, _series = _ficha(archivos=fila)
    assert "Una actualización propone otra publicación" not in texto


def test_la_ficha_no_se_sirve_de_cache():
    series = make_series(total_issues=3)
    session = FakeSession([FakeExecResult([series]), FakeExecResult([]), acuse(), retirados(),
                           FakeExecResult([])], series=series)
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{series.id}")
    assert r.headers.get("cache-control") == "no-store"


def _token(file_id=FILE, *, clave=CLAVE, issue_id=str(ISSUE), serie_id=str(SERIE), operacion=None) -> str:
    return crear_token_mantener(MantenerFirmada(
        file_id=str(file_id), clave=clave, issue_id=issue_id, serie_id=serie_id,
        vinculo_operacion=OPERACION, operacion=str(operacion or uuid4())), SECRETO)


def test_la_confirmacion_muestra_el_token_y_no_escribe(secreto):
    issue = SimpleNamespace(series_id=SERIE, issue_number="1", format=IssueFormat.SINGLE_ISSUE)
    session = FakeSession([FakeExecResult([_fila_archivo()]), FakeExecResult([issue])],
                          series=SimpleNamespace(id=SERIE, title="Thorgal"))
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{SERIE}/archivos/{FILE}/discrepancias/{CLAVE}/mantener")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    assert "Mantener lo mío" in r.text and 'name="token"' in r.text
    assert "La propuesta no se ha aplicado." in r.text
    assert "Confirmaste el número #1" in r.text


def test_confirmar_con_token_valido_muestra_el_resultado(secreto, monkeypatch):
    import zascarr.web.series as web
    r = ResultadoMantener(1, str(uuid4()), str(FILE), CLAVE, "mantenida", None,
                          "Listo: se mantiene la publicación que confirmaste.", FECHA)
    monkeypatch.setattr(web, "mantener_lo_mio", AsyncMock(return_value=r))
    session = FakeSession([], series=SimpleNamespace(id=SERIE, title="Thorgal"))
    with use_fake_session(session) as client:
        p = client.post(f"/ui/series/{SERIE}/archivos/{FILE}/discrepancias/{CLAVE}/mantener",
                        data={"token": _token()})
    assert p.status_code == 200 and "Listo: se mantiene la publicación que confirmaste." in p.text
    assert p.headers.get("cache-control") == "no-store"


def test_confirmar_con_token_de_otro_archivo_no_llama_al_servicio(secreto, monkeypatch):
    import zascarr.web.series as web
    llamada = AsyncMock()
    monkeypatch.setattr(web, "mantener_lo_mio", llamada)
    session = FakeSession([], series=SimpleNamespace(id=SERIE, title="Thorgal"))
    with use_fake_session(session) as client:
        p = client.post(f"/ui/series/{SERIE}/archivos/{FILE}/discrepancias/{CLAVE}/mantener",
                        data={"token": _token(file_id=uuid4())})
    assert p.status_code == 200 and "no es válida" in p.text
    llamada.assert_not_called()
