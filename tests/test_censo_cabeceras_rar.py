# ruff: noqa: E501
"""`scripts/medicion/evaluacion_rar/censo_cabeceras_rar.py` (spike #308): solo lectura de los primeros bytes. Cabeceras RAR4/RAR5 SINTÉTICAS
construidas byte a byte según el formato publicado: prueban el intérprete, **no** sustituyen a un RAR real (la primera ejecución en la Pi lo contrasta)."""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("censo_cabeceras_rar", RAIZ / "scripts" / "medicion" / "evaluacion_rar" / "censo_cabeceras_rar.py")
c = importlib.util.module_from_spec(_spec)
sys.modules["censo_cabeceras_rar"] = c
_spec.loader.exec_module(c)


def rar4(solido=False, cab_cifradas=False, fichero_cifrado=False, con_fichero=True, con_comentario=False):
    flags = (0x0008 if solido else 0) | (0x0080 if cab_cifradas else 0)
    b = c.RAR4 + struct.pack("<HBHH", 0, 0x73, flags, 13) + b"\0" * 6
    if con_comentario:                               # bloque 0x75 con datos añadidos (LONG_BLOCK + ADD_SIZE)
        b += struct.pack("<HBHH", 0, 0x75, 0x8000, 11) + struct.pack("<I", 5) + b"\0" * 5
    if con_fichero:
        b += struct.pack("<HBHH", 0, 0x74, 0x8000 | (0x0004 if fichero_cifrado else 0), 32) + b"\0" * 25
    return b


def vint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def bloque5(tipo, flags=0, cuerpo=b"", extra=b"", datos=None):
    interior = vint(tipo) + vint(flags | (0x01 if extra else 0) | (0x02 if datos is not None else 0))
    if extra:
        interior += vint(len(extra))
    if datos is not None:
        interior += vint(datos)
    interior += cuerpo + extra
    return b"\0\0\0\0" + vint(len(interior)) + interior


def rar5(solido=False, cab_cifradas=False, registro_cifrado=False, con_fichero=True):
    if cab_cifradas:
        return c.RAR5 + bloque5(4, cuerpo=b"\0" * 8)
    b = c.RAR5 + bloque5(1, cuerpo=vint(0x04 if solido else 0))
    if con_fichero:
        extra = (vint(5) + vint(0x01) + b"\0" * 4) if registro_cifrado else (vint(5) + vint(0x02) + b"\0" * 4)
        b += bloque5(2, cuerpo=b"\0" * 12, extra=extra, datos=1000)
    return b


class TestRar4:

    def test_normal_no_es_solido_ni_cifrado(self):
        assert c.clasificar(rar4()) == c.Cabecera("RAR4", False, "no")

    def test_solido(self):
        assert c.clasificar(rar4(solido=True)).solido is True

    def test_cabeceras_cifradas(self):
        r = c.clasificar(rar4(cab_cifradas=True))
        assert r.cifrado == "cabeceras" and r.firma == "RAR4"

    def test_primer_fichero_cifrado(self):
        assert c.clasificar(rar4(fichero_cifrado=True)).cifrado == "archivos"

    def test_un_bloque_con_datos_antes_del_fichero_se_salta_bien(self):
        assert c.clasificar(rar4(fichero_cifrado=True, con_comentario=True)).cifrado == "archivos"

    def test_sin_fichero_visible_es_desconocido_no_inventa(self):
        assert c.clasificar(rar4(con_fichero=False)).cifrado == "desconocido"


class TestRar5:

    def test_normal(self):
        assert c.clasificar(rar5()) == c.Cabecera("RAR5", False, "no")

    def test_solido(self):
        assert c.clasificar(rar5(solido=True)).solido is True

    def test_cabeceras_cifradas(self):
        assert c.clasificar(rar5(cab_cifradas=True)).cifrado == "cabeceras"

    def test_registro_de_cifrado_en_el_area_extra(self):
        assert c.clasificar(rar5(registro_cifrado=True)).cifrado == "archivos"


class TestOtrosYRobustez:

    def test_zip_y_7z_y_basura(self):
        assert c.clasificar(b"PK\x03\x04....").firma == "ZIP"
        assert c.clasificar(b"7z\xbc\xaf\x27\x1c....").firma == "7z"
        assert c.clasificar(b"hola").firma == "otro"

    def test_truncado_en_cualquier_punto_nunca_lanza(self):
        for b in (rar4(solido=True, fichero_cifrado=True), rar5(solido=True, registro_cifrado=True)):
            for i in range(len(b) + 1):
                r = c.clasificar(b[:i])
                assert r.cifrado in {"no", "cabeceras", "archivos", "desconocido"}

    def test_bytes_aleatorios_tras_la_firma_nunca_lanzan(self):
        import random
        rng = random.Random(308)
        for firma in (c.RAR4, c.RAR5):
            for _ in range(300):
                c.clasificar(firma + bytes(rng.randrange(256) for _ in range(rng.randrange(0, 80))))

    def test_vint_largo_sin_fin_no_se_cuelga(self):
        assert c._vint(b"\xff" * 40, 0) is None


class TestRecorridoYReglaDeEleccion:

    def test_solo_cbr_rar_y_sin_extension_y_no_escribe_nada(self, tmp_path):
        (tmp_path / "Serie").mkdir()
        (tmp_path / "Serie" / "a.cbr").write_bytes(rar4(solido=True))
        (tmp_path / "Serie" / "b.CBZ").write_bytes(b"PK\x03\x04")
        (tmp_path / "Serie" / "sin_extension").write_bytes(rar5())
        antes = sorted(p.name for p in tmp_path.rglob("*"))
        filas = list(c.recorrer(tmp_path))
        assert {f[0] for f in filas} == {"Serie/a.cbr", "Serie/sin_extension"}
        assert sorted(p.name for p in tmp_path.rglob("*")) == antes

    def test_regla_dos_solidos_dos_cifrados_y_tipicos_deterministas(self):
        MB = 1 << 20
        f = lambda r, t, **k: (r, t, c.Cabecera("RAR4", k.get("solido", False), k.get("cifrado", "no")))  # noqa: E731
        filas = [f(f"s{i:02d}.cbr", (10 + i) * MB, solido=(i % 10 == 0)) for i in range(130)]
        filas += [f("grande.cbr", 900 * MB, solido=True), f("cif1.cbr", 5 * MB, cifrado="archivos"), f("cif2.cbr", 6 * MB, cifrado="cabeceras"), f("cif3.cbr", 7 * MB, cifrado="archivos")]
        a, b = c.elegir(filas, 4), c.elegir(list(reversed(filas)), 4)
        assert a == b                                                          # no depende del orden de entrada
        motivos = [m for _, m in a]
        assert sum(m.startswith("sólido") for m in motivos) == 2
        assert "grande.cbr" not in {r for r, _ in a}                          # por encima del tope de 300 MB
        assert [r for r, m in a if m.startswith("cifrado")] == ["cif1.cbr", "cif2.cbr"]
        assert sum(m.startswith("típico") for m in motivos) == 4
        assert len({r for r, _ in a}) == len(a)                               # sin repetidos
