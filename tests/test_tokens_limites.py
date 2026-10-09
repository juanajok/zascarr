# ruff: noqa: E501
"""Tamaño máximo de los tokens de candidata y alta (`services/tokens_revision.py`): sin base de datos.

El contrato: **todo token de candidata o de alta que el servidor pueda emitir pasa los límites de quien lo recibe**.
Antes, `POST /api/revision/serie/previsualizar` (campo `candidata`) y `POST /api/revision/serie` (campo `token`)
aceptaban como mucho 8.000 caracteres, un número que no salía de ningún cálculo, mientras que lo que el productor
firmaba (el título, el identificador y la portada que devuelve una fuente) no tenía cota: un resultado legítimo con
texto largo o no latino podía emitirse y luego rechazarse por tamaño, después de que la persona lo hubiera elegido.

Aquí se prueba, con las funciones REALES de serialización, codificación y firma (nunca multiplicando a ojo):
- los máximos (`MAX_TOKEN_CANDIDATA`, `MAX_TOKEN_ALTA`) son la longitud del mayor token emitible, no un número elegido;
- ese mayor token cabe, se verifica y no hay carácter (ASCII, comillas, barras, saltos, acentos, CJK, 4 bytes) que
  lo supere;
- el límite antiguo de 8.000 SÍ rechazaba un token legítimo con texto no latino (reproducción del problema);
- cada cota de campo se acepta en su valor y se rechaza un carácter por encima;
- lo que no se puede firmar (sustitutos sueltos de Unicode, controles) ni se emite ni se acepta;
- el token de vinculación no cambia.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from zascarr.api.revision import (
    DatosManualesIn,
    PeticionConfirmarAlta,
    PeticionPrevisualizarAlta,
    PeticionVincular,
)
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import CAMPO_ID_EXTERNO
from zascarr.services.tokens_revision import (
    ANIO_MAX_FIRMABLE,
    ANIO_MIN_FIRMABLE,
    EPOCA_DEL_PEOR_CASO,
    MAX_CLAVE_GRUPO,
    MAX_COVER_URL,
    MAX_DESCRIPCION,
    MAX_ID_EXTERNO,
    MAX_PARECIDAS_FIRMADAS,
    MAX_TITULO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_CANDIDATA,
    MAX_TOKEN_VINCULACION,
    PROPOSITO_ALTA,
    PROPOSITO_CANDIDATA,
    AltaFirmada,
    CandidataFirmada,
    candidata_firmable,
    crear_token,
    crear_token_alta,
    crear_token_candidata,
    texto_firmable,
    verificar_token_alta,
    verificar_token_candidata,
)

SECRETO = "clave-de-prueba-para-firmar"
CLAVE = "Comics/Flash (1987)"
EMOJI = "\U0001F600"                 # 4 bytes en UTF-8: el carácter más pesado de un texto firmable
OP = str(uuid4())
#: Un mismo carácter repetido en cada texto: el peor caso de cada clase de carácter.
CLASES = [
    pytest.param("a", id="ascii"),
    pytest.param('"', id="comillas"),
    pytest.param("\\", id="barra"),
    pytest.param("\n", id="salto_de_linea"),
    pytest.param("é", id="acento_2_bytes"),
    pytest.param("漢", id="cjk_3_bytes"),
    pytest.param(EMOJI, id="emoji_4_bytes"),
]


def peor_candidata(ch: str, *, anio: int | None = ANIO_MIN_FIRMABLE) -> CandidataFirmada:
    fuente = max((m.value for m in MetadataSource), key=len)
    tradicion = max((t.value for t in ComicTradition), key=len)
    return CandidataFirmada(fuente, ch * MAX_ID_EXTERNO, ch * MAX_TITULO, anio, tradicion,
                            ch * MAX_DESCRIPCION, ch * MAX_COVER_URL)


def peor_alta(ch: str, *, modo: str = "crear", anio: int | None = ANIO_MIN_FIRMABLE) -> AltaFirmada:
    fuente = max((m.value for m in CAMPO_ID_EXTERNO), key=len)
    tradicion = max((t.value for t in ComicTradition), key=len)
    vistas = tuple(str(uuid4()) for _ in range(MAX_PARECIDAS_FIRMADAS)) if modo == "crear" else ()
    return AltaFirmada(
        clave=ch * MAX_CLAVE_GRUPO, modo=modo, origen="descubrir", fuente=fuente, id_externo=ch * MAX_ID_EXTERNO,
        titulo=ch * MAX_TITULO, anio=anio, tradicion=tradicion, descripcion=ch * MAX_DESCRIPCION,
        cover_url=ch * MAX_COVER_URL, serie_id=None if modo == "crear" else OP,
        vistas=vistas, operacion=OP, criterio=None if modo == "crear" else "identificador")


def firmada_candidata(c: CandidataFirmada, clave: str = CLAVE) -> str:
    return crear_token_candidata(clave, c, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)


def firmada_alta(a: AltaFirmada) -> str:
    return crear_token_alta(a, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)


def maximo_de_campo(modelo, campo: str) -> int | None:
    return next((m.max_length for m in modelo.model_fields[campo].metadata if hasattr(m, "max_length")), None)


# ── 1. Los máximos son el peor caso emitible ──────────────────────────────────────────────────────

class TestMaximosCalculados:

    def test_el_maximo_de_candidata_es_la_longitud_del_mayor_token_emitible(self):
        peor = firmada_candidata(peor_candidata(EMOJI), EMOJI * MAX_CLAVE_GRUPO)
        assert len(peor) == MAX_TOKEN_CANDIDATA
        assert verificar_token_candidata(peor, EMOJI * MAX_CLAVE_GRUPO, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    def test_el_maximo_de_alta_es_la_longitud_del_mayor_token_emitible(self):
        peor = firmada_alta(peor_alta(EMOJI))
        assert len(peor) == MAX_TOKEN_ALTA
        assert verificar_token_alta(peor, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    @pytest.mark.parametrize("ch", CLASES)
    def test_ninguna_clase_de_caracter_supera_el_maximo_de_candidata(self, ch):
        t = firmada_candidata(peor_candidata(ch), ch * MAX_CLAVE_GRUPO)
        assert len(t) <= MAX_TOKEN_CANDIDATA
        if ch.strip():           # un título en blanco no es válido: de «\n» solo importa el tamaño
            assert verificar_token_candidata(t, ch * MAX_CLAVE_GRUPO, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    @pytest.mark.parametrize("ch", CLASES)
    @pytest.mark.parametrize("modo", ["crear", "reutilizar"])
    def test_ninguna_clase_de_caracter_supera_el_maximo_de_alta(self, ch, modo):
        t = firmada_alta(peor_alta(ch, modo=modo))
        assert len(t) <= MAX_TOKEN_ALTA
        if ch.strip():
            assert verificar_token_alta(t, SECRETO, ahora=EPOCA_DEL_PEOR_CASO) is not None

    def test_el_emoji_es_la_clase_mas_pesada_y_alcanza_el_maximo(self):
        """Si alguna clase pesara más, el máximo estaría mal calculado; la que lo fija es la de 4 bytes."""
        tamanos = {ch: len(firmada_candidata(peor_candidata(ch), ch * MAX_CLAVE_GRUPO))
                   for ch in ("a", '"', "\\", "\n", "é", "漢", EMOJI)}
        assert max(tamanos, key=tamanos.get) == EMOJI and tamanos[EMOJI] == MAX_TOKEN_CANDIDATA

    @pytest.mark.parametrize("anio", [None, 1, 1987, 2100, ANIO_MIN_FIRMABLE, ANIO_MAX_FIRMABLE])
    def test_el_anio_no_supera_el_maximo(self, anio):
        assert len(firmada_candidata(peor_candidata(EMOJI, anio=anio), EMOJI * MAX_CLAVE_GRUPO)) <= MAX_TOKEN_CANDIDATA
        assert len(firmada_alta(peor_alta(EMOJI, anio=anio))) <= MAX_TOKEN_ALTA

    def test_un_alta_que_reutiliza_pesa_menos_que_la_que_crea_con_todas_sus_vistas(self):
        assert len(firmada_alta(peor_alta(EMOJI, modo="reutilizar"))) < len(firmada_alta(peor_alta(EMOJI)))

    def test_los_maximos_medidos(self):
        """Los números de esta medición (cotas de campo actuales). Si cambia una cota, estos valores se recalculan
        — no se editan a mano — y la prueba anterior comprueba que siguen siendo el peor caso. Las cifras que se
        estimaron antes a mano (4.625 / 5.889 y 14.625 / 15.889) no eran estos máximos."""
        assert (MAX_TOKEN_CANDIDATA, MAX_TOKEN_ALTA) == (17649, 23013)


# ── 2. El límite antiguo rechazaba un token legítimo (el problema) ────────────────────────────────

LIMITE_ANTIGUO = 8000


class TestElLimiteAntiguoNoAlcanzaba:
    """El 8.000 antiguo no salía de ningún cálculo. Un texto no latino ocupa tres bytes por carácter y el token los
    lleva en base64 (4/3): con TODO dentro de las cotas del sistema —título de 500 caracteres, descripción de 1000, una
    carpeta de 500 y una portada de 300— el token ya mide más de 8.000. No es el caso típico (una candidata normal
    ronda los 1.800 caracteres): es la prueba de que el límite viejo rechazaba un token válido, y de que el nuevo se
    deriva de las cotas en vez de adivinarse."""

    CLAVE_CJK = "漫" * 500

    def candidata(self) -> CandidataFirmada:
        return CandidataFirmada("tebeosfera", "id-" + "x" * 20, "漢" * MAX_TITULO, 2016, "manga",
                                "物" * MAX_DESCRIPCION, "https://www.tebeosfera.com/img/" + "1" * 300 + ".jpg")

    def test_una_candidata_legitima_con_texto_cjk_supera_los_8000_y_cabe_en_el_maximo(self):
        c = self.candidata()
        assert candidata_firmable(c.fuente, c.id_externo, c.titulo, c.anio, c.tradicion, c.descripcion, c.cover_url) == c
        t = crear_token_candidata(self.CLAVE_CJK, c, SECRETO)
        assert len(t) > LIMITE_ANTIGUO, "ya no reproduce el problema: sube el texto de la prueba"
        assert len(t) <= MAX_TOKEN_CANDIDATA
        assert verificar_token_candidata(t, self.CLAVE_CJK, SECRETO) == c

    def test_el_alta_de_esa_candidata_tambien_supera_los_8000_y_cabe_en_el_maximo(self):
        c = self.candidata()
        a = AltaFirmada(clave=self.CLAVE_CJK, modo="crear", origen="descubrir", fuente=c.fuente, id_externo=c.id_externo,
                        titulo=c.titulo, anio=c.anio, tradicion=c.tradicion, descripcion=c.descripcion,
                        cover_url=c.cover_url, serie_id=None, vistas=(), operacion=OP)
        t = crear_token_alta(a, SECRETO)
        assert len(t) > LIMITE_ANTIGUO and len(t) <= MAX_TOKEN_ALTA
        assert verificar_token_alta(t, SECRETO) is not None

    def test_ya_no_hay_un_limite_de_8000_en_la_peticion(self):
        assert maximo_de_campo(PeticionPrevisualizarAlta, "candidata") == MAX_TOKEN_CANDIDATA > LIMITE_ANTIGUO
        assert maximo_de_campo(PeticionConfirmarAlta, "token") == MAX_TOKEN_ALTA > LIMITE_ANTIGUO


# ── 3. Las cotas de campo ─────────────────────────────────────────────────────────────────────────

VALIDO = {"fuente": "tebeosfera", "id": "42", "titulo": "Flash", "anio": 1987, "tradicion": "american",
          "descripcion": "algo", "cover_url": "https://www.tebeosfera.com/a/x.jpg"}
VALIDO_ALTA = {"modo": "crear", "origen": "descubrir", "fuente": "tebeosfera", "id": "42", "titulo": "Flash",
               "anio": 1987, "tradicion": "american", "descripcion": "algo",
               "cover_url": "https://www.tebeosfera.com/a/x.jpg", "serie_id": None, "vistas": [], "operacion": OP,
               "criterio": None}


def candidata_con(**cambios):
    return verificar_token_candidata(crear_token(PROPOSITO_CANDIDATA, CLAVE, {**VALIDO, **cambios}, SECRETO), CLAVE, SECRETO)


def alta_con(clave: str = CLAVE, **cambios):
    return verificar_token_alta(crear_token(PROPOSITO_ALTA, clave, {**VALIDO_ALTA, **cambios}, SECRETO), SECRETO)


CAMPOS_DE_TEXTO = [("titulo", MAX_TITULO), ("id", MAX_ID_EXTERNO), ("descripcion", MAX_DESCRIPCION),
                   ("cover_url", MAX_COVER_URL)]


class TestCotasDeCampo:

    @pytest.mark.parametrize("campo,cota", CAMPOS_DE_TEXTO)
    def test_candidata_acepta_la_cota_y_rechaza_un_caracter_mas(self, campo, cota):
        assert candidata_con(**{campo: "a" * cota}) is not None
        assert candidata_con(**{campo: "a" * (cota + 1)}) is None

    @pytest.mark.parametrize("campo,cota", CAMPOS_DE_TEXTO)
    def test_alta_acepta_la_cota_y_rechaza_un_caracter_mas(self, campo, cota):
        assert alta_con(**{campo: "a" * cota}) is not None
        assert alta_con(**{campo: "a" * (cota + 1)}) is None

    def test_las_cotas_son_las_de_las_columnas_y_de_la_politica_de_portadas(self):
        from zascarr.models import Series
        from zascarr.utils.url_portada import LONGITUD_MAXIMA_URL
        assert Series.__table__.c.title.type.length == MAX_TITULO
        assert MAX_COVER_URL == Series.__table__.c.cover_url.type.length == LONGITUD_MAXIMA_URL
        assert Series.__table__.c.tebeosfera_slug.type.length == MAX_ID_EXTERNO
        assert MAX_DESCRIPCION == 1000          # el recorte que ya hacía `crear_token_candidata`

    @pytest.mark.parametrize("anio", [ANIO_MIN_FIRMABLE, -1, 0, 1987, ANIO_MAX_FIRMABLE])
    def test_el_anio_dentro_de_la_smallint_pasa(self, anio):
        assert candidata_con(anio=anio) is not None and alta_con(anio=anio) is not None

    @pytest.mark.parametrize("anio", [ANIO_MIN_FIRMABLE - 1, ANIO_MAX_FIRMABLE + 1, 10**30, True, 1987.0, "1987"])
    def test_el_anio_fuera_de_la_smallint_o_de_otro_tipo_no_pasa(self, anio):
        assert candidata_con(anio=anio) is None and alta_con(anio=anio) is None

    def test_el_alta_acepta_hasta_100_vistas_y_rechaza_la_101(self):
        assert MAX_PARECIDAS_FIRMADAS == 100
        assert alta_con(vistas=[str(uuid4()) for _ in range(MAX_PARECIDAS_FIRMADAS)]) is not None
        assert alta_con(vistas=[str(uuid4()) for _ in range(MAX_PARECIDAS_FIRMADAS + 1)]) is None

    def test_el_alta_acepta_una_clave_de_1000_caracteres_y_rechaza_1001(self):
        assert alta_con(clave="k" * MAX_CLAVE_GRUPO) is not None
        assert alta_con(clave="k" * (MAX_CLAVE_GRUPO + 1)) is None

    @pytest.mark.parametrize("malo", ["a\x00b", "a\x01b", "a\x1fb", "\x07"])
    @pytest.mark.parametrize("campo", ["titulo", "id", "descripcion", "cover_url"])
    def test_un_control_en_cualquier_texto_se_rechaza(self, campo, malo):
        assert candidata_con(**{campo: malo}) is None and alta_con(**{campo: malo}) is None

    @pytest.mark.parametrize("permitido", ["\t", "\n", "\r"])
    def test_tabulador_y_saltos_de_linea_se_aceptan_en_la_descripcion(self, permitido):
        assert candidata_con(descripcion=f"a{permitido}b") is not None and alta_con(descripcion=f"a{permitido}b") is not None


# ── 4. Lo que no se puede firmar ──────────────────────────────────────────────────────────────────

class TestTextoFirmable:

    @pytest.mark.parametrize("texto", ["", "Flash", "Astérix", "漢字", EMOJI, "a\tb\nc\r", '"\\', "\x7f", "\u0085"])
    def test_texto_firmable(self, texto):
        assert texto_firmable(texto)

    @pytest.mark.parametrize("texto", ["\x00", "a\x01", "\x1b[0m", "\x1f", "\ud800", "x\udfffy", "\udc00\ud800"])
    def test_texto_no_firmable(self, texto):
        assert not texto_firmable(texto)

    def test_un_sustituto_suelto_no_se_puede_codificar_ni_firmar(self):
        """El fallo que motivó la regla: antes, un título así de una fuente lanzaba `UnicodeEncodeError` al firmar y
        la búsqueda entera acababa en un 500."""
        with pytest.raises(UnicodeEncodeError):
            crear_token(PROPOSITO_CANDIDATA, CLAVE, {**VALIDO, "titulo": "\ud800"}, SECRETO)


class TestCandidataFirmable:

    def firmable(self, **kw):
        base = dict(fuente="tebeosfera", id_externo="42", titulo="Flash", anio=1987, tradicion="american",
                    descripcion="Velocista.", cover_url="https://www.tebeosfera.com/a/x.jpg")
        return candidata_firmable(**{**base, **kw})

    def test_un_resultado_normal_se_firma_tal_cual(self):
        c = self.firmable()
        assert c == CandidataFirmada("tebeosfera", "42", "Flash", 1987, "american", "Velocista.",
                                     "https://www.tebeosfera.com/a/x.jpg")

    def test_el_titulo_pierde_espacios_y_controles_como_lo_hace_el_alta(self):
        assert self.firmable(titulo="  El\t Flash \n\x00 (1987)  ").titulo == "El Flash (1987)"

    def test_el_titulo_de_exactamente_la_cota_pasa_aunque_el_original_llevara_espacios_de_mas(self):
        assert self.firmable(titulo=" " + "a" * MAX_TITULO + "   ").titulo == "a" * MAX_TITULO

    @pytest.mark.parametrize("titulo", ["a" * (MAX_TITULO + 1), "", "   ", None, "\x00\x01", "\ud800"])
    def test_un_titulo_que_no_cabe_o_esta_vacio_descarta_la_candidata(self, titulo):
        assert self.firmable(titulo=titulo) is None

    @pytest.mark.parametrize("ident", ["x" * (MAX_ID_EXTERNO + 1), "", "  ", "a\x00", "\ud800"])
    def test_un_identificador_que_no_cabe_o_no_es_firmable_descarta_la_candidata(self, ident):
        assert self.firmable(id_externo=ident) is None

    def test_un_identificador_numerico_se_convierte_en_texto(self):
        assert self.firmable(id_externo=796).id_externo == "796"

    def test_la_descripcion_se_depura_y_se_recorta_sin_descartar_la_candidata(self):
        d = self.firmable(descripcion="a\x00b\nc" + "z" * 5000).descripcion
        assert d.startswith("a b\nc") and len(d) == MAX_DESCRIPCION
        assert self.firmable(descripcion="\ud800\x00").descripcion is None
        assert self.firmable(descripcion="").descripcion is None and self.firmable(descripcion=None).descripcion is None

    def test_la_portada_que_no_cabe_o_no_es_firmable_se_omite_sin_descartar_la_candidata(self):
        assert self.firmable(cover_url="https://x/" + "a" * MAX_COVER_URL).cover_url is None
        assert self.firmable(cover_url="https://x/\ud800").cover_url is None
        assert self.firmable(cover_url="https://x/" + "a" * (MAX_COVER_URL - len("https://x/"))).cover_url is not None
        assert self.firmable(cover_url=None).cover_url is None

    @pytest.mark.parametrize("anio", [ANIO_MIN_FIRMABLE - 1, ANIO_MAX_FIRMABLE + 1, 10**30, True])
    def test_un_anio_imposible_se_ignora_sin_descartar_la_candidata(self, anio):
        c = self.firmable(anio=anio)
        assert c is not None and c.anio is None

    def test_lo_que_produce_lo_acepta_el_verificador(self):
        c = self.firmable(titulo=" X " * 100, descripcion="y" * 3000)
        assert verificar_token_candidata(crear_token_candidata(CLAVE, c, SECRETO), CLAVE, SECRETO) == c


# ── 5. Los límites de la petición ─────────────────────────────────────────────────────────────────

class TestLimitesDeLaPeticion:

    def test_el_campo_candidata_admite_el_maximo_de_candidata(self):
        assert maximo_de_campo(PeticionPrevisualizarAlta, "candidata") == MAX_TOKEN_CANDIDATA

    def test_el_campo_token_de_la_confirmacion_admite_el_maximo_de_alta(self):
        assert maximo_de_campo(PeticionConfirmarAlta, "token") == MAX_TOKEN_ALTA

    def test_el_titulo_manual_admite_la_cota_de_titulo(self):
        assert maximo_de_campo(DatosManualesIn, "titulo") == MAX_TITULO

    def test_el_token_de_vinculacion_no_cambia(self):
        """Esta corrección no toca el formato, la firma ni el máximo del token de vinculación (#103)."""
        assert MAX_TOKEN_VINCULACION == 56029
        assert maximo_de_campo(PeticionVincular, "token") == MAX_TOKEN_VINCULACION
