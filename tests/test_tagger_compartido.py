# ruff: noqa: E501, F811
"""#488/BL-CNV6: aviso de compartidos en B6 (vista previa, apply y lote/CLI).

Decisión del PO (2026-11-09): no bloquear; advertir y exigir confirmación explícita. Sin
`forzar_compartido` no se escribe; con él sí, y el resultado deja constancia. Sin red: se
sustituye `estado_de_comparticion` en el módulo del tagger.
"""
from __future__ import annotations

import os

import pytest

from tests.test_b6_tagger_pg import _montar, db  # noqa: F401 (fixtures/ayudas)
from zascarr.cli.etiquetar import _parser
from zascarr.services import tagger as tagger_mod
from zascarr.services.compartidos import Decision, EstadoComparticion
from zascarr.services.tagger import ESCRITO, PREVISTO, SALTADO, TaggerService

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requiere TEST_DATABASE_URL (Postgres real)")


def _puerta(estado: EstadoComparticion, causa: str):
    async def _estado(_path):
        return Decision(estado, causa)
    return _estado


@pytest.mark.asyncio
async def test_preview_advierte_pero_no_escribe(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "lo comparte Transmission"))
    previa = await TaggerService(db).ejecutar(archivo, dry_run=True)
    assert previa.advertencia and "parece compartido" in previa.advertencia
    assert previa.accion == PREVISTO
    assert ruta.read_bytes() == antes


@pytest.mark.asyncio
async def test_sin_confirmacion_no_escribe_y_avisa(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "lo comparte Transmission"))
    resultado = await TaggerService(db).ejecutar(archivo, dry_run=False)
    assert resultado.accion == SALTADO and resultado.advertencia
    assert "confirmación explícita" in resultado.advertencia
    assert ruta.read_bytes() == antes
    assert "comicinfo_estado" not in (archivo.metadata_ or {})


@pytest.mark.asyncio
async def test_con_forzar_escribe_y_deja_constancia(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "lo comparte Transmission"))
    resultado = await TaggerService(db).ejecutar(
        archivo, dry_run=False, forzar_compartido=True)
    assert resultado.accion == ESCRITO
    assert resultado.forzado_compartido is True and resultado.advertencia
    from zascarr.utils.cbz import leer_comicinfo
    assert leer_comicinfo(ruta) is not None


@pytest.mark.asyncio
async def test_no_se_sabe_advierte_y_solo_escribe_con_forzar(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.NO_SE_SABE, "sin fuentes"))
    sin = await TaggerService(db).ejecutar(archivo, dry_run=False)
    assert sin.accion == SALTADO and "Declara las carpetas" in sin.motivo
    assert ruta.read_bytes() == antes
    con = await TaggerService(db).ejecutar(
        archivo, dry_run=False, forzar_compartido=True)
    assert con.accion == ESCRITO and con.forzado_compartido is True


@pytest.mark.asyncio
async def test_el_lote_y_el_cli_advierten_y_exigen_forzar(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "está en una carpeta declarada"))
    sin = await TaggerService(db).run(
        limit=0, dry_run=False, file_ids=[str(archivo.id)])
    assert sin.escritos == 0 and sin.saltados == 1
    assert ruta.read_bytes() == antes

    con = await TaggerService(db).run(
        limit=0, dry_run=False, file_ids=[str(archivo.id)], forzar_compartido=True)
    assert con.escritos == 1 and con.resultados[-1].forzado_compartido is True


def test_el_cli_expone_la_confirmacion_explicita():
    args = _parser().parse_args(["--apply", "--forzar"])
    assert args.apply is True and args.forzar is True
    assert _parser().parse_args(["--apply"]).forzar is False
