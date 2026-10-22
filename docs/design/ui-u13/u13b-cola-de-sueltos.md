# U13b — Cola de sueltos (solo lectura)

> **Estado 2026-10-22:** implementación local terminada, pendiente de revisión. Contrato vigente en
> el issue #288; este documento recoge las decisiones y la evidencia de la PR.
>
> **Base:** `origin/main` `0fb10f095b16a0b220b150d95127b4ae36c1cdd8`. U13b es **independiente de
> U13a**; comparte la definición de suelto de #200 y no requiere que #287 esté fusionada.
>
> **Límites:** no se ha probado en navegador real, lector de pantalla, Pi ni biblioteca real. Esas
> comprobaciones siguen **NOT RUN** y no se presentan como PASS.

## 1. Historia

**Como** coleccionista,
**quiero** recorrer los archivos que no tienen una carpeta de serie y ver, para cada uno, la
sugerencia guardada o la ausencia explícita de sugerencia,
**para** saber qué queda suelto y decidir después, sin que la navegación cree, asigne, mueva ni
ignore nada.

## 2. Alcance

**Dentro**

- `GET /ui/pendientes/sueltos`, solo lectura y paginada.
- Los **sueltos de A**: los 14 del fixture de referencia, dentro de los 1.322 de «Por revisar».
- Nombre completo, `Detectado: …` y el estado de la candidata guardada.
- Enlaces GET a «Por revisar» y a la vista de carpetas.
- Enlace de entrada desde la vista individual existente (`/ui/pendientes`).

**Fuera**

- Los sueltos de B: no entran en esta cola (U13a los cuenta aparte si existen).
- Asignar, crear series, vincular, mover, renombrar o ignorar.
- Persistencia de `review_dismissed`, `metadata.candidates` o cualquier otro campo.
- Buscador o filtro nuevos dentro de esta vista.
- Comprobar si la serie candidata existe (`candidata_inexistente` pertenece a U13a).

## 3. Selección y paginación

`A_sueltos` es exactamente el subconjunto de archivos de A cuya ruta, tras `dividir_ruta()`, tiene
`contextual is None`. A se obtiene con el mismo filtro de «Por revisar»:

1. `issue_id IS NULL`.
2. `review_dismissed = false`.
3. `metadata->match_status = 'unsorted'`.

La regla se aplica después de leer A; un archivo agrupado sin candidata no entra por el hecho de no
tener sugerencia. Los sueltos de B no se mezclan.

- Orden: `(imported_at DESC, id DESC)`, el cursor de `ClavePendiente` de U12.
- Página: **50** (`POR_PAGINA`).
- Parámetros: `despues` y `antes`; una clave inválida, las dos a la vez o una clave que ya no existe
  dan la primera página.
- Sin `OFFSET`: se lee A una vez, se filtra en memoria y se corta la página; la respuesta solo lleva
  la página. No se consulta `series`.
- Texto: «Sueltos X–Y de N» y «N de 1.322 por revisar», con separador de miles.
- `Cache-Control: no-store`.

La lectura interna devuelve `file_path`, `imported_at`, `id`, `file_name` y `metadata` de A. Una
petición ejecuta una sola sentencia SQL; no hay una consulta por tarjeta ni por página.

## 4. Tarjeta

Cada tarjeta muestra:

- El nombre completo (`file_name`) sin truncar; si no cabe, se parte.
- `Detectado: …` con el mismo `_detected_label()` de la tarjeta existente.
- Uno de los tres estados siguientes.

### 4.1 Candidata guardada

Se lee **solo** `metadata.candidates[0]` y se muestra como texto:

> **Sugerencia guardada:** «Título» (año) · 94% · **no aplicada**.

- No hay formulario, botón de asignar ni número prefijado.
- Si `start_year` falta, se omite el paréntesis.
- La candidata se muestra **tal como está guardada**: no se comprueba si la serie existe.
- No se usa `tradition_guess` para decidir si hay candidata.

### 4.2 Sin candidata

Si `metadata.candidates` no existe o es una lista vacía:

> **Sin serie candidata guardada.** No se deduce ninguna serie del nombre ni de la tradición. Puedes
> abrirla en «Por revisar» para buscarla.

No se rellena una tradición por defecto ni se deduce una serie del nombre o de la carpeta.

### 4.3 Candidata ilegible

Si `metadata.candidates` no es una lista o el primer candidato no tiene `series_id`, `title` o
`score` utilizables, se muestra:

> **No se pudo leer la sugerencia guardada.**

Se registra un aviso sin ruta ni nombre y la página sigue funcionando. No se inventa una candidata.

## 5. Contraste con #276

La ausencia de tradición sugerida no es la ausencia de serie candidata:

| Situación | U13b muestra | U13b NO hace |
|---|---|---|
| Candidata guardada, sin `tradition_guess` | «Sugerencia guardada: …» | No dice «sin serie» ni rellena la tradición. |
| Sin candidata, con pista de tradición | «Sin serie candidata guardada» | No convierte la pista en una serie. |
| Sin candidata ni tradición | «Sin serie candidata guardada» | No inventa serie ni tradición. |
| Candidata guardada cuya serie ya no está en `series` | La candidata guardada | No consulta `series` ni la declara inexistente; eso es U13a. |

`tradition_guess` no se lee en U13b. El fixture obligatorio incluye una candidata guardada sin
tradición y se comprueba que sigue visible.

## 6. Errores, vacío y navegación

| Caso | Comportamiento |
|---|---|
| Cursor inválido o ambos cursores | Primera página; no es error. |
| `despues` que ya no existe | Primera página, sin prometer una instantánea. |
| Sin sueltos | «No hay archivos sueltos» y enlace GET a carpetas. |
| Candidata ilegible | Texto explícito y aviso en log; no 503. |
| Fallo de lectura | **503** sin recuentos parciales; enlace para reintentar. |
| Fallo de una tarjeta | No se sustituye por datos de otra; se muestra el estado explícito. |

La cabecera enlaza a «Por revisar» y a «Pendientes por carpeta». La paginación usa enlaces reales
`rel="prev/next"`; no hay JavaScript propio ni controles de escritura.

## 7. Solo lectura y accesibilidad

- No hay `<form>`, `<button>`, `hx-post`, `hx-delete`, `hx-put` ni `type="submit"`.
- No se llama a `dismiss()`, `asignar()` ni a ningún servicio de escritura.
- Una prueba con oyente SQL comprueba que solo hay `SELECT` y que la consulta no usa `OFFSET`.
- El estado se transmite con texto, no solo con color; cada tarjeta tiene nombre accesible y el
  nombre completo se parte sin recortarse.
- Navegador real, lector de pantalla, 360 px y cinco segundos: **NOT RUN**. La prueba local es ASGI.

## 8. Implementación y evidencia local

Archivos:

- `src/zascarr/services/revision_carpetas.py`: `CandidataGuardada`, `Suelto`, `PaginaSueltos`,
  `_candidata_guardada()` y `RevisionCarpetas.pagina_de_sueltos()`.
- `src/zascarr/web/pendientes.py`: `GET /ui/pendientes/sueltos`, enlaces y estados.
- `src/zascarr/web/templates/sueltos.html`: vista, tarjetas, vacío, error y paginación.
- `src/zascarr/web/templates/pendientes.html`: enlace de entrada.
- `src/zascarr/static/web.css`: lista de sueltos y nombre partible.
- `tests/test_web_sueltos_pg.py`: aceptación, fixture de referencia, cursor, lectura y medición.

Evidencia local (PostgreSQL 15 real, ASGI, sin navegador):

- **12 passed** en `tests/test_web_sueltos_pg.py`.
- **122 passed** al repetir la suite de U13b junto con `test_pendientes_navegacion_pg.py`,
  `test_web_carpetas_pg.py`, `test_revision_carpetas_pg.py` y
  `test_web_componentes.py::TestCompatibilidad`.
- Fixture de referencia: **1.322 A** (1.308 en 108 carpetas + 14 sueltos), **14** en la cola y
  **17 B** fuera.
- Una petición: **1 SELECT**, sin `OFFSET`, sin consultar `series`; `files` no cambia.
- Medición local de 20 lecturas sobre el fixture de referencia: **p95 ≈ 56 ms** en ASGI. El
  objetivo de desarrollo es ≤ 300 ms; no es una medición de navegador ni de Pi.
- `ruff check` sobre los archivos modificados: **All checks passed!**

## 9. Criterios de aceptación cubiertos

1. Solo entran los sueltos de A; el agrupado sin sugerencia y los B quedan fuera.
2. Los 14 están dentro de 1.322 y el texto no dice 1.336.
3. Solo enlaces GET; no hay «Ignorar» ni escritura.
4. La candidata se muestra como «no aplicada», sin botón ni número prefijado.
5. La ausencia se dice explícitamente y no se deduce de la tradición.
6. Candidata guardada sin tradición visible; `tradition_guess` no participa.
7. Candidata ilegible no rompe la página; no se comprueba la existencia de la serie.
8. Cursor inválido o caducado -> primera página; sin `OFFSET`.
9. Solo `SELECT`; `review_dismissed` permanece igual.
10. Navegador, lector, 360 px y cinco segundos: **NOT RUN**, no PASS.

## 10. Referencias

- `src/zascarr/services/review.py`: `ReviewService._condiciones_pendientes`, `ClavePendiente`,
  `POR_PAGINA`.
- `src/zascarr/core/carpetas.py::dividir_ruta`.
- `src/zascarr/services/revision_carpetas.py`: `RevisionCarpetas._carpetas_de`.
- Issue #288 y regla compartida de #200 (comentario `6340045935`).
- #276: contrato de tradición del alta, citado solo como contraste.
