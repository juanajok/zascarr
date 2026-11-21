"""Fase final de estado desde la unidad; no ejecuta update.sh."""
from __future__ import annotations

import json
import time

import pytest

from deploy.ops import estado_actualizar_ops4 as estado
from deploy.ops.escritor_estado_actualizar_ops4 import escribir_estado

ID = "a" * 32


def _estado(tmp_path, estado_inicial="en_curso"):
    ahora = int(time.time())
    ruta = tmp_path / "actualizar-status.json"
    assert escribir_estado(ruta, {
        "schema": 1, "id": ID, "estado": estado_inicial,
        "inicio_epoch": ahora - 5, "actualizado_epoch": ahora - 5,
    }).value == "ok"
    return ruta


def test_marca_hecha_conservando_id_e_inicio(tmp_path) -> None:
    ruta = _estado(tmp_path)
    assert estado.main(["--ruta", str(ruta), "--resultado", "hecha"]) == 0
    datos = json.loads(ruta.read_text())
    assert datos["estado"] == "hecha"
    assert datos["id"] == ID
    assert datos["inicio_epoch"] <= datos["actualizado_epoch"]


def test_fallida_por_timeout(tmp_path) -> None:
    ruta = _estado(tmp_path)
    assert estado.main(["--ruta", str(ruta), "--resultado", "fallida"]) == 0
    assert json.loads(ruta.read_text())["estado"] == "fallida"


@pytest.mark.parametrize("resultado", ["", "ok", "en_curso", "hecha\n"])
def test_resultado_cerrado(tmp_path, resultado) -> None:
    ruta = _estado(tmp_path)
    assert estado.main(["--ruta", str(ruta), "--resultado", resultado]) == 2


def test_sin_estado_no_inventa_ni_falla(tmp_path) -> None:
    assert estado.main([
        "--ruta", str(tmp_path / "no-existe.json"), "--resultado", "hecha",
    ]) == 0


def test_json_ajeno_no_se_toca(tmp_path) -> None:
    ruta = tmp_path / "ajeno.json"
    ruta.write_text('{"otra":"cosa"}\n', encoding="utf-8")
    assert estado.main(["--ruta", str(ruta), "--resultado", "hecha"]) == 0
    assert json.loads(ruta.read_text()) == {"otra": "cosa"}
