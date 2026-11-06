# ruff: noqa: E501
"""Rescan de la biblioteca (BL-R9) — Postgres y ficheros reales.

Prueba el contrato de `docs/design/especificacion-BL-R9-rescan-biblioteca.md` con base y disco reales:
lo nuevo se registra (a su serie o a «Por revisar»), lo cambiado se re-tría sobre la MISMA fila (igual
publicación / otra / a revisar / descartado sin reactivar), lo movido se reenlaza, lo desaparecido se
marca sin borrar, la línea de base (`file_mtime_ns` NULL) se fija una vez, el informe persiste con
`kind="rescan"` y no se confunde con el ciclo del importador, el rescan comparte el cerrojo de ciclo
`(326,2)`, no consulta fuentes y no abre los CBZ que no cambiaron. Se salta sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import Mundo, _cbz
from zascarr import database
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, Issue, Series
from zascarr.services import disponibilidad, registro_biblioteca, rescan_biblioteca
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
    # `Importer` (usado para la comprobación de desaparecidos del rescan) lee su propia config.
    monkeypatch.setattr("zascarr.services.importer.get_settings", lambda: SimpleNamespace(
        library_path=m.lib, transmission_download_dir=str(tmp_path / "transmission"),
        amule_incoming_dir=str(tmp_path / "amule"), downloads_path=tmp_path / "descargas"))
    monkeypatch.setattr(database, "async_session_factory", m.fabrica)
    registro_biblioteca.reiniciar_para_pruebas()
    rescan_biblioteca.reiniciar_para_pruebas()
    yield m
    registro_biblioteca.reiniciar_para_pruebas()
    rescan_biblioteca.reiniciar_para_pruebas()
    app.dependency_overrides.pop(get_db, None)
    await m.cerrar()


async def _rescan(m: Mundo, **kw):
    async with m.fabrica() as s:
        informe = await LibraryAdopter(s).rescanear(**kw)
    return informe


async def _filas(m: Mundo) -> dict:
    async with m.fabrica() as s:
        return {r.file_path: r for r in (await s.execute(select(File))).scalars().all()}


async def _n_runs(m: Mundo, kind: str) -> int:
    async with m.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM import_runs WHERE details->>'kind' = :k"),
                                {"k": kind})).scalar()


def _nuevo(m: Mundo, nombre: str, marca: str, sub: str = "Nuevos") -> Path:
    ruta = m.lib / sub / nombre
    m.contenido[ruta] = _cbz(ruta, marca)
    return ruta


def _cbz_comicinfo(ruta: Path, serie: str, numero: str, marca: str) -> bytes:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("ComicInfo.xml",
                   f'<?xml version="1.0"?><ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
                   f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                   f"<Series>{serie}</Series><Number>{numero}</Number></ComicInfo>")
        z.writestr("001.jpg", (marca * 3000).encode())
    return ruta.read_bytes()


async def _serie_id(m: Mundo, titulo: str):
    async with m.fabrica() as s:
        return (await s.execute(select(Series.id).where(Series.title == titulo))).scalar_one()


async def _sembrar_issue(m: Mundo, serie: str, numero: str) -> str:
    async with m.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=await _serie_id(m, serie), issue_number=numero, volume=1)
        s.add(issue)
        await s.commit()
        return str(issue.id)


async def _fila(m: Mundo, ruta: Path) -> File:
    async with m.fabrica() as s:
        return (await s.execute(select(File).where(File.file_path == str(ruta)))).scalar_one()


class TestPrimeraPasada:

    async def test_registra_lo_nuevo_y_fija_la_linea_de_base(self, mundo):
        """Lo nuevo va a su serie (si la reconoce) o a «Por revisar»; los presentes sin `file_mtime_ns`
        (línea de base) se re-trían una vez y quedan fijados; los desaparecidos sembrados se marcan."""
        _nuevo(mundo, "Saga del Faro 09.cbz", "s")
        _nuevo(mundo, "Cosa Inexistente 01.cbz", "u")
        informe = await _rescan(mundo)
        assert informe.nuevos_registrados == 1 and informe.nuevos_a_revisar >= 2    # «Cosa…» + los demás del mundo
        assert informe.re_triados == 3 and informe.re_triados_a_revisar == 3        # las 3 presentes sin línea de base
        # Las 3 filas sembradas (Desaparecida 1, 2 y la ajena) no existen en disco: se marcan sin borrarlas.
        assert informe.desaparecidos == 3 and informe.resultado_biblioteca == "comprobada"
        filas = await _filas(mundo)
        assert all(f.file_mtime_ns is not None for f in filas.values() if Path(f.file_path).exists())
        async with mundo.fabrica() as s:
            nuevo = (await s.execute(select(File).where(File.file_name == "Cosa Inexistente 01.cbz"))).scalar_one()
            assert nuevo.issue_id is None and nuevo.metadata_["match_status"] == "unsorted"

    async def test_segunda_pasada_sin_cambios_no_abre_ningun_cbz(self, mundo, monkeypatch):
        informe1 = await _rescan(mundo)
        assert informe1.re_triados == 3
        # La copia idéntica que quedó sin fila (contrato #326: «vuelve a salir en cada búsqueda y se
        # informa como repetida») se retira, igual que hace el fixture del registro incremental:
        # la garantía de «no abrir CBZ» es para las rutas REGISTRADAS sin cambios.
        filas = await _filas(mundo)
        sin_fila = [p for p in mundo.contenido if str(p) not in filas]
        assert len(sin_fila) == 1
        sin_fila[0].unlink()
        del mundo.contenido[sin_fila[0]]

        async def prohibido(path):
            raise AssertionError(f"no debía leerse el contenido de {path}")
        import zascarr.services.importer as imp
        monkeypatch.setattr(imp, "_triage_sin_bloquear", prohibido)
        informe2 = await _rescan(mundo)
        assert informe2.nuevos_entregados == 0 and informe2.re_triados == 0
        assert informe2.sin_cambios == 10 and informe2.desaparecidos == 0
        assert await _n_runs(mundo, "rescan") == 2

    async def test_el_cambio_que_conserva_tamano_y_fecha_no_se_detecta(self, mundo, monkeypatch):
        """Límite declarado (spec §5): la guarda compara tamaño e instante; sin diferencia no se re-lee."""
        informe1 = await _rescan(mundo)
        assert informe1.re_triados == 3
        objetivo = next(p for p in mundo.contenido if "Comics" in str(p))
        st = objetivo.stat()
        original = mundo.contenido[objetivo]
        _cbz(objetivo, "x")                                              # 1 carácter como el original: mismo tamaño
        os.utime(objetivo, ns=(st.st_atime_ns, st.st_mtime_ns))          # mismo tamaño E instante
        fila_antes = await _fila(mundo, objetivo)
        informe2 = await _rescan(mundo)
        assert informe2.re_triados == 0 and informe2.sin_cambios == 10
        fila_despues = await _fila(mundo, objetivo)
        assert fila_despues.sha256_hash == fila_antes.sha256_hash        # no se tocó
        mundo.contenido[objetivo] = original


class TestReTriaje:

    async def test_misma_publicacion_actualiza_la_fila(self, mundo):
        issue = await _sembrar_issue(mundo, "Saga del Faro", "1")
        ruta = _nuevo(mundo, "Faro 01.cbz", "a")
        _cbz_comicinfo(ruta, "Saga del Faro", "1", "b")
        informe1 = await _rescan(mundo)
        assert informe1.nuevos_registrados >= 1
        fila = await _fila(mundo, ruta)
        assert str(fila.issue_id) == issue and fila.file_mtime_ns is not None
        hash1, size1, mtime1 = fila.sha256_hash, fila.file_size_bytes, fila.file_mtime_ns

        _cbz_comicinfo(ruta, "Saga del Faro", "1", "c")                  # misma publicación, otros bytes
        informe2 = await _rescan(mundo)
        assert informe2.re_triados == 1 and informe2.re_triados_igual == 1
        fila = await _fila(mundo, ruta)
        assert str(fila.issue_id) == issue                              # el vínculo se conserva
        assert fila.sha256_hash != hash1 and fila.file_size_bytes == size1
        assert fila.file_mtime_ns is not None and fila.file_mtime_ns != mtime1
        assert await _n_runs(mundo, "rescan") == 2

    async def test_otra_publicacion_actualiza_el_vinculo(self, mundo):
        await _sembrar_issue(mundo, "Saga del Faro", "1")
        await _sembrar_issue(mundo, "Patrulla Azul", "7")
        ruta = _nuevo(mundo, "Faro 01.cbz", "a")
        _cbz_comicinfo(ruta, "Saga del Faro", "1", "b")
        await _rescan(mundo)
        fila = await _fila(mundo, ruta)
        fila_id = fila.id
        assert (await _serie_id(mundo, "Saga del Faro")) is not None and str(fila.issue_id) is not None

        _cbz_comicinfo(ruta, "Patrulla Azul", "7", "d")                  # ahora es OTRA publicación
        informe2 = await _rescan(mundo)
        assert informe2.re_triados_cambiado == 1
        fila = await _fila(mundo, ruta)
        assert fila.id == fila_id                                       # la MISMA fila, no una nueva
        issue_azul = await _fila(mundo, ruta)
        async with mundo.fabrica() as s:
            azul = (await s.execute(select(Issue).where(Issue.issue_number == "7"))).scalar_one()
        assert str(issue_azul.issue_id) == str(azul.id)

    async def test_sin_identificar_se_desvincula_y_pasa_a_revisar(self, mundo):
        issue = await _sembrar_issue(mundo, "Saga del Faro", "1")
        ruta = _nuevo(mundo, "Faro 01.cbz", "a")
        _cbz_comicinfo(ruta, "Saga del Faro", "1", "b")
        await _rescan(mundo)
        assert str((await _fila(mundo, ruta)).issue_id) == issue

        _cbz_comicinfo(ruta, "Serie Fantasma", "1", "d")                 # ComicInfo que no existe en el catálogo
        informe2 = await _rescan(mundo)
        assert informe2.re_triados_a_revisar == 1
        fila = await _fila(mundo, ruta)
        assert fila.issue_id is None and fila.metadata_["match_status"] == "unsorted"

    async def test_descartado_no_se_reactiva_pero_actualiza_el_stat(self, mundo):
        ruta = _nuevo(mundo, "Faro 01.cbz", "z9")                        # marca única: no puede ser copia de otro
        await _rescan(mundo)
        async with mundo.fabrica() as s:
            fila = (await s.execute(select(File).where(File.file_path == str(ruta)))).scalar_one()
            fila.review_dismissed = True
            fila.metadata_ = dict(fila.metadata_, ajuste_manual="no-tocar")
            await s.commit()
        hash_viejo = (await _fila(mundo, ruta)).sha256_hash

        _cbz(ruta, "contenido-nuevo")
        informe = await _rescan(mundo)
        assert informe.re_triados_descartado == 1
        fila = await _fila(mundo, ruta)
        assert fila.review_dismissed is True                            # el descarte no se reactiva
        assert fila.sha256_hash != hash_viejo and fila.file_mtime_ns is not None
        assert fila.metadata_["ajuste_manual"] == "no-tocar"            # lo demás se conserva
        assert fila.metadata_["match_status"] == "unsorted"             # sigue como estaba clasificada


class TestMovidosYDesaparecidos:

    async def test_movido_se_reenlaza_con_la_misma_fila(self, mundo):
        await _rescan(mundo)
        origen = next(p for p in mundo.contenido if "Comics" in str(p))
        destino = mundo.lib / "Otra carpeta" / origen.name
        destino.parent.mkdir()
        fila_id = (await _fila(mundo, origen)).id
        shutil.move(origen, destino)
        mundo.contenido[destino] = mundo.contenido.pop(origen)

        informe = await _rescan(mundo)
        assert informe.reenlazados == 1
        fila = await _fila(mundo, destino)
        assert fila.id == fila_id and fila.is_missing is False and fila.file_path == str(destino)
        async with mundo.fabrica() as s:
            viejas = (await s.execute(select(func.count(File.id)).where(File.file_path == str(origen)))).scalar()
        assert viejas == 0

    async def test_desaparecido_se_marca_y_reaparece(self, mundo):
        await _rescan(mundo)
        filas = await _filas(mundo)
        objetivo = next(p for p in mundo.contenido if "BD" in str(p) and str(p) in filas)
        fila_id = filas[str(objetivo)].id
        contenido = objetivo.read_bytes()
        st = objetivo.stat()
        objetivo.unlink()

        informe = await _rescan(mundo)
        assert informe.desaparecidos == 1                              # solo el borrado (los 3 sembrados ya constaban)
        fila = await _fila(mundo, objetivo)
        assert fila.id == fila_id and fila.is_missing is True and fila.missing_since is not None

        objetivo.write_bytes(contenido)                                 # vuelve a aparecer, con el MISMO stat
        os.utime(objetivo, ns=(st.st_atime_ns, st.st_mtime_ns))
        informe2 = await _rescan(mundo)
        assert informe2.reaparecidos == 1 and informe2.re_triados == 0
        fila = await _fila(mundo, objetivo)
        assert fila.is_missing is False and fila.missing_since is None

    async def test_desaparicion_masiva_guarda_el_guardarrail(self, mundo, monkeypatch):
        await _rescan(mundo)
        import zascarr.services.importer as imp
        monkeypatch.setattr(imp, "UMBRAL_DESAPARICION_MASIVA_MINIMO", 4)
        monkeypatch.setattr(imp, "UMBRAL_DESAPARICION_MASIVA_FRACCION", 0.5)
        filas = await _filas(mundo)
        borrados = [p for p in mundo.contenido if str(p) in filas][:5]
        contenido = {p: p.read_bytes() for p in borrados}
        for p in borrados:
            p.unlink()
        informe = await _rescan(mundo)
        assert informe.resultado_biblioteca == "desaparicion_masiva"
        async with mundo.fabrica() as s:
            marcadas = (await s.execute(select(func.count(File.id)).where(File.is_missing.is_(True)))).scalar()
        assert marcadas == 3                                           # solo las sembradas ausentes, nada nuevo
        for p, c in contenido.items():
            p.write_bytes(c)


    async def test_si_el_commit_del_lote_falla_no_se_cuenta_dos_veces(self, mundo, monkeypatch):
        """m3 del peer review: un lote cuyo commit no se acredita pasa a «por comprobar» y sus
        re-triajes NO se cuentan también como hechos; el bucle se detiene y el informe final
        (otro commit) sí se guarda."""
        async def falla(self, report, mirados):
            report.por_comprobar += mirados
            await self._db.rollback()          # como el commit fallido real: lo pendiente se revierte
            return False
        monkeypatch.setattr(LibraryAdopter, "_confirmar_lote_rescan", falla)
        informe = await _rescan(mundo)
        assert informe.re_triados == 0 and informe.por_comprobar == 3
        assert not informe.errores
        assert await _n_runs(mundo, "rescan") == 1
        sembrada = next(p for p in mundo.contenido if "Comics" in str(p))
        async with mundo.fabrica() as s:
            fila = (await s.execute(select(File).where(File.file_path == str(sembrada)))).scalar_one()
        assert fila.file_mtime_ns is None   # el lote fallido no dejó su línea de base fijada a medias

    async def test_si_el_informe_final_no_se_guarda_lo_dice(self, mundo, monkeypatch):
        """s4 del peer review: el commit final del `ImportRun` puede fallar; el rescan termina
        honesto («informe no se pudo guardar»), sin fingir un run que no existe."""
        async def revienta(self, report):
            raise RuntimeError("boom")
        monkeypatch.setattr(LibraryAdopter, "_persist_run_rescan", revienta)
        informe = await _rescan(mundo)
        assert informe.run_id is None
        assert any("informe no se pudo guardar" in e for e in informe.errores)
        assert await _n_runs(mundo, "rescan") == 0


class TestGuardasYContratos:

    async def test_raiz_inaccesible_no_revisa_ni_marca(self, mundo, monkeypatch):
        await _rescan(mundo)
        ajustes = type("A", (), {"library_path": mundo.lib / "no-montado"})()
        monkeypatch.setattr("zascarr.services.library_adopter.get_settings", lambda: ajustes)
        import zascarr.services.importer as imp
        monkeypatch.setattr(imp, "get_settings", lambda: SimpleNamespace(
            library_path=mundo.lib / "no-montado", transmission_download_dir="/tmp/t",
            amule_incoming_dir="/tmp/a", downloads_path=Path("/tmp/d")))
        informe = await _rescan(mundo)
        assert informe.no_revisado is True and informe.files_scanned == 0
        assert informe.resultado_biblioteca == "raiz_inaccesible"
        async with mundo.fabrica() as s:
            marcadas = (await s.execute(select(func.count(File.id)).where(File.is_missing.is_(True)))).scalar()
        assert marcadas == 3                                           # no se fabricó ninguna baja nueva

    async def test_archivo_que_cambia_mientras_se_lee_se_omite(self, mundo, monkeypatch):
        await _rescan(mundo)
        objetivo = next(p for p in mundo.contenido if "Comics" in str(p))
        import zascarr.services.importer as imp
        original = imp._triage_sin_bloquear
        # El archivo cambia ANTES de partir (entra en «cambiados») y OTRA vez durante la lectura.
        st = objetivo.stat()
        os.utime(objetivo, ns=(st.st_atime_ns, st.st_mtime_ns + 1))

        async def cambia_y_lee(path):
            _cbz(path, "cambiado-a-mitad")                              # sustituye el contenido al leer
            return await original(path)
        monkeypatch.setattr(imp, "_triage_sin_bloquear", cambia_y_lee)
        informe = await _rescan(mundo)
        assert informe.re_triados == 0
        assert any("cambió mientras se leía" in o for o in informe.omitidos)
        # El siguiente rescan sí lo re-tría (el archivo quedó cambiado de verdad).
        monkeypatch.setattr(imp, "_triage_sin_bloquear", original)
        informe2 = await _rescan(mundo)
        assert informe2.re_triados == 1

    async def test_no_consulta_fuentes_externas(self, mundo, monkeypatch):
        def explota(*a, **kw):
            raise AssertionError("el rescan no puede instanciar un cliente de fuentes")
        for mod, clase in (("comic_vine", "ComicVineClient"), ("anilist", "AniListClient"),
                           ("tebeosfera", "TebeosferaClient"), ("gcd", "GCDClient")):
            monkeypatch.setattr(f"zascarr.services.{mod}.{clase}", explota)
        _nuevo(mundo, "Saga del Faro 09.cbz", "s")
        informe = await _rescan(mundo)
        assert informe.nuevos_registrados == 1

    async def test_el_informe_persiste_y_no_se_lee_como_el_ciclo(self, mundo):
        await _rescan(mundo)
        assert await _n_runs(mundo, "rescan") == 1
        async with mundo.fabrica() as s:
            run = (await s.execute(text(
                "SELECT details FROM import_runs WHERE details->>'kind' = 'rescan'"))).scalar_one()
            assert run["sin_cambios"] == 0 and run["no_revisado"] is False
            comprobacion = await disponibilidad.ultima_comprobacion(s)
            assert comprobacion.resultado is None                       # el rescan NO es «el último ciclo»

    async def test_el_rescan_comparte_el_cerrojo_de_ciclo(self, mundo):
        from zascarr.services.comprobacion_disco import CLAVE_CERROJO_CICLO
        async with mundo.motor.connect() as c:
            await c.execute(text("SELECT pg_advisory_lock(:n, :o)"),
                            {"n": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})
            try:
                informe = await rescan_biblioteca.ejecutar_automatico(mundo.fabrica)
                assert informe is None                                  # cede el turno sin efectos
                assert await _n_runs(mundo, "rescan") == 0
                assert rescan_biblioteca.iniciar_manual(mundo.fabrica) is True
                await rescan_biblioteca._tarea
                assert rescan_biblioteca.estado_actual().fase is rescan_biblioteca.FaseRescan.OCUPADO
                assert await _n_runs(mundo, "rescan") == 0
            finally:
                await c.execute(text("SELECT pg_advisory_unlock(:n, :o)"),
                                {"n": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})
        await rescan_biblioteca.detener()

    async def test_repetir_no_duplica_y_la_linea_de_base_se_fija_una_vez(self, mundo):
        i1 = await _rescan(mundo)
        i2 = await _rescan(mundo)
        assert i1.nuevos_entregados == 8 and i2.nuevos_entregados == 1   # la copia sin fila sigue saliendo (contrato #326)
        assert i2.repetidos == 1 and i2.re_triados == 0 and i2.sin_cambios == 10
        async with mundo.fabrica() as s:
            total = (await s.execute(select(func.count(File.id)))).scalar()
            dobles = (await s.execute(text(
                "SELECT count(*) FROM (SELECT file_path FROM files GROUP BY file_path HAVING count(*) > 1) t"))).scalar()
        assert total == 13 and dobles == 0
