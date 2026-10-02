"""
tests/test_inicio.py — `services/inicio.py` (V4): cada dato del Inicio viene de su única fuente.

La función pura de pasos ya se prueba en test_primeros_pasos.py; aquí se comprueba el
pegamento: que el estado observado se traduce bien (y solo lee).
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_web_dashboard import FakeResult, FakeSession
from zascarr.services import inicio
from zascarr.services.library_adopter import EstadoAdopcion
from zascarr.services.orchestrator import hay_fuente_de_busqueda
from zascarr.services.primeros_pasos import ClavePaso, EstadoPaso


class _Fila:
    """Resultado con `.first()` / `.scalar_one()` / `.scalar_one_or_none()` para el glue."""

    def __init__(self, *, first=None, uno=None):
        self._first, self._uno = first, uno

    def first(self):
        return self._first

    def scalar_one(self):
        return self._uno

    def scalar_one_or_none(self):
        return self._uno


def _cola(*, archivos=0, sin_clasificar=0, seguidas=0, informe=None, legal=None):
    """Orden de consultas de `cargar_inicio` (la adopción se sustituye aparte)."""
    return [
        FakeResult(scalar=0), FakeResult(scalar=0), FakeResult(scalar=archivos),   # resumen
        FakeResult(rows=[]), FakeResult(rows=[]), FakeResult(scalars=[]),
        _Fila(uno=sin_clasificar),    # count_pending
        _Fila(uno=seguidas),          # count_active
        _Fila(first=informe),         # último informe de duplicados
        _Fila(uno=legal),             # aviso legal
    ]


@pytest.fixture
def adopcion(monkeypatch):
    def fijar(estado: EstadoAdopcion):
        monkeypatch.setattr(inicio.LibraryAdopter, "estado", AsyncMock(return_value=estado))
    return fijar


@pytest.fixture
def sin_fuente(monkeypatch):
    monkeypatch.setattr(inicio, "get_settings", lambda: SimpleNamespace(
        prowlarr_enabled=False, forum_enabled=False, forum_username="", forum_url=""))


@pytest.mark.asyncio
class TestCargarInicio:

    async def test_instalacion_nueva(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.SIN_TEBEOS)
        v = await inicio.cargar_inicio(FakeSession(_cola()))
        assert v.informe is None and v.archivos_sin_clasificar == 0
        assert v.pasos.hechos == 0 and not v.pasos.completo

    async def test_los_pendientes_son_el_recuento_real_no_el_tope_de_50(self, adopcion,
                                                                        sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        v = await inicio.cargar_inicio(FakeSession(_cola(archivos=1542, sin_clasificar=137)))
        paso = next(p for p in v.pasos.pasos if p.clave is ClavePaso.REVISAR)
        assert v.archivos_sin_clasificar == 137
        assert paso.titulo == "Revisa 137 tebeos que no hemos sabido clasificar"
        assert paso.estado is EstadoPaso.SIGUIENTE

    async def test_el_informe_aporta_fecha_y_cifras_propias(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.PENDIENTE)
        fecha = datetime(2026, 10, 3, 9, 30, tzinfo=UTC)
        v = await inicio.cargar_inicio(FakeSession(_cola(informe=(fecha, 1542, "432"))))
        assert (v.informe.fecha, v.informe.archivos_leidos, v.informe.archivos_comparados) == (
            fecha, 1542, 432)
        biblioteca = next(p for p in v.pasos.pasos if p.clave is ClavePaso.BIBLIOTECA)
        assert biblioteca.estado is EstadoPaso.SIGUIENTE      # el informe no registra nada

    async def test_informe_antiguo_sin_files_hashed_no_inventa_comparados(self, adopcion,
                                                                          sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        fecha = datetime(2026, 9, 1, tzinfo=UTC)
        v = await inicio.cargar_inicio(FakeSession(_cola(informe=(fecha, None, None))))
        assert (v.informe.archivos_leidos, v.informe.archivos_comparados) == (0, 0)

    async def test_las_series_seguidas_son_las_de_deseados(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        v = await inicio.cargar_inicio(FakeSession(_cola(seguidas=4)))
        assert next(p for p in v.pasos.pasos if p.clave is ClavePaso.SERIES).titulo == (
            "Sigues 4 series")

    async def test_sigues_n_series_usa_series_distintas_no_peticiones(self, adopcion, sin_fuente,
                                                                      monkeypatch):
        """Cinco peticiones de tres series dijeron «Sigues 5 series» (revisión de la PR #70)."""
        adopcion(EstadoAdopcion.HECHA)
        monkeypatch.setattr(inicio.WishlistService, "count_active_series",
                            AsyncMock(return_value=3))
        monkeypatch.setattr(inicio.WishlistService, "count_active",
                            AsyncMock(side_effect=AssertionError("cuenta peticiones")))
        sesion = FakeSession(_cola()[:-3] + _cola()[-2:])   # sin la consulta de deseados
        v = await inicio.cargar_inicio(sesion)
        assert next(p for p in v.pasos.pasos if p.clave is ClavePaso.SERIES).titulo == (
            "Sigues 3 series")

    async def test_descargas_necesita_aviso_legal_aceptado(self, adopcion, monkeypatch):
        adopcion(EstadoAdopcion.HECHA)
        monkeypatch.setattr(inicio, "get_settings", lambda: SimpleNamespace(
            prowlarr_enabled=True, forum_enabled=False, forum_username="", forum_url=""))
        sin = await inicio.cargar_inicio(FakeSession(_cola(legal=None)))
        con = await inicio.cargar_inicio(FakeSession(_cola(legal=object())))
        d = lambda v: next(p for p in v.pasos.pasos if p.clave is ClavePaso.DESCARGAS)  # noqa: E731
        assert d(sin).estado is EstadoPaso.OPCIONAL
        assert d(con).estado is EstadoPaso.HECHO

    async def test_solo_lee(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        sesion = FakeSession(_cola())
        sesion.commit = None
        sesion.flush = None
        await inicio.cargar_inicio(sesion)


class TestFuenteDeBusqueda:
    """La definición de «fuente activa» es la de D9 (orquestador), no una nueva."""

    @staticmethod
    def _s(**kw):
        base = dict(prowlarr_enabled=False, forum_enabled=False, forum_username="", forum_url="")
        return SimpleNamespace(**{**base, **kw})

    def test_ninguna(self):
        assert hay_fuente_de_busqueda(self._s()) is False

    def test_prowlarr(self):
        assert hay_fuente_de_busqueda(self._s(prowlarr_enabled=True)) is True

    def test_foro_solo_si_esta_configurado_del_todo(self):
        assert hay_fuente_de_busqueda(self._s(forum_enabled=True)) is False
        assert hay_fuente_de_busqueda(
            self._s(forum_enabled=True, forum_username="u", forum_url="")) is False
        assert hay_fuente_de_busqueda(
            self._s(forum_enabled=True, forum_username="u", forum_url="https://x")) is True
