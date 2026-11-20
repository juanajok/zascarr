"""OPS4 FR-01: el auxiliar actual no admite peticiones de actualización.

Pruebas aisladas de procesar, no de la UI, systemd ni de una instalación real.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from deploy.ops import zascarr_ops as ops

CLAVE = bytes(range(32))
AHORA = 1_800_000_000
ID = "a" * 32


def firmar(texto: str) -> str:
    return hmac.new(CLAVE, texto.encode(), hashlib.sha256).hexdigest()


def linea(cuerpo: dict) -> bytes:
    return json.dumps(cuerpo, separators=(",", ":")).encode() + b"\n"


class LanzadorProhibido:
    """Falla incluso si se consulta systemd, no solo si se inicia una unidad."""

    def __getattr__(self, nombre: str):
        pytest.fail(f"El gate llamó al lanzador: {nombre}")


@pytest.fixture
def estado(tmp_path: Path):
    run = tmp_path / "run"
    status = tmp_path / "status"
    run.mkdir()
    status.mkdir()
    estado = ops.EstadoOps(str(run), str(status))
    Path(estado.ruta_ops_status).write_bytes(b"estado anterior\n")
    return estado


def ejecutar(cuerpo: dict, estado, monkeypatch):
    def prohibido(*args, **kwargs):
        pytest.fail("No debe lanzarse ningún subproceso")

    monkeypatch.setattr(ops.subprocess, "run", prohibido)
    respuesta = ops.procesar(linea(cuerpo), AHORA, CLAVE, estado, LanzadorProhibido(), copias=[])
    assert respuesta.resultado == "rechazada"
    assert Path(estado.ruta_ops_status).read_bytes() == b"estado anterior\n"
    return respuesta


def test_v1_actualizar_con_hmac_correcto_no_es_accion_disponible(estado, monkeypatch):
    cuerpo = {"v": 1, "id": ID, "accion": "actualizar", "creada": AHORA,
              "firma": firmar(f"1|{ID}|actualizar|{AHORA}")}
    assert ops.parsear(linea(cuerpo)) == cuerpo
    respuesta = ejecutar(cuerpo, estado, monkeypatch)
    assert respuesta.codigo == "accion_no_disponible"
    assert respuesta.id == ID
    assert "actualizar" not in ops.UNIDADES


def test_v2_actualizar_con_hmac_del_protocolo_v2_no_pasa_esquema(estado, monkeypatch):
    copia, prueba = "backup-20260101_120000", "secreta"
    cuerpo = {"v": 2, "id": ID, "accion": "actualizar", "copia": copia,
              "prueba": prueba, "creada": AHORA,
              "firma": firmar(f"2|{ID}|restaurar|{copia}|{AHORA}|{prueba}")}
    assert ops.firma_de(CLAVE, 2, ID, "actualizar", AHORA, copia, prueba) == cuerpo["firma"]
    assert ops.parsear(linea(cuerpo)) is None
    assert ejecutar(cuerpo, estado, monkeypatch).codigo == "esquema_invalido"


@pytest.mark.parametrize("version", [3, 4])
def test_version_no_implementada_con_campos_de_actualizacion_se_rechaza(
    version, estado, monkeypatch
):
    # No existe una canonicalización v3: esta firma no pretende acreditar un HMAC v3 válido.
    cuerpo = {"v": version, "id": ID, "accion": "actualizar", "sha": "b" * 40,
              "prueba": "secreta", "creada": AHORA, "firma": "f" * 64}
    assert ops.parsear(linea(cuerpo)) is None
    assert ejecutar(cuerpo, estado, monkeypatch).codigo == "esquema_invalido"
