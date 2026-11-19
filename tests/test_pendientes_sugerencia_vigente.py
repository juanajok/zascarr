"""La sugerencia «¿Es esta serie?» se comprueba contra las series que existen AHORA.

Caso real (Absolute Batman, 2026-11-19): la serie se borró y se volvió a crear con otro id; los
pendientes seguían guardando el id antiguo en `metadata.candidates` y el botón «Sí, organizar»
mandaba una serie que ya no existe. 39 de 620 pendientes estaban así.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from tests.test_pendientes import FakeExecResult, FakeSession, cola_de, use_fake_session
from zascarr.models import File, FileFormat


def _archivo(sid_guardado, *, anio=2024, titulo="Absolute Batman"):
    return File(
        id=uuid4(), file_path="/lib/Comics/x/Absolute Batman 01 [HenryKabuto CRG].cbz",
        file_name="Absolute Batman 01 [HenryKabuto CRG].cbz", file_format=FileFormat.CBZ,
        metadata_={"match_status": "unsorted", "candidates": [
            {"series_id": str(sid_guardado), "title": titulo, "start_year": anio, "score": 1.0}]})


def _serie(sid, titulo="Absolute Batman", anio=2024):
    return SimpleNamespace(id=sid, title=titulo, title_norm=titulo.lower(), start_year=anio)


def _pagina(archivo, *resultados):
    cola = cola_de([archivo], series_actuales=[])        # ninguna de las guardadas existe
    return [*cola[:-1], FakeExecResult([]), *resultados]


def _get(archivo, *resultados):
    with use_fake_session(FakeSession(exec_queue=_pagina(archivo, *resultados))) as client:
        return client.get("/ui/pendientes")


def test_candidata_con_serie_recreada_apunta_a_la_serie_actual():
    """Regresión: id guardado inexistente + una serie actual con el mismo título y año."""
    vieja, nueva = uuid4(), uuid4()
    r = _get(_archivo(vieja), FakeExecResult([_serie(nueva)]))
    assert r.status_code == 200
    assert "¿Es esta serie?" in r.text
    assert f'value="{nueva}"' in r.text
    assert str(vieja) not in r.text


def test_candidata_sin_serie_actual_no_ofrece_sugerencia():
    """Una sugerencia que falla es peor que ninguna."""
    vieja = uuid4()
    r = _get(_archivo(vieja), FakeExecResult([]))
    assert r.status_code == 200
    assert "¿Es esta serie?" not in r.text
    assert str(vieja) not in r.text


def test_candidata_con_dos_series_del_mismo_titulo_y_año_no_se_adivina():
    r = _get(_archivo(uuid4()), FakeExecResult([_serie(uuid4()), _serie(uuid4())]))
    assert "¿Es esta serie?" not in r.text


def test_el_año_distinto_no_sirve_de_sustituta():
    """«Batman (1940)» no es «Batman (2011)»: con año en la candidata, el año debe coincidir."""
    r = _get(_archivo(uuid4(), anio=2024), FakeExecResult([_serie(uuid4(), anio=2011)]))
    assert "¿Es esta serie?" not in r.text


def test_candidata_con_serie_existente_se_deja_tal_cual():
    """Contraprueba: si el id guardado existe, no se busca otra serie ni se cambia nada."""
    sid = uuid4()
    archivo = _archivo(sid)
    with use_fake_session(FakeSession(exec_queue=cola_de([archivo]))) as client:
        r = client.get("/ui/pendientes")
    assert f'value="{sid}"' in r.text
