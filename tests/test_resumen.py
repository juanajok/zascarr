"""
tests/test_resumen.py — `services/resumen.py` (V4): las cifras del Inicio, de un único servicio.

La extracción desde `web/dashboard.py` NO cambia ninguna cifra; `test_web_dashboard.py` sigue
fijando el contrato HTTP con la misma cola de consultas. Aquí se prueba el servicio solo.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.test_web_dashboard import CapturingSession, FakeResult, FakeSession
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.resumen import ResumenBiblioteca, resumen_biblioteca


def _cola(*, series=0, con_archivos=0, catalogo=0, importados=0, totales=(), poseidos=(),
          ultimas=()):
    """Las 7 consultas, en el orden que fija el servicio."""
    return [
        FakeResult(scalar=series), FakeResult(scalar=con_archivos),
        FakeResult(scalar=catalogo), FakeResult(scalar=importados),
        FakeResult(rows=list(totales)), FakeResult(rows=list(poseidos)),
        FakeResult(scalars=list(ultimas)),
    ]


def _serie(titulo="Batman", fuente=MetadataSource.COMIC_VINE.value) -> Series:
    return Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN, start_year=2011,
                  metadata_source=fuente)


@pytest.mark.asyncio
class TestResumenBiblioteca:

    async def test_vacio_todo_a_cero(self):
        r = await resumen_biblioteca(FakeSession(_cola()))
        assert (r.total_series, r.series_con_archivos, r.total_issues, r.issues_importados,
                r.huecos_pendientes) == (0, 0, 0, 0, 0)
        assert r.ultimas_series == ()

    async def test_cifras_con_datos(self):
        s = _serie()
        r = await resumen_biblioteca(FakeSession(_cola(
            series=3, con_archivos=2, catalogo=40, importados=38,
            totales=[(s.id, 40, "comic_vine")],
            poseidos=[(s.id, "1", "single_issue", True), (s.id, "2", "single_issue", True)],
            ultimas=[s],
        )))
        assert (r.total_series, r.series_con_archivos) == (3, 2)
        assert (r.total_issues, r.issues_importados) == (40, 38)
        assert r.huecos_pendientes == 38          # 40 esperados, 2 poseídos
        assert r.porcentaje_completitud == 95     # 38/40
        assert r.ultimas_series == (s,)

    async def test_huecos_solo_de_series_con_recuento_de_grapas(self):
        """Sumar capítulos de AniList con grapas mezclaría unidades: esa serie no cuenta huecos."""
        a, b = _serie("A"), _serie("B", fuente=MetadataSource.ANILIST.value)
        r = await resumen_biblioteca(FakeSession(_cola(
            catalogo=20, totales=[(a.id, 10, "comic_vine"), (b.id, 10, "anilist")],
        )))
        assert r.huecos_pendientes == 10

    async def test_porcentaje_sin_catalogo_es_cero_sin_dividir(self):
        """Hoy 0 (V4b lo distingue de «no hay catálogo»); nunca ZeroDivisionError."""
        r = await resumen_biblioteca(FakeSession(_cola(importados=5)))
        assert r.total_issues == 0 and r.porcentaje_completitud == 0

    async def test_porcentaje_redondea(self):
        r = ResumenBiblioteca(1, 1, 3, 1, 0, ())
        assert r.porcentaje_completitud == 33

    async def test_las_consultas_de_archivos_filtran_is_missing(self):
        """B7: un fichero marcado como desaparecido no cuenta como «lo tienes»."""
        sesion = CapturingSession(_cola())
        await resumen_biblioteca(sesion)
        assert len(sesion.statements) == 7
        for i in (1, 3, 6):
            assert "is_missing" in sesion.statements[i]

    async def test_solo_lee_no_hace_commit(self):
        sesion = FakeSession(_cola())
        sesion.commit = None   # cualquier intento de commit reventaría
        await resumen_biblioteca(sesion)
