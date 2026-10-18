"""Consumidores del `.env` cuando está cerrado (modo 600, `root:root`).

Con el `.env` cerrado, quien lo lee tiene que ser root. Medido con Docker
Compose v5.5.1: sin permiso de lectura falla **en cerrado** («permission denied»,
en inglés, sin decir qué hacer) y **no** arranca con la contraseña por defecto
del compose. Eso es seguro pero hostil para el coleccionista, y en un script que
lee el `.env` por su cuenta (`uninstall.sh`) el fallo sería **silencioso**: lo
leería como «ausente» y trabajaría con valores por defecto. Estas pruebas fijan
que cada consumidor:

- comprueba la lectura **antes** de tocar nada;
- se detiene con una frase en español que dice qué hacer (`sudo`);
- no llega a llamar a `docker compose` con ese fichero.

Se ejecutan como usuario normal sobre un árbol sintético; con root el permiso 000
no se aplica, así que se saltan.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.skipif(
        os.name != "posix" or shutil.which("bash") is None, reason="requiere bash en Linux"),
    pytest.mark.skipif(
        hasattr(os, "geteuid") and os.geteuid() == 0,
        reason="root lee cualquier fichero: la denegación no se puede simular"),
]

REPO = Path(__file__).resolve().parents[1]

DOCKER_STUB = r"""#!/usr/bin/env bash
echo "docker $*" >> "${STUB_REGISTRO:?}"
case "$*" in
    "compose version"*) echo "Docker Compose version v2"; exit 0 ;;
    "info"*) exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def arbol(tmp_path: Path) -> dict[str, Path]:
    """Repo sintético: los scripts reales copiados junto a un `.env` ilegible."""
    raiz = tmp_path / "raiz"
    repo = raiz / "zascarr"
    (repo / "scripts").mkdir(parents=True)
    for f in ("docker-compose.yml", "scripts/_comun.sh", "scripts/_rutas.sh",
              "scripts/etiquetar.sh", "scripts/backup.sh", "scripts/uninstall.sh"):
        origen = REPO / f
        if origen.exists():
            shutil.copy(origen, repo / f)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    stub = bin_ / "docker"
    stub.write_text(DOCKER_STUB)
    stub.chmod(0o755)
    env = raiz / ".env"
    env.write_text("DB_PASSWORD=secreto_de_prueba\n")
    env.chmod(0o000)
    yield {"raiz": raiz, "repo": repo, "bin": bin_, "env": env,
           "registro": tmp_path / "docker.log", "backups": tmp_path / "backups"}
    if env.exists():
        env.chmod(0o600)


def _ejecutar(arbol, script: str, *args: str):
    entorno = {
        **os.environ,
        "PATH": f"{arbol['bin']}:{os.environ['PATH']}",
        "STUB_REGISTRO": str(arbol["registro"]),
        "ZASCARR_ROOT": str(arbol["raiz"]),
        "ZASCARR_REPO": str(arbol["repo"]),
        "BACKUP_DIR": str(arbol["backups"]),
    }
    entorno.pop("ENV_FILE", None)
    return subprocess.run(
        ["bash", str(arbol["repo"] / "scripts" / script), *args],
        capture_output=True, text=True, timeout=60, check=False, env=entorno,
        input="", cwd=str(arbol["repo"]),
    )


def _llamadas(arbol) -> str:
    return arbol["registro"].read_text() if arbol["registro"].exists() else ""


def _dice_sudo(r) -> bool:
    texto = (r.stdout + r.stderr)
    return "sudo" in texto and str(Path(r.args[1]).parent.parent.parent / ".env") in texto


class TestComprobarEnvLegible:

    def _funcion(self, arbol, cuerpo: str):
        """`_comun.sh` calcula su ubicación desde el script que lo carga
        (`BASH_SOURCE[1]`), así que se prueba desde un script de verdad."""
        llamador = arbol["repo"] / "scripts" / "_llamador.sh"
        llamador.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"\n'
            f"{cuerpo}\n")
        return subprocess.run(
            ["bash", str(llamador)], capture_output=True, text=True, timeout=30,
            check=False, cwd=str(arbol["repo"] / "scripts"),
            env={**os.environ, "ZASCARR_ROOT": str(arbol["raiz"]),
                 "PATH": f"{arbol['bin']}:{os.environ['PATH']}",
                 "STUB_REGISTRO": str(arbol["registro"])},
        )

    def test_ilegible_dice_que_hace_falta_sudo(self, arbol):
        r = self._funcion(arbol, "comprobar_env_legible")
        assert r.returncode == 1
        assert "sudo" in r.stderr and str(arbol["env"]) in r.stderr
        assert "contraseña" in r.stderr.lower()

    def test_no_imprime_el_contenido(self, arbol):
        r = self._funcion(arbol, "comprobar_env_legible")
        assert "secreto_de_prueba" not in r.stdout + r.stderr

    def test_legible_pasa(self, arbol):
        arbol["env"].chmod(0o600)
        assert self._funcion(arbol, "comprobar_env_legible").returncode == 0

    def test_ausente_no_es_cosa_suya(self, arbol):
        """Ausente tiene su propio mensaje en cada script (uninstall sigue sin él)."""
        arbol["env"].chmod(0o600)
        arbol["env"].unlink()
        assert self._funcion(arbol, "comprobar_env_legible").returncode == 0


class TestScriptsSeDetienenAntesDeTocarNada:

    def test_etiquetar(self, arbol):
        r = _ejecutar(arbol, "etiquetar.sh")
        assert r.returncode == 1
        assert _dice_sudo(r), r.stderr
        assert "compose" not in _llamadas(arbol).replace("compose version", "")

    def test_backup(self, arbol):
        r = _ejecutar(arbol, "backup.sh")
        assert r.returncode == 1
        assert _dice_sudo(r), r.stderr
        assert "run" not in _llamadas(arbol) and "exec" not in _llamadas(arbol)
        assert not arbol["backups"].exists() or not any(arbol["backups"].iterdir())

    def test_uninstall_no_trabaja_con_valores_por_defecto(self, arbol):
        """Peor caso: lo leería como «ausente» y calcularía rutas con los valores
        por defecto del compose. Tiene que negarse antes de preguntar nada."""
        r = _ejecutar(arbol, "uninstall.sh", "--purge")
        assert r.returncode == 1
        assert _dice_sudo(r), r.stdout + r.stderr
        llamadas = _llamadas(arbol)
        assert " down" not in llamadas and "docker run" not in llamadas

    def test_uninstall_sin_env_sigue_siendo_tolerante(self, arbol):
        """No se rompe lo que ya funcionaba: un `.env` AUSENTE avisa y sigue."""
        arbol["env"].chmod(0o600)
        arbol["env"].unlink()
        r = _ejecutar(arbol, "uninstall.sh")
        assert "No encuentro" in r.stdout + r.stderr
