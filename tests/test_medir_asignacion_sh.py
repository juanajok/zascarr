# ruff: noqa: E501
"""`scripts/medicion/medir_asignacion.sh`: solo escribe donde se le dice y no toca nada más.

Con un `docker` de pega que registra cada llamada (mismo enfoque que `tests/test_ensayo_aislamiento.py`):
se comprueba QUÉ se ejecutaría, no que Docker funcione.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "medicion" / "medir_asignacion.sh"


@pytest.fixture
def entorno(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    registro = tmp_path / "docker.log"
    (bin_ / "docker").write_text(f"""#!/usr/bin/env bash
echo "$@" >> {registro}
case "$1" in
    exec) exit 0 ;;
    run) if [[ " $* " == *" medir_asignacion.py "* || "$*" == *medir_asignacion.py* ]]; then echo '{{"ok": true}}'; fi ;;
esac
exit 0
""")
    (bin_ / "docker").chmod(0o755)
    ensayo = tmp_path / "ensayo"
    ensayo.mkdir()
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}")
    return env, registro, ensayo


def correr(env, *args):
    return subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60)


def llamadas(registro: Path) -> list[str]:
    return registro.read_text().splitlines() if registro.exists() else []


class TestNoHaceNadaSinPermiso:

    def test_sin_dir_se_niega(self, entorno):
        env, registro, _ = entorno
        r = correr(env, "--confirmo")
        assert r.returncode != 0 and "al menos una carpeta" in r.stderr and llamadas(registro) == []

    def test_sin_confirmo_solo_enseña_el_plan(self, entorno):
        env, registro, ensayo = entorno
        r = correr(env, "--dir", str(ensayo))
        assert r.returncode == 2 and "Sin --confirmo: no hago nada" in r.stdout
        assert str(ensayo) in r.stdout and llamadas(registro) == []

    def test_una_carpeta_inexistente_no_se_crea(self, entorno, tmp_path):
        env, registro, _ = entorno
        nueva = tmp_path / "no_existe"
        r = correr(env, "--dir", str(nueva), "--confirmo")
        assert r.returncode != 0 and "No creo carpetas" in r.stderr
        assert not nueva.exists() and llamadas(registro) == []

    def test_una_ruta_relativa_se_rechaza(self, entorno):
        env, registro, _ = entorno
        r = correr(env, "--dir", "ensayo", "--confirmo")
        assert r.returncode != 0 and "absoluta" in r.stderr and llamadas(registro) == []

    def test_un_enlace_simbolico_se_rechaza(self, entorno, tmp_path):
        env, registro, ensayo = entorno
        enlace = tmp_path / "enlace"
        enlace.symlink_to(ensayo)
        r = correr(env, "--dir", str(enlace), "--confirmo")
        assert r.returncode != 0 and "enlace simbólico" in r.stderr and llamadas(registro) == []

    def test_carpetas_solapadas_se_rechazan(self, entorno):
        env, registro, ensayo = entorno
        hija = ensayo / "hija"
        hija.mkdir()
        r = correr(env, "--dir", str(ensayo), "--dir", str(hija), "--confirmo")
        assert r.returncode != 0 and "se solapan" in r.stderr and llamadas(registro) == []

    def test_argumentos_numericos_invalidos(self, entorno):
        env, registro, ensayo = entorno
        r = correr(env, "--dir", str(ensayo), "--tamanos", "10;rm -rf /", "--confirmo")
        assert r.returncode != 0 and llamadas(registro) == []


class TestLoQueSeEjecuta:

    def test_solo_monta_las_carpetas_indicadas_y_limpia(self, entorno, tmp_path):
        env, registro, ensayo = entorno
        otra = tmp_path / "otra"
        otra.mkdir()
        r = correr(env, "--dir", str(ensayo), "--dir", str(otra), "--imagen", "img:x", "--confirmo")
        assert r.returncode == 0, r.stderr
        todas = "\n".join(llamadas(registro))
        # Montajes: exactamente las dos carpetas, ninguna más.
        assert todas.count(" -v ") == 2
        assert f"-v {ensayo.resolve()}:/ensayo/1" in todas and f"-v {otra.resolve()}:/ensayo/2" in todas
        # Nada se publica ni se comparte con el anfitrión; los datos de Postgres van a tmpfs.
        assert " -p " not in todas and "--publish" not in todas and "--privileged" not in todas
        assert "--tmpfs /var/lib/postgresql/data" in todas
        # Todo lo que crea lleva el prefijo propio y se borra al terminar.
        nombres = [ln for ln in llamadas(registro) if ln.startswith(("network create", "run -d"))]
        assert all("zascarr-medicion-" in ln for ln in nombres)
        assert any(ln.startswith("rm -f zascarr-medicion-pg-") for ln in llamadas(registro))
        assert any(ln.startswith("network rm zascarr-medicion-") for ln in llamadas(registro))
        # Nunca toca contenedores ni redes ajenos.
        assert not any(ln.split()[0] in ("stop", "restart", "kill", "prune") for ln in llamadas(registro))

    def test_corre_como_el_usuario_pedido_y_sin_entrypoint_de_la_app(self, entorno):
        env, registro, ensayo = entorno
        r = correr(env, "--dir", str(ensayo), "--imagen", "img:x", "--usuario", "1234:5678", "--confirmo")
        assert r.returncode == 0, r.stderr
        run = next(ln for ln in llamadas(registro) if "medir_asignacion.py" in ln)
        assert "--user 1234:5678" in run and "--entrypoint python" in run
