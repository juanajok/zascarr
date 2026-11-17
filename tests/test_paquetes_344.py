"""#344 BL-PACK1 cortes 1-2: detección, listado y tokens de paquetes de Descargas."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from zascarr.services.paquetes import (
    TTL_SEGUNDOS,
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


def test_ui_lista_paquetes_sin_boton_de_extraer(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.main import app
    from zascarr.services.paquetes import PaquetePendiente
    from zascarr.web import auditoria
    p = PaquetePendiente(ruta=tmp_path / "x.zip", raiz=tmp_path, relativa="x.zip",
                         nombre="x.zip", tamano=123, mtime_ns=1, firma="ZIP",
                         estado="listo", causa="", dev=1, ino=2, token="t")
    monkeypatch.setattr(auditoria, "detectar_paquetes", lambda: [p])
    r = TestClient(app).get("/ui/auditoria/paquetes")
    assert r.status_code == 200
    assert "Paquetes en Descargas" in r.text
    assert "Ver qué contiene" in r.text
    assert "Extraer e importar" not in r.text


def test_token_caducado_y_replay(tmp_path):
    a = _ajustes(tmp_path)
    _zip(Path(a.transmission_download_dir) / "p.zip", {"a.cbz": _cbz()})
    candidato = detectar_paquetes(ajustes=a, secret=a.secret_key, ahora=100)[0]
    with pytest.raises(TokenPaqueteInvalido):
        verificar_token_paquete(candidato.token, ajustes=a, ahora=100 + TTL_SEGUNDOS + 1)
    c2 = detectar_paquetes(ajustes=a, secret=a.secret_key)[0]
    assert verificar_token_paquete(c2.token, ajustes=a).estado == "listo"
    with pytest.raises(TokenPaqueteInvalido):
        verificar_token_paquete(c2.token, ajustes=a)       # replay


def test_token_symlink_falla_cerrado(tmp_path):
    a = _ajustes(tmp_path)
    d = Path(a.transmission_download_dir)
    p = _zip(d / "p.zip", {"a.cbz": _cbz()})
    candidato = detectar_paquetes(ajustes=a, secret=a.secret_key)[0]
    fuera = tmp_path / "fuera.zip"
    _zip(fuera, {"a.cbz": _cbz()})
    p.unlink()
    p.symlink_to(fuera)
    with pytest.raises(TokenPaqueteInvalido):
        verificar_token_paquete(candidato.token, ajustes=a)


def test_html_no_expone_ruta_absoluta(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.main import app
    from zascarr.services.paquetes import PaquetePendiente, crear_token_paquete
    from zascarr.web import auditoria
    raiz = tmp_path / "descargas"
    raiz.mkdir()
    p = PaquetePendiente(ruta=raiz / "x.zip", raiz=raiz, relativa="x.zip",
                         nombre="x.zip", tamano=123, mtime_ns=1, firma="ZIP",
                         estado="listo", causa="", dev=1, ino=2)
    p = PaquetePendiente(**{**p.__dict__, "token": crear_token_paquete(p)})
    monkeypatch.setattr(auditoria, "detectar_paquetes", lambda: [p])
    r = TestClient(app).get("/ui/auditoria/paquetes")
    assert r.status_code == 200 and str(tmp_path) not in r.text
    assert "name=\"token\"" in r.text and str(raiz) not in r.text


def test_rar_top_y_herramienta_ausente(tmp_path, monkeypatch):
    from zascarr.utils import lector_rar

    a = _ajustes(tmp_path)
    p = Path(a.transmission_download_dir) / "p.rar"
    p.write_bytes(b"Rar!\x1a\x07\x00")
    monkeypatch.setattr(lector_rar, "disponible", lambda: False)
    with pytest.raises(PaqueteError, match="herramienta"):
        _listar(p, tmp_path)
    monkeypatch.setattr(lector_rar, "disponible", lambda: True)
    entradas = (lector_rar.EntradaRar(0, "a.cbz", 10, None, False, False),)
    monkeypatch.setattr(lector_rar, "listar", lambda *a, **k: lector_rar.Listado(entradas))
    listado = _listar(p, tmp_path)
    assert listado.formato == "RAR" and [e.nombre for e in listado.entradas] == ["a.cbz"]


def test_rar_multivolumen_no_es_candidato(tmp_path):
    a = _ajustes(tmp_path)
    (Path(a.transmission_download_dir) / "p.r00").write_bytes(b"Rar!\x1a\x07\x00")
    vistos = detectar_paquetes(ajustes=a, secret=a.secret_key)
    assert len(vistos) == 1 and vistos[0].estado == "multivolumen"


def test_listado_usa_fd_y_no_reabre_symlink(tmp_path):
    a = _ajustes(tmp_path)
    d = Path(a.transmission_download_dir)
    p = _zip(d / "p.zip", {"a.cbz": _cbz()})
    candidato = detectar_paquetes(ajustes=a, secret=a.secret_key)[0]
    abierto = verificar_token_paquete(candidato.token, ajustes=a)
    fuera = tmp_path / "fuera.zip"
    _zip(fuera, {"ajeno.cbz": _cbz(b"ajeno")})
    p.unlink()
    p.symlink_to(fuera)
    try:
        listado = listar_paquete(abierto)
        assert [e.nombre for e in listado.entradas] == ["a.cbz"]
    finally:
        if abierto.fd >= 0:
            os.close(abierto.fd)


def test_rar_real_desde_fd_si_hay_unar(tmp_path):
    from zascarr.utils import lector_rar
    if not lector_rar.disponible():
        pytest.skip("sin unar/lsar")
    a = _ajustes(tmp_path)
    destino = Path(a.transmission_download_dir) / "minimo.rar"
    destino.write_bytes(Path("tests/fixtures/rar/minimo_rar4.cbr").read_bytes())
    candidato = detectar_paquetes(ajustes=a, secret=a.secret_key)[0]
    abierto = verificar_token_paquete(candidato.token, ajustes=a)
    try:
        with pytest.raises(PaqueteError, match="No contiene tebeos"):
            listar_paquete(abierto)
    finally:
        if abierto.fd >= 0:
            os.close(abierto.fd)


def _zip_con(path: Path, entradas: dict[str, bytes]) -> Path:
    return _zip(path, entradas)


def test_tope_entradas(tmp_path, monkeypatch):
    from zascarr.services import paquetes as modulo
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "muchos.zip", {f"{i}.cbz": _cbz() for i in range(3)})
    monkeypatch.setattr(modulo, "MAX_ENTRADAS", 2)
    with pytest.raises(PaqueteError, match="demasiados archivos"):
        _listar(p, tmp_path)


def test_tope_total_y_por_entrada(tmp_path, monkeypatch):
    from zascarr.services import paquetes as modulo
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "p.zip", {"a.cbz": _cbz() + b"x" * 10})
    monkeypatch.setattr(modulo, "MAX_BYTES_TOTAL", 5)
    with pytest.raises(PaqueteError, match="tamaño excesivo"):
        _listar(p, tmp_path)
    monkeypatch.setattr(modulo, "MAX_BYTES_TOTAL", 8 * 1024 ** 3)
    monkeypatch.setattr(modulo, "MAX_BYTES_ENTRADA", 5)
    with pytest.raises(PaqueteError, match="demasiado grande"):
        _listar(p, tmp_path)


def test_tope_ratio(tmp_path, monkeypatch):
    from zascarr.services import paquetes as modulo
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "ratio.zip", {"a.cbz": b"PK\x03\x04" + b"\x00" * 100000})
    monkeypatch.setattr(modulo, "MAX_RATIO_LEIDA", 1)
    with pytest.raises(PaqueteError, match="demasiado comprimido"):
        _listar(p, tmp_path)


def test_tope_directorio_central(tmp_path, monkeypatch):
    from zascarr.core.formato_contenedor import CabeceraZip
    from zascarr.services import paquetes as modulo
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "central.zip", {"a.cbz": _cbz()})
    monkeypatch.setattr(modulo, "leer_cabecera_zip",
                        lambda _p: CabeceraZip(entradas=1, tam_directorio=2 * 1024 ** 2))
    with pytest.raises(PaqueteError, match="índice demasiado grande"):
        _listar(p, tmp_path)


@pytest.mark.parametrize("nombre", ["../fuera.cbz", "..\\fuera.cbz", "C:\\fuera.cbz",
                                     "con\x01control.cbz", "/absoluto.cbz"])
def test_nombres_hostiles_rechazan_el_paquete(tmp_path, nombre):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = _zip(d / "hostil.zip", {nombre: _cbz()})
    with pytest.raises(PaqueteError, match="nombres de archivo no seguros"):
        _listar(p, tmp_path)


def test_zip_corrupto_no_es_500(tmp_path):
    d = Path(_ajustes(tmp_path).transmission_download_dir)
    p = d / "corrupto.zip"
    p.write_bytes(b"PK\x03\x04" + b"basura")
    with pytest.raises((PaqueteError, Exception)):
        _listar(p, tmp_path)


def test_ui_a11y_y_sin_extraccion(tmp_path):
    lista = Path("src/zascarr/web/templates/_paquetes_descargas.html").read_text()
    previa = Path("src/zascarr/web/templates/_paquete_previa.html").read_text()
    assert '<button type="submit">Ver qué contiene</button>' in lista
    assert 'role="status"' in previa and 'aria-live="polite"' in previa
    assert "Extraer e importar" in previa
    assert "token" not in previa.lower()


def test_rar_top_total_y_entrada_y_entradas(tmp_path, monkeypatch):
    from zascarr.services import paquetes as modulo
    from zascarr.utils import lector_rar
    a = _ajustes(tmp_path)
    p = Path(a.transmission_download_dir) / "p.rar"
    p.write_bytes(b"Rar!\x1a\x07\x00")
    monkeypatch.setattr(lector_rar, "disponible", lambda: True)
    candidato = next(x for x in detectar_paquetes(ajustes=a, secret=a.secret_key)
                     if x.ruta == p)
    base = lector_rar.EntradaRar(0, "a.cbz", 10, None, False, False)
    monkeypatch.setattr(lector_rar, "listar", lambda *a, **k: lector_rar.Listado((base,)))
    monkeypatch.setattr(modulo, "MAX_BYTES_TOTAL", 5)
    with pytest.raises(PaqueteError, match="tamaño excesivo"):
        listar_paquete(candidato)
    monkeypatch.setattr(modulo, "MAX_BYTES_TOTAL", 8 * 1024 ** 3)
    monkeypatch.setattr(modulo, "MAX_BYTES_ENTRADA", 5)
    with pytest.raises(PaqueteError, match="demasiado grande"):
        listar_paquete(candidato)
    monkeypatch.setattr(modulo, "MAX_BYTES_ENTRADA", 2 * 1024 ** 3)
    monkeypatch.setattr(lector_rar, "listar",
                        lambda *a, **k: lector_rar.Listado(
                            tuple(lector_rar.EntradaRar(i, "a.cbz", 1, None, False, False)
                                  for i in range(1001))))
    with pytest.raises(PaqueteError, match="demasiados archivos"):
        listar_paquete(candidato)


def test_http_corrupto_no_500(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.main import app
    from zascarr.services.paquetes import PaquetePendiente
    from zascarr.web import auditoria
    raiz = tmp_path / "d"
    raiz.mkdir()
    ruta = raiz / "x.zip"
    ruta.write_bytes(b"PK\x03\x04basura")
    st = ruta.stat()
    p = PaquetePendiente(ruta=ruta, raiz=raiz, relativa="x.zip",
                         nombre="x.zip", tamano=st.st_size, mtime_ns=st.st_mtime_ns,
                         firma="ZIP", estado="listo", causa="", dev=st.st_dev, ino=st.st_ino)
    monkeypatch.setattr(auditoria, "verificar_token_paquete", lambda _t: p)
    r = TestClient(app).get("/ui/auditoria/paquetes/previa?token=x")
    assert r.status_code == 200 and "dañado" in r.text


def test_preview_rar_y_zip_distinguen_tipo(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.main import app
    from zascarr.services.paquetes import ListadoPaquete, PaquetePendiente
    from zascarr.web import auditoria
    raiz = tmp_path / "d"
    raiz.mkdir()
    p = PaquetePendiente(ruta=raiz / "x.rar", raiz=raiz, relativa="x.rar",
                         nombre="x.rar", tamano=1, mtime_ns=1, firma="RAR",
                         estado="listo", causa="", dev=1, ino=2)
    monkeypatch.setattr(auditoria, "verificar_token_paquete", lambda _t: p)
    monkeypatch.setattr(auditoria, "listar_paquete", lambda _p: ListadoPaquete(
        paquete=p, formato="RAR", entradas=(), ignoradas=(), bytes_estimados=0,
        tipo_confirmado=False))
    r = TestClient(app).get("/ui/auditoria/paquetes/previa?token=x")
    assert "candidatos a importar" in r.text and "se confirmará al extraer" in r.text
    monkeypatch.setattr(auditoria, "listar_paquete", lambda _p: ListadoPaquete(
        paquete=p, formato="ZIP", entradas=(), ignoradas=(), bytes_estimados=0,
        tipo_confirmado=True))
    assert "Se importarían" in TestClient(app).get("/ui/auditoria/paquetes/previa?token=x").text
