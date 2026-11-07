# ruff: noqa: E501
"""RAR 4 HOSTILES para probar el lector con `unar`/`lsar` REALES (#418, dictamen de SecOps M-3).

Generador en la biblioteca estándar de SecOps (no hace falta el `rar` de RARLAB): el formato RAR 4 «stored» son
cabeceras fijas más CRC. Se generan en cada prueba, sin ficheros binarios en el repositorio. Lo escribió SecOps
(`encargos/rar-hostiles/gen_rar4_hostiles.py`); aquí solo se añade `generar` para usarlo desde pytest.
"""
# ruff: noqa: E401, E701, E702
import struct
import zlib
from pathlib import Path

MARCA = b"Rar!\x1a\x07\x00"
FIN = bytes.fromhex("c43d7b00400700")           # bloque de fin de archivo estándar
S_IFREG, S_IFLNK = 0o100644, 0o120777

def crc16(b): return zlib.crc32(b) & 0xFFFF

def cabecera_principal():
    cuerpo = struct.pack("<BHH", 0x73, 0, 13) + b"\0" * 6
    return struct.pack("<H", crc16(cuerpo)) + cuerpo

def entrada(nombre: bytes, datos: bytes, *, atributo=S_IFREG, declarado=None):
    unp = len(datos) if declarado is None else declarado
    cuerpo = struct.pack("<BHH", 0x74, 0x8000, 32 + len(nombre))
    cuerpo += struct.pack("<IIBIIBBHI", len(datos), unp, 3, zlib.crc32(datos) & 0xFFFFFFFF,
                          0x5A000000, 20, 0x30, len(nombre), atributo) + nombre
    return struct.pack("<H", crc16(cuerpo)) + cuerpo + datos

JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb004300") + b"\x08" * 64 + bytes.fromhex("ffd9")

CASOS = {
    "traversal.cbr":    (b"../../../tmp/secops-traversal.jpg", JPEG, S_IFREG, None),
    "absoluta.cbr":     (b"/tmp/secops-absoluta.jpg", JPEG, S_IFREG, None),
    "enlace.cbr":       (b"p.jpg", b"/etc/passwd", S_IFLNK, None),
    "comodines.cbr":    (b"[a]*?.jpg", JPEG, S_IFREG, None),
    "salto.cbr":        (b"a\nb.jpg", JPEG, S_IFREG, None),
    "tamano_falso.cbr": (b"p.jpg", b"0123456789", S_IFREG, 50 * 1024 * 1024),
}

def generar(destino: Path, fichero: str) -> Path:
    """Escribe el RAR hostil `fichero` (una clave de `CASOS`) en `destino` y devuelve su ruta."""
    nombre, datos, attr, declarado = CASOS[fichero]
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / fichero
    ruta.write_bytes(MARCA + cabecera_principal()
                     + entrada(nombre, datos, atributo=attr, declarado=declarado) + FIN)
    return ruta
