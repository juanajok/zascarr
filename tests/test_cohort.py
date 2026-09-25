"""
tests/test_cohort.py

Suite de core/cohort.py: detección de prefijos de orden de lectura por
evidencia de cohorte, cuando naming.py no puede distinguirlos por forma
(sin punto ni guion tras el número).
"""
from __future__ import annotations

from zascarr.core.cohort import (
    UMBRAL_EVIDENCIA,
    detectar_ordenes_de_lectura,
    quitar_prefijo_de_cohorte,
)


class TestDetectarOrdenesDeLectura:

    def test_prefijo_que_varia_con_evidencia_suficiente_se_detecta(self):
        """El caso real que motivó el módulo: "Dreadstar" con prefijos
        distintos y el resto del nombre estable."""
        nombres = [
            "42 Dreadstar (First Comics) 30 USA.cbr",
            "65 Dreadstar (First Comics) 53 USA.cbz",
            "74 Dreadstar (First Comics) 62 USA.cbz",
        ]
        pistas = detectar_ordenes_de_lectura(nombres)

        assert set(pistas) == set(nombres)
        assert pistas[nombres[0]].prefijo == "42"
        assert pistas[nombres[0]].evidencia == 3
        assert pistas[nombres[0]].cohorte == pistas[nombres[1]].cohorte

    def test_prefijo_constante_no_se_toca_es_parte_del_titulo(self):
        """"100 Balas" siempre con el mismo "100": es el título, no un
        orden de lectura — aunque hubiera evidencia de sobra."""
        nombres = [
            "100 Balas - Integral 01.cbz",
            "100 Balas - Integral 02.cbz",
            "100 Balas - Integral 03.cbz",
            "100 Balas - Integral 04.cbz",
        ]
        assert detectar_ordenes_de_lectura(nombres) == {}

    def test_menos_de_tres_hermanos_no_es_evidencia_suficiente(self):
        nombres = [
            "10 Algo Raro (Epic).cbr",
            "20 Algo Raro (Epic).cbr",
        ]
        assert len(nombres) < UMBRAL_EVIDENCIA
        assert detectar_ordenes_de_lectura(nombres) == {}

    def test_justo_en_el_umbral_si_detecta(self):
        nombres = [f"{n} Cosa Rara (Epic).cbr" for n in (10, 20, 30)]
        assert len(detectar_ordenes_de_lectura(nombres)) == 3

    def test_creditos_entre_corchetes_no_fragmentan_la_cohorte(self):
        """Bug real encontrado verificando el módulo contra la
        biblioteca real: el crédito del traductor varía por archivo
        DENTRO de la misma cohorte, y dejarlo en la firma fragmentaba
        una cohorte de ~70 en decenas de grupos de 1-2, todos por
        debajo del umbral."""
        nombres = [
            "42 Dreadstar (First Comics) 30 USA [Traducido porke yo lo valgo][CRG].cbr",
            "65 Dreadstar (First Comics) 53 USA [Trad por Skullpirates y Howard][CRG].cbz",
            "74 Dreadstar (First Comics) 62 USA [Trad por Otro Cualquiera][CRG].cbz",
        ]
        pistas = detectar_ordenes_de_lectura(nombres)
        assert len(pistas) == 3
        assert len({p.cohorte for p in pistas.values()}) == 1

    def test_creditos_sueltos_sin_corchetes_tampoco_fragmentan(self):
        nombres = [
            "42 Dreadstar (First Comics) 30 USA por Fulano.cbr",
            "65 Dreadstar (First Comics) 53 USA por Mengano.cbz",
            "74 Dreadstar (First Comics) 62 USA por Zutano.cbz",
        ]
        pistas = detectar_ordenes_de_lectura(nombres)
        assert len(pistas) == 3

    def test_cohortes_distintas_no_se_mezclan(self):
        """Dos familias reales distintas (First Comics / Malibu Comics)
        deben quedar como dos cohortes separadas, no una."""
        nombres = [
            "42 Dreadstar (First Comics) 30 USA.cbr",
            "65 Dreadstar (First Comics) 53 USA.cbz",
            "74 Dreadstar (First Comics) 62 USA.cbz",
            "77 Jim Starlin's Dreadstar (Malibu Comics) 01.cbr",
            "78 Jim Starlin's Dreadstar (Malibu Comics) 02.cbr",
            "79 Jim Starlin's Dreadstar (Malibu Comics) 03.cbr",
        ]
        pistas = detectar_ordenes_de_lectura(nombres)
        cohortes = {p.cohorte for p in pistas.values()}
        assert len(cohortes) == 2

    def test_nombre_sin_prefijo_numerico_se_ignora(self):
        nombres = ["Dreadstar sin numero A.cbr", "Dreadstar sin numero B.cbr",
                   "Dreadstar sin numero C.cbr"]
        assert detectar_ordenes_de_lectura(nombres) == {}

    def test_no_crea_ninguna_nocion_de_serie(self):
        """Contrato 1: la pista no lleva nombre de serie ni nada que se
        parezca — solo dice "este prefijo no es de fiar", el matcher
        sigue decidiendo la serie contra el catálogo real."""
        nombres = [f"{n} Cosa Rara (Epic).cbr" for n in (10, 20, 30)]
        pista = next(iter(detectar_ordenes_de_lectura(nombres).values()))
        assert not hasattr(pista, "series")
        assert not hasattr(pista, "serie")

    def test_explicacion_trae_la_evidencia_para_b12(self):
        """Contrato 2: la explicación es legible y lleva el número que
        la respalda, lista para dejar constancia en el informe del
        ciclo / sugerencia de B12."""
        nombres = [f"{n} Cosa Rara (Epic).cbr" for n in (10, 20, 30, 40, 50)]
        pista = next(iter(detectar_ordenes_de_lectura(nombres).values()))
        assert "5" in pista.explicacion
        assert pista.prefijo in pista.explicacion


class TestQuitarPrefijoDeCohorte:

    def test_quita_el_prefijo_bare(self):
        from zascarr.core.cohort import PistaDeCohorte

        pista = PistaDeCohorte(prefijo="42", cohorte="x", evidencia=3, explicacion="x")
        resultado = quitar_prefijo_de_cohorte("42 Dreadstar (First Comics) 30 USA.cbr", pista)

        assert resultado == "Dreadstar (First Comics) 30 USA.cbr"

    def test_no_toca_nada_si_el_prefijo_no_coincide(self):
        """Nunca corta a ciegas: si la pista no es de ESTE archivo, no
        pasa nada — se devuelve el nombre intacto."""
        from zascarr.core.cohort import PistaDeCohorte

        pista = PistaDeCohorte(prefijo="99", cohorte="x", evidencia=3, explicacion="x")
        original = "42 Dreadstar (First Comics) 30 USA.cbr"

        assert quitar_prefijo_de_cohorte(original, pista) == original

    def test_no_toca_el_formato_con_punto_o_guion(self):
        """"069.- Flash..." ya lo resuelve SORT_PREFIX_PATTERN en
        naming.py — este módulo no debe interferir ahí, es un no-op
        seguro si por lo que sea también generó una pista para él."""
        from zascarr.core.cohort import PistaDeCohorte

        pista = PistaDeCohorte(prefijo="69", cohorte="x", evidencia=3, explicacion="x")
        original = "069.- Flash v2 62 By Spiderman2099.cbr"

        assert quitar_prefijo_de_cohorte(original, pista) == original
