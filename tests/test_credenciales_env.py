"""Credenciales del `.env` en el instalador (hallazgos M4-01 y `.env` 0644).

Dos defectos medidos en el ensayo M4 (candidato 0a591d6, Debian 12, sin terminal):

1. **Instalación limpia imposible sin editar un fichero**: `bootstrap.sh` copiaba
   `.env.example` y después se negaba a seguir porque `DB_PASSWORD` seguía siendo
   el marcador `cambia_esto_ahora` (RC=1). El README promete «pegar una línea».
2. **`.env` legible por cualquiera**: se creaba con `cp` y la máscara por defecto
   (modo 644, `root:root`), de modo que `nobody` o cualquier cuenta local sin
   privilegios podía abrirlo. Contiene la contraseña de la base de datos.

La lógica vive en `scripts/_credenciales.sh` (Bash, sin dependencias) porque la
usa el instalador en el host antes de que exista nada. Aquí se carga en un `bash`
de verdad sobre un árbol sintético. No se arranca Docker ni se toca el `.env` de
quien ejecuta la suite.

Lo que se protege, por orden de riesgo:

- una contraseña válida **jamás** se pisa (reejecución idempotente);
- jamás se inventa una contraseña si ya existe una base de datos creada con otra
  (el instalador pararía el servicio con credenciales que no abren esa base);
- el valor generado no sale por la salida ni se escribe en ningún otro sitio;
- el `.env` nunca existe con un modo más abierto que 600, ni siquiera un instante,
  ni tras modificarlo.
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
    os.name != "posix" or shutil.which("bash") is None,
    reason="requiere bash en Linux",
)

REPO = Path(__file__).resolve().parents[1]
SH = REPO / "scripts" / "_credenciales.sh"
MARCADOR = "cambia_esto_ahora"
EJEMPLO = (
    "# Contraseña de la base de datos. Cámbiala por una segura.\n"
    f"DB_PASSWORD={MARCADOR}\n"
    "COMICVINE_API_KEY=\n"
    "TRANSMISSION_USERNAME=transmission\n"
    "FORUM_ENABLED=false\n"
)

# `info`/`warn`/`success`/`die` los define quien carga el fichero (bootstrap.sh,
# _comun.sh). Aquí imprimen con una etiqueta para poder comprobar qué se dijo.
PRELUDIO = r"""
set -uo pipefail
info()    { echo "INFO: $*"; }
success() { echo "OK: $*"; }
warn()    { echo "AVISO: $*"; }
die()     { echo "ERROR: $*" >&2; exit 1; }
"""


def _bash(cuerpo: str, *, umask: str = "022"):
    guion = f'umask {umask}\n{PRELUDIO}\nsource "{SH}"\n{cuerpo}\n'
    return subprocess.run(
        ["bash", "-c", guion], capture_output=True, text=True, timeout=30, check=False,
    )


def _modo(ruta: Path) -> int:
    return stat.S_IMODE(ruta.stat().st_mode)


@pytest.fixture
def entorno(tmp_path: Path) -> dict[str, Path]:
    datos = tmp_path / "datos"
    datos.mkdir()
    return {"env": tmp_path / ".env", "datos": datos, "ejemplo": tmp_path / ".env.example"}


def _crear_env(entorno, contenido: str = EJEMPLO, modo: int = 0o600) -> Path:
    entorno["env"].write_text(contenido)
    entorno["env"].chmod(modo)
    return entorno["env"]


def _valor(env: Path, clave: str) -> str | None:
    for linea in env.read_text().splitlines():
        if linea.startswith(f"{clave}="):
            return linea.split("=", 1)[1]
    return None


def _preparar(entorno):
    return _bash(f'preparar_credenciales "{entorno["env"]}" "{entorno["datos"]}"')


class TestGenerarContrasena:

    def test_longitud_y_alfabeto_seguros_para_url_y_sed(self):
        """Va dentro de `DATABASE_URL` y pasa por `sed`: sin `@ : / # & \\ %`."""
        r = _bash("generar_contrasena")
        valor = r.stdout.strip()
        assert r.returncode == 0
        assert re.fullmatch(r"[A-Za-z0-9]{32,}", valor), valor

    def test_dos_llamadas_dan_valores_distintos(self):
        a = _bash("generar_contrasena").stdout.strip()
        b = _bash("generar_contrasena").stdout.strip()
        assert a and b and a != b

    def test_nunca_devuelve_el_marcador(self):
        assert MARCADOR not in _bash("generar_contrasena").stdout


class TestMarcador:

    @pytest.mark.parametrize("valor", ["", MARCADOR, "   "])
    def test_son_marcador(self, valor):
        assert _bash(f'credencial_es_marcador "{valor}"').returncode == 0

    @pytest.mark.parametrize(
        "valor", ["abc123", "a&b\\c#d", f"{MARCADOR}_x", "SuperSecretPassword123"])
    def test_no_son_marcador(self, valor):
        """Cualquier valor puesto por una persona se respeta, aunque sea flojo:
        decidir si es 'bueno' no es cosa del instalador (y `SuperSecretPassword123`
        lo puso quien configuró esa instalación)."""
        assert _bash(f"credencial_es_marcador '{valor}'").returncode == 1


class TestCrearEnvProtegido:

    @pytest.mark.parametrize("umask", ["022", "000", "077"])
    def test_modo_600_con_cualquier_mascara(self, entorno, umask):
        """El defecto medido: `cp` + máscara 022 dejaba 644."""
        entorno["ejemplo"].write_text(EJEMPLO)
        entorno["ejemplo"].chmod(0o644)
        r = _bash(
            f'crear_env_protegido "{entorno["ejemplo"]}" "{entorno["env"]}"', umask=umask)
        assert r.returncode == 0, r.stderr
        assert _modo(entorno["env"]) == 0o600
        assert entorno["env"].read_text() == EJEMPLO

    def test_nunca_existe_mas_abierto_que_600(self, entorno):
        """Sin ventana: el fichero NACE cerrado (máscara 077); no se cierra
        después con un `chmod`. Se observa el modo en el instante exacto en que
        `cp` lo crea, con un `cp` de envoltorio que lo registra al terminar."""
        entorno["ejemplo"].write_text(EJEMPLO)
        registro = entorno["env"].parent / "modo_al_crear.txt"
        r = _bash(
            f'cp() {{ command cp "$@"; stat -c %a "${{@: -1}}" >> "{registro}"; }}\n'
            f'crear_env_protegido "{entorno["ejemplo"]}" "{entorno["env"]}"', umask="000")
        assert r.returncode == 0, r.stderr
        assert registro.read_text().split() == ["600"]

    def test_no_pisa_un_env_existente(self, entorno):
        entorno["ejemplo"].write_text(EJEMPLO)
        _crear_env(entorno, "DB_PASSWORD=la_mia\n")
        r = _bash(f'crear_env_protegido "{entorno["ejemplo"]}" "{entorno["env"]}"')
        assert r.returncode != 0
        assert entorno["env"].read_text() == "DB_PASSWORD=la_mia\n"


class TestPrepararCredenciales:

    def test_instalacion_nueva_genera_sin_pedir_nada(self, entorno):
        """M4-01: antes RC=1 y «Edita el .env a mano»."""
        env = _crear_env(entorno)
        r = _preparar(entorno)
        assert r.returncode == 0, r.stderr
        nueva = _valor(env, "DB_PASSWORD")
        assert nueva and nueva != MARCADOR
        assert re.fullmatch(r"[A-Za-z0-9]{32,}", nueva)

    def test_el_valor_generado_no_sale_por_la_salida(self, entorno):
        env = _crear_env(entorno)
        r = _preparar(entorno)
        nueva = _valor(env, "DB_PASSWORD")
        assert nueva
        assert nueva not in r.stdout and nueva not in r.stderr
        assert "contraseña" in (r.stdout + r.stderr).lower()  # se dice QUE se generó

    def test_el_resto_del_env_queda_intacto(self, entorno):
        env = _crear_env(entorno)
        _preparar(entorno)
        antes = [x for x in EJEMPLO.splitlines() if not x.startswith("DB_PASSWORD=")]
        despues = [x for x in env.read_text().splitlines() if not x.startswith("DB_PASSWORD=")]
        assert despues == antes

    def test_reejecucion_conserva_la_contraseña(self, entorno):
        """Conservación de credenciales válidas: dos pasadas, el mismo valor."""
        env = _crear_env(entorno)
        _preparar(entorno)
        primera = env.read_bytes()
        r = _preparar(entorno)
        assert r.returncode == 0
        assert env.read_bytes() == primera

    @pytest.mark.parametrize(
        "valor", ["la_de_siempre", "a&b\\c#d", "SuperSecretPassword123", "x" * 80])
    def test_contraseña_puesta_por_la_persona_no_se_toca(self, entorno, valor):
        contenido = f"A=1\nDB_PASSWORD={valor}\nB=2\n"
        env = _crear_env(entorno, contenido)
        r = _preparar(entorno)
        assert r.returncode == 0
        assert env.read_text() == contenido

    def test_una_linea_comentada_no_cuenta_como_marcador(self, entorno):
        """El control antiguo era un `grep` a secas: una línea comentada con el
        marcador paraba el instalador aunque la contraseña real estuviera puesta."""
        contenido = f"# DB_PASSWORD={MARCADOR}\nDB_PASSWORD=real_y_valida\n"
        env = _crear_env(entorno, contenido)
        assert _preparar(entorno).returncode == 0
        assert env.read_text() == contenido

    def test_solo_comentada_se_trata_como_ausente_y_se_genera(self, entorno):
        env = _crear_env(entorno, f"# DB_PASSWORD={MARCADOR}\nA=1\n")
        assert _preparar(entorno).returncode == 0
        assert re.fullmatch(r"[A-Za-z0-9]{32,}", _valor(env, "DB_PASSWORD") or "")
        assert "A=1" in env.read_text().splitlines()

    @pytest.mark.parametrize("contenido", ["DB_PASSWORD=\nA=1\n", "A=1\n"])
    def test_vacia_o_ausente_se_genera(self, entorno, contenido):
        env = _crear_env(entorno, contenido)
        assert _preparar(entorno).returncode == 0
        assert re.fullmatch(r"[A-Za-z0-9]{32,}", _valor(env, "DB_PASSWORD") or "")
        assert (env.read_text().count("DB_PASSWORD=")) == 1

    def test_con_base_de_datos_ya_creada_no_se_inventa_nada(self, entorno):
        """La base se inicializó con ALGUNA contraseña que este fichero ya no
        conoce: generar otra dejaría la aplicación sin poder entrar y el
        instalador pararía el servicio. Se explica y se corta sin tocar nada."""
        env = _crear_env(entorno)
        pg = entorno["datos"] / "postgres"
        pg.mkdir()
        (pg / "PG_VERSION").write_text("15\n")
        antes = env.read_bytes()
        r = _preparar(entorno)
        assert r.returncode != 0
        assert env.read_bytes() == antes
        texto = r.stderr + r.stdout
        assert "base de datos" in texto and "DB_PASSWORD" in texto
        assert MARCADOR not in texto.replace("DB_PASSWORD", "")  # sin jerga del marcador

    def test_carpeta_postgres_vacia_no_cuenta_como_base_creada(self, entorno):
        """`bootstrap.sh` crea la carpeta antes de que Postgres escriba nada: un
        primer intento fallido tras crearla no puede bloquear el segundo."""
        env = _crear_env(entorno)
        (entorno["datos"] / "postgres").mkdir()
        assert _preparar(entorno).returncode == 0
        assert _valor(env, "DB_PASSWORD") != MARCADOR

    def test_contraseña_valida_con_base_creada_no_molesta(self, entorno):
        contenido = "DB_PASSWORD=la_que_abrio_la_base\n"
        env = _crear_env(entorno, contenido)
        pg = entorno["datos"] / "postgres"
        pg.mkdir()
        (pg / "PG_VERSION").write_text("15\n")
        assert _preparar(entorno).returncode == 0
        assert env.read_text() == contenido

    def test_endurece_un_env_antiguo_abierto_y_avisa(self, entorno):
        """Instalaciones existentes: el 644 de antes se cierra al reejecutar."""
        contenido = "DB_PASSWORD=ya_puesta\n"
        env = _crear_env(entorno, contenido, modo=0o644)
        r = _preparar(entorno)
        assert r.returncode == 0
        assert _modo(env) == 0o600
        assert env.read_text() == contenido
        assert "AVISO" in r.stdout and "644" in r.stdout

    def test_sin_aviso_si_ya_estaba_cerrado(self, entorno):
        _crear_env(entorno, "DB_PASSWORD=ya_puesta\n", modo=0o600)
        r = _preparar(entorno)
        assert "AVISO" not in r.stdout

    def test_resultado_final_siempre_600(self, entorno):
        env = _crear_env(entorno, modo=0o644)
        _preparar(entorno)
        assert _modo(env) == 0o600

    def test_falta_el_env_es_error_claro(self, entorno):
        r = _preparar(entorno)
        assert r.returncode != 0
        assert "no encuentro" in (r.stderr + r.stdout).lower()


class TestEnvPoner:

    def test_modifica_conservando_el_modo_600(self, entorno):
        """El otro hueco: `sed -i` reescribe el fichero; no puede reabrirlo."""
        env = _crear_env(entorno, "A=1\nB=2\n", modo=0o600)
        r = _bash(f'env_poner "{env}" A nuevo')
        assert r.returncode == 0
        assert _valor(env, "A") == "nuevo"
        assert _modo(env) == 0o600

    def test_una_modificacion_cierra_un_env_que_estaba_abierto(self, entorno):
        env = _crear_env(entorno, "A=1\n", modo=0o644)
        _bash(f'env_poner "{env}" A 2')
        assert _modo(env) == 0o600

    def test_añade_la_clave_si_no_existe(self, entorno):
        env = _crear_env(entorno, "A=1\n")
        _bash(f'env_poner "{env}" B 2')
        assert env.read_text().splitlines() == ["A=1", "B=2"]

    @pytest.mark.parametrize("valor", ["/media/Juan & María", "a\\b", "x#y", "p&q"])
    def test_valores_con_caracteres_de_sed(self, entorno, valor):
        """Misma garantía que tenía `set_env_var` (M7): se escribe literal."""
        env = _crear_env(entorno, "A=1\n")
        r = _bash(f'env_poner "{env}" A "$1"'.replace("$1", valor.replace('"', '\\"')))
        assert r.returncode == 0
        assert _valor(env, "A") == valor

    def test_no_deja_ficheros_temporales_al_lado(self, entorno):
        env = _crear_env(entorno, "A=1\n")
        antes = {p.name for p in env.parent.iterdir()}
        _bash(f'env_poner "{env}" A 2')
        assert {p.name for p in env.parent.iterdir()} == antes


class TestBootstrapUsaElAyudante:
    """`bootstrap.sh` necesita root, Docker y red: no se ejecuta aquí. Se fija el
    contrato de lo que llama, para que nadie lo deshaga sin ver estas pruebas."""

    TEXTO = (REPO / "bootstrap.sh").read_text()

    def test_carga_el_ayudante(self):
        assert "scripts/_credenciales.sh" in self.TEXTO

    def test_ya_no_exige_editar_la_contraseña_a_mano(self):
        assert "Edita ${ENV_FILE} y pon una contraseña segura" not in self.TEXTO
        assert 'grep -q "DB_PASSWORD=cambia_esto_ahora"' not in self.TEXTO
        assert "preparar_credenciales" in self.TEXTO

    def test_el_env_se_crea_cerrado(self):
        assert 'cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}"' not in self.TEXTO
        assert "crear_env_protegido" in self.TEXTO

    def test_set_env_var_delega_en_env_poner(self):
        """Una sola escritura del `.env`: la que conserva el modo."""
        m = re.search(r"^set_env_var\(\) \{(.*?)^\}", self.TEXTO, re.S | re.M)
        assert m, "no encuentro set_env_var"
        assert "env_poner" in m.group(1)
        assert "sed -i" not in m.group(1)

    def test_la_contraseña_se_prepara_antes_de_levantar_nada(self):
        i_prep = self.TEXTO.index("preparar_credenciales")
        i_up = self.TEXTO.index("up -d postgres")
        assert i_prep < i_up

    def test_los_comandos_que_imprime_llevan_sudo(self):
        """Con el `.env` en 600, `docker compose` sin sudo da «permission denied»
        en inglés (medido con Compose v5): el instalador no puede proponer eso."""
        impresos = [
            linea for linea in self.TEXTO.splitlines()
            if "docker compose -f ${COMPOSE_FILE}" in linea
            and "--env-file" not in linea
        ]
        assert impresos, "no encuentro los comandos de ayuda"
        for linea in impresos:
            assert "sudo docker compose" in linea, linea
