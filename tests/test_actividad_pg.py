# ruff: noqa: E501, F401, F811
"""#1088: actividad de lectura, visitas y novedades sobre PostgreSQL real."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import cliente, entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, ReadingProgress, ReadingStatus, SeriesRecentView
from zascarr.services import actividad

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")


async def _serie(s, titulo):
    sid = uuid4()
    from zascarr.models import Series
    s.add(Series(id=sid, title=titulo))
    await s.flush()
    return sid


async def _issue(s, sid, numero, *, formato="single_issue", creada=None):
    iid = uuid4()
    campos = {"id": iid, "series_id": sid, "issue_number": numero, "volume": 1}
    if creada:
        campos["created_at"] = creada
    s.add(Issue(**campos))
    await s.flush()
    return iid


async def _archivo(s, iid, nombre, *, imported=None):
    f = File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}-{nombre}",
             file_name=nombre, file_format=FileFormat.CBZ, metadata_={},
             is_missing=False)
    if imported:
        f.imported_at = imported
    s.add(f)
    await s.flush()
    return f


@pytest.mark.asyncio
async def test_continuar_ultimos_y_por_empezar(entorno):
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Flash")
        i1 = await _issue(s, sid, "1")
        i2 = await _issue(s, sid, "2")
        i3 = await _issue(s, sid, "3")
        await _archivo(s, i1, "1.cbz")
        await _archivo(s, i2, "2.cbz")
        await _archivo(s, i3, "3.cbz")
        s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.COMPLETED,
                              started_at=datetime(2024, 1, 1, tzinfo=UTC),
                              completed_at=datetime(2024, 1, 2, tzinfo=UTC),
                              last_read_at=datetime(2024, 1, 2, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        continuar = await actividad.continuar_leyendo(s)
        ultimos = await actividad.ultimos_leidos(s)
        empezar = await actividad.por_empezar(s)
    assert [x.numero for x in continuar] == ["2"]
    assert [x.series_title for x in ultimos] == ["Flash"]
    assert empezar == []


@pytest.mark.asyncio
async def test_continuar_leyendo_actual_y_excluye_sin_archivo(entorno):
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Thorgal")
        i1 = await _issue(s, sid, "1")
        await _issue(s, sid, "2")
        await _archivo(s, i1, "1.cbz")
        s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.READING,
                              current_page=12,
                              last_read_at=datetime(2024, 2, 1, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.continuar_leyendo(s)
    assert len(r) == 1 and r[0].numero == "1" and r[0].pagina == 12


@pytest.mark.asyncio
async def test_por_empezar_y_recien_incorporados(entorno):
    ahora = datetime(2024, 5, 1, tzinfo=UTC)
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Nueva")
        iid = await _issue(s, sid, "1")
        await _archivo(s, iid, "1.cbz", imported=ahora)
        sid2 = await _serie(s, "Otra")
        await _issue(s, sid2, "1")
        await s.commit()
    async with entorno.banco.fabrica() as s:
        empezar = await actividad.por_empezar(s)
        recientes = await actividad.recien_incorporados(s)
    assert [x.series_title for x in empezar] == ["Nueva"]
    assert [x.series_title for x in recientes] == ["Nueva"]
    assert recientes[0].tipo == "serie_nueva"


@pytest.mark.asyncio
async def test_visita_idempotente(entorno):
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Visita")
        await s.commit()
    async with cliente() as c:
        assert (await c.post(f"/ui/series/{sid}/vista")).status_code == 204
        assert (await c.post(f"/ui/series/{sid}/vista")).status_code == 204
    async with entorno.banco.fabrica() as s:
        total = (await s.execute(select(func.count()).select_from(SeriesRecentView))).scalar_one()
        assert total == 1


@pytest.mark.asyncio
async def test_marcar_leido_actualiza_last_read_at(entorno):
    from zascarr.services import lectura

    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Marca")
        iid = await _issue(s, sid, "1")
        await _archivo(s, iid, "1.cbz")
        await s.commit()
        await lectura.marcar(s, iid, ReadingStatus.COMPLETED, series_id=sid)
        p = (await s.execute(
            __import__("sqlalchemy").select(ReadingProgress).where(
                ReadingProgress.issue_id == iid))).scalar_one()
        assert p.last_read_at is not None
        assert (await actividad.ultimos_leidos(s))[0].series_title == "Marca"


@pytest.mark.asyncio
async def test_anual_y_decimal_en_continuar(entorno):
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Secuencia")
        i1 = await _issue(s, sid, "1")
        i2 = await _issue(s, sid, "2")
        i25 = await _issue(s, sid, "2.5")
        anual = await _issue(s, sid, "Anual 1")
        for iid, nombre in ((i1, "1.cbz"), (i2, "2.cbz"), (i25, "2.5.cbz"), (anual, "anual.cbz")):
            await _archivo(s, iid, nombre)
        s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.COMPLETED,
                              last_read_at=datetime(2024, 1, 1, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.continuar_leyendo(s)
    assert r[0].numero == "2"

    async with entorno.banco.fabrica() as s:
        sid2 = await _serie(s, "SoloAnual")
        i1 = await _issue(s, sid2, "1")
        anual = await _issue(s, sid2, "Anual 2")
        await _archivo(s, i1, "1.cbz")
        await _archivo(s, anual, "anual.cbz")
        s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.COMPLETED,
                              last_read_at=datetime(2024, 1, 1, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.continuar_leyendo(s)
        anual_r = next(x for x in r if x.series_title == "SoloAnual")
        assert anual_r.numero == "Anual 2"


@pytest.mark.asyncio
async def test_continuar_acota_por_actividad_y_limite(entorno):
    async with entorno.banco.fabrica() as s:
        for i in range(8):
            sid = await _serie(s, f"Serie {i}")
            i1 = await _issue(s, sid, "1")
            i2 = await _issue(s, sid, "2")
            await _archivo(s, i1, "1.cbz")
            await _archivo(s, i2, "2.cbz")
            s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.COMPLETED,
                                  last_read_at=datetime(2024, 1, 1 + i, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.continuar_leyendo(s)
    assert len(r) == 6
    assert [x.series_title for x in r] == [f"Serie {i}" for i in range(7, 1, -1)]


@pytest.mark.asyncio
async def test_ultimos_agrupa_dos_series(entorno):
    async with entorno.banco.fabrica() as s:
        for titulo, fechas in (("A", (1, 3)), ("B", (2, 4))):
            sid = await _serie(s, titulo)
            for n, dia in enumerate(fechas, 1):
                iid = await _issue(s, sid, str(n))
                s.add(ReadingProgress(id=uuid4(), issue_id=iid, status=ReadingStatus.COMPLETED,
                                      last_read_at=datetime(2024, 1, dia, tzinfo=UTC)))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.ultimos_leidos(s)
    assert [x.series_title for x in r] == ["B", "A"]
    assert len({x.series_id for x in r}) == 2


@pytest.mark.asyncio
async def test_novedades_nueva_numero_sustitucion_variante(entorno):
    viejo = datetime(2023, 1, 1, tzinfo=UTC)
    medio = datetime(2024, 1, 1, tzinfo=UTC)
    nuevo = datetime(2025, 1, 1, tzinfo=UTC)
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Nueva")
        iid = await _issue(s, sid, "1")
        await _archivo(s, iid, "1.cbz", imported=nuevo)
        sid2 = await _serie(s, "Establecida")
        i1 = await _issue(s, sid2, "1")
        i2 = await _issue(s, sid2, "2")
        await _archivo(s, i1, "1.cbz", imported=viejo)
        await _archivo(s, i2, "2.cbz", imported=nuevo)
        sid3 = await _serie(s, "Sustituida")
        i1 = await _issue(s, sid3, "1")
        i2 = await _issue(s, sid3, "2", creada=medio)
        await _archivo(s, i1, "1.cbz", imported=viejo)
        await _archivo(s, i2, "2.cbz", imported=nuevo)
        sid4 = await _serie(s, "Variante")
        i1 = await _issue(s, sid4, "1")
        await _archivo(s, i1, "1.cbz", imported=nuevo)
        await _archivo(s, i1, "1-variante.cbz", imported=nuevo)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await actividad.recien_incorporados(s, limite=10)
    por_serie = {x.series_title: x for x in r}
    assert por_serie["Nueva"].tipo == "serie_nueva"
    assert por_serie["Establecida"].tipo == "numero_nuevo"
    assert por_serie["Establecida"].titulo is None or isinstance(por_serie["Establecida"].titulo, str)
    assert "Sustituida" not in por_serie
    assert len([x for x in r if x.series_title == "Variante"]) == 1


@pytest.mark.asyncio
async def test_vista_get_no_escribe_y_404(entorno):
    from sqlalchemy import func, select
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "GetNoEscribe")
        await s.commit()
    async with cliente() as c:
        assert (await c.get(f"/ui/series/{sid}/vista")).status_code == 405
        assert (await c.post(f"/ui/series/{uuid4()}/vista")).status_code == 404
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(func.count()).select_from(SeriesRecentView))).scalar_one() == 0


@pytest.mark.asyncio
async def test_marcar_leyendo_y_guardar_pagina_actualizan_last_read_at(entorno, tmp_path):
    from sqlalchemy import select

    from zascarr.services import lector, lectura
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Página")
        iid = await _issue(s, sid, "1")
        f = await _archivo(s, iid, "1.cbz")
        await s.commit()
        await lectura.marcar(s, iid, ReadingStatus.READING, series_id=sid)
        p = (await s.execute(select(ReadingProgress).where(
            ReadingProgress.issue_id == iid))).scalar_one()
        assert p.last_read_at is not None
    # Guardar página: un CBZ mínimo con una imagen; el servicio solo lista nombres.
    import zipfile
    ruta = tmp_path / "pagina.cbz"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", b"x")
    async with entorno.banco.fabrica() as s:
        f = (await s.execute(select(File).where(File.issue_id == iid))).scalar_one()
        f.file_path = str(ruta)
        # `_abrir` resuelve por id; actualiza la fila existente.
        await s.commit()
        await lector.guardar_progreso(s, f.id, 1)
        p = (await s.execute(select(ReadingProgress).where(
            ReadingProgress.issue_id == iid))).scalar_one()
        assert p.last_read_at is not None and p.current_page == 1


@pytest.mark.asyncio
async def test_cada_carrusel_es_una_sola_consulta(entorno):
    async with entorno.banco.fabrica() as s:
        sid = await _serie(s, "Consulta")
        i1 = await _issue(s, sid, "1")
        i2 = await _issue(s, sid, "2")
        await _archivo(s, i1, "1.cbz")
        await _archivo(s, i2, "2.cbz")
        s.add(ReadingProgress(id=uuid4(), issue_id=i1, status=ReadingStatus.COMPLETED,
                              last_read_at=datetime(2024, 1, 1, tzinfo=UTC)))
        await s.commit()
    for funcion in (actividad.continuar_leyendo, actividad.ultimos_leidos,
                    actividad.por_empezar, actividad.recien_incorporados):
        async with entorno.banco.fabrica() as s:
            antes = len(entorno.banco.sentencias)
            await funcion(s)
            assert len(entorno.banco.sentencias) - antes == 1, funcion.__name__
