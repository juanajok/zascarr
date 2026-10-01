"""Pruebas de `scripts/uninstall.sh` (lote de operación).

El script corre en el HOST con `docker` de verdad y borra cosas. Aquí se prueba
con **dobles de `docker` en el `PATH`** y un **árbol sintético** en un
directorio temporal, igual que `tests/test_diagnostico_red.py`: así se comprueba
lo que importa —que la ruta purgada sea la que ve `docker compose`, que se niegue
a purgar cuando no debe y que no diga «borrado» sin comprobarlo— sin tocar el
Docker ni las rutas de la máquina que ejecuta los tests.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix", reason="el desinstalador es un script de Bash para Linux"
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "uninstall.sh"

# El doble de docker responde por forma del argumento:
#   - `config --environment` imprime el entorno ya resuelto (STUB_ENV), o falla
#     si se pide (para probar el lector de reserva);
#   - `compose … down/version` no hace nada;
#   - `run --rm -v HOST:/purgar IMAGEN …` emula lo único que hace el contenedor
#     de purga: borrar las cuatro subcarpetas bajo HOST (o no, según STUB_PURGA).
DOCKER_STUB = r"""#!/usr/bin/env bash
args="$*"
[[ -n "${STUB_REGISTRO:-}" ]] && echo "docker $args" >> "${STUB_REGISTRO}"
if [[ "$args" == *"config --images"* ]]; then
    printf '%s\n' "${STUB_IMAGENES:-postgres:15-alpine}"
    exit 0
fi
if [[ "$args" == *"config --environment"* ]]; then
    if [[ "${STUB_CONFIG_FALLA:-}" == "si" ]]; then exit 1; fi
    printf '%s\n' "${STUB_ENV:-}"
    exit 0
fi
if [[ "${1:-}" == "compose" ]]; then
    for a in "$@"; do
        case "$a" in
            version) echo "Docker Compose version v2"; exit 0 ;;
            down) exit 0 ;;
        esac
    done
    exit 0
fi
if [[ "${1:-}" == "run" ]]; then
    host=""
    imagen=""
    anterior=""
    for a in "$@"; do
        if [[ "${anterior}" == "-v" ]]; then host="${a%:*}"; fi
        if [[ "${anterior}" == *":/purgar" ]]; then imagen="${a}"; fi
        anterior="${a}"
    done
    [[ -n "${STUB_IMAGEN_REGISTRO:-}" ]] && echo "${imagen}" >> "${STUB_IMAGEN_REGISTRO}"
    if [[ "${STUB_PURGA:-si}" == "si" && -n "${host}" ]]; then
        # NUNCA se borra fuera del árbol sintético: así una prueba que caiga en
        # un valor por defecto real (`/var/lib/zascarr`, por ejemplo) no toca
        # nada de la máquina. Se registra el intento, que es lo que interesa.
        case "${host}" in
            "${STUB_RAIZ:?}"/*)
                rm -rf "${host}/postgres" "${host}/redis" "${host}/covers" "${host}/vpn-state"
                ;;
            *)
                if [[ -n "${STUB_REGISTRO:-}" ]]; then
                    echo "purga fuera de la raiz: ${host}" >> "${STUB_REGISTRO}"
                fi
                ;;
        esac
    fi
    exit 0
fi
exit 0
"""


def _env_compose(datos: Path, *, biblioteca: Path | None = None,
                 descargas: Path | None = None, amule: Path | None = None) -> str:
    """Lo que devolvería `docker compose config --environment`."""
    return "\n".join([
        f"ZASCARR_DATA_DIR={datos}",
        f"HOST_LIBRARY_DIR={biblioteca or datos.parent / 'biblioteca'}",
        f"HOST_DOWNLOADS_DIR={descargas or datos.parent / 'descargas'}",
        f"HOST_AMULE_INCOMING_DIR={amule or datos.parent / 'amule'}",
    ])


@pytest.fixture
def entorno(tmp_path: Path):
    """PATH con el doble de docker, árbol sintético, `.env` propio y registro."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(DOCKER_STUB)
    docker.chmod(0o755)

    datos = tmp_path / "datos"
    for sub in ("postgres", "redis", "covers", "vpn-state"):
        (datos / sub).mkdir(parents=True, exist_ok=True)
    for nombre in ("biblioteca", "descargas", "amule"):
        (tmp_path / nombre).mkdir(exist_ok=True)

    env_file = tmp_path / ".env"
    env_file.write_text("")
    registro = tmp_path / "llamadas.txt"
    registro.write_text("")
    imagenes = tmp_path / "imagenes.txt"
    imagenes.write_text("")

    def ejecutar(*, env_file_texto: str = "", args: list[str] | None = None,
                 confirmacion: str = "si\n", env_compose: str | None = None,
                 limpiar: bool = True,
                 **stubs):
        env_file.write_text(env_file_texto)
        entorno_vars = dict(os.environ)
        entorno_vars["PATH"] = f"{bin_dir}:{entorno_vars['PATH']}"
        entorno_vars["ENV_FILE"] = str(env_file)
        entorno_vars["ZASCARR_ROOT"] = str(tmp_path)
        entorno_vars["STUB_REGISTRO"] = str(registro)
        entorno_vars["STUB_RAIZ"] = str(tmp_path)
        entorno_vars["STUB_IMAGEN_REGISTRO"] = str(imagenes)
        entorno_vars["STUB_ENV"] = env_compose if env_compose is not None else _env_compose(datos)
        entorno_vars["STUB_IMAGENES"] = stubs.pop(
            "STUB_IMAGENES", "postgres:15-alpine\nredis:7-alpine\nzascarr-zascarr\n")
        for clave, valor in stubs.items():
            if valor is None:
                entorno_vars.pop(clave, None)
            else:
                entorno_vars[clave] = valor
        # `try/finally`: si `subprocess.run` lanza (timeout, fallo al arrancar el
        # proceso, interrupción), la limpieza tiene que correr igual — son justo
        # los tests que disparan fallos los que más la necesitan.
        try:
            return subprocess.run(
                ["bash", str(SCRIPT), *(args or [])],
                input=confirmacion, capture_output=True, text=True,
                env=entorno_vars, timeout=60, check=False,
            )
        finally:
            # `limpiar=False` deja ver lo que hizo el SCRIPT, en vez de lo que
            # repara la prueba (lo usa `TestNoEnsuciarElRepo`).
            if limpiar:
                quitar_env_de_prueba(tmp_path)

    ejecutar.datos = datos          # type: ignore[attr-defined]
    ejecutar.registro = registro    # type: ignore[attr-defined]
    ejecutar.imagenes = imagenes    # type: ignore[attr-defined]
    return ejecutar


def texto(salida: subprocess.CompletedProcess) -> str:
    """Salida con espacios colapsados, **stdout y stderr juntos**: los mensajes
    van partidos en varias líneas y los de `die` salen por stderr."""
    return " ".join((salida.stdout + salida.stderr).split())


def quitar_env_de_prueba(tmp_path: Path) -> None:
    """Red de seguridad: si el script vuelve a enlazar `REPO/.env` al `ENV_FILE`
    temporal, se quita antes de que pytest borre el temporal (dejaría un **enlace
    roto en la raíz del repo**, y `get_settings()` lee `.env` desde el cwd).

    Desde el arreglo de `_comun.sh` esto no debería hacer falta —con `ENV_FILE`
    explícito el script **no toca** el checkout—, pero se queda como defensa para
    el caso de un `ENV_FILE` no explícito.

    La pertenencia se comprueba por **ruta resuelta**, no por prefijo de texto:
    `/tmp/pytest-1/foo` es prefijo de `/tmp/pytest-1/foobar`, y `startswith`
    confundiría el temporal de otra prueba con el de esta. Un `.env` de verdad
    (el que crea `bootstrap.sh`) tampoco se toca.
    """
    enlace = REPO / ".env"
    if not enlace.is_symlink():
        return
    try:
        if not Path(os.path.realpath(enlace)).is_relative_to(tmp_path.resolve()):
            return
    except (OSError, ValueError):
        return
    enlace.unlink(missing_ok=True)


class TestPurgaResuelveComoCompose:

    def test_valor_entrecomillado_se_purga_de_verdad(self, entorno):
        """El fallo original: con `ZASCARR_DATA_DIR="/ruta"` el script decía
        «borrado» sin borrar. `docker compose config --environment` ya quita las
        comillas, así que la purga va a la carpeta correcta."""
        datos = entorno.datos
        salida = entorno(
            env_file_texto=f'ZASCARR_DATA_DIR="{datos}"\n',
            env_compose=_env_compose(datos),
            args=["--purge"],
        )

        assert salida.returncode == 0, salida.stderr
        assert "Datos de la app borrados" in texto(salida)
        for sub in ("postgres", "redis", "covers", "vpn-state"):
            assert not (datos / sub).exists(), f"{sub} debería haberse borrado"

    @pytest.mark.parametrize("forma", ["comillas", "comentario", "export", "crlf"])
    def test_el_lector_de_reserva_interpreta_las_cuatro_formas(self, entorno, forma):
        """Con `docker compose config` caído, el lector propio tiene que resolver
        comillas, comentario en línea, `export` y CRLF a la MISMA ruta."""
        datos = entorno.datos
        linea = {
            "comillas": f'ZASCARR_DATA_DIR="{datos}"',
            "comentario": f"ZASCARR_DATA_DIR={datos} # datos de la app",
            "export": f"export ZASCARR_DATA_DIR={datos}",
            "crlf": f"ZASCARR_DATA_DIR={datos}\r",
        }[forma]
        salida = entorno(
            env_file_texto=linea + "\n",
            env_compose="",
            STUB_CONFIG_FALLA="si",
            args=["--purge"],
        )

        assert salida.returncode == 0, salida.stderr
        assert "no es una carpeta existente" not in texto(salida), texto(salida)
        assert "Datos de la app borrados" in texto(salida)
        # Y de verdad se borró: sin esto, el test pasaría en vacío (que es
        # justo el fallo que se está arreglando).
        for sub in ("postgres", "redis", "covers", "vpn-state"):
            assert not (datos / sub).exists(), f"{sub} debería haberse borrado ({forma})"

    def test_almohadilla_pegada_al_valor_no_es_comentario(self, entorno, tmp_path):
        """Compose solo trata `#` como comentario si va precedido de espacio: una
        ruta como `/media/Comics#1` no se trunca. Truncarla apuntaría a otra
        carpeta (que puede existir) y la red de seguridad no saltaría."""
        con_almohadilla = tmp_path / "Comics#1"
        for sub in ("postgres", "redis", "covers", "vpn-state"):
            (con_almohadilla / sub).mkdir(parents=True, exist_ok=True)
        sin_cola = tmp_path / "Comics"
        sin_cola.mkdir(exist_ok=True)   # existe: si se truncara, purgaría aquí

        salida = entorno(
            env_file_texto=f"ZASCARR_DATA_DIR={con_almohadilla}\n",
            env_compose="",
            STUB_CONFIG_FALLA="si",
            args=["--purge"],
        )

        assert salida.returncode == 0, salida.stderr
        for sub in ("postgres", "redis", "covers", "vpn-state"):
            assert not (con_almohadilla / sub).exists(), f"{sub}: debería borrarse en Comics#1"
        assert sin_cola.exists(), "no debería haberse tocado la carpeta truncada"

    def test_la_imagen_de_purga_sale_de_compose(self, entorno):
        """`config --images` resuelve el nombre real (entrecomillado o con
        `${VAR}` en el YAML); el valor del doble es distintivo para probar que
        la imagen viene de ahí y no de un literal del script."""
        salida = entorno(
            env_compose=_env_compose(entorno.datos), args=["--purge"],
            STUB_IMAGENES="postgres:99-de-prueba\nredis:7-alpine\n",
        )

        assert salida.returncode == 0, salida.stderr
        imagenes = entorno.imagenes.read_text().split()
        assert imagenes == ["postgres:99-de-prueba"], imagenes

    def test_valor_por_defecto_con_compose_responsiendo_no_se_niega(self, entorno, tmp_path):
        """Si la variable no está ni en el `.env` ni en el entorno y Compose SÍ
        respondió, el valor es el del compose: **no** es el caso incierto de la
        reserva, así que el script no se niega y la desinstalación termina.

        El valor por defecto se apunta a un directorio temporal que NO existe
        (`ZASCARR_DATA_DIR_POR_DEFECTO`), así que la prueba es determinista y no
        depende de si `/var/lib/zascarr` existe en la máquina: antes exigía
        `returncode == 0` y en una máquina con datos reales ahí el script veía
        «restos» que el doble no había borrado y terminaba en 1.
        """
        inexistente = tmp_path / "datos-por-defecto"
        salida = entorno(
            env_compose="HOST_LIBRARY_DIR=/tmp/x\nHOST_DOWNLOADS_DIR=/tmp/y\n",
            args=["--purge"],
            ZASCARR_DATA_DIR_POR_DEFECTO=str(inexistente),
        )

        assert salida.returncode == 0, texto(salida)
        assert "no había nada que purgar" in texto(salida)
        assert ".env borrado" in texto(salida)
        assert "me niego a hacer --purge" not in texto(salida)


class TestSeNiegaCuandoNoDebe:

    def test_datos_ausentes_con_compose_termina_bien(self, entorno, tmp_path):
        """Idempotencia: si la AUTORIDAD (Compose) dice dónde están los datos y
        esa carpeta ya no existe (la borraste a mano, o una ejecución anterior lo
        hizo), no había nada que purgar. Se avisa y se sigue con el resto — el
        `.env` incluido — en vez de dejar la desinstalación a medias."""
        inexistente = tmp_path / "no-existe"
        salida = entorno(env_compose=_env_compose(inexistente), args=["--purge"])

        assert salida.returncode == 0, texto(salida)
        assert "no había nada que purgar" in texto(salida)
        assert ".env borrado" in texto(salida)
        assert "no existe" in texto(salida)
        assert entorno.registro.read_text().count("down") >= 1

    def test_datos_ausentes_con_el_lector_de_reserva_se_niega(self, entorno, tmp_path):
        """Con el lector de reserva (Compose caído) no se sabe qué hay en esa
        ruta: ahí sí se falla cerrado."""
        inexistente = tmp_path / "no-existe"
        salida = entorno(
            env_file_texto=f"ZASCARR_DATA_DIR={inexistente}\n",
            env_compose="",
            STUB_CONFIG_FALLA="si",
            args=["--purge"],
        )

        assert salida.returncode != 0
        assert "no es una carpeta existente" in texto(salida)
        assert "borrados" not in texto(salida)
        assert ".env borrado" not in texto(salida)

    def test_symlink_roto_en_la_ruta_se_detecta(self, entorno, tmp_path):
        """`resolver_ruta` de `_rutas.sh` detecta el symlink roto; el
        `readlink -f` local anterior no lo veía."""
        roto = tmp_path / "datos"
        datos_reales = entorno.datos
        datos_reales.rename(tmp_path / "datos-reales")
        roto.symlink_to(tmp_path / "no-existe")

        salida = entorno(env_compose=_env_compose(roto), args=["--purge"])

        assert salida.returncode != 0
        assert "symlink roto" in texto(salida)
        assert "borrados" not in texto(salida)

    def test_misma_carpeta_por_otra_ruta_se_detecta(self, entorno, tmp_path):
        """Dos rutas de texto distinto que son la misma carpeta: `resolver_ruta`
        las unifica por `realpath` y `motivo_solapamiento` lo ve. (La rama de
        `(st_dev, st_ino)` —bind mount de verdad— se cubre en
        `tests/test_bootstrap_rutas.py`, que simula `stat`.)"""
        alias = tmp_path / "alias-biblioteca"
        alias.symlink_to(entorno.datos)

        salida = entorno(
            env_compose=_env_compose(entorno.datos, biblioteca=alias),
            args=["--purge"],
        )

        assert salida.returncode != 0
        assert "me niego a borrar ahí" in texto(salida)
        for sub in ("postgres", "redis", "covers", "vpn-state"):
            assert (entorno.datos / sub).exists(), "no debería haber borrado nada"

    def test_sin_purge_sigue_con_enlace_roto_en_la_biblioteca(self, entorno, tmp_path):
        """Fuera de `--purge` un fallo de resolución NO puede abortar: parar los
        contenedores no necesita la ruta resuelta. Se avisa y se sigue."""
        rota = tmp_path / "biblioteca"
        rota.rmdir()   # el fixture la crea como carpeta real
        rota.symlink_to(tmp_path / "no-existe")

        salida = entorno(
            env_compose=_env_compose(entorno.datos, biblioteca=rota), args=[],
        )

        assert salida.returncode == 0, texto(salida)
        assert "No pude resolver HOST_LIBRARY_DIR" in texto(salida)
        assert "Contenedores, red e imagen borrados" in texto(salida)
        assert entorno.registro.read_text().count("down") >= 1
        assert (entorno.datos / "postgres").exists(), "sin --purge no se toca nada"

    def test_sin_confirmacion_no_toca_nada(self, entorno):
        salida = entorno(
            env_compose=_env_compose(entorno.datos),
            args=["--purge"], confirmacion="no\n",
        )

        assert salida.returncode != 0
        assert "Cancelado" in texto(salida)
        assert (entorno.datos / "postgres").exists()

    def test_sin_purge_conserva_los_datos(self, entorno):
        salida = entorno(env_compose=_env_compose(entorno.datos), args=[])

        assert salida.returncode == 0, salida.stderr
        assert "CONSERVAR" in texto(salida)
        assert (entorno.datos / "postgres").exists()


class TestNoEnsuciarElRepo:
    """**Una prueba no debe modificar la raíz del checkout.**

    `_comun.sh` enlazaba `REPO/.env` al `ENV_FILE` que ve el script. Con un
    `ENV_FILE` temporal, al desaparecer el temporal quedaba un **enlace roto en la
    raíz del repo**, y `get_settings()` lee `.env` desde el cwd. El arreglo de
    raíz es que el script **no cree el enlace** cuando `ENV_FILE` viene explícito;
    la limpieza se queda como red de seguridad.
    """

    def test_con_env_explicito_el_script_no_crea_el_symlink(self, entorno):
        """El arreglo de raíz: si `ENV_FILE` lo pone quien llama, el checkout no
        se toca. Se ejecuta **sin la limpieza** de la fixture, para observar lo
        que hace el script y no lo que repara la prueba."""
        enlace = REPO / ".env"
        enlace.unlink(missing_ok=True)
        try:
            entorno(env_compose=_env_compose(entorno.datos), args=["--purge"],
                    confirmacion="si\n", limpiar=False)
            creado = enlace.is_symlink()
        finally:
            enlace.unlink(missing_ok=True)

        assert not creado, (
            "el script creó `REPO/.env` teniendo un ENV_FILE explícito"
        )

    def test_no_queda_un_env_apuntando_al_temporal(self, entorno, tmp_path):
        entorno(env_compose=_env_compose(entorno.datos), args=["--purge"],
                confirmacion="si\n")

        enlace = REPO / ".env"
        if enlace.is_symlink():
            assert not Path(os.path.realpath(enlace)).is_relative_to(
                tmp_path.resolve()
            ), "quedó un `.env` apuntando al temporal de la prueba"

    def test_la_limpieza_corre_aunque_subprocess_lance(self, entorno, tmp_path,
                                                       monkeypatch):
        """`try/finally`: si `subprocess.run` lanza (timeout, fallo al arrancar el
        proceso, interrupción), la limpieza tiene que correr igual."""
        enlace = REPO / ".env"
        enlace.unlink(missing_ok=True)

        def falso(*_args, **_kwargs):
            # Lo que hace el script: enlaza REPO/.env al ENV_FILE temporal.
            enlace.symlink_to(tmp_path / ".env")
            raise subprocess.TimeoutExpired(cmd="bash", timeout=60)

        monkeypatch.setattr(subprocess, "run", falso)
        with pytest.raises(subprocess.TimeoutExpired):
            entorno(env_compose=_env_compose(entorno.datos), args=[])

        assert not enlace.is_symlink(), (
            "el `finally` no limpió tras la excepción: el repo queda sucio"
        )

    def test_no_toca_un_env_que_no_es_del_temporal(self, tmp_path):
        """Un `.env` de verdad (ajeno al temporal de la prueba) no se toca."""
        enlace = REPO / ".env"
        ajeno = tmp_path.parent / "zascarr-env-ajeno"
        ajeno.write_text("X=1")
        previo = os.readlink(enlace) if enlace.is_symlink() else None
        enlace.unlink(missing_ok=True)
        try:
            enlace.symlink_to(ajeno)
            quitar_env_de_prueba(tmp_path)
            assert enlace.is_symlink(), "no debía borrar un `.env` ajeno"
        finally:
            enlace.unlink(missing_ok=True)
            if previo is not None:
                enlace.symlink_to(previo)
            ajeno.unlink(missing_ok=True)

    def test_un_temporal_con_prefijo_parecido_no_cuenta_como_propio(self, tmp_path):
        """`/tmp/pytest-1/foo` es prefijo de `/tmp/pytest-1/foobar`, pero no es
        su carpeta: la pertenencia se decide por ruta, no por texto."""
        enlace = REPO / ".env"
        gemelo = tmp_path.parent / f"{tmp_path.name}-gemelo"
        gemelo.mkdir(exist_ok=True)
        previo = os.readlink(enlace) if enlace.is_symlink() else None
        enlace.unlink(missing_ok=True)
        try:
            enlace.symlink_to(gemelo / ".env")
            quitar_env_de_prueba(tmp_path)
            assert enlace.is_symlink(), (
                "borró un enlace cuyo destino solo COMPARTE PREFIJO con el temporal"
            )
        finally:
            enlace.unlink(missing_ok=True)
            if previo is not None:
                enlace.symlink_to(previo)
            gemelo.rmdir()
