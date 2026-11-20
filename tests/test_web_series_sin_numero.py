"""Regresión: las publicaciones sin número no pueden quedar ocultas en «Archivos»."""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from tests.test_web_ficha_447 import _issue
from tests.test_web_series import FakeExecResult, FakeSession, make_series, use_fake_session
from zascarr.models import FileFormat
from zascarr.services.archivos_por_numero import ArchivoDeNumero, NumeroConArchivos
from zascarr.services.ficha_numero import FichaSerie, NumeroEnlace
from zascarr.web import series as web_series


def _publicacion(titulo="Las guerras silenciosas", *, falta=False):
    return NumeroConArchivos(
        issue_id=str(uuid4()), numero="(sin número)", titulo=titulo,
        archivos=[ArchivoDeNumero(
            id=str(uuid4()), nombre="Las guerras silenciosas.cbz", formato="cbz",
            falta_en_disco=falta, bloqueo=None,
        )],
    )


def _numeros(monkeypatch, publicaciones, *, numerada=False):
    serie = make_series(total_issues=1)
    ficha = FichaSerie(serie=serie, sinopsis="", numeros=[
        NumeroEnlace(id="numero-1", numero="1", tiene_archivos=True),
    ] if numerada else [])
    monkeypatch.setattr(web_series, "cargar_ficha_serie", AsyncMock(return_value=ficha))
    monkeypatch.setattr(
        web_series, "numeros_poseidos", AsyncMock(return_value={"1"} if numerada else set()),
    )
    monkeypatch.setattr(web_series, "huecos_de_serie", AsyncMock(return_value=SimpleNamespace(
        computable=True, faltantes=[], motivo=None,
    )))
    monkeypatch.setattr(
        web_series, "archivos_por_numero", AsyncMock(return_value=publicaciones),
    )
    sesion = FakeSession([FakeExecResult([serie])] + [FakeExecResult([])] * 8)
    with use_fake_session(sesion) as client:
        respuesta = client.get(f"/ui/series/{serie.id}")
    assert respuesta.status_code == 200
    seccion = re.search(
        r'<section id="numeros-serie".*?</section>', respuesta.text, flags=re.S,
    )
    assert seccion is not None
    return serie, seccion.group()


@pytest.mark.parametrize("falta", [False, True])
def test_sin_numero_se_accede_desde_numeros_no_solo_desde_archivos(monkeypatch, falta):
    publicacion = _publicacion(falta=falta)
    serie, html = _numeros(monkeypatch, [publicacion])
    assert "En tu biblioteca" in html
    assert "Sin número · Las guerras silenciosas" in html
    assert f'href="/ui/series/{serie.id}/numero/{publicacion.issue_id}"' in html
    assert "Ver tebeo" in html
    assert "#1" not in html and "#(sin número)" not in html
    # No se elige otro archivo ni se elude el selector de lectura de la ficha.
    assert "/ui/leer/" not in html


def test_varios_sin_numero_conservan_enlaces_distintos_junto_a_los_numerados(monkeypatch):
    publicaciones = [_publicacion("Especial A"), _publicacion("Especial B")]
    serie, html = _numeros(monkeypatch, publicaciones, numerada=True)
    assert "#1" in html
    assert f'href="/ui/series/{serie.id}/numero/numero-1"' in html
    for publicacion in publicaciones:
        assert publicacion.titulo in html
        assert f'href="/ui/series/{serie.id}/numero/{publicacion.issue_id}"' in html
    assert html.count("<h2>En tu biblioteca</h2>") == 1


@pytest.mark.parametrize("titulo", ["", "<script>alert(1)</script>"])
def test_sin_numero_sin_titulo_y_titulo_no_confiable(monkeypatch, titulo):
    _, html = _numeros(monkeypatch, [_publicacion(titulo)])
    assert "Sin número" in html and "Ver tebeo" in html
    assert "<script>" not in html
    if titulo:
        assert "&lt;script&gt;" in html
    else:
        assert "Sin número ·" not in html


def test_lista_larga_sin_numero_tiene_desplegable_y_no_pierde_publicaciones(monkeypatch):
    publicaciones = [_publicacion(f"Especial {n}") for n in range(31)]
    serie, html = _numeros(monkeypatch, publicaciones)
    assert "Ver 1 publicación sin número más" in html
    for publicacion in publicaciones:
        assert f'href="/ui/series/{serie.id}/numero/{publicacion.issue_id}"' in html
    assert html.index("<details") < html.index(
        f'href="/ui/series/{serie.id}/numero/{publicaciones[-1].issue_id}"',
    )


def test_sin_publicaciones_no_inventa_un_tebeo(monkeypatch):
    _, html = _numeros(monkeypatch, [])
    assert "Ver tebeo" not in html
    assert "En tu biblioteca" not in html


@pytest.mark.parametrize("legible", [False, True])
def test_enlace_del_sin_numero_lleva_a_ficha_con_lectura_segun_disponibilidad(monkeypatch, legible):
    publicacion = _publicacion()
    serie, html = _numeros(monkeypatch, [publicacion])
    enlace = re.search(r'href="([^"]+)"', html)
    assert enlace is not None
    archivo_id = uuid4()
    issue = _issue(
        id=UUID(publicacion.issue_id), series_id=serie.id, issue_number=None,
        title=publicacion.titulo, files=[SimpleNamespace(
            id=archivo_id, file_name="Las guerras silenciosas.cbz",
            file_format=FileFormat.CBZ, file_size_bytes=1, is_missing=not legible,
        )],
    )
    lector = AsyncMock(return_value=SimpleNamespace(id=str(archivo_id)) if legible else None)
    monkeypatch.setattr(web_series, "archivo_por_defecto", lector)
    sesion = FakeSession([
        FakeExecResult([issue]), FakeExecResult([serie]), FakeExecResult([]),
    ])
    with use_fake_session(sesion) as client:
        respuesta = client.get(enlace.group(1))
    assert respuesta.status_code == 200
    assert "Sin número" in respuesta.text
    assert (f'href="/ui/leer/{archivo_id}"' in respuesta.text) is legible
    lector.assert_awaited_once_with(sesion, issue.id)


def _tomo(numero: str, *, formato="trade_paperback"):
    return NumeroConArchivos(
        issue_id=str(uuid4()), numero=numero, titulo="",
        archivos=[ArchivoDeNumero(
            id=str(uuid4()), nombre=f"Tomo {numero}.cbz", formato="cbz",
            falta_en_disco=False, bloqueo=None, formato_publicacion=formato,
        )],
    )


def test_tomos_y_variantes_sin_hueco_se_muestran_en_la_ficha(monkeypatch):
    """Un TPB #1 o un 2a no son grapas, pero no pueden quedar sin acceso visible."""
    publicaciones = [_tomo("1"), _tomo("2"), _tomo("2a")]
    serie, html = _numeros(monkeypatch, publicaciones)
    assert "Tomos y especiales" in html
    assert "Tomo en rústica" in html
    assert "#1" in html and "#2a" in html
    for p in publicaciones:
        assert f'href="/ui/series/{serie.id}/numero/{p.issue_id}"' in html
    assert "no alteran tus huecos" in html
