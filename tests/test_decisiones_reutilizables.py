"""MIT-M7-US03 (#132-b): inventario de decisiones reutilizables (sin BD real)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.models import (
    EstadoAlias,
    EstadoRegla,
    OrigenAlias,
    OrigenRegla,
    TipoDestino,
    TipoSignificadoCarpeta,
)
from zascarr.services import alias_decisiones as alias_svc
from zascarr.services import correspondencias_contexto as corr_svc
from zascarr.services import decisiones_reutilizables as inv
from zascarr.services import declaraciones_carpeta as decl_svc
from zascarr.services.correspondencias_contexto import CorrespondenciaVista
from zascarr.services.declaraciones_carpeta import DeclaracionVista

AHORA = datetime(2026, 11, 11, 10, 0, tzinfo=UTC)


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, series):
        self._series = series
        self.llamadas = 0

    async def execute(self, *_a, **_k):
        self.llamadas += 1
        return _Resultado(self._series)


def _decl(origen=OrigenRegla.LOCAL, estado=EstadoRegla.ACTIVA, raiz="Superman",
          did=None):
    return DeclaracionVista(
        id=uuid4(), declaracion_id=did or uuid4(), version=2, contexto_raiz=raiz,
        incluir_descendientes=True, tipo_de_significado=TipoSignificadoCarpeta.AUTOR,
        origen=origen, estado=estado, vigente_desde=AHORA, vigente_hasta=None,
        procedencia={})


def _corr(origen=OrigenRegla.LOCAL, estado=EstadoRegla.ACTIVA, raiz="Superman",
          destino=None):
    return CorrespondenciaVista(
        id=uuid4(), correspondencia_id=uuid4(), version=1, supersedes_id=None,
        declaracion_version_id=uuid4(), contexto_raiz=raiz, incluir_descendientes=True,
        tipo_de_registro=None, destino_tipo=TipoDestino.SERIE,
        destino_id=destino or uuid4(), origen=origen, estado=estado,
        vigente_desde=AHORA, vigente_hasta=None)


def _aprendido(estado=EstadoAlias.PROPUESTO, series_id=None):
    return SimpleNamespace(
        id=uuid4(), pattern_norm="patrulla x", series_id=series_id or uuid4(),
        origen=OrigenAlias.APRENDIDO, estado=estado, version=1, scope_path=None,
        historial=[{"version": 1, "estado": estado.value, "motivo": "aprendizaje",
                    "fecha": "2026-11-11T10:00:00+00:00"}],
    )


def _importado(estado=EstadoAlias.PROPUESTO, series_id=None, scope=None):
    return SimpleNamespace(
        id=uuid4(), alias_id=uuid4(), patron_norm="patrulla x", series_id=series_id or uuid4(),
        origen=OrigenAlias.IMPORTADO, estado=estado, version=1, scope_path=scope,
        historial=[], procedencia={})


def _montar(monkeypatch, *, declaraciones=(), correspondencias=(), aprendidos=(),
            importados=()):
    ids = {a.series_id for a in aprendidos} | {i.series_id for i in importados}
    series = [SimpleNamespace(id=sid, title=f"Serie {n}") for n, sid in enumerate(ids)]
    async def _decls(*_a, **_k):
        return list(declaraciones)
    async def _corrs(*_a, **_k):
        return list(correspondencias)
    async def _aprend(*_a, **_k):
        return list(aprendidos)
    async def _import(*_a, **_k):
        return list(importados)
    monkeypatch.setattr(decl_svc, "listar", _decls)
    monkeypatch.setattr(corr_svc, "listar", _corrs)
    monkeypatch.setattr(alias_svc, "listar_aprendidos", _aprend)
    monkeypatch.setattr(alias_svc, "listar_importados", _import)
    return _Sesion(series)


@pytest.mark.asyncio
async def test_inventario_muestra_tipos_estados_efectos_y_acciones(monkeypatch):
    sid = uuid4()
    sesion = _montar(monkeypatch, declaraciones=[_decl()],
                     correspondencias=[_corr()],
                     aprendidos=[_aprendido(series_id=sid)],
                     importados=[_importado(series_id=sid)])
    filas = await inv.listar_decisiones(sesion)
    tipos = {f.tipo for f in filas}
    assert tipos == set(inv.TIPOS)
    aprendido = next(f for f in filas if f.tipo == "alias_aprendido")
    assert aprendido.estado_es == "Pendiente de activar"
    assert "No se aplica" in aprendido.efectos
    assert "activar" in aprendido.acciones
    assert aprendido.precedencia.startswith("Capa 3")
    importado = next(f for f in filas if f.tipo == "alias_importado")
    assert importado.precedencia.startswith("Capa 2")


@pytest.mark.asyncio
async def test_filtros_por_tipo_estado_origen_y_carpeta(monkeypatch):
    sesion = _montar(monkeypatch, declaraciones=[_decl(raiz="Superman")],
                     aprendidos=[_aprendido(estado=EstadoAlias.ACTIVO)])
    assert len(await inv.listar_decisiones(sesion)) == 2
    assert len(await inv.listar_decisiones(sesion, tipo="declaracion")) == 1
    assert len(await inv.listar_decisiones(sesion, estado="activo")) == 1
    assert len(await inv.listar_decisiones(sesion, origen="aprendido")) == 1
    assert len(await inv.listar_decisiones(sesion, carpeta="superman")) == 1
    assert await inv.listar_decisiones(sesion, carpeta="inexistente") == []


@pytest.mark.asyncio
async def test_conflictos_visibles_sin_elegir(monkeypatch):
    raiz = "Superman"
    sesion = _montar(
        monkeypatch,
        declaraciones=[_decl(raiz=raiz), _decl(origen=OrigenRegla.IMPORTACION, raiz=raiz)],
        aprendidos=[_aprendido(estado=EstadoAlias.ACTIVO)],
        importados=[_importado(estado=EstadoAlias.ACTIVO, scope=raiz)],
    )
    filas = await inv.listar_decisiones(sesion)
    decl = next(f for f in filas if f.tipo == "declaracion" and f.origen == "local")
    assert any("Otra declaración" in c for c in decl.conflictos)
    aprendido = next(f for f in filas if f.tipo == "alias_aprendido")
    assert any("decisiones locales" in c for c in aprendido.conflictos)
    importado = next(f for f in filas if f.tipo == "alias_importado")
    assert any("decisión local" in c for c in importado.conflictos)


def test_las_importadas_no_ofrecen_acciones():
    d = inv.Decision(tipo="declaracion", id=uuid4(), fila_id=uuid4(),
                     origen="importacion", estado="activa", version=1,
                     contexto="X", alcance="X", destino="—", efectos="x",
                     precedencia="y", es_importada=True)
    assert d.acciones == ()


@pytest.mark.asyncio
async def test_los_titulos_se_piden_en_una_sola_consulta(monkeypatch):
    """Benchmark §5: 4 consultas de fuentes + 1 de títulos, sin N+1."""
    sesion = _montar(monkeypatch, declaraciones=[_decl()],
                     aprendidos=[_aprendido(), _aprendido(estado=EstadoAlias.ACTIVO)],
                     importados=[_importado(), _importado(estado=EstadoAlias.ACTIVO)])
    await inv.listar_decisiones(sesion)
    assert sesion.llamadas == 1
