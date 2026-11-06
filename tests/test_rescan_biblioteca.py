# ruff: noqa: E501
"""Rescan de la biblioteca (BL-R9) — unidad, sin base de datos.

Cubre el contrato del servicio de disparo (`services/rescan_biblioteca.py`): una sola ejecución a la
vez, el automático cede ante la manual y ante el cerrojo de ciclo compartido con el importador, el
foco del resultado se consume una vez, y el único que lanza la cadencia periódica es el bucle de
`main`. También los textos de cadencia y la normalización del resumen que pinta Auditoría.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from zascarr.services import rescan_biblioteca
from zascarr.services.library_adopter import RescanReport


class _SesionFalsa:
    """Sin `bind`: `_cerrojo_ciclo` la trata como libre (igual que los dobles de prueba)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _fabrica():
    return _SesionFalsa()


@pytest.fixture(autouse=True)
def _estado_limpio():
    rescan_biblioteca.reiniciar_para_pruebas()
    yield
    rescan_biblioteca.reiniciar_para_pruebas()


def _informe() -> RescanReport:
    return RescanReport(started_at=datetime.now(UTC), disparador="manual")


class TestEstado:

    def test_en_curso_y_reinicio(self):
        assert rescan_biblioteca.estado_actual().fase is rescan_biblioteca.FaseRescan.INACTIVO
        rescan_biblioteca._estado.fase = rescan_biblioteca.FaseRescan.CORRIENDO
        assert rescan_biblioteca.estado_actual().en_curso is True
        rescan_biblioteca.reiniciar_para_pruebas()
        assert rescan_biblioteca.estado_actual().en_curso is False

    def test_el_foco_del_resultado_se_consume_una_vez(self):
        rescan_biblioteca._estado.foco_resultado = True
        assert rescan_biblioteca.consumir_foco_resultado() is True
        assert rescan_biblioteca.consumir_foco_resultado() is False


class TestDisparos:

    @staticmethod
    def _cerrojo_ocupado():
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def cerrojo(fabrica):
            yield False
        return cerrojo

    async def test_dos_manuales_no_duplican(self, monkeypatch):
        async def correr(fabrica, disparador):
            return _informe()
        monkeypatch.setattr(rescan_biblioteca, "_correr", correr)
        assert rescan_biblioteca.iniciar_manual(_fabrica) is True
        assert rescan_biblioteca.estado_actual().en_curso is True
        assert rescan_biblioteca.iniciar_manual(_fabrica) is False       # no se lanza otra
        await rescan_biblioteca._tarea
        estado = rescan_biblioteca.estado_actual()
        assert estado.fase is rescan_biblioteca.FaseRescan.TERMINADO
        assert estado.informe is not None and estado.run_id is None
        await rescan_biblioteca.detener()

    async def test_el_automatico_cede_ante_la_manual(self, monkeypatch):
        suelta = asyncio.Event()

        async def correr(fabrica, disparador):
            await suelta.wait()
            return _informe()
        monkeypatch.setattr(rescan_biblioteca, "_correr", correr)
        assert rescan_biblioteca.iniciar_manual(_fabrica) is True
        assert await rescan_biblioteca.ejecutar_automatico(_fabrica) is None   # manual en curso
        assert rescan_biblioteca.estado_actual().disparador == "manual"
        suelta.set()
        await rescan_biblioteca._tarea
        await rescan_biblioteca.detener()

    async def test_el_automatico_cede_ante_el_cerrojo_de_ciclo(self, monkeypatch):
        """Con el cerrojo ocupado (p. ej. el ciclo del importador), el turno se salta sin efectos."""
        monkeypatch.setattr(rescan_biblioteca, "_cerrojo_ciclo", self._cerrojo_ocupado())
        assert await rescan_biblioteca.ejecutar_automatico(_fabrica) is None
        assert rescan_biblioteca.estado_actual().fase is rescan_biblioteca.FaseRescan.INACTIVO

    async def test_la_manual_con_cerrojo_ocupado_queda_ocupada(self, monkeypatch):
        monkeypatch.setattr(rescan_biblioteca, "_cerrojo_ciclo", self._cerrojo_ocupado())
        assert rescan_biblioteca.iniciar_manual(_fabrica) is True
        await rescan_biblioteca._tarea
        assert rescan_biblioteca.estado_actual().fase is rescan_biblioteca.FaseRescan.OCUPADO
        await rescan_biblioteca.detener()


def test_el_periodico_solo_lo_lanza_el_bucle_de_main():
    """La cadencia periódica la dispara únicamente `main._rescan_loop` (decisión del PO, BL-R9)."""
    raiz = Path(__file__).resolve().parents[1] / "src" / "zascarr"
    llamadores = sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*.py")
                        if "rescan_biblioteca.ejecutar_automatico(" in p.read_text())
    assert llamadores == ["main.py"]


class TestTextos:

    def test_cadencia(self, monkeypatch):
        from zascarr.web import auditoria
        for minutos, esperado in (
            (0, "El rescan automático está apagado."),
            (1440, "Además, ZascArr lo hace solo una vez al día."),
            (2880, "Además, ZascArr lo hace solo cada 2 días."),
            (120, "Además, ZascArr lo hace solo cada 2 horas."),
            (45, "Además, ZascArr lo hace solo cada 45 minutos."),
        ):
            monkeypatch.setattr(auditoria, "get_settings",
                                lambda m=minutos: SimpleNamespace(rescan_interval_minutes=m))
            assert auditoria._texto_cadencia() == esperado

    def test_resumen_normaliza_y_conserva_las_listas(self):
        from zascarr.web import auditoria
        informe = _informe()
        informe.nuevos_registrados = 2
        informe.errores.append("una causa")
        resumen = auditoria._resumen(informe)
        assert resumen["nuevos_registrados"] == 2
        assert resumen["errores"] == ["una causa"]
        assert resumen["re_triados"] == 0 and resumen["resultado_biblioteca"] == ""
        assert auditoria._resumen(None) is None
        assert auditoria._resumen({"errores": None})["errores"] == []


class TestPantalla:

    def test_el_fragmento_sin_historial_invita_y_declara_la_garantia(self):
        """Sin ningún rescan: el fragmento se pinta, la garantía U21 va junto a la acción
        y no hay palabras internas («stat», «triaje», «cerrojo», «ImportRun»)."""
        from fastapi.testclient import TestClient

        from zascarr.database import get_db
        from zascarr.main import app

        class Ejec:
            def scalar_one_or_none(self):
                return None

        class Sesion:
            async def execute(self, _st):
                return Ejec()

        async def _get_db():
            yield Sesion()
        app.dependency_overrides[get_db] = _get_db
        try:
            r = TestClient(app).get("/ui/auditoria/rescanear")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200
        assert "Reescanear la biblioteca" in r.text
        assert "No mueve, no renombra y no borra nada" in r.text
        assert "Todavía no se ha hecho ningún rescan" in r.text
        for interna in (" stat", "triaje", "cerrojo", "ImportRun"):
            assert interna not in r.text

    def test_el_fragmento_tras_reinicio_pinta_el_informe_persistido(self):
        """B1 del peer review: sin estado en memoria (proceso recién arrancado), el fragmento lee el
        `ImportRun` persistido y lo pinta SIN reventar (antes `started_at=None` → 500)."""
        from datetime import UTC, datetime

        from fastapi.testclient import TestClient

        from zascarr.database import get_db
        from zascarr.main import app

        class Run:
            details = {
                "kind": "rescan", "disparador": "automatico", "files_scanned": 1300,
                "sin_cambios": 1290, "nuevos_registrados": 3, "nuevos_a_revisar": 2,
                "repetidos": 1, "reenlazados": 0, "re_triados": 0, "desaparecidos": 0,
                "reaparecidos": 0, "errores": [], "no_revisado": False,
                "resultado_biblioteca": "comprobada", "por_comprobar": 0,
            }
            started_at = datetime(2026, 11, 6, 8, 0, tzinfo=UTC)
            files_scanned = 1300

        class Ejec:
            def scalar_one_or_none(self):
                return Run()

        class Sesion:
            async def execute(self, _st):
                return Ejec()

        async def _get_db():
            yield Sesion()
        app.dependency_overrides[get_db] = _get_db
        try:
            r = TestClient(app).get("/ui/auditoria/rescanear")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200
        assert "Último rescan" in r.text and "automática" in r.text
        assert "<strong>3</strong> nuevos a su serie" in r.text
        assert "<strong>1300</strong> archivos mirados" in r.text
        assert "Todavía no se ha hecho ningún rescan" not in r.text

    def test_el_post_lanza_una_sola_y_enseña_el_curso(self, monkeypatch):
        from fastapi.testclient import TestClient

        import zascarr.web.auditoria as auditoria
        from zascarr.database import get_db
        from zascarr.main import app

        async def correr(fabrica, disparador):
            await asyncio.sleep(3600)                  # bloqueada hasta que el portal se cierre
            return _informe()
        monkeypatch.setattr(rescan_biblioteca, "_correr", correr)
        monkeypatch.setattr(auditoria.database, "async_session_factory", _fabrica)

        class Ejec:
            def scalar_one_or_none(self):
                return None

        class Sesion:
            async def execute(self, _st):
                return Ejec()

        async def _get_db():
            yield Sesion()
        app.dependency_overrides[get_db] = _get_db
        try:
            r = TestClient(app).post("/ui/auditoria/rescanear",
                                     headers={"HX-Request": "true"})
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 200
        assert "Rescan en curso" in r.text
        assert "No se ha lanzado otra" not in r.text
        assert "Reescaneando…" in r.text                   # el botón queda deshabilitado y nombra la tarea
