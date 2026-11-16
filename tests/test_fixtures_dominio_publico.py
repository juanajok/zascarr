"""Los fixtures de dominio público son válidos y se pueden usar en pruebas/demos (#344)."""
from __future__ import annotations

import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures" / "dominio-publico"
CBZS = sorted(FIXTURES.glob("*.cbz"))


def test_hay_tres_fixtures_cbz():
    assert [p.name for p in CBZS] == [
        "little-nemo-1905.cbz",
        "rarebit-fiend-1904.cbz",
        "yellow-kid-1895-1896.cbz",
    ]


def test_cada_cbz_tiene_dos_paginas_y_comicinfo():
    for ruta in CBZS:
        with zipfile.ZipFile(ruta) as z:
            nombres = z.namelist()
            assert nombres.count("ComicInfo.xml") == 1
            imagenes = [n for n in nombres if n.lower().endswith((".jpg", ".jpeg", ".png"))]
            assert len(imagenes) == 2, (ruta.name, imagenes)
            assert z.read("ComicInfo.xml").startswith(b"<?xml")


def test_el_pack_se_puede_construir_en_un_temporal(tmp_path):
    destino = tmp_path / "pack-dominio-publico.zip"
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_STORED) as z:
        for ruta in CBZS:
            z.write(ruta, ruta.name)
    with zipfile.ZipFile(destino) as z:
        assert sorted(z.namelist()) == [p.name for p in CBZS]
