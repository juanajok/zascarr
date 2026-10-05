"""
tests/test_primeros_pasos.py — `services/primeros_pasos.py` (V4): función pura, matriz de estados.

Lo que se fija aquí es lo que la épica pide no volver a hacer: no marcar «hecho» sin un hecho
observado, no confundir mirar el disco (informe) con registrar la biblioteca (adopción), y no
afirmar cifras sin decir de dónde salen.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from zascarr.services.library_adopter import EstadoAdopcion
from zascarr.services.primeros_pasos import (
    ClavePaso,
    EstadoInicio,
    EstadoPaso,
    InformeDisco,
    calcular_primeros_pasos,
    fecha_llana,
)

INFORME = InformeDisco(fecha=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
                       archivos_leidos=1542, archivos_comparados=432)


def estado(**cambios) -> EstadoInicio:
    base = EstadoInicio(
        adopcion=EstadoAdopcion.SIN_TEBEOS, archivos_registrados=0, archivos_sin_clasificar=0,
        series_seguidas=0, informe=None, aviso_legal_aceptado=False, hay_fuente_de_busqueda=False,
    )
    return replace(base, **cambios)


def paso(res, clave: ClavePaso):
    return next((p for p in res.pasos if p.clave is clave), None)


class TestVacio:

    def test_instalacion_nueva_sin_tebeos_no_marca_nada_como_hecho(self):
        res = calcular_primeros_pasos(estado())
        assert res.hechos == 0
        assert paso(res, ClavePaso.BIBLIOTECA).estado is EstadoPaso.BLOQUEADO
        assert paso(res, ClavePaso.REVISAR).estado is EstadoPaso.BLOQUEADO
        assert not res.completo

    def test_sin_nada_obligatorio_que_hacer_el_principal_es_un_opcional_con_enlace(self):
        res = calcular_primeros_pasos(estado())
        assert res.principal.clave is ClavePaso.SERIES
        assert res.principal.enlace == "/ui/descubrir"

    def test_el_paso_bloqueado_explica_por_que_y_no_ofrece_boton(self):
        p = paso(calcular_primeros_pasos(estado()), ClavePaso.BIBLIOTECA)
        assert "No hemos encontrado tebeos" in p.detalle
        assert p.enlace is None and p.accion is None


class TestAdopcionYAuditoria:

    def test_pendiente_es_el_siguiente_y_el_principal(self):
        res = calcular_primeros_pasos(estado(adopcion=EstadoAdopcion.PENDIENTE))
        p = paso(res, ClavePaso.BIBLIOTECA)
        assert p.estado is EstadoPaso.SIGUIENTE and res.principal is p
        assert p.enlace == "/ui/auditoria"

    def test_un_informe_no_equivale_a_biblioteca_registrada(self):
        """Mirar el disco (auditoría) y registrar la biblioteca (adopción) son hechos distintos."""
        res = calcular_primeros_pasos(estado(adopcion=EstadoAdopcion.PENDIENTE, informe=INFORME))
        p = paso(res, ClavePaso.BIBLIOTECA)
        assert p.estado is EstadoPaso.SIGUIENTE
        assert "Ya miraste qué hay repetido el 3 de octubre de 2026" in p.detalle
        assert "1542 leídos, 432 comparados" in p.detalle

    def test_sin_informe_no_se_afirma_ninguna_comparacion(self):
        res = calcular_primeros_pasos(estado(adopcion=EstadoAdopcion.PENDIENTE))
        detalle = paso(res, ClavePaso.BIBLIOTECA).detalle
        assert "comparados" not in detalle
        assert "Antes puedes ver qué hay repetido" in detalle

    def test_adopcion_hecha_sin_informe_es_hecho_y_no_inventa_comparados(self):
        res = calcular_primeros_pasos(
            estado(adopcion=EstadoAdopcion.HECHA, archivos_registrados=1542))
        p = paso(res, ClavePaso.BIBLIOTECA)
        assert p.estado is EstadoPaso.HECHO
        assert "1542 tebeos registrados" in p.detalle
        assert "comparados" not in p.detalle
        assert p.accion == "Buscar repetidos"

    def test_adopcion_hecha_con_informe_cita_fecha_y_cifra_del_informe(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=1542, informe=INFORME))
        p = paso(res, ClavePaso.BIBLIOTECA)
        assert "432 comparados a fondo el 3 de octubre de 2026" in p.detalle
        assert p.accion == "Ver duplicados"

    def test_adopcion_hecha_que_no_registro_nada_no_presume_de_tebeos(self):
        p = paso(calcular_primeros_pasos(estado(adopcion=EstadoAdopcion.HECHA)),
                 ClavePaso.BIBLIOTECA)
        assert p.estado is EstadoPaso.HECHO
        assert "no se registró ningún tebeo" in p.detalle

    def test_informe_sin_adopcion_no_marca_hecho_el_paso_de_biblioteca(self):
        for adopcion in (EstadoAdopcion.PENDIENTE, EstadoAdopcion.SIN_TEBEOS):
            res = calcular_primeros_pasos(estado(adopcion=adopcion, informe=INFORME))
            assert paso(res, ClavePaso.BIBLIOTECA).estado is not EstadoPaso.HECHO

    def test_catalogo_previo_ofrece_registrar_como_accion_consciente(self):
        """DECISIÓN CAMBIADA a propósito (2026-10-05). V4 no ofrecía registrar con catálogo previo;
        así un coleccionista con alguna serie dada de alta no podía incorporar sus archivos.
        Ahora se ofrece, dice que lo existente se conserva y no promete mover nada."""
        p = paso(calcular_primeros_pasos(estado(adopcion=EstadoAdopcion.CATALOGO_PREVIO)),
                 ClavePaso.BIBLIOTECA)
        assert p is not None and p.estado is EstadoPaso.SIGUIENTE and p.enlace == "/ui/auditoria"
        assert "se conservan" in p.detalle and "no mueve, renombra ni borra nada" in p.detalle
        assert "Antes de empezar verás cuántos son" in p.detalle   # inventario previo


class TestRevisar:

    def test_con_pendientes_cuenta_el_numero_real_y_enlaza(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=1542, archivos_sin_clasificar=137))
        p = paso(res, ClavePaso.REVISAR)
        assert p.titulo == "Revisa 137 tebeos que no hemos sabido clasificar"
        assert p.enlace == "/ui/pendientes"
        assert p.estado is EstadoPaso.SIGUIENTE and res.principal is p

    def test_singular(self):
        p = paso(calcular_primeros_pasos(estado(
            archivos_registrados=5, archivos_sin_clasificar=1)), ClavePaso.REVISAR)
        assert p.titulo == "Revisa 1 tebeo que no hemos sabido clasificar"

    def test_solo_uno_es_el_siguiente_el_otro_obligatorio_queda_pendiente(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.PENDIENTE, archivos_registrados=3, archivos_sin_clasificar=3))
        assert paso(res, ClavePaso.BIBLIOTECA).estado is EstadoPaso.SIGUIENTE
        assert paso(res, ClavePaso.REVISAR).estado is EstadoPaso.PENDIENTE
        assert sum(p.estado is EstadoPaso.SIGUIENTE for p in res.pasos) == 1
        assert res.principal.clave is ClavePaso.BIBLIOTECA

    def test_sin_pendientes_pero_con_archivos_es_hecho(self):
        p = paso(calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=10)), ClavePaso.REVISAR)
        assert p.estado is EstadoPaso.HECHO

    def test_sin_archivos_registrados_no_es_hecho(self):
        """Cero pendientes porque no hay nada registrado NO es «todo clasificado»."""
        p = paso(calcular_primeros_pasos(estado()), ClavePaso.REVISAR)
        assert p.estado is EstadoPaso.BLOQUEADO


class TestOpcionales:

    def test_series_seguidas_marca_hecho_con_el_numero(self):
        p = paso(calcular_primeros_pasos(estado(series_seguidas=3)), ClavePaso.SERIES)
        assert p.estado is EstadoPaso.HECHO and p.titulo == "Sigues 3 series"

    def test_una_serie_en_singular(self):
        p = paso(calcular_primeros_pasos(estado(series_seguidas=1)), ClavePaso.SERIES)
        assert p.titulo == "Sigues 1 serie"

    @pytest.mark.parametrize("fuente,legal,esperado,enlace", [
        (False, False, EstadoPaso.OPCIONAL, "/ui/ajustes"),
        (False, True, EstadoPaso.OPCIONAL, "/ui/ajustes"),
        (True, False, EstadoPaso.OPCIONAL, "/ui/legal"),
        (True, True, EstadoPaso.HECHO, "/ui/ajustes"),
    ])
    def test_descargas_exige_fuente_activa_y_aviso_legal(self, fuente, legal, esperado, enlace):
        p = paso(calcular_primeros_pasos(
            estado(hay_fuente_de_busqueda=fuente, aviso_legal_aceptado=legal)),
            ClavePaso.DESCARGAS)
        assert p.estado is esperado and p.enlace == enlace

    def test_activada_no_se_presenta_como_funciona(self):
        p = paso(calcular_primeros_pasos(
            estado(hay_fuente_de_busqueda=True, aviso_legal_aceptado=True)), ClavePaso.DESCARGAS)
        assert "No comprobamos que conteste" in p.detalle
        # La salida apunta a donde el motivo SÍ aparece (Deseados), no a un diagnóstico que Estado
        # todavía no ofrece para una búsqueda concreta.
        assert "el motivo aparece en Deseados" in p.detalle
        assert "Estado" not in p.detalle

    def test_los_opcionales_no_son_obligatorios(self):
        res = calcular_primeros_pasos(estado())
        assert not paso(res, ClavePaso.SERIES).obligatorio
        assert not paso(res, ClavePaso.DESCARGAS).obligatorio


class TestCompleto:

    def test_todo_listo(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=100, series_seguidas=2,
            informe=INFORME, aviso_legal_aceptado=True, hay_fuente_de_busqueda=True))
        assert res.completo and res.hechos == res.total == 4
        assert res.principal is None

    def test_completo_con_opcionales_por_hacer_sigue_ofreciendo_uno(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=100))
        assert res.completo
        assert res.principal.clave is ClavePaso.SERIES

    def test_pendientes_sin_clasificar_no_es_completo(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.HECHA, archivos_registrados=100, archivos_sin_clasificar=1))
        assert not res.completo

    def test_catalogo_previo_cuenta_los_mismos_pasos_que_cualquier_otro_caso(self):
        res = calcular_primeros_pasos(estado(
            adopcion=EstadoAdopcion.CATALOGO_PREVIO, archivos_registrados=10))
        assert res.total == 4 and not res.completo


class TestPureza:

    def test_mismo_estado_mismo_resultado(self):
        e = estado(adopcion=EstadoAdopcion.PENDIENTE, informe=INFORME)
        assert calcular_primeros_pasos(e) == calcular_primeros_pasos(e)

    def test_hay_como_maximo_un_principal_y_un_siguiente(self):
        import itertools
        for adopcion, reg, pend, seg, inf, legal, fuente in itertools.product(
                EstadoAdopcion, (0, 5), (0, 3), (0, 2), (None, INFORME),
                (False, True), (False, True)):
            res = calcular_primeros_pasos(estado(
                adopcion=adopcion, archivos_registrados=reg, archivos_sin_clasificar=pend,
                series_seguidas=seg, informe=inf, aviso_legal_aceptado=legal,
                hay_fuente_de_busqueda=fuente))
            assert sum(p.estado is EstadoPaso.SIGUIENTE for p in res.pasos) <= 1
            assert res.principal is None or res.principal in res.pasos
            # Nunca hay «hecho» en biblioteca sin adopción registrada.
            b = paso(res, ClavePaso.BIBLIOTECA)
            if b is not None and b.estado is EstadoPaso.HECHO:
                assert adopcion is EstadoAdopcion.HECHA


def test_fecha_llana_no_depende_del_locale():
    assert fecha_llana(datetime(2026, 1, 5, 12, 0)) == "5 de enero de 2026"
    assert fecha_llana(datetime(2026, 12, 31, 12, 0)) == "31 de diciembre de 2026"
