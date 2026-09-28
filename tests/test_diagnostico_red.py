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

DOCKER_STUB = r"""#!/usr/bin/env bash
# Doble de docker: responde por forma del argumento, no por coincidencia exacta.
args="$*"
[[ -n "${STUB_DOCKER_REGISTRO:-}" ]] && echo "docker $args" >> "${STUB_DOCKER_REGISTRO}"
case "$args" in
    *"ps -q zascarr"*) printf '%s\n' "${STUB_CONTENEDOR:-}"; exit 0 ;;
esac
if [[ "$args" == network\ inspect* ]]; then
    case "$args" in
        *IPAM.Config*)     printf '%s\n' "${STUB_SUBRED:-}"; exit 0 ;;
        *bridge.name*)     printf '%s\n' "${STUB_INTERFAZ:-}"; exit 0 ;;
        *".Id"*)           printf '%s\n' "${STUB_ID_RED:-}"; exit 0 ;;
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
    printf '%s\n' "${STUB_RESUELTO:-}"; exit 0
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
        printf '%s\n' "${STUB_UFW_REGLAS_STATUS:-}"
        ;;
    show)
        printf '%s\n' "${STUB_UFW_ANADIDAS:-}"
        ;;
esac
exit 0
"""

# Un escenario coherente por defecto: el contenedor está en 172.18.0.0/16 y
# host.docker.internal resuelve a su puerta de enlace real.
BASE = {
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

    def ejecutar(*, env_file_texto: str = "", args: list[str] | None = None, **stubs):
        env_file.write_text(env_file_texto)
        entorno_vars = dict(os.environ)
        entorno_vars["PATH"] = f"{bin_dir}:{entorno_vars['PATH']}"
        entorno_vars["ENV_FILE"] = str(env_file)
        entorno_vars["STUB_UFW_REGISTRO"] = str(registro)
        entorno_vars["STUB_DOCKER_REGISTRO"] = str(registro)
        for clave, valor in {**BASE, **stubs}.items():
            if valor is None:
                entorno_vars.pop(clave, None)
            else:
                entorno_vars[clave] = valor
        return subprocess.run(
            ["bash", str(SCRIPT), *(args or [])],
            capture_output=True, text=True, env=entorno_vars, timeout=60, check=False,
        )

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

    def test_un_deny_previo_cambia_la_propuesta(self, entorno):
        """Una regla nueva va al final: si un DENY casa antes, no serviría."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_UFW_ANADIDAS="ufw deny from 172.16.0.0/12 to any port 9696 proto tcp",
        )
        assert salida.returncode == 1
        assert "sudo ufw insert <número> allow from 172.18.0.0/16" in salida.stdout
        assert "DENIEGA" in texto(salida)


class TestRecorridoReal:

    def test_recorrido_bueno(self, entorno):
        salida = entorno(env_file_texto="", STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN)
        assert "es la puerta de enlace de su red" in texto(salida)

    def test_recorrido_roto_avisa_con_los_dos_valores(self, entorno):
        """Reproducción de la causa real del 2026-09-25 (docker0 vs red propia)."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://host.docker.internal:9696\n",
            STUB_RESUELTO="172.17.0.1",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert salida.returncode == 1
        assert "172.17.0.1" in salida.stdout
        assert "172.18.0.1" in salida.stdout
        assert "ninguna regla de ufw para la subred correcta lo arregla" in texto(salida)

    def test_no_se_puede_comprobar_el_recorrido(self, entorno):
        salida = entorno(env_file_texto="", STUB_RESUELTO=None, STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN)
        assert "queda sin comprobar" in texto(salida)


class TestPuertos:

    def test_url_a_otra_maquina_no_propone_regla(self, entorno):
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://192.168.1.50:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "otra máquina" in texto(salida)
        assert "9696 proto tcp" not in salida.stdout

    def test_url_a_127_0_0_1_es_un_error_de_configuracion(self, entorno):
        """Dentro del contenedor, 127.0.0.1 es el contenedor: ufw no lo arregla."""
        salida = entorno(
            env_file_texto="PROWLARR_URL=http://127.0.0.1:9696\n",
            STUB_UFW_ANADIDAS=REGLAS_SOLO_LAN,
        )
        assert "NO PUEDE FUNCIONAR" in texto(salida)
        assert "cámbialo por http://host.docker.internal:9696 en /ui/ajustes" in texto(salida)
        assert "9696 proto tcp" not in salida.stdout

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
        assert "sin subred declarada" in texto(salida)
        assert "ufw allow" not in salida.stdout

    def test_reglas_activas_que_no_puedo_leer(self, entorno):
        """Si `ufw show added` no me da las reglas, no propongo a ciegas."""
        salida = entorno(
            env_file_texto="",
            STUB_UFW_REGLAS_STATUS="9696  ALLOW  192.168.1.0/24",
            STUB_UFW_ANADIDAS="",
        )
        assert salida.returncode == 2
        assert "no puedo leerlas" in texto(salida)
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
        ("ufw allow from 172.16.0.0/12 to any port 9696 proto tcp",
         "allow||172.16.0.0/12|9696"),
        ("ufw allow 9696/tcp", "allow||any|9696/tcp"),
        ("ufw allow from 10.0.0.0/8 to 192.168.1.5 port 25", "allow||10.0.0.0/8|25"),
        ("ufw deny proto tcp to any port 80", "deny||any|80"),
        ("ufw allow in on eth0 from 192.168.1.0/24 to any port 9091",
         "allow|eth0|192.168.1.0/24|9091"),
        ("ufw limit 2222/tcp comment 'SSH port'", "limit||any|2222/tcp"),
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
