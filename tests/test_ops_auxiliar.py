"""BL-OPS1 (#443), paso 2: el auxiliar del host `deploy/ops/zascarr_ops.py` (T-01…T-09, T-19, T-23; AC-01…AC-12, 34, 39, 43).

Se prueba la función pura `procesar` con el reloj, el estado y el lanzador inyectados: sin systemd, sin socket y sin tocar
nada del equipo. La lectura acotada se prueba con un `socketpair` real.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("zascarr_ops", RAIZ / "deploy" / "ops" / "zascarr_ops.py")
ops = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ops)

CLAVE = bytes(range(32))
AHORA = 1_800_000_000


class Lanzador:
    """Cuenta los `start` y deja decidir si el cerrojo está tomado o la unidad activa."""

    def __init__(self, ocupado=False, activa=False, inicia=True):
        self.ocupado, self.activa, self.inicia = ocupado, activa, inicia
        self.iniciadas: list[str] = []

    def cerrojo_ocupado(self):
        return self.ocupado

    def estado_unidad(self, unidad):
        return "active" if self.activa else "inactive"

    def iniciar(self, unidad):
        self.iniciadas.append(unidad)
        return self.inicia


@pytest.fixture
def estado(tmp_path):
    (tmp_path / "run").mkdir()
    (tmp_path / "status").mkdir()
    return ops.EstadoOps(str(tmp_path / "run"), str(tmp_path / "status"))


def _id(n: int = 1) -> str:
    return f"{n:032x}"


def peticion(*, id_=None, accion="copia", creada=AHORA, clave=CLAVE, v=1, firma=None, **extra) -> bytes:
    id_ = id_ or _id()
    cuerpo = {"v": v, "id": id_, "accion": accion, "creada": creada,
              "firma": firma if firma is not None else ops.firma_de(clave, v, id_, accion, creada)}
    cuerpo.update(extra)
    return json.dumps(cuerpo, separators=(",", ":")).encode() + b"\n"


def correr(linea, estado, lanzador=None, ahora=AHORA, clave=CLAVE):
    lanzador = lanzador or Lanzador()
    return ops.procesar(linea, ahora, clave, estado, lanzador), lanzador


# ── T-01…T-04: lo que el auxiliar rechaza ───────────────────────────────────────────────────────────────────────
class TestRechazos:
    def test_peticion_valida_se_acepta_inicia_la_unidad_y_deja_ops_status(self, estado):
        r, lanz = correr(peticion(id_=_id(7)), estado)
        assert (r.resultado, r.codigo, r.id) == ("aceptada", "aceptada", _id(7))
        assert lanz.iniciadas == ["zascarr-backup.service"]
        escrito = json.loads(Path(estado.ruta_ops_status).read_text())
        assert escrito == {"schema": 1, "accion": "copia", "id": _id(7), "pedida_epoch": AHORA, "resultado": "aceptada"}
        assert Path(estado.ruta_ops_status).stat().st_mode & 0o777 == 0o644
        assert json.loads(r.linea()) == {"v": 1, "id": _id(7), "resultado": "aceptada", "codigo": "aceptada"}

    @pytest.mark.parametrize("firma_mal", ["0" * 64, "f" * 64, ""])
    def test_firma_erronea_o_ausente(self, estado, firma_mal):
        """AC-02: no se inicia nada y `ops-status.json` no cambia."""
        previo = json.dumps({"schema": 1, "id": "previo"})
        Path(estado.ruta_ops_status).write_text(previo)
        linea = json.dumps({"v": 1, "id": _id(), "accion": "copia", "creada": AHORA, "firma": firma_mal}).encode() + b"\n"
        r, lanz = correr(linea, estado)
        assert r.codigo in ("firma_invalida", "esquema_invalido")
        assert lanz.iniciadas == [] and Path(estado.ruta_ops_status).read_text() == previo

    def test_firma_de_otra_clave(self, estado):
        r, lanz = correr(peticion(clave=bytes(32)), estado)
        assert r.codigo == "firma_invalida" and lanz.iniciadas == []

    @pytest.mark.parametrize("desfase,esperado", [(-600, "caducada"), (-121, "caducada"), (121, "caducada"),
                                                  (-120, "aceptada"), (120, "aceptada"), (0, "aceptada")])
    def test_caducidad(self, estado, desfase, esperado):
        """AC-03: ±120 s exactos se aceptan; más, `caducada`."""
        r, _ = correr(peticion(creada=AHORA + desfase), estado)
        assert r.codigo == esperado

    def test_un_id_repetido_no_inicia_otra_vez(self, estado):
        """AC-04."""
        linea = peticion()
        correr(linea, estado)
        r, lanz = correr(linea, estado, ahora=AHORA + 1)
        assert r.codigo == "repetida" and lanz.iniciadas == []

    def test_el_id_vive_hasta_los_300_segundos(self, estado):
        """AC-39: con `creada = T+120` el `id` sigue visto en T+240 (la caducidad deja un margen de 60 s)."""
        linea = peticion(creada=AHORA + 120)
        correr(linea, estado)
        r, _ = correr(linea, estado, ahora=AHORA + 240)
        assert r.codigo == "repetida"
        # pasados los 300 s se purga: el `id` ya no está en el registro (la petición, eso sí, ha caducado)
        estado.purgar_vistos(AHORA + 301)
        assert estado.marcar_visto(_id(), AHORA + 301) is True

    @pytest.mark.parametrize("accion", ["restaurar", "actualizar", "copia ", "COPIA", "../x", "", "Copia"])
    def test_accion_fuera_de_la_lista(self, estado, accion):
        """AC-06 (T-03): solo `copia`, exacta."""
        r, lanz = correr(peticion(accion=accion), estado)
        assert r.codigo == "accion_no_disponible" and lanz.iniciadas == []

    @pytest.mark.parametrize("linea", [
        peticion(extra="x"),                                                           # clave de más
        json.dumps({"v": 1, "id": _id(), "accion": "copia", "creada": AHORA}).encode() + b"\n",     # falta `firma`
        b'{"v":1,"v":1,"id":"' + _id().encode() + b'","accion":"copia","creada":1,"firma":"' + b"0" * 64 + b'"}\n',
        b"[]\n", b"{}\n", b"no es json\n", b"\xff\xfe\xfd\n", b"", b"\n",
        peticion().rstrip(b"\n"),                                                      # sin salto de línea
        peticion() + b"{}\n",                                                          # dos líneas
        b"x" * 513 + b"\n", b"x" * 1_000_000,
        peticion(v=2),                                                                 # versión distinta
        peticion(id_="A" * 32), peticion(id_="a" * 31), peticion(id_="g" * 32),       # id mal formado
        json.dumps({"v": True, "id": _id(), "accion": "copia", "creada": AHORA, "firma": "0" * 64}).encode() + b"\n",
        json.dumps({"v": 1, "id": _id(), "accion": "copia", "creada": float(AHORA), "firma": "0" * 64}).encode() + b"\n",
        json.dumps({"v": 1, "id": _id(), "accion": 7, "creada": AHORA, "firma": "0" * 64}).encode() + b"\n",
    ])
    def test_esquema_invalido(self, estado, linea):
        """AC-05 (T-04)."""
        r, lanz = correr(linea, estado)
        assert r.codigo == "esquema_invalido" and r.id is None and lanz.iniciadas == []
        assert json.loads(r.linea())["id"] is None

    def test_el_orden_de_comprobacion_no_revela_estado_a_quien_no_sabe_firmar(self, estado):
        """FR-04: con la firma mala, ni la frecuencia ni el cerrojo ni la repetición se evalúan."""
        correr(peticion(id_=_id(1)), estado)                              # deja `aceptadas` y un `id` visto
        r, _ = correr(peticion(id_=_id(1), clave=bytes(32)), estado, Lanzador(ocupado=True), ahora=AHORA + 1)
        assert r.codigo == "firma_invalida"

    def test_sin_clave_responde_no_disponible_a_todo(self, estado):
        """AC-12."""
        r, lanz = correr(peticion(), estado, clave=None)
        assert r.codigo == "no_disponible" and r.diario == "clave_ausente" and lanz.iniciadas == []
        r, _ = correr(b"basura\n", estado, clave=None)
        assert r.codigo == "no_disponible" and r.diario == "clave_ausente"


# ── frecuencia (T-19, T-23; AC-09, 34, 43) ───────────────────────────────────────────────────────────────────────
class TestFrecuencia:
    def _aceptar(self, estado, n, ahora):
        r, _ = correr(peticion(id_=_id(n), creada=ahora), estado, ahora=ahora)
        return r.codigo

    def test_299_segundos_es_demasiado_pronto_y_300_se_acepta(self, estado):
        assert self._aceptar(estado, 1, AHORA) == "aceptada"
        assert self._aceptar(estado, 2, AHORA + 299) == "demasiado_pronto"
        assert self._aceptar(estado, 3, AHORA + 300) == "aceptada"

    def test_tope_de_seis_en_24_horas_y_poda_de_la_ventana(self, estado):
        for i in range(6):
            assert self._aceptar(estado, i, AHORA + i * 301) == "aceptada"
        assert self._aceptar(estado, 90, AHORA + 6 * 301) == "limite_diario"
        # al salir la más antigua de la ventana móvil de 24 h, se acepta
        assert self._aceptar(estado, 91, AHORA + 24 * 3600 + 1) == "aceptada"

    def test_tras_un_reinicio_el_contador_vuelve_a_cero(self, estado):
        for i in range(6):
            self._aceptar(estado, i, AHORA + i * 301)
        os.unlink(estado.ruta_aceptadas)                                  # /run es tmpfs: un reinicio lo vacía
        assert self._aceptar(estado, 50, AHORA + 6 * 301) == "aceptada"

    def test_contador_ausente_es_vacio(self, estado):
        assert estado.leer_aceptadas(AHORA) == []

    @pytest.mark.parametrize("contenido", ["{no es json", '{"a": 1}', '["x"]', "[1.5]", "[true]", "\xff"])
    def test_contador_ilegible_falla_cerrado_y_no_se_reescribe(self, estado, contenido):
        """AC-43: `no_disponible`, `contador_ilegible` en el diario, el fichero igual y nada iniciado."""
        Path(estado.ruta_aceptadas).write_bytes(contenido.encode("latin-1"))
        antes = Path(estado.ruta_aceptadas).read_bytes()
        r, lanz = correr(peticion(), estado)
        assert r.codigo == "no_disponible" and r.diario == "contador_ilegible" and lanz.iniciadas == []
        assert Path(estado.ruta_aceptadas).read_bytes() == antes

    def test_epoca_en_el_futuro_mas_alla_de_300_s_es_ilegible_y_hasta_300_se_interpreta(self, estado):
        Path(estado.ruta_aceptadas).write_text(json.dumps([AHORA + 301]))
        assert correr(peticion(id_=_id(1)), estado)[0].diario == "contador_ilegible"
        Path(estado.ruta_aceptadas).write_text(json.dumps([AHORA + 300]))
        r, _ = correr(peticion(id_=_id(2)), estado)
        assert r.codigo == "demasiado_pronto"                              # se interpreta con normalidad


# ── cerrojo y concurrencia (T-05, T-06; AC-07, 08) ──────────────────────────────────────────────────────────────
class TestCerrojo:
    def test_cerrojo_tomado_o_unidad_activa_es_operacion_en_curso(self, estado):
        for lanz in (Lanzador(ocupado=True), Lanzador(activa=True)):
            r, _ = correr(peticion(id_=_id(len(lanz.iniciadas) + 100 + int(lanz.activa))), estado, lanz)
            assert r.codigo == "operacion_en_curso" and lanz.iniciadas == []

    def test_con_el_cerrojo_ocupado_no_se_gasta_el_contador_ni_se_escribe_ops_status(self, estado):
        correr(peticion(), estado, Lanzador(ocupado=True))
        assert not os.path.exists(estado.ruta_aceptadas) and not os.path.exists(estado.ruta_ops_status)

    def test_cuatro_peticiones_validas_a_la_vez_aceptan_una_y_un_solo_start(self, estado, tmp_path):
        """T-05 / AC-08 (F-5): con `Accept=yes` hay un PROCESO por conexión; el bloqueo abarca leer-decidir-anotar-iniciar.
        Procesos reales (no hilos) y un lanzador lento que ensancha la ventana: exactamente una aceptada y un `start`."""
        import multiprocessing

        registro = tmp_path / "starts.log"

        class Lento(Lanzador):
            def estado_unidad(self, unidad):
                time.sleep(0.05)
                return "inactive"

            def iniciar(self, unidad):
                time.sleep(0.15)
                with open(registro, "a") as fh:
                    fh.write("start\n")
                return True

        def hijo(n, salida):
            r = ops.procesar(peticion(id_=_id(n)), AHORA, CLAVE, estado, Lento())
            salida.send(r.codigo)

        ctx = multiprocessing.get_context("fork")
        tubos = [ctx.Pipe(duplex=False) for _ in range(4)]
        procesos = [ctx.Process(target=hijo, args=(n, tubo[1])) for n, tubo in zip(range(1, 5), tubos, strict=True)]
        for p in procesos:
            p.start()
        for p in procesos:
            p.join(30)
        assert all(t[0].poll(5) for t in tubos), "un proceso hijo murió sin responder"
        codigos = sorted(t[0].recv() for t in tubos)
        assert codigos.count("aceptada") == 1 and codigos.count("demasiado_pronto") == 3, codigos
        assert registro.read_text().count("start") == 1
        assert len(json.loads(Path(estado.ruta_aceptadas).read_text())) == 1

    def test_la_comprobacion_del_cerrojo_no_crea_ni_bloquea(self, tmp_path):
        """FR-11: `ENOENT` = libre y no se crea el fichero; tomado por otro = ocupado; libre = se suelta al instante."""
        import fcntl
        ruta = tmp_path / "ops.lock"
        lanz = ops.LanzadorSystemd(ruta_cerrojo=str(ruta))
        assert lanz.cerrojo_ocupado() is False and not ruta.exists()      # no se crea
        fd = os.open(ruta, os.O_CREAT | os.O_WRONLY)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            assert lanz.cerrojo_ocupado() is True
        finally:
            os.close(fd)
        assert lanz.cerrojo_ocupado() is False                            # soltado: libre otra vez


# ── el lanzador (T-07: entorno vacío) ───────────────────────────────────────────────────────────────────────────
class TestLanzador:
    def test_inicia_con_argumentos_fijos_sin_shell_y_entorno_vacio_salvo_path(self, monkeypatch):
        monkeypatch.setenv("BRANCH", "envenenada")
        monkeypatch.setenv("BACKUP_DIR", "/tmp/otra")
        monkeypatch.setenv("ENV_FILE", "/tmp/otro.env")
        monkeypatch.setenv("REPO_DIR", "/tmp/repo")
        capturado = {}

        def falso(args, **kw):
            capturado["args"], capturado["kw"] = args, kw
            return subprocess.CompletedProcess(args, 0, stdout="inactive\n")

        lanz = ops.LanzadorSystemd(ejecutar=falso)
        assert lanz.iniciar("zascarr-backup.service") is True
        assert capturado["args"] == ["systemctl", "start", "--no-block", "zascarr-backup.service"]
        assert capturado["kw"]["env"] == {"PATH": ops.PATH_FIJO}
        assert not capturado["kw"].get("shell")
        assert lanz.estado_unidad("zascarr-backup.service") == "inactive"
        assert capturado["kw"]["env"] == {"PATH": ops.PATH_FIJO}

    def test_si_systemctl_falla_no_se_acepta(self, estado):
        r, _ = correr(peticion(), estado, Lanzador(inicia=False))
        assert r.codigo == "no_disponible" and r.diario == "inicio_fallido"
        assert not os.path.exists(estado.ruta_ops_status), "SOLO `aceptada` escribe ops-status.json"

    def test_la_unidad_se_deduce_de_la_tabla_del_codigo_no_de_la_peticion(self, estado):
        assert ops.UNIDADES == {"copia": "zascarr-backup.service"}
        r, lanz = correr(peticion(), estado)
        assert lanz.iniciadas == [ops.UNIDADES["copia"]]


# ── ops-status.json (T-09) ───────────────────────────────────────────────────────────────────────────────────────
class TestOpsStatus:
    def test_una_rechazada_firmada_no_pisa_el_rastro_de_la_que_esta_en_marcha(self, estado):
        correr(peticion(id_=_id(1)), estado)
        antes = Path(estado.ruta_ops_status).read_bytes()
        for r in (correr(peticion(id_=_id(2)), estado, ahora=AHORA + 1)[0],               # demasiado_pronto
                  correr(peticion(id_=_id(3), accion="restaurar"), estado, ahora=AHORA + 2)[0],
                  correr(peticion(id_=_id(4)), estado, Lanzador(ocupado=True), ahora=AHORA + 400)[0]):
            assert r.resultado == "rechazada"
        assert Path(estado.ruta_ops_status).read_bytes() == antes


# ── lectura acotada y diario (AC-05, FR-30) ──────────────────────────────────────────────────────────────────────
class TestEntradaSalida:
    def test_no_lee_mas_de_513_bytes_de_una_megabyte(self):
        a, b = socket.socketpair()
        try:
            # el envío va en un hilo: el búfer del socket es menor que 1 MB y `sendall` bloquearía la prueba
            def _enviar():
                with contextlib.suppress(OSError):
                    a.sendall(b"x" * 1_000_000)
            hilo = threading.Thread(target=_enviar, daemon=True)
            hilo.start()
            assert len(ops.leer_linea(b.fileno(), tiempo_s=2)) == 513
        finally:
            a.close()
            b.close()

    def test_para_en_el_salto_de_linea(self):
        a, b = socket.socketpair()
        try:
            a.sendall(b"hola\nresto")
            assert ops.leer_linea(b.fileno(), tiempo_s=2).startswith(b"hola\n")
        finally:
            a.close()
            b.close()

    def test_sin_salto_de_linea_se_rinde_a_los_5_segundos(self):
        a, b = socket.socketpair()
        try:
            a.sendall(b"sin salto")
            assert ops.leer_linea(b.fileno(), tiempo_s=0.3) == b"sin salto"      # no se bloquea esperando
        finally:
            a.close()
            b.close()

    def test_el_diario_no_lleva_cuerpo_firma_clave_ni_rutas(self, estado):
        secreto = "FIRMA-SECRETA-" + "0" * 50
        r, _ = correr(peticion(id_=_id(5)), estado)
        texto = ops.linea_de_diario(r, uid=1000, ms=3)
        assert texto.startswith("accion=copia id=") and "uid=1000" in texto and "ms=3" in texto
        assert "0" * 64 not in texto and secreto not in texto and "/" not in texto
        # una acción que no es la conocida no se vuelca (la cadena es del atacante)
        otro, _ = correr(peticion(accion="X\nINYECTADA"), estado)
        assert "INYECTADA" not in ops.linea_de_diario(otro, 1000, 1)

    def test_leer_clave_exige_64_hexadecimales(self, tmp_path):
        buena = tmp_path / "k1"
        buena.write_text(CLAVE.hex() + "\n")
        assert ops.leer_clave(str(buena)) == CLAVE
        for contenido in ("", "xyz", "00" * 31, "00" * 33, "ZZ" * 32, "AB" * 32):
            mala = tmp_path / "k2"
            mala.write_text(contenido)
            assert ops.leer_clave(str(mala)) is None, contenido
        assert ops.leer_clave(str(tmp_path / "no-existe")) is None

    def test_las_respuestas_son_de_la_lista_cerrada_y_nunca_llevan_texto_libre(self, estado):
        for linea in (peticion(), b"basura\n", peticion(accion="otra"), peticion(clave=bytes(32))):
            r, _ = correr(linea, estado)
            cuerpo = json.loads(r.linea())
            assert set(cuerpo) == {"v", "id", "resultado", "codigo"} and cuerpo["codigo"] in ops.CODIGOS
