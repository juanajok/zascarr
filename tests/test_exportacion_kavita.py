"""B20: planificación pura de la exportación a Kavita."""
from __future__ import annotations

from pathlib import Path

from zascarr.core.exportacion_kavita import (
    ArchivoFuente,
    nombre_de_archivo,
    plan_export,
)


def fuente(**cambios):
    base = dict(file_id="f1", issue_id="i1", series_id="s1", series_title="Flash",
                numero="1", issue_title="El origen", source_path="/lib/Flash 1.cbz",
                size_bytes=100, sha256="a" * 64)
    base.update(cambios)
    return ArchivoFuente(**base)


def test_nombre_numerado_y_sin_numero():
    assert nombre_de_archivo("Flash", "1", "El origen", "/x.cbz") == "Flash 001 - El origen.cbz"
    assert nombre_de_archivo("Flash", None, "Especial", "/x.CBR") == "Flash - Especial.cbr"
    assert nombre_de_archivo("Flash", "1.5", "Especial", "/x.cbz") == "Flash 1.5 - Especial.cbz"


def test_plan_una_fila_por_issue_y_omite_desaparecidos():
    plan = plan_export([
        fuente(file_id="f1", issue_id="i1"),
        fuente(file_id="f2", issue_id="i2", numero="2", source_path="/lib/Flash 2.cbz"),
        fuente(file_id="f3", issue_id="i3", is_missing=True),
    ], Path("/export"), folder="Grapas")
    assert plan.folder == "Grapas"
    assert [Path(a.destino_relativo).name for a in plan.archivos] == [
        "Flash 001 - El origen.cbz", "Flash 002 - El origen.cbz"]
    assert plan.omitidos == ["i3"]


def test_plan_detecta_colision_sin_pisar():
    plan = plan_export([
        fuente(file_id="f1", issue_id="i1", numero="1"),
        fuente(file_id="f2", issue_id="i2", numero="01"),
    ], Path("/export"), folder="Grapas")
    assert len(plan.archivos) == 1
    assert plan.colisiones and "Flash 001 - El origen.cbz" in plan.colisiones[0]


def test_plan_no_permite_escapar_de_la_raiz():
    plan = plan_export([fuente(series_title="../../fuera")], Path("/export"), folder="Grapas")
    assert plan.archivos[0].destino_relativo.startswith("Grapas/")
    assert ".." not in plan.archivos[0].destino_relativo.split("/")


def test_raiz_no_puede_estar_dentro_de_biblioteca_ni_ser_symlink(tmp_path):
    import pytest

    from zascarr.services.exportacion_kavita import ExportacionError, _resolver_raiz

    ajustes = lambda root: __import__("types").SimpleNamespace(  # noqa: E731
        export_path=root, library_path=tmp_path / "lib", downloads_path=tmp_path / "dl",
        amule_incoming_dir=tmp_path / "in", carpetas_compartidas=[])
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "export").mkdir()
    with pytest.raises(ExportacionError):
        _resolver_raiz(ajustes(tmp_path / "lib" / "export"))
    enlace = tmp_path / "enlace"
    enlace.symlink_to(tmp_path / "destino", target_is_directory=True)
    with pytest.raises(ExportacionError):
        _resolver_raiz(ajustes(enlace))
    with pytest.raises(ExportacionError):
        _resolver_raiz(ajustes(tmp_path / ".." / "export"))
    with pytest.raises(ExportacionError):
        _resolver_raiz(ajustes(tmp_path))       # padre de la biblioteca


def test_carpetas_de_serie_colisionadas_se_desambiguan():
    plan = plan_export([
        fuente(file_id="f1", issue_id="i1", series_id="s1", series_title="Flash"),
        fuente(file_id="f2", issue_id="i2", series_id="s2", series_title="Flash",
                numero="2", source_path="/lib/2.cbz"),
    ], Path("/export"), folder="Grapas")
    carpetas = {Path(a.destino_relativo).parts[1] for a in plan.archivos}
    assert len(carpetas) == 2
    assert plan.carpetas_colision
