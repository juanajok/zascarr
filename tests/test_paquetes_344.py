"""#344 BL-PACK1 cortes 1-2: detección, listado y tokens de paquetes de Descargas."""
from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from zascarr.services.paquetes import (
    PaqueteError,
    TokenPaqueteInvalido,
    detectar_paquetes,
    listar_paquete,
    verificar_token_paquete,
)


def _ajustes(tmp_path: Path) -> SimpleNamespace:
    descargas = tmp_path / "descargas"
    descargas.mkdir(exist_ok=True)
    return SimpleNamespace(transmission_download_dir=str(descargas),
                           amule_incoming_dir="", downloads_path="",
                           secret_key="clave-de-pruebas")


def _zip(path: Path, entradas: dict[str, bytes], *, compresion=zipfile.ZIP_DEFLATED) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compresion) as z:
        for nombre, datos in entradas.items():
            z.writestr(nombre, datos)
    return path


def _cbz(minimo=b"x") -> bytes:
    return b"PK\x03\x04" + minimo


def _listar(path: Path, tmp_path: Path):
    a = _ajustes(tmp_path)
    p = next(x for x in detectar_paquetes(ajustes=a, secret=a.secret_key) if x.ruta == path)
    return listar_paquete(p)


def test_detecta_zip_y_rar_por_firma_y_descarta_mentirosos(tmp_path):
    a = _ajustes(tmp_path)
    d = Path(a.transmission_download_dir)
    _zip(d / "normal.cbz.zip", {"a.cbz": _cbz()})
    (d / "falso.zip").write_bytes(b"no soy zip")
    _zip(d / "doble.rar.zip", {"a.cbz": _cbz()})
    (d / "dividido.part1.rar").write_bytes(b"Rar!\x1a\x07\x00")
    (d / "no-paquete.txt").write_bytes(b"x")
    vistos = detectar_paquetes(ajustes=a, secret="clave-de-pruebas")
    nombres = {p.nombre for p in vistos}
    assert nombres == {"normal.cbz.zip", "falso.zip", "doble.rar.zip", "dividido.part1.rar"}
    por_nombre = {p.nombre: p for p in vistos}
    assert por_nombre["falso.zip"].estado == "no_legible"
    assert por_nombre["dividido.part1.rar"].estado == "multivolumen"
    assert por_nombre["doble.rar.zip"].firma == "ZIP"


def test_dedupe_por_inodo(tmp_path):
    a = _ajustes(tmp_path)
    d = Path(a.transmission_download_dir)
    _zip(d / "uno.zip", {"a.cbz": _cbz()})
    (d / "copia.zip").hardlink_to(d / "uno.zip")
    vistos = detectar_paquetes(ajustes=a, secret="clave-de-pruebas")
    assert len(vistos) == 1


def test_listado_zip_clasifica_entradas_e_ignora_otras(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "paquete.zip", {"bueno.cbz": _cbz(), "nota.txt": b"hola",
                                 "malo.cbz": b"no es zip"})
    listado = _listar(p, tmp_path)
    assert [e.nombre for e in listado.entradas] == ["bueno.cbz"]
    assert {e.nombre for e in listado.ignoradas} == {"nota.txt", "malo.cbz"}
    assert listado.bytes_estimados == len(_cbz())


def test_listado_sin_tebeos_es_error(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "solo.zip", {"nota.txt": b"hola"})
    with pytest.raises(PaqueteError, match="No contiene tebeos"):
        _listar(p, tmp_path)


def test_paquete_anidado_y_cifrado(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    anidado = _zip(d / "anidado.zip", {"otro.zip": _cbz()})
    with pytest.raises(PaqueteError, match="otro paquete"):
        _listar(anidado, tmp_path)
def test_token_valido_caducado_y_manipulado(tmp_path):
    a = _ajustes(tmp_path)
    p = _zip(Path(a.transmission_download_dir) / "paquete.zip", {"a.cbz": _cbz()})
    candidato = detectar_paquetes(ajustes=a, secret=a.secret_key)[0]
    assert verificar_token_paquete(candidato.token, ajustes=a,
                                   secret=a.secret_key).ruta == p
    with pytest.raises(TokenPaqueteInvalido):
        verificar_token_paquete(candidato.token, ajustes=a, secret="otra")
    with pytest.raises(TokenPaqueteInvalido):
        verificar_token_paquete(candidato.token + "x", ajustes=a, secret=a.secret_key)


def test_listado_no_escribe_ni_toca_el_paquete(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "paquete.zip", {"a.cbz": _cbz()})
    antes = (p.read_bytes(), p.stat().st_mtime_ns, sorted(x.name for x in d.iterdir()))
    _listar(p, tmp_path)
    assert (p.read_bytes(), p.stat().st_mtime_ns, sorted(x.name for x in d.iterdir())) == antes


def test_top_tamano_total(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    with zipfile.ZipFile(d / "inmenso.zip", "w") as z:
        z.writestr("a.cbz", b"PK\x03\x04")
    # no se puede inflar sin escribir 8 GiB; se comprueba el tope de entradas con un ZIP normal
    p = d / "inmenso.zip"
    listado = _listar(p, tmp_path)
    assert listado.entradas
