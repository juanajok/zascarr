"""Pruebas del escritor atómico; no hay ejecución ni autorización."""
from __future__ import annotations

import json

import pytest

from deploy.ops.escritor_estado_actualizar_ops4 import (
    MAX_BYTES,
    ResultadoEscritura,
    escribir_estado,
)

ESTADO = {"schema": 1, "estado": "aceptada", "id": "a" * 32}


def test_publica_json_canonico(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, ESTADO) is ResultadoEscritura.OK
    assert json.loads(destino.read_text(encoding="utf-8")) == ESTADO
    assert destino.read_text(encoding="utf-8").startswith('{"estado":')


def test_original_permanece_si_falla_fsync_del_archivo(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    destino.write_text('{"antiguo":true}\n', encoding="utf-8")

    def fsync_falla(_fd: int) -> None:
        raise OSError("fsync")

    assert escribir_estado(destino, ESTADO, fsync=fsync_falla) is ResultadoEscritura.INCIERTO
    assert destino.read_text(encoding="utf-8") == '{"antiguo":true}\n'
    assert not list(tmp_path.glob(".estado.json.tmp-*"))


def test_original_permanece_si_falla_rename(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    destino.write_text('{"antiguo":true}\n', encoding="utf-8")

    def replace_falla(_a: str, _b: str) -> None:
        raise OSError("rename")

    assert escribir_estado(destino, ESTADO, replace=replace_falla) is ResultadoEscritura.INCIERTO
    assert destino.read_text(encoding="utf-8") == '{"antiguo":true}\n'
    assert not list(tmp_path.glob(".estado.json.tmp-*"))


def test_fallo_fsync_del_directorio_es_incierto(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    llamadas = []

    def fsync_dos_veces(fd: int) -> None:
        llamadas.append(fd)
        if len(llamadas) == 2:
            raise OSError("directorio")

    assert escribir_estado(destino, ESTADO, fsync=fsync_dos_veces) is ResultadoEscritura.INCIERTO
    assert destino.exists()


@pytest.mark.parametrize("datos", [None, [], {"x": object()}, {"x": float("nan")}])
def test_datos_invalidos_no_publican(tmp_path, datos) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, datos) is ResultadoEscritura.INVALIDO
    assert not destino.exists()


def test_tamano_excesivo(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, {"x": "a" * MAX_BYTES}) is ResultadoEscritura.INVALIDO
    assert not destino.exists()


def test_directorio_inexistente_falla_cerrado(tmp_path) -> None:
    assert escribir_estado(tmp_path / "no" / "estado.json", ESTADO) is ResultadoEscritura.INVALIDO
