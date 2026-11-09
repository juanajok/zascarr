# ruff: noqa: E501
"""#129 B: confirmación idempotente, R2, H9/H16 y resultado en pantalla. Sin red."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.services.asociacion_fuente import (
    MENSAJE_CADUCADO_SIN_APLICAR,
    MENSAJE_CADUCADO_SIN_INFORME,
    AsociacionDeFuente,
)
from zascarr.services.asociar_fuente import CandidataComparada, huella_de_asociacion
from zascarr.services.tokens_revision import (
    AsociacionFirmada,
    crear_token_asociacion,
    verificar_token_asociacion,
)
from zascarr.services.vinculacion import TokenInvalidoError

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
        self.llamadas = 0

    async def execute(self, statement, *_a, **_k):
        self.llamadas += 1
        if hasattr(statement, "_values"):
            self.valores = {getattr(k, "name", k): getattr(v, "value", v)
                            for k, v in statement._values.items()}
        respuesta = self.respuestas.pop(0) if self.respuestas else _Res()
        return respuesta

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1
        self.added.clear()


def _serie(**extra):
    datos = dict(id=uuid4(), title="The Wicked + The Divine", start_year=2014,
                 comic_vine_id=1, anilist_id=None, tebeosfera_slug=None, gcd_id=None,
                 tradition=None, metadata_={}, locked_fields=[], metadata_source="comic_vine")
    datos.update(extra)
    return SimpleNamespace(**datos)


def _token(serie, *, id_externo="123", fuente="gcd", kind="collection", op=None,
           ahora=None):
    candidata = CandidataComparada(
        titulo="The Wicked + The Divine", anio=2014, editorial=None, pais=None, idioma=None,
        id_externo=id_externo, sitio_url="https://www.comics.org/series/123/",
        tradicion=None, kind=kind, fuente=fuente)
    firmada = AsociacionFirmada(
        version=1, entidad="serie", kind=kind, fuente=fuente, id_externo=id_externo,
        titulo=candidata.titulo, anio=candidata.anio, sitio_url=candidata.sitio_url,
        huella=huella_de_asociacion(serie, candidata),
        operacion=op or str(uuid4()), serie_id=str(serie.id))
    return crear_token_asociacion(firmada, SECRETO, ahora=ahora)


def _servicio(db, *, ahora=None, encendida=True):
    import zascarr.services.asociacion_fuente as modulo
    modulo_get = lambda: SimpleNamespace(  # noqa: E731
        gcd_enabled=encendida, comicvine_enabled=True, anilist_enabled=True,
        tebeosfera_enabled=True)
    modulo.get_settings = modulo_get
    return AsociacionDeFuente(db, secret=SECRETO, ahora=ahora)


class TestConfirmar:
    @pytest.mark.asyncio
    async def test_confirma_columna_jsonb_y_comprobante(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "asociada" and resultado.repetida is False
        assert resultado.efectos["campos_serie"] == 1
        assert db.valores is not None and db.valores["gcd_id"] == 123
        entradas = db.valores["metadata"]["asociaciones"]
        assert entradas[-1]["fuente"] == "gcd" and entradas[-1]["operacion_id"]
        assert entradas[-1]["origen"] == "confirmada"
        assert serie.metadata_source == "comic_vine" and serie.locked_fields == []
        assert len(db.added) == 1 and db.commits == 1

    @pytest.mark.asyncio
    async def test_repeticion_con_comprobante_no_escribe(self):
        serie = _serie()
        op = str(uuid4())
        informe = {"version": 1, "tipo": "asociar_fuente", "operacion_id": op,
                   "series_id": str(serie.id), "resultado": "asociada", "motivo": None,
                   "mensaje": "Ficha asociada.", "repetida": False, "fuente": "gcd",
                   "id_externo": "123", "titulo": serie.title, "efectos": {}}
        previo = SimpleNamespace(resultado=informe)
        db = _DB([_Res(), _Res(scalar=previo)])
        resultado = await _servicio(db).confirmar(_token(serie, op=op))
        assert resultado.resultado == "asociada" and resultado.repetida is True
        assert db.added == [] and db.valores is None and db.commits == 1

    @pytest.mark.asyncio
    async def test_otro_id_de_la_misma_fuente_no_sobrescribe(self):
        serie = _serie(gcd_id=999)
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie, id_externo="123"))
        assert resultado.motivo == "ya_tiene_identidad_en_esa_fuente"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_id_de_otra_serie_es_conflicto_sin_reasignar(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(first=SimpleNamespace(title="Otra serie"))])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "conflicto_identificador"
        assert resultado.otra_serie == "Otra serie"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_token_caducado_con_evidencia_activa_es_repetida(self):
        serie = _serie()
        op = str(uuid4())
        serie.metadata_ = {"asociaciones": [{
            "version": 1, "fuente": "gcd", "id_externo": "123", "entidad": "serie",
            "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
            "operacion_id": op, "origen": "confirmada", "modo": "busqueda"}]}
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db, ahora=10**10).confirmar(
            _token(serie, op=op, ahora=10**9))
        assert resultado.resultado == "asociada" and resultado.repetida is True
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_token_caducado_sin_evidencia_no_escribe(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db, ahora=10**10).confirmar(
            _token(serie, ahora=10**9))
        assert resultado.motivo == "token_caducado"
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_saga_o_entidad_no_asociable(self):
        serie = _serie()
        db = _DB([_Res(), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie, kind="saga"))
        assert resultado.motivo == "propuesta_no_asociable"
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_fuente_apagada_guarda_sin_red_y_avisa(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db, encendida=False).confirmar(_token(serie))
        assert resultado.resultado == "asociada"
        assert "apagada" in (resultado.aviso or "").lower()
        assert len(db.added) == 1

    @pytest.mark.asyncio
    async def test_integrity_error_rollback_y_conflicto(self):
        serie = _serie()

        class _DBIntegrity(_DB):
            async def flush(self):
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError("INSERT", {}, Exception("unique"))

        db = _DBIntegrity([_Res(), _Res(), _Res(scalar=serie), _Res(), _Res(rowcount=1)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "conflicto_identificador"
        assert db.rollbacks == 1 and db.added == []


def test_huella_y_token_redondean_entidad_kind():
    serie = _serie()
    token = _token(serie, kind="collection")
    firmada = verificar_token_asociacion(token, SECRETO)
    assert firmada is not None and firmada.entidad == "serie"
    assert firmada.kind == "collection"


def _entrada(fuente="gcd", id_externo="123", *, op=None, extra=None):
    entrada = {
        "version": 1, "fuente": fuente, "id_externo": id_externo, "entidad": "serie",
        "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
        "operacion_id": op or str(uuid4()), "origen": "confirmada", "modo": "busqueda",
    }
    if extra:
        entrada.update(extra)
    return entrada


class TestR2YValidacion:

    @pytest.mark.asyncio
    async def test_ya_asociada_no_escribe(self):
        serie = _serie(gcd_id=123)
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "ya_asociada" and resultado.repetida is False
        assert resultado.efectos["campos_serie"] == 0
        assert db.valores is None and db.added == [] and db.commits == 1

    @pytest.mark.asyncio
    async def test_serie_esperada_distinta_no_consulta_ni_escribe(self):
        serie = _serie()
        otra = uuid4()
        db = _DB([])
        with pytest.raises(TokenInvalidoError, match="otra serie"):
            await _servicio(db).confirmar(_token(serie), serie_esperada=otra)
        assert db.llamadas == 0 and db.commits == 0

    @pytest.mark.asyncio
    async def test_token_invalido_no_consulta_ni_escribe(self):
        db = _DB([])
        with pytest.raises(TokenInvalidoError):
            await _servicio(db).confirmar("no-es-un-token")
        assert db.llamadas == 0 and db.commits == 0

    @pytest.mark.asyncio
    async def test_token_caducado_dentro_de_retencion_no_afirma_lo_que_no_sabe(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        # Caducó hace 1 s (TTL 900), dentro de las 24 h de retención: no llegó a aplicarse.
        resultado = await _servicio(db, ahora=10**9 + 901).confirmar(
            _token(serie, ahora=10**9))
        assert resultado.motivo == "token_caducado"
        assert resultado.mensaje == MENSAJE_CADUCADO_SIN_APLICAR
        assert "no se ha asociado nada" in resultado.mensaje
        assert db.valores is None

    @pytest.mark.asyncio
    async def test_token_caducado_pasada_la_retencion_no_afirma_que_no_cambio_nada(self):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db, ahora=10**9 + 900 + 25 * 3600).confirmar(
            _token(serie, ahora=10**9))
        assert resultado.motivo == "token_caducado"
        assert resultado.mensaje == MENSAJE_CADUCADO_SIN_INFORME
        assert "no se ha cambiado nada" not in resultado.mensaje.lower()
        assert "no se puede saber" in resultado.mensaje

    @pytest.mark.asyncio
    async def test_jsonb_corrupto_es_procedencia_invalida(self):
        serie = _serie(metadata_={"asociaciones": "no-es-una-lista"})
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "procedencia_invalida"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_entrada_con_campo_desconocido_es_invalida(self):
        serie = _serie(metadata_={"asociaciones": [
            _entrada("comic_vine", "1", extra={"campo_desconocido": "x"})]})
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "procedencia_invalida"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_entrada_incompleta_de_otra_fuente_no_se_propaga(self):
        incompleta = {"version": 1, "fuente": "comic_vine", "id_externo": "1"}
        serie = _serie(metadata_={"asociaciones": [incompleta]})
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "procedencia_invalida"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_entrada_valida_de_otra_fuente_se_conserva(self):
        serie = _serie(metadata_={"asociaciones": [_entrada("comic_vine", "1")]})
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res(first=None), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "asociada"
        fuentes = [e["fuente"] for e in db.valores["metadata"]["asociaciones"]]
        assert fuentes == ["comic_vine", "gcd"]
