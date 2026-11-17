"""Corte C (#156): la cuarentena de apartados se resuelve en la raíz de origen."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from zascarr.services.apartado_duplicados import ApartadoDuplicadosService


def _servicio(tmp_path: Path, a: Path, b: Path) -> ApartadoDuplicadosService:
    ajustes = SimpleNamespace(
        library_path=str(a), library_roots=f"{a},{b}", host_library_roots="",
        downloads_path=str(tmp_path / "dl"), amule_incoming_dir=str(tmp_path / "in"),
        export_path=str(tmp_path / "export"), carpetas_compartidas=[],
        secret_key="s" * 32)
    return ApartadoDuplicadosService(db=SimpleNamespace(), settings=ajustes)


def test_cada_copia_resuelve_su_raiz_y_su_cuarentena(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    svc = _servicio(tmp_path, a, b)
    origen = b / "Manga" / "Serie" / "x.cbz"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"x")

    assert svc._raiz_de(origen) == b
    assert svc._relativa(origen) == (origen, "Manga/Serie/x.cbz")
    base = svc._base_cuarentena(__import__("uuid").uuid4(), b)
    assert base.is_relative_to(b / ".zascarr" / "apartados")


def test_cuarentena_y_diario_de_conversion_usan_la_raiz_del_archivo(tmp_path):
    from zascarr.services.conversion import _cuarentena, _diario

    a, b = tmp_path / "A", tmp_path / "B"
    a.mkdir()
    b.mkdir()
    ajustes = SimpleNamespace(
        library_path=str(a), library_roots=f"{a},{b}", host_library_roots="",
        downloads_path=str(tmp_path / "dl"), amule_incoming_dir=str(tmp_path / "in"),
        export_path=str(tmp_path / "export"), carpetas_compartidas=[],
        secret_key="s" * 32)
    archivo = b / "Serie" / "x.cbz"
    assert _cuarentena(ajustes, archivo) == b / ".zascarr" / "originales"
    assert _diario(ajustes, archivo) == b / ".zascarr" / "diario"
    assert _cuarentena(ajustes) == a / ".zascarr" / "originales"
