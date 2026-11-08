# ruff: noqa: E501
"""RAR 4 HOSTILES para probar el lector con `unar`/`lsar` REALES (#418, dictamen de SecOps M-3, N-1 y generador v2).

Generador en la biblioteca estándar de SecOps (no hace falta el `rar` de RARLAB): el formato RAR 4 «stored» son cabeceras
fijas más CRC. Se generan en cada prueba, sin ficheros binarios en el repositorio. Lo escribió SecOps
(`encargos/rar-hostiles/gen_rar4_hostiles.py`, v2: JPEG 8×8 válido y el caso `tamano_mentira`); aquí se añaden `generar` y
`ESPERADO` para usarlos desde pytest y desde `scripts/comprobar_imagen_rar.py`.
"""
import struct
import zlib
from pathlib import Path

MARCA = b"Rar!\x1a\x07\x00"
FIN = bytes.fromhex("c43d7b00400700")           # bloque de fin de archivo estándar
S_IFREG, S_IFLNK = 0o100644, 0o120777

def crc16(b):
    return zlib.crc32(b) & 0xFFFF

def cabecera_principal():
    cuerpo = struct.pack("<BHH", 0x73, 0, 13) + b"\0" * 6
    return struct.pack("<H", crc16(cuerpo)) + cuerpo

def entrada(nombre: bytes, datos: bytes, *, atributo=S_IFREG, declarado=None):
    unp = len(datos) if declarado is None else declarado
    cuerpo = struct.pack("<BHH", 0x74, 0x8000, 32 + len(nombre))
    cuerpo += struct.pack("<IIBIIBBHI", len(datos), unp, 3, zlib.crc32(datos) & 0xFFFFFFFF,
                          0x5A000000, 20, 0x30, len(nombre), atributo) + nombre
    return struct.pack("<H", crc16(cuerpo)) + cuerpo + datos

JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb0043000201010101010201010102020202020403020202020504"
    "040304060506060605060606070908060709070606080b08090a0a0a0a0a06080b0c0b0a0c090a0a0affdb0043010202"
    "02020202050303050a0706070a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a"
    "0a0a0a0a0a0a0a0a0a0a0a0a0a0affc00011080008000803012200021101031101ffc4001f0000010501010101010100"
    "000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d010203000411051221"
    "31410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a"
    "434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a9293949596979899"
    "9aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1"
    "f2f3f4f5f6f7f8f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b51100"
    "020102040403040705040400010277000102031104052131061241510761711322328108144291a1b1c109233352f015"
    "6272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a63646566676869"
    "6a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4"
    "c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00f8"
    "fe8a28afe773fd903fffd9"
)   # JPEG 8x8 VÁLIDO (Pillow, calidad 95). La v1 llevaba un relleno que NO decodificaba: error de SecOps

CASOS = {
    "traversal.cbr":    (b"../../../tmp/secops-traversal.jpg", JPEG, S_IFREG, None),
    "absoluta.cbr":     (b"/tmp/secops-absoluta.jpg", JPEG, S_IFREG, None),
    "enlace.cbr":       (b"p.jpg", b"/etc/passwd", S_IFLNK, None),
    "comodines.cbr":    (b"[a]*?.jpg", JPEG, S_IFREG, None),
    "salto.cbr":        (b"a\nb.jpg", JPEG, S_IFREG, None),
    "tamano_falso.cbr": (b"p.jpg", b"0123456789", S_IFREG, 50 * 1024 * 1024),
    # v2: miente dentro del tope por entrada (32 MiB): llega a `unar`; la de arriba la corta el lector antes de lanzarlo
    "tamano_mentira.cbr": (b"p.jpg", b"0123456789", S_IFREG, 1024 * 1024),
}

#: Resultado ESPERADO de `portada_de_rar` por caso (SecOps). Si un `unar` saneara de otra manera, la prueba falla y eso es
#: información que hay que ver y documentar, no un criterio que suavizar.
ESPERADO = {
    "traversal.cbr": "portada",         # `unar` extrae con el nombre saneado: nada fuera del destino
    "absoluta.cbr": "portada",
    "comodines.cbr": "portada",
    "salto.cbr": "portada",
    "enlace.cbr": "ilegible",           # el lector rechaza el enlace simbólico
    "tamano_falso.cbr": "demasiado_grande",    # el tope por entrada corta ANTES de lanzar `unar`
    "tamano_mentira.cbr": "ilegible",   # dentro del tope: llega a `unar`, que no trae lo que declara
}


def generar(destino: Path, fichero: str) -> Path:
    """Escribe el RAR hostil `fichero` (una clave de `CASOS`) en `destino` y devuelve su ruta."""
    nombre, datos, attr, declarado = CASOS[fichero]
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / fichero
    ruta.write_bytes(MARCA + cabecera_principal()
                     + entrada(nombre, datos, atributo=attr, declarado=declarado) + FIN)
    return ruta
