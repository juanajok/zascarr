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
| P00, P00b | controles positivos (la denegación posterior no es un efecto del directorio temporal) |
| P01-P02b | confidencialidad: lectura denegada al usuario de servicio y a otros usuarios locales |
| P03-P08 | integridad: no editar, truncar, eliminar, mover, reemplazar, ni redirigir el enlace efectivo |
| P07* | el usuario de servicio tampoco puede tocar lo que root ejecuta (compose, Dockerfile, scripts) |
| P09-P09c | modo y propietario resultantes |
| P10 | un enlace hostil en el repo no logra que se cambie el dueño de un fichero ajeno |
| P11-P12 | compatibilidad: root opera, reconfigurar conserva modo y credencial |
| P14, P14b | una carpeta compartida no se reclama y se avisa |
"""
from __future__ import annotations

import pytest

from tests._sistema_aislado import Resultado, ejecutar

CASOS_INSTALACION = [
    "I01", "I02", "I03", "I04", "I05", "I05b", "I06", "I07a", "I07b", "I08",
    "I09-vacia", "I09-ausente", "I09-comillas", "I09-compose", "I09-mayusculas", "I09-espacios",
]
CASOS_IDENTIDADES = [
    "P00", "P00b", "P01", "P02", "P02b", "P03", "P03b", "P04", "P04b", "P05", "P05b", "P06", "P06b",
    "P07", "P07b", "P07c", "P08", "P09", "P09b", "P09c", "P10", "P11", "P11b", "P11c", "P12", "P13",
    "P14", "P14b",
]


@pytest.fixture(scope="module")
def instalacion() -> Resultado:
    return ejecutar("instalacion.sh")


@pytest.fixture(scope="module")
def identidades() -> Resultado:
    return ejecutar("identidades.sh")


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
