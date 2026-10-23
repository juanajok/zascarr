# ruff: noqa: E501
"""#307 — formato por contenido. T1–T4 y T8 del contrato (`docs/design/contrato-307-formato-por-contenido.md`): firma, matriz extensión × firma,
clasificación de un ZIP, lectura acotada. Sintético: ZIP/TAR/RAR fabricados en un directorio temporal; ni biblioteca real ni red."""
from __future__ import annotations

import io
import struct
import tarfile
import zipfile
from pathlib import Path

import pytest

from zascarr.core import formato_contenedor as fc
from zascarr.models import ClaseZip, Firma, Tratamiento

RAR4 = b"Rar!\x1a\x07\x00" + b"\0" * 40
RAR5 = b"Rar!\x1a\x07\x01\x00" + b"\0" * 40
SIETE_Z = b"7z\xbc\xaf\x27\x1c" + b"\0" * 40


def zip_de(ruta: Path, entradas: dict[str, bytes], cifrado: bool = False) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, d in entradas.items():
            zf.writestr(n, d)
    if cifrado:                                    # `zipfile` reinicia el indicador al escribir: se marca a mano en el directorio central
        b = bytearray(ruta.read_bytes())
        i = b.find(b"PK\x01\x02")
        while i != -1:
            b[i + 8] |= 0x1
            i = b.find(b"PK\x01\x02", i + 4)
        ruta.write_bytes(bytes(b))
    return ruta


def paginas(n: int, ext: str = ".jpg") -> dict[str, bytes]:
    return {f"{i:03d}{ext}": b"x" * 100 for i in range(n)}


class TestFirma:                                                                           # T1

    def test_cada_formato(self, tmp_path):
        zip_de(tmp_path / "a.zip", paginas(3))
        with zipfile.ZipFile(tmp_path / "vacio.zip", "w"):
            pass
        (tmp_path / "partido.zip").write_bytes(b"PK\x07\x08" + b"\0" * 30)
        (tmp_path / "r4").write_bytes(RAR4)
        (tmp_path / "r5").write_bytes(RAR5)
        (tmp_path / "s7").write_bytes(SIETE_Z)
        with tarfile.open(tmp_path / "t.tar", "w") as t:
            ti = tarfile.TarInfo("a.jpg")
            ti.size = 3
            t.addfile(ti, io.BytesIO(b"abc"))
        (tmp_path / "texto").write_text("hola mundo")
        (tmp_path / "vacio").write_bytes(b"")
        esperado = {"a.zip": Firma.ZIP, "vacio.zip": Firma.ZIP, "partido.zip": Firma.ZIP, "r4": Firma.RAR, "r5": Firma.RAR, "s7": Firma.SIETE_Z,
                    "t.tar": Firma.TAR, "texto": Firma.OTRO, "vacio": Firma.OTRO}
        assert {n: fc.firma_de(tmp_path / n) for n in esperado} == esperado

    def test_un_fichero_que_no_existe_o_no_se_puede_leer_es_ilegible_y_no_lanza(self, tmp_path):
        assert fc.firma_de(tmp_path / "no_existe") is Firma.ILEGIBLE
        assert fc.firma_de(tmp_path) is Firma.ILEGIBLE                                    # un directorio

    def test_lee_como_maximo_512_bytes(self, tmp_path, monkeypatch):
        f = tmp_path / "grande.cbr"
        f.write_bytes(b"PK\x03\x04" + b"\0" * 5_000_000)
        leido = []

        class Espia:
            def __init__(self, fh):
                self.fh = fh

            def read(self, n=-1):
                d = self.fh.read(n)
                leido.append(len(d))
                return d

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.fh.close()
        monkeypatch.setattr(fc, "open", lambda *a, **k: Espia(open(*a, **k)), raising=False)  # noqa: SIM115
        assert fc.firma_de(f) is Firma.ZIP and sum(leido) <= 512


class TestMatriz:                                                                           # T2

    @pytest.mark.parametrize("ext,firma,esperado", [
        (".cbz", Firma.ZIP, Tratamiento.LEER_COMO_ZIP),
        (".cbz", Firma.RAR, Tratamiento.AVISAR),
        (".cbz", Firma.SIETE_Z, Tratamiento.AVISAR),
        (".cbz", Firma.OTRO, Tratamiento.AVISAR),
        (".cbr", Firma.ZIP, Tratamiento.LEER_COMO_ZIP),                    # el caso principal: 56 ficheros en la biblioteca real
        (".cbr", Firma.RAR, Tratamiento.SOLO_HASH),
        (".cbr", Firma.SIETE_Z, Tratamiento.AVISAR),
        (".cbr", Firma.OTRO, Tratamiento.AVISAR),
        (".cb7", Firma.ZIP, Tratamiento.LEER_COMO_ZIP),
        (".cb7", Firma.SIETE_Z, Tratamiento.SOLO_HASH),
        (".cb7", Firma.RAR, Tratamiento.AVISAR),
        (".zip", Firma.ZIP, Tratamiento.LEER_COMO_ZIP),
        (".zip", Firma.RAR, Tratamiento.AVISAR),
        ("", Firma.ZIP, Tratamiento.AVISAR),                               # D1: sin extensión no se registra; se avisa
        ("", Firma.RAR, Tratamiento.AVISAR),
        ("", Firma.SIETE_Z, Tratamiento.AVISAR),
        ("", Firma.TAR, Tratamiento.AVISAR),
        ("", Firma.OTRO, Tratamiento.SOLO_HASH),
        (".rar", Firma.RAR, Tratamiento.AVISAR),
        (".pdf", Firma.ZIP, Tratamiento.SOLO_HASH),
        (".epub", Firma.OTRO, Tratamiento.SOLO_HASH),
        (".cbz", Firma.ILEGIBLE, Tratamiento.SOLO_HASH),
        ("", Firma.ILEGIBLE, Tratamiento.SOLO_HASH),
    ])
    def test_celda(self, ext, firma, esperado):
        assert fc.tratamiento(ext, firma) is esperado

    def test_la_funcion_es_pura_no_toca_el_disco(self, monkeypatch):
        monkeypatch.setattr(fc, "open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("E/S")), raising=False)
        assert fc.tratamiento(".cbr", Firma.ZIP) is Tratamiento.LEER_COMO_ZIP


class TestClasificarZip:                                                                    # T3 y T4

    def test_tebeo_paquete_no_tebeo_cifrado_vacio_invalido_limite(self, tmp_path):
        assert fc.clasificar_zip(zip_de(tmp_path / "t.zip", {**paginas(12), "ComicInfo.xml": b"<c/>"})).clase is ClaseZip.TEBEO
        assert fc.clasificar_zip(zip_de(tmp_path / "p.zip", {**paginas(20), "extra/otro.cbz": b"PK"})).clase is ClaseZip.PAQUETE
        assert fc.clasificar_zip(zip_de(tmp_path / "n.zip", {"a.txt": b"1", "b.docx": b"2", **paginas(2)})).clase is ClaseZip.NO_TEBEO
        assert fc.clasificar_zip(zip_de(tmp_path / "c.zip", paginas(12), cifrado=True)).clase is ClaseZip.CIFRADO
        with zipfile.ZipFile(tmp_path / "v.zip", "w"):
            pass
        assert fc.clasificar_zip(tmp_path / "v.zip").clase is ClaseZip.VACIO
        (tmp_path / "roto.zip").write_bytes(zip_de(tmp_path / "ok.zip", paginas(12)).read_bytes()[:200])
        assert fc.clasificar_zip(tmp_path / "roto.zip").clase is ClaseZip.INVALIDO
        assert fc.clasificar_zip(tmp_path / "no_existe.zip").clase is ClaseZip.INVALIDO
        assert fc.clasificar_zip(zip_de(tmp_path / "l.zip", paginas(30)), max_entradas=10).clase is ClaseZip.LIMITE

    def test_pdf_y_epub_dentro_hacen_paquete(self, tmp_path):                              # D4
        assert fc.clasificar_zip(zip_de(tmp_path / "a.zip", {**paginas(12), "x.pdf": b"%PDF"})).clase is ClaseZip.PAQUETE
        assert fc.clasificar_zip(zip_de(tmp_path / "b.zip", {**paginas(12), "x.epub": b"PK"})).clase is ClaseZip.PAQUETE

    @pytest.mark.parametrize("n,esperado", [(fc.MIN_IMAGENES - 1, ClaseZip.NO_TEBEO), (fc.MIN_IMAGENES, ClaseZip.TEBEO)])
    def test_minimo_de_imagenes(self, tmp_path, n, esperado):
        assert fc.clasificar_zip(zip_de(tmp_path / "m.zip", paginas(n))).clase is esperado

    def test_fraccion_de_imagenes_y_ruido(self, tmp_path):
        assert fc.clasificar_zip(zip_de(tmp_path / "f.zip", {**paginas(10), **{f"n{i}.txt": b"t" for i in range(5)}})).clase is ClaseZip.NO_TEBEO      # 0,67
        assert fc.clasificar_zip(zip_de(tmp_path / "g.zip", {**paginas(10), "Thumbs.db": b"x", "ComicInfo.xml": b"<c/>", ".DS_Store": b"x"})).clase is ClaseZip.TEBEO

    def test_primera_pagina_en_orden_natural_y_las_carpetas_no_cuentan(self, tmp_path):
        ruta = tmp_path / "n.zip"
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("cap/", b"")
            for n in ("10.jpg", "2.jpg", "1.jpg", *[f"x{i}.jpg" for i in range(9)]):
                zf.writestr(f"cap/{n}", b"x")
        c = fc.clasificar_zip(ruta)
        assert c.primera_pagina == "cap/1.jpg" and c.entradas == 12 and c.clase is ClaseZip.TEBEO

    def test_nunca_descomprime(self, tmp_path, monkeypatch):
        z = zip_de(tmp_path / "n.cbz", {**paginas(12), "ComicInfo.xml": b"<c/>"})

        def prohibido(*a, **k):
            raise AssertionError("se intentó descomprimir")
        monkeypatch.setattr(zipfile.ZipFile, "read", prohibido)
        monkeypatch.setattr(zipfile.ZipFile, "open", prohibido)
        assert fc.clasificar_zip(z).clase is ClaseZip.TEBEO


class TestLecturaAcotada:                                                                   # T8

    def _leer(self, ruta, nombre="a.jpg", **kw):
        with zipfile.ZipFile(ruta) as zf:
            return fc.leer_acotado(zf, zf.getinfo(nombre), **kw)

    def test_una_entrada_normal_se_lee(self, tmp_path):
        assert self._leer(zip_de(tmp_path / "a.zip", {"a.jpg": b"hola" * 10})) == b"hola" * 10

    def test_tamano_declarado_sobre_el_tope(self, tmp_path):
        with pytest.raises(fc.EntradaNoLegible, match="demasiado grande"):
            self._leer(zip_de(tmp_path / "a.zip", {"a.jpg": b"x" * 5000}), tope=1000)

    def test_ratio_sospechoso_bomba(self, tmp_path):
        with pytest.raises(fc.EntradaNoLegible, match="bomba"):
            self._leer(zip_de(tmp_path / "b.zip", {"a.jpg": b"\0" * 5_000_000}), tope=10_000_000)

    def test_tamano_declarado_falso_no_ocupa_mas_memoria_que_el_tope(self, tmp_path):
        """Una cabecera que MIENTE (declara 100 B y expande millones) no puede colar más de `tope` bytes."""
        z = zip_de(tmp_path / "m.zip", {"a.jpg": b"\0" * 5_000_000})
        b = bytearray(z.read_bytes())
        i = b.find(b"PK\x01\x02")
        b[i + 24:i + 28] = struct.pack("<I", 100)                 # tamaño descomprimido declarado en el directorio central
        z.write_bytes(bytes(b))
        try:
            datos = self._leer(z, tope=1000, ratio=10_000_000)
        except fc.EntradaNoLegible:
            return                                                # rechazada: válido
        assert len(datos) <= 1000                                 # o, como mucho, acotada

    def test_cifrada(self, tmp_path):
        with pytest.raises(fc.EntradaNoLegible, match="contraseña"):
            self._leer(zip_de(tmp_path / "c.zip", {"a.jpg": b"x" * 50}, cifrado=True))

    def test_entrada_danada(self, tmp_path):
        import random
        z = zip_de(tmp_path / "d.zip", {"a.jpg": random.Random(7).randbytes(3000)})      # poco comprimible: el ratio no salta antes
        b = bytearray(z.read_bytes())
        b[200:240] = b"\xff" * 40                                 # estropea el flujo comprimido
        z.write_bytes(bytes(b))
        with pytest.raises(fc.EntradaNoLegible, match="dañada"):
            self._leer(z)


class TestFormatoGuardado:

    def test_formato_contenido_es_json_plano_y_versionado(self):
        assert fc.formato_contenido(Firma.ZIP, ClaseZip.TEBEO) == {"firma": "zip", "contrato": 1, "clase": "tebeo"}
        assert fc.formato_contenido(Firma.RAR) == {"firma": "rar", "contrato": 1}

    def test_formato_real_de_un_fichero_ya_registrado(self, tmp_path):
        assert fc.formato_real_de(zip_de(tmp_path / "t.cbr", paginas(12))) == {"firma": "zip", "contrato": 1, "clase": "tebeo"}
        (tmp_path / "r.cbr").write_bytes(RAR5)
        assert fc.formato_real_de(tmp_path / "r.cbr") == {"firma": "rar", "contrato": 1}
        assert fc.formato_real_de(tmp_path / "no_existe.cbr") is None              # ilegible: se reintenta, no se marca

    @pytest.mark.parametrize("ext,guardado,esperado", [
        (".cbr", {"firma": "zip", "clase": "tebeo"}, True),
        (".cbr", {"firma": "zip", "clase": "paquete"}, False),
        (".cbr", {"firma": "zip", "clase": "no_tebeo"}, False),
        (".cbr", {"firma": "rar"}, False),
        (".cbz", {"firma": "zip", "clase": "no_tebeo"}, True),                     # un .cbz declarado y corto sigue dando su primera página
        (".cbz", {"firma": "zip", "clase": "paquete"}, True),
        (".cbz", {"firma": "zip", "clase": "cifrado"}, False),
        (".cbz", {"firma": "rar"}, False),                                          # un .cbz que es RAR: sin portada
        (".cbr", None, None),                                                       # nada guardado → decide la extensión
        (".cbr", {}, None),
    ])
    def test_puede_dar_portada_sin_tocar_el_disco(self, ext, guardado, esperado):
        assert fc.puede_dar_portada(ext, guardado) is esperado

    def test_los_avisos_dicen_causa_y_accion(self):
        assert fc.aviso_de_formato(".cbz", Firma.RAR) == ("Se llama .cbz, pero por dentro es un .cbr (RAR). "
                                                          "Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.")
        assert "su nombre no acaba en .cbz" in fc.aviso_de_formato("", Firma.ZIP) and "desde tu ordenador" in fc.aviso_de_formato("", Firma.ZIP)
        assert "cambia el final del nombre a .cbr" in fc.aviso_de_formato("", Firma.RAR)
        assert "cambia el final del nombre a .cb7" in fc.aviso_de_formato("", Firma.SIETE_Z)
        assert "(TAR) que ZascArr no usa" in fc.aviso_de_formato("", Firma.TAR)
        assert fc.aviso_de_extension(".rar").startswith("Es un archivo .rar.") and "descomprímelo" in fc.aviso_de_extension(".rar")
        assert "cambia el final del nombre a .cb7" in fc.aviso_de_extension(".7z")
        assert fc.aviso_de_extension(".cbt") == "ZascArr no usa este formato (CBT). Para conservarlo como tebeo, conviértelo a .cbz con otro programa."

    def test_todos_los_textos_siguen_las_reglas_de_ux(self):
        """Revisión de UX (2026-10-23): ≤ 2 frases; sin jerga (entradas, firma, contenedor, nombres de clase); «desde tu ordenador», nunca «fuera de ZascArr»;
        la garantía «no cambia nada» va una sola vez en la cabecera de la sección, no en cada fila; nunca «formato no soportado» a secas."""
        import re
        textos = list(fc.AVISO_CLASE.values()) + [fc.INFO_CBR_ES_ZIP]
        for ext in (".cbz", ".zip", ".cbr", ".cb7", ""):
            for firma in (Firma.ZIP, Firma.RAR, Firma.SIETE_Z, Firma.TAR, Firma.OTRO):
                textos.append(fc.aviso_de_formato(ext, firma))
        textos += [fc.aviso_de_extension(e) for e in (".rar", ".7z", ".tar", ".cbt")]
        prohibido = ("entradas", "firma", "contenedor", "PAQUETE", "INVALIDO", "NO_TEBEO", "fuera de ZascArr", "No se ha cambiado", "no se trata como tal",
                     "formato no soportado", "sin descomprimir")
        for t in textos:
            assert len(re.findall(r"[.?!](?:\s|$)", t)) <= 2, t
            assert not [p for p in prohibido if p.lower() in t.lower()], t
            assert t.strip() and t[0].isupper(), t
