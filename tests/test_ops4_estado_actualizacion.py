"""Regresiones del lector informativo, sin escritor ni operación real."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from zascarr.services.estado_actualizacion import (
    MAX_BYTES,
    SIN_NOTICIAS_SEGUNDOS,
    EstadoActualizacion,
    leer_estado_actualizacion,
)

ID = "a" * 32
NOW = 2_000_000


def record(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": 1, "id": ID, "estado": "aceptada",
        "inicio_epoch": NOW - 10, "actualizado_epoch": NOW - 1,
    }
    value.update(changes)
    return value


def read(path: Path, **kwargs: object) -> EstadoActualizacion:
    return leer_estado_actualizacion(path, id_esperado=ID, ahora_epoch=NOW, **kwargs)


@pytest.mark.parametrize("state", list(EstadoActualizacion))
def test_estados_cerrados(tmp_path: Path, state: EstadoActualizacion) -> None:
    path = tmp_path / "estado.json"
    path.write_text(json.dumps(record(estado=state.value)), encoding="utf-8")
    assert read(path) is state


@pytest.mark.parametrize("changes", [
    {"schema": True}, {"schema": 1.0}, {"schema": 2}, {"id": "b" * 32},
    {"estado": "desconocido"}, {"estado": None}, {"estado": ["hecha"]},
    {"inicio_epoch": True}, {"actualizado_epoch": 1.0},
    {"inicio_epoch": -1}, {"inicio_epoch": NOW},
    {"actualizado_epoch": NOW + 1}, {"extra": "secreto /ruta"},
])
def test_datos_invalidos_fallan_cerrado(tmp_path: Path, changes: dict[str, object]) -> None:
    path = tmp_path / "estado.json"
    path.write_text(json.dumps(record(**changes)), encoding="utf-8")
    assert read(path) is EstadoActualizacion.INCIERTA


@pytest.mark.parametrize("payload", [
    b'{"schema":1,"schema":1}', b'[]', b'null', b'\xff', b'{',
    b'{"schema":NaN}', b"x" * (MAX_BYTES + 1),
])
def test_json_invalido_duplicado_o_grande(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "estado.json"
    path.write_bytes(payload)
    assert read(path) is EstadoActualizacion.INCIERTA


def test_id_distinto_y_reloj_invalido(tmp_path: Path) -> None:
    path = tmp_path / "estado.json"
    path.write_text(json.dumps(record()), encoding="utf-8")
    assert leer_estado_actualizacion(
        path, id_esperado="b" * 32, ahora_epoch=NOW
    ) is EstadoActualizacion.INCIERTA
    assert leer_estado_actualizacion(
        path, id_esperado="secreto", ahora_epoch=NOW
    ) is EstadoActualizacion.INCIERTA
    assert leer_estado_actualizacion(
        path, id_esperado=ID, ahora_epoch=True
    ) is EstadoActualizacion.INCIERTA


@pytest.mark.parametrize("state", ["aceptada", "en_curso"])
def test_sin_noticias_es_incierto_no_fallido(tmp_path: Path, state: str) -> None:
    path = tmp_path / "estado.json"
    path.write_text(
        json.dumps(record(
            estado=state, inicio_epoch=NOW - SIN_NOTICIAS_SEGUNDOS,
            actualizado_epoch=NOW - SIN_NOTICIAS_SEGUNDOS,
        )),
        encoding="utf-8",
    )
    assert read(path) is EstadoActualizacion.INCIERTA
    path.write_text(
        json.dumps(record(
            estado=state, inicio_epoch=NOW - SIN_NOTICIAS_SEGUNDOS + 1,
            actualizado_epoch=NOW - SIN_NOTICIAS_SEGUNDOS + 1,
        )),
        encoding="utf-8",
    )
    assert read(path).value == state


def test_no_sigue_enlaces_ni_abre_fifo_bloqueante(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.write_text(json.dumps(record()), encoding="utf-8")
    link = tmp_path / "enlace"
    link.symlink_to(target)
    assert read(link) is EstadoActualizacion.INCIERTA
    folder = tmp_path / "dir"
    folder.mkdir()
    (folder / "estado").write_text(json.dumps(record()), encoding="utf-8")
    (tmp_path / "dirlink").symlink_to(folder, target_is_directory=True)
    assert read(tmp_path / "dirlink" / "estado") is EstadoActualizacion.INCIERTA
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert read(fifo) is EstadoActualizacion.INCIERTA
    assert read(folder) is EstadoActualizacion.INCIERTA
    assert read(tmp_path / "ausente") is EstadoActualizacion.INCIERTA


def test_lectura_de_fifo_termina_acotada(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo-acotado"
    os.mkfifo(fifo)
    codigo = (
        "import sys\n"
        "from pathlib import Path\n"
        "from zascarr.services.estado_actualizacion import "
        "EstadoActualizacion, leer_estado_actualizacion\n"
        "resultado = leer_estado_actualizacion("
        "Path(sys.argv[1]), id_esperado='a'*32, ahora_epoch=2000000)\n"
        "assert resultado is EstadoActualizacion.INCIERTA\n"
    )
    completado = subprocess.run(
        [sys.executable, "-c", codigo, str(fifo)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": ".:src"},
        capture_output=True,
        timeout=3,
        check=False,
    )
    assert completado.returncode == 0, completado.stderr.decode("utf-8", "replace")


def test_no_revela_secretos_ni_rutas(tmp_path: Path) -> None:
    path = tmp_path / "clave-secreta"
    path.write_text(json.dumps(record(estado="/ruta/clave-secreta")), encoding="utf-8")
    result = read(path)
    assert result is EstadoActualizacion.INCIERTA
    assert "secreta" not in str(result)
