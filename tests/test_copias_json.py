"""BL-OPS1 FR-16 / AC-21: `escribir_copias_json` — listado para la interfaz, sin rutas ni hashes."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="requiere jq")

RUN = """set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:?}"
source "$(dirname "$0")/_comun.sh"
escribir_copias_json "$1" "$2" "$3"
"""


def _entorno(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("_comun.sh", "_credenciales.sh", "_espacio.sh", "_cerrojo.sh"):
        shutil.copy2(SCRIPTS / nombre, repo / "scripts" / nombre)
    (repo / "scripts" / "run.sh").write_text(RUN, encoding="utf-8")
    for d in ("local", "fuera", "estado"):
        (tmp_path / d).mkdir()
    return {"repo": repo, "local": tmp_path / "local", "fuera": tmp_path / "fuera", "estado": tmp_path / "estado"}


def _copia(e, ts: str, fuera: bool, manifiesto=True, extra=None):
    nombre = f"backup_{ts}.sql.gz"
    (e["local"] / nombre).write_bytes(b"x" * 100)
    if fuera:
        (e["fuera"] / nombre).write_bytes(b"x" * 100)
    if manifiesto:
        cuerpo = {"schema": 1, "backup": nombre, "sha256": "ab" * 32, "bytes": 100,
                  "created_at": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}T{ts[9:11]}:{ts[11:13]}:{ts[13:15]}+00:00",
                  "verificacion": {"sha256": "ok"}, **(extra or {})}
        (e["local"] / f"MANIFIESTO-backup_{ts}.json").write_text(json.dumps(cuerpo))


def _correr(e, tmp_path):
    return subprocess.run(["bash", str(e["repo"] / "scripts" / "run.sh"), str(e["local"]), str(e["fuera"]), str(e["estado"])],
                          env={"PATH": "/usr/bin:/bin", "BACKUP_DIR": str(e["local"])}, capture_output=True, text=True, timeout=60)


def test_lista_las_copias_con_manifiesto_sin_rutas_ni_hashes(tmp_path):
    e = _entorno(tmp_path)
    _copia(e, "20261110_040000", fuera=True)
    _copia(e, "20261111_040000", fuera=False)
    _copia(e, "20261112_040000", fuera=True, manifiesto=False)           # sin manifiesto: no entra
    (e["local"] / "update_20261109_000000.sql.gz").write_bytes(b"x")       # otra clase: no entra
    r = _correr(e, tmp_path)
    assert r.returncode == 0, r.stderr
    datos = json.loads((e["estado"] / "copias.json").read_text())
    assert datos["schema"] == 1
    assert [c["id"] for c in datos["copias"]] == ["backup-20261111_040000", "backup-20261110_040000"]
    assert datos["copias"][0]["fuera_del_disco"] is False and datos["copias"][1]["fuera_del_disco"] is True
    assert all(set(c) == {"id", "creada_epoch", "bytes", "fuera_del_disco", "verificada"} for c in datos["copias"])
    texto = (e["estado"] / "copias.json").read_text()
    assert "abab" not in texto and str(tmp_path) not in texto and ".sql.gz" not in texto
    assert oct((e["estado"] / "copias.json").stat().st_mode & 0o777) == "0o644"


def test_como_mucho_30_las_mas_recientes(tmp_path):
    e = _entorno(tmp_path)
    for dia in range(1, 29):
        for hora in ("04", "16"):
            _copia(e, f"202610{dia:02d}_{hora}0000", fuera=False)
    _correr(e, tmp_path)
    copias = json.loads((e["estado"] / "copias.json").read_text())["copias"]
    assert len(copias) == 30 and copias[0]["id"] == "backup-20261028_160000"


def test_manifiesto_corrupto_se_salta_y_nunca_falla(tmp_path):
    e = _entorno(tmp_path)
    _copia(e, "20261110_040000", fuera=False)
    (e["local"] / "MANIFIESTO-backup_20261110_040000.json").write_text("{roto")
    r = _correr(e, tmp_path)
    assert r.returncode == 0
    assert json.loads((e["estado"] / "copias.json").read_text())["copias"] == []


def test_directorio_de_estado_inexistente_no_hace_fallar(tmp_path):
    e = _entorno(tmp_path)
    shutil.rmtree(e["estado"])
    assert _correr(e, tmp_path).returncode == 0


def test_backup_llama_al_listado_despues_de_la_retencion():
    texto = (SCRIPTS / "backup.sh").read_text(encoding="utf-8")
    assert texto.index("aplicar_retencion \"${BACKUP_DIR}\"") < texto.index("escribir_copias_json")
