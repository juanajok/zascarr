"""
matcher.py — El corazón del Comic Intelligence Engine.

Recibe un TriageResult de capa 0 y decide una única cosa: a qué (series_id,
issue_id) canónicos pertenece este archivo. Tres salidas posibles:

  direct    — match inequívoco. El importer mueve el archivo y punto.
  fuzzy     — match probabilístico >= umbral. El importer mueve el archivo y
              registra el score; revisión manual opcional via wishlist.
  unsorted  — sin match fiable o EMPATE AMBIGUO. El archivo va a _Unsorted/
              con los candidatos adjuntos para decisión humana. La ambigüedad
              NUNCA se resuelve eligiendo el primero: es la fuente principal
              de bibliotecas corrompidas silenciosamente.

Estrategia de tres capas:

  Capa 0 — si TriageResult.strong_candidate, el título y número vienen del
           ComicInfo.xml: aquí solo se VALIDA contra la DB, no se adivina.
  Capa 1 — naming.py extrae (título, número, año) del filename sucio.
           En este módulo es un inyectable (extractor) para que los
           tests lo sustituyan por fixtures.
  Capa 2 — normalización + pg_trgm contra series. El fuzzy vive en
           PostgreSQL, no en Python: un índice GIN trgm hace la query en
           milisegundos incluso sobre miles de series.

Desambiguación por año y volumen:
  - "Batman" existe como (1940), (2011), (2016). Año = discriminador canónico.
  - Si el ComicInfo trae Volume, se usa como segundo discriminador cuando el
    año no resuelve el empate (e.g., Batman Vol.1 1940 vs Batman Vol.2 2011).
  - Sin año ni volumen y con varios candidatos => unsorted. Punto.

Correcciones respecto al diseño original:
  - normalize_title elimina puntos de abreviaciones antes de la limpieza
    general: "S.H.I.E.L.D." → "shield" en lugar de "s h i e l d".
  - decide() usa el campo Volume del ComicInfo como segundo discriminador
    cuando year no resuelve el empate entre candidatos.

Requisito de esquema:
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  CREATE INDEX ix_series_title_trgm ON series USING gin (title gin_trgm_ops);
  (Ya incluido en la migración Alembic 0001.)
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

# Umbral de similarity() de pg_trgm.
# 0.35: discrimina bien títulos cortos con tokens distintivos ("Sandman").
# Bajarlo genera cruces tipo "Thor" ~ "Thorgal".
# Ajustar SOLO con la suite de tests de naming en verde.
SIMILARITY_THRESHOLD = 0.35
FUZZY_THRESHOLD = 0.60      # por debajo: ruido, aunque supere el WHERE

# B15: valor con el que se persiste una grapa suelta (models.IssueFormat.
# SINGLE_ISSUE). Se repite como literal a propósito: core/ no importa models/
# en ningún sitio y no es el momento de romper esa frontera. Un test
# (`test_formato_grapa_coincide_con_el_enum`) comprueba que siguen coincidiendo.
FORMATO_GRAPA = "single_issue"

_ARTICLE_WORDS = r"the|el|la|los|las|le|les|il|lo|die|der|das"
# Artículo inicial: "The Sandman" → "Sandman". El (?:\s+|$) en vez de \s+
# a secas cubre el caso patológico de un título que ES solo el artículo
# ("The" a secas), que antes no matcheaba por no tener nada detrás.
_ARTICLE_LEADING = re.compile(rf"^(?:{_ARTICLE_WORDS})(?:\s+|$)", re.IGNORECASE)
# Artículo pospuesto tras coma: "Sandman, The" → "Sandman".
_ARTICLE_TRAILING = re.compile(rf",\s*(?:{_ARTICLE_WORDS})\s*$", re.IGNORECASE)
_ABBREV = re.compile(r"(?<=\w)\.(?=\w)")   # punto entre letras → eliminar
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Normalización para matching: minúsculas, sin acentos, sin artículo
    inicial o pospuesto, sin puntuación.

    Decisiones documentadas:
    - Acentos eliminados (NFKD): los filenames de la escena son ASCII-seguros
      incluso para tebeos españoles ('Nausicaa' sin tilde por compatibilidad
      SMB). La DB puede tener tildes, pero la normalización las quita a ambos.
      **Precio aceptado a sabiendas:** plegar `ñ` a `n` une palabras distintas
      («año» y «ano», «caña» y «cana»). Para COMPARAR títulos compensa —un
      release sin tildes tiene que encontrar «Astérix» o «Doña Urraca»— y la
      colisión está acotada: el filtro sigue exigiendo el mismo número y, si hay
      alias, el mismo patrón.
    - Abreviaciones: "S.H.I.E.L.D." → "shield" (no "s h i e l d").
      El paso _ABBREV elimina puntos entre letras antes de la limpieza general.
    - 'The Sandman' y 'Sandman, The' colapsan al mismo valor: el artículo
      pospuesto tras coma se quita ANTES que el inicial, porque tras quitar
      la coma "Sandman The" ya no tiene el artículo al principio.
    """
    nfkd = unicodedata.normalize("NFKD", title)
    asciiish = "".join(c for c in nfkd if not unicodedata.combining(c))
    no_abbrev = _ABBREV.sub("", asciiish)           # S.H.I.E.L.D. → SHIELD
    no_trailing_article = _ARTICLE_TRAILING.sub("", no_abbrev.strip())
    no_article = _ARTICLE_LEADING.sub("", no_trailing_article.strip())
    no_punct = _PUNCT.sub(" ", no_article)
    return _WS.sub(" ", no_punct).strip().lower()


class MatchStatus(StrEnum):
    DIRECT = "direct"
    FUZZY = "fuzzy"
    UNSORTED = "unsorted"


@dataclass
class SeriesHit:
    series_id: UUID
    title: str
    start_year: int | None
    score: float         # 1.0 si exacto tras normalizar; similarity() si trgm


@dataclass
class MatchResult:
    status: MatchStatus
    series_id: UUID | None = None
    issue_id: UUID | None = None
    score: float = 0.0
    candidates: list[SeriesHit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SeriesMatcher:
    """Decisión de pertenencia. Stateless salvo la sesión; una instancia por
    ciclo de importación."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Capa 2: búsqueda en series ───────────────────────────────────────────

    async def find_series(
        self,
        raw_title: str,
        year: int | None = None,
        volume: int | None = None,
    ) -> list[SeriesHit]:
        """Exacto normalizado primero; trgm después.

        Desambiguación por año (±1) y, si el empate persiste, por volumen.
        Orden de prioridad: exacto → por año → por volumen → fuzzy completo.
        """
        norm = normalize_title(raw_title)

        # ── Exacto normalizado ───────────────────────────────────────────────
        # title_norm es una columna generada por Postgres (f_title_norm(title),
        # migración 0006) que espeja normalize_title(): antes se comparaba
        # contra lower(title) crudo y un título acentuado en la BD ("Nausicaä")
        # nunca hacía exact-match con un archivo sin tilde ("Nausicaa") — H1
        # del peer review v2.
        exact = await self.db.execute(sa.text("""
            SELECT id, title, start_year, 1.0::float AS score
            FROM series
            WHERE title_norm = :norm
               OR f_title_norm(COALESCE(sort_title, '')) = :norm
        """), {"norm": norm})
        hits = [SeriesHit(UUID(str(r.id)), r.title, r.start_year, r.score)
                for r in exact]

        # ── Fuzzy si no hay exacto ───────────────────────────────────────────
        if not hits:
            fuzzy = await self.db.execute(sa.text("""
                SELECT id, title, start_year,
                       similarity(title_norm, :norm) AS score
                FROM series
                WHERE title_norm % :norm
                ORDER BY score DESC
                LIMIT 5
            """), {"norm": norm})
            hits = [
                SeriesHit(UUID(str(r.id)), r.title, r.start_year, r.score)
                for r in fuzzy
                if r.score >= SIMILARITY_THRESHOLD
            ]

        if len(hits) <= 1:
            return hits

        # ── Desambiguación por año (±1) ──────────────────────────────────────
        if year is not None:
            by_year = [
                h for h in hits
                if h.start_year is not None
                and abs(h.start_year - year) <= 1
            ]
            if by_year:
                hits = by_year
                if len(hits) == 1:
                    return hits

        # ── Desambiguación por volumen si el empate persiste ─────────────────
        # Útil cuando el ComicInfo trae <Volume>2</Volume>:
        # Batman (1940) Vol.1 vs Batman (2011) Vol.2 pueden tener años distintos,
        # pero si el año no resuelve (ej. reedición), el volumen puede hacerlo.
        if volume is not None and len(hits) > 1:
            # El volumen en series se infiere del start_year o del título.
            # Estrategia conservadora: no filtramos si no tenemos certeza.
            # Solo aplicamos si hay series con vol explícito en metadata JSONB.
            by_vol = [
                h for h in hits
                if _volume_matches(h, volume)
            ]
            if by_vol:
                return by_vol

        return hits

    async def find_alias(self, raw_title: str) -> SeriesHit | None:
        """B13: alias local aprendido de una asignación manual anterior
        en Pendientes (ver ReviewService.assign_to_series). Se consulta
        ANTES del fuzzy de la capa 2 — si el coleccionista ya corrigió
        este patrón una vez, no vuelve a preguntarse."""
        pattern = normalize_title(raw_title)
        if not pattern:
            return None
        row = (await self.db.execute(sa.text("""
            SELECT s.id, s.title, s.start_year
            FROM local_aliases la
            JOIN series s ON s.id = la.series_id
            WHERE la.pattern_norm = :pattern
        """), {"pattern": pattern})).first()
        if not row:
            return None
        return SeriesHit(UUID(str(row.id)), row.title, row.start_year, 1.0)

    async def find_issue(self, series_id: UUID, number: str,
                          formato_esperado: str | None = None) -> tuple[UUID | None, bool]:
        """Issue de esa serie con ese número, y si hubo conflicto de ediciones.

        issue_number es VARCHAR por los '1.5' y 'Annual 3': match textual
        exacto tras recortar ceros a la izquierda ('007' ~ '7').

        B15: un mismo número puede estar ocupado por ediciones distintas (la
        grapa #12 y el Omnigold 12). Antes se cogía la primera fila a ciegas
        (LIMIT 1); ahora se exige que el format COINCIDA con el esperado. Si
        hay varias candidatas, o ninguna coincide con el formato esperado, se
        devuelve (None, True) y el archivo va a revisión: es preferible
        preguntar a enlazarlo a la edición equivocada.

        Devuelve (issue_id, conflicto):
          (id, False)   — exactamente una candidata con el formato esperado.
          (None, False) — no hay ningún issue registrado para ese número
                          (hueco del enricher, comportamiento de siempre).
          (None, True)  — hay issues pero el formato no permite decidir.
        """
        # Normalización SIMÉTRICA a propósito: antes se recortaban ceros solo
        # en la columna y el parámetro llegaba ya recortado, así que el #0
        # nunca encontraba su fila — ltrim('0','0') es la cadena VACÍA y la
        # comparación quedaba '' = '0'. Verificado contra Postgres real.
        # `issue_number <> ''` cierra el caso degenerado de una fila sin
        # número: si no, '' casaría con cualquier búsqueda de '0'.
        res = await self.db.execute(sa.text("""
            SELECT id, format FROM issues
            WHERE series_id = :sid
              AND issue_number <> ''
              AND ltrim(issue_number, '0') = ltrim(:num, '0')
        """), {"sid": str(series_id), "num": number})
        filas = res.fetchall()
        if not filas:
            return None, False
        if formato_esperado is None:
            # Sin marcador NO hay evidencia del formato: solo se enlaza si hay
            # una única candidata Y además es una grapa estándar. Una única
            # recopilación/tomo tampoco se enlaza — «solo hay una fila» no
            # demuestra que este archivo sin marcador sea ese tomo; podría ser
            # la grapa #12, todavía sin catalogar. Es el mismo emparejamiento
            # que rechaza el camino manual, así que los dos caminos coinciden.
            if len(filas) == 1 and filas[0].format == FORMATO_GRAPA:
                return UUID(str(filas[0].id)), False
            return None, True
        coinciden = [f for f in filas if f.format == formato_esperado]
        if len(coinciden) == 1:
            return UUID(str(coinciden[0].id)), False
        return None, True

    # ── Decisión ─────────────────────────────────────────────────────────────

    async def decide(self, triage, extractor=None,
                     formato_esperado: str | None = None) -> MatchResult:
        """Punto de entrada.

        `extractor` es la inyección de naming.py:
        callable(filename) -> tuple[title, number, year] | None.
        Es un parámetro para que los tests lo sustituyan por fixtures.
        """
        title = number = year = None
        volume = None

        if triage.strong_candidate:     # Capa 0: validar, no adivinar
            ci = triage.comic_info
            title, number = ci.series, ci.number
            year = ci.year
            volume = ci.volume          # Segundo discriminador si hay empate
        elif extractor is not None:     # Capa 1: regex del filename
            extracted = extractor(triage.path.name)
            if extracted:
                title, number, year = extracted

        if not title or not number:
            return MatchResult(
                MatchStatus.UNSORTED,
                notes=["sin título/número tras capas 0-1"],
            )

        # B13: alias local (corrección manual previa en Pendientes) manda
        # sobre el fuzzy — se salta capa 2 por completo si hay uno.
        alias_hit = await self.find_alias(title)
        if alias_hit:
            return await self._resolve(alias_hit, number, [alias_hit],
                                        MatchStatus.DIRECT, ["alias local aprendido"],
                                        formato_esperado)

        hits = await self.find_series(title, year, volume)
        good = [h for h in hits if h.score >= FUZZY_THRESHOLD]

        if not good:
            return MatchResult(
                MatchStatus.UNSORTED,
                candidates=hits,
                notes=["ningún candidato supera umbral"],
            )

        top = good[0].score
        tied = [h for h in good if abs(h.score - top) < 0.05]
        if len(tied) > 1:
            return MatchResult(
                MatchStatus.UNSORTED,
                candidates=tied,
                notes=[f"empate ambiguo: {[h.title for h in tied]}"],
            )

        hit = good[0]
        status = MatchStatus.DIRECT if hit.score == 1.0 else MatchStatus.FUZZY
        return await self._resolve(hit, number, good, status, [], formato_esperado)

    async def _resolve(self, hit: SeriesHit, number: str, candidates: list[SeriesHit],
                        status: MatchStatus, extra_notes: list[str],
                        formato_esperado: str | None = None) -> MatchResult:
        """Cola común de decide(): buscar el issue exacto y componer el
        MatchResult final, compartida entre el camino normal (fuzzy) y el
        alias local (B13) — ambos terminan igual, solo cambia cómo se
        encontró la serie.

        B15: si el número está compartido entre ediciones y el formato no
        permite decidir, NO se enlaza ni se mueve: el archivo va a Pendientes."""
        issue_id, conflicto = await self.find_issue(hit.series_id, number, formato_esperado)
        if conflicto:
            return MatchResult(
                MatchStatus.UNSORTED,
                candidates=candidates,
                notes=[f"número '{number}' compartido entre ediciones en "
                       f"'{hit.title}': no se enlaza sin poder verificar el formato"],
            )
        notes = list(extra_notes)
        if not issue_id:
            notes.append(
                f"issue '{number}' no registrado en serie '{hit.title}': "
                "posible hueco del enricher, encolar consulta a metadata.py"
            )
        return MatchResult(status, hit.series_id, issue_id, hit.score, candidates, notes)


def _volume_matches(hit: SeriesHit, volume: int) -> bool:
    """Heurística conservadora de desambiguación por volumen.

    Por ahora solo comprueba si el volumen aparece explícito en el título
    (ej. "Batman Vol. 2"). Cuando el enricher almacene el volumen en
    series.metadata, esta función se refactoriza para leer ese campo.
    """
    title_lower = hit.title.lower()
    vol_patterns = [
        rf"\bvol\.?\s*{volume}\b",
        rf"\bvolume\s+{volume}\b",
        rf"\btomo\s+{volume}\b",
    ]
    return any(re.search(p, title_lower) for p in vol_patterns)
