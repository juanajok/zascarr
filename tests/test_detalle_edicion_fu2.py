"""BL-FU2 PR-1 (#465): detalle de edición y ficha de colección de Tebeosfera.

Sin red: el parser usa el fixture real recortado y `get_collection` se prueba con
`pedir_con_cortesia` parcheado. No se escribe en Series/Issue (no hay BD).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from zascarr.models import IssueFormat, MetadataSource
from zascarr.services import tebeosfera as modulo_tebeosfera
from zascarr.services.detalle_edicion import (
    DetalleEdicion,
    ResultadoContraste,
    contrastar,
    detalle_desde_coleccion,
    mapa_formato,
)
from zascarr.services.tebeosfera import TebeosferaClient, _parse_collection

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = (RAIZ / "docs" / "design" / "fixtures-cobertura"
           / "tebeosfera_coleccion_dragon_ball_1992.html")
SLUG = "bola_de_drac_1992_planeta-deagostini_-col._superior-"


def _detalle_real() -> DetalleEdicion:
    return detalle_desde_coleccion(_parse_collection(
        FIXTURE.read_text(encoding="utf-8"), SLUG))


class TestParserTebeosfera:
    def test_extrae_los_campos_de_la_ficha_real(self):
        coleccion = _parse_collection(FIXTURE.read_text(encoding="utf-8"), SLUG)
        assert coleccion is not None
        assert coleccion.editorial == "Grupo Planeta"
        assert coleccion.sello == "Planeta DeAgostini"
        assert coleccion.anio == 1992 and coleccion.anio_fin == 1995
        assert coleccion.numeracion_inicio == 1 and coleccion.numeracion_fin == 153
        assert coleccion.numeracion_texto == "1 a 153"
        assert coleccion.formato_fuente == "CUADERNO / GRAPA"
        assert coleccion.pais == "ES"
        assert coleccion.idioma is None
        assert coleccion.numero_publicacion is None
        assert coleccion.paginas is None            # la ficha da 36/32/40/48/56
        assert coleccion.peticiones == 1
        assert coleccion.url_ficha.endswith(f"/colecciones/{SLUG}.html")

    def test_html_sin_ficha_o_roto_devuelve_none(self):
        assert _parse_collection("", SLUG) is None
        assert _parse_collection("<html><body>sin ficha</body></html>", SLUG) is None
        assert _parse_collection("<div id='div_ficha'<<<", SLUG) is None

    def test_detalle_deriva_los_campos_ausentes(self):
        detalle = _detalle_real()
        assert detalle.fuente is MetadataSource.TEBEOSFERA
        assert detalle.metodo == "get_collection"
        assert detalle.formato is IssueFormat.SINGLE_ISSUE
        assert detalle.campos_ausentes == frozenset({
            "numero_publicacion", "paginas", "idioma"})
        assert detalle.peticiones == 1

    def test_formato_desconocido_es_ausente_no_se_adivina(self):
        assert mapa_formato("COSIDO RARO") is None
        assert mapa_formato("cartoné") is IssueFormat.HARDCOVER
        assert mapa_formato("album") is IssueFormat.ALBUM
        assert mapa_formato("single_issue") is IssueFormat.SINGLE_ISSUE


class TestContrastar:
    def _etiqueta(self, **extra):
        base = {
            "identidad_acreditada": True, "editorial": "Planeta DeAgostini",
            "anio": 1992, "numero": None, "pais": "ES", "idioma": "es",
            "formato": "single_issue", "campos": {},
        }
        base.update(extra)
        return base

    def test_coincidencia_verificada_por_editorial_y_anio(self):
        r = contrastar(_detalle_real(), self._etiqueta(), unidad="serie")
        assert isinstance(r, ResultadoContraste)
        assert r.resultado == "coincidencia_verificada"
        assert r.campos_requeridos == ("editorial", "anio")
        assert "idioma" in r.campos_ausentes
        assert "numero_publicacion" in r.campos_ausentes

    def test_anio_distinto_es_incorrecto(self):
        r = contrastar(_detalle_real(), self._etiqueta(anio=2006), unidad="serie")
        assert r.resultado == "incorrecto" and "anio_discrepante" in r.motivos

    def test_requerido_ausente_es_ambiguo(self):
        detalle = replace(_detalle_real(), anio=None)
        r = contrastar(detalle, self._etiqueta(), unidad="serie")
        assert r.resultado == "ambiguo"
        assert "anio" in r.campos_requeridos
        assert "anio_ausente" in r.motivos

    def test_numero_ausente_con_unidad_numero_es_ambiguo_y_no_usa_numeracion(self):
        detalle = _detalle_real()
        r = contrastar(detalle, self._etiqueta(numero=15), unidad="numero")
        assert r.resultado == "ambiguo"
        assert "numero_publicacion" in r.campos_requeridos
        assert "numero_publicacion_ausente" in r.motivos

    def test_formato_distinto_es_ambiguo_no_incorrecto(self):
        detalle = replace(_detalle_real(), formato=IssueFormat.ALBUM)
        r = contrastar(detalle, self._etiqueta(formato="single_issue"), unidad="formato")
        assert r.resultado == "ambiguo" and "formato_discrepante" in r.motivos

    def test_pais_distinto_es_incorrecto(self):
        r = contrastar(_detalle_real(), self._etiqueta(pais="FR"), unidad="serie")
        assert r.resultado == "incorrecto" and "pais_discrepante" in r.motivos

    def test_etiqueta_no_acreditada_no_tiene_veredicto(self):
        r = contrastar(_detalle_real(), self._etiqueta(identidad_acreditada=False))
        assert r.resultado is None and "etiqueta_no_acreditada" in r.motivos

    def test_sin_detalle_no_tiene_veredicto(self):
        r = contrastar(None, self._etiqueta(), unidad="serie")
        assert r.resultado is None and "detalle_ausente" in r.motivos

    def test_editorial_aproximada_es_ambiguo(self):
        r = contrastar(_detalle_real(), self._etiqueta(editorial="Planeta"), unidad="serie")
        assert r.resultado == "ambiguo"
        assert any(m.startswith("editorial_aproximada") for m in r.motivos)


class TestGetCollection:
    @pytest.mark.asyncio
    async def test_usa_pedir_con_cortesia_y_una_sola_peticion(self, monkeypatch):
        cliente = TebeosferaClient()
        respuesta = httpx.Response(200, text=FIXTURE.read_text(encoding="utf-8"),
                                   request=httpx.Request("GET", "https://www.tebeosfera.com/x"))
        llamada = AsyncMock(return_value=respuesta)
        monkeypatch.setattr(modulo_tebeosfera, "pedir_con_cortesia", llamada)

        async with cliente:
            cliente._client.get = AsyncMock(side_effect=AssertionError(
                "get_collection no puede llamar a httpx directamente"))
            coleccion = await cliente.get_collection(SLUG)

        assert coleccion is not None and coleccion.editorial == "Grupo Planeta"
        assert llamada.await_count == 1
        assert llamada.await_args.args[:3] == (
            cliente._client, "GET",
            f"https://www.tebeosfera.com/colecciones/{SLUG}.html")

    @pytest.mark.asyncio
    async def test_404_o_fallo_devuelve_none(self, monkeypatch):
        from zascarr.utils.peticiones import RespuestaNoTransitoria
        cliente = TebeosferaClient()
        async def falla(*_a, **_k):
            raise RespuestaNoTransitoria(404)
        monkeypatch.setattr(modulo_tebeosfera, "pedir_con_cortesia", falla)
        async with cliente:
            assert await cliente.get_collection(SLUG) is None
