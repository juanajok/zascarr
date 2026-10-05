# ruff: noqa: E501
"""Registrar una biblioteca existente aunque YA haya catálogo — Postgres y ficheros reales.

Reproduce la situación que bloqueó una instalación real: la carpeta tiene cientos de CBZ/CBR, hay unas pocas
series dadas de alta y unas pocas filas registradas sin Issue, y no consta ningún registro completo. Se saltan sin
`TEST_DATABASE_URL`. Cada módulo crea su propia BD migrada.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Series
from zascarr.services import registro_biblioteca
from zascarr.services.library_adopter import EstadoAdopcion, LibraryAdopter

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
MARCADOR = "_library_adoption_done"


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


def _cbz(ruta: Path, marca: str) -> bytes:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", (marca * 3000).encode())
    return ruta.read_bytes()


def _cbr(ruta: Path, marca: str) -> bytes:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"Rar!\x1a\x07\x00" + (marca * 3000).encode())
    return ruta.read_bytes()


class Mundo:
    """10 archivos en disco (6 CBZ + 4 CBR, dos de ellos idénticos), 5 series, 3 filas ya registradas que
    SÍ están en disco, 2 filas registradas cuyo archivo ya no está y 1 fila fuera de la biblioteca."""

    def __init__(self, url: str, tmp: Path):
        self.lib = tmp / "lib"
        self.lib.mkdir()
        self.motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        self.fabrica = async_sessionmaker(self.motor, expire_on_commit=False)
        self.contenido: dict[Path, bytes] = {}

    async def sembrar(self) -> Mundo:
        async with self.motor.begin() as c:
            await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, local_aliases, "
                                 "runtime_settings, import_runs CASCADE"))
            await c.execute(text("INSERT INTO runtime_settings (id, \"values\") VALUES (1, '{}')"))
        for i in range(1, 7):
            ruta = self.lib / "Comics" / f"Coleccion {i}" / f"Obra rara {i:02d}.cbz"
            self.contenido[ruta] = _cbz(ruta, chr(96 + i))
        for i in range(1, 5):
            ruta = self.lib / "BD" / f"Album {i}" / f"Tomo raro {i:02d}.cbr"
            self.contenido[ruta] = _cbr(ruta, chr(110 + i))
        # Dos archivos con EXACTAMENTE el mismo contenido: uno se registra y el otro es «repetido».
        gemelo = self.lib / "BD" / "Album 1" / "Tomo raro 01 (copia).cbr"
        self.contenido[gemelo] = (self.lib / "BD" / "Album 1" / "Tomo raro 01.cbr").read_bytes()
        gemelo.write_bytes(self.contenido[gemelo])
        async with self.fabrica() as s:
            self.series = []
            for t in ("Saga del Faro", "Cronicas Lunares", "Patrulla Azul", "El Gato Gris", "Zona Cero"):
                serie = Series(id=uuid4(), title=t, tradition=ComicTradition.AMERICAN, start_year=2010)
                s.add(serie)
                self.series.append(serie.id)
            await s.flush()
            registradas = [r for r in sorted(self.contenido) if "Comics" in str(r)][:3]   # los gemelos quedan sin registrar
            for ruta in registradas:
                s.add(File(id=uuid4(), file_path=str(ruta), file_name=ruta.name,
                           file_format=FileFormat(ruta.suffix.lstrip(".")), file_size_bytes=len(self.contenido[ruta]),
                           sha256_hash=hashlib.sha256(self.contenido[ruta]).hexdigest(),
                           metadata_={"match_status": "unsorted", "ajuste_manual": "no-tocar"}))
            for k in (1, 2):                        # registradas cuyo archivo ya no está
                s.add(File(id=uuid4(), file_path=str(self.lib / "Comics" / f"Desaparecida {k}.cbz"),
                           file_name=f"Desaparecida {k}.cbz", file_format=FileFormat.CBZ, sha256_hash=f"{k}" * 64))
            s.add(File(id=uuid4(), file_path="/otro/sitio/ajeno.cbz", file_name="ajeno.cbz",
                       file_format=FileFormat.CBZ, sha256_hash="f" * 64))
            await s.commit()
        self.registradas_antes = registradas
        return self

    def hashes_en_disco(self) -> dict[str, str]:
        return {str(p.relative_to(self.lib)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.lib.rglob("*")) if p.is_file()}

    async def n_files(self) -> int:
        async with self.fabrica() as s:
            return (await s.execute(select(func.count(File.id)))).scalar()

    async def marcador(self) -> bool:
        async with self.fabrica() as s:
            valor = (await s.execute(text(f"SELECT \"values\" ->> '{MARCADOR}' FROM runtime_settings WHERE id = 1"))).scalar()
        return valor == "true"

    async def cerrar(self):
        await self.motor.dispose()


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


class TestEstadoYOferta:

    async def test_con_catalogo_previo_se_ofrece_el_registro_pero_no_arranca_nada_solo(self, mundo):
        async with mundo.fabrica() as s:
            a = LibraryAdopter(s)
            assert await a.estado() is EstadoAdopcion.CATALOGO_PREVIO
            assert await a.puede_registrar() is True      # acción consciente…
            assert await a.should_run() is False          # …y el disparo AUTOMÁTICO del arranque sigue sin disparar
        assert await mundo.n_files() == 6                 # consultar el estado no escribió nada

    async def test_con_catalogo_vacio_el_disparo_automatico_sigue_como_antes(self, mundo):
        async with mundo.motor.begin() as c:
            await c.execute(text("TRUNCATE series CASCADE"))
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).should_run() is True

    async def test_con_el_marcador_no_se_ofrece(self, mundo):
        async with mundo.fabrica() as s:
            a = LibraryAdopter(s)
            await a.adopt()
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).estado() is EstadoAdopcion.HECHA
            assert await LibraryAdopter(s).puede_registrar() is False

    async def test_sin_tebeos_no_se_ofrece_aunque_haya_catalogo(self, mundo):
        for p in list(mundo.lib.rglob("*.cb*")):
            p.unlink()
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).estado() is EstadoAdopcion.SIN_TEBEOS


class TestInventario:

    async def test_cruza_rutas_y_no_resta_totales(self, mundo):
        async with mundo.fabrica() as s:
            inv = await LibraryAdopter(s).inventario()
        assert inv.en_disco == 11 and inv.cbz == 6 and inv.cbr == 5      # 5 CBR: 4 álbumes + la copia
        assert inv.ya_registrados == 3 and inv.nuevos == 8
        assert inv.registrados_sin_fichero == 2          # las dos desaparecidas; la fila ajena a la biblioteca no cuenta
        assert inv.en_disco - inv.ya_registrados == inv.nuevos

    async def test_no_lee_el_contenido_ni_escribe_nada(self, mundo, monkeypatch):
        import zascarr.services.library_adopter as modulo
        monkeypatch.setattr(modulo, "_triage_and_match", lambda *a, **k: (_ for _ in ()).throw(AssertionError("leyó contenido")))
        antes = mundo.hashes_en_disco()
        async with mundo.fabrica() as s:
            await LibraryAdopter(s).inventario()
        assert mundo.hashes_en_disco() == antes and await mundo.n_files() == 6


class TestRegistro:

    async def test_registra_lo_nuevo_sin_tocar_nada_de_lo_existente(self, mundo):
        antes_disco = mundo.hashes_en_disco()
        async with mundo.fabrica() as s:
            previas = {f.id: (f.file_path, f.issue_id, dict(f.metadata_ or {}))
                       for f in (await s.execute(select(File))).scalars().all()}
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert mundo.hashes_en_disco() == antes_disco            # ni un archivo movido, renombrado o cambiado
        assert informe.already_registered == 3 and informe.to_process == 8 and informe.processed == 8
        assert informe.error_count == 0 and informe.duplicate_count == 1       # la copia idéntica
        assert informe.registered_count + informe.unsorted_count == 7 == informe.added_count
        # Mirados, añadidos, repetidos y errores son cosas distintas y cuadran: nada se pierde ni se cuenta dos veces.
        assert informe.processed == informe.added_count + informe.duplicate_count + informe.error_count + informe.by_other_run
        async with mundo.fabrica() as s:
            filas = (await s.execute(select(File))).scalars().all()
            series = (await s.execute(select(func.count(Series.id)))).scalar()
        assert series == 5                                        # el catálogo se conserva
        for f in filas:                                           # las filas previas, intactas
            if f.id in previas:
                assert (f.file_path, f.issue_id, dict(f.metadata_ or {})) == previas[f.id]
        assert len(filas) == 6 + 7
        assert {f.file_format.value for f in filas if f.file_name.startswith(("Obra", "Tomo"))} == {"cbz", "cbr"}   # CBZ y CBR
        assert await mundo.marcador() is True

    async def test_repetirlo_no_duplica_nada(self, mundo):
        async with mundo.fabrica() as s:
            await LibraryAdopter(s).adopt()
        n = await mundo.n_files()
        async with mundo.fabrica() as s:
            segundo = await LibraryAdopter(s).adopt()
        # Lo único que vuelve a aparecer es la copia idéntica, que se reconoce como repetida otra vez y no se registra.
        assert segundo.registered_count == 0 and segundo.unsorted_count == 0 and segundo.error_count == 0
        assert segundo.to_process == segundo.duplicate_count == 1
        assert await mundo.n_files() == n
        async with mundo.fabrica() as s:
            repetidas = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
        assert repetidas == 0

    async def test_un_archivo_que_falla_deja_el_resto_registrado_y_el_marcador_sin_poner(self, mundo, monkeypatch):
        original = LibraryAdopter._adopt_file

        async def falla_uno(self, path, report, pista=None):
            if path.name == "Obra rara 04.cbz":
                raise RuntimeError("disco roto en /ruta/secreta")
            return await original(self, path, report, pista)
        monkeypatch.setattr(LibraryAdopter, "_adopt_file", falla_uno)
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert informe.error_count == 1 and "secreta" not in informe.errors[0]
        assert await mundo.n_files() == 6 + 6                     # 7 nuevos menos el que falló
        assert await mundo.marcador() is False                    # no esconde lo pendiente
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).estado() is EstadoAdopcion.CATALOGO_PREVIO   # sigue ofreciendo continuar
            inv = await LibraryAdopter(s).inventario()
        assert inv.nuevos == 2          # el que falló y la copia idéntica (repetida, no registrada)

        monkeypatch.setattr(LibraryAdopter, "_adopt_file", original)       # el fallo se arregla: continuar
        async with mundo.fabrica() as s:
            segundo = await LibraryAdopter(s).adopt()
        assert segundo.already_registered == 9 and segundo.registered_count + segundo.unsorted_count == 1
        assert await mundo.n_files() == 6 + 7 and await mundo.marcador() is True

    async def test_un_error_de_la_bd_en_un_archivo_no_inutiliza_la_sesion_para_los_siguientes(self, mundo, monkeypatch):
        """Mecanismo: tras un `IntegrityError` en `flush` la transacción queda inservible; sin un savepoint por
        archivo, TODOS los siguientes fallaban en cascada. Aquí el 4.º viola una restricción NOT NULL (un error
        de datos que SÍ es un error) y los demás se registran igualmente. Que otra ejecución haya registrado la
        misma ruta (restricción única de `file_path`) NO es un error: se prueba en `TestSolapamiento`."""
        original = LibraryAdopter._adopt_file

        async def choca_con_otra_fila(self, path, report, pista=None):
            if path.name == "Obra rara 04.cbz":
                self._db.add(File(id=uuid4(), file_path=str(path) + ".mala", file_name=None,
                                  file_format=FileFormat.CBZ))
                await self._db.flush()                                  # IntegrityError (NOT NULL)
            return await original(self, path, report, pista)
        monkeypatch.setattr(LibraryAdopter, "_adopt_file", choca_con_otra_fila)
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert informe.error_count == 1 and "IntegrityError" in informe.errors[0]
        assert informe.registered_count + informe.unsorted_count == 6          # los otros 6 nuevos, sin cascada
        assert await mundo.marcador() is False

    async def test_un_corte_a_mitad_conserva_los_lotes_ya_confirmados(self, mundo):
        """Con una sola transacción un corte lo perdía todo. Se confirma cada lote."""
        class CorteError(Exception):
            pass

        def corta_en_el_quinto(report):
            if report.processed == 5:
                raise CorteError

        async with mundo.fabrica() as s:
            with pytest.raises(CorteError):
                await LibraryAdopter(s).adopt(progreso=corta_en_el_quinto, lote=2)
        # Cortó al terminar el 5.º archivo con lotes de 2: están confirmados los 4 primeros (3 añadidos y 1
        # repetido). El 5.º estaba en un lote a medias y se pierde con la sesión: exactamente 3, ni más ni menos.
        assert await mundo.n_files() == 6 + 3
        assert await mundo.marcador() is False
        async with mundo.fabrica() as s:                           # y se continúa sin duplicar
            await LibraryAdopter(s).adopt()
        assert await mundo.n_files() == 6 + 7 and await mundo.marcador() is True


class TestFalloDespuesDeConfirmarUnLote:
    """Mecanismo: lo confirmado en un lote no depende de que los siguientes salgan bien, y el informe solo
    cuenta como «añadido» lo que se ha acreditado guardado: nunca un lote revertido o dudoso."""

    @staticmethod
    def _commit_que_falla(monkeypatch, *, en_la_llamada: int, guardando_antes: bool = False):
        """Parchea `AsyncSession.commit`: la llamada nº `en_la_llamada` lanza `ConnectionError`. Con
        `guardando_antes` el commit SÍ se hace y después falla (se guardó y la respuesta se perdió)."""
        from sqlalchemy.ext.asyncio import AsyncSession
        original = AsyncSession.commit
        llamadas = {"n": 0}

        async def commit(self):
            llamadas["n"] += 1
            if llamadas["n"] == en_la_llamada:
                if guardando_antes:
                    await original(self)
                raise ConnectionError("password=secreta host=10.0.0.5")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit)
        return lambda: monkeypatch.setattr(AsyncSession, "commit", original)

    async def test_lote_revertido_no_se_cuenta_como_anadido(self, mundo, monkeypatch):
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2)
        vistas = []
        async with mundo.fabrica() as s:
            with pytest.raises(ConnectionError):
                await LibraryAdopter(s).adopt(
                    lote=2, progreso=lambda r: vistas.append(
                        (r.added_count, r.duplicate_count, r.reverted, r.unknown, r.pending_count, r.processed)))
        restaurar()
        # 1.er lote (copia + su gemelo): 1 añadido y 1 repetido, CONFIRMADOS. 2.º lote (2 archivos): el commit
        # falla y se comprueba que no quedó nada → 2 «no guardados», 0 añadidos de ese lote.
        assert vistas[-1] == (1, 1, 2, 0, 0, 4)
        assert await mundo.n_files() == 6 + 1                     # y la BD lo confirma
        assert await mundo.marcador() is False

    async def test_estado_y_pantalla_enseñan_lo_confirmado_y_no_los_intentos_del_lote_revertido(
            self, mundo, monkeypatch):
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2)
        monkeypatch.setattr(LibraryAdopter, "adopt", _adopt_con_lote_de(2, LibraryAdopter.adopt))
        registro_biblioteca.iniciar(mundo.fabrica)
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        restaurar()
        e = registro_biblioteca.estado_actual()
        assert e.fase.value == "interrumpido" and not e.completo and e.causa == "ConnectionError"
        assert (e.anadidos, e.repetidos, e.no_guardados, e.por_comprobar, e.procesados) == (1, 1, 2, 0, 4)
        assert "secreta" not in repr(e)

        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                     headers={"Origin": "http://localhost"}) as c:
            r = await c.get("/ui/auditoria/registro")
        assert "El registro ha quedado incompleto" in r.text and "Continuar el registro" in r.text
        assert "Biblioteca registrada" not in r.text
        assert "<strong>1</strong> añadidos al catálogo" in r.text            # el 1.º lote, no los 3 intentos
        assert "<strong>3</strong> añadidos" not in r.text
        assert "<strong>2</strong> del último grupo no llegaron a guardarse" in r.text
        assert "secreta" not in r.text and "10.0.0.5" not in r.text

    async def test_resultado_desconocido_no_se_cuenta_ni_como_anadido_ni_como_revertido(self, mundo, monkeypatch):
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2)

        async def no_se_puede_preguntar(self, rutas):
            return "desconocido"
        monkeypatch.setattr(LibraryAdopter, "_contrastar", no_se_puede_preguntar)
        monkeypatch.setattr(LibraryAdopter, "adopt", _adopt_con_lote_de(2, LibraryAdopter.adopt))
        registro_biblioteca.iniciar(mundo.fabrica)
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        restaurar()
        e = registro_biblioteca.estado_actual()
        assert (e.anadidos, e.no_guardados, e.por_comprobar) == (1, 0, 2)
        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                     headers={"Origin": "http://localhost"}) as c:
            r = await c.get("/ui/auditoria/registro")
        assert "no se ha podido comprobar si" in r.text and "llegaron a guardarse" in r.text
        assert "<strong>1</strong> añadidos al catálogo" in r.text
        assert "Biblioteca registrada" not in r.text

    async def test_el_contraste_no_depende_de_la_sesion_que_acaba_de_fallar(self, mundo, monkeypatch):
        """Tras un commit fallido la conexión de la sesión puede estar muerta: si el contraste usara esa misma
        sesión, un lote que de verdad se revirtió se daría por «desconocido». Aquí la sesión que falla queda
        inservible (como con la conexión caída) y aun así se acredita que no quedó nada → «no guardados»."""
        from sqlalchemy.ext.asyncio import AsyncSession
        original = AsyncSession.commit
        n = {"c": 0}

        async def commit_que_mata_la_sesion(self):
            n["c"] += 1
            if n["c"] == 2:
                async def muerta(*a, **k):
                    raise ConnectionError("conexión perdida")
                self.execute = muerta                                # a partir de aquí esta sesión no contesta
                self.rollback = muerta
                raise ConnectionError("conexión perdida")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit_que_mata_la_sesion)
        vistas = []
        async with mundo.fabrica() as s:
            with pytest.raises(ConnectionError):
                await LibraryAdopter(s).adopt(
                    lote=2, progreso=lambda r: vistas.append((r.added_count, r.reverted, r.unknown)))
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert vistas[-1] == (1, 2, 0)          # revertido y ACREDITADO por otra sesión, no «desconocido»

    async def test_un_resultado_parcial_no_se_da_por_confirmado(self, mundo, monkeypatch):
        """Si tras el fallo solo algunas de las rutas del lote constan (p. ej. las puso otra ejecución), no se
        sabe qué pasó: ni «confirmado» ni «revertido». El intruso entra DESPUÉS del rollback de la sesión del
        lote (antes, esa sesión tiene la ruta bloqueada y su insert esperaría)."""
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2)
        contrastar = LibraryAdopter._contrastar

        async def contrastar_con_intruso(self, rutas):
            intruso = mundo.lib / "BD" / "Album 2" / "Tomo raro 02.cbr"          # una de las rutas del 2.º lote
            async with mundo.fabrica() as otra:
                otra.add(File(id=uuid4(), file_path=str(intruso), file_name=intruso.name,
                              file_format=FileFormat.CBR, sha256_hash=None))
                await otra.commit()
            return await contrastar(self, rutas)
        monkeypatch.setattr(LibraryAdopter, "_contrastar", contrastar_con_intruso)
        vistas = []
        async with mundo.fabrica() as s:
            with pytest.raises(ConnectionError):
                await LibraryAdopter(s).adopt(
                    lote=2, progreso=lambda r: vistas.append((r.added_count, r.reverted, r.unknown)))
        restaurar()
        assert vistas[-1] == (1, 0, 2)          # solo 1 de 2 rutas consta: desconocido, y NO añadido

    async def test_commit_que_se_guardo_pero_cuya_respuesta_se_perdio_se_cuenta_tras_contrastarlo(
            self, mundo, monkeypatch):
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2, guardando_antes=True)
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt(lote=2)       # NO lanza: se contrastó con otra sesión
        restaurar()
        assert informe.added_count == 7 and informe.reverted == 0 and informe.unknown == 0
        assert informe.error_count == 0 and await mundo.n_files() == 6 + 7 and await mundo.marcador() is True
        async with mundo.fabrica() as s:
            repetidas = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
        assert repetidas == 0

    async def test_si_falla_el_ultimo_commit_el_ultimo_lote_no_se_cuenta(self, mundo, monkeypatch):
        """Con el tamaño de lote por defecto (25) los 8 archivos nuevos son UN solo lote, el del commit final."""
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=1)
        vistas = []
        async with mundo.fabrica() as s:
            with pytest.raises(ConnectionError):
                await LibraryAdopter(s).adopt(progreso=lambda r: vistas.append(
                    (r.added_count, r.reverted, r.unknown, r.pending_count, r.processed)))
        restaurar()
        assert vistas[-1] == (0, 8, 0, 0, 8)
        assert await mundo.n_files() == 6 and await mundo.marcador() is False

    async def test_tras_un_lote_revertido_continuar_completa_sin_duplicar(self, mundo, monkeypatch):
        restaurar = self._commit_que_falla(monkeypatch, en_la_llamada=2)
        async with mundo.fabrica() as s:
            with pytest.raises(ConnectionError):
                await LibraryAdopter(s).adopt(lote=2)
        restaurar()
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).estado() is EstadoAdopcion.CATALOGO_PREVIO   # sigue ofreciendo continuar
            informe = await LibraryAdopter(s).adopt()
        assert informe.already_registered == 3 + 1 and informe.error_count == 0
        assert informe.added_count == 6                           # los 6 que faltaban (el gemelo es repetido)
        assert await mundo.n_files() == 6 + 7 and await mundo.marcador() is True


async def _vacio() -> set[str]:
    return set()


def _adopt_con_lote_de(lote: int, original):
    async def adopt(self, *, progreso=None, lote_=None):
        return await original(self, progreso=progreso, lote=lote)
    return adopt


class TestSolapamiento:
    """Dos solicitudes de registro a la vez no duplican ni se estorban."""

    async def test_dos_peticiones_http_a_la_vez_lanzan_un_solo_registro(self, mundo):
        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                     headers={"Origin": "http://localhost"}) as c:
            a, b = await asyncio.gather(c.post("/ui/auditoria/adoptar"), c.post("/ui/auditoria/adoptar"))
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert a.status_code == b.status_code == 200
        assert "Registrando tu biblioteca" in a.text and "Registrando tu biblioteca" in b.text
        assert await mundo.n_files() == 6 + 7                     # un solo registro: ni filas dobles ni lotes repetidos
        async with mundo.fabrica() as s:
            repetidas = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
            corridas = (await s.execute(text(
                "SELECT count(*) FROM import_runs WHERE details->>'kind' = 'adoption'"))).scalar()
        assert repetidas == 0 and corridas == 1

    async def test_una_lista_vieja_no_convierte_lo_ya_registrado_en_repetido_ni_en_error(self, mundo, monkeypatch):
        """Primera capa: la lista de «nuevos» es una foto de antes de empezar. Con una foto desfasada (otra
        ejecución registró cosas entretanto) lo ya registrado se cuenta como tal y no como «repetido de sí mismo»."""
        monkeypatch.setattr(LibraryAdopter, "_rutas_registradas", lambda self: _vacio())
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert informe.by_other_run == 3                      # las 3 que ya constaban
        assert informe.error_count == 0 and informe.duplicate_count == 1
        assert informe.added_count == 7 and await mundo.n_files() == 6 + 7

    async def test_sin_la_comprobacion_por_archivo_decide_la_restriccion_unica_y_no_es_un_error(self, mundo, monkeypatch):
        """Segunda capa: aunque la comprobación por archivo no existiera, el choque con `files.file_path` (otra
        ejecución la registró a la vez) se reconoce por su restricción y no se cuenta como error ni duplica."""
        async with mundo.motor.begin() as c:       # filas sin hash: el cotejo por contenido no las encuentra
            await c.execute(text("UPDATE files SET sha256_hash = NULL"))

        async def nunca(self, path):
            return False
        monkeypatch.setattr(LibraryAdopter, "_ya_registrada", nunca)
        monkeypatch.setattr(LibraryAdopter, "_rutas_registradas", lambda self: _vacio())
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert informe.by_other_run >= 3 and informe.error_count == 0
        assert await mundo.n_files() == 6 + 7 and await mundo.marcador() is True

    async def test_dos_ejecuciones_a_la_vez_desde_sesiones_distintas_no_duplican_ni_cuentan_error(self, mundo):
        """Aunque el bloqueo de proceso no existiera (otro proceso, un cambio futuro), la restricción única de
        `file_path` y la comprobación por archivo impiden filas dobles; lo que otra ejecución ya registró se
        cuenta aparte y NO es un error."""
        async def correr():
            async with mundo.fabrica() as s:
                return await LibraryAdopter(s).adopt(lote=1)
        a, b = await asyncio.gather(correr(), correr())
        assert await mundo.n_files() == 6 + 7
        async with mundo.fabrica() as s:
            repetidas = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
        assert repetidas == 0
        for informe in (a, b):
            assert informe.error_count == 0, informe.errors
            assert informe.processed == informe.added_count + informe.duplicate_count + informe.by_other_run
        # Entre las dos hay exactamente 7 añadidas; el resto, de una u otra, son repetidos o «de la otra».
        assert a.added_count + b.added_count == 7
        assert await mundo.marcador() is True


class TestEnSegundoPlano:

    async def _esperar(self):
        await asyncio.wait_for(registro_biblioteca._tarea, 60)

    async def test_corre_en_su_tarea_y_acaba_completo(self, mundo):
        assert registro_biblioteca.iniciar(mundo.fabrica) is True
        assert registro_biblioteca.estado_actual().en_marcha
        await self._esperar()
        e = registro_biblioteca.estado_actual()
        assert e.completo and e.procesados == 8 and e.ya_registrados == 3 and not e.errores
        assert e.registrados + e.sin_identificar + e.repetidos == 8

    async def test_una_sola_ejecucion_a_la_vez(self, mundo):
        assert registro_biblioteca.iniciar(mundo.fabrica) is True
        assert registro_biblioteca.iniciar(mundo.fabrica) is False
        await self._esperar()
        assert await mundo.n_files() == 6 + 7                     # no se duplicó nada

    async def test_un_fallo_general_queda_interrumpido_con_la_causa_saneada(self, mundo, monkeypatch):
        async def explota(self, *, progreso=None, lote=25):
            raise ConnectionError("password=secreta host=10.0.0.5")
        monkeypatch.setattr(LibraryAdopter, "adopt", explota)
        registro_biblioteca.iniciar(mundo.fabrica)
        await self._esperar()
        e = registro_biblioteca.estado_actual()
        assert e.fase.value == "interrumpido" and e.causa == "ConnectionError" and not e.completo
        assert "secreta" not in repr(e)


class TestPantalla:

    @pytest.fixture
    def cliente(self, mundo):
        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                 headers={"Origin": "http://localhost"})

    async def test_antes_de_registrar_enseña_el_inventario_y_que_el_catalogo_se_conserva(self, mundo, cliente):
        async with cliente as c:
            r = await c.get("/ui/auditoria/registro")
        assert r.status_code == 200
        assert "<strong>11</strong> tebeos en la carpeta" in r.text and "6 CBZ, 5 CBR" in r.text
        assert "<strong>3</strong> ya registrados" in r.text and "<strong>8</strong> por registrar" in r.text
        assert "Tus <strong>5</strong> series" in r.text and "se conservan" in r.text
        assert "registrados cuyo archivo" in r.text               # los 2 que faltan en disco se avisan
        assert "Registrar los 8 tebeos nuevos" in r.text
        assert await mundo.n_files() == 6                         # GET no escribe

    async def test_registrar_muestra_progreso_y_solo_al_final_anuncia_el_exito(self, mundo, cliente):
        async with cliente as c:
            r = await c.post("/ui/auditoria/adoptar")
            assert 'hx-trigger="every 2s"' in r.text and "Registrando tu biblioteca" in r.text
            assert "Mirando qué hay en la carpeta" in r.text           # aún no se conoce el total: no se inventa «0 de 1»
            assert "Biblioteca registrada" not in r.text          # nada de éxito mientras corre
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            r2 = await c.get("/ui/auditoria/registro")
        assert "<strong>8</strong> de <strong>8</strong> tebeos nuevos mirados" in r2.text
        assert "<strong>7</strong> añadidos al catálogo" in r2.text        # añadidos ≠ mirados (hay 1 repetido)
        assert "<strong>1</strong> repetidos" in r2.text
        assert "Biblioteca registrada" in r2.text and "every 2s" not in r2.text    # y deja de consultarse
        assert 'hx-get="/ui/_nav/estado"' in r2.text                  # el menú recuenta «Por revisar» al terminar
        assert "nav-recuento" not in r.text                           # mientras corre, no
        assert "Ni un archivo se ha movido ni renombrado" in r2.text
        assert "incompleto" not in r2.text

    async def test_con_errores_no_dice_registrada_y_ofrece_continuar(self, mundo, cliente, monkeypatch):
        original = LibraryAdopter._adopt_file

        async def falla_uno(self, path, report, pista=None):
            if path.name == "Obra rara 04.cbz":
                raise RuntimeError("x")
            return await original(self, path, report, pista)
        monkeypatch.setattr(LibraryAdopter, "_adopt_file", falla_uno)
        async with cliente as c:
            await c.post("/ui/auditoria/adoptar")
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            r = await c.get("/ui/auditoria/registro")
        assert "El registro ha quedado incompleto" in r.text and "Continuar el registro" in r.text
        assert "Biblioteca registrada" not in r.text
        assert "<strong>8</strong> de <strong>8</strong> tebeos nuevos mirados" in r.text   # miró todo…
        assert "<strong>6</strong> añadidos al catálogo" in r.text                          # …pero no añadió todo
        assert "<strong>1</strong> con error: no se han añadido" in r.text
        assert "Obra rara 04.cbz" in r.text                       # dice cuál

    async def test_adoptar_sin_nada_que_ofrecer_no_lanza_nada(self, mundo, cliente):
        for p in list(mundo.lib.rglob("*.cb*")):
            p.unlink()
        async with cliente as c:
            r = await c.post("/ui/auditoria/adoptar")
        assert "No hemos encontrado tebeos" in r.text and not registro_biblioteca.estado_actual().en_marcha
