"""Contrato de raíces de biblioteca (#156, corte A), sin BD.

Cubre normalización/validación, solapamientos por componentes, symlinks, mapeo
tradición→raíz y los helpers de pertenencia/ruta visible.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zascarr.models import ComicTradition
from zascarr.services import raices


def _settings(tmp_path: Path, **extra):
    base = dict(
        library_path=tmp_path / "library",
        library_roots=str(tmp_path / "library"),
        host_library_roots=str(tmp_path / "host-library"),
        downloads_path=tmp_path / "downloads",
        amule_incoming_dir=tmp_path / "incoming",
        export_path=tmp_path / "export",
        carpetas_compartidas=[],
    )
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.fixture
def tmp_raiz(tmp_path, monkeypatch):
    (tmp_path / "library").mkdir()
    monkeypatch.setattr(raices, "get_settings", lambda: _settings(tmp_path))
    return tmp_path


def test_normaliza_absoluta_sin_barra_final():
    assert raices.normalizar_ruta("/media/library/") == "/media/library"
    assert raices.normalizar_ruta("/media/library/./x/../y") == "/media/library/y"
    for mala in ("", "media/library", "/"):
        with pytest.raises(raices.RaizInvalidaError):
            raices.normalizar_ruta(mala)


def test_prefijo_textual_no_es_anidado():
    assert raices.es_componente_de("/media/library/x.cbz", "/media/library")
    assert not raices.es_componente_de("/media/library2/x.cbz", "/media/library")


def test_valida_raiz_y_rechaza_solapamientos(tmp_raiz):
    raiz = raices.validar_raiz(tmp_raiz / "library", name=" Biblioteca ")
    assert raiz["path"] == str(tmp_raiz / "library")
    assert raiz["name"] == "Biblioteca"
    assert raiz["is_default"] is False
    existente = SimpleNamespace(id="r1", path=str(tmp_raiz / "library"), name="Biblioteca",
                                host_path=None)
    (tmp_raiz / "library" / "sub").mkdir()
    with pytest.raises(raices.RaizInvalidaError, match="solapa"):
        raices.validar_raiz(tmp_raiz / "library" / "sub", name="Sub", raices=[existente])
    with pytest.raises(raices.RaizInvalidaError, match="nombre"):
        raices.validar_raiz(tmp_raiz / "library", name="biblioteca", raices=[existente])


def test_rechaza_fuera_de_montaje_y_especiales(tmp_raiz):
    with pytest.raises(raices.RaizInvalidaError, match="montaje"):
        raices.validar_raiz(tmp_raiz / "otro", name="Otro")
    with pytest.raises(raices.RaizInvalidaError, match="montaje"):
        raices.validar_raiz(tmp_raiz / "downloads", name="Descargas")
    with pytest.raises(raices.RaizInvalidaError, match=".zascarr"):
        raices.validar_raiz(tmp_raiz / "library" / ".zascarr", name="Oculta")


def test_symlink_roto_y_fichero(tmp_raiz):
    roto = tmp_raiz / "library" / "roto"
    roto.symlink_to(tmp_raiz / "no-existe")
    with pytest.raises(raices.RaizInvalidaError, match="symlink roto"):
        raices.validar_raiz(roto, name="Roto")
    fichero = tmp_raiz / "library" / "archivo"
    fichero.write_text("x")
    with pytest.raises(raices.RaizInvalidaError, match="no es una carpeta"):
        raices.validar_raiz(fichero, name="Fichero")


def test_valida_raiz_por_defecto_debe_estar_habilitada(tmp_raiz):
    with pytest.raises(raices.RaizInvalidaError, match="deshabilitada"):
        raices.validar_raiz(tmp_raiz / "library", name="Biblioteca",
                            enabled=False, is_default=True)


def test_solo_una_raiz_por_defecto(tmp_raiz):
    existente = SimpleNamespace(id="r1", path="/media/library", name="Biblioteca",
                                host_path=None, enabled=True, is_default=True)
    with pytest.raises(raices.RaizInvalidaError, match="por defecto"):
        raices.validar_raiz("/media/library", name="Otra", is_default=True,
                            raices=[existente])


def test_host_path_absoluto(tmp_raiz):
    with pytest.raises(raices.RaizInvalidaError, match="host"):
        raices.validar_raiz(tmp_raiz / "library", name="Biblioteca", host_path="relativa")
    r = raices.validar_raiz(tmp_raiz / "library", name="Biblioteca",
                            host_path=str(tmp_raiz / "host"))
    assert r["host_path"] == str(tmp_raiz / "host")


@pytest.mark.asyncio
async def test_raiz_por_tradicion_consulta_la_raiz_habilitada():
    raiz = SimpleNamespace(id="r1", path="/media/library", enabled=True)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalar_one_or_none=lambda: raiz)))
    assert await raices.raiz_por_tradicion(db, ComicTradition.MANGA) is raiz
    db.execute.assert_awaited_once()


def test_raiz_de_elige_la_mas_especifica():
    a = SimpleNamespace(id="a", path="/media/library")
    b = SimpleNamespace(id="b", path="/media/library/manga")
    assert raices.raiz_de("/media/library/manga/x.cbz", [a, b]) is b
    assert raices.raiz_de("/media/library/otro/x.cbz", [a, b]) is a
    assert raices.raiz_de("/media/library2/x.cbz", [a, b]) is None


def test_relative_and_ruta_visible_por_raiz():
    raiz = SimpleNamespace(path="/media/library", host_path="/srv/library")
    assert raices.relative_to_root("/media/library/a/b.cbz", raiz) == Path("a/b.cbz")
    assert raices.ruta_visible("/media/library/a/b.cbz", raiz) == "/srv/library/a/b.cbz"
    sin_host = SimpleNamespace(path="/media/library", host_path=None)
    assert raices.ruta_visible("/media/library/a.cbz", sin_host) == "/media/library/a.cbz"
    assert raices.ruta_visible("/media/otra/a.cbz", sin_host) == "/media/otra/a.cbz"
    with pytest.raises(raices.RaizInvalidaError):
        raices.relative_to_root("/media/otra/a.cbz", raiz)


def test_una_raiz_conserva_rutas_y_recuentos():
    raiz = SimpleNamespace(path="/media/library", host_path="/srv/library")
    rutas = ["/media/library/a.cbz", "/media/library/sub/b.cbz", "/media/otra/c.cbz"]
    dentro = [r for r in rutas if raices.raiz_de(r, [raiz]) is raiz]
    assert dentro == ["/media/library/a.cbz", "/media/library/sub/b.cbz"]
    assert raices.relative_to_root("/media/library/sub/b.cbz", raiz) == Path("sub/b.cbz")
    assert raices.ruta_visible("/media/library/sub/b.cbz", raiz) == "/srv/library/sub/b.cbz"
    assert raices.ruta_visible("/media/otra/c.cbz", raiz) == "/media/otra/c.cbz"


def test_generador_de_raices_no_se_consume_antes_de_la_comprobacion(tmp_raiz):
    existente = SimpleNamespace(id="r1", path=str(tmp_raiz / "library"), name="Biblioteca",
                                host_path=None)
    with pytest.raises(raices.RaizInvalidaError, match="solapa"):
        raices.validar_raiz(tmp_raiz / "library", name="Otra", raices=(r for r in [existente]))


def test_allowlist_con_varios_montajes(tmp_raiz, monkeypatch):
    (tmp_raiz / "library2").mkdir()
    monkeypatch.setattr(raices, "get_settings", lambda: _settings(
        tmp_raiz, library_roots=f"{tmp_raiz / 'library'},{tmp_raiz / 'library2'}"))
    assert raices.validar_raiz(
        tmp_raiz / "library2", name="Segunda")["path"] == str(tmp_raiz / "library2")
    with pytest.raises(raices.RaizInvalidaError, match="montaje"):
        raices.validar_raiz(tmp_raiz / "otro", name="Otro")


def test_symlink_al_mismo_inodo_se_rechaza(tmp_raiz):
    existente = SimpleNamespace(id="r1", path=str(tmp_raiz / "library"), name="Biblioteca",
                                host_path=None)
    alias = tmp_raiz / "library" / "alias"
    alias.symlink_to(tmp_raiz / "library", target_is_directory=True)
    with pytest.raises(raices.RaizInvalidaError, match="inodo|solapa"):
        raices.validar_raiz(alias, name="Alias", raices=[existente])


def test_raiz_ausente_y_sin_escritura(tmp_raiz, monkeypatch):
    with pytest.raises(raices.RaizInvalidaError, match="no existe"):
        raices.validar_raiz(tmp_raiz / "library" / "ausente", name="Ausente")

    def sin_permiso(*_a, **_kw):
        raise PermissionError("solo lectura")
    monkeypatch.setattr("tempfile.NamedTemporaryFile", sin_permiso)
    with pytest.raises(raices.RaizInvalidaError, match="legible"):
        raices.validar_raiz(tmp_raiz / "library", name="Biblioteca")


def test_validar_conjunto_exige_una_raiz_por_defecto(tmp_raiz):
    with pytest.raises(raices.RaizInvalidaError, match="exactamente"):
        raices.validar_conjunto([])
    with pytest.raises(raices.RaizInvalidaError, match="exactamente"):
        raices.validar_conjunto([SimpleNamespace(is_default=False, enabled=True)])
    raices.validar_conjunto([SimpleNamespace(is_default=True, enabled=True)])


def test_symlink_intermedio_que_escapa_se_rechaza(tmp_raiz):
    fuera = tmp_raiz / "fuera"
    fuera.mkdir()
    escape = tmp_raiz / "library" / "escape"
    escape.symlink_to(fuera, target_is_directory=True)
    with pytest.raises(raices.RaizInvalidaError, match="montaje"):
        raices.validar_raiz(escape, name="Escape")


def test_bucle_de_symlink(tmp_raiz):
    bucle = tmp_raiz / "library" / "bucle"
    bucle.symlink_to(bucle)
    with pytest.raises(raices.RaizInvalidaError, match="symlink|bucle"):
        raices.validar_raiz(bucle, name="Bucle")


@pytest.mark.asyncio
async def test_tradicion_fuera_de_allowlist_actual_no_se_devuelve(tmp_raiz, monkeypatch):
    fila = SimpleNamespace(id="r1", path=str(tmp_raiz / "fuera"), enabled=True)
    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalar_one_or_none=lambda: fila)))
    assert await raices.raiz_por_tradicion(db, ComicTradition.MANGA) is None
