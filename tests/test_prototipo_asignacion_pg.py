# ruff: noqa: E501
"""ADR 0006: el contrato de asignación recuperable, demostrado con un prototipo de UN archivo.

Postgres real + ficheros reales. Cada prueba mata o rompe el flujo en un punto distinto y comprueba que
el sistema se reconcilia SIN escanear la biblioteca. La muerte es la del **proceso** (`os._exit`), no un
corte eléctrico (ver la auditoría). Se saltan sin `TEST_DATABASE_URL`.
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
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import RAIZ, bd_efimera_sync, migrar_a_head, url_asyncpg
from tests.prototipo_asignacion import DDL, AsignacionRecuperable
from zascarr.models import ComicTradition, File, FileFormat, Issue, LocalAlias, Series

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)

        async def crear():
            motor = create_async_engine(url_asyncpg(url))
            async with motor.begin() as c:
                for sentencia in [s for s in DDL.split(";\n") if s.strip()]:
                    await c.execute(text(sentencia))
            await motor.dispose()
        asyncio.run(crear())
        yield url


def hacer_cbz(ruta: Path, marca: str = "a", relleno: int = 5000) -> bytes:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", (marca * relleno).encode())
    return ruta.read_bytes()


class Mundo:
    def __init__(self, url: str, tmp: Path):
        self.url, self.lib = url, tmp / "lib"
        self.lib.mkdir()
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fabrica = async_sessionmaker(self.motor, expire_on_commit=False)
        self.serie_id = self.file_id = self.origen = None

    async def sembrar(self, nombre="Saga del Faro 12.cbz", marca="a"):
        async with self.motor.begin() as c:
            await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases CASCADE"))
        self.origen = self.lib / "_Unsorted" / nombre
        contenido = hacer_cbz(self.origen, marca)
        self.sha = hashlib.sha256(contenido).hexdigest()
        async with self.fabrica() as s:
            serie = Series(id=uuid4(), title="Saga del Faro", tradition=ComicTradition.AMERICAN, start_year=2010)
            f = File(id=uuid4(), file_path=str(self.origen), file_name=nombre, file_format=FileFormat.CBZ,
                     file_size_bytes=len(contenido), sha256_hash=self.sha, metadata_={"match_status": "unsorted"})
            s.add_all([serie, f])
            await s.commit()
            self.serie_id, self.file_id = serie.id, f.id
        return self

    def servicio(self, **kw) -> AsignacionRecuperable:
        return AsignacionRecuperable(self.fabrica, self.lib, **kw)

    async def estado(self):
        async with self.fabrica() as s:
            f = await s.get(File, self.file_id)
            ops = (await s.execute(text("SELECT estado, destino FROM asignacion_operaciones ORDER BY creada"))).all()
            issues = (await s.execute(select(Issue).where(Issue.series_id == self.serie_id))).scalars().all()
            alias = (await s.execute(select(LocalAlias).where(LocalAlias.series_id == self.serie_id))).scalars().all()
        cbz = sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*.cbz"))
        partes = sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*.part"))
        return type("E", (), dict(
            ruta=f.file_path, issue_id=f.issue_id, ops=[o[0] for o in ops], issues=len(issues), alias=len(alias),
            origen_existe=self.origen.exists(), destinos=[c for c in cbz if not c.startswith("_Unsorted")],
            cbz=cbz, partes=partes))()

    def subproceso(self, punto: str, accion: str = "os._exit(137)") -> subprocess.CompletedProcess:
        """Ejecuta `asignar` en otro proceso que MUERE en el punto indicado."""
        guion = textwrap.dedent(f"""
            import asyncio, os
            from pathlib import Path
            from uuid import UUID
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
            from tests.prototipo_asignacion import AsignacionRecuperable
            async def gancho(punto):
                if punto == {punto!r}:
                    {accion}
            async def main():
                motor = create_async_engine({url_asyncpg(self.url)!r})
                fab = async_sessionmaker(motor, expire_on_commit=False)
                await AsignacionRecuperable(fab, Path({str(self.lib)!r}), gancho=gancho).asignar(
                    UUID({str(self.file_id)!r}), UUID({str(self.serie_id)!r}), "12")
            asyncio.run(main())
        """)
        entorno = dict(os.environ, PYTHONPATH=os.pathsep.join([str(RAIZ / "src"), str(RAIZ)]))
        return subprocess.run([sys.executable, "-c", guion], env=entorno, capture_output=True, text=True, timeout=120)

    async def cerrar(self):
        await self.motor.dispose()


@pytest.fixture
async def mundo(url_bd, tmp_path):
    m = await Mundo(url_bd, tmp_path).sembrar()
    yield m
    await m.cerrar()


def _asignado_del_todo(e, mundo):
    assert e.ops == ["limpiada"]
    assert not e.origen_existe and len(e.destinos) == 1 and e.partes == []
    assert e.ruta.endswith(e.destinos[0]) and e.issue_id is not None and e.issues == 1 and e.alias == 1
    assert hashlib.sha256(Path(e.ruta).read_bytes()).hexdigest() == mundo.sha


class TestCaminoFeliz:

    @pytest.mark.asyncio
    async def test_asigna_con_copia_verificada_y_limpia_el_origen(self, mundo):
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        assert r.estado == "asignado"
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_repetir_lo_ya_asignado_no_mueve_ni_copia_otra_vez(self, mundo):
        await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        assert r.estado == "ya_asignado"
        _asignado_del_todo(await mundo.estado(), mundo)


class TestMuerteDelProceso:
    """Un subproceso real muere en cada punto; después se reconcilia en OTRO proceso, sin intervención."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("punto", ["tras_preparar", "tras_copiar", "tras_publicar"])
    async def test_antes_de_confirmar(self, mundo, punto):
        p = mundo.subproceso(punto)
        assert p.returncode == 137, p.stderr[-600:]
        e = await mundo.estado()
        assert e.ops == ["preparada"] and e.issue_id is None and e.origen_existe     # la BD no cambió; el origen sigue
        resultados = await mundo.servicio().reconciliar()
        assert [r.estado for r in resultados] == ["asignado"]
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_despues_de_confirmar_antes_de_limpiar(self, mundo):
        p = mundo.subproceso("tras_confirmar")
        assert p.returncode == 137, p.stderr[-600:]
        e = await mundo.estado()
        assert e.ops == ["confirmada"] and e.issue_id is not None and e.origen_existe   # confirmado; origen sin retirar
        assert [r.estado for r in await mundo.servicio().reconciliar()] == ["asignado"]
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_la_copia_a_medias_se_descarta_y_se_rehace(self, mundo):
        """Muerte DURANTE la copia: queda un temporal parcial y ningún destino."""
        servicio = mundo.servicio()
        preparada = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        async with mundo.fabrica() as s:
            temporal = Path((await s.execute(text("SELECT temporal FROM asignacion_operaciones"))).scalar())
        temporal.parent.mkdir(parents=True, exist_ok=True)
        temporal.write_bytes(b"PK\x03\x04 copia a medias")
        assert [r.estado for r in await mundo.servicio().reconciliar()] == ["asignado"]
        assert preparada is not None
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_la_reconciliacion_no_recorre_la_biblioteca(self, mundo, monkeypatch):
        mundo.subproceso("tras_publicar")

        def prohibido(*a, **k):
            raise AssertionError("la reconciliación no debe escanear la biblioteca")
        monkeypatch.setattr(Path, "rglob", prohibido)
        monkeypatch.setattr(Path, "iterdir", prohibido)
        monkeypatch.setattr(os, "walk", prohibido)
        assert [r.estado for r in await mundo.servicio().reconciliar()] == ["asignado"]


class TestCommitDeResultadoDesconocido:

    @pytest.mark.asyncio
    async def test_commit_confirmado_cuya_respuesta_se_pierde(self, mundo, monkeypatch):
        """Postgres confirma y la aplicación no se entera: NO se borra el destino ni se da por fallida."""
        original = AsyncSession.commit
        estado = {"n": 0}

        async def commit_con_respuesta_perdida(self):
            await original(self)
            estado["n"] += 1
            if estado["n"] == 2:                    # 1.º = preparar; 2.º = confirmar
                raise ConnectionResetError("se perdió la conexión tras enviar COMMIT")
        monkeypatch.setattr(AsyncSession, "commit", commit_con_respuesta_perdida)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert r.estado == "asignado"                # se comprobó en la BD: SÍ estaba confirmado
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_commit_no_aplicado_conserva_los_ficheros_y_se_reintenta(self, mundo, monkeypatch):
        original = AsyncSession.commit
        estado = {"n": 0}

        async def commit_que_no_llega(self):
            estado["n"] += 1
            if estado["n"] == 2:
                await self.rollback()
                raise ConnectionResetError("la conexión cayó antes de que llegara el COMMIT")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_que_no_llega)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        monkeypatch.setattr(AsyncSession, "commit", original)
        e = await mundo.estado()
        assert r.estado == "pendiente" and e.ops == ["preparada"]
        assert e.origen_existe and len(e.destinos) == 1       # NADA se borró: ni origen ni destino publicado
        assert [x.estado for x in await mundo.servicio().reconciliar()] == ["asignado"]
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_si_ni_se_puede_comprobar_se_conserva_todo(self, mundo, monkeypatch):
        original_commit = AsyncSession.commit
        servicio = mundo.servicio()
        original_op = AsignacionRecuperable._op
        estado = {"n": 0}

        async def commit_roto(self):
            estado["n"] += 1
            if estado["n"] == 2:
                raise ConnectionResetError("caída")
            return await original_commit(self)

        async def op_roto(self, op_id):
            raise ConnectionResetError("tampoco hay conexión para preguntar")
        monkeypatch.setattr(AsyncSession, "commit", commit_roto)
        # _op se usa dentro de _continuar (lectura inicial) y en la comprobación; solo falla la 2.ª llamada.
        llamadas = {"n": 0}

        async def op_a_ratos(self, op_id):
            llamadas["n"] += 1
            if llamadas["n"] >= 2:
                return await op_roto(self, op_id)
            return await original_op(self, op_id)
        monkeypatch.setattr(AsignacionRecuperable, "_op", op_a_ratos)
        r = await servicio.asignar(mundo.file_id, mundo.serie_id, "12")
        monkeypatch.setattr(AsyncSession, "commit", original_commit)
        monkeypatch.setattr(AsignacionRecuperable, "_op", original_op)
        e = await mundo.estado()
        assert r.estado == "pendiente_de_comprobar"
        assert e.origen_existe and len(e.destinos) == 1


class TestDestinoOcupado:

    @pytest.mark.asyncio
    async def test_destino_ocupado_usa_sufijo_y_la_recuperacion_respeta_el_efectivo(self, mundo):
        # Otro fichero (ajeno a ZascArr) ocupa el nombre canónico.
        canonico = mundo.lib / "Comics" / "Saga del Faro (2010)" / "Saga del Faro #012.cbz"
        hacer_cbz(canonico, "z")
        p = mundo.subproceso("tras_publicar")
        assert p.returncode == 137, p.stderr[-600:]
        async with mundo.fabrica() as s:
            efectivo = (await s.execute(text("SELECT destino FROM asignacion_operaciones"))).scalar()
        assert efectivo.endswith("Saga del Faro #012 (1).cbz")          # el EFECTIVO, no el canónico
        await mundo.servicio().reconciliar()
        e = await mundo.estado()
        assert e.ruta == efectivo and e.ops == ["limpiada"]
        assert canonico.read_bytes() != Path(efectivo).read_bytes()      # el ajeno no se tocó
        assert canonico.exists()

    @pytest.mark.asyncio
    async def test_dos_archivos_al_mismo_numero_no_comparten_destino(self, mundo):
        """Dos operaciones vivas no pueden reservar el mismo destino (índice único parcial)."""
        otro = mundo.lib / "_Unsorted" / "Saga del Faro 12 bis.cbz"
        contenido = hacer_cbz(otro, "b")
        async with mundo.fabrica() as s:
            f2 = File(id=uuid4(), file_path=str(otro), file_name=otro.name, file_format=FileFormat.CBZ,
                      file_size_bytes=len(contenido), sha256_hash=hashlib.sha256(contenido).hexdigest(),
                      metadata_={"match_status": "unsorted"})
            s.add(f2)
            await s.commit()
        a = await mundo.servicio()._preparar(mundo.file_id, mundo.serie_id, "12")
        b = await mundo.servicio()._preparar(f2.id, mundo.serie_id, "12")
        async with mundo.fabrica() as s:
            destinos = [r[0] for r in (await s.execute(text("SELECT destino FROM asignacion_operaciones"))).all()]
        assert a != b and len(set(destinos)) == 2


class TestSolicitudesSolapadas:

    @pytest.mark.asyncio
    async def test_dos_solicitudes_del_mismo_archivo_con_el_issue_ya_existente(self, mundo):
        """El caso que la prueba de la auditoría NO cubría: sin carrera por crear el Issue."""
        async with mundo.fabrica() as s:
            s.add(Issue(series_id=mundo.serie_id, issue_number="12", format=None))
            await s.commit()
        llegada = asyncio.Event()

        async def gancho(punto):
            if punto == "tras_copiar":
                llegada.set()
                await asyncio.sleep(0.5)             # A sigue ocupada cuando B llega
        a = asyncio.create_task(mundo.servicio(gancho=gancho).asignar(mundo.file_id, mundo.serie_id, "12"))
        await llegada.wait()
        b = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        ra = await a
        assert b.estado == "ya_en_curso" and ra.estado == "asignado"
        e = await mundo.estado()
        assert e.ops == ["limpiada"] and len(e.destinos) == 1 and e.partes == []

    @pytest.mark.asyncio
    async def test_la_segunda_encuentra_una_operacion_huerfana_y_la_continua(self, mundo):
        mundo.subproceso("tras_publicar")                           # A muere
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")   # B reintenta
        assert r.estado == "asignado"
        _asignado_del_todo(await mundo.estado(), mundo)


class TestFalloAlBorrarElOrigen:

    @pytest.mark.asyncio
    async def test_la_asignacion_confirmada_no_pasa_a_fallida(self, mundo):
        def borrar_roto(_p):
            raise PermissionError("sin permiso para borrar el original")
        r = await mundo.servicio(borrar=borrar_roto).asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "asignado_limpieza_pendiente"
        assert e.issue_id is not None and e.ops == ["confirmada"] and e.origen_existe     # asignado; limpieza pendiente
        assert [x.estado for x in await mundo.servicio().reconciliar()] == ["asignado"]
        _asignado_del_todo(await mundo.estado(), mundo)

    @pytest.mark.asyncio
    async def test_no_borra_un_origen_que_ya_no_es_el_preparado(self, mundo):
        p = mundo.subproceso("tras_confirmar")
        assert p.returncode == 137
        hacer_cbz(mundo.origen, "OTRO CONTENIDO", relleno=9000)     # alguien puso otro fichero con ese nombre
        r = (await mundo.servicio().reconciliar())[0]
        assert r.estado == "asignado_limpieza_pendiente" and mundo.origen.exists()


class TestCopiaVerificada:

    @pytest.mark.asyncio
    async def test_una_copia_corrupta_no_se_publica(self, mundo, monkeypatch):
        import tests.prototipo_asignacion as proto
        real = proto.shutil.copyfile

        def copia_corrupta(src, dst):
            real(src, dst)
            with open(dst, "r+b") as f:
                f.seek(10)
                f.write(b"\x00\x00\x00\x00")
        monkeypatch.setattr(proto.shutil, "copyfile", copia_corrupta)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "error" and "no se pudo verificar" in r.motivo
        assert e.destinos == [] and e.partes == [] and e.origen_existe and e.issue_id is None


class TestCancelacionDelCliente:

    @pytest.mark.asyncio
    async def test_cancelar_la_peticion_no_interrumpe_la_operacion(self, mundo):
        copiando = asyncio.Event()

        async def gancho(punto):
            if punto == "tras_preparar":
                copiando.set()
                await asyncio.sleep(0.5)
        servicio = mundo.servicio(gancho=gancho)
        tarea = asyncio.create_task(servicio.asignar(mundo.file_id, mundo.serie_id, "12"))
        await copiando.wait()
        tarea.cancel()                                    # el cliente se desconecta
        with pytest.raises(asyncio.CancelledError):
            await tarea
        for _ in range(100):                              # la operación sigue en segundo plano
            await asyncio.sleep(0.1)
            if (await mundo.estado()).ops == ["limpiada"]:
                break
        _asignado_del_todo(await mundo.estado(), mundo)


class TestMetadataNoBasta:
    """Por qué NO `File.metadata_`: cinco puntos la reescriben ENTERA a partir de una lectura anterior."""

    @pytest.mark.asyncio
    async def test_un_escritor_con_lectura_obsoleta_borra_el_marcador(self, mundo):
        # A (el servicio) anota la operación en metadata_ y confirma.
        async with mundo.fabrica() as a:
            fa = await a.get(File, mundo.file_id)
            fa.metadata_ = {**(fa.metadata_ or {}), "asignacion_pendiente": {"op": "abc", "destino": "/x.cbz"}}
            # B (p. ej. el etiquetador) había leído la fila ANTES y escribe DESPUÉS, como hacen
            # tagger.py:334/525, review.py:164, pendientes.py:115 e importer.py:181.
            async with mundo.fabrica() as b:
                fb = await b.get(File, mundo.file_id)
                await a.commit()
                fb.metadata_ = {**(fb.metadata_ or {}), "comicinfo_propio": {"x": 1}}
                await b.commit()
        async with mundo.fabrica() as s:
            meta = (await s.get(File, mundo.file_id)).metadata_
        assert "comicinfo_propio" in meta and "asignacion_pendiente" not in meta      # el marcador SE PERDIÓ

    @pytest.mark.asyncio
    async def test_con_tabla_propia_el_mismo_escritor_no_la_toca(self, mundo):
        servicio = mundo.servicio()
        await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        async with mundo.fabrica() as b:
            fb = await b.get(File, mundo.file_id)
            fb.metadata_ = {**(fb.metadata_ or {}), "comicinfo_propio": {"x": 1}}
            await b.commit()
        async with mundo.fabrica() as s:
            vivas = (await s.execute(text("SELECT count(*) FROM asignacion_operaciones WHERE estado = 'preparada'"))).scalar()
        assert vivas == 1
