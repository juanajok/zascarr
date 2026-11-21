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


@pytest.mark.parametrize("linea", [
    b'{"v":1,"id":"' + b"a" * 32 + b'","accion":"actualizar","creada":1800000000,'
    b'"firma":"' + b"f" * 64 + b'","firma":"' + b"f" * 64 + b'"}\n',
    b'{"v":1,"id":"' + b"a" * 32 + b'","accion":"actualizar","creada":1800000000,'
    b'"firma":"' + b"f" * 64 + b'","relleno":"' + b"x" * 600 + b'"}\n',
    b'{"v":true,"id":"' + b"a" * 32 + b'","accion":"actualizar","creada":1800000000,'
    b'"firma":"' + b"f" * 64 + b'"}\n',
])
def test_esquema_ambiguo_o_grande_no_llega_al_lanzador(linea, estado, monkeypatch):
    from deploy.ops import zascarr_ops as ops
    monkeypatch.setattr(ops.subprocess, "run", lambda *a, **k: pytest.fail("subproceso"))
    respuesta = ops.procesar(linea, AHORA, CLAVE, estado, LanzadorProhibido(), copias=[])
    assert respuesta.resultado == "rechazada"
    assert respuesta.codigo == "esquema_invalido"


def test_firma_incorrecta_de_actualizar_no_dispara_nada(estado, monkeypatch):
    from deploy.ops import zascarr_ops as ops
    monkeypatch.setattr(ops.subprocess, "run", lambda *a, **k: pytest.fail("subproceso"))
    cuerpo = {"v": 1, "id": ID, "accion": "actualizar", "creada": AHORA,
              "firma": "0" * 64}
    respuesta = ops.procesar(linea(cuerpo), AHORA, CLAVE, estado, LanzadorProhibido(), copias=[])
    assert respuesta.resultado == "rechazada"
    assert respuesta.codigo == "firma_invalida"


def test_bytes_aleatorios_no_escapan_del_parser() -> None:
    import random

    from deploy.ops import zascarr_ops as ops
    rng = random.Random(445)
    for _ in range(500):
        datos = rng.randbytes(rng.randrange(0, 600)) + b"\n"
        assert ops.parsear(datos) is None or isinstance(ops.parsear(datos), dict)
