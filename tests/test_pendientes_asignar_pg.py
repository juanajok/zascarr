# ruff: noqa: E501
"""`POST /ui/pendientes/{id}/asignar` conectado al servicio recuperable (ADR 0006) — Postgres real.

Qué se prueba aquí y no con una sesión simulada: que el endpoint ya NO mueve el fichero con la sesión de
la petición. El servicio abre sus propias sesiones y confirma por su cuenta, así que lo observable (fichero
movido, `Issue`, alias, motivo de la colisión) hay que mirarlo desde OTRA sesión, con la BD real. Se saltan
sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_asignacion_servicio_pg import Mundo
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, Issue, IssueFormat
from zascarr.services.asignacion import EstadoResultado
from zascarr.web import pendientes
from zascarr.web.pendientes import RESPUESTAS, interpretar

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
HTMX = {"HX-Request": "true"}


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def mundo(url_bd, tmp_path):
    m = await Mundo(url_bd, tmp_path).sembrar()
    yield m
    await m.cerrar()


@pytest.fixture
def cliente_de(mundo, monkeypatch):
    """Cliente HTTP sobre la app real, con el servicio y la sesión de la petición apuntando a la BD de prueba."""
    def crear(**kw_servicio):
        monkeypatch.setattr(pendientes, "servicio_por_defecto", lambda: mundo.servicio(**kw_servicio))

        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                 headers={"Origin": "http://localhost"})
    yield crear
    app.dependency_overrides.pop(get_db, None)


def _datos(mundo, numero="12"):
    return {"series_id": str(mundo.serie_id), "issue_number": numero}


def _url(mundo):
    return f"/ui/pendientes/{mundo.file_id}/asignar"


class TestAsignarConectadoAlServicio:

    async def test_asigna_mueve_el_fichero_y_deja_issue_y_alias(self, mundo, cliente_de):
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        assert r.status_code == 200 and r.text.strip() == ""      # la tarjeta desaparece
        e = await mundo.estado()
        assert e.ops == ["limpiada"] and not e.origen_existe and len(e.destinos) == 1
        assert e.issue_id is not None and e.issues == 1 and e.alias == 1

    async def test_repetir_la_peticion_no_duplica_nada(self, mundo, cliente_de):
        async with cliente_de() as c:
            await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
            r = await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        assert r.status_code == 200
        e = await mundo.estado()
        assert e.ops == ["limpiada"] and e.issues == 1 and len(e.destinos) == 1

    async def test_el_resultado_sobrevive_al_cierre_de_la_peticion(self, mundo, cliente_de):
        """Regresión del mecanismo: antes el commit lo hacía `get_db` DESPUÉS de enviar la respuesta."""
        async with cliente_de() as c:
            await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        async with mundo.fabrica() as s:      # sesión nueva: no ve nada que no esté confirmado
            f = await s.get(File, mundo.file_id)
        assert f.issue_id is not None and f.file_path != str(mundo.origen)

    async def test_serie_inexistente_da_400_y_no_toca_el_fichero(self, mundo, cliente_de):
        from uuid import uuid4
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data={"series_id": str(uuid4()), "issue_number": "12"}, headers=HTMX)
        assert r.status_code == 400
        assert 'id="card-' in r.text and "ya no existen" in r.text      # la tarjeta sigue, con el motivo
        e = await mundo.estado()
        assert e.origen_existe and e.ops == [] and e.issue_id is None

    async def test_numero_vacio_da_400(self, mundo, cliente_de):
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data=_datos(mundo, "   "), headers=HTMX)
        assert r.status_code == 400 and "número" in r.text
        assert (await mundo.estado()).origen_existe

    async def test_archivo_inexistente_da_400(self, mundo, cliente_de):
        from uuid import uuid4
        async with cliente_de() as c:
            r = await c.post(f"/ui/pendientes/{uuid4()}/asignar", data=_datos(mundo), headers=HTMX)
        assert r.status_code == 400 and "ya no existen" in r.text


class TestColisionDeEdiciones:
    """B15: el número compartido entre ediciones se rechaza, se explica y el motivo SE GUARDA."""

    async def _sembrar_otra_edicion(self, mundo):
        async with mundo.fabrica() as s:
            s.add(Issue(series_id=mundo.serie_id, issue_number="12", format=IssueFormat.OMNIBUS))
            await s.commit()

    async def test_htmx_recibe_la_tarjeta_con_el_aviso_no_un_json(self, mundo, cliente_de):
        await self._sembrar_otra_edicion(mundo)
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        assert r.status_code == 409
        assert "text/html" in r.headers["content-type"] and 'id="card-' in r.text
        assert "número compartido entre ediciones" in r.text
        assert "detail" not in r.text                  # el 409 JSON de FastAPI no se pinta en la página

    async def test_cliente_no_htmx_recibe_409_json(self, mundo, cliente_de):
        await self._sembrar_otra_edicion(mundo)
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data=_datos(mundo))
        assert r.status_code == 409 and "número compartido entre ediciones" in r.json()["detail"]

    async def test_el_motivo_persiste_tras_cerrar_la_sesion_y_el_fichero_no_se_mueve(self, mundo, cliente_de):
        await self._sembrar_otra_edicion(mundo)
        async with cliente_de() as c:
            await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        async with mundo.fabrica() as s:               # sesión distinta: solo ve lo confirmado
            motivo = (await s.execute(text("SELECT metadata->>'review_motivo' FROM files WHERE id = :f"),
                                      {"f": mundo.file_id})).scalar()
        assert motivo == "número compartido entre ediciones"
        e = await mundo.estado()
        assert e.origen_existe and e.issue_id is None and e.ops == [] and e.destinos == []   # rechazada al preparar: ni operación ni copia

    async def test_la_tarjeta_siguiente_muestra_el_motivo_guardado(self, mundo, cliente_de):
        await self._sembrar_otra_edicion(mundo)
        async with cliente_de() as c:
            await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
            r = await c.get("/ui/pendientes")
        assert r.status_code == 200 and "número compartido entre ediciones" in r.text


class TestResultadosRecuperables:
    """«Asignado con aviso» y «pendiente» no se esconden: el coleccionista ve qué pasó y los datos no se pierden."""

    async def test_limpieza_pendiente_es_exito_con_aviso(self, mundo, cliente_de):
        def borrar_fallido(_ruta):
            raise OSError("disco de solo lectura")
        async with cliente_de(borrar=borrar_fallido) as c:
            r = await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        assert r.status_code == 200 and "retirar el archivo original" in r.text
        assert "disco de solo lectura" not in r.text       # el motivo técnico no llega a pantalla
        e = await mundo.estado()
        assert e.ops == ["confirmada"] and e.origen_existe and e.issue_id is not None and len(e.destinos) == 1

    async def test_pendiente_devuelve_503_con_la_tarjeta_delante(self, mundo, cliente_de, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        original = AsyncSession.commit
        confirmaciones = {"n": 0}

        async def commit_que_no_llega(self):
            # El primer commit de la preparación pasa; el que confirma el resultado falla de forma definitiva.
            confirmaciones["n"] += 1
            if confirmaciones["n"] >= 3:
                raise ConnectionError("se cayó la base de datos")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_que_no_llega)
        async with cliente_de() as c:
            r = await c.post(_url(mundo), data=_datos(mundo), headers=HTMX)
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert r.status_code in (503, 500) and 'id="card-' in r.text
        assert "se cayó" not in r.text
        e = await mundo.estado()
        assert e.origen_existe or e.destinos                # nunca se pierde el contenido


class TestRespuestasExhaustivas:

    @pytest.mark.parametrize("estado", list(EstadoResultado))
    def test_todo_estado_del_servicio_tiene_respuesta_explicita(self, estado):
        assert estado in RESPUESTAS, f"{estado} no tiene respuesta explícita: caería en el 500 genérico"

    def test_solo_los_estados_con_asignacion_hecha_quitan_la_tarjeta(self):
        """`asignado=True` ⇔ el archivo YA está asignado (y entonces la respuesta es 200)."""
        asignados = {e for e, r in RESPUESTAS.items() if r.asignado}
        assert asignados == {EstadoResultado.ASIGNADO, EstadoResultado.YA_ASIGNADO,
                             EstadoResultado.ASIGNADO_LIMPIEZA_PENDIENTE, EstadoResultado.REPARACION_PENDIENTE}
        assert all(RESPUESTAS[e].status == 200 for e in asignados)
        assert all(r.status != 200 for e, r in RESPUESTAS.items() if e not in asignados)

    def test_estado_desconocido_no_queda_mudo(self):
        from types import SimpleNamespace
        assert interpretar(SimpleNamespace(estado="inventado", motivo="x", destino=None)).status == 500
