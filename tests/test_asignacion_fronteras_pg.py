# ruff: noqa: E501
"""V6a, auditoría (criterio 1): las MISMAS fronteras de fallo, ahora contra el endpoint conectado al servicio.

Historia del módulo. Se escribió como **caracterización** de `ReviewService.assign_to_series` con el endpoint
real, Postgres real y ficheros reales (PR #75): fijaba, a propósito, los defectos de entonces (fichero movido
con la BD revertida por cuatro caminos; el `commit` de `get_db` después de responder; ningún reconciliador;
solapamiento seguro solo por el índice único de `Issue`). El análisis sigue en
`docs/design/auditoria-mover-y-sesion.md`. Al conectar la asignación individual al servicio recuperable
(ADR 0006) esas pruebas **se cambian a propósito**, como se anunció: cada frontera conserva su nombre y
ahora afirma el comportamiento nuevo —o la prueba que lo cubre con más detalle—.

El endpoint se prueba SIN sustituir `servicio_por_defecto`: el motor y la biblioteca llegan por
`zascarr.database` y `get_settings`, como en producción. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    LocalAlias,
    MetadataSource,
    Series,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    """Una BD efímera y MIGRADA para todo el módulo (crearla y migrarla cuesta unos segundos)."""
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


def hacer_cbz(ruta: Path, marca: str = "x") -> bytes:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", (marca * 5000).encode())
    return ruta.read_bytes()


class Entorno:
    """Biblioteca real en `tmp_path`, BD real, y un endpoint real con `get_db` real."""

    def __init__(self, url: str, tmp_path: Path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import zascarr.database as dbmod
        from zascarr.web.pendientes import router

        self.url = url
        self.lib = tmp_path / "lib"
        self.dl = tmp_path / "dl"
        for d in (self.lib, self.dl):
            d.mkdir()
        # NullPool: el endpoint corre en el bucle del TestClient y la comprobación en el de la prueba.
        self.engine = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fabrica = async_sessionmaker(self.engine, expire_on_commit=False)
        monkeypatch.setattr(dbmod, "async_session_factory", self.fabrica)
        from zascarr.config import get_settings
        ajustes = get_settings().model_copy(update=dict(
            library_path=self.lib, downloads_path=self.dl, transmission_download_dir=str(self.dl),
            amule_incoming_dir=str(self.dl / "amule"), asignacion_simultaneas=1))
        monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
        app = FastAPI()
        app.include_router(router)
        self.app = app
        self.cliente = TestClient(app, raise_server_exceptions=False)
        self.serie_id: UUID | None = None
        self.file_id: UUID | None = None
        self.origen: Path | None = None

    async def sembrar(self, nombre="Saga del Faro 12.cbz", marca="a"):
        # La BD es EFÍMERA y de este módulo: se vacía entre pruebas para que el recuento de ficheros de
        # la biblioteca (y el guardarraíl de desaparición masiva de B7) dependa solo de cada prueba.
        async with self.engine.begin() as c:
            await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, import_runs CASCADE"))
        self.origen = self.lib / "_Unsorted" / nombre
        contenido = hacer_cbz(self.origen, marca)
        async with self.fabrica() as s:
            serie = Series(id=uuid4(), title=f"Saga {uuid4().hex[:6]}", tradition=ComicTradition.AMERICAN,
                           start_year=2010)
            f = File(id=uuid4(), file_path=str(self.origen), file_name=nombre, file_format=FileFormat.CBZ,
                     file_size_bytes=len(contenido), sha256_hash=hashlib.sha256(contenido).hexdigest(),
                     metadata_={"match_status": "unsorted"})
            s.add_all([serie, f])
            await s.commit()
            self.serie_id, self.file_id = serie.id, f.id
            self.serie_titulo = serie.title
        return self

    def asignar(self, numero="12"):
        return self.cliente.post(f"/ui/pendientes/{self.file_id}/asignar", headers={"HX-Request": "true"},
                                 data={"series_id": str(self.serie_id), "issue_number": numero})

    async def bd(self) -> SimpleNamespace:
        async with self.fabrica() as s:
            f = await s.get(File, self.file_id)
            issues = (await s.execute(select(Issue).where(Issue.series_id == self.serie_id))).scalars().all()
            alias = (await s.execute(select(LocalAlias).where(LocalAlias.series_id == self.serie_id))).scalars().all()
            ops = (await s.execute(text("SELECT estado FROM asignacion_operaciones ORDER BY creada"))).scalars().all()
            return SimpleNamespace(
                ruta=f.file_path, issue_id=f.issue_id, fuente=f.metadata_source, is_missing=f.is_missing,
                issues=len(issues), alias=len(alias), ops=list(ops))

    def disco(self) -> SimpleNamespace:
        todos = sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*.cbz"))
        return SimpleNamespace(
            origen_existe=self.origen.exists(), cbz=todos,
            destinos=[p for p in todos if not p.startswith("_Unsorted")])

    async def cerrar(self):
        await self.engine.dispose()


@pytest.fixture
async def ent(url_bd, tmp_path, monkeypatch):
    e = await Entorno(url_bd, tmp_path, monkeypatch).sembrar()
    yield e
    await e.cerrar()


class TestCaminoFeliz:

    @pytest.mark.asyncio
    async def test_mueve_y_confirma(self, ent):
        r = ent.asignar()
        assert r.status_code == 200
        bd, disco = await ent.bd(), ent.disco()
        assert not disco.origen_existe and len(disco.destinos) == 1
        assert bd.ruta.endswith(disco.destinos[0]) and bd.issue_id is not None
        assert bd.fuente == MetadataSource.MANUAL.value and bd.issues == 1 and bd.alias == 1
        assert bd.ops == ["limpiada"]


class TestFronterasDeFallo:
    """Cada prueba inyecta UN fallo en un punto distinto y mira disco y BD después."""

    @pytest.mark.asyncio
    async def test_fallo_antes_de_mover_no_deja_nada(self, ent, monkeypatch):
        def publicar_roto(temporal, destino):
            raise OSError("disco de destino de solo lectura")
        monkeypatch.setattr("zascarr.services.asignacion._publicar", publicar_roto)
        r = ent.asignar()
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500 and 'id="card-' in r.text         # la tarjeta sigue con su aviso
        assert "disco de destino" not in r.text and "No se pudo asignar" in r.text
        assert disco.origen_existe and disco.destinos == []            # disco intacto
        assert bd.issue_id is None and bd.ruta == str(ent.origen)

    @pytest.mark.asyncio
    async def test_antes_fallo_despues_de_mover_dejaba_el_fichero_movido_y_la_bd_revertida(self, ent, monkeypatch):
        """Era el punto que `CLAUDE.md` §3.1.2 marcaba «pendiente de auditar». Ahora el movimiento es una
        COPIA verificada y el original solo se borra tras confirmar: un fallo al confirmar deja el original."""
        original = AsyncSession.commit
        n = {"c": 0}

        async def commit_que_falla_al_confirmar(self):
            n["c"] += 1
            if n["c"] == 3:                 # 1.º: preparar; 2.º: tomar la operación; 3.º: confirmar fichero+Issue+alias
                raise RuntimeError("fallo al confirmar")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_que_falla_al_confirmar)
        r = ent.asignar()
        monkeypatch.setattr(AsyncSession, "commit", original)
        disco, bd = ent.disco(), await ent.bd()
        assert disco.origen_existe                                     # NUNCA se pierde el original
        assert r.status_code == 503 and 'id="card-' in r.text          # y el coleccionista ve que está pendiente
        assert bd.ops == ["preparada"] and bd.issue_id is None         # operación VIVA y sin confirmar: la retoma la reconciliación
        assert len(disco.destinos) == 1                                # la copia ya publicada se conserva, no se borra

    @pytest.mark.asyncio
    async def test_antes_el_commit_de_get_db_fallaba_tras_dar_exito_al_cliente(self, ent, monkeypatch):
        """Era el defecto (2) de la auditoría: el `commit` de `get_db` corre tras enviar la respuesta y, si
        fallaba, el cliente ya tenía su 200 sobre una BD sin cambios. Ahora el servicio confirma ANTES de
        responder: se hace fallar SOLO el commit de la sesión de la petición y se comprueba, desde otra
        sesión, que la asignación ya confirmada NO se revierte."""
        from zascarr.database import get_db
        intentos = {"n": 0}
        original = AsyncSession.commit

        async def commit_solo_de_la_peticion(self):
            if self.info.get("peticion"):
                intentos["n"] += 1
                raise RuntimeError("el commit de la petición falló (conexión perdida)")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_solo_de_la_peticion)

        async def get_db_de_la_peticion():                          # mismo ciclo que `get_db`, con sesión marcada
            async with ent.fabrica() as s:
                s.sync_session.info["peticion"] = True
                try:
                    yield s
                    await s.commit()
                except Exception:
                    await s.rollback()
                    raise
        ent.app.dependency_overrides[get_db] = get_db_de_la_peticion
        r = ent.asignar()
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert intentos["n"] >= 1                                     # el fallo SÍ se inyectó en la petición
        bd, disco = await ent.bd(), ent.disco()                       # sesión distinta de la de la petición
        assert r.status_code == 200
        assert bd.issue_id is not None and bd.ops == ["limpiada"]
        assert bd.ruta.endswith(disco.destinos[0]) and not disco.origen_existe

    @pytest.mark.asyncio
    async def test_antes_un_fallo_al_construir_la_respuesta_dejaba_el_estado_inconsistente(self, ent, monkeypatch):
        """Excepción DESPUÉS del servicio y antes de responder: la asignación ya está confirmada y es coherente."""
        import zascarr.web.pendientes as pend

        class Rota:
            def __init__(self, *a, **k):
                raise RuntimeError("no se puede construir la respuesta")
        monkeypatch.setattr(pend, "HTMLResponse", Rota)
        r = ent.asignar()
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500
        assert bd.issue_id is not None and bd.ruta.endswith(disco.destinos[0]) and not disco.origen_existe

    # «Si el proceso muere entre mover y confirmar» ya no es una caracterización de un defecto: lo cubren,
    # con subprocesos reales que mueren en cada punto, `TestMuerteDelProceso` y la reconciliación de
    # `tests/test_asignacion_servicio_pg.py` / `tests/test_asignacion_integracion_pg.py`.

    @pytest.mark.asyncio
    async def test_antes_entre_discos_si_fallaba_borrar_el_original_quedaban_dos_copias(self, ent, monkeypatch):
        """Ahora es un resultado explícito: asignado, con el original pendiente de retirar (y avisado)."""
        unlink = Path.unlink

        def unlink_que_falla_en_el_origen(self, *a, **k):
            if self == ent.origen:
                raise PermissionError("sin permiso para borrar el original")
            return unlink(self, *a, **k)
        monkeypatch.setattr(Path, "unlink", unlink_que_falla_en_el_origen)
        r = ent.asignar()
        monkeypatch.setattr(Path, "unlink", unlink)
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 200 and "se intentará retirar al reiniciar ZascArr" in r.text
        assert disco.origen_existe and len(disco.destinos) == 1       # dos copias, pero REGISTRADAS y avisadas
        assert bd.ops == ["confirmada"] and bd.issue_id is not None and bd.ruta.endswith(disco.destinos[0])


class TestSolapamientoDeEnvios:

    @pytest.mark.asyncio
    async def test_dos_envios_del_mismo_archivo_a_la_vez(self, ent):
        """Doble clic por HTTP. Antes el segundo esperaba al índice único de `Issue` y fallaba con
        IntegrityError; ahora lo ordena el servicio (bloqueo + operación única): una asignación, una copia."""
        import httpx

        from zascarr.main import app
        datos = {"series_id": str(ent.serie_id), "issue_number": "12"}
        url = f"/ui/pendientes/{ent.file_id}/asignar"
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                     headers={"Origin": "http://localhost", "HX-Request": "true"}) as c:
            a, b = await asyncio.gather(c.post(url, data=datos), c.post(url, data=datos))
        assert sorted([a.status_code, b.status_code])[0] == 200 and {a.status_code, b.status_code} <= {200, 409}
        bd, disco = await ent.bd(), ent.disco()
        assert bd.issues == 1 and len(disco.destinos) == 1 and bd.ruta.endswith(disco.destinos[0])
        assert bd.ops == ["limpiada"]


class TestExcepcionNoControlada:

    @pytest.mark.asyncio
    async def test_una_excepcion_inesperada_del_servicio_llega_como_tarjeta_y_no_como_500_en_crudo(self, ent, monkeypatch):
        async def explota(self, *a, **k):
            raise RuntimeError("fallo de /ruta/secreta")
        monkeypatch.setattr("zascarr.services.asignacion.AsignacionService.asignar", explota)
        r = ent.asignar()
        assert r.status_code == 500 and 'id="card-' in r.text and "secreta" not in r.text
        assert ent.disco().origen_existe
