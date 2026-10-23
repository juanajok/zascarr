# ruff: noqa: E501
"""`scripts/medicion/censo_zip_por_contenido.py` (spike #307): lee SOLO el directorio central, no descomprime, no escribe y no imprime nombres. ZIP sintéticos."""
from __future__ import annotations

import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("censo_zip_por_contenido", RAIZ / "scripts" / "medicion" / "censo_zip_por_contenido.py")
c = importlib.util.module_from_spec(_spec)
sys.modules["censo_zip_por_contenido"] = c
_spec.loader.exec_module(c)


def zip_de(ruta: Path, entradas: dict[str, bytes], cifrado: bool = False) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in entradas.items():
            zf.writestr(n, d)
    if cifrado:                                    # `zipfile` reinicia el indicador al escribir: se marca a mano en el directorio central (bit 0 = cifrada)
        b = bytearray(ruta.read_bytes())
        i = b.find(b"PK\x01\x02")
        while i != -1:
            b[i + 8] |= 0x1
            i = b.find(b"PK\x01\x02", i + 4)
        ruta.write_bytes(bytes(b))
    return ruta


def paginas(n: int, ext: str = ".jpg") -> dict[str, bytes]:
    return {f"{i:03d}{ext}": b"x" * 100 for i in range(n)}


class TestClasificacion:

    def test_tebeo_normal_con_comicinfo(self, tmp_path):
        z = zip_de(tmp_path / "a.cbz", {**paginas(12), "ComicInfo.xml": b"<ComicInfo/>"})
        m = c.medir(z)
        assert (m.estado, m.entradas, m.imagenes, m.anidados, m.comicinfo) == ("ok", 13, 12, 0, True)
        assert c.clasificar(m) == "tebeo"

    def test_paquete_con_un_contenedor_anidado(self, tmp_path):
        m = c.medir(zip_de(tmp_path / "p.zip", {**paginas(20), "Extras/otro.cbz": b"PK"}))
        assert m.anidados == 1 and c.clasificar(m) == "paquete"

    def test_zip_de_documentos_no_es_un_tebeo(self, tmp_path):
        m = c.medir(zip_de(tmp_path / "d.zip", {"a.txt": b"1", "b.docx": b"2", "c.mp3": b"3", **paginas(2)}))
        assert c.clasificar(m) == "no_tebeo"

    def test_un_pdf_o_epub_dentro_cuenta_como_contenedor_y_lo_hace_paquete(self, tmp_path):
        """Decisión conservadora (idea de Kapowarr): se MARCA como paquete, no se registra como un tebeo."""
        assert c.clasificar(c.medir(zip_de(tmp_path / "p.zip", {**paginas(10), "extra.pdf": b"%PDF"}))) == "paquete"
        assert c.clasificar(c.medir(zip_de(tmp_path / "q.zip", {**paginas(10), "extra.epub": b"PK"}))) == "paquete"

    @pytest.mark.parametrize("n,esperado", [(4, "no_tebeo"), (5, "tebeo"), (6, "tebeo")])
    def test_minimo_de_imagenes(self, tmp_path, n, esperado):
        assert c.clasificar(c.medir(zip_de(tmp_path / "m.zip", paginas(n)))) == esperado

    def test_fraccion_de_imagenes_sobre_el_contenido(self, tmp_path):
        ruido_real = {f"nota{i}.txt": b"t" for i in range(5)}
        assert c.clasificar(c.medir(zip_de(tmp_path / "f.zip", {**paginas(10), **ruido_real}))) == "no_tebeo"          # 10/15 = 0,67
        assert c.clasificar(c.medir(zip_de(tmp_path / "g.zip", {**paginas(10), **{"x.txt": b"t"}}))) == "tebeo"      # 10/11 = 0,91

    def test_thumbs_db_y_comicinfo_no_cuentan_como_contenido(self, tmp_path):
        m = c.medir(zip_de(tmp_path / "t.cbz", {**paginas(8), "Thumbs.db": b"x", "ComicInfo.xml": b"<c/>", ".DS_Store": b"x"}))
        assert m.contenido == 8 and c.clasificar(m) == "tebeo"

    def test_cifrado(self, tmp_path):
        m = c.medir(zip_de(tmp_path / "e.zip", paginas(10), cifrado=True))
        assert m.cifrado and c.clasificar(m) == "cifrado"

    def test_las_carpetas_no_cuentan_como_entradas(self, tmp_path):
        ruta = tmp_path / "d.cbz"
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("capitulo1/", b"")
            for i in range(6):
                zf.writestr(f"capitulo1/{i}.png", b"x")
        m = c.medir(ruta)
        assert m.entradas == 6 and c.clasificar(m) == "tebeo"

    def test_parametros_ajustables(self, tmp_path):
        z = zip_de(tmp_path / "p.zip", paginas(3))
        assert c.clasificar(c.medir(z)) == "no_tebeo" and c.clasificar(c.medir(z), min_imagenes=3) == "tebeo"


class TestLoQueImportaSiSoloSeLeeUnaPagina:

    def test_entrada_mayor_y_primera_pagina_en_orden_natural(self, tmp_path):
        z = zip_de(tmp_path / "n.cbz", {"10.jpg": b"a" * 50, "2.jpg": b"b" * 3000, "1.jpg": b"c" * 500, "ComicInfo.xml": b"<c/>" * 10, "z.txt": b"q" * 9000})
        m = c.medir(z)
        assert m.mayor_entrada == 9000 and m.pagina1_bytes == 500          # «1.jpg» antes que «2.jpg» y «10.jpg»

    def test_el_total_puede_superar_el_tope_aunque_cada_pagina_sea_pequena(self, tmp_path):
        z = zip_de(tmp_path / "t.cbz", paginas(30))
        assert c.medir(z, max_descomprimido=2000).estado == "demasiado_grande"          # 30 × 100 B
        assert c.medir(z).mayor_entrada == 100

    def test_el_resumen_cuenta_los_que_superan_los_topes(self, tmp_path):
        z = zip_de(tmp_path / "t.cbz", paginas(30))
        fila = ("cbz_control", Path("t.cbz"), 1, c.medir(z, max_descomprimido=2000))
        r = c.resumen([fila], 5, 0.8)
        assert "SUPERAN los topes de hoy" in r and "cómo son: imágenes mín 30 / máx 30" in r and "entrada mayor máx 0 KiB" in r


class TestLimitesYErrores:

    def test_demasiadas_entradas_y_demasiado_grande(self, tmp_path):
        z = zip_de(tmp_path / "g.zip", paginas(11))
        assert c.clasificar(c.medir(z, max_entradas=10)) == "limite" and c.medir(z, max_entradas=10).estado == "demasiadas_entradas"
        grande = zip_de(tmp_path / "h.zip", {"a.jpg": b"0" * 5000})
        assert c.medir(grande, max_descomprimido=1000).estado == "demasiado_grande"

    def test_los_que_superan_los_topes_se_miden_igual(self, tmp_path):
        """Hace falta saber CÓMO son los que superan el tope de hoy para decidir topes por entrada."""
        z = zip_de(tmp_path / "l.cbz", {**paginas(30), "ComicInfo.xml": b"<c/>"})
        m = c.medir(z, max_descomprimido=2000)
        assert (m.estado, m.imagenes, m.comicinfo, m.mayor_entrada, m.pagina1_bytes) == ("demasiado_grande", 30, True, 100, 100)
        m2 = c.medir(z, max_entradas=10)
        assert m2.estado == "demasiadas_entradas" and m2.imagenes == 30
        assert c.clasificar(m) == c.clasificar(m2) == "limite"

    def test_bomba_se_ve_por_el_ratio_sin_descomprimir(self, tmp_path):
        z = zip_de(tmp_path / "b.zip", {"a.jpg": b"\0" * 5_000_000})
        m = c.medir(z)
        assert m.ratio_max > 500 and m.descomprimido == 5_000_000

    def test_corrupto_y_vacio_y_basura(self, tmp_path):
        buena = zip_de(tmp_path / "ok.zip", paginas(8)).read_bytes()
        (tmp_path / "cortado.zip").write_bytes(buena[: len(buena) // 2])
        assert c.medir(tmp_path / "cortado.zip").estado == "invalido"
        (tmp_path / "basura.cbr").write_bytes(b"PK\x03\x04" + b"\xff" * 64)
        assert c.clasificar(c.medir(tmp_path / "basura.cbr")) == "invalido"
        with zipfile.ZipFile(tmp_path / "vacio.zip", "w"):
            pass
        assert c.clasificar(c.medir(tmp_path / "vacio.zip")) == "vacio" and c.es_zip(tmp_path / "vacio.zip")

    def test_no_existe_no_lanza(self, tmp_path):
        assert c.medir(tmp_path / "nada.zip").estado == "invalido"

    def test_nunca_descomprime(self, tmp_path, monkeypatch):
        z = zip_de(tmp_path / "n.cbz", {**paginas(10), "ComicInfo.xml": b"<c/>"})

        def prohibido(*a, **k):
            raise AssertionError("se intentó descomprimir")
        monkeypatch.setattr(zipfile.ZipFile, "read", prohibido)
        monkeypatch.setattr(zipfile.ZipFile, "open", prohibido)
        assert c.clasificar(c.medir(z)) == "tebeo"


class TestGruposYRecorrido:

    @pytest.mark.parametrize("nombre,grupo", [("a.cbz", "cbz_control"), ("A.CBR", "cbr_zip"), ("b.rar", "cbr_zip"), ("c.zip", "zip"), ("sin_ext", "sin_extension"), (".oculto", None), ("d.pdf", None), ("e.cbz.rar", "cbr_zip")])
    def test_grupo_por_extension(self, nombre, grupo):
        assert c.grupo_de(Path(nombre)) == grupo

    def test_solo_entran_los_de_firma_zip_y_el_original_no_cambia(self, tmp_path):
        serie = tmp_path / "Serie"
        serie.mkdir()
        zip_de(serie / "oculto.cbr", paginas(9))
        zip_de(serie / "sin_extension", paginas(7))
        (serie / "rar_de_verdad.cbr").write_bytes(b"Rar!\x1a\x07\x00" + b"\0" * 50)
        (serie / "notas.txt").write_text("x")
        antes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in serie.iterdir()}
        mtimes = {p.name: p.stat().st_mtime_ns for p in serie.iterdir()}
        filas = list(c.recorrer(tmp_path))
        assert sorted((g, str(r)) for g, r, _t, _m in filas) == [("cbr_zip", "Serie/oculto.cbr"), ("sin_extension", "Serie/sin_extension")]
        assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in serie.iterdir()} == antes
        assert {p.name: p.stat().st_mtime_ns for p in serie.iterdir()} == mtimes

    def test_la_salida_estandar_no_lleva_nombres_y_el_tsv_si(self, tmp_path, capsys):
        (tmp_path / "Biblioteca").mkdir()
        zip_de(tmp_path / "Biblioteca" / "Secreto_serie_01.cbr", paginas(9))
        zip_de(tmp_path / "Biblioteca" / "Control.cbz", paginas(9))
        tsv = tmp_path / "salida.tsv"
        assert c.main([str(tmp_path / "Biblioteca"), "--tsv", str(tsv)]) == 0
        fuera = capsys.readouterr().out
        assert "Secreto_serie" not in fuera and "Control" not in fuera and "[cbr_zip] 1 ficheros" in fuera and "[cbz_control] 1 ficheros" in fuera
        assert "Secreto_serie_01.cbr" in tsv.read_text()

    def test_raiz_inexistente(self, tmp_path, capsys):
        assert c.main([str(tmp_path / "no")]) == 2
