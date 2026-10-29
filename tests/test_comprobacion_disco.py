# ruff: noqa: E501
"""#232 — estado y exclusión en proceso de «Comprobar el disco», sin PostgreSQL.

El cerrojo real se prueba en `test_comprobacion_disco_pg.py`; aquí la fábrica no tiene bind y el
servicio se comporta como si el cerrojo estuviera libre.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from zascarr.services import comprobacion_disco as servicio
from zascarr.services.comprobacion_disco import EstadoCicloDisco, FaseCicloDisco
from zascarr.services.importer import ImportReport


class _FakeSession:
    bind = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _fabrica():
    return _FakeSession()


def _informe(disparador: str = "manual") -> ImportReport:
    ahora = datetime.now(UTC)
    return ImportReport(started_at=ahora, finished_at=ahora, disparador=disparador,
                        run_id=uuid4())


@pytest.fixture(autouse=True)
async def _limpio():
    servicio.reiniciar_para_pruebas()
    yield
    await servicio.detener()


class TestEstadoYEjecucion:

    async def test_manual_marca_en_curso_y_responde_sin_esperar_al_ciclo(self):
        evento = asyncio.Event()
        llamadas: list[str] = []

        async def ejecutar(_notifier, _fabrica, _importer, *, disparador="automatico"):
            llamadas.append(disparador)
            await evento.wait()
            return _informe(disparador)

        assert servicio.iniciar_manual(_fabrica, ejecutar=ejecutar) is True
        estado = servicio.estado_actual()
        assert estado.fase is FaseCicloDisco.CORRIENDO
        assert estado.disparador == "manual"
        assert llamadas == []

        evento.set()
        await asyncio.wait_for(servicio._tarea, 2)
        assert llamadas == ["manual"]
        assert servicio.estado_actual().fase is FaseCicloDisco.TERMINADO
        assert servicio.estado_actual().run_id

    async def test_segundo_post_no_crea_otra_tarea(self):
        evento = asyncio.Event()
        llamadas = 0

        async def ejecutar(*_a, **_k):
            nonlocal llamadas
            llamadas += 1
            await evento.wait()
            return _informe()

        assert servicio.iniciar_manual(_fabrica, ejecutar=ejecutar) is True
        assert servicio.iniciar_manual(_fabrica, ejecutar=ejecutar) is False
        evento.set()
        await asyncio.wait_for(servicio._tarea, 2)
        assert llamadas == 1

    async def test_automatico_salta_si_hay_manual_en_curso(self):
        evento = asyncio.Event()
        llamadas: list[str] = []

        async def ejecutar(_n, _f, _i, *, disparador="automatico"):
            llamadas.append(disparador)
            await evento.wait()
            return _informe(disparador)

        servicio.iniciar_manual(_fabrica, ejecutar=ejecutar)
        assert await servicio.ejecutar_automatico(_fabrica, ejecutar=ejecutar) is None
        assert llamadas == []
        evento.set()
        await asyncio.wait_for(servicio._tarea, 2)

    async def test_manual_no_lanza_si_el_automatico_esta_en_curso(self):
        evento = asyncio.Event()
        llamadas: list[str] = []

        async def ejecutar(_n, _f, _i, *, disparador="automatico"):
            llamadas.append(disparador)
            await evento.wait()
            return _informe(disparador)

        tarea = asyncio.create_task(servicio.ejecutar_automatico(_fabrica, ejecutar=ejecutar))
        for _ in range(20):
            if servicio.estado_actual().en_curso:
                break
            await asyncio.sleep(0)
        assert servicio.iniciar_manual(_fabrica, ejecutar=ejecutar) is False
        evento.set()
        await asyncio.wait_for(tarea, 2)
        assert llamadas == ["automatico"]

    async def test_excepcion_deja_error_y_no_run_id(self):
        class FallaError(Exception):
            pass

        async def ejecutar(*_a, **_k):
            raise FallaError

        servicio.iniciar_manual(_fabrica, ejecutar=ejecutar)
        await asyncio.wait_for(servicio._tarea, 2)
        estado = servicio.estado_actual()
        assert estado.fase is FaseCicloDisco.ERROR
        assert estado.causa == "FallaError" and estado.run_id is None

    async def test_detener_cancela_y_deja_inactivo(self):
        evento = asyncio.Event()

        async def ejecutar(*_a, **_k):
            await evento.wait()
            return _informe()

        servicio.iniciar_manual(_fabrica, ejecutar=ejecutar)
        assert servicio.estado_actual().en_curso
        await servicio.detener()
        assert servicio.estado_actual() == EstadoCicloDisco()

    async def test_foco_del_resultado_se_consume_una_sola_vez(self):
        async def ejecutar(*_a, **_k):
            return _informe()

        servicio.iniciar_manual(_fabrica, ejecutar=ejecutar)
        await asyncio.wait_for(servicio._tarea, 2)
        assert servicio.consumir_foco_resultado() is True
        assert servicio.consumir_foco_resultado() is False

    async def test_el_bucle_no_reinicia_la_espera_por_un_manual(self, monkeypatch):
        from zascarr import main
        from zascarr.services import comprobacion_disco as modulo

        esperas: list[int] = []

        async def automatico(_fabrica):
            return None

        async def dormir(segundos):
            esperas.append(segundos)
            raise asyncio.CancelledError

        monkeypatch.setattr(modulo, "ejecutar_automatico", automatico)
        monkeypatch.setattr(asyncio, "sleep", dormir)
        with pytest.raises(asyncio.CancelledError):
            await main._import_loop(15)
        assert esperas == [900]

    async def test_veinte_post_solo_crean_una_tarea(self):
        evento = asyncio.Event()

        async def ejecutar(*_a, **_k):
            await evento.wait()
            return _informe()

        resultados = [servicio.iniciar_manual(_fabrica, ejecutar=ejecutar) for _ in range(20)]
        assert sum(resultados) == 1
        evento.set()
        await asyncio.wait_for(servicio._tarea, 2)
