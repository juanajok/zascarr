# Retorno al contexto tras aceptar el aviso legal (UATP-01 / UXA-07)

> **Estado:** especificación para implementar y verificar (task-12, 2026-11-20). **No declara
> cumplido** el criterio «conserva consulta o selección válida» de Deseados: ver §8 **D-1**.
>
> **Insumos:** [#1124 · UXA-07](https://github.com/juanajok/zascarr/issues/1124) (ampliada por
> UATP-01), [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141), el primer corte
> de [PR #1180](https://github.com/juanajok/zascarr/pull/1180) (abierto; este documento corrige
> algunas de sus decisiones) y el informe de Benchmarking de UATP-01 (task-6, 2026-11-20; solo
> lectura, no versionado). Procedimiento y vocabulario del benchmark:
> [`benchmark-referencias.md`](benchmark-referencias.md).
>
> **Único escritor de este documento:** SPEC.writer. No toca código: la implementación es task-7.

## 1. Problema y resultado esperado

**Problema (estado de partida verificado en `main` y en el primer corte de #1180):**

- `services/legal.py::require_legal_acknowledgment` responde 403 con `HX-Redirect: /ui/legal`
  **sin destino**. `web/legal.py::accept` redirige siempre a `/ui/biblioteca`: quien venía de
  Deseados, de Mejoras o de la ficha de un número pierde la tarea.
- `volver_legal` acepta cualquier ruta que empiece por `/ui/`; no hay lista cerrada, ni filtro de
  parámetros, ni exclusión de banderas de un solo uso (`guardado`, `error`…), ni `no-store`.
- El gate **solo funciona con htmx** (403 + `HX-Redirect`). Los formularios normales de
  «Buscar una edición mejor» (`issue_detail.html:32`), «Escanear»/«Descargar» en Mejoras
  (`mejoras.html:9`, `:25`) y «Descargar esta edición» (`mejores_numero.html:27`) reciben el
  JSON `{"detail":"legal_acknowledgment_required"}` en el navegador.
- Los enlaces directos al aviso (`wishlist.html:21`, `_seguimiento_serie.html:15`,
  `_politica_serie.html:108`, `_lector_fin.html:26`) no llevan contexto: aceptar desde ellos
  también acaba en Biblioteca.
- `/ui/deseados` **no existe**: la ruta real es `/ui/wishlist` (los tests del primer corte usaban
  la ruta inventada). La búsqueda de Deseados vive en el DOM (`wishlist.html:27`, `hx-get` sin
  `hx-push-url`) y la selección son checkboxes del DOM (`_fila_wishlist.html:3`, lote en
  `wishlist.html:50`); **ni una ni otra viajan en la URL** (`web/wishlist.py::index`, `:94`, no
  lee query).

**Resultado esperado:** al aceptar las tres casillas, la persona vuelve a la página desde la que
intentó la acción protegida, con el estado de vista que esa página sí lee de la URL; si no hay un
destino válido, a `/ui/biblioteca`. El retorno funciona con htmx y con formularios normales, sin
JavaScript nuevo; una aceptación incompleta no guarda nada, conserva el destino y explica qué
falta; el destino nunca sale del propio servidor; la acción protegida **no se reintenta**.

## 2. Alcance / no alcance

**Dentro:**

| Pieza | Cambio |
|---|---|
| `services/legal.py` | Resolver único del destino (prioridad §3.1) y lista cerrada §3.2; gate con 403 htmx / 303 formulario normal / 403 JSON de API; `Cache-Control: no-store`. |
| `web/legal.py` | `GET /ui/legal` acepta `volver` y `falta`; `POST /ui/legal/accept` devuelve 303 al destino validado (o al respaldo); mensaje honesto de aceptación incompleta. |
| `web/templates/legal_wizard.html` | Campo oculto `volver` ya validado; aviso `falta`; enlace «Volver» del estado aceptado al destino. |
| Enlaces directos al aviso | Añadir `volver` a los 4 enlaces de §1 (Deseados, seguimiento/política de la ficha y final del lector). |
| `tests/test_legal.py`, `tests/test_log_acceso.py` | Casos §6; `falta` en el inventario `PARAMETROS_DE_QUERY` (`test_log_acceso.py:350`). |
| Suites dependientes | Ajustes mínimos en `test_web_wishlist*`, `test_api_wishlist`, `test_lector`, `test_web_series`, `test_web_navegacion` si el comportamiento intencional cambia. |

**Fuera:** cambiar `LEGAL.md` o `legal_version`; rediseñar el wizard (contenido, copy más allá del
aviso de `falta`); hacer que la búsqueda/selección de Deseados viaje en la URL (D-1); persistir el
destino en sesión, BD o cookie; firmar el destino con token; tocar el retorno Biblioteca → ficha
de BL-IT03 (`web/retorno.py`); autenticación/`returnUrl` de login; redirigir clientes de API al
wizard; añadir dependencias, migración o JavaScript; cambiar el endpoint del gate o volverlo
middleware.

## 3. Contrato de destino

### 3.1 Fuentes y prioridad

Un único resolver, usado por el gate (para construir el `volver` del 403/303) y por el wizard
(para pintar el campo oculto y para el 303 de `accept`). Prioridad **estricta**:

1. **`volver` explícito**: query de `GET /ui/legal` o campo del formulario de `POST
   /ui/legal/accept`. Es la única fuente que el llamador puede aportar; se revalida siempre
   (el campo oculto no es autoridad).
2. **`HX-Current-URL`** de la petición gateada (htmx).
3. **`Referer`** de la petición gateada (navegador/formulario normal).
4. **Respaldo**: la constante `/ui/biblioteca` (un solo literal; no se duplica en plantillas ni
   tests).

Reglas de resolución:

- Un candidato inválido **no aborta**: se prueba el siguiente. Si ninguno vale, respaldo.
- `HX-Current-URL` y `Referer` solo se aceptan si son de **este servidor**: esquema `http`/`https`
  y `hostname` (minúsculas, sin puerto) igual al `Host` de la propia petición. Si no, se ignoran
  (un `Referer` ajeno no decide adónde se vuelve). De una URL absoluta se conservan **solo ruta y
  query**; el fragmento se descarta (no viaja al servidor).
- La URL de la propia petición gateada **no** es candidata: es una acción, no una página.
- El valor devuelto se usa **tal cual** (sin normalizar) para no reescribir la URL que construyó
  la app; lo único que se transforma es la parte local de un candidato absoluto (punto anterior).
- Al construir `/ui/legal?volver=…` y el 303 de `accept`, el destino se codifica con
  `quote(destino, safe="")`. En el `Location` final va el valor ya validado, que empieza por `/`
  y nunca por `//`.

### 3.2 Lista cerrada de páginas y parámetros

Solo estas páginas (ruta exacta, sin subrutas) y solo estos nombres de parámetro. Una página
nueva con un control gateado (o un enlace directo al aviso) **añade su entrada y su prueba**;
mientras no esté, el destino cae al respaldo.

| Destino exacto | Por qué (control gateado / caso) | Parámetros de estado permitidos |
|---|---|---|
| `/ui/wishlist` | «Añadir a deseados», «Reintentar», «Buscar ahora», «Buscar seleccionados», «Descargar candidato»; banner del aviso | **ninguno** hoy (la búsqueda no está en la URL; ver D-1) |
| `/ui/descubrir` | «Añadir a deseados» del alta | `q` |
| `/ui/descubrir/identificador` | Ídem, por identificador | `identificador` |
| `/ui/mejoras` | «Escanear», «Descargar» | `pagina` |
| `/ui/series/<uuid>` | Enlaces «Aceptar el aviso legal» de seguimiento y política de la ficha | `volver` (contexto BL-IT03, validado por `web/retorno.py`; no se confía en su valor) |
| `/ui/series/<uuid>/numero/<uuid>` | «Buscar una edición mejor», «Descargar esta edición» | **ninguno** |
| `/ui/leer/<uuid>` | «Añadir a Deseados» al terminar el número | **ninguno** |

- `<uuid>` es el UUID canónico de 36 caracteres con guiones (hex en cualquier caja). La ruta se
  compara con `fullmatch`: no vale con barra final, subruta ni sufijo (`.jpg`, `/pagina`, etc.).
- `/ui/biblioteca` **no es una entrada** de la lista: es el respaldo constante (D-4). Si se
  quisiera volver a una Biblioteca filtrada habría que añadirla con los parámetros de
  `web/retorno.py::PARAMETROS_DE_VUELTA`.
- Quedan **fuera por definición**: `/ui/legal` y `/ui/legal/accept` (el propio aviso), `/api/**`
  (contrato JSON), endpoints de fragmento (`/ui/wishlist/buscar-serie`,
  `/ui/biblioteca/resultados`, respuestas `_fila_*`/`_resultados_*`, etc.), rutas de imagen y
  cualquier ruta desconocida.

### 3.3 Rechazo y canonicalización

No se repara lo que no es canónico: **se rechaza**. Un candidato/`volver` es inválido si:

- está vacío o supera 2000 caracteres;
- contiene controles (`ord < 32` o `127`), espacios o cualquier `isspace()`, o barra invertida;
- empieza por `//` **sobre el valor original** (`///ui/...` lo resolvería el navegador como host,
  aunque `urlsplit` lo vea como ruta); los candidatos de cabecera ya vienen reducidos a ruta+query
  y, en el `volver` explícito, tras `urlsplit` no puede haber esquema, host ni fragmento;
- no empieza por `/`, contiene `//` en la ruta, contiene `%` en la **ruta** (esto rechaza
  `%2e%2e`, `%2f`, `%00`, `%20`…), o tiene un segmento `.` o `..`;
- su query no se puede leer con `parse_qsl(..., keep_blank_values=True)`, repite un nombre, tiene
  un nombre vacío o un nombre fuera de la lista de la página;
- no coincide con ninguna ruta de §3.2.

**Valores de parámetro:** no se reinterpretan; se conservan codificados. Para no producir
destinos rotos, se exigen los límites que ya impone la ruta: `pagina` entero positivo; `q` ≤ 200
caracteres (`web/discovery.py:100`); `identificador` ≤ 500 (`web/discovery.py:164`). El resto de
valores son datos de la persona y la página de destino los valida como siempre.

**Sin normalizar:** no se añade ni quita barra final, no se cambia la caja, no se decodifica la
ruta, no se colapsan barras, no se ordenan parámetros. La comparación es exacta.

### 3.4 Banderas de un solo uso

Son parámetros que solo anuncian el resultado de una acción ya ocurrida. Si se conservaran al
volver, repintarían un éxito que no ha pasado (o un error ajeno). **Nunca** se permiten como
destino. En estas páginas: `guardado` (Mejoras, ficha de serie, ficha de número), `error`,
`nota`, `coleccion`, `exito`, `aviso`, `falta` (solo del wizard). Todo parámetro nuevo que se
quiera admitir debe justificar que es **estado de la vista** y traer una prueba de que volver con
él no anuncia una acción que no ocurrió.

### 3.5 Qué se conserva y qué no

- Se conserva: el filtro/página de una vista que la ruta lee de la URL (`q`, `tradition`,
  `publisher_id`, `character_id`, `story_arc_id`, `page`, `vista` en una futura Biblioteca;
  `q` en Descubrir; `pagina` en Mejoras) y el `volver` anidado de la ficha de serie.
- No se conserva: scroll, foco, texto tecleado en un buscador que no actualiza la URL, checkboxes
  marcados, pestañas ni el panel abierto. Nada de eso es una URL; no se inventa estado de sesión
  para simularlo (D-1).

## 4. Comportamiento HTTP

El gate distingue el tipo de cliente de la petición gateada (no el destino):

| Petición | Sin aceptación | Respuesta |
|---|---|---|
| htmx (`HX-Request: true`) | 403 + `HX-Redirect: /ui/legal[?volver=…]` + `Cache-Control: no-store` | htmx navega solo; `detail` JSON sin cambios; cero JS nuevo |
| Petición normal bajo `/ui/` (sin `HX-Request`, `Accept` contiene `text/html`) | 303 + `Location: /ui/legal[?volver=…]` + `Cache-Control: no-store` | el navegador pinta el wizard, no JSON |
| API/JSON (`/api/**`, o sin `text/html` en `Accept`) | 403 + `detail: legal_acknowledgment_required` + `HX-Redirect` (compatibilidad) + `Cache-Control: no-store` | contrato actual intacto |

- Solo las rutas `/ui/` pueden responder 303; `/api/**` **nunca** redirige al wizard.
- El gate es una dependencia: no puede devolver un `RedirectResponse`. El 303 se consigue con
  `HTTPException(303, headers={"Location": …})` o con una excepción propia registrada como handler
  (no un middleware global). Lo exigible es la respuesta observable de la tabla, no el mecanismo.
  Si se usa `HTTPException`, comprobar que `web/errores.py::manejar_http` no reescribe el 3xx
  (hoy los formularios gateados son POST y no pasan por la página de error; un GET gateado
  futuro sí, y habría que dejar pasar el 3xx con su `Location`).
- `GET /ui/legal` responde 200 con el formulario (o el estado «aceptado») y `no-store`; si
  `volver` es inválido pinta el respaldo y no promete conservarlo.
- `POST /ui/legal/accept`:
  - tres casillas → una fila de acuse y 303 al destino validado (o al respaldo), `no-store`;
  - incompleta → 303 a `/ui/legal?volver=<destino>&falta=1`, **sin** fila de acuse,
    `no-store`; el aviso explica que falta marcar las tres y que no se ha registrado nada; si el
    destino se perdió, el texto **no** dice que se conserva.
- Se usa **303** (POST → GET), nunca 302; el navegador no reenvía el POST al volver.
- `Cache-Control: no-store` es obligatorio en **toda** respuesta que lleve o acepte el destino:
  403 del gate, 303 de `accept` (completa e incompleta) y 200 del wizard. Motivo: el destino puede
  contener contexto de la persona y una respuesta cacheada podría reutilizarlo o mostrar un
  wizard obsoleto.
- La acción protegida **no se reintenta** en ningún caso: aceptar solo registra el acuse y
  devuelve a la página; la persona vuelve a pulsar el control y, si la acción tiene confirmación
  propia (candidato, descarga, lote), sigue exigiéndose.

## 5. Criterios de aceptación (UATP-01)

Trazabilidad: #1124 CA1 → AC-02/AC-03/AC-08; CA2 → AC-05/AC-06/AC-04/AC-12; CA3 → AC-07/AC-09;
UATP-01 (texto literal) → AC-11 (parcial) y D-1.

- **AC-01 · Gate htmx.** Sin acuse, desde `/ui/wishlist` con `HX-Request: true` y
  `HX-Current-URL` del mismo servidor, una acción gateada responde 403,
  `HX-Redirect: /ui/legal?volver=%2Fui%2Fwishlist`, `Cache-Control: no-store`, y no ejecuta la
  acción.
- **AC-02 · Aceptación completa.** `POST /ui/legal/accept` con las tres casillas y
  `volver=/ui/wishlist` responde 303 `Location: /ui/wishlist`, `no-store`, registra **una** fila
  de acuse; `GET /ui/wishlist` responde 200 y muestra «Deseados»; `/api/legal/status` da
  `accepted: true`.
- **AC-03 · Prioridad y procedencia.** `volver` explícito gana a `HX-Current-URL` y a `Referer`;
  sin explícito, gana `HX-Current-URL`; sin este, `Referer`; si todos faltan o son inválidos,
  respaldo. Un candidato de otro host se ignora y se pasa al siguiente. Un candidato inválido no
  gana por ser el primero.
- **AC-04 · Destino inválido.** Esquemas (`https:`, `javascript:`), `//host`, `///ui/...`,
  barra invertida, espacios/controles, `..`, `%2e%2e`, cualquier `%` en la ruta, fragmento,
  `/api/...`, `/ui/legal`, página desconocida, parámetro desconocido o bandera de un solo uso →
  respaldo `/ui/biblioteca` (si no hay otro candidato válido); el `Location`/`HX-Redirect`
  resultante es local y nunca empieza por `//`. El wizard pinta el respaldo, no el valor inválido.
- **AC-05 · Aceptación incompleta.** Con una o dos casillas: no se registra nada; 303 a
  `/ui/legal?volver=<destino>&falta=1` (el `volver` del respaldo puede omitirse); el destino
  válido se conserva; el aviso dice que falta marcar las tres y que no se ha guardado nada. Si
  el destino era inválido, el aviso no promete conservarlo. El wizard responde 200 con `no-store`.
- **AC-06 · Acceso directo.** `GET /ui/legal` sin `volver` ni historial → wizard con respaldo;
  aceptar → 303 `/ui/biblioteca`. Un POST gateado sin `HX-Current-URL` ni `Referer` usa el
  respaldo.
- **AC-07 · No reintento.** Durante el 403 y el `accept` no se llama al servicio/Orchestrator de
  la acción protegida (espía a cero). Tras aceptar, la persona debe volver a pulsar el control;
  la confirmación propia de la acción sigue vigente.
- **AC-08 · Formularios normales.** Un `POST` no-htmx bajo `/ui/` con `Accept: text/html` (p. ej.
  «Buscar una edición mejor» o «Escanear») responde 303 al wizard, no el JSON 403; tras aceptar,
  303 de vuelta a la página de origen; repetir la acción ya funciona.
- **AC-09 · Cliente JSON.** `POST /api/wishlist` sin acuse sigue recibiendo 403 con
  `detail: legal_acknowledgment_required` y `no-store`; no se redirige al wizard.
- **AC-10 · Enlaces directos.** Los 4 enlaces de §1 llevan `volver` de su propia página
  (`/ui/wishlist`, `/ui/series/<uuid>` —con su `volver` anidado si lo hay— y
  `/ui/leer/<uuid>`); aceptar desde ellos vuelve allí.
- **AC-11 · Deseados (mínimo acreditable, parcial).** Con el acuse pendiente, una acción gateada
  desde `/ui/wishlist` vuelve a `/ui/wishlist` (200, «Deseados» y la fila sigue ahí), sin ejecutar
  la acción y sin sacar a la persona del flujo. **No se acredita** que se conserven el texto
  buscado ni las casillas marcadas: hoy no viajan en la URL. Ver D-1; no cerrar UATP-01 como
  cumplida sin decisión del PO.
- **AC-12 · no-store, lista cerrada e inventario.** Todas las respuestas que llevan o aceptan
  destino tienen `Cache-Control: no-store`; ninguna página/parámetro fuera de §3.2 se acepta como
  destino (el respaldo es una constante, no una entrada); `falta` está en `PARAMETROS_DE_QUERY`
  (`tests/test_log_acceso.py:350`) y las pruebas de log pasan (los valores de query no se
  registran).

## 6. Casos de prueba

Nombres orientativos; lo exigible es el caso. Todos con `FakeSession`/TestClient salvo el UAT.

| # | Caso | Dónde | Espera |
|---|---|---|---|
| T1 | Destinos permitidos de §3.2 (parametrizado) | `test_legal.py::TestVolverLegal` | mismo valor, sin normalizar |
| T2 | Rechazos: `//`, `///`, `%2e%2e`, `%2f`, `\`, espacios, controles, `..`, fragmento, `/api/`, `/ui/legal`, desconocida, param desconocido, `guardado` | ídem | `None` |
| T3 | Prioridad explícito > `HX-Current-URL` > `Referer` > respaldo | `TestResolucionDelDestino` | destino esperado en cada combinación |
| T4 | `HX-Current-URL`/`Referer` de otro host se ignoran | ídem | siguiente candidato o respaldo |
| T5 | 403 htmx con `HX-Redirect` codificado y `no-store` | `TestRequireLegalAcknowledgment` | AC-01 |
| T6 | Formulario normal → 303 y `Location` del wizard, `no-store` | ídem | AC-08 |
| T7 | API JSON → 403 `detail` intacto, `no-store` | `test_api_wishlist.py` | AC-09 |
| T8 | Aceptación completa → 303 destino, 1 fila, GET 200 | `TestUatp01RetornoDelAviso` | AC-02 |
| T9 | Aceptación incompleta → `falta=1`, 0 filas, destino conservado | ídem | AC-05 |
| T10 | Destino inválido tampered en el POST → respaldo | ídem | AC-04 |
| T11 | Acceso directo → respaldo | ídem | AC-06 |
| T12 | No reintento: espía del servicio/Orchestrator a cero | ídem | AC-07 |
| T13 | Enlaces de §1 llevan `volver` | test de plantillas/GET de las páginas | AC-10 |
| T14 | `no-store` en 403, 303 (completa/incompleta) y 200 del wizard | ídem | AC-12 |
| T15 | `falta` en el inventario y valores de query no logueados | `test_log_acceso.py` | AC-12 |
| T16 | UAT: Deseados con acuse pendiente → aceptar → Deseados; acceso directo; retorno inválido; sesión nueva y estado persistido | Playwright/manual (`A1/resultado.md`, `replica-a1/A1/resultado.md`) | AC-02/05/06/11; marcar NOT RUN si no se ejecuta |

Comandos mínimos:

```bash
pytest -q tests/test_legal.py tests/test_log_acceso.py tests/test_api_wishlist.py \
  tests/test_web_wishlist.py tests/test_web_wishlist_lote.py tests/test_lector.py \
  tests/test_web_series.py tests/test_web_navegacion.py
ruff check src/ tests/
```

Si el cambio toca más suites (p. ej. `test_web_errores`), añadirlas al comando. La suite completa
se ejecuta con el directorio temporal en el mismo dispositivo que `/` (CLAUDE.md §8). No hace
falta Postgres para T1–T15.

## 7. Evidencia

- **Código:** SHA completo del commit, rama y fecha; enlace al PR. No vale un SHA anterior a la
  última corrección.
- **Pruebas:** salida de los comandos de §6 con PASS/FAIL, y `ruff` limpio. Cada AC con su fila
  PASS/FAIL/NOT RUN; lo no ejecutado se marca **NOT RUN**, no se deduce.
- **Cabeceras:** para AC-01/AC-04/AC-05/AC-12, mostrar los valores exactos observados de
  `HX-Redirect`, `Location` y `Cache-Control` (test o `curl`), incluido un intento con `///` y
  `%2e%2e` que cae al respaldo.
- **No reintento:** la prueba/espía que demuestra cero llamadas a la acción protegida.
- **UAT:** repetir el recorrido desde Deseados con sesión nueva; guardar `A1/resultado.md` y
  `replica-a1/A1/resultado.md` (evidencia que pide #1124), capturas y el estado persistido
  (`accepted: true`, fila de acuse). Enlazar desde #1124 y #1180 y anotar la limitación de D-1
  en la evidencia, sin presentarla como cumplida.
- **Seguridad:** tabla de destinos hostiles probados → respaldo, y confirmación de que ningún
  `Location` sale del servidor. SecOps (task-8) dictamina el SHA final.

## 8. Decisiones pendientes del PO

### D-1 · «Consulta o selección» de Deseados — **bloqueante para cerrar UATP-01 como está escrita**

El criterio literal de #1124/UATP-01 pide «conserva consulta o selección válida». Hoy **no hay
nada que conservar en la URL**: la búsqueda es un `hx-get` sin `hx-push-url`
(`wishlist.html:27`) y la selección son checkboxes del DOM (`_fila_wishlist.html:3`,
`wishlist.html:50`); `web/wishlist.py::index` no lee query. Por tanto:

- **Mínimo acreditable de esta historia:** volver a `/ui/wishlist` (200, «Deseados», la fila
  sigue ahí), sin ejecutar la acción y sin sacar del flujo. La consulta y la selección **no** se
  restauran; la evidencia lo dice expresamente.
- **Decisión necesaria:** elegir una.
  - **A (recomendada):** dar UATP-01 por cerrada en su parte de retorno a la página y abrir una
    historia aparte para que la búsqueda de Deseados sea direccionable (`?q=` leído por la ruta,
    con `hx-push-url`); la **selección no se restaura** (es intención transitoria, no un lugar).
  - **B:** ampliar UATP-01 para incluir `?q=` en `/ui/wishlist` (crece el alcance: ruta,
    plantilla, pruebas, URL).
  - **C:** persistir selección en sesión/BD — **descartada**: contradice la UI sin estado y
    promete algo que la persona no pidió.
- Mientras no se decida, **no** marcar cumplido el punto «consulta o selección» ni cerrar la
  tarjeta como completa.

### D-2 · 303 para formularios normales

El benchmark detectó que hoy reciben JSON 403. La alternativa es dejarlo como está y limitar
UATP-01 a htmx. **Recomendación: aceptar el 303** (solo bajo `/ui/`, solo con `Accept:
text/html`; API intacta): es el caso real de «Buscar una edición mejor» y Mejoras, y sin ello la
historia no cubre «u otro punto». Coste: una rama más en el gate y sus pruebas.

### D-3 · Ficha de serie en la allowlist

Se propone incluir `/ui/series/<uuid>` porque aloja los enlaces directos de seguimiento y
política (`_seguimiento_serie.html:15`, `_politica_serie.html:108`) y el `volver` anidado de
BL-IT03. **Recomendación: sí**; si el PO prefiere no incluirla, esos enlaces vuelven a Biblioteca
al aceptar (peor UX) y debe retirarse también AC-10 para esa página.

### D-4 · Biblioteca: respaldo o destino con filtros

**Recomendación: solo respaldo constante**, sin entrada en la allowlist: hoy no hay control
gateado en Biblioteca y una URL filtrada no se produce. Si el PO quiere «volver a mi Biblioteca
filtrada», se añade la entrada con los 7 parámetros de `web/retorno.py::PARAMETROS_DE_VUELTA` y su
prueba; no cambia la seguridad, solo el alcance.

### D-5 · URLs de resultado POST (`/ui/mejoras/escanear`, `/ui/series/.../mejorar`)

Si el aviso se invalida a mitad de sesión, el `Referer` puede ser una URL que solo existe como
resultado de un POST (sin ruta GET). Hoy caería al respaldo. **Recomendación: no canonicalizarlas
en esta historia**; documentar la limitación y abrir un ajuste si el UAT la encuentra. Añadirlas
exigiría una tabla de mapeo POST→página y más pruebas, sin cambiar el riesgo (el destino seguiría
siendo local).

## 9. Dependencias y orden

- **task-7** implementa esta spec (TDD); **task-8** SecOps (open redirect, `Referer`,
  `HX-Current-URL`, `no-store`, controles); **task-9** UI/UX (copy de `falta`, foco, enlaces);
  **task-10** QA (matriz §5/§6); **task-11** integración y SHA final.
- No hay migración ni dependencia nueva; no se añade JavaScript (htmx + 303 nativos).
- No se toca `LEGAL.md` ni `legal_version`. Si `LEGAL.md` cambia, la aceptación anterior queda
  invalidada (comportamiento existente) y el gate vuelve a pedir el aviso: este contrato es el que
  hace que retomar la tarea siga siendo posible.
- La lista de §3.2 es el punto único de verdad; cualquier página nueva con control gateado o
  enlace directo al aviso debe añadirse **con su prueba** o el destino caerá al respaldo.

## Referencias

- Historias y evidencias: [#1124](https://github.com/juanajok/zascarr/issues/1124),
  [#1141](https://github.com/juanajok/zascarr/issues/1141), [PR #1180](https://github.com/juanajok/zascarr/pull/1180).
- Procedimiento de benchmark: [`docs/design/benchmark-referencias.md`](benchmark-referencias.md).
  Hallazgos de UATP-01 en el informe de task-6 (2026-11-20): GitLab es la referencia más cercana
  (`Users::TermsController#redirect_path`, con `safe_redirect_path`/`InternalRedirect`, lista de
  rutas internas); Sonarr/Radarr llevan `returnUrl` y limitaron las redirecciones a rutas locales;
  Kapowarr, Mylar3 y Komga se usan como anti-patrón (destino fijo o sin validación estricta).
- [GitLab · `users/terms_controller.rb`](https://gitlab.com/gitlab-org/gitlab/-/blob/master/app/controllers/users/terms_controller.rb),
  [Sonarr · «Limit redirects after login to local paths»](https://github.com/Sonarr/Sonarr/commit/a524e0a954864650ca01f6de493d2c6adb2b383d),
  [Radarr · `login.html`](https://github.com/Radarr/Radarr/blob/develop/frontend/src/login.html),
  [Radarr · `AuthenticationController.cs`](https://github.com/Radarr/Radarr/blob/develop/src/Radarr.Http/Authentication/AuthenticationController.cs).
- Contrato de retorno ya existente (no se modifica): `src/zascarr/web/retorno.py` (BL-IT03, #286).
