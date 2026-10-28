"""#332 (residual 1 de #329) — un archivo que se puede `stat` pero no leer no crea fila.

Postgres y ficheros reales. El recorrido sí ve la carpeta; lo que falla es la lectura del archivo.
Debe contar como **error** (no como omisión silenciosa), informarse con la causa y dejar el marcador
sin poner, sin reabrir el hueco del residual 2.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_registro_biblioteca_pg import Mundo, _cbz
from zascarr import database
from zascarr.core import importer_triage
from zascarr.models import File
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
    yield m
    await m.cerrar()


class TestAdopcionConArchivoIlegible:

    async def test_ilegible_no_crea_fila_informa_causa_y_no_pone_marcador(self, mundo, monkeypatch):
        destino = mundo.lib / "Nuevos" / "Nuevo 01.cbz"
        _cbz(destino, "x")
        real = importer_triage.sha256_streaming

        def se_cae(ruta):
            if Path(ruta) == destino:
                raise OSError(5, "Input/output error")
            return real(ruta)

        monkeypatch.setattr(importer_triage, "sha256_streaming", se_cae)
        async with mundo.fabrica() as s:
            informe = await LibraryAdopter(s).adopt()

        assert informe.error_count == 1
        assert informe.errors == ["Nuevo 01.cbz: no se pudo leer (OSError: Input/output error)"]
        assert informe.unreadable == 0                  # el recorrido sí pudo leer la carpeta
        assert informe.added_count > 0                  # el resto de archivos se registra
        assert destino.exists()                         # la adopción nunca mueve

        async with mundo.fabrica() as s:
            fila = (await s.execute(
                select(File.id).where(File.file_path == str(destino))
            )).scalar_one_or_none()
        assert fila is None                             # el ilegible no crea fila

        assert await mundo.marcador() is False          # hay un error: no se da por completo
