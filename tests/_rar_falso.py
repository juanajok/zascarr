# ruff: noqa: E501
"""Un `lsar` y un `unar` FALSOS para probar el lector de RAR sin RAR ni la herramienta real (#418).

Son scripts de `sh` en una carpeta que se pone la primera en el `PATH`. Cada uno lee su «modo» de un
fichero de esa misma carpeta, y deja un rastro (`llamadas.log`, `entornos.log`) para comprobar qué se
lanzó y con qué entorno. Simulan las trampas que midió la evaluación de #308: código 0 sin salida,
listado truncado, tamaño o CRC distintos, cuelgue, salida enorme, enlace simbólico, dos ficheros.
"""
from __future__ import annotations

import json
import stat
import zlib
from dataclasses import dataclass
from pathlib import Path

_LSAR = """#!/bin/sh
d=$(dirname "$0")
echo "lsar $*" >> "$d/llamadas.log"
echo "HOME=$HOME" >> "$d/entornos.log"
echo "PATH=$PATH" >> "$d/entornos.log"
flag=0
for a in "$@"; do [ "$a" = "-json-skip-solid-information" ] && flag=1; done
case "$(cat "$d/modo_lsar")" in
  ok) cat "$d/listado.json" ;;
  # #528: sólido sintético. Con el flag, el listado compacto; sin él, el que repetiría el objeto
  # interno del sólido en cada entrada (el que supera el tope de 4 MiB).
  solido) if [ "$flag" = "1" ]; then cat "$d/listado_solido.json"; else cat "$d/listado_solido_sin_flag.json"; fi ;;
  # Un lsar 1.10.1 (bookworm): el flag no existe y lo dice por stdout, como la herramienta real.
  sin_flag)
    if [ "$flag" = "1" ]; then echo "Unknown option -json-skip-solid-information."; exit 1; fi
    cat "$d/listado.json" ;;
  rc1) echo "$(cat "$d/mensaje")" >&2; exit 1 ;;
  cuelga) sleep 60 & echo $! > "$d/hijo.pid"; wait ;;
  enorme) head -c 6000000 /dev/zero | tr '\\0' 'a' ;;
  basura) echo "esto no es json" ;;
esac
"""

_UNAR = """#!/bin/sh
d=$(dirname "$0")
echo "unar $*" >> "$d/llamadas.log"
echo "HOME=$HOME" >> "$d/entornos.log"
echo "PATH=$PATH" >> "$d/entornos.log"
for a; do ultimo=$a; done
while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift ;; esac; shift; done
case "$(cat "$d/modo_unar")" in
  ok) cp "$d/contenido.bin" "$out/p.jpg" ;;
  nada) exit 0 ;;
  otro_tamano) head -c 7 /dev/zero > "$out/p.jpg" ;;
  crc) cp "$d/contenido.bin" "$out/p.jpg"; printf 'X' | dd of="$out/p.jpg" bs=1 count=1 conv=notrunc 2>/dev/null ;;
  enlace) ln -s /etc/passwd "$out/p.jpg" ;;
  dos) cp "$d/contenido.bin" "$out/a.jpg"; cp "$d/contenido.bin" "$out/b.jpg" ;;
  rc1) echo "$(cat "$d/mensaje")" >&2; exit 1 ;;
  cuelga) sleep 60 & echo $! > "$d/hijo.pid"; wait ;;
  enorme) head -c 3000000 /dev/zero > "$out/p.jpg"; sleep 30 ;;
  memoria) sleep 60 & echo $! > "$d/hijo.pid"; python3 -c 'x = b"x" * (150 * 1024 * 1024); import time; time.sleep(30)' ;;
  lento) sleep 0.4; cp "$d/contenido.bin" "$out/p.jpg" ;;
  exclusivo)
    mkdir "$d/candado" 2>/dev/null || echo violacion >> "$d/violaciones.log"
    sleep 0.5; rmdir "$d/candado"; cp "$d/contenido.bin" "$out/p.jpg" ;;
esac
"""


@dataclass
class RarFalso:
    carpeta: Path

    def modo(self, lsar: str | None = None, unar: str | None = None, mensaje: str = "") -> None:
        if lsar is not None:
            (self.carpeta / "modo_lsar").write_text(lsar)
        if unar is not None:
            (self.carpeta / "modo_unar").write_text(unar)
        (self.carpeta / "mensaje").write_text(mensaje)

    def listado(self, entradas: list[dict]) -> None:
        (self.carpeta / "listado.json").write_text(json.dumps({"lsarContents": entradas}))

    def solido(self, n: int = 220, relleno: int = 29_000) -> list[dict]:
        """Sólido sintético de `n` entradas (#528).

        Deja dos listados: el compacto que devuelve `lsar -j -json-skip-solid-information` y el que
        devolvería sin el flag, con el objeto interno del sólido (~29 KB) repetido en cada entrada.
        Con 220 entradas el segundo supera de sobra `RAR_MAX_SALIDA_LISTADO` (4 MiB), que es el bug.
        """
        compacto = [entrada(i, f"{i:03d}.jpg", 100) for i in range(n)]
        (self.carpeta / "listado_solido.json").write_text(json.dumps({"lsarContents": compacto}))
        grande = [{**e, "XADSolidObject": "S" * relleno} for e in compacto]
        (self.carpeta / "listado_solido_sin_flag.json").write_text(json.dumps({"lsarContents": grande}))
        return compacto

    def contenido(self, datos: bytes) -> int:
        (self.carpeta / "contenido.bin").write_bytes(datos)
        return zlib.crc32(datos)

    def llamadas(self) -> list[str]:
        f = self.carpeta / "llamadas.log"
        return f.read_text().splitlines() if f.exists() else []

    def entornos(self) -> list[str]:
        f = self.carpeta / "entornos.log"
        return f.read_text().splitlines() if f.exists() else []

    def violaciones(self) -> list[str]:
        f = self.carpeta / "violaciones.log"
        return f.read_text().splitlines() if f.exists() else []

    def hijo_vivo(self) -> bool:
        """¿Sigue vivo el nieto que el falso dejó dormido? (prueba de que se mató el GRUPO)."""
        import os
        f = self.carpeta / "hijo.pid"
        if not f.exists():
            return False
        try:
            os.kill(int(f.read_text().strip()), 0)
        except ProcessLookupError:
            return False
        return True


def entrada(indice: int, nombre: str, tamano: int, crc32: int | None = None, *,
            directorio: bool = False, cifrada: bool = False) -> dict:
    d: dict = {"XADIndex": indice, "XADFileName": nombre, "XADFileSize": tamano,
               "XADIsDirectory": int(directorio), "XADIsEncrypted": int(cifrada)}
    if crc32 is not None:
        d["XADCRC32"] = crc32
    return d


def instalar(carpeta: Path, monkeypatch) -> RarFalso:
    """Crea `lsar` y `unar` falsos en `carpeta` y los pone los primeros en el PATH."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, cuerpo in (("lsar", _LSAR), ("unar", _UNAR)):
        f = carpeta / nombre
        f.write_text(cuerpo)
        f.chmod(f.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{carpeta}:/usr/bin:/bin")
    falso = RarFalso(carpeta)
    falso.modo(lsar="ok", unar="ok")
    falso.listado([])
    falso.contenido(b"")
    return falso
