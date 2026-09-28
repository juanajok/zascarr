"""B6 — reescritura segura del CBZ (`utils/cbz.py`).

Lo que se comprueba aquí es lo que protege la colección: el original no se
sustituye hasta que el reemplazo está **verificado**, y cualquier fallo lo deja
intacto y sin temporales sueltos.
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from zascarr.utils import cbz as zcbz
from zascarr.utils.cbz import (
    CbzInvalidoError,
    SinEspacioError,
    VerificacionError,
    leer_comicinfo,
    reescribir_con_xml,
)

PAGINAS = [f"p{i:03d}.jpg" for i in range(5)]


def _cbz(path: Path, *, xml: bytes | None = None, xml_nombre: str = "ComicInfo.xml",
         extras: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in PAGINAS:
            zf.writestr(p, f"contenido-{p}".encode())
        if xml is not None:
            zf.writestr(xml_nombre, xml)
        for nombre, datos in (extras or {}).items():
            zf.writestr(nombre, datos)
    return path


def _manifiesto(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as zf:
        return {i.filename: hashlib.sha256(zf.read(i)).hexdigest()
                for i in zf.infolist() if not i.is_dir()}


def _nombres(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return [i.filename for i in zf.infolist() if not i.is_dir()]


def _sin_temporales(directorio: Path) -> bool:
    return not [p for p in directorio.iterdir() if p.name.endswith(".zascarr.tmp")]


class TestLectura:

    def test_lee_el_xml(self, tmp_path):
        xml = b"<ComicInfo><Series>Thorgal</Series></ComicInfo>"
        assert leer_comicinfo(_cbz(tmp_path / "a.cbz", xml=xml)) == xml

    def test_sin_comicinfo_devuelve_none(self, tmp_path):
        assert leer_comicinfo(_cbz(tmp_path / "a.cbz")) is None

    @pytest.mark.parametrize("nombre", ["ComicInfo.xml", "comicinfo.xml", "COMICINFO.XML"])
    def test_nombre_es_case_insensitive(self, tmp_path, nombre):
        xml = b"<ComicInfo><Series>X</Series></ComicInfo>"
        ruta = _cbz(tmp_path / "a.cbz", xml=xml, xml_nombre=nombre)
        assert leer_comicinfo(ruta) == xml


class TestReescritura:

    def test_conserva_todas_las_paginas_byte_a_byte(self, tmp_path):
        ruta = _cbz(tmp_path / "a.cbz", xml=b"<ComicInfo><Series>Viejo</Series></ComicInfo>",
                    extras={"carpeta/nota.txt": b"hola"})
        antes = _manifiesto(ruta)

        reescribir_con_xml(ruta, b"<ComicInfo><Series>Nuevo</Series></ComicInfo>")

        despues = _manifiesto(ruta)
        for nombre in PAGINAS + ["carpeta/nota.txt"]:
            assert despues[nombre] == antes[nombre]
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Series") == "Nuevo"

    def test_dos_comicinfo_quedan_en_uno(self, tmp_path):
        ruta = _cbz(tmp_path / "a.cbz", xml=b"<ComicInfo><Series>Uno</Series></ComicInfo>")
        with zipfile.ZipFile(ruta, "a") as zf:  # segunda entrada, mismo nombre
            zf.writestr("ComicInfo.xml", b"<ComicInfo><Series>Dos</Series></ComicInfo>")
        assert _nombres(ruta).count("ComicInfo.xml") == 2

        reescribir_con_xml(ruta, b"<ComicInfo><Series>Tres</Series></ComicInfo>")

        assert _nombres(ruta).count("ComicInfo.xml") == 1
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Series") == "Tres"

    def test_comicinfo_anidado_tambien_se_normaliza(self, tmp_path):
        ruta = _cbz(tmp_path / "a.cbz", xml=b"<ComicInfo><Series>Uno</Series></ComicInfo>",
                    xml_nombre="sub/ComicInfo.xml")
        reescribir_con_xml(ruta, b"<ComicInfo><Series>Dos</Series></ComicInfo>")
        nombres = _nombres(ruta)
        assert sum(1 for n in nombres if os.path.basename(n).lower() == "comicinfo.xml") == 1
        assert "ComicInfo.xml" in nombres

    def test_crea_el_xml_si_no_existia(self, tmp_path):
        ruta = _cbz(tmp_path / "a.cbz")
        reescribir_con_xml(ruta, b"<ComicInfo><Series>Nueva</Series></ComicInfo>")
        assert ElementTree.fromstring(leer_comicinfo(ruta)).findtext("Series") == "Nueva"

    def test_no_deja_temporales(self, tmp_path):
        ruta = _cbz(tmp_path / "a.cbz")
        reescribir_con_xml(ruta, b"<ComicInfo><Series>X</Series></ComicInfo>")
        assert _sin_temporales(tmp_path)


class TestFallos:

    def test_espacio_insuficiente_aborta_sin_tocar_el_original(self, tmp_path, monkeypatch):
        ruta = _cbz(tmp_path / "a.cbz", xml=b"<ComicInfo><Series>Uno</Series></ComicInfo>")
        original = ruta.read_bytes()
        monkeypatch.setattr(
            zcbz.shutil, "disk_usage",
            lambda _: type("U", (), {"free": 1024, "total": 10**9, "used": 0})(),
        )

        with pytest.raises(SinEspacioError):
            reescribir_con_xml(ruta, b"<ComicInfo><Series>Dos</Series></ComicInfo>")

        assert ruta.read_bytes() == original
        assert _sin_temporales(tmp_path)

    def test_verificacion_fallida_original_intacto(self, tmp_path, monkeypatch):
        """Fallo a mitad de la reconstrucción (p.ej. ZIP corrupto): no se pierde."""
        ruta = _cbz(tmp_path / "a.cbz", xml=b"<ComicInfo><Series>Uno</Series></ComicInfo>")
        original = ruta.read_bytes()
        monkeypatch.setattr(zcbz, "_verificar",
                            lambda *a, **k: (_ for _ in ()).throw(
                                VerificacionError("fallo inyectado")))

        with pytest.raises(VerificacionError):
            reescribir_con_xml(ruta, b"<ComicInfo><Series>Dos</Series></ComicInfo>")

        assert ruta.read_bytes() == original
        assert _sin_temporales(tmp_path)

    def test_entrada_corrupta_no_se_toca(self, tmp_path):
        ruta = tmp_path / "a.cbz"
        ruta.write_bytes(b"esto no es un zip")
        with pytest.raises(CbzInvalidoError):
            reescribir_con_xml(ruta, b"<ComicInfo/>")
        assert ruta.read_bytes() == b"esto no es un zip"
        assert _sin_temporales(tmp_path)

    def test_fichero_inexistente_es_invalido(self, tmp_path):
        with pytest.raises(CbzInvalidoError):
            reescribir_con_xml(tmp_path / "no-existe.cbz", b"<ComicInfo/>")

    def test_manifiesto_distinto_aborta(self, tmp_path, monkeypatch):
        """Si la reconstrucción alterase una página, se aborta (no se publica)."""
        ruta = _cbz(tmp_path / "a.cbz")
        original = ruta.read_bytes()
        real = zcbz._manifiesto
        llamadas = {"n": 0}

        def _manifiesto_tramposo(zf):
            llamadas["n"] += 1
            out = real(zf)
            if llamadas["n"] > 1:  # el del CBZ reconstruido
                out["p000.jpg"] = "0" * 64
            return out

        monkeypatch.setattr(zcbz, "_manifiesto", _manifiesto_tramposo)
        with pytest.raises(VerificacionError):
            reescribir_con_xml(ruta, b"<ComicInfo/>")
        assert ruta.read_bytes() == original
