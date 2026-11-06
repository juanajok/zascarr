# Evaluación de encaje — propuesta externa de etiquetas (2026-11-04)

> **Qué es este documento.** Evaluación del Lead sobre la propuesta externa de
> etiquetas (`docs/design/propuesta-externa-etiquetas.md`) contra el código
> vigente de ZascArr (`35283b5`) y las referencias open source. No es la
> especificación: esta vive en `docs/design/especificacion-etiquetas.md`, y la
> evidencia del benchmark en `docs/design/benchmark-etiquetas.md`.
>
> **Veredicto de encaje: ADAPTAR, no adoptar literalmente.** La intención de
> producto es buena y el stack la soporta; el modelo propuesto, tal cual, choca
> con cinco realidades del repo (detalle en §2). El camino barato y honesto es
> un MVP pequeño a nivel de serie que reutiliza lo que ya existe, y dejar
> alias/padres/enriquecimiento/ComicInfo-export para fases posteriores.
>
> **Contraste ya cerrado (2026-11-04):** `docs/design/benchmark-etiquetas.md`
> puntúa 4,35/5 la opción «construir sobre lo propio» frente a 3,05 de la
> propuesta literal, 3,00 del statu quo y 2,40 del booru completo, y recomienda
> exactamente esta dirección: reutilizar `tags`/`issue_tags`, añadir
> `series_tags`, poblar `Series.genres`/`Issue.characters` y leer `<Tags>` de
> ComicInfo antes de escribir nada. La revisión de seguridad da el MVP por
> **APTO CON CONDICIONES** y bloquea el export a ComicInfo hasta extender el
> contrato B6 (§11).

## 1. Qué propone, en una frase

Un sistema de etiquetas libres con **namespace** (`genero:`, `tema:`,
`personaje:`, `universo:`, `publico:`, `formato:`), **alias** (sinónimos),
**padres/implicaciones** (batman → dc), **procedencia y peso** por asignación
(`source`, `weight` 0-100), importación de `<Tags>` de ComicInfo, mappers del
enricher por fuente y UI HTMX tipo booru (autocompletado, chips AND/exclusión,
facet counts) con exportación a ComicInfo para que Kavita lo lea.

## 2. Las cinco contradicciones duras con el repo

| # | La propuesta dice | El repo dice (verificado) | Consecuencia |
|---|---|---|---|
| 1 | «Una migración más, la 0010» | El head de Alembic es **0020** (`alembic/versions/2026020...`; `alembic heads` → `0020 (head)`). La 0001–0009 es historia antigua. | La migración nueva es la **0021** y encadena `down_revision="0020"`. |
| 2 | Ids `int` en cuatro tablas nuevas | **Todos los PK del dominio son UUID** (`models/__init__.py`: Series, Issue, Tag…), con `default=uuid4`; los ids de proveedor son `BigInteger` en columnas paralelas. | `tag_id`/`series_id` son `UUID(as_uuid=True)`; nada de `int`. |
| 3 | Tabla nueva `tag` (singular) y `serie_tag` | **`tags` (plural) e `issue_tags` ya existen desde la migración 0001** (`20260301_0001_initial_schema.py:159-166`), y `Tag` ya está en el modelo (`models/__init__.py:497-501`) con `name` único y `color`. Están **dormidas**: ningún servicio, router, test ni plantilla las usa. | No se crea `tag`: se **extiende `tags`** y se decide qué hacer con `issue_tags` (ver §4). Renombrar tablas existentes rompe la regla de migraciones one-shot y no aporta nada. |
| 4 | `SerieTag` a nivel de serie | El modelo existente ata etiquetas a **`Issue`** (`Issue.tags`, `issue_tags`), y no hay `Series.tags`. La propuesta recomienda serie-level primero. | Hay que **elegir y documentar**: o se añade `series_tags` y se deja `issue_tags` para después, o se reutiliza `issue_tags` (peor: los filtros de biblioteca y los recuentos tendrían que agregar por número). Recomendación: `series_tags` en el MVP; `issue_tags` queda declarado como no usado (no se borra sin decisión). |
| 5 | `<Tags>` de ComicInfo: «hay un util donde enchufarlo» | `CAMPOS_GESTIONADOS` solo tiene **7 campos** (`core/comicinfo_write.py:35-38`: Series, Number, Volume, Year, Publisher, Summary, LanguageISO). El parser de triaje **ignora `<Tags>`** (`core/importer_triage.py:113-190`) y el escritor **preserva cualquier XML desconocido** sin gestionarlo. | No es un enchufe: leer `<Tags>` es trabajo nuevo en el parser/triaje; escribir `<Tags>` exige ampliar el contrato B6 (plan, procedencia, `solo_rellenar`, tests, manifiesto) y decidir qué formato se escribe. No entra en el MVP. |

## 3. Lo que la propuesta acierta (y conviene conservar)

- **Separar identidad de descriptor.** Tradición, editorial, año, número, saga,
  autoría y formato son columnas/relaciones; las etiquetas son descriptores
  flexibles. Es la regla correcta y coincide con «JSONB para metadata suelta»
  (CLAUDE §12) sin sustituirlo.
- **Namespaces en español sin acentos** para la UI. Bien para El Coleccionista;
  el identificador interno puede ser estable y el rótulo humano aparte.
- **Alias e implicaciones como mecanismos distintos.** Es el patrón que evita
  que «super-man» y «superman» fragmenten el catálogo. Hydrus lo llama
  siblings/parents; los boorus, aliases/implications. La propuesta los acierta.
- **Procedencia y peso por asignación.** El repo ya tiene procedencia por fila
  (`metadata_source`) y protección por campo (`locked_fields`), y B6 tiene un
  contrato de autoría (`metadata_["comicinfo_propio"]`). Extender ese patrón a
  la relación serie↔etiqueta es coherente; inventar otro sistema de procedencia
  no.
- **Búsqueda con AND/exclusión y facet counts.** Es el patrón booru; encaja con
  HTMX y con la barra de filtros que ya existe en `/ui/biblioteca`.
- **Roadmap por fases.** Coincide con la realidad: alias/padres/reglas al final,
  no en el MVP.

## 4. Evaluación elemento por elemento

### 4.1 Namespaces: 4 de los 6 propuestos duplican entidades que ya existen

| Namespace propuesto | ¿Ya hay algo? | Veredicto |
|---|---|---|
| `genero:` | Tabla `genres` + `Series.genres` (M:N) **dormidas**, sin uso desde 0001. | **No crear un namespace paralelo.** O se puebla `genres` (trabajo aparte) o se expone como etiqueta derivada; almacenar lo mismo dos veces es la peor opción. |
| `personaje:` | Tabla `characters` + `Issue.characters` (M:N) **dormidas**. | Igual: no duplicar. Si el PO quiere `personaje:` en la UI, se puede **derivar** el facet de la relación sin almacenar un tag paralelo. |
| `universo:` | Tabla `universes` + `StoryArc.universe_id`, `Character.universe_id`. | Ya es estructura, no tag. Descartar como namespace de tag. |
| `formato:` | `IssueFormat` (enum) + `Files.file_format`; `Series` no tiene formato propio. | Ya es estructura. Descartar como namespace de tag. |
| `tema:` / `motivo:` | Nada equivalente. | **Aquí sí** tiene sentido una etiqueta libre. Es el namespace del MVP. |
| `publico:` | Nada equivalente (no hay `AgeRating` en el modelo, aunque CLAUDE §2 lo mencione; ComicInfo sí tiene `<AgeRating>`). | **Decisión aparte, no MVP.** Si el PO quiere edad, lo correcto es un atributo estructurado (columna/`AgeRating`), no un namespace de texto libre. |

Conclusión: el MVP debe empezar con **un namespace de tag** (`tema`/`motivo`,
más una etiqueta libre si el PO la pide); `genero`, `personaje`, `universo`,
`formato` y `publico` se resuelven poblando/exponiendo lo que ya existe o con
una decisión de producto aparte, no creando tags paralelos. Si el PO insiste en
la taxonomía completa de 6 namespaces, la decisión es «migramos
`genres`/`characters` a tags» o «conviven y asumimos el riesgo de divergencia»
— y eso es una historia aparte, no el MVP.

**Riesgo alto si no se decide:** dos fuentes de verdad para «género» (tabla
`genres` y tag `genero:`) que se desincronizan en cuanto una fuente externa
actualice una y no la otra. El coleccionista vería filtros que no cuadran.

### 4.2 Alias

- La propuesta acierta en tener tabla de alias separada.
- El repo ya tiene un precedente exacto: `local_aliases` (migración 0012) para
  series, con `pattern_norm` y normalización única (`core.matcher.normalize_title`).
- **No reutilizar `f_title_norm` para etiquetas**: esa función quita artículos
  iniciales y pospuestos («the», «la», «el»…) porque está pensada para títulos
  de serie. Una etiqueta «The Walking Dead» quedaría «walking dead»; una
  etiqueta «La» quedaría vacía. Hace falta un `f_tag_norm` propio (lower +
  `f_unaccent` + puntuación→espacio + colapsar), con su test de paridad
  Python/SQL como `tests/test_title_norm.py`.
- Reglas que la especificación debe fijar: un alias no puede coincidir con el
  nombre canónico de otra etiqueta del mismo namespace; alias único por
  namespace; si dos alias apuntan a tags distintos, error explícito, no fusión
  silenciosa; quién crea alias (manual o enricher) y con qué procedencia.
- **No entra en el MVP**: sin alias, el usuario puede corregir el nombre; con
  alias mal puestos, se fusionan etiquetas ajenas. La propuesta lo pone en fase
  4 y es correcto.

### 4.3 Padres / implicaciones

- El nombre «padres» es ambiguo: en Hydrus, *parent* = implicación (buscar el
  padre incluye a los hijos) y *sibling* = alias. La propuesta mezcla ambos en
  «alias y padres son el mecanismo de siblings/implications». La especificación
  debe separar **alias** (misma etiqueta) e **implicación** (A implica B).
- Coste real: consultas recursivas (CTE) o tabla de cierre; en una Pi compartida
  hay que acotar profundidad, impedir ciclos y decidir si la implicación se
  aplica al filtrar, al mostrar o al exportar. Es la parte más cara del sistema
  para el beneficio más tardío.
- **No entra en el MVP.** Fase 4, después de que el uso real diga si hacen
  falta.

### 4.4 `source` y `weight`

- `source`: el repo ya tiene el enum `MetadataSource` (`models/__init__.py:170`)
  con `comic_vine`, `gcd`, `anilist`, `tebeosfera`, `comicinfo_xml`, `manual`.
  La propuesta añade `regla`; si se acepta, se añade al enum (nunca un string
  libre con valores inventados). **Un solo enum**, no dos vocabularios.
- `weight`: la propuesta mezcla dos conceptos distintos:
  1. **relevancia** (el `rank` 0-100 de AniList),
  2. **confianza/procedencia** (manual vs fuente).
  Deben ser columnas separadas o, mejor, `weight` solo como orden/relevancia y
  `source` como procedencia. Un `weight` que signifique dos cosas no se puede
  ordenar ni auditar.
- **Procedencia por asignación**: `series_tags` necesita `source`, `weight`,
  `created_at`, `updated_at`; y una regla de precedencia explícita, la misma del
  enricher: `manual` nunca se pisa; una fuente no pisa a otra de mayor
  prioridad; volver a enriquecer es idempotente. Si se guarda una fila por
  (serie, etiqueta, fuente) se puede auditar pero las facetas agregan más; si se
  guarda una sola fila por (serie, etiqueta) se pierde la evidencia. **Decisión
  de la especificación**, no del MVP apresurado. Recomendación: una fila por
  (serie, etiqueta) con `source` de la última escritura y `weight` máximo
  observado, y registrar el detalle en `metadata_` si hace falta auditar.
- **`locked_fields`**: en el repo protege campos de `Series`/`Issue`/`Creator`/
  `Character`. Para tags, la forma barata es que `source='manual'` sea el lock
  (el enricher no toca filas manuales), como ya hace la query del enricher con
  `metadata_source != manual`.

### 4.5 ComicInfo

- **Leer `<Tags>`**: el parser actual (`parse_comic_info`) solo mapea Series,
  Number, Publisher, Summary, Genre, LanguageISO, Volume, Year, PageCount y
  créditos. Añadir `<Tags>` implica: lista separada por comas, tope de tamaño
  (ya hay `MAX_COMICINFO_BYTES = 1 MiB`), limpieza de espacios, Unicode, y
  procedencia `comicinfo_xml`. Es barato y buen candidato a **fase 2 (solo
  lectura)**, sin escribir nada.
- **Escribir `<Tags>`**: no es barato. B6 tiene un contrato cerrado (plan único,
  precedencia por procedencia, `solo_rellenar`, plan caduco, manifiesto de
  hashes, temporal hermano, `fsync`, reconciliación del SHA256, CBR intacto).
  Ampliar `CAMPOS_GESTIONADOS` con `Tags` obliga a: decidir si se escribe lista
  plana o `namespace:name`; decidir qué etiquetas se exportan (¿todas? ¿solo
  `source=manual`?); preservar el `<Tags>` ajeno; probar la fusión; y actualizar
  el CLI y la previsualización. **Fase 4 como muy pronto.**
- **No confundir campos**: ComicInfo tiene `Genre`, `Characters`, `Teams`,
  `Locations`, `StoryArc`. Si se exportan etiquetas a `<Tags>`, no se duplican
  en `Genre`/`Characters` sin una decisión explícita. Y si se pueblan
  `genres`/`characters` en ZascArr, el export natural sería a sus campos
  homónimos, no a `<Tags>`.
- **Kavita**: `scripts/kavita.sh` instala Kavita baremetal; **no hay export de
  ComicInfo desde ZascArr** (B6 escribe 7 campos; B20 planifica export de
  árbol de carpetas). El cierre de círculo «Kavita lee mis tags» es alcanzable,
  pero hoy no existe la integración que la propuesta sugiere.

### 4.6 Enricher

La propuesta asume que el enricher ya trae géneros/personajes/tags de las
fuentes. **Hoy no lo hace**:

- `ComicVineClient.search_series` pide `id,name,description,image,start_year,
  count_of_issues,site_detail_url`; no pide `genres` ni `characters`
  (`services/comic_vine.py:130-145`).
- `ComicVineClient.find_issue` solo pide `person_credits`; no
  `character_credits`/`story_arc_credits` (`services/comic_vine.py:191-203`).
- `AniListClient` pide título, descripción, portada, año, capítulos y volúmenes;
  **no** pide `tags`, `genres`, `isAdult` ni `rank` (`services/anilist.py:43-55`).
- `TebeosferaClient` devuelve slug, título, tipo, año, nº de números, portada y
  descripción; **no** género/argumento (`services/tebeosfera.py:100-109`).
- El enricher aplica a la serie: id de fuente, descripción, portada,
  `total_issues`, `metadata_source`; a los issues: id de CV, sinopsis, portada,
  créditos. No toca `Series.genres` ni `Issue.characters`
  (`services/enricher.py:258-400`).

Por tanto, el pipeline propuesto es **trabajo nuevo en los clientes + enricher +
tests + presupuesto de rate limit**, no un cableado. Además, cada fuente tiene
un límite de cortesía (Tebeosfera 2,5 s compartido) y una caché negativa de 30
días (`enrichment_attempted_at`); añadir tags multiplica llamadas si no se
aprovecha la misma respuesta. **Fase 3**, y solo para los namespaces que
sobrevivan a la decisión de §4.1. Para `genero`/`personaje` lo correcto sería
poblar `genres`/`characters` existentes, no tags.

### 4.7 UI HTMX

Encaja bien; el repo ya tiene casi todas las piezas:

- `/ui/biblioteca` ya es una barra de filtros que hace `hx-get` a
  `/ui/biblioteca/resultados` con `hx-target="#rejilla"`, `hx-push-url="true"` y
  debounce de 400 ms para personaje/saga (`web/library.py`,
  `templates/biblioteca.html`). Añadir tags es extender ese patrón, no inventar
  otro.
- `ui.chip` ya existe (`templates/_componentes.html:9`) con estados
  neutro/ok/warn/amber/info. Los chips de etiqueta deben ser **otro uso** del
  mismo componente, no CSS nuevo.
- La ficha de serie ya pinta `series.genres` como texto
  (`templates/series_detail.html:12-14`); el bloque de etiquetas debe ir ahí,
  con edición inline por `hx-post`, y el mismo patrón de `Form(...)` explícito y
  lista blanca que `_politica_serie.html`.
- **Ruta**: la propuesta propone `/api/etiquetas/sugerir` devolviendo HTML. En
  el repo, `api/` es JSON y `web/` es HTML/HTMX (`CLAUDE.md` §3.1). El parcial
  de sugerencias debe vivir en `web/` (p. ej.
  `/ui/biblioteca/etiquetas/sugerir`) o, si se quiere JSON, en
  `/api/etiquetas/sugerir` y que HTMX pinte con una plantilla; no mezclar.
- **Sintaxis booru**: chips y parámetros explícitos (`tag=`, `sin_tag=`) para el
  usuario; la sintaxis `-tema:escuela` puede quedar como atajo avanzado, nunca
  como único camino. El Coleccionista no debería aprender sintaxis.
- **Facet counts**: una consulta agregada por faceta, con límite y cacheada por
  petición; nunca una consulta por etiqueta. En Pi, con miles de series, el
  índice compuesto y el `LIMIT` importan más que la vista materializada.
- **Netflix**: la metáfora útil es «navegar por facetas», no un motor de
  recomendación. No prometer «más como esto» ni filas personalizadas en esta
  historia.

## 5. Contraste con open source (resumen; detalle en benchmark)

Los proyectos que inspiran la propuesta no tienen el mismo modelo:

| Proyecto | Lo que aporta | Lo que no conviene copiar |
|---|---|---|
| **Komga** 1.29.2 (Kotlin, MIT) | Metadatos de serie con géneros, tags, editorial, age rating; `SearchCondition`/`isNot`; `ComicInfoProvider` lee `<Tags>`/`<Genre>`. | Stack JVM pesado para la Pi; su modelo de tags es plano (sin namespaces/alias/padres). |
| **Kavita** 0.9.1 (.NET) | Tags/géneros, filtros AND/OR con `Must Contains`/`Must Not Contains`, age rating; lee ComicInfo. | El mapper genres↔tags y el age mapping viven en **Kavita+** (suscripción), no en el escáner base; su modelo no es booru. |
| **Kapowarr** 1.3.2 (Python, GPL-3.0) | Enriquecimiento Comic Vine, ediciones, ficheros; el patrón de metadatos del repo ya lo sigue. | No tiene sistema de tags de usuario comparable; no copiar código (GPL). |
| **Mylar3** (Python, GPL-3.0) | Búsqueda/gestión de cómics, metadatos; delegó el etiquetado en ComicTagger. | Su modelo de tags no es namespaced; no copiar código. |
| **Suwayomi** (MPL-2.0) | Capítulos/fuentes/lectura. | No es un catálogo de tebeos con tags; su «categoría» no es un tag. |
| **LANraragi** 0.9.81 | Tags tipo booru (namespaces `artist:`, `female:`…), búsqueda AND/exclusión, metadatos de archivo. | Es un lector de archivos, no un gestor de colección; su modelo es más simple. |
| **Hydrus** v694a | Siblings (alias), parents (implicaciones), namespaces, búsqueda potente. | Escritorio, modelo y UI muy distintos; copiar solo el **concepto**, no el diseño. |
| **Calibre-Web** 0.6.27 | Typeahead real (`#tags` → `/get_tags_json`), filtros. | No es cómic; su modelo no tiene namespaces. |
| **ComicTagger** | Lectura/escritura de ComicInfo, pero **no escribe `<Tags>`** (sí `<Genre>`). | No es un servidor; su contrato de escritura es más laxo que B6. |
| **Boorus** (Danbooru/e621/Gelbooru) | Namespaces, aliases, implications, búsqueda AND/exclusión. | Son bases de imágenes, no de tebeos; sus namespaces no trasladan 1:1. Danbooru estaba caído en la consulta; su contrato se leyó por código. |

**Conclusión del contraste:** nadie en el espacio «gestor de tebeoteca
self-hosted» tiene exactamente el modelo de la propuesta; los que más se
acercan (Kavita/Komga) usan tags planos y filtros, y los que tienen namespaces
(Hydrus, LANraragi, boorus) no gestionan una colección de tebeos con huecos,
wishlist e importador. ZascArr no debe «igualar» a todos: debe coger el patrón
de búsqueda booru (que sí aporta) y **no** duplicar identidad editorial que ya
tiene modelada.

## 6. Fases recomendadas (y qué es el MVP)

| Fase | Contenido | Por qué |
|---|---|---|
| **0. Esta historia** | Benchmark + especificación + decisiones de PO. Sin código. | Evitar construir la taxonomía equivocada. |
| **1a. MVP manual** | Migración 0021: extender `tags` (namespace, `name_norm` generado, color por namespace), `series_tags` con `source`/`weight`, `f_tag_norm` + GIN trigram; servicio de etiquetas; edición manual en ficha de serie; filtro por etiqueta en biblioteca con AND/exclusión; autocompletado HTMX; tests (FakeSession + Postgres real para trigram). Namespaces iniciales: `tema`/`motivo` (+ `etiqueta` libre si el PO lo pide). | Da búsqueda usable y valida el modelo con uso real, sin tocar fuentes ni ComicInfo. |
| **1b. ComicInfo de lectura** | Leer `<Tags>` y `<Genre>` en el triaje/importador, con `source=comicinfo_xml` y procedencia; **sin escribir**. | Barato, aporta datos ya presentes en los CBZ; el parser tiene tope y XXE cubiertos. |
| **2. Identidad estructurada** | Poblar `Series.genres` e `Issue.characters` (dormidos) desde los clientes, en vez de crear tags `genero:`/`personaje:`. Requiere ampliar `field_list` de CV/AniList/Tebeosfera y decidir precedencia. | Es más barato completar lo que ya existe que duplicarlo; evita dos verdades. |
| **3. Enriquecimiento de tags** | Mapear solo los namespaces que sobrevivan (`tema`/`motivo`), con `weight` real (AniList `rank`) y caché negativa. | Es donde está el coste real y donde la propuesta asume cosas que el código no hace. |
| **4. Taxonomía y export** | Alias, implicaciones, reglas, smart filters guardados; export a `<Tags>` de ComicInfo ampliando el contrato B6; Kavita (B20). | Lo más caro y lo menos urgente; solo si el uso lo pide. |

## 7. Riesgos principales

1. **Duplicidad de fuente de verdad** (§4.1) — el mayor. Si `genres`/`characters`
   quedan dormidos y a la vez se crean tags `genero:`/`personaje:`, el catálogo
   miente.
2. **Alcance**: la propuesta son 4 fases y toca modelo, migración, enricher,
   importer, ComicInfo, UI y tests. Una sola historia «sistema de etiquetas» no
   es una PR; hay que partirla.
3. **Rendimiento en Pi**: facetas + intersecciones + padres recursivos. Sin
   índices y límites, una biblioteca de miles de series castiga. Medir con
   datos reales antes de prometer.
4. **Procedencia**: si el enricher pisa etiquetas manuales, el usuario pierde
   su trabajo; si no las pisa nunca, no se actualizan. Hay que fijar la
   precedencia (la del enricher ya existe y es reutilizable).
5. **Calidad de datos**: los tags de fuentes vienen en inglés, con alias y
   pesos distintos; `weight` no es confianza. Sin decisión de idioma y de
   normalización, el catálogo se fragmenta.
6. **ComicInfo**: escribir `<Tags>` sin respetar B6 puede corromper CBZ o pisar
   datos de terceros. No hacerlo hasta tener el contrato extendido y probado.
7. **Legal**: etiquetas derivadas de fuentes con licencias/cortesía distintas;
   uso privado, sin redistribución; Tebeosfera mantiene su espaciado compartido.

## 8. Decisiones que debe tomar el PO antes de implementar el MVP

1. ¿Tags solo a nivel de **serie** en el MVP, o también de número? (Recomendación:
   serie.)
2. ¿Qué namespaces entran en el MVP? (Recomendación: `tema`/`motivo` y una etiqueta libre
   si se quiere; `publico` es decisión aparte y probablemente una columna estructurada, no
   un tag; `genero`/`personaje`/`universo`/`formato` se resuelven con lo existente.)
3. ¿Se pueblan `Series.genres`/`Issue.characters` (dormidos) como historia
   aparte, o se dejan dormidos y se usan tags? (No hacer las dos cosas.)
4. ¿Idioma de las etiquetas: español, idioma de la fuente o ambos con alias?
5. ¿Se exportan etiquetas a ComicInfo/Kavita en el MVP? (Recomendación: no;
   fase 4.)
6. ¿Quién puede crear/editar etiquetas? (Hoy no hay multiusuario; el
   coleccionista único.)
7. ¿Se aceptan etiquetas de fuentes externas automáticamente o solo se
   proponen para que el humano confirme? (El repo prefiere proponer antes que
   afirmar: B12, ADR 0008.)

## 9. Qué deja esta evaluación para la especificación

- Un MVP acotado (fase 1) con criterios verificables.
- Cinco contradicciones resueltas con el repo (UUID, 0021, tags/issue_tags,
  series vs issue, ComicInfo).
- La separación `source` (procedencia) vs `weight` (relevancia).
- La regla de no duplicar `genres`/`characters`/`universes`/`IssueFormat`.
- El contrato de lectura/escritura de ComicInfo por fases.
- La lista de referencias y el veredicto de qué adoptar de cada una.
- Las preguntas de PO que no puede decidir el equipo técnico.

## 10. Evidencia y artefactos

- Propuesta original: `docs/design/propuesta-externa-etiquetas.md`.
- Benchmark verificado: `docs/design/benchmark-etiquetas.md`.
- Especificación: `docs/design/especificacion-etiquetas.md`.
- Diseño UI: `docs/design/ui-etiquetas.md` + `docs/design/maqueta-etiquetas.html`.
- Tarjeta del kanban: **Feature #402** (`[BL-ETQ] Etiquetas para buscar y catalogar mi tebeoteca`) e
  **historia #403** (`[BL-ETQ1] Etiquetas por serie: añadir, quitar, filtrar (AND/exclusión) y
  autocompletar`), enlazadas desde `docs/BACKLOG.md` (Épica ETQ).
- Código citado: `src/zascarr/models/__init__.py`, `alembic/versions/20260301_0001_initial_schema.py`,
  `core/comicinfo_write.py`, `core/importer_triage.py`, `services/enricher.py`,
  `services/comic_vine.py`, `services/anilist.py`, `services/tebeosfera.py`,
  `web/library.py`, `templates/biblioteca.html`, `templates/series_detail.html`,
  `templates/_componentes.html`, `scripts/kavita.sh`.

## 11. Condiciones de seguridad y legal (SENTINEL.sec, 2026-11-04)

Dictamen completo: APTO CON CONDICIONES para el MVP manual; **NO APTO** para el export a
ComicInfo mientras no se extienda el contrato B6. Hallazgos que la especificación debe
incorporar como criterios, no como consejos:

- **ALTO — volumen al importar `<Tags>`**: un `<Tags>` de hasta 1 MiB puede contener cientos
  de miles de tokens y el importador corre en el ciclo automático sobre releases de terceros.
  Hacen falta topes por fichero, por etiqueta y totales, con aviso y sin abortar el ciclo.
- **MEDIO — contrato del fragmento HTML**: autoescape de Jinja ya protege texto y atributos,
  pero debe prohibirse el nombre de etiqueta en `hx-vals`/`hx-get`/`class`/`id`/`style`,
  `|safe`/`Markup`, y construir URLs con `urlencode`; namespace→clase por mapa de enum, nunca
  el namespace crudo a `ui.chip` (hoy lanza `ValueError` con estados desconocidos).
- **MEDIO — validación/normalización única**: nombre/alias ≤64, sin comas, saltos ni
  caracteres de control; NFKC + lower + `f_unaccent`; `name_norm` generado y
  `UNIQUE(namespace, name_norm)`; enum/`CHECK` de namespace; `f_tag_norm` con test de
  paridad Python/SQL (`f_title_norm` no vale).
- **MEDIO — endpoint y mass assignment**: `Form(...)` explícito o Pydantic `extra="forbid"`;
  el servidor fija `source='manual'` y `weight`; prohibido `Model(**data)`/`setattr`.
- **MEDIO — alias/padres**: alias único global normalizado; sin ciclos ni autoimplicación;
  fusión solo manual, confirmada y auditada; nunca automática desde fuentes.
- **MEDIO — rendimiento**: autocompletado con `q` acotado (2..64), `%`/GIN y `LIMIT`;
  facetas en una sola consulta con índice explícito por `tag_id`; filtros con
  `EXISTS`/`NOT EXISTS` (no JOIN+DISTINCT); sin N+1 en ficha/listado ni en el tagger.
- **MEDIO — ComicInfo/B6 (fase 4)**: serialización canónica ordenada/deduplicada, comparación
  por conjuntos, `Tags` fuera de `comicinfo_propio` (o solo hash), tope del XML de salida,
  política de qué `source` se exporta, tests de ida/vuelta y de caracteres especiales.
  `ElementTree` escapa `& < >`, pero los caracteres de control producen XML inválido.
- **BAJO — privacidad/documentación**: nada de texto de etiqueta/filtro en `structlog` ni en
  errores; `no-store` en el parcial de sugerencias; actualizar `SECURITY.md` (regla de
  `|safe` y la frase del segundo uso en `_asignacion_aviso.html`).
- **Legal**: fuentes detrás de sus toggles y rate limits; Tebeosfera con su espaciado
  compartido; política de export por `source` (manual/regla sí; fuentes externas, decisión y
  aviso) y cláusula en `LEGAL.md`; **ninguna** puerta legal ni middleware global nuevos.
- **Superficie/BD**: migración 0021 one-shot con `downgrade`; sin extensiones ni permisos
  nuevos (`pg_trgm`/`unaccent` ya están); sin dependencias nuevas; sin cambiar middleware/CORS;
  endpoints mutables solo `POST` bajo `/ui` con `Form(...)`.
