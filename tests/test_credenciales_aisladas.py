# ruff: noqa: E501
"""Credenciales del `.env`: instalación, conservación y protección, probadas en un sistema aislado y desechable.

Cada caso lo decide un guion de `tests/escenarios/` ejecutado como **root** (con usuarios sintéticos y un `docker`
de pega) y lo mide **intentándolo**: leer el `.env` como otro usuario, reemplazarlo como el usuario de servicio,
reejecutar el instalador real. Un `grep chmod` sobre el script no sustituye a esto (y por eso no hay ninguno aquí).

Sin un sistema desechable con root (ver `tests/_sistema_aislado.py`) la prueba se **salta** y se cuenta como «no
ejecutada» en el informe de la PR: una prueba saltada no es una prueba pasada. Los guiones no imprimen nunca el valor
de una credencial; solo longitudes, huellas y modos.

Casos (ID → qué demuestra), también el contrato de la PR:

| ID | Contrato |
|---|---|
| I01-I02 | instalación nueva sin intervención: se genera la contraseña antes de crear PostgreSQL |
| I03 | el `.env` queda `600 root:root` |
| I04, I06 | reejecución / credencial válida existente: se conserva |
| I05, I05b | base ya inicializada sin contraseña conocida: se detiene, no inventa otra |
| I07a, I07b, P13 | salidas saneadas |
| I08 | la plantilla no lleva secretos reales |
| I09-* | ausente, vacío, comillas, ejemplo de otra época, mayúsculas, espacios: rechazado y sustituido |
| I10 | un fallo al escribir el `.env` lo deja como estaba, sin temporales, y no arranca nada |
| M01-M08 | instalación manual: `scripts/credenciales.sh` iniciar / comprobar / corregir / detenerse |
| P00, P00b | controles positivos (la denegación posterior no es un efecto del directorio temporal) |
| P01-P02b | confidencialidad: lectura denegada al usuario de servicio y a otros usuarios locales |
| P03-P08 | integridad: no editar, truncar, eliminar, mover, reemplazar, ni redirigir el enlace efectivo |
| P07* | el usuario de servicio tampoco puede tocar lo que root ejecuta (compose, Dockerfile, scripts) |
| P09-P09c | modo y propietario resultantes |
| P10 | un enlace hostil en el repo no logra que se cambie el dueño de un fichero ajeno |
| P11-P12, P15* | compatibilidad: root opera (incl. `backup.sh`), reconfigurar conserva modo y credencial; el usuario de servicio no |
| P14, P14b | una carpeta compartida no se reclama y el instalador se detiene explicándolo |
| W01-W06 | el secreto nuevo nunca vive en un fichero abierto (ni el temporal ni un `.env` heredado en 644/666) |
| U01-U07 | ubicación insegura (carpeta de otra cuenta, antecesor, enlace, `.env` enlace, código del usuario de servicio) → se detiene sin escribir; los casos legítimos (enlace de root, raíz compartida de root) siguen |
"""
from __future__ import annotations

import re

import pytest

from tests._sistema_aislado import Resultado, ejecutar

CASOS_INSTALACION = [
    "I01", "I02", "I03", "I04", "I05", "I05b", "I06", "I07a", "I07b", "I08",
    "I09-vacia", "I09-ausente", "I09-comillas", "I09-compose", "I09-mayusculas", "I09-espacios", "I10",
]
CASOS_ESCRITURA = ["W01", "W02", "W03", "W04", "W05", "W06"]
CASOS_UBICACION = [
    "U01", "U01b", "U02", "U02b", "U03", "U03b", "U04", "U05", "U06", "U07", "U08", "U08b", "U09", "U09b", "U10", "U10b", "U10c",
]
CASOS_GUION = ["G01", "G01b", "G01c", "G01d", "G01e", "G02", "G02b", "G02c"]
CASOS_MANUAL = ["M01", "M02", "M03", "M04", "M05", "M06", "M07", "M08"]
CASOS_IDENTIDADES = [
    "P00", "P00b", "P01", "P02", "P02b", "P03", "P03b", "P04", "P04b", "P05", "P05b", "P06", "P06b",
    "P07", "P07b", "P07c", "P08", "P09", "P09b", "P09c", "P10", "P11", "P11b", "P11c", "P15", "P15b", "P15c", "P12", "P13",
    "P14", "P14b",
]


@pytest.fixture(scope="module")
def instalacion() -> Resultado:
    return ejecutar("instalacion.sh")


@pytest.fixture(scope="module")
def identidades() -> Resultado:
    return ejecutar("identidades.sh")


@pytest.fixture(scope="module")
def escritura() -> Resultado:
    return ejecutar("escritura.sh")


@pytest.fixture(scope="module")
def ubicacion() -> Resultado:
    return ejecutar("ubicacion.sh")


@pytest.fixture(scope="module")
def guion() -> Resultado:
    return ejecutar("guion_f1bis.sh")


@pytest.fixture(scope="module")
def manual() -> Resultado:
    return ejecutar("manual.sh")


def _comprobar(resultado: Resultado, caso: str) -> None:
    assert caso in resultado.casos, (
        f"el guion no llegó a evaluar {caso} (modo {resultado.modo}, rc={resultado.returncode}):\n"
        f"{resultado.stdout[-1500:]}\n{resultado.stderr[-800:]}"
    )
    estado, detalle = resultado.casos[caso]
    assert estado == "PASS", f"{caso}: {detalle}"


@pytest.mark.parametrize("caso", CASOS_INSTALACION)
def test_instalacion_y_conservacion(instalacion, caso):
    _comprobar(instalacion, caso)


@pytest.mark.parametrize("caso", CASOS_IDENTIDADES)
def test_proteccion_por_identidades(identidades, caso):
    _comprobar(identidades, caso)


@pytest.mark.parametrize("caso", CASOS_ESCRITURA)
def test_el_secreto_nuevo_nunca_esta_en_un_fichero_abierto(escritura, caso):
    _comprobar(escritura, caso)


@pytest.mark.parametrize("caso", CASOS_UBICACION)
def test_ubicacion_insegura_detiene_el_instalador(ubicacion, caso):
    _comprobar(ubicacion, caso)


@pytest.mark.parametrize("caso", CASOS_GUION)
def test_el_guion_de_la_fase_1_bis_mide_bien_la_proteccion(guion, caso):
    """El guion del ensayo real (docs/design/m4-fase1bis/vm-ejecutar.sh) da PASS sobre una instalación protegida y SE PARA
    sobre una expuesta: sin esto, un PASS del ensayo real no demostraría nada."""
    _comprobar(guion, caso)


@pytest.mark.parametrize("caso", CASOS_MANUAL)
def test_instalacion_manual(manual, caso):
    _comprobar(manual, caso)


def test_los_escenarios_terminan_bien_y_no_dejan_ninguna_credencial_en_sus_salidas(instalacion, identidades, manual, escritura, ubicacion, guion):
    """Salidas saneadas: lo que los guiones imprimen (y lo que se publicaría como artefacto de la CI) no lleva
    ninguna credencial: ni las sintéticas de las pruebas ni una generada (48 hexadecimales)."""
    for resultado in (instalacion, identidades, manual, escritura, ubicacion, guion):
        assert resultado.returncode == 0, resultado.stderr[-800:]
        todo = resultado.stdout + resultado.stderr
        assert "Sint3tica" not in todo
        assert not re.search(r"\b[0-9a-f]{48}\b", todo), "aparece una cadena con forma de contraseña generada"
