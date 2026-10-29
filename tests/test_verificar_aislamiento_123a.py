"""Pruebas de `scripts/verificar_aislamiento_123a.sh` (123a-i, caso 00).

La compuerta compara la configuración renderizada de la copia con la de
producción. Se ejecuta con un `docker` falso que devuelve dos JSON: uno para
`-f` de producción y otro para `-f` de la copia. No toca Docker real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "verificar_aislamiento_123a.sh"

DOCKER_FALSO = r"""#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "$STUB_LOG"
cmd="$*"
if [[ "$cmd" == *" config --format json"* ]]; then
    if [[ "$cmd" == *"$FAKE_PROD_COMPOSE"* ]]; then
        cat "$FAKE_PROD_JSON"
    else
        cat "$FAKE_COPY_JSON"
    fi
    exit 0
fi
if [[ "$cmd" == *" ps -q"* ]]; then
    printf '%s\n' "${FAKE_IDS:-}"
    exit 0
fi
exit 0
"""


def _prod() -> dict:
    return {
        "name": "zascarr",
        "services": {
            "postgres": {
                "container_name": "zascarr-db",
                "ports": [{"published": "5432", "protocol": "tcp"}],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/var/lib/zascarr/postgres",
                        "target": "/var/lib/postgresql/data",
                    }
                ],
            },
            "zascarr": {
                "container_name": "zascarr-orquestador",
                "ports": [{"published": "8000", "protocol": "tcp"}],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/media/library",
                        "target": "/media/library",
                    }
                ],
            },
        },
        "networks": {"zascarr-internal": {"name": "zascarr_zascarr-internal"}},
    }


def _copia() -> dict:
    return {
        "name": "zascarr-123a",
        "services": {
            "postgres": {
                "container_name": "zascarr-123a-db",
                "ports": [{"published": "15432", "protocol": "tcp"}],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/srv/123a/data/postgres",
                        "target": "/var/lib/postgresql/data",
                    }
                ],
            },
            "zascarr": {
                "container_name": "zascarr-123a-orquestador",
                "ports": [{"published": "18000", "protocol": "tcp"}],
                "volumes": [
                    {
                        "type": "bind",
                        "source": "/srv/123a/library",
                        "target": "/media/library",
                    }
                ],
            },
        },
        "networks": {"zascarr-internal": {"name": "zascarr-123a_zascarr-internal"}},
    }


def _preparar(tmp_path: Path) -> dict:
    prod = tmp_path / "prod.yml"
    prod.write_text("name: zascarr\n", encoding="utf-8")
    copia = tmp_path / "copia.yml"
    copia.write_text("name: zascarr-123a\n", encoding="utf-8")
    env_prod = tmp_path / ".env.prod"
    env_prod.write_text("DB_PASSWORD=x\n", encoding="utf-8")
    env_copia = tmp_path / ".env.copia"
    env_copia.write_text("DB_PASSWORD=y\n", encoding="utf-8")

    prod_json = tmp_path / "prod.json"
    copia_json = tmp_path / "copia.json"
    prod_json.write_text(json.dumps(_prod()), encoding="utf-8")
    copia_json.write_text(json.dumps(_copia()), encoding="utf-8")

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text(DOCKER_FALSO, encoding="utf-8")
    docker.chmod(0o755)
    stub = tmp_path / "docker.log"
    stub.write_text("", encoding="utf-8")

    return {
        "prod": prod,
        "copia": copia,
        "env_prod": env_prod,
        "env_copia": env_copia,
        "prod_json": prod_json,
        "copia_json": copia_json,
        "bin": bin_,
        "stub": stub,
    }


def _ejecutar(
    ctx: dict,
    *,
    extra: list[str] | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{ctx['bin']}:{env['PATH']}",
            "FAKE_PROD_COMPOSE": str(ctx["prod"]),
            "FAKE_PROD_JSON": str(ctx["prod_json"]),
            "FAKE_COPY_JSON": str(ctx["copia_json"]),
            "STUB_LOG": str(ctx["stub"]),
        }
    )
    if extra_env:
        env.update(extra_env)
    args = [
        "--entorno",
        str(Path("/srv/123a")),
        "--compose",
        str(ctx["copia"]),
        "--env",
        str(ctx["env_copia"]),
        "--prod-compose",
        str(ctx["prod"]),
        "--prod-env",
        str(ctx["env_prod"]),
    ]
    if extra:
        args += extra
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _mutar(ctx: dict, fn) -> None:
    datos = json.loads(ctx["copia_json"].read_text(encoding="utf-8"))
    fn(datos)
    ctx["copia_json"].write_text(json.dumps(datos), encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")
class TestVerificarAislamiento:
    def test_cero_colisiones(self, tmp_path):
        r = _ejecutar(_preparar(tmp_path))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "0 colisiones" in (r.stdout + r.stderr).lower()

    def test_colision_de_proyecto(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(ctx, lambda d: d.update({"name": "zascarr"}))
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "proyecto" in r.stderr.lower()

    def test_colision_de_contenedor(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(ctx, lambda d: d["services"]["postgres"].update({"container_name": "zascarr-db"}))
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "contenedor" in r.stderr.lower()

    def test_colision_de_puerto(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(
            ctx,
            lambda d: d["services"]["postgres"].update(
                {"ports": [{"published": "5432", "protocol": "tcp"}]}
            ),
        )
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "puerto" in r.stderr.lower()

    def test_colision_de_red(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(
            ctx,
            lambda d: d["networks"]["zascarr-internal"].update(
                {"name": "zascarr_zascarr-internal"}
            ),
        )
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "red" in r.stderr.lower()

    def test_bind_fuera_del_entorno(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(
            ctx,
            lambda d: d["services"]["postgres"]["volumes"][0].update(
                {"source": "/var/lib/zascarr/postgres"}
            ),
        )
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "bind" in r.stderr.lower() or "entorno" in r.stderr.lower()

    def test_bind_que_coincide_con_produccion(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(
            ctx,
            lambda d: d["services"]["zascarr"]["volumes"][0].update({"source": "/media/library"}),
        )
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "bind" in r.stderr.lower() or "producción" in r.stderr.lower()

    def test_un_override_inesperado_que_reintroduce_produccion_falla(self, tmp_path):
        ctx = _preparar(tmp_path)
        _mutar(
            ctx,
            lambda d: d["services"]["zascarr"].update({"container_name": "zascarr-orquestador"}),
        )
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "contenedor" in r.stderr.lower()

    def test_ids_antes_y_despues_iguales(self, tmp_path):
        ctx = _preparar(tmp_path)
        ids = tmp_path / "ids.txt"
        r = _ejecutar(ctx, extra=["--ids-antes", str(ids)], extra_env={"FAKE_IDS": "aaa\nbbb"})
        assert r.returncode == 0, r.stdout + r.stderr
        assert ids.read_text(encoding="utf-8").split() == ["aaa", "bbb"]
        r = _ejecutar(ctx, extra=["--ids-despues", str(ids)], extra_env={"FAKE_IDS": "bbb\naaa"})
        assert r.returncode == 0, r.stdout + r.stderr

    def test_ids_cambiados_falla(self, tmp_path):
        ctx = _preparar(tmp_path)
        ids = tmp_path / "ids.txt"
        assert (
            _ejecutar(
                ctx, extra=["--ids-antes", str(ids)], extra_env={"FAKE_IDS": "aaa\nbbb"}
            ).returncode
            == 0
        )
        r = _ejecutar(ctx, extra=["--ids-despues", str(ids)], extra_env={"FAKE_IDS": "aaa\nccc"})
        assert r.returncode != 0
        assert "producción" in r.stderr.lower() or "cambi" in r.stderr.lower()

    def test_ids_despues_sin_fichero_falla(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra=["--ids-despues", str(tmp_path / "no-existe")])
        assert r.returncode != 0
