# ruff: noqa: E501
"""#478: piezas puras de la conversión (manifiesto, nombres, límite, ZIP_STORED) y token."""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.services.conversion_cbr import (
    MAX_CBR_BYTES,
    ConversionBloqueadaError,
    MotivoConversion,
    analizar,
    construir_cbz,
)
from zascarr.services.tokens_revision import (
    MAX_TOKEN_CONVERSION,
    ConversionFirmada,
    crear_token_conversion,
    verificar_token_conversion,
)


class _Entrada:
    def __init__(self, nombre, datos, *, indice=0, directorio=False):
        self.indice = indice
        self.nombre = nombre
        self.tamano = len(datos)
        self.crc32 = __import__("zlib").crc32(datos) & 0xFFFFFFFF
        self.es_directorio = directorio
        self.cifrada = False
        self._datos = datos


class _Lector:
    def __init__(self, entradas, *, datos_alternativos=None):
        self.entradas = entradas
        self.datos = {e.nombre: e._datos for e in entradas}
        self.datos_alternativos = datos_alternativos or {}

    def disponible(self):
        return True

    def listar(self, _ruta, *, temporal):
        return SimpleNamespace(entradas=tuple(self.entradas))

    def leer_entrada(self, _ruta, entrada, _tope, *, temporal):
        # Imita a `unar`: reutilizar la misma salida en dos entradas daría FileExistsError.
        usadas = getattr(self, "_temporales", None)
        if usadas is None:
            usadas = self._temporales = set()
        if str(temporal) in usadas:
            raise FileExistsError(str(temporal))
        usadas.add(str(temporal))
        return self.datos_alternativos.get(entrada.nombre, self.datos[entrada.nombre])


def _cbr(tmp_path: Path, contenido=b"RAR-falso"):
    ruta = tmp_path / "Tebeo 01.cbr"
    ruta.write_bytes(contenido)
    return ruta


def test_analizar_bloquea_cbr_demasiado_grande_sin_leerlo(tmp_path):
    ruta = _cbr(tmp_path)
    with ruta.open("r+b") as fh:
        fh.truncate(MAX_CBR_BYTES + 1)
    with pytest.raises(ConversionBloqueadaError) as exc:
        analizar(ruta, lector=_Lector([]))
    assert exc.value.motivo is MotivoConversion.DEMASIADO_GRANDE
    assert "150" in exc.value.mensaje


def test_analizar_rechaza_nombre_inseguro(tmp_path):
    ruta = _cbr(tmp_path)
    with pytest.raises(ConversionBloqueadaError) as exc:
        analizar(ruta, lector=_Lector([_Entrada("../fuera.jpg", b"x")]))
    assert exc.value.motivo is MotivoConversion.NOMBRE_NO_SEGURO


def test_analizar_rechaza_entrada_gigante_y_doble_comicinfo(tmp_path):
    ruta = _cbr(tmp_path)
    with pytest.raises(ConversionBloqueadaError) as exc:
        analizar(ruta, lector=_Lector([_Entrada("a.jpg", b"x" * (33 * 1024 * 1024))]))
    assert exc.value.motivo is MotivoConversion.DEMASIADO_GRANDE
    with pytest.raises(ConversionBloqueadaError) as exc:
        analizar(ruta, lector=_Lector([_Entrada("ComicInfo.xml", b"a"),
                                       _Entrada("comicinfo.xml", b"b")]))
    assert exc.value.motivo is MotivoConversion.COMICINFO_DUPLICADO


def test_d5_un_cbr_que_es_zip_se_renombra_sin_recomprimir(tmp_path):
    ruta = tmp_path / "Zipeado.cbr"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("001.jpg", b"pagina")
    assert analizar(ruta, lector=_Lector([])).metodo == "renombrar_zip"


def test_construir_cbz_es_stored_y_manifiesto_coincide(tmp_path):
    ruta = _cbr(tmp_path)
    entradas = [_Entrada("001.jpg", b"pagina uno", indice=0),
                _Entrada("ComicInfo.xml", b"<ComicInfo/>", indice=1)]
    destino = tmp_path / "nuevo.cbz"
    construccion = construir_cbz(ruta, destino, lector=_Lector(entradas))
    assert [m.nombre for m in construccion.manifiesto] == ["001.jpg", "ComicInfo.xml"]
    with zipfile.ZipFile(destino) as zf:
        assert [i.filename for i in zf.infolist()] == ["001.jpg", "ComicInfo.xml"]
        assert all(i.compress_type == zipfile.ZIP_STORED for i in zf.infolist())
        assert zf.testzip() is None
    assert construccion.sha256 == hashlib.sha256(destino.read_bytes()).hexdigest()
    assert construccion.tamano == destino.stat().st_size


def test_si_el_lector_devuelve_otros_bytes_no_se_publica(tmp_path):
    ruta = _cbr(tmp_path)
    lector = _Lector([_Entrada("001.jpg", b"bueno")], datos_alternativos={"001.jpg": b"otro"})
    with pytest.raises(ConversionBloqueadaError) as exc:
        construir_cbz(ruta, tmp_path / "x.cbz", lector=lector)
    assert exc.value.motivo is MotivoConversion.ILEGIBLE


def test_token_de_conversion_ligado_al_archivo():
    secret = "x" * 32
    file_id, operacion = str(uuid4()), str(uuid4())
    f = ConversionFirmada(file_id=file_id, operacion=operacion, ruta="/media/library/a.cbr",
                          tamano=10, mtime_ns=20, sha256="a" * 64,
                          metodo="recomprimir", accion="convertir")
    token = crear_token_conversion(f, secret, ahora=1000.0)
    assert len(token) <= MAX_TOKEN_CONVERSION
    v = verificar_token_conversion(token, secret, ahora=1001.0)
    assert v is not None and v.file_id == file_id and v.accion == "convertir"
    assert verificar_token_conversion(token, secret, ahora=1001.0, ignorar_caducidad=True) is not None
    assert verificar_token_conversion(token, "y" * 32, ahora=1001.0) is None
    assert verificar_token_conversion(token, secret, ahora=10**9) is None


def test_unar_caido_o_cifrado_bloquea_con_motivo(tmp_path):
    from zascarr.models import MotivoRar
    from zascarr.utils.lector_rar import ErrorRar

    class _Roto:
        def disponible(self):
            return True
        def listar(self, *_a, **_k):
            raise ErrorRar(MotivoRar.CIFRADO)

    with pytest.raises(ConversionBloqueadaError) as exc:
        analizar(_cbr(tmp_path), lector=_Roto())
    assert exc.value.motivo is MotivoConversion.CIFRADO

    class _FallaExtraccion(_Lector):
        def leer_entrada(self, *_a, **_k):
            raise ErrorRar(MotivoRar.ILEGIBLE)

    ent = _Entrada("001.jpg", b"x")
    with pytest.raises(ConversionBloqueadaError) as exc:
        construir_cbz(_cbr(tmp_path), tmp_path / "x.cbz", lector=_FallaExtraccion([ent]))
    assert exc.value.motivo is MotivoConversion.ILEGIBLE


def test_el_recorrido_no_entra_en_la_cuarentena_zascarr(tmp_path):
    from zascarr.utils.fs import listar_comics, recorrer_comics

    (tmp_path / "serie").mkdir()
    real = tmp_path / "serie" / "01.cbr"
    real.write_bytes(b"x")
    cuarentena = tmp_path / ".zascarr" / "originales" / "abc" / "op"
    cuarentena.mkdir(parents=True)
    (cuarentena / "viejo.cbr").write_bytes(b"y")
    (tmp_path / ".zascarr" / "diario").mkdir()
    assert listar_comics([tmp_path], (".cbr", ".cbz")) == [real]
    assert recorrer_comics([tmp_path], (".cbr", ".cbz")).archivos == [real]


def test_d5_no_publica_un_zip_danado(tmp_path):
    ruta = tmp_path / "Roto.cbr"
    ruta.write_bytes(b"PK\x03\x04" + b"basura" * 20)
    with pytest.raises(ConversionBloqueadaError):
        analizar(ruta, lector=_Lector([]))


def test_cada_entrada_tiene_su_carpeta_temporal(tmp_path):
    ruta = _cbr(tmp_path)
    lector = _Lector([_Entrada("001.jpg", b"uno"), _Entrada("002.jpg", b"dos", indice=1)])
    construccion = construir_cbz(ruta, tmp_path / "dos.cbz", lector=lector)
    assert [m.nombre for m in construccion.manifiesto] == ["001.jpg", "002.jpg"]
    assert len(lector._temporales) == 2


@pytest.mark.skipif(not __import__("zascarr.utils.lector_rar", fromlist=["disponible"]).disponible(),
                    reason="requiere unar/lsar reales (no están en este entorno)")
@pytest.mark.parametrize("fixture", ["minimo_rar4.cbr", "minimo_rar5.cbr"])
def test_rar_real_con_dos_entradas(tmp_path, fixture):
    """Regresión real del fallo multi-entrada: dos páginas, dos carpetas temporales."""
    from zascarr.utils import lector_rar

    origen = Path(__file__).parent / "fixtures" / "rar" / fixture
    destino = tmp_path / f"{fixture}.cbz"
    construccion = construir_cbz(origen, destino, lector=lector_rar)
    assert len(construccion.manifiesto) >= 2
    with zipfile.ZipFile(destino) as zf:
        assert zf.testzip() is None


def test_el_cli_expone_reconciliar_y_vaciar():
    from zascarr.cli.originales import _parser

    assert _parser().parse_args(["reconciliar"]).accion == "reconciliar"
    assert _parser().parse_args(["vaciar", "--lote", "5"]).lote == 5
