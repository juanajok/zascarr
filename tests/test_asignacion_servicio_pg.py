# ruff: noqa: E501
"""ADR 0006: el contrato de asignación recuperable, demostrado sobre el servicio de UN archivo (`zascarr.services.asignacion`).

Postgres real + ficheros reales. Cada prueba mata o rompe el flujo en un punto distinto y comprueba que
el sistema se reconcilia SIN escanear la biblioteca. La muerte es la del **proceso** (`os._exit`), no un
corte eléctrico (ver la auditoría). Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import contextlib
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
from zascarr.models import ComicTradition, File, FileFormat, Issue, LocalAlias, Series
from zascarr.services.asignacion import AsignacionService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    """BD efímera y MIGRADA a head (incluye `asignacion_operaciones`, migración 0017)."""
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
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

    def servicio(self, **kw) -> AsignacionService:
        return AsignacionService(self.fabrica, self.lib, **kw)

    async def estado(self):
        async with self.fabrica() as s:
            f = await s.get(File, self.file_id)
            ops = (await s.execute(text("SELECT estado, destino FROM asignacion_operaciones ORDER BY creada"))).all()
            issues = (await s.execute(select(Issue).where(Issue.series_id == self.serie_id))).scalars().all()
            alias = (await s.execute(select(LocalAlias).where(LocalAlias.series_id == self.serie_id))).scalars().all()
        cbz = sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*.cbz"))
        partes = sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*.part*"))   # incluye `.part.<época>`
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
            from zascarr.services.asignacion import AsignacionService
            async def gancho(punto):
                if punto == {punto!r}:
                    {accion}
            async def main():
                motor = create_async_engine({url_asyncpg(self.url)!r})
                fab = async_sessionmaker(motor, expire_on_commit=False)
                await AsignacionService(fab, Path({str(self.lib)!r}), gancho=gancho).asignar(
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
            if estado["n"] == 3:                    # 1.º = preparar; 2.º = tomar la época; 3.º = confirmar
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
            if estado["n"] == 3:
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
        original_op = AsignacionService._op
        estado = {"n": 0}

        async def commit_roto(self):
            estado["n"] += 1
            if estado["n"] == 3:
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
        monkeypatch.setattr(AsignacionService, "_op", op_a_ratos)
        r = await servicio.asignar(mundo.file_id, mundo.serie_id, "12")
        monkeypatch.setattr(AsyncSession, "commit", original_commit)
        monkeypatch.setattr(AsignacionService, "_op", original_op)
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
        # Mismo motor (mismo pool) = límite COMPARTIDO: B espera su turno y, cuando llega, ya está asignado.
        b = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        ra = await a
        assert b.estado == "ya_asignado" and ra.estado == "asignado"
        e = await mundo.estado()
        assert e.ops == ["limpiada"] and len(e.destinos) == 1 and e.partes == []

    @pytest.mark.asyncio
    async def test_desde_otro_proceso_la_segunda_ve_ya_en_curso(self, mundo):
        """Otro motor = otro proceso: no comparten semáforo, así que quien frena es el candado de Postgres."""
        async with mundo.fabrica() as s:
            s.add(Issue(series_id=mundo.serie_id, issue_number="12", format=None))
            await s.commit()
        llegada = asyncio.Event()

        async def gancho(punto):
            if punto == "tras_copiar":
                llegada.set()
                await asyncio.sleep(0.8)
        otro = create_async_engine(url_asyncpg(mundo.url), poolclass=NullPool)
        try:
            a = asyncio.create_task(mundo.servicio(gancho=gancho).asignar(mundo.file_id, mundo.serie_id, "12"))
            await llegada.wait()
            b = await AsignacionService(async_sessionmaker(otro, expire_on_commit=False), mundo.lib).asignar(
                mundo.file_id, mundo.serie_id, "12")
            ra = await a
        finally:
            await otro.dispose()
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
        import zascarr.services.asignacion as proto
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


class TestNoBorrarLaUltimaCopia:
    """Revisión de la PR #76: la limpieza no puede dejar al coleccionista sin ninguna copia válida."""

    async def _tras_confirmar(self, mundo):
        p = mundo.subproceso("tras_confirmar")
        assert p.returncode == 137, p.stderr[-600:]
        async with mundo.fabrica() as s:
            return Path((await s.execute(text("SELECT destino FROM asignacion_operaciones"))).scalar())

    @pytest.mark.asyncio
    async def test_destino_ausente_tras_confirmar_conserva_el_origen(self, mundo):
        destino = await self._tras_confirmar(mundo)
        destino.unlink()                                          # el destino desaparece
        r = (await mundo.servicio().reconciliar())[0]
        e = await mundo.estado()
        assert r.estado == "reparacion_pendiente" and "falta" in r.motivo
        assert e.origen_existe and e.ops == ["confirmada"]       # la última copia sigue ahí; la operación sigue viva

    @pytest.mark.asyncio
    @pytest.mark.parametrize("corrupcion", ["mismo_tamano", "distinto_tamano"])
    async def test_destino_corrupto_tras_confirmar_conserva_el_origen(self, mundo, corrupcion):
        destino = await self._tras_confirmar(mundo)
        datos = bytearray(destino.read_bytes())
        if corrupcion == "mismo_tamano":
            datos[20] ^= 0xFF
        else:
            datos = datos[:-10]
        destino.write_bytes(bytes(datos))
        r = (await mundo.servicio().reconciliar())[0]
        assert r.estado == "reparacion_pendiente" and (await mundo.estado()).origen_existe

    @pytest.mark.asyncio
    async def test_si_la_bd_ya_no_apunta_a_la_asignacion_conserva_el_origen(self, mundo):
        await self._tras_confirmar(mundo)
        async with mundo.fabrica() as s:
            await s.execute(text("UPDATE files SET file_path = '/otra/ruta.cbz' WHERE id = :f"), {"f": mundo.file_id})
            await s.commit()
        r = (await mundo.servicio().reconciliar())[0]
        assert r.estado == "reparacion_pendiente" and "BD" in r.motivo and mundo.origen.exists()

    @pytest.mark.asyncio
    async def test_un_origen_sustituido_con_igual_tamano_y_fecha_no_se_borra(self, mundo):
        """Tamaño y mtime_ns iguales NO acreditan el mismo contenido."""
        await self._tras_confirmar(mundo)
        st = mundo.origen.stat()
        otro = bytearray(mundo.origen.read_bytes())
        otro[100] ^= 0xFF                                         # mismo tamaño, contenido distinto
        mundo.origen.write_bytes(bytes(otro))
        os.utime(mundo.origen, ns=(st.st_atime_ns, st.st_mtime_ns))     # y la misma fecha
        assert mundo.origen.stat().st_size == st.st_size and mundo.origen.stat().st_mtime_ns == st.st_mtime_ns
        r = (await mundo.servicio().reconciliar())[0]
        assert r.estado == "asignado_limpieza_pendiente" and "ya no es el fichero" in r.motivo
        assert mundo.origen.read_bytes() == bytes(otro)           # el fichero distinto sigue intacto


class TestPublicarEnElServicio:

    @pytest.mark.asyncio
    async def test_un_ajeno_que_ocupa_el_destino_justo_antes_de_publicar_queda_intacto(self, mundo):
        """El ajeno aparece DESPUÉS de reservar y copiar: el intento no lo pisa y se cancela (`destino_ocupado`)."""
        async def intruso(punto):
            if punto == "tras_copiar":
                async with mundo.fabrica() as s:
                    destino = Path((await s.execute(text("SELECT destino FROM asignacion_operaciones"))).scalar())
                hacer_cbz(destino, "AJENO", relleno=777)
        servicio = mundo.servicio(gancho=intruso)
        op = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        r = await servicio._ejecutar(op)                       # UN intento, sin el reintento de `asignar`
        e = await mundo.estado()
        assert r.estado == "destino_ocupado"
        assert e.ops == ["cancelada"] and e.origen_existe and e.partes == [] and e.issue_id is None
        ocupado = mundo.lib / e.destinos[0]
        ajeno_bytes = ocupado.read_bytes()
        assert ajeno_bytes.count(b"AJENO") > 0 or len(ajeno_bytes) > 0
        # El reintento reserva el siguiente nombre libre y el ajeno sigue intacto.
        r2 = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e2 = await mundo.estado()
        assert r2.estado == "asignado" and ocupado.read_bytes() == ajeno_bytes
        assert e2.ruta.endswith("(1).cbz") and e2.ruta != str(ocupado)

    @pytest.mark.asyncio
    async def test_asignar_reintenta_solo_con_el_siguiente_nombre_cuando_un_ajeno_ocupa_el_destino(self, mundo):
        hechos = {"n": 0}

        async def intruso_una_vez(punto):
            if punto == "tras_copiar" and hechos["n"] == 0:
                hechos["n"] += 1
                async with mundo.fabrica() as s:
                    destino = Path((await s.execute(text(
                        "SELECT destino FROM asignacion_operaciones WHERE estado = 'preparada'"))).scalar())
                hacer_cbz(destino, "AJENO", relleno=777)
        r = await mundo.servicio(gancho=intruso_una_vez).asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "asignado" and e.ruta.endswith("(1).cbz")
        assert e.ops == ["cancelada", "limpiada"] and e.partes == [] and not e.origen_existe

    @pytest.mark.asyncio
    async def test_un_montaje_sin_publicacion_segura_rechaza_la_operacion(self, mundo, monkeypatch):
        import errno

        import zascarr.services.asignacion as proto
        monkeypatch.setattr(proto, "_renameat2_noreplace",
                            lambda *_a: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "no")))
        monkeypatch.setattr(os, "link", lambda *_a: (_ for _ in ()).throw(OSError(errno.EPERM, "sin enlaces")))
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "error" and "no permite publicar sin reemplazar" in r.motivo
        assert e.origen_existe and e.destinos == [] and e.partes == [] and e.issue_id is None


class TestCandadoYPoolReutilizable:
    """El candado es de TRANSACCIÓN: ninguna conexión que vuelva al pool puede conservarlo."""

    async def _pool(self, mundo):
        motor = create_async_engine(url_asyncpg(mundo.url), pool_size=3, max_overflow=0)
        return motor, async_sessionmaker(motor, expire_on_commit=False)

    async def _candados(self, mundo) -> int:
        async with mundo.fabrica() as s:
            return (await s.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"))).scalar()

    @pytest.mark.asyncio
    async def test_tras_una_operacion_normal_el_pool_no_retiene_candados(self, mundo):
        motor, fab = await self._pool(mundo)
        try:
            r = await AsignacionService(fab, mundo.lib).asignar(mundo.file_id, mundo.serie_id, "12")
            assert r.estado == "asignado"
            assert await self._candados(mundo) == 0              # las conexiones siguen en el pool, sin candado
        finally:
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_cancelar_la_operacion_no_deja_el_candado_en_el_pool(self, mundo):
        motor, fab = await self._pool(mundo)
        dentro = asyncio.Event()

        async def gancho(punto):
            if punto == "tras_preparar":
                dentro.set()
                await asyncio.sleep(30)
        try:
            servicio = AsignacionService(fab, mundo.lib, gancho=gancho)
            op = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
            tarea = asyncio.create_task(servicio._ejecutar(op))        # SIN escudo: cancelación directa
            await dentro.wait()
            assert await self._candados(mundo) == 1                    # mientras trabaja, lo tiene
            tarea.cancel()
            with pytest.raises(asyncio.CancelledError):
                await tarea
            await asyncio.sleep(0.3)
            assert await self._candados(mundo) == 0                    # al cancelar, no queda en el pool
            # y la conexión reutilizada funciona: la operación huérfana se completa después
            assert [x.estado for x in await AsignacionService(fab, mundo.lib).reconciliar()] == ["asignado"]
        finally:
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_si_la_conexion_del_candado_muere_o_falla_al_cerrar_no_queda_nada_retenido(self, mundo, monkeypatch):
        """El equivalente de «falla el desbloqueo»: el cierre de la sesión del candado revienta."""
        motor, fab = await self._pool(mundo)
        original_close = AsyncSession.close
        estado = {"roto": False}

        async def close_que_falla_una_vez(self):
            if not estado["roto"]:
                estado["roto"] = True
                await original_close(self)       # la conexión vuelve al pool (reset = rollback)…
                raise ConnectionResetError("fallo al cerrar la sesión del candado")   # …y el cierre «falla»
            return await original_close(self)
        try:
            monkeypatch.setattr(AsyncSession, "close", close_que_falla_una_vez)
            with contextlib.suppress(ConnectionResetError):
                await AsignacionService(fab, mundo.lib).asignar(mundo.file_id, mundo.serie_id, "12")
            monkeypatch.setattr(AsyncSession, "close", original_close)
            assert await self._candados(mundo) == 0
            # El pool sigue sirviendo: se puede volver a reconciliar sin quedarse esperando un candado huérfano.
            await AsignacionService(fab, mundo.lib).reconciliar()
            assert await self._candados(mundo) == 0
        finally:
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_si_postgres_mata_la_conexion_del_candado_se_libera_y_se_puede_reconciliar(self, mundo):
        motor, fab = await self._pool(mundo)
        dentro = asyncio.Event()

        async def gancho(punto):
            if punto == "tras_preparar":
                dentro.set()
                await asyncio.sleep(1.0)
        try:
            servicio = AsignacionService(fab, mundo.lib, gancho=gancho)
            tarea = asyncio.create_task(servicio.asignar(mundo.file_id, mundo.serie_id, "12"))
            await dentro.wait()
            async with mundo.fabrica() as s:
                await s.execute(text(
                    "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND granted"))
                await s.commit()
            with contextlib.suppress(Exception):   # la operación puede acabar con el error de la conexión muerta
                await tarea
            await asyncio.sleep(0.3)
            assert await self._candados(mundo) == 0
            await AsignacionService(fab, mundo.lib).reconciliar()
            _asignado_del_todo(await mundo.estado(), mundo)
        finally:
            await motor.dispose()

    @pytest.mark.asyncio
    async def test_el_limite_de_simultaneas_no_interbloquea_con_un_pool_de_dos_por_operacion(self, mundo):
        otro = mundo.lib / "_Unsorted" / "Saga del Faro 13.cbz"
        contenido = hacer_cbz(otro, "q")
        async with mundo.fabrica() as s:
            f2 = File(id=uuid4(), file_path=str(otro), file_name=otro.name, file_format=FileFormat.CBZ,
                      file_size_bytes=len(contenido), sha256_hash=hashlib.sha256(contenido).hexdigest(),
                      metadata_={"match_status": "unsorted"})
            s.add(f2)
            await s.commit()
        motor = create_async_engine(url_asyncpg(mundo.url), pool_size=2, max_overflow=0)   # 2 conexiones = 1 operación
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            svc = AsignacionService(fab, mundo.lib, max_simultaneas=1)
            a, b = await asyncio.wait_for(asyncio.gather(
                svc.asignar(mundo.file_id, mundo.serie_id, "12"), svc.asignar(f2.id, mundo.serie_id, "13")), 60)
            assert a.estado == "asignado" and b.estado == "asignado"
        finally:
            await motor.dispose()


class TestIntegridadEnLaMismaEjecucion:
    """Revisión de #76: «lo verifiqué al publicar» no sostiene nada sin exclusión de escritores."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("punto", ["tras_publicar", "tras_confirmar"])
    async def test_un_destino_alterado_con_el_mismo_tamano_antes_de_limpiar_conserva_el_origen(self, mundo, punto):
        async def alterar(p):
            if p == punto:
                async with mundo.fabrica() as s:
                    destino = Path((await s.execute(text("SELECT destino FROM asignacion_operaciones"))).scalar())
                datos = bytearray(destino.read_bytes())
                datos[30] ^= 0xFF                                  # mismo tamaño, otro contenido
                destino.write_bytes(bytes(datos))
        r = await mundo.servicio(gancho=alterar).asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "reparacion_pendiente" and "íntegro" in r.motivo
        assert e.origen_existe and e.ops == ["confirmada"]          # el origen válido es la última copia


class _DosProcesos:
    """Dos «procesos» (dos motores, dos servicios) sobre la misma BD y los mismos ficheros."""

    def __init__(self, mundo, monkeypatch):
        self.mundo = mundo
        self.motores = [create_async_engine(url_asyncpg(mundo.url), pool_size=3, max_overflow=0) for _ in range(2)]
        self.fab = [async_sessionmaker(m, expire_on_commit=False) for m in self.motores]
        self.publicaciones: list[str] = []
        import zascarr.services.asignacion as proto
        real = proto._publicar

        def publicar_contando(temporal, destino):
            self.publicaciones.append(temporal.name)
            return real(temporal, destino)
        monkeypatch.setattr(proto, "_publicar", publicar_contando)

    def servicio(self, i: int, **kw) -> AsignacionService:
        return AsignacionService(self.fab[i], self.mundo.lib, **kw)

    async def matar_candado(self):
        """Postgres termina la conexión que sostiene el candado (la primera ejecución SIGUE viva en Python)."""
        async with self.mundo.fabrica() as s:
            await s.execute(text("SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND granted"))
            await s.commit()
        await asyncio.sleep(0.3)

    async def cerrar(self):
        for m in self.motores:
            await m.dispose()


class TestPerdidaDelCandadoMientrasSigueElTrabajo:
    """El candado desaparece con su conexión, pero el ejecutor antiguo sigue vivo: no puede actuar."""

    async def _escenario(self, mundo, monkeypatch, punto_de_pausa, *, borrar_b=None, vigente_siempre=False):
        dp = _DosProcesos(mundo, monkeypatch)
        parada, seguir = asyncio.Event(), asyncio.Event()
        borrados_a: list[Path] = []

        async def gancho_a(p):
            if p == punto_de_pausa:
                parada.set()
                await seguir.wait()

        def borrar_a(p):
            borrados_a.append(p)
            p.unlink()
        if vigente_siempre:
            import zascarr.services.asignacion as proto

            async def siempre(self):
                return True
            monkeypatch.setattr(proto._Propiedad, "vigente", siempre)
        a = asyncio.create_task(dp.servicio(0, gancho=gancho_a, borrar=borrar_a).asignar(mundo.file_id, mundo.serie_id, "12"))
        await parada.wait()
        await dp.matar_candado()
        # La segunda ejecución ENTRA mientras la primera sigue activa (pausada, no terminada).
        kw = {"borrar": borrar_b} if borrar_b else {}
        rb = await dp.servicio(1, **kw).reconciliar()
        assert not a.done()
        antes = len(dp.publicaciones)
        seguir.set()
        try:
            ra = await asyncio.wait_for(a, 60)
        except Exception as exc:  # noqa: BLE001 — también valdría que la conexión muerta lo hiciera fallar
            ra = exc
        return dp, ra, rb, antes, borrados_a

    @pytest.mark.asyncio
    async def test_el_antiguo_no_publica_tras_perder_el_candado(self, mundo, monkeypatch):
        dp, ra, rb, antes, _ = await self._escenario(mundo, monkeypatch, "tras_copiar")
        try:
            assert [x.estado for x in rb] == ["asignado"]                   # B completó TODO
            assert getattr(ra, "estado", None) == "propiedad_perdida"
            assert len(dp.publicaciones) == antes == 1                      # A no llegó a publicar: solo publicó B
            _asignado_del_todo(await mundo.estado(), mundo)                  # sin temporales de A
        finally:
            await dp.cerrar()

    @pytest.mark.asyncio
    async def test_el_antiguo_no_confirma_tras_perder_el_candado(self, mundo, monkeypatch):
        confirmaciones: list[int] = []
        original = AsignacionService._confirmar

        async def contando(self, op, prop):
            confirmaciones.append(prop.epoca)
            return await original(self, op, prop)
        monkeypatch.setattr(AsignacionService, "_confirmar", contando)
        dp, ra, rb, _, _ = await self._escenario(mundo, monkeypatch, "tras_publicar")
        try:
            assert [x.estado for x in rb] == ["asignado"]
            assert getattr(ra, "estado", None) == "propiedad_perdida"
            assert confirmaciones == [2]                                     # solo la época de B llegó a confirmar
            _asignado_del_todo(await mundo.estado(), mundo)
        finally:
            await dp.cerrar()

    @pytest.mark.asyncio
    async def test_el_antiguo_no_borra_el_origen_tras_perder_el_candado(self, mundo, monkeypatch):
        def b_no_puede_borrar(_p):
            raise PermissionError("B no puede borrar el origen")
        dp, ra, rb, _, borrados_a = await self._escenario(
            mundo, monkeypatch, "tras_confirmar", borrar_b=b_no_puede_borrar)
        try:
            e = await mundo.estado()
            assert [x.estado for x in rb] == ["asignado_limpieza_pendiente"]  # B dejó la limpieza pendiente
            assert getattr(ra, "estado", None) == "propiedad_perdida"
            assert borrados_a == [] and e.origen_existe                       # A NO llegó a borrar
            assert e.ops == ["confirmada"]                                    # y no cerró la operación de B
        finally:
            await dp.cerrar()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("punto", ["tras_copiar", "tras_publicar"])
    async def test_aunque_la_comprobacion_de_candado_fallara_el_vallado_de_epoca_protege_la_bd(self, mundo, monkeypatch, punto):
        """Defensa en profundidad: con `vigente()` mentiroso, A todavía no puede cerrar ni confirmar la operación de B."""
        dp, ra, rb, _, _ = await self._escenario(mundo, monkeypatch, punto, vigente_siempre=True)
        try:
            assert [x.estado for x in rb] == ["asignado"]
            assert getattr(ra, "estado", None) == "propiedad_perdida"       # el vallado de época lo detiene
            e = await mundo.estado()
            assert e.ops == ["limpiada"]                                     # la operación de B no fue alterada por A
            _asignado_del_todo(e, mundo)
        finally:
            await dp.cerrar()


class TestLimiteCompartido:
    """El límite de simultáneas es del MOTOR (del pool), no de cada instancia del servicio."""

    @pytest.mark.asyncio
    async def test_dos_instancias_sobre_el_mismo_motor_comparten_el_cupo(self, mundo):
        assert mundo.servicio()._cupo is mundo.servicio()._cupo

    @pytest.mark.asyncio
    async def test_motores_distintos_tienen_cupos_distintos(self, mundo):
        otro = create_async_engine(url_asyncpg(mundo.url), poolclass=NullPool)
        try:
            ajeno = AsignacionService(async_sessionmaker(otro, expire_on_commit=False), mundo.lib)
            assert ajeno._cupo is not mundo.servicio()._cupo
        finally:
            await otro.dispose()

    @pytest.mark.asyncio
    async def test_un_limite_distinto_para_el_mismo_motor_es_un_error_de_configuracion(self, mundo):
        _ = mundo.servicio(max_simultaneas=1)._cupo                  # fija 1 para este motor
        with pytest.raises(ValueError, match="ya tiene un límite de 1"):
            _ = mundo.servicio(max_simultaneas=2)._cupo
        with pytest.raises(ValueError, match="al menos 1"):
            _ = AsignacionService(mundo.fabrica, mundo.lib, max_simultaneas=0)._cupo

    @pytest.mark.asyncio
    async def test_la_segunda_operacion_espera_a_la_primera_aunque_use_otra_instancia(self, mundo):
        otro = mundo.lib / "_Unsorted" / "Saga del Faro 13.cbz"
        contenido = hacer_cbz(otro, "q")
        async with mundo.fabrica() as s:
            f2 = File(id=uuid4(), file_path=str(otro), file_name=otro.name, file_format=FileFormat.CBZ,
                      file_size_bytes=len(contenido), sha256_hash=hashlib.sha256(contenido).hexdigest(),
                      metadata_={"match_status": "unsorted"})
            s.add(f2)
            await s.commit()
        eventos: list[str] = []
        dentro, soltar = asyncio.Event(), asyncio.Event()

        async def gancho_a(punto):
            if punto == "tras_preparar":
                eventos.append("A dentro")
                dentro.set()
                await soltar.wait()
                eventos.append("A suelta")

        async def gancho_b(punto):
            if punto == "tras_preparar":
                eventos.append("B dentro")
        a = asyncio.create_task(mundo.servicio(gancho=gancho_a).asignar(mundo.file_id, mundo.serie_id, "12"))
        await dentro.wait()
        b = asyncio.create_task(mundo.servicio(gancho=gancho_b).asignar(f2.id, mundo.serie_id, "13"))
        await asyncio.sleep(0.8)
        assert eventos == ["A dentro"]                            # B no ha empezado: límite 1 compartido
        soltar.set()
        ra, rb = await asyncio.gather(a, b)
        assert (ra.estado, rb.estado) == ("asignado", "asignado") and eventos == ["A dentro", "A suelta", "B dentro"]

    @pytest.mark.asyncio
    async def test_el_pool_debe_dar_para_dos_conexiones_por_operacion(self, mundo):
        from zascarr.services.asignacion import comprobar_pool
        chico = create_async_engine(url_asyncpg(mundo.url), pool_size=3, max_overflow=0)
        grande = create_async_engine(url_asyncpg(mundo.url), pool_size=5, max_overflow=2)
        try:
            assert comprobar_pool(chico, 1) and not comprobar_pool(chico, 2)
            assert comprobar_pool(grande, 3) and not comprobar_pool(grande, 4)
        finally:
            await chico.dispose()
            await grande.dispose()


class TestValladoDeEpocaEnLaBd:
    """Cada escritura de un ejecutor antiguo se rechaza en la propia BD, sin depender de ninguna comprobación previa."""

    async def _con_epoca_2(self, mundo):
        servicio = mundo.servicio()
        op_id = await servicio._preparar(mundo.file_id, mundo.serie_id, "12")
        assert await servicio._tomar_epoca(op_id) == 1          # el ejecutor ANTIGUO
        assert await servicio._tomar_epoca(op_id) == 2          # el que lo sustituyó
        return servicio, op_id

    @pytest.mark.asyncio
    async def test_cerrar_con_una_epoca_antigua_no_cambia_nada(self, mundo):
        servicio, op_id = await self._con_epoca_2(mundo)
        assert await servicio._cerrar(op_id, "cancelada", 1) is False
        assert (await mundo.estado()).ops == ["preparada"]
        assert await servicio._cerrar(op_id, "cancelada", 2) is True      # la vigente sí puede

    @pytest.mark.asyncio
    async def test_confirmar_con_una_epoca_antigua_no_escribe_ni_una_fila(self, mundo):
        from zascarr.services.asignacion import _Propiedad
        servicio, op_id = await self._con_epoca_2(mundo)
        op = await servicio._op(op_id)
        # El destino ya está publicado (como si la ejecución antigua hubiera llegado hasta aquí).
        destino = Path(op["destino"])
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(mundo.origen.read_bytes())
        r = await servicio._confirmar(op, _Propiedad(None, 0, 1))
        e = await mundo.estado()
        assert r.estado == "propiedad_perdida"
        assert e.issue_id is None and e.issues == 0 and e.alias == 0 and e.ruta == str(mundo.origen)
        assert e.ops == ["preparada"]


class TestFalloDeEscrituraAlPublicar:
    """Un `OSError` al publicar no es siempre «no se publicó nada». Se distinguen tres casos:

    1. anterior a publicar (solo lectura, permisos, espacio): se retira la copia propia y se cancela;
    2. publicación REALIZADA y fallo posterior (`link` creó el destino y no se pudo retirar el temporal):
       se sigue hacia confirmar y el residuo se retira con el destino ya acreditado;
    3. resultado INCIERTO (el destino aparece tras el error): no se cancela ni se libera la reserva."""

    @staticmethod
    def _temporales_bloqueados(monkeypatch):
        """`Path.unlink` falla para los nombres temporales (`*.part*`), como un directorio sin permiso de borrado."""
        unlink = Path.unlink

        def unlink_selectivo(self, *a, **k):
            if ".part" in self.name and self.exists():
                raise PermissionError(13, "sin permiso para borrar")
            return unlink(self, *a, **k)
        monkeypatch.setattr(Path, "unlink", unlink_selectivo)
        return lambda: monkeypatch.setattr(Path, "unlink", unlink)

    @pytest.mark.asyncio
    async def test_oserror_antes_de_publicar_cancela_limpia_y_se_puede_reintentar(self, mundo, monkeypatch):
        import zascarr.services.asignacion as modulo
        publicar = modulo._publicar

        def publicar_roto(temporal, destino):
            raise OSError(30, "Read-only file system")
        monkeypatch.setattr(modulo, "_publicar", publicar_roto)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "error" and "Read-only" not in r.motivo
        assert e.ops == ["cancelada"] and e.origen_existe and e.issue_id is None
        assert e.partes == [] and e.destinos == []                 # ni copia a medias ni destino
        monkeypatch.setattr(modulo, "_publicar", publicar)          # el disco vuelve a estar bien
        r2 = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e2 = await mundo.estado()
        assert r2.estado == "asignado" and e2.ops == ["cancelada", "limpiada"] and len(e2.destinos) == 1

    @pytest.mark.asyncio
    async def test_publicado_con_link_y_fallo_al_retirar_el_temporal_no_cancela_y_conserva_el_origen(self, mundo, monkeypatch):
        """Regresión del mecanismo: `link` crea el destino y `unlink(temporal)` falla. Cancelar aquí dejaría un
        destino publicado SIN operación viva que lo reconcilie."""
        import errno

        import zascarr.services.asignacion as modulo

        def sin_renameat2(origen, destino):
            raise OSError(errno.EINVAL, "no soportado")            # fuerza el camino link → unlink
        monkeypatch.setattr(modulo, "_renameat2_noreplace", sin_renameat2)
        restaurar = self._temporales_bloqueados(monkeypatch)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        # Destino publicado y CONFIRMADO en la BD; el origen se conserva mientras quede un residuo; la operación sigue viva.
        assert r.estado == "asignado_limpieza_pendiente"
        assert e.ops == ["confirmada"] and e.origen_existe and e.issue_id is not None
        assert len(e.destinos) == 1 and len(e.partes) == 1          # el residuo está identificado, no perdido
        assert Path(e.ruta).read_bytes() == mundo.origen.read_bytes()
        # La reconciliación (arranque o reintento) lo cierra cuando ya se puede borrar.
        restaurar()
        rs = await mundo.servicio().reconciliar()
        e2 = await mundo.estado()
        assert [x.estado for x in rs] == ["asignado"]
        assert e2.ops == ["limpiada"] and e2.partes == [] and not e2.origen_existe and len(e2.destinos) == 1

    @pytest.mark.asyncio
    async def test_fallo_al_retirar_el_temporal_en_el_manejo_del_error_deja_la_operacion_viva(self, mundo, monkeypatch):
        """Nada publicado, y retirar la copia propia también falla: no se cancela (se perdería la pista del
        temporal) y el resultado es explícito. Reintentar retira el residuo y completa."""
        import zascarr.services.asignacion as modulo
        publicar = modulo._publicar

        def publicar_roto(temporal, destino):
            raise OSError(28, "No space left on device")
        monkeypatch.setattr(modulo, "_publicar", publicar_roto)
        restaurar = self._temporales_bloqueados(monkeypatch)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "error" and "temporal" in r.motivo
        assert e.ops == ["preparada"] and e.origen_existe and e.destinos == [] and len(e.partes) == 1
        # Reintentar con el temporal anterior TODAVÍA imposible de retirar: resultado explícito, no excepción,
        # y la operación sigue viva.
        r_mid = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e_mid = await mundo.estado()
        assert r_mid.estado == "error" and "temporal anterior" in r_mid.motivo
        assert e_mid.ops == ["preparada"] and e_mid.origen_existe and e_mid.destinos == []
        restaurar()
        monkeypatch.setattr(modulo, "_publicar", publicar)
        r2 = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")   # continúa LA MISMA operación
        e2 = await mundo.estado()
        assert r2.estado == "asignado" and e2.ops == ["limpiada"] and e2.partes == [] and len(e2.destinos) == 1

    @pytest.mark.asyncio
    async def test_resultado_incierto_con_el_destino_presente_no_cancela_ni_borra(self, mundo, monkeypatch):
        """Un montaje de red que publica y falla al responder: el destino aparece tras el error."""
        import os

        import zascarr.services.asignacion as modulo

        def publica_y_falla(temporal, destino):
            os.link(temporal, destino)
            raise OSError(5, "Input/output error")
        monkeypatch.setattr(modulo, "_publicar", publica_y_falla)
        r = await mundo.servicio().asignar(mundo.file_id, mundo.serie_id, "12")
        e = await mundo.estado()
        assert r.estado == "pendiente_de_comprobar"
        assert e.ops == ["preparada"] and e.origen_existe and len(e.destinos) == 1 and len(e.partes) == 1
        monkeypatch.undo()
        rs = await mundo.servicio().reconciliar()                    # comprueba el destino por contenido y sigue
        e2 = await mundo.estado()
        assert [x.estado for x in rs] == ["asignado"]
        assert e2.ops == ["limpiada"] and e2.partes == [] and not e2.origen_existe and len(e2.destinos) == 1
