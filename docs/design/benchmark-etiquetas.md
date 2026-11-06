# Ficha de benchmarking — sistema de etiquetas (tags)

> Ficha de **nivel 2** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): toca
> modelo de datos, importación de ficheros y UI de biblioteca. **No hay historia ni ID de
> backlog todavía**: el problema nace del anexo `docs/design/propuesta-externa-etiquetas.md`
> (pegado por el PO el 2026-11-04) y esta ficha es insumo para la especificación, no
> aprobación. **Commit contrastado: `35283b5` (2026-11-04, `origin/main`).** Fecha de la
> ficha: 2026-11-04. Caduca: 2027-01-03 (~60 días).

## 1. Problema local (código vigente, no la propuesta)

**Historia / problema observado.** El coleccionista busca «noir», «escuela», «Batman» o
«space opera» en su tebeoteca y solo puede buscar por título: la biblioteca filtra por
tradición, editorial, personaje y saga (cuatro campos cerrados), y los descriptores libres
no existen en la UI. La propuesta externa pide un sistema de etiquetas con espacios de
nombres, alias, padres/implicaciones, procedencia/peso, ida y vuelta con ComicInfo, mapeo
desde el enricher y filtros AND/exclusión en HTMX. Antes de dimensionarlo hay que fijar qué
hay ya en el repo, porque **la propuesta asume cosas que no son ciertas** (§2).

**Hechos comprobados en el código vigente** (todos re-verificados a `35283b5`):

| Hecho | Evidencia |
|---|---|
| El modelo `Tag` y la tabla `issue_tags` **ya existen desde la migración 0001** y están **dormidos**: no hay ni una referencia fuera de `models/__init__.py` (ni servicio, ni router, ni test, ni plantilla). | `src/zascarr/models/__init__.py:497-501` (`Tag`: `id` UUID, `name` único, `color`), `:216-228` (`issue_tags`: M:N issue↔tag), `alembic/versions/20260301_0001_initial_schema.py:159-168` |
| `Tag` no tiene `namespace`, ni alias, ni padres, ni `source`, ni `weight`; `Series.tags` **no existe**. | `models/__init__.py:497-501`; `Issue.tags` en `:462`; no hay relación `Series.tags` |
| `Series.genres` (M:N `series_genres`) e `Issue.characters` (M:N `issue_characters`) **existen, pero nadie los puebla**: el enricher no los escribe. | `models/__init__.py:181-196, 198-214, 279-284, 310-332, 405, 461`; `services/enricher.py:258-274` y `:349-401` solo tocan ids, descripción, portada, total y créditos |
| La ficha de serie **ya pinta** `Series.genres`, pero siempre sale vacío. | `web/templates/series_detail.html:12-13`; `api/series.py:164` carga la relación |
| La biblioteca **ya filtra** por tradición, editorial, personaje y saga, pero personaje/saga dependen de tablas que nadie rellena (no hay ningún `Character(...)` ni `StoryArc(...)` en `src/`). | `web/library.py:67-80`; `services/series.py:39-90` (`:53`, `:61`, `:68`); grep de creación: solo la definición del modelo |
| La búsqueda actual es título a texto completo en español; no hay filtro por etiqueta. | `services/series.py:58` (`to_tsvector('spanish', Series.title)`) |
| Los clientes de fuentes **no piden** tags, géneros ni personajes. | Comic Vine `field_list` de serie en `services/comic_vine.py:133` y de issue en `:166`; AniList no pide `tags`/`genres`/`isAdult` (`services/anilist.py:42-55`); Tebeosfera no devuelve género (`services/tebeosfera.py:100-109`) |
| El parser de ComicInfo **ignora `<Tags>`** y lee `<Genre>` en un campo (`ComicInfo.genre`) que **ningún consumidor lee**. | `core/importer_triage.py:135-181` (`genre` en `:139`, mapeo en `:162`; grep de `.genre` no encuentra consumidor) |
| La escritura de ComicInfo gestiona **solo 7 campos**: `Series, Number, Volume, Year, Publisher, Summary, LanguageISO`; no hay `Genre`, ni `Tags`, ni `AgeRating`. | `core/comicinfo_write.py:36-38`; `services/tagger.py:227-253` |
| `unaccent` y `f_unaccent()` ya están instalados (0006) además de `pg_trgm` (0001); **`f_title_norm` NO sirve para etiquetas** porque quita artículos y puntuación. | `alembic/versions/20260921_0006_matcher_metadata_fixes.py:92-104` (`unaccent`, `f_unaccent`), `:117` (`f_title_norm`); `alembic/versions/20260301_0001_initial_schema.py:16` (`pg_trgm`) |
| La caché negativa del enricher (H2, 30 días) ya existe y se puede reutilizar; no hace falta tabla nueva. | `services/enricher.py:88-94`, `:186-189`, `:232-233`, `:361-364` |
| Head real de Alembic: **0020**; la siguiente migración es **0021**. Los PK son **UUID**, no `int`. | `alembic/versions/20261019_0020_*`; `models/__init__.py:499` y resto del modelo |
| La «integración con Kavita baremetal» es **un script de instalación** (`scripts/kavita.sh`); la exportación B20 es diseño **no implementado**. | `scripts/kavita.sh`; `docs/design/B20-exportacion-kavita.md` («pendiente de implementar»); no hay código de exportación en `src/` |

**Resultado deseado (para la especificación).** Poder (1) etiquetar a nivel de serie con
descriptores libres; (2) encontrar por etiqueta con AND y exclusión y ver por qué aparece
cada etiqueta (procedencia); (3) que lo manual no lo pise el enricher; (4) leer y,
opcionalmente, escribir `<Tags>`/`<Genre>` de ComicInfo sin perder lo ajeno; (5) todo dentro
del presupuesto de la Pi (512 MiB, sin Redis, ADR-0011).

**Datos reales y medición de partida (NOT RUN).** No se ejecutó ninguna consulta contra la
BD real. Por construcción, `tags`, `issue_tags`, `series_genres` e `issue_characters` tienen
**0 filas**: ningún código de `src/` crea filas en esas tablas (grep a `35283b5`). Medición
que debe hacer la spec antes de dimensionar: `COUNT(*)` de las cuatro tablas, nº de series
con `genres`/`characters`, nº de CBZ con `<Tags>` en una muestra real (el parser actual no lo
cuenta), y tiempo en Pi de un `GROUP BY` de facetas sobre la biblioteca real. Caso real para
la historia: «Mortadelo y Filemón» o «Thorgal» no se pueden filtrar por «humor»/«fantasía», y
«Batman» no aparece por personaje porque `characters` está vacía.

## 2. Verificación del anexo §6 (afirmación por afirmación)

| # | Afirmación del anexo | Resultado | Evidencia / matiz |
|---|---|---|---|
| 1 | FastAPI + SQLAlchemy async + PostgreSQL 15 + Jinja2/HTMX, orientado a Raspberry Pi | **[verificado]** | `pyproject.toml` (FastAPI, SQLAlchemy async, Jinja2); `docker-compose.yml:38,72` `postgres:15-alpine`; límites de memoria en `docker-compose.yml:66-68,99-101`; ADR-0001 |
| 2 | Ya existen `pg_trgm`, `unaccent` y una función de normalización **reutilizable** | **[parcial]** | `pg_trgm` en 0001:16; `unaccent` + `f_unaccent` en 0006:92-104. `f_title_norm` existe (0006:117) pero **quita artículos** («The Sandman» → «sandman»): para etiquetas hay que usar `lower(f_unaccent(name))`, no `f_title_norm` |
| 3 | Ya existe un util de ComicInfo donde enchufar `<Tags>` | **[parcial]** | Hay parser (`importer_triage.py:151-181`) y escritor (`comicinfo_write.py`), pero el parser ignora `<Tags>` y el escritor no lo gestiona (7 campos). `<Genre>` se parsea y **nadie lo consume** |
| 4 | El enricher es multi-fuente y tiene procedencia **por campo** | **[parcial/incorrecto]** | Multi-fuente sí (CV/AniList/Tebeosfera; GCD solo Descubrir, ADR-0002). La procedencia es **por fila** (`metadata_source`) + `locked_fields`, no por campo; y ninguna fuente pide tags/géneros/personajes (`comic_vine.py:133,166`; `anilist.py:42-55`; `tebeosfera.py:100-109`) |
| 5 | El modelo ya filtra por tradición, editorial, personaje y saga | **[verificado en la consulta, datos dormidos]** | `services/series.py:53,61,68`; pero `Character`/`StoryArc` no tienen escritor en `src/`: el filtro funciona el día que existan datos |
| 6 | El repo ya tiene integración opcional con Kavita baremetal | **[incorrecto]** | Solo `scripts/kavita.sh` (instala Kavita en la Pi). B20 (exportación con parche ComicInfo) está **diseñado y no implementado**; no hay escritura de `<Tags>` ni llamada a Kavita |
| 7 | Kavita tiene smart filters y mapper genres↔tags; Calibre-Web typeahead; Hydrus aliases/parents; LANraragi y boorus AND/exclusión | **[verificado]** (con matices) | Kavita 0.9.1 y wiki de filtros: AND/OR, `Must Contains`/`Must Not Contains`, campos Tags/Genres/Age Rating/Characters; el **mapper genres↔tags y el age mapping viven en Kavita+** (suscripción), no en el escáner base. Calibre-Web 0.6.27: typeahead real (`cps/static/js/edit_books.js`, Bloodhound `#tags` → `/get_tags_json`). Hydrus v694a: siblings/parents y búsqueda. LANraragi 0.9.81 y e621/Gelbooru: sintaxis de búsqueda |
| 8 | La migración siguiente sería la 0010 y el repo va por 0001–0009 | **[incorrecto]** | Head **0020**; siguiente **0021**; 20 revisiones. PK **UUID en el dominio** (única excepción: el singleton `runtime_settings.id`, entero) |
| 9 | AniList devuelve tags con `rank` 0-100 e `isAdult` | **[verificado en la API; no en el cliente]** | Docs AniList (`MediaTag.rank`: «relevance ranking … out of the 100»; `MediaTag.isAdult`; `Media.isAdult`; `category`, spoilers) en el commit de docs `03281c0`. El cliente actual (`anilist.py:42-55`) **no pide** `tags` ni `isAdult` |
| 10 | ComicInfo define `<Tags>` como lista por comas y Kavita lo lee | **[verificado]** | Anansi `DOCUMENTATION.md` commit `99e1453`: `<Tags>` «comma separated» y también `<Genre>`; Kavita (wiki de metadatos) y Komga (`ComicInfoProvider.kt:118`, `:153`) lo leen. **Ojo:** ComicTagger **no escribe** `<Tags>` (§3) |

**Nota documental.** El anexo remite a `docs/design/evaluacion-propuesta-etiquetas.md`
para las marcas [verificado]/[incorrecto]. Ese documento **no existía cuando se abrió esta
ficha**; al cerrarla sí aparece en el árbol de trabajo (creado en paralelo por el Lead y
citando esta ficha como evidencia). El §2 se mantiene aquí como fuente porque el anexo se
pegó sin verificar y el benchmark no debe depender de otro documento: si la evaluación y esta
ficha divergen, manda el código y se anota la discrepancia.

## 3. Referencias consultadas (versión/commit)

| Referencia | Versión / commit | Licencia | Qué se inspeccionó |
|---|---|---|---|
| Komga | **1.29.2**, `25c67d14` (2026-10-30, `main`) | MIT | Modelo `SeriesMetadata`/`BookMetadata`, `SearchCondition`/`SearchOperator`, `SeriesSearchHelper`, `ComicInfoProvider` (código Kotlin por `git show` del checkout local) |
| Kapowarr | **1.3.2**, `c191dda` (2026-09-14, `main`) | GPL-3.0 | Esquema (`backend/internals/db_models.py`), `file_processing`, búsqueda; sin modelo de tags/géneros |
| Kavita | **0.9.1.18**, `9e17770` (2026-11-01, `develop`) | GPL-3.0 | Wiki de filtros y de metadatos ComicInfo (contrato de campos y operadores), wiki de Kavita+ (field mapping/age mapping); `openapi.json` presente en el repo (no abierto entero) |
| Mylar3 | `cdc94a4` (2025-08-17, `master`; actividad 2026-03) | GPL-3.0 | `mylar/cmtagmylar.py` (metatagging delegado a ComicTagger), esquema (sin tabla de tags propia) |
| Suwayomi | **v2.4.2366** (2026-09-30) | MPL-2.0 | `MangaType.kt` (`genre: List<String>`, sin entidades de tag/alias/parents), esquema GraphQL |
| LANraragi | **0.9.81** (2026-07-06) | MIT | `tools/Documentation/basic-operations/searching.md` (sintaxis de búsqueda) |
| Hydrus | **v694a** (2026-11-04) | WTFPL | Docs de tags, búsqueda, tag siblings y tag parents (`docs/` del repo) |
| Calibre-Web | **0.6.27** (2026-08-08) | GPL-3.0 | `cps/static/js/edit_books.js` (typeahead `#tags`), release notes 0.6.27 |
| ComicTagger | **1.5.5** (release 2022); `develop` `fa11a34` (2026-09-06) | Apache-2.0 | `comicapi/tags/comicrack.py`: campos soportados y escritura de `<Genre>`; **no** `<Tags>` |
| ComicInfo (Anansi) | commit `99e1453` (2026-06) | — | `DOCUMENTATION.md`: `<Tags>`, `<Genre>`, `<Characters>`, `<AgeRating>` |
| AniList API | docs `03281c0` (2026-08-18) | — | `MediaTag` (`rank`, `isAdult`, `category`), `Media` (`tags`, `genres`, `isAdult`) |
| Boorus | Danbooru `e8af67d` (2026-11-04); e621 `v26.11.04-fix.1`; Gelbooru wiki `howto:cheatsheet` v23 (2026-05-02) | Danbooru BSD-2 (texto del repo; GitHub lo marca NOASSERTION); e621/Gelbooru [licencia de código sin verificar] | Modelos de tag/alias/implication (Danbooru), categorías y relaciones (e621), sintaxis AND/OR/exclusión (e621, Gelbooru, Hydrus) |

### Teardown breve

- **Komga.** Lector/servidor para coleccionistas; metadatos por serie y por libro. Genres y
  tags son **conjuntos de textos planos** en minúsculas (`SeriesMetadata.kt`), con locks por
  campo; el buscador v2 es un árbol `anyOf`/`allOf` con operadores de igualdad
  `is`/`isNot`/`isNull` sobre `Tag`, `Genre`, `AgeRating`, etc. (`SearchCondition.kt:127,152`,
  `SearchOperator.kt`), más los operadores `contains`/`doesNotContain` (`SearchOperator.kt:48-53,161-170`;
  SQL en `SearchOperatorUtils.kt:38-39`) aplicados a los campos Tag/Genre (`SeriesSearchHelper.kt:97,238`).
  Lee `<Genre>`, `<Tags>` y
  `<AgeRating>` de ComicInfo. **Fricciones:** sin espacios de nombres, sin alias ni padres; el
  tag es un string y la agregación libro→serie es un caso especial (`SERIES_METADATA_TAG` /
  `BOOK_METADATA_AGGREGATION_TAG`); no escribe ComicInfo.
- **Kapowarr.** Descargador para lectores; unidad = volumen de Comic Vine. **No tiene modelo
  de tags, géneros ni personajes**: su BD solo guarda ficheros y volúmenes
  (`db_models.py`), y ComicInfo es un fichero de metadatos que detecta, no un catálogo.
  **Fricción:** nada que adoptar para etiquetas; sirve de contraejemplo de que el
  descriptor libre no es requisito de un gestor de descargas.
- **Kavita.** Servidor de lectura con metadatos; separa **Genres** y **Tags** y los expone en
  filtros guardables (Smart Filters) con AND/OR y operadores multiselección «must contain»/
  «must not contain» (wiki de filtros 0.9.1). Lee `<Genre>` y `<Tags>` de ComicInfo. El
  **mapper genres↔tags, el filtrado por peso y el age mapping desde tags/géneros** están en
  Kavita+ (wiki de *Metadata Controls*): es una función de pago sobre metadatos externos, no
  del escáner; la propia comunidad pide poder aplicar ese mapeo **fuera** del flujo de match
  ([discusión #3862](https://github.com/Kareadita/Kavita/discussions/3862)). **Fricciones:**
  tags planos sin alias/padres; la parte potente depende de una suscripción y de fuentes
  externas; el filtro de tags es a nivel de serie aunque el dato venga del fichero.
- **Mylar3.** Descargador clásico; escribe ComicInfo **delegando en el ComicTagger incluido**
  (`cmtagmylar.py`), y solo pasa volumen, `storyArc`/`storyArcNumber` y `ageRating`. **No hay
  vocabulario de tags**; sus «comic tags» son campos de ComicInfo. **Fricción:** no sirve
  como referencia de taxonomía; su tagger no escribe `<Tags>`.
- **Suwayomi.** Servidor de manga; `Manga.genre` es una **lista de strings que da la fuente**
  y la biblioteca se organiza por categorías. **No hay entidad tag, alias ni padre.** Es el
  caso más cercano a ZascArr en cuanto a tradición manga, y confirma que el género de fuente
  se guarda como dato, no como folksonomía.
- **LANraragi.** Lector de archivos; la búsqueda separa términos por comas (AND), admite `-`
  para excluir, comodines `*`/`?`, `$` para coincidencia exacta y autocompletado. **Fricción:**
  los tags son strings del archivo; sin alias/padres ni facetas verificadas.
- **Hydrus.** Cliente local de medios; **namespaces** con `namespace:tag`, **siblings** (n→1,
  transitivos: «bad tag» → «good tag») y **parents** (n→n, virtuales: todo lo que tiene C
  «aparece» con P), autocompletado con conteos y búsqueda AND implícita, `-tag` para excluir,
  OR con Shift y comodines. **Fricciones:** cliente de escritorio, mantenimiento por
  «janitors», los parents son inferencia editorial y consumen CPU, y la API de cliente no
  distingue bien parents/siblings
  ([issue #957](https://github.com/hydrusnetwork/hydrus/issues/957)); no es un servidor.
- **Calibre-Web.** Catálogo de libros; el campo `#tags` se edita con typeahead real
  (Bloodhound, `/get_tags_json`, separación por comas) y hay filtros incluir/excluir. En
  0.6.27 corrigió la creación de tags duplicados por mayúsculas. **Fricción:** el tag es
  texto plano; no hay namespace/alias/padre.
- **ComicTagger.** Etiquetador de referencia: escribe ComicInfo de ComicRack. **Soporta
  `Genre`, `Characters`, `Teams`, `Locations`, `AgeRating`… pero NO `<Tags>`** (no está en
  `supported_attributes` ni en `_convert_metadata_to_xml`). **Fricción:** quien espere que
  `<Tags>` venga «de ComicTagger» se equivoca; es un campo que casi nadie escribe.
- **ComicInfo (Anansi).** `<Tags>` es una lista separada por comas «del libro o la serie»,
  semánticamente **vaga** y sin namespace; convive con `<Genre>`, `<Characters>`,
  `<AgeRating>`. **Fricción:** el mismo descriptor puede ir en Genre o en Tags; sin regla,
  cada herramienta lo pone donde quiere.
- **Boorus.** e621: categorías (artist/character/copyright/species/general/meta/lore), alias
  e implicaciones mantenidas por la comunidad, búsqueda AND por espacios, `~` para OR,
  `-` para exclusión y grupos. Danbooru: categorías, `TagAlias` (n→1, transitivo) y
  `TagImplication` (n→n, sin bucles ni transitivos redundantes, con validaciones de tamaño y
  wiki), ancestros/descendientes recursivos. Gelbooru: AND, `-tag`, OR con `{a ~ b}`,
  comodines; su wiki no documenta alias/padres. **Fricciones:** la folksonomía exige
  moderación; la categoría es política de cada sitio; el modelo es fichero/imagen, no
  «serie con números».

## 4. Supuestos de sus modelos que NO valen en ZascArr

- **La unidad es la imagen/fichero, no la serie con números.** Hydrus/boorus etiquetan
  archivos; aquí el uso principal es «encontrar series» y los huecos/wishlist viven a nivel
  de número (`Issue`, `Wishlist`). Copiar `issue_tags` como única tabla obligaría a agregar
  por `COUNT(DISTINCT issue_id)` en cada filtro de biblioteca.
- **La taxonomía es comunitaria y se mantiene con janitors.** ZascArr tiene un solo
  coleccionista no técnico: no hay wiki de tags ni moderadores. Alias y padres deben ser
  pocos, manuales y con confirmación; no un sistema de peticiones.
- **El namespace es una convención de texto.** Hydrus y e621 lo escriben en el nombre
  (`character:batman`) o en una categoría; aquí hay `Genre`, `Universe`, `Character`,
  `StoryArc`, `IssueFormat` y `FileFormat` estructurados. Un namespace `personaje:` o
  `formato:` duplicaría identidad que el propio anexo dice conservar estructurada.
- **Hay un proveedor de tags fiable en todas las fuentes.** AniList tiene tags con rank;
  Comic Vine expone `genres`/`character_credits` si se piden; Tebeosfera no devuelve género.
  Los clientes actuales **no los piden**: el enricher tendría que cambiar peticiones, no solo
  mapear.
- **La Pi puede permitirse implicaciones materializadas y facets en vivo.** Hydrus avisa del
  coste de calcular parents; Kavita resuelve filtros con SQL sobre SQLite/SQL Server. Aquí
  512 MiB compartidos y `uvicorn --workers 1`: padres en `WITH RECURSIVE` limitados a la
  consulta y facets con `GROUP BY` indexado; nada de tabla de cierre transitivo en v1.
- **`<Tags>` es de fiar como canal de ida y vuelta.** ComicTagger no lo escribe; Kavita y
  Komga lo leen; B6 de ZascArr no lo escribe. El canal existe, pero su cobertura real en CBZ
  españoles es una incógnita que hay que medir antes de depender de él.

## 5. Resultado por idea (decisión por idea, no global)

| Idea de la propuesta | Resultado | Motivo y condición |
|---|---|---|
| Mantener identidad editorial (tradición, editorial, año, número, saga) en columnas y reservar tags para descriptores | **Adoptar** | Principio de Hydrus y del propio anexo; encaja con el modelo actual (`Series`, `Issue`, `StoryArc`, `Genre`, `Character`) |
| Namespaces (`genero:`, `tema:`, `personaje:`…) | **Adaptar** | Adoptar el concepto de Hydrus, pero como **columna `namespace`**, no dentro del nombre; y **no duplicar** `genero`/`personaje`/`formato` que ya son columnas/relaciones |
| Alias (siblings n→1) | **Adaptar** | Patrón Hydrus/Danbooru útil («super-man»→«superman»), pero con curación manual y sin el aparato de peticiones/revisión. Fase 2 |
| Padres/implicaciones (n→n, virtuales) | **Adaptar** | Patrón correcto (Hydrus), pero resueltas en consulta con profundidad limitada; materializarlas es «mejorar» solo si una medición en Pi lo justifica. Fase 3 |
| `source` por asignación | **Adaptar** | Reutilizar `MetadataSource` (+ valor nuevo `regla`, hoy no existe) o un string acotado; la procedencia es un requisito de confianza, ya hay `metadata_source`/`locked_fields` como precedente |
| `weight` 0–100 | **Adaptar** | Solo tiene fuente real AniList (`rank`); nullable y sin inventar pesos por fuente. No usarlo para ordenar resultados en v1 |
| Tabla `serie_tag` singular con ids int | **Descartar** y **construir sobre lo propio** | Los PK son UUID y ya existe `tags`; se reutiliza `tags` y se añade la relación de serie que falte (`series_tags`), no una tabla paralela. `issue_tags` se queda para el futuro |
| Etiquetar a nivel de serie por defecto, `issue_tag` después | **Adoptar** | Coincide con el filtro de biblioteca actual (`SeriesService` filtra series) y con el consejo del anexo; `issue_tags` ya existe, así que no hay que crear nada para la fase 2 |
| Poblar `Series.genres` e `Issue.characters` en vez de crear tags `genero:`/`personaje:` | **Construir sobre lo propio** | Las columnas/relaciones ya existen (`models:181-214,279-284,310-332,405,461`), la ficha ya pinta genres y `SeriesService` ya filtra por personaje. Es más barato completar eso que duplicarlo en tags |
| Mapear Comic Vine `genres`/`characters` y AniList tags en el enricher | **Adaptar** | Requiere ampliar los `field_list` de los clientes (`comic_vine.py:133,166`; `anilist.py:42-55`), respetar `locked_fields` y reutilizar la caché negativa H2. Es un cambio de cliente + mapeo, no solo de servicio |
| Importar `<Tags>` de ComicInfo con `source='comicinfo'` | **Adaptar** | Leer en `parse_comic_info` (`importer_triage.py:151-181`) y guardar al importar; `metadata_source` ya contempla `comicinfo_xml`. Nunca pisar manual |
| Exportar al `<Tags>` del CBZ | **Descartar por ahora** | B6 gestiona 7 campos y tiene garantías de autoría/reversión (`comicinfo_write.py`, `tagger.py`); añadir `<Tags>` es un cambio de contrato de fichero que debe esperar a que la spec decida y a B20 (Kavita) |
| Autocompletado con `similarity()` y conteo de series | **Adoptar** | Patrón Calibre-Web/Hydrus/Komga; en ZascArr `pg_trgm` ya está y `f_unaccent` permite ordenar insensible a tildes; una sola consulta con `COUNT(*) ... GROUP BY` |
| Filtros con chips: clic = AND, `alt`-clic o prefijo `-` = exclusión | **Adaptar** | Adoptar el contrato de Kavita (`must not contain`) y e621/Hydrus (`-tag`); **sin `alt`-clic** (JS que el repo evita): chip de excluir explícito o token `-`, con formulario HTMX |
| Chips coloreados por namespace y edición inline (`hx-post`) | **Adaptar** | Encaja con Jinja2+HTMX y el patrón de Pendientes; el color puede derivarse del namespace (Hydrus colorea por namespace) y `Tag.color` ya existe |
| Smart filters guardados | **Descartar en v1** | No es requisito core; añade tabla, CRUD y UI. La biblioteca ya tiene filtros fijos; se reevalúa cuando los tags estén poblados |
| Reglas de mapeo estilo Kavita (genres↔tags) | **Adaptar (fase 3)** | El mapper de Kavita vive en Kavita+ y sobre metadatos externos; aquí solo tiene sentido cuando existan alias/padres. Sin evidencia de necesidad, no en MVP |
| Integración/export a Kavita | **Descartar por ahora** | Solo existe el script de instalación; B20 es diseño. Escribir `<Tags>` para Kavita sin B20 mezcla dos historias |
| `formato:` como tag (grapa, integral, tankoubon) | **Descartar** | Ya está estructurado en `IssueFormat`/`FileFormat`; duplicarlo crea dos verdades (un integral etiquetado «grapa» y con `format=OMNIBUS`) |
| `publico:` como tag (infantil/adulto) | **Descartar en MVP; decisión aparte** | No hay campo `AgeRating` en el modelo actual (CLAUDE §2 lo menciona, pero no existe en `models/__init__.py`); ComicInfo sí tiene `<AgeRating>` y Kavita/Komga lo leen. Si se quiere edad, es una columna/atributo estructurado, no un namespace de texto |
| Caché negativa para fuentes sin tags | **Adoptar lo existente** | H2 ya implementada (`enricher.py:88-94`): extenderla a «fuente sin tags», sin tabla nueva |
| IDs `int` y migración 0010 | **Descartar** | PK UUID (`models:499`) y head 0020/0021; el anexo lo reconoce como transcription error, pero hay que decirlo en la spec |
| «Los tags sirven para reencontrar, no para describir» | **Adoptar** | Frase de Hydrus citada por el PO; es el criterio para decidir qué se queda estructurado |

## 6. Matriz 0–5 (pesos suman 100; una línea de evidencia por celda)

**Pesos** (se mueven tres respecto a los de por defecto, justificado):
cobertura del requisito core **25** (sube de 15: sin tags poblados no hay historia), encaje con
el Coleccionista **20** (baja de 25: el filtrado ya existe para cuatro campos),
coste en Pi **20**, legalidad/licencia **15** (baja de 20: todo es patrón, ningún runtime
externo), adaptabilidad al stack/modelo **10**, mantenimiento de la referencia **5**, lock-in **5**.

Opciones: **S0** statu quo (sin tags libres; solo filtros cerrados) · **A** propuesta literal
(`Tag` int, 0010, 4 tablas, namespaces `genero/personaje`, alias/padres, weights, UI
completa) · **B** construir sobre lo propio (UUID/0021, un `tags`, `series_tags` + `issue_tags`
dormida, poblar `Series.genres`/`Issue.characters`, leer `<Tags>`, filtros AND/exclusión;
alias/padres por fases) · **C** patrón booru completo (namespace en el nombre, alias y
parents materializados, pesos y smart filters) · **D** solo poblar
`Series.genres`/`Issue.characters` y ampliar filtros (sin tags libres).

| Criterio (peso) | S0 | A literal | **B sobre lo propio** | C booru completo | D solo estructurado |
|---|---:|---:|---:|---:|---:|
| Cobertura core (25) | **1** — no hay tag libre ni filtro por descriptor | **4** — cubre todo, pero duplica género/personaje y contradice UUID/0021 | **5** — descriptores libres + identidad estructurada + ComicInfo + filtros | **5** — cubre el patrón entero | **2** — genres/personajes sí; «noir»/«escuela» no |
| Encaje Coleccionista (20) | **1** — cuatro filtros y búsqueda por título | **3** — mucha maquinaria antes de ver el primer tag útil | **4** — chip+autocompletado+filtros; crece por fases | **2** — exige curar taxonomía y categorías | **2** — no puede etiquetar lo que no sea género/personaje |
| Coste en Pi (20) | **5** — cero trabajo | **2** — 4 tablas M:N, alias, parents, trigram, reglas | **3** — una tabla + una M:N + 2 índices; facets por `GROUP BY` | **1** — implicaciones materializadas, pesos, smart filters | **4** — sin tablas nuevas, pero más payload del enricher |
| Legalidad/licencia (15) | **5** — sin cambio | **3** — patrones de GPL/MPL si se copia implementación; riesgo de taxonomía ajena | **5** — solo patrones, código propio GPL-3.0 | **2** — copiar taxonomía/moderación de e621 no es un patrón | **5** — sin cambio de licencia |
| Adaptabilidad stack/modelo (10) | **3** — no hay nada que adaptar | **2** — `int`, `serie_tag`, `name` único global | **5** — UUID, 0021, reutiliza `MetadataSource`/`locked_fields` | **2** — namespace en nombre, choca con campos estructurados | **4** — usa relaciones ya existentes |
| Mantenimiento referencia (5) | **5** — no depende de nadie | **3** — mezcla Kavita+, Hydrus desktop y boorus | **4** — patrones de proyectos vivos (Komga/Kavita/e621) | **2** — Danbooru caído hoy; e621 exige moderación | **4** — fuentes activas |
| Lock-in (5) | **5** — ninguno | **5** — esquema propio | **5** — esquema propio, sin dependencias | **4** — esquema propio, taxonomía costosa | **5** — ninguno |
| **Total ponderado /5** | **3,00** | **3,05** | **4,35** | **2,40** | **3,30** |

**Lectura.** S0 puntúa bien en lo barato y no cumple el requisito; A cubre el requisito pero
paga de más y contradice el modelo (UUID, `name` único, migración, duplicar género/personaje);
D es barato pero no deja al coleccionista crear el descriptor que busca; C es el patrón de
otro dominio (fichero/imagen con moderación comunitaria). **B gana** porque reutiliza lo que ya
existe (Tag/issue_tags, `Series.genres`, `Issue.characters`, `unaccent`, H2) y añade solo lo
que falta.

**Veredicto global: CONSTRUIR SOBRE LO PROPIO**, con vocabulario y contrato de interacción
adoptados de Hydrus/Kavita/Komga. Se justifica el sesgo «adoptar > comprar > construir»:
no hay producto externo que comprar para el núcleo (ni Komga ni Kavita ofrecen un servicio de
etiquetas a ZascArr), y lo propio ya tiene las piezas caras hechas (modelo `Tag`/`issue_tags`,
`Series.genres`, `Issue.characters`, `pg_trgm`, `unaccent`, caché negativa H2). Construir de
cero un modelo paralelo (A) o importar el modelo booru entero (C) es más caro y contradice el
repo. El MVP de la especificación debe limitarse a: `tags` + `series_tags`, filtros
AND/exclusión, autocompletado, lectura de ComicInfo y poblado de géneros/personajes; alias,
padres, reglas y escritura de ComicInfo van por fases con evidencia.

## 7. IGUALAR (mínimos competitivos, nivel concreto)

1. **Filtro de biblioteca por etiqueta con AND y exclusión, a nivel de serie y paginado en
   servidor.** Mínimo: `GET /ui/biblioteca?etiquetas=tema:noir motivo:escuela -motivo:viajes`
   devuelve la rejilla con el mismo contrato HTMX de `_rejilla_biblioteca.html`; la consulta
   sale de `SeriesService`, no del router (CLAUDE §3.1). Referencias: Komga
   `SearchCondition.Tag` + `isNot` (`SeriesSearchHelper.kt:97`), Kavita `Must Not Contains`
   (wiki de filtros 0.9.1), e621 `-tag` y Hydrus `-tag`. **Contrato final (supera el ejemplo):**
   `?etiquetas=<expresión>` con `namespace:nombre`, AND por espacios y `-` para excluir; ver
   `especificacion-etiquetas.md` §7.2/§7.3 y `ui-etiquetas.md` §6.2.
2. **Autocompletado con conteo, tolerante a mayúsculas y tildes, ordenado por similitud y
   uso.** Mínimo: `GET /ui/biblioteca/etiquetas/sugerir?etiquetas=noi` → parcial HTML con ≤ 8
   resultados, cada uno con `namespace:name` y nº de series; consulta con `f_unaccent(lower(name))`,
   `%`/GIN trigram y `ORDER BY similarity(...) DESC, count DESC`. Referencias: Calibre-Web `#tags`
   Bloodhound (`edit_books.js`), Hydrus autocompletado con conteos, Komga tags en minúsculas.
   **Contrato final:** el parcial vive en `web/`, no en `/api` devolviendo HTML (spec §7.2).
3. **ComicInfo se lee de verdad.** Mínimo: al importar, `<Tags>` (coma) y `<Genre>` (coma)
   quedan guardados con procedencia (`comicinfo_xml`), `<Tags>` solo si existe; si el XML no
   se puede leer, no se toca nada (el contrato de `ComicInfoInvalidoError` ya existe).
   Referencias: Kavita (tabla de conversión ComicInfo), Komga (`ComicInfoProvider.kt:118,153`),
   Anansi `DOCUMENTATION.md` (`<Tags>`/`<Genre>`).
4. **Lo manual no se pisa.** Mínimo: una asignación `source=manual` (o `locked_fields`) no la
   modifica el enricher ni una regla; el mismo contrato que ya aplica
   `enricher.py:185,258-274,359,388-397`. Referencias: Kavita «locked fields + overrides»,
   Komga locks por campo, ZascArr H3.
5. **Unicidad normalizada.** Mínimo: no se crean dos etiquetas que solo difieren en
   mayúsculas/tildes (`Noir` = `noir` = `nóir` en el namespace `tema`); índice único sobre
   `(namespace, lower(f_unaccent(name)))` o columna generada. Referencias: Calibre-Web 0.6.27
   (fix de duplicados por mayúsculas), Komga (lowercase), Hydrus (normaliza espacios/underscore).

## 8. MEJORAR (huecos ordenados por oportunidad, con evidencia)

1. **Procedencia por asignación, no por fila.** Ninguna referencia combina
   `source`+`weight`+«manual gana» en la misma relación: Komga tiene locks por campo pero tags
   sin procedencia; Kavita+ mapea sin provenance por asignación; AniList da `rank` pero no
   dice quién lo escribió. ZascArr ya tiene `metadata_source` y `locked_fields`
   (`models:447-451`), así que añadir `source` (y `weight` nullable) a la relación es barato y
   es el habilitador de confianza para el coleccionista. **Criterio de «mejor»:** la UI puede
   explicar «este tag vino de ComicInfo el 2026-11-04» y el enricher no lo pisa.
2. **Coherencia serie/número explícita.** Los boorus etiquetan ficheros; Komga etiqueta serie
   y libro y agrega; Kavita filtra series sobre tags de fichero. ZascArr puede definir
   `series_tags` como contrato del filtro de biblioteca y dejar `issue_tags` para refinamiento
   por número, **sin agregar implícitamente** un tag de issue a la serie (evita «filtro
   fantasma»: una serie aparece por un número que el coleccionista no esperaba). Evidencia:
   la tabla `issue_tags` ya existe y `SeriesService` filtra series (`series.py:39-90`).
3. **Búsqueda en español insensible a tildes.** Hydrus/e621/Danbooru están en inglés y e621
   prohíbe explícitamente caracteres no ingleses en tags; Calibre-Web solo corrige
   mayúsculas. ZascArr tiene `unaccent`+`pg_trgm` desde 0006: `nóir`/`noir` y `escolar`/
   `escolà` deben encontrar lo mismo. **Criterio de «mejor»:** un test con «Nóir» y «NOIR»
   devuelve la misma serie.
4. **Ida y vuelta de ComicInfo con prueba de autoría.** Komga lee pero no escribe; Kavita
   escribe vía Kavita+; ComicTagger escribe `<Genre>` pero no `<Tags>`. ZascArr B6 ya tiene
   `file.metadata_["comicinfo_propio"]` y `solo_rellenar`/overlay: si algún día escribe
   `<Tags>`, puede demostrar que lo escribió él y no pisar lo ajeno. **Criterio:** el plan
   marca `conserva` un `<Tags>` desconocido, `cambia` solo si es propio o vacío.
5. **Padres/implicaciones con coste acotado.** Hydrus avisa de que calcular parents «consume
   CPU» y que son virtuales; en una Pi con 512 MiB no se materializa el cierre transitivo.
   Mejora: resolver 1–2 niveles en la consulta de filtro, con profundidad máxima y sin
   recalcular al pintar la ficha. **Criterio:** el filtro con un padre no supera el tiempo del
   filtro por personaje actual (medir en Pi; NOT RUN).
6. **Curación humana sin wiki.** e621/Danbooru necesitan janitors y wiki; Hydrus deja al
   usuario. ZascArr puede hacer «sugerir → confirmar» reutilizando el patrón de Pendientes
   (`hx-confirm` no sirve para la automatización, pero el usuario real sí; B2). **Criterio:**
   alias/padres nunca se crean solos; una regla propone y el coleccionista acepta.

## 9. Contradicciones con el repo (para la especificación)

| Lo que dice la propuesta | Lo que hay en el repo (35283b5) | Qué hacer |
|---|---|---|
| Ids `int` | PK **UUID en el dominio** (`models:499`, migración 0001; única excepción: el singleton `runtime_settings.id`, entero) | UUID; el anexo ya lo marca como error de transcripción |
| «Sería la migración 0010», repo 0001–0009 | Head **0020**; siguiente **0021**; 20 revisiones | 0021; no reescribir 0001–0020 |
| `Tag.name` único + `UniqueConstraint(namespace, name)` | `Tag.name` es **UNIQUE global** (`models:500`) | Migración: columna `namespace` y unicidad normalizada por `(namespace, name_norm)`; quitar el UNIQUE global |
| Tabla `serie_tag` (singular) | Existen `tags` (plural) e `issue_tags` (M:N a nivel de número); **no** hay `series_tags` ni `Series.tags` | Reutilizar `tags`; añadir `series_tags`; dejar `issue_tags` existente para fase 2 |
| «Etiquetar a nivel de serie por defecto» | La única tabla existente es `issue_tags`; el filtro de biblioteca es de serie (`SeriesService`) | Empezar por `series_tags`; no usar `issue_tags` como si fuera de serie |
| Namespaces `genero:`, `personaje:`, `formato:` | `Series.genres` (`Genre`), `Issue.characters` (`Character`), `Issue.format`/`FileFormat` existen y están dormidos | Poblar lo estructurado; namespaces libres solo para `tema`/`motivo`/`publico` (este último con decisión aparte) |
| `source` = manual/comicvine/anilist/tebeosfera/comicinfo/regla | `MetadataSource` = `comic_vine`, `gcd`, `anilist`, `tebeosfera`, `comicinfo_xml`, `manual` (`models:170-176`); no hay `regla` | Usar el enum y, si hace falta, añadir `regla`; `comicinfo` es `comicinfo_xml` |
| Procedencia «por campo» | `metadata_source` y `locked_fields` son **por fila** (`models:447-451`, H2/H3) | Si la spec quiere procedencia por asignación, es una columna nueva en `series_tags` (`source`), no un cambio de `metadata_source` |
| ComicInfo `<Tags>` y `<Genre>` como canal | Parser ignora `<Tags>` y lee `<Genre>` sin consumidor (`importer_triage.py:151-181`); B6 gestiona 7 campos (`comicinfo_write.py:36-38`); ComicTagger **no escribe `<Tags>`** | Leer `<Tags>`/`<Genre>` en importación; escribir `<Tags>` solo tras decidir contrato B6 (y no en v1) |
| `unaccent` reutilizable para tags | Existe `unaccent` y `f_unaccent` (0006:92-104), pero `f_title_norm` (0006:117) quita artículos/puntuación | Normalizar tags con `lower(f_unaccent(name))`; **no** usar `f_title_norm` |
| «integración opcional con Kavita baremetal» | Solo `scripts/kavita.sh`; B20 sin implementar | Descartar la integración como parte de esta historia; inscribirla en B20 |
| `AgeRating` como tag `publico:` | No hay `AgeRating` en `models/__init__.py` (aunque CLAUDE §2 lo menciona) | Decisión aparte: columna/atributo si el PO quiere edad; no un namespace de texto |
| El anexo remite a `docs/design/evaluacion-propuesta-etiquetas.md` | No existía al abrir esta ficha; al cerrarla sí existe (creado en paralelo, cita esta ficha) | Mantener el §2 de esta ficha como evidencia; si divergen, manda el código |
| «La migración siguiente es 0021» (dato del encargo) | Correcto | Se usa en la spec |

## 10. Barrera legal (§13) — se copian patrones, nunca código ni textos

| Referencia | Licencia | Qué se puede tomar | Qué NO |
|---|---|---|---|
| **Kapowarr** (c191dda) | GPL-3.0 | Ideas de flujo/estados (no aplican aquí: no tiene tags) | Código, textos, esquema literal |
| **Mylar3** (cdc94a4) | GPL-3.0 | Patrón de delegar el etiquetado en ComicTagger (histórico) | Código, plantillas, textos |
| **Kavita** (9e17770) | GPL-3.0 | Vocabulario de filtros (`Must Contains`/`Must Not Contains`) y conceptos de smart filter | Código C#, textos de la wiki, diseño de UI, taxonomía de Kavita+ |
| **Calibre-Web** (0.6.27) | GPL-3.0 | Idea de typeahead con endpoint y separación por comas | Código JS (Bloodhound), plantillas, textos |
| **Komga** (25c67d1) | **MIT** | Contrato de `SearchCondition`/operadores y modelo de locks | Código Kotlin, textos, UI |
| **Suwayomi** (v2.4.2366) | **MPL-2.0** (componentes Apache-2.0) | Solo el dato «género viene de la fuente» | Código, textos |
| **LANraragi** (0.9.81) | **MIT** | Sintaxis de búsqueda (comas = AND, `-` exclusión, `$` exacto) | Código Perl, textos |
| **Hydrus** (v694a) | **WTFPL** | Patrón namespaces/siblings/parents y comportamiento de autocompletado | Código Python, textos/docs, UI |
| **ComicTagger** (fa11a34/1.5.5) | **Apache-2.0** | Contrato de campos ComicInfo y `--no-overwrite` | Código, textos |
| **Danbooru** (e8af67d) | **BSD-2** (texto del repo; GitHub NOASSERTION) | Modelo de alias/implication y validaciones (patrón) | Código Ruby, su wiki/taxonomía de tags |
| **e621** (26.11.04-fix.1) | [licencia de código sin verificar] | Patrón de categorías y búsqueda AND/OR/exclusión | Código, textos, su folksonomía |
| **Gelbooru** (wiki v23) | [sin verificar] | Sintaxis AND/exclusión/OR (`howto:cheatsheet`) | Código, textos |
| **AniList API** (docs 03281c0) | — | Contrato `MediaTag.rank`/`isAdult` | — |

**Regla operativa:** ningún fragmento de código, CSS, texto de UI, icono o nombre de
producto de las referencias entra en ZascArr. Los nombres de campos (`namespace`, `alias`,
`parent`, `source`, `weight`) son vocabulario técnico común, no copia de implementación. La
taxonomía concreta (qué tags existen, qué implica qué) **no se copia de e621/Danbooru**: se
cura localmente con el coleccionista. ZascArr es GPL-3.0 (`LICENSE`); la ficha no cambia la
licencia.

## 11. NOT RUN, casos de prueba y caducidad

**NOT RUN (no ejecutado, no inferido):** no se consultó la BD real (no hay `SELECT COUNT(*)`
de `tags`/`issue_tags`/`genres`; por construcción el código no escribe filas, pero no se
midió); no se ejecutó ninguna migración; no se midió el coste en Pi de trigram/recursive CTE;
no se levantó Kavita, Calibre-Web, Hydrus ni LANraragi para probar la UI; la web de Danbooru
estaba **caída por mantenimiento** el 2026-11-04 (su contrato se leyó en el código); la
licencia del código de e621/Gelbooru no se comprobó; el `.cs` de `SeriesMetadata` de Kavita
no se localizó (se usó la documentación de contrato y el `openapi.json` del repo).

**Casos de prueba antes de implementar** (para la especificación, no implementados):

1. Importar un CBZ con `<Tags>dark, Occult</Tags>` y `<Genre>Horror</Genre>`: se crean
   `tema:dark`, `tema:occult` (o los nombres que decida la spec) con `source=comicinfo`; la
   segunda importación no duplica.
2. Un CBZ sin `<Tags>` no crea nada y no falla; un XML roto sigue el contrato
   `ComicInfoInvalidoError` (no se toca).
3. Filtro `tema:noir -publico:adulto` devuelve series con noir y sin adulto; el conteo de
   facetas coincide con el total paginado.
4. `Noir`, `noir` y `nóir` resuelven a la misma etiqueta (unicidad normalizada).
5. El enricher añade un tag con `source=comicvine`; una asignación manual con
   `source=manual` sobrevive a la siguiente pasada del enricher.

**Caducidad:** 2027-01-03. Antes hay que revisar si cambia la historia, Kavita/Komga o el
modelo; si no hay decisión del PO, esta ficha no autoriza implementar (es insumo, no
aprobación).
