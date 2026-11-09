# ruff: noqa: E501
"""#129 C: retirar la asociación con historial, idempotencia y R2. Sin red."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.models import MetadataSource
from zascarr.services.retirar_asociacion import (
    RetirarAsociacionDeFuente,
    huella_de_asociacion_actual,
)
from zascarr.services.tokens_revision import (
    MAX_TOKEN_RETIRAR_ASOCIACION,
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
    verificar_token_retirar_asociacion,
)

SECRETO = "x" * 32


class _Res:
    def __init__(self, *, scalar=None, rowcount=0, first=None):
        self._scalar = scalar
        self.rowcount = rowcount
        self._first = first

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._first


class _DB:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.valores = None

    async def execute(self, statement, *_a, **_k):
        if hasattr(statement, "_values"):
            self.valores = {getattr(k, "name", k): getattr(v, "value", v)
                            for k, v in statement._values.items()}
        return self.respuestas.pop(0) if self.respuestas else _Res()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        self.added.clear()


def _entrada(fuente="gcd", id_externo="123", operacion=None, deshecho=None):
    e = {"version": 1, "fuente": fuente, "id_externo": id_externo, "entidad": "serie",
         "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
         "operacion_id": operacion or str(uuid4()), "origen": "confirmada", "modo": "busqueda"}
    if deshecho:
        e["deshecho"] = deshecho
    return e


def _serie(**extra):
    datos = dict(id=uuid4(), title="The Wicked + The Divine", start_year=2014,
                 comic_vine_id=1, anilist_id=None, tebeosfera_slug=None, gcd_id=123,
                 metadata_={"asociaciones": [_entrada()]}, locked_fields=[],
                 metadata_source="comic_vine")
    datos.update(extra)
    return SimpleNamespace(**datos)


def _token(serie, *, op=None, fuente="gcd", id_externo="123", ahora=None):
    firmada = RetirarAsociacionFirmada(
        version=1, entidad="serie", fuente=fuente, id_externo=id_externo,
        huella=huella_de_asociacion_actual(serie, fuente),
        operacion=op or str(uuid4()), serie_id=str(serie.id))
    return crear_token_retirar_asociacion(firmada, SECRETO, ahora=ahora)


def _servicio(db, *, ahora=None):
    return RetirarAsociacionDeFuente(db, secret=SECRETO, ahora=ahora)


class TestPreview:
    @pytest.mark.asyncio
    async def test_preview_no_escribe_y_emite_token(self):
        serie = _serie()
        db = _DB([_Res(scalar=serie)])
        previa = await _servicio(db).previsualizar(serie.id, MetadataSource.GCD)
        assert previa.estado == "ok" and previa.token
        assert len(previa.token) <= MAX_TOKEN_RETIRAR_ASOCIACION
        assert verificar_token_retirar_asociacion(previa.token, SECRETO).id_externo == "123"
        assert db.added == [] and db.valores is None

    @pytest.mark.asyncio
    async def test_preview_sin_asociacion_es_ya_retirada(self):
        serie = _serie(gcd_id=None)
        db = _DB([_Res(scalar=serie)])
        previa = await _servicio(db).previsualizar(serie.id, MetadataSource.GCD)
        assert previa.estado == "ya_retirada" and previa.token is None


class TestConfirmar:
    @pytest.mark.asyncio
    async def test_retira_columna_y_append_historial(self):
        serie = _serie()
        op = str(uuid4())
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado == "retirada" and resultado.repetida is False
        assert db.valores["gcd_id"] is None
        assert db.valores["metadata"]["asociaciones"] == []
        hist = db.valores["metadata"]["asociaciones_historial"]
        assert len(hist) == 1
        assert hist[0]["deshecho"]["operacion_id"] == op and hist[0]["previo"]["fuente"] == "gcd"
        assert len(db.added) == 1 and db.commits == 1
        assert serie.metadata_source == "comic_vine" and serie.locked_fields == []

    @pytest.mark.asyncio
    async def test_repetir_con_comprobante_no_duplica(self):
        serie = _serie()
        op = str(uuid4())
        informe = {"version": 1, "tipo": "retirar_asociacion", "operacion_id": op,
                   "series_id": str(serie.id), "resultado": "retirada", "motivo": None,
                   "mensaje": "retirada", "fuente": "gcd", "id_externo": "123"}
        db = _DB([_Res(), _Res(scalar=SimpleNamespace(resultado=informe))])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado == "ya_retirada" and resultado.repetida is True
        assert db.added == [] and db.valores is None

    @pytest.mark.asyncio
    async def test_si_la_columna_cambio_no_retira(self):
        serie = _serie(gcd_id=999)
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "propuesta_desactualizada"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_historial_con_operacion_es_ya_retirada(self):
        serie = _serie()
        op = str(uuid4())
        serie.metadata_ = {"asociaciones": [], "asociaciones_historial": [_entrada(
            operacion=str(uuid4()), deshecho={"operacion_id": op, "fecha": "2026-11-09T10:00:00+00:00",
                                              "motivo": "retirada"})]}
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado == "ya_retirada"
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_token_caducado_sin_evidencia(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db, ahora=10**10).confirmar(_token(serie, ahora=10**9))
        assert resultado.motivo == "token_caducado"
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_columna_null_sin_historial_es_ya_retirada(self):
        serie = _serie(gcd_id=None)
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "ya_retirada"
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_entrada_sin_procedencia_se_retira_igual(self):
        serie = _serie(metadata_={})
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "retirada"
        hist = db.valores["metadata"]["asociaciones_historial"][0]
        assert hist["previo"]["procedencia"] == "desconocida"
        assert db.valores["gcd_id"] is None
