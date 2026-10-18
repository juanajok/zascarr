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


_BASE: list[str] = []


@pytest.fixture(autouse=True)
def _carpeta_base(tmp_path_factory):
    """Los antecesores se vigilan hasta la carpeta base de pytest (700, de quien
    ejecuta): lo de más arriba es de la máquina, no del código bajo prueba."""
    _BASE[:] = [str(tmp_path_factory.getbasetemp())]


def _bash(cuerpo: str, *, umask: str = "022", admin: bool = False):
    """`admin=False`: las pruebas no son root, así que el «propietario esperado» del
    .env es quien las ejecuta. `admin=True`: se SIMULA ser root (la variable `EUID` es
    de solo lectura; el ayudante pregunta por `_es_root`) con dobles de `chown` y de la
    consulta del propietario, para probar la rama administrativa sin serlo."""
    simulado = (
        '_es_root() { return 0; }\n'
        'CREDENCIAL_UID_ESPERADO=0\n'
    ) if admin else f'CREDENCIAL_UID_ESPERADO={os.getuid()}\n'
    simulado += f'CREDENCIAL_CONFIAR_DESDE="{_BASE[0]}"\n'
    guion = f'umask {umask}\n{PRELUDIO}\nsource "{SH}"\n{simulado}{cuerpo}\n'
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


class TestSinVentanaDeEscritura:
    """Hallazgo 2 de la revisión: el secreto nuevo no puede escribirse en un fichero
    todavía abierto, ni a un temporal abierto, ni «después se cierra»."""

    def _observando(self, env: Path, cuerpo: str, *, umask: str = "022"):
        """Dobles de `sed`, `cat`, `mv` y `cp` que anotan el modo del `.env` y de
        todo lo que haya a su lado EN EL INSTANTE de cada operación."""
        registro = env.parent / "modos.txt"
        doble = "".join(
            f'{f}() {{ _anota "{f}"; command {f} "$@"; _anota "{f}-despues"; }}\n'
            for f in ("sed", "cat", "mv", "cp", "tee"))
        guion = (
            f'_anota() {{ for x in "{env}" "{env}".*; do [[ -e "$x" ]] && '
            f'echo "$1 $(basename "$x") $(stat -c %a "$x")" >> "{registro}"; done; return 0; }}\n'
            f'{doble}{cuerpo}')
        r = _bash(guion, umask=umask)
        lineas = registro.read_text().splitlines() if registro.exists() else []
        return r, [linea.split() for linea in lineas]

    @pytest.mark.parametrize("umask", ["022", "000"])
    def test_fichero_antiguo_abierto_se_cierra_antes_de_escribir_nada(self, entorno, umask):
        env = _crear_env(entorno, modo=0o644)
        r, anotado = self._observando(
            env, f'preparar_credenciales "{env}" "{entorno["datos"]}"', umask=umask)
        assert r.returncode == 0, r.stderr
        assert anotado, "el doble no anotó nada: la prueba no observó la escritura"
        abiertos = [a for a in anotado if int(a[2], 8) & 0o077]
        assert not abiertos, f"fichero accesible a otros durante la escritura: {abiertos}"
        assert _modo(env) == 0o600

    def test_el_temporal_nace_cerrado_y_no_queda_nada(self, entorno):
        env = _crear_env(entorno, modo=0o600)
        antes = {p.name for p in env.parent.iterdir()}
        r, anotado = self._observando(env, f'env_poner "{env}" A nuevo', umask="000")
        assert r.returncode == 0
        temporales = [a for a in anotado if a[1] != env.name]
        assert temporales, "el ayudante debería escribir en un temporal y renombrar"
        assert all(a[2] == "600" for a in temporales), temporales
        assert {p.name for p in env.parent.iterdir()} - {"modos.txt"} == antes

    def test_env_poner_cierra_el_destino_antes_de_escribir(self, entorno):
        """Llamado directamente (como hace `set_env_var`) sobre un fichero heredado."""
        env = _crear_env(entorno, "A=1\nDB_PASSWORD=ya_puesta\n", modo=0o644)
        r, anotado = self._observando(env, f'env_poner "{env}" B 2')
        assert r.returncode == 0
        assert not [a for a in anotado if int(a[2], 8) & 0o077], anotado

    def test_el_fichero_nuevo_conserva_el_contenido_y_el_orden(self, entorno):
        env = _crear_env(entorno, "# c\nA=1\nB=2\n", modo=0o600)
        _bash(f'env_poner "{env}" B 3\nenv_poner "{env}" C 4')
        assert env.read_text() == "# c\nA=1\nB=3\nC=4\n"

    def test_añadir_a_un_fichero_sin_salto_de_linea_final(self, entorno):
        env = _crear_env(entorno, "A=1", modo=0o600)
        _bash(f'env_poner "{env}" B 2')
        assert env.read_text().splitlines() == ["A=1", "B=2"]


class TestFalloEnCerrado:
    """Hallazgo 3: si no se consigue el propietario o el modo exigidos, NO se sigue
    ni se anuncia una protección que no existe."""

    def test_chown_que_falla_corta_antes_de_escribir_el_secreto(self, entorno):
        env = _crear_env(entorno)
        antes = env.read_bytes()
        r = _bash(
            'chown() { return 1; }\n'
            '_propietario_de() { echo 0; }  # aísla el código de retorno de chown\n'
            'ubicacion_env_insegura() { return 1; }\n'
            f'preparar_credenciales "{env}" "{entorno["datos"]}"', admin=True)
        assert r.returncode != 0
        assert env.read_bytes() == antes, "no debe haberse escrito ninguna contraseña"
        salida = r.stdout + r.stderr
        assert "solo el administrador" not in salida and "listo" not in salida.lower()
        assert "ERROR" in r.stderr

    def test_chown_que_dice_ok_pero_no_cambia_el_propietario_tambien_corta(self, entorno):
        """No se fía del código de retorno: se comprueba el resultado."""
        env = _crear_env(entorno)
        r = _bash(
            'chown() { return 0; }\n'
            '_propietario_de() { echo 1000; }\n'
            'ubicacion_env_insegura() { return 1; }\n'
            f'preparar_credenciales "{env}" "{entorno["datos"]}"', admin=True)
        assert r.returncode != 0
        assert "listo" not in (r.stdout + r.stderr).lower()

    def test_con_chown_correcto_se_pide_root_root_y_se_continua(self, entorno):
        env = _crear_env(entorno)
        registro = entorno["env"].parent / "chown.txt"
        r = _bash(
            f'chown() {{ echo "$@" >> "{registro}"; return 0; }}\n'
            '_propietario_de() { echo 0; }\n'
            'ubicacion_env_insegura() { return 1; }  # la ubicación se prueba aparte\n'
            f'preparar_credenciales "{env}" "{entorno["datos"]}"', admin=True)
        assert r.returncode == 0, r.stderr
        assert f"0:0 {env}" in registro.read_text()
        assert re.fullmatch(r"[A-Za-z0-9]{32,}", _valor(env, "DB_PASSWORD") or "")

    def test_el_temporal_tambien_se_pide_de_root_antes_de_llevar_contenido(self, entorno):
        """El fichero que sustituye al `.env` es el temporal renombrado: su dueño ha de
        ser root desde que existe, no solo el del `.env` que reemplaza."""
        env = _crear_env(entorno, "A=1\n")
        registro = entorno["env"].parent / "chown.txt"
        r = _bash(
            f'chown() {{ echo "$@" >> "{registro}"; return 0; }}\n'
            '_propietario_de() { echo 0; }\n'
            f'env_poner "{env}" A 2', admin=True)
        assert r.returncode == 0, r.stderr
        destinos = [linea.split()[1] for linea in registro.read_text().splitlines()]
        assert any(d.startswith(f"{env}.") for d in destinos), destinos

    def test_un_enlace_simbolico_como_env_no_se_protege_ni_se_escribe(self, entorno, tmp_path):
        real = tmp_path / "real.env"
        real.write_text("A=1\n")
        real.chmod(0o644)
        entorno["env"].symlink_to(real)
        assert _bash(f'proteger_env "{entorno["env"]}"').returncode != 0
        assert _bash(f'env_poner "{entorno["env"]}" A 2').returncode != 0
        assert real.read_text() == "A=1\n" and _modo(real) == 0o644

    def test_env_poner_propaga_el_fallo_de_proteccion(self, entorno):
        env = _crear_env(entorno, "A=1\n")
        r = _bash(f'chown() {{ return 1; }}\nenv_poner "{env}" A 2', admin=True)
        assert r.returncode != 0
        assert env.read_text() == "A=1\n"

    def test_chmod_que_falla_corta(self, entorno):
        env = _crear_env(entorno, modo=0o644)
        r = _bash(
            'chmod() { return 1; }\n'
            f'preparar_credenciales "{env}" "{entorno["datos"]}"')
        assert r.returncode != 0
        assert _valor(env, "DB_PASSWORD") == MARCADOR


class TestUbicacionDelEnv:
    """Hallazgo 1: con el `.env` en 600 `root:root`, el dueño de la CARPETA que lo
    contiene puede borrarlo o sustituirlo (o ponerle un enlace). La carpeta, y el
    camino hasta ella, tienen que ser de root y no escribibles por otros."""

    def _motivo(self, env: Path, *, uid: int | None = None):
        uid = os.getuid() if uid is None else uid
        return _bash(f'ubicacion_env_insegura "{env}" {uid}')

    def test_carpeta_propia_y_cerrada_es_segura(self, entorno):
        env = _crear_env(entorno)
        entorno["env"].parent.chmod(0o755)
        r = self._motivo(env)
        assert r.returncode == 1 and r.stdout.strip() == ""

    @pytest.mark.parametrize("modo", [0o775, 0o757, 0o777, 0o770 | 0o020])
    def test_carpeta_escribible_por_otros_es_insegura(self, entorno, modo):
        env = _crear_env(entorno)
        entorno["env"].parent.chmod(modo)
        r = self._motivo(env)
        assert r.returncode == 0 and "escrib" in r.stdout

    def test_carpeta_de_otra_cuenta_es_insegura(self, entorno):
        """El caso medido: `/opt/zascarr` era de `media`."""
        env = _crear_env(entorno)
        r = self._motivo(env, uid=os.getuid() + 1)
        assert r.returncode == 0 and "propiedad" in r.stdout

    def test_un_enlace_simbolico_como_env_es_inseguro(self, entorno, tmp_path):
        real = tmp_path / "otro.env"
        real.write_text("DB_PASSWORD=x\n")
        entorno["env"].symlink_to(real)
        r = self._motivo(entorno["env"])
        assert r.returncode == 0 and "enlace" in r.stdout

    def test_un_antecesor_escribible_por_otros_es_inseguro(self, tmp_path):
        abierto = tmp_path / "abierto"
        abierto.mkdir()
        abierto.chmod(0o777)
        raiz = abierto / "zascarr"
        raiz.mkdir(mode=0o755)
        env = raiz / ".env"
        env.write_text("A=1\n")
        env.chmod(0o600)
        r = self._motivo(env)
        assert r.returncode == 0 and "abierto" in r.stdout

    def test_un_antecesor_con_sticky_no_se_puede_sustituir_desde_fuera(self, tmp_path):
        """Como `/tmp`: escribible por todos pero con el bit pegajoso."""
        pegajoso = tmp_path / "pegajoso"
        pegajoso.mkdir()
        pegajoso.chmod(0o1777)
        raiz = pegajoso / "zascarr"
        raiz.mkdir(mode=0o755)
        env = raiz / ".env"
        env.write_text("A=1\n")
        env.chmod(0o600)
        assert self._motivo(env).returncode == 1

    def test_preparar_credenciales_no_genera_nada_en_una_carpeta_insegura(self, entorno):
        env = _crear_env(entorno)
        entorno["env"].parent.chmod(0o777)
        antes = env.read_bytes()
        r = _preparar(entorno)
        assert r.returncode != 0
        assert env.read_bytes() == antes
        assert "ERROR" in r.stderr and str(entorno["env"].parent) in r.stderr

    def test_asegurar_cierra_la_carpeta_y_pide_root(self, entorno):
        entorno["env"].parent.chmod(0o777)
        registro = entorno["env"].parent / "chown.txt"
        r = _bash(
            f'chown() {{ echo "$@" >> "{registro}"; return 0; }}\n'
            '_propietario_de() { echo 0; }\n'
            f'asegurar_ubicacion_env "{entorno["env"]}"', admin=True)
        assert r.returncode == 0, r.stderr
        assert f"0:0 {entorno['env'].parent}" in registro.read_text()
        assert _modo(entorno["env"].parent) & 0o022 == 0
        assert "-R" not in registro.read_text()  # solo la carpeta, nada recursivo

    def test_asegurar_falla_en_cerrado_si_chown_falla(self, entorno):
        r = _bash(
            'chown() { return 1; }\n'
            f'asegurar_ubicacion_env "{entorno["env"]}"', admin=True)
        assert r.returncode != 0

    def test_crear_env_no_escribe_a_traves_de_un_enlace_colgante(self, entorno, tmp_path):
        """`[[ -e ]]` es falso para un enlace roto: `cp` escribiría en su destino."""
        destino = tmp_path / "fuera" / "robado.env"
        destino.parent.mkdir()
        entorno["env"].symlink_to(destino)
        entorno["ejemplo"].write_text(EJEMPLO)
        r = _bash(f'crear_env_protegido "{entorno["ejemplo"]}" "{entorno["env"]}"')
        assert r.returncode != 0
        assert not destino.exists()


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

    def test_no_entrega_la_carpeta_del_env_al_usuario_de_servicio(self):
        """Hallazgo 1: el `chown -R` de la rama de instalación en frío cubría
        `ZASCARR_ROOT` entero (y con él la carpeta que contiene el `.env`)."""
        for linea in self.TEXTO.splitlines():
            if "chown -R" in linea and "ZASCARR_USER" in linea and "ZASCARR_ROOT" in linea:
                assert '${ZASCARR_ROOT}/zascarr"' in linea, linea

    def test_asegura_la_ubicacion_antes_de_crear_o_escribir_el_env(self):
        i_ubic = self.TEXTO.index("asegurar_ubicacion_env")
        assert i_ubic < self.TEXTO.index("crear_env_protegido")
        assert i_ubic < self.TEXTO.index("preparar_credenciales")

    def test_los_comandos_que_imprime_llevan_sudo(self):
        """Con el `.env` en 600, `docker compose` sin sudo da «permission denied»
        en inglés (medido con Compose v5): el instalador no puede proponer eso."""
        impresos = [
            linea for linea in self.TEXTO.splitlines()
            if "docker compose -f ${COMPOSE_FILE}" in linea
        ]
        assert impresos, "no encuentro los comandos de ayuda"
        for linea in impresos:
            assert "sudo docker compose" in linea, linea
            # El enlace `repo/.env` lo puede cambiar el dueño del repo: lo que corre
            # root lleva siempre el fichero explícito.
            assert "--env-file ${ENV_FILE}" in linea, linea
