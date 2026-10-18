"""`scripts/_credenciales.sh`: leer, validar, generar y escribir credenciales del `.env`.

Bash de verdad sobre ficheros sintéticos en `tmp_path` (no hace falta root: lo que exige root —propietarios y
permisos— lo miden los escenarios de `test_credenciales_aisladas.py`). Los valores son SINTÉTICOS; las pruebas de
salida comprueban que ninguna función imprime el valor.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("awk") is None, reason="requiere bash y awk",
)

LIB = Path(__file__).resolve().parents[1] / "scripts" / "_credenciales.sh"
SINT = "Sint3tica-Lib-0004"


def _bash(cuerpo: str, *, path_extra: Path | None = None, cwd: Path | None = None):
    entorno = dict(os.environ)
    if path_extra is not None:
        entorno["PATH"] = f"{path_extra}:{entorno['PATH']}"
    guion = (
        'set -uo pipefail\nwarn() { echo "AVISO: $*" >&2; }\n'
        f'source "{LIB}"\n{cuerpo}\n'
    )
    return subprocess.run(["bash", "-c", guion], capture_output=True, text=True, env=entorno,
                          timeout=60, check=False, cwd=cwd)


def _valor(env: Path, clave: str = "DB_PASSWORD") -> str:
    r = _bash(f'env_valor "{env}" {clave}')
    assert r.returncode == 0, r.stderr
    return r.stdout


# ── env_valor: se lee como lo lee Compose ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [
    ("DB_PASSWORD=abc\n", "abc"),
    ("DB_PASSWORD=\"abc\"\n", "abc"),
    ("DB_PASSWORD='abc'\n", "abc"),
    ("export DB_PASSWORD=abc\n", "abc"),
    ("  DB_PASSWORD=abc  \n", "abc"),
    ("DB_PASSWORD=abc\r\n", "abc"),
    ("DB_PASSWORD=abc # comentario\n", "abc"),
    ("DB_PASSWORD=\"a # b\"\n", "a # b"),
    ("DB_PASSWORD=primera\nDB_PASSWORD=segunda\n", "segunda"),     # gana la última, como en Compose
    ("# DB_PASSWORD=comentada\n", ""),
    ("OTRA=1\n", ""),
    ("DB_PASSWORD=\n", ""),
    ("DB_PASSWORD=a=b\n", "a=b"),
])
def test_env_valor_lee_como_compose(tmp_path, texto, esperado):
    env = tmp_path / ".env"
    env.write_text(texto, encoding="utf-8")
    assert _valor(env) == esperado


def test_env_valor_de_un_fichero_que_no_existe_es_vacio(tmp_path):
    assert _valor(tmp_path / "no-existe") == ""


# ── credencial_invalida ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,invalida", [
    ("", True), ("   ", True), ('""', True),
    ("cambia_esto_ahora", True), ("CAMBIA_ESTO_AHORA", True), (' "cambia_esto_ahora" ', True),
    ("SuperSecretPassword123", True), ("changeme", True), ("ChangeMe", True),
    (SINT, False), ("cambia_esto_ahora_no", False), ("a" * 48, False),
])
def test_credencial_invalida(valor, invalida):
    r = _bash(f'credencial_invalida {_q(valor)}; echo $?')
    assert r.stdout.strip() == ("0" if invalida else "1")


def _q(v: str) -> str:
    return "'" + v.replace("'", "'\\''") + "'"


# ── generar_credencial ────────────────────────────────────────────────────────────────────────────

def test_generar_credencial_es_hexadecimal_de_192_bits_y_distinta_cada_vez():
    r = _bash('for i in $(seq 25); do generar_credencial; echo; done')
    valores = r.stdout.split()
    assert len(valores) == 25 and len(set(valores)) == 25
    assert all(re.fullmatch(r"[0-9a-f]{48}", v) for v in valores)


def test_lo_generado_no_se_confunde_con_un_valor_de_ejemplo():
    valores = _bash('for i in $(seq 25); do generar_credencial; echo; done').stdout.split()
    assert not any(_bash(f"credencial_invalida {v}").returncode == 0 for v in valores)


# ── env_escribir: atómico, literal, conserva propietario y modo ───────────────────────────────────

@pytest.mark.parametrize("valor", [
    "simple", "con espacios y # almohadilla", "a&b\\c", 'comillas "dobles" \'simples\'', "$(no) `se` ${expande}", "x=y=z",
    "/media/Juan & María",
])
def test_env_escribir_guarda_el_valor_literal(tmp_path, valor):
    env = tmp_path / ".env"
    env.write_text("A=1\nCLAVE=vieja\nB=2\n", encoding="utf-8")
    r = _bash(f'env_escribir "{env}" CLAVE {_q(valor)}')
    assert r.returncode == 0, r.stderr
    assert env.read_text(encoding="utf-8") == f"A=1\nCLAVE={valor}\nB=2\n"


def test_env_escribir_anade_si_no_existe_y_sustituye_todas_las_apariciones(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nK=1\nK=2\n", encoding="utf-8")
    assert _bash(f'env_escribir "{env}" K nuevo; env_escribir "{env}" Z 9').returncode == 0
    assert env.read_text(encoding="utf-8") == "A=1\nK=nuevo\nK=nuevo\nZ=9\n"


def test_env_escribir_crea_el_fichero_con_modo_600(tmp_path):
    env = tmp_path / ".env"
    assert _bash(f'env_escribir "{env}" K v').returncode == 0
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


@pytest.mark.parametrize("modo", [0o600, 0o640, 0o644])
def test_env_escribir_conserva_el_modo_del_original(tmp_path, modo):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    env.chmod(modo)
    assert _bash(f'env_escribir "{env}" K v').returncode == 0
    assert stat.S_IMODE(env.stat().st_mode) == modo


def test_env_escribir_rechaza_claves_y_valores_peligrosos(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    for orden in ('env_escribir "{e}" "K=1" v', 'env_escribir "{e}" "" v', 'env_escribir "{e}" "1K" v',
                  'env_escribir "{e}" K "$(printf "a\\nB=2")"'):
        assert _bash(orden.format(e=env)).returncode != 0, orden
    assert env.read_text(encoding="utf-8") == "A=1\n"


def test_env_escribir_sobre_un_enlace_escribe_el_destino_y_no_pisa_el_enlace(tmp_path):
    real = tmp_path / "real.env"
    real.write_text("A=1\n", encoding="utf-8")
    enlace = tmp_path / "enlace.env"
    enlace.symlink_to(real)
    assert _bash(f'env_escribir "{enlace}" K v').returncode == 0
    assert enlace.is_symlink() and "K=v" in real.read_text(encoding="utf-8")


def _herramienta_rota(tmp_path: Path, nombre: str) -> Path:
    """Un directorio con un `<nombre>` que siempre falla, para ponerlo delante en el PATH."""
    d = tmp_path / f"roto-{nombre}"
    d.mkdir()
    f = d / nombre
    f.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    f.chmod(0o755)
    return d


@pytest.mark.parametrize("herramienta", ["awk", "mv", "chmod", "chown"])
def test_si_falla_un_paso_el_original_queda_intacto_y_no_sobra_ningun_temporal(tmp_path, herramienta):
    """Fallo durante la escritura: ni configuración a medias ni pérdida de la anterior válida."""
    env = tmp_path / ".env"
    env.write_text(f"DB_PASSWORD={SINT}\nOTRA=1\n", encoding="utf-8")
    env.chmod(0o640)
    antes = env.read_bytes()
    r = _bash(f'env_escribir "{env}" DB_PASSWORD otra-nueva', path_extra=_herramienta_rota(tmp_path, herramienta))
    assert r.returncode != 0
    assert env.read_bytes() == antes
    assert stat.S_IMODE(env.stat().st_mode) == 0o640
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".env.tmp")) == []
    assert "otra-nueva" not in r.stdout + r.stderr


def test_sin_permiso_de_escritura_en_la_carpeta_falla_sin_tocar_nada(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root ignora los permisos de directorio")
    carpeta = tmp_path / "ro"
    carpeta.mkdir()
    env = carpeta / ".env"
    env.write_text(f"DB_PASSWORD={SINT}\n", encoding="utf-8")
    carpeta.chmod(0o555)
    try:
        r = _bash(f'env_escribir "{env}" DB_PASSWORD nueva')
    finally:
        carpeta.chmod(0o755)
    assert r.returncode != 0 and env.read_text(encoding="utf-8") == f"DB_PASSWORD={SINT}\n"


def test_limpiar_temporales_borra_solo_los_temporales_del_env(tmp_path):
    for nombre in (".env.tmp.AbC123", ".env.tmp.zzz999"):
        (tmp_path / nombre).write_text("copia", encoding="utf-8")
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / "otro.txt").write_text("x", encoding="utf-8")
    assert _bash(f'limpiar_temporales_env "{tmp_path}/.env"').returncode == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [".env", "otro.txt"]


# ── asegurar_credenciales ─────────────────────────────────────────────────────────────────────────

def _asegurar(tmp_path: Path, texto: str | None, *, con_base: bool = False):
    env = tmp_path / ".env"
    if texto is not None:
        env.write_text(texto, encoding="utf-8")
    datos = tmp_path / "datos"
    (datos / "postgres").mkdir(parents=True, exist_ok=True)
    if con_base:
        (datos / "postgres" / "PG_VERSION").write_text("15\n", encoding="utf-8")
    r = _bash(f'asegurar_credenciales "{env}" "{datos}"; echo "RC=$?"')
    rc = int(re.search(r"RC=(\d+)", r.stdout).group(1))
    return rc, env, r


def test_una_credencial_valida_no_se_toca_ni_aunque_haya_base(tmp_path):
    for con_base in (False, True):
        rc, env, r = _asegurar(tmp_path, f"DB_PASSWORD={SINT}\nOTRA=1\n", con_base=con_base)
        assert rc == 0 and env.read_text(encoding="utf-8") == f"DB_PASSWORD={SINT}\nOTRA=1\n"
        assert SINT not in r.stdout + r.stderr


@pytest.mark.parametrize("texto", ["", "OTRA=1\n", "DB_PASSWORD=\n", "DB_PASSWORD=cambia_esto_ahora\n",
                                   "DB_PASSWORD=SuperSecretPassword123\n", "DB_PASSWORD=changeme\n"])
def test_sin_base_y_sin_credencial_valida_se_genera_una_propia(tmp_path, texto):
    rc, env, r = _asegurar(tmp_path, texto)
    assert rc == 10
    nueva = _valor(env)
    assert re.fullmatch(r"[0-9a-f]{48}", nueva)
    assert nueva not in r.stdout + r.stderr, "se imprimió la contraseña generada"


def test_con_base_ya_creada_y_sin_credencial_valida_no_se_inventa_otra(tmp_path):
    original = "DB_PASSWORD=cambia_esto_ahora\nOTRA=1\n"
    rc, env, _ = _asegurar(tmp_path, original, con_base=True)
    assert rc == 20 and env.read_text(encoding="utf-8") == original


def test_reejecutar_no_regenera(tmp_path):
    rc1, env, _ = _asegurar(tmp_path, "OTRA=1\n")
    primera = _valor(env)
    rc2, _, _ = _asegurar(tmp_path, None)
    assert (rc1, rc2) == (10, 0) and _valor(env) == primera


def test_validar_credenciales_explica_el_motivo_sin_el_valor(tmp_path):
    env = tmp_path / ".env"
    for texto, frase in (("DB_PASSWORD=\n", "falta o está vacía"), ("DB_PASSWORD=changeme\n", "valor de ejemplo")):
        env.write_text(texto, encoding="utf-8")
        r = _bash(f'validar_credenciales "{env}"')
        assert r.returncode == 1 and frase in r.stderr
    env.write_text(f"DB_PASSWORD={SINT}\n", encoding="utf-8")
    r = _bash(f'validar_credenciales "{env}"')
    assert r.returncode == 0 and SINT not in r.stdout + r.stderr


# ── raiz_dedicada: no reclamar la carpeta de nadie ────────────────────────────────────────────────

def _instalacion(raiz: Path, *extras: str) -> Path:
    repo = raiz / "zascarr"
    repo.mkdir(parents=True)
    (raiz / ".env").write_text("A=1\n", encoding="utf-8")
    for e in extras:
        (raiz / e).mkdir()
    return repo


def test_la_raiz_estandar_es_dedicada(tmp_path):
    repo = _instalacion(tmp_path / "opt" / "zascarr")
    assert _bash(f'raiz_dedicada "{repo.parent}" "{repo}"').returncode == 0


def test_la_raiz_con_cosas_ajenas_no_es_dedicada(tmp_path):
    repo = _instalacion(tmp_path / "home" / "ana", "Documentos")
    assert _bash(f'raiz_dedicada "{repo.parent}" "{repo}"').returncode != 0


def test_el_repo_fuera_de_raiz_slash_zascarr_no_es_estandar(tmp_path):
    raiz = tmp_path / "opt" / "zascarr"
    otro = raiz / "otro-nombre"
    otro.mkdir(parents=True)
    assert _bash(f'raiz_dedicada "{raiz}" "{otro}"').returncode != 0


def test_un_home_de_usuario_no_se_reclama_aunque_solo_tenga_lo_de_zascarr(tmp_path):
    """Defensa en profundidad: un home que SOLO contiene un clon de zascarr sigue siendo el home de alguien."""
    repo = _instalacion(tmp_path / "home" / "ana")
    falso = tmp_path / "falso"
    falso.mkdir()
    getent = falso / "getent"
    getent.write_text(f"#!/bin/sh\necho 'ana:x:1000:1000::{repo.parent}:/bin/bash'\n", encoding="utf-8")
    getent.chmod(0o755)
    assert _bash(f'raiz_dedicada "{repo.parent}" "{repo}"', path_extra=falso).returncode != 0


def test_proteger_sin_ser_root_no_hace_nada_y_lo_dice(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("solo tiene sentido sin root")
    repo = _instalacion(tmp_path / "opt" / "zascarr")
    env = repo.parent / ".env"
    r = _bash(f'proteger_configuracion "{env}" "{repo.parent}" "{repo}"')
    assert r.returncode == 1 and "administrador" in r.stderr
    assert stat.S_IMODE(env.stat().st_mode) != 0o000


def test_comprobar_proteccion_no_imprime_valores(tmp_path):
    repo = _instalacion(tmp_path / "opt" / "zascarr")
    env = repo.parent / ".env"
    env.write_text(f"DB_PASSWORD={SINT}\n", encoding="utf-8")
    env.chmod(0o644)
    r = _bash(f'comprobar_proteccion "{env}" "{repo.parent}" "{repo}"; echo "RC=$?"')
    assert "RC=1" in r.stdout and "modo 644" in r.stdout
    assert SINT not in r.stdout + r.stderr
