# ruff: noqa: E501
"""#332 residual 4 — persistencia y evaluación de la aceptación, contra Postgres real.

Cubre el contrato del memo: oferta desde el último `ImportRun`, escritura atómica, evidencia
inmutable, rechazos sin escritura, idempotencia y concurrencia. Se salta sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import Mundo, _cbz
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ImportRun
from zascarr.services import registro_biblioteca
from zascarr.services.aceptacion_adopcion import (
    CLAVE_ACEPTACION,
    CLAVE_MARCADOR,
    MAX_ILEGIBLES,
    aceptar,
    evaluar,
)
from zascarr.services.library_adopter import AdoptionReport, LibraryAdopter
from zascarr.services.primeros_pasos import fecha_llana
from zascarr.services.registro_biblioteca import (
    CLAVE_CERROJO_REGISTRO,
    EstadoRegistro,
    FaseRegistro,
)

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


async def _adopt(m: Mundo):
    async with m.fabrica() as s:
        return await LibraryAdopter(s).adopt()


async def _aceptar(m: Mundo, run_id, count, *, en_marcha: bool = False):
    async with m.fabrica() as s:
        return await aceptar(s, run_id, count, en_marcha=en_marcha)


async def _evaluar(m: Mundo, *, en_marcha: bool = False):
    async with m.fabrica() as s:
        return await evaluar(s, en_marcha=en_marcha)


async def _valores(m: Mundo) -> dict:
    async with m.fabrica() as s:
        fila = (await s.execute(text('SELECT "values" FROM runtime_settings WHERE id = 1'))).scalar_one()
    return dict(fila or {})


async def _set_values(m: Mundo, patch: dict) -> None:
    async with m.fabrica() as s:
        await s.execute(text('UPDATE runtime_settings SET "values" = COALESCE("values", \'{}\'::jsonb) || CAST(:p AS jsonb) WHERE id = 1'), {"p": json.dumps(patch)})
        await s.commit()


async def _runs(m: Mundo, kind: str) -> list[ImportRun]:
    async with m.fabrica() as s:
        return list((await s.execute(
            select(ImportRun)
            .where(ImportRun.details["kind"].astext == kind)
            .order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        )).scalars().all())


async def _ultima_adopcion(m: Mundo) -> ImportRun:
    return (await _runs(m, "adoption"))[0]


async def _snapshot(m: Mundo):
    """Estado persistente completo que un rechazo no puede alterar."""
    async with m.fabrica() as s:
        valores = (await s.execute(text('SELECT "values" FROM runtime_settings WHERE id = 1'))).scalar_one_or_none()
        runs = (await s.execute(text("SELECT id, details FROM import_runs ORDER BY id"))).all()
    return (
        dict(valores) if valores is not None else None,
        sorted((str(fila[0]), json.dumps(fila[1] or {}, sort_keys=True)) for fila in runs),
    )


async def _insert_run(m: Mundo, *, kind: str, unreadable: int, errors: list[str] | None = None,
                      error_count: int = 0, finished_at=datetime.now(UTC), **extra) -> ImportRun:
    detalles = {"kind": kind, "unreadable": unreadable, "errors": errors or [], **extra}
    async with m.fabrica() as s:
        run = ImportRun(started_at=datetime.now(UTC), finished_at=finished_at,
                        error_count=error_count, details=detalles)
        s.add(run)
        await s.commit()
        return run


class TestAceptacionPersistente:

    async def test_aceptar_valido_escribe_marcador_registro_y_evidencia_sin_mutar_el_informe(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        antes = dict(run.details)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 200 and resultado.reason == "accepted"
        valores = await _valores(mundo)
        assert valores[CLAVE_MARCADOR] is True
        registro = valores[CLAVE_ACEPTACION]
        assert registro["count"] == 1
        assert UUID(registro["run_id"]) == run.id
        assert registro["auth_mode"] == "none"
        assert datetime.fromisoformat(registro["accepted_at"]).tzinfo is not None

        evidencia = await _runs(mundo, "adoption_acceptance")
        assert len(evidencia) == 1
        assert evidencia[0].details["adoption_run_id"] == str(run.id)
        assert evidencia[0].details["count"] == 1
        assert evidencia[0].details["auth_mode"] == "none"
        assert evidencia[0].details["accepted_at"] == registro["accepted_at"]

        assert (await _ultima_adopcion(mundo)).details == antes   # informe inmutable

    async def test_doble_post_es_idempotente_y_no_duplica_evidencia(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        primero = await _aceptar(mundo, run.id, 1)
        aceptado_en = (await _valores(mundo))[CLAVE_ACEPTACION]["accepted_at"]

        segundo = await _aceptar(mundo, run.id, 1)

        assert primero.reason == "accepted"
        assert segundo.status == 200 and segundo.reason == "already_accepted_idempotent"
        assert (await _valores(mundo))[CLAVE_ACEPTACION]["accepted_at"] == aceptado_en
        assert len(await _runs(mundo, "adoption_acceptance")) == 1

    async def test_run_obsoleto_no_escribe(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _adopt(mundo)
        runs = await _runs(mundo, "adoption")
        viejo = runs[-1]
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, viejo.id, 1)

        assert resultado.status == 409 and resultado.reason == "stale_run"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)
        assert await _runs(mundo, "adoption_acceptance") == []

    async def test_count_distinto_no_escribe(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 2)

        assert resultado.status == 409 and resultado.reason == "count_mismatch"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)
        assert await _runs(mundo, "adoption_acceptance") == []

    @pytest.mark.parametrize("kind", ["registro_incremental", "audit"])
    async def test_otro_kind_con_adopcion_previa_es_stale(self, mundo, carpeta_cerrada, kind):
        await _adopt(mundo)
        run = await _insert_run(mundo, kind=kind, unreadable=1)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "stale_run"

    @pytest.mark.parametrize("kind", ["registro_incremental", "audit"])
    async def test_otro_kind_sin_adopcion_previa_es_incremental(self, mundo, kind):
        run = await _insert_run(mundo, kind=kind, unreadable=1)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "incremental_run"
        assert CLAVE_MARCADOR not in await _valores(mundo)
        assert await _runs(mundo, "adoption_acceptance") == []

    async def test_informe_con_errores_no_se_acepta(self, mundo):
        run = await _insert_run(mundo, kind="adoption", unreadable=1, errors=["fallo"], error_count=1)
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "has_errors"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_informe_sin_ilegibles_no_se_acepta(self, mundo):
        run = await _insert_run(mundo, kind="adoption", unreadable=0)
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "zero_unreadable"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_lotes_sin_acreditar_no_se_aceptan(self, mundo):
        run = await _insert_run(mundo, kind="adoption", unreadable=1, reverted=1)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "batch_unverified"

    async def test_marcador_ya_puesto_con_otros_datos_no_reescribe(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        primero = await _ultima_adopcion(mundo)
        await _aceptar(mundo, primero.id, 1)
        registro = (await _valores(mundo))[CLAVE_ACEPTACION]
        segundo = await _insert_run(mundo, kind="adoption", unreadable=2)
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, segundo.id, 2)

        assert resultado.status == 409 and resultado.reason == "already_accepted"
        assert await _snapshot(mundo) == antes
        assert (await _valores(mundo))[CLAVE_ACEPTACION] == registro
        assert len(await _runs(mundo, "adoption_acceptance")) == 1

    @pytest.mark.parametrize("valor", ["false", 1, {}, []])
    async def test_marcador_corrupto_no_autoriza_ni_se_pisa(self, mundo, carpeta_cerrada, valor):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        await _set_values(mundo, {CLAVE_MARCADOR: valor})
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "corrupt_flag"
        assert await _snapshot(mundo) == antes
        assert (await _valores(mundo))[CLAVE_MARCADOR] == valor
        assert await _runs(mundo, "adoption_acceptance") == []

    async def test_registro_corrupto_no_autoriza(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        await _set_values(mundo, {CLAVE_MARCADOR: True,
                                  CLAVE_ACEPTACION: {"count": "1", "accepted_at": "no"}})
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 409 and resultado.reason == "corrupt_record"
        assert await _snapshot(mundo) == antes
        assert (await _valores(mundo))[CLAVE_ACEPTACION]["count"] == "1"   # no se borra

    async def test_run_inexistente(self, mundo):
        resultado = await _aceptar(mundo, uuid4(), 1)
        assert resultado.status == 404 and resultado.reason == "not_found"

    async def test_registro_en_marcha_no_acepta(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        antes = await _snapshot(mundo)

        resultado = await _aceptar(mundo, run.id, 1, en_marcha=True)

        assert resultado.status == 409 and resultado.reason == "in_progress"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_aceptar_no_recorre_el_disco(self, mundo, carpeta_cerrada, monkeypatch):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)

        def _prohibido(*_a, **_k):
            raise AssertionError("la aceptación no puede recorrer el disco")

        monkeypatch.setattr(Path, "rglob", _prohibido)
        monkeypatch.setattr(os, "walk", _prohibido)

        assert (await _aceptar(mundo, run.id, 1)).reason == "accepted"

    async def test_dos_conexiones_concurrentes_hacen_una_sola_escritura(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)

        resultados = await asyncio.gather(
            _aceptar(mundo, run.id, 1),
            _aceptar(mundo, run.id, 1),
        )

        assert sorted(r.status for r in resultados) == [200, 200]
        assert {r.reason for r in resultados} == {"accepted", "already_accepted_idempotent"}
        assert len(await _runs(mundo, "adoption_acceptance")) == 1
        valores = await _valores(mundo)
        assert valores[CLAVE_MARCADOR] is True
        assert valores[CLAVE_ACEPTACION]["run_id"] == str(run.id)

    async def test_log_saneado_con_auth_mode(self, mundo, carpeta_cerrada):
        import structlog

        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        with structlog.testing.capture_logs() as logs:
            await _aceptar(mundo, run.id, 1)

        evento = next(e for e in logs if e["event"] == "library_adopter.acceptance")
        assert evento["run_id"] == str(run.id) and evento["count"] == 1
        assert evento["auth_mode"] == "none" and evento["result"] == "accepted"
        assert str(mundo.lib) not in json.dumps(evento, default=str)


class TestEvaluacionDeLaOferta:

    async def test_oferta_desde_el_informe_persistido_sin_estado_en_memoria(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)

        ev = await _evaluar(mundo)

        assert ev.oferta is True
        assert ev.unreadable == 1 and ev.run_id == str(run.id)
        assert ev.aceptacion is None and ev.aviso is None

    async def test_sin_oferta_con_adopcion_completa(self, mundo):
        await _adopt(mundo)
        ev = await _evaluar(mundo)
        assert ev.oferta is False and ev.aceptacion is None and ev.aviso is None

    async def test_sin_oferta_con_errores(self, mundo):
        await _insert_run(mundo, kind="adoption", unreadable=1, errors=["x"], error_count=1)
        ev = await _evaluar(mundo)
        assert ev.oferta is False

    async def test_sin_oferta_con_lotes_sin_acreditar(self, mundo):
        await _insert_run(mundo, kind="adoption", unreadable=1, unknown=1)
        ev = await _evaluar(mundo)
        assert ev.oferta is False

    async def test_sin_oferta_si_hay_registro_en_marcha(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        ev = await _evaluar(mundo, en_marcha=True)
        assert ev.oferta is False

    async def test_un_incremental_mas_nuevo_no_roba_la_oferta_de_adopcion(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _insert_run(mundo, kind="registro_incremental", unreadable=1)
        ev = await _evaluar(mundo)
        assert ev.oferta is True and ev.unreadable == 1

    async def test_aviso_tras_aceptar(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        await _aceptar(mundo, run.id, 1)

        ev = await _evaluar(mundo)

        assert ev.oferta is False
        assert ev.aceptacion is not None and ev.aceptacion.count == 1
        assert ev.aceptacion.run_id == run.id and ev.aceptacion.auth_mode == "none"

    async def test_marcador_corrupto_no_se_lee_como_aceptado(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _set_values(mundo, {CLAVE_MARCADOR: "false"})

        ev = await _evaluar(mundo)

        assert ev.oferta is False and ev.aceptacion is None
        assert ev.aviso and "marcador" in ev.aviso.lower()

    async def test_registro_corrupto_no_se_lee_como_aceptado(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _set_values(mundo, {CLAVE_MARCADOR: True, CLAVE_ACEPTACION: {"count": 1}})

        ev = await _evaluar(mundo)

        assert ev.oferta is False and ev.aceptacion is None
        assert ev.aviso and "aceptación" in ev.aviso.lower()


def _cliente(m: Mundo) -> httpx.AsyncClient:
    async def _get_db():
        async with m.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    )


async def _get(cliente: httpx.AsyncClient) -> str:
    r = await cliente.get("/ui/auditoria/registro")
    assert r.status_code == 200
    return r.text


async def _post(cliente: httpx.AsyncClient, run_id, count: int, *, htmx: bool = True):
    headers = {"HX-Request": "true"} if htmx else {}
    return await cliente.post("/ui/auditoria/aceptar-ilegibles",
                              data={"run_id": str(run_id), "count": str(count)},
                              headers=headers)


class TestPantallaDeAceptacion:

    async def test_oferta_tras_reiniciar_usa_el_informe_persistido(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        registro_biblioteca.reiniciar_para_pruebas()

        async with _cliente(mundo) as c:
            html = await _get(c)

        plano = " ".join(html.split())
        assert "También puedes dar la biblioteca por registrada sin leer lo que falta." in plano
        assert "Registrar de todos modos (1 sin leer)" in html
        assert "Si ya has arreglado el acceso, usa Continuar el registro." in plano
        assert "Tu biblioteca ya está registrada" not in plano
        assert re.search(r'name="run_id" value="' + str(run.id) + '"', html)
        assert re.search(r'name="count" value="1"', html)
        assert 'class="audit-item"' in html and 'class="audit-acciones"' in html
        assert 'id="aceptar-ilegibles-consecuencia"' in html
        assert 'aria-describedby="aceptar-ilegibles-consecuencia"' in html
        assert 'role="alert"' not in html
        assert str(mundo.lib) not in html and "Obra rara 01.cbz" not in html

    async def test_continuar_es_primario_y_aceptar_neutro(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        registro_biblioteca.reiniciar_para_pruebas()
        async with _cliente(mundo) as c:
            html = await _get(c)

        assert html.index('hx-post="/ui/auditoria/adoptar"') < html.index('hx-post="/ui/auditoria/aceptar-ilegibles"')
        assert re.search(r'<button type="button" class="btn-primary"[^>]*hx-post="/ui/auditoria/adoptar"', html)
        aceptar = re.search(r"<button type=\"submit\"[^>]*>Registrar de todos modos", html)
        assert aceptar and "btn-secondary" not in aceptar.group(0)

    async def test_sin_oferta_con_adopcion_completa(self, mundo):
        await _adopt(mundo)
        registro_biblioteca.reiniciar_para_pruebas()
        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "Registrar de todos modos" not in html
        assert "Tu biblioteca ya está registrada" in html

    async def test_sin_oferta_con_errores(self, mundo):
        await _insert_run(mundo, kind="adoption", unreadable=1, errors=["fallo"], error_count=1)
        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "Registrar de todos modos" not in html

    async def test_sin_oferta_sin_informe(self, mundo):
        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "Registrar de todos modos" not in html

    async def test_sin_oferta_con_registro_en_marcha(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        registro_biblioteca._estado = EstadoRegistro(fase=FaseRegistro.CORRIENDO)
        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "Registrar de todos modos" not in html

    async def test_aviso_permanente_con_fecha_tras_aceptar_y_recargar(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with _cliente(mundo) as c:
            respuesta = await _post(c, run.id, 1)

        assert respuesta.status_code == 200
        html = respuesta.text
        assert "Registrar de todos modos" not in html
        assert re.search(r"Biblioteca registrada con 1 sin leer el \d{1,2} de [a-z]+ de \d{4}\.",
                         " ".join(html.split()))
        assert 'autofocus' in html and 'tabindex="-1"' in html
        assert 'role="alert"' not in html and 'role="status"' not in html
        assert await _valores(mundo) is not None

        registro_biblioteca.reiniciar_para_pruebas()
        async with _cliente(mundo) as c:
            recarga = await _get(c)
        assert "Biblioteca registrada con 1 sin leer" in recarga
        assert "autofocus" not in recarga
        assert "Registrar de todos modos" not in recarga

    async def test_conflicto_visible_y_sin_escritura(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _adopt(mundo)
        runs = await _runs(mundo, "adoption")
        viejo = runs[-1]
        async with _cliente(mundo) as c:
            respuesta = await _post(c, viejo.id, 1)

        assert respuesta.status_code == 200
        plano = " ".join(respuesta.text.split())
        assert "El informe ha cambiado." in plano and "No se ha aceptado nada." in plano
        assert 'autofocus' in respuesta.text and 'tabindex="-1"' in respuesta.text
        assert CLAVE_MARCADOR not in await _valores(mundo)

        async with _cliente(mundo) as c:
            fresco = await _get(c)
        assert "Registrar de todos modos (1 sin leer)" in fresco

    async def test_conflicto_sin_htmx_devuelve_409(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _adopt(mundo)
        viejo = (await _runs(mundo, "adoption"))[-1]
        async with _cliente(mundo) as c:
            respuesta = await _post(c, viejo.id, 1, htmx=False)

        assert respuesta.status_code == 409
        assert respuesta.json()["reason"] == "stale_run"
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_payload_invalido_es_422_y_no_escribe(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with _cliente(mundo) as c:
            for datos in (
                {"run_id": "no-uuid", "count": "1"},
                {"run_id": str(run.id), "count": "0"},
                {"run_id": str(run.id), "count": "-1"},
                {"run_id": str(run.id), "count": str(MAX_ILEGIBLES + 1)},
                {"run_id": str(run.id), "count": "muchos"},
            ):
                respuesta = await c.post("/ui/auditoria/aceptar-ilegibles", data=datos)
                assert respuesta.status_code == 422
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_cross_site_se_rechaza_sin_escribir(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with _cliente(mundo) as c:
            respuesta = await c.post("/ui/auditoria/aceptar-ilegibles",
                                      data={"run_id": str(run.id), "count": "1"},
                                      headers={"Origin": "https://mal.example"})
        assert respuesta.status_code == 403
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_aviso_sobrevive_a_un_incremental_posterior(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with _cliente(mundo) as c:
            await _post(c, run.id, 1)
        await _insert_run(mundo, kind="registro_incremental", unreadable=0)
        registro_biblioteca.reiniciar_para_pruebas()

        async with _cliente(mundo) as c:
            html = await _get(c)

        assert "Biblioteca registrada con 1 sin leer" in html
        assert "Registrar de todos modos" not in html

    async def test_interrumpido_no_ofrece_aceptar(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        registro_biblioteca._estado = EstadoRegistro(fase=FaseRegistro.INTERRUMPIDO, causa="OSError")
        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "Registrar de todos modos" not in html
        assert "Continuar el registro" in html


class TestIncrementalSigueConservador:

    async def test_tras_aceptar_un_incremental_con_ilegibles_sigue_bloqueado(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        assert (await _aceptar(mundo, run.id, 1)).ok

        async with mundo.fabrica() as s:
            adopter = LibraryAdopter(s)
            assert await adopter.ofrece_registro_incremental() is True
            inventario = await adopter.inventario()

        assert inventario.ilegibles >= 1
        assert inventario.se_puede_confirmar is False

    async def test_marcador_corrupto_avisa_y_no_ofrece(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        await _set_values(mundo, {CLAVE_MARCADOR: "false"})
        registro_biblioteca.reiniciar_para_pruebas()

        async with _cliente(mundo) as c:
            html = await _get(c)

        plano = " ".join(html.split())
        assert "Registrar de todos modos" not in html
        assert "marcador de adopción" in plano

    async def test_incremental_con_ilegibles_no_ofrece_aceptar(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        assert (await _aceptar(mundo, run.id, 1)).ok
        registro_biblioteca._estado = EstadoRegistro(
            fase=FaseRegistro.TERMINADO, incremental=True, ilegibles=1, total=1, procesados=1)

        async with _cliente(mundo) as c:
            html = await _get(c)

        assert "Registrar de todos modos" not in html
        assert "El registro de los archivos encontrados ha quedado incompleto" in html


    async def test_auth_mode_se_guarda_en_registro_evidencia_y_log(self, mundo, carpeta_cerrada, monkeypatch):
        import structlog

        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        monkeypatch.setattr("zascarr.services.aceptacion_adopcion.get_settings",
                            lambda: SimpleNamespace(auth_mode="password"))
        with structlog.testing.capture_logs() as logs:
            resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.ok
        assert (await _valores(mundo))[CLAVE_ACEPTACION]["auth_mode"] == "password"
        evidencia = await _runs(mundo, "adoption_acceptance")
        assert evidencia[0].details["auth_mode"] == "password"
        assert next(e for e in logs if e["event"] == "library_adopter.acceptance")["auth_mode"] == "password"


    async def test_el_cerrojo_del_registro_ocupado_rechaza_sin_escribir(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        antes = await _snapshot(mundo)
        async with mundo.motor.connect() as conexion:
            await conexion.execute(text("SELECT pg_advisory_lock(:k)"), {"k": CLAVE_CERROJO_REGISTRO})
            try:
                async with mundo.fabrica() as s:
                    resultado = await aceptar(s, run.id, 1, espera_cerrojo=0.1)
            finally:
                await conexion.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CLAVE_CERROJO_REGISTRO})

        assert resultado.status == 409 and resultado.reason == "in_progress"
        assert await _snapshot(mundo) == antes
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_un_rechazo_no_crea_la_fila_de_ajustes(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with mundo.fabrica() as s:
            await s.execute(text("DELETE FROM runtime_settings"))
            await s.commit()

        resultado = await _aceptar(mundo, run.id, 2)

        assert resultado.status == 409 and resultado.reason == "count_mismatch"
        async with mundo.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM runtime_settings"))).scalar() == 0


class TestPersistenciaDeLotesSinAcreditar:

    async def test_persiste_reverted_y_unknown_y_bloquea_la_aceptacion(self, mundo):
        ahora = datetime.now(UTC)
        report = AdoptionReport(started_at=ahora, finished_at=ahora,
                                unreadable=3, reverted=2, unknown=1)
        async with mundo.fabrica() as s:
            rid = await LibraryAdopter(s)._persist_run(report)
            await s.commit()

        run = next(r for r in await _runs(mundo, "adoption") if r.id == rid)
        assert run.details["reverted"] == 2 and run.details["unknown"] == 1
        assert (await _evaluar(mundo)).oferta is False
        resultado = await _aceptar(mundo, rid, 3)
        assert resultado.status == 409 and resultado.reason == "batch_unverified"
        assert CLAVE_MARCADOR not in await _valores(mundo)

    async def test_un_informe_viejo_sin_esas_claves_se_trata_como_cero(self, mundo):
        run = await _insert_run(mundo, kind="adoption", unreadable=1)

        assert (await _evaluar(mundo)).oferta is True
        assert (await _aceptar(mundo, run.id, 1)).reason == "accepted"

    async def test_el_camino_valido_crea_la_fila_si_falta_sin_paso_previo(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        async with mundo.fabrica() as s:
            await s.execute(text("DELETE FROM runtime_settings"))
            await s.commit()

        resultado = await _aceptar(mundo, run.id, 1)

        assert resultado.status == 200 and resultado.reason == "accepted"
        valores = await _valores(mundo)
        assert valores[CLAVE_MARCADOR] is True
        assert valores[CLAVE_ACEPTACION]["count"] == 1


async def _crear_trigger_fallo_evidencia(m: Mundo) -> None:
    async with m.fabrica() as s:
        await s.execute(text("DROP TRIGGER IF EXISTS zascarr_fallo_evidencia ON import_runs"))
        await s.execute(text("DROP FUNCTION IF EXISTS zascarr_fallo_evidencia()"))
        await s.execute(text("""
            CREATE FUNCTION zascarr_fallo_evidencia() RETURNS trigger AS $$
            BEGIN
              IF NEW.details->>'kind' = 'adoption_acceptance' THEN
                RAISE EXCEPTION 'fallo_evidencia';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """))
        await s.execute(text("""
            CREATE TRIGGER zascarr_fallo_evidencia BEFORE INSERT ON import_runs
            FOR EACH ROW EXECUTE FUNCTION zascarr_fallo_evidencia()
        """))
        await s.commit()


async def _quitar_trigger_fallo_evidencia(m: Mundo) -> None:
    async with m.fabrica() as s:
        await s.execute(text("DROP TRIGGER IF EXISTS zascarr_fallo_evidencia ON import_runs"))
        await s.execute(text("DROP FUNCTION IF EXISTS zascarr_fallo_evidencia()"))
        await s.commit()


class TestAvisoPermanenteEIntegridad:

    async def test_aviso_visible_tras_un_incremental_real_y_tras_reiniciar(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        assert (await _aceptar(mundo, run.id, 1)).ok

        nuevo = mundo.lib / "Nuevos" / "Nuevo 01.cbz"
        _cbz(nuevo, "n")
        registro_biblioteca.iniciar(mundo.fabrica, alcance=frozenset({str(nuevo)}))
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        estado = registro_biblioteca.estado_actual()
        assert estado.incremental and estado.fase is FaseRegistro.TERMINADO

        async with _cliente(mundo) as c:
            html = await _get(c)
        assert "sin leer" in html and "Biblioteca registrada con 1" in html

        registro_biblioteca.reiniciar_para_pruebas()
        async with _cliente(mundo) as c:
            recarga = await _get(c)
        assert "sin leer" in recarga and "Biblioteca registrada con 1" in recarga

    async def test_el_aviso_usa_la_fecha_de_aceptacion_no_la_del_informe(self, mundo):
        report = AdoptionReport(
            started_at=datetime(2025, 12, 31, 10, 0, tzinfo=UTC),
            finished_at=datetime(2025, 12, 31, 11, 0, tzinfo=UTC),
            unreadable=1,
        )
        async with mundo.fabrica() as s:
            run_id = await LibraryAdopter(s)._persist_run(report)
            await s.commit()

        assert (await _aceptar(mundo, run_id, 1)).ok
        aceptado = datetime.fromisoformat((await _valores(mundo))[CLAVE_ACEPTACION]["accepted_at"])
        esperada = fecha_llana(aceptado)

        registro_biblioteca.reiniciar_para_pruebas()
        async with _cliente(mundo) as c:
            html = await _get(c)

        plano = " ".join(html.split())
        assert f"Biblioteca registrada con 1 sin leer el {esperada}." in plano
        assert "2025" not in plano

    async def test_si_falla_la_evidencia_se_revierte_marcador_y_registro(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        antes = await _snapshot(mundo)
        await _crear_trigger_fallo_evidencia(mundo)
        try:
            with pytest.raises(Exception, match="fallo_evidencia"):
                async with mundo.fabrica() as s:
                    await aceptar(s, run.id, 1)
        finally:
            await _quitar_trigger_fallo_evidencia(mundo)

        assert await _snapshot(mundo) == antes
        valores = await _valores(mundo)
        assert CLAVE_MARCADOR not in valores
        assert CLAVE_ACEPTACION not in valores
        assert await _runs(mundo, "adoption_acceptance") == []

    async def test_aviso_en_la_lista_de_archivos_nuevos(self, mundo, carpeta_cerrada):
        await _adopt(mundo)
        run = await _ultima_adopcion(mundo)
        assert (await _aceptar(mundo, run.id, 1)).ok
        _cbz(mundo.lib / "Nuevos" / "Nuevo 02.cbz", "z")

        async with _cliente(mundo) as c:
            respuesta = await c.get("/ui/auditoria/nuevos")

        assert respuesta.status_code == 200
        assert "sin leer" in respuesta.text and "Biblioteca registrada con 1" in respuesta.text
        assert "Archivos encontrados sin registrar" in respuesta.text
