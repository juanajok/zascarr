"""
tests/test_ensayo_aislamiento.py

`docs/design/ui-baseline/ensayo.sh` (V0) levanta un stack de ENSAYO que escribe carpetas, marcas y
datos. Su garantía —no tocar nada que no sea del ensayo— se comprueba aquí con un `docker` de pega
que registra cada llamada: lo que importa es qué NO se ejecuta y qué NO se escribe fuera.

Regla que se prueba (la misma distinción que A9): la ruta ESCRITA no es la ruta EFECTIVA.
`mkdir -p`, `: >` y los montajes de Docker siguen los enlaces simbólicos.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SH = Path(__file__).resolve().parents[1] / "docs" / "design" / "ui-baseline" / "ensayo.sh"


@pytest.fixture
def entorno(tmp_path):
    """Un `docker` y un `ss` de pega en el PATH; el stack real nunca se toca."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(
        '#!/usr/bin/env bash\n'
        'echo "$*" >> "$DOBLE_LOG"\n'
        'case "$*" in\n'
        '  *" config --format json"*) cat "$DOBLE_CONFIG_JSON" ;;\n'
        '  "ps -a"*) printf "%s" "${DOBLE_PS_OUT:-}" ;;\n'
        '  "inspect "*) printf "%s" "${DOBLE_INSPECT_OUT:-}" ;;\n'
        'esac\n'
        'exit 0\n')
    (bin_ / "ss").write_text('#!/usr/bin/env bash\nexit 0\n')
    for f in ("docker", "ss"):
        (bin_ / f).chmod(0o755)
    base = (tmp_path / "ensayos").resolve()
    base.mkdir()
    return {"bin": bin_, "log": tmp_path / "docker.log", "base": base,
            "config": tmp_path / "config.json", "tmp": tmp_path.resolve()}


def config_valida(datos: Path) -> dict:
    return {
        "name": "zascarr-uibase",
        "services": {
            "postgres": {"container_name": "zascarr-uibase-db",
                         "volumes": [{"type": "bind", "source": f"{datos}/data/postgres"}]},
            "redis": {"container_name": "zascarr-uibase-cache",
                      "volumes": [{"type": "bind", "source": f"{datos}/data/redis"}]},
            "zascarr": {"container_name": "zascarr-uibase-app",
                        "ports": [{"published": "18000", "host_ip": "127.0.0.1"}],
                        "volumes": [{"type": "bind", "source": f"{datos}/lib"},
                                    {"type": "bind", "source": f"{datos}/dl"}]},
        },
        "networks": {"zascarr-internal": {"name": "zascarr-uibase_zascarr-internal"}},
    }


def ejecutar(entorno, orden: str, datos: Path | str, *args: str, config: dict | None = None,
             extra_env: dict | None = None):
    entorno["config"].write_text(json.dumps(config if config is not None else
                                            config_valida(Path(str(datos)))))
    env = {
        **os.environ,
        "PATH": f"{entorno['bin']}:{os.environ['PATH']}",
        "DOBLE_LOG": str(entorno["log"]),
        "DOBLE_CONFIG_JSON": str(entorno["config"]),
        "UI_BASE_DATOS": str(datos),
        **(extra_env or {}),
    }
    return subprocess.run(["bash", str(SH), orden, *args], capture_output=True, text=True,
                          env=env, timeout=60, check=False)


def llamadas(entorno) -> str:
    return entorno["log"].read_text() if entorno["log"].exists() else ""


def entorno_marcado(entorno, nombre="datos") -> Path:
    d = entorno["base"] / nombre
    d.mkdir()
    (d / ".ui-baseline").write_text("")
    return d


def nada_de_docker_que_arranque(entorno) -> bool:
    log = llamadas(entorno)
    verbos = ("build", "up ", "run ", "down", "stop", "restart", "start")
    return not any(f" {v}" in log for v in verbos)


class TestEnlacesSimbolicos:
    """Un entorno MARCADO puede contener enlaces que apunten fuera: nada se escribe allí."""

    def test_lib_enlazada_a_una_carpeta_externa_no_recibe_marca_ni_archivos(self, entorno):
        externa = entorno["tmp"] / "mi-biblioteca"
        externa.mkdir()
        datos = entorno_marcado(entorno)
        (datos / "lib").symlink_to(externa)

        r = ejecutar(entorno, "preparar", datos)

        assert r.returncode != 0
        assert "enlace simbólico" in r.stderr
        assert list(externa.iterdir()) == []          # ni `.ui-baseline` ni nada
        assert nada_de_docker_que_arranque(entorno)

    def test_data_enlazada_fuera_se_rechaza_sin_crear_carpetas_alli(self, entorno):
        externa = entorno["tmp"] / "datos-reales"
        externa.mkdir()
        datos = entorno_marcado(entorno)
        (datos / "data").symlink_to(externa)

        r = ejecutar(entorno, "preparar", datos)

        assert r.returncode != 0
        assert list(externa.iterdir()) == []          # `mkdir -p data/postgres` no se ejecutó
        assert nada_de_docker_que_arranque(entorno)

    def test_enlace_roto_hacia_fuera_se_rechaza_y_no_crea_el_destino(self, entorno):
        destino = entorno["tmp"] / "no-existe-todavia"
        datos = entorno_marcado(entorno)
        (datos / "lib").symlink_to(destino)           # roto

        r = ejecutar(entorno, "preparar", datos)

        assert r.returncode != 0
        assert not destino.exists()                   # `mkdir -p` lo habría creado
        assert nada_de_docker_que_arranque(entorno)

    def test_enlace_dentro_de_lib_tampoco_vale(self, entorno):
        """`sembrar.py` escribe en `lib/_Unsorted`: si es un enlace, escribiría fuera."""
        externa = entorno["tmp"] / "otra"
        externa.mkdir()
        datos = entorno_marcado(entorno)
        (datos / "lib").mkdir()
        (datos / "lib" / "_Unsorted").symlink_to(externa)

        r = ejecutar(entorno, "preparar", datos)

        assert r.returncode != 0
        assert "enlace simbólico" in r.stderr
        assert list(externa.iterdir()) == []

    def test_la_propia_ruta_de_ensayo_no_puede_ser_un_enlace(self, entorno):
        real = entorno["base"] / "real"
        real.mkdir()
        enlace = entorno["base"] / "atajo"
        enlace.symlink_to(real)

        r = ejecutar(entorno, "preparar", enlace)

        assert r.returncode != 0
        assert "enlace simbólico" in r.stderr
        assert list(real.iterdir()) == []
        assert nada_de_docker_que_arranque(entorno)

    def test_los_enlaces_se_rechazan_tambien_al_desmontar(self, entorno):
        externa = entorno["tmp"] / "mi-biblioteca"
        externa.mkdir()
        datos = entorno_marcado(entorno)
        (datos / ".env").write_text("")
        (datos / "lib").symlink_to(externa)

        r = ejecutar(entorno, "bajar", datos)

        assert r.returncode != 0
        assert " down" not in llamadas(entorno)


class TestCicloNormal:

    def test_preparar_en_una_carpeta_nueva_crea_marcas_y_siembra(self, entorno):
        datos = entorno["base"] / "nuevo"

        r = ejecutar(entorno, "preparar", datos)

        assert r.returncode == 0, r.stderr
        assert (datos / ".ui-baseline").exists() and (datos / "lib" / ".ui-baseline").exists()
        log = llamadas(entorno)
        assert "-p zascarr-uibase" in log                       # siempre con el proyecto de ensayo
        assert "up -d zascarr" in log and "python -" in log     # arranca y siembra

    def test_bajar_con_el_compose_aislado_desmonta(self, entorno):
        datos = entorno["base"] / "nuevo"
        assert ejecutar(entorno, "preparar", datos).returncode == 0

        r = ejecutar(entorno, "bajar", datos)

        assert r.returncode == 0, r.stderr
        assert " down" in llamadas(entorno)


class TestComposeNoAislado:
    """Si el Compose resuelto deja de ser de ensayo, NO se llama a `down` ni a nada."""

    @pytest.mark.parametrize("orden,args", [("bajar", ()), ("dc", ("stop", "postgres"))])
    def test_container_name_global_aborta_antes_de_actuar(self, entorno, orden, args):
        datos = entorno["base"] / "nuevo"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        entorno["log"].write_text("")                    # solo importa lo que ocurra ahora
        mala = config_valida(datos)
        mala["services"]["postgres"]["container_name"] = "zascarr-db"   # el de producción

        r = ejecutar(entorno, orden, datos, *args, config=mala)

        assert r.returncode != 0
        assert "container_name" in r.stderr
        log = llamadas(entorno)
        assert " down" not in log and " stop" not in log

    def test_puerto_publicado_distinto_aborta(self, entorno):
        datos = entorno["base"] / "nuevo"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        entorno["log"].write_text("")
        mala = config_valida(datos)
        mala["services"]["zascarr"]["ports"] = [{"published": "8000", "host_ip": "0.0.0.0"}]

        r = ejecutar(entorno, "bajar", datos, config=mala)

        assert r.returncode != 0
        assert " down" not in llamadas(entorno)

    def test_montaje_fuera_de_la_carpeta_de_ensayo_aborta(self, entorno):
        datos = entorno["base"] / "nuevo"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        entorno["log"].write_text("")
        mala = config_valida(datos)
        mala["services"]["zascarr"]["volumes"] = [
            {"type": "bind", "source": "/home/alguien/biblioteca"}]

        r = ejecutar(entorno, "bajar", datos, config=mala)

        assert r.returncode != 0
        assert "fuera de" in r.stderr
        assert " down" not in llamadas(entorno)

    def test_montaje_que_resuelve_fuera_por_un_enlace_aborta(self, entorno):
        """Defensa en profundidad: aunque el texto parezca interno, se compara el destino REAL."""
        datos = entorno["base"] / "nuevo"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        entorno["log"].write_text("")
        externa = entorno["tmp"] / "externa"
        externa.mkdir()
        (datos / "extra").symlink_to(externa)            # creado DESPUÉS de las comprobaciones
        mala = config_valida(datos)
        mala["services"]["zascarr"]["volumes"].append({"type": "bind", "source": f"{datos}/extra"})

        # `bajar` se detendría antes, en la comprobación de enlaces; aquí se prueba SOLO la
        # función que valida el Compose resuelto, con la configuración mala como salida de `config`.
        entorno["config"].write_text(json.dumps(mala))
        r = subprocess.run(
            ["bash", "-c",
             f'source <(sed -n "/^comprobar_compose()/,/^}}/p" "{SH}"); '
             'die() { echo "$*" >&2; exit 1; }; PUERTO=18000; '
             f'DATOS="{datos}"; dc() {{ cat "{entorno["config"]}"; }}; comprobar_compose'],
            capture_output=True, text=True, timeout=60, check=False)

        assert r.returncode != 0
        assert "fuera de" in r.stderr or "no está aislado" in r.stderr


class TestStackDeOtraCarpeta:
    """`zascarr-uibase` es un nombre único por máquina: otra sesión puede tener su stack vivo."""

    @pytest.mark.parametrize("orden,args", [("bajar", ()), ("dc", ("stop", "postgres"))])
    def test_no_actua_sobre_un_stack_cuyos_montajes_son_de_otra_carpeta(self, entorno, orden, args):
        datos = entorno["base"] / "mio"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        entorno["log"].write_text("")
        ajeno = {"DOBLE_PS_OUT": "zascarr-uibase-app\n",
                 "DOBLE_INSPECT_OUT": f"{entorno['base']}/de-otra-sesion/lib\n"}

        r = ejecutar(entorno, orden, datos, *args, extra_env=ajeno)

        assert r.returncode != 0
        assert "OTRA carpeta de datos" in r.stderr
        assert " down" not in llamadas(entorno) and " stop" not in llamadas(entorno)

    def test_si_el_stack_vivo_es_el_propio_si_actua(self, entorno):
        datos = entorno["base"] / "mio"
        assert ejecutar(entorno, "preparar", datos).returncode == 0
        propio = {"DOBLE_PS_OUT": "zascarr-uibase-app\n",
                  "DOBLE_INSPECT_OUT": f"{datos}/lib\n"}

        r = ejecutar(entorno, "bajar", datos, extra_env=propio)

        assert r.returncode == 0, r.stderr
        assert " down" in llamadas(entorno)
