# ruff: noqa: E501
"""B14 — `scripts/medicion/medir_carpetas.py`: la medición que sustenta `docs/design/auditoria-b14-carpetas.md`.

El corpus es SINTÉTICO pero con las formas reales de la biblioteca medida (autor, contenedor, refinamiento por
volumen, orden de lectura): los nombres de series son títulos publicados; ninguna ruta es de nadie.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("medir_carpetas", RAIZ / "scripts" / "medicion" / "medir_carpetas.py")
medir_carpetas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(medir_carpetas)


class TestLimpiarCarpeta:

    @pytest.mark.parametrize("carpeta,titulo,anio", [
        ("Flash (1987)", "Flash", 1987),
        ("JSA (1999)", "JSA", 1999),
        ("Arrowsmith (COMPLETO)(CRG)", "Arrowsmith", None),
        ("Superman Vol2 (Ed.Zinco)(1987-96)", "Superman Vol2", 1987),
        ("Locke & Key [HD]", "Locke & Key", None),
        ("Green Lantern - Saga de Geoff Johns", "Green Lantern - Saga de Geoff Johns", None),
    ])
    def test_titulo_y_anio(self, carpeta, titulo, anio):
        t, a, _ = medir_carpetas.limpiar_carpeta(carpeta)
        assert (t, a) == (titulo, anio)

    def test_las_etiquetas_se_separan_no_se_pierden(self):
        _, _, etiquetas = medir_carpetas.limpiar_carpeta("Arrowsmith (COMPLETO)(CRG)")
        assert etiquetas == ["(COMPLETO)", "(CRG)"]


class TestRelacion:

    @pytest.mark.parametrize("archivo,carpeta,esperada", [
        ("Flash", "Flash", "igual"),
        ("La Patrulla X", "Patrulla X", "igual"),            # el artículo no cuenta
        ("Superman", "Superman Vol2", "nombre_dentro_de_la_carpeta"),
        ("La Mazmorra Integral", "La Mazmorra", "carpeta_dentro_del_nombre"),
        ("Hiroaki Samura", "La Espada del Inmortal", "distinto"),
        ("", "Flash", "sin_titulo_en_el_nombre"),
    ])
    def test_casos(self, archivo, carpeta, esperada):
        assert medir_carpetas.relacion(archivo, carpeta) == esperada


class TestMedir:

    @staticmethod
    def _arbol(raiz: Path) -> None:
        for ruta in [
            "Comics/Flash (1987)/Flash 001.cbz",                       # igual
            "Comics/Flash (1987)/Impulse 005.cbz",                     # la carpeta MIENTE: otra serie dentro
            "Comics/Autor Famoso/Obra Uno 01.cbz",                     # carpeta de autor
            "Comics/Autor Famoso/Obra Dos 01.cbz",
            "Comics/Superman Vol2 (Ed.Zinco)(1987-96)/Superman 010.cbz",   # la carpeta refina
            "Comics/suelto 001.cbz",                                   # sin carpeta de serie
        ]:
            p = raiz / ruta
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")

    def test_clasifica_cada_forma(self, tmp_path):
        self._arbol(tmp_path)
        filas = {Path(f["ruta"]).name: f for f in medir_carpetas.medir(tmp_path)}
        assert filas["Flash 001.cbz"]["relacion"] == "igual"
        assert filas["Impulse 005.cbz"]["relacion"] == "distinto"           # evidencia de carpeta que no es su serie
        assert filas["Obra Uno 01.cbz"]["relacion"] == "distinto"
        assert filas["Superman 010.cbz"]["relacion"] == "nombre_dentro_de_la_carpeta"
        assert filas["suelto 001.cbz"]["relacion"] == "sin_carpeta_de_serie"

    def test_no_toca_la_biblioteca(self, tmp_path):
        self._arbol(tmp_path)
        antes = sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns) for p in tmp_path.rglob("*"))
        medir_carpetas.medir(tmp_path)
        assert sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns) for p in tmp_path.rglob("*")) == antes
