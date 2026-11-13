"""BL-OPS1 (#443), paso 1: el cerrojo único de operaciones y `backup.sh` (T-12, T-13, T-24, T-25; AC-22, 23, 33,
35, 36, 37, 42, 44).

Se ejecutan los scripts reales con un `docker` falso y directorios temporales (el mismo arnés que
`test_backup_script.py`). El cerrojo lo mantiene OTRO proceso con `fcntl.flock`, que es exactamente lo que el script
ve cuando lo tiene otra operación.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_backup_script import _ejecutar, _preparar

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
OPERATIVOS = ("backup.sh", "probar_restauracion.sh", "update.sh", "rollback.sh", "restaurar_datos.sh")
MENSAJE_OCUPADO = "Hay otra operación de ZascArr en marcha; espera a que termine."
MENSAJE_SUDO = "Ejecuta con sudo: hace falta para tomar el cerrojo de ZascArr."

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")


class OtroProceso:
    """Tiene el cerrojo (otra operación del equipo) mientras dura el `with`."""

    def __init__(self, ruta: Path):
        self.ruta = ruta

    def __enter__(self):
        self.fd = os.open(self.ruta, os.O_CREAT | os.O_WRONLY, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return self

    def __exit__(self, *a):
        os.close(self.fd)


def _estado_json(ctx) -> dict:
    return json.loads((ctx["status"] / "status.json").read_text(encoding="utf-8"))


def _previo_bueno(ctx) -> bytes:
    """Un `status.json` anterior con una última copia buena: lo que no se puede perder (M-1)."""
    contenido = json.dumps({
        "schema": 1, "status": "ok", "error": None, "last_attempt_at_epoch": 1_700_000_000,
        "last_success_at_epoch": 1_700_000_000, "last_local_success_at_epoch": 1_700_000_000,
    }).encode()
    (ctx["status"] / "status.json").write_bytes(contenido)
    return contenido


# ── backup.sh (T-12: AC-22, 23, 35, 36) ──────────────────────────────────────────────────────────
class TestBackupConElCerrojo:
    def test_con_el_cerrojo_ocupado_sale_75_deja_omitida_y_no_toca_el_estado(self, tmp_path):
        ctx = _preparar(tmp_path)
        previo = _previo_bueno(ctx)
        with OtroProceso(ctx["lock"]):
            r = _ejecutar(ctx)
        assert r.returncode == 75 and MENSAJE_OCUPADO in r.stderr
        assert (ctx["status"] / "status.json").read_bytes() == previo, "status.json debe quedar byte a byte igual"
        assert not (ctx["status"] / "ops-status.json").exists()
        omitida = json.loads((ctx["status"] / "omitida.json").read_text(encoding="utf-8"))
        assert omitida["schema"] == 1 and omitida["motivo"] == "operacion_en_curso"
        assert isinstance(omitida["omitida_epoch"], int)
        assert (ctx["status"] / "omitida.json").stat().st_mode & 0o777 == 0o644
        assert not list(ctx["backup"].glob("backup_*")), "con el cerrojo ocupado no se vuelca nada"

    def test_omitida_se_escribe_sin_jq(self, tmp_path):
        """FR-33: con `printf`, no `jq` (debe poder escribirse aunque falte)."""
        ctx = _preparar(tmp_path)
        sin_jq = tmp_path / "sinjq"
        sin_jq.mkdir()
        for herramienta in ("bash", "env", "date", "install", "chmod", "mv", "rm", "printf", "dirname", "stat",
                            "flock", "cat", "git", "mkdir", "sed", "tr", "head", "sort", "uniq"):
            ruta = shutil.which(herramienta)
            if ruta:
                (sin_jq / herramienta).symlink_to(ruta)
        with OtroProceso(ctx["lock"]):
            r = _ejecutar(ctx, extra_env={"PATH": f"{ctx['bin']}:{sin_jq}"})
        assert r.returncode == 75
        assert (ctx["status"] / "omitida.json").exists()

    def test_el_orden_cerrojo_antes_que_el_trap_el_75_no_escribe_failed_aunque_haya_otro_fallo(self, tmp_path):
        """M-1: con el cerrojo ocupado Y un requisito roto, manda el 75: nada de `failed` sobre la copia que sí corre."""
        ctx = _preparar(tmp_path)
        previo = _previo_bueno(ctx)
        (ctx["root"] / ".env").unlink()                      # un requisito roto (no hay .env)
        with OtroProceso(ctx["lock"]):
            r = _ejecutar(ctx)
        assert r.returncode == 75
        assert (ctx["status"] / "status.json").read_bytes() == previo

    def test_una_precondicion_rota_deja_precondition_failed_y_conserva_el_ultimo_exito(self, tmp_path):
        """AC-23: `failed/precondition_failed` y `last_success_*` intactos (nunca a 0)."""
        ctx = _preparar(tmp_path)
        _previo_bueno(ctx)
        (ctx["root"] / ".env").unlink()
        r = _ejecutar(ctx)
        assert r.returncode == 1
        estado = _estado_json(ctx)
        assert estado["status"] == "failed" and estado["error"] == "precondition_failed"
        assert estado["last_success_at_epoch"] == 1_700_000_000
        assert estado["last_local_success_at_epoch"] == 1_700_000_000
        assert not (ctx["status"] / "omitida.json").exists()

    def test_un_fallo_posterior_a_la_preparacion_sigue_siendo_unexpected(self, tmp_path):
        """Terminada la preparación, `on_exit` vuelve a `unexpected` (la fase no se queda puesta)."""
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DF_KB": "1024", "FAKE_MODE": "ok"})
        assert r.returncode != 0
        assert _estado_json(ctx)["error"] == "disk_full"          # un código propio gana a `unexpected`

    def test_la_copia_normal_no_deja_omitida_ni_toca_nada_nuevo(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stderr
        assert not (ctx["status"] / "omitida.json").exists()
        assert _estado_json(ctx)["status"] == "ok"


# ── los otros cuatro scripts (T-13: AC-22) ───────────────────────────────────────────────────────
def _entorno(lock: Path, **extra) -> dict:
    env = os.environ.copy()
    env.update({"ZASCARR_PRUEBAS": "1", "OPS_LOCK_FILE": str(lock), **extra})
    return env


ARGUMENTOS = {
    "update.sh": ["--rama", "main"],
    "rollback.sh": [],
    "probar_restauracion.sh": [],
    "restaurar_datos.sh": [],
}


@pytest.mark.parametrize("script", sorted(ARGUMENTOS))
def test_con_el_cerrojo_ocupado_los_otros_cuatro_salen_75_sin_tocar_nada(script, tmp_path):
    lock = tmp_path / "ops.lock"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    antes = sorted(p.name for p in cwd.iterdir())
    with OtroProceso(lock):
        r = subprocess.run(["bash", str(SCRIPTS / script), *ARGUMENTOS[script]], env=_entorno(lock),
                           capture_output=True, text=True, timeout=60, cwd=cwd, stdin=subprocess.DEVNULL)
    assert r.returncode == 75, r.stdout + r.stderr
    assert MENSAJE_OCUPADO in r.stderr
    assert sorted(p.name for p in cwd.iterdir()) == antes


# ── la herencia padre→hijo (AC-33) ───────────────────────────────────────────────────────────────
def _bash(script: str, lock: Path, **extra) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], env=_entorno(lock, **extra), capture_output=True,
                          text=True, timeout=60)


def _hijo(lock: Path) -> str:
    return (f'bash -c \'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones; echo "hijo rc=$?"\'')


def test_el_hijo_hereda_el_cerrojo_del_padre_y_no_sale_75(tmp_path):
    """AC-33 (A-1 de SecOps): `update.sh` → `probar_restauracion.sh --dump`: el hijo, con el descriptor 9
    heredado de la MISMA ruta, hace `flock -n 9` idempotente y sigue."""
    lock = tmp_path / "ops.lock"
    # `; exit $?` tras el hijo: si el hijo fuera la última orden, `bash -c` lo ejecutaría con `exec`, el
    # padre desaparecería y nadie retendría el cerrojo (la prueba pasaría aunque no hubiera herencia).
    padre = (f'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones || exit $?; {_hijo(lock)}; exit $?')
    r = _bash(padre, lock)
    assert r.returncode == 0 and "hijo rc=0" in r.stdout, r.stdout + r.stderr


def test_con_el_descriptor_9_ajeno_el_hijo_toma_el_cerrojo_por_su_cuenta(tmp_path):
    lock = tmp_path / "ops.lock"
    ajeno = tmp_path / "otro_fichero"
    padre = f'exec 9>"{ajeno}"; {_hijo(lock)}; exit $?'
    r = _bash(padre, lock)
    assert "hijo rc=0" in r.stdout, r.stdout + r.stderr


def test_con_el_cerrojo_de_otro_proceso_el_hijo_sale_75_aunque_tenga_descriptor_9(tmp_path):
    lock = tmp_path / "ops.lock"
    padre = f'exec 9>"{tmp_path / "otro_fichero"}"; {_hijo(lock)}; exit $?'
    with OtroProceso(lock):
        r = _bash(padre, lock)
    assert "hijo rc=75" in r.stdout and MENSAJE_OCUPADO in r.stderr


@pytest.mark.parametrize("modo_previo", [None, 0o666])
def test_el_fichero_del_cerrojo_es_0600(tmp_path, modo_previo):
    """F-1 (SecOps): nace 0600 y, si ya existía con otro modo, se corrige."""
    lock = tmp_path / "ops.lock"
    if modo_previo is not None:
        lock.write_text("")
        lock.chmod(modo_previo)
    r = _bash(f'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones', lock)
    assert r.returncode == 0, r.stderr
    assert (lock.stat().st_mode & 0o777) == 0o600


def test_el_cerrojo_se_suelta_al_terminar_quien_lo_tiene(tmp_path):
    lock = tmp_path / "ops.lock"
    r = _bash(f'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones', lock)
    assert r.returncode == 0
    r2 = _bash(f'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones', lock)
    assert r2.returncode == 0                                     # el primero ya terminó: libre


# ── la ruta constante (AC-37) y el aviso del override ────────────────────────────────────────────
def _ruta(env_extra: dict, con_pruebas: bool) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("ZASCARR_PRUEBAS", "OPS_LOCK_FILE", "BACKUP_LOCK_FILE")}
    env.update(env_extra)
    if con_pruebas:
        env["ZASCARR_PRUEBAS"] = "1"
    return subprocess.run(["bash", "-c", f'source "{SCRIPTS}/_cerrojo.sh"; ruta_cerrojo_operaciones'], env=env,
                          capture_output=True, text=True, timeout=30)


def test_sin_pruebas_la_ruta_es_la_constante_aunque_haya_variables_perdidas():
    r = _ruta({"OPS_LOCK_FILE": "/tmp/otra.lock", "BACKUP_LOCK_FILE": "/tmp/otra2.lock"}, con_pruebas=False)
    assert r.stdout == "/run/zascarr-ops.lock"


def test_con_pruebas_se_admite_otra_ruta_y_se_avisa(tmp_path):
    lock = tmp_path / "x.lock"
    assert _ruta({"OPS_LOCK_FILE": str(lock)}, con_pruebas=True).stdout == str(lock)
    r = _bash(f'source "{SCRIPTS}/_cerrojo.sh"; tomar_cerrojo_operaciones', lock)
    assert "ZASCARR_PRUEBAS activo: el cerrojo no es el de producción." in r.stderr


def test_la_ruta_de_produccion_esta_en_un_solo_sitio_de_los_scripts():
    """FR-12.1: la ruta constante vive en `_cerrojo.sh`; ningún otro script la repite ni lee `BACKUP_LOCK_FILE`."""
    for f in SCRIPTS.glob("*.sh"):
        texto = f.read_text(encoding="utf-8")
        if f.name == "_cerrojo.sh":
            assert 'OPS_LOCK_FILE_PRODUCCION="/run/zascarr-ops.lock"' in texto
        else:
            assert "/run/zascarr-ops.lock" not in texto, f.name
            assert "BACKUP_LOCK_FILE" not in texto, f.name


# ── sin ser root (T-24: AC-44) ───────────────────────────────────────────────────────────────────
@pytest.mark.skipif(os.geteuid() == 0, reason="se prueba sin ser root")
@pytest.mark.skipif(os.access("/run", os.W_OK), reason="/run escribible: no se puede reproducir «sin sudo»")
@pytest.mark.parametrize("script", OPERATIVOS)
def test_sin_ser_root_dice_ejecuta_con_sudo_y_sale_1_sin_el_error_crudo_de_bash(script, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("ZASCARR_PRUEBAS", "OPS_LOCK_FILE")}
    args = ARGUMENTOS.get(script, [])
    r = subprocess.run(["bash", str(SCRIPTS / script), *args], env=env, capture_output=True, text=True,
                       timeout=60, cwd=tmp_path, stdin=subprocess.DEVNULL)
    assert r.returncode == 1, r.stdout + r.stderr
    assert MENSAJE_SUDO in r.stderr
    assert "Permiso denegado" not in r.stderr and "Permission denied" not in r.stderr


# ── nada en segundo plano (T-25: AC-42) ──────────────────────────────────────────────────────────
def _lineas_de_codigo(texto: str):
    for n, linea in enumerate(texto.splitlines(), 1):
        limpia = linea.strip()
        if limpia and not limpia.startswith("#"):
            yield n, limpia


# `&` que lanza algo en segundo plano: ni `&&`, ni `2>&1`, ni `>&2`, ni `&>`, ni `|&`
_FONDO = re.compile(r"(?<![&>|0-9])&(?![&>0-9])")
_PALABRAS_DE_FONDO = re.compile(r"\b(nohup|disown|setsid|coproc)\b")


def test_ninguno_de_los_cinco_scripts_lanza_nada_en_segundo_plano():
    """FR-12.5 (SecOps A-1): un hijo que sobreviviera al padre se quedaría con el cerrojo (comparten la descripción)."""
    for nombre in OPERATIVOS:
        for n, linea in _lineas_de_codigo((SCRIPTS / nombre).read_text(encoding="utf-8")):
            sin_cadenas = re.sub(r'"[^"]*"|\'[^\']*\'', '""', linea)
            assert not _FONDO.search(sin_cadenas), f"{nombre}:{n}: {linea}"
            assert not _PALABRAS_DE_FONDO.search(sin_cadenas), f"{nombre}:{n}: {linea}"


@pytest.mark.parametrize("linea,fondo", [
    ("sleep 5 &", True), ("cmd & otro", True), ("nohup cmd", True), ("setsid cmd", True),
    ("a && b", False), ("cmd 2>&1", False), ("cmd >&2", False), ("cmd &> /dev/null", False),
    ("cmd |& tee", False), ('echo "a & b"', False),
])
def test_el_analisis_de_segundo_plano_no_da_falsos_positivos_ni_se_deja_nada(linea, fondo):
    sin_cadenas = re.sub(r'"[^"]*"|\'[^\']*\'', '""', linea)
    assert bool(_FONDO.search(sin_cadenas) or _PALABRAS_DE_FONDO.search(sin_cadenas)) is fondo


# ── las unidades (FR-12.4) ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("unidad", ["zascarr-backup.service", "zascarr-restore.service"])
def test_las_unidades_de_copia_y_restauracion_aceptan_el_75_como_exito(unidad):
    texto = (RAIZ / "deploy" / "systemd" / unidad).read_text(encoding="utf-8")
    assert re.search(r"^SuccessExitStatus=75\s*$", texto, flags=re.M)
