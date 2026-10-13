# ADR 0003: Identidad editorial y cobertura — cierre de B22 (censo real + cuatro decisiones)

- Estado: **Aceptado con decisiones diferidas** · 2026-10-13 (revisión de #124) — acepta lo listado en
  «Decisiones cerradas» y difiere lo listado en «Decisiones abiertas»; **no autoriza ninguna migración**.
  El ADR original (2026-09-27) estaba **Propuesto**.
- Relacionado: ADR-0002 (enricher), BACKLOG §B22, `docs/design/identidad-editorial-cobertura.md`

## Revisión de 2026-10-13 (#124): vocabulario, modelo mínimo y casos de identidad

> **Qué es esta sección.** El entregable documental de la historia **#124** (MIT-M5-US01, spike de decisión).
> **No implementa código, no añade migración y no autoriza ninguna.** Las cuatro decisiones de más abajo
> (D1–D4, 2026-09-27) **no se modifican**: esta revisión les pone vocabulario común, delimita el modelo
> mínimo, las contrasta con casos y separa lo cerrado de lo abierto. Lo que se afirma del código está
> verificado contra `main` en `8f2b190` (2026-10-13); lo que no, se marca como tal.

### Estado y autoría

| | |
|---|---|
| **Estado explícito** | **Aceptado con decisiones diferidas.** Se aceptan el vocabulario, el modelo mínimo y las reglas de identidad (y lo demás de «Decisiones cerradas»); quedan diferidas la función exacta de `number_key`, la reimpresión sin renumerar, el esquema N:M archivo ↔ publicaciones y los discriminantes para homónimas (ver «Decisiones abiertas»). **La migración no queda autorizada.** |
| **Aceptación** | 2026-10-13, en la revisión de la PR #180 (PO). Antes de eso el documento estaba **Propuesto**: se redactó así y se pasó a «Aceptado con decisiones diferidas» a petición de la revisión, **antes** de fusionar. |
| **Fecha** | 2026-10-13 (revisión); 2026-09-27 (ADR original) |
| **Autoría** | Revisión redactada por Claude (asistente de desarrollo) sobre el ADR de 2026-09-27 y su especificación. **Revisión y aceptación:** PR #180 (PO, `juanajok`). |
| **Especificación** | [`docs/design/identidad-editorial-cobertura.md`](../design/identidad-editorial-cobertura.md) |
| **Benchmark** | [`docs/design/benchmark-identidad-editorial.md`](../design/benchmark-identidad-editorial.md) (cerrado 2026-10-01: Kapowarr `c191dda`, Mylar3 `cdc94a4`). **No se ha vuelto a consultar** en esta revisión. |
| **Casos analizados** | Los cuatro de §«Casos de identidad» más la evidencia de nombres reales ya citada en D1–D4 (listado del disco del coleccionista). Los casos nuevos van **anonimizados**: «Serie A», «Serie B»; ningún título ni ruta real. |

### Vocabulario

Seis términos, usados **así** en documentos, pruebas y mensajes. La columna «No representa» es la que evita
las mezclas.

| Término | Qué representa | Qué **no** representa | Dónde vive hoy |
|---|---|---|---|
| **Obra** | La creación identificable por su título, con independencia de cuántas veces, bajo qué sello o con qué numeración se haya publicado. | Una serie del catálogo (dos series pueden ser la misma obra; una serie puede reunir varias) ni una edición. | **Ninguna entidad.** `library_audit` dice «misma obra» solo como lenguaje de auditoría de duplicados (clave título + número). |
| **Serie** | La agrupación que el coleccionista cataloga y que reúne sus publicaciones: la unidad de la tebeoteca. | La obra, ni una línea de numeración (eso es la edición), ni el sello. Dos series **pueden** compartir título y año. | `Series`. |
| **Edición** | Una línea de publicación con **numeración propia** dentro de una serie (grapas originales, reimpresión renumerada, Omnigold, Integral, tomos). Es el espacio donde un número identifica. | El sello (`Imprint`/`Publisher` son atributos), ni el formato, ni el «volumen». | **No existe** como entidad ni columna (verificado: ni `editions` ni `edition_id` en `src/` ni en `alembic/`). La propone D2. |
| **Publicación / número** | «Publicación»: la unidad editorial concreta e identificable (una grapa, un tomo, un álbum). «Número»: su **etiqueta dentro de la edición**. | El número no es la publicación: `12` solo identifica **dentro de una edición**. | `Issue` (`issue_number` texto libre; `number_key` propuesto por D1). |
| **Formato** | La forma de presentación de la **publicación**: grapa, tomo, tapa dura, ómnibus, álbum, tankobon, digital. | La edición (dos publicaciones del mismo formato pueden ser de ediciones distintas: *Omnibus* e *Integral* a la vez), ni el contenedor del archivo. | `Issue.format` (`IssueFormat`). |
| **Archivo** | Una **copia física** en disco (CBZ, CBR…), con ruta y hash. | La publicación: varias copias pueden ser de la misma publicación y un pack puede contener varias. | `File` (`issue_id` nullable, 0..1 hoy). |

**Términos que no se usan como identidad.**

- **«Volumen»** tiene al menos cuatro sentidos en el proyecto: la columna `Issue.volume` (entero, `server_default 1`,
  admite `NULL`), el «Vol 2» de títulos y carpetas que extrae `naming.py`, el volumen de Comic Vine (que equivale
  más a «serie» o «edición» que a un número) y el tomo del manga. **No es identidad ni parte del vocabulario
  mínimo**: se conserva como dato heredado y se evita en mensajes.
- **«Formato»** nombra en el código dos cosas distintas: `IssueFormat` (formato de la publicación) y `FileFormat`
  (contenedor: `cbz`, `cbr`…). En documentos y mensajes se escribe **«formato de publicación»** y **«formato
  de archivo»**.
- **«Sello»**: atributo (`Publisher`, `Imprint`), nunca identidad (D2).
- **«Pack»** y **«recopilación»** no son entidades: el primero es un archivo con varias publicaciones; la segunda,
  una publicación que reproduce otras (cobertura, D4).

**Decisión sobre la obra (aceptada el 2026-10-13; reversible y aditiva).** El modelo mínimo **no crea** una entidad «obra»: ninguna fuente
(Comic Vine, AniList, Tebeosfera, GCD) aporta una identidad de obra independiente de su volumen o ficha, y crearla
obligaría a **inventar un identificador**, lo que las reglas de identidad prohíben. Si más adelante hace falta,
un `work_id` opcional es **aditivo**.

### Modelo mínimo

| Entidad | ¿Existe hoy? | Qué la identifica | Qué **no** basta | Cardinalidad |
|---|---|---|---|---|
| **Serie** | Sí (`Series`) | `id` (UUID); cualquiera de `comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id` (cada uno único, paralelos, ninguno obligatorio) | Título, título normalizado (`title_norm`: columna de búsqueda, **sin unicidad**), año, editorial | 1 serie — N ediciones (hoy la edición es implícita) |
| **Edición** | **No** (propuesta, D2) | `id` (UUID); lógicamente `(series_id, kind, numbering_unit, nombre/ref. de fuente)` | `kind` solo (puede haber dos líneas del mismo tipo), el sello, `volume` | 1 edición — N publicaciones |
| **Publicación** | Sí (`Issue`) | `id` (UUID); `comic_vine_id` (único). Hoy `(series_id, issue_number, volume)`; propuesto `(edition_id, number_key)` si hay número, y UUID/ID externo si no | El número solo; `(serie, número)`; `volume` (un `NULL` no colisiona con otro `NULL`); título + año | N publicaciones — 1 edición |
| **Archivo** | Sí (`File`) | `id` (UUID); `file_path` (único) | El nombre, el hash (identifica **contenido**, no publicación), `issue_id` | N archivos — 0..1 publicación hoy; **N:M** propuesto (D4.1), sin esquema |
| **Cobertura** | **No** (propuesta, D4.2) | `(collection_issue_id, target_issue_id)` | Un rango «5–7», un número | N:M publicación — publicación, con estado `proposed`/`confirmed`/`rejected` y procedencia |

**Lo que el código ya hace y conviene no perder de vista.** El matcher (B15, `core/matcher.py::find_issue`) usa
hoy el **formato de publicación** como discriminante cuando un número está ocupado por varias publicaciones, y si
no puede decidir **no enlaza** (el archivo va a Pendientes). Es la misma regla de ambigüedad de este documento, pero
con un discriminante que D2 declara **insuficiente** como identidad (`kind`/formato solo falla con dos líneas del
mismo tipo). Es un parche conservador, no el modelo.

### Casos de identidad

| # | Caso (anonimizado) | Hoy (verificado) | Qué hace el modelo acordado | Estado |
|---|---|---|---|---|
| 1 | **Grapa y recopilación con el mismo número**: en la Serie A, la grapa nº 12 y el Omnigold nº 12. | La restricción `UNIQUE(series_id, issue_number, volume)` no incluye el formato (`alembic 0001`, `models`): con el mismo `volume` —el alta de vinculación crea `volume=1`— **chocan**; con `volume` distinto o `NULL` **coexisten por accidente**. El matcher los separa por formato y, si no puede, no enlaza. | Dos ediciones distintas; el mismo `number_key` coexiste entre ellas y **no** dentro de una. Ninguno se funde con el otro. | **Resuelto por el modelo**; implementación y migración no autorizadas (#125/#126). |
| 2 | **Dos publicaciones homónimas con el mismo título y año**: la Serie A y la Serie B, ambas «Título» (2011), de distinto sello o país. | `Series` solo tiene unicidad en los IDs de proveedor; `title_norm` no es único. En el matcher, varias candidatas con puntuación empatada (±0,05) **no se eligen**: `UNSORTED` con «empate ambiguo». El `PATCH` de series responde `409 serie_parecida` con la lista (`api/series.py`) y el alta muestra las parecidas antes de crear. `Series` **no tiene idioma ni país** (solo `Publisher.country`). | Título y año **no** son identidad. Se distinguen por ID de proveedor, sello, tradición, formato y unidad de numeración **cuando existen**; si tras eso quedan dos candidatas compatibles es **ambiguo** y no se inventa un identificador. | **Ambiguo por diseño**; qué discriminantes se muestran y la vía manual son de **#125**. |
| 3 | **Renumeración o reimpresión**: la Serie A reeditada con nueva numeración (nº 03 que remite al nº 122 original), o una reimpresión con la misma numeración. | `naming.py` reconoce el marcador de edición («Omnigold 5» → `issue_number=5`, `edition_kind=omnigold`) y solo lo traduce a `Issue.format`; **no se persiste** como edición ni existe «reimpresión de». | **Renumeración**: edición propia; `03` es la clave en la edición nueva y `122` es una **referencia** a la original, nunca el mismo número (D1/D2). **Reimpresión sin cambiar la numeración**: no crea publicación nueva por sí sola; se trata como otra **copia** (archivo) de la misma, salvo que una fuente la separe como edición con numeración propia. | Renumeración **resuelta**; reimpresión sin renumerar: la lectura «otra copia de la misma publicación, salvo que una fuente la separe» está **aceptada (2026-10-13)** y sigue **pendiente de revisión** porque no hay dónde guardar «reimpresión de»: #125 para la colisión, #126 si afecta a la migración. |
| 4 | **Un archivo que contiene varias publicaciones**: un CBZ «01–07» de la Serie A. | `File.issue_id` es 0..1: un pack no puede apuntar a N publicaciones. `naming.py` quita el rango (`era_pack`) y el archivo queda **sin número** → `UNSORTED`/Pendientes. `File.covered_issue_ids` solo se escribe `[]` (`importer.py:476`, `library_adopter.py:470`) y nadie lo lee. La vinculación (#103) exige un número por archivo. | Relación **archivo ↔ publicaciones N:M** (D4.1), distinta de la cobertura editorial (D4.2). El rango del nombre es evidencia **candidata** (`proposed`), nunca `confirmed` automático. Sin publicación identificable no se inventa un `Issue`. | **Pendiente de diseño**: el esquema N:M **no está decidido**. Mientras tanto, Pendientes. |

### Reglas de identidad

1. **Título y año no son identidad única** de una serie ni de una publicación. Sirven para buscar y comparar.
2. **Un número solo identifica dentro de su edición.** `(serie, número)` no es una clave editorial.
3. **Serie:** UUID propio; los IDs de proveedor son únicos y paralelos (ya así). Ninguno es obligatorio.
4. **Edición:** UUID propio; lógicamente `(serie, kind, numbering_unit, nombre/ref. de fuente)`. El sello **no** entra.
5. **Publicación numerada:** `(edición, number_key)`. **Sin número:** UUID o ID externo; **nunca un `0` inventado**.
6. **Discriminantes** (para mostrar y comparar, no para identificar): sello, tradición, años, formato de publicación,
   unidad de numeración, tamaño de la serie, y los IDs externos si existen. **ISBN:** `Issue.isbn` existe como columna,
   pero **nada la escribe ni la lee en `src/`**; no se da por disponible.
7. **Es ambiguo** —y no se resuelve solo— cuando, aplicados los discriminantes disponibles, queda **más de una
   candidata compatible**, o la edición **no está identificada con confianza**, o el número **no tiene forma
   canónica**. Entonces: no se elige, no se crea un identificador, va a Pendientes o a la elección manual.

### Decisiones cerradas y abiertas

**Cerradas en este documento** (D1–D4 más esta revisión):

| Decisión | Dónde |
|---|---|
| Vocabulario de seis términos y los términos que no se usan como identidad | esta revisión |
| La obra no es entidad del modelo mínimo (reversible y aditiva) | esta revisión |
| Título + año no son identidad; un número solo identifica dentro de su edición | reglas 1–2 |
| La edición es el espacio de numeración; el sello es atributo | D2 |
| Texto libre + clave canónica por edición; rangos y renumeraciones no se fuerzan como número | D1 (principios) |
| El universo esperado se calcula contra la edición y su unidad, no contra la serie | D3 (principio) |
| Archivo ↔ publicaciones y cobertura editorial son relaciones distintas | D4 |
| Una ambigüedad persistente no se resuelve sola | regla 7 |

**Abiertas** (no se cierran aquí):

| Decisión abierta | Pasa a | Nota |
|---|---|---|
| Función exacta de `number_key` (`Annual 1`, `1.5`, `0`, `12 B`, `1/2`; subespacio de anuales) | **#125** | D1 fija los principios; la especificación (§8) la mantiene abierta. Lo necesita el criterio «colisiones con la unidad editorial acordada». |
| Qué discriminantes se muestran para homónimas y la vía manual | **#125** | Idioma/país de la serie **no están modelados**: decidir si hacen falta. |
| Reimpresión sin renumerar: «reimpresión de» | **#125** / PO | Hoy no hay dónde guardarlo. |
| Esquema de la relación archivo ↔ publicaciones (N:M, `forced`, procedencia) | **#126** | Kapowarr usa `issues_files`; ZascArr no ha elegido. |
| Recuento externo: fuente, unidad, edición y fecha; no equiparar «publicado» con «previsto» | **#126** | Consecuencia de D3. |
| Backfill y migración sin confundir recuentos; destino de `Issue.volume` y de `File.covered_issue_ids` | **#126** | Requiere el censo de filas y colisiones. |
| `editions.publisher_id` frente a `Series.publisher_id`/`imprint_id` | PO / #126 | Evitar doblar la verdad del sello (§8 de la especificación). |

**Lo que este documento no promete:** el diseño ni la implementación de #125 y #126. Solo les entrega el vocabulario,
las reglas y la lista de lo que quedó abierto.

### Límites de migración

- **Este spike no autoriza ninguna migración.** No hay `editions`, `issues.edition_id` ni `issue_coverages` en el
  esquema y no se crean aquí.
- Si se plantea, **requiere antes el censo de filas y colisiones de la base de datos** (la sección «Próximo paso»
  de este ADR; `scripts/medicion/censo_identidad.py`). **Ese censo no se ha ejecutado** contra la base real: lo único
  medido hasta ahora es el censo de **nombres** del 2026-09-27.
- La migración, cuando proceda, es aditiva y por separado, con copia de seguridad y prueba de retroceso
  (especificación §6).

### Incoherencias encontradas al verificar

- La especificación (§2) cita `importer.py:384` y `library_adopter.py:180` para la escritura vacía de
  `covered_issue_ids`; hoy son `importer.py:476` y `library_adopter.py:470`. Corregido en la especificación; el
  hecho (solo se escribe vacío, nadie lo lee) **sigue siendo cierto**.
- La especificación (§8) deja `number_key` «abierta» mientras D1 se lee como una decisión: se aclara arriba que D1 son
  **principios** y la función exacta es una decisión abierta.
- `IssueFormat` y `FileFormat` comparten la palabra «formato» sin distinguirse (ver vocabulario).

### No verificado en esta revisión (NOT RUN)

- Censo de filas y colisiones contra la base real (no hay instalación disponible).
- Casos reales **nuevos**: los cuatro casos se contrastan con el código y con la evidencia de nombres del ADR, no con
  una muestra nueva de la biblioteca.
- Vocabulario en la interfaz y en los mensajes existentes: **no auditado**; esta revisión fija el término, no corrige
  textos.
- El benchmark no se ha repetido ni ampliado.

---

*Lo que sigue es el ADR original de 2026-09-27, sin modificar salvo su cabecera.*

## Contexto

B22 pedía medir la biblioteca real y cerrar, en un solo ADR, las cuatro
decisiones del modelo de identidad editorial antes de tocar el esquema. No hay
entorno local de BD, pero el coleccionista aportó el **listado real del disco**
(`find` de `/media/WDElements/Tebeos`). Aportó además un **segundo listado**: la
carpeta de **descargas** (no la tebeoteca), que confirma y amplía los mismos
patrones con el caso Dreadstar (tres ediciones renumeradas) y ruido de descarga
(`(1)` de redescarga, `.part`, doble extensión). Ese listado es más revelador para esta
pregunta que el censo de columnas: las columnas de la BD que íbamos a medir
(`volume IS NULL`, `covered_issue_ids`) las conocemos por código — `covered_issue_ids`
se escribe siempre **vacío** en importación y adopción —, mientras que el
listado muestra la estructura editorial real que el censo de columnas no ve.

**Hallazgo central del censo de nombres:** la evidencia de cobertura **sí
existe y es abundante, pero vive en el nombre de archivo, no en
`covered_issue_ids`**. Los rangos (`01-07`, `932-942`, `122-143`) son evidencia
**candidata**: justifican no descartar el proyecto de cobertura y generar
`proposed`, pero **no** prueban que el interior del archivo contenga exactamente
esas publicaciones ni cuántas relaciones podrán confirmarse. Por eso la
procedencia inicial será «rango en el nombre (heurística)» → `proposed`, nunca
`confirmed` automático. **Esto no autoriza aún la migración**: es un censo de
nombres, no el censo de filas/colisiones de la BD que B22 prometía.

## Decisión 1 — `number_key`: texto libre + clave canónica por edición; especiales y renumeraciones no se fuerzan

**Decisión.** `Issue.issue_number` se mantiene como texto libre (el literal del
nombre). `number_key` es una clave canónica **dentro de la edición**, usada para
ordenar y desambiguar, no para sustituir al texto:
- Número entero → el entero. Sufijos (`123a`, `123b`) → `123` + sufijo (no
  colapsan con `123`).
- Especiales/anuales (`Especial 1`, `Annual 01`) **no** entran en la numeración
  principal: subespacio propio (`especial-01`, `annual-01`) o edición propia.
- Un **rango** (`049-051a`) **no** es un número: es evidencia de cobertura
  (varias grapas en un archivo), va a la relación de cobertura, no a `number_key`.
- Una **renumeración** (`nº 03 (122)`) tiene su propia edición: `03` es la clave
  en la edición de reimpresión y `122` es la referencia a la edición de grapas
  original. `number_key` no mezcla las dos.

**Evidencia (biblioteca real).** `Superman Vol2 123a/123b/123c` y
`Animal Man (NuDC) 02a/02b/02c` (sufijos); `Superman Vol2 Especial 1–8` y
`Flash v2 Annual 01–13` (especiales); `Patrulla-X, nº 03 (122)` (renumeración);
`Superman Vol2 049-051a` y `Flash v2 164-169` (rangos). De la carpeta de
descargas se suman: **Dreadstar** (`Epic Comics 01–26` y `First Comics 27–64`
continúan la numeración al cambiar de sello — frontera por verificar; `Malibu/
Norma 01–06` reinicia en 01 — señal más fuerte de edición distinta);
`Transmetropolitan #01 … 1 de 4` («X de Y» = parte de un arco, no número de
grapa); `GunSmith Cats [P1N1]…[P3N9]` (codificación parte/número);
`M0N57R355 01 al 05` (rango en español); y ruido de descarga — sufijo `(1)` de
redescarga, `.part`, doble extensión `.cbr.zip`.

**Alternativa descartada.** Forzar todo a un `float` (el `sort_order` truncado ya
documentado: `123a` → `123` colisiona con `123`), o inventar un `0` para «sin
número» (NULL es el hueco honesto; lo dice la spec y lo confirma la regla de no
mentir).

## Decisión 2 — Edición ≠ Imprint: la edición es el espacio de numeración, el sello es atributo

**Decisión.** `editions` representa una **línea de numeración** dentro de una
serie (grapas originales, reimpresión Panini, Omnigold, Integral, tomos manga…).
Identidad: `series_id` + nombre/`kind` + `numbering_unit`, nunca el sello.
`Publisher`/`Imprint` (ya existen en `Series`) siguen siendo el sello editorial
(Panini, ECC, Zinco, Planeta, Norma, Glenat…) y **no** se duplican como clave en
`editions`; `editions.publisher_id`/`imprint_id` es opcional y solo para cuando
una edición la publica un sello distinto del de la serie.

**Evidencia (biblioteca real).** El caso que lo decide: `Superman (1987)` y
`Superman Vol2 (Ed.Zinco)(1987-96)` son **dos carpetas con el mismo contenido**
(`Superman Vol2 NNN`) — un duplicado, no dos ediciones. El sello «Zinco» es
atributo; la identidad editorial es «Superman Vol2». Frente a eso,
`Patrulla-X (Panini)` (reimpresión `nº 03 (122)`), `La Patrulla X Omnigold` y
`La Imposible Patrulla X` son **tres ediciones reales** de la misma serie. El
caso más instructivo lo da **Dreadstar** en la carpeta de descargas: `Dreadstar
(Epic Comics)(01 Ed.Forum)…(26)` y `Dreadstar (First Comics) 27 USA…64 USA`
**continúan la numeración** al cambiar de sello — candidatas cuya frontera hay
que verificar (no demuestran por sí solos dos espacios de numeración);
`Jim Starlin's Dreadstar (Malibu Comics)(01 Ed.Norma)…(06)` **reinicia en 01**,
señal más fuerte de edición distinta. El sello es dato; la edición es el espacio
de numeración, y su frontera se verifica, no se deduce del sello.

**Alternativa descartada.** Modelar cada sello como una edición (dobla filas
para el mismo contenido) o usar `kind` solo como identidad (falla cuando hay dos
líneas del mismo tipo: The Boys tiene *Omnibus* y *Edición Integral* a la vez).

## Decisión 3 — El universo esperado vive en la edición, no en la serie

**Decisión.** El «total de números esperados» se calcula contra la **edición**,
no contra `Series.total_issues` (que se conserva por compatibilidad). La unidad
se acredita por `numbering_unit` + fuente: solo `single_issue` con fuente que
cuente grapas (Comic Vine) define un universo de grapas `1..N`. El manga cuenta
**capítulos** (AniList) y sus ficheros son tomos; una reimpresión renumerada
tiene su **propio** universo, independiente del de las grapas originales.

**Evidencia (biblioteca real).** `One Piece Manga Volumen 93 (932-942)` — el
tomo declara el rango de **capítulos** en el nombre, no grapas. La separación
física del disco (carpetas `Comics/` de grapas americanas frente a `Manga/` de
tomos) refuerza que no comparten unidad.

**Alternativa descartada.** Seguir usando `Series.total_issues` como universo
único — es exactamente lo que produjo los 143 huecos falsos del manga de 120
capítulos (documentado en #13).

## Decisión 4 — Archivo ↔ publicaciones es una relación distinta de la cobertura editorial

**Decisión.** Se distinguen dos relaciones:
1. **Archivo ↔ publicaciones** (N:M, al estilo de Kapowarr `issues_files`): «este
   CBZ contiene estas publicaciones». Su evidencia inicial es el **rango en el
   nombre**.
2. **Cobertura editorial** (`issue_coverages`): «este tomo publicado reproduce
   estas grapas», con procedencia y confirmación.

En esta biblioteca ambas se alimentan de la misma señal porque el archivo **es**
la publicación recopilatoria (un tomo = un CBZ con N grapas dentro). En los
ejemplos revisados **no se identificaron de forma concluyente** packs sin
publicación: un listado de disco no informa si `File.issue_id` es NULL en la BD.
Si apareciera un pack sin publicación identificable, va a Pendientes sin `Issue`
y no se le inventa uno.

**Evidencia (biblioteca real).** `Tom Strong - Volumen 1 (01-07)`,
`One Piece Manga Volumen 93 (932-942)`, `Superman Vol2 049-051a`,
`Batman · El Tribunal De Los Búhos … {BMv2 #1-12 USA}`,
`La Patrulla X (122-143 usa) Omnigold nº 2`.

**Alternativa descartada.** `File.covered_issue_ids` como única verdad (está
vacío y sin procedencia) y «dar por resuelto» tomo→grapas copiando `issues_files`
sin confirmación (Kapowarr no resuelve esa afirmación bibliográfica, §9 de la
spec).

**Benchmark cerrado (§13, 2026-10-01) — refuerza esta decisión.** Con las
referencias **fijadas por commit** (Kapowarr `c191dda`, v1.3.2; Mylar3 `cdc94a4`,
v0.8.3) y leídas **en su código**, no en su interfaz:

- **Ninguna de las dos modela cobertura editorial.** Kapowarr no tiene ninguna
  relación entre el issue de un ómnibus y los issues de la edición original: un
  TPB/ómnibus es **otro volumen con un único issue**.
- **Mylar3 sí tiene un campo** (`comics.Collects`), y es el contraejemplo que
  justifica la procedencia y la confirmación: se **raspa** del HTML de la
  descripción de Comic Vine, **solo existe** si la descripción cumple una
  condición estrecha (empezar por «trade paperback» y contener «collecting»), y
  sus únicos consumidores son **pintarlo en la ficha y escribirlo en
  `series.json`** — no alimenta huecos, estados ni búsquedas.
- El **N:M archivo↔issues** de Kapowarr (`issues_files`, con `forced`) sí se
  adopta/adapta para la relación **física**; eso no autoriza a derivar de ahí la
  relación **bibliográfica**.
- Se descartan además dos mecanismos suyos por innecesarios aquí: codificar
  sufijos y especiales en un `float` (Kapowarr) y desambiguar dos números por
  **año** (Mylar3) en vez de por edición.

Ficha completa, con lo que **no** se pudo verificar: 
`docs/design/benchmark-identidad-editorial.md`.

## Consecuencias

- **No se descarta el proyecto de cobertura**: los rangos del nombre pueden ser
  su primera procedencia como `proposed`. Pero la migración aditiva **no queda
  autorizada aún**: el censo de nombres no sustituye al censo de filas y
  colisiones de la BD (PR #20), que es el paso previo obligatorio.
- **La procedencia inicial es el nombre de archivo** (rango), etiquetada
  `proposed`; una persona confirma o rechaza. Nunca `confirmed` automático.
- **C6 sigue bloqueado** hasta que la API distinga «completa» de «no computable»
  y el coleccionista elija entre «quiero la grapa suelta» y «me basta poder
  leerla». Este ADR no lo desbloquea; solo cierra el modelo previo.
- **B20 sigue aparcado**: también mueve conceptos de edición y nombre, y
  aumentaría los contratos cambiando en paralelo.

## Próximo paso: censo de BD (B22 sigue en curso)

El censo de nombres no sustituye al censo de filas/colisiones de la BD que B22
prometía. `scripts/medicion/censo_identidad.py` (PR #20) está **escrito y
listo**: es solo lectura (transacción `READ ONLY`), seudonimiza por defecto y
solo falta correrlo contra la instalación real, que es lo único que este entorno
no tiene. Ejecutado contra la BD de pruebas (vacía) termina sin errores; el
README de `scripts/medicion/` documenta la salida compartible y la `--local`:

```bash
DATABASE_URL=postgresql://usuario:clave@host:5432/zascarr \
    python3 scripts/medicion/censo_identidad.py
```

**Qué decide cada resultado**, para que esa ejecución cierre B22 en un solo paso:

| Lo que salga | Qué implica |
|---|---|
| `colisiones_null` > 0 | Hay duplicados ambiguos que el `UNIQUE(series_id, issue_number, volume)` **no** detiene (`volume` NULL repetido). Refuerza la decisión 1 y hace prioritario un `number_key` canónico por edición. |
| `otras_ediciones_posibles` > 0 | El mismo número con volúmenes distintos **ya existe**: la decisión 2 (edición ≠ imprint) deja de ser hipotética. |
| `covered_issue_ids` no vacíos = 0 | Confirma que la cobertura no está en la BD —el código lo dice: se escribe siempre vacía en importación y adopción— y que la única procedencia disponible hoy es el nombre → `proposed`, nunca `confirmed` automático. |
| Recopilaciones con archivo disponible y sin cobertura | Es el universo real del problema. Si es **pequeño**, la revisión manual es viable y el proyecto de cobertura sigue adelante; si es **enorme**, un `proposed` masivo no aporta nada y se pospone. |
| Nada contrastable (pocas recopilaciones, ningún rango, ninguna fuente con evidencia) | **Criterio de parada de B22:** recomendar «posponer» es un resultado válido. Este ADR se cerraría como «modelo decidido, migración pospuesta». |

Con el censo en la mano la revisión final es corta: **aceptar las cuatro
decisiones** —no dependen del censo para sostenerse: son un contrato, no una
medida— y decidir **una** cosa, si la migración aditiva de cobertura se autoriza
ahora o se pospone. Orden: censo local agregado → revisión final de ADR-0003 →
decidir migración.
