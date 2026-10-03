"""
tests/test_resumen.py — `services/resumen.py` (V4): las cifras del Inicio, de un único servicio.

V4a movió las consultas sin cambiar cifras; V4b corrige lo que afirmaban de más: la completitud
solo cuenta series con recuento de grapas acreditado y, sin ellas, NO hay cifra (no «0 %»).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.test_web_dashboard import CapturingSession, FakeResult, FakeSession
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.resumen import Completitud, resumen_biblioteca


def _cola(*, series=0, con_archivos=0, archivos=0, totales=(), poseidos=(), ultimas=()):
    """Las 6 consultas, en el orden que fija el servicio."""
    return [
        FakeResult(scalar=series), FakeResult(scalar=con_archivos), FakeResult(scalar=archivos),
        FakeResult(rows=list(totales)), FakeResult(rows=list(poseidos)),
        FakeResult(scalars=list(ultimas)),
    ]


def _serie(titulo="Batman", fuente=MetadataSource.COMIC_VINE.value) -> Series:
    return Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN, start_year=2011,
                  metadata_source=fuente)


def _tengo(serie_id, *numeros):
    return [(serie_id, str(n), "single_issue", True) for n in numeros]


@pytest.mark.asyncio
class TestResumenBiblioteca:

    async def test_vacio_todo_a_cero_y_sin_completitud(self):
        r = await resumen_biblioteca(FakeSession(_cola()))
        assert (r.total_series, r.series_con_archivos, r.archivos_registrados,
                r.huecos_pendientes, r.series_con_recuento) == (0, 0, 0, 0, 0)
        assert r.completitud is None
        assert r.ultimas_series == ()

    async def test_cifras_con_datos(self):
        s = _serie()
        r = await resumen_biblioteca(FakeSession(_cola(
            series=3, con_archivos=2, archivos=57,
            totales=[(s.id, 40, "comic_vine")], poseidos=_tengo(s.id, 1, 2), ultimas=[s],
        )))
        assert (r.total_series, r.series_con_archivos, r.archivos_registrados) == (3, 2, 57)
        assert r.huecos_pendientes == 38          # 40 esperados, 2 poseídos
        assert r.completitud == Completitud(tienes=2, de=40, series=1)
        assert r.completitud.porcentaje == 5
        assert r.series_con_recuento == 1 and r.series_sin_recuento == 2
        assert r.ultimas_series == (s,)

    async def test_completitud_solo_cuenta_series_con_recuento_de_grapas(self):
        """Antes: números de TODAS las series entre la suma del catálogo de TODAS las fuentes.
        Una serie de AniList (capítulos) no puede inflar ni diluir el porcentaje."""
        a, b = _serie("A"), _serie("B", fuente=MetadataSource.ANILIST.value)
        r = await resumen_biblioteca(FakeSession(_cola(
            series=2,
            totales=[(a.id, 10, "comic_vine"), (b.id, 100, "anilist")],
            poseidos=_tengo(a.id, 1, 2, 3, 4, 5) + _tengo(b.id, *range(1, 51)),
        )))
        assert r.completitud == Completitud(tienes=5, de=10, series=1)
        assert r.completitud.porcentaje == 50
        assert r.huecos_pendientes == 5
        assert r.series_sin_recuento == 1

    async def test_sin_series_con_recuento_no_hay_completitud_aunque_haya_total_issues(self):
        """Tener algún `total_issues` no acredita completitud: si no es de grapas, no se calcula."""
        s = _serie("Manga", fuente=MetadataSource.ANILIST.value)
        r = await resumen_biblioteca(FakeSession(_cola(
            series=1, totales=[(s.id, 120, "anilist")], poseidos=_tengo(s.id, 1, 2, 3))))
        assert r.completitud is None
        assert r.huecos_pendientes == 0 and r.series_con_recuento == 0
        assert r.series_sin_recuento == 1      # «0 huecos» NO es «completa»

    async def test_recuento_cero_no_cuenta_como_calculable(self):
        s = _serie()
        r = await resumen_biblioteca(FakeSession(_cola(
            series=1, totales=[(s.id, 0, "comic_vine")])))
        assert r.completitud is None and r.series_con_recuento == 0

    async def test_serie_con_recuento_y_cero_archivos_cuenta_todos_los_huecos(self):
        s = _serie()
        r = await resumen_biblioteca(
            FakeSession(_cola(series=1, totales=[(s.id, 12, "comic_vine")])))
        assert r.huecos_pendientes == 12
        assert r.completitud == Completitud(tienes=0, de=12, series=1)
        assert r.completitud.porcentaje == 0     # aquí SÍ es un 0 % real: hay catálogo

    async def test_las_consultas_de_archivos_filtran_is_missing(self):
        """B7: un fichero marcado como desaparecido no cuenta como «lo tienes»."""
        sesion = CapturingSession(_cola())
        await resumen_biblioteca(sesion)
        assert len(sesion.statements) == 6
        for i in (1, 2, 5):
            assert "is_missing" in sesion.statements[i]

    async def test_solo_lee_no_hace_commit(self):
        sesion = FakeSession(_cola())
        sesion.commit = None   # cualquier intento de commit reventaría
        await resumen_biblioteca(sesion)
