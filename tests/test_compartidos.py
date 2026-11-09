# ruff: noqa: E501
"""#488 / BL-CNV6: guardián único de archivos compartidos (sin red, dobles de clientes)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from zascarr.services.compartidos import (
    EstadoComparticion,
    _bajo,
    estado_de_comparticion,
    traducir_a_contenedor,
)


def _settings(tmp_path: Path, **kw) -> SimpleNamespace:
    lib = tmp_path / "lib"
    desc = tmp_path / "desc"
    amule = tmp_path / "amule"
    for d in (lib, desc, amule):
        d.mkdir(exist_ok=True)
    datos = dict(
        library_path=lib, downloads_path=desc, amule_incoming_dir=amule,
        host_library_dir="", transmission_download_dir="", transmission_enabled=False,
        amule_enabled=False, carpetas_compartidas=[],
    )
    datos.update(kw)
    return SimpleNamespace(**datos)


class _Transmission:
    def __init__(self, torrents=None, error=None):
        self.torrents = torrents or []
        self.error = error
        self.llamadas = 0

    async def list_torrents(self):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.torrents


class _AMule:
    def __init__(self, compartidos=None, error=None):
        self.compartidos = compartidos
        self.error = error
        self.llamadas = 0

    async def list_shared_paths(self):
        self.llamadas += 1
        if self.error:
            raise self.error
        return self.compartidos


def _torrent(download_dir: str, *nombres: str) -> dict:
    return {"name": "Torrent", "downloadDir": download_dir,
            "files": [{"name": n} for n in nombres]}


@pytest.mark.asyncio
async def test_sin_fuentes_es_no_se_sabe_y_bloquea(tmp_path):
    d = await estado_de_comparticion(tmp_path / "a.cbz", settings=_settings(tmp_path))
    assert d.estado is EstadoComparticion.NO_SE_SABE and d.bloquea
    assert "Declara las carpetas" in d.mensaje


@pytest.mark.asyncio
async def test_carpeta_declarada_coincide_por_raiz_real(tmp_path):
    s = _settings(tmp_path, carpetas_compartidas=[str(tmp_path / "lib")])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s)
    assert d.estado is EstadoComparticion.COMPARTIDO and "carpeta" in d.causa
    assert d.bloquea


@pytest.mark.asyncio
async def test_carpeta_declarada_sin_coincidencia_permite_escribir(tmp_path):
    s = _settings(tmp_path, carpetas_compartidas=[str(tmp_path / "lib")])
    d = await estado_de_comparticion(tmp_path / "desc" / "x.cbz", settings=s)
    assert d.estado is EstadoComparticion.NO_COMPARTIDO and not d.bloquea


@pytest.mark.asyncio
async def test_carpeta_declarada_invalida_falla_cerrado(tmp_path):
    s = _settings(tmp_path, carpetas_compartidas=["relativa/x"])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s)
    assert d.estado is EstadoComparticion.NO_SE_SABE
    s2 = _settings(tmp_path, carpetas_compartidas=[str(tmp_path / "lib" / ".." / "otra")])
    assert (await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s2)).estado is EstadoComparticion.NO_SE_SABE


@pytest.mark.asyncio
async def test_transmission_traduce_host_a_contenedor(tmp_path):
    host_lib = tmp_path / "host-lib"
    host_lib.mkdir()
    s = _settings(tmp_path, host_library_dir=str(host_lib), transmission_enabled=True)
    cliente = _Transmission([_torrent(str(host_lib), "Serie 01.cbz")])
    d = await estado_de_comparticion(tmp_path / "lib" / "Serie 01.cbz", settings=s,
                                     transmission=cliente)
    assert d.estado is EstadoComparticion.COMPARTIDO
    assert "Transmission" in d.causa and cliente.llamadas == 1


@pytest.mark.asyncio
async def test_transmission_traduce_descargas(tmp_path):
    host_desc = tmp_path / "host-desc"
    host_desc.mkdir()
    s = _settings(tmp_path, transmission_download_dir=str(host_desc), transmission_enabled=True)
    cliente = _Transmission([_torrent(str(host_desc), "x.cbz")])
    d = await estado_de_comparticion(tmp_path / "desc" / "x.cbz", settings=s,
                                     transmission=cliente)
    assert d.estado is EstadoComparticion.COMPARTIDO


@pytest.mark.asyncio
async def test_transmission_ruta_desconocida_falla_cerrado(tmp_path):
    s = _settings(tmp_path, transmission_enabled=True)
    cliente = _Transmission([_torrent("/otro/sitio", "x.cbz")])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s,
                                     transmission=cliente)
    assert d.estado is EstadoComparticion.NO_SE_SABE and d.bloquea


@pytest.mark.asyncio
async def test_transmission_caida_falla_cerrado(tmp_path):
    s = _settings(tmp_path, transmission_enabled=True)
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s,
                                     transmission=_Transmission(error=OSError("caída")))
    assert d.estado is EstadoComparticion.NO_SE_SABE


@pytest.mark.asyncio
async def test_amule_sin_api_falla_cerrado(tmp_path):
    s = _settings(tmp_path, amule_enabled=True, carpetas_compartidas=[str(tmp_path / "amule")])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s,
                                     amule=_AMule(compartidos=None))
    assert d.estado is EstadoComparticion.NO_SE_SABE


@pytest.mark.asyncio
async def test_amule_expone_carpeta_compartida(tmp_path):
    s = _settings(tmp_path, amule_enabled=True, carpetas_compartidas=[str(tmp_path / "amule")])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s,
                                     amule=_AMule(compartidos=[str(tmp_path / "lib")]))
    assert d.estado is EstadoComparticion.COMPARTIDO and "aMule" in d.causa


@pytest.mark.asyncio
async def test_amule_vacio_y_declaradas_permiten_escribir(tmp_path):
    s = _settings(tmp_path, amule_enabled=True, carpetas_compartidas=[str(tmp_path / "amule")])
    d = await estado_de_comparticion(tmp_path / "lib" / "x.cbz", settings=s,
                                     amule=_AMule(compartidos=[]))
    assert d.estado is EstadoComparticion.NO_COMPARTIDO


def test_traduccion_no_confunde_prefijos_de_texto(tmp_path):
    s = _settings(tmp_path, host_library_dir=str(tmp_path / "lib"), library_path=tmp_path / "otra")
    # No empieza por la raíz host real: no se traduce por prefijo textual.
    assert traducir_a_contenedor(str(tmp_path / "lib-otra" / "x.cbz"), s) is None
    assert _bajo(str(tmp_path / "otra" / "x.cbz"), str(tmp_path / "otra"))
