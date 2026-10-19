# ruff: noqa: E501
"""S-06 de la fase 1 bis: esperar de forma acotada a que DOCKER declare 'healthy' (reloj y respuestas simulados; sin Docker ni VM).

Origen: en la primera ejecución real S-06 evaluó la aplicación a ~23 s de arrancar; el HEALTHCHECK de la imagen (interval=30s) aún no había
hecho su primer sondeo y Docker decía 'starting'. Era un fallo de sincronización del arnés, no una prueba de que la aplicación estuviera mal.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EJECUTAR = REPO / "docs" / "design" / "m4-fase1bis" / "vm-ejecutar.sh"
ARRANQUE = "RELOJ=0"

BASE = """
set -uo pipefail
export EV="{ev}" ESPERA_SANA_MAX_S={maximo} ESPERA_SANA_PASO_S=5
source "{ejecutar}"
# Reloj simulado en un FICHERO (las funciones se llaman dentro de $(…): una variable no sobreviviría).
echo 0 > "{ev}/reloj"
ahora_s() {{ cat "{ev}/reloj"; }}
dormir_s() {{ echo $(( $(cat "{ev}/reloj") + $1 )) > "{ev}/reloj"; }}
# Respuestas simuladas de `docker inspect` en cola; la última se repite. Una línea 'RC=n texto' devuelve ese código.
printf '%s\\n' {respuestas} > "{ev}/cola"
estado_contenedor() {{
    local l; l=$(head -n 1 "{ev}/cola"); [[ $(wc -l < "{ev}/cola") -gt 1 ]] && sed -i 1d "{ev}/cola"
    echo "${{l#RC=* }}"
    if [[ "$l" == RC=* ]]; then local c="${{l%% *}}"; return "${{c#RC=}}"; fi
    return 0
}}
arranque_contenedor() {{ echo "abc123def456 2026-10-19T08:25:50Z"; }}
api() {{ echo "api llamada" >> "{ev}/api.txt"; echo 200; }}
{cuerpo}
"""


def _correr(tmp_path: Path, respuestas: list[str], cuerpo: str, maximo: int = 60) -> subprocess.CompletedProcess:
    resp = " ".join(f"'{r}'" for r in respuestas)
    guion = BASE.format(ev=tmp_path, maximo=maximo, ejecutar=EJECUTAR, respuestas=resp, cuerpo=cuerpo)
    return subprocess.run(["bash", "-c", guion], capture_output=True, text=True, timeout=60, check=False)


SANA = "running healthy 0 false 0"
ARRANCANDO = "running starting 0 false 0"


class TestEsperarSano:

    def test_starting_y_luego_healthy_es_pass_y_registra_las_transiciones(self, tmp_path):
        r = _correr(tmp_path, [ARRANCANDO, ARRANCANDO, SANA], 'esperar_sano zascarr; echo "rc=$? espera=${SANA_ESPERA_S}"')
        assert "rc=0 espera=10" in r.stdout, r.stdout + r.stderr
        reg = (tmp_path / "salud-zascarr.txt").read_text()
        assert "abc123def456 2026-10-19T08:25:50Z" in reg, "falta el identificador y la hora de arranque del contenedor"
        assert "T+0s running starting" in reg and "T+10s running healthy" in reg and "sano según Docker tras 10s" in reg
        assert reg.count("running starting") == 1, "una transición se registra una vez, no por sondeo"

    def test_starting_hasta_agotar_la_espera_es_fail(self, tmp_path):
        r = _correr(tmp_path, [ARRANCANDO], 'esperar_sano zascarr; echo "rc=$? espera=${SANA_ESPERA_S}"', maximo=30)
        assert "rc=1 espera=30" in r.stdout, r.stdout + r.stderr
        assert "plazo de 30s agotado" in (tmp_path / "salud-zascarr.txt").read_text()

    @pytest.mark.parametrize("estado", ["running unhealthy 0 false 0", "exited - 0 false 0", "exited unhealthy 0 false 137", "dead - 0 false 1",
                                        "inexistente", "running - 0 false 0", "exited healthy 0 false 0", "restarting healthy 3 false 1"],
                             ids=["unhealthy", "terminado-sin-salud", "terminado-con-salud", "dead", "desaparecido", "sin-healthcheck",
                                  "terminado-pero-aun-healthy", "reiniciandose"])
    def test_unhealthy_terminado_desaparecido_o_sin_healthcheck_es_fail_inmediato(self, tmp_path, estado):
        r = _correr(tmp_path, [ARRANCANDO, estado], 'esperar_sano zascarr; echo "rc=$? espera=${SANA_ESPERA_S}"')
        assert "rc=2 espera=5" in r.stdout, r.stdout + r.stderr          # no espera a agotar el plazo

    @pytest.mark.parametrize("respuesta", ["RC=1 Error: No such object", "RC=125 ", "error-ps", ""], ids=["inspect-falla", "rc-125", "error-ps", "salida-vacia"])
    def test_un_error_de_inspeccion_es_un_error_explicito_nunca_pass_ni_se_trata_como_starting(self, tmp_path, respuesta):
        r = _correr(tmp_path, [ARRANCANDO, respuesta], 'esperar_sano zascarr; echo "rc=$? espera=${SANA_ESPERA_S}"')
        assert "rc=3 espera=5" in r.stdout, r.stdout + r.stderr
        assert "ERROR DE INSPECCIÓN" in (tmp_path / "salud-zascarr.txt").read_text()

    def test_un_http_200_no_sustituye_al_estado_de_docker(self, tmp_path):
        r = _correr(tmp_path, [ARRANCANDO], 'esperar_sano zascarr; echo "rc=$?"', maximo=20)
        assert "rc=1" in r.stdout and not (tmp_path / "api.txt").exists(), "se consultó la API o se aceptó un 200 en lugar del estado de Docker"

    def test_no_se_inspecciona_con_docker_inspect_completo(self):
        texto = EJECUTAR.read_text()
        assert "docker inspect -f" in texto and "docker inspect " not in texto.replace("docker inspect -f", ""), \
            "un `docker inspect` completo puede volcar Config.Env (credenciales) a la evidencia"


class TestComprobacionS06:

    def _s06(self, tmp_path, respuestas, maximo=30):
        r = _correr(tmp_path, respuestas, "comprobar_aplicacion_sana", maximo=maximo)
        linea = [x for x in (tmp_path / "resultados.txt").read_text().splitlines() if " S-06 " in f" {x} "]
        return r, linea

    def test_pass_solo_cuando_docker_dice_healthy(self, tmp_path):
        _, linea = self._s06(tmp_path, [ARRANCANDO, SANA])
        assert len(linea) == 1 and linea[0].startswith("PASS S-06") and "tras esperar 5s" in linea[0], linea

    @pytest.mark.parametrize("respuestas,texto", [
        ([ARRANCANDO], "no llegó a 'healthy'"),
        (["running unhealthy 0 false 0"], "no sana o no en marcha"),
        (["exited - 0 false 1"], "no sana o no en marcha"),
        (["RC=1 fallo"], "no se pudo inspeccionar"),
    ], ids=["plazo", "unhealthy", "terminado", "inspeccion"])
    def test_cada_causa_de_fallo_es_un_fail_con_su_motivo(self, tmp_path, respuestas, texto):
        _, linea = self._s06(tmp_path, respuestas)
        assert len(linea) == 1 and linea[0].startswith("FAIL S-06") and texto in linea[0], linea

    def test_el_estado_final_queda_en_contenedores_txt(self, tmp_path):
        self._s06(tmp_path, [ARRANCANDO, SANA])
        assert "zascarr: running healthy" in (tmp_path / "contenedores.txt").read_text()

    def test_la_seccion_de_salud_usa_esta_comprobacion(self):
        texto = EJECUTAR.read_text()
        assert texto.count("comprobar_aplicacion_sana") == 2          # definición + llamada
        assert '== *" healthy "* ]] && pass S-06' not in texto, "S-06 volvió a evaluarse sin esperar"
