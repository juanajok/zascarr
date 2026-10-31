"""C6 / PR 1 (#152): techo de búsquedas de la política («completar»), prioridad 8 y marca persistente, con Postgres real.

El techo R cuenta ÍTEMS de política buscados en la última hora (ventana deslizante, hora de la BD) y se apoya en marcas ya
CONFIRMADAS: por eso vale también en el primer ciclo tras un arranque. Cada prueba usa una base efímera propia porque el
ciclo hace commits cortos (la marca se confirma antes de la petición externa), algo que un fixture con rollback no admite.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.config import get_settings
from zascarr.models import (
    ComicTradition,
    LegalAcknowledgment,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.legal import current_legal_version
from zascarr.services.orchestrator import PRIORIDAD_DE_LA_POLITICA, Orchestrator

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")]


@pytest.fixture
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
def ajustes(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "prowlarr_enabled", True)
    monkeypatch.setattr(s, "forum_enabled", False)
    monkeypatch.setattr(s, "politica_busquedas_por_hora", 2)
    return s


class Mundo:
    def __init__(self, url: str):
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fab = async_sessionmaker(self.motor, expire_on_commit=False)

    async def preparar(self) -> "Mundo":
        async with self.fab() as s:
            s.add(LegalAcknowledgment(id=uuid4(), legal_version=current_legal_version()))
            serie = Series(id=uuid4(), title="Serie C6", tradition=ComicTradition.AMERICAN,
                           wishlist_policy=WishlistPolicy.MISSING)
            s.add(serie)
            await s.commit()
            self.serie = serie.id
        return self

    async def item(self, numero: int, *, origen=WishlistOrigin.POLICY, hace_min: int | None = None,
                   status=WishlistStatus.WANTED, prioridad: int | None = None) -> str:
        """Un ítem; `hace_min` = marca de búsqueda de hace tantos minutos (hora de la BD), o `None` = nunca buscado."""
        async with self.fab() as s:
            w = Wishlist(id=uuid4(), series_id=self.serie, numero=numero, origen=origen, status=status,
                         search_query=f"Serie C6 {numero}")
            if prioridad is not None:
                w.priority = prioridad
            s.add(w)
            await s.flush()
            if hace_min is not None:
                await s.execute(text("update wishlist set last_searched_at = now() - make_interval(mins => :m) "
                                     "where id = :i"), {"m": hace_min, "i": w.id})
            await s.commit()
            return str(w.id)

    def orquestador(self, s) -> Orchestrator:
        o = Orchestrator(s)
        o._prowlarr = AsyncMock()
        o._prowlarr.search.return_value = []
        return o

    async def buscados(self) -> list[int]:
        """Números de política con marca de búsqueda de hace menos de 1 minuto (los que ESTE ciclo acaba de buscar)."""
        async with self.fab() as s:
            filas = (await s.execute(text(
                "select numero from wishlist where origen = 'politica' and last_searched_at > now() - interval '1 minute' "
                "order by numero"))).all()
        return [f[0] for f in filas]

    async def cerrar(self):
        await self.motor.dispose()


@pytest.fixture
async def mundo(url_bd, ajustes):
    m = await Mundo(url_bd).preparar()
    yield m
    await m.cerrar()


async def ciclo(mundo: Mundo, limit: int = 2, devolver_peticiones: bool = False) -> int:
    async with mundo.fab() as s:
        o = mundo.orquestador(s)
        n = await o.process_wishlist(limit=limit)
        await s.commit()
        return o._prowlarr.search.await_count if devolver_peticiones else n


class TestVentana:
    async def test_ac04_con_dos_buscados_en_la_ultima_hora_no_se_busca_ninguno_de_politica(self, mundo):
        await mundo.item(1, hace_min=20)
        await mundo.item(2, hace_min=40)
        for n in (3, 4, 5):
            await mundo.item(n)
        await ciclo(mundo)
        assert await mundo.buscados() == []                               # nada nuevo: el techo está agotado

    async def test_ac05_sin_busquedas_previas_se_buscan_como_mucho_r(self, mundo):
        for n in range(1, 6):
            await mundo.item(n)
        peticiones = await ciclo(mundo, devolver_peticiones=True)
        assert len(await mundo.buscados()) == 2
        assert peticiones == 2                                            # una sola búsqueda por ítem, sin repetir

    async def test_cada_item_se_busca_una_sola_vez_aunque_r_supere_el_lote_manual(self, mundo, ajustes, monkeypatch):
        monkeypatch.setattr(ajustes, "politica_busquedas_por_hora", 3)
        for n in range(1, 6):
            await mundo.item(n)
        assert await ciclo(mundo, limit=2, devolver_peticiones=True) == 3        # R=3 > lote manual=2: 3 búsquedas, no 5

    async def test_lo_manual_buscado_hace_poco_no_gasta_cupo_de_la_politica(self, mundo):
        """La ventana cuenta ítems de ORIGEN política (BR-06 solo suma las búsquedas manuales sobre ellos)."""
        await mundo.item(50, origen=WishlistOrigin.MANUAL, hace_min=10, status=WishlistStatus.DOWNLOADING)
        await mundo.item(51, origen=WishlistOrigin.MANUAL, hace_min=10, status=WishlistStatus.DOWNLOADING)
        for n in (1, 2, 3):
            await mundo.item(n)
        await ciclo(mundo)
        assert len(await mundo.buscados()) == 2

    async def test_ac29_las_marcas_se_escriben_con_la_hora_de_la_bd_aunque_el_reloj_del_proceso_este_atrasado(
            self, mundo, monkeypatch):
        import zascarr.services.orchestrator as mod

        class RelojAtrasado(mod.datetime):
            @classmethod
            def now(cls, tz=None):
                return super().now(tz) - mod.timedelta(days=2)

        for n in range(1, 6):
            await mundo.item(n)
        with monkeypatch.context() as m:
            m.setattr(mod, "datetime", RelojAtrasado)
            await ciclo(mundo)
        assert len(await mundo.buscados()) == 2                           # marcas «de ahora» según la BD
        await ciclo(mundo)                                                # el reloj ya es el bueno
        assert len(await mundo.buscados()) == 2                           # y la ventana las cuenta: no se busca más

    async def test_ac06_sin_nada_que_buscar_no_busca_ni_falla(self, mundo):
        assert await ciclo(mundo) == 0
        assert await mundo.buscados() == []

    async def test_ac07_y_ac21_el_primer_ciclo_tras_arrancar_respeta_las_marcas_ya_confirmadas(self, mundo):
        for n in range(1, 11):
            await mundo.item(n)
        await mundo.item(11, hace_min=20)
        await mundo.item(12, hace_min=20)
        await ciclo(mundo)                                                # sesión nueva = proceso recién arrancado
        assert await mundo.buscados() == []

    async def test_ac21_sin_busquedas_previas_el_primer_ciclo_busca_como_mucho_r(self, mundo):
        for n in range(1, 11):
            await mundo.item(n)
        await ciclo(mundo)
        assert len(await mundo.buscados()) == 2

    async def test_una_marca_de_hace_mas_de_una_hora_ya_no_cuenta(self, mundo):
        await mundo.item(1, hace_min=61, status=WishlistStatus.DOWNLOADING)      # buscado hace 61 min (no reintentable)
        await mundo.item(2, hace_min=59, status=WishlistStatus.DOWNLOADING)      # hace 59 min: cuenta
        for n in (3, 4, 5):
            await mundo.item(n)
        await ciclo(mundo)
        assert len(await mundo.buscados()) == 1                           # R=2, una ya gastada en la hora

    async def test_ac28_si_el_ciclo_falla_despues_de_buscar_la_marca_persiste(self, mundo):
        """Variante con fallo intermedio (SecOps): `check_completions` revienta tras buscar y la sesión se cierra SIN el commit
        final del bucle; la marca ya estaba confirmada, así que el siguiente ciclo (otro arranque) no busca más."""
        for n in range(1, 6):
            await mundo.item(n)
        async with mundo.fab() as s:
            o = mundo.orquestador(s)
            await o.process_wishlist(limit=2)
            o.check_completions = AsyncMock(side_effect=RuntimeError("boom"))
            with pytest.raises(RuntimeError):
                await o.check_completions()
            await s.rollback()                                            # equivale a cerrar sin commit
        assert len(await mundo.buscados()) == 2
        await ciclo(mundo)                                                # «reinicio»
        assert len(await mundo.buscados()) == 2                           # no se buscó ninguno más

    async def test_ac28_la_marca_se_confirma_antes_de_la_peticion_externa(self, mundo):
        await mundo.item(1)
        visto = {}

        async def busqueda(*_a, **_k):
            visto["buscados"] = await mundo.buscados()                    # desde OTRA sesión, en pleno envío
            return []

        async with mundo.fab() as s:
            o = mundo.orquestador(s)
            o._prowlarr.search.side_effect = busqueda
            await o.process_wishlist(limit=2)
        assert visto["buscados"] == [1]

    async def test_ac29_la_ventana_usa_la_hora_de_la_bd_no_la_del_proceso(self, mundo, monkeypatch):
        import zascarr.services.orchestrator as mod

        class RelojAdelantado(mod.datetime):
            @classmethod
            def now(cls, tz=None):
                return super().now(tz) + mod.timedelta(days=30)

        await mundo.item(1, hace_min=20)
        await mundo.item(2, hace_min=40)
        await mundo.item(3)
        monkeypatch.setattr(mod, "datetime", RelojAdelantado)             # un proceso con el reloj equivocado
        await ciclo(mundo)
        assert await mundo.buscados() == []

    async def test_r_cero_no_busca_ningun_item_de_politica(self, mundo, ajustes, monkeypatch):
        monkeypatch.setattr(ajustes, "politica_busquedas_por_hora", 0)
        await mundo.item(1)
        await ciclo(mundo)
        assert await mundo.buscados() == []


class TestManualesYAjustes:
    async def test_ac22_agotada_la_ventana_lo_manual_se_procesa_con_su_lote(self, mundo):
        await mundo.item(1, hace_min=10)
        await mundo.item(2, hace_min=10)
        manual = await mundo.item(50, origen=WishlistOrigin.MANUAL)
        await ciclo(mundo)
        async with mundo.fab() as s:
            marca = (await s.execute(text("select last_searched_at from wishlist where id = :i"), {"i": manual})).scalar()
        assert marca is not None

    async def test_ac08_el_techo_de_politica_no_depende_de_max_concurrent_downloads(self, mundo):
        for n in range(1, 8):
            await mundo.item(n)
        await ciclo(mundo, limit=10)                                      # el lote manual no cambia el techo de política
        assert len(await mundo.buscados()) == 2

    async def test_ac08_el_lote_manual_no_depende_de_r(self, mundo, ajustes, monkeypatch):
        monkeypatch.setattr(ajustes, "politica_busquedas_por_hora", 0)
        for n in (50, 51, 52):
            await mundo.item(n, origen=WishlistOrigin.MANUAL)
        await ciclo(mundo, limit=2)
        async with mundo.fab() as s:
            n = (await s.execute(text("select count(*) from wishlist where origen = 'manual' "
                                      "and last_searched_at is not null"))).scalar()
        assert n == 2                                                     # lote = limit, aunque R = 0

    def test_ac09_check_completions_sigue_usando_max_concurrent_downloads(self):
        main = open("src/zascarr/main.py", encoding="utf-8").read()
        assert "check_completions(limit=limit)" in main and "process_wishlist(limit=limit)" in main

    def test_ac30_r_fuera_de_0_a_10_se_rechaza(self):
        from pydantic import ValidationError

        from zascarr.config import Settings
        for malo in (-1, 11):
            with pytest.raises(ValidationError):
                Settings(_env_file=None, politica_busquedas_por_hora=malo)
        for bueno in (0, 2, 10):
            assert Settings(_env_file=None, politica_busquedas_por_hora=bueno).politica_busquedas_por_hora == bueno

    def test_ac23_el_comentario_de_r_lleva_la_declaracion_y_el_limite(self):
        fuente = open("src/zascarr/config.py", encoding="utf-8").read()
        trozo = fuente[fuente.index("# C6: techo de seguridad"):fuente.index("politica_busquedas_por_hora: int")]
        trozo = " ".join(trozo.replace("#", " ").split())            # sin marcas de comentario ni saltos de línea
        assert "hasta dos peticiones externas" in trozo and "CUENTA ÍTEMS, NO PETICIONES" in trozo
        assert "decisión nueva, no una reinterpretación" in trozo and "APROXIMADO" in trozo
        assert "last_searched_at" in trozo and "reintento manual" in trozo


class TestMarcaYBusquedaManual:
    async def test_decision_sin_fuentes_la_marca_se_escribe_antes_de_comprobarlas_y_gasta_cooldown_y_cupo(
            self, mundo, ajustes, monkeypatch):
        """Decisión del PO: sin NINGUNA fuente activa el ítem gasta el cooldown de 6 h (protege el lote) y también un
        hueco de la ventana, aunque no se haga ninguna petición externa."""
        monkeypatch.setattr(ajustes, "prowlarr_enabled", False)
        await mundo.item(1)
        await ciclo(mundo)
        assert await mundo.buscados() == [1]
        async with mundo.fab() as s:
            fila = (await s.execute(text("select status::text, last_error from wishlist"))).one()
        assert fila[0] == "wanted" and fila[1] is not None                # D9: se le dice por qué

    async def test_buscar_ahora_sobre_un_item_de_politica_tambien_cuenta_en_la_ventana(self, mundo):
        """BR-06: `last_searched_at` no distingue quién disparó la búsqueda, así que «Buscar ahora» gasta cupo."""
        await mundo.item(1)
        async with mundo.fab() as s:
            item = (await s.execute(text("select 1"))).scalar()
            w = (await s.get(Wishlist, (await s.execute(text("select id from wishlist"))).scalar()))
            o = mundo.orquestador(s)
            await o.preview_candidates(w)
            await s.commit()
        assert await mundo.buscados() == [1]


class TestPrioridad:
    async def test_ac15_lo_generado_nace_con_prioridad_8_y_va_detras_de_un_manual_de_la_misma_antiguedad(self, mundo):
        async with mundo.fab() as s:
            serie = await s.get(Series, mundo.serie)
            o = mundo.orquestador(s)
            await o._materializar(serie, 7)
            await s.commit()
        await mundo.item(60, origen=WishlistOrigin.MANUAL)
        async with mundo.fab() as s:
            prioridad = (await s.execute(text("select priority from wishlist where numero = 7"))).scalar()
            orden = (await s.execute(text(
                "select origen::text from wishlist order by priority asc, added_at asc"))).scalars().all()
        assert prioridad == PRIORIDAD_DE_LA_POLITICA == 8
        assert orden == ["manual", "politica"]

    async def test_ac16_reactivar_o_regenerar_no_cambia_la_prioridad_de_filas_existentes(self, mundo):
        await mundo.item(1, status=WishlistStatus.RETIRADO, prioridad=5)
        await mundo.item(2, status=WishlistStatus.IMPORTED, prioridad=5)
        await mundo.item(3, prioridad=5)
        async with mundo.fab() as s:
            serie = await s.get(Series, mundo.serie)
            o = mundo.orquestador(s)
            for n in (1, 2, 3):
                await o._materializar(serie, n)
            await s.commit()
        async with mundo.fab() as s:
            filas = (await s.execute(text("select numero, priority, status::text from wishlist order by numero"))).all()
        assert [(f[0], f[1]) for f in filas] == [(1, 5), (2, 5), (3, 5)]
        assert [f[2] for f in filas][:2] == ["wanted", "wanted"]           # sí se reactivaron


class TestEstadoNoSeConfirma:
    async def test_a2_si_el_proceso_cae_durante_la_peticion_el_item_no_queda_buscando_para_siempre(self, mundo):
        """SecOps A-2: la marca (`last_searched_at`) se confirma antes de la petición, pero el estado `searching` NO: si el
        proceso muere o se cancela durante la petición, el rollback lo deshace y el ítem vuelve a ser reintentable."""
        import asyncio

        await mundo.item(1)

        async def cancelada(*_a, **_k):
            raise asyncio.CancelledError

        async with mundo.fab() as s:
            o = mundo.orquestador(s)
            o._prowlarr.search.side_effect = cancelada
            with pytest.raises(asyncio.CancelledError):
                await o.process_wishlist(limit=2)
            await s.rollback()                                            # lo que ocurre al cerrar la sesión sin commit
        async with mundo.fab() as s:
            fila = (await s.execute(text("select status::text, last_searched_at is not null from wishlist"))).one()
        assert fila[0] == "wanted"                                        # no `searching` para siempre
        assert fila[1] is True                                            # y la marca sí persiste (FR-22)
