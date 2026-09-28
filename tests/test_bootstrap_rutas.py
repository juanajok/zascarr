"""A9 — comprobación de rutas del instalador (biblioteca vs. cola de entrada).

La lógica vive en `scripts/_rutas.sh` (Bash, sin dependencias) porque la usa
`bootstrap.sh` **en el host**, antes de que exista nada: no puede depender de
que el paquete de Python esté instalado. Aquí se carga en un `bash` de verdad y
se prueba sobre un sistema de ficheros sintético — iguales, symlinks distintos
al mismo directorio, anidadas, prefijos de texto que NO son anidamiento, y
rutas que no se pueden resolver.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("realpath") is None,
    reason="requiere bash y realpath (coreutils)",
)

RUTAS_SH = Path(__file__).resolve().parents[1] / "scripts" / "_rutas.sh"


def _bash(cuerpo: str, *, env_extra: str = "", stdin: str | None = None):
    """Carga `_rutas.sh` en un bash limpio y ejecuta `cuerpo`.

    Sin `set -e`: los tests comprueban el código de retorno a mano, y con él
    bash abortaría antes de poder leerlo (que es justo lo que hace
    `bootstrap.sh` con `|| ESTADO=$?`)."""
    guion = f'set -uo pipefail\nsource "{RUTAS_SH}"\n{env_extra}{cuerpo}\n'
    return subprocess.run(
        ["bash", "-c", guion], capture_output=True, text=True, input=stdin,
        timeout=30, check=False,
    )


@pytest.fixture
def arbol(tmp_path: Path) -> dict[str, Path]:
    """Un árbol sintético con lo mínimo para cada caso."""
    rutas = {
        "biblioteca": tmp_path / "tebeoteca",
        "descargas": tmp_path / "descargas",
        "amule": tmp_path / "entrada_amule",
        "padre": tmp_path / "padre",
        "hija": tmp_path / "padre" / "hija",
    }
    for ruta in rutas.values():
        ruta.mkdir(parents=True, exist_ok=True)
    # Dos symlinks distintos al MISMO directorio real.
    (tmp_path / "acceso_tebeos").symlink_to(rutas["biblioteca"])
    (tmp_path / "acceso_descargas").symlink_to(rutas["descargas"])
    rutas["symlink_biblioteca"] = tmp_path / "acceso_tebeos"
    rutas["symlink_descargas"] = tmp_path / "acceso_descargas"
    return rutas


def _comprobar(a: Path, b: Path, c: Path):
    return _bash(
        f'comprobar_solapamiento "{a}" "{b}" "{c}"\n'
        'echo "RC=$?"\n'
    )


class TestResolverRuta:

    def test_resuelve_symlinks(self, arbol):
        salida = _bash(f'resolver_ruta "{arbol["symlink_biblioteca"]}"')
        assert salida.returncode == 0
        assert salida.stdout.strip() == str(arbol["biblioteca"].resolve())

    def test_normaliza_puntos_y_padres(self, arbol):
        torcida = arbol["hija"] / ".." / ".." / "descargas"
        salida = _bash(f'resolver_ruta "{torcida}"')
        assert salida.stdout.strip() == str(arbol["descargas"].resolve())

    def test_una_carpeta_que_aun_no_existe_se_resuelve(self, arbol):
        """Instalación nueva: la biblioteca puede no existir todavía."""
        futura = arbol["biblioteca"] / "aun" / "no" / "existe"
        salida = _bash(f'resolver_ruta "{futura}"')
        assert salida.returncode == 0
        assert salida.stdout.strip() == str(futura)

    def test_ruta_vacia_falla_con_motivo(self):
        salida = _bash('resolver_ruta ""')
        assert salida.returncode == 1
        assert "ruta vacía" in salida.stderr

    def test_fichero_por_medio_falla_con_motivo(self, tmp_path):
        fichero = tmp_path / "no_soy_carpeta"
        fichero.write_text("hola")
        salida = _bash(f'resolver_ruta "{fichero}/dentro"')
        assert salida.returncode == 1
        assert "es un fichero" in salida.stderr
        assert str(fichero) in salida.stderr


class TestSolapamiento:

    def test_carpetas_independientes(self, arbol):
        salida = _comprobar(arbol["biblioteca"], arbol["descargas"], arbol["amule"])
        assert salida.returncode == 0
        assert "RC=0" in salida.stdout
        assert "Sin solapamiento" in salida.stdout

    def test_la_misma_carpeta(self, arbol):
        salida = _comprobar(arbol["biblioteca"], arbol["biblioteca"], arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "es la misma carpeta" in salida.stdout

    def test_symlinks_distintos_al_mismo_directorio(self, arbol):
        """El caso que la comparación de texto no ve."""
        salida = _comprobar(arbol["symlink_biblioteca"], arbol["biblioteca"], arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "es la misma carpeta" in salida.stdout

    def test_la_descarga_es_un_symlink_a_la_biblioteca(self, arbol):
        salida = _comprobar(
            arbol["biblioteca"], arbol["symlink_biblioteca"], arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "es la misma carpeta" in salida.stdout

    def test_anidadas_biblioteca_contiene_descargas(self, arbol):
        salida = _comprobar(arbol["padre"], arbol["hija"], arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "está dentro de la otra" in salida.stdout

    def test_anidadas_descargas_contienen_biblioteca(self, arbol):
        salida = _comprobar(arbol["hija"], arbol["padre"], arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "está dentro de la otra" in salida.stdout

    def test_anidamiento_por_symlink(self, arbol):
        """Un symlink dentro de la biblioteca también anida."""
        dentro = arbol["biblioteca"] / "dentro"
        dentro.mkdir()
        (arbol["biblioteca"] / "atajo_descargas").symlink_to(dentro)
        salida = _comprobar(
            arbol["biblioteca"], arbol["biblioteca"] / "atajo_descargas", arbol["amule"])
        assert "RC=1" in salida.stdout
        assert "está dentro de la otra" in salida.stdout

    def test_prefijo_de_texto_no_es_anidamiento(self, arbol):
        """`/media/lib` NO está dentro de `/media/library`, aunque sea prefijo."""
        hermana = arbol["biblioteca"].with_name(str(arbol["biblioteca"].name) + "_extra")
        hermana.mkdir()
        salida = _comprobar(arbol["biblioteca"], hermana, arbol["amule"])
        assert "RC=0" in salida.stdout
        assert "Sin solapamiento" in salida.stdout

    def test_las_dos_colas_pueden_ser_la_misma_carpeta(self, arbol):
        """No es un solapamiento que haya que advertir: `bootstrap.sh` da a
        descargas y a aMule la MISMA carpeta a propósito (dos montajes del
        mismo sitio), así que avisar aquí sería avisar en todas las
        instalaciones. Lo que importa es que la biblioteca no se solape."""
        salida = _comprobar(arbol["biblioteca"], arbol["descargas"], arbol["descargas"])
        assert "RC=0" in salida.stdout
        assert "Sin solapamiento" in salida.stdout

    def test_la_biblioteca_si_se_solapa_con_la_cola_de_amule(self, arbol):
        salida = _comprobar(arbol["biblioteca"], arbol["descargas"], arbol["biblioteca"])
        assert "RC=1" in salida.stdout
        assert "la entrada de aMule" in salida.stdout

    def test_bind_mount_mismo_dispositivo_e_inodo(self, arbol):
        """Dos rutas de texto distinto, la misma carpeta: se ve por `(dev, ino)`.

        Se simula `stat` porque montar un bind mount exige privilegios; lo que
        se comprueba es que la comprobación MIRA ese dato y lo trata como
        solapamiento."""
        otra = arbol["amule"]  # carpeta real distinta
        salida = _bash(
            f'comprobar_solapamiento "{arbol["biblioteca"]}" "{arbol["descargas"]}" "{otra}"\n'
            'echo "RC=$?"\n',
            env_extra="stat() { echo '8:42'; }\n",
        )
        assert "RC=1" in salida.stdout
        assert "mismo dispositivo e inodo" in salida.stdout


class TestInforme:

    def test_muestra_la_ruta_resuelta_junto_a_la_escrita(self, arbol):
        """El usuario tiene que ver a dónde apunta de verdad lo que escribió."""
        salida = _comprobar(arbol["symlink_biblioteca"], arbol["descargas"], arbol["amule"])
        assert str(arbol["biblioteca"].resolve()) in salida.stdout
        assert f'lo que escribiste: {arbol["symlink_biblioteca"]}' in salida.stdout

    def test_no_menciona_lo_escrito_si_coincide(self, arbol):
        salida = _comprobar(arbol["biblioteca"], arbol["descargas"], arbol["amule"])
        assert "lo que escribiste" not in salida.stdout

    def test_ruta_irresoluble_devuelve_2_y_lo_explica(self, tmp_path):
        fichero = tmp_path / "fichero"
        fichero.write_text("x")
        salida = _bash(
            f'comprobar_solapamiento "{fichero}/nada" "{tmp_path}" "{tmp_path}"\n'
            'echo "RC=$?"\n'
        )
        assert "RC=2" in salida.stdout
        assert "es un fichero" in salida.stderr

    def test_la_comprobacion_no_toca_nada(self, arbol):
        """A9 avisa, nunca cambia rutas, permisos ni montajes."""
        antes = sorted(p.name for p in arbol["biblioteca"].iterdir())
        _comprobar(arbol["biblioteca"], arbol["biblioteca"], arbol["amule"])
        assert sorted(p.name for p in arbol["biblioteca"].iterdir()) == antes


class TestConfirmacion:

    def test_confirmar_con_s(self):
        salida = _bash(
            "pedir_confirmacion_solapamiento\n" 'echo "RC=$?"\n', stdin="s\n")
        assert "RC=0" in salida.stdout

    @pytest.mark.parametrize("respuesta", ["n\n", "\n", "si\n", "SÍ\n"])
    def test_cualquier_otra_cosa_no_continua(self, respuesta):
        salida = _bash(
            "pedir_confirmacion_solapamiento || echo RECHAZADO\n", stdin=respuesta)
        assert "RECHAZADO" in salida.stdout

    def test_sin_terminal_no_continua(self):
        """EOF (instalación desatendida): la respuesta por defecto es NO."""
        salida = _bash(
            "pedir_confirmacion_solapamiento || echo RECHAZADO\n", stdin="")
        assert "RECHAZADO" in salida.stdout

    def test_mayuscula_tambien_vale(self):
        salida = _bash(
            "pedir_confirmacion_solapamiento\n" 'echo "RC=$?"\n', stdin="S\n")
        assert "RC=0" in salida.stdout


class TestIntegracionConBootstrap:
    """El idioma exacto con el que `bootstrap.sh` llama a la comprobación.

    Importa porque `bootstrap.sh` corre con `set -euo pipefail`: si el código
    de retorno se capturase mal, un solapamiento detectado abortaría el
    instalador **antes** de poder preguntar al coleccionista."""

    def _con_set_e(self, cuerpo: str):
        guion = f'set -euo pipefail\nsource "{RUTAS_SH}"\n{cuerpo}\n'
        return subprocess.run(
            ["bash", "-c", guion], capture_output=True, text=True,
            timeout=30, check=False,
        )

    def test_un_solapamiento_no_aborta_antes_de_preguntar(self, arbol):
        salida = self._con_set_e(
            "ESTADO_RUTAS=0\n"
            f'comprobar_solapamiento "{arbol["biblioteca"]}" '
            f'"{arbol["biblioteca"]}" "{arbol["amule"]}" || ESTADO_RUTAS=$?\n'
            'echo "SEGUIMOS CON ESTADO=${ESTADO_RUTAS}"\n'
        )
        assert salida.returncode == 0
        assert "SEGUIMOS CON ESTADO=1" in salida.stdout

    def test_una_ruta_irresoluble_no_aborta_antes_de_poder_explicarla(self, tmp_path):
        fichero = tmp_path / "fichero"
        fichero.write_text("x")
        salida = self._con_set_e(
            "ESTADO_RUTAS=0\n"
            f'comprobar_solapamiento "{fichero}/nada" "{tmp_path}" "{tmp_path}"'
            ' || ESTADO_RUTAS=$?\n'
            'echo "SEGUIMOS CON ESTADO=${ESTADO_RUTAS}"\n'
        )
        assert salida.returncode == 0
        assert "SEGUIMOS CON ESTADO=2" in salida.stdout
        assert "es un fichero" in salida.stderr

    def test_sin_solapamiento_el_estado_queda_en_cero(self, arbol):
        salida = self._con_set_e(
            "ESTADO_RUTAS=0\n"
            f'comprobar_solapamiento "{arbol["biblioteca"]}" '
            f'"{arbol["descargas"]}" "{arbol["amule"]}" || ESTADO_RUTAS=$?\n'
            'echo "SEGUIMOS CON ESTADO=${ESTADO_RUTAS}"\n'
        )
        assert "SEGUIMOS CON ESTADO=0" in salida.stdout
