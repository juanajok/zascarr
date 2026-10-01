"""A11 — la elección de exposición del instalador (`scripts/_exposicion.sh`).

La lógica vive en Bash porque la usa `bootstrap.sh` en el host, antes de que
exista nada instalado. Aquí se carga en un `bash` de verdad. Lo que se protege:

- **Nunca se abre por error**: una respuesta ilegible, una URL sin HTTPS o una
  contraseña que no se consigue acaban en «solo esta máquina».
- La validación de la URL pública es **la misma** que la de la app (paridad con
  `services/seguridad.py::url_publica_valida`, con los mismos casos).
- La contraseña no sale por la salida ni se escribe en ningún sitio.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from zascarr.services.seguridad import url_publica_valida

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="requiere bash")

SH = Path(__file__).resolve().parents[1] / "scripts" / "_exposicion.sh"


def _bash(cuerpo: str, stdin: str | None = None):
    guion = f'set -uo pipefail\nsource "{SH}"\n{cuerpo}\n'
    return subprocess.run(
        ["bash", "-c", guion], capture_output=True, text=True, input=stdin,
        timeout=30, check=False,
    )


class TestExposicionABind:

    @pytest.mark.parametrize(
        "opcion,bind", [("1", "127.0.0.1"), ("2", "0.0.0.0"), ("3", "127.0.0.1")])
    def test_traduccion(self, opcion, bind):
        r = _bash(f"exposicion_a_bind {opcion}")
        assert r.returncode == 0 and r.stdout.strip() == bind

    @pytest.mark.parametrize("opcion", ["", "0", "4", "lan", "2 "])
    def test_opcion_invalida_falla(self, opcion):
        assert _bash(f'exposicion_a_bind "{opcion}"').returncode == 1

    def test_solo_la_opcion_2_publica_fuera_de_localhost(self):
        """La 3 también deja el puerto en localhost: lo expuesto es el proxy."""
        salida = {o: _bash(f"exposicion_a_bind {o}").stdout.strip() for o in "123"}
        assert [o for o, b in salida.items() if b != "127.0.0.1"] == ["2"]


class TestExposicionActual:
    """Qué se propone por defecto al volver a ejecutar el instalador."""

    @pytest.mark.parametrize("bind,base_url,esperada", [
        ("", "", "1"),
        ("127.0.0.1", "", "1"),
        ("localhost", "", "1"),
        ("[::1]", "", "1"),
        ("0.0.0.0", "", "2"),
        ("192.168.1.50", "", "2"),
        ("127.0.0.1", "https://tebeos.ejemplo.org", "3"),
        ("127.0.0.1", "http://tebeos.ejemplo.org", "1"),      # sin https no cuenta como proxy
        ("127.0.0.1", "https://localhost", "1"),
        ("0.0.0.0", "https://tebeos.ejemplo.org", "2"),       # el puerto abierto manda
    ])
    def test_casos(self, bind, base_url, esperada):
        r = _bash(f'exposicion_actual "{bind}" "{base_url}"')
        assert r.stdout.strip() == esperada


CASOS_URL = [
    "https://tebeos.ejemplo.org", "https://tebeos.ejemplo.org:8443", "https://localhost",
    "https://192.168.1.50", "https://xn--ndalo-ysa.es", "https://a.org:1", "https://a.org:65535",
    "", "  ", "tebeos.ejemplo.org", "http://tebeos.ejemplo.org", "https://", "https:///ruta",
    "ftp://ejemplo.org", "javascript:alert(1)", "https://a b.org", "https://u@a.org",
    "https://ejemplo.org/zascarr", "https://ejemplo.org/", "https://a.org?x=1",
    "https://a.org:0", "https://a.org:65536", "https://a.org:99999", "https://a.org:",
    "https://999.1.1.1", "https://1.2.3", "https://1.2.3.4.5", "https://01.2.3.4",
    "https://256.0.0.1", "https://[::1]", "https://[2001:db8::1]:8443", "https://[::1",
    "https://a..org", "https://.a.org", "https://a.org.", "https://-a.org", "https://a-.org",
    "https://" + "a" * 64 + ".org", "https://" + ".".join(["abcdefghi"] * 30) + ".org",
]


class TestUrlPublicaValida:

    @pytest.mark.parametrize("url", CASOS_URL)
    def test_misma_regla_que_la_app(self, url):
        """Si el instalador aceptara lo que la app rechaza (o al revés), la opción 3
        dejaría una `BASE_URL` que luego no sirve."""
        en_bash = _bash(f'url_publica_valida "{url}"').returncode == 0
        assert en_bash == url_publica_valida(url), url


class TestContrasenaSuficiente:

    def test_el_limite_exacto(self):
        assert _bash('contrasena_suficiente "abcdefghijk"').returncode == 1       # 11
        assert _bash('contrasena_suficiente "abcdefghijkl"').returncode == 0      # 12

    def test_vacia_no_vale(self):
        assert _bash('contrasena_suficiente ""').returncode == 1


class TestPreguntarExposicion:

    def _preguntar(self, entrada: str, defecto: str = "1"):
        r = _bash(
            f'preguntar_exposicion {defecto}\n'
            'echo "OPCION=$EXPOSICION_OPCION BIND=$ZASCARR_BIND_ADDRESS URL=$BASE_URL_PUBLICA"',
            stdin=entrada,
        )
        linea = [x for x in r.stdout.splitlines() if x.startswith("OPCION=")][-1]
        return dict(p.split("=", 1) for p in linea.split(" ")), r

    def test_intro_acepta_el_valor_por_defecto_seguro(self):
        datos, _ = self._preguntar("\n")
        assert datos == {"OPCION": "1", "BIND": "127.0.0.1", "URL": ""}

    def test_sin_entrada_cae_en_solo_esta_maquina(self):
        """Sin terminal el instalador no pregunta; si `read` llegara a leer EOF, nada se abre."""
        datos, _ = self._preguntar("")
        assert datos["OPCION"] == "1" and datos["BIND"] == "127.0.0.1"

    def test_opcion_2_abre_a_la_red(self):
        datos, _ = self._preguntar("2\n")
        assert datos == {"OPCION": "2", "BIND": "0.0.0.0", "URL": ""}

    def test_opcion_3_pide_url_y_deja_el_puerto_en_localhost(self):
        datos, _ = self._preguntar("3\nhttps://tebeos.ejemplo.org/\n")
        assert datos == {"OPCION": "3", "BIND": "127.0.0.1", "URL": "https://tebeos.ejemplo.org"}

    @pytest.mark.parametrize("respuesta", ["4", "lan", "dos", "0", "  "])
    def test_respuesta_ilegible_nunca_abre(self, respuesta):
        datos, r = self._preguntar(respuesta + "\n")
        assert datos["OPCION"] == "1" and datos["BIND"] == "127.0.0.1"

    def test_en_una_instalacion_nueva_el_prompt_dice_que_intro_deja_solo_esta_maquina(self):
        _, r = self._preguntar("\n")
        assert "Intro lo deja solo en esta máquina" in r.stdout

    def test_al_reejecutar_el_prompt_dice_que_intro_mantiene_lo_actual(self):
        """Intro acepta la opción ACTUAL, que puede ser abrir a la red: el menú lo dice."""
        _, r = self._preguntar("\n", defecto="2")
        assert "Ahora mismo está: abierto a tu red local" in r.stdout
        assert "Intro lo mantiene" in r.stdout

    def test_la_opcion_por_defecto_la_marca_quien_llama(self):
        datos, _ = self._preguntar("\n", defecto="2")
        assert datos["OPCION"] == "2"

    def test_tres_urls_invalidas_en_la_opcion_3_vuelven_a_la_1(self):
        datos, r = self._preguntar("3\nhttp://sin-tls.org\nmi dominio\nftp://x.org\n")
        assert datos["OPCION"] == "1" and datos["BIND"] == "127.0.0.1" and datos["URL"] == ""
        assert "solo esta máquina" in r.stderr

    def test_la_tercera_url_buena_se_acepta(self):
        datos, _ = self._preguntar("3\nmala\nhttp://mala.org\nhttps://buena.org\n")
        assert datos["OPCION"] == "3" and datos["URL"] == "https://buena.org"


class TestPedirContrasenaAcceso:

    def _pedir(self, entrada: str):
        r = _bash(
            'pedir_contrasena_acceso; rc=$?\n'
            'echo "RC=$rc"\n'
            'echo "LONGITUD=${#CONTRASENA_ACCESO}"',
            stdin=entrada,
        )
        datos = dict(
            x.split("=", 1) for x in r.stdout.splitlines() if x.startswith(("RC=", "LONGITUD=")))
        return datos, r

    def test_contrasena_valida_y_confirmada(self):
        frase = "una frase larga que nadie adivina"
        datos, _ = self._pedir(f"{frase}\n{frase}\n")
        assert datos["RC"] == "0" and datos["LONGITUD"] == str(len(frase))

    def test_corta_se_reintenta(self):
        datos, r = self._pedir("corta\nuna frase larga de verdad\nuna frase larga de verdad\n")
        assert datos["RC"] == "0"
        assert "demasiado corta" in r.stderr

    def test_no_coinciden_se_reintenta(self):
        buena = "una frase larga de verdad"
        datos, r = self._pedir(f"{buena}\notra distinta aunque larga\n{buena}\n{buena}\n")
        assert datos["RC"] == "0" and "No coinciden" in r.stderr

    def test_tres_fallos_devuelven_1_y_no_dejan_nada(self):
        datos, _ = self._pedir("a\nb\nc\n")
        assert datos["RC"] == "1" and datos["LONGITUD"] == "0"

    def test_sin_entrada_devuelve_1(self):
        datos, _ = self._pedir("")
        assert datos["RC"] == "1" and datos["LONGITUD"] == "0"

    def test_la_contrasena_no_sale_por_la_salida(self):
        secreta = "esta es una frase secreta larga"
        _, r = self._pedir(f"{secreta}\n{secreta}\n")
        assert secreta not in r.stdout + r.stderr

    def test_los_espacios_de_los_extremos_son_parte_de_la_contrasena(self):
        """`read -r` sin `IFS=` recorta los espacios de los extremos: la contraseña que se
        confirmó y la que llega a la app serían distintas."""
        contrasena = "  frase con espacios  "
        datos, _ = self._pedir(f"{contrasena}\n{contrasena}\n")
        assert datos["RC"] == "0"
        assert datos["LONGITUD"] == str(len(contrasena))


class TestIpDeLaRed:

    def test_devuelve_una_ipv4_o_nada_y_nunca_falla(self):
        r = _bash("ip_de_la_red")
        assert r.returncode == 0
        salida = r.stdout.strip()
        assert salida == "" or all(p.isdigit() for p in salida.split("."))


class TestDescripcionYResumen:

    @pytest.mark.parametrize("opcion,texto", [
        ("1", "solo esta máquina"), ("2", "red local"), ("3", "proxy"), ("", "solo esta máquina"),
    ])
    def test_descripcion(self, opcion, texto):
        assert texto in _bash(f'exposicion_descripcion "{opcion}"').stdout

    def test_resumen_de_solo_esta_maquina_explica_como_abrir(self):
        salida = _bash('resumen_exposicion 1 ""').stdout
        assert "opción 2" in salida and "http://" not in salida

    def test_resumen_de_red_da_la_direccion_y_avisa_del_router(self):
        salida = _bash('ip_de_la_red() { echo 192.168.1.50; }\nresumen_exposicion 2 ""').stdout
        assert "http://192.168.1.50:8000" in salida
        assert "router" in salida

    def test_resumen_de_red_sin_ip_no_inventa_una(self):
        salida = _bash('ip_de_la_red() { :; }\nresumen_exposicion 2 ""').stdout
        assert "<la IP de este equipo>" in salida

    def test_resumen_de_proxy_deja_claro_que_el_proxy_lo_pone_el_operador(self):
        salida = _bash('resumen_exposicion 3 "https://tebeos.ejemplo.org"').stdout
        assert "tebeos.ejemplo.org {" in salida
        assert "reverse_proxy 127.0.0.1:8000" in salida
        assert "los pones tú" in salida


@pytest.fixture
def docker_doble(tmp_path):
    """Un `docker` de pega en el PATH: registra los argumentos y lo que llega por
    stdin a `fijar-contrasena`, y devuelve los códigos que pida cada prueba.

    Como el `docker compose run -T` real, **consume la entrada estándar** también en
    `estado` (hallazgo de la verificación en vivo: sin esto, `estado` se tragaba la
    contraseña que el instalador acababa de recibir)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    doble = bin_ / "docker"
    doble.write_text(
        '#!/usr/bin/env bash\n'
        'echo "$*" >> "$DOBLE_LOG"\n'
        'case "$*" in\n'
        '  *"cli.seguridad estado"*) cat > /dev/null; exit "${DOBLE_ESTADO_RC:-3}" ;;\n'
        '  *"cli.seguridad fijar-contrasena"*)\n'
        '    cat > "$DOBLE_STDIN"; exit "${DOBLE_FIJAR_RC:-0}" ;;\n'
        # `efectiva`: la BASE_URL efectiva es la de Ajustes si hay, y si no la del .env
        # (la misma precedencia que la app); la exposición se deduce de ella y del bind.
        '  *"cli.seguridad efectiva"*)\n'
        '    cat > /dev/null\n'
        '    base="$(cat "$DOBLE_DB_BASE_URL" 2>/dev/null)"\n'
        '    [ -z "$base" ] && base="$(cat "$DOBLE_ENV_BASE_URL" 2>/dev/null)"\n'
        '    if [ "${DOBLE_BIND:-127.0.0.1}" != "127.0.0.1" ]; then nivel=red\n'
        '    elif [ -n "$base" ] && [[ "$base" != *localhost* ]]; then nivel=proxy\n'
        '    else nivel=local; fi\n'
        '    echo "exposicion=$nivel"; echo "contrasena=${DOBLE_CONTRASENA:-no}"\n'
        '    echo "base_url=$base"; exit "${DOBLE_EFECTIVA_RC:-0}" ;;\n'
        '  *"cli.seguridad retirar-base-url"*)\n'
        '    cat > /dev/null; : > "$DOBLE_DB_BASE_URL"; exit "${DOBLE_RETIRAR_RC:-0}" ;;\n'
        '  *"port zascarr-orquestador"*)\n'
        '    printf "%s" "${DOBLE_PORT:-}"; exit "${DOBLE_PORT_RC:-0}" ;;\n'
        'esac\n'
        'exit 99\n'
    )
    doble.chmod(0o755)
    return {
        "bin": bin_, "log": tmp_path / "docker.log", "stdin": tmp_path / "docker.stdin",
        "env_base_url": tmp_path / "env_base_url", "db_base_url": tmp_path / "db_base_url",
        "tmp": tmp_path,
    }


def _asegurar(docker_doble, *, entrada="", interactivo="1", estado_rc="3", fijar_rc="0"):
    import os

    entorno = {
        **os.environ,
        "PATH": f"{docker_doble['bin']}:{os.environ['PATH']}",
        "DOBLE_LOG": str(docker_doble["log"]), "DOBLE_STDIN": str(docker_doble["stdin"]),
        "DOBLE_ESTADO_RC": estado_rc, "DOBLE_FIJAR_RC": fijar_rc,
        "DOBLE_ENV_BASE_URL": str(docker_doble["env_base_url"]),
        "DOBLE_DB_BASE_URL": str(docker_doble["db_base_url"]),
    }
    guion = (
        f'set -uo pipefail\nsource "{SH}"\n'
        'COMPOSE_FILE=/x/docker-compose.yml; ENV_FILE=/x/.env\n'
        f'EXPOSICION_INTERACTIVA={interactivo}\n'
        'asegurar_contrasena_de_acceso; rc=$?\n'
        'echo "RC=$rc LONG=${#CONTRASENA_ACCESO}"'
    )
    r = subprocess.run(["bash", "-c", guion], capture_output=True, text=True, input=entrada,
                       env=entorno, timeout=30, check=False)
    registro = docker_doble["log"].read_text() if docker_doble["log"].exists() else ""
    recibido = docker_doble["stdin"].read_text() if docker_doble["stdin"].exists() else None
    rc = [x for x in r.stdout.splitlines() if x.startswith("RC=")][-1]
    return rc, registro, recibido, r


FRASE = "una frase larga que nadie adivina"


class TestAsegurarContrasenaDeAcceso:

    def test_sin_contrasena_la_pide_y_la_fija_por_stdin(self, docker_doble):
        rc, registro, recibido, _ = _asegurar(docker_doble, entrada=f"{FRASE}\n{FRASE}\n")
        assert rc == "RC=0 LONG=0"                      # y no se queda en memoria
        assert recibido == FRASE + "\n"
        assert "fijar-contrasena" in registro

    def test_estado_no_se_traga_la_entrada_del_instalador(self, docker_doble):
        """`docker compose run -T` lee stdin aunque el comando no la use. La
        comprobación de `estado` va con `</dev/null`, o se llevaría las líneas de
        la contraseña y los `read` siguientes recibirían vacío."""
        rc, _, recibido, r = _asegurar(docker_doble, entrada=f"{FRASE}\n{FRASE}\n")
        assert rc.startswith("RC=0"), r.stderr
        assert recibido == FRASE + "\n"

    def test_los_espacios_de_los_extremos_llegan_tal_cual_a_la_app(self, docker_doble):
        """Lo que se confirmó es EXACTAMENTE lo que recibe el comando (no solo «hay éxito»)."""
        contrasena = "  una frase larga con espacios  "
        rc, _, recibido, _ = _asegurar(docker_doble, entrada=f"{contrasena}\n{contrasena}\n")
        assert rc.startswith("RC=0")
        assert recibido == contrasena + "\n"

    def test_la_contrasena_nunca_va_en_los_argumentos_de_docker(self, docker_doble):
        _, registro, _, r = _asegurar(docker_doble, entrada=f"{FRASE}\n{FRASE}\n")
        assert FRASE not in registro and FRASE not in r.stdout + r.stderr

    def test_ya_hay_y_sin_terminal_se_acepta_sin_tocar_nada(self, docker_doble):
        rc, registro, recibido, _ = _asegurar(docker_doble, interactivo="0", estado_rc="0")
        assert rc.startswith("RC=0") and recibido is None
        assert "fijar-contrasena" not in registro

    def test_ya_hay_e_intro_la_mantiene(self, docker_doble):
        rc, registro, recibido, _ = _asegurar(docker_doble, estado_rc="0", entrada="\n")
        assert rc.startswith("RC=0") and recibido is None

    def test_ya_hay_pero_se_quiere_cambiar(self, docker_doble):
        rc, _, recibido, _ = _asegurar(
            docker_doble, estado_rc="0", entrada=f"n\n{FRASE}\n{FRASE}\n")
        assert rc.startswith("RC=0") and recibido == FRASE + "\n"

    def test_sin_contrasena_y_sin_terminal_no_abre(self, docker_doble):
        rc, registro, recibido, r = _asegurar(docker_doble, interactivo="0", estado_rc="3")
        assert rc.startswith("RC=1") and recibido is None
        assert "no puedo pedírtela" in r.stderr

    def test_si_no_se_puede_comprobar_no_abre(self, docker_doble):
        """Ante la duda (base de datos caída, imagen sin construir…), cerrado."""
        rc, _, recibido, r = _asegurar(docker_doble, estado_rc="1")
        assert rc.startswith("RC=1") and recibido is None
        assert "No he podido comprobar" in r.stderr

    def test_tres_contrasenas_cortas_no_abren_ni_llaman_a_fijar(self, docker_doble):
        rc, registro, recibido, _ = _asegurar(docker_doble, entrada="a\nb\nc\n")
        assert rc.startswith("RC=1")
        assert "fijar-contrasena" not in registro

    def test_si_la_app_rechaza_la_contrasena_no_abre(self, docker_doble):
        rc, _, _, _ = _asegurar(docker_doble, entrada=f"{FRASE}\n{FRASE}\n", fijar_rc="2")
        assert rc == "RC=1 LONG=0"


class TestOrdenEnBootstrap:
    """La invariante de seguridad de A11, comprobada sobre el propio instalador:
    la contraseña existe ANTES de que el puerto pueda abrirse."""

    @staticmethod
    def _lineas():
        texto = (Path(__file__).resolve().parents[1] / "bootstrap.sh").read_text(encoding="utf-8")
        return texto.splitlines()

    def _indice(self, fragmento: str) -> int:
        lineas = [i for i, linea in enumerate(self._lineas())
                  if fragmento in linea and not linea.lstrip().startswith("#")]
        assert lineas, f"no encuentro {fragmento!r} en bootstrap.sh"
        return lineas[0]

    def test_migra_luego_fija_la_contrasena_luego_escribe_la_direccion_luego_levanta_la_app(self):
        migrar = self._indice("alembic upgrade head")
        contrasena = self._indice("! asegurar_contrasena_de_acceso")
        escribir = self._indice('set_env_var "ZASCARR_BIND_ADDRESS"')
        levantar = self._indice("up -d --force-recreate zascarr")
        assert migrar < contrasena < escribir < levantar

    def test_un_contenedor_ya_abierto_se_para_antes_de_lo_que_pueda_fallar(self):
        """Escribir 127.0.0.1 en el .env no cierra el puerto de un contenedor ya creado."""
        parar = self._indice("stop zascarr")
        comprobar = self._indice("contenedor_abierto_a_la_red; then")
        assert comprobar < parar < self._indice("up -d postgres redis")
        assert parar < self._indice("alembic upgrade head")

    def test_la_aplicacion_se_recrea_siempre(self):
        """`up -d` no recrea si Compose no ve cambios: la app seguiría con la contraseña
        ANTIGUA en memoria (verificado en vivo)."""
        assert "--force-recreate zascarr" in "\n".join(self._lineas())

    def test_se_reconcilia_la_base_url_y_se_verifica_lo_efectivo_antes_de_arrancar(self):
        contrasena = self._indice("! asegurar_contrasena_de_acceso")
        base_url = self._indice("! ajustar_base_url")
        escribir = self._indice('set_env_var "ZASCARR_BIND_ADDRESS"')
        verificar = self._indice("verificar_exposicion_efectiva ||")
        levantar = self._indice("up -d --force-recreate zascarr")
        assert contrasena < base_url < escribir < verificar < levantar

    def test_la_direccion_de_publicacion_no_se_escribe_antes_de_la_contrasena(self):
        """Hay una sola escritura de ZASCARR_BIND_ADDRESS y es posterior al paso de contraseña."""
        escrituras = [i for i, linea in enumerate(self._lineas())
                      if 'set_env_var "ZASCARR_BIND_ADDRESS"' in linea
                      and not linea.lstrip().startswith("#")]
        assert len(escrituras) == 1

    def test_si_no_se_consigue_contrasena_se_vuelve_a_solo_esta_maquina(self):
        texto = "\n".join(self._lineas())
        i = texto.index("volver_a_solo_esta_maquina() {")
        funcion = texto[i:texto.index("}", i)]
        assert 'ZASCARR_BIND_ADDRESS="127.0.0.1"' in funcion
        assert "EXPOSICION_OPCION=1" in funcion
        j = texto.index("! asegurar_contrasena_de_acceso")
        assert "volver_a_solo_esta_maquina" in texto[j:j + 600]


def _con_doble(docker_doble, cuerpo: str, *, env: dict | None = None):
    """Ejecuta `cuerpo` con el `docker` de pega, un `set_env_var` que escribe en un fichero
    y el estado (`.env` y Ajustes) en ficheros: así se prueban TRANSICIONES, no fotos fijas."""
    import os

    entorno = {
        **os.environ,
        "PATH": f"{docker_doble['bin']}:{os.environ['PATH']}",
        "DOBLE_LOG": str(docker_doble["log"]), "DOBLE_STDIN": str(docker_doble["stdin"]),
        "DOBLE_ENV_BASE_URL": str(docker_doble["env_base_url"]),
        "DOBLE_DB_BASE_URL": str(docker_doble["db_base_url"]),
        **(env or {}),
    }
    guion = (
        f'set -uo pipefail\nsource "{SH}"\n'
        'COMPOSE_FILE=/x/docker-compose.yml; ENV_FILE=/x/.env\n'
        'set_env_var() { [[ "$1" == BASE_URL ]] && '
        'printf "%s" "$2" > "$DOBLE_ENV_BASE_URL"; return 0; }\n'
        f'{cuerpo}'
    )
    return subprocess.run(["bash", "-c", guion], capture_output=True, text=True,
                          env=entorno, timeout=30, check=False)


def _estado(docker_doble, *, env_url: str = "", db_url: str = ""):
    docker_doble["env_base_url"].write_text(env_url)
    docker_doble["db_base_url"].write_text(db_url)


def _efectiva_tras(docker_doble, opcion: str, url: str = "", **env):
    """Aplica `ajustar_base_url` y devuelve (rc, efectiva) leyendo lo que ve la app."""
    r = _con_doble(
        docker_doble,
        f'ajustar_base_url {opcion} "{url}"; rc=$?\n'
        'leer_efectiva\n'
        'echo "RC=$rc EXP=$EFECTIVA_EXPOSICION URL=$EFECTIVA_BASE_URL"',
        env=env,
    )
    linea = [x for x in r.stdout.splitlines() if x.startswith("RC=")][-1]
    return dict(p.split("=", 1) for p in linea.split(" ")), r


class TestTransicionesDeLaBaseUrl:
    """La BASE_URL puede estar en el `.env` Y guardada en Ajustes, y la de Ajustes manda.
    El instalador deja UNA fuente de verdad y cuenta lo EFECTIVO."""

    def test_solo_esta_maquina_a_proxy(self, docker_doble):
        _estado(docker_doble)
        datos, _ = _efectiva_tras(docker_doble, "3", "https://tebeos.ejemplo.org")
        assert datos == {"RC": "0", "EXP": "proxy", "URL": "https://tebeos.ejemplo.org"}

    def test_proxy_a_solo_esta_maquina_no_deja_un_proxy_fantasma(self, docker_doble):
        _estado(docker_doble, env_url="https://tebeos.ejemplo.org")
        datos, _ = _efectiva_tras(docker_doble, "1")
        assert datos == {"RC": "0", "EXP": "local", "URL": ""}
        assert docker_doble["env_base_url"].read_text() == ""

    def test_proxy_a_a_proxy_b_con_un_override_previo_en_ajustes(self, docker_doble):
        """El caso del revisor: Ajustes guarda A, el instalador configura B. Sin retirar el
        override, la app seguiría usando A."""
        _estado(docker_doble, env_url="https://a.ejemplo.org", db_url="https://a.ejemplo.org")
        datos, _ = _efectiva_tras(docker_doble, "3", "https://b.ejemplo.org")
        assert datos["URL"] == "https://b.ejemplo.org"
        assert docker_doble["db_base_url"].read_text() == ""

    def test_una_publica_solo_en_ajustes_se_retira_al_cerrar(self, docker_doble):
        """El `.env` está limpio pero Ajustes guardó una pública: seguía expuesto «a escondidas»."""
        _estado(docker_doble, env_url="", db_url="https://escondida.ejemplo.org")
        datos, r = _efectiva_tras(docker_doble, "1")
        assert datos["EXP"] == "local" and datos["URL"] == ""
        assert "Retiro la dirección pública anterior" in r.stderr

    def test_la_opcion_2_tambien_retira_una_publica_antigua(self, docker_doble):
        _estado(docker_doble, env_url="https://a.ejemplo.org", db_url="https://a.ejemplo.org")
        datos, _ = _efectiva_tras(docker_doble, "2", DOBLE_BIND="0.0.0.0")
        assert datos["URL"] == "" and datos["EXP"] == "red"

    def test_una_url_local_guardada_en_ajustes_no_se_toca(self, docker_doble):
        """No es pública: no es asunto del instalador."""
        _estado(docker_doble, db_url="http://localhost:8000")
        datos, _ = _efectiva_tras(docker_doble, "1")
        assert datos["URL"] == "http://localhost:8000"
        assert docker_doble["db_base_url"].read_text() == "http://localhost:8000"

    def test_si_no_se_puede_leer_la_efectiva_falla_y_no_toca_nada(self, docker_doble):
        _estado(docker_doble, env_url="https://a.ejemplo.org")
        datos, _ = _efectiva_tras(docker_doble, "1", DOBLE_EFECTIVA_RC="1")
        assert datos["RC"] == "1"
        assert docker_doble["env_base_url"].read_text() == "https://a.ejemplo.org"

    def test_si_no_se_puede_retirar_el_override_falla(self, docker_doble):
        _estado(docker_doble, db_url="https://a.ejemplo.org")
        datos, _ = _efectiva_tras(docker_doble, "3", "https://b.ejemplo.org", DOBLE_RETIRAR_RC="1")
        assert datos["RC"] == "1"


class TestVerificarExposicionEfectiva:

    def _verificar(self, docker_doble, **env):
        r = _con_doble(docker_doble, 'verificar_exposicion_efectiva; echo "RC=$?"', env=env)
        return [x for x in r.stdout.splitlines() if x.startswith("RC=")][-1]

    def test_solo_esta_maquina_es_seguro_sin_contrasena(self, docker_doble):
        _estado(docker_doble)
        assert self._verificar(docker_doble) == "RC=0"

    def test_abierto_a_la_red_sin_contrasena_no(self, docker_doble):
        _estado(docker_doble)
        assert self._verificar(docker_doble, DOBLE_BIND="0.0.0.0") == "RC=1"

    def test_abierto_a_la_red_con_contrasena_si(self, docker_doble):
        _estado(docker_doble)
        assert self._verificar(docker_doble, DOBLE_BIND="0.0.0.0", DOBLE_CONTRASENA="si") == "RC=0"

    def test_una_publica_efectiva_sin_contrasena_no(self, docker_doble):
        """Aunque el `.env` diga localhost: manda lo que guardó Ajustes."""
        _estado(docker_doble, db_url="https://a.ejemplo.org")
        assert self._verificar(docker_doble) == "RC=1"

    def test_si_no_se_puede_comprobar_no_se_da_por_seguro(self, docker_doble):
        _estado(docker_doble)
        assert self._verificar(docker_doble, DOBLE_EFECTIVA_RC="1") == "RC=1"


class TestContenedorAbiertoALaRed:
    """Mira lo que Docker publicó de verdad, no lo que dice el `.env`."""

    def _abierto(self, docker_doble, salida: str, rc: str = "0"):
        r = _con_doble(docker_doble, 'contenedor_abierto_a_la_red; echo "RC=$?"',
                       env={"DOBLE_PORT": salida, "DOBLE_PORT_RC": rc})
        return [x for x in r.stdout.splitlines() if x.startswith("RC=")][-1] == "RC=0"

    def test_todas_las_interfaces(self, docker_doble):
        assert self._abierto(docker_doble, "0.0.0.0:8000\n[::]:8000\n")

    def test_una_ip_de_la_lan(self, docker_doble):
        assert self._abierto(docker_doble, "192.168.1.50:8000\n")

    def test_solo_localhost_no(self, docker_doble):
        assert not self._abierto(docker_doble, "127.0.0.1:8000\n")

    def test_localhost_ipv6_no(self, docker_doble):
        assert not self._abierto(docker_doble, "[::1]:8000\n")

    def test_una_publicacion_mixta_cuenta_como_abierta(self, docker_doble):
        assert self._abierto(docker_doble, "127.0.0.1:8000\n0.0.0.0:8000\n")

    def test_sin_contenedor_no(self, docker_doble):
        """`docker port` falla si el contenedor no existe: no hay nada abierto."""
        assert not self._abierto(docker_doble, "", rc="1")


class TestSubredReal:

    def _con_ip(self, tmp_path, ruta_get: str, ruta_show: str):
        bin_ = tmp_path / "binip"
        bin_.mkdir()
        doble = bin_ / "ip"
        doble.write_text(
            '#!/usr/bin/env bash\n'
            'case "$*" in\n'
            f'  *"route get"*) echo "{ruta_get}" ;;\n'
            f'  *"route show"*) echo "{ruta_show}" ;;\n'
            'esac\n'
        )
        doble.chmod(0o755)
        return bin_

    def _subred(self, bin_):
        import os

        r = subprocess.run(
            ["bash", "-c", f'source "{SH}"; subred_de_la_red'], capture_output=True, text=True,
            env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}, timeout=30, check=False)
        return r.stdout.strip()

    def test_da_la_subred_que_dice_el_sistema_no_una_deducida(self, tmp_path):
        """192.168.1.149 NO está siempre en un /24: aquí el sistema dice /23."""
        bin_ = self._con_ip(
            tmp_path, "1.1.1.1 via 192.168.0.1 dev eth0 src 192.168.1.149 uid 1000",
            "192.168.0.0/23 proto kernel src 192.168.1.149")
        assert self._subred(bin_) == "192.168.0.0/23"

    def test_si_no_hay_ruta_no_inventa_nada(self, tmp_path):
        assert self._subred(self._con_ip(tmp_path, "", "")) == ""

    def test_una_salida_rara_no_se_toma_por_subred(self, tmp_path):
        bin_ = self._con_ip(tmp_path, "1.1.1.1 dev eth0", "no es una subred")
        assert self._subred(bin_) == ""


class TestResumenDeRedYUfw:

    def _resumen(self, tmp_path, subred: str):
        import os

        bin_ = tmp_path / "binufw"
        bin_.mkdir()
        (bin_ / "ufw").write_text('#!/usr/bin/env bash\necho "Status: active"\n')
        (bin_ / "ufw").chmod(0o755)
        guion = (
            f'source "{SH}"\n'
            'ip_de_la_red() { echo 192.168.1.149; }\n'
            f'subred_de_la_red() {{ echo "{subred}"; }}\n'
            'resumen_exposicion 2 ""'
        )
        r = subprocess.run(["bash", "-c", guion], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}"}, check=False)
        return r.stdout

    def test_con_subred_conocida_propone_el_comando_con_esa_subred(self, tmp_path):
        salida = self._resumen(tmp_path, "192.168.0.0/23")
        assert "sudo ufw allow from 192.168.0.0/23 to any port 8000" in salida
        assert "/24" not in salida

    def test_sin_subred_no_propone_ningun_comando(self, tmp_path):
        salida = self._resumen(tmp_path, "")
        assert "sudo ufw allow" not in salida
        assert "No he podido saber tu subred" in salida


class TestExposicionAOpcion:

    @pytest.mark.parametrize("nivel,opcion", [
        ("local", "1"), ("red", "2"), ("proxy", "3"), ("", "1"), ("raro", "1")])
    def test_mapeo(self, nivel, opcion):
        assert _bash(f'exposicion_a_opcion "{nivel}"').stdout.strip() == opcion
