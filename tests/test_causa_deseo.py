"""UXA-13a (#1130): causa clasificada de un deseo, qué hacer y adónde ir (funciones puras)."""
from __future__ import annotations

import pytest

from zascarr.services import orchestrator as o
from zascarr.services.causa_deseo import (
    _POR_MOTIVO,
    AJUSTES,
    causa_de_motivo,
    cliente_de_descarga,
)

TIPOS = {"sin_configurar", "en_espera", "fallo", "sin_resultados"}


@pytest.mark.parametrize("motivo, tipo", [
    (o.MOTIVO_SIN_FUENTE, "sin_configurar"),
    (o.MOTIVO_PROWlARR_CONFIGURACION, "sin_configurar"),
    (o.MOTIVO_CANDIDATO_RECHAZADO, "sin_configurar"),
    (o.MOTIVO_FORO_ESPERA, "en_espera"),
    (o.MOTIVO_ESPERA_CON_DESCARTES, "en_espera"),
    (o.MOTIVO_FUENTE_INACCESIBLE, "en_espera"),
    (o.MOTIVO_TRANSMISSION_INACCESIBLE, "fallo"),
    (o.MOTIVO_AMULE_INACCESIBLE, "fallo"),
    (o.MOTIVO_CLIENTE_INACCESIBLE, "fallo"),
    (o.MOTIVO_ERROR_INESPERADO, "fallo"),
    (o.MOTIVO_CANDIDATO_INVALIDO, "fallo"),
    (o.MOTIVO_SIN_RESULTADOS, "sin_resultados"),
    (o.MOTIVO_NUMERO_DISTINTO, "sin_resultados"),
])
def test_cada_motivo_cae_en_su_causa(motivo, tipo):
    assert causa_de_motivo(motivo).tipo == tipo


def test_sin_configurar_lleva_a_ajustes_y_lo_que_se_reintenta_sola_no_pide_nada():
    motivos = (o.MOTIVO_SIN_FUENTE, o.MOTIVO_PROWlARR_CONFIGURACION, o.MOTIVO_CANDIDATO_RECHAZADO)
    for motivo in motivos:
        c = causa_de_motivo(motivo)
        assert c.destino == AJUSTES and c.enlace and c.accion
    espera = causa_de_motivo(o.MOTIVO_FORO_ESPERA)
    assert espera.destino is None and "No hace falta hacer nada" in espera.accion


def test_los_numeros_que_no_coinciden_apuntan_a_por_revisar_no_a_ajustes():
    assert causa_de_motivo(o.MOTIVO_NUMERO_DISTINTO).destino == "/ui/pendientes"


def test_cada_causa_tiene_etiqueta_accion_y_aspecto_validos():
    for c in _POR_MOTIVO.values():
        assert c.tipo in TIPOS and c.etiqueta and c.accion
        assert c.aspecto in {"neutro", "ok", "warn", "amber", "info"}


@pytest.mark.parametrize("motivo", [None, "", "Un motivo que ZascArr no conoce"])
def test_un_motivo_desconocido_no_se_clasifica_ni_se_inventa_una_causa(motivo):
    assert causa_de_motivo(motivo) is None


def test_todo_motivo_del_orquestador_esta_clasificado():
    """Regresión: un `MOTIVO_*` nuevo del orquestador sin causa aquí saldría sin «qué hacer»."""
    motivos = {v for k, v in vars(o).items() if k.startswith("MOTIVO_") and isinstance(v, str)}
    sin_clasificar = sorted(m for m in motivos if m not in _POR_MOTIVO)
    assert sin_clasificar == [], sin_clasificar


@pytest.mark.parametrize("url, cliente", [
    ("ed2k://|file|Flash 01.cbz|1234|HASH|/", "aMule"),
    ("magnet:?xt=urn:btih:abc", "Transmission"),
    ("https://indexer.example/x.torrent", "Transmission"),
    ("", "Transmission"),
])
def test_el_cliente_se_dice_segun_el_enlace(url, cliente):
    assert cliente_de_descarga(url) == cliente
