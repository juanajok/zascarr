# ruff: noqa: E501
"""Coste de abrir contenedores (spike #305): tiempo y memoria máxima con datos SINTÉTICOS (páginas de bytes aleatorios de 1 MB).

Fabrica en un directorio temporal un volumen de N páginas empaquetado como ZIP, TAR y 7z (sólido y no sólido) y mide, con `/usr/bin/time`,
el tiempo y el pico de memoria de: listar las entradas, sacar la primera página (la portada), sacar la última y calcular el SHA-256.
Los números dependen de la máquina: la ficha del spike da los de un PC y deja la Pi como NOT RUN. Para la Pi usa pocas páginas
(`PAGINAS=100`): 100 páginas son ~100 MB por empaquetado y ~500 MB temporales en total. No lee ni escribe fuera del directorio temporal.

Uso:  PAGINAS=400 python3 scripts/medicion/banco_formatos_coste.py        (necesita `7z` y `/usr/bin/time`)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

N = int(os.environ.get("PAGINAS", "100"))
TAM_PAGINA = 1_000_000


def medir(cmd: list[str]) -> tuple[float, float]:
    """(segundos, MiB de pico de memoria) de ejecutar `cmd`."""
    p = subprocess.run(["/usr/bin/time", "-f", "%e %M"] + cmd, capture_output=True)
    seg, kb = p.stderr.decode(errors="replace").strip().splitlines()[-1].split()
    return float(seg), int(kb) / 1024


def main() -> int:
    if shutil.which("7z") is None or not Path("/usr/bin/time").exists():
        print("Hacen falta `7z` y /usr/bin/time", file=sys.stderr)
        return 2
    raiz = Path(tempfile.mkdtemp(prefix="zas305b-"))
    try:
        origen = raiz / "origen"
        origen.mkdir()
        for i in range(N):
            (origen / f"p{i:03d}.jpg").write_bytes(os.urandom(TAM_PAGINA))
        with zipfile.ZipFile(raiz / "m.zip", "w", zipfile.ZIP_STORED) as z:
            for f in sorted(origen.iterdir()):
                z.write(f, f.name)
        with tarfile.open(raiz / "m.tar", "w") as t:
            for f in sorted(origen.iterdir()):
                t.add(f, f.name)
        subprocess.run(["7z", "a", "-bso0", "-bsp0", "-ms=off", str(raiz / "m_nosolido.7z"), str(origen / "*")], check=True)
        subprocess.run(["7z", "a", "-bso0", "-bsp0", "-ms=on", str(raiz / "m_solido.7z"), str(origen / "*")], check=True)
        py = sys.executable
        primera, ultima = "p000.jpg", f"p{N - 1:03d}.jpg"
        z, t = raiz / "m.zip", raiz / "m.tar"
        pruebas = {
            "Listar las entradas": [
                ("zip (zipfile)", [py, "-c", f"import zipfile;zipfile.ZipFile('{z}').namelist()"]),
                ("tar (tarfile)", [py, "-c", f"import tarfile;tarfile.open('{t}').getnames()"]),
                ("7z no sólido", ["7z", "l", "-ba", str(raiz / "m_nosolido.7z")]),
                ("7z sólido", ["7z", "l", "-ba", str(raiz / "m_solido.7z")])],
            f"Sacar la PRIMERA página ({primera}) a memoria": [
                ("zip", [py, "-c", f"import zipfile;zipfile.ZipFile('{z}').read('{primera}')"]),
                ("tar", [py, "-c", f"import tarfile;tarfile.open('{t}').extractfile('{primera}').read()"]),
                ("7z no sólido", ["7z", "e", "-so", str(raiz / "m_nosolido.7z"), primera]),
                ("7z sólido", ["7z", "e", "-so", str(raiz / "m_solido.7z"), primera])],
            f"Sacar la ÚLTIMA página ({ultima}) a memoria": [
                ("zip", [py, "-c", f"import zipfile;zipfile.ZipFile('{z}').read('{ultima}')"]),
                ("tar", [py, "-c", f"import tarfile;tarfile.open('{t}').extractfile('{ultima}').read()"]),
                ("7z no sólido", ["7z", "e", "-so", str(raiz / "m_nosolido.7z"), ultima]),
                ("7z sólido", ["7z", "e", "-so", str(raiz / "m_solido.7z"), ultima])],
            "SHA-256 en streaming (lo que ya hace el importador)": [("sha256sum del zip", ["sha256sum", str(z)])],
        }
        print(f"{N} páginas de {TAM_PAGINA // 1000} kB: " + ", ".join(f"{p.name} {p.stat().st_size / 1e6:.0f} MB" for p in sorted(raiz.glob('m*'))))
        for titulo, casos in pruebas.items():
            print(f"\n{titulo}:")
            for nombre, cmd in casos:
                seg, mib = medir(cmd)
                print(f"  {nombre:<22}{seg:>7.2f} s  {mib:>8.1f} MiB de pico")
        return 0
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
