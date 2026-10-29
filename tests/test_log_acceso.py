# ruff: noqa: E501
"""#361: el registro de acceso de uvicorn no lleva la query, con uvicorn REAL y con los argumentos del `CMD` del Dockerfile.

Casos de aceptación (informe de QA, B361-01/02/03/04/05/06/09): la prueba decisiva lanza `python -m uvicorn` como lo hace la
imagen (argumentos LEÍDOS del Dockerfile, solo cambia host y puerto), pide rutas con valores centinela en la query y lee la
salida. Exige que aparezca la línea de acceso CON la ruta (para no dar verde por no registrar nada) y que NO aparezca ningún
centinela. El control negativo demuestra que el detector sabe ver una query cuando el filtro no está.
Sin base de datos: el arranque degradado responde, y aun así uvicorn escribe la línea de acceso.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from zascarr.utils.log_acceso import MARCA_DE_QUERY_OMITIDA, SinQueryEnAcceso, instalar_filtro_de_acceso

RAIZ = Path(__file__).resolve().parents[1]
CENTINELAS = {
    "clave": "CENTINELA-CLAVE-7Q",
    "cursor": base64.urlsafe_b64encode(b"Coleccion secreta 001.cbz").decode().rstrip("="),
    "ref": "eyJSRUZFUkVOQ0lBIjoiQ0VOVElORUxBLVJFRiJ9.firmaCENTINELA",
    "q": "CENTINELA-BUSQUEDA-9Z",
}
QUERY = "&".join(f"{k}={v}" for k, v in CENTINELAS.items())


def _registro(args: tuple) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', args, None)


class TestFiltroUnitario:
    def test_quita_la_query_entera_y_conserva_ruta_metodo_y_estado(self):
        r = _registro(("127.0.0.1:5", "GET", "/ui/x?clave=A&cursor=B&ref=C&q=D", "1.1", 200))
        assert SinQueryEnAcceso().filter(r) is True
        assert r.getMessage() == f'127.0.0.1:5 - "GET /ui/x{MARCA_DE_QUERY_OMITIDA} HTTP/1.1" 200'
        assert "clave" not in r.getMessage() and "=" not in r.getMessage()

    def test_sin_query_no_toca_nada(self):
        r = _registro(("127.0.0.1:5", "GET", "/ui/x", "1.1", 200))
        SinQueryEnAcceso().filter(r)
        assert r.getMessage() == '127.0.0.1:5 - "GET /ui/x HTTP/1.1" 200'

    @pytest.mark.parametrize("path", ["/a?", "/a?x", "/a?x=1?y=2", "/a?%s=%%s", "/?" + "?" * 100_000])
    def test_particiones_raras_de_la_query(self, path):
        r = _registro(("c", "GET", path, "1.1", 200))
        SinQueryEnAcceso().filter(r)
        assert r.args[2] == path.split("?", 1)[0] + MARCA_DE_QUERY_OMITIDA

    def test_es_lineal_con_una_query_de_64_kb(self):
        r = _registro(("c", "GET", "/a?" + "x" * 65_536, "1.1", 200))
        t = time.perf_counter()
        SinQueryEnAcceso().filter(r)
        assert time.perf_counter() - t < 0.5

    @pytest.mark.parametrize("args", [(), ("solo",), ("a", "b"), ("a", "b", None, "1.1", 200), ("a", "b", 3, "1.1", 200), None])
    def test_argumentos_inesperados_no_lanzan_y_dejan_pasar_el_registro(self, args):
        r = _registro(("a", "b", "c", "d", 1))
        r.args = args
        assert SinQueryEnAcceso().filter(r) is True

    def test_instalarlo_es_idempotente(self):
        logger = logging.getLogger("uvicorn.access")
        antes = [f for f in logger.filters if isinstance(f, SinQueryEnAcceso)]
        try:
            instalar_filtro_de_acceso()
            instalar_filtro_de_acceso()
            assert len([f for f in logger.filters if isinstance(f, SinQueryEnAcceso)]) == max(1, len(antes))
        finally:
            for f in [f for f in logger.filters if isinstance(f, SinQueryEnAcceso) and f not in antes]:
                logger.removeFilter(f)


def _cmd_del_dockerfile() -> list[str]:
    texto = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    m = re.search(r"^CMD\s*(\[.*?\])\s*$", texto, re.S | re.M)
    assert m, "no encuentro el CMD del Dockerfile"
    cmd = json.loads(re.sub(r"\\\s*\n\s*", " ", m.group(1)))
    assert cmd[:3] == ["python", "-m", "uvicorn"], cmd
    return cmd


def _con_host_y_puerto(cmd: list[str], puerto: int) -> list[str]:
    cmd = list(cmd)
    cmd[cmd.index("--host") + 1] = "127.0.0.1"
    cmd[cmd.index("--port") + 1] = str(puerto)
    cmd[0] = sys.executable
    return cmd


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _servir_y_pedir(cmd: list[str], rutas: list[str], cwd: Path, entorno_extra: dict[str, str] | None = None) -> str:
    puerto = _puerto_libre()
    entorno = {**os.environ, "PYTHONPATH": f"{RAIZ / 'src'}{os.pathsep}{cwd}", "AUTH_MODE": "none", **(entorno_extra or {})}
    proc = subprocess.Popen(_con_host_y_puerto(cmd, puerto), cwd=cwd, env=entorno, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        fin = time.time() + 40
        while time.time() < fin:
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.5).close()
                break
            except OSError:
                if proc.poll() is not None:
                    raise AssertionError(f"uvicorn terminó al arrancar: {proc.stdout.read()[-800:]}") from None
                time.sleep(0.2)
        else:
            raise AssertionError("uvicorn no arrancó a tiempo")
        for ruta in rutas:
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}", headers={"Origin": f"http://127.0.0.1:{puerto}"}), timeout=15).read()
            except urllib.error.HTTPError:
                pass   # 4xx/5xx también escriben su línea de acceso
        time.sleep(0.5)
    finally:
        proc.terminate()
        try:
            salida, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            salida, _ = proc.communicate()
    return salida


RUTAS = [
    f"/ui/pendientes/carpetas/asistente/vinculacion?{QUERY}",
    f"/ui/pendientes/carpetas/asistente/vinculacion/resultado?{QUERY}",
    f"/ui/descubrir?{QUERY}",
    f"/ui/biblioteca?{QUERY}",
]


class TestConUvicornReal:
    def test_con_el_cmd_del_dockerfile_la_query_no_llega_al_registro_pero_si_la_ruta(self, tmp_path):
        salida = _servir_y_pedir(_cmd_del_dockerfile(), RUTAS, RAIZ)
        # El detector no se engaña: hay líneas de acceso con la RUTA (si no, un registro mudo daría verde)
        lineas = [linea for linea in salida.splitlines() if " - \"GET " in linea]
        assert len(lineas) >= len(RUTAS), salida[-1500:]
        for ruta in ("/ui/pendientes/carpetas/asistente/vinculacion", "/ui/descubrir", "/ui/biblioteca"):
            assert any(ruta in linea for linea in lineas), (ruta, lineas[:5])
        for nombre, valor in CENTINELAS.items():
            assert valor not in salida, f"el centinela de «{nombre}» está en el registro"
        assert MARCA_DE_QUERY_OMITIDA in salida
        assert "clave=" not in salida and "ref=" not in salida and "cursor=" not in salida

    def test_con_el_nivel_debug_la_query_tampoco_llega_al_registro(self):
        """Con `--log-level warning` uvicorn ni escribe el acceso (una prueba ahí daría verde por no registrar nada), así
        que solo se ejerce `debug`; `info` es el del CMD."""
        nivel = "debug"
        cmd = _cmd_del_dockerfile()
        cmd[cmd.index("--log-level") + 1] = nivel
        salida = _servir_y_pedir(cmd, RUTAS[:1] + RUTAS[2:3], RAIZ)
        for valor in CENTINELAS.values():
            assert valor not in salida

    def test_un_422_o_un_404_tampoco_dejan_la_query(self):
        salida = _servir_y_pedir(_cmd_del_dockerfile(), [f"/ruta/que/no/existe?{QUERY}", f"/api/series?page=0&{QUERY}"], RAIZ)
        assert "/ruta/que/no/existe" in salida
        for valor in CENTINELAS.values():
            assert valor not in salida

    def test_control_negativo_sin_el_filtro_el_detector_si_ve_la_query(self, tmp_path):
        """Una aplicación ASGI mínima bajo el MISMO uvicorn y los mismos argumentos, pero SIN el filtro: el centinela debe
        aparecer. Si no apareciera, el detector no serviría para nada."""
        (tmp_path / "app_sin_filtro.py").write_text(
            "async def app(scope, receive, send):\n"
            "    if scope['type'] != 'http':\n        return\n"
            "    await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
            "    await send({'type': 'http.response.body', 'body': b'ok'})\n", encoding="utf-8")
        cmd = _cmd_del_dockerfile()
        cmd[cmd.index("zascarr.main:app")] = "app_sin_filtro:app"
        salida = _servir_y_pedir(cmd, RUTAS[:1], tmp_path)
        assert CENTINELAS["clave"] in salida and CENTINELAS["ref"] in salida


class TestRotacionDeLogsEnElCompose:
    COMPOSE = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")

    def test_el_bloque_comun_de_rotacion_es_json_file_10m_por_3(self):
        m = re.search(r"^x-logging: &logging\n((?:  .*\n)+)", self.COMPOSE, re.M)
        assert m, "falta el bloque x-logging"
        bloque = m.group(1)
        assert "driver: json-file" in bloque and 'max-size: "10m"' in bloque and 'max-file: "3"' in bloque

    @pytest.mark.parametrize("servicio", ["postgres", "zascarr"])
    def test_los_servicios_con_estado_usan_la_rotacion(self, servicio):
        inicio = self.COMPOSE.index(f"\n  {servicio}:\n")
        siguiente = re.search(r"\n  [a-z_-]+:\n", self.COMPOSE[inicio + 1:])
        bloque = self.COMPOSE[inicio: inicio + 1 + (siguiente.start() if siguiente else len(self.COMPOSE))]
        assert "logging: *logging" in bloque

    def test_el_presupuesto_se_describe_como_nominal_y_de_disco(self):
        cabecera = self.COMPOSE[: self.COMPOSE.index("x-logging:")]
        assert "NOMINALES" in cabecera and "no un límite" in cabecera and "DISCO" in cabecera
