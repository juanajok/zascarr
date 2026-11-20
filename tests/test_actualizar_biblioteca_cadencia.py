# ruff: noqa: E501
"""Cadencia de «Actualizar la biblioteca» (#1160) — unidad, sin base de datos.

La cuenta del periódico sale del último rescan (no del arranque), la cadencia se lee en cada vuelta
(Ajustes se aplica sin reiniciar) y un turno saltado no se reintenta de inmediato.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from zascarr import main
from zascarr.services import rescan_biblioteca
from zascarr.services.library_adopter import RescanReport


@pytest.fixture(autouse=True)
def _estado_limpio():
    rescan_biblioteca.reiniciar_para_pruebas()
    yield
    rescan_biblioteca.reiniciar_para_pruebas()


def test_proxima_apagada_es_none():
    assert rescan_biblioteca.proxima_ejecucion(0) is None


def test_proxima_sin_historial_cuenta_desde_el_arranque():
    esperado = rescan_biblioteca._arranque + timedelta(minutes=1440)
    assert rescan_biblioteca.proxima_ejecucion(1440) == esperado


def test_proxima_con_historial_cuenta_desde_el_ultimo_rescan():
    ultimo = datetime.now(UTC) - timedelta(hours=5)
    rescan_biblioteca.anotar_ultima(ultimo)
    assert rescan_biblioteca.proxima_ejecucion(1440) == ultimo + timedelta(minutes=1440)


def test_anotar_ultima_nunca_retrocede():
    ahora = datetime.now(UTC)
    rescan_biblioteca.anotar_ultima(ahora)
    rescan_biblioteca.anotar_ultima(ahora - timedelta(days=3))
    assert rescan_biblioteca.ultima_ejecucion() == ahora


@pytest.mark.asyncio
async def test_se_lee_la_ultima_persistida_una_sola_vez_al_arrancar(monkeypatch):
    ultima = datetime.now(UTC) - timedelta(days=2)

    async def _ultimo(db):
        return {"started_at": ultima}

    class _Sesion:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(rescan_biblioteca, "ultimo_persistido", _ultimo)
    await rescan_biblioteca.cargar_ultima_persistida(lambda: _Sesion())
    assert rescan_biblioteca.ultima_ejecucion() == ultima


@pytest.mark.asyncio
async def test_un_rescan_terminado_anota_su_fecha(monkeypatch):
    informe = RescanReport(started_at=datetime.now(UTC), disparador="automatico")

    async def _correr(fabrica, disparador):
        return informe

    class _Sesion:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(rescan_biblioteca, "_correr", _correr)
    assert await rescan_biblioteca.ejecutar_automatico(lambda: _Sesion()) is informe
    assert rescan_biblioteca.ultima_ejecucion() == informe.started_at


class _Reloj:
    """Sustituye `asyncio.sleep` del bucle: cuenta vueltas y corta tras `vueltas`."""

    def __init__(self, vueltas, entre=None):
        self.restantes = vueltas
        self.entre = entre or (lambda: None)

    async def __call__(self, _segundos):
        if self.restantes <= 0:
            raise asyncio.CancelledError
        self.restantes -= 1
        self.entre()


async def _correr_bucle(monkeypatch, *, minutos, ultima, vueltas=2, entre=None):
    lanzadas = []

    async def _cargar(fabrica):
        rescan_biblioteca.anotar_ultima(ultima)

    async def _automatico(fabrica):
        lanzadas.append(1)
        informe = RescanReport(started_at=datetime.now(UTC), disparador="automatico")
        rescan_biblioteca.anotar_ultima(informe.started_at)   # lo que hace el servicio real
        return informe

    config = SimpleNamespace(rescan_interval_minutes=minutos)
    monkeypatch.setattr(main, "get_settings", lambda: config)
    monkeypatch.setattr(rescan_biblioteca, "cargar_ultima_persistida", _cargar)
    monkeypatch.setattr(rescan_biblioteca, "ejecutar_automatico", _automatico)
    monkeypatch.setattr(main.asyncio, "sleep", _Reloj(vueltas, (lambda: entre(config)) if entre else None))
    with pytest.raises(asyncio.CancelledError):
        await main._rescan_loop()
    return lanzadas


@pytest.mark.asyncio
async def test_tras_un_reinicio_toca_segun_el_ultimo_rescan_y_no_un_intervalo_despues_del_arranque(monkeypatch):
    """Criterio 2 de #1160: el último fue hace 2 días y la cadencia es diaria → toca ya."""
    lanzadas = await _correr_bucle(monkeypatch, minutos=1440,
                                   ultima=datetime.now(UTC) - timedelta(days=2))
    assert len(lanzadas) == 1


@pytest.mark.asyncio
async def test_si_el_ultimo_fue_reciente_no_se_lanza(monkeypatch):
    lanzadas = await _correr_bucle(monkeypatch, minutos=1440,
                                   ultima=datetime.now(UTC) - timedelta(hours=1))
    assert lanzadas == []


@pytest.mark.asyncio
async def test_apagado_no_lanza_aunque_este_vencido(monkeypatch):
    lanzadas = await _correr_bucle(monkeypatch, minutos=0,
                                   ultima=datetime.now(UTC) - timedelta(days=30))
    assert lanzadas == []


@pytest.mark.asyncio
async def test_la_cadencia_cambiada_en_ajustes_se_aplica_sin_reiniciar(monkeypatch):
    """Criterio 3 de #1160: empieza apagado y, al activarlo, el mismo bucle lo lanza."""
    def _activar(config):
        config.rescan_interval_minutes = 1440

    lanzadas = await _correr_bucle(monkeypatch, minutos=0, vueltas=3,
                                   ultima=datetime.now(UTC) - timedelta(days=30),
                                   entre=_activar)
    assert len(lanzadas) >= 1


@pytest.mark.asyncio
async def test_un_turno_saltado_no_se_reintenta_en_la_vuelta_siguiente(monkeypatch):
    saltos = []

    async def _cargar(fabrica):
        rescan_biblioteca.anotar_ultima(datetime.now(UTC) - timedelta(days=2))

    async def _automatico(fabrica):
        saltos.append(1)
        return None   # cerrojo ocupado por el importador

    config = SimpleNamespace(rescan_interval_minutes=1440)
    monkeypatch.setattr(main, "get_settings", lambda: config)
    monkeypatch.setattr(rescan_biblioteca, "cargar_ultima_persistida", _cargar)
    monkeypatch.setattr(rescan_biblioteca, "ejecutar_automatico", _automatico)
    monkeypatch.setattr(main.asyncio, "sleep", _Reloj(4))
    with pytest.raises(asyncio.CancelledError):
        await main._rescan_loop()
    assert len(saltos) == 1
