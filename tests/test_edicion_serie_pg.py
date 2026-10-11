# ruff: noqa: E501
"""`PATCH /api/series/{id}` detecta colisiones al cambiar la identidad (I5 de #114, ADR 0010 P-4) — Postgres real.

Se fija: cambiar título, tradición o año hacia una serie parecida (misma definición que el alta) da `409 serie_parecida`
y no cambia nada; con `vistas` procede; los demás campos no cambian de comportamiento; el alta y la edición comparten
detección y candado; y una edición que llega mientras un alta tiene el candado del título espera y luego ve lo que esa
alta creó. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, Series, WishlistPolicy
from zascarr.services.alta_serie import AltaDeSerie, bloquear_titulo

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

AM, MANGA = ComicTradition.AMERICAN, ComicTradition.MANGA


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


class Banco:
    def __init__(self, url, monkeypatch):
        import zascarr.database as dbmod
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fabrica = async_sessionmaker(self.motor, expire_on_commit=False)
        monkeypatch.setattr(dbmod, "async_session_factory", self.fabrica)

    async def vaciar(self):
        async with self.motor.begin() as c:
            await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, wishlist, alta_operaciones CASCADE"))

    async def serie(self, titulo, tradicion=AM, anio=2010, **kw) -> Series:
        async with self.fabrica() as s:
            serie = Series(id=uuid4(), title=titulo, tradition=tradicion, start_year=anio, **kw)
            s.add(serie)
            await s.commit()
            return serie

    async def leer(self, serie_id) -> Series:
        async with self.fabrica() as s:
            return await s.get(Series, serie_id)

    def _cliente(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from zascarr.api.series import router
        app = FastAPI()
        app.include_router(router, prefix="/api")
        return TestClient(app, raise_server_exceptions=False)

    async def patch(self, serie_id, cuerpo):
        return await asyncio.to_thread(self._cliente().patch, f"/api/series/{serie_id}", json=cuerpo)


@pytest.fixture
async def banco(url_bd, monkeypatch):
    b = Banco(url_bd, monkeypatch)
    await b.vaciar()
    yield b
    await b.motor.dispose()


class TestCambiarLaIdentidadHaciaUnaParecida:
    @pytest.mark.asyncio
    async def test_cambiar_el_titulo_a_uno_existente_da_409_con_la_lista_y_no_cambia_nada(self, banco):
        otra = await banco.serie("Saga del Faro", anio=2010)
        mia = await banco.serie("Crónicas Lunares", anio=2010)
        r = await banco.patch(mia.id, {"title": "saga del faro"})        # mismo título normalizado
        assert r.status_code == 409
        d = r.json()["detail"]
        assert d["codigo"] == "serie_parecida" and [p["series_id"] for p in d["parecidas"]] == [str(otra.id)]
        assert (await banco.leer(mia.id)).title == "Crónicas Lunares"

    @pytest.mark.asyncio
    async def test_con_vistas_procede_y_la_respuesta_trae_el_titulo_nuevo(self, banco):
        otra = await banco.serie("Saga del Faro")
        mia = await banco.serie("Crónicas Lunares")
        r = await banco.patch(mia.id, {"title": "Saga del Faro", "vistas": [str(otra.id)]})
        assert r.status_code == 200 and r.json()["title"] == "Saga del Faro"
        assert r.json()["title_norm"] == (await banco.leer(otra.id)).title_norm          # columna generada, releída
        assert (await banco.leer(mia.id)).title == "Saga del Faro"

    @pytest.mark.asyncio
    async def test_declarar_solo_parte_de_las_parecidas_no_basta(self, banco):
        a = await banco.serie("Saga del Faro", anio=2009)
        await banco.serie("Saga del Faro", anio=2011)
        mia = await banco.serie("Otra", anio=2010)
        r = await banco.patch(mia.id, {"title": "Saga del Faro", "vistas": [str(a.id)]})
        assert r.status_code == 409 and len(r.json()["detail"]["parecidas"]) == 2
        assert (await banco.leer(mia.id)).title == "Otra"

    @pytest.mark.asyncio
    async def test_cambiar_la_tradicion_hacia_una_parecida_da_409(self, banco):
        await banco.serie("Saga del Faro", tradicion=MANGA)
        mia = await banco.serie("Saga del Faro", tradicion=AM)
        r = await banco.patch(mia.id, {"tradition": "manga"})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "serie_parecida"
        assert (await banco.leer(mia.id)).tradition == AM

    @pytest.mark.asyncio
    @pytest.mark.parametrize("anio,codigo", [(2011, 409), (2009, 409), (2012, 200), (None, 409)])
    async def test_cambiar_el_anio_se_compara_a_mas_menos_uno_y_un_ano_desconocido_no_descarta(self, banco, anio, codigo):
        await banco.serie("Saga del Faro", anio=2010)
        mia = await banco.serie("Saga del Faro", anio=1990)
        r = await banco.patch(mia.id, {"start_year": anio})
        assert r.status_code == codigo

    @pytest.mark.asyncio
    async def test_otra_tradicion_con_el_mismo_titulo_no_es_parecida(self, banco):
        await banco.serie("Saga del Faro", tradicion=MANGA)
        mia = await banco.serie("Otra", tradicion=AM)
        assert (await banco.patch(mia.id, {"title": "Saga del Faro"})).status_code == 200


class TestLaPropiaSerieNoCuentaComoParecida:
    @pytest.mark.asyncio
    async def test_cambiar_el_anio_de_una_serie_unica_a_uno_cercano_procede(self, banco):
        mia = await banco.serie("Saga del Faro", anio=2010)
        r = await banco.patch(mia.id, {"start_year": 2011})
        assert r.status_code == 200 and (await banco.leer(mia.id)).start_year == 2011


class TestLoQueNoCambia:
    @pytest.mark.asyncio
    async def test_repetir_el_mismo_titulo_no_dispara_la_deteccion_aunque_ya_haya_duplicados(self, banco):
        await banco.serie("Saga del Faro")
        mia = await banco.serie("Saga del Faro")                      # duplicado preexistente
        r = await banco.patch(mia.id, {"title": "Saga del Faro", "status": "completed"})
        assert r.status_code == 200 and r.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_los_demas_campos_no_se_ven_afectados_por_un_duplicado_existente(self, banco):
        await banco.serie("Saga del Faro")
        mia = await banco.serie("Saga del Faro")
        r = await banco.patch(mia.id, {"description": "Nueva", "status": "completed", "wishlist_policy": "faltantes",
                                       "cover_url": None, "total_issues": 12})
        assert r.status_code == 200
        s = await banco.leer(mia.id)
        assert s.description == "Nueva" and s.wishlist_policy == WishlistPolicy.MISSING and s.total_issues == 12

    @pytest.mark.asyncio
    async def test_vistas_no_es_un_campo_de_la_serie_y_se_valida(self, banco):
        mia = await banco.serie("Saga del Faro")
        assert (await banco.patch(mia.id, {"vistas": [str(uuid4())], "status": "completed"})).status_code == 200
        assert (await banco.patch(mia.id, {"vistas": ["no-es-un-uuid"]})).status_code == 422
        assert (await banco.patch(mia.id, {"vistas": [str(uuid4()) for _ in range(101)]})).status_code == 422

    @pytest.mark.asyncio
    async def test_una_serie_inexistente_da_404_tambien_al_cambiar_la_identidad(self, banco):
        assert (await banco.patch(uuid4(), {"title": "X"})).status_code == 404

    @pytest.mark.asyncio
    async def test_mas_de_cien_parecidas_da_422_como_el_alta(self, banco):
        async with banco.fabrica() as s:
            s.add_all([Series(id=uuid4(), title="Saga del Faro", tradition=AM, start_year=2010) for _ in range(101)])
            await s.commit()
        mia = await banco.serie("Otra")
        r = await banco.patch(mia.id, {"title": "Saga del Faro"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "demasiadas_parecidas"
        assert (await banco.leer(mia.id)).title == "Otra"


class TestParidadConElAlta:
    @pytest.mark.asyncio
    async def test_la_edicion_y_el_alta_ven_las_mismas_parecidas(self, banco):
        for t, a, tr in (("Saga del Faro", 2009, AM), ("SAGA del faro", 2011, AM), ("Saga del Faro", 2010, MANGA),
                         ("Saga del Faro", 2020, AM), ("Otra cosa", 2010, AM)):
            await banco.serie(t, tr, a)
        mia = await banco.serie("Nada que ver", anio=2010)
        r = await banco.patch(mia.id, {"title": "Saga del Faro"})
        en_edicion = {p["series_id"] for p in r.json()["detail"]["parecidas"]}
        async with banco.fabrica() as s:
            en_alta = {p.series_id for p in await AltaDeSerie(s, secret="x")._parecidas("Saga del Faro", 2010, AM, excluir=str(mia.id))}
        assert r.status_code == 409 and en_edicion == en_alta and len(en_edicion) == 2


class TestConcurrencia:
    @pytest.mark.asyncio
    async def test_una_edicion_espera_al_candado_del_titulo_y_luego_ve_lo_que_creo_otra_operacion(self, banco):
        """Una alta en curso tiene el candado del título; la edición hacia ese título espera, y al continuar ve la serie
        recién creada. Sin candado, vería el título libre y crearía el duplicado."""
        mia = await banco.serie("Otra")
        async with banco.fabrica() as alta:
            await bloquear_titulo(alta, "Saga del Faro")
            edicion = asyncio.create_task(banco.patch(mia.id, {"title": "Saga del Faro"}))
            for _ in range(200):                                            # espera ACTIVA a que la edición esté bloqueada
                async with banco.motor.connect() as c:
                    esperando = (await c.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"))).scalar()
                if esperando:
                    break
                await asyncio.sleep(0.05)
            assert esperando and not edicion.done()
            alta.add(Series(id=uuid4(), title="Saga del Faro", tradition=AM, start_year=2010))
            await alta.commit()
        r = await asyncio.wait_for(edicion, timeout=30)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "serie_parecida"
        assert (await banco.leer(mia.id)).title == "Otra"

    @pytest.mark.asyncio
    async def test_dos_ediciones_a_la_vez_hacia_el_mismo_titulo_solo_dejan_pasar_una(self, banco):
        a, b = await banco.serie("Uno"), await banco.serie("Dos")
        ra, rb = await asyncio.gather(banco.patch(a.id, {"title": "Saga del Faro"}), banco.patch(b.id, {"title": "Saga del Faro"}))
        assert sorted([ra.status_code, rb.status_code]) == [200, 409]
        async with banco.fabrica() as s:
            assert len((await s.execute(select(Series).where(Series.title == "Saga del Faro"))).scalars().all()) == 1
