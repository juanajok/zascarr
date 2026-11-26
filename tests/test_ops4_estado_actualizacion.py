"""Regresiones del lector informativo, sin escritor ni operación real."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoEscritura,
    escribir_estado,
)
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


def test_lee_el_estado_0640_que_escribe_el_host(tmp_path: Path) -> None:
    """H-5: el escritor crea `0640`; la app (PUID:PGID, montaje `ro`) lo lee."""
    path = tmp_path / "actualizar-status.json"
    assert escribir_estado(path, record(estado="hecha")) is ResultadoEscritura.OK
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert read(path) is EstadoActualizacion.HECHA


# ── Último intento v2 y reconciliación (B1) ─────────────────────────────────


def _escribir_v2(tmp_path, datos):
    from deploy.ops.escritor_estado_actualizar_ops4 import (
        ResultadoEscritura,
        escribir_estado,
    )
    ruta = tmp_path / "actualizar-status.json"
    assert escribir_estado(ruta, datos) is ResultadoEscritura.OK
    return ruta


def _inicial_v2():
    from deploy.ops.escritor_estado_actualizar_ops4 import estado_inicial
    return estado_inicial("b" * 32, 1_700_000_000)


def test_ultimo_intento_v2_sin_id_y_terminal(tmp_path) -> None:
    from deploy.ops.escritor_estado_actualizar_ops4 import CODIGO_EXITO, calcular_transicion
    from zascarr.services.estado_actualizacion import (
        EstadoActualizacion,
        leer_ultimo_intento,
    )

    ini = _inicial_v2()
    ruta = _escribir_v2(tmp_path, ini)
    intento = leer_ultimo_intento(ruta, ahora_epoch=1_700_000_001)
    assert intento is not None
    assert intento.estado is EstadoActualizacion.ACEPTADA
    assert intento.fase == "aceptada" and intento.sin_noticias is False
    terminal = calcular_transicion(
        ini, "hecha", ahora=1_700_000_100, fase="fin", codigo=CODIGO_EXITO,
    )
    assert terminal is not None
    assert _escribir_v2(tmp_path, terminal) is not None
    intento = leer_ultimo_intento(ruta, ahora_epoch=1_700_100_000)
    assert intento is not None and intento.estado is EstadoActualizacion.HECHA
    assert (intento.resultado, intento.codigo, intento.sin_noticias) == (
        "hecha", CODIGO_EXITO, False,
    )


def test_ultimo_intento_reconcilia_activo_a_los_7200(tmp_path) -> None:
    from zascarr.services.estado_actualizacion import (
        EstadoActualizacion,
        interpretar_ultimo_intento,
    )
    ini = _inicial_v2()
    fresco = interpretar_ultimo_intento(ini, ahora_epoch=1_700_000_000 + 7199)
    assert fresco is not None and fresco.estado is EstadoActualizacion.ACEPTADA
    justo = interpretar_ultimo_intento(ini, ahora_epoch=1_700_000_000 + 7200)
    assert justo is not None
    assert justo.estado is EstadoActualizacion.INCIERTA and justo.sin_noticias is True


def test_ultimo_intento_v1_compatible(tmp_path) -> None:
    from zascarr.services.estado_actualizacion import (
        EstadoActualizacion,
        leer_ultimo_intento,
    )
    v1 = {"schema": 1, "id": "c" * 32, "estado": "en_curso",
          "inicio_epoch": 1_700_000_000, "actualizado_epoch": 1_700_000_000}
    with open(tmp_path / "v1.json", "w", encoding="utf-8") as salida:
        json.dump(v1, salida)
    os.chmod(tmp_path / "v1.json", 0o640)
    intento = leer_ultimo_intento(tmp_path / "v1.json", ahora_epoch=1_700_000_001)
    assert intento is not None
    assert intento.estado is EstadoActualizacion.EN_CURSO
    assert intento.fase == "aceptada" and intento.head0 is None


def test_ultimo_intento_rechaza_invalido_y_futuro(tmp_path) -> None:
    from zascarr.services.estado_actualizacion import (
        interpretar_ultimo_intento,
        leer_ultimo_intento,
    )
    ini = _inicial_v2()
    assert interpretar_ultimo_intento({**ini, "extra": 1}, ahora_epoch=1_700_000_001) is None
    assert interpretar_ultimo_intento({**ini, "fase": "fin"}, ahora_epoch=1_700_000_001) is None
    assert interpretar_ultimo_intento({**ini, "head0": "corta"}, ahora_epoch=1_700_000_001) is None
    assert interpretar_ultimo_intento(ini, ahora_epoch=1_699_999_999) is None
    assert leer_ultimo_intento(tmp_path / "no-existe.json", ahora_epoch=1_700_000_001) is None
