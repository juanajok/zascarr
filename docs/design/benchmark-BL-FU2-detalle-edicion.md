# Benchmark BL-FU2 — método de detalle de edición (historia #465)

> **Ficha de benchmarking** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Historia:** #465 «[BL-FU2] Detalle de edición: resolver editorial, año y número» (L · P1).
> **Fecha:** 2026-11-07. **Base contrastada:** `origin/main` `89a165e`.
> **Nivel 2** (fija el contrato de un método nuevo sobre fuentes externas; no toca modelo).
> **Autor:** SCOUT.bench. **Esto es insumo, no aprobación:** decide el PO.

## 0. Resumen para el PO

1. **Tebeosfera sí tiene detalle de edición**: la ficha de **colección** devuelve editorial
   (entidad + sello), año, numeración, formato y país en **una petición**; el idioma **no**
   consta como campo. La ficha de **saga** no sirve para esto (es nivel obra).
2. **Comic Vine sí tiene detalle de volumen**, pero indexa **la edición que Comic Vine tiene**,
   que para los casos del corpus es la estadounidense (Dragon Ball = Viz, 2003, 16), no la
   española. No tiene campo `format` ni país/idioma. Sirve de contraste, no de resolución.
3. **GCD no es «descartable»**: su detalle de serie ya trae editorial, año, formato, país e
   idioma, y la propia búsqueda los devuelve. Lo que falló en #135 fue **seleccionar el
   candidato** (sin filtro de idioma), no el detalle. Su cobertura de las ediciones ES
   probadas es escasa.
4. **AniList y la ficha de saga de Tebeosfera: descartar** para edición (nivel obra).
5. **Coste:** el detalle exige **+1 petición por candidato** (Tebeosfera 2,5 s). La ficha de
   colección de Tebeosfera es el único método que llena editorial + año + número + formato de
   la edición española.

## 1. Problema local

**Historia.** El piloto de #135 midió **0 de 12** ediciones españolas resueltas
(`docs/design/piloto-cobertura-2026-11-06.md` §3 y §6). Solo se ejercitó `search_series` de
Comic Vine/GCD/AniList y el buscador de colecciones de Tebeosfera; **ningún método de
detalle** estaba integrado. Encontrar «Dragon Ball» no acredita la edición Ultimate de Planeta
de 2006.

**Casos reales del corpus** (`docs/design/corpus-cobertura-v1.json`, acreditados por el PO):

| Caso | Etiqueta acreditada | Unidad |
|---|---|---|
| ES-018 | Tintín *El país del oro negro*, Juventud, 1989, **nº 15**, cartoné | número |
| ES-019 | Astérix *y los godos*, Salvat, 2011, **nº 3**, álbum | número |
| ES-007 | Dragon Ball, Planeta DeAgostini, **2006**, Ultimate (34 tomos) | serie/edición |

**Comportamiento actual del código** (verificado en `89a165e`):

- `services/comic_vine.py`: `search_series` pide `id,name,description,image,start_year,count_of_issues,site_detail_url`
  — **sin** `publisher`. Existe detalle de número (`get_issue_detail`, `/issue/4000-{id}/`) y
  `find_issue` (filtro `volume` + `issue_number`), pero **no existe `get_volume`**.
- `services/tebeosfera.py`: solo buscar; `_parse_results` **borra** el sufijo
  `(año, editorial)` del título (`_TITLE_SUFFIX_RE`) y guarda del texto de la fila solo
  `start_year` y `count_of_issues`. Nunca pide la ficha.
- `services/gcd.py`: `search_series` pide `/series/name/{q}/` y **solo mapea**
  `year_began/language/country`; la respuesta ya trae `publisher`, `publishing_format`,
  `binding`, `issue_descriptors` y `active_issues`, que quedan en `raw` sin uso.
- `services/anilist.py`: solo serie, declarado en su docstring.
- `services/estados_fuentes.py`: la única capacidad verificada es `busqueda`; un detalle
  necesitará su propia capacidad y estados (decisión de la spec, no de esta ficha).

**Resultado deseado.** `detalle(candidato) → {editorial, año, número, formato, país, idioma}`
con `campo_ausente` por separado, **+1 petición por candidato**, pasando por
`pedir_con_cortesia` (#134).

## 2. Evidencia

Todo lo marcado «observado» se abrió el **2026-11-07** con `User-Agent` propio y, en
Tebeosfera, con el `Referer`/`Accept-Language` del cliente real. Lo que exige clave de Comic
Vine y no se pudo abrir va marcado `[sin verificar]`.

### 2.1 Comic Vine

**Documentación oficial** — <https://comicvine.gamespot.com/api/documentation> (HTTP 200,
abierta; la ruta correcta es `/api/documentation`, no `/api/documenters/`). Campos declarados:

- recurso **`volume`**: `aliases`, `api_detail_url`, `character_credits`, `concept_credits`,
  `count_of_issues`, `date_added`, `date_last_updated`, `deck`, `description`, `first_issue`,
  `id`, `image`, `last_issue`, `location_credits`, `name`, `object_credits`, `person_credits`,
  **`publisher`**, `site_detail_url`, `start_year`, `team_credits`.
  **No hay `format`, ni `country`, ni `language`.**
- `publisher`: «The primary publisher a volume is attached to.» El recurso **`publisher`**
  declara `name`, `location_address`, `location_city`, `location_state`… **tampoco `country`**.
- recurso **`issue`**: `issue_number`, `cover_date`, `store_date`, `volume`, `person_credits`…
  **sin `format` y sin `publisher` directo** (el `volume` es una referencia).
- detalle: la doc declara el campo `api_detail_url` («URL pointing to the volume detail
  resource») pero **no imprime la ruta**. La forma canónica es `/volume/4050-{id}/`; el id de
  volumen de Comic Vine es el `4050-…` de la web y el cliente ya usa el análogo
  `/issue/4000-{id}/`. **`[sin verificar: respuesta real de /volume/4050-XXXX/ — requiere clave]`**

**Evidencia de qué edición indexa Comic Vine** (espejo público de sus datos, Kaboom,
<https://kaboom.rocks/comics/176>): el volumen de Comic Vine enlazado es
<https://comicvine.gamespot.com/dragon-ball/4050-31306/> y muestra **«Started in 2003»,
«Published by Viz», «16 issues», «Manga»**, con la sinopsis «The English translation of the
Japanese manga Dragon Ball… published … by Viz». Es decir: el volumen «Dragon Ball» de Comic
Vine es **la edición USA de Viz**, no la Ultimate de Planeta (2006, 34 tomos) del corpus
ES-007. El detalle devolvería `publisher=Viz`, `start_year=2003`, `count_of_issues=16` →
comparado con la etiqueta, `incorrecto` (difiere), no `ambiguo`.

*Corroboración terciaria* (no oficial, <https://pipeworx.io/docs/reference/comicvine/volume/>):
describe el detalle de volumen como «name, start year, publisher, issue count, deck
description» — coincide con los campos de la doc.

**Código de referencia:** el cliente de Mylar
(<https://raw.githubusercontent.com/evilhero/mylar/8a5443814409da47b3e2c399747d7c150da61cbd/mylar/cv.py>)
llama a `/volume/{id}/` con `field_list=name,count_of_issues,start_year,last_issue,site_detail_url,image,publisher`,
lo que confirma que `publisher` es un campo pedible del detalle de volumen. (Solo se leyó para
contrastar el contrato; no se copia nada.)

**Conclusión Comic Vine.** El detalle de volumen existe y da editorial + año + recuento. **No
da formato ni país/idioma**, y el volumen que devuelve es el de *su* edición. Para el corpus,
sirve como **contraste** (detectar que la fuente no tiene la edición española) más que como
resolución.

### 2.2 Tebeosfera

Peticiones reales: **3** (una de tanteo y dos de ficha), espaciadas ≥ 3 s, con el
`User-Agent`/`Referer`/`Accept-Language` del cliente. No se pidió nada más.

| URL | Resultado |
|---|---|
| `/colecciones/bola_de_drac_1992_planeta-deagostini_-col._superior-.html` | HTTP 200, ~31,6 KB |
| `/sagas/dragon_ball_1984_toriyama.html` | HTTP 200, 25,2 KB |

**Ficha de colección** — campos observados (estructura `div.row-fluid`, valores literales):

| Campo de la ficha | Valor observado | ¿Sirve para #465? |
|---|---|---|
| editorial + sello | `<div class="titulo"><a href="/entidades/grupo_planeta.html">Grupo Planeta</a> : <a href="/entidades/planeta_deagostini.html">Planeta DeAgostini</a></div>` | **sí**: editorial y sello, con enlace estable; **no** va etiquetado «Editorial» |
| país | bandera `…/banderas/spain.png` con `title="España"`; ciudad «BARCELONA» en `div.subtitulo` | **sí** (bandera + ciudad), no es un campo de texto |
| fechas | `Fechas: IV-1992 - III-1995` | **sí** (rango mes-año; el año está en el título `(1992, PLANETA-DEAGOSTINI)`) |
| números | `Números: 153 ordinarios (271 catalogados)` · `Numeración: 1 a 153` | **sí**: numeración de la edición |
| formato | `Formato: CUADERNO / GRAPA [ 1-153]` | **sí**: formato físico de la edición |
| paginación | `Paginación: 36 pp. · 32 pp. · 40 pp. …` | no pedido; refuerza el formato |
| periodicidad | `Edición: Semanal` | no es editorial; es frecuencia |
| vinculación | `Vinculación: BOLA DE DRAC (2006, PLANETA-DEAGOSTINI) -EDICIO DEFINITIVA-` | enlace a otra colección (útil para navegar ediciones) |
| idioma | **no hay campo** (`0` ocurrencias de «Idioma»); solo prosa: «Traducción al catalán…» | **`campo_ausente`** |
| números enlazados | **153** enlaces `/numeros/bola_de_drac_1992_planeta-deagostini_N.html` (1…153), más 213 de otras colecciones (bloques de afines y vinculadas) | permite mapear número → ficha sin otra petición |

**Ficha de saga** (misma sesión) — `TÍTULOS` (alias), `Creadores`, `Génesis: XI-1984 ·
SHUEISHA : SHONEN JUMP`, `Estreno: POKER (1991, POKER) 1 1991`, `Evolución: Cronológica ·
519 Entregas`, `Raíces`. **No** da editorial de la edición española, ni formato, ni
numeración de una edición; solo 2 enlaces a `/colecciones/` y ambos al índice. Es nivel
**obra**, no edición → no sirve como método de detalle de #465.

**Búsqueda ya documentada.** El fixture real
`docs/design/fixtures-cobertura/tebeosfera_dragon_ball_2026-11-06.html` muestra que la fila de
resultado ya lleva `BOLA DE DRAC (1992, PLANETA-DEAGOSTINI) -COL. SUPERIOR-`, `IV-1992 a
III-1995` y `153 números`: **editorial y año ya vienen en la búsqueda**, pero
`_TITLE_SUFFIX_RE` los tira. El detalle solo es imprescindible para formato, numeración,
sello y país.

**Diagnóstico previo** (`diagnostico-tebeosfera-135-2026-11-06.md`): el buscador devuelve 83
filas y pone resultados ajenos antes que la coincidencia. Eso es **selección de candidato**
(decisión del PO, otra historia), no un fallo del parser ni de la ficha.

### 2.3 GCD (Grand Comics Database)

**Verificado en vivo el 2026-11-07** (API anónima, `Accept: application/json`):

`GET /api/series/224764/` → HTTP 200:

| Campo | Valor |
|---|---|
| `name` | `Absolute Batman` |
| `year_began` | `2025` |
| `publisher` | `https://www.comics.org/api/publisher/3932/` (**URL**, no nombre) |
| `language` / `country` | `es` / `es` |
| `publishing_format` / `binding` | `serie regular` / `grapa` |
| `issue_count` | **`null`** |
| `active_issues` | 14 URLs de número (`…/issue/2746364/`…) |
| `issue_descriptors` | `["1" … "14"]` |
| `dimensions`, `color`, `paper_stock` | `17 cm x 26 cm`, `color`, `satinado` |

`GET /api/publisher/3932/` → `name: "Panini España"`, `country: "es"`. Por tanto el nombre de
la editorial exige **una petición más**; el país viene ya en la serie.

La ficha **E7** (`docs/design/benchmark-E7-gcd-api.md`, verificada el 2026-09-28) ya dejó
acreditado que `/series/name/Absolute Batman/` devuelve **30 ediciones separables por
`language`/`country`/`publisher`**, incluida la Panini España `224764`, y que el detalle de
número (`/api/issue/<id>/`) trae `number`, `variant_of` y `cover` (portada 403), con datos de
número esqueléticos.

**Cobertura de los casos del corpus** (búsquedas en vivo, 2026-11-07; la API devolvió 50
resultados por página):

| Consulta | Resultados totales | Ediciones `es/es` en la 1.ª página | ¿Está la del corpus? |
|---|---:|---|---|
| `Dragon Ball` | 98 | 1 (`Dragon Ball`, 2015, publisher 8999, **mx**) | **no** (no hay Planeta 2006) |
| `Tintin` | 145 | 3 (1958, 1967, 1981) | **no** (no hay Juventud 1985) |
| `Astérix` | 189 | 1 (`Astèrix`, 1980, cartoné) | **no** (es catalana, no Salvat 2011) |

**Conclusión GCD.** El **detalle de serie sí da edición española** cuando la edición está
catalogada: editorial (URL → nombre), año, formato (`publishing_format` + `binding`), país e
idioma. Y **no hace falta pedir detalle**: esos campos ya vienen en cada resultado de
`/series/name/`. Lo que falla en #135 es que el cliente no filtra `country == "es"` ni ordena
por país/idioma antes de recortar a 10, así que devuelve la edición francesa de Thorgal. **El
detalle no es el hueco; el hueco es selección de candidato** — y la cobertura de las ediciones
concretas del corpus es escasa. `issue_count` es `null` (no sirve como «número»);
`issue_descriptors`/`active_issues` sí listan números, sin recuento fiable (E7).

### 2.4 AniList

**Documentación oficial del objeto `Media`** — <https://docs.anilist.co/reference/object/media>
(HTTP 200, abierta). Campos relevantes: `format` («The format the media was released in»,
enum `MediaFormat`), `countryOfOrigin` («Where the media was created»), `startDate`,
`chapters`, `volumes`, `staff`, `studios`. **No hay `publisher`**, ni edición, ni datos por
tomo. `format` describe la obra (MANGA/ONE_SHOT/NOVEL), no el formato de la edición española;
`countryOfOrigin` es el país de creación (JP), no el de publicación de la edición.

**Cliente** (`services/anilist.py`): ya declara alcance solo-serie y el piloto dio 1/10
respuestas. **Conclusión: descartar para detalle de edición.**

## 3. Matriz fuente × campo

Símbolos: **✓** el método lo da tal cual; **~** lo da parcial o requiere otra petición/mapeo;
**✗** no lo da. «Peticiones» = desde cero para llenar editorial + año + número + formato de un
candidato (búsqueda incluida).

| Método | editorial | año | número | formato | país / idioma | Peticiones | Veredicto |
|---|---|---|---|---|---|---|---|
| **CV** `search_series` (actual) | ✗ | ✓ | ~ (`count_of_issues`) | ✗ | ✗ / ✗ | 1 (1,0 s) | insuficiente |
| **CV** `get_volume` (`/volume/4050-…/`) | ✓ `publisher` | ✓ `start_year` | ~ (`count_of_issues`, `first_issue`/`last_issue`; sin lista) | ✗ | ✗ / ✗ | 2 (2,0 s) | **adaptar** (contraste; edición USA) |
| **CV** `get_issue` (`/issue/4000-…/`) | ✗ (solo `volume` ref.) | ~ `cover_date` | ✓ `issue_number` | ✗ | ✗ / ✗ | 2 (2,0 s) | adaptar (para el número) |
| **Tebeosfera** búsqueda (actual) | ~ (texto en el título, **se descarta**) | ✓ | ~ (`N números`) | ✗ | ✗ / ✗ | 2 (5,0 s) | construir sobre lo propio |
| **Tebeosfera** ficha de **colección** | ✓ entidad + sello | ✓ `Fechas` + título | ✓ `Numeración 1 a N` + N enlaces | ✓ `CUADERNO / GRAPA` | ✓ bandera / ✗ | **3** (7,5 s) | **adoptar** |
| **Tebeosfera** ficha de **saga** | ✗ (editorial de origen JP) | ~ `Génesis` | ✗ (`519 Entregas`) | ✗ | ✗ / ✗ | 3 (7,5 s) | **descartar** |
| **GCD** detalle de serie (y búsqueda) | ~ (`publisher` = URL) | ✓ `year_began` | ~ `issue_descriptors` (`issue_count` null) | ✓ `publishing_format` + `binding` | ✓ `country` / ✓ `language` | **1** (+1 si se quiere el nombre de la editorial; 2,0 s/petición) | **adaptar** |
| **GCD** detalle de número | ✗ | ~ | ✓ `number` | ✗ | ✗ | 2 | adaptar (número puntual) |
| **AniList** `Media` (detalle) | ✗ | ~ (`startDate` de la obra) | ✗ (`chapters`/`volumes`) | ~ (`MediaFormat` de la obra) | ~ (`countryOfOrigin`) / ✗ | 1 (1,5 s) | **descartar** |

**Lo que la matriz dice de un vistazo:** solo **Tebeosfera colección** llena las cuatro celdas
del enunciado (editorial, año, número, formato) para **la edición española**. GCD llena cinco
(con editorial por resolver) pero solo si la edición está catalogada. Comic Vine llena tres y
de la edición equivocada. AniList no llena ninguna.

## 4. Veredicto por idea

| Idea | Resultado | Motivo |
|---|---|---|
| Ficha de **colección de Tebeosfera** como método de detalle principal | **Adoptar** | Único que da editorial + año + numeración + formato + país de la edición ES, en 1 petición; campos estructurados (`div.row-fluid`, `/entidades/…`). Coste 1 petición por candidato. |
| Recuperar `(año, editorial)` del **título de la búsqueda** de Tebeosfera | **Construir sobre lo propio** | El dato ya viaja en la fila y el cliente lo tira (`_TITLE_SUFFIX_RE`). Recuperarlo ahorra la petición cuando solo se necesitan editorial/año. |
| Detalle de **serie de GCD** como segunda fuente de edición | **Adaptar** | Da editorial (URL), año, formato, país e idioma, y ya en la búsqueda; pero `publisher` es una URL, `issue_count` es `null` y hay que filtrar `country == "es"`. Corrige el diagnóstico: el fallo de #135 es de selección, no de detalle. |
| `get_volume` de **Comic Vine** | **Adaptar** (solo contraste) | Existe y devuelve editorial/año/recuento, pero de la edición USA; sin `format` ni país/idioma. Sirve para acreditar «la fuente no tiene la edición ES» (`incorrecto`), no para resolverla. |
| `get_issue` de **Comic Vine** para el número | **Adaptar** | `issue_number` + `cover_date`; el `format` no existe en la API. Una petición por número. |
| Ficha de **saga de Tebeosfera** | **Descartar** | Nivel obra: editorial de origen (SHUEISHA), `Entregas`, sin formato ni numeración de edición. |
| **AniList** para detalle de edición | **Descartar** | Sin `publisher` ni edición por tomo; `format`/`countryOfOrigin` son de la obra. |
| Campo **`format` de Comic Vine** | **Descartar** | No existe en `volume`, `issue` ni `publisher` según la doc oficial. |
| Inferir idioma/editorial por el título o por el país de la editorial | **Descartar** | Viola «campos ausentes se muestran como no consta» (`discriminantes-publicacion.md` §4.2): el detalle declara `campo_ausente`. |

**Recomendación de orden:** Tebeosfera ficha de colección → GCD serie (filtrada por país) como
contraste → Comic Vine volumen solo como contraste. El idioma se queda en `campo_ausente` en
Tebeosfera y en Comic Vine; solo GCD lo da cuando tiene la edición.

## 5. Coste y cortesía

- **Por celda:** ver la columna «Peticiones» de §3. Para llenar editorial + año + número +
  formato: **Tebeosfera 3 peticiones** (2 de búsqueda + 1 de ficha) ≈ **7,5 s**; **GCD 1-2**
  (búsqueda y, si se quiere el nombre, editorial) ≈ 2-4 s; **Comic Vine 2** ≈ 2 s (sin
  formato); **AniList 1** ≈ 1,5 s (sin nada útil).
- **Por candidato:** el detalle es **+1 petición** en Tebeosfera y Comic Vine, **+0** en GCD
  (los campos de edición ya vienen en el resultado de búsqueda). Con `k` candidatos:
  Tebeosfera `2 + k`; GCD `1 + k` (solo si se resuelve la editorial de cada uno); Comic Vine
  `1 + k`.
- **Cortesía #134:** Tebeosfera mantiene **2,5 s mínimo** por petición y salto, compartido por
  proceso; el detalle debe pasar por `pedir_con_cortesia` como la búsqueda. `espera_max_s` es
  **por llamada** (30 s por defecto): una ficha cabe de sobra, pero una tanda de 10 fichas son
  ≥ 25 s de espera acumulada y debe presupuestarse en quien orqueste (no en el cliente).
- **Presupuesto del banco** (`banco-cobertura-espanola.md` §9): 80 peticiones y 20 por fuente.
  Añadir detalle a los 12 casos: Tebeosfera +12 como máximo, Comic Vine +12, GCD +12 → cabe,
  pero **no** cabe detallar los 10 candidatos de cada caso.
- **Recomendación:** detallar **solo los candidatos que pasen el filtro de título** (top-1 o
  top-2), cachear la ficha por slug/id y no pedir detalle si la etiqueta solo necesita
  editorial + año (ya están en la fila de búsqueda de Tebeosfera).

## 6. Riesgos legales

- **Portadas ©.** La ficha de Tebeosfera declara en su pie: «©1992 / 2026 Los autores y
  editores, o sus herederos legales, por las imágenes.» La ficha de colección trae una galería
  de portadas; **no hace falta descargarla** para el detalle. ZascArr ya cachea portadas para
  uso privado y no las redistribuye (`src/zascarr/LEGAL.md`, filas de portadas y fuentes).
- **Tebeosfera, derecho *sui generis*.** `LEGAL.md` la clasifica como «base de datos protegida
  por derecho *sui generis*; no redistribuir extractos; uso local del usuario». El detalle
  puede cachearse en la BD local y servirse al propio coleccionista desde su instancia, pero
  **no** debe volcarse en masa ni redistribuirse; una petición por candidato y 2,5 s encajan
  con ese uso.
- **Comic Vine, términos propios.** `LEGAL.md`: «Términos de uso propios; API con rate
  limits; no redistribución masiva». El detalle exige **clave** y 1 req/s; no cambia la
  postura.
- **GCD, CC BY-SA 4.0.** Atribución + enlace de vuelta (ya se cumple en `/ui/descubrir`). Si
  el detalle muestra campos de GCD, debe conservar el enlace a la ficha; la licencia cubre los
  **datos**, no las portadas (E7 §3).
- **AniList:** sin uso nuevo.
- **Coste para una asociación sin ánimo de lucro:** el método añade una petición por candidato;
  se mantiene el mínimo de 2,5 s y se evita pedir detalle de todos los resultados.

## 7. Qué NO está verificado (y cómo verificarlo)

1. **Respuesta real de `/volume/4050-XXXX/` de Comic Vine.** No hay `COMICVINE_API_KEY` en este
   entorno (comprobado: ausente). Sin clave, la API devuelve `401`/`status_code 100` para
   cualquier ruta y no distingue el endpoint. **Cómo:** con una clave de lectura, pedir
   `/api/volume/4050-31306/?field_list=id,name,publisher,start_year,count_of_issues,first_issue,last_issue`
   y guardar una fixture saneada; repetir para los tres casos del corpus y anotar
   `publisher`/`start_year`/`count_of_issues`. La ruta exacta con prefijo `4050-` y la forma
   del objeto `publisher` (nombre anidado) quedan **`[sin verificar]`**.
2. **Si Comic Vine tiene alguna edición española de los casos.** **Cómo:** `search` con
   `resources=volume` para Tintín/Astérix/Dragon Ball e inspeccionar `publisher` de cada
   volumen; no se hizo (sin clave).
3. **Ficha de número de Tebeosfera** (`/numeros/…`): no se abrió (tope de cortesía: 3
   peticiones). El docstring del cliente cita un parser de ~700 líneas para la ficha completa
   de un número, pero **no se comprobó en vivo** qué campos da. **Cómo:** 1 petición en una
   ejecución autorizada.
4. **Generalización de la ficha de colección:** se inspeccionó **una** colección. No consta que
   *todas* traigan entidad editorial, bandera de país o `Numeración`; el `Edición: Semanal`
   demuestra que las etiquetas de la ficha no son un contrato. **Cómo:** 2-3 fichas más, de
   estratos distintos (álbum, tomo, grapa).
5. **Ficha de saga:** se inspeccionó **una** (Dragon Ball). Que no dé datos de edición es
   coherente con su vocabulario (`Génesis`, `Entregas`, `Raíces`), pero no se generaliza.
6. **Cobertura de GCD:** las búsquedas devuelven 98/145/189 resultados y solo se miró la
   primera página (50). «No está» significa **«no está en la primera página»**; con paginación
   o filtros de la API podría aparecer. **Cómo:** paginar o probar los filtros de la API de
   series (`?language=es` si existe) para los tres casos.
7. **Fiabilidad de `issue_descriptors`** como «número»: E7 ya documentó que engaña para
   recuentos; no se re-probó con las series ES. **Cómo:** comparar con `active_issues` en una
   serie ES concreta.
8. **Texto exacto de `robots.txt`/ToS de Tebeosfera:** no se descargó (cortesía). La postura
   del proyecto es la de `LEGAL.md`, no una lectura nueva del sitio.

## 8. Casos de prueba antes de implementar

1. Ficha de colección (fixture saneada del HTML real): devuelve editorial + sello, año, rango
   de numeración, formato y país; **idioma = `campo_ausente`**.
2. Ficha de colección sin bloque de entidad → `editorial = campo_ausente` (no se inventa).
3. Ficha de saga → no produce campos de edición (se rechaza como método).
4. Detalle de volumen de Comic Vine (fixture cuando haya clave) → `publisher`, `start_year`,
   `count_of_issues`; `format = campo_ausente`.
5. Detalle de serie de GCD → `country/language/publishing_format/binding`; `issue_count` nulo
   no se convierte en número; el nombre de editorial exige la petición a `/publisher/`.
6. Cortesía: el detalle pasa por `pedir_con_cortesia`, respeta 2,5 s y el presupuesto; fuente
   apagada = cero peticiones.
7. Coincidencia: etiqueta Planeta/2006/34 vs volumen CV Viz/2003/16 → `incorrecto`; ficha que
   coincide en editorial + año + número → `coincidencia_verificada`; dato ausente → `ambiguo`.
8. Mapeo de formato: `CUADERNO / GRAPA` → `single_issue`, `cartoné` → `hardcover`… **no** es
   identidad: el corpus usa `album`/`manga_tankobon` y la fuente usa formato físico; un
   formato sin equivalencia va a `campo_ausente`, no a una suposición.

## 9. IGUALAR / MEJORAR

- **IGUALAR:** un detalle que devuelve exactamente los campos que la fuente tiene, con
  `campo_ausente` explícito y sin inferencias; una petición por candidato.
- **MEJORAR (con evidencia):** ninguna de las referencias de este benchmark resuelve la
  **edición española**: Comic Vine devuelve la USA (Kaboom/CV: Viz 2003), GCD solo si la
  edición está catalogada y su búsqueda no filtra idioma (piloto: Thorgal francés), AniList es
  nivel obra. La ficha de colección de Tebeosfera sí lo hace y **no está integrada**. El
  criterio de «mejor» es comprobable: editorial + año + número + formato de la edición ES en
  una petición, contra 0/12 del piloto.

## 10. Reproducible

- Comic Vine: `GET https://comicvine.gamespot.com/api/documentation` (campos `volume`/`issue`/`publisher`).
- Tebeosfera (3 peticiones, ≥ 3 s entre ellas, con `Referer` y `Accept-Language` del cliente):
  - `GET /colecciones/bola_de_drac_1992_planeta-deagostini_-col._superior-.html`
  - `GET /sagas/dragon_ball_1984_toriyama.html`
- GCD (API anónima, `Accept: application/json`):
  - `GET /api/series/224764/` · `GET /api/publisher/3932/`
  - `GET /api/series/name/Dragon%20Ball/` · `…/Tintin/` · `…/Ast%C3%A9rix/`
- AniList: `GET https://docs.anilist.co/reference/object/media`.

No se repiten las peticiones a Tebeosfera sin autorización; el HTML descargado no se versiona
(no se redistribuye contenido del sitio).

## 11. Caducidad

**~60 días: 2027-01-06**, o antes si cambia la ficha de Tebeosfera, la API de Comic Vine o la
historia #465. La evidencia de campo se tomó el 2026-11-07 sobre `origin/main` `89a165e`.
