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
from sqlalchemy import and_
from sqlalchemy.dialects import postgresql

from tests.test_web_dashboard import FakeResult, FakeSession
from zascarr.services import inicio
from zascarr.services.library_adopter import EstadoAdopcion
from zascarr.services.orchestrator import hay_fuente_de_busqueda
from zascarr.services.primeros_pasos import ClavePaso, EstadoPaso
from zascarr.services.review import ReviewService


class _Fila:
    """Resultado con `.first()` / `.scalar_one()` / `.scalar_one_or_none()` para el glue."""

    def __init__(self, *, first=None, uno=None, fila=None):
        self._first, self._uno, self._fila = first, uno, fila

    def first(self):
        return self._first

    def one(self):
        return self._fila

    def scalar_one(self):
        return self._uno

    def scalar_one_or_none(self):
        return self._uno


def _cola(*, archivos=0, sin_clasificar=0, seguidas=0, informe=None, legal=None, desglose=None,
          registro=None):
    """Orden de consultas de `cargar_inicio` (la adopción se sustituye aparte).

    `desglose` = (total, clasificados, por revisar presentes, descartados, por revisar ausentes);
    por defecto, lo registrado sin clasificar es «por revisar». `registro`: el último registro."""
    if desglose is None:
        desglose = (archivos, archivos - sin_clasificar, sin_clasificar, 0, 0)
    return [
        FakeResult(scalar=0), FakeResult(scalar=0), FakeResult(scalar=archivos),   # resumen
        FakeResult(rows=[]), FakeResult(rows=[]), FakeResult(scalars=[]),
        _Fila(fila=desglose),         # desglose de los registrados
        _Fila(uno=seguidas),          # count_active
        _Fila(first=informe),         # último informe de duplicados
        _Fila(first=registro),        # último registro de la biblioteca (copias descartadas)
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

    async def test_dice_cuanto_hace_que_se_miro_el_disco(self, adopcion, sin_fuente):
        """Fecha muy anterior a cualquier ejecución de la suite: siempre es vieja."""
        adopcion(EstadoAdopcion.HECHA)
        fecha = datetime(2020, 1, 1, tzinfo=UTC)
        v = await inicio.cargar_inicio(FakeSession(_cola(informe=(fecha, 10, "5"))))
        assert v.informe_hace == "hace más de un año"
        assert v.informe_antiguo is True

    async def test_sin_informe_no_hay_antiguedad(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        v = await inicio.cargar_inicio(FakeSession(_cola()))
        assert (v.informe_hace, v.informe_antiguo) == (None, False)

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
        sesion = FakeSession(_cola()[:-4] + _cola()[-3:])   # sin la consulta de deseados
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

    async def test_el_desglose_da_el_paso_2_y_lo_registrado(self, adopcion, sin_fuente):
        """Caso real (2026-10-20): 1325 registrados y «Revisa 1322». Los por revisar cuyo archivo
        ya no está donde se registró los lista «Por revisar» (y el paso 2); no son registrados."""
        adopcion(EstadoAdopcion.HECHA)
        v = await inicio.cargar_inicio(FakeSession(_cola(desglose=(1325, 17, 1308, 0, 14))))
        assert v.archivos_sin_clasificar == 1322 == v.registrados.por_revisar
        assert v.registrados.total == 1325 and v.registrados.sin_numero == 0
        paso = next(p for p in v.pasos.pasos if p.clave is ClavePaso.REVISAR)
        assert paso.titulo == "Revisa 1322 tebeos que no hemos sabido clasificar"

    async def test_copias_descartadas_salen_del_ultimo_registro(self, adopcion, sin_fuente):
        adopcion(EstadoAdopcion.HECHA)
        con = await inicio.cargar_inicio(FakeSession(_cola(registro=(217,))))
        sin = await inicio.cargar_inicio(FakeSession(_cola()))
        assert (con.copias_descartadas, sin.copias_descartadas) == (217, 0)

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


class TestDesglose:
    """Las partes de lo registrado suman el total: lo que el Inicio promete con «Tienes N: …»."""

    def test_las_partes_suman_el_total(self):
        d = inicio.Desglose(total=100, clasificados=20, por_revisar_presentes=70, descartados=4,
                            por_revisar_ausentes=9)
        assert d.sin_numero == 6
        assert sum(n for n, _, _ in d.partes) == d.total
        assert d.por_revisar == 79                      # la lista entera, también las ausentes

    def test_solo_salen_las_partes_no_vacias_y_enlazan_a_su_lista(self):
        d = inicio.Desglose(total=1325, clasificados=17, por_revisar_presentes=1308)
        assert d.partes == ((17, "clasificados", "/ui/biblioteca"),
                            (1308, "por revisar", "/ui/pendientes"))

    def test_singular(self):
        d = inicio.Desglose(total=2, clasificados=1, descartados=1)
        assert [t for _, t, _ in d.partes] == ["clasificado", "descartado"]

    @pytest.mark.asyncio
    async def test_una_sola_consulta_con_el_filtro_de_por_revisar(self):
        """Si fueran varias consultas, un ciclo del importador entre medias descuadraría la suma;
        y «por revisar» tiene que ser el filtro de la lista, el mismo que cuenta el menú."""
        compilar = lambda c: str(c.compile(dialect=postgresql.dialect(),  # noqa: E731
                                           compile_kwargs={"literal_binds": True}))

        class _Captura(FakeSession):
            def __init__(self, cola):
                super().__init__(cola)
                self.sql: list[str] = []

            async def execute(self, stmt):
                self.sql.append(compilar(stmt))
                return await super().execute(stmt)

        sesion = _Captura([_Fila(fila=(0, 0, 0, 0, 0))])
        assert await inicio.desglose_registrados(sesion) == inicio.Desglose()
        assert len(sesion.sql) == 1
        assert compilar(and_(*ReviewService._condiciones_pendientes())) in sesion.sql[0]
        assert "files.is_missing IS false" in sesion.sql[0]
