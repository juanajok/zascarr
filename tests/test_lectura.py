# ruff: noqa: E501
"""#150 BL-C3: servicio de lectura, validación e idempotencia."""
from __future__ import annotations

from uuid import uuid4

import pytest

from zascarr.models import ReadingProgress, ReadingStatus
from zascarr.services.lectura import (
    EstadoInvalidoError,
    IssueNoEncontradoError,
    NotaInvalidaError,
    ValoracionInvalidaError,
    lectura_de,
    marcar,
)


class _Res:
    def __init__(self, valor=None):
        self._valor = valor

    def scalar_one_or_none(self):
        return self._valor


class _DB:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.added = []
        self.commits = 0

    async def execute(self, _s):
        return self.respuestas.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


def _progress(**extra):
    datos = dict(issue_id=uuid4(), status=ReadingStatus.UNREAD, current_page=5,
                 rating=None, notes=None, started_at=None, completed_at=None)
    datos.update(extra)
    return ReadingProgress(**datos)


@pytest.mark.asyncio
async def test_marca_los_tres_estados_y_completed_at():
    issue_id = uuid4()
    db = _DB([_Res(issue_id), _Res(None)])
    r = await marcar(db, issue_id, "completed", rating=4, nota="Muy bueno")
    assert r.estado is ReadingStatus.COMPLETED and r.rating == 4
    assert r.completed_at is not None and db.added and db.commits == 1

    p = _progress(issue_id=issue_id, status=ReadingStatus.COMPLETED)
    db = _DB([_Res(issue_id), _Res(p)])
    r = await marcar(db, issue_id, "reading", rating=3, nota="Sigo")
    assert r.estado is ReadingStatus.READING and r.completed_at is None
    assert p.rating == 3 and p.notes == "Sigo"


@pytest.mark.asyncio
async def test_desmarcar_leido_conserva_rating_y_nota_y_current_page():
    issue_id = uuid4()
    p = _progress(issue_id=issue_id, status=ReadingStatus.COMPLETED,
                  rating=5, notes="Excelente", completed_at="2026-11-09T10:00:00+00:00")
    db = _DB([_Res(issue_id), _Res(p)])
    r = await marcar(db, issue_id, "unread")
    assert r.estado is ReadingStatus.UNREAD
    assert r.rating == 5 and r.nota == "Excelente" and r.completed_at is None
    assert p.current_page == 5


@pytest.mark.asyncio
async def test_repetir_la_misma_marca_no_duplica():
    issue_id = uuid4()
    p = _progress(issue_id=issue_id)
    db = _DB([_Res(issue_id), _Res(p)])
    await marcar(db, issue_id, "reading", rating=4, nota="ok")
    db2 = _DB([_Res(issue_id), _Res(p)])
    r2 = await marcar(db2, issue_id, "reading", rating=4, nota="ok")
    assert r2.estado is ReadingStatus.READING
    assert db2.added == [] and p.current_page == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("rating", [0, 6, -1, "x"])
async def test_valoracion_fuera_de_rango(rating):
    db = _DB([])
    with pytest.raises(ValoracionInvalidaError):
        await marcar(db, uuid4(), "reading", rating=rating)


@pytest.mark.asyncio
async def test_nota_larga_y_estado_no_expuesto():
    db = _DB([])
    with pytest.raises(NotaInvalidaError):
        await marcar(db, uuid4(), "reading", nota="x" * 281)
    db = _DB([])
    with pytest.raises(EstadoInvalidoError):
        await marcar(db, uuid4(), "dropped")


@pytest.mark.asyncio
async def test_issue_inexistente():
    db = _DB([_Res(None)])
    with pytest.raises(IssueNoEncontradoError):
        await marcar(db, uuid4(), "reading")


@pytest.mark.asyncio
async def test_issue_de_otra_serie_404():
    db = _DB([_Res(None)])
    with pytest.raises(IssueNoEncontradoError):
        await marcar(db, uuid4(), "reading", series_id=uuid4())


@pytest.mark.asyncio
async def test_lectura_de_no_existe_es_none():
    db = _DB([_Res(None)])
    assert await lectura_de(db, uuid4()) is None


@pytest.mark.asyncio
async def test_recuento_por_series_no_por_numeros():
    from zascarr.services.lectura import recuento_lectura
    ids = [uuid4() for _ in range(12)]

    class _Count:
        def __init__(self, n):
            self._n = n

        def scalar_one(self):
            return self._n

    class _DBRecuento:
        def __init__(self, n):
            self._n = n

        async def execute(self, _s):
            return _Count(self._n)

    assert await recuento_lectura(_DBRecuento(3), ids, "si") == "3 de 12 series con algún número leído."
    assert await recuento_lectura(_DBRecuento(2), ids, "leyendo") == "2 de 12 series con algún número en lectura."
    assert await recuento_lectura(_DBRecuento(9), ids, "no") == "3 de 12 series sin ningún número leído."
