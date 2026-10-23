"""
tests/test_bucle_no_bloqueado.py

Regresión del hallazgo del ensayo con la biblioteca real (2026-10-01, 160 GB
en una unidad de red SMB): al arrancar, la auditoría inicial recorría y
hasheaba la biblioteca **directamente sobre el bucle de eventos** — durante
minutos `/api/health` no respondía (timeouts de 20 s) y el contenedor pasaba a
`unhealthy`. Es la regla de CLAUDE.md §4 («nada bloqueante en handlers
async»), incumplida por tres sitios que hacen E/S de disco síncrona dentro de
una corrutina:

  - `LibraryAudit.run` (listado, `stat`, hash SHA-256 en streaming).
  - `LibraryAdopter.adopt` / `Importer.scan_and_import` (listado con `rglob`).
  - `_triage_and_match` (`triage(path)` hashea el fichero ENTERO, por cada
    fichero, al adoptar y al importar).

Cómo se mide: un «latido» (una tarea que duerme 10 ms en bucle) corre a la vez
que la operación. Si la operación bloquea el bucle, el hueco entre dos latidos
crece hasta lo que dure el bloqueo; si va a un hilo, el hueco sigue siendo de
milisegundos. La operación se sustituye por una que bloquea 0,4 s a propósito
(`time.sleep`), así que la prueba no depende de lo rápido que sea el disco.
"""
from __future__ import annotations

import asyncio
import time
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from zascarr.core.importer_triage import TriageResult
from zascarr.services.importer import Importer, _triage_sin_bloquear
from zascarr.services.library_adopter import LibraryAdopter
from zascarr.services.library_audit import LibraryAudit

BLOQUEO_S = 0.4
# Un hilo aparte deja el bucle libre: el peor hueco entre latidos es de
# milisegundos. Medio bloqueo ya delata el fallo, con margen para un CI lento.
HUECO_MAXIMO_S = BLOQUEO_S / 2


async def _latido(parar: asyncio.Event) -> float:
    """Peor hueco entre dos latidos de 10 ms — mide cuánto se congeló el bucle."""
    peor = 0.0
    previo = time.perf_counter()
    while not parar.is_set():
        await asyncio.sleep(0.01)
        ahora = time.perf_counter()
        peor = max(peor, ahora - previo)
        previo = ahora
    return peor


async def _con_latido(corrutina) -> float:
    parar = asyncio.Event()
    tarea = asyncio.create_task(_latido(parar))
    await asyncio.sleep(0.05)  # que el latido arranque antes de la operación
    try:
        await corrutina
    finally:
        parar.set()
    return await tarea


def _bloquear(*_args, **_kwargs):
    time.sleep(BLOQUEO_S)


class FakeSessionAuditoria:
    def __init__(self):
        self.flush = AsyncMock()

    def add(self, _obj):
        pass


class TestLaAuditoriaNoCongelaLaApp:

    @pytest.mark.asyncio
    async def test_el_analisis_de_disco_corre_fuera_del_bucle(self, monkeypatch, tmp_path):
        with zipfile.ZipFile(tmp_path / "a.cbz", "w") as zf:
            zf.writestr("1.jpg", b"x")
        monkeypatch.setattr(
            "zascarr.services.library_audit.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        # Cualquier detector sirve: todos hacen la misma E/S síncrona.
        monkeypatch.setattr(LibraryAudit, "_detectar_mismo_contenido", _bloquear)
        auditor = LibraryAudit(db=FakeSessionAuditoria())

        hueco = await _con_latido(auditor.run())

        assert hueco < HUECO_MAXIMO_S, (
            f"la auditoría congeló el bucle {hueco:.2f} s: el análisis de "
            "disco debe ir en asyncio.to_thread (CLAUDE.md §4)"
        )


class TestLaAdopcionNoCongelaLaApp:

    @pytest.mark.asyncio
    async def test_el_listado_de_la_biblioteca_corre_fuera_del_bucle(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )

        def listado_lento(*_a, **_k):
            time.sleep(BLOQUEO_S)
            return []

        monkeypatch.setattr("zascarr.services.library_adopter.listar_comics", listado_lento)
        monkeypatch.setattr(
            "zascarr.services.runtime_settings.RuntimeSettingsService.set_flag", AsyncMock()
        )
        adopter = LibraryAdopter(db=MagicMock(commit=AsyncMock()))
        monkeypatch.setattr(adopter, "_persist_run", AsyncMock())
        # `adopt` pregunta primero qué rutas ya están registradas (consulta a la BD, no a disco).
        monkeypatch.setattr(adopter, "_rutas_registradas", AsyncMock(return_value=set()))
        monkeypatch.setattr(adopter, "_ya_registrada", AsyncMock(return_value=False))

        hueco = await _con_latido(adopter.adopt())

        assert hueco < HUECO_MAXIMO_S, f"el listado congeló el bucle {hueco:.2f} s"

    @pytest.mark.asyncio
    async def test_el_inventario_tambien_lista_fuera_del_bucle(self, monkeypatch, tmp_path):
        """El inventario previo al registro recorre toda la carpeta: en una Pi con el disco por USB
        son segundos, y la pantalla no puede congelar la app mientras tanto."""
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )

        def listado_lento(*_a, **_k):
            time.sleep(BLOQUEO_S)
            return []

        monkeypatch.setattr("zascarr.services.library_adopter.listar_comics", listado_lento)
        adopter = LibraryAdopter(db=MagicMock())
        monkeypatch.setattr(adopter, "_rutas_registradas", AsyncMock(return_value=set()))

        hueco = await _con_latido(adopter.inventario())

        assert hueco < HUECO_MAXIMO_S, f"el inventario congeló el bucle {hueco:.2f} s"


class TestElImportadorNoCongelaLaApp:

    @pytest.mark.asyncio
    async def test_el_listado_de_descargas_corre_fuera_del_bucle(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "zascarr.services.importer.get_settings",
            lambda: MagicMock(
                library_path=tmp_path / "library",
                transmission_download_dir=str(tmp_path / "d"),
                amule_incoming_dir=str(tmp_path / "a"),
                downloads_path=tmp_path / "d",
            ),
        )

        def listado_lento(*_a, **_k):
            time.sleep(BLOQUEO_S)
            return []

        monkeypatch.setattr("zascarr.services.importer.listar_comics", listado_lento)
        importer = Importer(AsyncMock())

        hueco = await _con_latido(importer.scan_and_import())

        assert hueco < HUECO_MAXIMO_S, f"el listado congeló el bucle {hueco:.2f} s"

    @pytest.mark.asyncio
    async def test_el_triage_hashea_el_fichero_fuera_del_bucle(self, monkeypatch, tmp_path):
        """`triage` lee el fichero entero para hashearlo — es lo más caro de
        adoptar o importar, y se hace una vez por fichero."""
        def triage_lento(path: Path) -> TriageResult:
            time.sleep(BLOQUEO_S)
            return TriageResult(path=path)

        monkeypatch.setattr("zascarr.services.importer.triage", triage_lento)

        hueco = await _con_latido(_triage_sin_bloquear(tmp_path / "x.cbz"))

        assert hueco < HUECO_MAXIMO_S, f"el triage congeló el bucle {hueco:.2f} s"
