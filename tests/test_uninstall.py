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
        rm -rf "${host}/postgres" "${host}/redis" "${host}/covers" "${host}/vpn-state"
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
                 **stubs):
        env_file.write_text(env_file_texto)
        entorno_vars = dict(os.environ)
        entorno_vars["PATH"] = f"{bin_dir}:{entorno_vars['PATH']}"
        entorno_vars["ENV_FILE"] = str(env_file)
        entorno_vars["ZASCARR_ROOT"] = str(tmp_path)
        entorno_vars["STUB_REGISTRO"] = str(registro)
        entorno_vars["STUB_IMAGEN_REGISTRO"] = str(imagenes)
        entorno_vars["STUB_ENV"] = env_compose if env_compose is not None else _env_compose(datos)
        for clave, valor in stubs.items():
            if valor is None:
                entorno_vars.pop(clave, None)
            else:
                entorno_vars[clave] = valor
        return subprocess.run(
            ["bash", str(SCRIPT), *(args or [])],
            input=confirmacion, capture_output=True, text=True,
            env=entorno_vars, timeout=60, check=False,
        )

    ejecutar.datos = datos          # type: ignore[attr-defined]
    ejecutar.registro = registro    # type: ignore[attr-defined]
    ejecutar.imagenes = imagenes    # type: ignore[attr-defined]
    return ejecutar


def texto(salida: subprocess.CompletedProcess) -> str:
    """Salida con espacios colapsados, **stdout y stderr juntos**: los mensajes
    van partidos en varias líneas y los de `die` salen por stderr."""
    return " ".join((salida.stdout + salida.stderr).split())


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

    def test_la_imagen_de_purga_sale_del_compose(self, entorno):
        entorno(env_compose=_env_compose(entorno.datos), args=["--purge"])

        imagenes = entorno.imagenes.read_text().split()
        assert imagenes, "no se llamó a `docker run`"
        esperada = None
        for linea in (REPO / "docker-compose.yml").read_text().splitlines():
            if linea.strip().startswith("image:") and "postgres" in linea:
                esperada = linea.split()[1]
                break
        assert esperada, "el compose no declara imagen de postgres"
        assert imagenes[0] == esperada


class TestSeNiegaCuandoNoDebe:

    def test_directorio_inexistente_se_niega(self, entorno, tmp_path):
        """Red de seguridad: si la ruta resuelta no es una carpeta, no se purga
        (cubre cualquier desajuste de interpretación del `.env`)."""
        inexistente = tmp_path / "no-existe"
        salida = entorno(
            env_compose=_env_compose(inexistente),
            args=["--purge"],
        )

        assert salida.returncode != 0
        assert "no es una carpeta existente" in texto(salida)
        assert "borrados" not in texto(salida)

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

    def test_mismo_inodo_por_bind_mount_se_detecta(self, entorno, tmp_path):
        """`motivo_solapamiento` compara (st_dev, st_ino): dos rutas distintas que
        son la misma carpeta. El prefijo de texto anterior no lo veía."""
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
