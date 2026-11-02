"""#123 (QA, A1 y A3 de #385): `reconciliar_al_arrancar` NUNCA propaga una excepción, reintenta con backoff y deja su estado.

Se prueba sin base de datos: un servicio falso y un `asyncio.sleep` que anota cuánto se esperó.
"""
from __future__ import annotations

import pytest

import zascarr.services.asignacion as asignacion_mod
from zascarr.services.asignacion import estado_ultima_reconciliacion, reconciliar_al_arrancar


class Roto:
    def __init__(self, fallos: int):
        self.fallos, self.llamadas = fallos, 0

    async def reconciliar(self):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise RuntimeError("la BD se cayó")
        return []


@pytest.fixture
def esperas(monkeypatch):
    anotadas: list[float] = []

    async def dormir(segundos):
        anotadas.append(segundos)

    monkeypatch.setattr(asignacion_mod.asyncio, "sleep", dormir)
    return anotadas


@pytest.mark.asyncio
async def test_a1_si_construir_el_servicio_por_defecto_falla_no_propaga(monkeypatch, esperas):
    """Antes `servicio_por_defecto()` quedaba fuera del `try`: una configuración rota subía por la tarea de fondo y, al apagar,
    `main.py` relanzaba la excepción y cortaba la limpieza."""
    def explota():
        raise ValueError("configuración inválida")

    monkeypatch.setattr(asignacion_mod, "servicio_por_defecto", explota)
    assert await reconciliar_al_arrancar() == 0                      # no lanza
    assert estado_ultima_reconciliacion()["ok"] is False
    assert estado_ultima_reconciliacion()["error"] == "ValueError"


@pytest.mark.asyncio
async def test_a3_el_backoff_es_exponencial_y_no_espera_tras_el_ultimo_intento(esperas):
    roto = Roto(fallos=99)
    assert await reconciliar_al_arrancar(roto) == 0
    b = asignacion_mod.RECONCILIACION_BACKOFF_S
    assert roto.llamadas == asignacion_mod.RECONCILIACION_INTENTOS
    assert esperas == [b, b * 2]                                      # 1 s, 2 s; tras el 3.º fallo no se duerme


@pytest.mark.asyncio
async def test_a3_un_fallo_y_luego_exito_deja_ok_con_dos_intentos(esperas):
    assert await reconciliar_al_arrancar(Roto(fallos=1)) == 0
    assert esperas == [asignacion_mod.RECONCILIACION_BACKOFF_S]
    assert estado_ultima_reconciliacion() == {"ok": True, "intentos": 2, "error": None}


@pytest.mark.asyncio
async def test_a3_los_intentos_intermedios_dejan_el_estado_en_curso(esperas, monkeypatch):
    vistos = []
    real = asignacion_mod.estado_ultima_reconciliacion

    async def dormir(segundos):
        vistos.append(dict(real()))

    monkeypatch.setattr(asignacion_mod.asyncio, "sleep", dormir)
    await reconciliar_al_arrancar(Roto(fallos=99))
    assert [v["ok"] for v in vistos] == [None, None] and [v["intentos"] for v in vistos] == [1, 2]
    assert real()["ok"] is False and real()["intentos"] == 3


@pytest.mark.asyncio
async def test_una_cancelacion_no_se_traga(monkeypatch, esperas):
    """Apagar la aplicación cancela la tarea: `CancelledError` NO es una excepción a tragar."""
    import asyncio

    class Cancelado:
        async def reconciliar(self):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await reconciliar_al_arrancar(Cancelado())


@pytest.mark.asyncio
async def test_a3_el_backoff_dobla_la_espera_en_cada_intento(monkeypatch, esperas):
    """Con 3 intentos solo hay dos esperas (1 y 2 s), que un backoff lineal también daría: con 5 se ve la progresión."""
    monkeypatch.setattr(asignacion_mod, "RECONCILIACION_INTENTOS", 5)
    await reconciliar_al_arrancar(Roto(fallos=99))
    b = asignacion_mod.RECONCILIACION_BACKOFF_S
    assert esperas == [b, b * 2, b * 4, b * 8]
