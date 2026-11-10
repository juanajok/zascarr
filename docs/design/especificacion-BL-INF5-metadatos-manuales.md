# Especificación — BL-INF5: editar metadatos a mano (serie y número)

> Historia [#591](https://github.com/juanajok/zascarr/issues/591), continuación de BL-INF (#446).
> **Benchmark:** [`benchmark-BL-INF5-metadatos-manuales.md`](benchmark-BL-INF5-metadatos-manuales.md).
> **Fecha:** 2026-11-10. **Base:** `origin/main` = `d26d815`. **Sin migración, sin JS nuevo y sin
> escribir en la biblioteca.** Solo se escribe en `series`, `issues` y `publishers` de PostgreSQL.
>
> Las decisiones de producto (campos, procedencia por campo, colisión llana, formularios propios,
> fuera de alcance) vienen **aceptadas por el PO** en la tarjeta. Las decisiones de detalle que esta
> especificación añade para que el contrato sea cerrado están marcadas como **[detalle]** y el PO
> puede revertirlas sin reabrir la historia.

---

## 1. Problema local y resultado deseado

El coleccionista tiene series y números cuyos datos no coinciden con la realidad: título original en
vez del español, año o editorial de otra edición, sinopsis ausente, total de números equivocado, un
tomo numerado como «#1» cuando en su serie es el «#12». Hoy **no hay ninguna pantalla para
corregirlo**; las únicas escrituras de metadatos son el alta, el `ComicInfo.xml` (#448) y el
enriquecido de fuentes. Si la fuente no tiene el dato o lo tiene mal, la ficha miente.

**Resultado deseado:** dos formularios propios (ficha de serie y ficha de número), en español llano,
sin JavaScript nuevo, que escriban **solo** en la base de datos; que dejen cada campo tocado como
**manual, fechado y protegido**; que no cambien `metadata_source` de toda la serie; que expliquen la
colisión de número en llano; que recalculen orden y huecos; y que repitan junto al botón la garantía
«Solo cambia lo que ves en ZascArr; tus archivos no se tocan».

---

## 2. Alcance

### 2.1 Dentro

- **Serie:** título, año de inicio, año de fin, editorial, sinopsis y total de números.
- **Número:** número, título, fecha de portada, formato y sinopsis.
- **Procedencia por campo:** `metadata_["manual"][campo]` con fecha UTC; candado por defecto en
  `locked_fields`; tabla «De dónde sale cada dato» con **Manual + fecha** y acción para devolver el
  control a la fuente (y volver a protegerlo) **[detalle]**.
- **Colisión `(serie, número, volumen)`** explicada antes de guardar; `UNIQUE` como última defensa.
- **`sort_order`** recalculado al cambiar el número; huecos y «te faltan» recalculados al volver a la
  ficha.
- Formularios HTML nativos (POST + 303), sin `hx-*`, con aviso verde al volver.

### 2.2 Fuera (decidido por el PO y por el estado del código)

- Crear números que faltan, crear series desde cero o editar la lista de números (alta aparte).
- Escribir `ComicInfo.xml` en el archivo o cualquier escritura en disco (#480/B6).
- Autores/créditos, géneros, etiquetas, portada, IDs externos, `volume`, tradición, estado, política
  de búsqueda.
- Edición en lote, historial de cambios, deshacer un guardado, papelera de valores anteriores.
- Renombrar carpetas o archivos al cambiar el título (la garantía lo dice explícitamente).
- API pública nueva, tareas de fondo, colas, dependencias nuevas, migración de esquema.

---

## 3. Contrato de datos

### 3.1 Campos de serie editables

`publisher_id` es la columna real; el formulario y la ficha hablan de **«Editorial»**. El campo del
formulario se llama `publisher` (nombre escrito); la clave de procedencia, de candado y de las
acciones es `publisher_id`.

| Clave de contrato (`metadata_`/`locked_fields`) | Etiqueta en pantalla | Columna | Tipo | Obligatorio | Límite / validación |
|---|---|---|---|---|---|
| `title` | Título | `series.title` | texto | **sí** | recortado; 1–500 caracteres |
| `start_year` | Año de inicio | `series.start_year` | entero o vacío | no | 1800–2100 |
| `end_year` | Año de fin | `series.end_year` | entero o vacío | no | 1800–2100; ≥ `start_year` si ambos constan |
| `publisher_id` | Editorial | `series.publisher_id` | texto en el formulario; FK al guardar | no | recortado; 1–255; se resuelve/crea `Publisher` (3.3) |
| `description` | Sinopsis | `series.description` | texto o vacío | no | ≤ 20.000 caracteres |
| `total_issues` | Números en total | `series.total_issues` | entero o vacío | no | 0–99.999 |

### 3.2 Campos de número editables

| Clave de contrato | Etiqueta en pantalla | Columna | Tipo | Obligatorio | Límite / validación |
|---|---|---|---|---|---|
| `issue_number` | Número | `issue.issue_number` | texto o vacío | no | recortado; 0–20; vacío = «sin número» |
| `title` | Título | `issue.title` | texto o vacío | no | recortado; ≤ 500 |
| `release_date` | Fecha de portada | `issue.release_date` | fecha o vacío | no | `AAAA-MM-DD` real; 1800-01-01–2100-12-31 |
| `format` | Formato | `issue.format` | selector | **sí** | un valor de `IssueFormat`; etiquetas de `FORMATOS_LEGIBLES` |
| `synopsis` | Sinopsis | `issue.synopsis` | texto o vacío | no | ≤ 20.000 caracteres |

`volume` **no se edita** en esta historia; se conserva el valor actual de la fila y se usa en la
comprobación de colisión. Los formularios llevan únicamente estos campos (más las acciones), con
`Form(...)` explícitos: **prohibido `Model(**data)` o `setattr` sobre el cuerpo**.

**[detalle] Sinopsis:** 20.000 caracteres es un tope de cordura, no una regla de negocio; `Text` en
PostgreSQL no impone longitud. No se trunca nunca: si se supera, se rechaza y se conserva lo escrito.
El tope de 4.000 de `services/comicinfo.py::MAX_SINOPSIS` aplica al texto que llega del archivo, no
a lo que escribe la persona.

**[detalle] Total de números:** 0 se guarda como 0 y la ficha lo trata como «sin total conocido»
(`services/series.py::razon_de_no_calculable` usa `if not series.total_issues`). El tope 99.999 es
el mismo orden de magnitud que el resto de topes de UI y evita un número absurdo.

### 3.3 Editorial: resolución y creación

Al guardar un nombre de editorial no vacío:

1. Se recorta y se colapsan espacios; si queda vacío, `publisher_id = NULL`.
2. Se busca un `Publisher` existente con `lower(name) = lower(nombre)` (mismo criterio que
   `services/comicinfo.py::_aplicar_editorial:146-158`).
3. Se serializa el alta con un candado consultivo de transacción sobre el nombre normalizado
   (`pg_advisory_xact_lock`, mismo patrón que `services/alta_serie.py::bloquear_titulo`) para que
   dos peticiones no creen dos editoriales que solo difieren en mayúsculas. Si no existe, se crea
   `Publisher(name=nombre, metadata_source="manual")` dentro de un savepoint; si aun así otra
   petición la creó, se vuelve a buscar y se usa la existente (el `UNIQUE` de `publishers.name` es
   la red).
4. No se renombra ni se modifica un `Publisher` existente; solo se enlaza desde la serie.

**[detalle] Crear editorial:** el PO aceptó «editorial» como campo de la serie; crear la entidad
normalizada cuando no existe es la forma de que el nombre escrito se vea en la ficha y sea
reutilizable por otras series, sin pedir a la persona que «cree una editorial» en otra pantalla.

### 3.4 Procedencia por campo: `metadata_["manual"]`

Estructura añadida al JSONB existente (no se toca ninguna otra clave):

```json
{
  "alta": {"version": 1, "fuente": "comic_vine", "origen": "descubrir", "fecha": "2026-10-01T10:00:00+00:00"},
  "manual": {
    "title":        {"fecha": "2026-11-10T18:30:12+00:00"},
    "publisher_id": {"fecha": "2026-11-10T18:30:12+00:00"},
    "total_issues": {"fecha": "2026-11-10T18:30:12+00:00"}
  },
  "comicinfo_aplicado": {"mtime_ns": 123, "size": 456, "aplicado": {"synopsis": "..."}}
}
```

Reglas del contrato:

- **P-1.** Una entrada por **campo gestionado** con `{"fecha": "<ISO-8601 UTC>"}`. La fecha la pone
  el servidor con `datetime.now(UTC)`; no se acepta del formulario.
- **P-2.** No se guarda una copia del valor ni el valor anterior: el valor vive en su columna. El
  JSONB solo dice *qué campos ha tocado la persona y cuándo*.
- **P-3.** **Solo se crea/actualiza la entrada si el valor enviado difiere del actual.** Abrir el
  formulario y guardar sin cambios no marca nada.
- **P-4.** Al volver a cambiar un campo ya manual, se **refresca la fecha** de esa entrada.
- **P-5.** Desbloquear **no borra** la entrada manual: sigue constando que lo escribió la persona;
  el candado es independiente (`locked_fields`). Borrar la marca solo ocurriría con una acción
  explícita de «olvidar que es manual», que **no** entra en esta historia.
- **P-6.** El JSONB se reasigna a un diccionario **nuevo** (`series.metadata_ = {**actual, "manual":
  ...}`); mutar el diccionario en sitio no lo detecta SQLAlchemy. Igual con `locked_fields`: se
  asigna una lista nueva.
- **P-7.** Se toleran claves desconocidas del JSONB: los datos previos de `alta`,
  `comicinfo_aplicado`, `asociaciones`, etc. se conservan tal cual. Tamaño acotado: el conjunto de
  claves nuevas es el de 3.1/3.2 (11 como máximo).
- **P-8.** `metadata_source` de la serie y del número **no cambia** al guardar.

### 3.5 Candados (`locked_fields`)

- **C-1.** Al crear/refrescar una entrada manual, la clave del campo se **añade** a
  `locked_fields` si no estaba.
- **C-2.** Un campo no cambiado conserva su candado actual (si ya estaba protegido, sigue; si no,
  sigue sin estarlo). No se bloquean campos por el mero hecho de aparecer en el formulario.
- **C-3.** Las claves de `locked_fields` que ya usa el resto de la app (`series_id`,
  `comic_vine_id`, `cover_url`, etc.) **no se tocan**.
- **C-4.** «Devolver a la fuente» = **quitar** la clave de `locked_fields`, sin tocar el valor ni la
  entrada `manual`. El campo queda protegido por la procedencia (la ficha dirá «Manual · fecha») pero
  el enriquecido vuelve a poder proponer/cambiar.
- **C-5.** «Proteger» **[detalle]** = volver a añadir la clave a `locked_fields`, solo si existe
  entrada manual en ese campo. Es la operación inversa de C-4, necesaria para que el desbloqueo no
  sea irreversible; si el PO no la quiere, C-4 sigue cumpliendo AC-2 y esta acción se retira.
- **C-6.** Las acciones de candado solo aceptan la lista blanca de 3.1/3.2; cualquier otra clave
  responde `404` sin escribir. «Proteger» sobre un campo gestionado sin entrada manual también
  responde `404` (la UI no ofrece el botón en ese caso; un enlace fabricado no debe inventar una
  manualidad).

### 3.6 Procedencia que se muestra (resolución honesta)

Para cada campo gestionado, en este orden:

1. Si existe `metadata_["manual"][campo]` → origen **«Manual»** y su fecha (dd/mm/aaaa);
   `bloqueado` según `locked_fields`.
2. Si no, se aplica la lógica actual de `services/procedencia.py` (alta/enriquecido) con la misma
   semántica; si no consta, «Origen no registrado». **Nunca** se atribuye a una fuente un valor que
   tiene entrada manual.
3. Editorial y año de fin dejan de estar fijos en la plantilla y pasan a resolverse por esta regla
   (hoy `series_detail.html:92-93` los pinta siempre como «Origen no registrado»).
4. Desbloqueado con entrada manual se muestra «Manual · fecha · sin proteger: las fuentes pueden
   cambiarlo» y la acción «Proteger»; bloqueado, «Manual · fecha» + chip «Protegido» y acción
   «Devolver a la fuente».

### 3.7 `sort_order`

- **O-1.** Si `issue_number` cambia y el texto recortado encaja en `^[-+]?\d+(?:[.,]\d+)?$`, se
  escribe `issue.sort_order = float(texto.replace(",", "."))` (p. ej. `"2"` → `2.0`, `"2,5"` →
  `2.5`, `"03"` → `3.0`).
- **O-2.** Si el nuevo número **no** es numérico (`"Annual 1"`, vacío, texto), `sort_order = NULL`.
  El orden de lectura y de ficha ya cae a `natural_key(issue_number)` (`services/ficha_numero.py`,
  `services/archivos_por_numero.py`), así que no se inventa una posición.
- **O-3.** Si el número **no cambia**, `sort_order` no se toca (aunque el número edite otra cosa).
  Así esta historia no reescribe el estado histórico de `sort_order` de toda la biblioteca.
- **O-4.** No se recalculan `sort_order` de otros números de la serie.

### 3.8 Huecos y «te faltan»

- **H-1.** No hay escritura extra: al guardar número/formato/`total_issues`, la próxima carga de la
  ficha recalcula `numeros_poseidos` y `faltantes` con las reglas vigentes (solo una grapa
  `SINGLE_ISSUE` con número entero tapa el hueco de esa grapa).
- **H-2.** **Límite conocido y aceptado:** `razon_de_no_calculable` solo acredita la unidad de
  Comic Vine (`UNIDAD_DE_GRAPA = {comic_vine}`). Editar `total_issues` **no** cambia esa regla: en
  una serie de AniList/Tebeosfera/GCD la ficha seguirá diciendo que no se puede comparar. Se decide
  **no** tocar la regla C6 en esta historia (cambiaría el significado de «faltan» para mangas/tomos).
  Si el PO quiere que un total manual acredite la unidad, es una historia aparte.
- **H-3.** Cambiar el formato de un número a no-grapa lo saca de `numeros_poseidos` (el hueco
  reaparece); cambiar a `SINGLE_ISSUE` con número entero lo mete. Es comportamiento existente, no
  se duplica lógica.

### 3.9 Colisión `(serie, número, volumen)`

- **K-1.** Antes de escribir, si `issue_number` no está vacío, se buscan otras filas de **la misma
  serie** con el mismo `volume` y un número equivalente. Equivalencia: texto recortado igual, o
  ambos numéricos con el mismo valor (`"3"` y `"03"` colisionan).
- **K-2.** Si hay colisión: **no se escribe nada** (ni campos ni procedencia), se vuelve al
  formulario con los valores escritos y el mensaje llano:
  «Ya existe el nº {número} en esta serie. No se ha guardado nada: cambia el número o corrige el
  otro.»
- **K-3.** Si la fila en conflicto tiene un `volume` distinto, no es colisión (la clave es la del
  `UNIQUE`); no se enseña el volumen en el mensaje salvo que sea > 1, en cuyo caso se añade
  «(edición {volumen})» **[detalle]**.
- **K-4.** El `UNIQUE (series_id, issue_number, volume)` sigue siendo la última defensa. Si aun así
  salta un `IntegrityError` por carrera, se traduce al mismo mensaje K-2 y no se devuelve 500. Los
  cambios se hacen dentro de un savepoint para que el error no deje la sesión inservible.
- **K-5.** Vaciar el número no colisiona (varias filas «sin número» son válidas; el `UNIQUE` de
  PostgreSQL no compara `NULL`).

### 3.10 Validación de lo que no cambia

- **V-1.** Los límites y la coherencia se comprueban sobre los valores **enviados**; pero un valor
  que ya estaba guardado y llega **igual** no se rechaza aunque supere un tope nuevo de esta
  historia (p. ej. una sinopsis antigua de 25.000 caracteres). Se muestra y se conserva tal cual;
  el tope solo impide **empeorarlo**.
- **V-2.** Igual con la coherencia de años: si `start_year` y `end_year` no cambian, no se rechaza
  un guardado por una incoherencia preexistente; si alguno cambia, se valida el par.
- **V-3.** El título de la serie y el formato del número se validan siempre (el título es
  obligatorio y el formato no puede quedar nulo).

---

## 4. Contrato HTTP y flujo de UI

### 4.1 Rutas

Todas cuelgan del router de series (`/ui/series/{series_id}`), detrás de la autenticación existente
(`AuthMiddleware`); no se añade permiso nuevo. `Cache-Control: no-store` en todas.

| Método | Ruta | Qué hace | Éxito | Error |
|---|---|---|---|---|
| `GET` | `/ui/series/{series_id}/editar` | formulario de serie | 200 HTML | 404 si no existe |
| `POST` | `/ui/series/{series_id}/editar` | guarda la serie | 303 a `/ui/series/{id}?guardado=serie` | 200 con el formulario y errores |
| `GET` | `/ui/series/{series_id}/numero/{issue_id}/editar` | formulario de número | 200 HTML | 404 si el número no es de esa serie |
| `POST` | `/ui/series/{series_id}/numero/{issue_id}/editar` | guarda el número | 303 a `/ui/series/{id}/numero/{iid}?guardado=numero` | 200 con el formulario y errores |
| `POST` | `/ui/series/{series_id}/campo/{campo}/devolver` | desbloquea un campo de serie | 303 a `/ui/series/{id}?guardado=campo` | 404 si el campo no es gestionado |
| `POST` | `/ui/series/{series_id}/campo/{campo}/proteger` | vuelve a bloquear | 303 a `/ui/series/{id}?guardado=campo` | 404 si el campo no es gestionado o no hay entrada manual |
| `POST` | `/ui/series/{series_id}/numero/{issue_id}/campo/{campo}/devolver` | desbloquea un campo del número | 303 a la ficha del número | 404 |
| `POST` | `/ui/series/{series_id}/numero/{issue_id}/campo/{campo}/proteger` | vuelve a bloquear | 303 a la ficha del número | 404 |

- El `volver` seguro de la ficha se reutiliza (`web/routes.py`/`volver_segura`), sin aceptar una URL
  arbitraria.
- El aviso de éxito se deriva **solo** de un parámetro fijo de la lista blanca (`serie`, `numero`,
  `campo`); no se refleja texto del usuario en el HTML.
- **No se usan `hx-*` en estos formularios.** Motivo: htmx 4 intercambia cuerpos 4xx/5xx (recogido en
  `docs/design/ui-migracion.md` §2.5); un error de validación se convertiría en un fragmento pegado
  sobre la ficha. Navegación nativa: POST → 303 (o 200 con el formulario) y el navegador pinta la
  página entera.
- La garantía no se guarda en sesión ni en token: es texto fijo de plantilla.

### 4.2 Formulario de serie («Editar la ficha»)

- Se llega desde un botón **secundario** al final de la cabecera de la ficha:
  `<a class="btn ghost" href="/ui/series/{id}/editar">Editar la ficha</a>`.
- Título de pantalla: «Editar la ficha» (rótulo `h1` en Anton, ≤ 3 palabras).
- Frase de entrada (≤ 20 palabras): «Corrige lo que no cuadre. Solo se guarda en ZascArr; tus
  archivos no se tocan.»
- Campos en el orden de 3.1, cada uno con `<label for>`, ayuda de una línea y `aria-describedby`
  cuando hay error. Años y total con `inputmode="numeric"`; sinopsis con `<textarea rows>`.
- Botón principal **único**: «Guardar» (`.primary`). Al lado, enlace «Cancelar» que vuelve a la
  ficha sin escribir.
- **Garantía junto al botón** (no en la cabecera): «Solo cambia lo que ves en ZascArr; tus archivos
  no se tocan. Cambiar el título no renombra carpetas ni archivos.»
- Presupuesto U21: antes de la primera acción solo la frase de entrada y los campos; la explicación
  de procedencia va en `<details>` («¿Qué pasa con lo que no cambie?»), no en el cuerpo.

### 4.3 Formulario de número («Editar el número»)

- Se llega desde un botón secundario en la cabecera de la ficha del número.
- Título: «Editar el número».
- Frase de entrada: «Corrige lo que no cuadre. Solo se guarda en ZascArr; el archivo no se toca.»
- Campos en el orden de 3.2. El formato es un `<select>` con las etiquetas de `FORMATOS_LEGIBLES`
  (grapa, tomo en rústica, …); la fecha es `<input type="date">` (el navegador no manda nada si está
  vacía).
- Un único «Guardar» + «Cancelar»; misma garantía junto al botón.

### 4.4 Errores de validación

- Se responde **200** con la misma plantilla del formulario, los valores tal como se enviaron
  (incluido el erróneo) y un resumen al principio `role="alert"` con enlaces a los campos; cada campo
  erróneo lleva su mensaje debajo.
- **Nunca** un 422 de FastAPI ni JSON en superficie; nunca se pierde lo escrito.
- Si el error es de colisión, se conserva el número escrito y el resto de campos; no se aplica
  ningún cambio (la transacción no escribe nada).
- Si el error es inesperado (fallo de BD), mensaje «No se ha podido guardar. No se ha cambiado nada:
  vuelve a intentarlo.» y log técnico; no se muestra el detalle.

### 4.5 Mensajes (texto exacto)

| Código | Cuándo | Texto |
|---|---|---|
| `titulo_vacio` | título de serie vacío | «Escribe un título para la serie.» |
| `titulo_largo` | > 500 | «El título es demasiado largo (máximo 500 caracteres).» |
| `anio_invalido` | año no entero 1800–2100 | «El año tiene que ser un número entre 1800 y 2100.» |
| `anio_fin_menor` | fin < inicio | «El año de fin no puede ser anterior al año de inicio.» |
| `total_invalido` | total no entero ≥ 0 | «El total de números tiene que ser un número entero de 0 o más.» |
| `total_grande` | > 99.999 | «Ese total es demasiado grande (máximo 99.999).» |
| `editorial_larga` | > 255 | «El nombre de la editorial es demasiado largo (máximo 255 caracteres).» |
| `sinopsis_larga` | > 20.000 | «La sinopsis es demasiado larga (máximo 20.000 caracteres).» |
| `numero_largo` | > 20 | «El número es demasiado largo (máximo 20 caracteres).» |
| `fecha_invalida` | no es fecha real | «La fecha no es válida. Usa el calendario del campo.» |
| `fecha_rango` | fuera de 1800–2100 | «La fecha tiene que estar entre 1800 y 2100.» |
| `formato_invalido` | no es `IssueFormat` | «Elige un formato de la lista.» |
| `colision` | K-2/K-4 | «Ya existe el nº {número} en esta serie. No se ha guardado nada: cambia el número o corrige el otro.» |
| `error_al_guardar` | fallo inesperado | «No se ha podido guardar. No se ha cambiado nada: vuelve a intentarlo.» |

**Avisos de éxito** (verde, `ui.aviso("ok", …)`, junto a la cabecera de la ficha al volver):

- Serie: «Guardado: la ficha de «{título}» ya dice lo que has escrito. Tus archivos siguen
  intactos.»
- Número: «Guardado: el nº {número} ya dice lo que has escrito. Tus archivos siguen intactos.»
- Desbloqueo: «Hecho: «{campo}» ya no está protegido. El valor se queda como está; las fuentes
  podrán actualizarlo.»
- Re-protección: «Hecho: «{campo}» vuelve a estar protegido.»

### 4.6 Ficha de serie: qué cambia

- Botón secundario «Editar la ficha» en la cabecera (junto a los ya existentes).
- «De dónde sale cada dato»:
  - Fila por campo de 3.1 (incluidas **Editorial** y **Año de fin**, ya no fijas). Se mantienen
    **Portada** e **Identificador de la fuente** como hoy (no son editables en esta historia), con
    su resolución actual.
  - Si hay entrada manual: chip «Manual», fecha «10/11/2026» y, según candado, «Protegido» +
    botón pequeño «Devolver a la fuente» o «Sin proteger» + botón «Proteger».
  - Los botones son `<form method="post" action="…/campo/{campo}/devolver">` con un solo submit,
    sin `hx-confirm` (la acción no destruye datos: conserva valor y procedencia).
  - La leyenda existente de «Manual»/«Protegido» se mantiene y se amplía una línea para explicar
    «Devolver a la fuente».
- La fila de **Editorial** deja de pintar «Origen no registrado» fijo cuando hay manualidad; el
  resto del comportamiento no cambia.
- Si la serie es «vacía» (`serie_vacia`), el bloque de procedencia sigue como hoy (se oculta), pero
  el botón «Editar la ficha» **sí** se pinta: es la forma de rellenarla.

### 4.7 Ficha de número: qué cambia

- Botón secundario «Editar el número» en la cabecera, **siempre visible**, aunque el número no tenga
  datos todavía (es la forma de rellenarlo).
- Tabla «De dónde sale cada dato» del número (`ficha_numero.procedencia`), hoy un diccionario
  etiqueta→valor/origen, pasa a:
  - Filas de **Número, Título, Fecha, Formato, Sinopsis** con la misma resolución honesta de 3.6.
  - Origen = fuente actual del número cuando no es manual; nunca «Manual» por descarte.
  - Chip «Manual» + fecha y acciones de candado iguales que en la serie.
  - Páginas y Autores se mantienen como hoy (no son editables en esta historia).
- El aviso verde de éxito aparece al volver con `?guardado=numero`.

### 4.8 Accesibilidad y estilo

- Todo en español llano, texto ≥ 14 px (`.875rem`) y contraste de las clases existentes; no se
  añade CSS nuevo salvo el mínimo reutilizando `.ficha-serie-meta`, `.procedencia-*`, `.btn`,
  `.primary`, `.caption`, `.aviso`. Si hiciera falta una clase nueva, se declara en
  `test_web_css_contraste` y cumple §6.
- Formularios nativos: `<label for>`, `required` solo donde el contrato lo exige, `aria-describedby`
  para errores, resumen `role="alert"`; si se usa `autofocus`, va en el resumen de errores y nunca
  se mueve el foco con JS.
- Sin `hx-confirm`, sin diálogos nativos (`window.confirm`), sin `<script>` nuevo.
- Teclado: tabulación por todos los campos, «Cancelar» como enlace, «Guardar» como submit; un solo
  botón principal por pantalla.

---

## 5. Requisitos EARS

Convención: **Cuando** [evento] el sistema **debe** [respuesta]; **Si** [condición] **entonces**
[respuesta]; **Mientras** [estado] el sistema **debe** [respuesta]. «El sistema» = ZascArr.

### 5.1 Datos y validación

- **REQ-D1.** Cuando la persona envía el formulario de serie, el sistema debe escribir solo las seis
  claves de 3.1 desde `Form(...)` explícitos y rechazar el resto sin mirarlo.
- **REQ-D2.** Cuando la persona envía el formulario de número, el sistema debe escribir solo las
  cinco claves de 3.2 desde `Form(...)` explícitos y rechazar el resto sin mirarlo.
- **REQ-D3.** Cuando un campo opcional llega vacío, el sistema debe guardar `NULL` (o `""`→`NULL`
  según la columna) sin inventar un valor.
- **REQ-D4.** Si el título de la serie está vacío o supera 500 caracteres, entonces el sistema debe
  rechazar el guardado y conservar todo lo escrito.
- **REQ-D5.** Si un año no es entero o está fuera de 1800–2100, o el año de fin es anterior al de
  inicio, entonces el sistema debe rechazar el guardado con el mensaje de 4.5.
- **REQ-D6.** Si `total_issues` no es entero ≥ 0, entonces el sistema debe rechazar el guardado.
- **REQ-D7.** Si la editorial supera 255 caracteres, entonces el sistema debe rechazar el guardado.
- **REQ-D8.** Si la sinopsis supera 20.000 caracteres, entonces el sistema debe rechazar el guardado.
- **REQ-D9.** Si el número supera 20 caracteres, entonces el sistema debe rechazar el guardado.
- **REQ-D10.** Si la fecha no es real o está fuera de 1800–2100, entonces el sistema debe rechazar el
  guardado y conservar el resto de valores.
- **REQ-D11.** Si el formato no es un `IssueFormat` válido, entonces el sistema debe rechazar el
  guardado con «Elige un formato de la lista».
- **REQ-D12.** Cuando la editorial no está vacía, el sistema debe resolverla o crearla según 3.3 y
  enlazarla; cuando está vacía, debe dejar `publisher_id = NULL` sin borrar la editorial del catálogo.
- **REQ-D13.** Cuando un valor guardado llega igual al formulario, el sistema no debe rechazarlo por
  superar un tope nuevo o por una incoherencia preexistente (3.10); solo valida lo que cambia.

### 5.2 Procedencia y candados

- **REQ-P1.** Cuando un campo cambia y se guarda, el sistema debe escribir
  `metadata_["manual"][campo] = {"fecha": <UTC ISO-8601>}` y añadir `campo` a `locked_fields`.
- **REQ-P2.** Cuando un campo no cambia, el sistema no debe crear ni refrescar su entrada manual ni
  alterar su candado.
- **REQ-P3.** El sistema no debe modificar `metadata_source` de la serie ni del número al guardar.
- **REQ-P4.** El sistema debe conservar todas las claves de `metadata_` ajenas a `manual`,
  `metadata_["alta"]` y `metadata_["comicinfo_aplicado"]`, y no tocar las claves de `locked_fields`
  que no gestiona.
- **REQ-P5.** El sistema debe reasignar el dict de `metadata_` y la lista de `locked_fields` (no
  mutarlos en sitio) para que el cambio se persista.
- **REQ-P6.** Cuando la persona pulsa «Devolver a la fuente», el sistema debe quitar el campo de
  `locked_fields`, mantener el valor y mantener la entrada manual con su fecha.
- **REQ-P7.** Cuando la persona pulsa «Proteger» sobre un campo manual, el sistema debe añadir el
  campo a `locked_fields` sin cambiar el valor.
- **REQ-P8.** Si el campo de la acción de candado no pertenece a la lista blanca de 3.1/3.2, entonces
  el sistema debe responder 404 y no escribir nada.
- **REQ-P9.** Cuando se muestra «De dónde sale cada dato», el sistema debe poner «Manual» y la fecha
  si hay entrada manual, y no debe atribuir ese valor a una fuente.
- **REQ-P10.** Mientras un campo manual esté desbloqueado, la ficha debe decir que las fuentes pueden
  cambiarlo y ofrecer «Proteger»; mientras esté bloqueado, debe decir «Protegido» y ofrecer
  «Devolver a la fuente».

### 5.3 Colisión, orden y huecos

- **REQ-H1.** Cuando se guarda un número no vacío, el sistema debe comprobar la colisión de 3.9
  antes de escribir y, si existe, no debe escribir nada.
- **REQ-H2.** Si el `UNIQUE` salta por una carrera, entonces el sistema debe devolver el mismo
  mensaje llano de colisión, no un 500.
- **REQ-H3.** Cuando el número cambia a un texto numérico, el sistema debe escribir
  `sort_order` como `float` (3.7); cuando cambia a no numérico o vacío, debe escribir `NULL`; cuando
  el número no cambia, no debe tocar `sort_order`.
- **REQ-H4.** Cuando se guarda un cambio de número, formato o total, el sistema debe dejar que la
  siguiente carga de la ficha recalcule huecos y «te faltan» sin escrituras adicionales.
- **REQ-H5.** El sistema no debe cambiar la regla de unidad de `razon_de_no_calculable` (H-2 de
  3.8); un total manual no acredita la unidad de la fuente.

### 5.4 HTTP y UI

- **REQ-U1.** Cuando se pide el formulario de serie o de número, el sistema debe responder 200 con
  los valores actuales precargados; si el número no pertenece a la serie, 404.
- **REQ-U2.** Cuando el guardado es correcto, el sistema debe responder 303 a la ficha
  correspondiente con el parámetro fijo de éxito; el navegador no debe reenviar el POST al recargar.
- **REQ-U3.** Cuando el guardado falla por validación o colisión, el sistema debe responder 200 con
  el formulario, los valores escritos y el resumen de errores; no debe responder 422 ni JSON.
- **REQ-U4.** El sistema no debe usar `hx-*`, `<script>` nuevo, diálogos nativos ni `hx-confirm` en
  estos formularios.
- **REQ-U5.** El sistema debe ofrecer «Editar la ficha» y «Editar el número» como botones
  secundarios en las fichas correspondientes.
- **REQ-U6.** El sistema debe pintar la garantía de 4.2/4.3 junto al botón Guardar y en el aviso de
  éxito, y no en la cabecera de pantallas sin efecto.
- **REQ-U7.** El sistema debe responder con `Cache-Control: no-store` en formularios, POST y fichas
  con aviso de guardado.
- **REQ-U8.** El sistema debe mantener el presupuesto de texto de §6 de CLAUDE.md: una frase de
  entrada de ≤ 20 palabras, ≤ 50 palabras antes de la primera acción, sin jerga interna en
  superficie.

### 5.5 Archivos, seguridad y rendimiento

- **REQ-S1.** El sistema no debe abrir, leer, escribir, mover ni renombrar ningún archivo de la
  biblioteca al guardar metadatos; no debe crear ni modificar filas de `files`.
- **REQ-S2.** El sistema no debe consultar ninguna fuente externa ni hacer red al guardar.
- **REQ-S3.** El sistema no debe usar `Model(**data)`, `setattr` sobre el cuerpo crudo ni SQL
  concatenado; el guardado va por campos explícitos y parámetros.
- **REQ-S4.** El sistema debe comprobar que el número pertenece a la serie de la URL antes de
  escribir (404 si no) y no debe permitir editar una serie/número por ID de otra.
- **REQ-S5.** El sistema no debe añadir dependencias ni migraciones de Alembic.
- **REQ-S6.** El guardado debe resolverse en una transacción corta con un número acotado de
  consultas (objetivo ≤ 5: cargar entidad, colisión, editorial, escritura), sin tareas de fondo ni
  N+1.
- **REQ-S7.** Los logs no deben incluir el texto de la sinopsis ni el nombre completo de la
  editorial; como mucho la serie, el número y los campos cambiados.
- **REQ-S8.** El sistema no debe modificar `title_norm` a mano (columna generada por Postgres) ni
  escribir en `files`/`import_runs`.

---

## 6. Criterios de aceptación

| AC | Enunciado | Requisitos |
|---|---|---|
| **AC-1** | Guardar un campo lo deja manual con fecha y bloqueado; la tabla de procedencia lo refleja. | REQ-P1, P9, U3 |
| **AC-2** | Desbloquear un campo devuelve el control al enriquecido **sin borrar el valor**; se puede volver a proteger. | REQ-P6, P7, P10 |
| **AC-3** | Las validaciones y la colisión dan un aviso claro, sin 422 crudo, sin perder lo escrito y sin escribir nada. | REQ-D4..D11, H1, H2, U3 |
| **AC-4** | No se toca ningún archivo; no hay migración; pruebas PG (procedencia, bloqueo, colisión) y web (FakeSession). | REQ-S1, S5; §7 |
| **AC-5** | Existen el benchmark §13 y esta especificación, enlazados desde la PR. | este documento + benchmark |
| **AC-6** | Al cambiar el número se recalcula `sort_order` y los huecos/«faltan» de la ficha. | REQ-H1, H3, H4 |
| **AC-7** | Al volver a la ficha se ve un aviso verde de guardado y la garantía de que los archivos no se tocaron. | REQ-U2, U6, U7 |
| **AC-8** | Están los 6 campos de serie y los 5 de número, con sus límites y mensajes. | §3.1, §3.2, REQ-D1..D11 |
| **AC-9** | `metadata_source` de la serie y del número no cambia al editar. | REQ-P3 |
| **AC-10** | La procedencia nunca atribuye a una fuente un valor manual; incluye Editorial y Año de fin y la fecha manual. | REQ-P9, P10, §3.6 |
| **AC-11** | Sin JS nuevo, sin htmx en los formularios y sin diálogos nativos; errores por navegación normal. | REQ-U4, U8 |
| **AC-12** | El enriquecido y el `ComicInfo.xml` (#448) siguen respetando el candado; no hay regresión en sus tests. | REQ-P1, S1; §7.4 |

---

## 7. Plan de pruebas

Entorno: PG real con `TEST_DATABASE_URL` (nombre de BD con «test», migrada a `head` por
`tests/conftest.py`) y web con `app.dependency_overrides[get_db]` + `FakeSession` queue-driven.
Sin dependencias nuevas. Los dos ficheros nuevos se marcan `skipif` si falta `TEST_DATABASE_URL` en
el caso PG, como `tests/test_huecos_pg.py`.

Comandos de referencia (no ejecutados en esta tarea):

```bash
# PG: base de pruebas cuyo nombre lleve «test»
TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/zascarr_test \
  pytest tests/test_metadatos_manuales_pg.py tests/test_metadatos_manuales_web.py
# La suite completa, con el temporal en el mismo dispositivo que / (CLAUDE.md §8)
pytest --basetemp=/var/tmp/zascarr-tests
```

### 7.1 Servicio puro / unitario (sin BD o con objetos)

- `test_sort_order_de_numero`: `"2"`→2.0, `"2.5"`→2.5, `"2,5"`→2.5, `"03"`→3.0, `"-1"`→-1.0,
  `"Annual 1"`→NULL, `""`→NULL.
- `test_equivalencia_de_numero`: `"3"`≡`"03"`, `"3"`≢`"3.5"`, `"Annual 1"`≠`"1"`.
- `test_fechas_y_anios`: límites 1800/2100, 29 de febrero real, 31 de abril inválido.
- `test_mensajes_no_filtran_internos`: ningún mensaje contiene `metadata_source`, `locked_fields`,
  `None`, `422` ni el texto de la excepción.

### 7.2 PG real (`tests/test_metadatos_manuales_pg.py`)

Usa el fixture transaccional de `tests/test_huecos_pg.py` (revierte siempre). Casos:

| # | Caso | Comprueba |
|---|---|---|
| PG-1 | Guardar los 6 campos de serie en una serie con `metadata_={"alta": …}` | valores; `metadata_["manual"][campo]["fecha"]` valida; `locked_fields` con las claves; `metadata_source` y `metadata_["alta"]` intactos; `updated_at` cambia |
| PG-2 | Guardar los 5 campos de número con `metadata_={"comicinfo_aplicado": …}` | valores; manual+fecha; `locked_fields`; `metadata_source` y `comicinfo_aplicado` intactos |
| PG-3 | Guardar sin cambiar nada | no crea entradas manual, no añade candados, no cambia `updated_at` (o lo cambia solo si el ORM lo hace; el test no exige lo segundo) |
| PG-4 | Cambiar solo un campo de los seis | solo ese queda manual y bloqueado |
| PG-5 | Desbloquear | valor igual; `manual` sigue; `locked_fields` sin la clave; re-proteger la vuelve a añadir |
| PG-6 | Editorial existente con otra caja (`"Planeta"` vs `"planeta"`) | reutiliza la fila; no duplica |
| PG-7 | Editorial nueva | crea `Publisher` con `metadata_source='manual'`; segunda serie la reutiliza |
| PG-8 | Editorial vacía | `publisher_id=NULL`; el `Publisher` no se borra |
| PG-9 | Colisión exacta `(serie,"3",1)` | no escribe nada; error `colision`; valores previos intactos |
| PG-10 | Colisión por ceros (`"03"` frente a `"3"`) | misma respuesta; no escribe |
| PG-11 | Mismo número con `volume=2` | no es colisión; guarda |
| PG-12 | Número vacío | guarda `NULL`; `sort_order=NULL`; dos «sin número» conviven |
| PG-13 | `sort_order` al cambiar número | 2→2.0; 2,5→2.5; Annual→NULL; número sin cambio no lo toca |
| PG-14 | Huecos por número | serie Comic Vine total=5 con issues 1,2,4 → faltan {3,5}; cambiar 2→3 → faltan {2,5} |
| PG-15 | Huecos por formato | cambiar el 3 a `trade_paperback` → el 3 vuelve a faltar (solo grapa cubre grapa) |
| PG-16 | Huecos por total | total=6 → falta {6}; total=0/NULL → `computable=False` con `MOTIVO_SIN_TOTAL` |
| PG-17 | Unidad no acreditada | serie `metadata_source='anilist'` con total manual → sigue `computable=False` (H-2) |
| PG-18 | JSONB asignado en sitio vs. dict nuevo | mutar `metadata_` in situ no persiste; el servicio asigna dict nuevo y sí persiste tras `commit`+`refresh` |
| PG-19 | Carrera del `UNIQUE` | segunda sesión inserta el mismo número entre la comprobación y el flush → se traduce a `colision`, no 500 |
| PG-20 | `locked_fields` ajenos | una serie con `series_id`/`comic_vine_id` en `locked_fields` los conserva |
| PG-21 | Archivos | `files` no cambia (mismo número de filas y mismos `file_path`/`mtime`), y ninguna ruta de disco se toca |

### 7.3 Web (`tests/test_metadatos_manuales_web.py`, FakeSession)

| # | Caso | Comprueba |
|---|---|---|
| W-1 | GET `/ui/series/{id}/editar` | 200; campos precargados; garantía junto a Guardar; `Cache-Control: no-store`; sin `<script>` ni `hx-` en el formulario |
| W-2 | GET editar número | 200; formato seleccionado con etiqueta llana; fecha `YYYY-MM-DD` |
| W-3 | GET número de otra serie | 404 |
| W-4 | POST serie correcto | 303 a `/ui/series/{id}?guardado=serie`; cuerpo vacío o mínimo |
| W-5 | POST número correcto | 303 a la ficha del número con `?guardado=numero` |
| W-6 | POST serie con año inválido | 200; mismo formulario; valores conservados; mensaje «El año tiene que ser…»; no 422 |
| W-7 | POST número con formato inválido | 200; mensaje «Elige un formato de la lista.» |
| W-8 | POST colisión | 200; mensaje «Ya existe el nº 3…»; el servicio devuelve el error antes de escribir (no se llama a `flush`) |
| W-9 | Ficha con manual bloqueado | «Manual», fecha, chip «Protegido» y botón «Devolver a la fuente» |
| W-10 | Ficha con manual desbloqueado | «sin proteger» y botón «Proteger» |
| W-11 | POST devolver | 303; el campo sale de `locked_fields` (servicio) y la ficha no pierde el valor |
| W-12 | Aviso de éxito | la ficha con `?guardado=serie` pinta `ui.aviso("ok", …)` con la garantía |
| W-13 | Sin JS/htmx | ninguna plantilla nueva contiene `<script>`, `hx-confirm` ni `onclick=` |
| W-14 | Sinopsis preexistente de 25.000 caracteres sin tocar | guardar otro campo funciona; la sinopsis se conserva (3.10) |

### 7.4 Regresión (no se reescribe, se ejecuta)

- `tests/test_web_series.py` (ficha de serie y procedencia existente).
- `tests/test_huecos_pg.py` y `tests/test_api_series.py` (contrato de huecos).
- `tests/test_comicinfo.py` / los tests de #448 (respeto del candado y procedencia
  `comicinfo_aplicado`).
- `tests/test_web_css_contraste.py` si se añade cualquier clase CSS.
- `tests/test_web_comicinfo_ficha.py` (no romper la ficha del número al añadir la tabla).

### 7.5 Lo que no se prueba aquí

- Navegador real, móvil, lector de pantalla y flujo de teclado completo (NOT RUN; lo valida UX/QA).
- Tiempo real de guardado en la Pi (el presupuesto es estructural; medirlo sería otra ficha).
- Carrera con dos pestañas reales: PG-19 simula la carrera del `UNIQUE`, no la concurrencia de
  navegador.

---

## 8. Interacción con lo que ya existe

- **#448 (ComicInfo):** `services/comicinfo.py` ya respeta `locked_fields` y guarda su propia
  procedencia (`comicinfo_aplicado.aplicado`). Esta historia **no la toca**; los campos manuales
  bloqueados quedan fuera de su alcance por el candado. Su test de regresión debe seguir verde.
- **Enriquecido:** `services/enricher.py` y `services/enriquecimiento_plan.py` ya respetan
  `locked_fields` y proponen sin aplicar. Un campo manual desbloqueado vuelve a ser proponible; los
  bloqueados se muestran como «Protegido» en «Revisar cambios». No se cambia su contrato.
- **Título de serie y matcher:** `series.title_norm` es una columna generada por Postgres; al
  cambiar el título se recalcula sola. Si la serie **no** tiene identidad externa, el próximo
  enriquecido buscará por el nuevo título (efecto esperado: si el título corregido ya no coincide,
  no se enriquece; si coincide, puede traer datos a los campos no bloqueados). Si la serie ya tiene
  identidad externa, no se re-matchea. No se toca el matcher.
- **Número y enriquecido:** el enriquecido de issues busca por `series.comic_vine_id` +
  `issue.issue_number`. Corregir el número puede hacer que el próximo ciclo busque otro número y
  proponga sinopsis/portada/créditos del número nuevo. Los campos editados están bloqueados; los no
  editados pueden recibir propuesta. **No se limpia `comic_vine_id` del issue ni
  `enrichment_attempted_at`** en esta historia: hacerlo provocaría un enriquecido inmediato sobre un
  número recién corregido. Se documenta como interacción conocida y NOT RUN.
- **Huecos:** se recalculan con las reglas existentes; editar total no cambia la acreditación de
  unidad (3.8, H-2).
- **`sort_order`:** esta historia es la primera que lo escribe de forma deliberada para números
  editados. El resto de la biblioteca queda como está (NULL); todos los consumidores ya tienen el
  respaldo de `natural_key`, así que no hay orden mixto incorrecto.
- **Files/archivos:** ninguna consulta nueva toca `files` salvo las que ya hace la ficha; guardar no
  abre el archivo ni su `ComicInfo`.
- **Alta de series/números:** no se toca; la procedencia `metadata_["alta"]` convive con `manual`.
- **BL-INF6/7 y #480/B6:** quedan fuera; si en el futuro se escribe ComicInfo, deberá consultar
  `locked_fields` y `metadata_["manual"]` (nota para esa historia, no implementación aquí).

---

## 9. Rendimiento (Pi)

| Operación | Coste previsto |
|---|---|
| GET formulario de serie | 1 consulta a `series` (+ editorial si se precarga el nombre); < 20 ms |
| GET formulario de número | 1 consulta a `issue` + 1 a `series`; < 20 ms |
| POST guardado | cargar entidad + 1 consulta de colisión + 1 de editorial (solo si cambia) + UPDATE; < 50 ms |
| Re-render tras error | las mismas consultas del GET, sin escrituras |
| Memoria | sin estructuras grandes; el JSONB nuevo son ≤ 11 claves |

No hay red, ni disco, ni tareas de fondo. Sin N+1: la colisión se resuelve con una consulta a
`issues` de la serie (o `SELECT ... WHERE series_id=... AND volume=...`) y comparación acotada en
memoria. El tamaño de una serie (decenas/cientos de números) no justifica un índice nuevo; el
`UNIQUE` existente ya indexa `(series_id, issue_number, volume)`.

---

## 10. Seguridad y marco legal

- **Sin mass assignment:** `Form(...)` explícitos; no se copia el cuerpo crudo.
- **Sin IDOR:** el número se busca por `(id, series_id)`; si no coincide, 404.
- **Sin archivos:** no se importa `zipfile`, `shutil`, `Path` de escritura en el servicio nuevo; un
  test comprueba que no se crean/modifican filas `files`.
- **Sin red:** no se consultan fuentes; la edición manual funciona con las fuentes apagadas.
- **Sin JS ni dependencias:** no se añade ninguna.
- **XSS:** Jinja2 escapa; los mensajes de error son fijos, no incluyen el valor enviado (salvo el
  número en el mensaje de colisión, escapado por la plantilla). No se pinta HTML de la sinopsis.
- **Logs:** sin sinopsis ni editorial completas; sin rutas ni credenciales.
- **Legal:** el software gestiona metadatos; no facilita contenido ni escribe en los archivos. Los
  textos de procedencia no atribuyen a Tebeosfera/Comic Vine datos que no constan (LEGAL.md y §5 de
  CLAUDE.md).
- **Licencia:** no se copia código de las referencias (ver benchmark §12); si se reutilizara alguna
  idea de Komga (MIT), se revisaría el fichero y su aviso.

---

## 11. Despliegue y reversión

- **Sin migración:** `metadata_ JSONB`, `locked_fields ARRAY` y `publisher_id` ya existen en la base.
  No se escribe `alembic/versions/`.
- **Compatibilidad hacia atrás:** las filas con `metadata_` sin `manual` se leen como hoy; las
  claves nuevas de `locked_fields` (`title`, `start_year`, `end_year`, `publisher_id`,
  `total_issues`, `issue_number`, `release_date`, `format`, `synopsis`) son nombres que el
  enriquecido ya entiende o ignora sin romper.
- **Reversión de código:** volver a la versión anterior deja los valores en sus columnas y las
  entradas `manual` en JSONB; el código viejo no las lee pero tampoco se rompe. No hace falta
  limpiar datos. Si se quisiera «olvidar» la manualidad, sería un borrado de claves JSONB aparte
  (no está en esta historia).
- **Sin tareas de mantenimiento:** no hay cron, ni recomputación masiva, ni backfill.

---

## 12. NOT RUN (declaración explícita)

Esta tarea es **solo documentación**; no se ha implementado código ni ejecutado pruebas.

- No se ejecutó la suite, ni PG real, ni el navegador, ni el servidor.
- No se midió el rendimiento de guardado en la Pi; los números de §9 son presupuesto estructural.
- No se validó el flujo táctil/móvil ni el lector de pantalla.
- No se comprobó en una instalación real que el JSONB de una serie concreta no contenga ya una
  clave `manual` con otra forma; el código de lectura debe tolerarlo (P-7), pero eso se verifica en
  la implementación.
- No se probó la carrera real de dos pestañas; solo está prevista su simulación PG.
- No se ejecutó ninguna referencia externa (Sonarr, Radarr, Komga, Kavita, Mylar3, Kapowarr); el
  benchmark es lectura estática de código en los commits citados.
- No se reutilizó código de terceros.

---

## 13. Decisiones de detalle y dudas para el PO

**Tomadas por esta especificación [detalle] (reversibles):**

1. **Re-proteger** un campo manual desbloqueado (`POST .../proteger`), para que C-4 no sea
   irreversible.
2. **Conservar la entrada manual al desbloquear** (no borrarla): es lo que permite decir «Manual,
   sin proteger» sin mentir. La alternativa —borrar la marca— haría creer que el valor vino de una
   fuente.
3. **Tope de sinopsis 20.000** y **total 99.999**; sin truncar.
4. **Crear la editorial** si no existe (con `metadata_source='manual'`), en vez de obligar a elegir
   solo editoriales existentes.
5. **No tocar `sort_order` si el número no cambia**, para no reescribir la biblioteca existente.

**Dudas que conviene confirmar antes de implementar:**

1. **Huecos en series no-Comic Vine:** editar el total de una serie de Tebeosfera/AniList/GCD **no**
   hará que «te faltan» sea computable, porque C6 solo acredita la unidad de Comic Vine
   (`UNIDAD_DE_GRAPA = {comic_vine}`). ¿El PO quiere que un total escrito a mano acredite la unidad
   (historia aparte) o mantenemos la regla C6 y lo explicamos en la ficha? Esta spec propone
   mantenerla (H-2) para no cambiar el significado de «faltan» en mangas/tomos.
2. **«Manual» heredado:** un número o serie con `metadata_source='manual'` (alta manual antigua) no
   tiene fecha por campo. ¿Se muestra «Puesto a mano» sin fecha y sin acción de desbloqueo hasta que
   se edite, o se ofrece también desbloquear? Esta spec propone lo primero (no hay candado por campo
   que quitar).
3. **Re-protección:** si se considera demasiada superficie, se puede retirar la acción «Proteger» y
   dejar solo «Devolver a la fuente»; el AC-2 se sigue cumpliendo.

---

## 14. Trazabilidad AC ↔ requisitos ↔ pruebas

| AC | Requisitos | Pruebas |
|---|---|---|
| AC-1 | REQ-P1, P9, U3 | PG-1, PG-2, PG-4, W-9, W-12 |
| AC-2 | REQ-P6, P7, P10 | PG-5, W-10, W-11 |
| AC-3 | REQ-D4..D11, H1, H2, U3 | PG-9..PG-12, PG-19, W-6..W-8 |
| AC-4 | REQ-S1, S5 | PG-21, W-13, §7.4 |
| AC-5 | — | este documento + benchmark |
| AC-6 | REQ-H3, H4 | PG-13..PG-17 |
| AC-7 | REQ-U2, U6, U7 | W-1, W-4, W-5, W-12 |
| AC-8 | §3.1, §3.2, REQ-D1..D13 | PG-1, PG-2, W-1, W-2, W-6, W-7, W-14 |
| AC-9 | REQ-P3 | PG-1, PG-2 |
| AC-10 | REQ-P9, P10 | W-9, W-10, PG-5 |
| AC-11 | REQ-U4, U8 | W-1, W-13 |
| AC-12 | REQ-P1, S1 | §7.4 |

---

## 15. Caducidad

Esta especificación caduca con el benchmark: **2027-01-09**, o antes si cambia el contrato de
`metadata_`/`locked_fields`, la regla de huecos o el flujo de enriquecido.
