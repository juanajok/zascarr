"""BL-B9 (#158): composición pura de nombres de archivo de la biblioteca."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from zascarr.models import ComicTradition, IssueFormat, Series
from zascarr.services.importer import build_library_path
from zascarr.utils.nombres_biblioteca import PRESETS, construir_nombre


def _serie(titulo="Batman", tradicion=ComicTradition.AMERICAN) -> Series:
    return Series(title=titulo, tradition=tradicion, start_year=2011)


def _settings(**kw):
    base = dict(
        naming_enabled=False, naming_preset="clasico", naming_padding=0,
        covers_cache_path=Path("/tmp/covers"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_presets_basicos_y_padding():
    serie = _serie()
    assert construir_nombre(serie, "3", preset="clasico") == "Batman #003"
    assert construir_nombre(serie, "3", preset="compacto") == "Batman #03"
    assert construir_nombre(serie, "3", preset="clasico", padding=2) == "Batman #03"
    assert construir_nombre(serie, "3", preset="compacto", padding=4) == "Batman #0003"
    assert set(PRESETS) == {"clasico", "compacto", "tradicion", "titulo"}


def test_preset_tradicion():
    assert construir_nombre(_serie(tradicion=ComicTradition.MANGA), "1",
                            preset="tradicion") == "Batman v01"
    assert construir_nombre(_serie(tradicion=ComicTradition.FRANCO_BELGIAN), "1",
                            preset="tradicion") == "Batman T01"
    assert construir_nombre(_serie(tradicion=ComicTradition.TEBEO), "1",
                            preset="tradicion") == "Batman nº 01"
    for trad in (ComicTradition.AMERICAN, ComicTradition.FUMETTI,
                 ComicTradition.BRITISH, ComicTradition.MANHUA,
                 ComicTradition.MANHWA, ComicTradition.OTHER):
        assert construir_nombre(_serie(tradicion=trad), "3",
                                preset="tradicion") == "Batman #003"


def test_titulo_y_sin_titulo_nunca_inventa_unknown():
    serie = _serie()
    assert construir_nombre(serie, "3", titulo="Corte de los búhos",
                            preset="titulo") == "Batman #003 - Corte de los búhos"
    for preset in PRESETS:
        nombre = construir_nombre(serie, "3", titulo=None, preset=preset)
        assert "Unknown" not in nombre and "unknown" not in nombre
    assert construir_nombre(serie, "3", preset="titulo") == "Batman #003"
    assert construir_nombre(serie, "3", titulo="", preset="titulo") == "Batman #003"
    assert construir_nombre(serie, "3", titulo="Unknown", preset="titulo") == "Batman #003"


def test_especial_pack_y_sanitizado():
    serie = _serie()
    assert construir_nombre(serie, "3", formato=IssueFormat.OMNIBUS,
                            preset="clasico") == "Batman #003 (Ómnibus)"
    assert construir_nombre(serie, "3", pack=True,
                            preset="clasico") == "Batman #003 (Pack)"
    assert construir_nombre(_serie("A/B"), "3", preset="clasico") == "A B #003"


def test_build_library_path_respeta_enabled_y_legacy():
    serie = _serie()
    with patch("zascarr.services.importer.get_settings",
               return_value=_settings(naming_enabled=False)):
        legacy = build_library_path(Path("/lib"), serie, "3", ".cbz")
    assert legacy == Path("/lib/Comics/Batman (2011)/Batman #003.cbz")

    with patch("zascarr.services.importer.get_settings",
               return_value=_settings(naming_enabled=True, naming_preset="compacto")):
        nuevo = build_library_path(
            Path("/lib"), serie, "3", ".cbz", issue_title="Corte",
            issue_format=IssueFormat.OMNIBUS)
    assert nuevo == Path("/lib/Comics/Batman (2011)/Batman #03 (Ómnibus).cbz")

    with patch("zascarr.services.importer.get_settings",
               return_value=_settings(naming_enabled=True, naming_preset="titulo")):
        con_titulo = build_library_path(
            Path("/lib"), serie, "3", ".cbz", issue_title="Corte")
    assert con_titulo.name == "Batman #003 - Corte.cbz"
