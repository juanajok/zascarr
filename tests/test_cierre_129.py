"""#129 cierre: evidencia de historial, huella C y FOR UPDATE."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b import _DB, _Res, _serie, _servicio, _token
from tests.test_retirar_asociacion_c import (
    _DB as _DBC,
)
from tests.test_retirar_asociacion_c import (
    _Res as _ResC,
)
from tests.test_retirar_asociacion_c import (
    _serie as _serie_c,
)
from tests.test_retirar_asociacion_c import (
    _token as _token_c,
)
from zascarr.services.retirar_asociacion import RetirarAsociacionDeFuente


class _DBStatements(_DB):
    def __init__(self, respuestas):
        super().__init__(respuestas)
        self.statements = []

    async def execute(self, statement, *_a, **_k):
        self.statements.append(statement)
        return await super().execute(statement, *_a, **_k)


def _entrada(fuente="gcd", id_externo="123", op=None, deshecho=True):
    e = {"version": 1, "fuente": fuente, "id_externo": id_externo, "entidad": "serie",
         "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
         "operacion_id": op or str(uuid4()), "origen": "confirmada", "modo": "busqueda"}
    if deshecho:
        e["deshecho"] = {"operacion_id": str(uuid4()),
                         "fecha": "2026-11-09T11:00:00+00:00", "motivo": "retirada"}
    return e


class TestEvidenciaHistorialB:
    @pytest.mark.asyncio
    async def test_historial_invalido_no_es_ya_retirada(self):
        serie = _serie(gcd_id=123)
        op = str(uuid4())
        serie.metadata_ = {"asociaciones": [], "asociaciones_historial": [{"operacion_id": op}]}
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado != "ya_retirada"
        assert resultado.resultado == "ya_asociada"

    @pytest.mark.asyncio
    async def test_historial_valido_si_es_ya_retirada_sin_escribir(self):
        serie = _serie(gcd_id=None)
        op = str(uuid4())
        serie.metadata_ = {"asociaciones": [], "asociaciones_historial": [_entrada(op=op)]}
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado == "ya_retirada"
        assert db.valores is None and db.added == []


class TestHuellaC:
    @pytest.mark.asyncio
    async def test_cambia_solo_metadata_sin_tocar_columna_es_desactualizada(self):
        serie = _serie_c()
        token = _token_c(serie)
        serie.metadata_ = {"asociaciones": []}       # la columna gcd_id sigue en 123
        db = _DBC([_ResC(), _ResC(), _ResC(scalar=serie), _ResC(rowcount=1), _ResC()])
        resultado = await RetirarAsociacionDeFuente(
            db, secret="x" * 32).confirmar(token)
        assert resultado.motivo == "propuesta_desactualizada"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_for_update_de_c_en_la_sentencia(self):
        serie = _serie_c()
        db = _DBStatements([_Res(), _Res(), _Res(scalar=serie), _Res(rowcount=1), _Res()])
        await RetirarAsociacionDeFuente(db, secret="x" * 32).confirmar(_token_c(serie))
        assert any(getattr(s, "_for_update_arg", None) is not None for s in db.statements)
