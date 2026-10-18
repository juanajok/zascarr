"""Compose no pone en servicio el sistema con `DB_PASSWORD` ausente, vacía o conocida por defecto.

Compose puede exigir una variable presente y no vacía (`${VAR:?}`), pero eso por sí solo NO rechaza un valor de
ejemplo, y además hace fallar `docker compose down/logs/ps` cuando el `.env` falta (justo cuando se quiere parar o
desinstalar). Por eso el rechazo vive en un servicio de un solo uso, `credenciales`, del que dependen PostgreSQL y la
aplicación: se ejecuta antes de crear nada y, si falla, `up` se detiene con un mensaje en español. Estas pruebas lo
ejecutan de verdad (Docker real, sin red, con valores sintéticos) y miden el código de salida.

Sin demonio de Docker o sin la imagen `postgres:15-alpine` ya descargada, se SALTAN (= no ejecutadas, no pasadas).
Las aserciones son booleanas: nunca se vuelca la configuración renderizada.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = RAIZ / "docker-compose.yml"
PROYECTO = "zascarr-cred-prueba"
IMAGEN = "postgres:15-alpine"
VALIDA = "Sint3tica-Valida-Compose-0003"


def _docker_listo() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "image", "inspect", IMAGEN], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_listo(),
    reason=f"NO EJECUTADA: hace falta un demonio de Docker con la imagen {IMAGEN} ya descargada",
)


def _compose(tmp_path: Path, env_texto: str, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    env = tmp_path / ".env"
    env.write_text(env_texto, encoding="utf-8")
    return subprocess.run(
        ["docker", "compose", "-p", PROYECTO, "-f", str(COMPOSE), "--env-file", str(env), *args],
        capture_output=True, text=True, timeout=timeout, check=False, cwd=tmp_path,
    )


def _config(tmp_path: Path, env_texto: str) -> dict:
    r = _compose(tmp_path, env_texto, "config", "--format", "json")
    assert r.returncode == 0, "docker compose config falló (la salida no se vuelca: puede llevar valores)"
    return json.loads(r.stdout)


def _comprobar(tmp_path: Path, linea: str | None) -> subprocess.CompletedProcess:
    return _compose(tmp_path, "TZ=Europe/Madrid\n" + (linea + "\n" if linea is not None else ""),
                    "run", "--rm", "--no-deps", "-T", "credenciales")


@pytest.mark.parametrize("linea", [
    pytest.param(None, id="ausente"),
    pytest.param("DB_PASSWORD=", id="vacia"),
    pytest.param("DB_PASSWORD=   ", id="solo-espacios"),
    pytest.param("DB_PASSWORD=cambia_esto_ahora", id="ejemplo-del-proyecto"),
    pytest.param("DB_PASSWORD=CAMBIA_ESTO_AHORA", id="ejemplo-en-mayusculas"),
    pytest.param('DB_PASSWORD="cambia_esto_ahora"', id="ejemplo-entre-comillas"),
    pytest.param("DB_PASSWORD=SuperSecretPassword123", id="defecto-historico-del-compose"),
    pytest.param("DB_PASSWORD=changeme", id="changeme"),
])
def test_el_comprobador_rechaza_ausente_vacia_y_conocida(tmp_path, linea):
    r = _comprobar(tmp_path, linea)
    assert r.returncode != 0, "Compose dejó pasar una credencial ausente, vacía o conocida por defecto"
    assert "DB_PASSWORD" in (r.stdout + r.stderr), "el rechazo no dice cuál es la variable"


def test_el_comprobador_acepta_una_credencial_propia(tmp_path):
    r = _comprobar(tmp_path, f"DB_PASSWORD={VALIDA}")
    assert r.returncode == 0, "rechazó una credencial válida"
    assert VALIDA not in (r.stdout + r.stderr), "el comprobador imprimió la credencial"


def test_postgres_y_la_aplicacion_esperan_al_comprobador(tmp_path):
    servicios = _config(tmp_path, f"DB_PASSWORD={VALIDA}\n")["services"]
    for nombre in ("postgres", "zascarr"):
        dep = servicios[nombre]["depends_on"]["credenciales"]
        assert dep["condition"] == "service_completed_successfully", nombre
    assert servicios["credenciales"].get("restart", "no") == "no"


def test_sin_contrasena_la_configuracion_no_cae_en_una_conocida(tmp_path):
    """La causa raíz: `${DB_PASSWORD:-SuperSecretPassword123}` ponía en servicio una base con una contraseña
    publicada en el propio repositorio cuando el `.env` no se encontraba."""
    servicios = _config(tmp_path, "TZ=Europe/Madrid\n")["services"]
    conocidas = ("supersecretpassword123", "cambia_esto_ahora", "changeme")
    candidatas = [servicios["postgres"]["environment"].get("POSTGRES_PASSWORD", "")]
    candidatas += [e for e in _entorno_lista(servicios["zascarr"]) if e.startswith("DATABASE_URL=")]
    assert not any(c in texto.lower() for texto in candidatas for c in conocidas)


def _entorno_lista(servicio: dict) -> list[str]:
    ent = servicio.get("environment", {})
    return [f"{k}={v}" for k, v in ent.items()] if isinstance(ent, dict) else list(ent)


def test_la_aplicacion_no_monta_el_env(tmp_path):
    """El `.env` es administrativo (de root): el contenedor solo recibe las variables que el compose le pasa."""
    servicios = _config(tmp_path, f"DB_PASSWORD={VALIDA}\n")["services"]
    for nombre, servicio in servicios.items():
        for vol in servicio.get("volumes", []):
            origen = str(vol.get("source", ""))
            assert not origen.endswith(".env") and "/.env" not in origen, f"{nombre} monta el .env"
