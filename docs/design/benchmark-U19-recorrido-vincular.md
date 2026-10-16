# Ficha de benchmarking y matriz de navegación — U19: de la carpeta a sus archivos vinculados

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #206 (BL-U19, P0, MVP).
> **Esta ficha es de preparación: no se ha escrito código de U19 ni se mueve la tarjeta.** Es un documento propio de
> U19; no es el estudio U10 ni la ficha de U20 (`benchmark-U20-marcar-todos.md`).
> Cierra tres casillas de la Definition of Ready de #206: vigencia contra un SHA, ficha §13 identificada con su
> decisión, y matriz de navegación. **La estimación y las decisiones abiertas (D1–D4) las valida quien revisa.**

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
cierto **hasta 24 h** y **necesita una lectura nueva** (ver D3).

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

## 7. Diseño propuesto y decisiones abiertas

> Esto es una **propuesta para validar**, no una decisión tomada. Quien revisa decide D1–D4 antes de implementar.

**Propuesta (recorrido objetivo):** A → (R | L | M) → P → C → V → X, con un indicador de tres pasos
(«1 Elegir la serie», «2 Revisar los archivos», «3 Vincular») en A, P, C, V y X, `aria-current="step"` en el actual y
una frase que no da por hecho lo pendiente.

- **D1 — Selección local directa (criterio 1).** *Propuesta:* un bloque «Series que ya tienes» en A con un buscador
  `hx-get` (título parcial) sobre `ReviewService.search_series`, y los `parecidas_locales` pintados bajo cada
  candidata de R. Elegir una serie local lleva a V **sin pasar por P/C** (no hay alta: no hay E1) con la frase
  «Ya en tu biblioteca». Sin selección automática aunque haya un solo resultado. *Cuestión:* `search_series` no filtra
  por tradición ni muestra año/editorial: el criterio 1 pide «datos para distinguirlas» → mostrar año, tradición y nº
  de números ya vinculados (consulta de lectura, ¿es aceptable el coste en la Pi? límite 20 ya existe).
- **D2 — Continuidad desde una candidata (criterio 2).** *Propuesta:* en `/elegir`, en lugar de la página muerta,
  devolver la vista previa del alta **con grupo** (`previsualizar(clave, candidata=…)`, ya existe; H1). Cambio solo en
  la capa web: pasar `clave` a la plantilla y distinguir el origen. *Alternativa descartada:* quitar `/elegir` y que
  las candidatas apunten directamente a `/ui/descubrir/revisar`: `revisar` ya mezcla dos orígenes y un tercero
  (candidata + grupo) la volvería más difícil de probar. Mantener `/elegir` como el paso que pide la tradición.
- **D3 — Volver y recargar (criterios 5–7).** Es **la parte de más riesgo** (H6). Dos opciones:
  - *A (mínima, solo estado de la BD):* los textos de V y de A se calculan por lo que existe en la base («la serie ya
    existe», «quedan N pendientes»); X sigue siendo un fragmento. Criterio 7 se cumple en el sentido de «no se vuelve
    a ejecutar ni se llama pendiente a lo vinculado», **pero no** muestra el informe del comprobante.
  - *B (completa):* una **lectura nueva** del comprobante por `operacion_id` (`GET …/vinculacion/resultado?operacion=`,
    solo lectura, válida mientras dure la retención de 24 h; después, el mensaje de «ya no se conserva el resultado»
    que ya existe). Toca `services/vinculacion.py` (método de lectura, sin cambiar `confirmar` ni el formato del
    informe; la tarjeta lo permite: «no cambia ejecutar_vinculacion ni el formato del comprobante»).
  *Recomendación:* **B**, porque el criterio 7 dice «acreditado por el comprobante». Si se prefiere A, debe quedar
  escrito que el criterio 7 se cumple en versión reducida.
- **D4 — Cómo se conserva «lo elegido» al volver (criterio 5).** Sin JS y sin guardar nada en el servidor, la única
  memoria es la URL. *Propuesta:* que R, L y M acepten sus parámetros en la URL (`?clave=&consulta=`) y que el enlace
  «Volver» de P/E las reconstruya; las acciones siguen siendo POST. Sin esto, «volver antes del alta» no puede
  conservar la elección más allá de lo que el navegador cachee (y las respuestas llevan `Cache-Control: no-store`).

## 8. Casos de prueba que se escribirán ANTES de implementar (§13 punto 5)

**Aún no existen.** Se escribirán rojos primero, en Postgres real (`entorno`/`ent`, patrón de
`tests/test_asistente_carpetas_pg.py`). El caso que motivó la historia y los límites que las referencias no cubren:

| # | Criterio | Prueba (nombre por mecanismo) |
|---|---|---|
| T1 | 1 | `test_serie_local_sin_identificadores_se_encuentra_y_se_elige_sin_alta` — serie sin `comic_vine_id`/`anilist_id`/`tebeosfera_slug`; buscar y elegir lleva a V; no se crea ninguna `Series` |
| T2 | 1 | `test_candidatas_ambiguas_muestran_datos_y_no_se_elige_ninguna` — dos locales con el mismo título; ninguna preseleccionada; se ven año y tradición |
| T3 | 2 | `test_candidata_de_fuente_con_grupo_llega_a_la_vista_previa_del_alta` — regresión de H1 (hoy rojo: token con grupo no verifica sin grupo) |
| T4 | 2 | `test_elegir_candidata_no_crea_nada` y `test_confirmar_el_alta_no_vincula_ningun_archivo` (compara BD y disco) |
| T5 | 2 | `test_candidata_ya_existente_se_reutiliza_y_no_se_duplica` y `test_la_revision_recibe_el_series_id_local_no_el_externo` |
| T6 | 3 | `test_cada_pantalla_marca_su_paso_con_aria_current_step` y `test_el_paso_pendiente_no_se_presenta_como_hecho` |
| T7 | 4 | `test_navegar_y_volver_no_escriben_en_la_bd` — recorre todas las transiciones de 6.1 que no son confirmación |
| T8 | 5 | `test_volver_antes_del_alta_conserva_la_eleccion_y_dice_que_no_hay_nada_creado` |
| T9 | 6 | `test_volver_despues_del_alta_dice_que_la_serie_existe_y_no_la_repite_ni_la_deshace` |
| T10 | 7 | `test_volver_despues_de_vincular_muestra_el_comprobante_y_no_ejecuta_de_nuevo` (con D3-B) y el caso de comprobante expirado |
| T11 | 8 | `test_serie_borrada_grupo_vaciado_o_token_caducado_dicen_el_resultado_real` — sin inventar IDs ni reintentos de resultado desconocido |
| T12 | límite | `test_cambiar_de_serie_descarta_los_numeros_borrador_de_la_anterior` (patrón de Sonarr) |
| T13 | límite | `test_token_de_candidata_con_clave_larga_cabe_en_el_campo` (H2: ya medido a mano, sin test) |

Verificación en navegador (DoD): el entorno del ensayo (`ensayo.sh`) **mantiene las fuentes externas apagadas a
propósito**; el camino «candidata de fuente» se verificará con candidatas **simuladas** (como en U14) y se declarará
así, **NOT RUN** contra fuentes reales. El teclado se prueba con eventos reales (CDP), no por inspección.

## 9. Estimación (relativa, sin datos de flujo)

La tarjeta dice 8 / L / confianza Baja. Con lo leído:

| Pieza | Tamaño relativo | Riesgo |
|---|---|---|
| D2: cablear `/elegir` → vista previa con grupo (H1) | S | Bajo: el servicio existe |
| D1: buscador local + `parecidas_locales` + datos para distinguir | M | Medio: consulta de lectura nueva, accesibilidad del resultado |
| Indicador de pasos en 5 plantillas + CSS compacto | S | Bajo |
| D4: parámetros en la URL y textos de volver | S–M | Medio: muchos estados (6.2) |
| D3-B: lectura del comprobante + ruta | M | **Alto** (toca el servicio de vinculación sin cambiar su contrato) |
| T1–T13 en Postgres real + evidencia de navegador | M | Medio |

**Sin datos de flujo no se calibra con medidas, solo con comparación relativa:** la parte de continuidad (D2 + D1 +
indicador) es comparable a U20; D3-B es lo que hace que la tarjeta sea grande. *Propuesta:* mantener **8** y subir la
confianza de Baja a **Media** (H1 y H3 reducen la incertidumbre), con la advertencia de que si D3-B se complica, la
salida honesta es **partir** en U19a (continuidad: D1, D2, indicador, criterios 1–4 y 8) y U19b (volver/recargar:
criterios 5–7). **La partición no se hace sin que quien revisa la decida.**

## 10. Qué NO cambia

`ejecutar_vinculacion`, el formato del comprobante, las reglas del alta, `previsualizar`/`confirmar` del servicio de
alta, las migraciones (ninguna), la entrada de «Por revisar» (U13). Tampoco hay **ningún JavaScript propio ni
dependencia nueva** (ADR 0005, decisiones 3 y 5). Sin ADR: no cambia la arquitectura. La decisión duradera, si D3-B se
aprueba, es «lectura del comprobante por `operacion_id`» y se anotará entonces.
