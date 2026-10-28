# ruff: noqa: E501
"""#332 (residual 2 de #329) — la adopción NO se da por completa tras un recorrido parcial. Postgres y ficheros reales.

`LibraryAdopter.adopt` usaba solo `Recorrido.archivos` e ignoraba `Recorrido.ilegibles`: con una subcarpeta sin permisos podía terminar «completo» y
poner `_library_adoption_done` sin haber visto toda la biblioteca. Ahora cuenta lo ilegible, no pone el marcador, no es «completo» y lo dice.
Se saltan sin `TEST_DATABASE_URL` y si se ejecutan como root (los permisos no impiden listar).
"""
from __future__ import annotations

import os

import httpx
import pytest

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import Mundo, _cbz
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import registro_biblioteca
from zascarr.services.library_adopter import EstadoAdopcion, LibraryAdopter

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def mundo(url_bd, tmp_path, monkeypatch):
    m = await Mundo(url_bd, tmp_path).sembrar()
    ajustes = type("A", (), {"library_path": m.lib})()
    monkeypatch.setattr("zascarr.services.library_adopter.get_settings", lambda: ajustes)
    monkeypatch.setattr(database, "async_session_factory", m.fabrica)
    registro_biblioteca.reiniciar_para_pruebas()
    yield m
    registro_biblioteca.reiniciar_para_pruebas()
    app.dependency_overrides.pop(get_db, None)
    await m.cerrar()


@pytest.fixture
def carpeta_cerrada(mundo):
    cerrada = mundo.lib / "Cerrada"
    cerrada.mkdir()
    _cbz(cerrada / "Escondido 01.cbz", "h")
    cerrada.chmod(0)
    if os.access(cerrada, os.R_OK):
        cerrada.chmod(0o755)
        pytest.skip("se ejecuta como root: los permisos no impiden listar")
    yield cerrada
    cerrada.chmod(0o755)


async def _adopt(m: Mundo, **kw):
    async with m.fabrica() as s:
        return await LibraryAdopter(s).adopt(**kw)


async def _runs_adopcion(m: Mundo):
    from sqlalchemy import text
    async with m.fabrica() as s:
        return (await s.execute(text("SELECT details FROM import_runs WHERE details->>'kind' = 'adoption'"))).scalars().all()


class TestAdopcionInicialConRecorridoParcial:

    async def test_no_pone_el_marcador_cuenta_lo_ilegible_y_sigue_ofreciendo_continuar(self, mundo, carpeta_cerrada):
        informe = await _adopt(mundo)
        assert informe.unreadable >= 1 and informe.error_count == 0               # sin errores por archivo… pero NO completo
        assert informe.added_count > 0                                            # lo que sí se vio, se registró
        assert await mundo.marcador() is False                                    # y el marcador NO se pone
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).estado() is EstadoAdopcion.CATALOGO_PREVIO   # sigue ofreciendo registrar/continuar
        (detalle,) = await _runs_adopcion(mundo)
        assert detalle["unreadable"] >= 1                                         # el informe guardado lo dice

    async def test_coincide_con_lo_que_dice_el_inventario(self, mundo, carpeta_cerrada):
        async with mundo.fabrica() as s:
            inv = await LibraryAdopter(s).inventario()
        informe = await _adopt(mundo)
        assert inv.ilegibles == informe.unreadable >= 1                           # un solo criterio de «recorrido incompleto»

    async def test_arreglado_el_acceso_continuar_completa_y_entonces_si_pone_el_marcador(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        assert await mundo.marcador() is False
        carpeta_cerrada.chmod(0o755)                                              # se arregla el permiso
        segundo = await _adopt(mundo)
        assert segundo.unreadable == 0 and segundo.error_count == 0
        assert segundo.added_count >= 1                                           # el archivo que no se había visto
        assert await mundo.marcador() is True

    async def test_sin_nada_ilegible_el_comportamiento_de_siempre(self, mundo):
        informe = await _adopt(mundo)
        assert informe.unreadable == 0 and informe.error_count == 0 and await mundo.marcador() is True


class TestEstadoYPantalla:

    async def test_el_estado_no_es_completo_y_la_pantalla_lo_dice_y_ofrece_continuar(self, mundo, carpeta_cerrada):
        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        registro_biblioteca.iniciar(mundo.fabrica)
        import asyncio
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        e = registro_biblioteca.estado_actual()
        assert e.fase.value == "terminado" and e.ilegibles >= 1 and not e.errores and e.completo is False
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers={"Origin": "http://localhost"}) as c:
            r = await c.get("/ui/auditoria/registro")
        plano = " ".join(r.text.split())
        assert "El registro ha quedado incompleto" in plano and "No se ha podido leer 1 carpeta o archivo" in plano
        assert "Continuar el registro" in plano and "Biblioteca registrada" not in plano
        assert "No se pudo registrar 0" not in plano                              # no el mensaje de «errores» vacío


class TestRegistroIncrementalConRecorridoParcial:

    async def test_el_alcance_que_no_se_vio_consta_como_omitido_con_causa_y_el_marcador_no_se_toca(self, mundo):
        await _adopt(mundo)                                                       # registro inicial completo
        assert await mundo.marcador() is True
        destino = mundo.lib / "Nuevos" / "Nuevo 01.cbz"
        _cbz(destino, "x")
        async with mundo.fabrica() as s:
            inv = await LibraryAdopter(s).inventario()
        assert str(destino) in inv.rutas_nuevas
        destino.parent.chmod(0)                                                   # la carpeta del archivo confirmado deja de poder leerse
        try:
            if os.access(destino.parent, os.R_OK):
                pytest.skip("se ejecuta como root: los permisos no impiden listar")
            informe = await _adopt(mundo, alcance=inv.rutas_nuevas)
        finally:
            destino.parent.chmod(0o755)
        assert informe.unreadable >= 1 and informe.added_count == 0
        assert any("su carpeta no se pudo leer" in o for o in informe.omitted)    # no se afirma que «desapareció»
        assert await mundo.marcador() is True

    async def test_ilegible_ajena_al_alcance_marca_el_incremental_incompleto_sin_errores(self, mundo):
        await _adopt(mundo)                                                       # adopción inicial completa
        assert await mundo.marcador() is True
        destino = mundo.lib / "Nuevos" / "Nuevo 01.cbz"                           # lo confirmado: visible
        _cbz(destino, "x")
        async with mundo.fabrica() as s:
            inv = await LibraryAdopter(s).inventario()
        assert str(destino) in inv.rutas_nuevas
        ajena = mundo.lib / "Ajena"                                               # fuera del alcance confirmado
        ajena.mkdir()
        _cbz(ajena / "Escondido 01.cbz", "h")
        ajena.chmod(0)
        try:
            if os.access(ajena, os.R_OK):
                pytest.skip("se ejecuta como root: los permisos no impiden listar")
            assert registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas) is True
            import asyncio
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
        finally:
            ajena.chmod(0o755)
        e = registro_biblioteca.estado_actual()
        assert e.incremental is True
        assert e.fase.value == "terminado"
        assert e.errores == [] and e.ilegibles >= 1 and e.completo is False       # incompleto, pero sin errores
        assert await mundo.marcador() is True                                     # el incremental no toca el marcador
