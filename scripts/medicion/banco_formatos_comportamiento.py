# ruff: noqa: E501
"""Banco de pruebas del spike #305: qué hace ZascArr HOY con cada tipo de contenedor (ficheros SINTÉTICOS en un directorio temporal).

No toca ninguna biblioteca real ni la red: fabrica una mini-biblioteca con los mismos contenidos metidos en distintos envoltorios (ZIP, TAR,
7z, con y sin extensión, con doble extensión) y ejecuta las funciones REALES del importador, del triaje, de la portada y de la auditoría.

No hay herramienta para CREAR un RAR aquí: los casos RAR llevan solo la FIRMA de un RAR5 (no son legibles). Sirven para ver qué decide ZascArr
por la extensión (que es lo que hace), no para probar la lectura real de un RAR (NOT RUN: ver la ficha).

Uso:  PYTHONPATH=src python3 scripts/medicion/banco_formatos_comportamiento.py      (necesita Pillow y `7z`; sin `7z` se saltan los casos 7z)
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from zascarr.core.importer_triage import triage
from zascarr.services.importer import COMIC_EXTS
from zascarr.services.library_audit import AuditReport, LibraryAudit
from zascarr.utils.cover import extract_cover_thumbnail
from zascarr.utils.fs import listar_comics

COMICINFO = b'<?xml version="1.0"?><ComicInfo><Series>Prueba</Series><Number>1</Number></ComicInfo>'


def _jpeg(i: int) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (400, 600), (i * 20 % 255, 80, 160)).save(b, "JPEG")
    return b.getvalue()


PAGINAS = [(f"p{i:03d}.jpg", _jpeg(i)) for i in range(8)]


def hay_7z() -> bool:
    return shutil.which("7z") is not None


def crear_zip(ruta: Path, _tmp: Path) -> None:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        z.writestr("ComicInfo.xml", COMICINFO)
        for n, d in PAGINAS:
            z.writestr(n, d)


def crear_tar(ruta: Path, _tmp: Path) -> None:
    with tarfile.open(ruta, "w") as t:
        for n, d in PAGINAS:
            ti = tarfile.TarInfo(n)
            ti.size = len(d)
            t.addfile(ti, io.BytesIO(d))


def crear_7z(ruta: Path, tmp: Path) -> None:
    origen = tmp / "origen7z"
    origen.mkdir(exist_ok=True)
    for n, d in PAGINAS:
        (origen / n).write_bytes(d)
    paquete = tmp / "paquete.7z"          # `7z a` añade «.7z» si falta: se crea aparte y se renombra
    paquete.unlink(missing_ok=True)
    subprocess.run(["7z", "a", "-bso0", "-bsp0", str(paquete), str(origen / "*")], check=True)
    shutil.move(str(paquete), str(ruta))


def crear_rar_firma(ruta: Path, _tmp: Path) -> None:
    ruta.write_bytes(b"Rar!\x1a\x07\x01\x00" + os.urandom(2048))      # solo la firma RAR5: NO es un RAR legible


CASOS = [  # (nombre, creador, qué es de verdad, ¿necesita 7z?)
    ("a.cbz", crear_zip, "ZIP con ComicInfo", False),
    ("b.zip", crear_zip, "ZIP", False),
    ("c_sin_ext", crear_zip, "ZIP sin extensión", False),
    ("d.cbz.rar", crear_zip, "ZIP con doble extensión .cbz.rar", False),
    ("e.7z", crear_7z, "7z real", True),
    ("f_7z_sin_ext", crear_7z, "7z sin extensión", True),
    ("g.tar", crear_tar, "TAR real", False),
    ("h_tar_sin_ext", crear_tar, "TAR sin extensión", False),
    ("i.cbt", crear_tar, "TAR llamado .cbt", False),
    ("j.rar", crear_rar_firma, "firma RAR sintética (no legible)", False),
    ("k.cbr", crear_rar_firma, "firma RAR sintética como .cbr (no legible)", False),
]


@dataclass
class Fila:
    nombre: str
    que_es: str
    lo_lista_el_importador: bool
    tiene_hash: bool
    lee_comicinfo: bool
    da_portada: bool
    auditoria: str            # motivo de «no reconocido» o «—»
    avisos_triaje: list[str]
    file_format: str


def medir(raiz: Path | None = None) -> list[Fila]:
    """Fabrica la mini-biblioteca en `raiz` (o en un directorio temporal que se borra) y devuelve una fila por caso."""
    propia = raiz is None
    raiz = raiz or Path(tempfile.mkdtemp(prefix="zas305-"))
    try:
        lib = raiz / "biblioteca"
        lib.mkdir(parents=True, exist_ok=True)
        casos = [c for c in CASOS if not c[3] or hay_7z()]
        for nombre, crear, _, _ in casos:
            crear(lib / nombre, raiz)
        vistos = {p.name for p in listar_comics([lib], COMIC_EXTS)}
        auditoria = LibraryAudit.__new__(LibraryAudit)       # solo se usa su detector, sin base de datos
        auditoria._library = lib
        informe = AuditReport(started_at=datetime.now(UTC))
        auditoria._detectar_no_reconocidos(informe)
        motivos = {Path(n.ruta).name: n.motivo for n in informe.no_reconocidos}
        filas = []
        for nombre, _, que_es, _ in casos:
            ruta = lib / nombre
            r = triage(ruta)
            filas.append(Fila(nombre, que_es, nombre in vistos, bool(r.sha256), bool(r.comic_info),
                              extract_cover_thumbnail(ruta) is not None, motivos.get(nombre, "—"), list(r.warnings), r.file_format or ""))
        return filas
    finally:
        if propia:
            shutil.rmtree(raiz, ignore_errors=True)


def main() -> int:
    filas = medir()
    print(f"COMIC_EXTS (lo que el importador recorre) = {sorted(COMIC_EXTS)}\n")
    print(f"{'fichero':<16}{'qué es de verdad':<46}{'lo lista':<9}{'hash':<6}{'ComicInfo':<10}{'portada':<8}auditoría")
    for f in filas:
        print(f"{f.nombre:<16}{f.que_es:<46}{('sí' if f.lo_lista_el_importador else 'NO'):<9}{('sí' if f.tiene_hash else 'no'):<6}"
              f"{('sí' if f.lee_comicinfo else 'no'):<10}{('sí' if f.da_portada else 'no'):<8}{f.auditoria}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
