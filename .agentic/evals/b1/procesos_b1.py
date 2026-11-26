"""Prueba de procesos real de B1: publicación concurrente y durabilidad."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/src/deploy/ops")
import escritor_estado_actualizar_ops4 as w  # noqa: E402

ID = "0123456789abcdef0123456789abcdef"
BASE = 1_700_000_000


def exige(cond: object, mensaje: str) -> None:
    if not cond:
        raise AssertionError(mensaje)


root = Path(tempfile.mkdtemp(dir="/scratch", prefix="b1-"))
estado = root / "estado.json"
exige(
    w.escribir_estado(estado, w.estado_inicial(ID, BASE)) is w.ResultadoEscritura.OK,
    "escritura inicial",
)
hijo = """
import sys
sys.path.insert(0, "/src/deploy/ops")
import escritor_estado_actualizar_ops4 as w
ruta, base, indice = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
for paso in range(12):
    r = w.publicar_transicion(
        ruta, "en_curso", ahora=base + indice * 100 + paso,
        id_="0123456789abcdef0123456789abcdef", inicio_epoch=base,
        fase="copia", sha_actual="b" * 40,
    )
    if r is w.ResultadoEscritura.INCIERTO:
        sys.exit(3)
"""
procesos = [
    subprocess.Popen(
        [sys.executable, "-B", "-c", hijo, str(estado), str(BASE), str(indice)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for indice in range(4)
]
for proceso in procesos:
    _, error = proceso.communicate()
    exige(proceso.returncode == 0, f"hijo {proceso.returncode}: {error[:200]!r}")

lectura, datos = w.leer_estado_estricto(estado)
exige(lectura is w.ResultadoLectura.OK and datos is not None, f"estado final: {lectura}")
exige(datos["id"] == ID and datos["inicio_epoch"] == BASE, "identidad")
exige(datos["estado"] == "en_curso" and datos["fase"] == "copia", "estado activo")
exige(BASE < datos["actualizado_epoch"] <= BASE + 1200, "época final")


def fsync_roto(_fd: int) -> None:
    raise OSError("fsync simulado")


antes = datos["actualizado_epoch"]
resultado = w.publicar_transicion(
    estado,
    "en_curso",
    ahora=antes + 1,
    id_=ID,
    inicio_epoch=BASE,
    fase="copia",
    fsync=fsync_roto,
)
exige(resultado is w.ResultadoEscritura.INCIERTO, f"durabilidad: {resultado}")
lectura, datos_tras_fallo = w.leer_estado_estricto(estado)
exige(
    lectura is w.ResultadoLectura.OK and datos_tras_fallo == datos,
    "el estado cambió tras un fallo de durabilidad",
)

exige(
    w.publicar_transicion(
        estado,
        "hecha",
        ahora=antes + 2,
        id_=ID,
        inicio_epoch=BASE,
        fase="fin",
        codigo="success:exited:0",
    )
    is w.ResultadoEscritura.OK,
    "cierre terminal",
)
exige(
    w.publicar_transicion(
        estado,
        "en_curso",
        ahora=antes + 3,
        id_=ID,
        inicio_epoch=BASE,
        fase="fin",
    )
    is w.ResultadoEscritura.INVALIDO,
    "se pisó un terminal",
)
exige(sorted(p.name for p in root.iterdir()) == ["estado.json"], "quedaron temporales")
print("procesos B1 ok")
