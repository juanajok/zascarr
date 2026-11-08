# Benchmark — modelo de datos de Comic Vine y GCD (qué se puede deducir y qué no)

> **Ficha de benchmarking (nivel 2)** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Pregunta del PO (2026-11-08):** ¿se puede deducir el modelo de datos de Comic Vine y GCD
> desde otros proyectos de benchmark en GitHub?
> **Respuesta corta:** **sí para el esquema, no para la cobertura.** Los clientes públicos
> enseñan qué campos existen, cómo se relacionan y cómo se pagina; **no** hay ningún campo de
> país/idioma en Comic Vine que copiar, y GCD solo resuelve la edición española cuando está
> catalogada. **El problema medido no es el esquema: es la selección de candidato.**
> **Fecha:** 2026-11-08. **Base contrastada:** `origin/main` `2f1621e`.
> **Autor:** SCOUT.bench. **Insumo, no aprobación:** decide el PO.

## 0. Resumen para el PO (seis líneas)

1. **El esquema se deduce y está claro.** GCD modela `series` (con `country` y `language` como
   claves foráneas) e `issue` (con `variant_of`); Comic Vine modela `volume`/`issue`/`publisher`
   **sin país, sin idioma y sin formato**. Los cuatro clientes leídos lo confirman.
2. **Ninguna referencia resuelve la edición española con Comic Vine.** Kapowarr solo marca
   «traducido» con una expresión regular sobre la sinopsis y filtra a inglés; Mylar3,
   ComicTagger y OdinsList no tienen el concepto de país/idioma para CV.
3. **La cobertura de GCD no era «escasa»: era «primera página».** GCD **sí pagina**
   (`?page=N`, 50 por página) y al mirar la página 2 aparece la edición del corpus:
   *Dragon Ball. Ultimate Edition*, **Planeta DeAgostini, 2006** (serie GCD `country=es`).
4. **ZascArr pierde candidatos en su propio cliente:** `services/gcd.py` recorta a `limit`
   antes de filtrar `country == "es"` y nunca pide la página 2; Comic Vine pide `limit=10` y
   no pagina. Es un arreglo de selección, no de modelo.
5. **Reglas propuestas:** paginar GCD con filtro ES y tope (o usar su filtro de año), filtrar
   antes de recortar, y ordenar con señales que la fuente sí tiene (título, año ±1, editorial,
   país/idioma cuando exista, recuento). Sin campo inventado: lo ausente se declara ausente.
6. **Límite duro:** GCD anónima son **30 peticiones/hora** (ajuste del servidor; se observó
   `429` con `Retry-After: 2385 s`). Paginar hay que presupuestarlo y cachearlo; Comic Vine no
   puede acreditar por sí sola que un volumen sea la edición ES (no tiene país ni idioma).

## 1. Problema local y qué se midió antes

**Historia de origen.** #135 (banco de cobertura) midió **0/12** ediciones españolas
(`docs/design/piloto-cobertura-2026-11-06.md` §3). La ficha `benchmark-BL-FU2-detalle-edicion.md`
concluyó que lo que faltaba era **detalle de edición** y que GCD tenía «cobertura escasa».
Las dos conclusiones se matizan aquí: falta **detalle**, sí, pero sobre todo falta **selección**
—páginas y orden— tanto en GCD como en Comic Vine.

> Nota de lectura: `piloto-cobertura-2026-11-06.md` termina en **§7** (no tiene §8). Lo
> pertinente para esta pregunta es §3 (0/12 y qué se probó) y §7 (límites del piloto).

### 1.1 Lo que hace hoy ZascArr (verificado en `2f1621e`)

- **Comic Vine**: `search_series` pide `id,name,description,image,start_year,count_of_issues,site_detail_url`
  y por defecto `limit=10` (`src/zascarr/services/comic_vine.py:145-158`). No hay paginación ni
  `publisher` en la búsqueda, aunque el detalle ya lo pide (`get_volume`).
- **GCD**: `search_series` llama a `/series/name/{q}/` **sin `page`** y corta
  `data["results"][:limit]` (`src/zascarr/services/gcd.py:248-275`). El filtro de edición
  española se aplica **después**, en `DiscoveryService._search_gcd`
  (`src/zascarr/services/discovery.py:463-470`): una edición `es` que caiga en la posición
  11-50 de la primera página se descarta sin llegar a evaluarse, y la página 2 no se pide.
- **Orden de candidatos**: `DescubrimientoDeGrupo._ordenar` es **neutro** a propósito
  (`src/zascarr/services/descubrimiento_grupo.py:217`): fija el orden de fuentes
  (`ORDEN_DE_FUENTES`, `discovery.py:61-64`) y luego el título. Nunca «la mejor primero».
- **Cortesía**: `gcd_rate_limit = 2.0` s (`src/zascarr/config.py:90`) y
  `comicvine_rate_limit = 1.0` s (`config.py:44`). El espaciado de 2 s permite ~1800
  peticiones/hora; la cuota real de GCD es 30/hora (§2.4): **el espaciado no es la restricción
  que manda**.

## 2. Evidencia

Todo lo marcado «verificado» se abrió el **2026-11-08**. Las llamadas a la API de Comic Vine
sin clave devuelven `401`/`status_code 100` (comprobado: `GET /api/volume/4050-31306/` →
`401 {"error": "Invalid API Key", "status_code": 100}`), así que la respuesta viva de un
volumen queda **`[sin verificar]`**; su contrato se deduce de la documentación y de cuatro
clientes que lo consumen a diario.

### 2.1 Comic Vine — documentación oficial

<https://comicvine.gamespot.com/api/documentation> — **HTTP 200**, 239 268 bytes, abierta el
2026-11-08. Tablas de campos por recurso (extraídas del HTML servido):

| Recurso | Campos declarados (resumen) | Lo que **no** tiene |
|---|---|---|
| `volume` | `aliases`, `count_of_issues`, `deck`, `description`, `first_issue`, `id`, `image`, `last_issue`, `name`, `person_credits`, **`publisher`**, `site_detail_url`, `start_year`, `character_credits`, `concept_credits`, `location_credits`, `object_credits`, `team_credits` | **`country`**, **`language`**, **`format`**, `variant_of` |
| `issue` | `issue_number`, `cover_date`, `store_date`, `volume`, `person_credits`, `character_credits`, `story_arc_credits`, `team_credits`, `name`, `description`, `image` | **`country`**, **`language`**, `format`, **`variant_of`**; `associated_images` existe pero **no está documentado** |
| `publisher` | `name`, `location_address`, `location_city`, `location_state`, `image`, `site_detail_url` | **`country`** |

Parámetros de la API (misma página):

- `/search`: `query`, `resources` (incluye `volume`), **`limit`** (la doc dice 10 por defecto),
  **`offset`** («Return results starting with the object at the offset specified»). Los clientes
  piden 50 (Kapowarr) y 100 (ComicTagger); Mylar3 pagina por `offset` sin fijar `limit`.
- `/volumes` (lista): `limit` (máx. 100), `offset`, y `filter` **solo** sobre los campos
  marcados como filtrables: **`id`, `name`, `date_added`, `date_last_updated`**. **No** son
  filtrables `publisher` ni `start_year`; por tanto **no hay filtro de servidor por editorial
  ni por año en Comic Vine**. Kapowarr lo confirma usando `filter=id:...` para lotes
  (`backend/implementations/comicvine.py:561`).
- Ruta de detalle: la doc declara `api_detail_url` y el prefijo de tipo `4050` para volumen;
  Kapowarr compone `/volume/4050-{id}` (`helpers.py:704-717`,
  `implementations/comicvine.py:502`). **La respuesta real sigue `[sin verificar]` (sin clave)**.

**Variantes en Comic Vine.** La documentación **no** declara ningún campo de variante. El
`TypedDict` de ComicTagger incluye `associated_images: list[CVAltImage]` y lo pide y usa en
el detalle de número (`comictalker/talkers/comicvine.py:117,489,1046`): en CV una variante es
**una portada alternativa del mismo número**, no un número distinto. Que exista de verdad
está verificado en el cliente; que la doc lo calle, también. `[sin verificar en vivo]`.

**Créditos en Comic Vine.** `person_credits` con `name`, `role` (texto libre) en volumen y
número; el volumen añade créditos de personajes, equipos, conceptos, localizaciones y objetos.
No hay tipos cerrados: el rol es prosa («writer, plotter»).

### 2.2 Cómo lo modelan los proyectos (commits y fechas)

#### Mylar3 — `mylar3/mylar3` `cdc94a4`, 2025-08-17, GPL-3.0

- Cliente **XML** de la API antigua: `format=xml`. Pide `field_list=...publisher...`
  (`mylar/cv.py:38`) y **no** pide país/idioma porque no existen.
- **Sí pagina**: `pullsearch` usa `&offset=` y `sort=date_last_updated:desc`
  (`mylar/mb.py:56-66`); `findComic` recorre `offset` hasta **1000 resultados**
  (`mb.py:158-167`).
- **Selección**: calcula un rango de años a partir de `start_year` y `count_of_issues`
  (`yearRange` = `start_year … start_year + count/12`, `mb.py:344-366`), descarta editoriales
  de una lista negra (`ignored_publisher_check`) y deja el resto a la interfaz. **No hay
  país/idioma.**
- **GCD**: no usa la API; **scrapea HTML** en `mylar/parseit.py:28-120`
  (`/search/advanced/process/` con `series`, `start_date`, `end_date`) y exige nombre
  normalizado exacto + año (`ComicYear` o `+1`) + recuento (`Total` o `±1`). Se usa al
  importar **solo para fechas de publicación** (`mylar/importer.py:230-255`), no para elegir
  edición. `GCDAdd` (`parseit.py:487`) scrapea además la ficha `/series/{id}`.
- **Lección**: Mylar3 demuestra que se puede «resolver» una serie con nombre+año+recuento sin
  país; también que así se puede aceptar una edición extranjera con el mismo nombre y año.

#### Kapowarr — `Casvt/Kapowarr` `c191dda`, 2026-09-14, GPL-3.0

- `volume_field_list` y `search_field_list` incluyen `publisher`, `count_of_issues`,
  `start_year`, `aliases`, `description`; **nunca país/idioma** (`implementations/comicvine.py:140-170`).
- **No pagina la búsqueda**: `/search` con `limit: 50` y sin `offset`
  (`comicvine.py:700-710`). Los lotes por ID sí usan `filter=id:` y `/issues?...&offset=`
  (`comicvine.py:561,653-668`).
- **La única señal de «edición de otro país» es prosa**: `translation_regex` sobre la
  descripción limpia (`comicvine.py:36-52`) produce `translated: bool`
  (`comicvine.py:317`, `VolumeMetadata`, `base/definitions.py:730-744`). La importación de
  biblioteca tiene `only_english` por defecto `True` (`features/library_import.py:125`) y
  **descarta** los volúmenes marcados `translated` (`matching.py:577`).
- **Selección** (`implementations/matching.py`): `match_title` normaliza título
  (`matching.py:51`), `match_year` acepta **±1 año** (`matching.py:77`), y
  `select_best_volume_result_for_file` puntúa: año exacto +1, año aproximado +1,
  `volume_number` +2, recuento igual +1, y **penaliza** si el número más alto del grupo supera
  el recuento del volumen (`matching.py:621-650`).
- **Lección**: es el único que «detecta» traducciones, y lo hace para **excluirlas**; para
  ZascArr (colección en español) la señal estaría invertida y no es fiable como campo.

#### ComicTagger — `comictagger/comictagger` `fa11a34`, 2026-09-06, Apache-2.0

- `CVSeries` no tiene país/idioma; sí `publisher`, `start_year`, `count_of_issues`, `aliases`
  (`comictalker/talkers/comicvine.py:97-110`).
- **Pagina** `/search` por `page` y `limit: 100`, con **tope de 500 resultados** y parada
  temprana cuando algún resultado baja del umbral de título (`comicvine.py:301-350`).
- **Selección** (`comictaggerlib/issueidentifier.py:471-500`): descarta series cuyo
  `start_year > año + 1`, exige `titles_match` con `difflib` **≥ 90** contra el nombre o sus
  alias (`comicapi/utils.py:521-545`), aplica una **lista negra de editoriales** y comprueba
  recuento. **No hay país/idioma.**
- **Variantes**: usa `associated_images` como portadas alternativas del número
  (`comicvine.py:489,1046`).

#### OdinsList — `boyobob/OdinsList` `39cb73c`, 2026-03-10, MIT

- Proyecto que **sí** combina GCD y Comic Vine, y el más cercano a la pregunta: usa el
  **volcado SQLite de GCD** (`README.md:14-15,27`), no la API, y CV para portada/verificación.
- **GCD local** (`src/odinslist/core/gcd.py`): filtra por número, **editorial con alias
  normalizados** (`_get_publisher_variants`, `normalize_publisher`), **ventana de año**
  (`year_began <= max_year AND (year_ended IS NULL OR year_ended >= min_year)`) y mes de
  portada; puntúa títulos por Jaccard ≥ 0.4 y deduplica por serie. **No filtra por
  `country`/`language` aunque el volcado los tiene.**
- **Comic Vine** (`src/odinslist/core/scoring.py:227-410`): puntúa tokens de título,
  editorial normalizada, probabilidad de año, descriptores de serie y número.
- **Lección**: aun con la base completa de GCD, la selección se hace por **título +
  editorial + año + número**; el país queda sin usar. Es la evidencia más fuerte de que el
  hueco es de criterio, no de campos.

**Respuesta directa a la pregunta 1.** *¿Tienen `country`/`language` en `volume`?* **No**:
Comic Vine no tiene esos campos (ni `format`), y ninguno de los cuatro clientes los modela
para CV. *¿Cómo identifican la edición de un país?* **No la identifican**: Kapowarr es el
único que detecta «traducción» con una regex sobre la sinopsis y la usa para **excluir**
(`only_english`); Mylar3 y ComicTagger no tienen el concepto; OdinsList se apoya en GCD, no
en CV. En GCD, en cambio, cada edición **es** una fila `Series` con su `country` y su
`language`, y no hay enlace de traducción entre ediciones.

### 2.3 GCD — repositorio y modelo de datos

`GrandComicsDatabase/gcd-django` `3219098`, 2026-11-08. **Código GPL-3.0** (`LICENSE`);
**datos CC BY-SA 4.0** (fila de GCD en `src/zascarr/LEGAL.md:106`; el pie del sitio no se pudo
abrir: `https://www.comics.org/` devolvió **403** en este entorno, `[sin verificar]`).

**`Series`** (`apps/gcd/models/series.py:41-115`) — una fila **por edición**, no por obra:

- `name`, `sort_name`, `format` (legado), `color`, `dimensions`, `paper_stock`, `binding`,
  `publishing_format`, `publication_type` (FK), `notes`, `external_link`, `keywords`.
- `year_began`, `year_ended` (+ `*_uncertain`), `is_current`, `publication_dates`,
  `first_issue`/`last_issue` (FK), `issue_count`.
- **`country` (FK a `Country`)** y **`language` (FK a `Language`)**
  (`series.py:107-108`); `publisher` (FK a `Publisher`).
- `Country`/`Language` viven en `apps/stddata/models.py`: `code` (máx. 10; en la práctica
  ISO de 2 letras: `es`, `en`, `fr`, `de`…) y `name`.
- `Publisher` (`apps/gcd/models/publisher.py:82-90`): `name`, `year_began`, `url`, `notes` y
  **`country` (FK)**; hay además `IndiciaPublisher` y `Brand` con su propio `country`.

**`Issue`** (`apps/gcd/models/issue.py:125-181`):

- `number`, `title`, `volume`, `variant_of` (FK a sí mismo), **`variant_name`**,
  `variant_cover_status`, `barcode`, `isbn`, `rating`, `publication_date`, **`key_date`**
  (fecha de portada), `on_sale_date`, `price`, `page_count`, `editing`, `notes`.
- `series` (FK), `indicia_publisher` (FK), `brand_emblem` (M2M).
- **Créditos**: `IssueCredit` (creator + `credit_type` + `credited_as` + `uncertain`) y
  `StoryCredit` (`story.py:621-655`: `is_signed`, `signature`, `credited_as`, `uncertain`);
  `CreditType` es una tabla cerrada con `sort_code` (`story.py:602-616`). Más granular que el
  rol de texto libre de CV.

**Relación entre ediciones.** `SeriesBond` (`seriesbond.py:6-40`) enlaza series con tipos
1-7 (seguimiento, fusión, reboot). **No hay un tipo «traducción»**: GCD no enlaza la edición
española con su original; solo comparten el nombre y cada una declara su `country`/`language`.

### 2.4 GCD — API (verificada en vivo el 2026-11-08)

Rutas (`apps/api/urls.py`):

```
/series/name/<name>/                      icontains sobre Series.name (deleted=False)
/series/name/<name>/year/<int:year>/      + year_began == year (exacto)
/series/name/<name>/issue/<number>/[year/<year>/]   IssuesList (key_date startswith year)
/series/<id>/  ·  /series/<id>/overview/  ·  /issue/<id>/  ·  /publisher/<id>/
```

**Paginación: sí.** `settings.py:351-373` fija `DEFAULT_PAGINATION_CLASS =
rest_framework.pagination.PageNumberPagination` y **`PAGE_SIZE = 50`**. Comprobado en vivo:

| Petición | Respuesta |
|---|---|
| `GET /api/series/name/Dragon%20Ball/?page=2` | `200`, `count: 98`, `previous: …/Dragon%20Ball/`, `next: null`, **48** resultados |
| `GET /api/series/name/Dragon%20Ball/` | `200`, `count: 98`, `next: …?page=2`, 50 resultados |
| `GET /api/series/name/Tintin/?page=3` | `200`, `count: 146`, 46 resultados (última página) |

**No hay filtro de servidor por país, idioma ni editorial.** Probado en vivo:
`?country=es` se **ignora** —devuelve el mismo `count: 98` y el mismo `next`, que arrastra el
parámetro—. La vista `SeriesList` solo filtra `name__icontains` (+ `year_began` si se usa la
ruta con `/year/`) y `deleted=False` (`apps/api/views.py:24-43`). El filtro por país/idioma
es **del lado del cliente**, sobre cada resultado.

**Qué devuelve `SeriesSerializer`** (`apps/api/serializers.py:182-200`):

```
api_url, name, country (código), language (código), active_issues (URLs),
issue_descriptors (texto: "1", "2"…), color, dimensions, paper_stock, binding,
publishing_format, notes, year_began, year_ended, publisher (URL)
```

**`issue_count` no está en el serializer** —la respuesta viva de `/series/224764/` trae 15
claves y ninguna es `issue_count`; `[sin verificar]` si la ficha E7 lo vio `null` por una
versión anterior—. Por eso el recuento no es usable como «número» (E7 ya lo avisaba).
`PublisherSerializer` sí incluye `country` (`serializers.py:203-208`).

**Límite de peticiones.** `settings.py:375-379`: `AnonRateThrottle` con
**`anon: 30/hour`**. Comprobado: tras la tanda de medición, GCD devolvió
**`429` con `Retry-After: 2385`** y cuerpo
`{"detail": "Request was throttled. Expected available in 2385 seconds."}`. La cuota es
**por hora**, compartida por IP; el `Retry-After` puede ser de ~40 minutos.

**Clientes de la API de GCD encontrados.** No hay gestor de biblioteca de cómics que use la
API de GCD para resolver ediciones:

- `ipkgs/go-gcd` `83e7942`, 2024-11-13, MIT: cliente Go mínimo; usa `/api/series/name/…`,
  `/year/…`, `/issue/…` y expone `Page`/`Next`/`Previous` (`series.go:83,95`). Sin selección.
- **Mylar3** usa el **HTML** de GCD (no la API) y solo para fechas (§2.2).
- **OdinsList** usa el **volcado SQLite** (no la API).
- `gcdb-graphql` (`adamhathcock`) usa los **volcados MySQL**, no la API.
- Kapowarr y ComicTagger usan **solo Comic Vine**; no consultan GCD.

### 2.5 Medición: paginar GCD cambia el resultado

Búsquedas en vivo el 2026-11-08 (`Accept: application/json`, `User-Agent` propio), paginando
con `?page=N` hasta agotar cada consulta:

| Consulta | `count` | Páginas | Ediciones `country=es` encontradas | ¿Está la del corpus? |
|---|---:|---|---|---|
| `Dragon Ball` | 98 | 2 (50+48) | p1: 0 · **p2: `Dragon Ball. Ultimate Edition`, 2006, publisher `4437`** | **sí**: `4437` = **Planeta DeAgostini** (`country: es`), 2006 → coincide con ES-007; ES-029 (2007) habría que contrastar el año |
| `Tintin` | 146 | 3 (50+50+46) | p1: `Las Aventuras de Tintín` 1958, `Tintin` 1967, `Tintin` 1981 ; p2/p3: 0 | **no**: no hay Juventud 1985/1989 en las 146 |
| `Astérix` | 189 | 4 (50+50+50+39) | p1: `Astèrix` 1980 (publisher `4426`) ; p2: 0 ; **p3/p4: bloqueadas por `429`** | **`[sin verificar]`** (p3/p4; el nombre de `4426` tampoco se resolvió por la cuota) |

**Corrección expresa a las fichas previas.** `benchmark-BL-FU2-detalle-edicion.md` §2.3
concluyó que la edición del corpus «no está» en GCD mirando **solo la primera página**. Con
paginación, la edición de Dragon Ball **sí está** (página 2). La frase correcta es «no está en
la primera página», no «no está». Para Tintin, con las 146 filas vistas, la cobertura de
Juventud 1985/1989 sigue **sin aparecer**; para Astérix queda pendiente de verificar.

**Coste real de la medición:** la tanda completa de la sesión (3 sondas iniciales + 6 páginas +
3 páginas más + 2 editoriales ≈ **14 peticiones**) agotó la cuota y provocó el `429`; no consta
cuántas consumieron otros procesos de la misma IP.

## 3. Matriz campo × fuente × proyecto

Símbolos: **✓** lo da tal cual; **~** lo da parcial, derivado o con otra petición; **✗** no lo
da; **—** no aplica.

### 3.1 Fuente × campo (Comic Vine vs GCD)

| Campo | Comic Vine (`volume`/`issue`) | GCD (`series`/`issue`) | Nota |
|---|---|---|---|
| Título | ✓ `name` | ✓ `name` (+ `sort_name`) | — |
| Alias | ✓ `aliases` | ✗ (solo `name`/`sort_name`) | CV permite alias; GCD no |
| Año inicio / fin | ~ `start_year` (solo inicio) | ✓ `year_began` / `year_ended` | GCD da rango |
| Editorial | ✓ `publisher.name` (inline) | ~ `publisher` = **URL** (+1 petición al nombre) | GCD ya resuelto en `main` (`b9551b1`) |
| País | ✗ | ✓ `country` (código ISO, p. ej. `es`) | **CV no tiene el campo** |
| Idioma | ✗ | ✓ `language` (código ISO) | **CV no tiene el campo** |
| Formato físico | ✗ | ✓ `publishing_format`, `binding`, `color`, `dimensions`, `paper_stock` | CV no tiene `format` |
| Recuento de números | ✓ `count_of_issues` | ~ `issue_count` en el modelo, **✗ en el serializer**; `active_issues`/`issue_descriptors` | No usar como «número» |
| Número concreto | ✓ `issue_number` | ✓ `number` | — |
| Variantes | ~ `associated_images` (no documentado) | ✓ `variant_of` + `variant_name` | CV: portadas; GCD: número variante real |
| Créditos | ✓ `person_credits` (rol texto libre) | ✓ `IssueCredit`/`StoryCredit` + `CreditType` | GCD más granular |
| Sinopsis | ✓ `description` / `deck` | ~ `notes` (no sinopsis de obra) | — |
| Portada | ✓ `image` | ~ `cover` por número (URL; E7: 403) | — |
| Enlace a ficha | ✓ `site_detail_url` | ✓ `api_url` (+ web `comics.org/series/<id>/`) | — |
| Filtro de servidor por país/idioma | ✗ | ✗ (verificado: `?country=es` ignorado) | Filtro en cliente |
| Paginación de búsqueda | ✓ `offset`, `limit` (≤100) | ✓ `?page=N`, 50/página | Mylar3 offset; ComicTagger page |

### 3.2 Proyecto × campo (lo que cada cliente pide o modela)

| Campo | Mylar3 (CV) | Mylar3 (GCD, HTML) | Kapowarr (CV) | ComicTagger (CV) | OdinsList (CV + GCD local) |
|---|---|---|---|---|---|
| Título | ✓ | ✓ | ✓ | ✓ (+alias) | ✓ (Jaccard) |
| Año | ✓ (+rango calculado) | ✓ (±1) | ✓ (±1) | ✓ (`start_year ≤ año+1`) | ✓ (ventana `year_began..year_ended`) |
| Editorial | ✓ (lista negra) | ✓ (nombre) | ✓ | ✓ (lista negra) | ✓ (alias normalizados) |
| País | ✗ (no existe) | ✗ | ✗ | ✗ | ✗ (aun teniéndolo en GCD) |
| Idioma | ✗ | ✗ | ~ `translated` (prosa) | ✗ | ✗ |
| Formato | ✗ | ✗ | ✗ | ✗ | ✗ |
| Recuento | ✓ | ✓ (±1) | ✓ (desempate) | ✓ | ✓ |
| Número | ✓ | ~ (ficha) | ✓ | ✓ | ✓ |
| Variantes | ✗ | ✗ | ✗ | ~ portadas `associated_images` | ✗ |
| Créditos | ~ | ✗ | ✗ | ~ | ~ |
| Paginación | ✓ offset ≤1000 | ✗ (HTML 1 página) | ✗ (limit 50) | ✓ page ≤500 | — (dump local) |

### 3.3 Lo que ningún proyecto resuelve

- **Ninguno identifica la edición de un país con Comic Vine.** La única señal es la prosa de
  la descripción (`translated` de Kapowarr), y se usa para **excluir**, no para resolver.
- **Ninguno usa `country`/`language` de GCD para elegir candidato**, ni siquiera OdinsList con
  el volcado completo. GCD lo tiene; los clientes no lo miran.
- **Ninguno pagina GCD por la API**: Mylar3 scrapea HTML; OdinsList usa el volcado; go-gcd
  expone `?page` pero no selecciona nada. **No se encontró ningún proyecto que use `?page` o el
  filtro de año de GCD para elegir edición**; ZascArr sería el primero de estas referencias.

## 4. Veredicto por idea

| Idea | Resultado | Motivo |
|---|---|---|
| Leer `country`/`language` de GCD y **filtrar la edición ES** | **Adoptar** | GCD es la única de las dos fuentes que tiene el campo, y ya viene en cada resultado de búsqueda. |
| **Paginar GCD** (`?page=N`) y quedarse con las ediciones `es` | **Adaptar** | La API pagina (verificado); cuesta cuota (30/h) y hay que poner tope y caché. |
| Usar el **filtro de año del path** de GCD (`/series/name/<q>/year/<y>/`) | **Adoptar** | Filtro de servidor, 1 petición, sin paginar; `year_began` es exacto (si la etiqueta da el año). |
| **Filtrar antes de recortar** en el cliente | **Adoptar** | Hoy `gcd.py` corta `[:limit]` antes del filtro ES: se pierden candidatos de la propia página 1. |
| Ranking por **título + año ±1 + editorial + recuento** (Kapowarr, ComicTagger) | **Adaptar** | Sirve sin país; hay que añadir país/idioma cuando GCD los dé y conservar `campo_ausente` cuando no. |
| **`translated` por expresión regular sobre la descripción** (Kapowarr) | **Descartar** | Es prosa, no un campo; para ZascArr (colección ES) la señal estaría invertida. A lo sumo, pista mostrada, nunca dato. |
| `only_english` de Kapowarr | **Descartar** | ZascArr es de tebeo español; filtrar a inglés es el criterio contrario. |
| **Scraping HTML de GCD** (Mylar3) | **Descartar** | Hay API JSON; el HTML cambia y obliga a mantener un parser frágil (Mylar3 arrastra uno). |
| `variant_of`/`variant_name` de GCD | **Adoptar** | Identifica la variante como número distinto; CV solo tiene portadas alternativas. |
| `associated_images` de CV como variante | **Adaptar** | Sirve para portadas alternativas, no para identidad de edición; no está documentado. |
| Créditos con `CreditType`/`credited_as` de GCD | **Adaptar** | Mapeo a `CreatorRole`; el rol de CV es texto libre y ya se normaliza en el enricher. |
| `issue_count` de GCD como recuento | **Descartar** | No está en el serializer actual; E7 ya documentó que engaña. |
| Paginar Comic Vine (`offset`) por defecto | **Adaptar** (solo si hace falta) | CV ordena por relevancia y no tiene país; paginar 500 resultados a 1 req/s es caro y no resuelve la edición ES. |
| Volcado SQLite de GCD en la Pi (OdinsList) | **Descartar** | Coste de disco/memoria en la Pi y actualización manual; para consultas puntuales, API con caché. |

## 5. Reglas propuestas para ZascArr

Cambios de **selección de candidato**, no de esquema. Ninguna toca el modelo ni los ficheros.

### R1 — Paginar GCD con filtro ES y tope (o usar su filtro de año)

**Regla.** Al buscar en GCD, si el año de la etiqueta es conocido, pedir primero
`/series/name/<q>/year/<año>/` (1 petición, filtro de servidor); si no hay resultado o no hay
año, pedir páginas `?page=1..N` (N ≤ 3) y **quedarse con `country == "es"`** antes de recortar.
Cachear por `(fuente, consulta, página)`.

**Justificación.** `Dragon Ball. Ultimate Edition` (Planeta DeAgostini, 2006) está en la
**página 2** de 98 resultados; hoy ZascArr no la ve. El filtro de año existe en el código de
la API (`apps/api/urls.py`, `views.py:24-43`) y evita paginar cuando la etiqueta da el año.

**Coste.** 1-3 peticiones por consulta; GCD anónima 30/h; 2 s de cortesía no bastan como tope
(§6). Si la cuota está agotada, `429` → estado `limite_de_cortesia` (ya soportado), no lista
vacía.

### R2 — Filtrar antes de recortar y subir el techo de candidatos

**Regla.** El filtro de país/idioma y el descarte por título se aplican **antes** de
`[:limit]`. GCD: pedir la página (50) y filtrar; Comic Vine: subir `limit` de 10 a 50-100
(la doc marca 10 por defecto en `/search`; los clientes usan 50 y 100) y recortar **después**
de puntuar.

**Justificación.** `src/zascarr/services/gcd.py:275` corta a 10 y
`src/zascarr/services/discovery.py:463-470` filtra después: una edición ES en la posición
11-50 de la primera página se pierde. Con Tintin, las tres ediciones `es` de la página 1 no
tienen por qué caer en el top-10. No cuesta ni una petición más.

**Coste.** Ninguno en red; algo más de CPU y de tamaño de respuesta (50/100 filas).

### R3 — Ranking explicable con las señales que la fuente sí tiene

**Regla.** Puntuar candidatos con: título normalizado (exacto > contiene > fuzzy), año (exacto
> ±1), editorial (normalizada/alias), `country`/`language` cuando la fuente los dé, y recuento
de números como desempate. Orden determinista y **explicable en la UI** («coincide año y
editorial», «año a ±1»). Si un campo falta, no puntúa y se declara ausente; **nunca** se
convierte en un valor por defecto.

**Justificación.** Es el patrón común de Kapowarr (`matching.py:621-650`), ComicTagger
(`issueidentifier.py:471-500`) y OdinsList (`scoring.py:356-410`), y el que evita el «primero
que devuelve la fuente». ZascArr hoy ordena neutro (`descubrimiento_grupo.py:217`).

**Coste.** Solo CPU; sin peticiones. Riesgo: un ranking mal calibrado esconde el candidato
correcto → mostrar siempre el resto y no borrar candidatos.

### R4 — Año como ventana (±1), no como igualdad; recuento como desempate

**Regla.** Aceptar `año_candidato ∈ [año_etiqueta-1, año_etiqueta+1]`; usar `count_of_issues`
(recuento de la edición) solo para desempatar y **nunca** como número de ejemplar.

**Justificación.** Kapowarr acepta ±1 (`matching.py:77`), ComicTagger descarta solo
`start_year > año+1`, Mylar3 calcula un rango de años a partir del recuento
(`mb.py:344-366`). Las ediciones cambian de año entre el sello y la ficha; el año exacto como
filtro duro descarta la edición correcta. El recuento no es el número (E7).

**Coste.** Cero peticiones.

### R5 — No inferir país/idioma por prosa ni scrapear; GCD manda cuando lo tiene

**Regla.** El país/idioma solo se toma de un campo de la fuente (GCD `country`/`language`). La
detección de «traducido» de Kapowarr se **descarta** como dato; el scraping HTML de GCD
(Mylar3) también. Si GCD no informa país/idioma, el candidato se conserva marcado
(`idioma_no_informado`, ya existe) y no se descarta.

**Justificación.** La regex de Kapowarr es prosa y está pensada para excluir; el scraping de
Mylar3 ya obligó a mantener un parser frágil. `discovery.py` ya distingue «no informado» de
«no español» (`services/gcd.py::es_edicion_espanola`).

**Coste.** Cero peticiones; se pierde la pista de «posible traducción» (asumible: no es un
campo).

### 5.1 Matriz ponderada (nivel 2)

Pesos por defecto de `docs/design/benchmark-referencias.md`, sin cambios: encaje con el
Coleccionista 25 · coste en Pi 20 · seguridad/legalidad/licencia 20 · cobertura del requisito
15 · adaptabilidad al stack 10 · mantenimiento 5 · lock-in 5. Escala 1-5.

| Idea | Encaje | Coste | Legal | Cobertura | Adapt. | Mant. | Lock-in | **Total** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **R2** filtrar antes de recortar | 5 | 4 | 5 | 5 | 5 | 5 | 5 | **96** |
| **R5** no inferir por prosa/scraping | 5 | 5 | 5 | 2 | 5 | 5 | 5 | **91** |
| **R4** año ±1 y recuento | 4 | 5 | 5 | 3 | 5 | 5 | 5 | **89** |
| **R1** paginar GCD + país | 5 | 3 | 5 | 4 | 5 | 4 | 5 | **88** |
| **R3** ranking explicable | 4 | 4 | 5 | 4 | 4 | 3 | 5 | **84** |

**Las tres que más sirven:** **R2** (recupera candidatos que hoy se tiran sin gastar red),
**R1** (es la que hace aparecer la edición de Dragon Ball) y **R3** (sin ranking, R1 y R2 solo
devuelven más ruido). R4 y R5 son baratas y evitan falsos positivos; pueden ir en el mismo
cambio que R3.

## 6. Coste y cortesía

- **Por consulta GCD:** 1 petición = 50 filas; `Dragon Ball` necesita 2 (98); `Tintin` 3
  (146); `Astérix` 4 (189). Con el **filtro de año** del path, 1 petición si el año es exacto.
- **Cuota GCD:** **30 peticiones/hora** (`settings.py:376-379`) y `429` con `Retry-After` de
  hasta ~40 min (observado 2385 s). Con 2 s de espaciado ZascArr podría lanzar ~1800/h: el
  tope que manda es la cuota, no el espaciado. `pedir_con_cortesia` ya respeta `Retry-After` y
  bloquea la fuente (`src/zascarr/utils/peticiones.py:297-316`); lo que falta es **no
  gastar** páginas que no cambian la decisión (tope + caché + filtro de año).
- **Por consulta Comic Vine:** 1 petición (`/search`, `limit` 100) a 1 req/s; el detalle de
  volumen es +1. Paginar más de 100 es posible con `offset`, pero CV ordena por relevancia y
  no tiene país: **no resuelve la edición ES**, así que no se propone por defecto.
- **Detalle:** GCD `get_series` 1 petición (+1 para el nombre de editorial); CV `get_volume`
  1. El detalle debe pedirse **solo al top-k** tras el ranking (ya recomendado en BL-FU2 §5).
- **Peor caso razonable por búsqueda del coleccionista:** GCD 3 páginas + 1 ficha (+1 si se
  resuelve el nombre de la editorial) = 4-5 peticiones; CV 1 búsqueda + 1 volumen = 2. Cabe en
  la cuota GCD solo si no se repite la misma consulta; de ahí la caché por consulta.

## 7. Riesgos legales

- **GCD, datos CC BY-SA 4.0** (`src/zascarr/LEGAL.md:106`): atribución y enlace de vuelta ya
  presentes en `/ui/descubrir`. Paginar no cambia la licencia; **no** se redistribuye el
  volcado ni se cachea más de lo que se muestra.
- **GCD, código GPL-3.0** (`LICENSE` del repo). ZascArr también es GPL-3.0, pero esta ficha
  **no reutiliza código**: solo lee modelos y clientes para describir el contrato.
- **Comic Vine, términos propios** (`LEGAL.md:104`): API con clave y 1 req/s; paginar no es
  «redistribución masiva», pero tampoco hace falta. No se copia código.
- **OdinsList (MIT), ComicTagger (Apache-2.0), Mylar3 y Kapowarr (GPL-3.0)**: solo se citan
  para describir sus contratos; ningún fragmento se traslada.
- **Portadas**: GCD sirve la URL de portada por número (E7: 403 en pruebas); no se descarga
  para esta ficha.

## 8. Qué NO está verificado (y cómo verificarlo)

1. **Respuesta viva de `/volume/4050-{id}/` de Comic Vine y de su `associated_images`.**
   Sin `COMICVINE_API_KEY` en este entorno (comprobado: `401`). **Cómo:** con clave de lectura,
   `GET /api/volume/4050-31306/?field_list=id,name,publisher,start_year,count_of_issues,first_issue,last_issue`
   y `GET /api/issue/4000-{id}/?field_list=id,issue_number,associated_images`; guardar fixture
   saneada. También comprobar si existe algún volumen ES de los tres casos (búsqueda por
   `resources=volume` y `publisher` de cada resultado).
2. **Astérix, páginas 3-4 de GCD.** Bloqueadas por `429` (cuota 30/h). **Cómo:** esperar la
   ventana (≈40 min) y repetir `?page=3` y `?page=4`; anotar si aparece Salvat 2011.
3. **`issue_count` de GCD.** En `3219098` no está en el serializer; la ficha E7 (2026-09-28)
   lo vio `null`. **Cómo:** `GET /api/series/224764/` y comprobar claves; contrastar con
   `active_issues`/`issue_descriptors`.
4. **Licencia de datos de GCD en el sitio.** `https://www.comics.org/` devolvió **403**;
   `docs.comics.org` también. Se usa `LEGAL.md:106` (CC BY-SA 4.0) como fuente del proyecto.
   **Cómo:** abrir el pie del sitio desde un navegador con IP no bloqueada.
5. **Cuota GCD compartida.** El `429` apareció tras la tanda de medición; no consta cuántas
   peticiones consumieron otros procesos de la misma IP ni si el límite es por IP o por
   sesión. **Cómo:** repetir la medición en una ventana limpia y contar.
6. **Filtro de año del path de GCD en vivo.** Verificado en el código (`urls.py`,
   `views.py:24-43`), **no** en vivo (la cuota ya estaba agotada). **Cómo:**
   `GET /api/series/name/Dragon%20Ball/year/2006/` y comprobar que devuelve la Ultimate.
7. **Cobertura de Tintin/Astérix más allá del nombre.** GCD indexa por `name__icontains`;
   una edición con otro título («Las aventuras de…») puede quedar fuera de la consulta.
   **Cómo:** probar variantes de título y el buscador de la web.
8. **Que `?page` más allá de la última página devuelva 404 o lista vacía.** No probado (no
   hace falta para la regla: se para cuando `next` es `null`).

## 9. Casos de prueba antes de implementar

1. **Paginación GCD**: con una fixture de dos páginas (98 resultados, edición `es` en la
   segunda), `search_series("Dragon Ball")` devuelve la edición `es`; no la pierde al recortar.
2. **Filtro antes de recortar**: un resultado `es` en la posición 11-50 de la primera página
   llega a la lista; uno `fr` no; uno sin país se conserva con `idioma_no_informado=True`.
3. **Tope de páginas**: N=3; si no aparece, se devuelve lo encontrado y el estado es `ok` (no
   se inventa «sin resultados»); con cuota agotada, `limite_de_cortesia` y `reintentar_en`.
4. **`429` + `Retry-After`**: el cliente no reintenta en bucle; bloquea la fuente y propaga el
   estado (comportamiento actual de `pedir_con_cortesia`, ya probado).
5. **Filtro de año**: `year/<y>` devuelve la edición con `year_began == y`; si no hay, se cae
   a paginar (sin duplicar peticiones ya cacheadas).
6. **Ranking**: entre dos candidatos con el mismo título, uno con año exacto + editorial + país
   y otro sin país, gana el primero; el orden es estable entre ejecuciones y el motivo se
   muestra; el segundo no se borra.
7. **`campo_ausente`**: CV no rellena país/idioma; no se convierte `tradition_guess=AMERICAN`
   (valor por defecto del producto) en `country`.
8. **Variantes**: `variant_of` de GCD no crea una edición nueva; `associated_images` de CV no
   se interpreta como número distinto.
9. **Detalle solo del top-k**: con 10 candidatos, solo se piden fichas de los 2 primeros; el
   resto queda sin detalle y así se declara.

## 10. Reproducible

- **Comic Vine (doc, HTTP 200; API sin clave, 401):**
  `GET https://comicvine.gamespot.com/api/documentation`;
  `GET https://comicvine.gamespot.com/api/volume/4050-31306/?format=json` → `401`, `status_code 100`.
- **GCD (anónima, `Accept: application/json`, `User-Agent` propio):**
  - `GET /api/series/name/Dragon%20Ball/?page=1` y `?page=2` (98; `es` en p2).
  - `GET /api/series/name/Tintin/?page=1..3` (146; 3 `es` en p1).
  - `GET /api/series/name/Ast%C3%A9rix/?page=1..4` (189; p3/p4 → `429`).
  - `GET /api/series/name/Dragon%20Ball/?country=es` (filtro ignorado: mismo `count` y `next`).
  - `GET /api/publisher/4437/` → `Planeta DeAgostini`, `country: es`.
  - `GET /api/series/224764/` → claves del serializer (sin `issue_count`).
- **Repos (commit, fecha):** Mylar3 `cdc94a4` (2025-08-17), Kapowarr `c191dda` (2026-09-14),
  ComicTagger `fa11a34` (2026-09-06), gcd-django `3219098` (2026-11-08), OdinsList `39cb73c`
  (2026-03-10), go-gcd `83e7942` (2024-11-13). Rutas citadas en §2.
- **Método**: clon superficial de cada repo y lectura de los ficheros citados; no se ejecutó
  código de terceros ni se copió ninguna implementación.

## 11. Caducidad

**~60 días: 2027-01-07**, o antes si cambia el serializer o la paginación de GCD, la
documentación de Comic Vine o la cuota anónima. La evidencia de campo se tomó el
**2026-11-08** sobre `origin/main` `2f1621e`.
