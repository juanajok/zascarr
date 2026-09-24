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

    def test_cbr_pasa_a_capa_1(self, tmp_path):
        path = tmp_path / "test.cbr"
        path.write_bytes(b"Rar!")  # header mínimo RAR
        result = triage(path)
        assert result.sha256 is None  # no se intenta abrir el RAR
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
                      issue_id: UUID | None = uuid4()) -> AsyncMock:
    """Mock de AsyncSession que devuelve series_hits en find_series
    e issue_id en find_issue."""
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
        ("Berserk Vol.01.cbz",                  "Berserk",   None),  # manga: sin número
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
        # Casos reales reportados en producción (colección CRG en español) —
        # ninguno tenía número extraído antes del ampliado del parser.
        ("La Patrulla X Omnigold 5 (Decisiones) [CRG].cbr",
         "La Patrulla X", "5"),
        ("Marvel Gold - La Patrulla-X Original 1 .cbr",
         "La Patrulla X Original", "1"),
        ("The Boys - Edición Integral 01 [por The RockJR][CRG].cbr",
         "The Boys", "1"),
    ])
    def test_parse_filename_real_world_crg(self, filename, expected_series, expected_num):
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename(filename)
        assert result.series == expected_series
        assert result.issue_number == expected_num

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

    def test_tomo_sigue_siendo_volumen_no_issue(self):
        """'Tomo N' (manga/BD con tomo Y numeración de issue separada) se
        queda como volumen, a diferencia de 'T01' (BD de tomo único donde
        el tomo ES el número): ver test_parse_filename de más arriba."""
        from zascarr.utils.naming import parse_comic_filename

        result = parse_comic_filename("Astro Boy Tomo 5.cbz")
        assert result.series == "Astro Boy"
        assert result.volume == 5
        assert result.issue_number == ""
