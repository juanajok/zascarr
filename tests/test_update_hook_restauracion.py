# ruff: noqa: E501
"""#334 B2 — el hook de `update.sh` que comprueba que la copia de rescate restaura.

`update.sh` lo ejecuta SOLO tras una actualización real (`HIZO_UPDATE=1`: hubo fast-forward), nunca cuando ya estabas en
la última versión, y su fallo es un aviso: la aplicación ya está arriba y no se revierte nada. Hasta ahora ninguna prueba
miraba el hook: el único test de `update.sh` (`test_update_manifest.py`) lo dejaba ejecutarse con un `docker` falso y no
comprobaba si se llamó, con qué ni cuándo.

Se monta el mismo origen sintético que en `test_update_manifest.py` y se sustituye `probar_restauracion.sh` por un
espía que registra cada llamada (argumentos, si el dump y su manifiesto ya existían y en qué commit estaba el código).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

from tests.test_update_manifest import _git, _preparar

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None or shutil.which("curl") is None,
    reason="requiere git y curl",
)

ESPIA = r"""#!/usr/bin/env bash
dump="${2:-}"
manifiesto="$(dirname "${dump}")/MANIFIESTO-$(basename "${dump}" .sql.gz).json"
{
    echo "args: $*"
    [[ -s "${dump}" ]] && echo "dump_existe"
    [[ -f "${manifiesto}" ]] && echo "manifiesto_existe"
    echo "codigo: $(git -C "$(dirname "$0")/.." rev-parse HEAD)"
} >> "${HOOK_LOG}"
exit "${HOOK_RC:-0}"
"""


def _actualizar(tmp_path, *, al_dia: bool = False, hook_rc: int = 0):
    repo, _raiz, bin_, log, entorno, prev, nuevo, fixture = _preparar(tmp_path)
    espia = repo / "scripts" / "probar_restauracion.sh"
    espia.write_text(ESPIA, encoding="utf-8")
    espia.chmod(0o755)
    _git(repo, "update-index", "--skip-worktree", "scripts/probar_restauracion.sh", env=entorno)   # que no cuente como «cambio local»
    if al_dia:                                  # el código local ya es el del origen: no habrá fast-forward
        _git(repo, "fetch", "-q", "origin", "main", env=entorno)
        _git(repo, "merge", "-q", "--ff-only", "origin/main", env=entorno)
    backup, registro = tmp_path / "backups", tmp_path / "hook.log"
    r = subprocess.run(
        ["bash", str(repo / "scripts" / "update.sh"), "--rama", "main"],
        capture_output=True, text=True, timeout=180, check=False, stdin=subprocess.DEVNULL,
        env={
            **entorno,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "STUB_LOG": str(log),
            "FIXTURE_SQL": str(fixture),
            "BACKUP_DIR": str(backup),
            "HEALTH_TIMEOUT": "2",
            "BRANCH": "main",
            "HOOK_LOG": str(registro),
            "HOOK_RC": str(hook_rc),
        },
    )
    llamadas = registro.read_text(encoding="utf-8").splitlines() if registro.exists() else []
    return r, llamadas, repo, backup, log, entorno, prev, nuevo


def test_tras_un_fast_forward_real_se_comprueba_la_restauracion_con_el_dump_recien_hecho(tmp_path):
    r, llamadas, repo, backup, _log, entorno, prev, nuevo = _actualizar(tmp_path)
    assert prev != nuevo and r.returncode == 0, r.stdout + r.stderr
    dumps = sorted(backup.glob("update_*.sql.gz"))
    assert len(dumps) == 1
    assert [x for x in llamadas if x.startswith("args:")] == [f"args: --dump {dumps[0]}"]    # una sola vez, con ese dump
    assert "dump_existe" in llamadas and "manifiesto_existe" in llamadas    # ya hecho el dump y escrito su manifiesto
    assert f"codigo: {nuevo}" in llamadas                                   # y con el código ya actualizado
    assert "Actualización completada" in r.stdout


def test_si_ya_estabas_en_la_ultima_version_no_se_comprueba_nada(tmp_path):
    r, llamadas, _repo, backup, _log, _entorno, prev, nuevo = _actualizar(tmp_path, al_dia=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Ya estabas en la última versión" in r.stdout
    assert llamadas == []                                                   # el hook no se ejecutó
    assert not list(backup.glob("update_*.sql.gz"))                         # y el dump del no-op se descartó
    assert "Actualización completada" in r.stdout


def test_si_la_comprobacion_falla_avisa_y_la_aplicacion_no_se_revierte(tmp_path):
    r, llamadas, repo, backup, log, entorno, prev, nuevo = _actualizar(tmp_path, hook_rc=1)
    assert [x for x in llamadas if x.startswith("args:")], "el hook debía ejecutarse"
    assert r.returncode == 0, r.stdout + r.stderr                           # un aviso, no un fallo del despliegue
    assert "La restauración post-despliegue no pasó; la app sigue arriba" in r.stdout
    assert "Actualización completada" in r.stdout
    assert _git(repo, "rev-parse", "HEAD", env=entorno).stdout.strip() == nuevo      # el código sigue en el nuevo
    assert "up -d" in log.read_text(encoding="utf-8")                       # el servicio se recreó
    assert list(backup.glob("update_*.sql.gz")) and _git(                   # y el dump y su referencia de rescate siguen
        repo, "for-each-ref", "refs/zascarr/update", env=entorno).stdout.strip()
