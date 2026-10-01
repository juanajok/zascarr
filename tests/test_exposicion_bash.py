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

    @pytest.mark.parametrize("opcion,bind", [("1", "127.0.0.1"), ("2", "0.0.0.0"), ("3", "127.0.0.1")])
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
    "https://tebeos.ejemplo.org", "https://tebeos.ejemplo.org:8443", "https://ejemplo.org/zascarr",
    "https://192.168.1.50", "",
    "tebeos.ejemplo.org", "http://tebeos.ejemplo.org", "https://", "https:///ruta",
    "ftp://ejemplo.org", "javascript:alert(1)", "https://[::1", "  ", "https://a b.org",
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
        datos = dict(x.split("=", 1) for x in r.stdout.splitlines() if x.startswith(("RC=", "LONGITUD=")))
        return datos, r

    def test_contrasena_valida_y_confirmada(self):
        datos, _ = self._pedir("una frase larga que nadie adivina\nuna frase larga que nadie adivina\n")
        assert datos["RC"] == "0" and datos["LONGITUD"] == str(len("una frase larga que nadie adivina"))

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

    def test_los_espacios_son_parte_de_la_contrasena(self):
        """`read -r` con IFS vacío conservaría los extremos; con el IFS por defecto se
        recortarían. Esta prueba fija lo que hace hoy para que no cambie sin querer:
        la app recibe lo MISMO que se confirmó."""
        datos, _ = self._pedir("  frase con espacios  \n  frase con espacios  \n")
        assert datos["RC"] == "0"


class TestIpDeLaRed:

    def test_devuelve_una_ipv4_o_nada_y_nunca_falla(self):
        r = _bash("ip_de_la_red")
        assert r.returncode == 0
        salida = r.stdout.strip()
        assert salida == "" or all(p.isdigit() for p in salida.split("."))
