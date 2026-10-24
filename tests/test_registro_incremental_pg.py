# ruff: noqa: E501
"""Registro INCREMENTAL de la biblioteca (#326) — Postgres y ficheros reales.

Tras el registro inicial (marcador `_library_adoption_done`), nada recogía los archivos que el coleccionista deja después en sus carpetas
(hallazgo de #307, `docs/design/contrato-307-formato-por-contenido.md` §12.4). Aquí se prueba, con ficheros y base reales, el contrato de
`docs/design/registro-incremental-326.md`: «nuevo» es una RUTA no registrada; el inventario no lee ni escribe; el alcance es lo que la persona
vio y confirmó; lo existente se conserva; las copias idénticas se informan sin tocar nada; la ambigüedad no se resuelve por azar.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import MARCADOR, Mundo, _cbz
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, FileFormat
from zascarr.services import registro_biblioteca
from zascarr.services.library_adopter import LibraryAdopter

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
    # Estado de partida de #326: el registro inicial YA se hizo (marcador puesto).
    async with m.fabrica() as s:
        informe = await LibraryAdopter(s).adopt()
    assert informe.error_count == 0 and await m.marcador()
    # La copia idéntica que sembró `Mundo` quedó como «repetido» (sin fila): se retira para partir de una carpeta sin nada pendiente.
    # Su comportamiento propio (sigue saliendo como nueva) se prueba aparte.
    async with m.fabrica() as s:
        registradas = set((await s.execute(select(File.file_path))).scalars().all())
    sin_fila = [p for p in m.contenido if str(p) not in registradas]
    assert len(sin_fila) == 1
    sin_fila[0].unlink()
    del m.contenido[sin_fila[0]]
    yield m
    registro_biblioteca.reiniciar_para_pruebas()
    app.dependency_overrides.pop(get_db, None)
    await m.cerrar()


def _nuevo(m: Mundo, nombre: str, marca: str, sub: str = "Nuevos") -> Path:
    ruta = m.lib / sub / nombre
    m.contenido[ruta] = _cbz(ruta, marca)
    return ruta


async def _filas(m: Mundo) -> dict:
    async with m.fabrica() as s:
        return {r.file_path: r for r in (await s.execute(select(File))).scalars().all()}


async def _n_runs(m: Mundo, kind: str) -> int:
    async with m.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM import_runs WHERE details->>'kind' = :k"), {"k": kind})).scalar()


async def _inventario(m: Mundo):
    async with m.fabrica() as s:
        return await LibraryAdopter(s).inventario()


async def _incremental(m: Mundo, inv, **kw):
    async with m.fabrica() as s:
        return await LibraryAdopter(s).adopt(alcance=inv.rutas_nuevas, **kw)


class TestInventarioIncremental:

    async def test_enseña_lo_nuevo_por_ruta_sin_abrir_ni_escribir_nada(self, mundo, monkeypatch):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        _nuevo(mundo, "Nuevo 02.cbz", "y")
        antes = (await _filas(mundo)).keys(), await _n_runs(mundo, "adoption")

        async def no_se_abre(path):
            raise AssertionError("el inventario no puede leer el contenido")
        monkeypatch.setattr("zascarr.services.importer._triage_sin_bloquear", no_se_abre)
        inv = await _inventario(mundo)
        assert inv.nuevos == 2 and inv.carpeta_accesible and inv.hay_que_registrar
        assert inv.ya_registrados == 10 and inv.en_disco == 12
        assert (await _filas(mundo)).keys() == antes[0] and await _n_runs(mundo, "adoption") == antes[1]

    async def test_sin_registro_inicial_no_se_ofrece_el_incremental(self, mundo):
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).ofrece_registro_incremental() is True
            await s.execute(text(f"UPDATE runtime_settings SET \"values\" = \"values\" - '{MARCADOR}' WHERE id = 1"))
            await s.commit()
        async with mundo.fabrica() as s:
            assert await LibraryAdopter(s).ofrece_registro_incremental() is False        # entonces lo que se ofrece es el registro completo

    async def test_la_huella_depende_de_las_rutas_nuevas_y_no_del_orden(self, mundo):
        a = _nuevo(mundo, "Nuevo A.cbz", "p")
        h1 = (await _inventario(mundo)).huella
        assert h1 == (await _inventario(mundo)).huella                       # estable
        _nuevo(mundo, "Nuevo B.cbz", "q")
        h2 = (await _inventario(mundo)).huella
        assert h2 != h1                                                      # apareció algo
        a.unlink()
        assert (await _inventario(mundo)).huella != h2                       # desapareció algo

    async def test_carpeta_inaccesible_no_fabrica_nuevos_ni_bajas(self, mundo, monkeypatch):
        filas_antes = {k: (v.is_missing, v.file_path) for k, v in (await _filas(mundo)).items()}
        ajustes = type("A", (), {"library_path": mundo.lib / "no-montado"})()
        monkeypatch.setattr("zascarr.services.library_adopter.get_settings", lambda: ajustes)
        inv = await _inventario(mundo)
        assert inv.carpeta_accesible is False and inv.nuevos == 0 and not inv.hay_que_registrar
        assert {k: (v.is_missing, v.file_path) for k, v in (await _filas(mundo)).items()} == filas_antes


class TestRegistroDeLoNuevo:

    async def test_registra_solo_lo_nuevo_y_conserva_lo_existente(self, mundo):
        existentes = await _filas(mundo)
        meta_antes = {k: dict(v.metadata_ or {}) for k, v in existentes.items()}
        ids_antes = {k: v.id for k, v in existentes.items()}
        disco_antes = mundo.hashes_en_disco()
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        _nuevo(mundo, "Nuevo 02.cbz", "y")
        informe = await _incremental(mundo, await _inventario(mundo))

        assert informe.to_process == 2 and informe.added_count == 2 and informe.error_count == 0
        despues = await _filas(mundo)
        assert len(despues) == len(existentes) + 2
        for k in existentes:                                   # nada de lo existente cambia: ni id, ni metadata
            assert despues[k].id == ids_antes[k] and dict(despues[k].metadata_ or {}) == meta_antes[k]
        assert await mundo.marcador() is True                                # el marcador del registro inicial no se toca
        assert await _n_runs(mundo, "registro_incremental") == 1
        assert await _n_runs(mundo, "adoption") == 1                         # el informe del registro inicial sigue siendo el único
        nuevo_disco = {k: v for k, v in mundo.hashes_en_disco().items() if k not in disco_antes}
        assert {k: v for k, v in mundo.hashes_en_disco().items() if k in disco_antes} == disco_antes   # ningún original cambia
        assert len(nuevo_disco) == 2                                          # y no hay archivos de más (nada movido ni copiado)

    async def test_repetirlo_no_duplica_nada(self, mundo):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        await _incremental(mundo, await _inventario(mundo))
        n = len(await _filas(mundo))
        inv = await _inventario(mundo)
        assert inv.nuevos == 0
        segundo = await _incremental(mundo, inv)
        assert segundo.to_process == 0 and segundo.added_count == 0 and len(await _filas(mundo)) == n

    async def test_solo_se_registra_lo_que_la_persona_vio_y_confirmó(self, mundo):
        a = _nuevo(mundo, "Nuevo A.cbz", "p")
        _nuevo(mundo, "Nuevo B.cbz", "q")
        inv = await _inventario(mundo)                                        # lo que la persona revisa y confirma
        _nuevo(mundo, "Nuevo C.cbz", "r")                                     # aparece DESPUÉS de revisar
        a.unlink()                                                            # y otro desaparece
        informe = await _incremental(mundo, inv)
        filas = await _filas(mundo)
        assert informe.to_process == 1 and informe.added_count == 1 and informe.out_of_scope_gone == 1
        assert str(mundo.lib / "Nuevos" / "Nuevo B.cbz") in filas
        assert str(mundo.lib / "Nuevos" / "Nuevo C.cbz") not in filas         # no se cuela lo que la persona no vio
        assert (await _inventario(mundo)).nuevos == 1                         # y la próxima búsqueda lo enseña

    async def test_una_copia_identica_se_informa_sin_segunda_fila_ni_tocar_nada(self, mundo):
        origen = next(iter(mundo.contenido))                                  # un archivo ya registrado y presente
        copia = mundo.lib / "Copias" / "Copia de algo.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(origen, copia)
        disco = mundo.hashes_en_disco()
        n = len(await _filas(mundo))
        informe = await _incremental(mundo, await _inventario(mundo))
        assert informe.duplicate_count == 1 and informe.added_count == 0
        assert len(await _filas(mundo)) == n and copia.exists() and mundo.hashes_en_disco() == disco

    async def test_una_copia_identica_sigue_saliendo_como_nueva_y_se_informa_cada_vez_sin_crear_filas(self, mundo):
        """Consecuencia asumida de «nuevo = ruta no registrada» + «un mismo contenido no se registra dos veces»: mientras la copia siga en la carpeta,
        cada búsqueda la vuelve a enseñar y cada registro la vuelve a contar como repetida. Nunca se crea una segunda fila ni se toca la copia."""
        copia = mundo.lib / "Copias" / "Copia de algo.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(next(iter(mundo.contenido)), copia)
        n = len(await _filas(mundo))
        for _ in range(2):
            inv = await _inventario(mundo)
            assert inv.nuevos == 1
            informe = await _incremental(mundo, inv)
            assert informe.duplicate_count == 1 and informe.added_count == 0 and len(await _filas(mundo)) == n and copia.exists()

    async def test_un_archivo_movido_reenlaza_su_ficha_y_conserva_vinculo_y_decisiones(self, mundo):
        movido = _nuevo(mundo, "Movido.cbz", "m", sub="Reorganizado")
        sha = hashlib.sha256(movido.read_bytes()).hexdigest()
        fila_id = uuid4()
        async with mundo.fabrica() as s:
            s.add(File(id=fila_id, file_path=str(mundo.lib / "Viejo" / "Movido.cbz"), file_name="Movido.cbz", file_format=FileFormat.CBZ,
                       sha256_hash=sha, original_sha256=sha, is_missing=True,
                       metadata_={"ajuste_manual": "conservar", "review_dismissed_nota": "x"}))
            await s.commit()
        n = len(await _filas(mundo))
        informe = await _incremental(mundo, await _inventario(mundo))
        filas = await _filas(mundo)
        assert informe.relinked == 1 and len(filas) == n                      # reutiliza la fila: no crea otra
        fila = filas[str(movido)]
        assert fila.id == fila_id and fila.is_missing is False
        assert fila.metadata_["ajuste_manual"] == "conservar"                 # sus decisiones se conservan

    async def test_un_contenido_que_coincide_con_varias_filas_desaparecidas_no_se_adjudica_por_azar(self, mundo):
        movido = _nuevo(mundo, "Ambiguo.cbz", "Z", sub="Reorganizado")
        sha = hashlib.sha256(movido.read_bytes()).hexdigest()
        async with mundo.fabrica() as s:
            for k in (1, 2):
                s.add(File(id=uuid4(), file_path=str(mundo.lib / "Viejo" / f"Ambiguo {k}.cbz"), file_name=f"Ambiguo {k}.cbz",
                           file_format=FileFormat.CBZ, sha256_hash=sha, original_sha256=sha, is_missing=True))
            await s.commit()
        antes = await _filas(mundo)
        informe = await _incremental(mundo, await _inventario(mundo))
        despues = await _filas(mundo)
        assert len(informe.ambiguous) == 1 and informe.relinked == 0 and informe.added_count == 0 and informe.error_count == 0
        assert despues.keys() == antes.keys()                                 # ni fila nueva ni reenlace
        for k in (1, 2):
            fila = despues[str(mundo.lib / "Viejo" / f"Ambiguo {k}.cbz")]
            assert fila.is_missing is True                                    # siguen como estaban
        assert str(movido) not in despues

    async def test_la_ambiguedad_solo_cambia_el_trato_del_incremental(self, mundo):
        """El registro inicial y el importador siguen reenlazando la fila más antigua, como siempre (mismo `_triage_and_match`)."""
        movido = _nuevo(mundo, "Ambiguo.cbz", "Z", sub="Reorganizado")
        sha = hashlib.sha256(movido.read_bytes()).hexdigest()
        async with mundo.fabrica() as s:
            for k in (1, 2):
                s.add(File(id=uuid4(), file_path=str(mundo.lib / "Viejo" / f"Ambiguo {k}.cbz"), file_name=f"Ambiguo {k}.cbz",
                           file_format=FileFormat.CBZ, sha256_hash=sha, original_sha256=sha, is_missing=True))
            await s.commit()
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()                         # SIN alcance: comportamiento de siempre
        assert informe.relinked == 1 and not informe.ambiguous

    async def test_un_fallo_no_toca_el_marcador_y_el_resto_se_registra(self, mundo, monkeypatch):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        _nuevo(mundo, "Nuevo 02.cbz", "y")
        original = LibraryAdopter._adopt_file

        async def falla_uno(self, path, report, pista=None):
            if path.name == "Nuevo 01.cbz":
                raise RuntimeError("disco roto en /ruta/secreta")
            return await original(self, path, report, pista)
        monkeypatch.setattr(LibraryAdopter, "_adopt_file", falla_uno)
        informe = await _incremental(mundo, await _inventario(mundo))
        assert informe.error_count == 1 and informe.added_count == 1
        assert "secreta" not in " ".join(informe.errors)
        assert await mundo.marcador() is True
        monkeypatch.setattr(LibraryAdopter, "_adopt_file", original)          # se arregla: buscar de nuevo completa sin duplicar
        segundo = await _incremental(mundo, await _inventario(mundo))
        assert segundo.added_count == 1 and segundo.error_count == 0


class TestEnSegundoPlanoYPantalla:

    @pytest.fixture
    def cliente(self, mundo):
        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                 headers={"Origin": "http://localhost"})

    async def test_la_pagina_ofrece_buscar_y_buscar_no_escribe_nada(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        n, runs = len(await _filas(mundo)), await _n_runs(mundo, "registro_incremental")
        async with cliente as c:
            r = await c.get("/ui/auditoria/registro")
            assert "Tu biblioteca ya está registrada" in r.text and "Buscar archivos sin registrar" in r.text
            r2 = await c.get("/ui/auditoria/nuevos")
        assert "<strong>1</strong> en una ruta sin registrar" in r2.text
        assert "Registrar los 1 archivos sin registrar" in r2.text and 'name="huella"' in r2.text
        plano = " ".join(r2.text.split())
        assert "no se ha abierto ninguno" in plano and "ninguna fuente de internet" in plano
        assert len(await _filas(mundo)) == n and await _n_runs(mundo, "registro_incremental") == runs

    async def test_confirmar_con_la_huella_vista_registra_y_el_resultado_separa_categorias(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        copia = mundo.lib / "Copias" / "Copia.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(next(iter(mundo.contenido)), copia)
        inv = await _inventario(mundo)
        async with cliente as c:
            r = await c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella})
            assert "Registrando los archivos encontrados" in r.text and 'hx-trigger="every 2s"' in r.text
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            r2 = await c.get("/ui/auditoria/registro")
        assert "Archivos sin registrar revisados" in r2.text and "every 2s" not in r2.text
        assert "<strong>2</strong> de <strong>2</strong> archivos mirados" in r2.text
        assert "<strong>1</strong> filas nuevas en el catálogo" in r2.text
        assert "<strong>1</strong> repetidos" in r2.text and "No se ha borrado ni movido ninguna copia" in r2.text
        assert "Buscar archivos sin registrar otra vez" in r2.text and "Continuar el registro" not in r2.text
        assert await mundo.marcador() is True

    async def test_si_la_carpeta_cambio_tras_revisar_no_se_registra_nada(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        visto = await _inventario(mundo)
        _nuevo(mundo, "Nuevo 02.cbz", "y")                                    # aparece entre revisar y confirmar
        n = len(await _filas(mundo))
        async with cliente as c:
            r = await c.post("/ui/auditoria/registrar-nuevos", data={"huella": visto.huella})
        assert "ha cambiado desde que lo revisaste" in r.text and "Registrar los 2 archivos sin registrar" in r.text
        assert not registro_biblioteca.estado_actual().en_marcha and len(await _filas(mundo)) == n

    async def test_sin_registro_inicial_o_con_otra_en_marcha_no_lanza_nada(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        async with mundo.fabrica() as s:
            await s.execute(text(f"UPDATE runtime_settings SET \"values\" = \"values\" - '{MARCADOR}' WHERE id = 1"))
            await s.commit()
        async with cliente as c:
            await c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella})
        assert not registro_biblioteca.estado_actual().en_marcha and len(await _filas(mundo)) == 6 + 7

    async def test_dos_confirmaciones_a_la_vez_lanzan_una_sola_ejecucion(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        _nuevo(mundo, "Nuevo 02.cbz", "y")
        inv = await _inventario(mundo)
        async with cliente as c:
            a, b = await asyncio.gather(c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella}),
                                        c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella}))
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert a.status_code == b.status_code == 200
        assert await _n_runs(mundo, "registro_incremental") == 1
        async with mundo.fabrica() as s:
            repetidas = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
            total = (await s.execute(select(func.count(File.id)))).scalar()
        assert repetidas == 0 and total == 6 + 7 + 2                          # 6 sembradas + 7 del registro inicial + las 2 nuevas

    async def test_el_registro_incremental_comparte_la_exclusion_con_el_inicial(self, mundo):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        assert registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas) is True
        assert registro_biblioteca.iniciar(mundo.fabrica) is False            # ni siquiera el inicial entra mientras corre
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        e = registro_biblioteca.estado_actual()
        assert e.incremental and e.completo and e.filas_nuevas == 1

    async def test_carpeta_inaccesible_lo_dice_y_no_ofrece_registrar(self, mundo, cliente, monkeypatch):
        ajustes = type("A", (), {"library_path": mundo.lib / "no-montado"})()
        monkeypatch.setattr("zascarr.services.library_adopter.get_settings", lambda: ajustes)
        async with cliente as c:
            r = await c.get("/ui/auditoria/nuevos")
        assert "No se puede leer la carpeta" in r.text and "no se da por nuevo ni por perdido" in r.text
        assert "Registrar los" not in r.text


def test_el_unico_que_lanza_el_registro_incremental_es_la_pantalla():
    """Sin automatismo (D del alcance de #326): ningún ciclo, arranque ni servicio llama a `iniciar` ni a `adopt(alcance=...)`."""
    raiz = Path(__file__).resolve().parents[1] / "src" / "zascarr"
    llamadores = sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*.py")
                        if "registro_biblioteca.iniciar(" in p.read_text() or "alcance=" in p.read_text() and ".adopt(" in p.read_text())
    assert llamadores == ["web/auditoria.py"]


class TestRecorridoIncompleto:

    @pytest.fixture
    def carpeta_cerrada(self, mundo):
        cerrada = mundo.lib / "Cerrada"
        cerrada.mkdir()
        _cbz(cerrada / "Escondido 01.cbz", "h")
        cerrada.chmod(0)
        if os.access(cerrada, os.R_OK):
            cerrada.chmod(0o755)
            pytest.skip("se ejecuta como root: los permisos no impiden listar")
        yield cerrada
        cerrada.chmod(0o755)

    async def test_el_inventario_distingue_completo_de_incompleto_y_no_fabrica_bajas(self, mundo, carpeta_cerrada):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        assert inv.ilegibles >= 1 and not inv.recorrido_completo and not inv.se_puede_confirmar
        assert inv.nuevos == 1 and inv.registrados_sin_fichero == 0

    async def test_la_pantalla_avisa_y_no_deja_confirmar_ni_aunque_se_fuerce_la_peticion(self, mundo, carpeta_cerrada):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        visto = await _inventario(mundo)
        n = len(await _filas(mundo))

        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers={"Origin": "http://localhost"}) as c:
            r = await c.get("/ui/auditoria/nuevos")
            r2 = await c.post("/ui/auditoria/registrar-nuevos", data={"huella": visto.huella})   # con la huella correcta
        plano = " ".join(r.text.split())
        assert "puede estar incompleta" in plano and "Registrar los" not in plano
        assert not registro_biblioteca.estado_actual().en_marcha and len(await _filas(mundo)) == n
        assert "Registrar los" not in r2.text


class TestExclusionEntreProcesos:

    async def _otro_proceso_con_el_cerrojo(self, mundo):
        """Otra conexión (como la de otro proceso) que ya tiene el cerrojo del registro."""
        conexion = await mundo.motor.connect()
        ok = (await conexion.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": registro_biblioteca._CLAVE_CERROJO})).scalar()
        assert ok
        return conexion

    async def test_si_otro_proceso_tiene_el_cerrojo_no_se_hace_nada(self, mundo):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        n, runs = len(await _filas(mundo)), await _n_runs(mundo, "registro_incremental")
        ajeno = await self._otro_proceso_con_el_cerrojo(mundo)
        try:
            assert registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas) is True
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            e = registro_biblioteca.estado_actual()
            assert e.fase.value == "ocupado" and not e.completo and not e.en_marcha
            assert len(await _filas(mundo)) == n and await _n_runs(mundo, "registro_incremental") == runs
        finally:
            await ajeno.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": registro_biblioteca._CLAVE_CERROJO})
            await ajeno.close()
        # Soltado el cerrojo ajeno, el mismo alcance se registra sin problema.
        assert registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas) is True
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert registro_biblioteca.estado_actual().completo and len(await _filas(mundo)) == n + 1

    async def test_el_cerrojo_se_suelta_al_terminar_y_tambien_si_el_registro_falla(self, mundo, monkeypatch):
        async def libre() -> bool:
            async with mundo.motor.connect() as c:
                ok = (await c.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": registro_biblioteca._CLAVE_CERROJO})).scalar()
                if ok:
                    await c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": registro_biblioteca._CLAVE_CERROJO})
                return bool(ok)
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas)
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert await libre()

        async def explota(self, *, progreso=None, lote=25, alcance=None):
            raise ConnectionError("x")
        monkeypatch.setattr(LibraryAdopter, "adopt", explota)
        registro_biblioteca.iniciar(mundo.fabrica, alcance=frozenset())
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert registro_biblioteca.estado_actual().fase.value == "interrumpido" and await libre()

    async def test_la_pantalla_dice_que_hay_otro_registro_en_marcha(self, mundo):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        ajeno = await self._otro_proceso_con_el_cerrojo(mundo)

        async def _get_db():
            async with mundo.fabrica() as s:
                yield s
        app.dependency_overrides[get_db] = _get_db
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost", headers={"Origin": "http://localhost"}) as c:
                await c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella})
                await asyncio.wait_for(registro_biblioteca._tarea, 60)
                r = await c.get("/ui/auditoria/registro")
        finally:
            await ajeno.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": registro_biblioteca._CLAVE_CERROJO})
            await ajeno.close()
        assert "El catálogo estaba ocupado" in r.text


class TestArchivoQueCambiaOSeVa:

    async def test_si_cambia_mientras_se_lee_no_se_registra_un_hash_que_ya_no_le_corresponde(self, mundo, monkeypatch):
        destino = _nuevo(mundo, "Nuevo 01.cbz", "x")
        import zascarr.services.library_adopter as la
        original = la._triage_and_match

        async def cambia_tras_leer(db, path, pista=None):
            salida = await original(db, path, pista)
            if path == destino:
                with open(path, "ab") as f:
                    f.write(b"mas bytes")                                # alguien lo modifica después de haberlo hasheado
            return salida
        monkeypatch.setattr(la, "_triage_and_match", cambia_tras_leer)
        n = len(await _filas(mundo))
        informe = await _incremental(mundo, await _inventario(mundo))
        assert informe.added_count == 0 and informe.error_count == 1 and "cambió mientras se leía" in informe.errors[0]
        assert len(await _filas(mundo)) == n                              # no se guardó nada con ese hash
        monkeypatch.setattr(la, "_triage_and_match", original)
        despues = await _incremental(mundo, await _inventario(mundo))      # al buscar de nuevo, se registra lo que hay AHORA
        assert despues.added_count == 1 and despues.error_count == 0
        fila = (await _filas(mundo))[str(destino)]
        assert fila.sha256_hash == hashlib.sha256(destino.read_bytes()).hexdigest() and fila.file_size_bytes == destino.stat().st_size

    async def test_si_desaparece_entre_la_busqueda_y_la_lectura_no_es_un_error(self, mundo, monkeypatch):
        fantasma = mundo.lib / "Nuevos" / "Fantasma.cbz"
        import zascarr.services.library_adopter as la
        from zascarr.utils.fs import Recorrido, recorrer_comics

        def con_fantasma(dirs, exts):
            r = recorrer_comics(dirs, exts)
            return Recorrido([*r.archivos, fantasma], r.ilegibles)
        monkeypatch.setattr(la, "recorrer_comics", con_fantasma)
        informe = await _incremental(mundo, SimpleAlcance({str(fantasma)}))
        assert informe.error_count == 0 and informe.out_of_scope_gone == 1 and informe.added_count == 0


class SimpleAlcance:
    def __init__(self, rutas):
        self.rutas_nuevas = frozenset(rutas)


class TestReenlaceExigeAusenciaDelOriginal:

    async def test_si_la_ruta_anterior_sigue_teniendo_el_archivo_no_se_reenlaza(self, mundo):
        """La fila quedó marcada como desaparecida (p. ej. por un fallo pasajero) pero su archivo sigue en su sitio: una copia en otra ruta NO le roba la ficha."""
        viejo = _nuevo(mundo, "Original.cbz", "o", sub="Viejo")
        copia = mundo.lib / "Copias" / "Original.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(viejo, copia)
        sha = hashlib.sha256(viejo.read_bytes()).hexdigest()
        fila_id = uuid4()
        async with mundo.fabrica() as s:
            s.add(File(id=fila_id, file_path=str(viejo), file_name=viejo.name, file_format=FileFormat.CBZ, sha256_hash=sha, original_sha256=sha,
                       is_missing=True, metadata_={"ajuste_manual": "conservar"}))
            await s.commit()
        inv = SimpleAlcance({str(copia)})
        informe = await _incremental(mundo, inv)
        filas = await _filas(mundo)
        assert informe.relinked == 0 and informe.added_count == 0 and len(informe.ambiguous) == 1
        assert "no ha podido dar por desaparecido" in informe.ambiguous[0]
        fila = filas[str(viejo)]
        assert fila.id == fila_id and fila.is_missing is True and fila.metadata_["ajuste_manual"] == "conservar"
        assert str(copia) not in filas


class TestFalloParcialYRecuperacion:

    async def test_si_falla_un_lote_lo_confirmado_se_conserva_y_buscar_de_nuevo_completa_sin_duplicar(self, mundo, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        for i in range(4):
            _nuevo(mundo, f"Nuevo {i}.cbz", f"n{i}")
        inv = await _inventario(mundo)
        original = AsyncSession.commit
        llamadas = {"n": 0}

        async def commit(self):
            llamadas["n"] += 1
            if llamadas["n"] == 2:
                raise ConnectionError("password=secreta")
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit)
        antes = len(await _filas(mundo))
        with pytest.raises(ConnectionError):
            await _incremental(mundo, inv, lote=2)
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert len(await _filas(mundo)) == antes + 2                        # el primer lote quedó confirmado; el segundo, no
        again = await _inventario(mundo)
        assert again.nuevos == 2                                            # lo que falta sale de nuevo en la búsqueda
        informe = await _incremental(mundo, again)
        assert informe.added_count == 2 and len(await _filas(mundo)) == antes + 4
        async with mundo.fabrica() as s:
            dobles = (await s.execute(text("SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
        assert dobles == 0 and await mundo.marcador() is True


@pytest.fixture
def descargas(mundo, tmp_path, monkeypatch):
    """Carpeta de descargas del importador REAL (junto a la biblioteca de `Mundo`)."""
    from types import SimpleNamespace
    d = tmp_path / "descargas"
    d.mkdir()
    monkeypatch.setattr("zascarr.services.importer.get_settings", lambda: SimpleNamespace(
        library_path=mundo.lib, transmission_download_dir=str(tmp_path / "transmission"),
        amule_incoming_dir=str(tmp_path / "amule"), downloads_path=d))
    return d


async def _ciclo_del_importador(m: Mundo):
    from zascarr.services.importer import Importer
    async with m.fabrica() as s:
        informe = await Importer(s).scan_and_import()
        await s.commit()
    return informe


class TestCarreraConElImportadorDeDescargas:
    """El mismo contenido llega a la vez por la biblioteca (registro incremental) y por descargas (importador): no puede haber dos filas."""

    def _preparar(self, mundo, descargas):
        en_biblioteca = _nuevo(mundo, "Carrera.cbz", "K")
        en_descargas = descargas / "Carrera (descargada).cbz"
        shutil.copyfile(en_biblioteca, en_descargas)
        return en_biblioteca, en_descargas, hashlib.sha256(en_biblioteca.read_bytes()).hexdigest()

    @staticmethod
    def _retraso_en_la_busqueda_por_contenido(monkeypatch):
        """Fuerza el solapamiento: ambos leen «no hay nadie con este contenido» antes de que el otro inserte."""
        import zascarr.services.importer as imp
        original = imp._coincidencias_de_hash

        async def lenta(db, sha):
            salida = await original(db, sha)
            await asyncio.sleep(0.4)
            return salida
        monkeypatch.setattr(imp, "_coincidencias_de_hash", lenta)

    async def _filas_con(self, m: Mundo, sha: str) -> int:
        async with m.fabrica() as s:
            return (await s.execute(select(func.count(File.id)).where(File.sha256_hash == sha))).scalar()

    async def test_con_el_cerrojo_hay_una_sola_fila_y_ambos_resultados_reflejan_lo_sucedido(self, mundo, descargas, monkeypatch):
        en_biblioteca, en_descargas, sha = self._preparar(mundo, descargas)
        inv = await _inventario(mundo)
        self._retraso_en_la_busqueda_por_contenido(monkeypatch)
        informe_imp, informe_reg = await asyncio.gather(_ciclo_del_importador(mundo), _incremental(mundo, inv))
        assert await self._filas_con(mundo, sha) == 1                       # una sola fila por el mismo contenido
        creadas = informe_reg.added_count + len(informe_imp.imported) + len(informe_imp.unsorted)
        repetidas = informe_reg.duplicate_count + len(informe_imp.duplicates)
        assert creadas == 1 and repetidas == 1                              # uno la incorporó y el otro lo informó como repetido
        assert informe_reg.error_count == 0 and not informe_imp.errors
        # Ninguno de los dos informes describe «nada»: el que perdió nombra EXACTAMENTE el archivo de la fila ganadora; el que ganó, lo que registró.
        async with mundo.fabrica() as s:
            ganadora = (await s.execute(select(File).where(File.sha256_hash == sha))).scalar_one()
        if informe_reg.duplicate_count:                                     # ganó el importador
            assert informe_reg.duplicates == [f"{en_biblioteca.name} — duplicado de {ganadora.file_name}, descartado"]
            assert len(informe_imp.imported) + len(informe_imp.unsorted) == 1 and informe_imp.duplicates == []
        else:                                                               # ganó el registro
            assert informe_imp.duplicates == [f"{en_descargas.name} — duplicado de {ganadora.file_name}, descartado"]
            assert informe_reg.added_count == 1 and ganadora.file_path == str(en_biblioteca) and informe_reg.duplicates == []

    async def test_control_negativo_sin_el_cerrojo_el_mismo_escenario_si_duplica(self, mundo, descargas, monkeypatch):
        """Demuestra que la carrera era real: la misma prueba, sin el cerrojo, deja dos filas."""
        import zascarr.services.importer as imp

        async def sin_cerrojo(db):
            return None
        monkeypatch.setattr(imp, "tomar_cerrojo_de_contenido", sin_cerrojo)
        _en_biblioteca, _en_descargas, sha = self._preparar(mundo, descargas)
        inv = await _inventario(mundo)
        self._retraso_en_la_busqueda_por_contenido(monkeypatch)
        await asyncio.gather(_ciclo_del_importador(mundo), _incremental(mundo, inv))
        assert await self._filas_con(mundo, sha) == 2

    async def test_si_el_importador_tiene_el_cerrojo_el_registro_se_detiene_con_ocupado_y_no_inserta(self, mundo, descargas, monkeypatch):
        import zascarr.services.importer as imp
        monkeypatch.setattr(imp, "ESPERA_MAXIMA_CERROJO_CONTENIDO_S", 0.3)
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        inv = await _inventario(mundo)
        n = len(await _filas(mundo))
        async with mundo.fabrica() as importador:                            # transacción larga del importador, con el cerrojo
            await imp.tomar_cerrojo_de_contenido(importador)
            registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas)
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            e = registro_biblioteca.estado_actual()
            assert e.fase.value == "ocupado" and not e.completo
            await importador.rollback()
        assert len(await _filas(mundo)) == n                                  # nada insertado
        assert await _n_runs(mundo, "registro_incremental") == 0              # y ningún informe de un registro que no terminó
        registro_biblioteca.iniciar(mundo.fabrica, alcance=inv.rutas_nuevas)  # liberado el cerrojo, se completa
        await asyncio.wait_for(registro_biblioteca._tarea, 60)
        assert registro_biblioteca.estado_actual().completo and len(await _filas(mundo)) == n + 1

    async def test_si_el_registro_tiene_el_cerrojo_el_importador_deja_el_archivo_y_lo_reintenta(self, mundo, descargas, monkeypatch):
        import zascarr.services.importer as imp
        monkeypatch.setattr(imp, "ESPERA_MAXIMA_CERROJO_CONTENIDO_S", 0.3)
        _en_biblioteca, en_descargas, _sha = self._preparar(mundo, descargas)
        otra = descargas / "Otra descarga.cbz"
        _cbz(otra, "J")
        n = len(await _filas(mundo))
        async with mundo.fabrica() as registro:
            await imp.tomar_cerrojo_de_contenido(registro)
            t0 = asyncio.get_running_loop().time()
            informe = await _ciclo_del_importador(mundo)
            assert asyncio.get_running_loop().time() - t0 < 2.5               # una sola espera: el ciclo se corta, no espera por cada archivo
            assert "se reintentará en el próximo ciclo" in informe.errors[0] and "se detuvo antes de mirar el resto" in informe.errors[1]
            assert en_descargas.exists() and otra.exists() and len(await _filas(mundo)) == n     # nada se movió ni se registró
            await registro.rollback()
        siguiente = await _ciclo_del_importador(mundo)                        # sin el cerrojo ocupado, el siguiente ciclo los incorpora
        assert not siguiente.errors and len(await _filas(mundo)) == n + 2

    async def test_el_cerrojo_se_toma_antes_de_buscar_por_contenido_y_se_suelta_tras_el_commit_del_ciclo(self, mundo, descargas, monkeypatch):
        import zascarr.services.importer as imp
        _en_biblioteca, _en_descargas, _sha = self._preparar(mundo, descargas)
        pasos: list[str] = []
        original_cerrojo, original_busqueda = imp.tomar_cerrojo_de_contenido, imp._coincidencias_de_hash

        async def cerrojo(db):
            pasos.append("cerrojo")
            await original_cerrojo(db)

        async def busqueda(db, sha):
            pasos.append("busqueda")
            return await original_busqueda(db, sha)
        monkeypatch.setattr(imp, "tomar_cerrojo_de_contenido", cerrojo)
        monkeypatch.setattr(imp, "_coincidencias_de_hash", busqueda)
        from zascarr.services.importer import Importer
        async with mundo.fabrica() as s:
            await Importer(s).scan_and_import()
            assert pasos[:2] == ["cerrojo", "busqueda"]                       # primero el cerrojo, después la búsqueda por contenido
            monkeypatch.setattr(imp, "ESPERA_MAXIMA_CERROJO_CONTENIDO_S", 0.3)
            async with mundo.fabrica() as otro:
                with pytest.raises(imp.CerrojoDeContenidoOcupado):            # ANTES del commit sigue tomado
                    await original_cerrojo(otro)
                await otro.rollback()
            await s.commit()
        async with mundo.fabrica() as otro:
            await original_cerrojo(otro)                                      # TRAS el commit, libre
            await otro.rollback()

    async def test_si_el_ciclo_del_importador_falla_a_medias_el_cerrojo_se_suelta_al_cerrar_la_sesion(self, mundo, descargas, monkeypatch):
        import zascarr.services.importer as imp
        self._preparar(mundo, descargas)
        original = imp.Importer._persist_run

        async def explota(self, report):
            raise RuntimeError("fallo al guardar el informe del ciclo")
        monkeypatch.setattr(imp.Importer, "_persist_run", explota)
        with pytest.raises(RuntimeError):
            async with mundo.fabrica() as s:
                await imp.Importer(s).scan_and_import()
                await s.commit()
        monkeypatch.setattr(imp.Importer, "_persist_run", original)
        async with mundo.fabrica() as otro:
            await imp.tomar_cerrojo_de_contenido(otro)                        # la sesión se cerró con rollback: no queda tomado
            await otro.rollback()

    async def test_el_cerrojo_se_libera_al_acabar_la_transaccion_aunque_falle(self, mundo):
        import zascarr.services.importer as imp
        async with mundo.fabrica() as a:
            await imp.tomar_cerrojo_de_contenido(a)
            await a.rollback()                                                # el fallo de quien lo tenía
        async with mundo.fabrica() as b:
            await imp.tomar_cerrojo_de_contenido(b)                           # no espera ni lanza: estaba libre
            await b.rollback()


class TestContabilidadYRecuperacion:

    async def test_cada_archivo_del_alcance_cae_en_una_categoria_y_el_total_cuadra(self, mundo, monkeypatch):
        import zascarr.services.library_adopter as la
        from zascarr.utils.fs import Recorrido, recorrer_comics
        nuevo = _nuevo(mundo, "Fresco.cbz", "Q")
        copia = mundo.lib / "Copias" / "Copia.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(next(iter(mundo.contenido)), copia)
        movido = _nuevo(mundo, "Movido.cbz", "W", sub="Reorganizado")
        sha_m = hashlib.sha256(movido.read_bytes()).hexdigest()
        ambiguo = _nuevo(mundo, "Ambiguo.cbz", "Z", sub="Reorganizado")
        sha_a = hashlib.sha256(ambiguo.read_bytes()).hexdigest()
        async with mundo.fabrica() as s:
            s.add(File(id=uuid4(), file_path=str(mundo.lib / "Viejo" / "M.cbz"), file_name="M.cbz", file_format=FileFormat.CBZ,
                       sha256_hash=sha_m, original_sha256=sha_m, is_missing=True))
            for k in (1, 2):
                s.add(File(id=uuid4(), file_path=str(mundo.lib / "Viejo" / f"A{k}.cbz"), file_name=f"A{k}.cbz", file_format=FileFormat.CBZ,
                           sha256_hash=sha_a, original_sha256=sha_a, is_missing=True))
            await s.commit()
        fantasma = mundo.lib / "Nuevos" / "Fantasma.cbz"
        se_fue_antes = _nuevo(mundo, "SeFueAntes.cbz", "V")
        inv = await _inventario(mundo)                                         # lo que la persona confirma
        se_fue_antes.unlink()                                                  # y desaparece antes de empezar

        def con_fantasma(dirs, exts):
            r = recorrer_comics(dirs, exts)
            return Recorrido([*r.archivos, fantasma], r.ilegibles)             # …y otro desaparece justo al leerlo
        monkeypatch.setattr(la, "recorrer_comics", con_fantasma)
        alcance = SimpleAlcance({*inv.rutas_nuevas, str(fantasma)})
        informe = await _incremental(mundo, alcance)

        categorias = (informe.added_count + informe.duplicate_count + len(informe.ambiguous) + informe.by_other_run
                      + informe.error_count + informe.vanished + informe.reverted + informe.unknown)
        assert informe.processed == categorias == informe.to_process           # cada archivo mirado cae en UNA categoría y el total cuadra
        assert (informe.added_count, informe.relinked, informe.duplicate_count, len(informe.ambiguous), informe.vanished) == (2, 1, 1, 1, 1)
        assert len(informe.omitted) == 2                                       # el que se fue antes de empezar y el que se fue al leerlo
        assert any("ya no estaba pendiente al empezar" in o for o in informe.omitted) and any("desapareció antes de leerlo" in o for o in informe.omitted)
        assert nuevo.name in " ".join(informe.unsorted) and "Movido.cbz" in " ".join(informe.registered)

    async def test_commit_aplicado_con_la_respuesta_perdida_se_acredita_sin_duplicar_ni_decir_que_no_se_hizo_nada(self, mundo, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        for i in range(4):
            _nuevo(mundo, f"Nuevo {i}.cbz", f"n{i}")
        inv = await _inventario(mundo)
        original = AsyncSession.commit
        llamadas = {"n": 0}

        async def commit(self):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                await original(self)                                           # el commit SÍ termina…
                raise ConnectionError("password=secreta")                      # …pero la respuesta se pierde
            return await original(self)
        monkeypatch.setattr(AsyncSession, "commit", commit)
        antes = len(await _filas(mundo))
        informe = await _incremental(mundo, inv, lote=2)                       # no lanza: se acredita contra otra sesión
        monkeypatch.setattr(AsyncSession, "commit", original)
        assert informe.added_count == 4 and informe.reverted == 0 and informe.unknown == 0
        assert len(await _filas(mundo)) == antes + 4
        async with mundo.fabrica() as s:
            dobles = (await s.execute(text("SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
            guardado = (await s.execute(text("SELECT details FROM import_runs WHERE details->>'kind' = 'registro_incremental'"))).scalar()
        assert dobles == 0 and len(guardado["registered"]) + len(guardado["unsorted"]) == 4     # el informe persistido cuenta lo que pasó
        assert (await _inventario(mundo)).nuevos == 0                          # y buscar de nuevo no encuentra nada pendiente
