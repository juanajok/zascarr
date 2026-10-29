# ruff: noqa: E501
"""#232 — ruta, fragmento y copy de «Comprobar el disco» (#231/#232)."""
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ImportRun
from zascarr.services import comprobacion_disco as servicio
from zascarr.services.comprobacion_disco import EstadoCicloDisco, FaseCicloDisco

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd, monkeypatch):
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as conexion:
        await conexion.execute(text("TRUNCATE import_runs, files, issues, series CASCADE"))
    monkeypatch.setattr(database, "async_session_factory", fabrica)
    servicio.reiniciar_para_pruebas()

    async def _get_db():
        async with fabrica() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    yield fabrica
    app.dependency_overrides.pop(get_db, None)
    await servicio.detener()
    await motor.dispose()


def _cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                             base_url="http://localhost",
                             headers={"Origin": "http://localhost"})


async def _insertar(fabrica, **kw):
    base = dict(started_at=datetime.now(UTC) - timedelta(minutes=2),
                finished_at=datetime.now(UTC) - timedelta(minutes=1),
                files_scanned=5, imported_count=0, duplicate_count=0,
                unsorted_count=0, error_count=0, disappeared_count=0,
                details={"disparador": "manual", "reappeared": [], "errors": []})
    base.update(kw)
    async with fabrica() as s:
        run = ImportRun(**base)
        s.add(run)
        await s.commit()
        return str(run.id)


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


async def _get(cliente, ruta="/ui/no-disponibles"):
    r = await cliente.get(ruta)
    assert r.status_code == 200
    return r


class TestCargaYAccion:

    async def test_get_no_lanza_y_muestra_el_aviso_previo(self, fabrica, monkeypatch):
        llamado = False

        def prohibido(*_a, **_k):
            nonlocal llamado
            llamado = True
            return True

        monkeypatch.setattr(servicio, "iniciar_manual", prohibido)
        async with _cliente() as c:
            pagina = await _get(c)
            fragmento = await _get(c, "/ui/no-disponibles/comprobar")
        texto = _texto(pagina.text)
        assert "Comprobar el disco" in texto
        assert "No consulta fuentes de datos ni descarga portadas" in texto
        assert "Todavía no hay ninguna comprobación registrada" in texto
        assert "Buscar archivos sin registrar" not in texto
        assert 'id="comprobar-aviso"' in pagina.text and 'aria-describedby="comprobar-aviso"' in pagina.text
        assert "próxima" not in texto.lower() and "programada" not in texto.lower()
        assert fragmento.headers["cache-control"] == "no-store"
        assert llamado is False

    async def test_post_responde_en_curso_sin_esperar(self, fabrica, monkeypatch):
        def lanzar(_fabrica):
            servicio._estado = EstadoCicloDisco(
                fase=FaseCicloDisco.CORRIENDO, iniciado=datetime.now(UTC),
                disparador="manual")
            return True

        monkeypatch.setattr(servicio, "iniciar_manual", lanzar)
        async with _cliente() as c:
            r = await c.post("/ui/no-disponibles/comprobar", headers={"HX-Request": "true"})

        assert r.status_code == 200
        assert "Comprobación en curso" in r.text
        assert "autofocus" in r.text and 'role="status"' in r.text
        assert 'hx-trigger="every 5s"' in r.text

    async def test_post_sin_htmx_redirige_a_la_pantalla(self, fabrica, monkeypatch):
        monkeypatch.setattr(servicio, "iniciar_manual", lambda _f: True)
        async with _cliente() as c:
            r = await c.post("/ui/no-disponibles/comprobar")
        assert r.status_code == 303 and r.headers["location"] == "/ui/no-disponibles"

    async def test_doble_post_dice_que_ya_hay_una(self, fabrica):
        servicio._estado = EstadoCicloDisco(fase=FaseCicloDisco.CORRIENDO,
                                            iniciado=datetime.now(UTC), disparador="manual")
        async with _cliente() as c:
            r = await c.post("/ui/no-disponibles/comprobar", headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert "Ya hay una comprobación en curso" in r.text
        assert "No se ha lanzado otra" in r.text

    async def test_cifras_exactas_y_duracion(self, fabrica):
        await _insertar(fabrica, files_scanned=9, imported_count=2, duplicate_count=3,
                        unsorted_count=1, error_count=0, disappeared_count=1,
                        details={"disparador": "manual", "reappeared": ["r1", "r2"],
                                 "errors": []})
        async with _cliente() as c:
            html = (await _get(c)).text
        plano = _texto(html)
        for fragmento in ("9 archivos mirados", "2 importados", "3 repetidos",
                          "1 sin clasificar", "0 con error", "1 nuevo no disponible",
                          "2 reaparecidos", "Terminó con cambios"):
            assert fragmento in plano
        assert "Tardó" in plano
        assert "automática" not in plano and "origen sin dato" not in plano

    async def test_sin_cambios_y_ceros_visibles(self, fabrica):
        await _insertar(fabrica)
        async with _cliente() as c:
            plano = _texto((await _get(c)).text)
        assert "Sin cambios" in plano and "5 archivos mirados" in plano
        assert "0 importados" in plano and "0 nuevos no disponibles" in plano

    async def test_disparador_antiguo_es_origen_no_consta(self, fabrica):
        await _insertar(fabrica, details={"reappeared": [], "errors": []})
        async with _cliente() as c:
            plano = _texto((await _get(c)).text)
        assert "origen sin dato" in plano
        assert "automática" not in plano

    async def test_ultima_automatica_se_etiqueta(self, fabrica):
        await _insertar(fabrica, details={"disparador": "automatico", "reappeared": [], "errors": []})
        async with _cliente() as c:
            plano = _texto((await _get(c)).text)
        assert "automática" in plano and "origen sin dato" not in plano

    async def test_ultima_ignora_informes_con_kind(self, fabrica):
        await _insertar(fabrica, files_scanned=1,
                        details={"kind": "adoption", "disparador": "manual"})
        await _insertar(fabrica, files_scanned=8,
                        details={"disparador": "automatico", "reappeared": [], "errors": []})
        async with _cliente() as c:
            plano = _texto((await _get(c)).text)
        assert "8 archivos mirados" in plano and "1 archivo mirado" not in plano

    async def test_bloque_231_se_muestra_dentro_del_resultado(self, fabrica):
        await _insertar(fabrica, details={
            "disparador": "manual", "reappeared": [], "errors": [],
            "comprobacion_biblioteca": {
                "ambito": "biblioteca", "resultado": "comprobada",
                "archivos_registrados": 12, "ausentes": 2, "bajas_omitidas": False,
                "fecha": datetime.now(UTC).isoformat(),
            },
        })
        async with _cliente() as c:
            plano = _texto((await _get(c)).text)
        assert "Se miraron las 12 rutas registradas" in plano
        assert "2 no estaban" in plano


class TestEstadosYFoco:

    async def test_en_curso_deshabilita_y_no_muestra_cifras_anteriores(self, fabrica):
        await _insertar(fabrica, files_scanned=7)
        servicio._estado = EstadoCicloDisco(fase=FaseCicloDisco.CORRIENDO,
                                            iniciado=datetime.now(UTC), disparador="manual")
        async with _cliente() as c:
            html = (await _get(c)).text
        assert "Comprobación en curso" in html and 'role="status"' in html
        assert "disabled" in html and "Comprobando…" in html
        assert "7 archivos mirados" not in html

    async def test_error_generico_sin_detalle_ni_foco(self, fabrica):
        servicio._estado = EstadoCicloDisco(fase=FaseCicloDisco.ERROR,
                                            causa="RuntimeError")
        async with _cliente() as c:
            html = (await _get(c)).text
        assert "La comprobación no se pudo completar" in html
        assert 'role="alert"' in html and "RuntimeError" not in html
        assert "autofocus" not in html

    async def test_foco_al_resultado_solo_una_vez(self, fabrica):
        run_id = await _insertar(fabrica)
        servicio._estado = EstadoCicloDisco(fase=FaseCicloDisco.TERMINADO,
                                            iniciado=datetime.now(UTC),
                                            run_id=run_id, disparador="manual",
                                            foco_resultado=True)
        async with _cliente() as c:
            primero = (await _get(c, "/ui/no-disponibles/comprobar")).text
            segundo = (await _get(c, "/ui/no-disponibles/comprobar")).text
        assert "autofocus" in primero and 'tabindex="-1"' in primero
        assert 'role="alert"' not in primero
        assert "autofocus" not in segundo
        assert "8 archivos mirados" not in primero  # no inventa cifras

    async def test_sin_proxima_ejecucion_en_html(self, fabrica):
        async with _cliente() as c:
            html = (await _get(c)).text
        assert "próxima" not in html.lower() and "programada" not in html.lower()

    async def test_cross_site_no_lanza_ni_escribe(self, fabrica):
        async with _cliente() as c:
            r = await c.post("/ui/no-disponibles/comprobar",
                             headers={"Origin": "https://mal.example"})
        assert r.status_code == 403
        assert servicio.estado_actual().fase is FaseCicloDisco.INACTIVO

    async def test_con_password_sin_sesion_redirige_al_login(self, fabrica, monkeypatch):
        from zascarr.config import get_settings

        ajustes = get_settings().model_copy(update={"auth_mode": "password", "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        async with _cliente() as c:
            r = await c.post("/ui/no-disponibles/comprobar")
        assert r.status_code == 303
        assert "/login" in r.headers["location"]
        assert servicio.estado_actual().fase is FaseCicloDisco.INACTIVO


    async def test_post_real_devuelve_antes_de_que_el_ciclo_lento_termine(self, fabrica, monkeypatch):
        from datetime import timedelta

        from zascarr.services.importer import ImportReport

        iniciado = asyncio.Event()

        async def lento(_fabrica, disparador, _ejecutar):
            iniciado.set()
            await asyncio.sleep(1.2)
            ahora = datetime.now(UTC)
            return ImportReport(started_at=ahora - timedelta(seconds=1),
                                finished_at=ahora, disparador=disparador,
                                run_id=uuid4())

        monkeypatch.setattr(servicio, "_correr", lento)
        t0 = time.perf_counter()
        async with _cliente() as c:
            respuesta = await asyncio.wait_for(
                c.post("/ui/no-disponibles/comprobar", headers={"HX-Request": "true"}),
                timeout=0.8)
        transcurrido = time.perf_counter() - t0
        await asyncio.wait_for(iniciado.wait(), timeout=0.5)
        assert respuesta.status_code == 200
        assert "Comprobación en curso" in respuesta.text
        assert servicio.estado_actual().fase is FaseCicloDisco.CORRIENDO
        assert transcurrido < 0.8
        await asyncio.wait_for(servicio._tarea, 3)
        assert servicio.estado_actual().fase is FaseCicloDisco.TERMINADO
