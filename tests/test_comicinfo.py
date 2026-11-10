# ruff: noqa: E501
"""#448 BL-INF2: lectura de ComicInfo de CBZ sintéticos (sin red)."""
from __future__ import annotations

import zipfile
from pathlib import Path

from zascarr.services.comicinfo import _leer_comicinfo


def _cbz(path: Path, xml: str | None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        if xml is not None:
            zf.writestr("ComicInfo.xml", xml)
    return path


XML = """<?xml version="1.0"?><ComicInfo>
<Writer>Ana</Writer><Penciller>Bea</Penciller><Editor>Eva</Editor>
<Summary>Una historia</Summary><PageCount>32</PageCount><Publisher>Norma</Publisher>
</ComicInfo>"""


def test_lee_comicinfo_de_cbz(tmp_path):
    info, estado, avisos, _, _ = _leer_comicinfo(_cbz(tmp_path / "a.cbz", XML))
    assert estado == "ok" and info is not None
    assert info.credits["writer"] == ["Ana"] and info.credits["editor"] == ["Eva"]
    assert info.summary == "Una historia" and info.page_count == 32


def test_sin_comicinfo_no_es_error(tmp_path):
    info, estado, _, _, _ = _leer_comicinfo(_cbz(tmp_path / "b.cbz", None))
    assert info is None and estado == "sin_comicinfo"


def test_xml_roto_no_lanza(tmp_path):
    info, estado, avisos, _, _ = _leer_comicinfo(_cbz(tmp_path / "c.cbz", "<ComicInfo>"))
    assert info is None and estado == "ilegible" and avisos


def test_cbr_se_cuenta_como_ilegible(tmp_path):
    ruta = tmp_path / "d.cbr"
    ruta.write_bytes(b"Rar!")
    info, estado, avisos, _, _ = _leer_comicinfo(ruta)
    assert info is None and estado == "ilegible" and "CBR" in avisos[0]


def test_xml_enorme_no_se_parsea(tmp_path):
    xml = "<ComicInfo><Summary>" + ("x" * (1024 * 1024 + 10)) + "</Summary></ComicInfo>"
    info, estado, avisos, _, _ = _leer_comicinfo(_cbz(tmp_path / "e.cbz", xml))
    assert info is None and estado == "ilegible" and avisos
