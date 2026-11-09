# Benchmark — fuentes de metadatos de referencia (Kapowarr, ComicTagger, Calibre y fuentes no contempladas)

> **Ficha de benchmarking (nivel 2)** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Pregunta del PO (2026-11-09):** ¿cómo recaban metadatos Kapowarr, ComicTagger y el addon de
> Calibre para cómics? ¿Utilizan fuentes que ZascArr no contempla? ¿Merece la pena alguna fuente
> nueva o el problema sigue siendo la selección?
> **Fecha:** 2026-11-09. **Base contrastada:** `origin/main` `ecc5234` (2026-11-09).
> **Método:** lectura de repositorios, código y documentación pública; comprobaciones HTTP de
> lectura puntuales, sin credenciales y sin activar ninguna fuente en ZascArr. **No** se ha
> ejecutado el enricher, no se han tocado ficheros reales y no se ha escrito código ni tests.
> Lo que no se pudo abrir va marcado **`[sin verificar]`**.
> **Autor:** SCOUT.bench. **Esto es insumo, no aprobación:** decide el PO.

---

## 0. Respuesta para el PO

1. **Kapowarr no es multi-fuente.** Su única fuente de metadatos es **Comic Vine** por API; no usa
   Metron ni GCD. Guarda volumen y número en SQLite, sin precedencia por campo, y la release
   **v1.3.2 no lee ni escribe `ComicInfo.xml`**: solo lo reconoce como fichero de metadatos y lo
   conserva. La rama `metadata-export` (no fusionada en `main` a 2026-11-09) lo **escribe**, pero
   tampoco lo lee.
2. **ComicTagger sí es multi-fuente por plugins, pero solo Comic Vine viene incluido.** GCD es un
   plugin externo que usa el **volcado SQLite** de GCD, no scraping de `comics.org` para metadatos;
   solo raspa la ficha de portada si se piden covers. Metron se **retiró** en 2025 por el daño que
   causaba al servicio. Escribe `ComicInfo.xml` con estrategia *overlay* o *add missing*.
3. **Calibre no tiene una fuente de cómics nativa.** Descarga metadatos de libros (Amazon, Google,
   Edelweiss; Open Library solo portadas) y los addons de cómic son, o un cliente de Comic Vine
   antiguo, o lectura/escritura de `ComicInfo.xml`/ZIP comment. Ninguno resuelve la edición española.
4. **La única fuente nueva con cobertura española a nivel edición/número es Whakoom.** Su base es
   CC BY-SA 4.0 (imágenes aparte), pero sus términos **prohíben el acceso automatizado** y no hay
   API pública documentada. No es un scraper: es un acuerdo de datos o una exportación.
5. **Open Library** aporta ISBN y tomos españoles (útil para `Issue.isbn`, hoy una columna muerta),
   pero no grapas. **Bedetheque/BDGest** aporta BD europea original, no edición española. **Metron**
   aporta fumetti y una API excelente, pero solo admite series en **inglés e italiano**.
   **MangaDex, Wikidata y Marvel API** no resuelven la edición española.
6. **Ninguna fuente nueva arregla el cuello de botella medido.** #135 ya demostró que Comic Vine no
   acredita la edición española (0/12) y que Tebeosfera/GCD sí cuando se busca bien (3 ediciones;
   ES-022 por dos fuentes). El problema es **selección, paginación y precedencia**, no el número de
   fuentes.
7. **Recomendación:** no integrar un scraper de Whakoom; pilotar Open Library para ISBN/tomos;
   estudiar un acuerdo de datos con Whakoom y, solo si se abre, Bedetheque/Metron. Antes de sumar
   fuentes, cerrar el ranking/paginación de #135 y la procedencia por campo.
8. **Las tres que más faltan:** **Whakoom** (tebeo español), **Open Library** (ISBN/tomos españoles)
   y **Bedetheque/BDGest** (BD europea). Metron es la cuarta, solo para fumetti.

---

## 1. Problema local y método

### 1.1 Qué tiene ZascArr hoy (verificado en `ecc5234`)

Las cuatro fuentes están **apagadas por defecto** (ADR 0013) y se encienden en Ajustes. El enricher
enruta **una sola fuente por tradición** (`services/enricher.py`), no combina fuentes para la misma
serie.

| Fuente | Cliente | Capacidad real | Persistencia |
|---|---|---|---|
| Comic Vine | `services/comic_vine.py` | serie, volumen, número, créditos, personajes, arcos, portada | `Series.comic_vine_id`, `Issue.comic_vine_id`, campos de fila |
| AniList | `services/anilist.py` | solo serie (título, sinopsis, portada, año, capítulos/volúmenes) | `Series.anilist_id` |
| Tebeosfera | `services/tebeosfera.py` | búsqueda de colecciones/sagas + detalle de colección y de número | `Series.tebeosfera_slug`; el detalle es evidencia, no identidad persistida |
| GCD | `services/gcd.py` | búsqueda/detalle de serie y edición (país, idioma, formato) | `Series.gcd_id`; no hay `Issue.gcd_id` |

Límites locales que importan para esta pregunta:

- **No existe entidad edición** (ADR 0003). La edición se evalúa como unidad, pero no se modela.
- **`Issue.isbn` existe y nada la lee ni la escribe** (`models/__init__.py:486`;
  `docs/design/discriminantes-publicacion.md:38`). Es la vía natural para un tomo con ISBN.
- **`MetadataSource` solo tiene cuatro fuentes** (`models/__init__.py:187-193`): añadir una quinta
  no es solo un cliente, toca enum, ajustes, estados, cortesía y UI.
- La procedencia es **por fila** (`metadata_source`), no por campo. El único mecanismo de
  precedencia fina está en la escritura de `ComicInfo.xml` (`services/tagger.py`,
  `core/comicinfo_write.py`), con `locked_fields` y marca de autoría.

### 1.2 Lo que midió #135

El banco de cobertura y su piloto son la evidencia local de partida:

- **Comic Vine:** 12/12 `incorrecto` a nivel edición; su volumen es la edición USA (Viz, etc.).
- **Tebeosfera:** 2/12 `coincidencia_verificada` (ES-014 y ES-022, los dos integrales de Blueberry
  de Norma), tras corregir recall y selección; 8 incorrectas y 1 ambigua.
- **GCD:** 2 ediciones acreditadas (ES-007 y ES-022), con paginación y filtro de año; sin ese
  filtro, 8 casos se quedaban sin candidato. ES-022 queda acreditada por GCD y Tebeosfera, así que
  el bloque cierra con **3 ediciones distintas** (ES-007, ES-014 y ES-022).
- **AniList:** sin método de edición; 1/10 respuestas útiles en el piloto.
- **Conclusión registrada:** «el cuello de botella original —las fuentes no tienen la edición
  española— era falso: la tienen, y lo que fallaba era cómo la buscábamos» (recorte antes del
  filtro, primera página, sin año, sin ranking).

Evidencia local: [piloto de cobertura #135](piloto-cobertura-2026-11-06.md),
[benchmark del modelo CV/GCD](benchmark-modelo-cv-gcd.md) y
[benchmark de detalle de edición](benchmark-BL-FU2-detalle-edicion.md). Esta ficha no repite la
medición: la usa para no confundir «fuente nueva» con «mejor selección».

### 1.3 Referencias leídas y fechas

| Proyecto / fuente | Repositorio o documento | Commit / versión | Fecha | Licencia del código |
|---|---|---|---|---|
| Kapowarr | `Casvt/Kapowarr` | `c191dda` (v1.3.2) | 2026-09-14 | GPL-3.0 |
| Kapowarr (rama ComicInfo) | `Casvt/Kapowarr` `metadata-export` | `c3e9ea1` (PR #396) | 2026-11-07 | GPL-3.0 |
| ComicTagger | `comictagger/comictagger` | `fa11a34` | 2026-09-06 | Apache-2.0 |
| GCD talker | `comictagger/gcd_talker` | `4474ca5` | 2026-09-28 | Apache-2.0 |
| Calibre | `kovidgoyal/calibre` | `0ccdcb2` (9.18.0) | 2026-11-09 | GPL-3.0 |
| Embed Comic Metadata | `RichardScottOZ/EmbedComicMetadata` | `caa41a8` | 2023-04-05 | GPL-3.0 |
| calibre-comicvine | `xchewtoyx/calibre-comicvine` | `38252c8` (0.11.2) | 2014-06-16 | MIT |
| Comicalibre | `pewsplosions/comicalibre` | `9915b1b` | 2025-01-29 | GPL-3.0 |
| Metron | `Metron-Project/metron` | `c6e1c48` | 2026-11-07 | GPL-3.0 (datos: CC BY-SA 4.0) |
| Bedetheque (scraper de referencia) | `Inervo/BedethequeKomga` | `bc05042` | 2023-08-05 | no revisada para reutilizar código |

Calibre no se ha ejecutado. Se ha leído su árbol de fuentes de metadatos y el índice público de
plugins (`plugins.calibre-ebook.com`, consultado 2026-11-09).

---

## 2. Cómo recaban metadatos los tres proyectos

### 2.1 Kapowarr — una sola fuente, sin precedencia, sin lectura de ComicInfo

**Fuente.** Solo Comic Vine. La documentación lo dice sin ambigüedad: «Kapowarr uses ComicVine as
its metadata source» (`docs/src/settings/general.md:68`). El cliente pide `volume`, `issue`,
`search` y portadas a `https://comicvine.gamespot.com/api`
(`backend/base/definitions.py:112-118`; `backend/implementations/comicvine.py:140-173`).

**¿Metron o GCD?** No hay implementación. Una búsqueda en todo `backend/` y `docs/` no encuentra
Metron ni GCD; solo hay una **petición abierta** para Metron, `Casvt/Kapowarr#182` (2024-09-28,
abierta a 2026-11-09), motivada porque «the ComicVine API has been down for a couple of days». No
hay issue equivalente para GCD. La rama `metadata-export` tampoco añade fuentes: sigue usando
Comic Vine para los campos extendidos.

**Qué pide y qué guarda.**

| Unidad | Campos que pide | Dónde queda |
|---|---|---|
| Volumen | `id`, `name`, `start_year`, `publisher`, `count_of_issues`, `description`, `image`, `site_detail_url`, `aliases` | tabla `volumes` (`comicvine_id`, `title`, `alt_title`, `year`, `publisher`, `volume_number`, `description`, `site_url`, `special_version`) |
| Número | `id`, `issue_number`, `name`, `cover_date`/`store_date`, `description`, `volume` | tabla `issues` (`comicvine_id`, `issue_number`, `calculated_issue_number`, `title`, `date`, `description`) |
| Portada | `image.small_url` | `volumes_covers.cover` (BLOB) |

No guarda país, idioma, formato físico, ISBN, créditos ni personajes en el esquema base. Los
créditos/personajes se piden **solo** para la exportación a `ComicInfo.xml` de la rama
`metadata-export` (`fetch_extended_issue_metadata`, `person_credits`, `character_credits`,
`team_credits`, `location_credits`, `story_arc_credits`), no para la base.

**Precedencia.** No existe precedencia entre fuentes: hay una sola. El refresco de Comic Vine
**sobrescribe** los campos de volumen/número en SQLite; no hay `metadata_source` por campo ni
histórico de procedencia. La base local es la fuente de verdad para la exportación posterior.

**ComicInfo.xml.**

- **v1.3.2 (release):** no lo lee ni lo escribe. `comicinfo.xml` está en `METADATA_FILES`
  (`backend/base/definitions.py:170-173`); al escanear se clasifica como fichero general de tipo
  `metadata` (`backend/implementations/file_matching.py:470-478`), al renombrar se conserva su
  nombre (`backend/implementations/naming.py:772-773`) y al extraer el nombre se ignora su
  contenido (`backend/base/file_extraction.py:387-395`). **No hay parser**: una búsqueda de
  `comicinfo` en `backend/` solo devuelve esa constante.
- **Rama `metadata-export` (`c3e9ea1`, PR #396, 2026-11-07):** añade
  `backend/implementations/comicinfo.py` y escribe `ComicInfo.xml` dentro de CBZ/ZIP y CBR/RAR.
  Fuente de los campos: **base local** (serie, número, volumen, editorial, formato, fecha,
  título, sinopsis, web) más **Comic Vine** para créditos/personajes/equipos/localizaciones/arcos.
  **No lee** el XML existente: si ya hay uno, lo **elimina y lo sustituye** por el generado
  (`_zip_with_xml`, `_rar_with_xml`). No hay merge, no hay `LanguageISO`, no hay `PageCount`, no
  hay `Manga`. El comentario del mantenedor en `#388` (2026-10-16) explica por qué no se piden los
  datos a Comic Vine en cada exportación: «Because ComicVine has a rate limit that is easily hit».
  A 2026-11-09 esta rama **no está en `main` ni en la release**.

**Coste.** 1 petición por volumen y 1 por número, con `CV_BRAKE_TIME = 1.0 s`
(`backend/base/definitions.py:118`) y el límite de Comic Vine; la documentación habla de 20 000
volúmenes/hora para el refresco masivo. Requiere clave de API.

**Lectura para ZascArr.** Kapowarr demuestra que una sola fuente basta para un catálogo
angloparlante, y que **exportar** ComicInfo desde la base local es barato. No demuestra nada sobre
la edición española: no tiene país/idioma y nunca los pidió. Su exportación es más pobre que la de
ZascArr (B6): sobrescribe el XML y no conserva campos de procedencia desconocida.

### 2.2 ComicTagger — plugins, Comic Vine incluido y GCD por volcado local

**Arquitectura.** `comictalker` descubre «talkers» por entry point. El único talker incluido en el
paquete es Comic Vine (`setup.cfg:71-72`). El resto se instala como plugin local. La GUI avisa de
que «the Metron is not supported anymore and the GCD plugin is no longer bundled»
(`comictaggerlib/taggerwindow.py:418-424`).

**Comic Vine.** El talker pide búsqueda, serie y número; usa la clave del usuario. Su limitador
propio es **100 peticiones/hora** por defecto y **200/hora** si se configura
(`comictalker/talkers/comicvine.py:162-165`), más 1 petición cada 10 s. La GUI/CLI puede hacer
auto-tagging por comparación de imágenes, que es costoso en CPU pero no añade una fuente nueva.

**GCD.** No se scrapea `comics.org` para metadatos. El plugin `gcd-talker` (extra `gcd` del
paquete, `setup.cfg:76-90`) requiere que el usuario:

1. cree una cuenta en GCD;
2. descargue el **volcado SQLite** de `https://www.comics.org/download/` (sin imágenes ni URLs de
   imagen);
3. apunte el plugin a ese fichero.

El talker consulta ese SQLite local, crea índices/FTS5 y **solo** hace HTTP para las portadas:
`GET https://www.comics.org/issue/{id}/cover/4` (`gcd_talker/gcd.py:629-636`), con un limitador de
10 peticiones/10 s (`gcd_talker/gcd.py:90`). Es decir: **no hay scraping de fichas de metadatos**;
sí hay scraping de portadas, y el propio README avisa de que Cloudflare puede impedirlo.

**Metron.** Se retiró el 2025-09-02 (`comictagger/comictagger#783`): «ComicTagger has been causing
problems for Metron so the simplest thing I can do is remove support for it». En `main` hay un
bloqueo explícito que elimina cualquier plugin Metron local (`comictaggerlib/main.py:129-147`) y
recomienda Metron-Tagger o Perdoo. No es una fuente disponible en la práctica.

**ComicInfo.xml.** Es una referencia de facto del formato:

- Lee y escribe **ComicRack** (`ComicInfo.xml`) y **ComicBookLover** (ZIP comment),
  `comicapi/tags/comicrack.py:30-38`; también lee/escribe otros tags.
- Estrategia de merge configurable: `--tag-merge` y `--metadata-merge`, por defecto
  **`overlay`** (el dato nuevo pisa el viejo si no está vacío); la alternativa es `add_missing`
  (solo rellena vacíos) (`comictaggerlib/ctsettings/file.py:174-188`; `comicapi/merge.py:10-53`).
- El merge es **por campo**, pero **entre el tag existente y la fuente elegida**, no entre varias
  fuentes a la vez: el usuario elige un talker y descarga; no hay un ranking automático de fuentes.

**Límites y licencias.**

- Código **Apache-2.0**; GCD talker **Apache-2.0**; datos de GCD con la licencia que declare GCD.
- El plugin de GCD atribuye «CCA license» enlazando a **CC BY 3.0**
  (`gcd_talker/gcd.py:103-106`), mientras que `src/zascarr/LEGAL.md` y el cliente de ZascArr citan
  **CC BY-SA 4.0**. La web de GCD no se pudo abrir (403 Cloudflare) el 2026-11-09: la discrepancia
  queda **`[sin verificar]`** y hay que resolverla antes de integrar el volcado.
- El volcado SQLite es grande y de actualización manual; no es un coste de red, pero sí de disco y
  de operación en una Pi.
- Sin clave de Comic Vine, el talker incluido no funciona. Sin volcado de GCD, el plugin de GCD no
  funciona. Metron no está.
- **Ningún talker tiene país/idioma de edición.** Como mucho, el nombre de la serie o del álbum
  sugiere la edición; no hay un campo que permita filtrar «esta es la edición española». Para el
  problema de #135, ComicTagger no aporta criterio nuevo: aporta el formato y el plugin.

**Lectura para ZascArr.** ComicTagger es la mejor referencia de **lectura/escritura de ComicInfo**
con merge por campo y de **plugin externo que usa un volcado** en vez de scraping. También es la
prueba de que una fuente grande (GCD) se puede consumir sin API, a cambio de un fichero local y de
unos términos de datos que hay que respetar.

### 2.3 Calibre y sus addons — el libro, no la grapa

**Calibre base.** El manual de 9.18.0 dice que la descarga de metadatos usa Google Books y Amazon
(`manual.calibre-ebook.com/metadata.html`, consultado 2026-11-09). En el código de 9.18.0 las
fuentes incluidas son:

| Fuente | Capacidad | Qué aporta |
|---|---|---|
| Amazon | `identify`, `cover` | título, autores, editorial, fechas, ISBN/ASIN, portada |
| Google Books | `identify` | título, autores, editorial, fechas, ISBN, descripción |
| Edelweiss | `identify`, `cover` | catálogo editorial, metadatos de libro |
| Open Library | **solo `cover`** | portada por ISBN |
| Google Images | `cover` | portada por búsqueda de imagen |

Ninguna es una base de cómics: no hay concepto de número, edición, variante ni grapa. Calibre
modela `series` + `series_index` y columnas personalizadas; los addons de cómic añaden columnas,
pero no una entidad edición.

**Addons relevantes** (índice público de plugins, consultado 2026-11-09):

| Addon | Versión / fecha | Fuente | Qué hace |
|---|---|---|---|
| **Comicvine** | 0.14.2 · 2023-10-09 | Comic Vine API | descarga metadatos y portadas de Comic Vine; el repositorio `xchewtoyx/calibre-comicvine` es de 2014 (0.11.2, MIT) |
| **Embed Comic Metadata** | 1.6.9 · 2026-07-26 | **ninguna** (solo fichero) | lee/escribe `ComicInfo.xml` y ZIP comment; importa a Calibre; convierte CBR→CBZ; GPL-3.0 |
| **Comicalibre** | 2025-01-29 (GitHub) | Comic Vine API | plugin GUI; exige IDs de volumen/número o un nombre `Título --- v1234 n0023`; **reemplaza** los metadatos; GPL-3.0 |
| **Goodreads** | 1.10.0 · 2026-10-31 | Goodreads | metadatos de libro (ISBN, serie, editorial, portada); no es cómic; GPL-3.0 |

En el índice no hay un plugin llamado exactamente «Comic Metadata»: el addon de cómic es
**Embed Comic Metadata** (dloraine), y **Comicvine** es la fuente de metadatos. **Embed Comic
Metadata** es el más cercano a lo que pide el PO.
No consulta ninguna fuente: lee `ComicInfo.xml`/ComicBookLover del archivo y lo importa a Calibre,
o escribe los metadatos de Calibre en el archivo. Es un **puente de formato**, no un enriquecedor.
Su modelo es el de Calibre: columnas personalizadas para personajes, creadores, arcos, etc.

**Comicvine / Comicalibre** sí son fuentes, pero dependen de Comic Vine y de que el usuario aporte
el ID correcto; no buscan edición española. El plugin `Comicvine` de 2023 es el que sigue en el
índice; el repositorio de 2014 es la versión histórica. **No se ha verificado** que el plugin de
2023 funcione con Calibre 9.18 sin probarlo.

**Lectura para ZascArr.** Calibre no resuelve el problema: su unidad es el libro/tomo, no la grapa,
y sus addons de cómic o son Comic Vine o son un puente de `ComicInfo.xml`. Lo aprovechable es el
**patrón de round-trip** (leer el XML existente, mapear a columnas, escribir sin perder lo manual),
que ZascArr ya mejora en B6 con `locked_fields` y procedencia.

### 2.4 Comparación directa

| Proyecto | Fuente(s) de metadatos | Cómo accede | Campos que guarda | Precedencia | ComicInfo |
|---|---|---|---|---|---|
| **Kapowarr** | Comic Vine | API con clave; 1 req/s | volumen, número, editorial, año, sinopsis, portada | una sola fuente; el refresco pisa | 1.3.2: no lee/escribe; rama: escribe, no lee, sobrescribe |
| **ComicTagger** | Comic Vine incluido; GCD por plugin; Metron retirado | API CV; SQLite local de GCD; portadas por HTTP | serie, número, créditos, personajes, arcos, portada, ISBN (GCD) | talker elegido; `overlay`/`add_missing` por campo | lee y escribe; merge por campo |
| **Calibre + addons** | Amazon, Google, Edelweiss, Open Library (covers); Comic Vine (addon); Goodreads | APIs/scraping de libros; plugin CV | título, autores, serie, ISBN, editorial, portada; columnas de cómic | varias fuentes; el usuario elige; merge por ISBN/título | Embed: lee/escribe; sin fuente online |
| **ZascArr** | CV, AniList, Tebeosfera, GCD | APIs/scraping; una fuente por tradición | serie, número, créditos, personajes, editorial, formato; país/idioma solo como evidencia de detalle | una fuente por serie; locks por campo; `metadata_source` por fila | lee y escribe; `locked_fields` + procedencia (B6) |

**Lo que ningún proyecto hace y ZascArr sí puede hacer.** Ninguno de los tres cruza varias fuentes
para la misma edición con procedencia por campo. Kapowarr no lo necesita (una fuente); ComicTagger
no lo intenta (un talker por operación); Calibre mezcla libros, no ediciones. ZascArr ya tiene el
modelo y el `ComicInfo` para hacerlo, pero hoy enruta una sola fuente por tradición.

---

## 3. Fuentes no contempladas por ZascArr

Criterio de esta sección: **no** basta con que la fuente exista; importa si añade una **edición
española o europea identificable** (editorial + colección + año + número/formato) y si se puede
usar **legal y cortésmente** desde una Pi.

### 3.1 Whakoom — la base española que ZascArr no tiene

**Qué es.** Base colaborativa española de cómics, con fichas de **ediciones/colecciones** y de
**números**, editoriales, autores, portadas y fechas. Es la fuente más cercana al objeto de ZascArr
(tebeo español y europeo publicado en España).

**Qué datos da.** Según sus términos, el usuario rellena nombre, **idioma, editorial**, título,
autores, argumento, **número de publicaciones** y portada; las fichas se organizan en
`/comics/<id>/<slug>/<n>` y `/ediciones/<id>/<slug>`. Los resultados indexados muestran, por
ejemplo, `Blueberry #6 (Norma Editorial)` y `Dragon Ball - Ultimate Edition #34 (Planeta Cómic)`,
es decir, **número + editorial + colección**. Las páginas se abren con login: el intento de abrir
`https://en.whakoom.com/comics/xIvRq/blueberry/6` redirigió a `/login?ReturnUrl=...` el 2026-11-09
(`[sin verificar]` el contenido completo; los títulos y editoriales proceden de los resultados
indexados).

**Acceso.** No hay API pública documentada. `https://api.whakoom.com/v1` responde **404 JSON**
(`No HTTP resource was found...`) y las rutas de documentación probadas (`/docs`, `/swagger`,
`/openapi.json`) también fallan; parece una API interna de la app, no un contrato público. Las
páginas web exigen cuenta y sus términos **prohíben expresamente** «make any automated use of the
system» y «use any software, technology or device to scrape [...] or collect or manipulate data»
(ToS, §5.4).

**Licencia.** La base de datos se declara **CC BY-SA 4.0**, «except for comic images that are the
property of their respective authors and publishers»; Whakoom además **renuncia al derecho de
atribución** (ToS, §4.3). Eso no concede acceso: la licencia de los datos y los términos de uso del
servicio son cosas distintas.

**Cobertura española.** Muy alta para ediciones, colecciones y números; es la que más se parece a
lo que #135 no encontraba en CV. No hay medición propia: **`[sin verificar]`** a nivel de corpus.

**¿Identifica número/edición?** Sí, a nivel de ficha de número y de edición/colección, con
editorial y portada. Es justo la unidad que ZascArr no modela.

**Coste de cortesía.** No hay tasa legal que respetar porque **no hay acceso automatizado
permitido**. Un scraper sería una violación de ToS y una carrera de bloqueos; no es una opción de
producto.

**Veredicto.** **Estudiar un acuerdo de datos/exportación; descartar el scraper.** Es la fuente que
más falta, pero no se puede integrar como las demás. Si Whakoom ofreciera una exportación o una
API, sería la primera candidata.

### 3.2 Metron — API excelente, pero no española

**Qué es.** Base comunitaria de cómics con API REST v1.0, alternativa a Comic Vine. El código es
GPL-3.0; los datos se declaran **CC BY-SA 4.0** en el pie del sitio («except where noted
otherwise»).

**Qué datos da.** Series, números, editoriales, sellos, creadores, personajes, equipos, universos,
arcos, portadas y listas. La serie tiene `language`, `publisher`, `imprint`, `series_type`,
`volume`, `year_began`, `year_end`, `status`, `genres`; **no tiene `country`**. El número tiene
`number`, `name`, `title`, `cover_date`, `store_date`, `price`, `isbn`, `upc`, `page`, `reprints` y
variantes; es un modelo propio, con más campos bibliográficos que el de CV.

**Acceso.** API oficial con autenticación (Basic o token Bearer); todos los endpoints exigen
credenciales (`api/README.md:68-98`). Límites por defecto: **20 peticiones/minuto** y **5 000/día**
por usuario autenticado (`api/RATELIMIT.md:22-27`), con cabeceras y `Retry-After`. El sitio web está
detrás de Anubis (prueba anti-bot) desde este entorno; la API no se ha probado con token
(`[sin verificar]` la respuesta viva).

**Cobertura española.** **Nula por diseño actual.** El formulario de serie solo admite los idiomas
declarados en `settings.LANGUAGES`, que son **inglés e italiano**; cualquier otro produce el error
«Currently only English and Italian language Series are supported»
(`comicsdb/forms/series.py:127-134`; `metron/settings.py:290-293`). No hay campo país. Puede tener
series italianas (Bonelli) y estadounidenses, pero **no ediciones españolas**.

**¿Identifica número/edición?** Número, sí; edición española, no. La edición que modela es la
original en inglés o italiano.

**Coste de cortesía.** Bajo y compatible con la Pi (20/min, 5 000/día), pero exige cuenta/token y
un cliente nuevo. Es la API más «cómoda» de las nuevas.

**Veredicto.** **Estudiar solo para el hueco `fumetti`/italiano o como contraste de CV**; **descartar
para la edición española** mientras no admita series en español. Es la cuarta de la lista, no la
tercera.

### 3.3 Bedetheque / BDGest — la BD europea, sin API y sin licencia clara

**Qué es.** Bedetheque es la base pública de BD francófona (series, álbumes, autores, editoriales,
colecciones, ISBN/EAN, fechas, resúmenes, portadas). BDGest es el software/DB online de gestión de
colecciones asociado; comparten ecosistema.

**Qué datos da.** A nivel de **serie** y de **álbum**: título, tomo, serie, autores, editorial,
colección, ISBN/EAN, fecha de publicación, resumen, géneros, estado y portada. El scraper de
referencia `BedethequeKomga` parsea exactamente esos campos (`bedethequeApi.py:144-258`), lo que
confirma que están en la ficha; no se ha abierto la ficha en vivo.

**Acceso.** **No hay API pública** localizada. El sitio está detrás de Cloudflare: las peticiones a
`bedetheque.com` y `m.bedetheque.com` devolvieron **403 / «Just a moment…»** el 2026-11-09, y su
`robots.txt` declara `Content-Signal: search=yes, ai-train=no, use=reference`. El scraper de Komga
usa **proxies** para «limit the chance of being blacklisted with too many calls», lo que es evidencia
de que el acceso automatizado no es bienvenido. Las CGU de BDGest no se pudieron abrir (403).

**Licencia.** No se localizó una licencia abierta para los datos. `robots.txt` no es una licencia,
pero sí una señal de uso; sin CGU legibles, hay que tratar los datos como **no reutilizables sin
permiso**. **`[sin verificar]`** el texto exacto de las CGU.

**Cobertura española.** No es su foco: cubre BD francófona y europea original; puede tener
ediciones extranjeras, pero no es una fuente de edición española comparable a Tebeosfera o Whakoom.
Sí es buena para **orden de álbumes, autores y editorial original**.

**¿Identifica número/edición?** Álbum/tomo y serie, sí; edición española, no de forma fiable.

**Coste de cortesía.** Alto: sin API, con Cloudflare, sin licencia clara y con terceros usando
proxies. No es un coste de rate limit; es un coste legal y de mantenimiento.

**Veredicto.** **Descartar la integración automatizada; estudiar solo una licencia/exportación de
datos.** No compensa el riesgo para la cobertura española que ya ataca Tebeosfera.

### 3.4 MangaDex — capítulos, no ediciones impresas

**Qué es.** Lector/DB de manga con API pública. Devuelve manga, títulos alternativos, descripciones
(en varios idiomas, incluido `es-la`), autores, artistas, tags, año, estado, portada y listas de
capítulos/volúmenes. No devuelve editorial, ISBN ni edición impresa.

**Acceso.** API pública `https://api.mangadex.org`, sin clave para lectura. Límite global
**~5 req/s por IP**; `User-Agent` obligatorio y no falsificable; no se permite `Via`; hay que
**acreditar a MangaDex** y a los scanlation groups, no poner anuncios y retirar contenido a petición
de un grupo (`api.mangadex.org/docs`, consultado 2026-11-09). El tamaño de página está limitado
(100; algunos feeds 500) y `offset + size <= 10 000`.

**Cobertura española.** Capítulos en español de scanlation, no la edición impresa española. Para
ZascArr, que identifica **números de una edición** (grapa/tomo), no sirve: un capítulo no es un
número de Planeta/Panini.

**¿Identifica número/edición?** Capítulo, sí; edición impresa, no.

**Coste de cortesía.** Bajo técnicamente (5 req/s), pero el contenido es scanlation y la licencia de
los datos no es abierta; hay obligaciones de atribución y retirada.

**Veredicto.** **Descartar para metadatos de edición.** Podría estudiarse como lista de capítulos
para manga, pero AniList ya cubre la serie y el problema de ZascArr es la edición, no el capítulo.

### 3.5 Wikidata — mapa de IDs CC0, no fuente de edición

**Qué es.** Base estructurada de Wikimedia. Todo el dato estructurado es **CC0**; el texto de otros
espacios es CC BY-SA 4.0 (`Wikidata:Licensing`, última edición 2026-09-24).

**Qué datos da.** Etiquetas/alias en varios idiomas, enlaces, y **propiedades de identificador
externo** muy útiles para reconciliar: Comic Vine (`P5905`), GCD serie/issue/publisher/creator
(`P3589`, `P11308`, `P9432`, `P9707`), BDGest serie/autor (`P8619`, `P5491`). También puede tener
editorial, país, fecha de inicio, etc., pero de forma incompleta.

**Cobertura española.** Escasa a nivel de unidad editorial. Consulta SPARQL del 2026-11-09:
**250** series de cómic con país de origen España (`P495 = Q29`) y **377** números de cómic
(`P31 = Q140727568`) en toda Wikidata. Son órdenes de magnitud, no un censo; para comparar, GCD
tiene cientos de miles de números. No hay universo `1..N` ni edición española sistemática.

**¿Identifica número/edición?** Como mucho, un ítem suelto; no de forma fiable. Su valor es el
**mapa de IDs** entre CV, GCD y BDGest, no el dato editorial.

**Coste de cortesía.** Bajo; API/SPARQL sin clave, con etiqueta de usuario y sin abusar.

**Veredicto.** **Adaptar como mapa de identificadores y enlaces** (por ejemplo, para reconciliar
`comic_vine_id`/`gcd_id`), **no como fuente de edición**.

### 3.6 Marvel API — Marvel USA, no la edición española

**Qué es.** API oficial de Marvel Comics: cómics, series, creadores, personajes, eventos, historias.
Los cómics traen `issueNumber`, `title`, `description`, `isbn`, `upc`, `ean`, `format`, `pageCount`,
`dates`, `prices`, `creators`, `characters`, `variants`, `collections`.

**Acceso.** Requiere clave pública/privada y hash; el portal `developer.marvel.com` redirige (301) a
`www.marvel.com` y devuelve **403** desde este entorno el 2026-11-09. La documentación se consultó en
la copia de Wayback del **2025-10-08**; el gateway `gateway.marvel.com/v1/public/comics` responde
**500** sin clave. La disponibilidad actual del portal queda **`[sin verificar]`**; la API se ha
usado históricamente con normalidad.

**Límites y términos.** **1 000 llamadas/día** por defecto (algunos servicios varían); atribución
«Data provided by Marvel. © 2014 Marvel» en cada pantalla; enlace a Marvel cuando se muestra algo
más que título y miniatura; caché de 24 h orientativa, no indefinida
(`developer.marvel.com/documentation/attribution`, Wayback 2025-10-08).

**Cobertura española.** Solo Marvel USA. No incluye Panini España, ni la edición española, ni el
precio/número de la grapa española. Para ZascArr no añade nada que Comic Vine no tenga.

**¿Identifica número/edición?** Número USA sí; edición española no.

**Veredicto.** **Descartar** para la edición española; si algún día se enriquece el universo Marvel
USA, Comic Vine ya lo cubre.

### 3.7 Open Library — ISBN y tomos, no grapas

**Qué es.** Proyecto de Internet Archive con API de búsqueda, obras, ediciones, autores y portadas.
Aporta título, autores, editorial, año, idioma, ISBN y portada por ISBN.

**Acceso.** API pública; **1 req/s** sin identificar y **3 req/s** con `User-Agent` + email; no se
debe usar como backend masivo ni raspar HTML; para volumen, usar los dumps mensuales
(`openlibrary.org/developers/api`, consultado 2026-11-09). No requiere clave.

**Licencia.** Internet Archive «does not assert any new copyright or other proprietary rights» sobre
la base, pero «there may be existing rights issues on some contributions»; no es CC0 y no garantiza
que cada edición sea reutilizable (`openlibrary.org/developers/licensing`). Para caché local privada
es aceptable; para redistribuir, hay que mirar caso a caso.

**Cobertura española.** Sorprendentemente útil para **tomos con ISBN**: la búsqueda devuelve, por
ejemplo, *Blueberry* de Norma Editorial con ISBN `9788484315582` y *Dragon Ball Super* de Planeta
Cómic con ISBN `9788491746461`. No tiene grapas ni número de publicación; su unidad es la edición
de libro.

**¿Identifica número/edición?** Edición/tomo por ISBN, sí; número de grapa, no. Es la vía natural
para llenar `Issue.isbn` y para portadas de tomos que no estén en Tebeosfera/GCD.

**Coste de cortesía.** Bajo; 1-3 req/s, con `User-Agent` identificado. No requiere clave ni cuenta.

**Veredicto.** **Adaptar como fuente complementaria de ISBN/tomos y portadas**, no como sustituto de
Tebeosfera/GCD para grapas. Es la más barata de probar y la que menos riesgo legal tiene de las
nuevas, siempre que se respete el no-bulk y la identificación.

### 3.8 Otras que aparecieron

- **League of Comic Geeks:** su API solo está disponible para retailers; Metron la descarta
  explícitamente por eso (`Metron/README.md`). **Descartar.**
- **ComicBookDB:** proyecto histórico, sin API viva localizada; **`[sin verificar]`**.
- **Google Books:** ya lo usa Calibre; sirve para ISBN/tomos, no para grapas; no se propone como
  fuente nueva.
- **ISBNdb / bases comerciales:** de pago; no encajan con el coste de cortesía ni con la licencia.

---

## 4. Matrices

### 4.1 Fuente × proyecto (quién la usa)

**4.1 responde «quién la usa»; 4.2, «qué dato, acceso y licencia».** Juntas forman la matriz
fuente × proyecto × dato × acceso × licencia que pide la ficha.

Símbolos: **✓** uso directo; **~** plugin/extra o uso parcial; **✗** no la usa.

| Fuente | Kapowarr | ComicTagger | Calibre + addons | ZascArr | Nota |
|---|---|---|---|---|---|
| **Comic Vine** | ✓ única | ✓ incluida | ~ plugin `Comicvine`/`Comicalibre` | ✓ | la base de los tres proyectos |
| **GCD** | ✗ | ~ plugin externo (volcado SQLite) | ✗ | ✓ (solo Descubrir) | ComicTagger no la trae de serie |
| **AniList** | ✗ | ✗ | ✗ | ✓ | solo serie, no edición |
| **Tebeosfera** | ✗ | ✗ | ✗ | ✓ | scraping cortés; edición ES |
| **Whakoom** | ✗ | ✗ | ✗ | ✗ | sin API; ToS prohíbe automatizar |
| **Metron** | ✗ (issue #182 abierta) | ✗ (retirada en #783) | ✗ | ✗ | API con token; sin ES |
| **Bedetheque/BDGest** | ✗ | ✗ | ✗ | ✗ | sin API; Cloudflare |
| **MangaDex** | ✗ | ✗ | ✗ | ✗ | capítulos, no edición |
| **Wikidata** | ✗ | ✗ | ✗ | ✗ | IDs CC0 |
| **Marvel API** | ✗ | ✗ | ✗ | ✗ | Marvel USA |
| **Open Library** | ✗ | ✗ | ~ solo portadas en Calibre | ✗ | ISBN/tomos |

### 4.2 Fuente × qué dato × acceso × licencia × cobertura × coste

| Fuente | Qué dato | Acceso | Licencia / términos | Cobertura ES | Coste de cortesía | ¿Número / edición? |
|---|---|---|---|---|---|---|
| **Comic Vine** | serie, volumen, número, créditos, personajes, arcos, portada | API con clave (`/api`) | términos de GameSpot/CBS; sin redistribución masiva | serie USA; edición ES **no acreditada** (0/12) | 1 req/s en ZascArr; CV limita por clave | número sí; edición ES no |
| **GCD** | serie/edición, número, país, idioma, formato, créditos, portada (403) | API anónima `/api/`; paginación 50 | datos **CC BY-SA 4.0**; imágenes reservadas | **sí cuando está catalogada** (2 ediciones en #135; 3 en el bloque con Tebeosfera) | **30/h anónima**; 429 con `Retry-After` | edición sí; número parcial |
| **AniList** | serie manga, títulos, sinopsis, portada, capítulos/volúmenes | GraphQL público | términos de AniList | solo serie; sin edición | 1,5 s en ZascArr | no |
| **Tebeosfera** | colecciones/sagas, número, editorial, sello, país, formato, portada | scraping AJAX + fichas | derecho *sui generis*; uso personal; sin redistribuir | **fuerte**; 2/12 verificadas en #135 | 2,5 s mínimo | edición y número sí |
| **Whakoom** | edición/colección, número, editorial, autores, portada | **sin API pública**; login; ToS prohíbe automatizar | base **CC BY-SA 4.0**; imágenes de autores; renuncia a atribución | **muy alta** (fichas ES) | no hay tasa legal: no automatizable | **sí** |
| **Metron** | serie, número, editorial, sello, creadores, personajes, portada | API con token; 20/min, 5 000/día | datos **CC BY-SA 4.0**; código GPL-3.0 | **nula**: solo series EN/IT | 20/min · 5 000/día | número sí; edición ES no |
| **Bedetheque/BDGest** | serie/álbum, autores, editorial, colección, ISBN/EAN, fecha, resumen, portada | **sin API**; Cloudflare; robots `use=reference` | **sin licencia abierta localizada**; CGU no accesibles (403) | BD francófona; edición ES no fiable | alto: proxies/bloqueos; no sostenible | álbum sí; edición ES no |
| **MangaDex** | manga, títulos, descripciones `es-la`, autores, tags, portada, capítulos | API pública; 5 req/s | acceptable use: atribución, sin ads, retirada de scanlations | capítulos ES de scanlation; no edición impresa | ~5 req/s | capítulo sí; edición no |
| **Wikidata** | etiquetas, alias, enlaces, IDs externos (CV/GCD/BDGest) | API/SPARQL; CC0 | **CC0** (dato estructurado) | 250 series ES y 377 números en total (orden de magnitud) | bajo; etiqueta de usuario | no fiable |
| **Marvel API** | cómics USA, series, creadores, personajes, ISBN/UPC, formato | API con clave; 1 000/día | términos Marvel; atribución + enlace; caché 24 h | **solo Marvel USA** | 1 000/día | número USA sí; edición ES no |
| **Open Library** | obra/edición, ISBN, editorial, año, idioma, portada | API; 1 req/s (3 con UA+email) | IA no reclama copyright nuevo; derechos de terceros posibles | **tomos ES con ISBN**; no grapas | 1-3 req/s | ISBN/tomo sí; grapa no |

### 4.3 Capacidad por unidad editorial (solo fuentes nuevas y las cuatro de ZascArr)

Símbolos: **S** = método/estructura que permite identificarlo; **P** = parcial o con otra petición;
**—** = no aplica o no hay método.

| Fuente | Serie | Edición | Número | Formato | Campo |
|---|---|---|---|---|---|
| Comic Vine | S | — | S | — | S |
| GCD | S | S | S | S | S |
| Tebeosfera | S | S | S | S | S |
| AniList | S | — | — | — | S |
| **Whakoom** | S | S | S | S | S |
| **Metron** | S | P (solo idioma EN/IT) | S | S | P |
| **Bedetheque/BDGest** | S | S | S | S | S |
| **MangaDex** | S | — | P (capítulo) | P (serialización) | S |
| **Wikidata** | P | — | P | — | P |
| **Marvel API** | S | P (USA) | S | S | P |
| **Open Library** | S | S (tomo/ISBN) | — | P | S |

**Lectura.** Solo **Whakoom, Bedetheque y Open Library** añaden una unidad de edición que ZascArr no
tenga ya cubierta por Tebeosfera/GCD, y cada una con un coste distinto: Whakoom no es accesible,
Bedetheque no es legalmente claro, Open Library no tiene grapas. Metron añade número, pero no
edición española.

---

## 5. Veredictos por fuente

| Fuente | Veredicto | Motivo | Coste | Qué la cambiaría |
|---|---|---|---|---|
| **Comic Vine** | **Adaptar / mantener** | ya integrada y con número/créditos; no tiene país/idioma/formato y su volumen ES es la edición USA | ya integrada; 1 req/s | que CV modele edición o que GCD/Tebeosfera cubran el caso |
| **GCD** | **Adoptar / adaptar** | única con país e idioma como campos y edición ES cuando está catalogada; cuota 30/h | ya integrada; paginar y cachear | que la cuota suba o que el volcado local sea viable en la Pi |
| **AniList** | **Mantener** | solo serie manga; no compite en edición | ya integrada | nada: su unidad no es la edición |
| **Tebeosfera** | **Construir sobre lo propio** | la mejor para edición ES; el límite es la selección/recall, no el parser | ya integrada; 2,5 s | mejorar ranking/paginación; no necesita fuente nueva |
| **Whakoom** | **Estudiar (acuerdo) / descartar scraper** | cobertura ES única, pero ToS prohíbe automatizar y no hay API pública | alto: acuerdo o exportación | una API/licencia o una exportación autorizada |
| **Metron** | **Estudiar (fumetti) / descartar para ES** | API excelente y CC BY-SA; solo EN/IT, sin país | medio: cuenta/token + cliente | que admita series en español |
| **Bedetheque/BDGest** | **Descartar automatización / estudiar licencia** | BD europea muy buena, pero sin API, Cloudflare y sin licencia clara | alto: legal + mantenimiento | una API/licencia de datos |
| **MangaDex** | **Descartar** | capítulos de scanlation; no edición impresa; obligaciones de retirada | bajo técnico, alto legal | nada mientras ZascArr identifique ediciones |
| **Wikidata** | **Adaptar (mapa de IDs)** | CC0 y enlaces CV/GCD/BDGest; datos de edición escasos | bajo | más ítems de edición y números |
| **Marvel API** | **Descartar** | solo Marvel USA; CV ya lo cubre; sin edición ES | bajo | nada para el problema actual |
| **Open Library** | **Adaptar (ISBN/tomos)** | ISBN y tomos ES, bajo coste; no grapas | bajo: 1-3 req/s | que cubra más cómics y números |

---

## 6. Recomendación para ZascArr (3-5 líneas)

1. **El problema no es la falta de fuentes, es la selección:** CV no modela la edición española;
   Tebeosfera y GCD sí la acreditan cuando se pagina, se filtra por país/año y se ordena antes de
   recortar. Cerrar eso primero.
2. **Open Library** es la única fuente nueva que se puede pilotar ya: barata, sin clave, con ISBN y
   tomos españoles; llena `Issue.isbn` y portadas de tomos, pero no resuelve grapas.
3. **Whakoom** es la que más falta por cobertura, pero solo con acuerdo/exportación autorizada;
   un scraper viola sus términos y no es una opción de producto.
4. **Bedetheque/BDGest y Metron** quedan para estudio: la primera no tiene API ni licencia clara;
   el segundo no admite series en español. **MangaDex, Wikidata y Marvel** no resuelven edición.
5. **No sumar una quinta fuente antes de arreglar ranking, paginación y procedencia por campo:**
   sin eso, cada fuente nueva añade ambigüedad y coste de cortesía, no aciertos.

---

## 7. Evidencia, límites y caducidad

### 7.1 Qué se abrió y qué no

| Comprobación | Resultado (2026-11-09) |
|---|---|
| `developer.marvel.com/documentation/*` | 301 a `www.marvel.com`; 403 desde este entorno. Docs leídas en Wayback 2025-10-08 |
| `gateway.marvel.com/v1/public/comics` sin clave | HTTP 500 `Internal server error` |
| `www.comics.org/` y `/download/` | 403 Cloudflare; no se pudo verificar la licencia actual en el sitio |
| `www.bedetheque.com` y `m.bedetheque.com` | 403 Cloudflare / «Just a moment…»; CGU de BDGest no accesibles |
| `en.whakoom.com/comics/...` | 302 a `/login`; ficha no visible sin cuenta |
| `api.whakoom.com/v1`, `/docs`, `/swagger` | 404 JSON «No HTTP resource was found…»; no hay API pública documentada |
| `metron.cloud` | Anubis (prueba anti-bot) en la web; API no probada con token |
| Wikidata SPARQL | 250 series ES; 377 números de cómic (consulta propia) |
| Open Library Search API | devuelve tomos ES con ISBN (Blueberry/Norma, Dragon Ball/Planeta Cómic) |

### 7.2 Límites de esta ficha

- **No se ha medido cobertura nueva**: no se ha ejecutado un corpus contra Whakoom, Metron,
  Bedetheque, MangaDex, Wikidata, Marvel ni Open Library. Los juicios de cobertura son
  estructurales (qué campos y qué unidad modela cada fuente), no una medición como #135.
- **No se ha probado Calibre 9.18 con los plugins**: la compatibilidad del plugin `Comicvine` de
  2023 con la versión actual queda **`[sin verificar]`**.
- **No se ha probado la API de Metron con token** ni la de Marvel con clave; se han leído contratos
  y documentación, no respuestas autenticadas.
- **La licencia de GCD tiene una discrepancia** (3.0 en el plugin, 4.0 en ZascArr/LEGAL) que hay que
  resolver antes de usar su volcado.
- **Whakoom y Bedetheque pueden cambiar sus términos**; la fecha de consulta es la única garantía.
- **No es asesoramiento jurídico.** La decisión de integrar una fuente con ToS restrictivos
  corresponde al PO y, si hace falta, a quien asesore legalmente al proyecto.

### 7.3 Caducidad

Esta ficha caduca el **2027-01-08** (≈60 días), o antes si cambia una de las fuentes, si el PO
decide una integración o si #135 cambia el contrato de selección.

---

## Appendix — Reproducible (lectura, sin credenciales)

```text
# Wikidata: series de cómic con país de origen España
SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {
  ?s wdt:P31/wdt:P279* wd:Q14406742 .
  ?s wdt:P495 wd:Q29 .
}
# -> 250 (2026-11-09)

# Wikidata: números de cómic
SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE { ?s wdt:P31 wd:Q140727568 . }
# -> 377 (2026-11-09)

# Open Library: tomos españoles por editorial
GET https://openlibrary.org/search.json?q=title%3A%22Blueberry%22+publisher%3ANorma&limit=3
GET https://openlibrary.org/search.json?q=title%3A%22Dragon+Ball%22+publisher%3APlaneta&limit=3

# MangaDex: ficha de manga (sin clave)
GET https://api.mangadex.org/manga?title=Dragon%20Ball&limit=1

# Metron / Whakoom / Bedetheque / Marvel: solo lectura de documentación;
# las páginas con login/Cloudflare/Anubis no se han sorteado.
```

**Regla de esta ficha:** ninguna fuente se ha activado en ZascArr, no se ha usado ninguna clave y no
se ha descargado ningún volcado. Las comprobaciones HTTP son GET de lectura y no se han repetido
para evitar carga innecesaria.
