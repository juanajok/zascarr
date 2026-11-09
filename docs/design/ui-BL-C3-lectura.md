# UX — Marcar leído, leyendo o pendiente y puntuar (BL-C3, #150)

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas ni
> plantillas nuevas. Fija el control, el gesto, el copy, los estados, el filtro y las condiciones de
> accesibilidad; la implementación los lleva al código.
> **Base:** `origin/main` = `19e801612c5ee6b6ddab2d54e9ab8bb683aedb0e` (2026-11-09), worktree
> `.squad/wt-c3-ui`, rama `docs/c3-ui`.
> **Insumos:** issue #150 y su comentario de refinamiento del corte S (2026-11-09), benchmark
> `docs/design/benchmark-features-coleccionista-metron.md` §7.3, `CLAUDE.md` §6, el diseño de la
> ficha de número `docs/design/ui-BL-INF1-ficha-numero.md` y la ficha real
> (`web/templates/series_detail.html`, `web/templates/issue_detail.html`).
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**; este documento fija las
> condiciones que la implementación debe medir.

---

## 0. Resumen

C3 es **una capa de lectura local**, no un lector. No abre archivos, no habla con Kavita ni con la
red, no crea tablas ni migraciones y no toca `current_page`.

1. **Ficha de serie:** cada fila de número de «Archivos por número» lleva un **control segmentado de
   tres estados** (`Sin leer`, `Leyendo`, `Leído`). Se cambia **con un toque** en la etiqueta; se
   guarda solo, sin botón y sin recargar la página.
2. **Ficha de número:** bloque **«Tu lectura»** con estado, puntuación 1–5, nota corta y fechas si
   constan. Un único botón principal: **«Guardar mi lectura»**.
3. **Biblioteca:** filtro `?leido=si|no|leyendo` por series con números en ese estado, con recuento
   `3 de 12 series con algún número leído.` y un enlace de vuelta claro.
4. **Regla de oro:** quitar «Leído» **borra la fecha de fin**, pero **conserva la nota y la
   puntuación**. Se dice junto al control, no en una página de ayuda.

**Lo que no hace:** no muestra progreso de páginas, no pide valoración media, no escribe reseñas
públicas, no añade historial de relecturas ni estadísticas y no cambia ningún archivo.

**Presupuesto de entrada:** no se crea una pantalla nueva. Las frases fijas añadidas son el aviso
de la ficha de serie (14 palabras) y la ayuda de «Tu lectura» (9); la entrada existente de la ficha
de número sigue siendo «Todo lo que ZascArr sabe de este número.» (8). Ninguna supera 20.

---

## 1. Decisiones de estructura

### 1.1 Dónde vive el control en la ficha de serie

- En **«Archivos por número»**, en la **cabecera de cada fila de número**, junto al `#N` que ya
  enlaza a su ficha. Un solo control por número, no uno por archivo.
- La tira de chips de «En tu biblioteca» y los chips de «Te faltan» **no** llevan control: los chips
  son navegación, no formularios. El control de un número que no tiene fila de archivo se ejerce en
  su ficha de número (bloque «Tu lectura»), que se abre desde el chip.
- Los números «que faltan» no tienen `Issue` ni fila: no tienen control, ni un estado inventado.
- Si la implementación lista también números con `Issue` pero sin archivo, la misma regla se aplica a
  su fila: un control por número, siempre junto al `#N`, nunca dentro de un enlace.
- La fila actual (`h3` + archivos) **no se reordena**: el control se añade en la cabecera del número,
  antes de la lista de archivos.
- El bloque **no añade un botón principal** a la ficha de serie: el único sigue siendo «Añadir
  números del disco». El control de lectura guarda solo, sin botón por fila.

### 1.2 El gesto: etiqueta segmentada, sin botón

**Gesto elegido: un toque en una de las tres etiquetas del control segmentado.** No hay que abrir un
desplegable, no hay que pulsar «Guardar» y no se cicla con un botón único.

- El grupo es un `<fieldset>` con tres radios reales y etiquetas visibles:
  `Sin leer`, `Leyendo`, `Leído`.
- El estado actual se ve en la etiqueta seleccionada: fondo/borde de estado, peso de fuente y el
  punto nativo del radio. No depende solo del color.
- Al cambiar de radio, el formulario hace `POST` por HTMX y sustituye **solo la fila del número**.
  El estado se guarda en el acto.
- La garantía va justo debajo del título de la sección: «El estado se guarda al tocarlo; cambiarlo
  no borra tu nota ni tu puntuación.»
- En teclado, el grupo se recorre con Tab y las flechas; el foco visible es el del radio. Si las
  flechas producen varios cambios seguidos, `hx-sync` deja ganar al último estado; el resultado
  final es el que se confirma.

### 1.3 Dónde vive «Tu lectura» en la ficha de número

- **Justo después de la cabecera** (portada, H1, serie) y **antes** de «Datos del número». Es la
  tarea de la pantalla; no se esconde al final de la información.
- Funciona también si el número no tiene metadatos: la lectura es independiente de que exista
  sinopsis, fecha o páginas.
- Es el único bloque con acción de escritura de la pantalla y contiene el único botón principal,
  «Guardar mi lectura». Las secciones de datos, autores, archivos y procedencia no ganan botones.

### 1.4 Filtro de Biblioteca: qué significa cada valor

La Biblioteca pinta **series**, no números. El filtro se aplica a la serie según lo que contienen sus
números:

| Valor URL | Serie que entra | Etiqueta visible |
|---|---|---|
| `si` | tiene **al menos un** número con estado `completed` | «Con leídos» |
| `leyendo` | tiene **al menos un** número con estado `reading` | «Leyendo» |
| `no` | **no tiene ningún** número con estado `completed` | «Sin leídos» |

- `si` y `leyendo` pueden solaparse: una serie con un número leído y otro en lectura aparece en los
  dos filtros. Son facetas, no compartimentos estancos.
- `no` se interpreta como **«sin ningún número terminado»**, no como «al menos un número sin leer».
  Lo literal («al menos un número unread») incluiría casi toda la biblioteca y no filtraría nada; el
  valor útil para el coleccionista es «series sin leídos». Una serie que está leyendo pero no ha
  terminado aparece en «Sin leídos», y su etiqueta es verdadera: no tiene ningún número leído.
- **No** se llama «Sin empezar» a `no`: una serie puede estar empezada y seguir sin leídos; el copy
  no miente.
- El filtro se combina con `q`, tradición, editorial, personaje, saga y etiquetas. No cambia la
  paginación ni los demás contratos HTMX de la Biblioteca.

### 1.5 Recuento: series, no números

El criterio habla de «3 de 12 leídos», pero la pantalla cuenta **series**. El recuento visible es:

> **3 de 12 series con algún número leído.**

- El **3** son las series que cumplen el filtro.
- El **12** son las series que cumplen **los demás filtros** (sin contar el de lectura). Si no hay
  otros filtros, es el total de la biblioteca.
- Para el resto de valores: `2 de 12 series con algún número en lectura.` y
  `9 de 12 series sin ningún número leído.`
- Se evita la forma corta «3 de 12 leídos» porque confundiría series con números; el recuento de
  números no es el objeto de este filtro y exigiría otra consulta y otro concepto.

---

## 2. Wireframes

### 2.1 Ficha de serie — fila de número a 320/360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ARCHIVOS POR NÚMERO                          │
│ Cada número de la serie con sus archivos.    │
│ El estado se guarda al tocarlo; cambiarlo no │
│ borra tu nota ni tu puntuación.              │
│                                              │
│ #12  ver información del número 12           │
│ ┌──────────┬──────────┬──────────┐           │
│ │ Sin leer │ Leyendo  │ ● Leído  │  ← radios │
│ └──────────┴──────────┴──────────┘           │
│   The Wicked + The Divine 012.cbz   CBZ      │
│   ✓ En el disco                  [Desvincular]│
│                                              │
│ #13                                          │
│ ┌──────────┬──────────┬──────────┐           │
│ │● Sin leer│ Leyendo  │ Leído    │           │
│ └──────────┴──────────┴──────────┘           │
│   …                                          │
└──────────────────────────────────────────────┘
```

- A 320 px el `#N` y el control pueden ir en la misma línea o el control bajar a la siguiente; el
  grupo hace `flex-wrap` y **nunca** crea scroll lateral.
- Cada etiqueta es un objetivo táctil de al menos 44 px de alto; el radio nativo de 24 px queda
  dentro.
- El estado guardado se anuncia en una región `role="status"` pequeña junto al control, vacía al
  cargar: «Guardando…», «Guardado: Leído.». La fila no se convierte en un enlace.

### 2.2 Ficha de número — bloque «Tu lectura» a 320/360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a la serie                          │
│ [portada]  NÚMERO 12                         │
│            El panteón                        │
│            Todo lo que ZascArr sabe…         │
│                                              │
│ TU LECTURA                                   │
│ Márcalo cuando lo termines; ZascArr no lee   │
│ el archivo.                                  │
│                                              │
│ Estado                                       │
│ ┌──────────┬──────────┬──────────┐           │
│ │ Sin leer │ Leyendo  │ ● Leído  │           │
│ └──────────┴──────────┴──────────┘           │
│ Quitar «Leído» borra la fecha de fin, pero   │
│ conserva tu nota y tu puntuación.            │
│                                              │
│ Puntuación (1–5)   [ 4 ▾ ]                   │
│                                              │
│ Nota corta                                  │
│ ┌──────────────────────────────────────────┐ │
│ │ Lo que te pareció…                       │ │
│ └──────────────────────────────────────────┘ │
│ Máximo 280 caracteres.                       │
│                                              │
│ Empezado el 1 de septiembre de 2014          │
│ Terminado el 3 de septiembre de 2014         │
│                                              │
│ [ Guardar mi lectura ]  ← único principal    │
└──────────────────────────────────────────────┘
```

- Las fechas solo se pintan si constan y el estado las hace legibles: «Empezado» con `Leyendo` o
  `Leído`; «Terminado» solo con `Leído`.
- En la primera vez, bajo el H2 aparece «Todavía no has guardado nada de este número.»; no se pinta
  una caja de vacío ni un formulario deshabilitado.
- `current_page` no aparece en ninguna parte: no hay barra, ni «página 12 de 32», ni porcentaje.
- La puntuación es un `<select>` nativo con «Sin puntuación» y 1–5. Se eligió frente a cinco
  estrellas porque a 320 px las estrellas necesitan un sexto control para borrar la puntuación y
  añaden ruido al formulario; el select conserva el valor visible, se maneja con teclado y ocupa
  una línea.

### 2.3 Biblioteca — filtro, recuento y vacío

```
┌─ 360 px ─────────────────────────────────────┐
│ Biblioteca                                   │
│ Acota tu biblioteca por título, tradición…   │
│                                              │
│ [ Buscar por título… ]                       │
│ [ Todas las tradiciones ▾ ]                  │
│ [ Todas las editoriales ▾ ]                  │
│ Lectura  [ Con leídos ▾ ]                    │
│                                              │
│ 3 de 12 series con algún número leído.       │
│ [ Ver toda la biblioteca ]                   │
│                                              │
│ [portada] Título 1                           │
│ [portada] Título 2                           │
│ [portada] Título 3                           │
└──────────────────────────────────────────────┘
```

Vacío:

```
┌─ 360 px ─────────────────────────────────────┐
│ Lectura  [ Con leídos ▾ ]                    │
│                                              │
│ 0 de 12 series con algún número leído.       │
│                                              │
│ Ninguna serie de tu biblioteca tiene números │
│ leídos todavía.                              │
│ [ Ver toda la biblioteca ]                   │
└──────────────────────────────────────────────┘
```

- El filtro «Lectura» es un `<select>` nativo, con etiqueta visible; no hay chips de tres estados en
  la barra de filtros (serían tres controles más por pantalla).
- El enlace «Ver toda la biblioteca» aparece junto al recuento y en el vacío; devuelve a la
  biblioteca sin filtros. Con resultados, el chip «Lectura: con leídos» y su «Quitar» siguen siendo
  el camino preciso para quitar solo la lectura.
- «3 de 12» se pinta dentro de la región viva del recuento (`role="status"` existente), para que el
  cambio se anuncie al filtrar por HTMX.

---

## 3. Control de tres estados en la ficha de serie

### 3.1 Anatomía

- Contenedor: un formulario `POST` al endpoint de lectura del número; la fila de la serie y el
  bloque «Tu lectura» comparten el mismo contrato.
- Dentro: un `fieldset` con una leyenda (visible o solo para lectores de pantalla) y tres pares
  etiqueta/radio con el **mismo nombre** y valores internos `unread`, `reading`, `completed`.
- Una región de estado pequeña junto al control, vacía al cargar; muestra `Guardando…` y luego
  `Guardado: …` o el error.
- No se envía la nota ni la puntuación desde la fila de la serie: el formulario de la fila solo lleva
  `estado`; el servidor no toca esos datos.


- Esta es una **descripción de comportamiento**, no código para copiar: la implementación decide
  clases y nombres, pero debe conservar el grupo de radios accesible y las etiquetas visibles.
- Un solo nombre `estado`; los tres valores internos `unread`, `reading`, `completed`; los textos
  visibles son `Sin leer`, `Leyendo`, `Leído`.
- El formulario de la fila **solo envía `estado`**. No envía nota ni puntuación; esos datos no se
  tocan desde la fila y el servidor no los borra.
- El `POST` es explícito con `Form(...)`, sin puerta legal (dato local), `no-store` y sin red. La
  respuesta es el fragmento de la fila (o del control) para la actualización HTMX; con HTMX
  desactivado, el formulario hace POST normal y vuelve a la ficha con el estado guardado.

### 3.2 Cómo se ve el estado actual

- El radio del estado guardado está marcado.
- La etiqueta marcada usa el tratamiento de selección de los controles de la app: fondo de papel
  secundario, borde de tinta y peso; conserva el punto nativo del radio.
- Las tres etiquetas están siempre visibles; no se sustituyen por una sola etiqueta que cambia.
- Si no hay fila de `reading_progress`, el estado es `Sin leer` (el valor por defecto del modelo) y
  ese radio aparece marcado. No se escribe una fila solo por abrir la ficha.
- Si la fila existente tuviera un estado no expuesto (`on_hold` o `dropped`), el control muestra
  `Sin leer` y el aviso de la sección no promete conservarlo: la primera escritura normaliza al
  estado elegido. No se añade un cuarto control; esos valores quedan en el modelo, sin superficie.

### 3.3 Cómo se cambia y qué se confirma

- Un toque en otra etiqueta cambia el radio y lanza el guardado; no hay botón «Guardar» por fila.
- El radio se marca en el acto; el **estado guardado anterior** sigue en el servidor hasta que la
  respuesta confirma. Si la petición falla, se repinta el estado guardado anterior y se avisa.
- La región de estado anuncia **«Guardando…»** mientras se envía y **«Guardado: Leyendo.»**,
  **«Guardado: Leído.»** o **«Guardado: Sin leer.»** al terminar. El foco vuelve al radio elegido.
- Repetir el mismo estado no dispara un `change`; si se envía por otra vía, el servicio es
  idempotente y responde «Guardado».
- La fila no se recarga: se sustituye solo el control/fila; no hay `window.location.reload()` ni
  recarga bruta.

### 3.4 Desmarcar «Leído»

- Pasar de `Leído` a `Sin leer` o a `Leyendo` hace `POST` con `estado=unread` o `estado=reading`.
- El servicio pone `completed_at = NULL`; **no toca `rating` ni `notes`**.
- Si el estado nuevo es `Sin leer`, las fechas no se muestran (aunque `started_at` histórico siga en
  la base); si es `Leyendo`, se muestra «Empezado» si consta. No se inventa una fecha.
- La ficha de número conserva la nota y la puntuación en el formulario; el aviso junto al control y
  el copy de la sección lo dicen antes de que ocurra:
  «El estado se guarda al tocarlo; cambiarlo no borra tu nota ni tu puntuación.»
- No hay confirmación modal: el gesto es reversible (volver a marcar «Leído»), y el dato que se
  conserva es el que más duele perder.

### 3.5 Errores al guardar

| Situación | Qué se ve | Qué pasa con el control |
|---|---|---|
| Servidor responde error (validación/404) | «No se ha guardado. El número sigue como estaba.» + «Reintentar» | Se repinta el estado guardado anterior; no se finge el nuevo |
| Red caída / sin respuesta | «No se ha podido guardar: no hay conexión. El número sigue como estaba.» + «Reintentar» | Se restaura el estado anterior y se ofrece reintentar |
| Mismo estado | — | Sin petición; no hay cambio que guardar |

- «Reintentar» es un botón neutro, no principal; reenvía el estado elegido.
- La implementación puede reutilizar el patrón de eventos HTMX que ya existe en la app
  (`hx-on::send-error`/`hx-on::response-error` en `_vinculacion_revision.html`) para enseñar la
  región de error ya renderizada, sin añadir un script ni una librería. Si el proyecto prefiere no
  usar `hx-on`, el fallback es POST normal: el navegador muestra el error de red y no se presenta
  como guardado.
- El texto del error no incluye detalles técnicos ni el identificador del número.

### 3.6 Accesibilidad del control

- `<fieldset>` + `<legend>` (visible o `.sr`) + tres `<label>` asociados a sus radios.
- Teclado: Tab entra al grupo, flechas cambian de estado, Espacio confirma el radio enfocado; el
  foco es visible y no se pierde al sustituir el fragmento (el radio marcado recibe el foco).
- No se usan `<div>` clicables ni `aria-pressed` manual; el estado lo comunica el radio nativo.
- El color no es el único indicador: etiqueta de texto + radio marcado + peso/borde.
- A 320 px los labels tienen `min-height` táctil y el grupo envuelve; no hay scroll horizontal.
- El aviso de estado es `role="status"` (educado); el error es `role="alert"`.

---

## 4. Bloque «Tu lectura» en la ficha de número

### 4.1 Campos y orden

1. **H2 «Tu lectura»**.
2. Frase de ayuda: «Márcalo cuando lo termines; ZascArr no lee el archivo.» (9 palabras).
3. **Estado**: mismo grupo de tres radios; etiqueta visible «Estado» o `legend`; por defecto
   `Sin leer`.
4. **Puntuación (1–5)**: `<select>` con «Sin puntuación», 1, 2, 3, 4, 5. La opción vacía permite
   borrar la puntuación (`NULL`); no se puede poner 0 ni 6.
5. **Nota corta**: `<textarea>` con etiqueta visible y `maxlength="280"`; ayuda «Máximo 280
   caracteres.». Texto plano; el servidor la escapa y valida la longitud. No se muestran etiquetas
   HTML ni se interpretan.
6. **Fechas si constan**: «Empezado el …» / «Terminado el …», solo cuando el estado las hace
   legibles. Sin fecha inventada; sin hora si el dato es de día.
7. **Único botón principal**: **«Guardar mi lectura»**.
8. Garantía junto al estado: «Quitar «Leído» borra la fecha de fin, pero conserva tu nota y tu
   puntuación.» (14 palabras).
9. Si no hay fila guardada, una línea discreta: **«Todavía no has guardado nada de este número.»**
   (8 palabras). Desaparece en cuanto existe una lectura guardada.

- La frase de ayuda y la garantía están visibles antes del botón; el resto son campos.
- **Presupuesto:** la copy fija visible antes del principal (H2, ayuda, primera vez, etiqueta de
  estado y sus tres radios, «Puntuación (1–5)», «Nota corta», «Máximo 280 caracteres.» y la
  garantía) suma **45 palabras**; con la etiqueta del propio botón, **48**. En ambos casos queda
  dentro del límite de 50. Los valores variables (serie, fecha, puntuación elegida) no cuentan.
- No hay botón «Cancelar», «Borrar lectura» ni «Marcar como leído» separado: el estado se cambia en
  el mismo formulario y se guarda con el principal.
- No se muestra `current_page` ni ningún progreso por páginas; no es un lector.

### 4.2 Estados del formulario

| Situación | Estado de los campos | Copy |
|---|---|---|
| Primera vez (sin fila) | `Sin leer`; puntuación «Sin puntuación»; nota vacía; sin fechas | «Todavía no has guardado nada de este número.» |
| Datos parciales | Lo que consta; lo ausente queda vacío | Sin «No consta» por campo: los campos vacíos son la ausencia |
| Leído | Estado `Leído`; fechas si constan; nota/puntuación si constan | Garantía de conservación visible |
| Guardado correcto | Mismos valores confirmados | «Guardado: Leído.» / «Guardado: Leyendo.» / «Guardado: Sin leer.» |
| Sin cambios | Mismos valores | «No había cambios que guardar.» |
| Error de validación | Valores conservados | «La puntuación debe ser de 1 a 5, o estar vacía.» / «La nota es demasiado larga. Máximo 280 caracteres.» |
| Error de red | Valores conservados | «No se ha podido guardar: no hay conexión. Tu lectura no ha cambiado.» |
| Error del servidor | Valores conservados | «No se ha podido guardar. No se ha cambiado nada.» |
| Desmarcar «Leído» | `Sin leer`; nota/puntuación intactas; «Terminado» desaparece | «Guardado: Sin leer. Tu nota y tu puntuación se conservan.» |

### 4.3 Guardado sin recarga

- El formulario hace `POST` con HTMX a
  `/ui/series/{series_id}/numero/{issue_id}/lectura`; la respuesta sustituye **solo el bloque «Tu
  lectura»** (cabecera, formulario y aviso), no la página entera.
- El botón principal muestra el estado de envío (`Guardando…`) y no se duplica; al terminar, el
  aviso `role="status"` anuncia «Guardado…» y el foco va al aviso o al H2 del bloque, no al principio
  de la página.
- Sin HTMX, el `POST` normal recarga la ficha con los valores guardados; no se depende de JS para lo
  esencial.
- `Cache-Control: no-store`; sin red externa; sin puerta legal.
- El servicio hace `upsert` por `issue_id` (la tabla tiene `unique=True`), valida estado, puntuación
  y nota, y es idempotente. Repetir el guardado no duplica.

### 4.4 Fechas

- `Empezado`: `started_at` si consta y el estado es `Leyendo` o `Leído`.
- `Terminado`: `completed_at` si consta y el estado es `Leído`.
- Se muestra la fecha en llano («1 de septiembre de 2014»), sin hora y sin locale dependiente.
- Al pasar a `Leído`: se pone `completed_at` si estaba vacío (no se pisa una fecha ya existente).
- Al salir de `Leído`: se borra `completed_at`; la nota y la puntuación se conservan. `started_at`
  histórico puede quedar en la base, pero **no se pinta** con `Sin leer` para no decir «Empezado» y
  «Sin leer» a la vez.
- Si no hay fechas, no se pinta ninguna fila.

### 4.5 Estados no expuestos

`ReadingStatus` tiene también `on_hold` y `dropped`. En el corte S **no se ofrecen**: el control
muestra solo `Sin leer`, `Leyendo` y `Leído`. Si una fila existente tuviera uno de esos valores, el
control lo presenta como `Sin leer` y el guardado normaliza al estado elegido; no se promete
conservar un estado que la pantalla no sabe explicar. No hay migración ni cuarto botón.

---

## 5. Filtro de Biblioteca

### 5.1 Dónde y cómo

- Un `<select name="leido" id="f-leido">` en la barra de filtros principal, con etiqueta visible
  **«Lectura»**:
  - `Todas` → `""`
  - `Con leídos` → `si`
  - `Leyendo` → `leyendo`
  - `Sin leídos` → `no`
- El formulario existente ya hace `hx-get` sobre `#rejilla` con `hx-trigger="change, submit"`; el
  nuevo select se suma a ese contrato, sin JavaScript nuevo.
- La URL canónica incorpora `leido`; se valida contra los tres valores; un valor desconocido se
  descarta y se avisa («El filtro de lectura no era válido; se ha quitado.»), como el resto de
  filtros.
- El filtro se conserva al paginar y al cambiar de vista (tarjetas/lista), porque viaja en la URL.
- «Limpiar todos» y «Quitar» del chip lo eliminan; la URL sin `leido` es la vuelta a todas.

### 5.2 Recuento con filtro activo

- La consulta calcula **dos** totales fijos, sin N+1:
  - `total`: series que cumplen todos los filtros, incluido lectura.
  - `base`: series que cumplen todos los filtros **excepto** lectura (denominador del «de»).
- Texto exacto:
  - `si`: «{total} de {base} series con algún número leído.»
  - `leyendo`: «{total} de {base} series con algún número en lectura.»
  - `no`: «{total} de {base} series sin ningún número leído.»
- Si `base` es 0 (los demás filtros no dejan ninguna serie), no se pinta una fracción imposible: se
  usa el vacío general de la Biblioteca («Ninguna serie coincide con estos filtros.»).
- El total de la página y el recuento usan la misma condición; no se muestran tarjetas que no
  cumplan.
- El recuento vive en la región `role="status"` existente para que el cambio se anuncie al filtrar.

### 5.3 Chip activo y enlace de vuelta

- Con el filtro activo, aparece un chip:
  - «Lectura: con leídos»
  - «Lectura: leyendo»
  - «Lectura: sin leídos»
- El chip lleva «Quitar» con las URLs de página y de fragmento, como el resto de filtros activos.
- **Enlace de vuelta:** el recuento con filtro activo termina con **«Ver toda la biblioteca»**, que
  lleva a la biblioteca sin filtros. El «Quitar» del chip sigue disponible para quitar solo la
  lectura y conservar los demás filtros.
- En el vacío se repite **«Ver toda la biblioteca»** como acción principal de vuelta.
- No se duplica el enlace en la barra de filtros: el chip es el camino preciso y «Ver toda la
  biblioteca» el general.

### 5.4 Vacíos

| Filtro | Situación | Texto exacto |
|---|---|---|
| `si` | sin resultados | «Ninguna serie de tu biblioteca tiene números leídos todavía.» |
| `si` | sin resultados con otros filtros | «Ninguna serie coincide con estos filtros y tiene números leídos.» |
| `leyendo` | sin resultados | «Ninguna serie tiene números en lectura.» |
| `leyendo` | sin resultados con otros filtros | «Ninguna serie coincide con estos filtros y tiene números en lectura.» |
| `no` | sin resultados | «Todas las series de tu biblioteca tienen algún número leído.» |
| `no` | sin resultados con otros filtros | «Con estos filtros, todas las series tienen algún número leído.» |

- En todos los vacíos se muestra «Ver toda la biblioteca» como acción de vuelta.
- No se muestra una cuadrícula vacía ni un «0 series» sin explicación; el recuento (`0 de N`) y la
  frase explican por qué no hay nada.

---

## 6. Tabla de estados y textos finales

| # | Contexto | Situación | Texto visible | Comportamiento |
|---|---|---|---|---|
| 1 | Serie | Número sin fila de lectura | «Sin leer» marcado | Primera vez; no se escribe nada hasta que se toque otro estado |
| 2 | Serie | Tocar «Leyendo» | «Guardado: Leyendo.» | `status=reading`; fila actualizada; foco en el radio |
| 3 | Serie | Tocar «Leído» | «Guardado: Leído.» | `status=completed`; `completed_at` si vacío |
| 4 | Serie | Quitar «Leído» → «Sin leer» | «Guardado: Sin leer. Tu nota y tu puntuación siguen guardadas.» | `completed_at=NULL`; `rating`/`notes` intactos |
| 5 | Serie | Quitar «Leído» → «Leyendo» | «Guardado: Leyendo.» | `completed_at=NULL`; nota/puntuación intactas |
| 6 | Serie | Guardando | «Guardando…» | Indicador HTMX; sin recarga |
| 7 | Serie | Error del servidor | «No se ha guardado. El número sigue como estaba.» + «Reintentar» | Vuelve al estado guardado; botón neutro |
| 8 | Serie | Error de red | «No se ha podido guardar: no hay conexión. El número sigue como estaba.» + «Reintentar» | Restaura el estado anterior; reintento |
| 9 | Número | Primera vez | Estado «Sin leer», puntuación «Sin puntuación», nota vacía, sin fechas; «Todavía no has guardado nada de este número.» | Formulario listo; no hay fila hasta guardar |
| 10 | Número | Parcial | Los campos que constan; los vacíos quedan vacíos | Sin «No consta» por campo: la ausencia es el estado vacío |
| 11 | Número | Guardar cambio | «Guardado: Leído.» / «Guardado: Leyendo.» / «Guardado: Sin leer.» | Bloque actualizado; foco al aviso; sin recarga |
| 12 | Número | Guardar sin cambios | «No había cambios que guardar.» | Sin escritura duplicada |
| 13 | Número | Quitar «Leído» | «Guardado: Sin leer. Tu nota y tu puntuación se conservan.» | `completed_at=NULL`; nota/puntuación intactas; «Terminado» desaparece |
| 14 | Número | Puntuación fuera de rango | «La puntuación debe ser de 1 a 5, o estar vacía.» | No guarda; conserva el resto |
| 15 | Número | Nota demasiado larga | «La nota es demasiado larga. Máximo 280 caracteres.» | No guarda; conserva el resto |
| 16 | Número | Error de red | «No se ha podido guardar: no hay conexión. Tu lectura no ha cambiado.» | Valores conservados; el principal reintenta |
| 17 | Número | Error del servidor | «No se ha podido guardar. No se ha cambiado nada.» | Valores conservados; el principal reintenta |
| 18 | Número | Estado no expuesto (`on_hold`/`dropped`) | «Sin leer» marcado | La primera escritura normaliza; no hay cuarto control |
| 19 | Biblioteca | Filtro «Con leídos» con resultados | «3 de 12 series con algún número leído.» | Chip «Lectura: con leídos» + Quitar |
| 20 | Biblioteca | Filtro «Leyendo» con resultados | «2 de 12 series con algún número en lectura.» | Chip «Lectura: leyendo» + Quitar |
| 21 | Biblioteca | Filtro «Sin leídos» con resultados | «9 de 12 series sin ningún número leído.» | Chip «Lectura: sin leídos» + Quitar |
| 22 | Biblioteca | «Con leídos» sin resultados | «0 de 12 series con algún número leído.» + «Ninguna serie de tu biblioteca tiene números leídos todavía.» + «Ver toda la biblioteca» | Enlace de vuelta a toda la biblioteca |
| 23 | Biblioteca | «Leyendo» sin resultados | «0 de 12 series con algún número en lectura.» + «Ninguna serie tiene números en lectura.» + «Ver toda la biblioteca» | Enlace de vuelta |
| 24 | Biblioteca | «Sin leídos» sin resultados | «0 de 12 series sin ningún número leído.» + «Todas las series de tu biblioteca tienen algún número leído.» + «Ver toda la biblioteca» | Enlace de vuelta |
| 25 | Biblioteca | `leido` inválido en la URL | «El filtro de lectura no era válido; se ha quitado.» | Se muestra la biblioteca sin ese filtro |
| 26 | Biblioteca | Otros filtros dejan base 0 | «Ninguna serie coincide con estos filtros.» | Sin fracción «0 de 0» |

---

## 7. Accesibilidad y 320 px

### 7.1 Formularios y etiquetas

- Los tres estados son `<input type="radio">` reales dentro de un `<fieldset>`; cada uno tiene su
  `<label>` visible y su nombre accesible («Sin leer», «Leyendo», «Leído»).
- La puntuación es un `<select>` con `<label for>` visible; la nota, un `<textarea>` con etiqueta
  visible; la fecha no es un control, es texto.
- El botón «Guardar mi lectura» es un `<button type="submit">` real con `.primary`; es el único
  principal de la ficha de número. «Reintentar» y «Quitar» son neutros.
- La fila de serie no contiene un enlace que envuelva el control: el `#N` es un enlace y el
  formulario es un control aparte; no se anidan interactivos.
- El select de filtro tiene etiqueta visible «Lectura»; el chip activo tiene su «Quitar» con nombre
  accesible.

### 7.2 Teclado y foco

- Radios: Tab entra, flechas cambian, Espacio confirma; el foco visible no se oculta.
- Tras guardar en la fila: el foco vuelve al radio marcado; el aviso se anuncia sin mover el foco
  fuera del control.
- Tras guardar en «Tu lectura»: el foco va al aviso `role="status"` o al H2 del bloque, nunca al
  inicio de la página.
- Tras un error: el foco va al `role="alert"`; el formulario conserva los valores para reintentar.
- El filtro actualiza el recuento en la región viva existente; el foco se queda en el select.
- No hay atajos propios ni trampas de foco; no hay diálogos nativos ni `hx-confirm`.

### 7.3 320 px y contraste

- El grupo de estados usa `display: flex; flex-wrap: wrap; gap`; a 320 px puede ocupar dos líneas,
  pero no crea scroll horizontal.
- Cada etiqueta de estado tiene un objetivo táctil de al menos 44 px de alto; el radio nativo no se
  oculta a 24 px.
- El bloque «Tu lectura» es una sola columna; el `<select>` y el `<textarea>` ocupan el ancho
  disponible; la nota no desborda.
- La fila de número mantiene el `#N` y los archivos con `overflow-wrap: anywhere`; el control no
  tapa ni desplaza el botón «Desvincular».
- El estado no se distingue solo por color: texto + radio marcado + borde/peso. Se usan los tokens
  de `web.css`; no se añaden colores.
- Texto informativo ≥14 px; cifras de recuento con `font-variant-numeric: tabular-nums`.
- El foco visible y el contraste de los estados se comprueban con la prueba de contraste existente y
  con teclado real.

### 7.4 Anuncios

- `Guardando…` y `Guardado…` en una región `role="status"` (educada).
- Errores en `role="alert"`.
- El recuento de Biblioteca sigue en su `role="status"`/región viva existente.
- No se anuncia cada tecla ni cada cambio de radio antes de guardar; se anuncia el resultado.

---

## 8. Decisiones de copy

1. **«Sin leer / Leyendo / Leído»**, no «Pendiente / En curso / Terminado». Son los textos del
   criterio y los que el coleccionista usa; el modelo interno (`unread`, `reading`, `completed`) no
   aparece.
2. **«Guardar mi lectura»** es el único principal de la ficha de número. En la fila de serie no hay
   botón: **un toque en la etiqueta guarda**. La garantía va junto al control, no en una cabecera
   lejana.
3. **«Quitar «Leído» no borra tu nota ni tu puntuación»** se dice de forma visible en las dos
   pantallas. Es la decisión que evita que el coleccionista tenga miedo de tocar el estado.
4. **«ZascArr no lee el archivo»** aparece en «Tu lectura» para separar «leído» de una integración
   con Kavita que no existe. No se promete sincronización.
5. **«3 de 12 series con algún número leído.»**, no «3 de 12 leídos»: la pantalla cuenta series, no
   números. El filtro es de series; el recuento de números exigiría otro concepto.
6. **«Sin leídos»** es el valor `no`: series sin ningún número terminado. No se llama «Sin empezar»
   porque una serie puede estar leyéndose y seguir sin leídos; el copy no miente.
7. **Puntuación con «Sin puntuación»**: el select permite borrar (`NULL`) sin un botón extra; no se
   usan estrellas que obliguen a un sexto control para quitar la nota. El valor actual siempre se ve.
8. **Fechas solo si constan y son legibles**: «Empezado»/«Terminado», nunca una fecha deducida ni
   `created_at`. Al quitar «Leído» desaparece «Terminado»; no se inventa «Sin fecha».
9. **Sin `current_page`**: no hay progreso de páginas, ni porcentaje, ni barra. El modelo lo guarda
   para el lector, pero esta UI no lo expone ni lo escribe.
10. **Sin jerga**: no aparecen `reading_progress`, `completed_at`, `current_page`, `upsert`, `rating`
    ni `status`; tampoco «token» ni «lote». Los errores no enseñan códigos internos.
11. **La nota es corta**: máximo 280 caracteres, texto plano, sin HTML. Se valida en el servicio, no
    solo en el formulario.
12. **Idempotencia**: repetir el mismo guardado no crea otra fila ni cambia la fecha; el copy dice
    «No había cambios que guardar.» cuando no hay nada que hacer.

---

## 9. Lo que deja fuera

- **`current_page` y progreso de lectura**: no se muestra, no se edita y no se toca.
- **Historial y relecturas** (varias fechas, `read_count`), estadísticas de lectura, porcentaje leído
  y contadores del Inicio.
- **Nota o puntuación en la fila de la serie**: la fila solo lleva el estado; la nota vive en la
  ficha de número. Tampoco se muestra «Puntuado 4/5» junto al control.
- **Estados `on_hold` y `dropped`**: quedan en el modelo sin superficie; no hay cuarto estado ni
  migración.
- **Integración con Kavita** o cualquier lector; no hay scrobble automático.
- **Reseñas públicas, «me gusta», valoración media de otros.**
- **Filtros de lectura sobre números** o una lista de números en Biblioteca: el filtro es de series,
  como el resto de la pantalla.
- **Botón de lectura en números que no existen como `Issue`**: los huecos no tienen lectura.
- **Nuevo JS, nueva dependencia, migración, red o cambios de archivos**: nada de eso entra.
- **Medición real** de navegador, teclado físico, lector de pantalla, 320 px y Pi: queda como
  verificación pendiente de la implementación.

---

## 10. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Control de tres estados en cada número presente de la ficha de serie | Cada fila de «Archivos por número» tiene su grupo; los huecos no; un solo control por número |
| 2 | Estado actual visible y cambiable con un gesto | Radio marcado + etiqueta seleccionada; tocar otra etiqueta guarda; sin botón por fila |
| 3 | Desmarcar «Leído» conserva nota y puntuación | Servicio: `completed_at=NULL`; `rating`/`notes` intactos; copy visible |
| 4 | Bloque «Tu lectura» con estado, 1–5, nota y fechas | Render de la ficha de número; un solo `.primary`; sin `current_page` |
| 5 | Filtro `?leido=si|no|leyendo` con recuento y vuelta | URL canónica, chip activo, ratio «N de M», vacío con «Ver toda la biblioteca» |
| 6 | Guardado sin recarga y errores claros | HTMX actualiza fragmento; `role=status`; error de red y de servidor con reintento |
| 7 | Accesibilidad y 320 px | Radios/etiquetas, teclado, foco visible, 14 px, sin scroll lateral, contraste |
| 8 | Sin código nuevo de red, archivo o migración | POST local, `Form(...)`, `no-store`, sin red ni cambios de archivos |
| 9 | Copy sin jerga | Buscar en render `reading_progress`, `completed_at`, `current_page`, `status`, `rating`, `upsert`, `token` |
| 10 | Idempotencia | Dos guardados iguales no duplican ni cambian la fecha; «No había cambios…» si procede |

**PASS de este documento:** control, gesto, copy, estados, filtro y condiciones de accesibilidad
decididos y coherentes con #150 (corte S), benchmark §7.3 y `CLAUDE.md` §6.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos y
Pi. No se declaran.
