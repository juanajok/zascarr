# Fuentes para buscar sagas y órdenes de lectura (BL-D7 / #163)

**Fecha:** 2026-11-14. **Estado:** investigación previa a implementar el modo
«buscar saga en fuentes». No autoriza a scrapear sitios sin API ni a crear
series desde referencias externas.

## Pregunta

El coleccionista quiere buscar una saga o evento en fuentes externas y elegir
su **orden de lectura** para importarlo a ZascArr, en vez de teclearlo a mano.
No basta con que la fuente liste «números que pertenecen al arco»: hace falta
un orden, y que se pueda casar con las series/números locales sin inventar.

## Lo que ya hay en ZascArr

- **C4** permite crear y ordenar sagas a mano (`story_arcs`,
  `story_arc_issues.reading_order`).
- El **enricher de Fandom DC** lee `StoryArcs` de la plantilla del volumen y
  crea/actualiza arcos con sus números locales en orden, pero solo DC y solo
  para series ya vinculadas (`fandom_dc_slug`). No hay búsqueda ni elección.
- **#163** añade «Pedir los números que faltan» a una saga ya existente; no
  busca arcos nuevos.

## Comparativa

| Fuente | ¿Buscar arcos? | ¿Orden de lectura? | Mapeo local | API / coste | Veredicto |
|---|---|---|---|---|---|
| **Fandom DC Database** | Sí, por búsqueda MediaWiki y páginas `Storyline` | Sí: la página del arco lista los números en orden | `fandom_dc_slug` de serie + `issue_number` | API MediaWiki, sin clave; ya hay cliente y cortesía. Texto CC BY-SA 3.0; imágenes *fair use* cacheadas | **Mantener y ampliar** (ya integrado; falta búsqueda explícita) |
| **Metron** | Sí: `/api/arc/?name=…` | **Sí, la mejor**: `reading_list` tiene `order` explícito e `issue_type` (Prologue/Core/Tie-In/Epilogue) y `attribution_source` CBRO/CMRO/CBH/CBT/MG/HTLC/LOCG | `cv_id`/`gcd_id` en series e issues; si no, título+año+número | REST autenticada (cuenta + token/Basic), rate limit; datos con atribución | **Primera fuente nueva recomendada** para órdenes de lectura |
| **Comic Vine** | Sí: `/story_arcs` | No hay campo de orden; el arco trae `issues`, pero sin `reading_order`; ordenar por número/fecha es una aproximación | `comic_vine_id` ya existe en series/issues; API key ya soportada | API key, ~1 req/s; portadas © | **Descubrimiento/membresía**, no orden fiable |
| **Grand Comics Database (GCD)** | No: la API pública solo expone `series` y `publisher` | No | `gcd_id` en Metron/Comic Vine | API limitada; dumps | **No** para arcos/orden |
| **Marvel Comics API** | No hay recurso de «story arc»; su unidad es `story` (portada, interior, texto) | No hay campo de orden de lectura | IDs propios, no los locales | API oficial con clave; límites | **No** para esta función |
| **League of Comic Geeks** | Tiene listas de lectura, pero **no API pública oficial**; el CLI `locg` usa sesión de navegador (Playwright) | Sus listas tienen orden, pero son de usuario | Requiere login/scraping | Sin API estable; riesgo de ToS | **No integrar**; Metron ya atribuye listas LOCG |
| **Comic Book Herald / CBRO / CMRO / CBT / Marvel Guides / How To Love Comics** | Son listas editoriales, no API | Sí, pero en HTML | Habría que scrapear y mapear a mano | Sin API; contenido editorial con derechos | **No scrapear**; usar Metron, que las atribuye |
| **Wikipedia / Wikidata** | Páginas de arcos, datos dispersos | No estructurado | — | API, pero sin modelo de orden | **No** como fuente principal |
| **Tebeosfera / Whakoom** | Fichas de colecciones/sagas en español | No orden de lectura explícito | Tebeosfera ya tiene cliente de scraping; Whakoom sin API | Sin API pública / ToS | **No** para órdenes |
| **AniList / MangaUpdates** | Capítulos de manga | Orden de capítulos, no eventos cross-series | IDs de manga | API | **No** para arcos de cómic |

### Notas de verificación

- **Metron** documenta `GET /api/arc/{id}/issue_list/` para el arco y, sobre
  todo, `GET /api/reading_list/{id}/items/` con `order`, `issue_type` y
  `attribution_source`. La lista de lectura requiere autenticación; el detalle
  de una lista pública es accesible si no es privada. Fuente:
  [documentación de Metron](https://github.com/metron-project/metron/blob/c46a3dcfd8400d6877626e19bb343044ba762d03/api/README.md)
  y [esquema Mokkari](https://mokkari.readthedocs.io/en/latest/mokkari/schemas/reading_list/).
- **Comic Vine** documenta el recurso `story_arc` con `issues`,
  `first_appeared_in_issue` y `count_of_issue_appearances`, pero **sin**
  `reading_order`. Fuente:
  [documentación de Comic Vine](https://comicvine.gamespot.com/api/documentation).
- **Fandom DC** usa `StoryArcs` en la plantilla de volumen y la
  [plantilla de storyline](https://dc.fandom.com/wiki/DC_Database:Storyline_Template)
  para la página del arco; Marvel Database no declara `StoryArcs` en la
  plantilla de volumen (ya comprobado en el cliente actual).
- **GCD** solo publica en su API raíz `series` y `publisher`:
  [api.comics.org](https://www.comics.org/api/). No hay endpoint de arcos.
- **LOCG** no ofrece API pública; el paquete `locg` se autentica con una
  sesión de navegador y cookies, no con una API documentada:
  [locg en PyPI](https://pypi.org/project/locg/).

## Recomendación

1. **Metron como primera fuente nueva**, porque es la única revisada que
   separa «arco» de «orden de lectura» y ofrece el orden explícito, el tipo de
   número y la atribución de la lista. Es también la que permite cubrir Marvel
   y editoriales no DC sin scraping.
2. **Fandom DC como fuente ya integrada**, añadiendo búsqueda explícita de
   sagas para DC; no duplicar su parser.
3. **Comic Vine como descubrimiento**, nunca como orden definitivo: si se usa,
   marcar el orden como «propuesto» y pedir confirmación.
4. **No integrar** GCD, Marvel API, LOCG por scraping ni las webs editoriales.
   Si se necesita su contenido, Metron ya lo agrega con atribución.

## Diseño propuesto del modo «Buscar saga en fuentes»

- Entrada desde **Sagas → «Buscar saga en fuentes»**.
- Selector de fuente (Metron / Fandom DC / Comic Vine) y búsqueda por título.
- Resultado normalizado:
  `titulo, descripcion, fuente, url, issues[{serie_externa, numero, orden, tipo}]`.
- Previsualización: qué números casan con series locales, cuáles no, y qué
  orden se propone. **Nunca crear series automáticamente**; si faltan, se
  importa la parte posible y se dice cuántos quedaron fuera.
- Confirmación explícita; no sobrescribir enlaces manuales sin mostrar
  conflictos; guardar `metadata_` con fuente, URL y fecha de consulta.
- Fuentes apagadas por defecto y con el mismo cliente de cortesía/semáforo.
  Metron requiere credenciales de cuenta; Comic Vine, su API key; Fandom no
  necesita clave pero ya tiene su política.
- Nada de imágenes externas: las portadas siguen saliendo de la caché local.

## Estimación

- **MVP Metron + Fandom DC**: M. Incluye cliente HTTP autenticado, búsqueda,
  normalizador, previsualización, mapeo y confirmación.
- **Añadir Comic Vine**: +S/M (ya hay cliente y claves; orden solo aproximado).
- **Tests**: parsers y normalizador con respuestas grabadas; integración con
  Postgres para el mapeo; ninguna prueba debe llamar a la red en CI.
