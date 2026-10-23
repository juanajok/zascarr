# ruff: noqa: E501
"""#307 — formato por contenido: cómo lo usan `triage`, la portada, el tagger y el relleno de los ya registrados (T5, T6, T9, T10, T11 del contrato
`docs/design/contrato-307-formato-por-contenido.md`). Sintético y sin base de datos real (el relleno usa una sesión falsa)."""
from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from zascarr.core.importer_triage import triage
from zascarr.models import FileFormat
from zascarr.services.importer import Importer, _reenlazar_fila
from zascarr.services.tagger import SALTADO, TaggerService
from zascarr.utils.cover import extract_cover_thumbnail, puede_tener_portada

COMICINFO = b'<?xml version="1.0"?><ComicInfo><Series>Prueba</Series><Number>3</Number></ComicInfo>'
RAR5 = b"Rar!\x1a\x07\x01\x00" + b"\0" * 64


def _jpeg(i: int = 0) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (320, 480), (i * 17 % 255, 90, 160)).save(b, "JPEG")
    return b.getvalue()


def zip_de(ruta: Path, paginas: int = 12, comicinfo: bool = True, extra: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        if comicinfo:
            z.writestr("ComicInfo.xml", COMICINFO)
        for i in range(paginas):
            z.writestr(f"p{i:03d}.jpg", _jpeg(i))
        for n, d in (extra or {}).items():
            z.writestr(n, d)
    return ruta


def huella(p: Path) -> tuple[str, int]:
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


class TestTriageDeUnCbrQueEsUnZip:                                                          # T5

    def test_se_lee_comicinfo_anchura_y_hash_sin_modificar_el_fichero(self, tmp_path):
        f = zip_de(tmp_path / "Serie 03.cbr")
        antes = huella(f)
        r = triage(f)
        assert r.comic_info is not None and r.comic_info.series == "Prueba" and r.comic_info.number == "3"
        assert r.width_px == 320 and r.sha256 == antes[0]
        assert r.file_format == "cbr"                                                         # la extensión DECLARADA no cambia
        assert r.formato_contenido == {"firma": "zip", "contrato": 1, "clase": "tebeo"}
        assert not any("solo por filename" in w for w in r.warnings)
        assert huella(f) == antes

    def test_un_cbr_zip_con_otros_comprimidos_dentro_no_se_trata_como_tebeo(self, tmp_path):
        f = zip_de(tmp_path / "Pack.cbr", extra={"Extras/otro.cbz": b"PK"})
        r = triage(f)
        assert r.comic_info is None and r.width_px is None and r.sha256
        assert r.formato_contenido["clase"] == "anidados" and any("Contiene otros archivos comprimidos, PDF o EPUB" in w for w in r.warnings)

    def test_un_cbr_zip_con_pocas_imagenes_no_es_un_tebeo_comprobado(self, tmp_path):
        r = triage(zip_de(tmp_path / "Corto.cbr", paginas=3))
        assert r.comic_info is None and r.formato_contenido["clase"] == "no_tebeo" and any("no parece un tebeo" in w for w in r.warnings)

    def test_un_cbz_declarado_y_corto_sigue_leyendose_como_siempre(self, tmp_path):
        """El usuario lo declara tebeo: la clase no bloquea la lectura (sí los topes). Evita perder el ComicInfo de un especial de 8 páginas."""
        r = triage(zip_de(tmp_path / "Especial.cbz", paginas=8))
        assert r.comic_info is not None and r.width_px == 320 and r.formato_contenido["clase"] == "no_tebeo"

    def test_un_cbz_declarado_no_recibe_aviso_por_su_clase(self, tmp_path):
        """Regresión (vista en `test_naming_core`): un especial de 8 páginas declarado .cbz se lee como siempre y sin avisos."""
        r = triage(zip_de(tmp_path / "Especial.cbz", paginas=1))
        assert r.warnings == [] and r.formato_contenido["clase"] == "no_tebeo"

    def test_un_cbz_que_no_es_ningun_contenedor_no_recibe_hash(self, tmp_path):
        """Regresión: un .cbz roto o una descarga incompleta no se hashea (el hash sugeriría una identidad de contenido que no existe); un RAR
        con otro nombre, que es un contenedor válido, sí."""
        roto = tmp_path / "roto.cbz"
        roto.write_bytes(b"esto no es un zip")
        r = triage(roto)
        assert r.sha256 is None and any("zip ilegible" in w for w in r.warnings)

    def test_un_cbr_rar_de_verdad_sigue_solo_hasheado(self, tmp_path):
        f = tmp_path / "Real.cbr"
        f.write_bytes(RAR5)
        r = triage(f)
        assert r.sha256 and r.comic_info is None and r.formato_contenido == {"firma": "rar", "contrato": 1}
        assert any("solo por filename" in w for w in r.warnings) and not any("Se llama" in w for w in r.warnings)

    def test_un_cbz_que_es_un_rar_se_hashea_y_se_avisa_con_causa_y_accion(self, tmp_path):
        f = tmp_path / "Mentira.cbz"
        f.write_bytes(RAR5)
        r = triage(f)
        assert r.sha256 and r.formato_contenido["firma"] == "rar"
        assert any("Se llama .cbz, pero por dentro es un .cbr (RAR)" in w and "no puede sacarle la portada" in w for w in r.warnings)

    def test_un_zip_sin_extension_no_se_lee_y_se_avisa(self, tmp_path):
        f = zip_de(tmp_path / "sin_extension")
        r = triage(f)                                                                         # D1: no se registra; la auditoría lo avisa
        assert r.comic_info is None and r.sha256 and any("no acaba en .cbz, así que ZascArr no lo registra" in w for w in r.warnings)

    def test_un_zip_corrupto_con_extension_cbr_no_lanza_y_no_tiene_hash(self, tmp_path):
        f = tmp_path / "Roto.cbr"
        f.write_bytes(b"PK\x03\x04 esto no es un zip de verdad")
        r = triage(f)
        assert r.sha256 is None and r.formato_contenido["clase"] == "invalido" and any("zip ilegible" in w for w in r.warnings)


class TestPortada:                                                                          # T9

    def test_un_cbr_zip_da_portada_con_o_sin_formato_guardado(self, tmp_path):
        f = zip_de(tmp_path / "Serie 03.cbr")
        guardado = {"firma": "zip", "clase": "tebeo", "contrato": 1}
        for fc in (guardado, None):                                                           # con la base rellena y con la fila aún sin rellenar
            data, tipo = extract_cover_thumbnail(f, fc)
            assert tipo == "image/jpeg" and Image.open(io.BytesIO(data)).width <= 240

    def test_un_cbr_zip_con_anidados_o_un_rar_no_dan_portada(self, tmp_path):
        paquete = zip_de(tmp_path / "Pack.cbr", extra={"x/y.cbz": b"PK"})
        rar = tmp_path / "R.cbr"
        rar.write_bytes(RAR5)
        assert extract_cover_thumbnail(paquete) is None and extract_cover_thumbnail(rar) is None
        assert extract_cover_thumbnail(paquete, {"firma": "zip", "clase": "anidados"}) is None

    def test_un_cbz_que_es_un_rar_no_da_portada_y_no_explota(self, tmp_path):
        f = tmp_path / "Mentira.cbz"
        f.write_bytes(RAR5)
        assert extract_cover_thumbnail(f) is None and extract_cover_thumbnail(f, {"firma": "rar"}) is None

    def test_puede_tener_portada_no_toca_el_disco_ni_abre_nada(self, monkeypatch):
        import zipfile as zipmod
        monkeypatch.setattr(zipmod, "ZipFile", lambda *a, **k: (_ for _ in ()).throw(AssertionError("abrió el zip")))
        monkeypatch.setattr(Path, "exists", lambda self: (_ for _ in ()).throw(AssertionError("tocó el disco")))
        assert puede_tener_portada("/no/existe/S 03.cbr", {"firma": "zip", "clase": "tebeo"}) is True      # guardado: lo dice la base
        assert puede_tener_portada("/no/existe/S 03.cbr", {"firma": "rar"}) is False
        assert puede_tener_portada("/no/existe/S 03.cbr") is False                                          # sin nada guardado: la extensión, como hoy
        assert puede_tener_portada("/no/existe/S 03.cbz") is True

    def test_una_primera_pagina_enorme_no_se_lee_sin_tope(self, tmp_path, monkeypatch):
        """Hallazgo de #307: `extract_cover_thumbnail` leía `zf.read(pages[0])` sin ningún tope."""
        from zascarr.core import formato_contenedor
        f = zip_de(tmp_path / "Grande.cbz")
        monkeypatch.setattr(formato_contenedor, "MAX_ENTRADA_LEIDA", 100)
        assert extract_cover_thumbnail(f) is None


class TestElTaggerNoEscribeEnUnZipQueSeLlamaCbr:                                           # T6

    @pytest.mark.asyncio
    async def test_se_salta_porque_file_format_es_la_extension_declarada(self, tmp_path):
        f = zip_de(tmp_path / "Serie 03.cbr")
        antes = huella(f)
        fila = SimpleNamespace(id=uuid4(), file_name=f.name, file_format=FileFormat.CBR, is_missing=False,
                               metadata_={"formato_contenido": {"firma": "zip", "clase": "tebeo", "contrato": 1}})
        r = await TaggerService.__new__(TaggerService)._ejecutar_con(fila, None, f, dry_run=False, solo_rellenar=False, reconciliar_todo=False)
        assert r.accion == SALTADO and "solo CBZ" in r.motivo
        assert huella(f) == antes


class _SesionFalsa:
    """Lo mínimo de una AsyncSession para `scan_and_import` con un listado vacío."""

    def __init__(self, filas):
        self.filas = filas

    async def execute(self, _stmt):
        return self

    def scalars(self):
        return self

    def all(self):
        return list(self.filas)

    async def flush(self):
        return None


class TestElRellenoNoSeLanzaSolo:                                                           # D5 (PO, 2026-10-23): a demanda

    @pytest.mark.asyncio
    async def test_scan_and_import_no_llama_al_relleno(self, tmp_path, monkeypatch):
        """El relleno de `formato_contenido` es una operación explícita (CLI): ni `scan_and_import` ni ningún ciclo la lanzan."""
        from zascarr.services import importer as mod
        imp = Importer.__new__(Importer)
        imp._db = _SesionFalsa([])
        imp._library = tmp_path / "no_hay_biblioteca"
        imp._scan_dirs = []
        monkeypatch.setattr(mod, "listar_comics", lambda *a, **k: [])
        monkeypatch.setattr(imp, "_persist_run", _async_nada)
        monkeypatch.setattr(imp, "rellenar_formato_contenido", _async_error)          # si el ciclo lo llamara, fallaría
        informe = await imp.scan_and_import()
        assert informe.finished_at is not None and not informe.errors

    def test_ningun_modulo_de_ciclo_lo_referencia(self):
        """Ni `main.py` ni los bucles: solo el CLI (y el propio servicio) conocen `rellenar_formato_contenido`."""
        raiz = Path(__file__).resolve().parents[1] / "src" / "zascarr"
        usuarios = sorted(str(p.relative_to(raiz)) for p in raiz.rglob("*.py") if "rellenar_formato_contenido" in p.read_text(encoding="utf-8"))
        assert usuarios == ["cli/rellenar_formato.py", "services/importer.py"]


async def _async_nada(*_a, **_k):
    return None


async def _async_error(*_a, **_k):
    raise RuntimeError("el ciclo no debe llamar al relleno")


class TestReenlazarConservaElFormato:

    @pytest.mark.asyncio
    async def test_actualiza_el_formato_real_sin_perder_los_metadatos(self, tmp_path):
        dest = zip_de(tmp_path / "Nuevo.cbr")
        fila = SimpleNamespace(file_path="/viejo", file_name="viejo", file_size_bytes=0, sha256_hash=None, is_missing=True, missing_since=1,
                               imported_at=None, original_sha256=None, metadata_={"match_status": "matched", "formato_contenido": {"firma": "rar"}})
        tr = triage(dest)
        await _reenlazar_fila(fila, tr, dest)
        assert fila.metadata_["formato_contenido"] == {"firma": "zip", "contrato": 1, "clase": "tebeo"}
        assert fila.metadata_["match_status"] == "matched" and fila.is_missing is False and fila.sha256_hash == tr.sha256


class TestTarjetaDePendientes:                                                              # U12 + #307

    def test_la_tarjeta_usa_el_formato_guardado_para_decidir_si_hay_portada(self):
        from zascarr.web.pendientes import _card
        base = dict(file_name="Serie 03.cbr", file_path="/x/Serie 03.cbr")
        cbr_zip = SimpleNamespace(**base, metadata_={"candidates": [], "formato_contenido": {"firma": "zip", "clase": "tebeo"}})
        cbr_rar = SimpleNamespace(**base, metadata_={"candidates": [], "formato_contenido": {"firma": "rar"}})
        sin = SimpleNamespace(**base, metadata_={"candidates": []})
        assert _card(cbr_zip)["con_portada"] is True and _card(cbr_rar)["con_portada"] is False and _card(sin)["con_portada"] is False


class TestNadaRecogeFicherosNuevosDeLaBiblioteca:
    """Hallazgo de la revisión de #325, comprobado con ficheros sintéticos: por eso los avisos NO dicen «descomprímelo» ni «cambia el final del
    nombre». Un fichero que aparece DENTRO de la biblioteca después de la adopción inicial no lo registra nada automático."""

    def test_el_importador_solo_recorre_las_carpetas_de_descarga_no_la_biblioteca(self, tmp_path, monkeypatch):
        from zascarr.services import importer as mod
        from zascarr.utils.fs import listar_comics
        biblioteca, descargas = tmp_path / "biblioteca", tmp_path / "descargas"
        (biblioteca / "Pack").mkdir(parents=True)
        descargas.mkdir()
        zip_de(biblioteca / "Pack" / "Numero 01.cbz")                         # lo que saldría de descomprimir un pack en la biblioteca
        zip_de(descargas / "Numero 02.cbz")
        monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(
            library_path=biblioteca, transmission_download_dir=str(tmp_path / "t"), amule_incoming_dir=str(tmp_path / "a"), downloads_path=descargas))
        imp = Importer(db=None)
        vistos = {p.name for p in listar_comics(imp._scan_dirs, mod.COMIC_EXTS)}
        assert vistos == {"Numero 02.cbz"}

    @pytest.mark.asyncio
    async def test_con_la_adopcion_hecha_registrar_la_biblioteca_ya_no_se_ofrece(self, tmp_path, monkeypatch):
        from zascarr.services import library_adopter as mod
        from zascarr.services.runtime_settings import RuntimeSettingsService

        async def hecha(_self, clave, *a, **k):
            return clave == mod._MARCADOR_HECHO
        monkeypatch.setattr(RuntimeSettingsService, "get_flag", hecha)
        monkeypatch.setattr(mod, "get_settings", lambda: SimpleNamespace(library_path=tmp_path))
        adopter = mod.LibraryAdopter(db=None)
        assert await adopter.estado() is mod.EstadoAdopcion.HECHA and await adopter.puede_registrar() is False
