"""B2b: la entrada de la unidad toma el cerrojo antes de efectos y reserva."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoEscritura,
    escribir_estado,
    estado_inicial,
)

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "deploy" / "ops" / "zascarr_actualizar_entrada.py"
ID = "a" * 32


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "update.sh").write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "source \"$(dirname \"$0\")/_cerrojo.sh\"\n"
        "tomar_cerrojo_operaciones\n"
        "echo \"fd9=$(test -e /proc/self/fd/9 && echo si || echo no)\" > \"$MARCA\"\n"
        "flock -n 9 && echo \"flock9=si\" >> \"$MARCA\"\n"
        "echo \"lock_fds=$(ls -l /proc/self/fd | grep -c ops.lock)\" >> \"$MARCA\"\n"
        "echo \"rama=$2\" >> \"$MARCA\"\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "update.sh").chmod(0o755)
    (repo / "scripts" / "_cerrojo.sh").write_text(
        (RAIZ / "scripts" / "_cerrojo.sh").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "b2@test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "B2"], cwd=repo, check=True)
    (repo / "x").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "x"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def _entorno(tmp_path: Path, repo: Path, *, inicio: int | None = None):
    ops = tmp_path / "ops"
    ops.mkdir()
    ops4 = tmp_path / "ops4"
    (ops4 / "intentos").mkdir(parents=True, mode=0o700)
    (ops4 / "intentos").chmod(0o700)
    estado = ops / "actualizar-status.json"
    assert escribir_estado(
        estado, estado_inicial(ID, int(time.time()) if inicio is None else inicio),
    ) is ResultadoEscritura.OK
    entorno = os.environ.copy()
    entorno.update({
        "ZASCARR_REPO": str(repo),
        "ZASCARR_OPS_DIR": str(ops),
        "ZASCARR_OPS4_DIR": str(ops4),
        "INVOCATION_ID": "b" * 32,
        "ZASCARR_PRUEBAS": "1",
        "OPS_LOCK_FILE": str(tmp_path / "ops.lock"),
        "MARCA": str(tmp_path / "marca"),
    })
    return estado, entorno


def _ejecutar(entorno: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRADA)], env=entorno,
        capture_output=True, text=True, timeout=60,
    )


def test_toma_cerrojo_y_reserva_antes_de_update(tmp_path) -> None:
    repo = _repo(tmp_path)
    estado, entorno = _entorno(tmp_path, repo)
    r = _ejecutar(entorno)
    assert r.returncode == 0, r.stderr
    marca = (tmp_path / "marca").read_text(encoding="utf-8")
    assert "fd9=si" in marca
    assert "flock9=si" in marca
    assert "rama=main" in marca
    assert "lock_fds=1" in marca
    assert (tmp_path / "ops4" / "intentos" / ("inv-" + "b" * 32)).read_text() == ID + "\n"
    datos = json.loads(estado.read_text(encoding="utf-8"))
    assert (datos["estado"], datos["fase"]) == ("en_curso", "reservada")
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True,
    ).strip()
    assert datos["head0"] == head


def test_cerrojo_ocupado_sale_75_sin_efectos(tmp_path) -> None:
    repo = _repo(tmp_path)
    estado, entorno = _entorno(tmp_path, repo)
    antes = estado.read_bytes()
    cerrojo = entorno["OPS_LOCK_FILE"]
    poseedor = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl,os,sys,time;"
         "fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600);"
         "fcntl.flock(fd,fcntl.LOCK_EX);print('ok',flush=True);time.sleep(10)",
         cerrojo],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert poseedor.stdout is not None
        assert poseedor.stdout.readline().strip() == "ok"
        r = _ejecutar(entorno)
        assert r.returncode == 75, r.stderr
        assert estado.read_bytes() == antes
        assert not (tmp_path / "marca").exists()
    finally:
        poseedor.kill()
        poseedor.wait()


def test_reserva_caducada_sale_76_sin_efectos(tmp_path) -> None:
    repo = _repo(tmp_path)
    estado, entorno = _entorno(tmp_path, repo, inicio=int(time.time()) - 301)
    antes = estado.read_bytes()
    r = _ejecutar(entorno)
    assert r.returncode == 76, r.stderr
    assert estado.read_bytes() == antes
    assert not (tmp_path / "marca").exists()


def test_segundo_update_sh_sale_75(tmp_path) -> None:
    repo = _repo(tmp_path)
    lento = repo / "scripts" / "lento.sh"
    lento.write_text(
        "#!/bin/bash\n"
        "set -eu\n"
        "source \"$(dirname \"$0\")/_cerrojo.sh\"\n"
        "tomar_cerrojo_operaciones || exit $?\n"
        "echo ok > \"$MARCA\"\n"
        "sleep 2\n",
        encoding="utf-8",
    )
    lento.chmod(0o755)
    entorno = os.environ.copy()
    entorno.update({
        "ZASCARR_PRUEBAS": "1",
        "OPS_LOCK_FILE": str(tmp_path / "ops.lock"),
        "MARCA": str(tmp_path / "marca"),
    })
    primero = subprocess.Popen(
        ["bash", str(lento)], env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if (tmp_path / "marca").exists():
                break
            time.sleep(0.05)
        segundo = subprocess.run(
            ["bash", str(lento)], env=entorno,
            capture_output=True, text=True, timeout=10,
        )
        assert segundo.returncode == 75, segundo.stderr
    finally:
        primero.wait(timeout=10)


def test_sin_estado_sale_76(tmp_path) -> None:
    repo = _repo(tmp_path)
    ops = tmp_path / "ops"
    ops.mkdir()
    entorno = os.environ.copy()
    entorno.update({
        "ZASCARR_REPO": str(repo), "ZASCARR_OPS_DIR": str(ops),
        "ZASCARR_PRUEBAS": "1", "OPS_LOCK_FILE": str(tmp_path / "ops.lock"),
        "MARCA": str(tmp_path / "marca"),
    })
    assert _ejecutar(entorno).returncode == 76
    assert stat.S_IMODE((tmp_path / "ops.lock").stat().st_mode) == 0o600
