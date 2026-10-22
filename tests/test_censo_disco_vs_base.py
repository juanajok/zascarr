# ruff: noqa: E501
"""`scripts/medicion/censo_disco_vs_base.py` (spike #297): solo lectura, sin base de datos ni disco. Pruebas con listados sintéticos."""
from __future__ import annotations

import importlib.util
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("censo_disco_vs_base", RAIZ / "scripts" / "medicion" / "censo_disco_vs_base.py")
censo = importlib.util.module_from_spec(_spec)
sys.modules["censo_disco_vs_base"] = censo      # los `dataclass` lo necesitan
_spec.loader.exec_module(censo)

P = "/media/library/"


def base(*filas):
    return censo.leer_base((f"{P}{r}\t{t}\t{m}\t{n}\n" for r, t, m, n in filas), P)


def disco(*filas):
    return censo.leer_inventario(f"{r}\t{t}\t1.0\n" for r, t in filas)


class TestLectura:

    def test_el_prefijo_del_contenedor_se_quita_y_lo_demas_se_deja(self):
        b = censo.leer_base([f"{P}Comics/a.cbz\t10\tf\tt\n", "/otro/sitio/b.cbz\t5\tt\tf\n"], P)
        assert [f.ruta for f in b] == ["Comics/a.cbz", "/otro/sitio/b.cbz"]
        assert (b[0].tamano, b[0].is_missing, b[0].con_numero) == (10, False, True) and b[1].is_missing is True

    def test_lineas_mal_formadas_se_ignoran(self):
        assert censo.leer_inventario(["", "sin tabuladores\n", "a.cbz\tNO\t1\n", "ok.cbz\t3\t1\n"]) == {"ok.cbz": 3}
        assert censo.leer_base(["solo\ttres\tcampos\n", f"{P}a.cbz\tx\tf\tf\n"], P)[0].tamano == -1


class TestComparacion:

    def test_registrado_y_presente_no_cuenta_como_sin_registrar(self):
        c = censo.comparar(disco(("Comics/a.cbz", 10)), base(("Comics/a.cbz", 10, "f", "t")))
        assert (c.comunes, c.solo_disco, c.solo_base) == (1, {}, {})

    def test_categorias_de_lo_que_esta_en_el_disco_y_no_en_la_base(self):
        c = censo.comparar(
            disco(("x/a.cbr", 1), ("x/b.rar", 2), ("x/c.tar", 3), ("x/d.part", 4), ("x/sin_ext", 5), ("x/e.PDF", 6)),
            base(("otra/z.cbz", 99, "f", "f")))
        assert c.solo_disco == {"x/a.cbr": "tebeo_sin_registrar", "x/b.rar": "formato_no_soportado", "x/c.tar": "formato_no_soportado",
                                "x/d.part": "descarga_a_medias", "x/sin_ext": "sin_extension", "x/e.PDF": "tebeo_sin_registrar"}

    def test_misma_ruta_con_otra_codificacion_unicode_o_mayusculas(self):
        nfd = unicodedata.normalize("NFD", "Cómics/Árbol.cbz")
        c = censo.comparar(disco((nfd, 1), ("COMICS/x.cbz", 2)), base(("Cómics/Árbol.cbz", 1, "f", "f"), ("Comics/X.cbz", 2, "f", "f")))
        assert set(c.solo_disco.values()) == {"misma_ruta_otra_forma"} and len(c.solo_disco) == 2

    def test_mismo_tamano_que_uno_registrado_es_una_pista_solo_para_tebeos(self):
        c = censo.comparar(disco(("n/copia.cbz", 777), ("n/otro.cbz", 5), ("n/raro.rar", 777)),
                           base(("orig/a.cbz", 777, "f", "t")))
        assert c.mismo_tamano == {"n/copia.cbz"}

    def test_filas_de_la_base_sin_fichero(self):
        c = censo.comparar(disco(("a.cbz", 1)), base(("a.cbz", 1, "f", "t"), ("falta1.cbz", 1, "t", "f"), ("falta2.cbz", 1, "f", "f")))
        assert c.solo_base == {"falta1.cbz": True, "falta2.cbz": False}

    def test_los_recuentos_cuadran(self):
        c = censo.comparar(disco(("a.cbz", 1), ("b.cbz", 2), ("c.rar", 3)), base(("a.cbz", 1, "f", "t"), ("z.cbz", 9, "t", "f")))
        assert c.en_disco == 3 and c.en_base == 2 and c.comunes + len(c.solo_disco) == c.en_disco


class TestResumenYCli:

    def test_resumen_dice_las_cifras_y_las_carpetas(self):
        c = censo.comparar(disco(*[(f"Graphic Novels/Neil/{i}.cbz", i + 100) for i in range(3)], ("Comics/a.rar", 1)),
                           base(("Comics/b.cbz", 5, "f", "t")))
        t = censo.resumen(c)
        assert "DISCO: 4 ficheros · BASE: 1 filas" in t and "tebeos (.cbz/.cbr/.cb7/.pdf/.epub) sin registrar" in t
        assert "    3  tebeos" in t
        assert "Graphic Novels/Neil" in t and ".rar=1" in t

    def test_cli_escribe_la_lista_y_no_toca_nada_mas(self, tmp_path, capsys):
        d, b, lista = tmp_path / "disco.tsv", tmp_path / "base.tsv", tmp_path / "lista.tsv"
        d.write_text("Comics/a.cbz\t10\t1\nComics/nuevo.cbz\t10\t1\nx.rar\t3\t1\n")
        b.write_text(f"{P}Comics/a.cbz\t10\tf\tt\n")
        antes = {p.name for p in tmp_path.iterdir()}
        assert censo.main(["--disco", str(d), "--base", str(b), "--lista", str(lista)]) == 0
        assert lista.read_text().splitlines() == ["Comics/nuevo.cbz\ttebeo_sin_registrar\tsi", "x.rar\tformato_no_soportado\tno"]
        assert {p.name for p in tmp_path.iterdir()} == antes | {"lista.tsv"}
        assert "DISCO: 3 ficheros" in capsys.readouterr().out

    def test_cli_con_un_listado_vacio_no_compara(self, tmp_path, capsys):
        d, b = tmp_path / "d", tmp_path / "b"
        d.write_text("")
        b.write_text(f"{P}a.cbz\t1\tf\tf\n")
        assert censo.main(["--disco", str(d), "--base", str(b)]) == 2


H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


class TestIdentidadPorContenido:

    def test_lee_la_salida_de_sha256sum_y_la_de_la_base(self):
        hd = censo.leer_hash_disco([f"{H1}  Comics/a b.cbz\n", f"{H2} *Comics/c.cbz\n", "basura\n"])
        assert hd == {"Comics/a b.cbz": H1, "Comics/c.cbz": H2}
        hb = censo.leer_hash_base([f"{P}Comics/x.cbz\t{H1}\t{H3}\n", f"{P}Comics/y.cbz\t\t\n"], P)
        assert hb == {H1: "Comics/x.cbz", H3: "Comics/x.cbz"}

    def test_idenicos_distintos_y_pares_de_carpetas(self):
        c = censo.comparar(disco(("Dup/a.cbz", 1), ("Dup/b.cbz", 2), ("Nuevo/c.cbz", 3), ("Nuevo/sin_hash.cbz", 4)),
                           base(("Orig/a.cbz", 1, "f", "t"), ("Orig/b.cbz", 2, "f", "t")))
        hd = {"Dup/a.cbz": H1, "Dup/b.cbz": H2, "Nuevo/c.cbz": H3}
        hb = {H1: "Orig/a.cbz", H2: "Orig/b.cbz"}
        t = censo.confirmar_identidad(c, hd, hb)
        assert "tebeos sin registrar: 4 · con hash calculado: 3 · sin hash: 1" in t
        assert "2  IDÉNTICOS a un archivo registrado" in t
        assert "1  contenido que NO está registrado" in t and "2  Dup  →  Orig" in t

    def test_cli_con_los_dos_pasos(self, tmp_path, capsys):
        d, b, hd, hb = (tmp_path / n for n in ("d", "b", "hd", "hb"))
        d.write_text("Dup/a.cbz\t10\t1\n")
        b.write_text(f"{P}Orig/a.cbz\t10\tf\tt\n")
        hd.write_text(f"{H1}  Dup/a.cbz\n")
        hb.write_text(f"{P}Orig/a.cbz\t{H1}\t\n")
        assert censo.main(["--disco", str(d), "--base", str(b), "--hash-disco", str(hd), "--hash-base", str(hb)]) == 0
        assert "IDÉNTICOS a un archivo registrado" in capsys.readouterr().out

    def test_un_identico_cuyo_original_esta_marcado_is_missing_es_un_movimiento_no_una_copia(self):
        c = censo.comparar(disco(("Nueva/a.cbz", 1), ("Nueva/b.cbz", 2)),
                           base(("Vieja/a.cbz", 1, "t", "f"), ("Vieja/b.cbz", 2, "f", "t")))
        hd = {"Nueva/a.cbz": H1, "Nueva/b.cbz": H2}
        hb = {H1: "Vieja/a.cbz", H2: "Vieja/b.cbz"}
        t = censo.confirmar_identidad(c, hd, hb)
        assert "2  IDÉNTICOS a un archivo registrado" in t
        assert "1  de los idénticos corresponden a una fila marcada is_missing" in t
