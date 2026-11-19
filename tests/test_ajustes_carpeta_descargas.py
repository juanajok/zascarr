"""Aviso de carpeta de descargas de Transmission (2026-11-17)."""
from __future__ import annotations

from zascarr.web.ajustes import (
    _aviso_de_carpeta_transmission,
    _carpeta_de_descargas_valida,
)


def test_avisa_si_la_carpeta_no_es_la_de_transmission():
    aviso = _aviso_de_carpeta_transmission(
        "/media/downloads/comics", "/media/Descargas/torrents/completos")
    assert aviso is not None
    assert "/media/downloads/comics" in aviso
    assert "/media/Descargas/torrents/completos" in aviso


def test_no_avisa_si_coinciden_o_falta_alguna():
    assert _aviso_de_carpeta_transmission("/media/comics", "/media/comics") is None
    assert _aviso_de_carpeta_transmission("", "/media/comics") is None
    assert _aviso_de_carpeta_transmission("/media/comics", None) is None


def test_valida_ruta_absoluta_del_host():
    assert _carpeta_de_descargas_valida("/media/Descargas/torrents/completos")
    assert not _carpeta_de_descargas_valida("media/Descargas")
    assert not _carpeta_de_descargas_valida("/media/../etc")
    assert not _carpeta_de_descargas_valida("/")
    assert not _carpeta_de_descargas_valida("/media/\x01raro")
