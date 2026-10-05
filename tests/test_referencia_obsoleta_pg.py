# ruff: noqa: E501
"""Referencias obsoletas: una fila `is_missing = false` cuya ruta YA NO EXISTE — Postgres y ficheros reales.

Caso de producción: 14 filas registradas apuntaban a rutas que ya no existían (con `is_missing = false`). El cotejo por hash
las tomaba por «copia presente» y descartaba como REPETIDO el archivo real: la fila seguía apuntando a la nada y el archivo
quedaba sin registrar. Ahora una copia solo cuenta como presente si su fichero existe de verdad.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import Mundo
from zascarr import database
from zascarr.models import File, FileFormat, Issue
from zascarr.services import importer as modulo_importer
from zascarr.services import registro_biblioteca
from zascarr.services.importer import _fichero_de_la_fila_existe, _triage_and_match
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
    yield m
    registro_biblioteca.reiniciar_para_pruebas()
    await m.cerrar()


def _real(mundo) -> Path:
    return mundo.lib / "Comics" / "Coleccion 4" / "Obra rara 04.cbz"


async def _fila_obsoleta(mundo) -> File:
    """Fila `is_missing = false` con el contenido de «Obra rara 04.cbz», enlazada a un Issue, con una decisión
    manual guardada, y cuya ruta (carpeta existente, archivo no) ya no existe."""
    real = _real(mundo)
    async with mundo.fabrica() as s:
        issue = Issue(id=uuid4(), series_id=mundo.series[0], issue_number="4")
        s.add(issue)
        await s.flush()
        fila = File(id=uuid4(), file_path=str(real.with_name("Obra rara 04 (antes de moverlo).cbz")),
                    file_name="Obra rara 04 (antes de moverlo).cbz", file_format=FileFormat.CBZ,
                    sha256_hash=hashlib.sha256(mundo.contenido[real]).hexdigest(), is_missing=False,
                    issue_id=issue.id, metadata_={"match_status": "manual", "ajuste_manual": "no-tocar"})
        s.add(fila)
        await s.commit()
        return fila


class TestReferenciaObsoletaAlRegistrar:

    async def test_la_fila_con_la_ruta_obsoleta_se_recupera_y_el_archivo_no_se_descarta_como_repetido(self, mundo):
        fila = await _fila_obsoleta(mundo)
        antes = await mundo.n_files()
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        real = _real(mundo)
        assert any("Obra rara 04.cbz" in r and "reenlazado" in r for r in informe.registered)
        assert not any("Obra rara 04" in d for d in informe.duplicates)       # NO «duplicado de la fila obsoleta»
        assert informe.error_count == 0
        async with mundo.fabrica() as s:
            reenlazada = await s.get(File, fila.id)
            con_ese_hash = (await s.execute(
                select(func.count(File.id)).where(File.sha256_hash == fila.sha256_hash))).scalar()
        # Mismo id, mismos enlaces y decisiones; solo cambia lo que describe el archivo (ruta, nombre, tamaño, hash).
        assert reenlazada.file_path == str(real) and reenlazada.file_name == real.name and reenlazada.is_missing is False
        assert reenlazada.issue_id == fila.issue_id
        assert reenlazada.metadata_["ajuste_manual"] == "no-tocar" and reenlazada.metadata_["match_status"] == "manual"
        assert con_ese_hash == 1                                               # no se creó una fila nueva
        assert await mundo.n_files() == antes + 6                              # 8 nuevos: 1 reenlace, 1 repetido, 6 filas

    async def test_una_copia_realmente_accesible_con_el_mismo_hash_sigue_siendo_un_repetido(self, mundo):
        """Control: el tratamiento de duplicado no se pierde cuando la otra copia SÍ existe."""
        original = mundo.lib / "BD" / "Album 1" / "Tomo raro 01.cbr"
        copia = mundo.lib / "BD" / "Album 1" / "Tomo raro 01 (copia).cbr"
        async with mundo.fabrica() as s:
            fila = File(id=uuid4(), file_path=str(original), file_name=original.name, file_format=FileFormat.CBR,
                        sha256_hash=hashlib.sha256(mundo.contenido[original]).hexdigest(), is_missing=False,
                        metadata_={"ajuste_manual": "no-tocar"})
            s.add(fila)
            await s.commit()
        antes = await mundo.n_files()
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()
        assert any("Tomo raro 01 (copia).cbr" in d for d in informe.duplicates)
        assert not any("reenlazado" in r for r in informe.registered)
        async with mundo.fabrica() as s:
            intacta = await s.get(File, fila.id)
            fila_de_la_copia = (await s.execute(select(File).where(File.file_path == str(copia)))).first()
        assert intacta.file_path == str(original) and intacta.metadata_ == {"ajuste_manual": "no-tocar"}
        assert fila_de_la_copia is None                                        # la copia no se registra dos veces
        assert await mundo.n_files() == antes + 6

    async def test_repetir_el_registro_tras_recuperarla_no_vuelve_a_tocar_nada(self, mundo):
        await _fila_obsoleta(mundo)
        async with mundo.fabrica() as s:
            await LibraryAdopter(s).adopt()
        n = await mundo.n_files()
        async with mundo.fabrica() as s:
            segundo = await LibraryAdopter(s).adopt()
        assert not any("reenlazado" in r for r in segundo.registered) and segundo.error_count == 0
        assert await mundo.n_files() == n


class TestMismoCotejoQueUsaElImportador:
    """`_triage_and_match` lo comparten el registro y el importador de descargas: la corrección vale para los dos."""

    async def test_obsoleta_es_recuperar_y_accesible_es_duplicado(self, mundo):
        fila = await _fila_obsoleta(mundo)
        async with mundo.fabrica() as s:
            salida = await _triage_and_match(s, _real(mundo))
        assert salida.recuperar is not None and salida.recuperar.id == fila.id and salida.duplicate_of is None
        async with mundo.fabrica() as s:
            existente = await s.get(File, fila.id)
            existente.file_path = str(_real(mundo).with_name("Obra rara 04.cbz"))     # ahora SU fichero existe
            await s.commit()
        copia = mundo.lib / "Comics" / "Coleccion 4" / "Obra rara 04 (otra copia).cbz"
        copia.write_bytes(mundo.contenido[_real(mundo)])
        async with mundo.fabrica() as s:
            salida = await _triage_and_match(s, copia)
        assert salida.recuperar is None and salida.duplicate_of == "Obra rara 04 (antes de moverlo).cbz"

    async def test_varias_coincidencias_basta_una_con_fichero_para_que_sea_repetido(self, mundo):
        """Una fila obsoleta y otra cuyo fichero sí existe, con el mismo hash: es un repetido de la que existe."""
        obsoleta = await _fila_obsoleta(mundo)
        real = _real(mundo)
        async with mundo.fabrica() as s:
            s.add(File(id=uuid4(), file_path=str(real), file_name=real.name, file_format=FileFormat.CBZ,
                       sha256_hash=obsoleta.sha256_hash, is_missing=False))
            await s.commit()
        copia = mundo.lib / "Comics" / "Coleccion 4" / "Obra rara 04 (otra copia).cbz"
        copia.write_bytes(mundo.contenido[real])
        async with mundo.fabrica() as s:
            salida = await _triage_and_match(s, copia)
        assert salida.recuperar is None and salida.duplicate_of == real.name


class TestAcreditacionDeUnReenlaceDeReferenciaObsoleta:

    async def test_una_fila_obsoleta_sin_tocar_es_revertido_y_no_por_comprobar(self, mundo):
        """Su estado PREVIO es (ruta vieja, is_missing = false): «sigue como estaba» debe reconocerlo."""
        fila = await _fila_obsoleta(mundo)
        async with mundo.fabrica() as s:
            veredicto = await LibraryAdopter(s)._contrastar(
                [(fila.id, str(_real(mundo)), fila.file_path, False)])
        assert veredicto == "revertido"


class TestFicheroDeLaFilaExiste:

    def test_existente(self, tmp_path):
        (tmp_path / "a.cbz").write_bytes(b"x")
        assert _fichero_de_la_fila_existe(str(tmp_path / "a.cbz"), tmp_path / "b.cbz") is True

    def test_ausente_con_su_carpeta_en_el_mismo_disco_es_obsoleta(self, tmp_path):
        (tmp_path / "b.cbz").write_bytes(b"x")
        assert _fichero_de_la_fila_existe(str(tmp_path / "ya_no_esta.cbz"), tmp_path / "b.cbz") is False

    def test_ausente_en_una_carpeta_que_tampoco_existe_pero_cuyo_ancestro_esta_en_el_mismo_disco(self, tmp_path):
        (tmp_path / "b.cbz").write_bytes(b"x")
        assert _fichero_de_la_fila_existe(str(tmp_path / "carpeta" / "movida" / "a.cbz"), tmp_path / "b.cbz") is False

    def test_si_el_sitio_viejo_cuelga_de_otro_disco_no_se_afirma_que_falte(self, tmp_path, monkeypatch):
        """Un disco desmontado deja su punto de montaje (vacío, en OTRO dispositivo): no se confunde con «borrado»."""
        (tmp_path / "b.cbz").write_bytes(b"x")
        monkeypatch.setattr(modulo_importer, "_dispositivo",
                            lambda ruta: 2 if Path(ruta) == tmp_path else 1)
        assert _fichero_de_la_fila_existe(str(tmp_path / "montaje" / "a.cbz"), tmp_path / "b.cbz") is True

    def test_si_no_se_puede_consultar_se_conserva_el_comportamiento_de_siempre(self, tmp_path, monkeypatch):
        def sin_permiso(_ruta):
            raise PermissionError(13, "sin permiso")
        monkeypatch.setattr(modulo_importer.os, "stat", sin_permiso)
        assert _fichero_de_la_fila_existe(str(tmp_path / "a.cbz"), tmp_path / "b.cbz") is True

    def test_sin_ningun_ancestro_visible_tampoco_se_afirma(self, tmp_path, monkeypatch):
        def nada_existe(_ruta):
            raise FileNotFoundError
        monkeypatch.setattr(modulo_importer.os, "stat", nada_existe)
        assert _fichero_de_la_fila_existe(str(tmp_path / "a.cbz"), tmp_path / "b.cbz") is True
