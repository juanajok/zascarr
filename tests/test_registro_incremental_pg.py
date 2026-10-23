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
            assert "Tu biblioteca ya está registrada" in r.text and "Buscar archivos nuevos" in r.text
            r2 = await c.get("/ui/auditoria/nuevos")
        assert "<strong>1</strong> en una ruta que ZascArr aún no conoce" in r2.text
        assert "Registrar los 1 archivos nuevos" in r2.text and 'name="huella"' in r2.text
        assert "no se ha abierto ninguno" in r2.text and "ninguna fuente de internet" in r2.text
        assert len(await _filas(mundo)) == n and await _n_runs(mundo, "registro_incremental") == runs

    async def test_confirmar_con_la_huella_vista_registra_y_el_resultado_separa_categorias(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        copia = mundo.lib / "Copias" / "Copia.cbz"
        copia.parent.mkdir(parents=True)
        shutil.copyfile(next(iter(mundo.contenido)), copia)
        inv = await _inventario(mundo)
        async with cliente as c:
            r = await c.post("/ui/auditoria/registrar-nuevos", data={"huella": inv.huella})
            assert "Registrando los archivos nuevos" in r.text and 'hx-trigger="every 2s"' in r.text
            await asyncio.wait_for(registro_biblioteca._tarea, 60)
            r2 = await c.get("/ui/auditoria/registro")
        assert "Archivos nuevos revisados" in r2.text and "every 2s" not in r2.text
        assert "<strong>2</strong> de <strong>2</strong> archivos nuevos mirados" in r2.text
        assert "<strong>1</strong> filas nuevas en el catálogo" in r2.text
        assert "<strong>1</strong> repetidos" in r2.text and "No se ha borrado ni movido ninguna copia" in r2.text
        assert "Buscar archivos nuevos otra vez" in r2.text and "Continuar el registro" not in r2.text
        assert await mundo.marcador() is True

    async def test_si_la_carpeta_cambio_tras_revisar_no_se_registra_nada(self, mundo, cliente):
        _nuevo(mundo, "Nuevo 01.cbz", "x")
        visto = await _inventario(mundo)
        _nuevo(mundo, "Nuevo 02.cbz", "y")                                    # aparece entre revisar y confirmar
        n = len(await _filas(mundo))
        async with cliente as c:
            r = await c.post("/ui/auditoria/registrar-nuevos", data={"huella": visto.huella})
        assert "ha cambiado desde que lo revisaste" in r.text and "Registrar los 2 archivos nuevos" in r.text
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
