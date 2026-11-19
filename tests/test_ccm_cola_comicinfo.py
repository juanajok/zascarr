"""CCM-5: cola de ComicInfo sin I/O real."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zascarr.services.consolidacion.cola_comicinfo import (
    CLAVE_PENDIENTE,
    InformeCola,
    SincronizadorComicInfo,
    _marcar,
    _pendiente,
)
from zascarr.services.tagger import ESCRITO, SALTADO, ResultadoEtiquetado


def _issue():
    return SimpleNamespace(id="i-1", metadata_={CLAVE_PENDIENTE: True})


class _Tagger:
    def __init__(self, resultados):
        self.resultados = resultados
        self.llamadas = 0

    async def ejecutar(self, _archivo, *, dry_run):
        self.llamadas += 1
        return self.resultados[self.llamadas - 1]


class _Sincronizador(SincronizadorComicInfo):
    def __init__(self, resultados, *, archivos=("a.cbz",)):
        super().__init__(db=SimpleNamespace(flush=AsyncMock(), commit=AsyncMock(),
                                            rollback=AsyncMock()),
                         pausa_s=0, tagger_factory=lambda _db: _Tagger(resultados))
        self._archivos_falsos = list(archivos)

    async def _archivos(self, _issue_id):
        return self._archivos_falsos


def test_pendiente_y_marca():
    issue = _issue()
    assert _pendiente(issue) is True
    _marcar(issue, False)
    assert _pendiente(issue) is False and CLAVE_PENDIENTE not in issue.metadata_


@pytest.mark.asyncio
async def test_escrito_limpia_pendiente():
    issue = _issue()
    sincronizador = _Sincronizador([
        ResultadoEtiquetado("f1", "a.cbz", ESCRITO)])
    informe = InformeCola()
    await sincronizador.procesar_issue(issue, informe=informe)
    assert informe.escritos == 1 and _pendiente(issue) is False


@pytest.mark.asyncio
async def test_compartido_o_ausente_deja_pendiente():
    issue = _issue()
    sincronizador = _Sincronizador([
        ResultadoEtiquetado("f1", "a.cbz", SALTADO,
                            motivo="archivo compartido", advertencia="compartido")])
    informe = InformeCola()
    await sincronizador.procesar_issue(issue, informe=informe)
    assert informe.aplazados == 1 and _pendiente(issue) is True
