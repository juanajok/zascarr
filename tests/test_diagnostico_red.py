"""A10 — diagnóstico de la red Docker/UFW.

El script corre en el HOST con `docker` y `ufw` de verdad. Aquí se prueba con
**dobles** en el `PATH`: así se puede comprobar lo que de verdad importa —que la
subred y el recorrido se lean de la instalación y no se adivinen, que no se
proponga una regla cuando no se puede determinar, y que el script **nunca**
ejecute `ufw` para cambiar nada— sin tocar la red de la máquina que ejecuta los
tests.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="el diagnóstico es un script de Bash para Linux"
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnostico-red.sh"
REPO = SCRIPT.parents[1]


def quitar_env_de_prueba(tmp_path: Path) -> None:
    """`_comun.sh` enlaza `REPO/.env` al `ENV_FILE` que ve el script. Con un
    `ENV_FILE` temporal eso deja un **enlace roto en la raíz del repo** en cuanto
    pytest borra el temporal — y `get_settings()` lee `.env` desde el cwd, así que
    puede ensuciar otros tests (los de Postgres, por ejemplo). Se quita, pero
    **solo si apunta al temporal de esta prueba**: un `.env` de verdad no se
    toca."""
    enlace = REPO / ".env"
    if not enlace.is_symlink():
        return
    try:
        destino = os.readlink(enlace)
    except OSError:
        return
    if destino.startswith(str(tmp_path)):
        enlace.unlink()

DOCKER_STUB = r"""#!/usr/bin/env bash
# Doble de docker: responde por forma del argumento, no por coincidencia exacta.
args="$*"
[[ -n "${STUB_DOCKER_REGISTRO:-}" ]] && echo "docker $args" >> "${STUB_DOCKER_REGISTRO}"
case "$args" in
    *"ps -q zascarr"*) printf '%s\n' "${STUB_CONTENEDOR:-}"; exit 0 ;;
esac
if [[ "$args" == network\ inspect* ]]; then
    # `otra-red` permite montar un contenedor con DOS redes.
    if [[ "$args" == *"otra-red"* ]]; then
        sub="${STUB_SUBRED_OTRA:-}"; int="${STUB_INTERFAZ_OTRA:-}"; id="${STUB_ID_OTRA:-}"
    else
        sub="${STUB_SUBRED:-}"; int="${STUB_INTERFAZ:-}"; id="${STUB_ID_RED:-}"
    fi
    case "$args" in
        *IPAM.Config*) printf '%s\n' "${sub}"; exit 0 ;;
        *bridge.name*) printf '%s\n' "${int}"; exit 0 ;;
        *".Id"*)       printf '%s\n' "${id}"; exit 0 ;;
    esac
    exit 1
fi
if [[ "$args" == inspect* ]]; then
    case "$args" in
        *NetworkSettings.Networks*) printf '%s\n' "${STUB_REDES:-}"; exit 0 ;;
    esac
    exit 1
fi
if [[ "$args" == exec* ]]; then
    case "$args" in
        *runtime_settings*) printf '%s\n' "${STUB_CONFIG:-}"; exit 0 ;;
        *gethostbyname*)    printf '%s\n' "${STUB_RESUELTO:-}"; exit 0 ;;
    esac
    exit 1
fi
echo "doble de docker sin caso: $args" >&2
exit 1
"""

UFW_STUB = r"""#!/usr/bin/env bash
# Doble de ufw. Registra TODO lo que se le pide: es la forma de comprobar que
# el diagnóstico no ejecuta ninguna orden que cambie reglas.
if [[ "${STUB_UFW_REGISTRO:-}" != "" ]]; then echo "ufw $*" >> "${STUB_UFW_REGISTRO}"; fi
if [[ "${STUB_UFW_FALLA:-}" == "si" ]]; then exit 1; fi
case "${1:-}" in
    status)
        if [[ "${2:-}" == "numbered" ]]; then
            printf '%s\n' "${STUB_UFW_ESTADO:-Status: active}"; exit 0
        fi
        printf '%s\n' "${STUB_UFW_ESTADO:-Status: active}"
        if [[ -n "${STUB_UFW_REGLAS_STATUS:-}" ]]; then
            printf '%s\n' "${STUB_UFW_REGLAS_STATUS}"
        else
            # Una línea de tabla por regla añadida: así las dos fuentes cuadran
            # (como en una Pi de verdad) salvo que la prueba diga lo contrario.
            while read -r r; do
                [[ "$r" == ufw\ * ]] && echo "9696 ALLOW 0.0.0.0/0"
            done <<< "${STUB_UFW_ANADIDAS:-}"
        fi
        ;;
    show)
        printf '%s\n' "${STUB_UFW_ANADIDAS:-}"
        ;;
esac
exit 0
"""

def config_activa(prowlarr="http://host.docker.internal:9696",
                  transmission="http://host.docker.internal:9091",
                  amule="http://host.docker.internal:4711") -> str:
    """Lo que la app dice estar usando (precedencia de D11)."""
    return "\n".join([
        f"prowlarr_url={prowlarr}",
        f"transmission_url={transmission}",
        f"amule_url={amule}",
    ])


# Un escenario coherente por defecto: el contenedor está en 172.18.0.0/16 y
# host.docker.internal resuelve a su puerta de enlace real.
BASE = {
    "STUB_CONFIG": config_activa(),
    "STUB_CONTENEDOR": "abc123def456",
    "STUB_REDES": "zascarr_zascarr-internal 172.18.0.5 172.18.0.1",
    "STUB_SUBRED": "172.18.0.0/16",
    "STUB_ID_RED": "089a55cef0407814eea4c683eb80a4d669915bba4d899a9804ac05f63e2ee284",
    "STUB_INTERFAZ": "",
    "STUB_RESUELTO": "172.18.0.1",
    "STUB_UFW_ESTADO": "Status: active",
    "STUB_UFW_REGLAS_STATUS": "",
    "STUB_UFW_ANADIDAS": "",
}
# Reglas de "solo LAN", el caso real: no cubren ninguna subred de Docker.
REGLAS_SOLO_LAN = "ufw allow 22/tcp\nufw allow from 192.168.1.0/24 to any port 9696 proto tcp"


@pytest.fixture
def entorno(tmp_path: Path):
    """PATH con los dobles, un `.env` propio y un registro de llamadas."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for nombre, cuerpo in (("docker", DOCKER_STUB), ("ufw", UFW_STUB)):
        ruta = bin_dir / nombre
        ruta.write_text(cuerpo)
        ruta.chmod(0o755)

    env_file = tmp_path / ".env"
    env_file.write_text("")
    registro = tmp_path / "llamadas.txt"
    registro.write_text("")

    def ejecutar(*, env_file_texto: str = "", args: list[str] | None = None,
                 config: str | None = None, **stubs):
        env_file.write_text(env_file_texto)
        entorno_vars = dict(os.environ)
        entorno_vars["PATH"] = f"{bin_dir}:{entorno_vars['PATH']}"
        entorno_vars["ENV_FILE"] = str(env_file)
        entorno_vars["STUB_UFW_REGISTRO"] = str(registro)
        entorno_vars["STUB_DOCKER_REGISTRO"] = str(registro)
        if config is not None:
            stubs["STUB_CONFIG"] = config
        for clave, valor in {**BASE, **stubs}.items():
            if valor is None:
                entorno_vars.pop(clave, None)
            else:
                entorno_vars[clave] = valor
        resultado = subprocess.run(
            ["bash", str(SCRIPT), *(args or [])],
            capture_output=True, text=True, env=entorno_vars, timeout=60, check=False,
        )
        # `_comun.sh` deja `REPO_DIR/.env` apuntando al ENV_FILE temporal: se
        # quita antes de que pytest borre el temporal y quede un enlace roto en
        # la raíz del repo (que `get_settings()` leería desde el cwd).
        quitar_env_de_prueba(tmp_path)
        return resultado

    ejecutar.registro = registro  # type: ignore[attr-defined]
    return ejecutar


def texto(salida: subprocess.CompletedProcess) -> str:
    """Salida con los espacios colapsados.

    Los mensajes van partidos en varias líneas a propósito, para que se lean en
    una terminal; las aserciones no deben depender de dónde cae el salto."""
    return " ".join(salida.stdout.split())


class TestCuandoNoAplica:

    def test_ufw_no_instalado(self, entorno, tmp_path):
        bin_dir = tmp_path / "sin_ufw"
        bin_dir.mkdir()
        (bin_dir / "docker").write_text(DOCKER_STUB)
        (bin_dir / "docker").chmod(0o755)
        salida = entorno(env_file_texto="")
        assert salida.returncode in (0, 1, 2)  # control: con ufw sí corre

        env_vars = dict(os.environ)
        env_vars["PATH"] = f"{bin_dir}:/usr/bin:/bin"
        env_vars["ENV_FILE"] = str(tmp_path / ".env")
        resultado = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True,
            env=env_vars, timeout=60, check=False,
        )
        assert resultado.returncode == 0
        assert "No hay ufw instalado" in texto(resultado)

    def test_ufw_inactivo(self, entorno):
        salida = entorno(env_file_texto="", STUB_UFW_ESTADO="Status: inactive")
        assert salida.returncode == 0
        assert "inactivo" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_ufw_no_responde_sin_root(self, entorno):
        """Un usuario normal no puede leer las reglas: se dice, no se adivina."""
        salida = entorno(env_file_texto="", STUB_UFW_FALLA="si")
        assert salida.returncode == 2
        assert "permisos de administrador" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_ufw_contesta_cosa_que_no_entiendo(self, entorno):
        salida = entorno(env_file_texto="", STUB_UFW_ESTADO="Status: rarísimo")
        assert salida.returncode == 2
        assert "No entiendo la respuesta" in texto(salida)


class TestSubredReal:

    def test_propone_la_subred_leida_de_docker(self, entorno):
        """Ni 172.17.0.0/16 ni una adivinada: la que tiene el contenedor."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout
        assert "172.17.0.0/16" not in salida.stdout

    def test_la_regla_amplia_del_proyecto_cuenta_como_cobertura(self, entorno):
        """172.16.0.0/12 contiene a 172.18.0.0/16: no se propone nada redundante."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 172.16.0.0/12 to any port 9696 proto tcp",
        )
        assert salida.returncode == 0
        assert "ya hay una regla que cubre 172.18.0.0/16" in salida.stdout
        assert "ufw allow from" not in salida.stdout

    def test_la_subred_equivocada_no_cuenta_como_cobertura(self, entorno):
        """El caso real: la regla existía, era correcta en sí… y apuntaba a otra red."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS="ufw allow from 172.17.0.0/16 to any port 9696 proto tcp",
        )
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout

    def test_anywhere_como_origen_si_cubre(self, entorno):
        """ufw(8): 'Anywhere' equivale a cualquier origen, no es texto literal."""
        salida = entorno(args=["--puerto", "9696"], STUB_UFW_ANADIDAS="ufw allow 9696/tcp")
        assert salida.returncode == 0
        assert "ya hay una regla que cubre" in salida.stdout

    def test_una_regla_atada_a_otra_interfaz_no_cubre(self, entorno):
        """Reglas 'solo LAN' con `on eth0`: la interfaz del puente es otra."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=(
                "ufw allow in on eth0 from 172.16.0.0/12 to any port 9696 proto tcp"
            ),
        )
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout
        assert "atadas a otra interfaz" in texto(salida)

    def test_una_regla_atada_al_puente_correcto_si_cubre(self, entorno):
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS=(
                "ufw allow in on br-089a55cef040 from 172.16.0.0/12 "
                "to any port 9696 proto tcp"
            ),
        )
        assert salida.returncode == 0
        assert "ya hay una regla que cubre" in salida.stdout

    def test_la_regla_no_lleva_on(self, entorno):
        """Omitir `on` es deliberado: la interfaz del puente cambia con la red."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        assert "NO lleva 'on <interfaz>'" in texto(salida)
        assert "br-089a55cef040" in salida.stdout  # se enseña, pero no se usa en la regla

    def test_un_deny_no_propone_comando(self, entorno):
        """Con un DENY que casa, una regla nueva al final podría quedarle por
        detrás. No se propone comando: se remite a inspección manual."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw deny from 172.16.0.0/12 to any port 9696 proto tcp",
        )
        assert salida.returncode == 1
        assert "DENIEGA" in texto(salida)
        assert "ufw status numbered" in texto(salida)
        assert "ufw allow from" not in salida.stdout
        assert "ya hay una regla que cubre" not in texto(salida)

    def test_deny_y_allow_juntos_no_se_dan_por_cubiertos(self, entorno):
        """Cuál gana depende del ORDEN EFECTIVO, y `ufw show added` no lo
        conserva (ufw(8)). Ante la duda, ni «cubre» ni propuesta."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS=(
                "ufw deny from 172.18.0.0/16 to any port 9696 proto tcp\n"
                "ufw allow from 172.18.0.0/16 to any port 9696 proto tcp"
            ),
        )
        assert salida.returncode == 1
        assert "DENIEGA" in texto(salida)
        assert "ya hay una regla que cubre" not in texto(salida)
        assert "ufw allow from" not in salida.stdout

    def test_allow_y_deny_juntos_tampoco(self, entorno):
        """El mismo caso con los dos en el otro orden: no se puede saber cuál
        gana desde `show added`, así que tampoco se dice que cubre."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS=(
                "ufw allow from 172.18.0.0/16 to any port 9696 proto tcp\n"
                "ufw deny from 172.18.0.0/16 to any port 9696 proto tcp"
            ),
        )
        assert salida.returncode == 1
        assert "ya hay una regla que cubre" not in texto(salida)
        assert "ufw allow from" not in salida.stdout

    def test_una_regla_proto_udp_no_cubre_tcp(self, entorno):
        """`proto udp` no autoriza este tráfico: no puede acreditar cobertura."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow proto udp from 172.18.0.0/16 to any port 9696",
        )
        assert salida.returncode == 1
        assert "ya hay una regla que cubre" not in texto(salida)
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout

    def test_una_regla_dirigida_a_otra_direccion_no_cubre(self, entorno):
        """`to 192.168.1.5 port 9696` no autoriza el tráfico que va a la puerta
        de enlace de Docker."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 172.18.0.0/16 to 192.168.1.5 port 9696 proto tcp",
        )
        assert salida.returncode == 1
        assert "ya hay una regla que cubre" not in texto(salida)
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout

    def test_una_regla_dirigida_a_la_puerta_de_enlace_si_cubre(self, entorno):
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 172.18.0.0/16 to 172.18.0.1 port 9696 proto tcp",
        )
        assert salida.returncode == 0
        assert "ya hay una regla que cubre" in texto(salida)

    def test_una_regla_que_no_se_entiende_impide_proponer_si_deniega(self, entorno):
        """Un DENY con destino que no sé leer podría casar: no propongo nada."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw deny from 172.18.0.0/16 to any port OpenSSH",
        )
        assert salida.returncode == 2
        assert "no puedo interpretar" in texto(salida)
        assert "ufw allow from" not in salida.stdout

    def test_una_regla_que_no_se_entiende_y_solo_permite_no_bloquea_el_diagnostico(self, entorno):
        """Un ALLOW ilegible no acredita cobertura, pero tampoco puede tapar
        nada: se propone la regla (y se avisa de que no se contó)."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 172.18.0.0/16 to any port OpenSSH",
        )
        assert salida.returncode == 1
        assert "ya hay una regla que cubre" not in texto(salida)
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout
        assert "no he podido interpretar" in texto(salida)


class TestRecorridoReal:

    def test_recorrido_bueno(self, entorno):
        salida = entorno(env_file_texto="", STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN)
        assert "la puerta de enlace de 172.18.0.0/16" in texto(salida)

    def test_recorrido_roto_no_propone_ninguna_regla(self, entorno):
        """Causa real del 2026-09-25 (docker0 vs red propia): una regla para la
        subred «correcta» NO arregla esto, así que no se imprime."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_RESUELTO="172.17.0.1",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        assert "172.17.0.1" in salida.stdout
        assert "172.18.0.1" in salida.stdout
        assert "ninguna de sus redes" in texto(salida)
        assert "ufw allow" not in salida.stdout
        assert "--force-recreate zascarr" in texto(salida)

    def test_sin_poder_comprobar_el_recorrido_no_propone_nada(self, entorno):
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_RESUELTO=None,
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 2
        assert "no sé por qué red sale el tráfico" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_varias_redes_usa_la_del_recorrido_comprobado(self, entorno):
        """Con dos redes, la subred es la de la puerta de enlace a la que
        resuelve host.docker.internal, no la primera de la lista."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_REDES=(
                "zascarr_zascarr-internal 172.18.0.5 172.18.0.1\n"
                "otra-red 172.19.0.5 172.19.0.1"
            ),
            STUB_SUBRED_OTRA="172.19.0.0/16",
            STUB_RESUELTO="172.19.0.1",
        )
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.19.0.0/16 to any port 9696 proto tcp" in salida.stdout
        # La otra red sale en el listado, pero NO en la regla propuesta.
        assert "allow from 172.18.0.0/16" not in salida.stdout

    def test_varias_redes_con_la_misma_puerta_de_enlace_no_decide(self, entorno):
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_REDES=(
                "zascarr_zascarr-internal 172.18.0.5 172.18.0.1\n"
                "otra-red 172.18.0.6 172.18.0.1"
            ),
            STUB_SUBRED_OTRA="172.18.0.0/16",
            STUB_RESUELTO="172.18.0.1",
        )
        assert salida.returncode == 2
        assert "comparten la puerta de enlace" in texto(salida)
        assert "ufw allow" not in salida.stdout


class TestPuertos:

    def test_url_a_otra_maquina_no_propone_regla(self, entorno):
        salida = entorno(
            config=config_activa(prowlarr="http://192.168.1.50:9696"),
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "otra máquina" in texto(salida)
        assert "9696 proto tcp" not in salida.stdout

    def test_url_a_127_0_0_1_es_un_error_de_configuracion(self, entorno):
        """Dentro del contenedor, 127.0.0.1 es el contenedor: ufw no lo arregla."""
        salida = entorno(
            config=config_activa(prowlarr="http://127.0.0.1:9696"),
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "NO PUEDE FUNCIONAR" in texto(salida)
        assert "cámbialo por http://host.docker.internal:9696 en /ui/ajustes" in texto(salida)
        assert "9696 proto tcp" not in salida.stdout

    def test_el_override_de_ajustes_manda_sobre_el_env(self, entorno):
        """Ajustes (D11) sobrescribe las URLs en caliente: el `.env` puede estar
        viejo y una regla calculada sobre él apuntaría al puerto equivocado."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            config=config_activa(prowlarr="http://192.168.1.50:9697"),
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        # El .env decía 9696 en esta misma Pi; la app usa 9697 en otra máquina.
        assert "9696 proto tcp" not in salida.stdout
        assert "9697 proto tcp" not in salida.stdout
        assert "otra máquina" in texto(salida)

    def test_override_a_127_0_0_1_explica_el_error_y_no_toca_ufw(self, entorno):
        salida = entorno(
            env_file_texto="AMULE_URL=http://host.docker.internal:4711\n",
            config=config_activa(amule="http://127.0.0.1:4711"),
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "NO PUEDE FUNCIONAR" in texto(salida)
        assert "4711 proto tcp" not in salida.stdout
        assert "host.docker.internal:4711" in texto(salida)

    def test_sin_configuracion_activa_no_analiza_el_env(self, entorno):
        """Si no se puede leer lo que la app usa, el `.env` NO es un sustituto:
        puede estar desfasado. Se piden los puertos a mano."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_CONFIG="",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 2
        assert "No analizo el .env" in texto(salida)
        assert "ufw allow from" not in salida.stdout

    def test_sin_configuracion_activa_pero_con_puertos_a_mano_sigue(self, entorno):
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_CONFIG="",
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout
        assert "solo con los\n  puertos" in salida.stdout or "solo con los" in texto(salida)

    def test_puerto_a_mano(self, entorno):
        salida = entorno(args=["--puerto", "8080"], STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN)
        assert salida.returncode == 1
        assert "sudo ufw allow from 172.18.0.0/16 to any port 8080 proto tcp" in salida.stdout

    def test_los_tres_por_defecto_sin_env(self, entorno):
        salida = entorno(env_file_texto="", STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN)
        for puerto in (9696, 9091, 4711):
            assert f"to any port {puerto} proto tcp" in salida.stdout

    def test_puerto_ya_cubierto_y_otro_no(self, entorno):
        salida = entorno(
            env_file_texto=(
                "PROWLARR_URL=http://host.docker.internal:9696\n"
                "TRANSMISSION_URL=http://host.docker.internal:9091\n"
            ),
            STUB_UFW_ANADIDAS="ufw allow from 172.16.0.0/12 to any port 9696 proto tcp",
        )
        assert salida.returncode == 1
        assert "9696/tcp): ya hay una regla que cubre" in texto(salida)
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9091 proto tcp" in salida.stdout


class TestCuandoNoSePuedeDeterminar:

    def test_contenedor_parado(self, entorno):
        salida = entorno(env_file_texto="", STUB_CONTENEDOR="")
        assert salida.returncode == 2
        assert "no está arrancado" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_sin_subred_declarada(self, entorno):
        salida = entorno(env_file_texto="", STUB_SUBRED="")
        assert salida.returncode == 2
        assert "no declara subred" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_fuentes_que_no_cuadran_no_permiten_decidir(self, entorno):
        """`ufw status` y `ufw show added` tienen que decir lo mismo. Si no
        (reglas editadas a mano), no sé qué está en vigor."""
        salida = entorno(
            env_file_texto="",
            STUB_UFW_REGLAS_STATUS="9696  ALLOW  192.168.1.0/24",
            STUB_UFW_ANADIDAS="",
        )
        assert salida.returncode == 2
        assert "no puedo decirte qué reglas están en vigor" in texto(salida)
        assert "ufw allow from" not in salida.stdout

    def test_ipv6_duplica_las_lineas_de_status_y_no_es_indeterminado(self, entorno):
        """Con IPv6 habilitado, cada orden aparece como dos reglas activas (la
        IPv4 y la IPv6). Eso es normal y no puede convertir A10 en un falso
        «no puedo determinarlo»."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 192.168.1.0/24 to any port 22 proto tcp\n"
                              "ufw allow from 192.168.1.0/24 to any port 9091 proto tcp",
            STUB_UFW_REGLAS_STATUS=(
                "22/tcp                     ALLOW       Anywhere\n"
                "22/tcp                     ALLOW       Anywhere (v6)\n"
                "9091                       ALLOW       192.168.1.0/24\n"
                "9091                       ALLOW       192.168.1.0/24 (v6)"
            ),
        )
        assert salida.returncode == 1          # decide, no se declara indeterminado
        assert "IPv6" in texto(salida)          # y lo dice
        assert "sudo ufw allow from 172.18.0.0/16 to any port 9696 proto tcp" in salida.stdout

    def test_menos_reglas_activas_que_ordenadas_no_decide(self, entorno):
        """Si `status` tiene MENOS reglas que `show added`, hay órdenes que ya
        no están en vigor: no sé qué está activo."""
        salida = entorno(
            args=["--puerto", "9696"],
            STUB_UFW_ANADIDAS="ufw allow from 192.168.1.0/24 to any port 22 proto tcp\n"
                              "ufw allow from 192.168.1.0/24 to any port 9091 proto tcp",
            STUB_UFW_REGLAS_STATUS="22/tcp ALLOW Anywhere",
        )
        assert salida.returncode == 2
        assert "no puedo decirte qué reglas están en vigor" in texto(salida)
        assert "ufw allow from" not in salida.stdout


class TestNuncaAplicaNada:

    def test_solo_se_le_pide_status_y_show(self, entorno):
        """El script no puede ejecutar nada de ufw que cambie reglas."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        llamadas = [
            linea for linea in entorno.registro.read_text().splitlines()
            if linea.startswith("ufw ")
        ]
        assert llamadas, "el doble de ufw no registró nada"
        for llamada in llamadas:
            assert llamada in ("ufw status", "ufw show added", "ufw status numbered"), llamada

    def test_lo_dice_en_la_salida(self, entorno):
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "No he ejecutado nada" in texto(salida)

    def test_no_cambia_el_env_ni_crea_ficheros(self, entorno, tmp_path):
        antes = sorted(p.name for p in tmp_path.iterdir())
        entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        despues = sorted(p.name for p in tmp_path.iterdir())
        assert antes == despues


class TestUtilidades:
    """La parte delicada, aislada: contención de subredes y parser de reglas.

    Se carga solo el trozo de utilidades del script (hasta donde empieza a
    ejecutar), que es puro: no llama a docker ni a ufw."""

    def _bash(self, cuerpo: str, tmp_path: Path):
        # Se cargan las utilidades desde un fichero de verdad: el script usa
        # ${BASH_SOURCE[0]} para situarse, y con `bash -c` no existe.
        utilidades = SCRIPT.read_text()[: SCRIPT.read_text().index(
            "# ── ¿hay algo que comprobar?")]
        fichero = tmp_path / "utilidades.sh"
        fichero.write_text(utilidades)
        return subprocess.run(
            ["bash", "-c", f'source "{fichero}"\n{cuerpo}'],
            capture_output=True, text=True, timeout=30, check=False,
        )

    @pytest.mark.parametrize(("regla", "subred", "cubre"), [
        ("172.16.0.0/12", "172.18.0.0/16", True),    # la regla que recomienda el README
        ("172.16.0.0/12", "172.17.0.0/16", True),
        ("172.17.0.0/16", "172.18.0.0/16", False),   # la subred equivocada del caso real
        ("172.18.0.0/16", "172.18.0.0/16", True),
        ("172.18.1.0/24", "172.18.0.0/16", False),   # máscara más larga: no contiene
        ("10.0.0.0/8", "172.18.0.0/16", False),
        ("0.0.0.0/0", "172.18.0.0/16", True),
        ("192.168.1.0/24", "172.18.0.0/16", False),
        ("172.18.0.0", "172.18.0.0/32", True),       # sin máscara = /32
        ("no-es-una-ip", "172.18.0.0/16", False),    # no revienta: no cubre
    ])
    def test_contencion_cidr(self, tmp_path, regla, subred, cubre):
        salida = self._bash(
            f'if cidr_contiene "{regla}" "{subred}"; then echo SI; else echo NO; fi\n',
            tmp_path)
        assert salida.stdout.strip() == ("SI" if cubre else "NO")

    @pytest.mark.parametrize(("linea", "esperado"), [
        # acción | interfaz | proto | origen | dirección destino | puertos
        ("ufw allow from 172.16.0.0/12 to any port 9696 proto tcp",
         "allow||tcp|172.16.0.0/12|any|9696"),
        ("ufw allow 9696/tcp", "allow|||any|any|9696/tcp"),
        ("ufw allow from 10.0.0.0/8 to 192.168.1.5 port 25",
         "allow|||10.0.0.0/8|192.168.1.5|25"),
        ("ufw deny proto tcp to any port 80", "deny||tcp|any|any|80"),
        ("ufw allow in on eth0 from 192.168.1.0/24 to any port 9091",
         "allow|eth0||192.168.1.0/24|any|9091"),
        ("ufw limit 2222/tcp comment 'SSH port'", "limit|||any|any|2222/tcp"),
        # Lo que no se entiende se marca "?", no se da por bueno.
        ("ufw allow proto udp from 172.18.0.0/16 to any port 9696",
         "allow||udp|172.18.0.0/16|any|9696"),
        ("ufw allow smtp", "allow|||any|any|?"),
        ("ufw allow to 10.0.0.0/8", "allow|||any|10.0.0.0/8|any"),
        ("ufw allow from cualquier-cosa", "allow|||?|any|any"),
        ("ufw allow out on eth1 to 10.0.0.0/8", "FALLA"),          # saliente
        ("ufw route allow in on eth0 from 10.0.0.0/8", "FALLA"),    # route
        ("", "FALLA"),
    ])
    def test_parser_de_reglas(self, tmp_path, linea, esperado):
        salida = self._bash(f'normalizar_regla "{linea}" || echo FALLA\n', tmp_path)
        assert salida.stdout.strip() == esperado

    @pytest.mark.parametrize(("expr", "puerto", "cubre"), [
        ("any", 9696, True),
        ("9696", 9696, True),
        ("9696/tcp", 9696, True),
        ("9696/udp", 9696, False),        # no es este tráfico
        ("80,443,9696", 9696, True),
        ("8080:8090", 9696, False),
        ("8080:8090", 8085, True),
        ("8080:8090/tcp", 8085, True),
        ("smtp", 25, False),              # nombre de servicio: no se puede afirmar
        ("", 9696, True),                 # sin cláusula `to`: todos los puertos
    ])
    def test_rango_de_puertos(self, tmp_path, expr, puerto, cubre):
        salida = self._bash(
            f'if rango_cubre "{expr}" {puerto}; then echo SI; else echo NO; fi\n',
            tmp_path)
        assert salida.stdout.strip() == ("SI" if cubre else "NO")

    @pytest.mark.parametrize(("url", "esperado"), [
        ("http://host.docker.internal:9696", "host.docker.internal 9696"),
        ("http://127.0.0.1:9091/", "127.0.0.1 9091"),
        ("http://192.168.1.50", "192.168.1.50 "),
        ("http://usuario:clave@host.docker.internal:4711", "host.docker.internal 4711"),
        ("host.docker.internal:9696", "host.docker.internal 9696"),
    ])
    def test_partir_la_url(self, tmp_path, url, esperado):
        salida = self._bash(f'url_partes "{url}"\n', tmp_path)
        assert salida.stdout.strip() == esperado.strip()
