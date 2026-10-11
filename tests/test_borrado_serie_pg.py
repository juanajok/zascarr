# ruff: noqa: E501
"""`DELETE /api/series/{id}` protegido (I4 de #114, ADR 0010 P-3) — pruebas sobre Postgres real.

Lo que se fija: solo se borra una serie SIN dependientes; con operación viva, archivos vinculados, números o
deseados responde 409 y no cambia nada; los alias y los géneros se borran con ella; los comprobantes de alta se
conservan; el disco no se toca; y un borrado concurrente con una vinculación nunca deja archivos vinculados a números
borrados. Ningún fichero fuera de un directorio temporal; ninguna fuente real. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    AltaEstado,
    AltaOperacion,
    ComicTradition,
    File,
    FileFormat,
    Issue,
    LocalAlias,
    Series,
    Wishlist,
    WishlistPolicy,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SHA = "a" * 64


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


class Banco:
    def __init__(self, url, monkeypatch, tmp_path):
        import zascarr.database as dbmod
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fabrica = async_sessionmaker(self.motor, expire_on_commit=False)
        self.dir = tmp_path
        monkeypatch.setattr(dbmod, "async_session_factory", self.fabrica)

    async def vaciar(self):
        async with self.motor.begin() as c:
            await c.execute(text(
                "TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, wishlist, alta_operaciones CASCADE"))

    async def serie(self, titulo="Saga del Faro", **kw) -> Series:
        async with self.fabrica() as s:
            serie = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN, start_year=2010, **kw)
            s.add(serie)
            await s.commit()
            return serie

    async def numero(self, serie_id, numero="1") -> Issue:
        async with self.fabrica() as s:
            issue = Issue(series_id=serie_id, issue_number=numero)
            s.add(issue)
            await s.commit()
            return issue

    async def archivo(self, nombre="Saga del Faro 01.cbz", issue_id=None, contenido=b"contenido-que-no-debe-cambiar") -> File:
        ruta = self.dir / nombre
        ruta.write_bytes(contenido)
        async with self.fabrica() as s:
            f = File(id=uuid4(), file_path=str(ruta), file_name=nombre, file_format=FileFormat.CBZ,
                     file_size_bytes=len(contenido), sha256_hash=SHA, issue_id=issue_id)
            s.add(f)
            await s.commit()
            return f

    async def contar(self, modelo, **filtros) -> int:
        async with self.fabrica() as s:
            return len((await s.execute(select(modelo).filter_by(**filtros))).scalars().all())

    async def existe(self, serie_id) -> bool:
        async with self.fabrica() as s:
            return (await s.get(Series, serie_id)) is not None

    def cliente(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from zascarr.api.series import router
        app = FastAPI()
        app.include_router(router, prefix="/api")
        return TestClient(app, raise_server_exceptions=False)

    async def borrar(self, serie_id):
        return await asyncio.to_thread(self.cliente().delete, f"/api/series/{serie_id}")


@pytest.fixture
async def banco(url_bd, monkeypatch, tmp_path):
    b = Banco(url_bd, monkeypatch, tmp_path)
    await b.vaciar()
    yield b
    await b.motor.dispose()


async def operacion_viva(banco, serie_id, file_id, estado="preparada"):
    async with banco.motor.begin() as c:
        await c.execute(text(
            "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
            "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST(:e AS asignacion_estado), '/a', '/b', '/c', 1, 1, "
            "repeat('a', 64), '12', 'single_issue')"), {"f": file_id, "s": serie_id, "e": estado})


class TestSoloSeBorraUnaSerieSinDependientes:
    @pytest.mark.asyncio
    async def test_una_serie_vacia_se_borra(self, banco):
        s = await banco.serie()
        r = await banco.borrar(s.id)
        assert r.status_code == 204
        assert not await banco.existe(s.id)

    @pytest.mark.asyncio
    async def test_una_serie_inexistente_da_404(self, banco):
        r = await banco.borrar(uuid4())
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_con_archivos_vinculados_da_409_y_no_cambia_nada(self, banco):
        s = await banco.serie()
        i = await banco.numero(s.id)
        f = await banco.archivo(issue_id=i.id)
        r = await banco.borrar(s.id)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tiene_archivos"
        assert "nunca toca los archivos del disco" in r.json()["detail"]["mensaje"]
        assert await banco.existe(s.id) and await banco.contar(Issue, series_id=s.id) == 1
        assert await banco.contar(File, id=f.id, issue_id=i.id) == 1          # sigue vinculado

    @pytest.mark.asyncio
    async def test_con_numeros_sin_archivos_da_409(self, banco):
        s = await banco.serie()
        await banco.numero(s.id)
        r = await banco.borrar(s.id)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tiene_numeros"
        assert await banco.existe(s.id) and await banco.contar(Issue, series_id=s.id) == 1

    @pytest.mark.asyncio
    async def test_con_deseados_da_409(self, banco):
        s = await banco.serie()
        async with banco.fabrica() as ses:
            ses.add(Wishlist(series_id=s.id))
            await ses.commit()
        r = await banco.borrar(s.id)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tiene_deseados"
        assert await banco.existe(s.id) and await banco.contar(Wishlist, series_id=s.id) == 1

    @pytest.mark.asyncio
    async def test_con_politica_de_busqueda_activa_da_409(self, banco):
        s = await banco.serie(wishlist_policy=WishlistPolicy.MISSING)
        r = await banco.borrar(s.id)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tiene_deseados"
        assert await banco.existe(s.id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["preparada", "confirmada"])
    async def test_la_operacion_viva_conserva_su_409_de_siempre(self, banco, estado):
        """El mensaje en TEXTO, tal cual estaba; y gana aunque la serie además tenga archivos vinculados."""
        s = await banco.serie()
        i = await banco.numero(s.id)
        f = await banco.archivo(issue_id=i.id)
        await operacion_viva(banco, s.id, f.id, estado)
        r = await banco.borrar(s.id)
        assert r.status_code == 409 and isinstance(r.json()["detail"], str)
        assert "asignación de archivos en curso" in r.json()["detail"]
        assert await banco.existe(s.id) and await banco.contar(Issue, series_id=s.id) == 1


class TestQueSeLlevaLaSerieYQueSeConserva:
    @pytest.mark.asyncio
    async def test_los_alias_locales_se_borran_con_la_serie(self, banco):
        s = await banco.serie()
        async with banco.fabrica() as ses:
            ses.add(LocalAlias(pattern_norm="saga del faro", series_id=s.id))
            await ses.commit()
        assert (await banco.borrar(s.id)).status_code == 204
        assert await banco.contar(LocalAlias) == 0

    @pytest.mark.asyncio
    async def test_el_comprobante_de_alta_sobrevive_al_borrado(self, banco):
        s = await banco.serie()
        op = uuid4()
        async with banco.fabrica() as ses:
            ses.add(AltaOperacion(operacion_id=op, series_id=s.id, estado=AltaEstado.CREADA,
                                  token_hasta=datetime.now(UTC) + timedelta(minutes=15)))
            await ses.commit()
        assert (await banco.borrar(s.id)).status_code == 204
        assert await banco.contar(AltaOperacion, operacion_id=op) == 1          # sin clave foránea: se conserva


class TestElBorradoNoTocaElDisco:
    @pytest.mark.asyncio
    async def test_borrar_una_serie_vacia_no_toca_los_ficheros_de_al_lado(self, banco):
        s = await banco.serie()
        suelto = await banco.archivo("Suelto.cbz")
        antes = {p.name: p.read_bytes() for p in banco.dir.iterdir()}
        assert (await banco.borrar(s.id)).status_code == 204
        assert {p.name: p.read_bytes() for p in banco.dir.iterdir()} == antes
        assert await banco.contar(File, id=suelto.id) == 1

    @pytest.mark.asyncio
    async def test_la_negativa_por_archivos_tampoco_toca_el_disco(self, banco):
        s = await banco.serie()
        i = await banco.numero(s.id)
        f = await banco.archivo(issue_id=i.id)
        antes = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in banco.dir.iterdir()}
        assert (await banco.borrar(s.id)).status_code == 409
        assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in banco.dir.iterdir()} == antes
        assert (banco.dir / f.file_name).exists()


class TestConcurrenciaConUnaVinculacion:
    """Quien vincula archivos a números de la serie la toma `FOR SHARE` (2d) y los números se insertan con `FOR KEY SHARE`.
    Un borrado que llegue en medio debe esperar y, al ver lo confirmado, negarse: nunca puede dejar un archivo
    vinculado a un número que ya no existe."""

    @pytest.mark.asyncio
    async def test_el_borrado_espera_a_la_vinculacion_y_luego_se_niega(self, banco):
        s = await banco.serie()
        f = await banco.archivo()                                    # pendiente: sin vincular
        async with banco.fabrica() as vinculacion:
            await vinculacion.execute(select(Series.id).where(Series.id == s.id).with_for_update(read=True))
            borrado = asyncio.create_task(banco.borrar(s.id))
            await asyncio.sleep(1.0)
            assert not borrado.done(), "el borrado debía esperar al candado de la vinculación"
            issue = Issue(series_id=s.id, issue_number="1")
            vinculacion.add(issue)
            await vinculacion.flush()
            fila = await vinculacion.get(File, f.id)
            fila.issue_id = issue.id
            await vinculacion.commit()
        r = await asyncio.wait_for(borrado, timeout=30)
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tiene_archivos"
        assert await banco.existe(s.id)
        assert await banco.contar(File, id=f.id) == 1
        async with banco.fabrica() as ses:
            assert (await ses.get(File, f.id)).issue_id is not None          # sigue vinculado a un número que existe
