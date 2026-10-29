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
import contextlib
import http.client
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from zascarr.utils.log_acceso import (
    MARCA_DE_QUERY_OMITIDA,
    REGISTRO_OMITIDO,
    SinQueryEnAcceso,
    instalar_filtro_de_acceso,
)

RAIZ = Path(__file__).resolve().parents[1]
CENTINELAS = {
    "clave": "CENTINELA-CLAVE-7Q",
    "cursor": base64.urlsafe_b64encode(b"Coleccion secreta 001.cbz").decode().rstrip("="),
    "ref": "eyJSRUZFUkVOQ0lBIjoiQ0VOVElORUxBLVJFRiJ9.firmaCENTINELA",
    "q": "CENTINELA-BUSQUEDA-9Z",
}
CENTINELAS["desconocido"] = "CENTINELA-X-NO-LISTADO"        # un nombre que ninguna lista de «prohibidos» conoce
CENTINELAS["codificado"] = "CENTINELA%2FY%20Z"             # valores con %2F y %20: uvicorn escribe la query tal cual
QUERY = "&".join(f"{k}={v}" for k, v in CENTINELAS.items() if k != "codificado") + "&zzz=" + CENTINELAS["codificado"]


def _registro(args: tuple) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', args, None)


class TestFiltroUnitario:
    def test_la_marca_de_query_omitida_es_el_literal_acordado(self):
        assert MARCA_DE_QUERY_OMITIDA == "?…"   # no se compara solo con la propia constante (sería tautológico)

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
    def test_argumentos_sin_query_no_lanzan_y_el_registro_sale_igual(self, args):
        r = _registro(("a", "b", "c", "d", 1))
        r.args = args
        assert SinQueryEnAcceso().filter(r) is True
        assert r.args == args and r.msg != REGISTRO_OMITIDO

    def test_cualquier_argumento_de_texto_con_query_se_limpia_no_solo_el_tercero(self):
        r = _registro(("c?x=1", "GET", "/a?clave=SECRETA", "1.1?y=2", 200))
        SinQueryEnAcceso().filter(r)
        assert "=" not in r.getMessage() and "SECRETA" not in r.getMessage()

    @pytest.mark.parametrize("args", ["texto suelto con ?clave=SECRETA", 12345, object(), ["a", "b?c=SECRETA"]])
    def test_falla_cerrado_si_el_formato_de_los_argumentos_no_se_reconoce(self, args):
        """R-2 de SecOps: si una versión futura de uvicorn cambia la forma de `args`, la línea se pierde en lugar de dejar
        pasar una query. Nunca lanza."""
        r = _registro(("a", "b", "c", "d", 1))
        r.args = args
        assert SinQueryEnAcceso().filter(r) is True
        assert r.msg == REGISTRO_OMITIDO and r.args == ()
        assert "SECRETA" not in r.getMessage()

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


@contextlib.contextmanager
def _uvicorn(cmd: list[str], cwd: Path, entorno_extra: dict[str, str] | None = None):
    """Arranca uvicorn como lo hace la imagen (argumentos del CMD) y cede `(puerto, lineas)`; al salir lo para."""
    puerto = _puerto_libre()
    entorno = {**os.environ, "PYTHONPATH": f"{RAIZ / 'src'}{os.pathsep}{cwd}", "AUTH_MODE": "none", **(entorno_extra or {})}
    proc = subprocess.Popen(_con_host_y_puerto(cmd, puerto), cwd=cwd, env=entorno, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    lineas: list[str] = []
    lector = threading.Thread(target=lambda: lineas.extend(iter(proc.stdout.readline, "")), daemon=True)
    lector.start()
    try:
        fin = time.time() + 40
        while time.time() < fin:
            try:
                socket.create_connection(("127.0.0.1", puerto), timeout=0.5).close()
                break
            except OSError:
                if proc.poll() is not None:
                    lector.join(timeout=2)
                    raise AssertionError(f"uvicorn terminó al arrancar: {''.join(lineas)[-800:]}") from None
                time.sleep(0.2)
        else:
            raise AssertionError("uvicorn no arrancó a tiempo")
        yield puerto, lineas
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        lector.join(timeout=5)


def _esperar_lineas(lineas: list[str], n: int, plazo: float = 5.0) -> None:
    """En vez de dormir un rato fijo, espera a que haya salido una línea por petición (o se agote el plazo)."""
    fin = time.time() + plazo
    while time.time() < fin and sum(1 for linea in lineas if "HTTP/1.1" in linea or "WebSocket" in linea) < n:
        time.sleep(0.1)


def _pedir(puerto: int, ruta: str, cabeceras: dict[str, str] | None = None, datos: dict | None = None) -> tuple[int, str]:
    """GET (o POST de formulario si hay `datos`); devuelve (estado, cuerpo) también ante 4xx/5xx."""
    cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
    peticion = urllib.request.Request(f"http://127.0.0.1:{puerto}{ruta}", data=cuerpo, method="POST" if cuerpo is not None else "GET",
                                      headers={"Origin": f"http://127.0.0.1:{puerto}", **(cabeceras or {})})
    try:
        with urllib.request.urlopen(peticion, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _servir_y_pedir(cmd: list[str], rutas: list, cwd: Path, entorno_extra: dict[str, str] | None = None,
                    estados: dict[str, int] | None = None) -> str:
    with _uvicorn(cmd, cwd, entorno_extra) as (puerto, lineas):
        for item in rutas:
            ruta, cabeceras = item if isinstance(item, tuple) else (item, {})
            try:
                if "Upgrade" in cabeceras:
                    # urllib fuerza `Connection: close` y no deja pedir un Upgrade de verdad: se usa http.client
                    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=15)
                    conexion.putrequest("GET", ruta)
                    for nombre, valor in {"Origin": f"http://127.0.0.1:{puerto}", **cabeceras}.items():
                        conexion.putheader(nombre, valor)
                    conexion.endheaders()
                    respuesta = conexion.getresponse()
                    respuesta.read()
                    if estados is not None:
                        estados[ruta] = respuesta.status
                    conexion.close()
                else:
                    estado, _ = _pedir(puerto, ruta, cabeceras)
                    if estados is not None:
                        estados[ruta] = estado
            except (http.client.HTTPException, ConnectionError):
                pass
        _esperar_lineas(lineas, len(rutas))
    return "".join(lineas)


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
        assert "/ui/pendientes/carpetas/asistente/vinculacion" in salida and "/ui/descubrir" in salida   # no un registro mudo
        for valor in CENTINELAS.values():
            assert valor not in salida

    def test_otras_rutas_y_un_404_tampoco_dejan_la_query(self):
        """Rutas distintas, mismo filtro. Un 422 de validación con base de datos NO se ejerce aquí (el arranque degradado sin
        base responde 503 a todo): NOT RUN con `TEST_DATABASE_URL`; el filtro actúa antes que el estado de la respuesta."""
        salida = _servir_y_pedir(_cmd_del_dockerfile(), [f"/ruta/que/no/existe?{QUERY}", f"/api/series?page=0&{QUERY}"], RAIZ)
        assert "/ruta/que/no/existe" in salida and "/api/series" in salida
        for valor in CENTINELAS.values():
            assert valor not in salida

    def test_el_cmd_del_dockerfile_desactiva_websockets(self):
        """La app no tiene rutas WebSocket y uvicorn escribe su handshake rechazado en `uvicorn.error` (no en
        `uvicorn.access`) con la query: sin `--ws none` el filtro no la alcanza (R-1 de SecOps)."""
        cmd = _cmd_del_dockerfile()
        assert cmd[cmd.index("--ws") + 1] == "none"

    def test_una_peticion_de_upgrade_a_websocket_con_query_tampoco_la_deja_en_el_registro(self):
        cabeceras = {"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
                     "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
        salida = _servir_y_pedir(_cmd_del_dockerfile(), [(f"/ui/descubrir?{QUERY}", cabeceras)], RAIZ)
        for valor in CENTINELAS.values():
            assert valor not in salida

    def test_control_negativo_websockets_activados_el_detector_si_ve_la_query_del_handshake(self):
        """Con `--ws` en `auto` (sin la opción del CMD) el handshake rechazado SÍ deja la query en `uvicorn.error`: demuestra
        que la prueba anterior ve el camino que cubre `--ws none`."""
        cmd = _cmd_del_dockerfile()
        cmd[cmd.index("--ws") + 1] = "auto"
        cabeceras = {"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
                     "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
        salida = _servir_y_pedir(cmd, [(f"/ui/descubrir?{QUERY}", cabeceras)], RAIZ)
        assert CENTINELAS["clave"] in salida, salida[-1200:]

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


URL_PRUEBAS = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not URL_PRUEBAS, reason="NOT RUN sin TEST_DATABASE_URL (Postgres real; la base de pruebas lleva «test» en el nombre)")
class TestEstadosRealesConBaseDeDatos:
    """B361-08 con estados REALES (no el 503 del arranque degradado): una base efímera migrada hace que la app arranque de
    verdad, y se piden una serie inexistente (404) y un parámetro fuera de rango (422), con los centinelas en la query. Se
    exige el estado en la RESPUESTA y en la LÍNEA DE ACCESO, y que ninguna marca llegue al registro."""

    def test_404_y_422_reales_dejan_la_linea_con_su_estado_y_sin_query(self, tmp_path):
        from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
        rutas = [f"/api/series/00000000-0000-4000-8000-000000000404?{QUERY}", f"/api/series?page=0&{QUERY}"]
        estados: dict[str, int] = {}
        with bd_efimera_sync(URL_PRUEBAS) as url:
            migrar_a_head(url)
            entorno = {"DATABASE_URL": url_asyncpg(url), "IMPORT_INTERVAL_MINUTES": "99999", "ENRICH_INTERVAL_MINUTES": "99999",
                       "SCAN_INTERVAL_MINUTES": "99999", "LIBRARY_PATH": str(tmp_path / "lib"),
                       "TRANSMISSION_DOWNLOAD_DIR": str(tmp_path / "t"), "AMULE_INCOMING_DIR": str(tmp_path / "a"),
                       "DOWNLOADS_PATH": str(tmp_path / "d"), "COVERS_CACHE_PATH": str(tmp_path / "c")}
            salida = _servir_y_pedir(_cmd_del_dockerfile(), rutas, RAIZ, entorno, estados)
        assert estados[rutas[0]] == 404 and estados[rutas[1]] == 422, (estados, salida[-800:])
        lineas = [linea for linea in salida.splitlines() if ' - "GET ' in linea]
        assert any("/api/series/00000000-0000-4000-8000-000000000404" in linea and linea.rstrip().endswith("404 Not Found") for linea in lineas), lineas
        assert any(linea.split('"')[1].startswith("GET /api/series") and linea.rstrip().endswith("422 Unprocessable Content")
                   or linea.rstrip().endswith("422 Unprocessable Entity") for linea in lineas), lineas
        for valor in CENTINELAS.values():
            assert valor not in salida


class TestRotacionEfectivaConDockerCompose:
    """La configuración EFECTIVA (con anclas resueltas): `docker compose config --format json`. Sin Docker, NOT RUN: la
    comprobación del texto de arriba (que ignora comentarios) sigue cubriendo los dos servicios."""

    def test_postgres_y_zascarr_tienen_json_file_10m_por_3(self):
        import shutil
        if shutil.which("docker") is None:
            pytest.skip("NOT RUN: no hay Docker")
        r = subprocess.run(["docker", "compose", "-f", str(RAIZ / "docker-compose.yml"), "config", "--format", "json"],
                           capture_output=True, text=True, cwd=RAIZ, env={**os.environ, "DB_PASSWORD": "Sintetica-Prueba-0001"},
                           check=False, timeout=60)
        if r.returncode != 0:
            pytest.skip(f"NOT RUN: `docker compose config` no pudo ejecutarse ({r.stderr.strip()[:120]})")
        servicios = json.loads(r.stdout)["services"]
        for nombre in ("postgres", "zascarr"):
            log = servicios[nombre].get("logging") or {}
            assert log.get("driver") == "json-file", nombre
            assert log.get("options") == {"max-size": "10m", "max-file": "3"}, (nombre, log)


#: B361-07 — INVENTARIO de los parámetros de query de las rutas GET (a 2026-10-29, 29 nombres). Si se añade, renombra o quita uno
#: sin tocar esta lista, `test_el_inventario_coincide_con_las_rutas` FALLA: obliga a mirar si el parámetro nuevo lleva datos de la
#: persona y a seguir viéndolo fuera del registro de acceso. (El filtro quita la query entera, así que el inventario no decide qué
#: se quita: sirve para que nadie dé por «sin datos» un parámetro nuevo sin haberlo mirado.)
PARAMETROS_DE_QUERY = frozenset({
    "anio", "antes", "candidata", "character_id", "clave", "consulta", "cursor", "decision", "desplazamiento", "despues",
    "limite", "next", "operacion", "page", "page_size", "primero", "publisher_id", "q", "ref", "search", "serie_id",
    "series_id", "source", "status", "story_arc_id", "titulo", "tradition", "ultimo", "url",
})


def _rutas_get_de_la_app() -> list:
    from fastapi.routing import APIRoute

    from zascarr.main import app

    def recorrer(contenedor):
        for ruta in contenedor.routes:
            if hasattr(ruta, "original_router"):   # los routers incluidos cuelgan de un envoltorio
                yield from recorrer(ruta.original_router)
            else:
                yield ruta
    return [r for r in recorrer(app) if isinstance(r, APIRoute) and "GET" in r.methods]


class TestInventarioDeParametros:
    def test_el_inventario_coincide_con_las_rutas(self):
        reales = {q.alias or q.name for r in _rutas_get_de_la_app() for q in r.dependant.query_params}
        assert reales == set(PARAMETROS_DE_QUERY), (
            f"inventario desactualizado: nuevos {sorted(reales - PARAMETROS_DE_QUERY)}, "
            f"retirados {sorted(PARAMETROS_DE_QUERY - reales)}. Mira si llevan datos de la persona y actualiza PARAMETROS_DE_QUERY.")

    def test_ninguna_ruta_lee_la_query_a_mano_sin_declararla(self):
        """Un parámetro leído con `request.query_params` no aparece en las rutas: se vigila por texto."""
        usos = [str(p.relative_to(RAIZ)) for p in (RAIZ / "src").rglob("*.py") if "query_params" in p.read_text(encoding="utf-8")]
        assert usos == [], f"hay lectura manual de query_params: {usos}; añádela al inventario y a esta prueba"

    def test_cada_parametro_con_su_centinela_no_llega_al_registro_ni_su_nombre_con_valor(self):
        centinelas = {nombre: f"CENTINELA-{nombre.upper().replace('_', '-')}-INV" for nombre in sorted(PARAMETROS_DE_QUERY)}
        rutas = [f"/ui/descubrir?{nombre}={valor}" for nombre, valor in centinelas.items()]
        salida = _servir_y_pedir(_cmd_del_dockerfile(), rutas, RAIZ)
        assert salida.count('GET /ui/descubrir') >= len(rutas)   # una línea de acceso por petición (no un registro mudo)
        for nombre, valor in centinelas.items():
            assert valor not in salida, f"el valor de «{nombre}» está en el registro"
            assert not re.search(rf"[?&]{re.escape(nombre)}=", salida), f"el nombre «{nombre}=» está en el registro"


def _campos_ocultos(html_: str) -> dict[str, str]:
    import html
    return {html.unescape(n): html.unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', html_)}


def _primero(patron: str, texto: str) -> str:
    import html
    m = re.search(patron, texto)
    assert m, f"no encuentro {patron!r}"
    return html.unescape(m.group(1))


@pytest.mark.skipif(not URL_PRUEBAS, reason="NOT RUN sin TEST_DATABASE_URL (Postgres real; la base de pruebas lleva «test» en el nombre)")
class TestRecorridoCompletoConElFiltro:
    """B361-10/11: el recorrido REAL del asistente de vinculación con el filtro activo y uvicorn real: entrar, revisar, marcar,
    confirmar, abrir el resultado guardado por su `ref` (dos veces: enlace recargable), paginar con el cursor, seguir revisando
    con el enlace que lleva `cursor`. En cada paso, el resultado funcional esperado; al final, el registro de acceso conserva
    ruta y estado de cada petición y NO lleva ninguna query ni dato de la persona (nombre de carpeta, `ref`, cursor)."""

    @staticmethod
    def _sembrar(url: str, biblioteca: Path) -> str:
        import asyncio
        import zipfile
        from uuid import uuid4

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from tests._pg import url_asyncpg
        from zascarr.models import ComicTradition, File, FileFormat, Series

        carpeta = biblioteca / "Comics" / "Carpeta Secreta Del Coleccionista (1999)"
        carpeta.mkdir(parents=True)
        serie_id = uuid4()

        async def sembrar():
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            async with async_sessionmaker(motor, expire_on_commit=False)() as sesion:
                sesion.add(Series(id=serie_id, title="Serie Secreta Local", tradition=ComicTradition.AMERICAN, start_year=1999,
                                  total_issues=200))
                for i in range(1, 121):
                    ruta = carpeta / f"Serie Secreta Local {i:03d} (1999).cbz"
                    with zipfile.ZipFile(ruta, "w") as z:
                        z.writestr("001.jpg", (chr(65 + i % 26) * 300).encode())
                    sesion.add(File(id=uuid4(), file_path=str(ruta), file_name=ruta.name, file_format=FileFormat.CBZ,
                                    file_size_bytes=ruta.stat().st_size, metadata_={"match_status": "unsorted", "candidates": []}))
                await sesion.commit()
            await motor.dispose()
        asyncio.run(sembrar())
        return str(serie_id)

    def test_el_recorrido_funciona_y_el_registro_no_lleva_query(self, tmp_path):
        from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
        clave = "Comics/Carpeta Secreta Del Coleccionista (1999)"
        base = "/ui/pendientes/carpetas/asistente"
        with bd_efimera_sync(URL_PRUEBAS) as url:
            migrar_a_head(url)
            serie_id = self._sembrar(url, tmp_path / "lib")
            entorno = {"DATABASE_URL": url_asyncpg(url), "IMPORT_INTERVAL_MINUTES": "99999", "ENRICH_INTERVAL_MINUTES": "99999",
                       "SCAN_INTERVAL_MINUTES": "99999", "LIBRARY_PATH": str(tmp_path / "lib"),
                       "TRANSMISSION_DOWNLOAD_DIR": str(tmp_path / "t"), "AMULE_INCOMING_DIR": str(tmp_path / "a"),
                       "DOWNLOADS_PATH": str(tmp_path / "d"), "COVERS_CACHE_PATH": str(tmp_path / "c")}
            sensibles: list[str] = []
            pedidas: list[tuple[str, str, int]] = []
            with _uvicorn(_cmd_del_dockerfile(), RAIZ, entorno) as (puerto, lineas):
                def get(ruta):
                    estado, cuerpo = _pedir(puerto, ruta)
                    pedidas.append(("GET", ruta.split("?", 1)[0], estado))
                    return estado, cuerpo

                def post(ruta, datos):
                    estado, cuerpo = _pedir(puerto, ruta, datos=datos, cabeceras={"HX-Request": "true"})
                    pedidas.append(("POST", ruta, estado))
                    return estado, cuerpo

                q = urllib.parse.quote(clave, safe="/")
                # 1. entrar al asistente de la carpeta
                estado, pagina = get(f"{base}?clave={q}")
                assert estado == 200 and "Elegir la serie" in pagina
                # 2. revisar la carpeta para la serie (página 1: 100 archivos)
                estado, pagina = get(f"{base}/vinculacion?clave={q}&series_id={serie_id}")
                assert estado == 200 and "archivos 1–100" in pagina, pagina[:300]
                campos = _campos_ocultos(pagina)
                siguiente = _primero(r'name="ir_a" value="([^"]+)"[^>]*>\s*Página siguiente', pagina)
                sensibles += [siguiente]
                # 3. marcar todos los vinculables (acción del servidor)
                estado, revisada = post(f"{base}/vinculacion/revisar", {**campos, "accion": "marcar_todos"})
                assert estado == 200 and "Vincular 100 archivos" in revisada, revisada[:400]
                # 4. confirmar la página 1
                campos2 = _campos_ocultos(revisada)
                estado, resultado = post(f"{base}/vinculacion/confirmar", {k: campos2[k] for k in ("token", "cursor_actual") if k in campos2})
                assert estado == 200 and "Todos los archivos que preparaste están vinculados" in resultado, resultado[:500]
                ref = _primero(r'resultado\?ref=([^"&]+)', resultado)
                sensibles += [ref]
                # 5. el enlace recargable del resultado guardado, dos veces
                for _ in range(2):
                    estado, guardado = get(f"{base}/vinculacion/resultado?ref={ref}")
                    assert estado == 200 and "Resultado de la vinculación" in guardado
                # 6. paginar con el cursor: segunda página (quedan 20)
                estado, pagina2 = post(f"{base}/vinculacion/revisar", {**campos, "ir_a": siguiente})
                assert estado == 200 and "archivos 1–20" in pagina2, pagina2[:300]   # quedan los 20 que la primera página no cubrió
                c3 = _campos_ocultos(pagina2)
                estado, marcada2 = post(f"{base}/vinculacion/revisar", {**c3, "accion": "marcar_todos"})
                assert estado == 200 and "Vincular 20 archivos" in marcada2, marcada2[:400]
                c4 = _campos_ocultos(marcada2)
                estado, resultado2 = post(f"{base}/vinculacion/confirmar", {k: c4[k] for k in ("token", "cursor_actual") if k in c4})
                assert estado == 200 and "vinculados" in resultado2, resultado2[:400]
                # 7. «Seguir revisando esta carpeta» lleva `cursor`: se abre y responde
                seguir = _primero(r'href="(/ui/pendientes/carpetas/asistente/vinculacion\?clave=[^"]*cursor=[^"]*)"', resultado2)
                sensibles += [_primero(r"cursor=([^&]+)", seguir)]
                estado, _ = get(seguir)
                assert estado == 200
                _esperar_lineas(lineas, len(pedidas))
            salida = "".join(lineas)
        # el registro: una línea por petición con su ruta y su estado, y nada de la query ni de los datos de la persona
        acceso = [linea for linea in salida.splitlines() if ' - "' in linea and ("GET " in linea or "POST " in linea)]
        assert len(acceso) >= len(pedidas), (len(acceso), len(pedidas))
        for metodo, ruta, estado in pedidas:
            assert any(re.search(rf'"{metodo} {re.escape(ruta)}[^"]* HTTP/1.1" {estado}\b', linea) for linea in acceso), (metodo, ruta, estado)
        for marca in ("Carpeta Secreta", "Serie Secreta", "Carpeta%20Secreta", *sensibles):
            assert marca not in salida, f"«{marca[:30]}…» está en el registro de acceso"
        assert not re.search(r"[?&](clave|cursor|ref|series_id)=", salida)


class TestRotacionDeLogsEnElCompose:
    COMPOSE = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")

    def test_el_bloque_comun_de_rotacion_es_json_file_10m_por_3(self):
        m = re.search(r"^x-logging: &logging\n((?:  .*\n)+)", self.COMPOSE, re.M)
        assert m, "falta el bloque x-logging"
        bloque = m.group(1)
        assert "driver: json-file" in bloque and 'max-size: "10m"' in bloque and 'max-file: "3"' in bloque

    #: servicios SIN rotación a propósito: `credenciales` corre, comprueba y termina (no es un contenedor persistente)
    SIN_ROTACION = {"credenciales"}

    def _servicios(self) -> dict[str, str]:
        raiz = self.COMPOSE[self.COMPOSE.index("\nservices:\n"):]
        trozos = re.split(r"\n  ([a-z_-]+):\n", raiz)
        return {nombre: cuerpo for nombre, cuerpo in zip(trozos[1::2], trozos[2::2], strict=True)}

    def test_todos_los_servicios_rotan_salvo_los_de_un_solo_uso_declarados(self):
        servicios = self._servicios()
        assert {"postgres", "zascarr", "credenciales"} <= set(servicios)
        for nombre, cuerpo in servicios.items():
            tiene = re.search(r"(?m)^    logging: \*logging\s*$", cuerpo) is not None   # una línea comentada no cuenta
            assert tiene == (nombre not in self.SIN_ROTACION), nombre

    def test_el_presupuesto_se_describe_como_nominal_y_de_disco(self):
        cabecera = self.COMPOSE[: self.COMPOSE.index("x-logging:")]
        assert "NOMINALES" in cabecera and "no un límite" in cabecera and "DISCO" in cabecera
