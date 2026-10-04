# ruff: noqa: E501
"""Servicio de asignación (ADR 0006) frente al resto de la aplicación — Postgres real y ficheros reales.

Coordinación con otros escritores de `files`, alias, hash obsoleto, reconciliación al arrancar (función y
`lifespan`) y el 409 al borrar con una asignación viva. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import RAIZ, bd_efimera_sync, migrar_a_head, url_asyncpg
from tests.test_asignacion_servicio_pg import Mundo, hacer_cbz
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    LocalAlias,
    Series,
)
from zascarr.services.asignacion import (
    EstadoResultado,
    conflicto_por_operacion_viva,
    reconciliar_al_arrancar,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


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


async def _destino_de(mundo) -> Path:
    async with mundo.fabrica() as s:
        return Path((await s.execute(text("SELECT destino FROM asignacion_operaciones ORDER BY creada DESC LIMIT 1"))).scalar())


class TestCoordinacionConOtrosEscritores:
    """La restricción única de `files.file_path` — no una consulta previa — decide frente a escritores concurrentes."""

    @pytest.mark.asyncio
    async def test_un_destino_ya_registrado_por_otra_fila_se_salta_al_reservar(self, mundo):
        canonico = mundo.lib / "Comics" / "Saga del Faro (2010)" / "Saga del Faro #012.cbz"
        async with mundo.fabrica() as s:        # una fila ajena registra el nombre canónico (sin fichero en disco)
            s.add(File(id=uuid4(), file_path=str(canonico), file_name=canonico.name, file_format=FileFormat.CBZ,
                       sha256_hash="c" * 64))
            await s.commit()
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "asignado" and e.ruta.endswith("#012 (1).cbz")
        assert e.ops == ["limpiada"]                       # UNA sola operación: no hubo intento fallido y reintento

    @pytest.mark.asyncio
    async def test_otra_fila_que_registra_el_destino_mientras_se_copia_gana_la_restriccion_unica(self, mundo):
        """Aparece DESPUÉS de reservar y publicar: la consulta previa ya no ayuda; decide la restricción de la BD."""
        hecho = {"n": 0}

        async def intruso(punto):
            if punto == "tras_publicar" and hecho["n"] == 0:
                hecho["n"] += 1
                destino = await _destino_de(mundo)
                async with mundo.fabrica() as s:
                    s.add(File(id=uuid4(), file_path=str(destino), file_name=destino.name, file_format=FileFormat.CBZ,
                               sha256_hash="d" * 64))
                    await s.commit()
        servicio = mundo.servicio(gancho=intruso)
        op = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        r = await servicio._ejecutar(op)                        # UN intento
        e = await mundo.estado()
        assert r.estado == "destino_ocupado"
        assert e.ops == ["cancelada"] and e.origen_existe and e.issue_id is None and e.ruta == str(mundo.origen)
        assert e.destinos == [] and e.partes == []              # la copia propia se retiró: no queda basura
        # La fila ajena sigue intacta y el reintento usa otro nombre.
        r2 = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        assert r2.estado == "asignado" and (await mundo.estado()).ruta.endswith("(1).cbz")

    @pytest.mark.asyncio
    async def test_si_aparece_otra_edicion_mientras_se_copia_se_cancela_y_no_queda_basura(self, mundo):
        hecho = {"n": 0}

        async def otra_edicion(punto):
            if punto == "tras_publicar" and hecho["n"] == 0:
                hecho["n"] += 1
                async with mundo.fabrica() as s:
                    s.add(Issue(series_id=mundo.serie_id, issue_number="12", format=IssueFormat.OMNIBUS))
                    await s.commit()
        r = await mundo.servicio(gancho=otra_edicion).asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "colision_edicion"
        assert e.ops == ["cancelada"] and e.origen_existe and e.destinos == [] and e.partes == []
        assert e.issue_id is None and e.ruta == str(mundo.origen)

    @pytest.mark.asyncio
    async def test_no_se_retira_una_copia_que_no_es_la_propia(self, mundo):
        """Si por lo que sea el contenido del destino ya no es el verificado, `_abandonar` no lo borra."""
        hecho = {"n": 0}

        async def altera_y_registra(punto):
            if punto == "tras_publicar" and hecho["n"] == 0:
                hecho["n"] += 1
                destino = await _destino_de(mundo)
                datos = bytearray(destino.read_bytes())
                datos[40] ^= 0xFF
                destino.write_bytes(bytes(datos))
                async with mundo.fabrica() as s:
                    s.add(File(id=uuid4(), file_path=str(destino), file_name=destino.name, file_format=FileFormat.CBZ,
                               sha256_hash="e" * 64))
                    await s.commit()
        servicio = mundo.servicio(gancho=altera_y_registra)
        op = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        r = await servicio._ejecutar(op)
        e = await mundo.estado()
        assert r.estado == "destino_ocupado" and len(e.destinos) == 1       # el fichero alterado NO se borró


class TestHashObsoleto:

    @pytest.mark.asyncio
    async def test_un_sha256_obsoleto_en_la_bd_no_provoca_un_fallo_espurio(self, mundo):
        """Tras reescribir ComicInfo (B6) `File.sha256_hash` puede no ser el del fichero actual."""
        async with mundo.fabrica() as s:
            f = await s.get(File, mundo.file_id)
            f.sha256_hash = "f" * 64
            await s.commit()
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "asignado" and e.ops == ["limpiada"]
        assert hashlib.sha256(Path(e.ruta).read_bytes()).hexdigest() == mundo.sha


class TestAprenderAlias:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("aprender,esperado", [(True, 1), (False, 0)])
    async def test_el_alias_solo_se_aprende_si_se_pide(self, mundo, aprender, esperado):
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12", aprender_alias=aprender)
        async with mundo.fabrica() as s:
            alias = (await s.execute(select(LocalAlias).where(LocalAlias.series_id == mundo.serie_id))).scalars().all()
            guardado = (await s.execute(text("SELECT aprender_alias FROM asignacion_operaciones"))).scalar()
        assert r.estado == "asignado" and len(alias) == esperado and guardado is aprender

    @pytest.mark.asyncio
    async def test_la_peticion_completa_sobrevive_a_un_reinicio(self, mundo):
        """`aprender_alias=False` se persiste: la reconciliación, en otro proceso, no lo olvida."""
        guion = textwrap.dedent(f"""
            import asyncio, os
            from pathlib import Path
            from uuid import UUID
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from zascarr.services.asignacion import AsignacionService
            async def gancho(p):
                if p == "tras_publicar":
                    os._exit(137)
            async def main():
                m = create_async_engine({url_asyncpg(mundo.url)!r})
                await AsignacionService(async_sessionmaker(m, expire_on_commit=False), Path({str(mundo.lib)!r}),
                                        gancho=gancho).asignar(UUID({str(mundo.file_id)!r}), UUID({str(mundo.serie_id)!r}),
                                                               "12", aprender_alias=False)
            asyncio.run(main())
        """)
        p = subprocess.run([sys.executable, "-c", guion], env=dict(os.environ, PYTHONPATH=str(RAIZ / "src")),
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 137, p.stderr[-500:]
        assert [r.estado for r in await mundo.servicio().reconciliar()] == ["asignado"]
        async with mundo.fabrica() as s:
            assert (await s.execute(select(LocalAlias).where(LocalAlias.series_id == mundo.serie_id))).scalars().all() == []


class TestReconciliarAlArrancar:

    @pytest.mark.asyncio
    async def test_cierra_lo_que_quedo_vivo_y_cuenta_las_operaciones(self, mundo):
        subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
            import asyncio, os
            from pathlib import Path
            from uuid import UUID
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from zascarr.services.asignacion import AsignacionService
            async def g(p):
                if p == "tras_confirmar":
                    os._exit(137)
            async def main():
                m = create_async_engine({url_asyncpg(mundo.url)!r})
                await AsignacionService(async_sessionmaker(m, expire_on_commit=False), Path({str(mundo.lib)!r}),
                                        gancho=g).asignar(UUID({str(mundo.file_id)!r}), UUID({str(mundo.serie_id)!r}), "12")
            asyncio.run(main())"""
        )], env=dict(os.environ, PYTHONPATH=str(RAIZ / "src")), capture_output=True, text=True, timeout=120)
        assert (await mundo.estado()).ops == ["confirmada"]
        assert await reconciliar_al_arrancar(mundo.servicio()) == 1
        assert (await mundo.estado()).ops == ["limpiada"]
        assert await reconciliar_al_arrancar(mundo.servicio()) == 0         # idempotente: nada vivo

    @pytest.mark.asyncio
    async def test_nunca_propaga_una_excepcion(self):
        class Roto:
            async def reconciliar(self):
                raise RuntimeError("la BD se cayó")
        assert await reconciliar_al_arrancar(Roto()) == 0

    @pytest.mark.asyncio
    async def test_no_recorre_la_biblioteca(self, mundo, monkeypatch):
        def prohibido(*a, **k):
            raise AssertionError("la reconciliación no debe escanear la biblioteca")
        monkeypatch.setattr(Path, "rglob", prohibido)
        monkeypatch.setattr(Path, "iterdir", prohibido)
        monkeypatch.setattr(os, "walk", prohibido)
        assert await reconciliar_al_arrancar(mundo.servicio()) == 0

    def test_el_lifespan_la_lanza_en_segundo_plano_cuando_la_bd_esta_disponible(self, url_bd, tmp_path, monkeypatch):
        """Arranque REAL de la aplicación con una operación huérfana en la BD: se cierra sola."""
        from fastapi.testclient import TestClient

        import zascarr.database as dbmod
        from zascarr.main import app

        lib = tmp_path / "lib"
        origen, destino = lib / "_Unsorted" / "x.cbz", lib / "Comics" / "S" / "x.cbz"
        contenido = hacer_cbz(origen, "k")
        destino.parent.mkdir(parents=True)
        destino.write_bytes(contenido)
        sha = hashlib.sha256(contenido).hexdigest()

        async def sembrar():
            m = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
            fab = async_sessionmaker(m, expire_on_commit=False)
            async with m.begin() as c:
                await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases CASCADE"))
            async with fab() as s:
                serie = Series(id=uuid4(), title="S", tradition=ComicTradition.AMERICAN)
                s.add(serie)
                await s.flush()
                issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1", format=IssueFormat.SINGLE_ISSUE)
                s.add(issue)
                await s.flush()
                f = File(id=uuid4(), file_path=str(destino), file_name=destino.name, file_format=FileFormat.CBZ,
                         sha256_hash=sha, issue_id=issue.id, file_size_bytes=len(contenido))
                s.add(f)
                await s.flush()
                st = origen.stat()
                await s.execute(text(
                    "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                    "mtime_ns, sha256, issue_number, formato, epoca) VALUES (:f, :s, 'confirmada', :o, :d, :t, :sz, :mt, "
                    ":sha, '1', 'single_issue', 1)"),
                    {"f": f.id, "s": serie.id, "o": str(origen), "d": str(destino), "t": str(destino) + ".part",
                     "sz": st.st_size, "mt": st.st_mtime_ns, "sha": sha})
                await s.commit()
            await m.dispose()

        async def estado():
            m = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
            async with m.connect() as c:
                e = (await c.execute(text("SELECT estado::text FROM asignacion_operaciones"))).scalar()
            await m.dispose()
            return e
        asyncio.run(sembrar())
        motor = create_async_engine(url_asyncpg(url_bd), pool_size=5, max_overflow=2)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        monkeypatch.setattr(dbmod, "engine", motor)
        monkeypatch.setattr(dbmod, "async_session_factory", fab)
        with TestClient(app, raise_server_exceptions=False):
            for _ in range(100):
                if asyncio.run(estado()) == "limpiada":
                    break
                import time
                time.sleep(0.2)
        assert asyncio.run(estado()) == "limpiada" and not origen.exists() and destino.exists()


class TestConflictoPorOperacionViva:
    """El 409 traduce SOLO la restricción concreta, con rollback, y antes de que haya operaciones vivas en producción."""

    @staticmethod
    def _cliente(url, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import zascarr.database as dbmod
        from zascarr.api.series import router
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        monkeypatch.setattr(dbmod, "async_session_factory", async_sessionmaker(motor, expire_on_commit=False))
        app = FastAPI()
        app.include_router(router, prefix="/api")
        return TestClient(app, raise_server_exceptions=False)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["preparada", "confirmada"])
    async def test_borrar_una_serie_con_asignacion_viva_da_409_y_no_pierde_nada(self, mundo, monkeypatch, estado):
        async with mundo.motor.begin() as c:
            await c.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST(:e AS asignacion_estado), '/a', '/b', '/c', 1, 1, "
                "repeat('a', 64), '12', 'single_issue')"), {"f": mundo.file_id, "s": mundo.serie_id, "e": estado})
        cliente = self._cliente(mundo.url, monkeypatch)
        r = await asyncio.to_thread(cliente.delete, f"/api/series/{mundo.serie_id}")
        assert r.status_code == 409 and "asignación de archivos en curso" in r.json()["detail"]
        async with mundo.fabrica() as s:
            assert await s.get(Series, mundo.serie_id) is not None
            assert (await s.execute(text("SELECT count(*) FROM asignacion_operaciones"))).scalar() == 1

    @pytest.mark.asyncio
    async def test_con_la_asignacion_cerrada_el_borrado_procede(self, mundo, monkeypatch):
        async with mundo.motor.begin() as c:
            await c.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, 'limpiada', '/a', '/b', '/c', 1, 1, "
                "repeat('a', 64), '12', 'single_issue')"), {"f": mundo.file_id, "s": mundo.serie_id})
        cliente = self._cliente(mundo.url, monkeypatch)
        r = await asyncio.to_thread(cliente.delete, f"/api/series/{mundo.serie_id}")
        assert r.status_code == 204
        async with mundo.fabrica() as s:
            assert await s.get(Series, mundo.serie_id) is None

    @pytest.mark.asyncio
    async def test_otro_error_de_integridad_no_se_disfraza_de_409(self, mundo, monkeypatch):
        """Un `IntegrityError` ajeno sigue siendo un error (aquí, un 500), no el conflicto de la asignación."""
        cliente = self._cliente(mundo.url, monkeypatch)
        import zascarr.api.series as api

        async def flush_roto(self, *a, **k):
            raise IntegrityError("DELETE", {}, Exception("duplicate key value violates unique constraint «otra_cosa»"))
        monkeypatch.setattr(api.AsyncSession, "flush", flush_roto)
        r = await asyncio.to_thread(cliente.delete, f"/api/series/{mundo.serie_id}")
        assert r.status_code == 500

    @pytest.mark.asyncio
    async def test_solo_esa_restriccion_se_reconoce(self, mundo):
        serie, f1 = mundo.serie_id, mundo.file_id
        # La del CHECK de operación viva.
        async with mundo.motor.begin() as c:
            await c.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, 'preparada', '/a', '/b', '/c', 1, 1, "
                "repeat('a', 64), '12', 'single_issue')"), {"f": f1, "s": serie})
        with pytest.raises(IntegrityError) as viva:
            async with mundo.motor.begin() as c:
                await c.execute(text("DELETE FROM files WHERE id = :f"), {"f": f1})
        assert conflicto_por_operacion_viva(viva.value) is True
        # Una ÚNICA distinta (reservar dos veces el mismo archivo) y una de clave foránea: no son ese conflicto.
        with pytest.raises(IntegrityError) as unica:
            async with mundo.motor.begin() as c:
                await c.execute(text(
                    "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                    "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, 'preparada', '/a2', '/b2', '/c2', 1, 1, "
                    "repeat('a', 64), '12', 'single_issue')"), {"f": f1, "s": serie})
        assert conflicto_por_operacion_viva(unica.value) is False
        with pytest.raises(IntegrityError) as fk:
            async with mundo.motor.begin() as c:
                await c.execute(text(
                    "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                    "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, 'limpiada', '/a3', '/b3', '/c3', 1, 1, "
                    "repeat('a', 64), '12', 'single_issue')"), {"f": uuid4(), "s": serie})
        assert conflicto_por_operacion_viva(fk.value) is False


def test_los_resultados_recuperables_no_incluyen_destino_ocupado():
    from zascarr.services.asignacion import RESULTADOS_RECUPERABLES
    assert EstadoResultado.DESTINO_OCUPADO not in RESULTADOS_RECUPERABLES
    assert {EstadoResultado.PENDIENTE, EstadoResultado.REPARACION_PENDIENTE,
            EstadoResultado.ASIGNADO_LIMPIEZA_PENDIENTE} <= RESULTADOS_RECUPERABLES
