# ruff: noqa: E501
"""V6a, auditoría (criterio 1): qué queda en disco y en BD si algo falla entre mover y confirmar.

PRUEBAS DE CARACTERIZACIÓN: describen lo que `ReviewService.assign_to_series` hace HOY, con el
endpoint real (`POST /ui/pendientes/{id}/asignar`), el `get_db` real, Postgres real y ficheros reales.
Los nombres dicen el mecanismo. Algunas fijan un comportamiento que NO es el deseable (un fichero
movido con la BD revertida): están ahí para que el lote de V6a las cambie a propósito, no por
accidente. El análisis y la propuesta de reconciliación: `docs/design/auditoria-mover-y-sesion.md`.

Se saltan sin `TEST_DATABASE_URL`. Cada módulo crea su propia BD efímera y migrada.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import RAIZ, bd_efimera_sync, entorno_para_alembic, migrar_a_head, url_asyncpg
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
        ajustes = SimpleNamespace(
            library_path=self.lib, downloads_path=self.dl,
            transmission_download_dir=str(self.dl), amule_incoming_dir=str(self.dl / "amule"))
        monkeypatch.setattr("zascarr.services.review.get_settings", lambda: ajustes)
        monkeypatch.setattr("zascarr.services.importer.get_settings", lambda: ajustes)
        app = FastAPI()
        app.include_router(router)
        self.cliente = TestClient(app, raise_server_exceptions=False)
        self.serie_id: UUID | None = None
        self.file_id: UUID | None = None
        self.origen: Path | None = None

    async def sembrar(self, nombre="Saga del Faro 12.cbz", marca="a"):
        # La BD es EFÍMERA y de este módulo: se vacía entre pruebas para que el recuento de ficheros de
        # la biblioteca (y el guardarraíl de desaparición masiva de B7) dependa solo de cada prueba.
        async with self.engine.begin() as c:
            await c.execute(text("TRUNCATE files, issues, series, local_aliases, import_runs CASCADE"))
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
        return self.cliente.post(f"/ui/pendientes/{self.file_id}/asignar",
                                 data={"series_id": str(self.serie_id), "issue_number": numero})

    async def bd(self) -> SimpleNamespace:
        async with self.fabrica() as s:
            f = await s.get(File, self.file_id)
            issues = (await s.execute(select(Issue).where(Issue.series_id == self.serie_id))).scalars().all()
            alias = (await s.execute(select(LocalAlias).where(LocalAlias.series_id == self.serie_id))).scalars().all()
            return SimpleNamespace(
                ruta=f.file_path, issue_id=f.issue_id, fuente=f.metadata_source, is_missing=f.is_missing,
                issues=len(issues), alias=len(alias))

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


class TestFronterasDeFallo:
    """Cada prueba inyecta UN fallo en un punto distinto y mira disco y BD después."""

    @pytest.mark.asyncio
    async def test_fallo_antes_de_mover_no_deja_nada(self, ent, monkeypatch):
        async def mover_roto(orig, dest):
            raise OSError("disco de destino de solo lectura")
        monkeypatch.setattr("zascarr.services.review.safe_move_async", mover_roto)
        r = ent.asignar()
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500
        assert disco.origen_existe and disco.destinos == []          # disco intacto
        assert bd.issue_id is None and bd.issues == 0 and bd.alias == 0  # el Issue del flush se revirtió

    @pytest.mark.asyncio
    async def test_hoy_fallo_despues_de_mover_deja_el_fichero_movido_y_la_bd_revertida(self, ent, monkeypatch):
        """El punto que `CLAUDE.md` §3.1.2 marcaba «pendiente de auditar»."""
        async def alias_roto(self, *a, **k):
            raise RuntimeError("fallo en _learn_alias, después de mover y de actualizar la fila")
        monkeypatch.setattr("zascarr.services.review.ReviewService._learn_alias", alias_roto)
        r = ent.asignar()
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500
        assert not disco.origen_existe and len(disco.destinos) == 1   # EL FICHERO SE MOVIÓ…
        assert bd.ruta == str(ent.origen) and bd.issue_id is None     # …y la BD sigue apuntando al origen
        assert bd.issues == 0                                          # (el Issue se revirtió)

    @pytest.mark.asyncio
    async def test_hoy_si_el_commit_de_get_db_falla_el_cliente_ya_recibio_exito(self, ent, monkeypatch):
        """El `commit` de `get_db` corre al SALIR de la dependencia. En este FastAPI el cierre de una
        dependencia con `yield` es, por defecto, posterior al envío de la respuesta."""
        original = AsyncSession.commit
        llamadas = {"n": 0}

        async def commit_que_falla_la_primera(self):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise RuntimeError("el commit falló (conexión perdida)")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_que_falla_la_primera)
        r = ent.asignar()
        monkeypatch.setattr(AsyncSession, "commit", original)
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 200                                    # el cliente cree que fue bien…
        assert not disco.origen_existe and len(disco.destinos) == 1   # …el fichero se movió…
        assert bd.ruta == str(ent.origen) and bd.issue_id is None     # …y la BD no lo sabe

    @pytest.mark.asyncio
    async def test_hoy_un_fallo_tras_el_servicio_pero_en_el_endpoint_tambien_revierte(self, ent, monkeypatch):
        """Excepción DESPUÉS de `assign_to_series` y antes de responder (p. ej. al construir la respuesta)."""
        import zascarr.web.pendientes as pend

        class Rota:
            def __init__(self, *a, **k):
                raise RuntimeError("no se puede construir la respuesta")
        monkeypatch.setattr(pend, "HTMLResponse", Rota)
        r = ent.asignar()
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500
        assert not disco.origen_existe and bd.issue_id is None        # mismo estado inconsistente

    @pytest.mark.asyncio
    async def test_hoy_si_el_proceso_muere_entre_mover_y_commit_queda_igual(self, ent):
        """Un `kill -9` / OOM en la Pi entre `safe_move` y el `commit`. Subproceso real que sale con
        `os._exit` justo después del `flush`: sin `rollback` ni `finally`, como una muerte real."""
        guion = textwrap.dedent(f"""
            import asyncio, os, sys
            from pathlib import Path
            from types import SimpleNamespace
            from uuid import UUID
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            import zascarr.services.review as review
            ajustes = SimpleNamespace(library_path=Path({str(ent.lib)!r}))
            review.get_settings = lambda: ajustes
            async def main():
                motor = create_async_engine({url_asyncpg(ent.url)!r})
                async with async_sessionmaker(motor, expire_on_commit=False)() as s:
                    async def alias_y_muerte(self, *a, **k):
                        os._exit(137)          # tras mover y tras el UPDATE+flush de la fila
                    review.ReviewService._learn_alias = alias_y_muerte
                    await review.ReviewService(s).assign_to_series(
                        UUID({str(ent.file_id)!r}), UUID({str(ent.serie_id)!r}), "12")
            asyncio.run(main())
        """)
        entorno = entorno_para_alembic(os.environ, ent.url)
        entorno["PYTHONPATH"] = str(RAIZ / "src")
        p = subprocess.run([sys.executable, "-c", guion], env=entorno, capture_output=True, text=True, timeout=120)
        assert p.returncode == 137, p.stderr[-800:]
        bd, disco = await ent.bd(), ent.disco()
        assert not disco.origen_existe and len(disco.destinos) == 1
        assert bd.ruta == str(ent.origen) and bd.issue_id is None and bd.issues == 0

    @pytest.mark.asyncio
    async def test_hoy_entre_discos_si_falla_borrar_el_original_quedan_las_dos_copias(self, ent, monkeypatch):
        """`safe_move` entre sistemas de ficheros distintos: copia, `os.replace` y SOLO ENTONCES `unlink`
        del original. Si ese `unlink` falla, el destino ya está colocado y el original sigue ahí."""
        import zascarr.utils.fs as fs
        monkeypatch.setattr(fs, "_same_filesystem", lambda a, b: False)
        unlink = Path.unlink

        def unlink_que_falla_en_el_origen(self, *a, **k):
            if self == ent.origen:
                raise PermissionError("sin permiso para borrar el original")
            return unlink(self, *a, **k)
        monkeypatch.setattr(Path, "unlink", unlink_que_falla_en_el_origen)
        r = ent.asignar()
        monkeypatch.setattr(Path, "unlink", unlink)
        bd, disco = await ent.bd(), ent.disco()
        assert r.status_code == 500
        assert disco.origen_existe and len(disco.destinos) == 1       # DOS copias en disco
        assert bd.ruta == str(ent.origen) and bd.issue_id is None


class TestSolapamientoDeEnvios:

    @pytest.mark.asyncio
    async def test_hoy_dos_envios_del_mismo_archivo_a_la_vez(self, ent):
        """Doble clic: A mueve y aún no ha confirmado; B llega con la fila vieja."""
        from zascarr.services.review import ReviewService

        a = ent.fabrica()
        sa = await a.__aenter__()
        await ReviewService(sa).assign_to_series(ent.file_id, ent.serie_id, "12")   # movido, sin commit

        async def segundo():
            async with ent.fabrica() as sb:
                try:
                    await ReviewService(sb).assign_to_series(ent.file_id, ent.serie_id, "12")
                    await sb.commit()
                    return "ok"
                except Exception as exc:  # noqa: BLE001
                    await sb.rollback()
                    return type(exc).__name__

        tarea = asyncio.create_task(segundo())
        await asyncio.sleep(1.0)
        bloqueado = not tarea.done()          # ¿B espera al `commit` de A (índice único) o sigue de largo?
        await sa.commit()
        await a.__aexit__(None, None, None)
        resultado_b = await asyncio.wait_for(tarea, 30)
        bd, disco = await ent.bd(), ent.disco()
        # B se queda esperando al `commit` de A (el índice único de Issue se lo impone) y después falla
        # con IntegrityError y se revierte: un solo Issue, un solo fichero, fila apuntando al destino real.
        assert bloqueado is True and resultado_b == "IntegrityError"
        assert bd.issues == 1 and len(disco.destinos) == 1 and bd.ruta.endswith(disco.destinos[0])


class TestReconciliacionQueYaExiste:
    """Desde el estado inconsistente (fichero movido a la biblioteca, BD apuntando al origen)."""

    @pytest.mark.asyncio
    async def test_hoy_el_importador_lo_marca_desaparecido_y_nadie_registra_el_destino(self, ent, monkeypatch):
        from zascarr.services.importer import Importer

        async def alias_roto(self, *a, **k):
            raise RuntimeError("fallo tras mover")
        monkeypatch.setattr("zascarr.services.review.ReviewService._learn_alias", alias_roto)
        ent.asignar()
        # Hace falta algo más en la biblioteca para que el guardarraíl de «biblioteca vacía» no omita B7.
        hacer_cbz(ent.lib / "otra" / "Otra #001.cbz", "z")
        async with ent.fabrica() as s:
            desaparecidos, reaparecidos = await Importer(s)._detectar_desaparecidos()
            await s.commit()
        bd, disco = await ent.bd(), ent.disco()
        async with ent.fabrica() as s:
            fila_en_destino = (await s.execute(
                select(File).where(File.file_path.like(f"%{Path(disco.destinos[0]).name}")))).scalars().all()
        assert desaparecidos == ["Saga del Faro 12.cbz"] and bd.is_missing is True
        assert fila_en_destino == []             # el fichero movido NO tiene fila en la BD
        assert [d for d in disco.destinos if "#012" in d] == [disco.destinos[0]]

    @pytest.mark.asyncio
    async def test_si_el_fichero_vuelve_a_las_descargas_el_importador_lo_recupera_por_hash(self, ent, monkeypatch):
        """Sí hay reconciliación hoy, pero manual: hay que devolver el fichero a una carpeta de entrada."""
        from zascarr.services.importer import Importer

        async def alias_roto(self, *a, **k):
            raise RuntimeError("fallo tras mover")
        monkeypatch.setattr("zascarr.services.review.ReviewService._learn_alias", alias_roto)
        ent.asignar()
        hacer_cbz(ent.lib / "otra" / "Otra #001.cbz", "z")
        async with ent.fabrica() as s:
            await Importer(s)._detectar_desaparecidos()
            await s.commit()
        destino = ent.lib / ent.disco().destinos[0]
        (ent.dl / "devuelto.cbz").write_bytes(destino.read_bytes())
        destino.unlink()
        async with ent.fabrica() as s:
            informe = await Importer(s).scan_and_import()
            await s.commit()
        bd = await ent.bd()
        assert any("recuperado" in linea for linea in informe.imported)
        assert bd.is_missing is False
