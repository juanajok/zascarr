# Ficha de benchmarking y matriz de navegación — U19: de la carpeta a sus archivos vinculados

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #206 (BL-U19, P0, MVP).
> **Esta ficha es de preparación: no se ha escrito código de U19 ni se mueve la tarjeta.** Es un documento propio de
> U19; no es el estudio U10 ni la ficha de U20 (`benchmark-U20-marcar-todos.md`).
> Cierra tres casillas de la Definition of Ready de #206: vigencia contra un SHA, ficha §13 identificada con su
> decisión, y matriz de navegación. **Tercera versión** tras dos devoluciones (2026-10-16): D1–D4 resueltas por quien revisa (7); conservación al volver
> (6.4); lectura del comprobante (7.2) con la **precedencia de caducidad** (integridad → vencimiento → fila) separada de la purga.

## 1. Vigencia contra un SHA concreto

Comprobado en `main` **`b912f2e790dda90906c6ac945f8c0a77cc87aaa6`** (2026-10-16). La tarjeta cita `a5369ef`.

`git diff a5369ef b912f2e` **no cambia** ninguno de los ficheros que cita la tarjeta para el recorrido:
`_alta_resultado.html`, `_alta_vista_previa.html`, `_alta_manual_form.html`, `_asistente_resultados.html`,
`_asistente_eleccion.html`, `asistente_carpeta.html`, `web/discovery.py`, `web/asistente_carpetas.py`,
`services/alta_serie.py`, `services/descubrimiento_grupo.py`. **Sí cambian** `web/asistente_vinculacion.py`,
`_vinculacion_revision.html` y `_vinculacion_resultado.html` (U20, #212): U19 las **consume** sin tocar su contrato.

| Afirmación de la tarjeta | Estado en `b912f2e` | Dónde |
|---|---|---|
| Acceso a revisión desde el alta | **Vigente** (solo si el alta partió de una carpeta: `grupo` sale del token) | `_alta_resultado.html:22-27`, enlace en la línea 26 |
| Acceso desde una candidata de fuente coincidente por identificador | **Vigente**, solo con `ya_en_biblioteca` | `_asistente_resultados.html:39-43`, enlace en la línea 42 |
| Serie local sin fuentes solo por la coincidencia del formulario manual | **Vigente** (decisión `elegir`/`reutilizar` de las «parecidas»: mismo título normalizado, misma tradición, año ±1) | `_alta_vista_previa.html:4-18` y `17-32`; `alta_serie.py::buscar_parecidas` |
| `_asistente_eleccion.html` termina en callejón | **Vigente.** «Elección anotada…» (línea 3) y «El paso siguiente … todavía no está disponible en esta pantalla» (línea 11); solo salen «Elegir otra» y «Volver a las carpetas» | `_asistente_eleccion.html:3,11,12` |
| `POST /elegir` no crea nada | **Vigente**, y su docstring lo deja como historia aparte | `asistente_carpetas.py:175-206` |

**Rutas y contratos que U19 reutiliza** (prefijos tal cual en `b912f2e`):

| Ruta | Efecto | Nota |
|---|---|---|
| `GET /ui/pendientes/carpetas/asistente?clave=` | ninguno, no consulta fuentes | abre el asistente |
| `POST …/asistente/buscar` | ninguno, consulta fuentes a petición | resultados con `r.candidatas` |
| `GET …/asistente/manual?clave=` | ninguno | formulario a mano |
| `POST …/asistente/elegir` | ninguno (callejón) | solo anota la elección |
| `POST /ui/descubrir/revisar` | ninguno (vista previa) | acepta `candidata` o título/año a mano, `clave` opcional |
| `POST /ui/descubrir/crear` | **escribe 1 serie vacía** + comprobante | solo el token |
| `POST /ui/descubrir/deshacer` | borra la serie creada si nada depende de ella | |
| `GET …/asistente/vinculacion?clave=&series_id=&cursor=` | ninguno | recargable |
| `POST …/vinculacion/revisar` | ninguno | borradores |
| `POST …/vinculacion/confirmar` | **vincula** + comprobante (24 h, `RETENCION_HORAS`) | solo el token |

## 2. Hallazgos nuevos al comprobar la vigencia (no están en la tarjeta)

Cada uno con su prueba o su lectura; los dos primeros condicionan el diseño.

**H1 — El servicio ya soporta «candidata de fuente + carpeta»; lo que falta es el cableado web.**
`AltaDeSerie.previsualizar(clave, candidata=…)` (con grupo) existe (`alta_serie.py:255`). Pero
`web/discovery.py::revisar` envía **siempre** una candidata a `previsualizar_sin_grupo` y devuelve `clave=None` a la
plantilla (`"clave": clave if a_mano else None`, línea 247). Medido: un token de candidata firmado con la clave de
un grupo **verifica** con ese grupo y **no verifica** con `CLAVE_SIN_GRUPO` (script de comprobación, 2026-10-16:
`True / False`). Es decir, hoy una candidata del asistente **no puede** pasar por la vista previa del alta de
Descubrir, y por eso el camino está cortado en `_asistente_eleccion.html`. **Consecuencia:** el criterio 2 de #206
no necesita lógica de negocio nueva, sino que la ruta pase `clave` cuando hay candidata y la vista previa la lleve.

**H2 — Un posible problema que NO existe (descartado midiendo).** Sospeché que el límite de longitud del campo
`candidata` de `/ui/descubrir/revisar` y `/crear` (`MAX_TOKEN_CANDIDATA_SIN_GRUPO` = 12 333) rechazaría un token con
grupo largo. Medido: con una clave de 1000 caracteres el token mide 1 625. Cabe de sobra. No hace falta cambiar ese
límite (sí conviene una prueba de que no se rompe).

**H3 — El dato para elegir una serie local ya se calcula y no se pinta.** `DescubrimientoDeGrupo._candidata`
rellena `parecidas_locales` por candidata (`descubrimiento_grupo.py:83,284`); **ninguna plantilla ni ruta lo usa**
(`grep` de `parecidas_locales`: solo el servicio). Y `ReviewService.search_series(q)` (título parcial, `ilike`,
20 resultados) ya existe y lo usa el selector por archivo (`web/pendientes.py::buscar_serie`). Para el criterio 1
(«serie local sin identificadores externos, encontrada y seleccionada») hay dos piezas reutilizables y **ningún
buscador de series locales en el asistente de carpeta**.

**H4 — «Elegir otra» tira lo hecho.** Es un enlace a `asistente?clave=` (GET): se pierde la búsqueda y sus resultados.
Para quien ya esperó una consulta lenta (Tebeosfera 2,5 s/req) es un coste real.

**H5 — Hay precedente de indicador de pasos.** `dashboard.html:24` ya usa `aria-current="step"` en una `<ol
class="steps">` (CSS en `web.css:940`). El indicador del criterio 3 no necesita ninguna idea nueva ni JavaScript;
hace falta una variante compacta.

**H6 — La caducidad del comprobante acota el criterio 7.** El informe de vinculación se conserva `RETENCION_HORAS` =
24 desde la creación (`vinculacion.py:57`) y después se purga; el servicio solo expone `confirmar(token)`, no una
lectura por `operacion_id`. «Volver después de vincular muestra el resultado acreditado por el comprobante» es
cierto **hasta 24 h** y **necesita una lectura nueva** (ver 7.2).

## 3. Referencias consultadas (código leído, no pantallas)

| Referencia | Commit | Licencia | Ficheros leídos |
|---|---|---|---|
| Sonarr, rama `v5-develop` | `d137dc5a19f46a8aa6d41e706143cad1f0af27af` | GPL-3.0 | `frontend/src/InteractiveImport/Series/SelectSeriesModalContent.tsx`, `Interactive/InteractiveImportModalContent.tsx`, `InteractiveImportModal.tsx` (más `InteractiveImportRow.tsx`, leído para U20) |
| Kapowarr, rama `development` | `5b225cfed49d9eccf13e14cb2a947143477606ef` | GPL-3.0 | `frontend/static/js/library_import.js` (`openEditCVMatch`, `editCVMatch`, `searchCV`, `importLibrary`) |

**Solo como patrón: no se copia código** (barrera legal del §13). **No consultadas:** Radarr (su importación manual
comparte base con la de Sonarr pero no se leyó), Mylar3 y Suwayomi — no se buscó en ellas un recorrido
«carpeta → serie → importar», así que **no se afirma que no lo tengan**.

### Cómo lo resuelve cada una

**Sonarr (Importación manual).**
- Elegir la serie de un archivo abre un **selector sobre la biblioteca local** (todas las series ya añadidas), con un
  filtro por texto (título, `tvdbId`, `imdbId`) y «Cancelar». **No crea series ahí**: añadir una serie nueva es otro
  flujo (Añadir serie).
- Al elegir serie se **borran las decisiones que dependían de ella**: `handleSeriesSelect` pone `seasonNumber:
  undefined, episodes: []`. Elegir otra serie invalida lo elegido debajo.
- Nada se escribe hasta pulsar Importar; entonces un solo comando (`ManualImport`). «Cancelar» cierra sin efectos.
  El estado vive en memoria del cliente: no hay «volver» persistente ni recuperable al recargar.
- Importar se bloquea con filas inválidas seleccionadas o con destinos duplicados (ya recogido en la ficha de U20).

**Kapowarr (Library Import).**
- El emparejamiento de cada fila es con un volumen de **ComicVine** (fuente externa), no con una serie local: el
  equivalente a nuestra «candidata de fuente». Cambiar el emparejamiento (`openEditCVMatch` → `searchCV` →
  `editCVMatch`) es una búsqueda en la fuente.
- `editCVMatch` aplica la nueva coincidencia a **todas las filas seleccionadas** si la editada está entre ellas: un
  efecto masivo implícito.
- Importar **crea/enlaza el volumen y vincula los archivos en una sola petición** (`POST /libraryimport`), sin vista
  previa de lo que se creará aparte de la fila.
- Escape o un clic fuera **vacía la selección** (`document` listeners), sin confirmación; el estado es de JS y se
  pierde al recargar.

## 4. Supuestos de su modelo que NO valen en ZascArr

- **Elegir ≠ efecto.** En ambas, elegir serie es parte de importar y el único efecto es el botón final. En ZascArr hay
  **dos** efectos separados con su propia vista previa y su propio token (alta de serie, y luego vinculación): la
  tarjeta (criterio 4) los quiere en consentimientos distintos y Kapowarr los junta en uno.
- **Estado en el cliente.** Ambas guardan la elección en memoria del navegador (JS). ADR 0005 (decisión 3): sin JS
  propio. El estado de ZascArr tiene que poder reconstruirse **desde el servidor** (URL + base de datos), o no existe.
- **Operación inversa.** Ninguna vuelve atrás tras importar; ZascArr tiene «Deshacer» del alta (condicionado) y **no**
  tiene deshacer de la vinculación (fuera de alcance de #206).
- **Efectos implícitos sobre la selección** (Kapowarr cambia todas las filas seleccionadas; Escape las vacía): chocan
  con el invariante «nada se decide ni se descarta por la persona sin decirlo».

## 5. Adoptar / adaptar / descartar

| Idea | Decisión | Motivo |
|---|---|---|
| Selector sobre la biblioteca local con filtro de texto, sin crear nada (Sonarr `SelectSeriesModalContent`) | **Adoptar** para el criterio 1 | Es exactamente «seleccionar una serie existente sin abrir alta». Se resuelve con un `hx-get` al servidor reutilizando `ReviewService.search_series` y `parecidas_locales`, sin JS propio |
| Búsqueda en la fuente para emparejar (Kapowarr `searchCV`) | **Ya existe** (`/buscar`); **adaptar** su continuación | Lo que falta no es buscar sino continuar (H1) |
| Elegir otra opción invalida lo dependiente (Sonarr `episodes: []`) | **Adoptar** | Cambiar de serie en la revisión debe descartar los números borrador de la anterior; hoy la revisión se abre limpia para cada `series_id` (comprobar con prueba) |
| Alta + vinculación en una sola petición (Kapowarr) | **Descartar** | Rompe el criterio 4 (un consentimiento por efecto) y la vista previa de la vinculación (#119–#120) |
| Aplicar el cambio a todas las filas seleccionadas sin avisar (Kapowarr) | **Descartar** | Efecto implícito |
| Vaciar la selección con Escape/clic fuera (Kapowarr) | **Descartar** | La persona pierde lo hecho sin avisar |
| Estado en memoria del cliente (ambas) | **Descartar** | ADR 0005; el criterio 5–7 exige conservar estado entre pantallas |
| «Cancelar/Volver» sin efectos ni confirmación (Sonarr) | **Adoptar** como principio | Volver, navegar y paginar no confirman nada (criterio 4) |
| Importación automática de lo que no tiene coincidencia | **Descartar** | Ninguna selección automática (criterio 1) |

## 6. Matriz de navegación y estados

Convención de pantallas (cada una con su URL o su fragmento): **A** asistente de carpeta (`GET asistente`) ·
**R** resultados de búsqueda en fuentes (fragmento en A) · **M** formulario a mano (fragmento en A) ·
**L** (nuevo, D1) elegir entre series locales (fragmento en A) · **P** vista previa del alta (`/ui/descubrir/revisar`,
fragmento) · **C** resultado del alta (`/ui/descubrir/crear`, fragmento) · **V** revisión de la vinculación
(`GET …/vinculacion`, página recargable) · **X** resultado de la vinculación (`POST …/confirmar`, fragmento).

Efectos: **E1** crear/reutilizar serie (solo en C) · **E2** vincular archivos (solo en X). Todo lo demás: ninguno.

### 6.1 Transiciones hoy (`b912f2e`) y callejones

| Desde | Acción | Hasta | Efecto | Callejón / problema |
|---|---|---|---|---|
| A | Buscar en las fuentes | R | ninguno | |
| A | Abrir el formulario a mano | M | ninguno | |
| R | «Elegir esta serie» (`/elegir`) | **`_asistente_eleccion` (E)** | ninguno | **CALLEJÓN 1:** solo «Elegir otra» (vuelve a A y pierde R) y «Volver a las carpetas». Nada continúa (H1, H4) |
| R | «Preparar los archivos…» (solo si `ya_en_biblioteca`) | V | ninguno | Solo para candidatas que coinciden por identificador. Una serie local **sin** identificador externo no tiene entrada (criterio 1) |
| M | «Revisar lo que se creará» | P | ninguno | |
| P | `accion=elegir` → «Es esta» | P (reutilizar) | ninguno | Única vía actual a una serie local sin fuente: depende de que el título normalizado y la tradición coincidan |
| P | «Crear serie vacía» / «Usar esta serie» | C | **E1** | |
| C | «Revisar los archivos de esta carpeta» (solo con grupo) | V | ninguno | Con alta **sin** carpeta (Descubrir libre) no hay continuación |
| C | «Deshacer» | fin | revierte E1 si nada depende | |
| V | revisar/marcar/paginar | V | ninguno | |
| V | «Vincular…» (confirmar) | X | **E2** | |
| X | «Revisar de nuevo» / «Volver a las carpetas» | V / lista | ninguno | |

### 6.2 Estados de la persona y qué sabe cada pantalla (la base de los criterios 5–7)

| Momento | Qué existe en el servidor | Si recarga o vuelve atrás | Debe decir (criterios 5–7) | Cobertura hoy |
|---|---|---|---|---|
| Antes del alta (A, R, L, M, P) | Nada nuevo (tokens firmados con caducidad en el cliente) | A es recargable; R, L, M, P son fragmentos: **se pierden** | «Aún no se ha creado ni vinculado nada» | R dice «no se ha creado» solo en E; P dice «no se ha guardado» implícitamente |
| Después del alta (C) | 1 serie + comprobante `alta_operaciones` | C es un fragmento de POST: recargar **reenvía** el POST (idempotente por token) o se pierde | «La serie ya existe (id real); aún no se ha vinculado nada» | C lo dice al pie («Siguiente paso, que todavía no se ha hecho»); **volviendo a A no hay rastro** |
| Revisión (V) | Serie y archivos pendientes; nada vinculado | V es página con URL (`clave`+`series_id`): **recargable y sin efectos** | «La serie ya existe; nada vinculado todavía» (hoy no lo dice) | V no menciona el alta |
| Tras vincular (X) | Vínculos + comprobante `vinculacion_operaciones` (24 h) | X es fragmento de POST; volver a V muestra los archivos **ya no pendientes** | El resultado acreditado, sin ejecutar de nuevo, sin llamar pendiente a lo vinculado | X ofrece «Seguir revisando»; **no hay ruta de lectura por comprobante** (H6) |
| Caducidad / fallos | Token de alta o vinculación caducado; serie borrada; grupo sin registros | | El resultado real y la acción permitida (criterio 8) | Mensajes existentes: `MENSAJES_DE_FALLO`, `MENSAJE_SERIE_NO_EXISTE`, `MENSAJE_GRUPO_NO_EXISTE`, `_error` de Descubrir. Falta el caso «serie creada pero borrada antes de revisar» y «V con serie que cambió» |

### 6.3 Un efecto, un consentimiento

| Efecto | Dónde se confirma | Vista previa previa | Idempotencia |
|---|---|---|---|
| E1 alta/reutilizar | botón de P («Crear serie vacía»/«Usar esta serie»), con token | P (`revisar`) | token + `alta_operaciones` |
| E2 vincular | botón de V → X, con token | V (`previsualizar`) | token + `vinculacion_operaciones` (24 h) |

Elegir (R→P, L→P/V), cambiar de pantalla, paginar y «Volver» no confirman ninguno. **Invariante a probar:** entre A y
X solo se escriben las filas de E1 y E2 (la prueba compara la BD y el disco antes y después de cada transición que no
sea confirmación).

### 6.4 Referencias de navegación: qué conserva cada pantalla y cómo se valida (contrato de D4)

Completa 6.2. La URL es la única memoria que no depende del navegador (las respuestas llevan `Cache-Control: no-store`,
así que **no se confía en la caché ni en el botón Atrás**). Cuatro reglas:

1. **La URL lleva solo referencias que el servidor revalida en cada carga.** Ninguna es un permiso: el acceso lo da la
   autenticación existente (ver 7.2).
2. **Todo lo reconstruible tiene un GET gemelo de solo lectura** (la vista previa ya es de solo lectura: `previsualizar`
   no escribe). Las acciones con efecto siguen siendo POST con su token y su botón.
3. **Ninguna reconstrucción consulta una fuente externa.** Lo que no se puede reconstruir sin consultarlas (la lista de
   candidatas de R) **se dice**, y de ella solo se conserva el *texto* de la consulta para rellenar el campo, nunca para
   ejecutarla: buscar de nuevo es siempre un botón que pulsa la persona.
4. **Si la referencia falta, caduca o ya no vale, se dice qué pasó y qué se puede hacer**; nunca se rehace en silencio
   ni se muestra una pantalla vacía.

| Pantalla | URL de reconstrucción (GET, sin efectos) | Referencia mínima | Cómo se valida | Si caduca, cambia o falta |
|---|---|---|---|---|
| **A** asistente | `…/asistente?clave=&consulta=` | `clave`; `consulta` (≤ 200 caracteres, solo precarga el campo) | el grupo existe (ya existe) | grupo sin registros → la página de «esa carpeta ya no tiene registros pendientes» (ya existe). La consulta **no se ejecuta** |
| **R** resultados de fuentes | **no se reconstruye** | — | — | Al volver a A: «La búsqueda no se conserva (volver a hacerla consulta las fuentes). Pulsa «Buscar» si quieres repetirla». Nada se lanza solo |
| **L** series locales | `…/asistente/locales?clave=&q=` | `clave`, `q` (texto) | solo consulta la base local (`search_series`, ≤ 20) | sin resultados → «No hay series tuyas con ese título» (no es un error) |
| **M** a mano | `…/asistente/manual?clave=&titulo=&anio=` (ya admite `titulo`) | texto tecleado | las reglas de `DatosManuales` (título, año 1..9999, tradición) | datos inválidos → el formulario con el motivo y lo escrito (ya existe) |
| **P** vista previa del alta, desde candidata | `…/asistente/alta?clave=&candidata=<token>&tradition=` | el **token de candidata** (firmado, ligado a la `clave`, 15 min) y la tradición elegida | `verificar_token_candidata(token, clave)` + tradición ∈ enum. Recalcula la vista previa (las parecidas pueden haber cambiado: es lo que ya hace el servicio) | token caducado, manipulado o de otra carpeta → «Lo que elegiste caducó (se conserva 15 minutos) o no es de esta carpeta. Vuelve a buscar», con A y la consulta precargada, **sin buscar** |
| **P** a mano | `…/asistente/alta?clave=&titulo=&anio=&tradition=` | datos tecleados | `DatosManuales` | igual que M |
| **C** alta hecha | `…/asistente/alta/resultado?clave=&series_id=[&operacion=]` | `series_id` (y `operacion`, solo si el alta *creó* la serie) | la `Series` existe; si hay `operacion`, su fila de `alta_operaciones` coincide en `series_id` | ver «C reconstruida» abajo |
| **V** revisión | `…/asistente/vinculacion?clave=&series_id=&cursor=` (ya existe) | `clave`, `series_id` | grupo y serie existen (`MENSAJE_GRUPO_NO_EXISTE`, `MENSAJE_SERIE_NO_EXISTE`, ya existen) | ver el aviso de contexto abajo |
| **X** resultado de la vinculación | `…/asistente/vinculacion/resultado?ref=<referencia>` | la **referencia firmada** de 7.2 | 7.2 | 7.2 |

**C reconstruida** (criterio 6). Lo que el servidor sabe de un alta: una fila de `alta_operaciones` solo existe si el alta
**creó** la serie (estado `creada` o `deshecha`); **reutilizar no escribe nada** y no deja comprobante. Por tanto la pantalla
dice solo lo que consta:

| Hechos que el servidor encuentra | Texto (resumen) | ¿Ofrece «Deshacer»? |
|---|---|---|
| Serie existe + fila `creada` | «La serie «X» ya está creada. Quedan N archivos de la carpeta sin vincular.» + «Revisar los archivos» | **No** (solo la respuesta recién hecha lo ofrece; reconstruir no reabre un efecto) |
| Fila `deshecha` | «El alta de «X» se deshizo: la serie ya no está en tu biblioteca.» + «Volver a elegir la serie» | No |
| Serie existe, sin fila (reutilizada, o comprobante ya purgado) | ««X» está en tu biblioteca.» **No afirma** si la creó este recorrido ni que no | No |
| Serie no existe, sin fila | «Esa serie ya no existe. Vuelve a elegir.» | No |

**Aviso de contexto en V** (criterios 5–6): cuando V se abre con una `series_id` válida, dice «Vas a preparar los archivos de
esta carpeta para «X» (ya en tu biblioteca). Esta pantalla no vincula nada hasta que lo confirmes.» y el número de
pendientes que quedan. **No afirma** «aún no se ha vinculado nada» por su cuenta: eso no consta sin comprobante; se dice con
hechos («quedan N archivos pendientes de esta carpeta»).

**Cambiar de serie en V descarta los borradores de la anterior** (patrón de Sonarr, 5): los borradores viajan por
`series_id`; con otra serie, la revisión se abre limpia.

## 7. Decisiones y contratos

> **Revisión recibida (2026-10-16, en la conversación; no hay review en GitHub).** #218 **devuelta** por dos bloqueantes:
> la conservación de D4 sin especificar (6.4 la completa) y la lectura del comprobante sin contrato (7.2 lo define). Las
> decisiones D1–D4 las resolvió quien revisa; se recogen tal cual.

| Decisión | Resolución del revisor | Cómo la recoge esta ficha |
|---|---|---|
| **D1** Selección local | Buscador local y entrada directa a revisión, sin alta ni preselección. Mostrar título, año y tradición disponibles. El número de ejemplares vinculados es **opcional**: no añadir consultas por fila solo para enriquecer el selector | L muestra título, año y tradición **de la misma consulta** (`Series` ya trae ambos). **Se retira** de la propuesta anterior el «nº de números vinculados» (era una consulta por fila). Sin selección automática aunque haya un solo resultado |
| **D2** Candidata con carpeta | Reutilizar `previsualizar(clave, candidata=…)` desde `/elegir`, conservando el grupo. Elegir no escribe; alta y vinculación mantienen confirmaciones separadas | `/elegir` pasa a devolver la vista previa del alta **con grupo** (P). Confirmar (C) y vincular (X) siguen siendo dos botones y dos tokens |
| **D3** Resultado al volver | **B:** lectura del comprobante, sin ejecutar de nuevo. A no cumple íntegramente el criterio 7 y no se autoriza rebajarlo | 7.2 |
| **D4** Conservación al volver | URLs para el estado de navegación y referencias verificadas, pero `clave + consulta` no basta: debe distinguir selección local, candidata elegida y alta confirmada; volver no relanza búsquedas externas | 6.4 |

### 7.1 Recorrido objetivo

A → (R | L | M) → P → C → V → X, con un indicador de tres pasos («1 Elegir la serie», «2 Revisar los archivos», «3
Vincular») en A, P, C, V y X, `aria-current="step"` en el actual y sin presentar lo pendiente como hecho. Elegir una serie
**local** (L) lleva a V sin pasar por P ni C (no hay alta: no hay E1).

### 7.2 Contrato de la lectura del comprobante de la vinculación (D3-B)

**Qué es.** Una ruta `GET …/asistente/vinculacion/resultado?ref=` de **solo lectura** que vuelve a pintar el informe ya
guardado en `vinculacion_operaciones`. **Nunca** confirma, reintenta, repara ni alarga la retención.

**La referencia (`ref`).** Un token firmado como los demás (`crear_token`), con propósito propio `resultado_vinculacion`,
contexto = la `clave` del grupo y datos `{series_id, operacion}`. Lo emite la ruta `confirmar` **a partir del token de
vinculación ya validado** (serie, grupo y operación salen de él, no del formulario) y se pasa tal cual a los enlaces del
resultado. *Por qué firmada y no `?operacion=`:* (a) liga `clave`, `series_id` y `operacion` entre sí y a este servidor;
(b) permite **distinguir «expirado» de «manipulada o inexistente»** sin depender de que la fila siga o no en la tabla.
Es **integridad y contexto, no control de acceso**.

**El vencimiento de la `ref` es el de la retención, calculado una sola vez desde la firma del token de vinculación.**

> `vence = firma + RETENCION_HORAS × 3600`, con `firma = caduca_del_token_de_vinculacion − TTL_SEGUNDOS`
> (la misma cuenta que `confirmar` ya hace para un token caducado). La `ref` se crea con `ahora=firma` y
> `ttl=RETENCION_HORAS × 3600`, así que su `exp` **es** `vence`.

Consecuencias, para que no haya dos relojes:
- **Es una constante de la operación.** Repetir la confirmación con el mismo token (idempotente) emite una `ref` con **el
  mismo `exp`**; leer el resultado **no emite ninguna `ref` nueva** (los enlaces de esa pantalla reenvían la recibida); y
  regenerar o copiar el enlace no mueve el plazo. Leer o regenerar **no reinicia** las 24 horas.
- **Es compatible con la purga real.** `_purgar` solo borra filas con `creada < now() − 24 h` **y** `token_hasta < now()`, y
  `creada ≥ firma` (la fila se escribe al confirmar con un token ya firmado). Luego, para cualquier `ahora < vence`, la
  fila **existe físicamente** salvo fallo o borrado manual: su ausencia antes de `vence` es genuinamente inesperada.
- **El vencimiento lógico manda sobre la purga física.** Pasado `vence`, la respuesta es «expirado» **haya o no** purgado
  la fila: no se lee la tabla. (El `confirmar` repetido sí devuelve el informe mientras la fila siga; eso es un
  comportamiento ya existente que esta ficha no cambia y que la lectura no hereda: **la lectura es más estricta a
  propósito**, para que el mismo comprobante no se interprete distinto según cuándo corra la purga.)

**Servicio.** Un método de lectura en `VinculacionDeArchivos` (sin tocar `confirmar`, el formato del informe ni la tabla):
dado `(operacion_id, series_id)` devuelve la `RespuestaEjecucion` con `repetida=True` si la fila existe **y su `serie_id`
coincide**, o `None`. Reglas: una consulta por clave primaria más la de nombres actuales; **sin candado consultivo**, sin
`_purgar()`, sin `commit` con escritura, sin `flush`. (La tabla ya rechaza todo `UPDATE` con un disparador: la prueba lo
comprueba igualmente.)

**Precedencia de la comprobación** (se evalúa **en este orden** y se corta en el primer caso que aplique; con tiempo
controlado en las pruebas):

1. **Integridad y contexto** — sin mirar el reloj ni la base: `ref` ausente, malformada, firma inválida, propósito distinto,
   contexto ≠ `clave` o datos con forma incorrecta (`series_id`/`operacion` no son UUID) ⇒ **referencia no válida**. Se
   verifica con `ignorar_caducidad=True`, igual que `confirmar` lee un token caducado: así **una `ref` vencida e íntegra no se
   confunde con una manipulada**, y una manipulada nunca revela si estaba vencida.
2. **Vencimiento** — `ahora ≥ exp` (el límite exacto **ya cuenta como vencida**, como `puede = ahora >= firma + …` en
   `confirmar`) ⇒ **expirado**. No se consulta la base.
3. **Vigente** (`ahora < exp`) — se lee el comprobante:
   - hay fila y su `serie_id` coincide con el de la `ref` ⇒ **válido**;
   - hay fila con **otro** `serie_id` ⇒ **referencia no válida** (incoherente; mismo texto que el caso 1, sin pistas);
   - no hay fila ⇒ **no encontrado** (ausencia inesperada, por lo dicho arriba).

| Estado | Cuándo | Qué ve la persona | Qué puede hacer |
|---|---|---|---|
| **No válida** | caso 1, o fila con otro `serie_id` | «Esta referencia no es válida. No se ha cambiado nada.» **Sin pistas** sobre si la operación existe ni si venció | «Volver a las carpetas» |
| **Expirado** | caso 2 (`ahora ≥ exp`), **con o sin fila** | «El resultado de esta vinculación ya no se conserva (pasaron más de 24 horas). Que ya no se muestre no deshace nada: revisa la carpeta para ver su estado actual.» | «Revisar de nuevo» |
| **Válido** | caso 3 con fila coincidente | El informe de siempre (totales, por archivo, motivos en llano) con el aviso ya existente «este es su resultado guardado, no se ha repetido nada» | «Revisar de nuevo», «Volver a las carpetas» |
| **No encontrado** | caso 3 sin fila | «No se encuentra el resultado de esta vinculación. **No se sabe** si se aplicó: no lo des por hecho ni por fallido.» Sin botón de reintento (no hay token que repetir aquí) | «Revisar de nuevo» para ver qué hay vinculado |

Es el mismo razonamiento que `confirmar` ya aplica a un token caducado (`puede_haberse_aplicado`) y **no inventa éxito,
recuperación ni reintento**. El texto «pasaron más de 24 horas» es exacto porque `exp` se mide desde la firma, que es
anterior al informe.

**Qué datos expone.** Exactamente lo que el resultado inmediato ya muestra: totales, estado y número por archivo, motivo
traducido, «número nuevo en la serie», y el **nombre actual** de cada archivo que aún exista (presentación, no del informe;
si ya no existe, el texto que hoy se usa). **No** expone rutas, ids de archivo, token, sesión ni hash (el modelo no los
guarda). Las respuestas llevan `Cache-Control: no-store`.

**Acceso.** Lo da el `AuthMiddleware` global (A6) como para el resto de `/ui`: con la autenticación activada, sin sesión no
se llega ni a la ruta. ZascArr tiene **un solo operador** (no hay usuarios ni permisos por objeto), así que no hay IDOR que
modelar; el `operacion_id` (UUID aleatorio) no es un secreto, pero tampoco hay forma de listar operaciones. La `clave` ya
viaja en las URLs del asistente; no se añade ningún dato nuevo.

## 8. Casos de prueba que se escribirán ANTES de implementar (§13 punto 5)

**Aún no existen.** Se escribirán rojos primero, en Postgres real (`entorno`/`ent`, patrón de
`tests/test_asistente_carpetas_pg.py`).

| # | Criterio | Prueba (nombre por mecanismo) |
|---|---|---|
| T1 | 1 | `test_serie_local_sin_identificadores_se_encuentra_y_se_elige_sin_alta` — serie sin ids externos; buscar y elegir lleva a V; no se crea ninguna `Series` |
| T2 | 1 | `test_candidatas_ambiguas_muestran_titulo_anio_y_tradicion_y_no_se_elige_ninguna` — dos locales con el mismo título; ninguna preseleccionada, ni con una sola |
| T2b | 1 | `test_el_selector_local_no_hace_una_consulta_por_fila` — nº de sentencias constante con 1 y con 20 resultados (D1) |
| T3 | 2 | `test_candidata_de_fuente_con_grupo_llega_a_la_vista_previa_del_alta` — regresión de H1 (hoy rojo) |
| T4 | 2, 4 | `test_elegir_candidata_no_crea_nada` y `test_confirmar_el_alta_no_vincula_ningun_archivo` (BD y disco idénticos) |
| T5 | 2 | `test_candidata_ya_existente_se_reutiliza_y_no_se_duplica` y `test_la_revision_recibe_el_series_id_local_no_el_externo` |
| T6 | 3 | `test_cada_pantalla_marca_su_paso_con_aria_current_step` y `test_el_paso_pendiente_no_se_presenta_como_hecho` |
| T7 | 4 | `test_navegar_y_volver_no_escriben_en_la_bd` — recorre todas las transiciones de 6.1 que no son confirmación |
| T8a | 5 | `test_p_desde_candidata_se_reconstruye_por_get_sin_efectos` — mismo resultado que el POST; BD idéntica |
| T8b | 5 | `test_p_caducada_manipulada_o_de_otra_carpeta_dice_que_caduco_y_no_busca` — token caducado (`ahora` controlado), con la firma rota y firmado para otra `clave` |
| T8c | 5 | `test_volver_nunca_llama_a_las_fuentes` — `buscar_a_ritmo` y `DiscoveryService.search*` sustituidos por funciones que fallan; recorrer A, P, C, V, X reconstruidos |
| T8d | 5 | `test_la_consulta_se_precarga_pero_no_se_ejecuta` |
| T8e | 5 | `test_la_serie_elegida_cambia_o_desaparece_antes_de_volver` — la vista previa se recalcula y lo dice; serie borrada → mensaje, sin éxito inventado |
| T9a | 6 | `test_c_reconstruida_con_alta_creada_dice_que_la_serie_existe_sin_repetirla_ni_deshacerla` — BD idéntica; sin botón «Deshacer» |
| T9b | 6 | `test_c_reconstruida_cubre_creada_deshecha_reutilizada_y_purgada` — las cuatro filas de 6.4; **nunca** dice «no hubo alta» |
| T10a | 7 | `test_lectura_valida_devuelve_el_informe_guardado_sin_ejecutar` — `confirmar` sustituido por uno que falla; `vinculacion_operaciones` (incl. `creada`) y `files`/`issue_files` idénticos antes y después |
| T10b | 7 | `test_lectura_no_valida` — `ref` malformada, con la firma rota, con otro propósito, firmada para otra `clave`, con datos que no son UUID, y válida con otra `serie_id` en la fila: el mismo texto sin pistas |
| T10c | 7 | `test_lectura_no_encontrada_antes_del_vencimiento` — `ref` vigente y fila ausente (borrada a mano): «no encontrado», sin éxito ni fracaso ni reintento |
| T10c2 | 7 | `test_lectura_expirada_con_la_fila_ya_purgada` — `ahora` ≥ `exp`, fila purgada: «expirado» |
| **T10h** | 7 | **`test_referencia_vencida_con_la_fila_todavia_presente_es_expirada`** — `ahora` ≥ `exp`, **la fila sigue en la tabla** (la purga aún no ha corrido): «expirado», **no** el informe, y la respuesta es la misma que con la fila purgada. Con `confirmar` repetido en el mismo instante, éste sí devuelve el informe (comportamiento existente, comprobado para dejar constancia de la diferencia) |
| **T10i** | 7 | **`test_el_limite_exacto_del_vencimiento`** — con `ahora` = `exp − 1` ⇒ válido (fila presente); `ahora` = `exp` ⇒ expirado; `ahora` = `exp + 1` ⇒ expirado |
| **T10j** | 7 | **`test_integridad_antes_que_vencimiento`** — una `ref` manipulada (firma rota o `exp` alterado) y además vencida ⇒ «no válida», **no** «expirado»; una íntegra y vencida ⇒ «expirado» |
| **T10k** | 7 | **`test_leer_o_regenerar_no_reinicia_el_plazo`** — dos `confirmar` con el mismo token emiten `ref` con el mismo `exp` (= `firma + 24 h`); la lectura no emite ninguna `ref` nueva y reenvía la recibida en sus enlaces |
| **T10l** | 7 | **`test_el_plazo_es_el_de_la_retencion_original`** — para varias firmas, `exp − firma == RETENCION_HORAS × 3600`, y `_purgar` no borra ninguna fila con `ahora < exp` (la ausencia antes del vencimiento es genuinamente inesperada) |
| T10d | 7 | `test_la_lectura_no_alarga_la_retencion` — leer no cambia `creada`; tras 24 h y token caducado, la purga borra igual aunque se haya leído |
| T10e | 7 | `test_la_lectura_no_confirma_ni_reintenta` — ninguna escritura (comparación de sentencias), sin candado consultivo, sin llamar a `_purgar` |
| T10f | 7 | `test_la_lectura_no_expone_rutas_token_ni_sesion` — el cuerpo no contiene `file_path`, el token ni `zascarr_session` |
| T10g | 7 | `test_la_lectura_exige_autenticacion` — con `auth_mode=password` y sin cookie, la ruta no devuelve el informe |
| T11 | 8 | `test_serie_borrada_grupo_vaciado_o_token_caducado_dicen_el_resultado_real` — sin inventar IDs ni reintentos de resultado desconocido (alta y vinculación) |
| T12 | límite | `test_cambiar_de_serie_descarta_los_numeros_borrador_de_la_anterior` (patrón de Sonarr) |
| T13 | límite | `test_token_de_candidata_con_clave_larga_cabe_en_el_campo` (H2: medido a mano, sin test) |

Verificación en navegador (DoD): el entorno del ensayo (`ensayo.sh`) **mantiene las fuentes externas apagadas a
propósito**; el camino «candidata de fuente» se verifica con candidatas **simuladas** (como en U14) y se declara así. El
teclado se prueba con eventos reales (CDP); el anuncio del indicador de pasos, con Orca como en U14. Lo no ejecutado
(otros lectores, móvil real, Pi) se declara **NOT RUN**.

## 9. Estimación (relativa, sin datos de flujo)

Se mantiene **8 y confianza Media** (decisión del revisor); esta ficha no las cambia. Lo que añaden los contratos:

| Pieza | Tamaño relativo | Riesgo |
|---|---|---|
| D2: `/elegir` → vista previa con grupo (H1) | S | Bajo: el servicio existe |
| D1: buscador local + `parecidas_locales` (sin consulta por fila) | M | Medio |
| Indicador de pasos en 5 plantillas + CSS compacto | S | Bajo |
| D4: GET gemelos (P, C), `ref`, avisos de V, textos de volver (6.4) | M | **Medio-alto**: muchos estados |
| D3-B: lectura + `ref` + ruta + cuatro estados (7.2) | M | **Alto**: toca el servicio de vinculación sin cambiar su contrato |
| T1–T13 en Postgres real + evidencia de navegador/Orca | M–L | Medio |

La carga se concentra en D3 y D4, que son los criterios 5–7. **Señal para decidir partir** (la decide quien revisa, no
yo): si al escribir los tests rojos de T8–T10 el cableado de 6.4 y 7.2 supera lo que cabe en una sola PR revisable. **Una
partición no elimina los criterios 5–7:** cualquier corte debe dejarlos como una tarjeta enlazada a #206 con su
trazabilidad (criterio → prueba), y #206 no se cierra mientras ellos estén abiertos.

## 10. Qué NO cambia

`ejecutar_vinculacion`, el formato del comprobante, las reglas del alta, `previsualizar`/`confirmar` del servicio de
alta, las migraciones (ninguna), la entrada de «Por revisar» (U13). Tampoco hay **ningún JavaScript propio ni
dependencia nueva** (ADR 0005, decisiones 3 y 5). Sin ADR: no cambia la arquitectura. La decisión duradera, si D3-B se
aprueba, es «lectura del comprobante por `operacion_id`» y se anotará entonces.
