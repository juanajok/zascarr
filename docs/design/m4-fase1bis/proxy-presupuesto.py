#!/usr/bin/env python3
"""Proxy HTTP/HTTPS con PRESUPUESTO DE DESCARGA medido en el ANFITRIÓN. Solo biblioteca estándar.

Por qué existe (devolución de #242): un tope DENTRO de la VM —una cuota de nftables, el contador `rx_bytes` del invitado— no mide ni acota
lo que el anfitrión descarga de Internet: los paquetes descartados dentro del invitado ya han entrado por su interfaz, y las
retransmisiones siguen contando. La única medida que acota de verdad el consumo es la del lado que tiene la conexión con Internet. Aquí
la VM no tiene red directa (QEMU `restrict=on`): su ÚNICA salida es este proxy (por `guestfwd`), que

  · deja pasar solo a una LISTA de nombres (por defecto, los de Debian y PyPI que necesita la construcción) y solo a los puertos 80/443;
  · cuenta los bytes que LLEGAN de Internet (lo que se descarga), conexión por conexión;
  · al llegar a  TOPE − MARGEN  CORTA: cierra todas las conexiones, rechaza las nuevas y deja el estado en un fichero.

Exceso residual DECLARADO (no se llama «cero»): tras el corte pueden estar ya en tránsito, en el búfer del núcleo de cada conexión de
subida, hasta  SO_RCVBUF efectivo (el núcleo duplica el valor pedido) + un fragmento leído; con como mucho MAX_CONEXIONES conexiones a la vez.
El MARGEN por defecto (8 MiB) cubre ese límite con holgura y el proxy se NIEGA A ARRANCAR si no lo cubre. `tests/test_ensayo_f1bis_arnes.py`
mide el residual real con un emisor independiente del cliente.

Uso: proxy-presupuesto.py --puerto N --tope-mib 600 --estado FICHERO [--margen-mib 8] [--permitidos a.org,b.org]
                          [--max-conexiones 8] [--rcvbuf-kib 128] [--registro FICHERO]
"""
from __future__ import annotations

import argparse
import json
import os
import select
import signal
import socket
import socketserver
import sys
import threading
import time

PERMITIDOS_POR_DEFECTO = "deb.debian.org,security.debian.org,pypi.org,files.pythonhosted.org"
PUERTOS_POR_DEFECTO = "80,443"
FRAGMENTO = 16 * 1024


class Presupuesto:
    """Contadores y estado compartidos entre hilos."""

    def __init__(self, tope_bytes: int, margen_bytes: int, max_conexiones: int, estado: str, registro: str | None):
        self.tope = tope_bytes
        self.corte = tope_bytes - margen_bytes
        self.max_conexiones = max_conexiones
        self.estado = estado
        self.registro = registro
        self.cerrojo = threading.Lock()
        self.recibido = 0           # bytes que LLEGAN de Internet (el presupuesto)
        self.enviado = 0            # bytes que salen hacia Internet (peticiones; informativo)
        self.cortado = False
        self.activas: set[socket.socket] = set()
        self.max_simultaneas = 0
        self.rechazadas_lista = 0
        self.rechazadas_presupuesto = 0
        self.rechazadas_limite = 0
        self.inicio = time.time()

    def contar_recibido(self, n: int) -> bool:
        """Cuenta n bytes recibidos de Internet (SIEMPRE: ya han llegado, se entreguen o no). False —y corta— si con ellos se pasa el umbral."""
        with self.cerrojo:
            self.recibido += n
            if self.cortado:
                return False
            if self.recibido > self.corte:
                self._cortar_locked("umbral de corte")
                return False
            return True

    def _cortar_locked(self, motivo: str) -> None:
        self.cortado = True
        for s in list(self.activas):
            for fn, arg in ((s.shutdown, (socket.SHUT_RDWR,)), (s.close, ())):
                try:
                    fn(*arg)
                except OSError:
                    pass
        self._escribir_locked(motivo)

    def cortar(self, motivo: str) -> None:
        with self.cerrojo:
            if not self.cortado:
                self._cortar_locked(motivo)

    def registrar(self, linea: str) -> None:
        if self.registro:
            with self.cerrojo, open(self.registro, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {linea}\n")

    def alta(self, s: socket.socket) -> bool:
        with self.cerrojo:
            if self.cortado:
                self.rechazadas_presupuesto += 1
                return False
            if len(self.activas) >= self.max_conexiones:
                self.rechazadas_limite += 1
                return False
            self.activas.add(s)
            self.max_simultaneas = max(self.max_simultaneas, len(self.activas))
            return True

    def baja(self, s: socket.socket) -> None:
        with self.cerrojo:
            self.activas.discard(s)

    def escribir(self, motivo: str = "") -> None:
        with self.cerrojo:
            self._escribir_locked(motivo)

    def _escribir_locked(self, motivo: str) -> None:
        datos = {
            "recibido_bytes": self.recibido, "enviado_bytes": self.enviado,
            "tope_bytes": self.tope, "umbral_de_corte_bytes": self.corte,
            "cortado": self.cortado, "motivo": motivo,
            "conexiones_activas": len(self.activas), "max_conexiones_simultaneas": self.max_simultaneas,
            "rechazadas_por_lista": self.rechazadas_lista, "rechazadas_por_presupuesto": self.rechazadas_presupuesto,
            "rechazadas_por_limite": self.rechazadas_limite, "segundos": round(time.time() - self.inicio, 1),
        }
        tmp = f"{self.estado}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f)
        os.replace(tmp, self.estado)


def host_permitido(host: str, permitidos: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == p or host.endswith("." + p) for p in permitidos)


class Manejador(socketserver.BaseRequestHandler):
    presupuesto: Presupuesto
    permitidos: list[str]
    puertos: set[int]
    rcvbuf: int

    def handle(self) -> None:
        p = self.presupuesto
        cliente = self.request
        cliente.settimeout(30)
        try:
            cabecera = b""
            while b"\r\n\r\n" not in cabecera and len(cabecera) < 65536:
                trozo = cliente.recv(4096)
                if not trozo:
                    return
                cabecera += trozo
            cabeza, _, resto = cabecera.partition(b"\r\n\r\n")
            linea, _, cabeceras = cabeza.partition(b"\r\n")
            metodo, _, tail = linea.decode("latin-1").partition(" ")
            destino = tail.rpartition(" ")[0]
            if metodo.upper() == "CONNECT":
                host, _, puerto = destino.rpartition(":")
                ruta = None
            else:
                if not destino.lower().startswith("http://"):
                    return self._responder(cliente, 400, "solo proxy HTTP/CONNECT")
                resto_url = destino[7:]
                autoridad, _, ruta = resto_url.partition("/")
                ruta = "/" + ruta
                host, _, puerto = autoridad.partition(":")
                puerto = puerto or "80"
            try:
                puerto_i = int(puerto)
            except ValueError:
                return self._responder(cliente, 400, "puerto no válido")
            if not host_permitido(host, self.permitidos) or puerto_i not in self.puertos:
                with p.cerrojo:
                    p.rechazadas_lista += 1
                p.registrar(f"RECHAZADO lista {host}:{puerto_i}")
                p.escribir("rechazo por lista")
                return self._responder(cliente, 403, "destino no permitido por el presupuesto del ensayo")
            remoto = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if not p.alta(remoto):
                remoto.close()
                p.escribir("rechazo por presupuesto o límite")
                return self._responder(cliente, 503, "presupuesto agotado o demasiadas conexiones")
            try:
                # El búfer de recepción se fija ANTES de conectar: acota lo que puede estar en tránsito tras un corte.
                remoto.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.rcvbuf)
                remoto.settimeout(30)
                remoto.connect((host, puerto_i))
                if ruta is None:
                    cliente.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    saliente = resto
                else:
                    filtradas = [c for c in cabeceras.split(b"\r\n")
                                 if c and not c.lower().startswith((b"proxy-", b"connection:", b"keep-alive"))]
                    peticion = f"{metodo} {ruta} HTTP/1.1".encode("latin-1") + b"\r\n" + b"\r\n".join(filtradas) \
                        + b"\r\nConnection: close\r\n\r\n" + resto
                    saliente = peticion
                if saliente:
                    remoto.sendall(saliente)
                    with p.cerrojo:
                        p.enviado += len(saliente)
                recibido = self._tunel(cliente, remoto, p)
                p.registrar(f"{metodo} {host}:{puerto_i} recibido={recibido}")
            except OSError as e:
                p.registrar(f"ERROR {host}:{puerto_i} {e.__class__.__name__}")
            finally:
                p.baja(remoto)
                try:
                    remoto.close()
                except OSError:
                    pass
        except OSError:
            return

    @staticmethod
    def _responder(cliente: socket.socket, codigo: int, texto: str) -> None:
        cuerpo = texto.encode()
        cliente.sendall(f"HTTP/1.1 {codigo} {texto}\r\nContent-Length: {len(cuerpo)}\r\nConnection: close\r\n\r\n".encode() + cuerpo)

    @staticmethod
    def _tunel(cliente: socket.socket, remoto: socket.socket, p: Presupuesto) -> int:
        """Copia en ambos sentidos. Lo que llega de Internet se cuenta ANTES de entregarlo y, si se pasa el umbral, se corta."""
        total = 0
        cliente.settimeout(None)
        remoto.settimeout(None)
        pares = [cliente, remoto]
        while True:
            try:
                listos, _, _ = select.select(pares, [], [], 60)
            except (OSError, ValueError):
                return total
            if not listos:
                return total
            for s in listos:
                try:
                    datos = s.recv(FRAGMENTO)
                except OSError:
                    return total
                if not datos:
                    return total
                if s is remoto:
                    if not p.contar_recibido(len(datos)):
                        return total
                    total += len(datos)
                    try:
                        cliente.sendall(datos)
                    except OSError:
                        return total
                else:
                    try:
                        remoto.sendall(datos)
                    except OSError:
                        return total
                    with p.cerrojo:
                        p.enviado += len(datos)


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--puerto", type=int, required=True)
    a.add_argument("--tope-mib", type=int, required=True)
    a.add_argument("--margen-mib", type=int, default=8)
    a.add_argument("--permitidos", default=PERMITIDOS_POR_DEFECTO)
    a.add_argument("--puertos", default=PUERTOS_POR_DEFECTO)
    a.add_argument("--max-conexiones", type=int, default=8)
    a.add_argument("--rcvbuf-kib", type=int, default=128)
    a.add_argument("--estado", required=True)
    a.add_argument("--registro")
    a.add_argument("--escuchar", default="127.0.0.1")
    arg = a.parse_args(argv)

    # El margen tiene que cubrir lo que puede quedar en tránsito en el núcleo tras un corte (el núcleo duplica SO_RCVBUF).
    residual_max = arg.max_conexiones * (2 * arg.rcvbuf_kib * 1024 + FRAGMENTO)
    if arg.margen_mib * 1048576 < residual_max:
        print(f"ERROR: el margen ({arg.margen_mib} MiB) no cubre el residual máximo posible "
              f"({residual_max / 1048576:.2f} MiB = {arg.max_conexiones} conexiones × (2×{arg.rcvbuf_kib} KiB + fragmento)); no arranco.", file=sys.stderr)
        return 2
    p = Presupuesto(arg.tope_mib * 1048576, arg.margen_mib * 1048576, arg.max_conexiones, arg.estado, arg.registro)
    Manejador.presupuesto = p
    Manejador.permitidos = [x.strip().lower() for x in arg.permitidos.split(",") if x.strip()]
    Manejador.puertos = {int(x) for x in arg.puertos.split(",") if x.strip()}
    Manejador.rcvbuf = arg.rcvbuf_kib * 1024
    srv = Servidor((arg.escuchar, arg.puerto), Manejador)
    p.escribir("arrancado")

    def parar(*_):
        p.escribir("parado")
        threading.Thread(target=srv.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, parar)
    signal.signal(signal.SIGINT, parar)

    def volcado():
        while True:
            time.sleep(1)
            p.escribir("" if not p.cortado else "cortado")
    threading.Thread(target=volcado, daemon=True).start()
    print(f"proxy con presupuesto escuchando en {arg.escuchar}:{arg.puerto}; tope {arg.tope_mib} MiB, corte a {arg.tope_mib - arg.margen_mib} MiB; "
          f"destinos: {','.join(Manejador.permitidos)}", flush=True)
    srv.serve_forever()
    p.escribir("parado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
