# ruff: noqa: E501, F811
"""#488/BL-CNV6: regresión de B6 con el guardián de archivos compartidos.

Sin red: se sustituye `estado_de_comparticion` en el módulo del tagger. Con `compartido` o
`no_se_sabe` no se escribe el CBZ ni se marca `metadata_` (vista previa, apply y lote/CLI).
"""
from __future__ import annotations

import os

import pytest

from tests.test_b6_tagger_pg import _montar, db  # noqa: F401 (fixtures/ayudas)
from zascarr.services import tagger as tagger_mod
from zascarr.services.compartidos import Decision, EstadoComparticion
from zascarr.services.tagger import SALTADO, TaggerService

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requiere TEST_DATABASE_URL (Postgres real)")


def _puerta(estado: EstadoComparticion, causa: str):
    async def _estado(_path):
        return Decision(estado, causa)
    return _estado


@pytest.mark.asyncio
async def test_archivo_compartido_no_se_escribe_ni_en_apply(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "lo comparte Transmission"))
    servicio = TaggerService(db)

    previa = await servicio.ejecutar(archivo, dry_run=True)
    assert previa.accion == SALTADO and "No se toca" in previa.motivo

    aplicado = await servicio.ejecutar(archivo, dry_run=False)
    assert aplicado.accion == SALTADO and "No se toca" in aplicado.motivo
    assert ruta.read_bytes() == antes
    assert "comicinfo_estado" not in (archivo.metadata_ or {})


@pytest.mark.asyncio
async def test_no_se_sabe_tambien_bloquea(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.NO_SE_SABE, "sin fuentes"))
    resultado = await TaggerService(db).ejecutar(archivo, dry_run=False)
    assert resultado.accion == SALTADO
    assert "Declara las carpetas" in resultado.motivo
    assert ruta.read_bytes() == antes


@pytest.mark.asyncio
async def test_el_lote_del_cli_tambien_respeta_el_guardian(db, tmp_path, monkeypatch):
    archivo, ruta = await _montar(db, tmp_path)
    antes = ruta.read_bytes()
    monkeypatch.setattr(tagger_mod, "estado_de_comparticion",
                        _puerta(EstadoComparticion.COMPARTIDO, "está en una carpeta declarada"))
    informe = await TaggerService(db).run(
        limit=0, dry_run=False, file_ids=[str(archivo.id)])
    assert informe.escritos == 0 and informe.saltados == 1
    assert ruta.read_bytes() == antes
