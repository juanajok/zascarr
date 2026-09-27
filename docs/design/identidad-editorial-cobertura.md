# Identidad editorial: relación tomo → grapas cubiertas (especificación breve)

**Estado:** especificación, pendiente de implementación (migración y código van aparte)
**Origen:** cierre de la cadena A4 → A6 → B15 → huecos fiables (2026-09-27). La vista de
huecos de grapas ya es fiable y acotada (PR #13); esto es el rediseño de catálogo que la
precede. **No es C6.**

## 1. El problema en una frase

Una recopilación (tomo, ómnibus, integral) contiene **varias** grapas originales. Hoy el
catálogo la guarda como un `Issue` con otro `format` y un único `issue_number`; nada dice
«este tomo cubre las grapas 7..12». Hasta que eso exista, **un tomo no rellena huecos de
grapa por inferencia** — regla que ya se aplica en la vista de huecos.

## 2. Realidad del esquema (no diseñar desde una idea equivocada)

- `Issue` tiene `UNIQUE(series_id, issue_number, volume)`, **sin `format`**.
- Con `volume=1` (el default), la grapa #12 y el ómnibus #12 de la misma serie **chocan**.
- Con volúmenes **distintos** sí coexisten.
- `volume` admite `NULL`; en PostgreSQL los `NULL` son distintos entre sí en una restricción
  única ordinaria, así que puede haber duplicados ambiguos. No se parte de «nunca coexisten».
- `File.covered_issue_ids` (array de UUID) existe, pero importación y adopción lo inicializan
  vacío. Es una pista **ligada a una copia física**, sin procedencia ni confirmación, y sin
  las garantías relacionales de una tabla. No es la verdad editorial por sí solo.

## 3. Tres ejemplos que el diseño debe resolver

### A. Tomo que cubre grapas de una misma serie

`Berserk Deluxe 1` (tomo) contiene las grapas `1..3`. El catálogo debe poder afirmar
«el tomo #1 cubre las grapas #1, #2, #3» con un **origen** (explícito o inferido) y, si la
fuente no es fiable, una **confirmación manual**.

### B. Dos ediciones del mismo #12

Grapa #12 (`SINGLE_ISSUE`, volumen 1) y ómnibus #12 (`OMNIBUS`, volumen 2) de la misma
serie. Deben **coexistir sin colisión**, y el ómnibus debe declarar qué grapas cubre
(p. ej. las grapas #7..#12) sin confundirse con la grapa #12 que es una unidad distinta.

### C. Pack que cruza series

Un archivo (pack/crossover) con material de dos series distintas. `covered_issue_ids` ya
insinúa esto, pero sin serie de referencia por grapa cubierta ni procedencia. El diseño
debe decidir si una cobertura puede cruzar series o si se modela como una entrada por serie.

## 4. Reglas de procedencia y confirmación

- Toda cobertura tiene un **origen**: `comic_vine`, `anilist`, `tebeosfera`,
  `comicinfo_xml` o `manual`.
- Si el origen no es fiable, la cobertura queda **no confirmada**: se puede mostrar, pero
  **no** cuenta como «lo tengo» ni rellena huecos.
- La **confirmación humana** es lo que la promueve a fiabilidad plena.

## 5. Qué NO decide este documento

- No define migración ni código.
- No cambia `GET /missing` ni empieza C6.
- No decide aún el destino de `covered_issue_ids`: abandonarlo, mantenerlo para
  packs/archivos físicos, o migrarlo hacia la tabla de cobertura.
