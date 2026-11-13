# Especificación — Etiquetas (sistema de tags, MVP manual) — v0.3

> **Estado:** **v0.3 (2026-11-07)**: decisiones D-1…D-7 ratificadas por el PO, BL-ETQ1 partida en
> 1a/1b, namespace único `etiqueta` y migración corregida a **0022** (la 0021 la ocupa BL-R9).
> Biblioteca reconciliada con BL-IT01 (#283) y re-verificada tras #284/#286. **Leer primero §0**,
> que manda sobre el resto. **No autoriza implementar** por sí misma: cada historia pasa a «Lista
> para desarrollar» con su DoR; no cambia `src/`, `tests/` ni `alembic/`.
> **Base contrastada:** `origin/main` = `61c85d6` (2026-11-07). **Fecha:** 2026-11-07.
> **Caducidad:** 2027-01-03, la de la ficha que lo sustenta; antes si cambia el repo, Kavita/Komga
> o las decisiones del PO.
> **Insumos (leídos y citados, no repetidos):** [`benchmark-etiquetas.md`](benchmark-etiquetas.md)
> (§5, §7, §8, §9), [`evaluacion-propuesta-etiquetas.md`](evaluacion-propuesta-etiquetas.md) (§2, §4,
> §6, §8, §11), [`ui-etiquetas.md`](ui-etiquetas.md) (contratos HTMX, textos, accesibilidad),
> [`propuesta-externa-etiquetas.md`](propuesta-externa-etiquetas.md), procedimiento en
> [`benchmark-referencias.md`](benchmark-referencias.md) y maqueta `maqueta-etiquetas.html`.
> **Notación:** EARS con palabras clave en español (Ubicuo, CUANDO, SI/ENTONCES, MIENTRAS, DONDE);
> criterios en Given/When/Then; identificadores en inglés.


## 0. Enmienda v0.2 (2026-11-06) — decisiones del PO, partición y reconciliación con BL-IT01

**Esta sección manda sobre el resto del documento** donde lo contradiga. El cuerpo se conserva como historial de la v0.1.

### 0.1 Decisiones del PO (ratificadas el 2026-11-06)

| # | Decisión |
|---|---|
| **D-1** | **Un solo espacio de nombres visible: `etiqueta`.** La columna `namespace` y su `CHECK` se crean (con `('etiqueta')` como único valor de 0022) para poder ampliarlos más adelante con otra migración. La persona **no escribe prefijos**: el token es el nombre (`noir`, `space-opera`) y `-noir` excluye. Desaparecen la ambigüedad entre espacios (FR-09, segunda mitad de AC-09) y los ejemplos `tema:`/`motivo:`, que se leen como el nombre sin prefijo. |
| **D-2** | **Español, escrito a mano** por el coleccionista en el MVP. El idioma de lo que traigan las fuentes se decide en BL-ETQ4. |
| **D-3** | **Público/edad fuera de etiquetas**: un campo estructurado, en otra historia si hace falta. Nunca un espacio de nombres de texto. |
| **D-4** | **Exportar a ComicInfo/Kavita, fuera del MVP** (BL-ETQ6, NO APTO hasta ampliar el contrato B6). |
| **D-5** | **Alias e implicaciones solo manuales y confirmados** (BL-ETQ5); nunca automáticos desde fuentes. |
| **D-6** | **Sí se crean etiquetas desde la ficha**, como acción explícita («Crear "noir"»), con `source='manual'`. El buscador de Biblioteca **nunca** crea. AC-19 deja de ser condicional y forma parte de BL-ETQ1a. |
| **D-7** | **Orden: 1a → 1b, y medir antes de seguir** (etiquetas usadas de verdad y CBZ con `<Tags>`). Después, ETQ2 si hay datos que leer y ETQ3 en paralelo; ETQ4–ETQ6 solo si el uso lo pide. |

### 0.2 Partición de BL-ETQ1 (aprobada por el PO el 2026-11-06)

| Historia | Tarjeta | Qué entra | Criterios |
|---|---|---|---|
| **BL-ETQ1a — Etiquetar una serie** | #403 | Migración **0022** (`down_revision="0021"`), `services/etiquetas.py`, ficha (añadir, quitar, crear) y sugerencias de la ficha | AC-01…AC-05, AC-07 (ficha), AC-10, AC-12…AC-16, AC-19 |
| **BL-ETQ1b — Filtrar Biblioteca por etiquetas** | #431 | Filtro AND/exclusión, chips, sugerencias, facetas y recuento en Biblioteca, sobre BL-IT01 | AC-06, AC-07 (Biblioteca), AC-08, AC-09 (primera mitad), AC-11, AC-17, AC-18, NFR-07 |

AC-20 (sin daño colateral) aplica a las dos. Una PR por historia.

### 0.3 Reconciliación con BL-IT01 (#283, `323dbc2`, 2026-11-05)

La v0.1 se escribió sobre la Biblioteca anterior. BL-IT01 ya trae el estado de la vista en la URL (`Filtros` / `_leer_filtros`), un chip por filtro activo con su retirada (`FiltroActivo`, `#filtros-activos`, `quitar` de valores cerrados), «Limpiar todos», el recuento en `#resumen-biblioteca`, el intercambio en **`#rejilla`** y el empuje de la URL de la **página** desde el servidor (`HX-Push-Url`). BL-ETQ1b **se construye sobre ese contrato**:

- `etiquetas` es **un campo más de `Filtros`** y viaja en `_qs`, como `q` o `tradition`; la paginación lo conserva sin código nuevo.
- Cada etiqueta incluida o excluida es **un `FiltroActivo`** en la lista `#filtros-activos` existente. La exclusión lleva el texto «Sin», borde discontinuo e icono `minus` (FR-18). Su `url_quitar` es la expresión **sin ese token**, construida en el servidor; `quitar` admite el valor cerrado `etiquetas` para el foco.
- El destino es **`#rejilla`** (no se crea `#resultados-biblioteca`), el recuento va en `#resumen-biblioteca` y la URL la empuja el servidor (no `hx-push-url="true"` en el cliente). **R-2 desaparece.**
- Un token desconocido entra en los **`avisos`** que BL-IT01 ya pinta para los valores descartados (AC-09).
- Las facetas se pintan dentro del fragmento de `#rejilla`, después de los chips.
- **R-7** (`autofocus` en el intercambio): BL-IT01 ya lo usa en `#filtros-activos`; se reutiliza su prueba.
- No se duplica ningún id del DOM (`#filtros-activos`, `#rejilla`, `#resumen-biblioteca`, `#recuento-biblioteca`).

La ficha de serie (BL-ETQ1a) no cambia por esto: `#etiquetas-serie` es nuevo y no choca con nada.

### 0.4 Entorno de pruebas

`TEST_DATABASE_URL` con una base de nombre «test» y `pytest --basetemp` en el mismo dispositivo que `/` **y en un sistema de ficheros POSIX**: en un disco NTFS fallan pruebas ajenas por nombres con `<` o saltos de línea y fechas anteriores a 1970.

### 0.5 Corrección v0.3 (2026-11-07) — migración 0022 y namespace único

Esta revisión **no cambia ninguna decisión de producto**; corrige la documentación para que se pueda implementar:

1. **La migración de etiquetas es la 0022, con `down_revision="0021"`.** BL-R9 (#457, PR #459) ocupó la 0021 con `files.file_mtime_ns` (`20261106_0021_rescan_file_mtime.py`). Todas las referencias normativas a «0021» en esta especificación, en `ui-etiquetas.md`, en el backlog y en las tarjetas se leen como **0022**; las menciones históricas del benchmark/evaluación se conservan con su nota de vigencia.
2. **Un solo espacio de nombres visible, `etiqueta` (D-1).** El cuerpo histórico de la v0.1 conserva ejemplos con `tema:`/`motivo:`; a partir de §0 se leen **sin prefijo** (`noir`, `escuela`). El `CHECK` de 0022 solo admite `('etiqueta')`; ampliarlo exige otra migración.
3. **La partición 1a/1b es la de §0.2.** La 1a (#403) no toca Biblioteca; la 1b (#431) no empieza hasta que la 1a esté fusionada. El filtro de Biblioteca se construye sobre `#rejilla`, nunca sobre un `#resultados-biblioteca` nuevo.
4. **D-6 está ratificada:** crear etiquetas desde la ficha forma parte de la 1a y AC-19 deja de ser condicional.

## 1. Problema y valor para El Coleccionista

El coleccionista busca «noir», «escuela», «Batman» o «space opera» y solo puede buscar por título:
la biblioteca filtra por tradición, editorial, personaje y saga (cuatro campos cerrados) y no hay
descriptores libres. La ficha ya pinta `Series.genres` pero el enricher no lo puebla; `tags`/
`issue_tags` existen desde 0001 y están dormidas (ningún servicio, router, test ni plantilla las
usa); `core/importer_triage` ignora `<Tags>` y el escritor de ComicInfo gestiona siete campos.

**Valor de esta entrega:** que El Coleccionista pueda **describir sus tebeos con sus palabras** y
**reencontrarlos** por lo que tratan, sin aprender sintaxis, sin terminal, sin JSON y sin que nada
se mueva del disco. Etiqueta en la ficha de una serie en un clic; en Biblioteca ve las series que
tienen todas las etiquetas que elige y puede excluir las que no quiere. El trabajo manual manda:
lo que él escribe no lo pisa ninguna fuente. Es la primera capa de una taxonomía que crecerá por
fases (ComicInfo, fuentes externas, alias/implicaciones) solo si el uso real lo pide.

**Criterio de éxito:** (O-1) una serie se etiqueta y desetiqueta desde la ficha; (O-2) el filtro
AND/exclusión devuelve el recuento que anuncia; (O-3) `Noir`, `noir` y `nóir` son la misma etiqueta;
(O-4) 0 fallos de fragmento en los estados vacío/error probados; (O-5) 0022 se aplica y revierte en BD
de pruebas.

## 2. Decisiones cerradas (benchmark/evaluación) — no se reabren

| # | Decisión | Evidencia / código vigente |
|---|---|---|
| 1 | **Se reutilizan `tags` e `issue_tags`** (UUID, desde 0001) y se añade `series_tags`; **no** se crean `tag`/`serie_tag`. Migración **0022** (`down_revision="0021"`), one-shot con downgrade. | `models/__init__.py:497` (`Tag`), `:216` (`issue_tags`), `alembic/versions/20260301_0001_initial_schema.py:159`; head `20261106_0021_*` |
| 2 | **MVP a nivel de SERIE.** `issue_tags` queda **dormida** para una fase posterior: no se agregan etiquetas de número a la serie en silencio (evita «filtro fantasma»). | `SeriesService.list_series` filtra series (`services/series.py:39`); benchmark §8.2 |
| 3 | **Un solo espacio de nombres visible en el MVP: `etiqueta`** (D-1); la columna `namespace` queda preparada para ampliarse con otra migración. La persona no escribe prefijos. **No se duplican** en tags: `genero` (poblar `Series.genres`), `personaje` (`Issue.characters`), `formato` (`IssueFormat`/`FileFormat`), `universo` (`Universe`); `publico`/`AgeRating` es decisión aparte, atributo estructurado. | `models:181` (`series_genres`), `:198` (`issue_characters`), `:279` (`Genre`), `:405`, `:461`; evaluación §4.1 |
| 4 | **`source` reutiliza `MetadataSource`** (`comic_vine`, `gcd`, `anilist`, `tebeosfera`, `comicinfo_xml`, `manual`); `regla` solo si el PO lo aprueba (hoy no existe y no entra en 0022). **`weight` es relevancia (0–100, nullable)**, no confianza; solo el `rank` real de AniList la tendrá. **`manual` gana**: el escritor automático no pisa filas manuales. | `models:170` (`MetadataSource`); `enricher.py:185,359` (excluye `manual` y respeta `locked_fields`); evaluación §4.4 |
| 5 | **ComicInfo:** fase 1b **solo lectura** de `<Tags>`/`<Genre>` con `source='comicinfo_xml'`, topes de volumen y **sin escribir**. La escritura/export a ComicInfo/Kavita es fase 4 y **NO APTO** hasta extender el contrato B6 (7 campos en `CAMPOS_GESTIONADOS`). | `core/comicinfo_write.py:35`, `core/importer_triage.py:151`, benchmark §2/§7, evaluación §11 |
| 6 | **Alias (siblings, n→1) e implicaciones (parents, n→n) son mecanismos distintos**; fase 4, manuales, sin ciclos, alias único normalizado. | evaluación §4.2–4.3; benchmark §5 |
| 7 | **Normalización propia `f_tag_norm`** (lower + `f_unaccent` + puntuación→espacio + colapsar) + columna generada `name_norm` + GIN trigram + test de paridad Python/SQL. **`f_title_norm` no sirve** (quita artículos). `pg_trgm` (0001) y `unaccent`/`f_unaccent` (0006) ya están. | `alembic/versions/20260921_0006_*:92-117`; `tests/test_title_norm.py` |
| 8 | **UI:** se sigue [`ui-etiquetas.md`](ui-etiquetas.md); fragmentos HTML bajo `/ui/...` (nunca `/api` devolviendo HTML); **sin JS propio nuevo**; chip de excluir explícito, **sin `alt`-clic**. | ADR-0001/0005; `web/library.py:105`; `ui-migracion.md` §2.5 (htmx 4 intercambia todo estado ≠ 204/304) |

**Contradicciones del anexo resueltas contra el repo:** ids `int`→UUID; migración «0010»→0022;
`Tag.name` único global→`UNIQUE(namespace, name_norm)`; `serie_tag` nueva→`series_tags` +
`issue_tags` dormida; `source` por campo→columna por asignación; `f_title_norm`→`f_tag_norm`;
«integración Kavita»→solo `scripts/kavita.sh` (B20 sin implementar); `AgeRating` inexistente→no es
un namespace.

## 3. Alcance y NO-goals

**En alcance (BL-ETQ1a, #403, una PR):** migración **0022** y modelo; `services/etiquetas.py`
(normalización, token, alta/baja y sugerencias de la ficha); rutas/fragmentos y plantillas de la
ficha en [`ui-etiquetas.md`](ui-etiquetas.md) §6; textos exactos §8.2; CSS del Anexo A e iconos
`x`/`minus`/`plus`/`tag`; pruebas FakeSession + PostgreSQL real; `SECURITY.md` y
`docs/BACKLOG.md` actualizados en el mismo PR. **BL-ETQ1b (#431)** añade después el filtro por
etiqueta en `SeriesService.list_series`, las facetas y el fragmento compuesto de Biblioteca sobre
el contrato de §0.3; no empieza hasta que la 1a esté fusionada.

**Fuera de alcance explícito (NO-goals):**

1. **Etiquetar números**: `issue_tags` no se escribe ni se agrega a la serie; «etiquetas por número» es fase posterior.
2. **Namespaces `genero`, `personaje`, `universo`, `formato`, `publico`**: lo primero es poblar lo estructurado (BL-ETQ3) o decisión aparte; nunca dos fuentes de verdad. Tampoco se crean `tema` ni `motivo`: el único espacio visible del MVP es `etiqueta` (D-1).
3. **Leer o escribir ComicInfo** (BL-ETQ2 lectura; BL-ETQ6 escritura/export).
4. **Enricher y clientes de fuentes** (BL-ETQ3/BL-ETQ4): ni `field_list`, ni mapeos, ni caché negativa nueva.
5. **Alias, implicaciones, reglas y smart filters** (BL-ETQ5): no hay tabla, ni UI, ni resolución por sinónimos.
6. **Renombrar/fusionar etiquetas, etiquetado masivo, importación CSV, OR/comodines/regex**.
7. **Export a ComicInfo/Kavita** (BL-ETQ6/B20): escribir `<Tags>` exige extender B6 y sus pruebas.
8. **Infraestructura nueva:** sin dependencias, sin Redis, sin extensiones nuevas (`pg_trgm`/`unaccent` ya están), sin vistas materializadas, sin cambios de middleware/CORS, sin ADR nuevo (no cambia arquitectura; el contrato vive en esta spec).

**Fases posteriores:** las de [`evaluacion-propuesta-etiquetas.md`](evaluacion-propuesta-etiquetas.md)
§6 (1b ComicInfo lectura → 2 identidad estructurada → 3 enriquecimiento → 4 taxonomía/export).

## 4. User story EARS principal

**US-ETQ (EARS, español llano):**

> **CUANDO** estoy en Biblioteca y quiero encontrar tebeos por lo que tratan, escribo una palabra
> en «Buscar por etiqueta»; el sistema me sugiere etiquetas de mi biblioteca y, al elegir una, veo
> solo las series que la tienen. **CUANDO** añado otra etiqueta, el sistema exige que la serie
> tenga **todas**; **CUANDO** marco una como excluida, el sistema quita del resultado las series
> que la tengan. **SI** escribo una etiqueta que no existe, **ENTONCES** la pantalla no se rompe:
> me lo dice y conserva los filtros que ya tenía. **MIENTRAS** una etiqueta la he puesto yo, la
> aplicación no la cambia ni la quita por su cuenta. En la ficha de una serie puedo añadir y quitar
> etiquetas al momento, sin diálogos y sin que se toque ningún archivo.

**Valor:** reencontrar por lo que trata, con las palabras del coleccionista, en la pantalla donde
ya busca; sin saber Postgres, HTMX ni qué es un namespace. Las etiquetas complementan los filtros
cerrados (tradición, editorial, personaje, saga), no los sustituyen.

## 5. Requisitos funcionales (EARS)

| ID | Patrón | Requisito | AC |
|---|---|---|---|
| FR-01 | Ubicuo | El sistema extenderá `tags` con `namespace`, `name_norm` generada y unicidad `(namespace, name_norm)`, y añadirá `series_tags` (UUID, `source`, `weight`, `oculta`); `issue_tags` no se modifica. Migración 0022 one-shot con downgrade. | AC-01 |
| FR-02 | Ubicuo | El sistema normalizará todo nombre de etiqueta con `f_tag_norm` y su espejo Python `normalize_tag` (NFKC + lower + sin acentos + puntuación→espacio + colapsar); `f_tag_norm` conservará artículos (`The Walking Dead` ≠ `walking dead`). | AC-02 |
| FR-03 | Ubicuo | El sistema impedirá dos etiquetas que solo difieran en mayúsculas/tildes dentro del espacio visible; mientras el MVP tenga un solo espacio (`etiqueta`), no habrá colisión entre espacios. | AC-03 |
| FR-04 | Por evento | CUANDO el coleccionista añade una etiqueta desde la ficha, el sistema validará el token, escribirá una fila `source='manual'` con `weight=NULL`, y devolverá el fragmento `#etiquetas-serie` con un aviso de éxito; repetirla no duplica ni da error. | AC-04 |
| FR-05 | Por evento | CUANDO quita una etiqueta manual, el sistema borrará la asignación; si la fila es de una fuente (`source<>'manual'`), la marcará `oculta=true` en vez de borrarla (contrato para BL-ETQ2/4). | AC-05 |
| FR-06 | Ubicuo | El sistema filtrará la biblioteca por una expresión `etiquetas`: todos los tokens positivos en AND y los `-` como exclusión, con `EXISTS`/`NOT EXISTS`; paginará en servidor y conservará `etiquetas` en la URL de paginación. El token es el nombre normalizado, sin prefijos. | AC-06 |
| FR-07 | Ubicuo | El sistema ofrecerá sugerencias a partir del texto tecleado (`etiqueta` en la ficha; último token de `etiquetas` en Biblioteca; 2–64 caracteres), tolerantes a mayúsculas y tildes, ordenadas por prefijo/similitud y uso, **máximo 8**, sin repetir las ya aplicadas, cada una con token canónico y número de series y con URLs construidas en el servidor. | AC-07 |
| FR-08 | Estado | Mientras hay filtros de etiqueta activos, el sistema mostrará chips (incluidos los de exclusión), **un solo grupo de facetas («Etiquetas») con recuento** y **una** frase de recuento en región viva. Las facetas contarán con los tokens positivos aplicados; las exclusiones no descuentan. | AC-08 |
| FR-09 | No deseado | SI un token no existe, ENTONCES el sistema devolverá 200 con un aviso ámbar dentro del fragmento, conservará los filtros previos y no aplicará el token. | AC-09 |
| FR-10 | Ubicuo | El sistema aplicará topes: expresión ≤100 caracteres y ≤12 tokens; nombre 1–64 caracteres sin comas, saltos ni controles; texto de sugerencia 2–64; 8 sugerencias; 8 facetas por grupo. Al pasarse de tokens aplicará los 12 primeros y lo dirá. | AC-10 |
| FR-11 | Estado | El sistema pintará los cuatro estados vacíos con los textos exactos de `ui-etiquetas.md` §5/F5 (biblioteca sin etiquetas, filtro sin resultados, serie sin etiquetas, sugerencias sin coincidencias), sin culpar al usuario. | AC-11 |
| FR-12 | No deseado | SI falla el servidor o la BD en una ruta de fragmento, ENTONCES el sistema devolverá 200 con `ui.aviso("warn")` y el estado actual de chips; nunca JSON de FastAPI dentro de la rejilla. | AC-12 |
| FR-13 | Ubicuo | El sistema no escribirá texto de etiqueta ni la expresión de filtro en `structlog` ni en mensajes de error, y responderá `Cache-Control: no-store` en fragmentos con estado (sugerencias, resultados, ficha). | AC-13 |
| FR-14 | Ubicuo | El sistema tratará todo nombre/alias como dato no confiable: autoescape de Jinja, nunca en `class`/`id`/`style`/`hx-*`, `safe`/`Markup` de Jinja prohibidos, URLs con `urlencode` y clase de namespace derivada de un mapa de enum (desconocido = error explícito). | AC-14 |
| FR-15 | Ubicuo | Los endpoints mutables usarán `Form(...)` explícito; el servidor fijará `source='manual'` y `weight`; prohibido `Model(**data)`/`setattr`; namespace validado contra enum/CHECK y campos extra rechazados. | AC-15 |
| FR-16 | Ubicuo | Una fila `source='manual'` no se modificará ni borrará por un escritor automático (contrato probado con función pura en esta entrega; la consumen BL-ETQ2/4). | AC-16 |
| FR-17 | Ubicuo | El sistema mantendrá el coste acotado: ≤3 consultas por request de resultados, ≤1 de sugerencias, ≤2 de ficha; facetas en una sola consulta con índice por `tag_id`; sin N+1 en ficha/listado. | AC-17 |
| FR-18 | Ubicuo | El sistema respetará la accesibilidad de `ui-etiquetas.md` §9: región viva, foco tras quitar, ≥14 px, exclusión no solo por color (texto «Sin», borde discontinuo, icono `minus`), nombres accesibles. | AC-18 |
| FR-19 | Ubicuo | El sistema permitirá **crear** una etiqueta desde la ficha como acción explícita y confirmada (`source='manual'`), con D-6 ratificada; nunca desde el buscador principal ni como efecto colateral de buscar. | AC-19 |

## 6. Requisitos no funcionales

| ID | NFR | Umbral | Medición |
|---|---|---|---|
| NFR-01 | Coste de consultas | resultados ≤3 SELECT; sugerencias 1; ficha ≤2; POST ≤3 | contador de sentencias de SQLAlchemy en pruebas con `FakeSession` y con Postgres real |
| NFR-02 | Sin N+1 | el número de consultas no depende de series ni de etiquetas pintadas | prueba con 24 series / 30 etiquetas |
| NFR-03 | Payload de fragmentos | sugerencias ≤6 KB; panel de facetas ≤8 KB | longitud de `response.text` en prueba |
| NFR-04 | Cero red externa | 0 peticiones HTTP salientes en rutas de etiquetas | doble de clientes de fuente que falla si se invoca |
| NFR-05 | Cero dependencias/extensiones nuevas | `pyproject.toml` sin cambios; `CREATE EXTENSION` ausente de 0022 | revisión del diff + prueba de migración |
| NFR-06 | Cero JS propio nuevo | 0 `<script>`, `onclick`, `onerror` en plantillas nuevas/ampliadas | `grep` en el PR |
| NFR-07 | Latencia en Pi | p95 ≤ 250 ms para `/ui/biblioteca/resultados` con 2.000 series / 20.000 números / 5.000 asignaciones | **NOT RUN** hoy: guion en la Pi antes de fusionar; si no se cumple, plan B «Ver más sin recuento exacto» (no caché nueva) |
| NFR-08 | Texto y contraste | texto informativo ≥14 px; cualquier clase nueva entra en `test_web_css_contraste` | pruebas existentes de CSS |
| NFR-09 | Migración | 0022 es DDL (sin reescritura de datos); upgrade y downgrade deterministas en BD efímera | `tests/_pg.py::bd_efimera` + `alembic` |

## 7. Contratos y datos de la primera entrega

### 7.1 Modelo (migración 0022, `down_revision="0021"`)

- **`tags`**: `namespace VARCHAR(16)` se añade en tres pasos — **nullable → backfill `etiqueta` en las
  filas existentes → `SET NOT NULL`** — (no se asume tabla vacía, aunque por construcción lo esté) con
  `CHECK (namespace IN ('etiqueta'))` (D-1: único valor en 0022; ampliarlo exige otra migración); se
  añade `name_norm TEXT GENERATED ALWAYS AS (f_tag_norm(name)) STORED`; se **elimina** el UNIQUE global
  de `name` y se crea `UNIQUE (namespace, name_norm)`; `CHECK (char_length(name) BETWEEN 1 AND 64 AND
  name_norm <> '')`; índice `GIN (name_norm gin_trgm_ops)` para sugerencias. `color` se conserva **sin
  uso en el MVP** (el color del chip no informa de nada; el nombre va escrito).
- **`series_tags`**: `series_id UUID FK series ON DELETE CASCADE`, `tag_id UUID FK tags ON DELETE
  CASCADE`, `source VARCHAR(20) NOT NULL DEFAULT 'manual'` con `CHECK (source IN ('comic_vine','gcd',
  'anilist','tebeosfera','comicinfo_xml','manual'))`, `weight SMALLINT NULL CHECK (0–100)`, `oculta
  BOOLEAN NOT NULL DEFAULT false`, `created_at`/`updated_at`; `PRIMARY KEY (series_id, tag_id)`; índice
  parcial `(tag_id, series_id) WHERE oculta = false` para facetas y filtros. `oculta` lo usan
  BL-ETQ2/4; en BL-ETQ1a solo lo escribe FR-05.
- **Función `f_tag_norm(text) RETURNS text IMMUTABLE PARALLEL SAFE STRICT`** = `btrim(regexp_replace(
  regexp_replace(lower(f_unaccent($1)), '[^[:alnum:] ]', ' ', 'g'), '\s+', ' ', 'g'))`. **No** quita
  artículos ni colapsa puntos entre letras. Espejo Python `services/etiquetas.py::normalize_tag`
  (NFKC → NFKD sin marcas combinantes → lower → no-alfanumérico→espacio → colapsar).
- **Relaciones**: `Series.tags` (secundaria `series_tags`) en el modelo, y `Tag.series`; `Issue.tags`
  se queda como está. La relación **no** pinta la ficha: el servicio filtra `oculta = false`.
- **Downgrade coherente**: borra `series_tags` (las asignaciones se pierden: son lo nuevo) y
  deduplica `tags` por `name` conservando la fila con más referencias en `issue_tags` (empate: menor
  `id::text`) para poder recrear el UNIQUE global; elimina índices, checks, `name_norm`, `namespace`
  y `f_tag_norm`; **no** toca `issue_tags`, `series`, `genres` ni `pg_trgm`/`unaccent`. Documenta la
  pérdida en el docstring, como 0020.

### 7.2 Rutas (de `ui-etiquetas.md` §6, normativas)

| Método | Ruta | Parámetros | Responde |
|---|---|---|---|
| GET | `/ui/biblioteca` | `page, tradition, publisher_id, character_id, story_arc_id, q, etiquetas` | página con `#rejilla` |
| GET | `/ui/biblioteca/resultados` | los mismos | fragmento de `_rejilla_biblioteca.html` ampliado (chips + facetas + recuento + rejilla + paginación), destino `#rejilla` |
| GET | `/ui/biblioteca/etiquetas/sugerir` | `etiquetas` (expresión actual: el último token es el prefijo a completar, ≥2 caracteres; los anteriores son contexto y no se sugieren) | `_sugerencias_etiquetas.html` (≤8) |
| GET | `/ui/series/{series_id}` | — | ficha con `#etiquetas-serie` |
| GET | `/ui/series/{series_id}/etiquetas/sugerir` | `etiqueta` (texto tecleado, 2–64) | `_sugerencias_etiqueta_serie.html` |
| POST | `/ui/series/{series_id}/etiquetas` | `etiqueta` (Form, 1 token) | `_etiquetas_serie.html` |
| POST | `/ui/series/{series_id}/etiquetas/quitar` | `etiqueta` (Form, 1 token) | `_etiquetas_serie.html` |

Reglas: routers finos (lógica en `services/`); `Cache-Control: no-store`; 200 con aviso para errores
recuperables; 404 solo en ruta de página; serie inexistente en POST de fragmento → 200 con aviso (no
romper el swap); `href`/`action` reales (sin htmx funciona como navegación normal). **Nombres de
parámetro:** los de `ui-etiquetas.md` §6.2/§6.4, sin `q`: Biblioteca manda la expresión como
`etiquetas` (se completa su último token) y la ficha manda `etiqueta` con lo tecleado.
`/ui/biblioteca/resultados` pasa de devolver la rejilla a devolver el fragmento compuesto **en
BL-ETQ1b**, sobre el destino `#rejilla` y sin crear `#resultados-biblioteca`; el cambio de contrato y
sus pruebas van en la PR de 1b.

### 7.3 Expresión de filtro y token canónico

- Un parámetro `etiquetas` (URL-encoded). Tokens separados por **espacios**; `-` inicial = exclusión;
  sin prefijos, comillas, OR, paréntesis ni comodines. La URL canónica es la del formulario
  (`hx-push-url="true"`): Atrás/recargar reconstruyen la pantalla.
- **Token canónico** = `name_norm` con cada espacio sustituido por `-` (`noir`, `space-opera`,
  `-space-opera`). El campo acepta tildes/mayúsculas y guion interno; un nombre con espacios se
  escribe con `-` o se elige de las sugerencias (el espacio separa tokens).
- No hay prefijos de espacio: el token es siempre el nombre. Un token desconocido produce aviso y no
  se aplica. Un token está incluido **o** excluido, no ambas: el segundo cambia el signo.

### 7.4 Normalización, validación y topes

- Todo nombre/alias pasa por `normalize_tag` (NFKC) antes de escribir; la BD solo recibe texto
  normalizado por los servicios. Validación: 1–64 caracteres tras `strip`; rechaza comas, `\n`/`\r`,
  controles y `name_norm` vacío; conserva espacios internos. Duplicado normalizado → «Esa etiqueta ya
  existe: `space-opera`» (no un 500).
- Sugerencias: texto tecleado de menos de 2 caracteres (o último token vacío) → fragmento vacío sin
  consulta; más de 64 → se recorta; `LIMIT 8`; orden por prefijo, `similarity(name_norm, :q_norm)` y
  uso; nunca se sugieren etiquetas que ya estén en la expresión.
- Facetas: una consulta agregada (`ROW_NUMBER() OVER (ORDER BY count DESC, name_norm)` + `rn <= 8`),
  un solo grupo visible («Etiquetas») con 8 chips; ampliar a más espacios exigirá otra migración.
- Filtro: `EXISTS` por token positivo y `NOT EXISTS` por exclusión, nunca `JOIN`+`DISTINCT`; el
  recuento y la página salen del mismo WHERE.
- Lectura de ComicInfo (BL-ETQ2) tendrá sus topes: XML ≤1 MiB, `<Tags>`/`<Genre>` ≤32 KiB y ≤200
  tokens por campo (≤400 en total), 64 caracteres por token; lo que exceda se ignora con aviso en el
  informe de importación y **no** aborta el ciclo.

### 7.5 Precedencia y autoría

`source` dice de dónde salió cada asignación. Regla única: una fila `source='manual'` **no se
modifica ni se borra** por un escritor automático; el escritor añade la suya solo si no hay una
manual para esa (serie, etiqueta). Borrar desde la ficha una fila no manual la marca `oculta=true`
(no resucita en el siguiente ciclo); volver a añadirla a mano la hace `manual`, `oculta=false`,
`weight=NULL`. `weight` no decide precedencia ni ordena resultados en el MVP.

## 8. Criterios de aceptación (Given/When/Then)

### BL-ETQ1a y BL-ETQ1b (criterios de la primera entrega partida)

Reparto de criterios: **1a (#403)** = AC-01…AC-05, AC-07 (ficha), AC-10, AC-12…AC-16 y AC-19;
**1b (#431)** = AC-06, AC-07 (Biblioteca), AC-08, AC-09, AC-11, AC-17 y AC-18. AC-20 es el cierre
común: cada PR cumple la parte que le toca.

**AC-01 (FR-01, NFR-09) — migración y reversión**
Given una BD efímera sin migrar con **una fila legacy sembrada en `tags`** y su referencia en
`issue_tags` tras `upgrade 0021`, When se ejecuta `alembic upgrade head` (0022), Then existen
`namespace`, `name_norm`, el índice trigram, el unique `(namespace, name_norm)` y `series_tags` con
sus checks e índices; Then la fila legacy queda con `namespace='etiqueta'`, `name_norm` calculado y
su `issue_tags` intacta; Then `genres`/`series` conservan sus filas y no se crea ninguna extensión;
When se ejecuta `alembic downgrade 0021` y `upgrade head`, Then el downgrade restaura el schema de
0021 y no deja `f_tag_norm` ni `series_tags`. — *Prueba:* `tests/test_etiquetas_migracion_pg.py` con
`tests/_pg.py::bd_efimera` + `alembic` (skip sin `TEST_DATABASE_URL`).

**AC-02 (FR-02) — paridad Python/SQL**
Given un corpus de ≥60 nombres (tildes, `ñ`, `ü`, mayúsculas, guiones, apóstrofos, signos, espacios
múltiples, `The Walking Dead`, `S.H.I.E.L.D.`, `Nóir`), When se compara `normalize_tag(x)` con
`SELECT f_tag_norm($1)`, Then son idénticos para todo el corpus y `f_tag_norm('The Walking Dead')`
conserva el artículo. — *Prueba:* `tests/test_tag_norm_pg.py`, extrayendo el SQL del propio fichero de migración como
`tests/test_title_norm.py` (skip sin `TEST_DATABASE_URL`).

**AC-03 (FR-03) — unicidad normalizada**
Given `Noir`, When se intenta crear `noir` y `nóir`, Then la segunda y la tercera devuelven «ya
existe» y en BD hay una fila; Then el `CHECK` de 0022 solo admite `namespace='etiqueta'` (ampliarlo
exige otra migración). — *Prueba:* servicio con Postgres real + caso con `UNIQUE` directamente.

**AC-04 (FR-04) — añadir manual**
Given una serie y una etiqueta existente, When `POST /ui/series/{id}/etiquetas` con
`etiqueta=noir`, Then 200 con el fragmento `#etiquetas-serie`, chip visible, aviso
«Etiqueta añadida.», fila `source='manual'` y `weight IS NULL`; When se repite, Then 200 con «Esa
etiqueta ya estaba en la serie.» y una sola fila; Then la respuesta lleva `Cache-Control: no-store`. — *Prueba:* `tests/test_web_etiquetas.py` (FakeSession) + `tests/test_etiquetas_service_pg.py`.

**AC-05 (FR-05) — quitar y ocultar**
Given una fila manual, When `POST …/etiquetas/quitar`, Then se borra, el chip desaparece y aviso
«Etiqueta quitada.»; Given una fila `source='comicinfo_xml'` sembrada, When se quita, Then no se
borra: queda `oculta=true` y la ficha no la muestra. — *Prueba:* servicio con FakeSession/Postgres real; la rama automática se cubre aunque BL-ETQ1 no
produzca filas de fuente.

**AC-06 (FR-06) — AND, exclusión y paginación**
Given series con `noir`, `escuela` y ambas, When `GET /ui/biblioteca/resultados?
etiquetas=noir -escuela`, Then solo aparece la serie noir sin escuela; Then el recuento
dice «1 serie con noir. No se muestran las de escuela.»; When hay >24 resultados y se
pulsa la página 2, Then la URL conserva `etiquetas` y el filtro. — *Prueba:* `tests/test_web_library.py` actualizado (colas de FakeSession) + prueba de regresión de
`_rejilla_biblioteca.html::pagina_url`.

**AC-07 (FR-07) — autocompletado tolerante**
Given una etiqueta `Nóir` con 34 series, When `GET /ui/biblioteca/etiquetas/sugerir?etiquetas=noi`
y `?etiquetas=NOIR`, Then ambas incluyen `noir`, «34 series» y enlaces «Añadir»/«Excluir»
(URLs correctas y URL-encoded); Then la ficha responde igual con `?etiqueta=NOI`; Then un último token
de 1 carácter y una expresión vacía devuelven fragmento vacío sin consulta; Then las etiquetas ya
aplicadas no se sugieren; Then ≤8 filas y el fragmento no repite layout. — *Prueba:*
`tests/test_web_etiquetas.py` con FakeSession; orden y tolerancia con Postgres real en
`test_tag_norm_pg.py`.

**AC-08 (FR-08) — recuento y facetas**
Given 2 tokens positivos y 1 exclusión, When se piden resultados, Then las facetas cuentan solo con
los positivos (una serie excluida sigue sumando en la faceta), el recuento principal es exacto y la
región viva tiene una sola frase; Then se emite **una** consulta de facetas y ≤4 grupos × 8 chips. — *Prueba:* contador de sentencias; prueba de la semántica documentada.

**AC-09 (FR-09) — token desconocido**
Given `etiquetas=noirx`, When se piden resultados, Then 200, aviso ámbar «No conocemos la
etiqueta «noirx». Búscala en la lista de etiquetas.», chips previos intactos y sin 500. — *Prueba:* `tests/test_web_etiquetas.py`.

**AC-10 (FR-10) — límites**
Given 13 tokens, When se filtra, Then se aplican los 12 primeros y se avisa «Hay demasiadas
etiquetas a la vez. Quita alguna.»; Given una expresión de >100 caracteres, Then se recorta; Given
un nombre de 65 caracteres o con coma o salto de línea, Then el alta devuelve aviso de validación
(200) y no escribe; Given un texto de sugerencia de 65 caracteres (`etiqueta` o último token de `etiquetas`), Then se
recorta a 64. — *Prueba:* pruebas de servicio (límites puros) + `tests/test_web_etiquetas.py`.

**AC-11 (FR-11) — estados vacíos**
Given cada uno de los cuatro casos de `ui-etiquetas.md` §5/F5, When se renderiza, Then aparece el
título y texto exactos de esa tabla; Then el vacío de filtro ofrece «Quitar etiquetas» conservando
los demás filtros; Then ningún estado dice «0 resultados». — *Prueba:* aserciones de texto exacto sobre los fragmentos.

**AC-12 (FR-12) — error de servidor/BD**
Given un fallo simulado de sesión, When se piden resultados o se intenta guardar, Then 200 con
`ui.aviso("warn")` («No se pudieron cargar las etiquetas. Vuelve a intentarlo.» / «No se pudo
guardar. Vuelve a intentarlo.»), chips anteriores conservados y nunca un `{"detail":…}` en la
rejilla. — *Prueba:* FakeSession que lanza; aserción de que el cuerpo es HTML y no JSON.

**AC-13 (FR-13) — privacidad y caché (PASS esperado)**
Given una petición con `?etiquetas=secreto-mio` y otra con `?etiqueta=secreto`, When se emiten
las líneas de `uvicorn.access` con el filtro instalado en `main.py` y se captura `structlog`, Then la
línea de acceso **no contiene la query**: `SinQueryEnAcceso` (`utils/log_acceso.py`, #361) la
sustituye por `?…` y el filtro sigue instalado; Then el `structlog` de la app no contiene el texto de
la etiqueta ni la expresión; Then los fragmentos con estado llevan `Cache-Control: no-store`; Then
los errores al usuario no nombran tablas, columnas ni valores internos. — *Prueba:* `caplog` sobre
`uvicorn.access` con `?etiquetas=…` (como `tests/test_log_acceso.py`) + comprobación de que
`instalar_filtro_de_acceso` sigue en `main.py` + cabeceras HTTP. **Alcance:** proxies inversos y otros
registros quedan fuera de #361 (advertido en `SECURITY.md` §162-168); la app no escribe nombres en
`structlog`.

**AC-14 (FR-14) — XSS y atributos**
Given una etiqueta almacenada `<script>alert(1)</script>` y `?etiqueta=<img src=x onerror=alert(1)>`, When
se pinta en sugerencias, chips, ficha, avisos y `aria-label`, Then el HTML la escapa
(`&lt;script&gt;`), no aparece ningún `<script>` ejecutable, el nombre no aparece en ningún atributo
`class`/`id`/`style`/`hx-*`, las URLs llevan el token `urlencode`-ado y la clase de namespace sale
de un mapa de enum (namespace desconocido: error explícito, nunca `ui.chip(ns, …)`). — *Prueba:* aserciones sobre HTML (patrón `test_titulo_con_script_se_escapa`) + grep de plantillas
(`|safe`, `Markup`, `hx-vals` con tag).

**AC-15 (FR-15) — mass assignment y enum**
Given un POST con `etiqueta=noir&source=comic_vine&weight=100&namespace=genero`, When se
procesa, Then solo cuenta `etiqueta`; el servidor escribe `source='manual'`/`weight=NULL`; Then
`etiqueta` ausente/vacía → 422 o 200 con aviso (según ruta), y un namespace fuera del enum/CHECK →
rechazo con aviso, nunca un insert; Then una revisión del diff no encuentra `Model(**data)` ni
`setattr` sobre cuerpo crudo. — *Prueba:* `tests/test_web_etiquetas.py` + revisión.

**AC-16 (FR-16) — precedencia manual**
Given una fila `source='manual'`, When se evalúa la función pura `puede_escribir(existente,
source_nuevo)` (y el helper de upsert del servicio) para `comicinfo_xml` y `anilist`, Then devuelve
False y no cambia `source`/`weight`/`oculta`; Then un escritor nunca borra una fila manual. — *Prueba:* `tests/test_etiquetas_service.py` (sin BD). Es el contrato que consumen BL-ETQ2/4.

**AC-17 (FR-17, NFR-01/02) — coste**
Given la biblioteca con 24 series y 30 etiquetas, When se piden resultados, Then ≤3 SELECT y las
facetas salen de una sola consulta; When se abre una ficha con 30 etiquetas, Then ≤2 SELECT; Then la
migración deja el índice parcial por `tag_id` y el GIN trigram (comprobado en AC-01). — *Prueba:* contador de sentencias + `EXPLAIN` en Postgres para sugerencias (índice trigram
disponible; el plan exacto es NOT RUN hasta tener datos). NFR-07 (p95) es NOT RUN: se mide en la Pi
antes de fusionar.

**AC-18 (FR-18) — accesibilidad y textos**
Given los fragmentos y la ficha, When se inspecciona el HTML, Then el recuento está en **una**
región `aria-live` y la rejilla no es viva; Then cada chip de quitar tiene nombre accesible; Then la
exclusión lleva texto «Sin», borde discontinuo e icono `minus`; Then se usan los textos exactos de
`ui-etiquetas.md` §8.2 y los iconos nuevos son SVG de Lucide con aviso; Then no hay `<script>` ni
caracteres usados como iconos. — *Prueba:* `tests/test_web_etiquetas.py` + `test_web_css_contraste` si hay clases nuevas.

**AC-19 (FR-19, D-6 ratificada) — crear etiqueta**
Given D-6 ratificada, When el coleccionista escribe un nombre nuevo en la ficha y confirma
«Crear «…»», Then se crea la etiqueta normalizada con `source='manual'` y aviso; un nombre
duplicado normalizado devuelve «ya existe»; Then el buscador principal de Biblioteca **nunca** crea
etiquetas al pulsar Enter. — *Prueba:* `tests/test_web_etiquetas.py`.

**AC-20 (NFR-05/06, cierre) — sin daño colateral**
Given el diff de la PR, When se revisa, Then no entra `src/` fuera de lo listado en §3, ni
dependencias, ni extensiones, ni JS, ni `alembic/versions/` reescritas; Then `tests/test_web_series.py`
se actualiza en la PR de 1a y `tests/test_web_library.py` en la de 1b, y la suite completa pasa;
Then `SECURITY.md` recoge la regla de `|safe` y la frase del segundo uso en
`_asignacion_aviso.html`, y `docs/BACKLOG.md` la fila de BL-ETQ1a al cerrar.

### Historias posteriores (criterios que ya se fijan aquí)

**AC-21 (BL-ETQ2) — ComicInfo de lectura:** `<Tags>dark, Occult</Tags>` y `<Genre>Horror</Genre>` en
un CBZ → `dark`, `occult` con `source='comicinfo_xml'` y `Series.genres` con
«Horror» (solo si estaba vacío); segunda importación idempotente; `<Tags>` de 1 MiB / miles de tokens
se recorta a los topes de §7.4 **con aviso, sin abortar el ciclo**; XML roto = no se toca nada
(`ComicInfoInvalidoError`); no pisa manuales; no escribe XML. *Prueba:* `tests/test_comicinfo_tags_pg.py`
+ CBZ sintéticos; cuántos CBZ reales traen `<Tags>` es NOT RUN (benchmark §1) y se mide aquí.

**AC-22 (BL-ETQ3) — identidad estructurada:** los clientes piden en la misma petición los campos
que su API documenta: AniList `genres` (sin `characters`: no hay relación serie↔personajes donde
persistirlos) y Comic Vine `character_credits`/`story_arc_credits` en el detalle del número
(**Comic Vine no expone `genres`**: no se pide). El enricher puebla `Series.genres`/`Issue.characters`
respetando `locked_fields` y sin pisar `manual`, solo si están vacíos; hay un backfill acotado por
identidad (`anilist_id`/`comic_vine_id`) para filas ya identificadas con la relación vacía. Tebeosfera
sigue sin género (no se inventa); `story_arc_credits` se pide pero no se persiste (no hay relación
inequívoca serie↔arco). Probado con respuestas grabadas, sin red real. *(Implementado en #671,
fusionado el 2026-11-12.)*

**AC-23 (BL-ETQ4) — enriquecimiento de tags:** una serie con `anilist_id` recibe solo el espacio
`etiqueta` ratificado en D-1/D-2 con `weight` = `rank` real (0–100) y `source='anilist'`; una fila
manual de la misma etiqueta sobrevive y no se duplica; una fila `oculta` no resucita; se reutiliza la
caché negativa H2 de 30 días y el espaciado 1,5 s de AniList; sin toggles nuevos. Depende de D-2.

**AC-24 (BL-ETQ5) — alias e implicaciones:** alias único global normalizado (`alias_norm`), que no
colisiona con ningún `name_norm`; sin alias duplicado entre namespaces; implicación sin
autoimplicación ni ciclos (validación al insertar, con prueba de A→B→A) y resuelta en consulta a
profundidad ≤2; fusión de etiquetas solo manual, confirmada y auditada; ninguna fuente crea alias ni
padres sola.

**AC-25 (BL-ETQ6) — export a ComicInfo/Kavita (NO APTO hoy):** no se implementa hasta ampliar el
contrato B6 con plan, autoría (`comicinfo_propio` / hash), `solo_rellenar`, serialización canónica
ordenada y deduplicada, política de qué `source` se exporta, tope del XML de salida, control de
caracteres y pruebas de ida/vuelta; mientras, el veredicto de seguridad es **NO APTO** (evaluación
§11) y no se escribe ni un byte de `<Tags>`.

## 9. Reparto en historias (una PR por historia)

| Historia | Qué entra | Depende de | PR | Talla | Riesgo principal |
|---|---|---|---|---|---|
| **BL-ETQ1a** Etiquetar una serie | §7.1, §7.4–§7.5, ficha (añadir, quitar, crear), sugerencias de la ficha, migración **0022**, pruebas, docs | benchmark + esta spec + D-1/D-6 | 1 PR (#403) | M | sin datos si D-6 se rechaza (ya ratificada); validación y autoescape |
| **BL-ETQ1b** Filtrar Biblioteca | §7.2–§7.4 (filtro, facetas, sugerencias), `SeriesService.list_series`, fragmento compuesto sobre `#rejilla`, pruebas | **BL-ETQ1a fusionada** + BL-IT01 (#283) | 1 PR (#431) | M | paginación que pierde `etiquetas`; coste de facetas |
| **BL-ETQ2** ComicInfo de lectura | `<Tags>`/`<Genre>`, `source='comicinfo_xml'`, `Series.genres` desde fichero, topes, `oculta` | ETQ1a | 1 PR (#544) | M | volumen de `<Tags>` (ALTO §11); cobertura real desconocida (NOT RUN) |
| **BL-ETQ3** Identidad estructurada | poblado de `genres`/`characters` desde fuentes (campos nuevos en la misma petición) + backfill acotado | ETQ1a (contrato) | 1 PR (#671) | M–L | duplicidad con BL-ETQ4 si se decide mal D-1; rate limits intactos |
| **BL-ETQ4** Enriquecimiento de tags | mapeo de fuentes a `etiqueta` con `weight=rank`, precedencia, caché H2 | ETQ1a, ETQ3, **D-1/D-2** | 1 PR | M | idioma de tags (D-2); fragmentación; no pisar manual |
| **BL-ETQ5** Alias / implicaciones / reglas | tablas de alias/padres, validación de ciclos, reglas propuestas, `regla` en `MetadataSource` (si se aprueba) | ETQ1a, ETQ4 | 1 PR | L | ciclos, fusión silenciosa, coste de CTE; ¿quién cura? (D-5) |
| **BL-ETQ6** Export ComicInfo/Kavita | extender B6 + escritura de `<Tags>` + B20 | ETQ1a, contrato B6 | 1 PR (no autorizada antes de extender B6) | L | corromper CBZ / pisar ajeno; **NO APTO** hasta B6 |

Reglas del reparto: **BL-ETQ1a (#403)**, **BL-ETQ1b (#431)** y **BL-ETQ2 (#538, PR #544)**
están fusionadas y desplegadas; **BL-ETQ3 (#565)** está fusionada (PR #671) y pendiente de
despliegue; **BL-ETQ4 ya tiene tarjeta (#697)** por decisión del PO, sin implementar. BL-ETQ5…6
quedan **propuestas** al PO, sin tarjeta, y no empiezan sin su decisión. Una historia = una PR; la
ficha de benchmark de una fase nueva se abre si toca modelo/ficheros. Orden recomendado: 1a → 1b →
2 → 3 → 4 → 5 → 6, con 3 en paralelo a 2 si conviene (comparten clientes, no plantillas).

## 10. Decisiones abiertas del PO y DoR

### 10.1 Decisiones que debe ratificar el PO antes de implementar

> **Respondidas el 2026-11-06: ver §0.1.** La tabla se conserva como el razonamiento de cada opción.

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| D-1 | **Namespaces finales del MVP** (la lista del `CHECK` de 0022) | (a) `tema`, `motivo`, `etiqueta`; (b) solo `tema`; (c) los 6 del anexo | **Ratificada:** solo `etiqueta` visible; `tema`/`motivo` quedan fuera del MVP y la columna se amplía con otra migración |
| D-2 | **Idioma de los tags** | (a) español curado a mano; (b) idioma de la fuente; (c) ambos con alias (fase 4) | (a) en el MVP manual; (b) prohibido hasta ETQ5; la fuente entra en `etiqueta` con `source` visible y peso |
| D-3 | **`publico`/`AgeRating`** | (a) columna estructurada nueva (historia aparte); (b) namespace `publico` de texto; (c) no hacerlo | (a): el anexo promete edad y el modelo no la tiene; **nunca** un namespace de texto |
| D-4 | **Export a ComicInfo/Kavita** | (a) no en el MVP (fase 4, tras extender B6); (b) export ya | (a): seguridad da **NO APTO** hoy; Kavita solo tiene el script de instalación, no integración |
| D-5 | **Quién cura alias/implicaciones** | (a) solo el coleccionista, manual y confirmado; (b) el enricher propone y él confirma; (c) automático | (a) en fase 4; nunca automático desde fuentes (sin wiki ni janitors) |
| D-6 | **¿Se crean etiquetas desde la ficha en BL-ETQ1?** (hueco detectado: `ui-etiquetas.md` §13.3 deja la UI v1 solo asignando existentes, y aún no hay fuentes que siembren) | (a) sí, acción explícita «Crear» con confirmación y `source='manual'`; (b) no, y BL-ETQ1 espera a BL-ETQ2 o a una siembra | (a): sin ella el MVP no tiene datos con los que probarse; **bloquea el DoR si no se decide** |
| D-7 | **Orden y prioridad de BL-ETQ2…6** | el de §9 u otro | 1 → 2 → 3 → 4 → 5 → 6 |

### 10.2 DoR de la tarjeta BL-ETQ1a (para pasar a «Lista para desarrollar»)

- [ ] Ficha de benchmark enlazada (hecha: `benchmark-etiquetas.md`; caduca 2027-01-03).
- [ ] Esta especificación aprobada por el PO, con **D-1, D-2, D-3, D-4 y D-6 ratificadas** (D-5 y D-7 no bloquean la primera PR).
- [ ] Diseño de UI aceptado: `ui-etiquetas.md` §5–§9 y textos de §8.2 (o sus cambios, hechos en ese documento y en sus pruebas).
- [ ] Dictamen de seguridad §11 incorporado como criterios (AC-13…AC-17 y AC-21/23/24/25).
- [ ] Tarjeta con: título `[BL-ETQ1a] …`, criterios AC-01…AC-05, AC-07 (ficha), AC-10, AC-12…AC-16 y AC-19 enlazados, talla M, `Bloqueada = No`, «Etiquetas» como etiqueta del Project 1.
- [ ] Entorno: `TEST_DATABASE_URL` con BD de nombre «test» y `pytest --basetemp` en el mismo
      dispositivo que `/`; ninguna otra historia del MVP en curso (WIP: máx. 1 MVP + 1).

**DoD de la PR de 1a:** AC-01…AC-05, AC-07 (ficha), AC-10, AC-12…AC-16 y AC-19 en verde
(FakeSession y Postgres real), migración 0022 upgrade/downgrade probada, `SECURITY.md` y
`docs/BACKLOG.md` actualizados, sin dependencias/JS/extensiones nuevas. NFR-07 (latencia en la Pi)
se mide en la PR de 1b, que es la que añade el filtro de Biblioteca.

## 11. Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R-1 | BL-ETQ1a se queda sin datos si no hay etiquetas que asignar | baja | alto | D-6 ratificada: se pueden crear desde la ficha; si el uso real no aparece, se mide antes de ETQ2 |
| R-2 | Ampliar el fragmento de `/ui/biblioteca/resultados` rompe htmx/Atrás y las pruebas existentes | media | bajo | en 1b: destino `#rejilla`, `pagina_url` y colas de FakeSession actualizadas; prueba de regresión de paginación; no se crea `#resultados-biblioteca` |
| R-3 | Facetas/recuento caros con miles de series en la Pi | media | medio | EXISTS/NOT EXISTS, índice parcial, una consulta, topes; plan B «Ver más sin recuento exacto»; NFR-07 se mide |
| R-4 | Fragmentación del catálogo por mayúsculas/tildes/espacios | media | medio | unicidad normalizada + sugerencias + token canónico; D-2 |
| R-5 | XSS/atributos con nombres de etiqueta | baja | alto | autoescape + no `safe` + tests adversariales (AC-14) |
| R-6 | El downgrade de 0022 pierde asignaciones o falla por duplicados de `name` | baja | medio | dedupe determinista documentado; prueba upgrade→downgrade→upgrade (AC-01) |
| R-7 | `autofocus` en swap OOB no funciona en htmx 4.0.0 (NOT RUN) | media | bajo | plan B de `ui-etiquetas.md` §7.4 (foco en destino/`hx-focus`), nunca JS a mano |
| R-8 | Otros registros o un proxy inverso conservan la query (el access log de uvicorn la quita: #361) | baja | bajo | fuera del alcance de #361, advertido en `SECURITY.md` §162-168; la app no escribe nombres en `structlog` (AC-13) |
| R-9 | Caché negativa/rate limits de fuentes se tocan antes de tiempo | baja | medio | BL-ETQ4 reutiliza H2 y espaciados; BL-ETQ1a/1b no tocan clientes |

## 12. Trazabilidad, límites y caducidad

- **Requisito → criterio:** FR-01…FR-19→AC-01…AC-19 (en orden); NFR-01…09→AC-01/17/20; historias
  futuras→AC-21…AC-25.
- **Condiciones §11 → criterios:** volumen ComicInfo→AC-21; fragmento HTML→AC-14; validación→
  AC-02/03/10; mass assignment→AC-15; alias/ciclos→AC-24; rendimiento→AC-17/NFR-01/02/07;
  ComicInfo/B6→AC-25; privacidad/`no-store`→AC-13/AC-20; legal→AC-21/23; superficie/BD→AC-01/NFR-05.
- **NOT RUN:** `COUNT(*)` real de `tags`/`issue_tags`/`series_genres` (0 filas por construcción, no
  medido); nº de CBZ con `<Tags>`; latencia en Pi (NFR-07); plan trigram con datos; `autofocus` OOB
  en htmx 4.0.0; cobertura de alias/padres en la Pi. Se cubren en sus historias, no se suponen.
- **Lo que esta spec no decide:** tablas distintas de las del repo, la lista de namespaces sin D-1,
  el diseño de las fases 2–4 (cada una abre su ficha) ni arquitectura (sin ADR nuevo; si ETQ5
  introduce reglas con `MetadataSource.regla`, se decide allí con su migración).
- **Caducidad: 2027-01-03.** Antes hay que revisar el head de Alembic, el contrato B6 y que
  `ui-etiquetas.md` no haya cambiado. Sin decisión del PO, esta spec no autoriza implementar.
