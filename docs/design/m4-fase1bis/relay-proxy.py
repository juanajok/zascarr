#!/usr/bin/env python3
"""Puente entrada/salida estándar ↔ TCP local, para el `guestfwd=…-cmd:` de QEMU. Solo biblioteca estándar.

QEMU lanza una instancia por cada conexión del invitado a 10.0.2.100:3128 y conecta su flujo a stdin/stdout de este proceso; aquí se
reenvía al proxy con presupuesto del anfitrión (127.0.0.1:PUERTO). Uso: relay-proxy.py PUERTO
"""
from __future__ import annotations

import os
import select
import socket
import sys


def main() -> int:
    puerto = int(sys.argv[1])
    s = socket.create_connection(("127.0.0.1", puerto), timeout=10)
    s.settimeout(None)
    entrada, salida = sys.stdin.fileno(), sys.stdout.fileno()
    abierto = True
    while True:
        listos, _, _ = select.select([s] + ([entrada] if abierto else []), [], [], 120)
        if not listos:
            return 0
        for f in listos:
            if f is s:
                datos = s.recv(65536)
                if not datos:
                    return 0
                os.write(salida, datos)
            else:
                datos = os.read(entrada, 65536)
                if not datos:
                    abierto = False
                    s.shutdown(socket.SHUT_WR)
                else:
                    s.sendall(datos)


if __name__ == "__main__":
    sys.exit(main())
