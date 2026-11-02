"""Criterio 4: clasificación del inventario, sin estados inventados."""

from __future__ import annotations

import uuid

import pytest

from zascarr.services.operaciones import (
    _clave_candado,
    clasificar_alta,
    clasificar_asignacion,
    clasificar_vinculacion,
)


class TestClasificarAsignacion:
    def test_estados_historicos(self):
        assert clasificar_asignacion("limpiada", en_curso=False) == "completada"
        assert clasificar_asignacion("cancelada", en_curso=False) == "fallida"

    def test_viva_sin_candado_es_recuperable(self):
        assert clasificar_asignacion("preparada", en_curso=False) == "recuperable"
        assert clasificar_asignacion("confirmada", en_curso=False) == "recuperable"

    def test_viva_con_candado_es_en_curso(self):
        assert clasificar_asignacion("preparada", en_curso=True) == "en_curso"

    def test_estado_inventado_no_se_clasifica_como_completada(self):
        with pytest.raises(ValueError):
            clasificar_asignacion("inventado", en_curso=False)


class TestClasificarAlta:
    def test_creada_y_deshecha(self):
        assert clasificar_alta("creada") == "completada"
        assert clasificar_alta("deshecha") == "no_aplica"

    def test_desconocida(self):
        with pytest.raises(ValueError):
            clasificar_alta("otra")


class TestClasificarVinculacion:
    @pytest.mark.parametrize(
        ("global_", "esperado"),
        [
            ("vinculados_todos", "completada"),
            ("vinculados_parcialmente", "parcial"),
            ("nada_vinculado", "sin_efecto"),
        ],
    )
    def test_globales(self, global_, esperado):
        assert clasificar_vinculacion(global_) == esperado

    def test_desconocido(self):
        with pytest.raises(ValueError):
            clasificar_vinculacion("otra")


def test_la_clave_del_candado_es_la_misma_del_servicio():
    op = uuid.UUID("00000000-0000-0000-0000-000000000101")
    clave = op.int & 0x7FFF_FFFF_FFFF_FFFF
    assert _clave_candado(op) == (clave >> 32, clave & 0xFFFFFFFF)


def test_la_ruta_get_operaciones_esta_registrada():
    from zascarr.main import app

    assert "/api/operaciones" in app.openapi()["paths"]


class TestResumenClasificaLoDesconocido:
    """#123 (QA, A3 de #385): un estado fuera del enum cuenta como «desconocida», no como completada ni rompe la petición."""

    @pytest.mark.asyncio
    async def test_estados_inventados_van_a_desconocida(self, monkeypatch):
        import zascarr.services.operaciones as ops

        async def sin_candados(_db):
            return set()

        async def contar(_db, columna):
            nombre = str(columna)
            if "AsignacionOperacion.estado" in nombre:
                return {"limpiada": 2, "rara": 3}
            if "AltaOperacion.estado" in nombre:
                return {"creada": 1, "rarisima": 4}
            return {"vinculados_todos": 5, "nada_vinculado": 1, None: 2, "otra": 1}

        class Resultado:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                return self

            def all(self):
                return []

            def one(self):
                return (0, 0)

        class Db:
            async def execute(self, *_a, **_k):
                return Resultado()

        monkeypatch.setattr(ops, "_candados", sin_candados)
        monkeypatch.setattr(ops, "_contar_por", contar)
        r = await ops.resumen_operaciones(Db())
        assert r["asignacion"]["completada"] == 2 and r["asignacion"]["desconocida"] == 3
        assert r["asignacion"]["total"] == 5
        assert r["alta"]["completada"] == 1 and r["alta"]["desconocida"] == 4 and r["alta"]["total"] == 5
        assert r["vinculacion"]["completada"] == 5 and r["vinculacion"]["sin_efecto"] == 1
        assert r["vinculacion"]["desconocida"] == 3 and r["vinculacion"]["total"] == 9
