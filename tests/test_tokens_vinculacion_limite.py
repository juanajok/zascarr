# ruff: noqa: E501
"""Tamaño máximo del token de vinculación (`MAX_TOKEN_VINCULACION`): sin base de datos.

El contrato: **todo token de vinculación válido que la vista previa pueda emitir pasa el límite de quien lo recibe**,
y el máximo es una **cota calculada para la representación admitida, deliberadamente holgada** respecto al recorrido
actual de la vista previa (no «el mayor token que la vista previa emite»: reúne cosas que hoy ningún recorrido junta).
`MAX_TOKEN_VINCULACION` (#103) se calculó con el peor caso que entonces se imaginó: clave de grupo de 1000 caracteres
de cuatro bytes, números de 20 dígitos y `tamano`/`mtime_ns` de 63 bits. Tres de esas hipótesis no valían:

- la **clave del grupo** es la ruta de la carpeta tal cual y puede llevar controles, que JSON escribe con SEIS bytes;
- el **número** de cada archivo lo escribe la persona (la vista previa solo rechaza `\\n \\r \\t` y NUL, y un máximo de
  20 caracteres), así que también puede llevar controles: 20 × 6 bytes en cada uno de los 100 archivos;
- **`st_mtime_ns` no está limitado a 63 bits**: es `time_t` de 64 bits × 10**9 + nanosegundos, hasta 28 dígitos
  (un archivo en `tmpfs` conserva 10**19 y 10**27). Ni el verificador ni el proyecto lo limitan.

Aquí se prueba, con las funciones REALES de serialización, codificación y firma:
- qué caracteres admite cada campo (derivado de los validadores del código, no supuesto) y cuánto pesa cada uno;
- que el máximo es la longitud del token que reúne el peor caso de cada campo y que ninguna clase de carácter lo supera;
- que una construcción con `mtime_ns` de 63 bits se queda corta;
- que el límite anterior (56.029) rechazaba un token VÁLIDO (que el verificador acepta). En los recorridos ensayados la
  vista previa real emitió tokens por debajo de ese límite: es un defecto de la cota, no un fallo observado.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zascarr.api.revision import PeticionVincular
from zascarr.models import IssueFormat
from zascarr.services.tokens_revision import (
    CARACTER_MAS_PESADO_DE_UNA_CLAVE,
    CODIGOS_DE_SENAL,
    CONTROLES_DE_SEIS_BYTES_EN_UN_NUMERO,
    EPOCA_DEL_PEOR_CASO,
    MAX_ARCHIVOS_FIRMADOS,
    MAX_CLAVE_GRUPO,
    MAX_MTIME_NS_STAT,
    MAX_NUMERO,
    MAX_TAMANO_STAT,
    MAX_TOKEN_VINCULACION,
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token_vinculacion,
    verificar_token_vinculacion,
)
from zascarr.services.vinculacion_previa import (
    LIMITE_ARCHIVOS,
    NumeroNoValidoError,
    VistaPreviaDeVinculacion,
)

SECRETO = "clave-de-prueba-para-firmar"
EMOJI = "\U0001F600"
IDENT = "00000000-0000-4000-8000-000000000000"
GRANDE = 2**63 - 1                                  # lo que se suponía para `tamano` y `mtime_ns` en #103 (63 bits)
FORMATO = max((f.value for f in IssueFormat), key=len)
#: El límite que tenía el código antes de esta corrección (el que calculó #103) y la cifra que decía la documentación.
LIMITE_ANTERIOR = 56029
CIFRA_DOCUMENTAL_ERRONEA = 56021
CLASES = [
    pytest.param("a", id="ascii"),
    pytest.param('"', id="comillas"),
    pytest.param("\\", id="barra"),
    pytest.param("é", id="acento_2_bytes"),
    pytest.param("漢", id="cjk_3_bytes"),
    pytest.param(EMOJI, id="emoji_4_bytes"),
    pytest.param("\x01", id="control_6_bytes"),
]


def peso_json(o: int) -> int:
    """Bytes que ocupa un carácter dentro del JSON del token (UTF-8, sin ASCII forzado), sin las comillas."""
    return len(json.dumps(chr(o), ensure_ascii=False).encode()) - 2


def admite_el_numero(o: int) -> bool:
    """¿Acepta la vista previa este carácter dentro de un número, tal cual (sin que `strip` lo convierta en nada)?"""
    try:
        return VistaPreviaDeVinculacion._numero_valido(chr(o)) == chr(o)
    except NumeroNoValidoError:
        return False


PUNTOS = [o for o in range(0x110000) if not 0xD800 <= o <= 0xDFFF]
#: Caracteres de seis bytes que un número admite y que no son espacio (un espacio en un extremo lo quitaría `strip`).
CONTROLES_PESADOS = [chr(o) for o in PUNTOS if o < 0x20 and peso_json(o) == 6 and admite_el_numero(o)]


def numero_pesado(i: int) -> str:
    """El i-ésimo número de 20 caracteres, todos de seis bytes y distintos entre sí (dos posiciones varían)."""
    n = len(CONTROLES_PESADOS)
    return "\x01" * (MAX_NUMERO - 2) + CONTROLES_PESADOS[i // n] + CONTROLES_PESADOS[i % n]


def numero_de_clase(ch: str, i: int) -> str:
    """20 caracteres, 18 de la clase y dos dígitos distintos para que los 100 números no se repitan."""
    return ch * (MAX_NUMERO - 2) + f"{i:02d}"


def token(clave: str, numeros, *, tamano=MAX_TAMANO_STAT, mtime=MAX_MTIME_NS_STAT, conflictos=CODIGOS_DE_SENAL,
          serie: str = IDENT) -> str:
    """Un token firmado de 100 archivos. Por defecto, con `tamano` y `mtime_ns` en el máximo del ABI."""
    archivos = tuple(ArchivoFirmado(f"{i:08d}-0000-4000-8000-000000000000", numeros(i), FORMATO, tamano, mtime, conflictos)
                     for i in range(MAX_ARCHIVOS_FIRMADOS))
    return crear_token_vinculacion(VinculacionFirmada(clave, serie, IDENT, archivos), SECRETO, ahora=EPOCA_DEL_PEOR_CASO)


def token_de_63_bits(clave: str, numeros, **kw) -> str:
    """Lo que calculaba #103 para `tamano` y `mtime_ns`: enteros de 63 bits."""
    return token(clave, numeros, tamano=GRANDE, mtime=GRANDE, **kw)


def maximo_de_campo(modelo, campo: str) -> int | None:
    return next((m.max_length for m in modelo.model_fields[campo].metadata if hasattr(m, "max_length")), None)


# ── 0. Qué admite cada campo y cuánto pesa ───────────────────────────────────────────────────────

class TestCaracteresAdmitidos:
    """El máximo depende de qué caracteres puede llevar cada campo. Se deriva de los validadores del código."""

    def test_un_numero_admite_los_controles_salvo_nul_y_saltos_y_tabulador(self):
        assert not any(admite_el_numero(o) for o in (0, 9, 10, 13))             # \x00 \t \n \r
        assert CONTROLES_PESADOS and "\x01" in CONTROLES_PESADOS

    def test_el_caracter_que_mas_pesa_en_un_numero_pesa_seis_bytes(self):
        pesos = {peso_json(o) for o in PUNTOS if admite_el_numero(o)}
        assert max(pesos) == 6 and pesos == {1, 2, 3, 4, 6}

    def test_el_verificador_acepta_un_numero_de_20_controles(self):
        t = token("Comics/Flash", numero_pesado, tamano=1, mtime=1)
        v = verificar_token_vinculacion(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        assert v is not None and all(len(a.numero) == MAX_NUMERO for a in v.archivos)

    def test_el_conjunto_de_controles_del_calculo_coincide_con_lo_que_admite_el_validador(self):
        """Si `_numero_valido` cambia (admite o rechaza otros caracteres), el cálculo del máximo se revisa."""
        assert tuple(CONTROLES_PESADOS) == CONTROLES_DE_SEIS_BYTES_EN_UN_NUMERO

    def test_en_las_combinaciones_examinadas_un_archivo_lleva_como_mucho_tres_conflictos_pero_el_calculo_cuenta_ocho(self):
        """Dato para la lectura de la cota (no cambia el cálculo). `_Hallazgos.evaluar` se recorre con TODAS las
        combinaciones de título igual o no, año de la carpeta y del archivo (ausente, que discrepa, que cuadra) y
        calificadores que faltan o no: un mismo archivo da como mucho 3 códigos de conflicto (`titulo_distinto` y
        `titulo_exacto_sin_corroboracion` se excluyen, y el segundo también a `anio_discrepa`). `candidatas_distintas`
        es de grupo y no lleva archivos. La cota, en cambio, cuenta los 8 códigos en cada archivo."""
        from itertools import product
        from types import SimpleNamespace as N

        from zascarr.services.revision_carpetas import _Hallazgos
        maximo, vistos = 0, set()
        for t_igual, c_anio, a_anio, faltan, vol in product([True, False], [None, 1990, 1950], [None, 1990, 1950], [False, True], [None, 3]):
            h = _Hallazgos()
            carpeta = N(titulo="Flash", titulo_completo="Flash", anio=c_anio, volumen=vol, calificadores=["Omnigold"] if faltan else [])
            h.evaluar(N(id="f", titulo_norm="flash" if t_igual else "otra", anio=a_anio, titulo="Flash"), "Flash", "flash", 1990, carpeta)
            codigos = {c for c, hay in (("anio_discrepa", h.anio_carpeta or h.anio_archivo), ("calificador_de_carpeta", h.sin_calificador),
                                        ("titulo_distinto", h.titulo_distinto), ("titulo_exacto_sin_corroboracion", h.exacto_sin_corroboracion)) if hay}
            maximo = max(maximo, len(codigos))
            vistos |= codigos
        assert maximo == 3 and len(vistos) == 4 and len(CODIGOS_DE_SENAL) == 8

    def test_un_escenario_de_calculo_con_tres_conflictos_queda_por_debajo_del_limite_anterior(self):
        """Un ESCENARIO DE CÁLCULO, no una demostración de máximos: clave de 970 controles, números de 20 controles,
        `tamano` de 16 TiB, `mtime_ns` de 19 dígitos (≈ 2026) y 3 conflictos por archivo (el máximo que dieron las
        combinaciones examinadas de `_Hallazgos.evaluar`). Da ≈ 52.700, menos que el límite anterior. No prueba que ningún
        entorno pase de ahí: `st_mtime_ns` puede tener 28 dígitos y la clave hasta 1000 caracteres."""
        tres = ("anio_discrepa", "calificador_de_carpeta", "titulo_distinto")
        escenario = len(token("\x01" * 970, numero_pesado, tamano=2**44, mtime=1_760_000_000_000_000_000, conflictos=tres))
        assert escenario < LIMITE_ANTERIOR < MAX_TOKEN_VINCULACION
        assert 52000 < escenario < 53500

    def test_la_clave_se_calcula_con_el_caracter_mas_pesado_de_una_clave(self):
        assert peso_json(ord(CARACTER_MAS_PESADO_DE_UNA_CLAVE)) == max(peso_json(o) for o in PUNTOS) == 6

    def test_la_pagina_de_la_vista_previa_y_el_token_tienen_el_mismo_tope_de_archivos(self):
        assert LIMITE_ARCHIVOS == MAX_ARCHIVOS_FIRMADOS == 100

    def test_la_edicion_y_los_codigos_de_senal_son_ascii(self):
        assert all(f.value.isascii() for f in IssueFormat) and all(c.isascii() for c in CODIGOS_DE_SENAL)

    def test_las_cotas_de_stat_son_las_del_abi_de_linux_y_no_las_de_63_bits(self):
        """`st_size` es un `off_t` de 64 bits con signo; `st_mtime_ns` es `time_t` de 64 bits × 10**9 + nsec (< 10**9)."""
        assert MAX_TAMANO_STAT == 2**63 - 1 and len(str(MAX_TAMANO_STAT)) == 19
        assert MAX_MTIME_NS_STAT == (2**63 - 1) * 10**9 + 999_999_999 and len(str(MAX_MTIME_NS_STAT)) == 28
        assert MAX_MTIME_NS_STAT > GRANDE

    def test_un_archivo_real_conserva_un_mtime_por_encima_de_2_63(self, tmp_path):
        """La razón de la cota: `stat` NO devuelve como mucho 19 dígitos. Se prueba con un archivo de verdad, sin saltar
        nada: de los valores pedidos, los que el sistema de archivos conserve han de caber en la cota, y al menos uno
        (10**19, año 2286) debe conservarse. Mide el entorno donde se ejecuta, no demuestra otros sistemas de archivos."""
        import os
        conservados = []
        for pedido in (10**19, 10**22, 10**27):
            f = tmp_path / f"f{len(conservados)}"
            f.write_bytes(b"x")
            try:
                os.utime(f, ns=(pedido, pedido))
            except (OSError, OverflowError):
                continue
            real = f.stat().st_mtime_ns
            if real == pedido:
                conservados.append(real)
        assert 10**19 in conservados, conservados
        assert all(GRANDE < m <= MAX_MTIME_NS_STAT for m in conservados)

    def test_un_mtime_negativo_es_posible_en_stat_pero_el_verificador_lo_rechaza(self, tmp_path):
        """Hallazgo, no corrección: antes de 1970 `stat` da un `mtime_ns` negativo; el verificador exige `>= 0`. Se
        registra en `docs` y no se cambia aquí (sería una restricción nueva de fechas)."""
        import os
        f = tmp_path / "antiguo"
        f.write_bytes(b"x")
        os.utime(f, ns=(-10**9, -10**9))
        assert f.stat().st_mtime_ns < 0
        t = token("Comics/Flash", numero_pesado, mtime=f.stat().st_mtime_ns)
        assert verificar_token_vinculacion(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is None


# ── 1. El máximo es el peor caso emitible ─────────────────────────────────────────────────────────

class TestMaximoCalculado:

    def test_el_maximo_es_la_longitud_del_token_que_reune_el_peor_caso_de_cada_campo(self):
        peor = token(CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, numero_pesado)
        assert len(peor) == MAX_TOKEN_VINCULACION
        assert verificar_token_vinculacion(peor, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    def test_el_maximo_medido(self):
        """Si cambia una cota, este valor se recalcula (no se edita a mano) y la prueba anterior comprueba que sigue
        siendo el peor caso. No es 58.697 (solo la clave de controles) ni 72.029 (clave y números de controles pero
        `mtime_ns` de 63 bits): cada una dejaba una hipótesis sin comprobar."""
        assert MAX_TOKEN_VINCULACION == 73229

    @pytest.mark.parametrize("mtime", [GRANDE + 1, 10**19, 10**22, 10**27, MAX_MTIME_NS_STAT])
    def test_un_mtime_por_encima_de_2_63_cabe_en_el_maximo(self, mtime):
        t = token(CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, numero_pesado, mtime=mtime)
        assert len(t) <= MAX_TOKEN_VINCULACION
        assert verificar_token_vinculacion(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    def test_una_construccion_con_63_bits_se_queda_corta(self):
        """Detecta el error que había: con `mtime_ns` de 63 bits el máximo sería 72.029, y un token VÁLIDO con un
        `mtime_ns` de 10**19 (que `stat` devuelve de verdad) lo supera."""
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        de_63_bits = len(token_de_63_bits(clave, numero_pesado))
        assert de_63_bits == 72029 < MAX_TOKEN_VINCULACION
        con_20_digitos = token(clave, numero_pesado, mtime=10**19)
        assert de_63_bits < len(con_20_digitos) <= MAX_TOKEN_VINCULACION
        assert verificar_token_vinculacion(con_20_digitos, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    @pytest.mark.parametrize("tamano", [0, 1, MAX_TAMANO_STAT])
    def test_el_tamano_cabe_en_el_maximo(self, tamano):
        t = token(CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, numero_pesado, tamano=tamano)
        assert len(t) <= MAX_TOKEN_VINCULACION

    def test_los_codigos_de_senal_del_calculo_siguen_a_los_del_productor(self):
        """La cota cuenta los 8 códigos en cada archivo a propósito. Si el productor gana un código, esto falla y obliga
        a añadirlo a `CODIGOS_DE_SENAL` (y a recalcular)."""
        import re

        from zascarr.services import revision_carpetas
        fuente = Path(revision_carpetas.__file__).read_text(encoding="utf-8")
        assert set(CODIGOS_DE_SENAL) == set(re.findall(r'codigo="([a-z_]+)"', fuente))

    @pytest.mark.parametrize("ch", CLASES)
    def test_ninguna_clase_de_caracter_en_los_numeros_supera_el_maximo(self, ch):
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        t = token(clave, lambda i: numero_de_clase(ch, i))
        assert len(t) <= MAX_TOKEN_VINCULACION
        assert verificar_token_vinculacion(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    @pytest.mark.parametrize("ch", CLASES + [pytest.param("/", id="barra_de_ruta")])
    def test_ninguna_clase_de_caracter_en_la_clave_supera_el_maximo(self, ch):
        assert len(token(ch * MAX_CLAVE_GRUPO, numero_pesado)) <= MAX_TOKEN_VINCULACION

    def test_cada_hipotesis_aporta_lo_que_se_dice(self):
        """Descompone la diferencia con el límite anterior, una hipótesis cada vez."""
        clave_de_4_bytes = EMOJI * MAX_CLAVE_GRUPO
        clave_de_controles = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        digitos = lambda i: "9" * (MAX_NUMERO - 3) + f"{i:03d}"                                    # noqa: E731
        anterior = len(token_de_63_bits(clave_de_4_bytes, digitos))
        solo_la_clave = len(token_de_63_bits(clave_de_controles, digitos))
        solo_los_numeros = len(token_de_63_bits(clave_de_4_bytes, numero_pesado))
        clave_y_numeros = len(token_de_63_bits(clave_de_controles, numero_pesado))
        todo = len(token(clave_de_controles, numero_pesado))
        assert anterior == LIMITE_ANTERIOR
        assert solo_la_clave == 58697                 # la medición aislada que dio la alarma en #138
        assert solo_los_numeros - anterior > 13000    # 100 números × 100 bytes más, en base64
        assert clave_y_numeros == 72029               # el primer intento de esta corrección (mtime de 63 bits)
        assert todo == MAX_TOKEN_VINCULACION > clave_y_numeros > solo_la_clave > anterior


# ── 2. El límite anterior rechazaba un token válido (que la vista previa real no llega a emitir) ──

class TestElLimiteAnteriorNoAlcanzaba:

    def test_un_token_valido_para_el_verificador_con_numeros_de_controles_superaba_56029(self):
        t = token("Comics/Flash (1987)", numero_pesado)
        assert LIMITE_ANTERIOR < len(t) <= MAX_TOKEN_VINCULACION
        assert verificar_token_vinculacion(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    def test_la_cifra_que_decia_la_documentacion_era_otra_distinta_del_codigo(self):
        assert CIFRA_DOCUMENTAL_ERRONEA != LIMITE_ANTERIOR


# ── 3. El límite de la petición ───────────────────────────────────────────────────────────────────

class TestLimiteDeLaPeticion:

    def test_el_endpoint_admite_exactamente_el_maximo(self):
        assert maximo_de_campo(PeticionVincular, "token") == MAX_TOKEN_VINCULACION

    def test_acotado_no_infinito(self):
        assert 40000 < MAX_TOKEN_VINCULACION < 100000
