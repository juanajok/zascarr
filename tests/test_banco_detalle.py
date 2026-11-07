"""#135 + BL-FU2: el banco pide detalle y contrasta, sin red."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from scripts.medicion import banco_cobertura as banco
from zascarr.models import MetadataSource
from zascarr.services.detalle_edicion import (
    DetalleEdicion,
    EstadoFuente,
    ResultadoDetalle,
)

AHORA = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _fuente_disponible(monkeypatch):
    monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))


def _caso(caso_id, *, editorial="Planeta DeAgostini", anio=1992, acreditada=True):
    return {
        "caso_id": caso_id, "consulta": "Dragon Ball",
        "identidad_acreditada": acreditada,
        "etiqueta_editorial": {
            "obra": "Dragon Ball", "serie": "Dragon Ball", "editorial": editorial,
            "anio": anio, "numero": None, "formato": "single_issue",
            "pais": "ES", "idioma": "es", "campos": {},
        },
    }


def _corpus():
    return {
        "version": "v1",
        "casos": [
            _caso("C1"), _caso("C2"), _caso("C3"),
            _caso("C4", acreditada=False),
        ],
    }


def _plan(corpus):
    return [{"caso": c, "fuente": "tebeosfera", "unidad": "serie",
             "capacidad": "busqueda", "metodo": "search_series"}
            for c in corpus["casos"]]


def _auth():
    return {
        "id": "prueba", "ambito": ["tebeosfera"], "presupuesto_peticiones": 80,
        "max_por_fuente": 20,
        "desde": (AHORA - timedelta(days=1)).isoformat(),
        "hasta": (AHORA + timedelta(days=1)).isoformat(),
        "concede": "PO", "condiciones": "", "sha_corpus": "sha-corpus",
    }


class _Candidato:
    def __init__(self, slug):
        self.slug = slug
        self.title = "Dragon Ball"
        self.start_year = 1992


class _BusquedaFalsa:
    def __init__(self):
        self.search_series = AsyncMock(return_value=[_Candidato("dragon_ball")])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


class _DetalleFalso:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    async def detalle_de(self, resultado, *, unidad, numero_esperado=None):
        self.llamadas.append((resultado, unidad, numero_esperado))
        return self.respuestas.pop(0)


def _detalle(*, editorial="Planeta DeAgostini", anio=1992, peticiones=1):
    return DetalleEdicion(
        fuente=MetadataSource.TEBEOSFERA, external_id="dragon_ball",
        metodo="get_collection", editorial=editorial, sello=None, anio=anio,
        pais="ES", idioma=None, peticiones=peticiones,
        campos_ausentes=frozenset(
            {"sello", "anio_fin", "numeracion_inicio", "numeracion_fin",
             "numeracion_texto", "numero_publicacion", "paginas", "formato", "idioma"}
            if peticiones == 1 else ()),
    )


def _ok(detalle):
    return ResultadoDetalle(
        EstadoFuente("tebeosfera", "detalle", "ok"), detalle)


def _ejecutar(respuestas, *, max_peticiones=10, plan=None):
    corpus = _corpus()
    servicio = _DetalleFalso(respuestas)
    return asyncio.run(banco.ejecutar_real(
        plan or _plan(corpus), corpus, _auth(), max_peticiones=max_peticiones,
        max_por_fuente=20, salida=Path("/tmp/x"), corpus_sha="sha-corpus",
        fuentes=["tebeosfera"], cliente_factory=lambda _f: _BusquedaFalsa(),
        detalle_service_factory=lambda: servicio,
        sha_ejecutor="abc", aplicar_ajustes=False, con_detalle=True))


class TestContrasteDelBanco:
    def test_llena_los_cuatro_contrastes_y_no_publica_urls(self):
        filas = _ejecutar([
            _ok(_detalle()),
            _ok(_detalle(editorial=None)),          # campo requerido ausente
            _ok(_detalle(anio=2006)),               # incorrecto
            _ok(_detalle()),                        # no acreditada
        ])
        assert [f["contraste"] for f in filas] == [
            "coincidencia_verificada", "ambiguo", "incorrecto", "sin_veredicto"]
        assert [f["resultado_editorial"] for f in filas] == [
            "coincidencia_verificada", "ambiguo", "incorrecto", None]
        assert all(f["estado_detalle"] == "ok" for f in filas)
        assert all(f["detalle"] is not None for f in filas)
        assert all("http" not in str(f["detalle"]).lower() for f in filas)
        assert all(f["peticiones"] == 2 for f in filas)  # búsqueda + detalle
        metricas = banco.calcular_metricas(filas, _corpus())["por_fuente_unidad"]
        grupo = metricas["tebeosfera__serie"]
        assert grupo["coincidencias_verificadas"] == 1
        assert grupo["ambiguos"] == 1 and grupo["incorrectos"] == 1
        assert grupo["evaluables"] == 3 and grupo["no_acreditadas"] == 1

    def test_sin_presupuesto_conserva_la_busqueda_y_marca_el_detalle(self):
        corpus = _corpus()
        filas = _ejecutar([_ok(_detalle())], max_peticiones=1,
                          plan=_plan(corpus)[:1])
        assert len(filas) == 1
        fila = filas[0]
        assert fila["estado_tecnico"] == "ok"            # la búsqueda se conserva
        assert fila["candidatos"]
        assert fila["estado_detalle"] == "no_ejecutado"
        assert fila["motivo_detalle"] == "presupuesto_agotado"
        assert fila["contraste"] is None and fila["detalle"] is None
        assert fila["peticiones"] == 1

    def test_un_fallo_de_detalle_no_convierte_la_fila_en_ausencia(self):
        fallo = ResultadoDetalle(
            EstadoFuente("tebeosfera", "detalle", "limite_de_cortesia"),
            None, "Hay que esperar por cortesía.")
        corpus = _corpus()
        filas = _ejecutar([fallo], plan=_plan(corpus)[:1])
        fila = filas[0]
        assert fila["estado_tecnico"] == "ok"
        assert fila["estado_detalle"] == "limite_de_cortesia"
        assert fila["contraste"] is None
        grupo = banco.calcular_metricas(filas, _corpus())["por_fuente_unidad"]["tebeosfera__serie"]
        assert grupo["ausencias"] == 0
        assert grupo["respuestas_ok"] == 1

    def test_el_detalle_usa_el_primer_candidato_y_respeta_el_contrato(self):
        detalle = _DetalleFalso([_ok(_detalle())])
        corpus = _corpus()
        filas = asyncio.run(banco.ejecutar_real(
            _plan(corpus)[:1], corpus, _auth(), max_peticiones=10, max_por_fuente=20,
            salida=Path("/tmp/x"), corpus_sha="sha-corpus", fuentes=["tebeosfera"],
            cliente_factory=lambda _f: _BusquedaFalsa(),
            detalle_service_factory=lambda: detalle, sha_ejecutor="abc",
            aplicar_ajustes=False, con_detalle=True))
        assert len(detalle.llamadas) == 1
        resultado, unidad, numero_esperado = detalle.llamadas[0]
        assert resultado.external_id == "dragon_ball" and unidad == "serie"
        assert numero_esperado is None
        assert filas[0]["detalle"]["editorial"] == "Planeta DeAgostini"


def test_detalle_en_seco_es_error_claro(tmp_path):
    rc = banco.main(["--seco", "--detalle", "--salida", str(tmp_path)])
    assert rc == 2


def test_el_banco_pasa_el_numero_esperado_de_la_etiqueta(monkeypatch):
    monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
    corpus = _corpus()
    corpus["casos"][0]["etiqueta_editorial"]["numero"] = 15
    detalle = _DetalleFalso([_ok(_detalle())])
    filas = asyncio.run(banco.ejecutar_real(
        _plan(corpus)[:1], corpus, _auth(), max_peticiones=10, max_por_fuente=20,
        salida=Path("/tmp/x"), corpus_sha="sha-corpus", fuentes=["tebeosfera"],
        cliente_factory=lambda _f: _BusquedaFalsa(),
        detalle_service_factory=lambda: detalle, sha_ejecutor="abc",
        aplicar_ajustes=False, con_detalle=True))
    _, _, numero_esperado = detalle.llamadas[0]
    assert numero_esperado == 15
    # búsqueda (1) + resolución colección+número (2)
    assert filas[0]["peticiones"] == 3
