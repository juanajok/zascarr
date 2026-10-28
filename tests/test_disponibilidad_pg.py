# ruff: noqa: E501
"""BL-R2 (#231) con Postgres real: lo que el ciclo deja escrito, cómo se lee y la lista de no disponibles.

Cubre los criterios 1, 2, 3, 5, 6, 8, 9, 10 y 12 contra una base de verdad (JSONB, orden, cursor) y ficheros reales. Se saltan sin
`TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, ImportRun, Issue, ResultadoComprobacion, Series
from zascarr.services import disponibilidad
from zascarr.services.importer import CLAVE_COMPROBACION, Importer

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
R = ResultadoComprobacion


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd):
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    async with motor.begin() as c:
        await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, series, import_runs CASCADE"))
    yield async_sessionmaker(motor, expire_on_commit=False)
    app.dependency_overrides.pop(get_db, None)
    await motor.dispose()


def _cliente(fabrica):
    async def _get_db():
        async with fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                             headers={"Origin": "http://localhost"})


def _run(inicio: datetime, details: dict) -> ImportRun:
    return ImportRun(id=uuid4(), started_at=inicio, finished_at=inicio, details=details)


def _comp(resultado: R, cuando: datetime, **extra) -> dict:
    return {"ambito": "biblioteca", "resultado": resultado.value, "archivos_registrados": 10, "ausentes": 0,
            "bajas_omitidas": resultado is not R.COMPROBADA, "fecha": cuando.isoformat(), **extra}


def _fila(ruta: str, **kw) -> File:
    return File(id=kw.pop("id", uuid4()), file_path=ruta, file_name=kw.pop("nombre", Path(ruta).name),
                file_format="cbz", **kw)


T0 = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)


class TestLecturaDelUltimoInforme:
    async def test_sin_ningun_ciclo_es_sin_dato(self, fabrica):
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
        assert d.sin_dato and not d.sin_verificar and d.ultima_valida is None

    async def test_ignora_auditoria_y_adopcion_y_toma_el_ultimo_ciclo_del_importador(self, fabrica):
        """Criterio 9: informes de otros tipos en la misma tabla (aunque llevaran la clave) no cuentan."""
        async with fabrica() as s:
            s.add_all([
                _run(T0, {"imported": [], CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0, archivos_registrados=500, ausentes=2)}),
                _run(T0 + timedelta(hours=1), {"imported": [], CLAVE_COMPROBACION: _comp(R.RAIZ_VACIA, T0 + timedelta(hours=1))}),
                # más recientes, de otra clase: no deben leerse como «el último ciclo»
                _run(T0 + timedelta(hours=2), {"kind": "audit", CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0 + timedelta(hours=2))}),
                _run(T0 + timedelta(hours=3), {"kind": "adoption", CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0 + timedelta(hours=3))}),
                _run(T0 + timedelta(hours=4), {"kind": "registro_incremental"}),
            ])
            await s.commit()
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
        assert d.resultado is R.RAIZ_VACIA and d.sin_verificar
        assert d.fecha == T0 + timedelta(hours=1)
        assert d.ultima_valida == T0  # la última que SÍ se completó, no la de auditoría/adopción de después

    async def test_un_ciclo_anterior_a_la_clave_se_lee_como_sin_dato_aunque_haya_una_comprobacion_mas_antigua(self, fabrica):
        async with fabrica() as s:
            s.add_all([_run(T0, {"imported": [], CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0)}),
                       _run(T0 + timedelta(days=1), {"imported": [], "disappeared": []})])  # el último: sin la clave
            await s.commit()
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
        assert d.sin_dato and d.ultima_valida is None and d.fecha is None  # no se reconstruye ninguna fecha

    async def test_una_clave_corrupta_no_rompe_la_lectura(self, fabrica):
        async with fabrica() as s:
            s.add(_run(T0, {CLAVE_COMPROBACION: {"resultado": "algo_nuevo", "fecha": "ayer"}}))
            await s.commit()
        async with fabrica() as s:
            assert (await disponibilidad.ultima_comprobacion(s)).sin_dato


class TestCicloCompletoDelImportador:
    """Criterios 2, 3 y 6 con el ciclo real (`scan_and_import`), la base real y el disco real."""

    @pytest.fixture
    def montaje(self, tmp_path, monkeypatch):
        vacio = tmp_path / "vacio"
        vacio.mkdir()
        ajustes = type("A", (), {})()
        ajustes.library_path = tmp_path / "lib"
        ajustes.transmission_download_dir = str(vacio / "t")
        ajustes.amule_incoming_dir = str(vacio / "a")
        ajustes.downloads_path = vacio / "d"
        monkeypatch.setattr("zascarr.services.importer.get_settings", lambda: ajustes)
        return ajustes.library_path

    async def _ciclo(self, fabrica):
        async with fabrica() as s:
            informe = await Importer(s).scan_and_import()
            await s.commit()
        return informe

    async def _ultimo(self, fabrica) -> dict:
        async with fabrica() as s:
            run = (await s.execute(select(ImportRun).order_by(ImportRun.started_at.desc()).limit(1))).scalar_one()
            return run.details

    async def _sembrar(self, fabrica, rutas: list[Path], **kw):
        async with fabrica() as s:
            s.add_all([_fila(str(r), **kw) for r in rutas])
            await s.commit()

    async def _estado_de_los_archivos(self, fabrica) -> list[tuple]:
        async with fabrica() as s:
            return (await s.execute(select(File.file_name, File.is_missing, File.missing_since).order_by(File.file_name))).all()

    async def test_raiz_inexistente_se_registra_y_no_cambia_ningun_archivo(self, fabrica, montaje):
        await self._sembrar(fabrica, [montaje / f"A{i}.cbz" for i in range(12)])
        antes = await self._estado_de_los_archivos(fabrica)

        informe = await self._ciclo(fabrica)

        assert informe.comprobacion.resultado is R.RAIZ_INACCESIBLE
        assert await self._estado_de_los_archivos(fabrica) == antes
        guardado = (await self._ultimo(fabrica))[CLAVE_COMPROBACION]
        assert guardado["resultado"] == "raiz_inaccesible" and guardado["archivos_registrados"] == 12
        assert guardado["bajas_omitidas"] is True and guardado["ambito"] == "biblioteca"
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
        assert d.sin_verificar and d.ultima_valida is None  # nunca hubo una comprobación válida

    async def test_raiz_vacia_y_desaparicion_masiva(self, fabrica, montaje):
        montaje.mkdir()
        await self._sembrar(fabrica, [montaje / f"A{i}.cbz" for i in range(12)])
        antes = await self._estado_de_los_archivos(fabrica)

        vacia = await self._ciclo(fabrica)
        assert vacia.comprobacion.resultado is R.RAIZ_VACIA

        (montaje / "otra-cosa.txt").write_text("x")  # ya no está vacía, pero faltan los 12 registrados
        masiva = await self._ciclo(fabrica)
        assert masiva.comprobacion.resultado is R.DESAPARICION_MASIVA
        assert (masiva.comprobacion.archivos_registrados, masiva.comprobacion.ausentes) == (12, 12)

        assert await self._estado_de_los_archivos(fabrica) == antes  # ninguna baja en ninguno de los dos ciclos
        assert (await self._ultimo(fabrica))[CLAVE_COMPROBACION]["resultado"] == "desaparicion_masiva"

    async def test_baja_reaparicion_e_idempotencia(self, fabrica, montaje):
        montaje.mkdir()
        presentes = [montaje / f"P{i}.cbz" for i in range(9)]
        for p in presentes:
            p.write_bytes(b"x")
        falta = montaje / "Falta.cbz"
        await self._sembrar(fabrica, [*presentes, falta])

        uno = await self._ciclo(fabrica)
        assert uno.comprobacion.resultado is R.COMPROBADA and uno.disappeared == ["Falta.cbz"]
        (marcado,) = [f for f in await self._estado_de_los_archivos(fabrica) if f.is_missing]
        desde = marcado.missing_since

        dos = await self._ciclo(fabrica)  # sigue ausente: no es una baja nueva
        assert dos.disappeared == [] and dos.comprobacion.ausentes == 1
        (marcado2,) = [f for f in await self._estado_de_los_archivos(fabrica) if f.is_missing]
        assert marcado2.missing_since == desde

        falta.write_bytes(b"x")  # criterio 6: reaparece
        tres = await self._ciclo(fabrica)
        assert tres.reappeared == ["Falta.cbz"] and tres.comprobacion.ausentes == 0
        assert not [f for f in await self._estado_de_los_archivos(fabrica) if f.is_missing]
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
            assert d.comprobada and await disponibilidad.contar_no_disponibles(s) == 0

    async def test_un_ciclo_con_la_raiz_inaccesible_conserva_lo_que_ya_figuraba_no_disponible(self, fabrica, montaje):
        montaje.mkdir()
        (montaje / "P.cbz").write_bytes(b"x")
        async with fabrica() as s:
            s.add(_fila(str(montaje / "P.cbz")))
            s.add(_fila(str(montaje / "Ya-falta.cbz"), is_missing=True, missing_since=T0))
            await s.commit()
        await self._ciclo(fabrica)  # comprobada: una valida
        montaje.rename(montaje.parent / "lib-desconectada")  # la raíz «se va»

        informe = await self._ciclo(fabrica)

        assert informe.comprobacion.resultado is R.RAIZ_INACCESIBLE
        async with fabrica() as s:
            d = await disponibilidad.ultima_comprobacion(s)
            pagina = await disponibilidad.listar_no_disponibles(s)
        assert d.sin_verificar and d.ultima_valida is not None
        assert [a.nombre for a in pagina.archivos] == ["Ya-falta.cbz"] and pagina.archivos[0].desde == T0


class TestListaDeNoDisponibles:
    async def _sembrar_250(self, fabrica) -> list[File]:
        """250 no disponibles con fechas REPETIDAS (10 instantes distintos) y 25 sin `missing_since`, más 10 disponibles."""
        filas = []
        for i in range(250):
            sin_fecha = i % 10 == 0
            filas.append(_fila(f"/media/lib/Archivo {i:03d}.cbz", is_missing=True,
                               missing_since=None if sin_fecha else T0 + timedelta(hours=i % 10)))
        filas += [_fila(f"/media/lib/Presente {i}.cbz") for i in range(10)]
        async with fabrica() as s:
            s.add_all(filas)
            await s.commit()
        return filas

    @staticmethod
    def _esperado(filas: list[File]) -> list[str]:
        ausentes = [f for f in filas if f.is_missing]
        # más recientes primero; sin fecha al final; desempate por nombre y luego id
        return [f.file_name for f in sorted(ausentes, key=lambda f: (f.missing_since is None,
                                                                    -(f.missing_since.timestamp() if f.missing_since else 0),
                                                                    f.file_name, str(f.id)))]

    async def test_250_en_tres_paginas_sin_repetir_ni_saltarse_con_el_orden_acordado(self, fabrica):
        filas = await self._sembrar_250(fabrica)
        vistos, token, paginas = [], None, []
        async with fabrica() as s:
            while True:
                p = await disponibilidad.listar_no_disponibles(s, token)
                assert p.total == 250  # criterio 12: el total sigue visible en cada página
                paginas.append(len(p.archivos))
                vistos += [a.nombre for a in p.archivos]
                if p.siguiente is None:
                    break
                token = p.siguiente
        assert paginas == [100, 100, 50]
        assert len(vistos) == len(set(vistos)) == 250
        assert vistos == self._esperado(filas)

    async def test_pagina_exacta_sin_pagina_fantasma(self, fabrica):
        async with fabrica() as s:
            s.add_all([_fila(f"/m/{i:03d}.cbz", is_missing=True, missing_since=T0 + timedelta(minutes=i)) for i in range(100)])
            await s.commit()
        async with fabrica() as s:
            p = await disponibilidad.listar_no_disponibles(s)
        assert len(p.archivos) == 100 and p.siguiente is None

    async def test_el_cursor_es_estable_si_los_datos_cambian_entre_peticiones(self, fabrica):
        filas = await self._sembrar_250(fabrica)
        esperado = self._esperado(filas)
        async with fabrica() as s:
            primera = await disponibilidad.listar_no_disponibles(s)
        vistos = [a.nombre for a in primera.archivos]
        assert vistos == esperado[:100]

        # Entre la primera y la segunda petición: uno de los ya vistos reaparece, otro de la cola reaparece, y llega
        # uno NUEVO con una fecha más reciente que todas (caería en la página 1: con offset empujaría el resto).
        async with fabrica() as s:
            await s.execute(text("UPDATE files SET is_missing = false, missing_since = NULL WHERE file_name = :n"),
                            {"n": vistos[0]})
            await s.execute(text("UPDATE files SET is_missing = false, missing_since = NULL WHERE file_name = :n"),
                            {"n": esperado[-1]})
            s.add(_fila("/media/lib/Zzz nuevo.cbz", is_missing=True, missing_since=T0 + timedelta(days=30)))
            await s.commit()

        async with fabrica() as s:
            segunda = await disponibilidad.listar_no_disponibles(s, primera.siguiente)
        resto = [a.nombre for a in segunda.archivos]
        assert resto == esperado[100:200]  # ni repite los ya vistos ni se salta ninguno de los que seguían por delante

    async def test_mismo_nombre_y_misma_fecha_se_desempata_por_id_sin_repetir_ni_saltar(self, fabrica):
        """Dos carpetas pueden tener `Obra 01.cbz` y desaparecer en el mismo ciclo: el cursor debe cortar entre ellas."""
        async with fabrica() as s:
            s.add_all([_fila(f"/m/carpeta{i}/Obra 01.cbz", is_missing=True, missing_since=T0) for i in range(7)]
                      + [_fila(f"/m/carpeta{i}/Obra 02.cbz", is_missing=True) for i in range(5)])  # y 5 sin fecha, también repetidos
            await s.commit()
        vistos, token = [], None
        async with fabrica() as s:
            while True:
                p = await disponibilidad.listar_no_disponibles(s, token, limite=2)
                vistos += [a.id for a in p.archivos]
                if p.siguiente is None:
                    break
                token = p.siguiente
            todos = (await s.execute(select(File.id).where(File.is_missing.is_(True)))).scalars().all()
        assert len(vistos) == len(set(vistos)) == 12 and set(vistos) == {str(i) for i in todos}

    async def test_un_token_ilegible_se_trata_como_el_principio(self, fabrica):
        await self._sembrar_250(fabrica)
        async with fabrica() as s:
            p = await disponibilidad.listar_no_disponibles(s, "esto-no-es-un-cursor!!")
            normal = await disponibilidad.listar_no_disponibles(s)
        assert [a.nombre for a in p.archivos] == [a.nombre for a in normal.archivos]

    async def test_vinculado_conserva_serie_y_numero_y_desvinculado_no_da_error(self, fabrica):
        """Criterios 5 y 10 (ADR 0014): el archivo desvinculado sigue siendo no disponible, sin serie ni número y con su
        procedencia anterior intacta."""
        sid, iid = uuid4(), uuid4()
        historial = [{"operacion_id": str(uuid4()), "deshecho": {"fecha": T0.isoformat()},
                      "previo": {"serie": "Saga del Faro", "numero": "7"}}]
        async with fabrica() as s:
            s.add(Series(id=sid, title="Saga del Faro", tradition=ComicTradition.AMERICAN, start_year=2010))
            await s.flush()
            s.add(Issue(id=iid, series_id=sid, issue_number="7"))
            await s.flush()
            s.add_all([
                _fila("/m/Vinculado.cbz", issue_id=iid, is_missing=True, missing_since=T0),
                _fila("/m/Desvinculado.cbz", issue_id=None, is_missing=True, missing_since=T0 - timedelta(days=1),
                      metadata_={"vinculo_historial": historial}),
            ])
            await s.commit()
        async with fabrica() as s:
            p = await disponibilidad.listar_no_disponibles(s)
        por_nombre = {a.nombre: a for a in p.archivos}
        assert (por_nombre["Vinculado.cbz"].serie, por_nombre["Vinculado.cbz"].numero) == ("Saga del Faro", "7")
        assert (por_nombre["Desvinculado.cbz"].serie, por_nombre["Desvinculado.cbz"].numero) == (None, None)
        async with fabrica() as s:
            assert (await s.execute(select(File.issue_id).where(File.file_name == "Vinculado.cbz"))).scalar_one() == iid
            meta = (await s.execute(select(File.metadata_).where(File.file_name == "Desvinculado.cbz"))).scalar_one()
        assert meta["vinculo_historial"] == historial

    async def test_navegar_no_modifica_nada(self, fabrica):
        """Criterio 8, con la base de verdad: ni filas nuevas ni cambios, y el listado no necesita el disco (las rutas
        sembradas no existen)."""
        await self._sembrar_250(fabrica)
        async with fabrica() as s:
            s.add(_run(T0, {CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0)}))
            await s.commit()

        async def instantanea():
            async with fabrica() as s:
                return ((await s.execute(text("SELECT md5(string_agg(f::text, '|' ORDER BY id)) FROM files f"))).scalar_one(),
                        (await s.execute(select(func.count()).select_from(ImportRun))).scalar_one())
        antes = await instantanea()
        async with _cliente(fabrica) as c:
            r1 = await c.get("/ui/no-disponibles")
            siguiente = re.search(r'href="(/ui/no-disponibles\?despues=[^"]+)"', r1.text).group(1)
            r2 = await c.get(siguiente.replace("&amp;", "&"))
            r3 = await c.get("/estado")
        assert (r1.status_code, r2.status_code, r3.status_code) == (200, 200, 200)
        assert await instantanea() == antes


class TestPantallas:
    async def test_lista_y_estado_con_datos_reales(self, fabrica):
        async with fabrica() as s:
            s.add(_run(T0, {CLAVE_COMPROBACION: _comp(R.COMPROBADA, T0, archivos_registrados=200, ausentes=2)}))
            s.add_all([_fila("/m/Falta uno.cbz", is_missing=True, missing_since=T0),
                       _fila("/m/Falta dos.cbz", is_missing=True, missing_since=T0 - timedelta(days=2)),
                       _fila("/m/Sin fecha.cbz", is_missing=True)])
            await s.commit()
        async with _cliente(fabrica) as c:
            lista = await c.get("/ui/no-disponibles")
            estado = await c.get("/estado")
        plano = " ".join(lista.text.split())
        assert "3 archivos no disponibles" in plano
        assert "Falta uno.cbz" in plano and "Sin fecha de cuándo dejó de encontrarse" in plano
        assert plano.index("Falta uno.cbz") < plano.index("Falta dos.cbz") < plano.index("Sin fecha.cbz")
        assert "Se miraron las 200 rutas registradas; 2 no estaban" in plano
        assert "sin verificar" not in plano
        assert 'href="/ui/no-disponibles"' in estado.text and "Ver los 3 archivos no disponibles" in " ".join(estado.text.split())

    async def test_sin_ningun_dato_no_se_presenta_como_todo_disponible(self, fabrica):
        async with _cliente(fabrica) as c:
            lista = await c.get("/ui/no-disponibles")
        plano = " ".join(lista.text.split())
        assert "Sin dato de última comprobación válida" in plano
        assert "no es una comprobación nueva" in plano  # la lista vacía no afirma que todo esté bien
        assert "La última revisión encontró todos los archivos" not in plano
