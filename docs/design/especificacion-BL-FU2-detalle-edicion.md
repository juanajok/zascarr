# SPEC BL-FU2 — Detalle de edición (#465)

> **Estado:** v1.0, contrato y plan de pruebas. **No implementa código, no activa fuentes, no toca
> el modelo ni crea migración.** Benchmark de partida: [`benchmark-BL-FU2-detalle-edicion.md`](benchmark-BL-FU2-detalle-edicion.md)
> (fusionado en `main` `6f54968`; ficha fechada 2026-11-07 sobre `89a165e`).
> **Base de esta spec:** `origin/main` `6f54968`, worktree `.squad/wt-fu2-spec`.
> **Decide el PO.** Lo que el benchmark no verificó se marca aquí `[sin verificar]` o `NOT RUN`; no se
> rellena por inferencia.

---

## 0. Resumen para el PO

**Problema.** El piloto de #135 resolvió **0 de 12** ediciones españolas porque solo se ejercitó
`search_series`; encontrar «Dragon Ball» no acredita la edición Ultimate de Planeta de 2006
(`piloto-cobertura-2026-11-06.md` §3). Falta un **método de detalle** que, a partir de un candidato,
devuelva los datos de la edición y permita contrastarlos con la etiqueta acreditada del corpus.

**Contrato que se propone:**

1. **Tebeosfera ficha de colección: adoptar.** Es el único método que da editorial (entidad + sello),
   año, formato, país y numeración de la edición española en **una petición**; el **idioma no consta**
   (`campo_ausente`). La ficha de **saga se descarta** (nivel obra).
2. **Comic Vine `get_volume`: adaptar, no resolver.** Existe y da `publisher`, `start_year` y
   `count_of_issues`, pero de **su** edición (en el caso probado, la USA de Viz), sin `format` ni
   país/idioma. Sirve como **contraste** (si difiere, `incorrecto`). La respuesta real de
   `/volume/4050-…/` está `[sin verificar: requiere clave]`; sin clave, **no se llama** y queda NOT RUN.
3. **GCD detalle de serie: adaptar.** Da editorial (URL → nombre, +1 petición), año, formato, país e
   idioma; el `issue_count` es `null` y **no** se convierte en número. En la búsqueda ya vienen casi
   todos los campos, así que el detalle puede costar **0 peticiones** si se conserva el `raw` del
   resultado. El hueco de GCD es la **selección** de candidato, no el detalle.
4. **AniList: descartar** para edición; su `format`/`countryOfOrigin` son de la obra, no de la edición.
5. **Coste:** **+1 petición por candidato** en Tebeosfera y Comic Vine; **0/1/2** en GCD según se
   reutilice el `raw`, se pida la serie o se resuelva el nombre de la editorial. Tebeosfera mantiene
   **2,5 s** y todo pasa por `pedir_con_cortesia` (#134). Se detalla solo el **top-1/top-2** que pase
   el filtro de título; nunca los 10 resultados.

**Consecuencia honesta:** el método de Tebeosfera devuelve **numeración de la colección** (p. ej.
«1 a 153»), **no** el número concreto del ejemplar. Para los casos de número del corpus
(ES-018/ES-019) el detalle de colección deja `numero_publicacion = campo_ausente` y el contraste es
`ambiguo`; **no se acredita el número por pertenecer a un rango**. La ficha de número de Tebeosfera
no se abrió en el benchmark (`[sin verificar]`). Esta es la corrección principal a la ficha y se
desarrolla en §2.4 y §4.3.

**Corte:** Tebeosfera primero (método + contraste + tests), integración en Discovery/banco después y
Comic Vine al final, cuando haya clave. La cobertura real sigue **NOT RUN** hasta una ejecución
autorizada, y esta spec no la declara (§8).

---

## 1. Contratos que se reutilizan

### 1.1 Estados y capacidad de #133

`services/estados_fuentes.py:19-39` define el conjunto cerrado —`ok`, `sin_resultados`,
`fallo_transitorio`, `configuracion_incompleta`, `limite_de_cortesia`, `fuente_apagada`— y
`EstadoFuente(fuente, capacidad, estado, motivo, reintentar_en)`. Hoy la única capacidad verificada es
`CAPACIDAD_BUSQUEDA` (`:25`), y `discovery.py` la reexporta (`:58-61`).

Esta historia añade una **capacidad de contrato**, no una capacidad de producto ya verificada:

```python
CAPACIDAD_DETALLE = "detalle_edicion"   # nueva; no sustituye CAPACIDAD_BUSQUEDA
```

- `EstadoFuente(capacidad=CAPACIDAD_DETALLE)` describe el resultado del detalle (mismo conjunto
  cerrado). No se publica en la UI como «disponible»: la interfaz solo muestra lo que el servicio
  declara y esta entrega no añade UI.
- Un estado `fuente_apagada`/`configuracion_incompleta` se comprueba **antes** de instanciar el
  cliente, sin petición. `ok`/`sin_resultados` se reservan para una respuesta del detalle.
- No se toca `ESTADOS_DE_FUENTE`; el detalle consume el mismo contrato.

### 1.2 Cortesía de #134

El detalle no hace peticiones directas: usa `pedir_con_cortesia` (`utils/peticiones.py:228`) a través
de cada cliente. La política es la del proceso (`utils/cortesia.py:169` `PoliticaFuente`, `:206`
`politica_de`, `:229` `fuente_habilitada`), con:
- Tebeosfera: **2,5 s mínimo** por petición y salto, ≤3 redirecciones y solo su origen
  (`services/tebeosfera.py:77,80,172-196`); una ficha es **1 petición** dentro de esa cola.
- Comic Vine: 1,0 s y política de la fuente; GCD: 2,0 s; AniList no aplica (descartada).
- `espera_max_s` por llamada: **30 s** (fondo) por defecto; el banco usa el mismo presupuesto de #135.
- Errores ya definidos: `CortesiaEnEspera`, `FuenteApagada`, `ReintentosAgotados` (429),
  `ErrorDePeticion` y redirecciones no permitidas. El detalle los mapea a #133 (§3.6), sin inventar
  estados nuevos en la app.

### 1.3 Corpus y etiquetas de #135

El contraste usa el corpus v1 (`docs/design/corpus-cobertura-v1.json`) y sus reglas:
- Solo una etiqueta con `identidad_acreditada: true` puede producir `coincidencia_verificada`
  (`banco-cobertura-espanola.md:3.3`); una etiqueta en borrador se marca y no suma.
- `campo_ausente` se registra por campo y puede coexistir con una coincidencia (`:4.2`).
- El resultado editorial es una **propuesta automática** del contraste; la acreditación final sigue
  siendo humana (`:9`). Esta spec no convierte el contraste en regla de producto.

### 1.4 Vocabulario e identidad

Se usa el vocabulario del ADR 0003: **serie**, **edición** (no existe como entidad), **publicación/
número**, **formato de publicación** (`IssueFormat`, `models/__init__.py:55-63`), **archivo**. Título y
año sirven para buscar; no son identidad (`discriminantes-publicacion.md` §2). `edición` aquí es una
unidad de evaluación observable, no una tabla nueva.

---

## 2. Modelo del resultado

### 2.1 `DetalleEdicion`

Dataclass inmutable en `services/detalle_edicion.py`; **no** se persiste, no hay migración y no se
escribe en `Series`/`Issue`. Es un resultado de lectura para contraste y evidencia.

| Campo | Tipo | Significado |
|---|---|---|
| `fuente` | `MetadataSource` | Fuente que respondió |
| `external_id` | `str` | Slug de Tebeosfera, id de CV/GCD |
| `metodo` | `str` | Método autorizado que lo produjo (§3) |
| `editorial` | `str \| None` | Entidad editorial tal cual la da la fuente |
| `sello` | `str \| None` | Sello/colección editorial cuando la fuente lo separa |
| `anio` | `int \| None` | Año de inicio de la edición |
| `anio_fin` | `int \| None` | Año final si la fuente da rango |
| `numeracion_inicio` | `int \| None` | Inicio de la numeración de la colección |
| `numeracion_fin` | `int \| None` | Fin de la numeración de la colección |
| `numeracion_texto` | `str \| None` | Texto original («1 a 153») para evidencia |
| `numero_publicacion` | `str \| None` | Número concreto del ejemplar, **solo** si la fuente lo da |
| `paginas` | `int \| None` | Páginas solo si hay **un** valor; si la ficha da varios, `campo_ausente` |
| `formato` | `IssueFormat \| None` | Formato de publicación mapeado (§4.3) |
| `formato_fuente` | `str \| None` | Texto original del formato, para evidencia; no se compara |
| `pais` | `str \| None` | `ES` u otro ISO cuando se puede mapear; si no, ausente |
| `idioma` | `str \| None` | `es` u otro cuando la fuente lo da; si no, ausente |
| `campos_ausentes` | `frozenset[str]` | Campos que la fuente **no** da, explícitos |
| `peticiones` | `int` | Peticiones HTTP consumidas por este detalle |
| `url_ficha` | `str \| None` | Ficha para atribución/revisión; no se registra en logs |

`campos_ausentes` es obligatorio y derivado: `editorial`, `sello`, `anio`, `anio_fin`,
`numeracion_*`, `numero_publicacion`, `paginas`, `formato`, `pais`, `idioma`. Un campo `None` por
ausencia **no** se rellena con una suposición.

### 2.2 `ResultadoDetalle`

```python
@dataclass(frozen=True)
class ResultadoDetalle:
    estado: EstadoFuente       # capacidad = CAPACIDAD_DETALLE
    detalle: DetalleEdicion | None
    motivo: str | None = None
```

- `estado.estado` es del conjunto de #133; `detalle` solo existe si hubo respuesta parseable.
- No se usa `ok` para «hay ficha pero faltan campos»: `ok` puede convivir con `campos_ausentes`.
  «Ficha encontrada pero sin el bloque de editorial» no es `sin_resultados`: es `ok` con
  `editorial` ausente (benchmark §8.2).

### 2.3 Por qué no hay modelo nuevo

No se añaden tablas `editions`, ni columnas de editorial/año/formato, ni se escribe
`Series.publisher_id`/`Imprint` en esta historia. `Publisher`/`Imprint` existen
(`models/__init__.py:233-262`) pero **no se tocan**: hacerlo sería una decisión de modelado
(ADR 0003, #183/#184) fuera del alcance de #465. El detalle es evidencia de lectura; si más adelante
se persiste, será otra historia con migración y aceptación explícita.

### 2.4 `numeracion` ≠ `numero_publicacion` (corrección a la ficha)

La ficha de colección observada trae `Numeración: 1 a 153` y **153 enlaces** a fichas de número
(benchmark §2.2). Eso acredita que la colección **abarca** esos números, no que el ejemplar concreto
del corpus sea el nº 15. Por eso:

- `numeracion_inicio/fin/texto` describen la **colección**; `numero_publicacion` es el **ejemplar**.
- La ficha de colección de Tebeosfera **no rellena** `numero_publicacion`: queda `campo_ausente`.
- Para los casos `unidad=numero` (ES-018, ES-019), el contraste exige `numero_publicacion`; si falta,
  el resultado es **`ambiguo`**, nunca `coincidencia_verificada` por «15 está entre 1 y 153».
- La ficha de **número** de Tebeosfera (`/numeros/…`) no se abrió en el benchmark; si se abre en una
  ejecución autorizada y devuelve el número, podrá rellenar `numero_publicacion`; hasta entonces es
  **NOT RUN**. Comic Vine `get_issue` sí da `issue_number` (benchmark §2.1), pero sin editorial; se
  combina, como mucho, con `get_volume` y se marca `[sin verificar]`.

---

## 3. Contrato por fuente

### 3.1 Tebeosfera — ficha de colección (adoptar)

**Método del cliente:** `TebeosferaClient.get_collection(slug: str, *, espera_max_s: float = 30.0)
-> TebeosferaColeccion | None`.

- **Entrada:** slug de una colección obtenido de `search_series` (`TebeosferaResult.slug`; el buscador
  ya mezcla colecciones y sagas, `services/tebeosfera.py:198-204`).
- **Petición:** `GET {_BASE_URL}/colecciones/{slug}.html` por `pedir_con_cortesia`, **1 petición**,
  con los headers actuales del cliente (`User-Agent`, `Referer`, `Accept-Language`;
  `tebeosfera.py:144-156`), `follow_redirects=False` y la política de 2,5 s. No se pide la galería de
  portadas ni ninguna imagen.
- **Campos observados** (benchmark §2.2, una colección):

| Campo de la ficha | Selector/estructura observada | Campo normalizado |
|---|---|---|
| editorial + sello | `div.titulo` con dos enlaces `/entidades/…` | `editorial`, `sello` |
| país | bandera `…/banderas/spain.png` `title="España"` + ciudad | `pais` (`ES`) |
| fechas | `Fechas: IV-1992 - III-1995`; año también en el título | `anio`, `anio_fin` |
| números | `Números: 153 ordinarios` · `Numeración: 1 a 153` | `numeracion_*` |
| formato | `Formato: CUADERNO / GRAPA [1-153]` | `formato` (mapa §4.3) |
| paginación | `Paginación: 36 pp. · 32 pp. · …` | `paginas` **solo si un valor**; si varios, ausente |
| idioma | **no hay campo**; solo prosa | `campo_ausente` |

- **No se inventa:** si no hay `div.titulo` con entidad, `editorial`/`sello` son `campo_ausente`; si no
  hay bandera, `pais` ausente; si no hay `Formato`, `formato` ausente. La ficha observada demuestra que
  las etiquetas **no son un contrato** (`Edición: Semanal` no es editorial); el parser debe ser
  defensivo y no depender de una maqueta perfecta.
- **Salida:** `TebeosferaColeccion` (dataclass del cliente) con campos crudos; el servicio la normaliza
  a `DetalleEdicion`.
- **Límites:** se inspeccionó **una** colección; la generalización (álbum, tomo, grapa, otras
  editoriales) es **NOT RUN**. No se afirma que todas las fichas traigan entidad, bandera o numeración.
- **Selector de `div.row-fluid`:** el benchmark lo observó; el parser usa una lista de selectores
  tolerante y, si no encuentra un campo, lo declara ausente (nunca lanza un `KeyError` que tumbe la
  búsqueda).

**Atajo opcional (no bloqueante).** La fila de búsqueda ya trae `(1992, PLANETA-DEAGOSTINI)` y
`153 números` (benchmark §2.2); `_TITLE_SUFFIX_RE` los tira (`tebeosfera.py:110`). Recuperarlos para
editorial/año **podría** ahorrar la ficha cuando solo se necesitan esos dos campos, pero solo hay
evidencia de una fila; esta spec lo deja como **mejora posterior**, no como parte del contrato de
#465.

### 3.1.1 Tebeosfera — ficha de número (#489)

**Método:** `TebeosferaClient.get_numero(slug: str, *, espera_max_s: float = 30.0)
-> TebeosferaNumero | None`.

- **Petición:** `GET https://www.tebeosfera.com/numeros/<slug>.html` por
  `pedir_con_cortesia`, **1 petición**, misma política de 2,5 s/origen y headers; sin galería ni
  imágenes. 404/HTML sin ficha → `None`.
- **Cuándo se usa:** cuando el candidato declara un slug de número (p. ej. `site_url` con
  `/numeros/` o `external_id` con prefijo `numero:`). Si no lo declara, se sigue usando la ficha
  de colección y el número queda `campo_ausente`/`ambiguo`: no se inventa un slug.
- **Campos observados en la ficha real** (`docs/design/fixtures-cobertura/
  tebeosfera_numero_bola_de_drac_2017_super_roja_1.html`, captura recortada del 2026-11-07):
  `numero_publicacion` («Nº 1 de…»), `editorial`/`sello` (entidades), `anio`/`fecha`
  («21-III-2017»), `paginas` («32 págs.») y `formato_fuente` («CUADERNO · ENCOLADO»).
- **Salida:** `TebeosferaNumero` crudo; el servicio lo normaliza a `DetalleEdicion` con
  `numero_publicacion` y, si constan, editorial/sello/año/fecha/páginas/formato.
- **Contraste:** con número presente y etiqueta que lo trae, editorial+año+número iguales →
  `coincidencia_verificada`; número distinto → `incorrecto`; número ausente → `ambiguo`
  (la ficha de colección no acredita el ejemplar).
- **Límites:** se verificó **una** ficha de número (grapa encolada de 2017); otras maquetas
  (tomo, álbum, número sin fecha/páginas) son **NOT RUN**. Una segunda petición solo sería
  necesaria si en el futuro se quiere resolver primero la colección; este método no la hace.

### 3.2 Comic Vine — volumen (adaptar; `[sin verificar]`)

**Métodos:** `ComicVineClient.get_volume(volume_id: int) -> CVVolume | None` y, para número,
`get_issue(issue_id: int) -> CVIssue | None` (la ruta de issue ya existe como `get_issue_detail`,
`comic_vine.py:137-147`, pero devuelve `dict`; se normaliza).

- **Volumen:** `GET /volume/4050-{id}/` con
  `field_list=id,name,publisher,start_year,count_of_issues,first_issue,last_issue,site_detail_url`.
  La doc oficial declara esos campos (benchmark §2.1); **la respuesta real no se abrió** por falta de
  `COMICVINE_API_KEY`: ruta canónica, forma del objeto `publisher` y valores quedan `[sin verificar]`.
- **Issue:** `GET /issue/4000-{id}/` con `field_list=id,issue_number,cover_date,volume`; da
  `issue_number` y `cover_date`, **no** editorial ni formato.
- **Campos:** `publisher` → `editorial`; `start_year` → `anio`; `count_of_issues` → recuento, **no**
  `numero_publicacion`; `first_issue`/`last_issue` → referencias, no número del ejemplar. `formato`,
  `pais` e `idioma` son **`campo_ausente`** (la doc no los tiene).
- **Uso:** **contraste**, no resolución. El volumen de Comic Vine es la edición que CV indexa; en el
  caso Dragon Ball es Viz 2003/16, no Planeta 2006/34 (benchmark §2.1, Kaboom). Comparado con ES-007
  da `incorrecto`; no se presenta como «la edición española».
- **Sin clave:** el cliente no se instancia y el detalle no se pide; estado `configuracion_incompleta`
  (o NOT RUN en el banco). Cero peticiones.
- **Coste:** volumen **1 petición**; issue **1**; si se combinan editorial (volumen) y número (issue),
  **2**. Presupuesto de #134 y 1,0 s.

### 3.3 GCD — detalle de serie (adaptar)

**Métodos:** `GCDClient.get_series(gcd_id: int) -> GCDSerie | None` y
`GCDClient.get_publisher(publisher_url: str) -> str | None`.

- **Serie:** `GET /api/series/{id}/` (API anónima, `Accept: application/json`; base actual
  `services/gcd.py:100-128`). Campos observados (benchmark §2.3):
  `name`, `year_began`, `year_ended`, `publisher` (URL), `language`, `country`,
  `publishing_format`, `binding`, `issue_count`, `active_issues`, `issue_descriptors`.
- **Editorial:** `publisher` es una **URL**; el nombre exige `GET /api/publisher/{id}/` (observado:
  «Panini España»). Sin esa petición, `editorial` queda `campo_ausente` (no se inventa un nombre).
- **Campos:** `editorial` (+1 petición), `anio` (`year_began`), `anio_fin`, `pais` y `idioma` (ya en la
  serie), `formato` desde `publishing_format` + `binding` (§4.3; si no hay equivalencia, ausente).
- **Número:** `issue_count` es **`null`** en el caso observado; `issue_descriptors`/`active_issues`
  listan números pero **no son un recuento fiable** (E7). No se convierten en `numero_publicacion`;
  para número, GCD no tiene método de detalle en esta historia → `campo_ausente`/NOT RUN.
- **Sin petición extra en el banco:** el `GCDResult.raw` de `search_series` ya contiene esos campos
  (`gcd.py:130-167`); el arnés puede construir el detalle con **0 peticiones**. En Discovery, que no
  conserva `raw`, se usa `get_series` (1) y, si se quiere el nombre, `get_publisher` (1).
- **Selección:** GCD ya filtra país/idioma en Discovery con `es_edicion_espanola`
  (`gcd.py:62-75`); el detalle **no** arregla la selección del candidato, que sigue fuera de #465.
  Cobertura escasa de las ediciones ES del corpus (benchmark §2.3) es un límite, no un fallo del
  detalle.

### 3.4 AniList — descartar

No se añade método. `format`/`countryOfOrigin` describen la obra, no la edición; `publisher` no
existe (benchmark §2.4). Un candidato AniList produce `sin_metodo_autorizado`/NOT RUN, nunca un
detalle inventado.

### 3.5 Resumen del contrato

| Fuente | Método | Peticiones | editorial | año | número | formato | país | idioma |
|---|---|---|---:|---|---|---|---|---|
| Tebeosfera | `get_collection(slug)` | 1 | ✓ entidad+sello | ✓ | ✗ (solo numeración) | ✓ | ✓ | ✗ `campo_ausente` |
| Comic Vine | `get_volume(id)` | 1 | ✓ `publisher` | ✓ | ✗ (recuento) | ✗ | ✗ | ✗ |
| Comic Vine | `get_issue(id)` | 1 | ✗ | ~ `cover_date` | ✓ `issue_number` | ✗ | ✗ | ✗ |
| GCD | `get_series(id)` | 1 | ~ URL (+1 nombre) | ✓ | ✗ (`issue_count` null) | ✓ | ✓ | ✓ |
| GCD (raw de búsqueda) | sin método | 0 | ~ URL (+1 nombre) | ✓ | ✗ | ✓ | ✓ | ✓ |
| AniList | — | — | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

`✓` = el campo viene; `~` = viene parcial o exige otra petición/mapeo; `✗` = no viene y se marca
`campo_ausente`. No se rellena ninguna celda `✗` por inferencia.

### 3.6 Estados del detalle (mapeo a #133)

`detalle_de` devuelve `ResultadoDetalle` con `EstadoFuente(capacidad=CAPACIDAD_DETALLE)`:

| Situación | Estado | Petición |
|---|---|---|
| Fuente apagada en Ajustes | `fuente_apagada` | no |
| CV sin clave / configuración incompleta | `configuracion_incompleta` | no |
| Respuesta con ficha y campos | `ok` (con `campos_ausentes` si faltan) | sí |
| 404, o ficha que no es de colección | `sin_resultados` | sí |
| Ficha válida con solo parte de los campos | `ok` + `campos_ausentes` | sí |
| Red, timeout, HTTP no transitorio, parseo roto | `fallo_transitorio` | sí |
| `CortesiaEnEspera` / `ReintentosAgotados(429)` | `limite_de_cortesia` | sí/limitada |

Un detalle `ok` con `editorial` ausente **no** es `fallo_transitorio` ni `sin_resultados`: es una
respuesta válida con `campo_ausente`. El parser no convierte un campo faltante en excepción.

### 3.7 Caché y coste

- Caché **en memoria, por ejecución** del banco, clave `(fuente, external_id)`: evita pedir dos veces
  la misma ficha si el candidato aparece en varios casos. No hay caché en disco, ni nueva tabla, ni
  cache persistente en esta historia.
- Detallar **solo** el top-1/top-2 que pase el filtro de título; nunca los 10 resultados (benchmark
  §5). Presupuesto del banco: 80 peticiones / 20 por fuente; +12 Tebeosfera, +12 CV, +12 GCD como
  máximo caben, pero el número de candidatos detallados se limita explícitamente.
- Tebeosfera: 1 ficha = 2,5 s de cola; un lote de 10 fichas ≥25 s y debe presupuestarse en quien
  orquesta, no en el cliente.

---

## 4. Cómo se usa

### 4.1 Consumidores

1. **Banco de #135 (principal):** elige un candidato de `search_series`, pide su detalle y lo contrasta
   con la etiqueta acreditada; registra `estado`, `campos_ausentes` y `resultado_editorial`.
2. **Discovery:** expone `DiscoveryService.detalle_de(resultado, *, unidad)` como método de servicio
   (no hay ruta HTTP nueva, no cambia `DiscoveryResult` ni `Busqueda`). El banco lo usa si trabaja con
   `DiscoveryResult`; si trabaja con `GCDResult.raw`, usa el detalle directo.
3. **Enricher:** puede llamar al mismo servicio para obtener evidencia de un candidato ya elegido; en
   esta historia **no escribe** editorial/año/formato en `Series`/`Issue` (no hay columnas y no se
   migra). No se activa ningún camino automático de identidad.

No hay UI, API pública, migración, activación de fuentes ni cambio de reglas de producto.

### 4.2 Flujo

```
candidato (fuente, external_id, unidad)
  → detalle_de(candidato)         # 1 petición (o 0 si GCD raw); estados #133
  → DetalleEdicion + campos_ausentes
  → contrastar(detalle, etiqueta, unidad)
  → Contraste automático (propuesta)
  → revisión humana del banco      # veredicto final; sin ella no es "verificada"
```

**Selección del candidato fuera de alcance.** El benchmark y el piloto demuestran que la selección es
un hueco distinto (Thorgal francés, Tebeosfera con resultados ajenos). #465 **no** elige candidato: usa
el que devuelve la búsqueda en su orden actual y registra cuál se detalló. Si el candidato es de otra
edición, el contraste dará `incorrecto`, y eso es evidencia, no un fallo del detalle.

### 4.3 Reglas de contraste (explícitas)

`contrastar(detalle, etiqueta, *, unidad)` es una función **pura**, sin red. Devuelve un `Contraste`
con `resultado` (`coincidencia_verificada`, `ambiguo`, `incorrecto` o `None` si la etiqueta no está
acreditada o no hay detalle), `campos_requeridos`, `campos_ausentes` y `motivos` (códigos cortos, sin
URL).

**Campos requeridos por unidad:**

| Unidad | Requeridos para un veredicto positivo |
|---|---|
| `serie` | `editorial` + `anio` (la serie no acredita edición; se marca como nivel serie) |
| `edicion` | `editorial` + `anio`; `numero_publicacion` **solo si la etiqueta lo trae** |
| `publicacion` / `numero` | `editorial` + `anio` + `numero_publicacion` |
| `formato` | `editorial` + `anio` + `formato` |
| `campo` | `editorial` + `anio` + los campos que compare la etiqueta |

**Comparación:**

- **Editorial:** normalizar (NFKD, sin diacríticos, minúsculas, puntuación a espacio, espacios
  colapsados). Coincide si el nombre normalizado de la etiqueta es igual a `editorial` **o** a
  `sello` del detalle. Si no es igual pero uno es prefijo/sufijo del otro por palabra completa
  («Panini»/«Panini España», «Planeta»/«Grupo Planeta»), es **`ambiguo`**: no se acredita por
  parecido. Si ambos existen y no hay relación, `incorrecto`. No se usa `normalize_title` (que quita
  artículos): para editoriales sería una inferencia.
- **Año:** igualdad exacta con `anio` de inicio. Sin tolerancia ±1. Si el año de la etiqueta cae
  dentro de `[anio, anio_fin]` pero no es el inicio, `ambiguo` (rango), no `verificado`.
- **Número:** normalizar `numero_publicacion` (trim, minúsculas, ceros a la izquierda; dígitos como
  entero; resto como texto) y comparar con `etiqueta.numero`. Si la etiqueta no trae número, no se
  exige. Si la fuente solo trae `numeracion_*` (rango), **no** se usa como número: `campo_ausente` y
  `ambiguo`.
- **País:** mapear `España`/`ES`/`es` → `ES`; `es` de GCD → `ES`. Si etiqueta y detalle tienen país y
  difieren → `incorrecto` (edición de otro país). Si falta en el detalle → `campo_ausente`; no bloquea
  por sí solo.
- **Idioma:** análogo; `es`/`español` → `es`. Si difiere → `incorrecto`; si falta → `campo_ausente`.
- **Formato:** mapeo **cerrado y conservador** a `IssueFormat` (§4.4). Si falta en el detalle →
  `campo_ausente`; no bloquea **salvo que la unidad sea `formato`**, donde el formato es el campo
  requerido y su ausencia da `ambiguo`. Si ambos existen y difieren → **`ambiguo`**, no `incorrecto`:
  el formato físico de la fuente y el `IssueFormat` del corpus no son la misma taxonomía y #182 ya
  decidió que el formato **no es identidad**. Se registra `formato_fuente` y el motivo. Lo mismo
  aplica a `unidad=campo`: el campo que compara la etiqueta es requerido y su ausencia da `ambiguo`.
- **Páginas:** no se compara con la etiqueta; es evidencia de formato. Si la ficha da varios valores,
  `campo_ausente` (no se elige uno).

**Resultado:**

1. Si el detalle no está `ok` → no hay resultado editorial (`null`), solo estado técnico.
2. Si la etiqueta no está `identidad_acreditada` → no hay veredicto editorial (`resultado=None`);
   el registro la marca como `no_acreditada` y no suma a coincidencias.
3. Si falta un requerido → **`ambiguo`** (con `campos_ausentes`).
4. Si un requerido difiere → **`incorrecto`**.
5. Si país o idioma difieren → **`incorrecto`**.
6. Si formato difiere → **`ambiguo`**.
7. Si todo lo requerido coincide (y no hay conflicto de país/idioma) → **`coincidencia_verificada`**
   **propuesta**; el banco la eleva a veredicto final solo con revisión humana.

**Ejemplos con el corpus:**

- ES-007 (Planeta DeAgostini, 2006, Ultimate 34 tomos): ficha Tebeosfera 1992 de Planeta → editorial
  y sello coinciden, año 1992 ≠ 2006 → **`incorrecto`**. Volumen CV Viz 2003 → editorial y año
  difieren → **`incorrecto`**.
- ES-007 con una ficha que dé editorial Planeta, año 2006, `numero=null` y sin contradicción de
  formato/país/idioma → **`coincidencia_verificada`**; si el formato se mapea y difiere, el máximo es
  `ambiguo` (§4.3).
- ES-018 (Juventud, 1989, nº 15): ficha de colección con editorial Juventud y año 1989, pero
  `numero_publicacion` ausente → **`ambiguo`** (NO se acredita el 15 por el rango).
- ES-019 (Salvat, 2011, nº 3): ídem → **`ambiguo`**.
- Cualquier etiqueta en borrador → `resultado=None` y registro `no_acreditada`; no suma a
  coincidencias.

### 4.4 Mapa de formatos (solo lo observado/equivalente)

| Texto de la fuente | `IssueFormat` | Base |
|---|---|---|
| `CUADERNO / GRAPA` | `single_issue` | observado en Tebeosfera |
| `cartoné` / `CARTONE` | `hardcover` | benchmark §8.8 |
| `álbum` / `album` | `album` | equivalencia directa |
| otro / vacío | `None` + `campo_ausente` | no se adivina |

El corpus usa `album`/`manga_tankobon` y la fuente formato físico: si no hay equivalencia inequívoca,
el campo queda ausente, y el contraste **no** convierte una diferencia de taxonomía en `incorrecto`.

### 4.5 Integración con el banco (#135)

- `scripts/medicion/banco_cobertura.py` gana un mapa de detalle (`METODOS_DETALLE`) además de
  `METODOS` (`:80-99`): Tebeosfera `get_collection`, CV `get_volume`/`get_issue`, GCD
  `get_series`/raw; AniList `None`. `_invocar` (`:582-607`) aprende a llamar a esos métodos.
- Flujo del banco: búsqueda → candidato (top-1/top-2) → detalle → contraste → registro. Si no hay
  candidato, `sin_resultados`; si el método es `None`, `no_ejecutado: sin_metodo_autorizado`.
- El registro conserva `campos_ausentes`, `peticiones` y `resultado_editorial` con la misma
  separación técnico/editorial de #135; no se añaden porcentajes nuevos.
- El corpus **no se edita**; las etiquetas acreditadas y las que no lo están se tratan como en §1.3.
- `--seco` usa fixtures (§7) y sigue declarando cobertura **NOT RUN**; `--real` no cambia su
  autorización, presupuesto ni cortesía.

---

## 5. Riesgos legales

- **Portadas ©.** La ficha de Tebeosfera incluye galería de portadas; el detalle **no** descarga
  imágenes, solo campos textuales. ZascArr ya cachea portadas para uso privado y no las redistribuye
  (`src/zascarr/LEGAL.md`, filas de portadas y fuentes).
- **Tebeosfera, derecho *sui generis*.** `LEGAL.md` la clasifica como base de datos protegida y pide
  no redistribuir extractos; uso local del usuario. El detalle se cachea en memoria/BD local de la
  instancia, no se vuelca en masa ni se publica; 1 petición por candidato y 2,5 s son coherentes con
  ese uso.
- **Comic Vine, términos propios.** Clave, rate limits y no redistribución masiva; el detalle no
  cambia la postura y no se llama sin clave.
- **GCD, CC BY-SA 4.0.** Si el detalle muestra datos de GCD, conservar atribución y enlace a la ficha;
  la licencia cubre datos, no portadas (E7 §3). No se descargan portadas.
- **AniList:** sin uso nuevo.
- **Fixtures:** solo fragmentos HTML/JSON saneados, sin galerías, sin sinopsis largas, sin claves ni
  URL con credenciales; no se versiona una página completa.

---

## 6. Límites del benchmark (lo no verificado)

1. **CV `/volume/4050-…/`:** respuesta real no abierta (sin clave); ruta y forma de `publisher`
   `[sin verificar]`. Sin clave no se pide; tests con fixture manual cuando exista.
2. **CV edición española:** no se comprobó si CV tiene alguna edición ES de los casos; el volumen
   probado es la USA de Viz. El detalle sirve de contraste, no de resolución.
3. **Tebeosfera ficha de número:** implementada en §3.1.1 (#489) con una ficha real recortada de
   grapa encolada de 2017; la generalización a tomo/álbum y otras maquetas sigue **NOT RUN**. La
   ficha de colección por sí sola no acredita el número concreto (§2.4).
4. **Generalización de la ficha de colección:** una sola colección; no consta que todas traigan entidad,
   bandera o numeración. El parser debe marcar ausencias; la generalización es NOT RUN.
5. **Ficha de saga:** una sola; se descarta por nivel obra, sin generalizar.
6. **GCD:** se miró la primera página de búsqueda; «no está» significa «no está en la primera página».
   Paginación/filtros no probados. `issue_descriptors` no es recuento fiable (E7).
7. **Tebeosfera robots/ToS:** no se descargó; rige `LEGAL.md`, no una lectura nueva.
8. **Coste:** una ficha y una serie; el patrón de múltiples candidatos es una estimación, no una
   medición.

---

## 7. Pruebas sin red

Todas las pruebas usan `httpx.MockTransport`/transportes inyectados, reloj y `dormir` simulados; sin
claves, sin red, sin Postgres. Fixtures saneados y pequeños.

### 7.1 Fixtures

| Fixture | Contenido | Origen |
|---|---|---|
| `tests/fixtures/tebeosfera_coleccion_dragon_ball_1992.html` | solo bloques `div.titulo`, bandera, `Fechas`, `Números`, `Formato`, `Paginación`; sin galería ni prosa | ficha del benchmark §2.2, saneada |
| `tests/fixtures/tebeosfera_saga_dragon_ball_1984.html` | bloque de saga con `TÍTULOS`/`Génesis`/`Entregas`; sin edición | benchmark §2.2 |
| `tests/fixtures/comicvine_volume_31306.json` | `name`, `publisher`, `start_year`, `count_of_issues`; **fixture manual** | benchmark §2.1 (Kaboom/doc), `[sin verificar]` hasta clave |
| `tests/fixtures/gcd_series_224764.json` + `gcd_publisher_3932.json` | campos observados §2.3 | benchmark §2.3, saneado |

El fixture de Tebeosfera es **derivado de la evidencia del benchmark** (mismos valores y estructura),
no una captura nueva; no incluye imágenes ni texto completo. Si el PO exige una captura nueva, se hace
en una ejecución autorizada y se sanea antes de versionar.

### 7.2 Pruebas

**Parser Tebeosfera**
1. Colección válida → editorial/sello, año, numeración, formato, país; `idioma` en `campos_ausentes`.
2. Sin bloque de entidad → `editorial`/`sello` ausentes, sin excepción.
3. Saga → no produce campos de edición; el servicio la rechaza para `unidad=edicion`.
4. HTML roto/404 → `fallo_transitorio`/`sin_resultados`; no `ok` vacío.
5. `Formato` desconocido → `formato=None` + `campo_ausente`; no se adivina.
6. Paginación múltiple → `paginas=None` + `campo_ausente`.

**Parser CV**
7. Volumen fixture → publisher, start_year, count; `formato`/`pais`/`idioma` ausentes.
8. Issue fixture → `issue_number`; editorial ausente.
9. Sin clave → `configuracion_incompleta`, cero peticiones (test con doble que falla si hay red).

**Parser GCD**
10. Serie fixture → editorial URL, país, idioma, formato, año; `get_publisher` da el nombre.
11. `issue_count=null` → `numero_publicacion` ausente; `issue_descriptors` no se usa como número.
12. `es_edicion_espanola` se reutiliza para no llamar detalle de una edición no ES (si el flujo lo
    decide; el detalle en sí no filtra).

**Contraste**
13. ES-007 Tebeosfera 1992 → `incorrecto` (año).
14. ES-007 ficha 2006 Planeta, `numero=null` → `coincidencia_verificada` (editorial+año).
15. ES-018/ES-019 ficha con editorial+año pero sin `numero_publicacion` → `ambiguo`.
16. Editorial near-match → `ambiguo`; editorial distinta → `incorrecto`.
17. País/idioma distintos → `incorrecto`; formato distinto → `ambiguo`; formato ausente → no bloquea.
18. Etiqueta `identidad_acreditada=false` → `no_acreditada`, no veredicto.
19. `campos_ausentes` es el conjunto exacto; no se inventa editorial desde `pais`.
20. Sin detalle (`estado != ok`) → `resultado_editorial=None`.

**Cortesía/estados**
21. El detalle pasa por `pedir_con_cortesia`: fuente apagada → cero peticiones; 429 → `limite_de_cortesia`;
    2,5 s Tebeosfera con reloj simulado; presupuesto agotado → `CortesiaEnEspera` visible.
22. Caché por `(fuente, external_id)` no duplica peticiones en la misma ejecución del banco.
23. `DiscoveryService.detalle_de` no cambia `DiscoveryResult`/`Busqueda`; no hay ruta nueva.
24. `banco_cobertura --seco` con fixtures de detalle sigue dando cobertura `NOT RUN`; `--real` sin
    autorización sigue en exit 2 y cero peticiones.

---

## 8. Cortes de entrega y orden

La historia no cabe en una entrega: el benchmark ya pedía método → spec → implementación con fixtures.
Se propone:

| PR | Contenido | Red | Depende de |
|---|---|---|---|
| **PR-1** | Núcleo: `services/detalle_edicion.py` (`DetalleEdicion`, `ResultadoDetalle`, estados, `contrastar`), Tebeosfera `get_collection` + parser + fixtures + tests; **sin** wiring en Discovery | no | benchmark + esta spec |
| **PR-2** | Integración: `DiscoveryService.detalle_de`, GCD `get_series`/`get_publisher` (y reutilización de `raw`), mapa de detalle del banco, tests; sin UI ni escritura en BD | no | PR-1 |
| **PR-3** | Comic Vine `get_volume`/`get_issue` cuando haya clave (`COMICVINE_API_KEY`), fixture manual, tests y NOT RUN sin clave; ficha de número de Tebeosfera en #489 (§3.1.1) | no (fixtures) / real solo banco autorizado | PR-1/PR-2 + clave/permiso |

**Qué entra primero:** PR-1, Tebeosfera, porque es el único método que llena la edición española y no
depende de clave. **Qué queda NOT RUN:** PR-3 completo sin clave; generalización de la ficha de número a más
maquetas; generalización de la ficha de colección a más colecciones; y la **cobertura real**, que no
se declara en esta spec.
PR-2 no se abre hasta que PR-1 tenga parser y contraste verdes.

---

## 9. Criterios de aceptación (Given/When/Then)

**AC-01 (criterio 1) — detalle Tebeosfera.** Given un candidato de colección, When se pide su detalle,
Then devuelve editorial, sello, año, numeración, formato y país; `idioma` y `numero_publicacion` van en
`campos_ausentes`; no se descarga la galería. *pytest con fixture.*

**AC-02 (criterio 2) — detalle Comic Vine.** Given un candidato de volumen, When se pide su detalle,
Then devuelve `publisher`, `start_year` y `count_of_issues`; `formato`/`pais`/`idioma` son
`campo_ausente`; sin clave no se instancia cliente y es `configuracion_incompleta`/NOT RUN. *pytest con
fixture manual o skip declarado.*

**AC-03 — GCD detalle.** Given un candidato GCD, When se pide su detalle, Then editorial (URL→nombre),
año, formato, país e idioma; `issue_count=null` **no** es número y `issue_descriptors` no se usa como
recuento; +1 petición para el nombre o 0 con `raw`. *pytest con fixtures.*

**AC-04 (criterio 3) — contraste.** Given un detalle y una etiqueta acreditada, When se contrasta,
Then editorial+año (+número si la etiqueta lo trae) son requeridos; si falta → `ambiguo`; si difiere →
`incorrecto`; si coinciden → `coincidencia_verificada` (propuesta); formato distinto → `ambiguo`;
país/idioma distinto → `incorrecto`; etiqueta no acreditada → sin veredicto. *pytest parametrizado.*

**AC-05 (criterio 4) — cortesía.** Given el detalle, When se ejecuta, Then pasa por
`pedir_con_cortesia`, respeta 2,5 s en Tebeosfera y el presupuesto; fuente apagada → cero peticiones;
429 → `limite_de_cortesia`; no se compensa con tráfico. *pytest de estados y reloj simulado.*

**AC-06 (criterio 5) — tests sin red.** Given la suite, When se ejecuta, Then todos los tests de
detalle/contraste usan fixtures y transportes simulados, sin claves, sin red y sin Postgres; el test
de `--seco` demuestra cero peticiones. *pytest.*

**AC-07 — sin modelo/escritura.** Given el diff, When se revisa, Then no hay migración, ni columnas
nuevas, ni escritura en `Series`/`Issue`/`Publisher`/`Imprint`, ni UI/ruta nueva; `DetalleEdicion` es
in-memory. *inspección del diff + prueba de no escritura.*

**AC-08 — numeración ≠ número.** Given una ficha que da «1 a 153», When la etiqueta pide el nº 15,
Then `numero_publicacion` es `campo_ausente` y el resultado es `ambiguo`; no se acredita por rango.
*pytest ES-018/ES-019.*

**AC-09 — integración con #135.** Given el banco en seco, When se añade el detalle, Then el registro
conserva estados #133, `campos_ausentes` y la separación técnico/editorial; la cobertura sigue
`NOT RUN`; sin autorización no hay peticiones. *pytest del banco.*

**AC-10 — límites declarados.** Given el informe de la implementación, When se revisa, Then CV real,
número de Tebeosfera, generalización y cobertura están `NOT RUN`/`[sin verificar]`; no se presentan
como PASS. *inspección.*

---

## 10. Riesgos

| ID | Riesgo | Mitigación |
|---|---|---|
| R-01 | Una sola ficha de colección no generaliza | parser defensivo, campos ausentes, generalización NOT RUN |
| R-02 | Selectores/etiquetas de Tebeosfera cambian | selectores tolerantes, fixture, log de parseo sin URL/query |
| R-03 | Confundir numeración con número | campos separados; ES-018/019 ambiguo; no acreditar por rango |
| R-04 | Falso positivo por editorial parecida | exacto para verificar; prefijo/sufijo → ambiguo |
| R-05 | Formato físico vs `IssueFormat` | mapa cerrado; diferencia → ambiguo; sin equivalencia → ausente |
| R-06 | CV sin clave y ruta no verificada | fixture manual, NOT RUN; nunca llamar sin clave |
| R-07 | GCD `issue_count`/`issue_descriptors` engañosos | no se usan como número |
| R-08 | Coste/cortesía (+1 por candidato) | top-1/2, caché, presupuesto, 2,5 s |
| R-09 | Persistir sin modelo | prohibido en esta historia; solo in-memory |
| R-10 | Legal (portadas/sui generis) | no descargar galería, fixtures saneados, uso local |
| R-11 | Selección de candidato sigue fallando | fuera de #465; se registra el candidato y el veredicto es evidencia |

---

## 11. Trazabilidad y auto-revisión

| Criterio #465 | AC | Sección |
|---|---|---|
| 1. Tebeosfera: editorial, año, número, formato; `campo_ausente` | AC-01, AC-08 | §3.1, §2.4 |
| 2. Comic Vine: `get_volume`/`get_issue` | AC-02 | §3.2 |
| 3. Contraste: verificado/ambiguo/incorrecto; falta → ambiguo | AC-04, AC-08 | §4.3 |
| 4. `pedir_con_cortesia` y presupuesto | AC-05 | §1.2, §3.7 |
| 5. Tests con fixtures saneadas, sin red | AC-06 | §7 |

- [x] Benchmark leído entero; veredictos por fuente respetados (Tebeosfera adoptar, CV adaptar, GCD
      adaptar, AniList descartar).
- [x] No se inventan campos: `idioma`/`formato`/`país` ausentes donde el benchmark no los vio;
      `numeracion` se separa de `numero_publicacion`.
- [x] Reutiliza #133 (`estados_fuentes.py`), #134 (`pedir_con_cortesia`), corpus y reglas de #135, y
      ADR 0003/#182.
- [x] Sin código, sin migración, sin activar fuentes, sin declarar cobertura.
- [x] Corte en tres PRs, con PR-1 (Tebeosfera) primero y NOT RUN explícitos.
- [x] Tests sin red con fixtures saneados y casos de campo ausente/error/cortesía.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-07 | v1.0 | Primera especificación de #465 sobre el benchmark fusionado: contrato por fuente, modelo de detalle, reglas de contraste, pruebas sin red, riesgos legales y corte Tebeosfera → integración → Comic Vine. |
