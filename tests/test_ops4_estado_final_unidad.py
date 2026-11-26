"""Fase final de estado desde la unidad; no ejecuta update.sh ni systemd.

Se ejecuta la cadena real de `ExecStopPost=` de la unidad sustituyendo solo la
ruta instalada del programa por el módulo del árbol: así la tabla de
`SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` que se prueba es la que se instala.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deploy.ops import estado_actualizar_ops4 as estado
from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoEscritura,
    escribir_estado,
)

RAIZ = Path(__file__).resolve().parents[1]
UNIDAD = RAIZ / "deploy" / "systemd" / "zascarr-actualizar.service"
PROGRAMA_INSTALADO = (
    "/usr/bin/python3 -I /usr/local/lib/zascarr/zascarr-estado-actualizar-ops4"
)
PROGRAMA_ARBOL = (
    f"{sys.executable} -I {RAIZ / 'deploy' / 'ops' / 'estado_actualizar_ops4.py'}"
)
ID = "a" * 32
# El finalizador compara con el reloj real: el estado de prueba debe ser pasado.
AHORA = int(time.time()) - 3600


def _estado(tmp_path, estado_inicial="en_curso", *, inicio=None, actualizado=None):
    inicio = AHORA - 5 if inicio is None else inicio
    actualizado = inicio if actualizado is None else actualizado
    ruta = tmp_path / "ops" / "actualizar-status.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    assert escribir_estado(ruta, {
        "schema": 1, "id": ID, "estado": estado_inicial,
        "inicio_epoch": inicio, "actualizado_epoch": actualizado,
    }) is ResultadoEscritura.OK
    return ruta


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def _comando_stoppost(tmp_path: Path) -> str:
    """Cadena real de ExecStopPost con la ruta instalada apuntando al árbol."""
    texto = UNIDAD.read_text(encoding="utf-8")
    lineas = [linea for linea in texto.splitlines() if linea.startswith("ExecStopPost=")]
    assert len(lineas) == 1, "la unidad debe declarar un único ExecStopPost"
    valor = lineas[0][len("ExecStopPost="):]
    assert valor.startswith("-"), "ExecStopPost debe ir con prefijo - (T-10)"
    comando = valor[1:]
    comando = comando.replace("@ZASCARR_DATA_DIR@", str(tmp_path))
    assert PROGRAMA_INSTALADO in comando
    return comando.replace(PROGRAMA_INSTALADO, PROGRAMA_ARBOL)


def _ejecutar_stoppost(tmp_path: Path, resultado: str, exit_code: str,
                       exit_status: str, *, id_marca: str = "") -> subprocess.CompletedProcess:
    entorno = os.environ.copy()
    invocacion = "b" * 32
    marca = tmp_path / "ops4" / "intentos"
    marca.mkdir(parents=True, exist_ok=True)
    estado = tmp_path / "ops" / "actualizar-status.json"
    id_ = json.loads(estado.read_text(encoding="utf-8")).get("id", ID) if estado.exists() else ID
    (marca / f"inv-{invocacion}").write_text((id_marca or id_) + "\n", encoding="utf-8")
    entorno.update({
        "SERVICE_RESULT": resultado,
        "EXIT_CODE": exit_code,
        "EXIT_STATUS": exit_status,
        "INVOCATION_ID": invocacion,
    })
    return subprocess.run(
        ["/bin/sh", "-c", _comando_stoppost(tmp_path)],
        env=entorno, capture_output=True, text=True, timeout=30, check=False,
    )


# ── Tabla normativa pura ────────────────────────────────────────────────────


@pytest.mark.parametrize("resultado,exit_code,exit_status,esperado", [
    ("success", "exited", "0", "hecha"),
    ("exit-code", "exited", "75", "fallida"),
    ("exit-code", "exited", "1", "incierta"),
    ("exit-code", "exited", "2", "incierta"),
    ("exit-code", "exited", "76", "fallida"),
    ("timeout", "exited", "0", "incierta"),
    ("timeout", "killed", "TERM", "incierta"),
    ("signal", "killed", "15", "incierta"),
    ("killed", "killed", "9", "incierta"),
    ("watchdog", "exited", "0", "incierta"),
    ("success", "killed", "0", "incierta"),
])
def test_resultado_final_mapea_sin_inventar_exito(resultado, exit_code,
                                                  exit_status, esperado) -> None:
    assert estado.resultado_final(resultado, exit_code, exit_status) == esperado


@pytest.mark.parametrize("resultado,exit_code,exit_status", [
    (None, "exited", "0"),
    ("success", None, "0"),
    ("success", "exited", None),
    ("success", "exited", 0),
    (True, "exited", "0"),
])
def test_resultado_final_solo_acepta_el_contrato_de_systemd(resultado, exit_code,
                                                           exit_status) -> None:
    assert estado.resultado_final(resultado, exit_code, exit_status) is None


def test_una_marca_de_otro_intento_no_cierra_el_estado(tmp_path) -> None:
    ruta = _estado(tmp_path, "en_curso")
    antes = _leer(ruta)
    _ejecutar_stoppost(
        tmp_path, "success", "exited", "0", id_marca="b" * 32,
    )
    assert _leer(ruta) == antes


def test_stoppost_no_confunde_marca_historica_de_peticion(tmp_path) -> None:
    ruta = _estado(tmp_path, "en_curso")
    antes = ruta.read_bytes()
    directorio = tmp_path / "ops4" / "intentos"
    directorio.mkdir(parents=True)
    historica = directorio / ("b" * 32)
    historica.write_text(ID + "\n", encoding="ascii")
    entorno = os.environ.copy()
    entorno.update(SERVICE_RESULT="success", EXIT_CODE="exited", EXIT_STATUS="0",
                   INVOCATION_ID="b" * 32)
    completado = subprocess.run(
        ["/bin/sh", "-c", _comando_stoppost(tmp_path)], env=entorno,
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert completado.returncode == 0, completado.stderr
    assert ruta.read_bytes() == antes
    assert historica.read_text(encoding="ascii") == ID + "\n"


# ── Cadena real de ExecStopPost ─────────────────────────────────────────────


@pytest.mark.parametrize("service_result,exit_code,exit_status,estado_inicial,esperado", [
    ("success", "exited", "0", "aceptada", "hecha"),
    ("success", "exited", "0", "en_curso", "hecha"),
    ("exit-code", "exited", "75", "aceptada", "fallida"),
    ("exit-code", "exited", "75", "en_curso", "fallida"),
    ("exit-code", "exited", "2", "en_curso", "incierta"),
    ("exit-code", "exited", "76", "aceptada", "fallida"),
    ("exit-code", "exited", "1", "en_curso", "incierta"),
    ("timeout", "exited", "0", "en_curso", "incierta"),
    ("signal", "killed", "15", "en_curso", "incierta"),
])
def test_cadena_real_escribe_terminal_honesto(tmp_path, service_result,
                                              exit_code, exit_status,
                                              estado_inicial, esperado) -> None:
    ruta = _estado(tmp_path, estado_inicial)
    completado = _ejecutar_stoppost(tmp_path, service_result, exit_code, exit_status)
    assert completado.returncode == 0, completado.stderr
    datos = _leer(ruta)
    assert datos["estado"] == esperado
    assert datos["id"] == ID
    assert datos["inicio_epoch"] == AHORA - 5


def test_cadena_real_conserva_id_e_inicio_y_actualiza_epoch(tmp_path) -> None:
    ruta = _estado(tmp_path)
    completado = _ejecutar_stoppost(tmp_path, "success", "exited", "0")
    assert completado.returncode == 0, completado.stderr
    datos = _leer(ruta)
    assert set(datos) == {
        "schema", "id", "unidad", "estado", "fase", "inicio_epoch",
        "actualizado_epoch", "head0", "sha_destino", "sha_actual",
        "resultado", "codigo",
    }
    assert datos["schema"] == 2
    assert datos["id"] == ID
    assert datos["inicio_epoch"] == AHORA - 5
    assert datos["actualizado_epoch"] >= datos["inicio_epoch"]
    assert datos["fase"] == "fin"
    assert (datos["estado"], datos["resultado"]) == ("hecha", "hecha")
    assert datos["codigo"] == "success:exited:0"


def test_cadena_real_sin_estado_no_crea_ni_falla(tmp_path) -> None:
    (tmp_path / "ops").mkdir()
    completado = _ejecutar_stoppost(tmp_path, "success", "exited", "0")
    assert completado.returncode == 0, completado.stderr
    assert not (tmp_path / "ops" / "actualizar-status.json").exists()


@pytest.mark.parametrize("service_result,exit_code,exit_status", [
    ("success", "exited", "0"),
    ("exit-code", "exited", "1"),
    ("signal", "killed", "15"),
])
def test_cadena_real_no_pisa_un_terminal(tmp_path, service_result,
                                         exit_code, exit_status) -> None:
    ruta = _estado(tmp_path, "hecha")
    completado = _ejecutar_stoppost(tmp_path, service_result, exit_code, exit_status)
    assert completado.returncode == 0, completado.stderr
    assert _leer(ruta)["estado"] == "hecha"


def test_cadena_real_con_reloj_invertido_no_escribe(tmp_path) -> None:
    futuro = int(time.time()) + 3600
    ruta = _estado(tmp_path, inicio=futuro, actualizado=futuro)
    antes = ruta.read_bytes()
    completado = _ejecutar_stoppost(tmp_path, "success", "exited", "0")
    assert completado.returncode == 0, completado.stderr
    assert ruta.read_bytes() == antes


def test_cadena_real_json_ajeno_no_se_toca(tmp_path) -> None:
    ruta = tmp_path / "ops" / "actualizar-status.json"
    ruta.parent.mkdir(parents=True)
    ruta.write_text('{"otra":"cosa"}\n', encoding="utf-8")
    completado = _ejecutar_stoppost(tmp_path, "success", "exited", "0")
    assert completado.returncode == 0, completado.stderr
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"otra": "cosa"}


# ── CLI y fallos de escritura ───────────────────────────────────────────────


def _intento(tmp_path: Path, id_: str = ID) -> list[str]:
    ruta = tmp_path / "intento"
    ruta.write_text(id_ + "\n", encoding="utf-8")
    return ["--intento", str(ruta)]


@pytest.mark.parametrize("resultado", ["", "ok", "en_curso", "hecha\n"])
def test_resultado_cerrado(tmp_path, resultado) -> None:
    ruta = _estado(tmp_path)
    assert estado.main(["--ruta", str(ruta), "--resultado", resultado]) == 2


def test_sin_estado_no_inventa_ni_falla(tmp_path) -> None:
    assert estado.main([
        "--ruta", str(tmp_path / "no-existe.json"), "--resultado", "hecha",
        *_intento(tmp_path),
    ]) == 0


def test_fallo_durable_devuelve_1_pero_la_unidad_lo_ignora(tmp_path, monkeypatch) -> None:
    ruta = _estado(tmp_path)
    monkeypatch.setattr(
        estado, "publicar_transicion", lambda *a, **k: ResultadoEscritura.INCIERTO,
    )
    assert estado.main([
        "--ruta", str(ruta), "--resultado", "hecha", *_intento(tmp_path),
    ]) == 1
    assert _leer(ruta)["estado"] == "en_curso"
    # El prefijo - de la unidad ya está cubierto por _comando_stoppost (T-10).


def test_fichero_de_estado_no_sigue_enlaces(tmp_path) -> None:
    real = _estado(tmp_path)
    enlace = tmp_path / "ops" / "enlace.json"
    enlace.symlink_to(real)
    assert estado.main([
        "--ruta", str(enlace), "--resultado", "hecha", *_intento(tmp_path),
    ]) == 0
    assert _leer(real)["estado"] == "en_curso"


@pytest.mark.parametrize("service_result,exit_code,exit_status,codigo", [
    ("success", "exited", "0", "success:exited:0"),
    ("exit-code", "exited", "75", "exit-code:exited:75"),
    ("signal", "killed", "15", "otro"),
])
def test_cadena_real_escribe_codigo_cerrado(tmp_path, service_result, exit_code,
                                            exit_status, codigo) -> None:
    ruta = _estado(tmp_path)
    completado = _ejecutar_stoppost(tmp_path, service_result, exit_code, exit_status)
    assert completado.returncode == 0, completado.stderr
    datos = _leer(ruta)
    assert datos["fase"] == "fin"
    assert datos["resultado"] == datos["estado"]
    assert datos["codigo"] == codigo


def test_modo_terminal_sin_codigo_usa_otro(tmp_path) -> None:
    ruta = _estado(tmp_path)
    assert estado.main([
        "--ruta", str(ruta), "--resultado", "hecha", *_intento(tmp_path),
    ]) == 0
    datos = _leer(ruta)
    assert (datos["estado"], datos["resultado"], datos["codigo"]) == ("hecha", "hecha", "otro")


def test_modo_terminal_sin_intento_se_rechaza(tmp_path) -> None:
    ruta = _estado(tmp_path)
    antes = _leer(ruta)
    assert estado.main(["--ruta", str(ruta), "--resultado", "hecha"]) == 2
    assert _leer(ruta) == antes
