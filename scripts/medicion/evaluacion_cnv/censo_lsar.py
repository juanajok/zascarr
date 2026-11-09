#!/usr/bin/env python3
"""Censo de CBR registrados con `lsar` (BL-CNV0). Solo lee; no escribe en la biblioteca.

Se ejecuta DENTRO de un contenedor desechable con la biblioteca montada en solo lectura.
Lee `/list.txt` (rutas relativas a la biblioteca) y escribe una línea TSV por fichero por
stdout. La ruta solo vive en esta salida interna; el informe publica recuentos.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import subprocess
from pathlib import Path

LIST = Path("/list.txt")
ROOT = Path("/media/library")
TIMEOUT = 20
VOLUMEN = re.compile(r"(?:\.part\d+\.rar|\.r\d{2,3}|\.part\d+\.rar|\.\d{3})$", re.I)
NESTED = re.compile(r"\.(?:rar|cbr|cbz|zip|7z)$", re.I)


def clasificar_error(stderr: str) -> str:
    s = stderr.lower()
    if "password" in s or "encrypted" in s:
        return "cifrado"
    if "volume" in s or "part" in s:
        return "multivolumen"
    if "corrupt" in s or "crc" in s or "damaged" in s or "truncated" in s:
        return "dañado"
    if "not a rar" in s or "unknown" in s or "unsupported" in s:
        return "formato"
    return "error"


def uno(rel: str) -> dict:
    p = ROOT / rel
    d = {"rel": rel, "lsar": "ok", "entradas": 0, "anidado": 0, "volumen": 0,
         "motivo_error": "", "formato_lsar": ""}
    if VOLUMEN.search(rel):
        d["volumen"] = 1
    try:
        r = subprocess.run(
            ["lsar", "-j", "-nr", str(p)],
            capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        d["lsar"] = "timeout"
        return d
    if r.returncode != 0:
        d["lsar"] = "error"
        d["motivo_error"] = clasificar_error(r.stderr)
        return d
    try:
        doc = json.loads(r.stdout)
    except json.JSONDecodeError:
        d["lsar"] = "error"
        d["motivo_error"] = "json"
        return d
    contenido = doc.get("lsarContents")
    if not isinstance(contenido, list):
        d["lsar"] = "error"
        d["motivo_error"] = "sin_lista"
        return d
    d["entradas"] = len(contenido)
    # `lsar` sin -r no debe entrar; si aparece un archivo comprimido como entrada, es anidado.
    d["anidado"] = sum(1 for e in contenido
                       if isinstance(e, dict) and NESTED.search(str(e.get("XADFileName", ""))))
    return d


def main() -> int:
    rutas = [line.strip() for line in LIST.read_text(encoding="utf-8").splitlines() if line.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        filas = list(ex.map(uno, rutas))
    for d in filas:
        print("\t".join(str(d[k]) for k in (
            "rel", "lsar", "entradas", "anidado", "volumen", "motivo_error")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
