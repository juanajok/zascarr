"""
tests/test_naming_core.py

Suite de tests para los dos módulos más críticos del Comic Intelligence Engine.
Cubre el 80% del valor con el 20% del esfuerzo: casos reales de filenames
caóticos de la escena que el sistema debe resolver correctamente.

Ejecutar:
    make test
    # o directamente:
    pytest tests/test_naming_core.py -v
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from zascarr.core.importer_triage import (
    ComicInfo,
    TriageResult,
    guess_source_tag,
    parse_comic_info,
    triage,
)
from zascarr.core.matcher import (
    MatchStatus,
    SeriesHit,
    SeriesMatcher,
    normalize_title,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. normalize_title — la función más usada de todo el sistema
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizeTitle:
    """Cada caso aquí representa un bug real que hemos visto o anticipamos."""

    def test_articulo_inicial_the(self):
        assert normalize_title("The Sandman") == normalize_title("Sandman, The")

    def test_articulo_inicial_el(self):
        assert normalize_title("El Eternauta") == normalize_title("Eternauta")

    def test_articulo_inicial_la(self):
        assert normalize_title("La Mansión de Arkanham") == "mansion de arkanham"

    def test_acentos_eliminados(self):
        assert normalize_title("Mortadelo y Filemón") == "mortadelo y filemon"

    def test_tilde_en_n(self):
        # ñ → n (NFKD: n + combining tilde)
        assert normalize_title("Mortadelo y Filemón") == \
               normalize_title("Mortadelo y Filemon")

    def test_abreviaciones_shield(self):
        # Bug original: "S.H.I.E.L.D." → "s h i e l d" (con espacios)
        # Corrección:  "S.H.I.E.L.D." → "shield"
        result = normalize_title("S.H.I.E.L.D.")
        assert result == "shield"
        # Y debe coincidir con la DB donde está sin puntos
        assert result == normalize_title("SHIELD")

    def test_abreviaciones_bprd(self):
        assert normalize_title("B.P.R.D.") == normalize_title("BPRD")

    def test_puntuacion_eliminada(self):
        assert normalize_title("Batman: Year One") == "batman year one"

    def test_guion_eliminado(self):
        assert normalize_title("Spider-Man") == "spider man"

    def test_collapse_espacios(self):
        assert normalize_title("  Batman   (2011) ") == "batman 2011"

    def test_numeros_conservados(self):
        # Los números en el título (no en el número de issue) se conservan
        assert normalize_title("2000 AD") == "2000 ad"

    def test_titulo_vacio(self):
        assert normalize_title("") == ""

    def test_titulo_solo_articulo(self):
        # Caso patológico: título = solo artículo
        assert normalize_title("The") == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. guess_source_tag — heurística de origen del release
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuessSourceTag:
    """El tag debe extraerse del sufijo de release, no del título de la obra."""

    def test_digital_en_sufijo(self):
        assert guess_source_tag("Batman #012 (2013) (Digital).cbz") == "digital"

    def test_digital_en_titulo_no_debe_matchear(self):
        # "Digital Conan" NO es una release digital, es el título de la obra
        # Bug original: el código buscaba en el stem completo
        assert guess_source_tag("Digital Conan Vol.01.cbz") is None

    def test_scan_detectado(self):
        assert guess_source_tag("Mortadelo #001 (Scan).cbz") == "scan"

    def test_c2c_detectado(self):
        assert guess_source_tag("Batman 001 (c2c).cbz") == "scan"

    def test_hd_detectado(self):
        assert guess_source_tag("Saga 001 (HD).cbz") == "scan_hq"

    def test_sin_parentesis_no_hay_fallback_al_stem(self):
        # Sin bloque de paréntesis no hay tag, ni aunque "Digital" aparezca
        # en el título: sería el mismo falso positivo que Digital Conan.
        assert guess_source_tag("Digital Edition Batman.cbz") is None

    def test_sin_tag(self):
        assert guess_source_tag("Batman #001.cbz") is None

    def test_case_insensitive(self):
        assert guess_source_tag("Batman (DIGITAL).cbz") == "digital"

    def test_zone_empire_grupo_no_tag(self):
        # Los grupos de release (Zone-Empire) no deben detectarse como tag
        assert guess_source_tag("Batman 012 (Zone-Empire).cbz") is None

    def test_webrip(self):
        assert guess_source_tag("Sandman 001 (Webrip).cbz") == "digital"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. parse_comic_info — parseo del XML interno
# ═══════════════════════════════════════════════════════════════════════════════

MINIMAL_COMIC_INFO = (
    '<?xml version="1.0" encoding="utf-8"?>'
    "<ComicInfo>"
    "<Series>Batman</Series>"
    "<Number>12</Number>"
    "<Volume>2</Volume>"
    "<Year>2013</Year>"
    "<Publisher>ECC Ediciones</Publisher>"
    "<Writer>Scott Snyder</Writer>"
    "<Penciller>Greg Capullo</Penciller>"
    "<Inker>Jonathan Glapion</Inker>"
    "<Summary>La Corte de los Buhos concluye.</Summary>"
    "<PageCount>32</PageCount>"
    "<LanguageISO>es</LanguageISO>"
    "</ComicInfo>"
).encode("utf-8")

MULTI_WRITER_COMIC_INFO = b"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo>
  <Series>Saga</Series>
  <Number>1</Number>
  <Writer>Brian K. Vaughan, Fiona Staples</Writer>
  <Penciller>Fiona Staples</Penciller>
</ComicInfo>"""

MALFORMED_COMIC_INFO = b"<ComicInfo><Series>Batman</ComicInfo>"

class TestParseComicInfo:

    def test_campos_basicos(self):
        info = parse_comic_info(MINIMAL_COMIC_INFO)
        assert info.series == "Batman"
        assert info.number == "12"
        assert info.volume == 2
        assert info.year == 2013
        assert info.publisher == "ECC Ediciones"
        assert info.page_count == 32
        assert info.language_iso == "es"

    def test_creditos_simples(self):
        info = parse_comic_info(MINIMAL_COMIC_INFO)
        assert info.credits["writer"] == ["Scott Snyder"]
        assert info.credits["penciler"] == ["Greg Capullo"]  # 'penciller' → 'penciler'
        assert info.credits["inker"] == ["Jonathan Glapion"]

    def test_creditos_multi_autor(self):
        info = parse_comic_info(MULTI_WRITER_COMIC_INFO)
        assert info.credits["writer"] == ["Brian K. Vaughan", "Fiona Staples"]

    def test_penciller_doble_l_mapeado_correctamente(self):
        # ComicInfo usa "Penciller" (doble L); nuestro enum usa "penciler" (una L)
        info = parse_comic_info(MINIMAL_COMIC_INFO)
        assert "penciler" in info.credits
        assert "penciller" not in info.credits

    def test_xml_malformado_lanza_parse_error(self):
        from xml.etree.ElementTree import ParseError
        with pytest.raises(ParseError):
            parse_comic_info(MALFORMED_COMIC_INFO)

    def test_campos_faltantes_son_none(self):
        xml = b"<ComicInfo><Series>Akira</Series></ComicInfo>"
        info = parse_comic_info(xml)
        assert info.series == "Akira"
        assert info.number is None
        assert info.year is None
        assert info.credits == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TriageResult.strong_candidate
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrongCandidate:

    def _result_with(self, series=None, number=None) -> TriageResult:
        ci = ComicInfo(series=series, number=number)
        return TriageResult(path=Path("test.cbz"), comic_info=ci)

    def test_candidato_fuerte_con_serie_y_numero(self):
        r = self._result_with("Batman", "12")
        assert r.strong_candidate is True

    def test_sin_comic_info_no_es_fuerte(self):
        r = TriageResult(path=Path("test.cbz"))
        assert r.strong_candidate is False

    def test_sin_numero_no_es_fuerte(self):
        r = self._result_with("Batman", None)
        assert r.strong_candidate is False

    def test_sin_serie_no_es_fuerte(self):
        r = self._result_with(None, "12")
        assert r.strong_candidate is False


# ═══════════════════════════════════════════════════════════════════════════════
# 5. triage() — integración con un ZIP real en memoria
# ═══════════════════════════════════════════════════════════════════════════════

def make_cbz(comic_info_xml: bytes | None = None,
             pages: list[str] | None = None) -> Path:
    """Crea un CBZ en /tmp con contenido mínimo para tests."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if comic_info_xml:
            zf.writestr("ComicInfo.xml", comic_info_xml)
        for page_name in (pages or ["001.jpg"]):
            # Imagen PNG 1x1 mínima
            zf.writestr(page_name, _minimal_png())
    path = Path(f"/tmp/test_{uuid4().hex[:8]}.cbz")
    path.write_bytes(buf.getvalue())
    return path


def _minimal_png() -> bytes:
    """PNG 1x1 píxel válido (para que Pillow pueda leerlo)."""
    import struct, zlib
    def chunk(name, data):
        c = struct.pack(">I", len(data)) + name + data
        return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"\x00\xFF\xFF\xFF"))
    png += chunk(b"IEND", b"")
    return png


class TestTriage:

    def test_cbz_con_comic_info(self, tmp_path):
        path = make_cbz(comic_info_xml=MINIMAL_COMIC_INFO)
        result = triage(path)
        assert result.sha256 is not None
        assert len(result.sha256) == 64
        assert result.strong_candidate is True
        assert result.comic_info.series == "Batman"
        assert result.comic_info.number == "12"
        assert result.width_px == 1  # PNG 1x1
        assert result.warnings == []
        path.unlink()

    def test_cbz_sin_comic_info(self, tmp_path):
        path = make_cbz(comic_info_xml=None)
        result = triage(path)
        assert result.sha256 is not None
        assert result.strong_candidate is False
        assert result.comic_info is None
        path.unlink()

    def test_cbz_con_comic_info_malformado(self):
        path = make_cbz(comic_info_xml=b"<malformed>")
        result = triage(path)
        assert result.comic_info is None
        assert any("malformado" in w for w in result.warnings)
        path.unlink()

    def test_cbr_pasa_a_capa_1_pero_si_se_hashea(self, tmp_path):
        """Este test afirmaba `sha256 is None` con el comentario "no se
        intenta abrir el RAR", confundiendo dos cosas distintas: no
        abrirlo (correcto, haría falta unrar) y no hashearlo (un bug,
        dejaba sin dedupe a toda una biblioteca de CBR). El hash son los
        bytes del fichero, no su contenido descomprimido."""
        path = tmp_path / "test.cbr"
        path.write_bytes(b"Rar!")  # header mínimo RAR
        result = triage(path)
        assert result.comic_info is None  # el RAR no se abre: eso sigue igual
        assert result.sha256 is not None  # pero el dedupe necesita el hash
        assert any("triaje solo por filename" in w for w in result.warnings)

    def test_source_tag_detectado(self):
        path = make_cbz(comic_info_xml=MINIMAL_COMIC_INFO)
        # Renombramos a un nombre con tag
        tagged = path.parent / "Batman 012 (2013) (Digital).cbz"
        path.rename(tagged)
        result = triage(tagged)
        assert result.source_tag == "digital"
        tagged.unlink()

    def test_orden_natural_paginas(self):
        """página10 no debe ir antes que página2."""
        path = make_cbz(pages=["pagina10.jpg", "pagina2.jpg", "pagina1.jpg"])
        result = triage(path)
        # Si el orden natural funciona, width_px viene de pagina1.jpg (1px)
        assert result.width_px == 1
        path.unlink()

    def test_zip_corrupto_no_lanza_excepcion(self, tmp_path):
        path = tmp_path / "corrupto.cbz"
        path.write_bytes(b"esto no es un zip")
        result = triage(path)
        assert result.sha256 is None
        assert any("ilegible" in w for w in result.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. SeriesMatcher.decide() — lógica de decisión del matcher
#    Tests sin DB real: mockean el session de SQLAlchemy.
# ═══════════════════════════════════════════════════════════════════════════════

def make_triage_result(series="Batman", number="12", year=None,
                       volume=None) -> TriageResult:
    ci = ComicInfo(series=series, number=number, year=year, volume=volume)
    return TriageResult(path=Path("batman.cbz"), comic_info=ci)


def make_session_mock(series_hits: list[SeriesHit],
                      issue_id: UUID | None = uuid4(),
                      alias_hit: SeriesHit | None = None) -> AsyncMock:
    """Mock de AsyncSession que devuelve series_hits en find_series,
    issue_id en find_issue, y alias_hit en find_alias (B13 — None por
    defecto: sin alias local aprendido, el camino normal de estos tests)."""
    session = AsyncMock()

    async def execute_side_effect(query, params=None):
        result_mock = MagicMock()
        norm = (params or {}).get("norm", "")
        sid = (params or {}).get("sid", "")

        # OJO: no dispatchar mirando si "series" está en el SQL — la query
        # de find_issue hace "FROM issues WHERE series_id = ...", así que
        # "series" (de "series_id") también aparecería ahí y esta rama
        # nunca se alcanzaría. Hay que mirar la tabla real (FROM issues).
        if "FROM issues" in str(query):
            row = MagicMock(id=str(issue_id)) if issue_id else None
            result_mock.first = MagicMock(return_value=row)
            return result_mock
        elif "local_aliases" in str(query):  # find_alias (B13)
            row = None
            if alias_hit is not None:
                row = MagicMock(id=str(alias_hit.series_id), title=alias_hit.title,
                                 start_year=alias_hit.start_year)
            result_mock.first = MagicMock(return_value=row)
            return result_mock
        else:  # find_series query
            rows = [
                MagicMock(id=str(h.series_id), title=h.title,
                          start_year=h.start_year, score=h.score)
                for h in series_hits
            ]
            result_mock.__iter__ = MagicMock(return_value=iter(rows))
            result_mock.scalars = MagicMock(return_value=rows)
            return result_mock

    session.execute = execute_side_effect
    return session


class TestSeriesMatcherDecide:

    @pytest.mark.asyncio
    async def test_match_directo_con_strong_candidate(self):
        sid = uuid4()
        iid = uuid4()
        hits = [SeriesHit(sid, "Batman", 2011, 1.0)]
        session = make_session_mock(hits, iid)

        matcher = SeriesMatcher(session)
        result = await matcher.decide(make_triage_result("Batman", "12"))

        assert result.status == MatchStatus.DIRECT
        assert result.series_id == sid
        assert result.issue_id == iid
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_match_fuzzy(self):
        sid = uuid4()
        iid = uuid4()
        hits = [SeriesHit(sid, "Batman: The Dark Knight", 2011, 0.75)]
        session = make_session_mock(hits, iid)

        matcher = SeriesMatcher(session)
        result = await matcher.decide(make_triage_result("Batman Dark Knight", "5"))

        assert result.status == MatchStatus.FUZZY
        assert result.score == 0.75

    @pytest.mark.asyncio
    async def test_sin_hits_va_a_unsorted(self):
        session = make_session_mock([])
        matcher = SeriesMatcher(session)
        result = await matcher.decide(make_triage_result("Desconocida", "1"))

        assert result.status == MatchStatus.UNSORTED

    @pytest.mark.asyncio
    async def test_empate_ambiguo_va_a_unsorted(self):
        """Dos series con el mismo score: ninguna gana, va a _Unsorted/."""
        sid1, sid2 = uuid4(), uuid4()
        hits = [
            SeriesHit(sid1, "Batman", 1940, 1.0),
            SeriesHit(sid2, "Batman", 2011, 1.0),
        ]
        session = make_session_mock(hits)
        matcher = SeriesMatcher(session)
        result = await matcher.decide(make_triage_result("Batman", "12"))

        assert result.status == MatchStatus.UNSORTED
        assert "empate ambiguo" in result.notes[0]
        assert len(result.candidates) == 2

    @pytest.mark.asyncio
    async def test_desambiguacion_por_año_resuelve_empate(self):
        """Dos Batman, el año en ComicInfo apunta al correcto."""
        sid1, sid2 = uuid4(), uuid4()
        iid = uuid4()
        hits = [
            SeriesHit(sid1, "Batman", 1940, 1.0),
            SeriesHit(sid2, "Batman", 2011, 1.0),
        ]
        session = make_session_mock(hits, iid)
        matcher = SeriesMatcher(session)

        # ComicInfo dice Year=2012 (dentro de la tolerancia ±1 del matcher)
        # → debe matchear Batman (2011), no (1940)
        result = await matcher.decide(
            make_triage_result("Batman", "12", year=2012)
        )
        assert result.status == MatchStatus.DIRECT
        assert result.series_id == sid2

    @pytest.mark.asyncio
    async def test_sin_titulo_va_a_unsorted(self):
        session = make_session_mock([])
        matcher = SeriesMatcher(session)
        triage_res = TriageResult(path=Path("unknown.cbz"))
        result = await matcher.decide(triage_res)

        assert result.status == MatchStatus.UNSORTED

    @pytest.mark.asyncio
    async def test_issue_no_encontrado_anota_nota(self):
        """El matcher sigue reportando la serie aunque el issue no exista."""
        sid = uuid4()
        hits = [SeriesHit(sid, "Saga", 2012, 1.0)]
        session = make_session_mock(hits, issue_id=None)
        matcher = SeriesMatcher(session)

        result = await matcher.decide(make_triage_result("Saga", "99"))

        assert result.series_id == sid
        assert result.issue_id is None
        assert any("enricher" in n for n in result.notes)

    @pytest.mark.asyncio
    async def test_extractor_capa_1_se_usa_sin_comic_info(self):
        """Sin strong_candidate, el extractor (naming.py) se invoca."""
        sid = uuid4()
        iid = uuid4()
        hits = [SeriesHit(sid, "Sandman", 1989, 1.0)]
        session = make_session_mock(hits, iid)

        extractor = lambda filename: ("Sandman", "1", 1989)
        triage_res = TriageResult(path=Path("Sandman_001_(1989).cbz"))

        matcher = SeriesMatcher(session)
        result = await matcher.decide(triage_res, extractor=extractor)

        assert result.status == MatchStatus.DIRECT
        assert result.series_id == sid


class TestSeriesMatcherAlias:
    """B13: un alias local aprendido (ReviewService._learn_alias tras una
    asignación manual en Pendientes) manda sobre el fuzzy — se consulta
    ANTES de find_series, y ni siquiera se llega a ejecutar esa query."""

    @pytest.mark.asyncio
    async def test_alias_encontrado_gana_al_fuzzy(self):
        """Aunque find_series() devolvería candidatos distintos/ambiguos,
        el alias resuelve directo sin tocar esa rama."""
        sid_alias = uuid4()
        iid = uuid4()
        alias_hit = SeriesHit(sid_alias, "La Patrulla-X", 1985, 1.0)
        # Candidatos de fuzzy que NO deberían usarse si el alias gana:
        hits_fuzzy_que_no_deben_usarse = [
            SeriesHit(uuid4(), "Otra Cosa", 1990, 0.9),
            SeriesHit(uuid4(), "Otra Cosa Más", 1991, 0.9),
        ]
        session = make_session_mock(hits_fuzzy_que_no_deben_usarse, iid, alias_hit=alias_hit)
        matcher = SeriesMatcher(session)

        result = await matcher.decide(make_triage_result("La Patrulla X Omnigold", "12"))

        assert result.status == MatchStatus.DIRECT
        assert result.series_id == sid_alias
        assert result.issue_id == iid
        assert "alias local aprendido" in result.notes

    @pytest.mark.asyncio
    async def test_sin_alias_sigue_el_camino_normal(self):
        """Sin fila en local_aliases, decide() se comporta exactamente
        como antes de B13 — find_alias no interfiere."""
        sid = uuid4()
        iid = uuid4()
        hits = [SeriesHit(sid, "Batman", 2011, 1.0)]
        session = make_session_mock(hits, iid, alias_hit=None)
        matcher = SeriesMatcher(session)

        result = await matcher.decide(make_triage_result("Batman", "12"))

        assert result.status == MatchStatus.DIRECT
        assert result.series_id == sid

    @pytest.mark.asyncio
    async def test_alias_con_issue_no_registrado_anota_nota(self):
        sid_alias = uuid4()
        alias_hit = SeriesHit(sid_alias, "La Patrulla-X", 1985, 1.0)
        session = make_session_mock([], issue_id=None, alias_hit=alias_hit)
        matcher = SeriesMatcher(session)

        result = await matcher.decide(make_triage_result("La Patrulla X Omnigold", "99"))

        assert result.series_id == sid_alias
        assert result.issue_id is None
        assert any("alias local aprendido" in n for n in result.notes)
        assert any("enricher" in n for n in result.notes)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Casos de filenames reales de la escena (end-to-end naming)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealWorldFilenames:
    """Casos que deben pasar por naming.py (Capa 1).

    Estos tests importan naming.py directamente para validar
    que los patrones de naming.py producen el output correcto.
    Son los tests más valiosos del proyecto y deben crecer con
    cada bug de naming que encuentres en producción.
    """

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        ("Batman_v2_012.cbz",                   "Batman",    "12"),
        ("Saga 001 (2013).cbz",                 "Saga",      "1"),
        ("One Piece c1054.cbz",                 "One Piece", "1054"),
        ("Batman (New 52) 012 (2013).cbz",      "Batman",    "12"),
        ("Sandman.001.(1989).(Digital).cbz",    "Sandman",   "1"),
        # "Berserk Vol.01" ya NO es "sin número" — ver B15 en
        # TestEdicionesComoIdentificador más abajo: el propio tomo/volumen
        # es el identificador cuando no hay otro número en el nombre.
        ("MF #001 - Safari Callejero.cbz",      "MF",        "1"),
        ("Asterix T01 - Asterix el Galo.cbz",   "Asterix",   "1"),
    ])
    def test_parse_filename(self, filename, expected_series, expected_num):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert (result.issue_number or None) == expected_num

    def test_guion_pegado_no_se_confunde_con_subtitulo(self):
        """'Spider-Man' no tiene espacios alrededor del guion: a diferencia
        de ' - Subtítulo', no debe cortarse el título por ahí."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Spider-Man 001.cbz")
        assert result.issue_number == "1"
        # El guion sigue colapsando a espacio en la limpieza final (mismo
        # criterio que matcher.normalize_title), pero el título no se trunca.
        assert result.series == "Spider Man"

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        # Casos reales reportados en producción (colección CRG en español).
        # "Marvel Gold - La Patrulla-X Original 1": el "1" es un número
        # suelto sin marcador de edición delante — issue_number real.
        ("Marvel Gold - La Patrulla-X Original 1 .cbr",
         "La Patrulla X Original", "1"),
    ])
    def test_parse_filename_real_world_crg(self, filename, expected_series, expected_num):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    @pytest.mark.parametrize("filename,expected_series,expected_num,expected_kind", [
        # RF-07 (2026-09-25) decidió que el número de Omnigold/Integral
        # NUNCA debía capturarse como issue_number, para no confundirlo
        # con la grapa original — así que estos dos casos se quedaban
        # sin número, con la serie más precisa pero sin poder clasificar
        # solos. Medido al día siguiente (B15, 2026-09-26): eso mandaba a
        # Pendientes TODOS los Omnigold/Integral de la biblioteca sin
        # necesidad, porque el modelo ya tenía `Issue.format` (omnibus/
        # trade_paperback/...) para distinguir "recopilación" de "grapa
        # suelta" sin tocar `issue_number`. Se revierte: el número SÍ se
        # captura, marcado con `edition_kind` para que quien cree el
        # Issue (ReviewService) le ponga el `format` correcto.
        ("La Patrulla X Omnigold 5 (Decisiones) [CRG].cbr", "La Patrulla X Omnigold", "5", "omnigold"),
        ("The Boys - Edición Integral 01 [por The RockJR][CRG].cbr", "The Boys", "1", "integral"),
    ])
    def test_omnigold_integral_capturan_el_numero_con_edition_kind(
        self, filename, expected_series, expected_num, expected_kind
    ):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num
        assert result.edition_kind == expected_kind


    def test_sin_numero_real_no_inventa_uno(self):
        """'[ML] La Patrulla-X - Los Años Perdidos [MQ][DI] by The Murdock
        [CRG].cbr': una recopilación sin número de grapa. El parser debe
        limpiar los corchetes de release y quedarse con la serie, sin
        inventar un número que no existe en el nombre."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "[ML] La Patrulla-X - Los Años Perdidos [MQ][DI] by The Murdock [CRG].cbr"
        )
        assert result.series == "La Patrulla X"
        assert result.issue_number == ""

    @pytest.mark.parametrize("filename,expected_series,expected_num,expected_year", [
        # Fecha de publicación de los scans digitales (DCP/Novus): el
        # "(2004-08)" se registraba como el NÚMERO DE GRAPA 2004.
        ("JSA (2004-08) 62 (digital) (OkC.O.M.P.U.T.O.-Novus-HD).cbz", "JSA", "62", 2004),
        ("JSA (1999-08) 01 (digital) (DreamGirl-Novus-HD).cbz", "JSA", "1", 1999),
        ("JSA 81 (2006) (Lightray-DCP).cbr", "JSA", "81", 2006),
    ])
    def test_fecha_de_publicacion_no_es_el_numero_de_grapa(
        self, filename, expected_series, expected_num, expected_year
    ):
        """Bug real (biblioteca del coleccionista, 2026-09-25): un JSA
        #2004 inventado a partir de la fecha. Peor que no clasificar,
        porque la sugerencia de un clic (B12) lo daba por bueno y el
        alias local (B13) lo aprendía.

        La primera corrección solo lograba que NO hubiera número; ahora
        además se saca el correcto, porque el ruido entre paréntesis se
        limpia antes de buscarlo y el 62 deja de estar a media cadena."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.issue_number == expected_num
        assert result.issue_number != str(expected_year)  # la garantía de fondo
        assert result.series == expected_series
        assert result.year == expected_year

    def test_prefijo_de_orden_de_lectura_no_es_el_numero_de_grapa(self):
        """'247.- Wonder Woman v2 214': el 247 numera la colección del
        coleccionista, la grapa es la 214. Antes ganaba el 247 por ser
        el primer número de 3 cifras del nombre."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("247.- Wonder Woman v2 214 Por Mr Miracle & Feddzor.cbr")
        assert result.series == "Wonder Woman"
        assert result.issue_number == "214"
        assert result.volume == 2

    @pytest.mark.parametrize("filename", [
        "La Imposible Patrulla X (144-158) Contra Magneto (Actualizado) [CRG].cbr",
        "Superman Vol2 049-051a [SC][HMERL].cbr",
    ])
    def test_un_rango_no_se_queda_con_el_primer_numero(self, filename):
        """Un pack que cubre 144-158 no es el número 144: afirmar eso es
        inventar una pertenencia que el archivo no dice. Sin número va a
        Pendientes, que es la respuesta honesta."""
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename(filename).issue_number == ""

    def test_rango_no_deja_huerfano_el_parentesis_de_cierre(self):
        """Encontrado arreglando el caso de arriba: quitar "(122-143" sin
        poder quitar el ")" dejaba "La Patrulla X usa) Omnigold..." como
        título, que envenena matching y alias."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "La Patrulla X (122-143 usa) Omnigold nº 2 Días del futuro pasado [Actualizado] (crg).cbr"
        )
        assert ")" not in result.series
        # El "nº 2" ya se reconoce como número (numeración española), así
        # que el título queda limpio en vez de arrastrar el subtítulo.
        assert result.series == "La Patrulla X Omnigold"
        assert result.issue_number == "2"

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        # El idiom más común de la escena en español: el número va antes
        # del subtítulo, no al final. Se quedaba pegado al título
        # ("Astérix 01"), así que ninguna serie igualaba jamás.
        ("Astérix (DI) 01 - Astérix el galo [Raven Co.][CRG].cbr", "Astérix", "1"),
        ("AIDP 05 - La Llama Negra [SC][por R.I.P.][CRG].cbr", "AIDP", "5"),
        ("Gideon Falls 01 - El Granero Negro [SC][por jbabylon5][CRG].cbr", "Gideon Falls", "1"),
        ("Fatale 04 - Reza Para que Llueva [por Aluci][CRG].cbr", "Fatale", "4"),
        ("Parker 04 - Matadero [SC][por Jbabylon5][CRG].cbr", "Parker", "4"),
    ])
    def test_numero_antes_del_subtitulo_no_se_queda_pegado_al_titulo(
        self, filename, expected_series, expected_num
    ):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        # Numeración española: no estaba cubierta en absoluto.
        ("Patrulla-X, nº 03 (122) [enriquechiper CRG].cbr", "Patrulla X", "3"),
        # Mojibake CP437 de "º" — medio catálogo de scans viene así.
        ("WildCATS vol1 n║05 por Cnavalon.cbr", "WildCATS", "5"),
    ])
    def test_numero_con_notacion_espanola(self, filename, expected_series, expected_num):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    def test_numero_con_sufijo_de_letra(self):
        """Las entregas partidas de Zinco ("123a", "123b") perdían el
        número entero porque los patrones solo aceptaban cifras."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Superman Vol2 123a [SC][CRG].cbr")
        assert result.series == "Superman"
        assert result.issue_number == "123a"

    def test_especial_no_forma_parte_del_nombre_de_la_serie(self):
        """"Superman Vol2 Especial 2" es el especial nº 2 de Superman, no
        una serie llamada "Superman Especial" que no iguala con nada."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Superman Vol2 Especial 2 [SC][CRG].cbz")
        assert result.series == "Superman"
        assert result.issue_number == "2"
        assert result.is_annual

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        ("Promethea Vol1 11 por TheRockJR [CRG].cbr", "Promethea", "11"),
        ("069.- Flash v2 62 By Spiderman2099.cbr", "Flash", "62"),
    ])
    def test_creditos_del_uploader_no_son_parte_del_titulo(
        self, filename, expected_series, expected_num
    ):
        """Además de ensuciar el título, tapaban el número: lo dejaban a
        media cadena, donde ningún patrón lo buscaba."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    def test_puntos_como_separador_no_esconden_el_numero(self):
        """Con los puntos sin convertir, ni el "3" ni el corte de subtítulo
        se reconocían y el título arrastraba a los autores."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "El.departamento.de.la.verdad.3.-.James.Tynion.IV.&.Martin.Simmonds."
            "[jbabylon5][CRG].cbr"
        )
        assert result.series == "El departamento de la verdad"
        assert result.issue_number == "3"

    def test_puntos_como_separador_no_esconden_el_numero_de_edicion(self):
        """Mismo caso que arriba, pero con "Integral N": el "6" es el
        tomo de la recopilación (edition_kind="integral", no una grapa
        estándar), y los puntos no deben esconderlo — igual que antes
        tapaban un número real de grapa."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "La.Mazmorra..Integral.6.-.Sfar.&.Trondheim.&.Larcenet.[jbabylon5][CRG].cbr"
        )
        assert result.series == "La Mazmorra Integral"
        assert result.issue_number == "6"
        assert result.edition_kind == "integral"

    def test_punto_entre_cifras_sigue_siendo_un_decimal(self):
        """El paso anterior no debe romper los números decimales, que el
        modelo sí soporta (issue_number es VARCHAR por esto)."""
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename("Batman #1.5 - Interludio.cbz").issue_number == "1.5"

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        ("XIII 01 El Dia del Sol Negro.cbz", "XIII", "1"),
        ("XIII 19 Ultimo asalto [por mikar][CRG].cbr", "XIII", "19"),
    ])
    def test_numero_seguido_de_subtitulo_sin_separador(
        self, filename, expected_series, expected_num
    ):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    def test_el_numero_del_titulo_no_se_confunde_con_el_de_la_grapa(self):
        """La contrapartida del test anterior: en "Top 10 07" el 10 es
        parte del nombre. La señal es que detrás del 10 hay otra cifra y
        no una palabra."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Top 10 07.cbr")
        assert result.series == "Top 10"
        assert result.issue_number == "7"

    def test_serie_numero_numero_conserva_el_numero_del_titulo(self):
        """"Delta 99 - 04" es el número 4 de la serie "Delta 99". Sin
        esta regla el patrón de subtítulo se quedaba con el 99 y dejaba
        la serie en "Delta"."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Delta 99 - 04 [por JGM y Luzroja][CRG].cbr")
        assert result.series == "Delta 99"
        assert result.issue_number == "4"

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        ("100 Balas - Integral (Ed.Planeta) 02 [por capdiajo y ntellez][CRG].cbz", "100 Balas", "2"),
        ("52 (Integral) 01 [SC][por Elessarsquall y Funkspider][CRGfunding-CRG].cbr", "52", "1"),
    ])
    def test_serie_que_empieza_por_cifra(self, filename, expected_series, expected_num):
        """Peor de los casos posibles: "100 Balas ... 02" daba serie
        "Balas" Y número 100 — las dos cosas mal a la vez."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    def test_etiqueta_de_linea_editorial_no_es_el_titulo(self):
        """"EVENTOS - La Era de Ultrón": igual que "Marvel Gold - X", lo
        de delante del guion es la colección, no la obra."""
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename("EVENTOS - La Era de Ultrón(1).cbr").series == "La Era de Ultrón"

    def test_credito_entre_parentesis_tambien_es_credito(self):
        """"Daytripper (por Aruso) CRG 8º Aniversario": el crédito iba
        entre paréntesis, así que no se reconocía y el título arrastraba
        la firma del grupo entera."""
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename(
            "Daytripper (por Aruso) CRG 8º Aniversario.cbr"
        ).series == "Daytripper"

    def test_edicion_de_aniversario_no_es_el_numero(self):
        """"Integral 20 aniversario" es una efeméride de la editorial, no
        el número 20 de la serie. Con B15 (naming.py ya captura el número
        de Omnigold/Integral) el orden pasó a importar de verdad: si
        ANIVERSARIO_PATTERN no corriera ANTES de buscar el marcador de
        edición, "Integral 20 aniversario" capturaría el 20 como si fuera
        el tomo de la recopilación."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "Iberia Inc. - Integral 20 aniversario (Dolmen) [por capdiajo & redvirux] [CRG].cbr"
        )
        assert result.series == "Iberia Inc"
        assert result.issue_number == ""
        assert result.edition_kind is None

    def test_guion_sin_espacio_detras_tambien_separa_el_subtitulo(self):
        """La escena escribe tanto "Serie - Sub" como "Serie -Sub". El
        espacio DELANTE sigue siendo obligatorio: es lo que distingue el
        separador de un guion interno ("Spider-Man")."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "La liga de los hombres extraordinarios -La Tempestad 02 por GBWilliams-Mastergel"
            "[Infinity-Gisicom].cbr"
        )
        assert result.series == "La liga de los hombres extraordinarios"
        assert result.issue_number == "2"
        # El guion interno no se toca (ya cubierto arriba, se reafirma aquí
        # porque este cambio es el que más cerca estuvo de romperlo).
        assert parse_comic_filename("Spider-Man 001.cbz").series == "Spider Man"

    @pytest.mark.parametrize("filename", [
        # El sufijo "(1)" que deja el navegador al descargar dos veces —
        # en la biblioteca real hay ~20 pares así. No debe convertirse en
        # el número 1 del tebeo.
        "Estudio en Esmeralda [traducido por Gb, Letho y Vander][Infinity Cómics](1).cb7",
        "Arrowsmith (ECC) [Tildoras, CRG](1).cbr",
    ])
    def test_sufijo_de_copia_duplicada_no_es_un_numero(self, filename):
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename(filename).issue_number == ""

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        # El sufijo de letra en MAYÚSCULA no se reconocía en ningún
        # patrón (solo minúscula) — el peor caso real: "019B" ni se veía
        # como número, y el parser seguía buscando y encontraba OTRO
        # número más adelante en el nombre ("09" de "Bonus Book 09"),
        # dando el número de una sub-numeración distinta por error.
        ("025.- Flash v2 #22b - manhunter 09 - por polar (c.r.g.).cbr", "Flash", "22b"),
        ("018.- Flash v2 019B Dc Bonus Book 09 Por Frahumata & Kelo5000.cbr", "Flash", "19B"),
        ("010.- Flash v2 012B Dc Bonus Book 02 Por Maxrabl & Sebasbender.cbr", "Flash", "12B"),
    ])
    def test_sufijo_de_letra_en_mayuscula(self, filename, expected_series, expected_num):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    @pytest.mark.parametrize("filename", [
        # Rango escrito con palabra en vez de guion: sin esto, "210 a 211"
        # afirmaba la grapa #210 suelta cuando en realidad es un pack de
        # dos números — justo el tipo de dato falso que el proyecto
        # prefiere evitar aunque cueste un Pendientes de más.
        "239.- Flash v2 210 a 211.cbr",
        "200.- Flash v2 170 al 173 - Que corra la sangre por KS.cbr",
    ])
    def test_rango_en_palabra_no_se_queda_con_el_primer_numero(self, filename):
        from zascarr.utils.naming import parse_comic_filename

        assert parse_comic_filename(filename).issue_number == ""

    def test_entidad_html_amp_se_decodifica(self):
        """El propio nombre de archivo en disco lleva "&amp;" literal
        (no es un artefacto del navegador) — sin decodificarlo, el título
        queda roto a medias en vez de con un "&" limpio."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "WildC.A.T.S 01 (Planeta) [Cnavalon, Jrgandalf &amp; Tildoras, CRG].cbr"
        )
        assert "&amp;" not in result.series
        assert result.issue_number == "1"

    @pytest.mark.parametrize("filename,expected_series,expected_num", [
        # Orden de lectura SIN el punto ("01 - X", no "01.- X"): antes
        # solo se reconocía la forma con punto, así que el guion se
        # confundía con un separador de subtítulo y la serie se quedaba
        # en el propio número de orden ("01").
        ("01 - Irredeemable #1.cbz", "Irredeemable", "1"),
        ("19 - Irredeemable Special #1.cbz", "Irredeemable Special", "1"),
        # Con sufijo de letra Y punto a la vez ("049b.-"): el patrón
        # exigía \d{1,3} puros antes del punto, así que ni el punto se
        # reconocía y "049b" entero acababa siendo la serie.
        ("049b.- Hawkworld v2 Annual 01 Por Kelo5000.cbr", "Hawkworld", "1"),
    ])
    def test_orden_de_lectura_sin_punto_o_con_sufijo_de_letra(
        self, filename, expected_series, expected_num
    ):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

    @pytest.mark.parametrize("filename,expected_num,expected_vol", [
        # "[P1N1]", "[P2N9]": notación parte+número de un grupo concreto
        # (GunSmith Cats/Mukankakuna). Sin reconocerla, la serie entera
        # quedaba sin número — invisible para el matcher pese a tener un
        # esquema de numeración perfectamente regular.
        ("GunSmith Cats[P1N1][4k][Mukankakuna][CRG].cbr", "1", 1),
        ("GunSmith Cats[P2N9][4k][Mukankakuna][CRG].cbr", "9", 2),
        ("GunSmith Cats[P3N1][4k][Mukankakuna][CRG].cbr", "1", 3),
    ])
    def test_notacion_parte_numero_entre_corchetes(self, filename, expected_num, expected_vol):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == "GunSmith Cats"
        assert result.issue_number == expected_num
        assert result.volume == expected_vol

    def test_posicion_de_arco_no_reemplaza_al_numero_real(self):
        """"#01 - ... 1 de 4": el "1 de 4" es la posición dentro del arco
        publicado en fascículos, el número real de grapa es el que va
        tras el "#"."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(
            "Transmetropolitan - #01 - De Nuevo en la Calle 1 de 4."
            "howtoarsenio.blogspot.com.cbr"
        )
        assert result.series == "Transmetropolitan"
        assert result.issue_number == "1"

    def test_tomo_sin_otro_numero_es_el_identificador_del_archivo(self):
        """Este test se llamaba "test_tomo_sigue_siendo_volumen_no_issue"
        y afirmaba justo lo contrario, con un razonamiento que no se
        sostenía ni en su propio ejemplo ("manga/BD con tomo Y numeración
        de issue separada" — pero "Astro Boy Tomo 5" no tiene ningún otro
        número en el nombre). B15 (2026-09-26), medido sobre la biblioteca
        real: 8 de 81 archivos de la muestra oficial perdían así su único
        número ("Nancy in Hell Tomo 1", "En un rayo de sol Vol.1/2", "Los
        Inhumanos vol.3") — se guardaba en `volume` pero el matcher exige
        TAMBIÉN un `issue_number` para no mandar el archivo a Pendientes
        sin necesidad. Ahora el propio tomo/volumen hace de identificador
        cuando es el ÚNICO número del nombre, marcado con `edition_kind`
        para que no se confunda con una grapa estándar."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Astro Boy Tomo 5.cbz")
        assert result.series == "Astro Boy"
        assert result.volume == 5
        assert result.issue_number == "5"
        assert result.edition_kind == "tomo"

    @pytest.mark.parametrize("filename,expected_series,expected_num,expected_kind", [
        # Casos reales de la biblioteca del coleccionista que motivaron
        # el cambio de postura de arriba.
        ("Nancy in Hell Tomo 1.cbr", "Nancy in Hell", "1", "tomo"),
        ("En un rayo de sol Vol.1 - Tillie Walden [xavib].cbr", "En un rayo de sol", "1", "volumen"),
        ("En un rayo de sol Vol.2 - Tillie Walden [xavib].cbr", "En un rayo de sol", "2", "volumen"),
        ("Los Inhumanos vol.3 por Jiman(CRG).cbr", "Los Inhumanos", "3", "volumen"),
        ("Berserk Vol.01.cbz", "Berserk", "1", "volumen"),
    ])
    def test_tomo_o_volumen_solo_da_series_e_issue_number(
        self, filename, expected_series, expected_num, expected_kind
    ):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num
        assert result.edition_kind == expected_kind

    def test_volumen_con_otro_numero_real_no_se_toca(self):
        """El caso que YA funcionaba y no debe romperse: cuando SÍ hay un
        número de grapa además del volumen ("Vol2 05"), quedan separados
        — volume=2, issue_number=5, sin edition_kind (es una grapa
        estándar dentro de un volumen, no una edición de recopilación)."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Sleeper Vol2  05 [TM][por Kingpin y Wild][CRG].cbr")
        assert result.series == "Sleeper"
        assert result.volume == 2
        assert result.issue_number == "5"
        assert result.edition_kind is None

    def test_volumen_de_la_serie_en_un_pack_no_sustituye_al_numero_que_falta(self):
        """"Superman Vol2 049-051a": "Vol2" es el volumen DE LA SERIE
        (Zinco, años 90), no el identificador de este archivo — es un
        pack de grapas 49-51 sin número único real. Usar el "2" del
        volumen aquí sería fabricar una identidad falsa para tapar el
        hueco de un pack: exactamente lo que este proyecto evita. Bug
        real encontrado implementando el test de arriba, antes de
        comitear el cambio."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Superman Vol2 049-051a [SC][HMERL].cbr")
        assert result.series == "Superman"
        assert result.volume == 2
        assert result.issue_number == ""
        assert result.edition_kind is None
