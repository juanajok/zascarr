# ruff: noqa: E501
"""#307 — formato por contenido. T1–T4 y T8 del contrato (`docs/design/contrato-307-formato-por-contenido.md`): firma, matriz extensión × firma,
clasificación de un ZIP, lectura acotada. Sintético: ZIP/TAR/RAR fabricados en un directorio temporal; ni biblioteca real ni red."""
from __future__ import annotations

import contextlib
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

    def test_tebeo_anidados_no_tebeo_cifrado_vacio_invalido_limite(self, tmp_path):
        assert fc.clasificar_zip(zip_de(tmp_path / "t.zip", {**paginas(12), "ComicInfo.xml": b"<c/>"})).clase is ClaseZip.TEBEO
        assert fc.clasificar_zip(zip_de(tmp_path / "p.zip", {**paginas(20), "extra/otro.cbz": b"PK"})).clase is ClaseZip.ANIDADOS
        assert fc.clasificar_zip(zip_de(tmp_path / "n.zip", {"a.txt": b"1", "b.docx": b"2", **paginas(2)})).clase is ClaseZip.NO_TEBEO
        assert fc.clasificar_zip(zip_de(tmp_path / "c.zip", paginas(12), cifrado=True)).clase is ClaseZip.CIFRADO
        with zipfile.ZipFile(tmp_path / "v.zip", "w"):
            pass
        assert fc.clasificar_zip(tmp_path / "v.zip").clase is ClaseZip.VACIO
        (tmp_path / "roto.zip").write_bytes(zip_de(tmp_path / "ok.zip", paginas(12)).read_bytes()[:200])
        assert fc.clasificar_zip(tmp_path / "roto.zip").clase is ClaseZip.INVALIDO
        assert fc.clasificar_zip(tmp_path / "no_existe.zip").clase is ClaseZip.INVALIDO
        assert fc.clasificar_zip(zip_de(tmp_path / "l.zip", paginas(30)), max_entradas=10).clase is ClaseZip.LIMITE

    def test_d4_pdf_epub_o_varios_cbz_dentro_no_se_interpretan_como_un_tebeo(self, tmp_path):        # D4 (PO, 2026-10-23)
        """Once imágenes y un PDF podrían ser un tebeo con un suplemento: NO se afirma «varios tebeos»; solo se deja de interpretarlo automáticamente como UN
        tebeo. No hace falta abrir esos documentos."""
        casos = {"imagenes_y_pdf": {**paginas(11), "suplemento.pdf": b"%PDF"}, "imagenes_y_epub": {**paginas(11), "extra.epub": b"PK"},
                 "varios_cbz": {"Serie 01.cbz": b"PK", "Serie 02.cbz": b"PK", "Serie 03.cbz": b"PK"}}
        for nombre, entradas in casos.items():
            c = fc.clasificar_zip(zip_de(tmp_path / f"{nombre}.zip", entradas))
            assert c.clase is ClaseZip.ANIDADOS and c.anidados >= 1, nombre
            assert "varios tebeos" not in fc.AVISO_CLASE[c.clase] and "pack" not in fc.AVISO_CLASE[c.clase].lower()
        assert fc.AVISO_CLASE[ClaseZip.ANIDADOS] == ("Contiene otros archivos comprimidos, PDF o EPUB. "
                                                     "ZascArr no lo interpreta automáticamente como un solo tebeo ni separa su contenido.")

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
        (".cbr", {"firma": "zip", "clase": "anidados"}, False),
        (".cbr", {"firma": "zip", "clase": "no_tebeo"}, False),
        (".cbr", {"firma": "rar"}, False),
        (".cbz", {"firma": "zip", "clase": "no_tebeo"}, True),                     # un .cbz declarado y corto sigue dando su primera página
        (".cbz", {"firma": "zip", "clase": "anidados"}, True),
        (".cbz", {"firma": "zip", "clase": "cifrado"}, True),                      # solo cuenta la firma: la clase guardada puede quedar vieja si el fichero se sustituye
        (".cbz", {"firma": "rar"}, False),                                          # un .cbz que es RAR: sin portada
        (".cbr", None, None),                                                       # nada guardado → decide la extensión
        (".cbr", {}, None),
    ])
    def test_puede_dar_portada_sin_tocar_el_disco(self, ext, guardado, esperado):
        assert fc.puede_dar_portada(ext, guardado) is esperado

    def test_los_avisos_dicen_causa_y_accion(self):
        assert fc.aviso_de_formato(".cbz", Firma.RAR) == ("Se llama .cbz, pero por dentro es un .cbr (RAR). "
                                                          "Sigue en tu biblioteca, aunque por ahora ZascArr no puede sacarle la portada.")
        assert fc.aviso_de_formato("", Firma.ZIP) == "Parece un tebeo, pero su nombre no acaba en .cbz, así que ZascArr no lo registra."
        assert "no acaba en .cbr" in fc.aviso_de_formato("", Firma.RAR) and "no acaba en .cb7" in fc.aviso_de_formato("", Firma.SIETE_Z)
        assert "(TAR) que ZascArr no usa" in fc.aviso_de_formato("", Firma.TAR)
        assert fc.aviso_de_extension(".rar") == "Es un archivo .rar: ZascArr no lo registra como tebeo, aunque dentro haya uno."
        assert fc.aviso_de_extension(".cbt") == "ZascArr no usa este formato (CBT), así que no lo registra como tebeo."

    def test_todos_los_textos_siguen_las_reglas_de_ux(self):
        """Revisión de UX (2026-10-23): ≤ 2 frases; sin jerga (entradas, firma, contenedor, nombres de clase); «desde tu ordenador», nunca «fuera de ZascArr»;
        la garantía «no cambia nada» va una sola vez en la cabecera de la sección, no en cada fila; nunca «formato no soportado» a secas."""
        import re
        textos = list(fc.AVISO_CLASE.values()) + [fc.INFO_CBR_ES_ZIP, fc.AVISO_LIMITE_DIRECTORIO]
        for ext in (".cbz", ".zip", ".cbr", ".cb7", ""):
            for firma in (Firma.ZIP, Firma.RAR, Firma.SIETE_Z, Firma.TAR, Firma.OTRO):
                textos.append(fc.aviso_de_formato(ext, firma))
        textos += [fc.aviso_de_extension(e) for e in (".rar", ".7z", ".tar", ".cbt")]
        # «descomprímelo» / «cambia el final del nombre» están prohibidos hasta que exista un recorrido VERIFICADO que recoja el fichero (hoy, tras la
        # adopción inicial, nada registra ficheros nuevos de la biblioteca: ver TestNadaRecogeFicherosNuevosDeLaBiblioteca).
        prohibido = ("entradas", "firma", "contenedor", "PAQUETE", "ANIDADOS", "INVALIDO", "NO_TEBEO", "pack", "fuera de ZascArr", "No se ha cambiado", "no se trata como tal",
                     "formato no soportado", "sin descomprimir", "descomprímelo", "cambia el final", "conviértelo")
        for t in textos:
            assert len(re.findall(r"[.?!](?:\s|$)", t)) <= 2, t
            assert not [p for p in prohibido if p.lower() in t.lower()], t
            assert t.strip() and t[0].isupper(), t


class TestLimitesSinAbrirElZip:
    """Revisión de #325: qué límites hay para LISTAR y procesar muchas entradas. `zipfile.ZipFile()` carga el directorio central entero en memoria
    antes de que se pueda contar: se mira el registro final (EOCD / ZIP64) y un ZIP que DECLARA demasiado ni siquiera se abre."""

    @staticmethod
    def _sin_abrir(monkeypatch):
        def prohibido(*a, **k):
            raise AssertionError("se abrió el ZIP")
        monkeypatch.setattr(zipfile, "ZipFile", prohibido)

    def test_cabecera_de_un_zip_normal(self, tmp_path):
        c = fc.leer_cabecera_zip(zip_de(tmp_path / "a.zip", paginas(12)))
        assert c is not None and c.entradas == 12 and 0 < c.tam_directorio < 4096

    def test_un_registro_final_que_declara_millones_de_entradas_no_se_abre(self, tmp_path, monkeypatch):
        z = zip_de(tmp_path / "m.zip", paginas(12))
        b = bytearray(z.read_bytes())
        i = b.rfind(b"PK\x05\x06")
        b[i + 10:i + 12] = struct.pack("<H", 60000)                   # entradas declaradas en el EOCD
        z.write_bytes(bytes(b))
        self._sin_abrir(monkeypatch)
        assert fc.zip_fuera_de_limite(z) and fc.clasificar_zip(z).clase is ClaseZip.LIMITE

    def test_un_directorio_central_enorme_no_se_abre(self, tmp_path, monkeypatch):
        z = zip_de(tmp_path / "d.zip", paginas(12))
        b = bytearray(z.read_bytes())
        i = b.rfind(b"PK\x05\x06")
        b[i + 12:i + 16] = struct.pack("<I", 400 * 1024 * 1024)       # tamaño del directorio central declarado
        z.write_bytes(bytes(b))
        self._sin_abrir(monkeypatch)
        assert fc.zip_fuera_de_limite(z)

    def test_zip64_con_70000_entradas_se_detecta_sin_abrirlo(self, tmp_path, monkeypatch):
        ruta = tmp_path / "grande.zip"
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for i in range(70_000):
                zf.writestr(f"p{i:05d}.jpg", b"")
        c = fc.leer_cabecera_zip(ruta)
        assert c is not None and c.entradas == 70_000                                 # el registro ampliado, no el EOCD saturado a 0xFFFF
        self._sin_abrir(monkeypatch)
        assert fc.zip_fuera_de_limite(ruta) and fc.clasificar_zip(ruta).clase is ClaseZip.LIMITE

    def test_triage_y_portada_tampoco_abren_un_zip_fuera_de_limite(self, tmp_path, monkeypatch):
        from zascarr.core.importer_triage import triage
        from zascarr.utils.cover import extract_cover_thumbnail
        z = zip_de(tmp_path / "m.cbr", paginas(12))
        b = bytearray(z.read_bytes())
        i = b.rfind(b"PK\x05\x06")
        b[i + 10:i + 12] = struct.pack("<H", 60000)
        z.write_bytes(bytes(b))
        self._sin_abrir(monkeypatch)
        r = triage(z)
        assert r.sha256 and r.formato_contenido["clase"] == "limite" and any("demasiados archivos dentro" in w for w in r.warnings)
        assert extract_cover_thumbnail(z) is None

    def test_un_fichero_que_no_es_zip_no_tiene_cabecera(self, tmp_path):
        (tmp_path / "x").write_bytes(b"hola" * 100)
        assert fc.leer_cabecera_zip(tmp_path / "x") is None and fc.leer_cabecera_zip(tmp_path / "no_existe") is None


class TestMiniaturaAcotadaEnPixeles:

    @staticmethod
    def _png_declarado(ancho: int, alto: int) -> bytes:
        """Un PNG cuya CABECERA declara ancho×alto y cuyos datos no existen: Pillow lo abre (lee solo la cabecera) pero no debe decodificarlo."""
        import zlib

        def chunk(tipo: bytes, datos: bytes) -> bytes:
            return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b""))

    def test_una_imagen_de_cientos_de_megapixeles_no_se_decodifica(self, tmp_path):
        from zascarr.utils.cover import extract_cover_thumbnail
        z = tmp_path / "enorme.cbz"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("001.png", self._png_declarado(20000, 20000))           # 400 Mpx declarados en unos 70 bytes
        assert extract_cover_thumbnail(z) is None

    def test_una_pagina_normal_si_se_decodifica(self, tmp_path):
        from PIL import Image

        from zascarr.utils.cover import extract_cover_thumbnail
        buf = io.BytesIO()
        Image.new("RGB", (3000, 4500), (10, 20, 30)).save(buf, "JPEG")           # 13,5 Mpx: una página de tebeo real
        z = tmp_path / "normal.cbz"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("001.jpg", buf.getvalue())
        assert extract_cover_thumbnail(z) is not None


class TestLaCausaDichaEsLaQueSalto:
    """Condición 1 del PO sobre D3: un ZIP rechazado por el tamaño de su directorio central no puede decir «más de 2000 archivos»."""

    @staticmethod
    def _con_registro(tmp_path, nombre, *, entradas=None, tam_directorio=None, ext=".zip"):
        z = zip_de(tmp_path / f"{nombre}{ext}", paginas(12))
        b = bytearray(z.read_bytes())
        i = b.rfind(b"PK\x05\x06")
        if entradas is not None:
            b[i + 10:i + 12] = struct.pack("<H", entradas)
        if tam_directorio is not None:
            b[i + 12:i + 16] = struct.pack("<I", tam_directorio)
        z.write_bytes(bytes(b))
        return z

    def test_motivo_directorio_con_pocas_entradas(self, tmp_path):
        z = self._con_registro(tmp_path, "d", entradas=500, tam_directorio=5 * 1024 * 1024)       # 500 entradas, pero un índice de 5 MiB
        assert fc.motivo_fuera_de_limite(z) == "directorio"
        c = fc.clasificar_zip(z)
        assert c.clase is ClaseZip.LIMITE and c.motivo_limite == "directorio"
        assert fc.aviso_de_clase(c.clase, c.motivo_limite) == fc.AVISO_LIMITE_DIRECTORIO
        assert "2000" not in fc.AVISO_LIMITE_DIRECTORIO and "demasiados archivos" not in fc.AVISO_LIMITE_DIRECTORIO

    def test_motivo_entradas(self, tmp_path):
        z = self._con_registro(tmp_path, "e", entradas=3000)
        assert fc.motivo_fuera_de_limite(z) == "entradas"
        c = fc.clasificar_zip(z)
        assert fc.aviso_de_clase(c.clase, c.motivo_limite) == fc.AVISO_CLASE[ClaseZip.LIMITE] and "más de 2000" in fc.AVISO_CLASE[ClaseZip.LIMITE]

    def test_si_saltan_los_dos_se_dice_el_del_tamano_del_indice(self, tmp_path):
        assert fc.motivo_fuera_de_limite(self._con_registro(tmp_path, "ambos", entradas=60000, tam_directorio=9 * 1024 * 1024)) == "directorio"

    def test_triage_dice_y_guarda_la_causa_correcta(self, tmp_path):
        from zascarr.core.importer_triage import triage
        d = triage(self._con_registro(tmp_path, "d", entradas=500, tam_directorio=5 * 1024 * 1024, ext=".cbr"))
        e = triage(self._con_registro(tmp_path, "e", entradas=3000, ext=".cbr"))
        assert d.formato_contenido == {"firma": "zip", "contrato": 1, "clase": "limite", "motivo": "directorio"}
        assert e.formato_contenido == {"firma": "zip", "contrato": 1, "clase": "limite", "motivo": "entradas"}
        assert any("índice interno es demasiado grande" in w for w in d.warnings) and not any("más de 2000" in w for w in d.warnings)
        assert any("más de 2000" in w for w in e.warnings) and not any("índice interno" in w for w in e.warnings)

    def test_el_limite_tras_abrir_tambien_dice_entradas(self, tmp_path):
        c = fc.clasificar_zip(zip_de(tmp_path / "l.zip", paginas(30)), max_entradas=10)
        assert c.clase is ClaseZip.LIMITE and c.motivo_limite == "entradas"


class TestCoherenciaConLoQueAbreZipFile:
    """Condición 2 del PO sobre D3: el control previo y el lector que abre el ZIP deben interpretar el MISMO registro final; si no, se eludiría haciendo que
    ambos vean registros distintos (firmas falsas en el comentario, localizador ZIP64…). Se comprueba contra lo que `ZipFile` realmente usa."""

    @staticmethod
    def _eocd_falso(entradas: int, tam: int) -> bytes:
        return b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, entradas, entradas, tam, 0, 0)

    @staticmethod
    def _lo_que_usa_zipfile(ruta, monkeypatch):
        vistos = []
        original = zipfile._EndRecData

        def espia(fp):
            r = original(fp)
            vistos.append(r)
            return r
        monkeypatch.setattr(zipfile, "_EndRecData", espia)
        with contextlib.suppress(zipfile.BadZipFile, OSError):
            zipfile.ZipFile(ruta).close()
        monkeypatch.setattr(zipfile, "_EndRecData", original)
        return vistos

    def _variantes(self, tmp_path):
        base = zip_de(tmp_path / "base.zip", paginas(12)).read_bytes()
        eocd = base.rfind(b"PK\x05\x06")
        v = {"normal": base}
        # comentario con una firma EOCD falsa al final: `ZipFile` toma la ÚLTIMA firma
        comentario = b"nota " + self._eocd_falso(60000, 90 * 1024 * 1024)
        real = bytearray(base)
        real[eocd + 20:eocd + 22] = struct.pack("<H", len(comentario))
        v["firma_falsa_en_el_comentario"] = bytes(real) + comentario
        # localizador + registro ZIP64 que el EOCD normal no refleja (EOCD con 12 entradas; el ZIP64 dice 60000)
        cd_tam = struct.unpack_from("<I", base, eocd + 12)[0]
        cd_off = struct.unpack_from("<I", base, eocd + 16)[0]
        z64 = b"PK\x06\x06" + struct.pack("<QHHIIQQQQ", 44, 45, 45, 0, 0, 60000, 60000, cd_tam, cd_off)
        loc = b"PK\x06\x07" + struct.pack("<IQI", 0, eocd + len(z64) - len(z64), 1)
        v["zip64_no_reflejado_por_el_eocd"] = base[:eocd] + z64 + loc + base[eocd:]
        # registro final truncado
        v["eocd_truncado"] = base[:eocd + 10]
        # basura al final del fichero tras el registro (no es comentario)
        v["basura_final"] = base + b"\0" * 300
        return v

    def test_el_control_ve_lo_mismo_que_zipfile(self, tmp_path, monkeypatch):
        for nombre, datos in self._variantes(tmp_path).items():
            ruta = tmp_path / f"{nombre}.zip"
            ruta.write_bytes(datos)
            nuestro = fc.leer_cabecera_zip(ruta)
            vistos = self._lo_que_usa_zipfile(ruta, monkeypatch)
            if vistos and vistos[0]:
                esperado = (vistos[0][zipfile._ECD_ENTRIES_TOTAL], vistos[0][zipfile._ECD_SIZE])
                assert nuestro is not None and (nuestro.entradas, nuestro.tam_directorio) == esperado, nombre
            else:
                assert nuestro is None, nombre                      # ZipFile no encontró registro: nosotros tampoco inventamos uno

    def test_una_firma_falsa_en_el_comentario_no_elude_el_control(self, tmp_path):
        ruta = tmp_path / "f.zip"
        ruta.write_bytes(self._variantes(tmp_path)["firma_falsa_en_el_comentario"])
        assert fc.zip_fuera_de_limite(ruta)                       # la ve igual que ZipFile: 60000 entradas y 90 MiB de índice

    def test_un_zip64_que_el_eocd_no_refleja_tampoco_la_elude(self, tmp_path):
        ruta = tmp_path / "z.zip"
        ruta.write_bytes(self._variantes(tmp_path)["zip64_no_reflejado_por_el_eocd"])
        c = fc.leer_cabecera_zip(ruta)
        assert c is not None and c.entradas == 60000 and fc.motivo_fuera_de_limite(ruta) == "entradas"

    def test_un_indice_real_enorme_con_un_registro_que_declara_pocas_entradas_se_rechaza_sin_abrir(self, tmp_path, monkeypatch):
        """La carga de memoria de `ZipFile` es proporcional al TAMAÑO del índice (lo recorre por bytes, no por el nº de entradas declarado)."""
        ruta = tmp_path / "indice.zip"
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as zf:
            for i in range(30_000):
                zf.writestr(f"p{i:05d}.jpg", b"")
        b = bytearray(ruta.read_bytes())
        i = b.rfind(b"PK\x05\x06")
        b[i + 10:i + 12] = struct.pack("<H", 5)                       # el registro dice 5 entradas; el índice real mide ~1,6 MiB
        ruta.write_bytes(bytes(b))
        c = fc.leer_cabecera_zip(ruta)
        assert c.entradas == 5 and c.tam_directorio > fc.MAX_DIRECTORIO_CENTRAL
        monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: (_ for _ in ()).throw(AssertionError("se abrió el ZIP")))
        assert fc.motivo_fuera_de_limite(ruta) == "directorio" and fc.clasificar_zip(ruta).motivo_limite == "directorio"

    def test_lo_que_se_acepta_se_abre_con_poca_memoria(self, tmp_path):
        import tracemalloc
        ruta = zip_de(tmp_path / "ok.zip", {f"p{i:04d}.jpg": b"x" for i in range(fc.MAX_ENTRADAS)})
        assert fc.motivo_fuera_de_limite(ruta) is None            # justo en el límite de entradas
        tracemalloc.start()
        with zipfile.ZipFile(ruta) as zf:
            assert len(zf.infolist()) == fc.MAX_ENTRADAS
        pico = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert pico < 5 * 1024 * 1024                              # medido: ~1 MiB con 2000 entradas

    def test_el_lector_privado_de_la_biblioteca_estandar_sigue_existiendo(self):
        """Si una versión de Python lo renombrara, el módulo ya no se importaría (ruidoso); esta prueba lo deja dicho."""
        assert callable(zipfile._EndRecData) and zipfile._ECD_ENTRIES_TOTAL == 4 and zipfile._ECD_SIZE == 5
