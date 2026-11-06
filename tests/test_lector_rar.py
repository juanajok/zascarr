"""#418 (BL-PORT3) commit 1: el lector de RAR por subproceso, con `lsar`/`unar` FALSOS.

Cubre AC-02, 03, 05, 08..13 de la spec. No necesita RAR ni la herramienta real (esa parte, con
fixtures, va en `test_lector_rar_real.py`). Cada prueba nombra el mecanismo que protege.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from tests._rar_falso import entrada, instalar
from zascarr.models import MotivoRar
from zascarr.utils import lector_rar
from zascarr.utils.lector_rar import ErrorRar, carpeta_temporal, disponible, leer_entrada, listar

JPEG = b"\xff\xd8" + b"0123456789" * 20 + b"\xff\xd9"


def _a_entrada(e):
    """`entrada()` de los falsos da el dict que imprimiría `lsar`; el lector lo lee igual que él."""
    return lector_rar._entrada_de(e, e["XADIndex"])


@pytest.fixture
def falso(tmp_path, monkeypatch):
    return instalar(tmp_path / "bin", monkeypatch)


@pytest.fixture
def rar(tmp_path):
    f = tmp_path / "serie" / "n1.cbr"
    f.parent.mkdir()
    f.write_bytes(b"Rar!\x1a\x07\x00" + b"x" * 100)
    return f


@pytest.fixture
def base(tmp_path):
    return tmp_path / "covers" / ".rar"


def _listar(rar: Path, base: Path):
    with carpeta_temporal(base) as tmp:
        return listar(rar, temporal=tmp)


def _leer(rar: Path, base: Path, e, tope: int = 32 * 1024 * 1024, **kw):
    with carpeta_temporal(base) as tmp:
        return leer_entrada(rar, _a_entrada(e), tope, temporal=tmp, **kw)


# ── disponibilidad (FR-13, FR-25) ─────────────────────────────────────────────────────────────────
def test_disponible_segun_el_path(falso, monkeypatch, tmp_path):
    assert disponible() is True
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    monkeypatch.setenv("PATH", str(vacio))
    assert disponible() is False


def test_herramienta_ausente_es_un_motivo_de_entorno_no_un_fallo_del_archivo(monkeypatch, tmp_path, rar, base):
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    monkeypatch.setenv("PATH", str(vacio))
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.HERRAMIENTA_AUSENTE


# ── listado: topes (AC-02) y vacío sospechoso (AC-03) ─────────────────────────────────────────────
def test_listado_ok_trae_indice_nombre_tamano_y_crc(falso, rar, base):
    falso.listado([entrada(0, "ComicInfo.xml", 10), entrada(1, "01.jpg", 123, 0xDEADBEEF)])
    lis = _listar(rar, base)
    assert [(e.indice, e.nombre, e.tamano, e.crc32) for e in lis.entradas] == [
        (0, "ComicInfo.xml", 10, None), (1, "01.jpg", 123, 0xDEADBEEF)]


def test_demasiadas_entradas_no_extrae_nada(falso, rar, base):
    falso.listado([entrada(i, f"{i}.jpg", 1) for i in range(lector_rar.RAR_MAX_ENTRADAS + 1)])
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE
    assert not [x for x in falso.llamadas() if x.startswith("unar")]


def test_bytes_declarados_por_encima_del_tope(falso, rar, base):
    falso.listado([entrada(0, "a.jpg", lector_rar.RAR_MAX_BYTES_DECLARADOS + 1)])
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE


def test_salida_del_listado_mayor_que_el_tope_se_corta(falso, rar, base):
    falso.modo(lsar="enorme")
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE


def test_listado_vacio_en_un_archivo_grande_es_ilegible_no_sin_imagenes(falso, tmp_path, base):
    """`lsar` lista un truncado con código 0 (#308): vacío + archivo de 5 MiB = sospechoso."""
    grande = tmp_path / "g.cbr"
    grande.write_bytes(b"Rar!\x1a\x07\x00" + b"\0" * (5 * 1024 * 1024))
    falso.listado([])
    with pytest.raises(ErrorRar) as exc:
        _listar(grande, base)
    assert exc.value.motivo is MotivoRar.ILEGIBLE


def test_listado_vacio_en_un_archivo_pequeno_no_es_error(falso, rar, base):
    falso.listado([])
    assert _listar(rar, base).entradas == ()


def test_listado_que_no_es_json_es_ilegible(falso, rar, base):
    falso.modo(lsar="basura")
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.ILEGIBLE


@pytest.mark.parametrize("mensaje,motivo", [
    ("This archive requires a password", MotivoRar.CIFRADO),
    ("next volume is missing", MotivoRar.MULTIVOLUMEN),
    ("algo raro", MotivoRar.ILEGIBLE),
    ("", MotivoRar.ILEGIBLE),
])
def test_codigo_distinto_de_cero_se_mapea_a_un_motivo_de_dominio(falso, rar, base, mensaje, motivo):
    falso.modo(lsar="rc1", mensaje=mensaje)
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is motivo


def test_entrada_cifrada_en_el_listado(falso, rar, base):
    falso.listado([entrada(0, "01.jpg", 10, cifrada=True)])
    with pytest.raises(ErrorRar) as exc:
        _listar(rar, base)
    assert exc.value.motivo is MotivoRar.CIFRADO


# ── extracción: verificación (AC-05) ──────────────────────────────────────────────────────────────
def test_extraccion_correcta_devuelve_los_bytes(falso, rar, base):
    crc = falso.contenido(JPEG)
    assert _leer(rar, base, entrada(3, "01.jpg", len(JPEG), crc)) == JPEG


def test_se_extrae_por_indice_sin_comodines(falso, rar, base):
    """Los nombres llevan corchetes que `unar` toma por comodines: se pasa el ÍNDICE."""
    crc = falso.contenido(JPEG)
    _leer(rar, base, entrada(7, "[Fansub] 00.jpg", len(JPEG), crc))
    linea = [x for x in falso.llamadas() if x.startswith("unar")][0]
    assert linea.split()[-1] == "7"
    assert "[Fansub]" not in linea
    assert " -i " in linea


@pytest.mark.parametrize("modo", ["nada", "otro_tamano", "crc", "enlace", "dos"])
def test_codigo_cero_no_prueba_nada(falso, rar, base, modo):
    """Mutación: aceptar `rc 0` sin verificar tamaño, CRC, enlaces ni nº de ficheros."""
    crc = falso.contenido(JPEG)
    falso.modo(unar=modo)
    with pytest.raises(ErrorRar) as exc:
        _leer(rar, base, entrada(0, "01.jpg", len(JPEG), crc))
    assert exc.value.motivo is MotivoRar.ILEGIBLE


def test_sin_crc_en_el_listado_se_verifica_solo_el_tamano(falso, rar, base):
    falso.contenido(JPEG)
    assert _leer(rar, base, entrada(0, "01.jpg", len(JPEG), None)) == JPEG


def test_entrada_mayor_que_el_tope_no_se_extrae(falso, rar, base):
    falso.contenido(JPEG)
    with pytest.raises(ErrorRar) as exc:
        _leer(rar, base, entrada(0, "01.jpg", 1000), tope=999)
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE
    assert not [x for x in falso.llamadas() if x.startswith("unar")]


def test_un_directorio_no_se_extrae(falso, rar, base):
    with pytest.raises(ErrorRar) as exc:
        _leer(rar, base, entrada(0, "carpeta", 0, directorio=True))
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE


# ── subproceso (AC-08..10) ────────────────────────────────────────────────────────────────────────
def test_argv_sin_shell_entorno_sin_home_heredado_y_home_temporal(falso, rar, base, monkeypatch):
    monkeypatch.setenv("HOME", "/home/secreto")
    crc = falso.contenido(JPEG)
    with carpeta_temporal(base) as tmp:
        leer_entrada(rar, _a_entrada(entrada(0, "01.jpg", len(JPEG), crc)), 1 << 20, temporal=tmp)
        home_visto = falso.entornos()[-1]
        assert home_visto == f"HOME={tmp}"
    assert all("secreto" not in x for x in falso.entornos())


def test_cuelgue_mata_el_grupo_entero_y_el_motivo_es_tiempo(falso, rar, base):
    """Mutación: matar solo el proceso y no el grupo dejaría vivo al nieto (`sleep`)."""
    crc = falso.contenido(JPEG)
    falso.modo(unar="cuelga")
    with pytest.raises(ErrorRar) as exc:
        _leer(rar, base, entrada(0, "01.jpg", len(JPEG), crc), timeout=0.6)
    assert exc.value.motivo is MotivoRar.TIEMPO
    assert falso.hijo_vivo() is False


def test_listar_que_se_cuelga_tambien_vence(falso, rar, base):
    falso.modo(lsar="cuelga")
    with pytest.raises(ErrorRar) as exc, carpeta_temporal(base) as tmp:
        listar(rar, temporal=tmp, timeout=0.6)
    assert exc.value.motivo is MotivoRar.TIEMPO
    assert falso.hijo_vivo() is False


def test_escribir_mas_del_tope_interrumpe_y_es_demasiado_grande(falso, rar, base):
    falso.contenido(JPEG)
    falso.modo(unar="enorme")
    with pytest.raises(ErrorRar) as exc:
        _leer(rar, base, entrada(0, "01.jpg", 1000, None), tope=1000, timeout=20)
    assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE


# ── limpieza (AC-11) ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("modo", ["ok", "nada", "cuelga", "rc1"])
def test_el_temporal_se_borra_siempre_y_el_original_no_cambia(falso, rar, base, modo):
    """Mutación: no borrar el temporal."""
    crc = falso.contenido(JPEG)
    falso.modo(unar=modo)
    antes = (rar.read_bytes(), rar.stat().st_mtime_ns, rar.stat().st_size)
    with pytest.raises(ErrorRar) if modo != "ok" else _nulo():
        _leer(rar, base, entrada(0, "01.jpg", len(JPEG), crc), timeout=0.6)
    assert list(base.iterdir()) == []
    assert (rar.read_bytes(), rar.stat().st_mtime_ns, rar.stat().st_size) == antes
    assert sorted(p.name for p in rar.parent.iterdir()) == ["n1.cbr"]


def test_el_temporal_se_borra_ante_una_excepcion_cualquiera(base):
    with pytest.raises(RuntimeError), carpeta_temporal(base) as tmp:
        (tmp / "x").write_text("x")
        raise RuntimeError
    assert list(base.iterdir()) == []


def test_el_temporal_es_privado(base):
    with carpeta_temporal(base) as tmp:
        assert (tmp.stat().st_mode & 0o777) == 0o700
        assert tmp.parent == base


class _nulo:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ── un solo lector a la vez (AC-12) ───────────────────────────────────────────────────────────────
def test_cinco_lecturas_simultaneas_nunca_son_mas_de_un_unar(falso, rar, base):
    crc = falso.contenido(JPEG)
    falso.modo(unar="exclusivo")
    resultados: list[bytes] = []

    def lanzar():
        resultados.append(_leer(rar, base, entrada(0, "01.jpg", len(JPEG), crc)))

    hilos = [threading.Thread(target=lanzar) for _ in range(5)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert falso.violaciones() == []
    assert len(resultados) == 5


# ── la interfaz no conoce portadas (AC-13) ────────────────────────────────────────────────────────
def test_el_modulo_no_conoce_portadas_ni_la_web():
    codigo = Path(lector_rar.__file__).read_text()
    cuerpo = codigo.split('"""', 2)[2]          # sin el docstring de cabecera
    assert "web" not in {l.split()[1].split(".")[1] for l in cuerpo.splitlines()
                         if l.startswith("from zascarr")}
    for nombre in ("listar", "leer_entrada"):
        doc = getattr(lector_rar, nombre).__doc__ or ""
        assert "portada" not in doc.lower()
    importados = [l for l in cuerpo.splitlines() if l.startswith("from zascarr")]
    assert importados == ["from zascarr.models import MotivoRar"]
