"""Flujo app → admisión host en memoria; sin socket, unidad ni efectos."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.ops.admision_actualizar_ops4 import CodigoAdmision
from deploy.ops.admision_host_actualizar_ops4 import admitir_host
from zascarr.services.reautenticacion import Reauth, ResultadoReauth
from zascarr.services.solicitud_actualizacion import ResultadoSolicitud, preparar_solicitud

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000
SAL = b"sal-flujo"
HASH = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
    "sha256", b"clave", SAL, 10_000
).hex()


async def comprobar_ok(_p, _s):
    return ResultadoReauth(Reauth.OK)


def settings(tmp_path: Path) -> SimpleNamespace:
    clave = tmp_path / "ops.key"
    clave.write_text(CLAVE.hex() + "\n", encoding="ascii")
    return SimpleNamespace(auth_mode="password", ops_key_file=str(clave))


class Lector:
    def __init__(self, password_hash: str = HASH) -> None:
        self.password_hash = password_hash
        self.llamadas = 0

    def leer(self):
        self.llamadas += 1
        return "password", self.password_hash


@pytest.mark.asyncio
async def test_flujo_completo_en_memoria(tmp_path: Path) -> None:
    preparada = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True,
        ahora=AHORA, id_=ID, comprobar=comprobar_ok,
    )
    assert preparada.resultado is ResultadoSolicitud.PREPARADA

    lector = Lector()
    reclamados: list[str] = []

    def reclamar(id_: str) -> bool:
        if id_ in reclamados:
            return False
        reclamados.append(id_)
        return True

    assert admitir_host(
        preparada.linea.bytes(), clave=CLAVE, ahora=AHORA,
        lector=lector, reclamar_id=reclamar,
    ) is CodigoAdmision.ACEPTADA
    assert lector.llamadas == 1

    assert admitir_host(
        preparada.linea.bytes(), clave=CLAVE, ahora=AHORA,
        lector=lector, reclamar_id=reclamar,
    ) is CodigoAdmision.REPETIDA
    assert lector.llamadas == 1


@pytest.mark.asyncio
async def test_flujo_con_password_incorrecta_en_host(tmp_path: Path) -> None:
    preparada = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True,
        ahora=AHORA, id_=ID, comprobar=comprobar_ok,
    )
    otro = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
        "sha256", b"otra", SAL, 10_000
    ).hex()
    assert admitir_host(
        preparada.linea.bytes(), clave=CLAVE, ahora=AHORA,
        lector=Lector(otro), reclamar_id=lambda _: True,
    ) is CodigoAdmision.PRUEBA_INVALIDA


@pytest.mark.asyncio
async def test_flujo_caducado_no_verifica_bd(tmp_path: Path) -> None:
    preparada = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True,
        ahora=AHORA - 121, id_=ID, comprobar=comprobar_ok,
    )
    lector = Lector()
    assert admitir_host(
        preparada.linea.bytes(), clave=CLAVE, ahora=AHORA,
        lector=lector, reclamar_id=lambda _: True,
    ) is CodigoAdmision.CADUCADA
    assert lector.llamadas == 0
