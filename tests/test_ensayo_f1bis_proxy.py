# ruff: noqa: E501
"""El PRESUPUESTO DE DESCARGA se mide y se hace cumplir en el ANFITRIÓN (`docs/design/m4-fase1bis/proxy-presupuesto.py`).

Devolución de #242: una cuota de nftables DENTRO de la VM descarta paquetes que ya entraron por la interfaz (y las retransmisiones siguen
contando en `rx_bytes`): no acota lo que se descarga de Internet. La VM no tiene red directa (QEMU `restrict=on`); su única salida es este
proxy, que cuenta los bytes que LLEGAN de Internet y corta al umbral. Estas pruebas lo ejercitan con un «Internet» de mentira en el bucle local:
un emisor INDEPENDIENTE del cliente (sigue enviando hasta que el núcleo se lo impide) y la medida real del residual con `TCP_INFO.tcpi_bytes_acked` (lo que el
núcleo del anfitrión llegó a aceptar del emisor). Sin QEMU, sin Docker, sin red externa.
"""
from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="requiere Linux")

DOC = Path(__file__).resolve().parents[1] / "docs" / "design" / "m4-fase1bis"
PROXY = DOC / "proxy-presupuesto.py"
RELAY = DOC / "relay-proxy.py"
MIB = 1048576


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Origen:
    """Un «Internet» de mentira: sirve /grande (flujo sin fin) y /pequeno (100 KiB). Cuenta conexiones y mide `bytes_acked` con `ss`."""

    def __init__(self) -> None:
        self.puerto = _puerto_libre()
        self.conexiones = 0
        self.enviado = 0                 # bytes que el núcleo aceptó del emisor (cota superior de lo ACK-eado)
        self.max_acked = 0               # máximo `bytes_acked` observado con ss: lo que el núcleo del anfitrión llegó a recibir
        self._cerrar = threading.Event()
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", self.puerto))
        self._srv.listen(16)
        self._hilos: list[threading.Thread] = []
        threading.Thread(target=self._aceptar, daemon=True).start()

    def _aceptar(self) -> None:
        self._srv.settimeout(0.2)
        while not self._cerrar.is_set():
            try:
                c, _ = self._srv.accept()
            except (TimeoutError, OSError):
                continue
            self.conexiones += 1
            t = threading.Thread(target=self._servir, args=(c,), daemon=True)
            t.start()
            self._hilos.append(t)

    def _servir(self, c: socket.socket) -> None:
        try:
            c.settimeout(5)
            peticion = b""
            while b"\r\n\r\n" not in peticion:
                d = c.recv(4096)
                if not d:
                    return
                peticion += d
            if b" /pequeno" in peticion.split(b"\r\n")[0]:
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 102400\r\nConnection: close\r\n\r\n" + b"x" * 102400)
                return
            c.sendall(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
            trozo = b"y" * 65536
            c.settimeout(0.5)
            fin = time.time() + 25
            while not self._cerrar.is_set() and time.time() < fin:
                try:
                    self.enviado += c.send(trozo)
                except TimeoutError:
                    continue                      # búfer de envío lleno: el receptor no lee
                except OSError:
                    break
            # `tcpi_bytes_acked` (struct tcp_info, offset 120): lo que el núcleo del RECEPTOR llegó a aceptar de este emisor.
            with contextlib.suppress(OSError, struct.error):
                info = c.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 232)
                self.max_acked = max(self.max_acked, struct.unpack_from("<Q", info, 120)[0])
        except OSError:
            return
        finally:
            with contextlib.suppress(OSError):
                c.close()

    def cerrar(self) -> None:
        self._cerrar.set()
        with contextlib.suppress(OSError):
            self._srv.close()


@pytest.fixture
def origen():
    o = Origen()
    yield o
    o.cerrar()


def _arrancar_proxy(tmp_path: Path, origen_puerto: int | None, *, tope=5, margen=2, extra=(), rcvbuf=64, permitidos="localhost"):
    puerto = _puerto_libre()
    estado = tmp_path / "estado.json"
    args = [sys.executable, str(PROXY), "--puerto", str(puerto), "--tope-mib", str(tope), "--margen-mib", str(margen),
            "--permitidos", permitidos, "--estado", str(estado), "--registro", str(tmp_path / "proxy.log"),
            "--rcvbuf-kib", str(rcvbuf), "--puertos", str(origen_puerto) if origen_puerto else "80,443", *extra]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    fin = time.time() + 10
    while time.time() < fin:
        with contextlib.suppress(OSError):
            socket.create_connection(("127.0.0.1", puerto), timeout=0.3).close()
            return p, puerto, estado
        if p.poll() is not None:
            break
        time.sleep(0.1)
    p.kill()
    raise AssertionError(f"el proxy no arrancó: {p.stderr.read() if p.stderr else ''}")


def _pedir(proxy_puerto: int, destino_puerto: int, ruta="/grande", *, connect=False, host="localhost", limite=None, tiempo=25, mantener=0.0):
    """Cliente del proxy. → (código, bytes recibidos del cuerpo). `limite`: dejar de leer tras esos bytes."""
    s = socket.create_connection(("127.0.0.1", proxy_puerto), timeout=5)
    s.settimeout(tiempo)
    if connect:
        s.sendall(f"CONNECT {host}:{destino_puerto} HTTP/1.1\r\nHost: {host}:{destino_puerto}\r\n\r\n".encode())
        cab = b""
        while b"\r\n\r\n" not in cab:
            d = s.recv(4096)
            if not d:
                return 0, 0
            cab += d
        codigo = int(cab.split()[1])
        if codigo != 200:
            return codigo, 0
        s.sendall(f"GET {ruta} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
        recibido = len(cab.partition(b"\r\n\r\n")[2])
        cuerpo_codigo = 200
    else:
        s.sendall(f"GET http://{host}:{destino_puerto}{ruta} HTTP/1.1\r\nHost: {host}:{destino_puerto}\r\n\r\n".encode())
        cab = b""
        while b"\r\n\r\n" not in cab:
            d = s.recv(4096)
            if not d:
                return 0, 0
            cab += d
        codigo = int(cab.split()[1])
        recibido = len(cab.partition(b"\r\n\r\n")[2])
        cuerpo_codigo = codigo
        if codigo != 200:
            return codigo, 0
    total = recibido
    try:
        while limite is None or total < limite:
            d = s.recv(65536)
            if not d:
                break
            total += len(d)
    except (TimeoutError, ConnectionError, OSError):
        pass
    finally:
        time.sleep(mantener)                  # mantiene la conexión abierta (para ocupar un hueco del límite de conexiones)
        s.close()
    return cuerpo_codigo, total


def _estado(estado: Path) -> dict:
    return json.loads(estado.read_text())


def _parar(p: subprocess.Popen) -> None:
    if p.poll() is None:
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


class TestPresupuestoEnElAnfitrion:

    @pytest.mark.parametrize("connect", [False, True], ids=["http-absoluta", "connect-https"])
    def test_corta_al_umbral_y_el_emisor_independiente_deja_de_ser_aceptado(self, tmp_path, origen, connect):
        """Tope 5 MiB, margen 2 (corte a 3 MiB). El emisor sigue enviando sin fin: lo que cesa es lo que el núcleo del anfitrión acepta."""
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto)
        try:
            codigo, recibido = _pedir(puerto, origen.puerto, connect=connect)
            time.sleep(1.0)
            st = _estado(estado)
            assert codigo == 200 and st["cortado"] is True, st
            assert st["recibido_bytes"] <= 3 * MIB + 16384 + 64 * 1024, f"el proxy contó {st['recibido_bytes']}"
            assert recibido <= st["recibido_bytes"], "se entregó al cliente más de lo contado"
            # El emisor seguía enviando: lo que el núcleo del anfitrión llegó a ACEPTAR (bytes_acked) es la medida real del residual.
            if True:
                residual = origen.max_acked - st["recibido_bytes"]
                declarado = 8 * (2 * 64 * 1024 + 16 * 1024)
                assert origen.max_acked <= 5 * MIB, f"el anfitrión recibió {origen.max_acked / MIB:.2f} MiB: supera el tope de 5"
                assert residual <= declarado, f"residual medido {residual} B > declarado {declarado} B"
                print(f"\n[residual medido] contado={st['recibido_bytes']} B, aceptado por el núcleo (bytes_acked)={origen.max_acked} B, "
                      f"residual={residual} B (declarado ≤ {declarado} B); el emisor llegó a ofrecer {origen.enviado} B")
        finally:
            _parar(p)

    def test_tras_el_corte_rechaza_las_nuevas_sin_contactar_con_el_origen(self, tmp_path, origen):
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto)
        try:
            _pedir(puerto, origen.puerto)
            time.sleep(0.5)
            antes = origen.conexiones
            codigo, _ = _pedir(puerto, origen.puerto, "/pequeno")
            assert codigo == 503 and origen.conexiones == antes, "tras el corte se contactó con el origen"
            assert _estado(estado)["rechazadas_por_presupuesto"] >= 1
        finally:
            _parar(p)

    def test_por_debajo_del_umbral_pasa_todo_y_cuenta_exactamente(self, tmp_path, origen):
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto)
        try:
            codigo, recibido = _pedir(puerto, origen.puerto, "/pequeno")
            time.sleep(1.2)
            st = _estado(estado)
            assert codigo == 200 and recibido == 102400
            assert st["cortado"] is False and st["recibido_bytes"] >= 102400, st      # cuerpo + cabeceras de respuesta
            assert st["recibido_bytes"] < 102400 + 1024
        finally:
            _parar(p)

    def test_solo_los_destinos_de_la_lista_y_nunca_se_contacta_con_los_demas(self, tmp_path, origen):
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto)       # lista: solo «localhost»
        try:
            codigo, _ = _pedir(puerto, origen.puerto, connect=True, host="127.0.0.1")
            assert codigo == 403 and origen.conexiones == 0, "se contactó con un destino fuera de la lista"
            codigo, _ = _pedir(puerto, origen.puerto, host="127.0.0.1")
            assert codigo == 403 and origen.conexiones == 0
            assert _estado(estado)["rechazadas_por_lista"] >= 2
        finally:
            _parar(p)

    def test_el_puerto_tambien_esta_limitado(self, tmp_path, origen):
        p, puerto, _ = _arrancar_proxy(tmp_path, origen.puerto)            # solo se admite el puerto del origen de la prueba
        try:
            otro = _puerto_libre()
            codigo, _ = _pedir(puerto, otro, "/pequeno")
            assert codigo == 403
        finally:
            _parar(p)

    def test_subdominios_si_y_nombres_parecidos_no(self, tmp_path, origen):
        p, puerto, _ = _arrancar_proxy(tmp_path, origen.puerto, permitidos="ejemplo.org")
        try:
            assert _pedir(puerto, origen.puerto, host="evilejemplo.org")[0] == 403
            assert _pedir(puerto, origen.puerto, host="ejemplo.org.mal.net")[0] == 403
        finally:
            _parar(p)

    def test_el_numero_de_conexiones_simultaneas_esta_acotado(self, tmp_path, origen):
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto, tope=50, margen=8, extra=("--max-conexiones", "2"))
        try:
            hilos = [threading.Thread(target=_pedir, args=(puerto, origen.puerto), kwargs={"limite": 200000, "tiempo": 6, "mantener": 3.0}) for _ in range(2)]
            for h in hilos:
                h.start()
            time.sleep(1.0)
            codigo, _ = _pedir(puerto, origen.puerto, "/pequeno")
            assert codigo == 503
            assert _estado(estado)["rechazadas_por_limite"] >= 1
            for h in hilos:
                h.join()
        finally:
            _parar(p)

    def test_un_margen_que_no_cubre_el_residual_maximo_no_arranca(self, tmp_path):
        r = subprocess.run([sys.executable, str(PROXY), "--puerto", str(_puerto_libre()), "--tope-mib", "5", "--margen-mib", "0",
                            "--estado", str(tmp_path / "e.json")], capture_output=True, text=True, timeout=20, check=False)
        assert r.returncode == 2 and "no cubre el residual máximo" in r.stderr

    def test_sigterm_deja_el_estado_escrito(self, tmp_path, origen):
        p, puerto, estado = _arrancar_proxy(tmp_path, origen.puerto)
        _pedir(puerto, origen.puerto, "/pequeno")
        p.send_signal(signal.SIGTERM)
        p.wait(timeout=10)
        assert _estado(estado)["motivo"] == "parado" and _estado(estado)["recibido_bytes"] >= 102400


class TestRelayDelInvitado:

    def test_el_puente_reenvia_en_ambos_sentidos(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        puerto = srv.getsockname()[1]

        def eco():
            c, _ = srv.accept()
            while True:
                d = c.recv(4096)
                if not d:
                    break
                c.sendall(d.upper())
            c.close()
        threading.Thread(target=eco, daemon=True).start()
        r = subprocess.run([sys.executable, str(RELAY), str(puerto)], input=b"hola proxy", capture_output=True, timeout=20, check=False)
        srv.close()
        assert r.stdout == b"HOLA PROXY", r.stderr
