"""BL-OPS3 (#456), T-03: la reautenticación compartida (retraso, bloqueo duro, cola, ráfaga).

`credenciales_validas` se sustituye por un doble que cuenta cuántas veces se calcula PBKDF2; el reloj es
inyectable. No se toca ningún secreto real.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from zascarr.services import auth, reautenticacion
from zascarr.services.reautenticacion import (
    BLOQUEO_S,
    UMBRAL_FALLOS,
    VENTANA_S,
    Reauth,
    comprobar_contrasena_actual,
)

AJUSTES = SimpleNamespace(auth_username="", auth_mode="password")


class Reloj:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def pbkdf2(monkeypatch):
    """Doble de la verificación: `.correcta` decide si acierta y `.llamadas` cuenta los cálculos."""
    estado = SimpleNamespace(correcta=False, llamadas=0, pausa=0.0)

    async def falso(_u, _p, _s):
        estado.llamadas += 1
        if estado.pausa:
            await asyncio.sleep(estado.pausa)
        return estado.correcta

    async def sin_espera():
        return None

    monkeypatch.setattr(auth, "credenciales_validas", falso)
    monkeypatch.setattr(auth, "esperar_retraso", sin_espera)
    return estado


async def _fallar(n: int, reloj: Reloj):
    for _ in range(n):
        await comprobar_contrasena_actual("mal", AJUSTES, reloj=reloj)


@pytest.mark.asyncio
async def test_un_acierto_es_ok_y_un_fallo_incorrecta(pbkdf2):
    pbkdf2.correcta = True
    assert (await comprobar_contrasena_actual("bien", AJUSTES)).resultado is Reauth.OK
    pbkdf2.correcta = False
    assert (await comprobar_contrasena_actual("mal", AJUSTES)).resultado is Reauth.INCORRECTA


@pytest.mark.asyncio
async def test_el_sexto_intento_esta_bloqueado_aunque_sea_la_correcta_y_no_calcula_pbkdf2(pbkdf2):
    """AC-05: 5 fallos en 15 min ⇒ bloqueo, sin PBKDF2, con la hora de fin."""
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS, reloj)
    assert pbkdf2.llamadas == UMBRAL_FALLOS
    pbkdf2.correcta = True
    r = await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)
    assert r.resultado is Reauth.BLOQUEADA and r.hasta_epoch == reloj.t + BLOQUEO_S
    assert pbkdf2.llamadas == UMBRAL_FALLOS, "durante el bloqueo no se calcula PBKDF2"


@pytest.mark.asyncio
async def test_a_los_30_minutos_del_ultimo_fallo_vuelve_a_comprobarse(pbkdf2):
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS, reloj)
    pbkdf2.correcta = True
    reloj.t += BLOQUEO_S - 1
    assert (await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)).resultado is Reauth.BLOQUEADA
    reloj.t += 2
    assert (await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)).resultado is Reauth.OK


@pytest.mark.asyncio
async def test_un_acierto_antes_del_quinto_pone_el_contador_a_cero(pbkdf2):
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS - 1, reloj)
    pbkdf2.correcta = True
    assert (await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)).resultado is Reauth.OK
    pbkdf2.correcta = False
    await _fallar(UMBRAL_FALLOS - 1, reloj)          # otra vez cuatro: aún no hay bloqueo
    assert (await comprobar_contrasena_actual("mal", AJUSTES, reloj=reloj)).resultado is Reauth.INCORRECTA


@pytest.mark.asyncio
async def test_los_fallos_caducan_a_los_15_minutos(pbkdf2):
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS - 1, reloj)
    reloj.t += VENTANA_S + 1
    assert (await comprobar_contrasena_actual("mal", AJUSTES, reloj=reloj)).resultado is Reauth.INCORRECTA
    assert reautenticacion._bloqueada_hasta == 0.0       # el quinto «lejano» ya no suma con los viejos


@pytest.mark.asyncio
async def test_cola_llena_es_ocupada_y_no_cuenta_como_fallo(pbkdf2, monkeypatch):
    async def llena(*_a, **_k):
        raise auth.ColaDeVerificacionLlenaError

    monkeypatch.setattr(reautenticacion, "intentar_credenciales", llena)
    r = await comprobar_contrasena_actual("x", AJUSTES)
    assert r.resultado is Reauth.OCUPADA and reautenticacion._fallos == []


@pytest.mark.asyncio
async def test_el_bloqueo_de_reautenticacion_no_bloquea_login_ni_al_reves(pbkdf2):
    """AC-22: el bloqueo duro es solo de aquí; `/login` (intentar_credenciales) sigue funcionando; el RETRASO es
    el contador global compartido (los fallos de aquí lo alimentan)."""
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS, reloj)
    assert auth._fallos_contador == UMBRAL_FALLOS, "el retraso progresivo global se alimenta desde aquí"
    pbkdf2.correcta = True
    assert await auth.intentar_credenciales("", "bien", AJUSTES) is True       # /login entra
    assert (await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)).resultado is Reauth.BLOQUEADA
    # y al revés: fallos de /login suben el contador global pero no bloquean la reautenticación
    reautenticacion.reiniciar_estado()
    pbkdf2.correcta = False
    for _ in range(UMBRAL_FALLOS + 2):
        await auth.intentar_credenciales("", "mal", AJUSTES)
    pbkdf2.correcta = True
    assert (await comprobar_contrasena_actual("bien", AJUSTES, reloj=reloj)).resultado is Reauth.OK


@pytest.mark.asyncio
async def test_en_una_rafaga_se_cuelan_como_mucho_dos_intentos_de_mas(pbkdf2):
    """AC-21: con el contador en 4 y 8 intentos a la vez, solo caben los de la cola (3): uno hace el 5.º y
    se cuelan 2 más; el resto reciben «ocupada» o «bloqueada» sin PBKDF2."""
    reloj = Reloj()
    await _fallar(UMBRAL_FALLOS - 1, reloj)
    antes = pbkdf2.llamadas
    pbkdf2.pausa = 0.02
    resultados = await asyncio.gather(*(
        comprobar_contrasena_actual("mal", AJUSTES, reloj=reloj) for _ in range(8)))
    calculados = pbkdf2.llamadas - antes
    assert calculados <= 3, f"se calcularon {calculados} verificaciones: pasan más de 1 + 2 intentos"
    assert sum(r.resultado in (Reauth.OCUPADA, Reauth.BLOQUEADA) for r in resultados) >= 5


def test_las_constantes_son_las_de_la_spec_y_estan_en_un_solo_sitio():
    assert (UMBRAL_FALLOS, VENTANA_S, BLOQUEO_S) == (5, 15 * 60, 30 * 60)
