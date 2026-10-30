"""Criterio 6: la guarda de espacio no escribe, no borra y puede fallar."""

from __future__ import annotations

import pytest

from zascarr.utils.espacio import (
    MARGEN_BYTES,
    EspacioInsuficienteError,
    comprobar_espacio,
)


class TestComprobarEspacio:
    def test_suficiente_pasa(self, tmp_path):
        comprobar_espacio(tmp_path, 100, "guardar una portada", libre=100 + MARGEN_BYTES + 11)

    def test_justo_por_debajo_falla_con_cifras_y_accion(self, tmp_path):
        with pytest.raises(EspacioInsuficienteError) as exc:
            comprobar_espacio(tmp_path, 100, "guardar una portada", libre=100 + MARGEN_BYTES + 9)
        e = exc.value
        assert e.bytes_libres == 100 + MARGEN_BYTES + 9
        assert e.bytes_necesarios == 100
        assert e.contexto == "guardar una portada"
        assert "No hay espacio suficiente" in str(e)
        assert "Libera espacio" in str(e)
        assert "no ha borrado nada" in str(e)

    def test_margen_es_10_por_ciento_mas_64_mib(self, tmp_path):
        necesario = 100 * 1024 * 1024
        with pytest.raises(EspacioInsuficienteError) as exc:
            comprobar_espacio(tmp_path, necesario, "x", libre=necesario + MARGEN_BYTES)
        assert exc.value.margen == int(necesario * 0.10) + MARGEN_BYTES

    def test_ruta_inexistente_usa_el_padre(self, tmp_path):
        comprobar_espacio(tmp_path / "no" / "existe", 1, "x", libre=10**9)

    def test_negativo_es_error_de_programa(self, tmp_path):
        with pytest.raises(ValueError):
            comprobar_espacio(tmp_path, -1, "x", libre=10**9)
