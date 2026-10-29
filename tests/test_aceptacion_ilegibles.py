# ruff: noqa: E501
"""#332 residual 4 — validación pura de la aceptación de ilegibles.

Sin BD: fija el contrato de `validar_informe`, la lectura estricta del registro y el significado
de `EstadoRegistro.completo`. La parte de persistencia y UI vive en `test_aceptacion_ilegibles_pg.py`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.services.aceptacion_adopcion import parsear_aceptacion, validar_informe
from zascarr.services.registro_biblioteca import EstadoRegistro, FaseRegistro


def _run(**over):
    base = dict(
        id=uuid4(),
        finished_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        error_count=0,
        details={"kind": "adoption", "unreadable": 3, "errors": []},
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestValidarInforme:

    def test_adopcion_terminada_sin_errores_y_con_tres_ilegibles_es_valida(self):
        run = _run()
        assert validar_informe(run, run.id, 3) is None

    def test_run_inexistente_no_se_puede_validar(self):
        assert validar_informe(None, uuid4(), 3) == "not_found"

    def test_otro_kind_no_es_adopcion(self):
        run = _run(details={"kind": "registro_incremental", "unreadable": 3})
        assert validar_informe(run, run.id, 3) == "incremental_run"

    def test_un_kind_audit_tampoco_es_adopcion(self):
        run = _run(details={"kind": "audit", "unreadable": 3})
        assert validar_informe(run, run.id, 3) == "incremental_run"

    def test_sin_cierre_no_esta_terminada(self):
        run = _run(finished_at=None)
        assert validar_informe(run, run.id, 3) == "not_terminated"

    def test_con_errores_no_es_aceptable(self):
        run = _run(error_count=1)
        assert validar_informe(run, run.id, 3) == "has_errors"

    def test_con_lista_de_errores_no_es_aceptable(self):
        run = _run(details={"kind": "adoption", "unreadable": 3, "errors": ["x"]})
        assert validar_informe(run, run.id, 3) == "has_errors"

    def test_cero_ilegibles_no_justifica_aceptar(self):
        run = _run(details={"kind": "adoption", "unreadable": 0})
        assert validar_informe(run, run.id, 0) == "zero_unreadable"

    def test_unreadable_no_entero_no_autoriza(self):
        run = _run(details={"kind": "adoption", "unreadable": "3"})
        assert validar_informe(run, run.id, 3) == "zero_unreadable"

    def test_unreadable_booleano_no_autoriza(self):
        run = _run(details={"kind": "adoption", "unreadable": True})
        assert validar_informe(run, run.id, 1) == "zero_unreadable"

    def test_count_distinto_no_cuadra(self):
        run = _run()
        assert validar_informe(run, run.id, 4) == "count_mismatch"

    def test_informe_que_no_es_el_ultimo_es_stale(self):
        run = _run()
        assert validar_informe(run, uuid4(), 3) == "stale_run"

    def test_stale_tiene_prioridad_sobre_kind(self):
        run = _run(details={"kind": "registro_incremental", "unreadable": 3})
        assert validar_informe(run, uuid4(), 3) == "stale_run"

    def test_sin_adopcion_previa_el_kind_sigue_mandando(self):
        run = _run(details={"kind": "registro_incremental", "unreadable": 3})
        assert validar_informe(run, None, 3) == "incremental_run"

    def test_lotes_sin_acreditar_no_permiten_aceptar(self):
        run = _run(details={"kind": "adoption", "unreadable": 3, "reverted": 1})
        assert validar_informe(run, run.id, 3) == "batch_unverified"

    def test_por_comprobar_tampoco_permite_aceptar(self):
        run = _run(details={"kind": "adoption", "unreadable": 3, "unknown": 2})
        assert validar_informe(run, run.id, 3) == "batch_unverified"


class TestLecturaEstrictaDelRegistro:

    def _valido(self, **over):
        base = {
            "count": 3,
            "accepted_at": "2026-10-29T10:00:00+00:00",
            "run_id": str(uuid4()),
            "auth_mode": "none",
        }
        base.update(over)
        return base

    def test_un_registro_completo_y_bien_tipado_se_lee(self):
        reg = parsear_aceptacion(self._valido())
        assert reg is not None and reg.count == 3 and reg.auth_mode == "none"

    @pytest.mark.parametrize("valor", [None, "false", 1, [], {}])
    def test_un_registro_que_no_es_dict_no_autoriza(self, valor):
        assert parsear_aceptacion(valor) is None

    @pytest.mark.parametrize("count", ["3", 3.0, True, 0, -1, 1_000_001])
    def test_count_invalido_no_autoriza(self, count):
        assert parsear_aceptacion(self._valido(count=count)) is None

    def test_fecha_no_parseable_no_autoriza(self):
        assert parsear_aceptacion(self._valido(accepted_at="ayer")) is None

    def test_fecha_sin_zona_no_autoriza(self):
        assert parsear_aceptacion(self._valido(accepted_at="2026-10-29T10:00:00")) is None

    def test_run_id_no_uuid_no_autoriza(self):
        assert parsear_aceptacion(self._valido(run_id="no-es-uuid")) is None

    def test_auth_mode_ausente_no_autoriza(self):
        reg = self._valido()
        reg.pop("auth_mode")
        assert parsear_aceptacion(reg) is None


class TestCompletoNoCambia:

    def test_completo_sigue_exigiendo_cero_ilegibles(self):
        estado = EstadoRegistro(fase=FaseRegistro.TERMINADO, ilegibles=3)
        assert estado.completo is False


class TestResponsiveYCss:

    def test_audit_acciones_es_solo_layout_y_se_apila_en_movil(self):
        from pathlib import Path
        css = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
        assert ".audit-acciones { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }" in css
        assert "@media (max-width: 480px)" in css
        bloque = css.split(".audit-acciones", 1)[1].split("}", 1)[0]
        assert "color" not in bloque and "background" not in bloque
