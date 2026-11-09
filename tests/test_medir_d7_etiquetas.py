"""Medición D-7 (#402): la parte de ficheros del script es de solo lectura y cuenta bien.

Se ejecuta el script real con una biblioteca sintética y `--solo-ficheros` (sin BD): los CBZ
se abren en modo lectura y se aplican los mismos topes de `<Tags>`/`<Genre>` que ETQ2.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "medicion" / "medir_d7_etiquetas.py"


def _cbz(ruta: Path, comicinfo: str | None = None) -> None:
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("001.jpg", b"img")
        if comicinfo is not None:
            z.writestr("ComicInfo.xml", comicinfo)


def _correr(lib: Path, *args: str) -> subprocess.CompletedProcess:
    entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"))
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--solo-ficheros", "--biblioteca", str(lib), *args],
        capture_output=True, text=True, env=entorno, cwd=RAIZ, timeout=120,
    )


def _biblioteca_sintetica(lib: Path) -> None:
    lib.mkdir()
    _cbz(lib / "a.cbz", '<ComicInfo><Tags>dark, Occult</Tags><Genre>Horror</Genre></ComicInfo>')
    _cbz(lib / "b.cbz", "<ComicInfo><Tags>superman</Tags></ComicInfo>")
    _cbz(lib / "c.cbz")
    _cbz(lib / "f.cbz", "<ComicInfo><Title>Sin listas</Title></ComicInfo>")
    _cbz(lib / "g.cbz", "<ComicInfo><Tags>roto")
    (lib / "d.cbz").write_bytes(b"no es un zip")
    (lib / "e.cbr").write_bytes(b"Rar!\x1a\x07\x00")


class TestMedicionD7:

    def test_cuenta_cbz_y_lee_tags_y_genero(self, tmp_path):
        lib = tmp_path / "lib"
        _biblioteca_sintetica(lib)
        r = _correr(lib, "--json")
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout)
        assert d["cbz"] == 6 and d["cbr"] == 1
        assert d["comicinfo"]["presente"] == 3
        assert d["comicinfo"]["con_tags"] == 2
        assert d["comicinfo"]["con_genero"] == 1
        assert d["comicinfo"]["con_ambos"] == 1
        assert d["comicinfo"]["valores_tags"] == 3
        assert d["errores"]["sin_comicinfo"] == 1
        assert d["errores"]["xml_roto"] == 1
        assert d["errores"]["no_zip"] == 1

    def test_no_modifica_la_biblioteca(self, tmp_path):
        lib = tmp_path / "lib"
        _biblioteca_sintetica(lib)
        antes = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in lib.rglob("*")}
        _correr(lib)
        despues = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in lib.rglob("*")}
        assert antes == despues
        assert not (tmp_path / "no_existe").exists()
