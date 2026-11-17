"""Los especiales sin número van a …/Serie (Año)/Especiales/ (PO 2026-11-16)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from zascarr.models import ComicTradition, Series
from zascarr.services.importer import build_library_path


def _serie() -> Series:
    return Series(id=uuid4(), title="Sector Lejano",
                  tradition=ComicTradition.AMERICAN, start_year=None)


def test_un_especial_sin_numero_va_a_su_carpeta_dentro_de_la_serie():
    destino = build_library_path(
        Path("/lib"), _serie(), None, ".cbz",
        fallback_name="Sector Lejano (Aniversario).cbz", especial=True)
    assert destino.parent.name == "Especiales"
    assert destino.name == "Sector Lejano (Aniversario).cbz"


def test_un_issue_normal_no_se_mete_en_especiales():
    destino = build_library_path(
        Path("/lib"), _serie(), "1", ".cbz", fallback_name="x.cbz")
    assert "Especiales" not in destino.parts
