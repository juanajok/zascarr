# SPEC: «Filtrar Pendientes por carpeta por nombre y estado» (BL-FILT1, issue #397) — v1.0

> **Estado:** v1.0 — **ratifica los 7 criterios** del issue y las decisiones del PO del **2026-10-31** y del
> **2026-11-01** (ficha). No hay preguntas abiertas que bloqueen; los textos exactos quedan fijados aquí y los
> valida UX en contenido, no en significado. Esta spec **no autoriza implementar por sí sola**: decide el PO.
> **Base contrastada:** `origin/main` = `f6964ae` (worktree `feat/397-filtro-carpetas`). La ficha contrasta
> `9d7fedf`; los ficheros que toca esta historia **no han cambiado** desde entonces (`git log 9d7fedf..HEAD --
> <ficheros>` sin commits), así que sus referencias de código siguen vigentes salvo el número de línea, que aquí
> se actualiza.
> **Semilla:** issue #397 + `docs/design/benchmark-FILT1-filtro-carpetas.md` (nivel 1, 2026-11-01), con las
> decisiones del PO de su §«Decisiones del PO del 2026-11-01».
> **Notación:** EARS con CUANDO / MIENTRAS / SI…ENTONCES / DONDE; AC en Given/When/Then; IDs `FR-`/`AC-`.
> **Textos de UI:** los de §5 son **exactos**; van entre comillas y se prueban tal cual.
> **Hermana, no la misma:** #283 (BL-IT01, filtros de la Biblioteca) ya está en `main` y se toma como
> **precedente de estilo y de contrato**, no se toca.

---

## 0. Resumen ejecutivo

**Qué pide la historia.** En «Pendientes por carpeta» (`/ui/pendientes/carpetas`) hoy solo se pagina y se puede
fijar una serie con `?serie=`; no hay filtro. Con ~108 carpetas de referencia (y más), encontrar una concreta
obliga a recorrer páginas. Se añade un filtro por **nombre de la carpeta** (coincidencia parcial, sin
mayúsculas ni tildes) y por **estado** (selector excluyente: todas / sin serie / con serie sugerida / mixto),
más dos **marcas independientes** («Por confirmar» y «En conflicto»), combinables entre sí y con la serie
fijada. El filtro vive en la **URL**, sobrevive a paginar y al asistente, y la pantalla dice cuántas carpetas
coinciden (**«N de M»**) y qué hacer si no coincide ninguna.

**Cómo se resuelve (decisiones ya tomadas).** Se filtra **en memoria, en el servicio**
(`RevisionCarpetas.carpetas`), sobre los grupos que hoy ya se construyen con **dos consultas**: la decisión
del PO del **2026-11-01** descarta el prefiltro SQL del nombre (pliegue distinto entre Python y PostgreSQL,
mismos totales, mismo coste). El criterio 5 del issue («se filtra en SQL») se ratifica en su parte
**verificable**: **el número de consultas no crece**. Ver §13.

**Qué no cambia.** Sin filtro, los datos, recuentos, orden, paginación, textos existentes y la API JSON son
los de hoy; la única adición visible es el formulario de filtro (y los enlaces de vuelta del asistente dejan
de perder página y serie cuando existen, §6.3/§13.3). `limite`/`desplazamiento` conservan su contrato actual
(422 si no son enteros), fuera de esta historia.

**Coste.** Una PR. Toca `services/revision_carpetas.py` (filtro y `coinciden`), `web/pendientes.py` (validación
y contexto), `templates/carpetas.html` (formulario, recuentos, vacío, enlaces) y los enlaces del asistente que
vuelven a la lista (§6). Sin migración, sin dependencia nueva, sin configuración nueva.

---

## 1. Problema y comportamiento actual (contrastado en `f6964ae`)

| Pieza | Hoy | Dónde |
|---|---|---|
| Ruta | `GET /ui/pendientes/carpetas` con `limite` (50 por defecto, 1–1000), `desplazamiento` (≥0) y `serie`. **Sin `nombre` ni `estado`.** | `web/pendientes.py:292-299` |
| Lectura | **Dos** consultas: `_leer` (una para A∪B, sin `WHERE` por nombre) y `_series` (solo si hay candidatas) | `services/revision_carpetas.py:475-506`, `:508-515` |
| Agrupación | Agrupa en memoria por `clave`, deriva el estado, ordena (conflicto primero, luego más registros, luego clave) y **pagina después** de quedarse con las útiles | `services/revision_carpetas.py:323-357` |
| Estado del grupo | `estado ∈ {sin_serie, serie_sugerida, mixto}`; además `por_confirmar` y `en_conflicto`, **no excluyentes** | `services/revision_carpetas.py:45`, `:99-112`, `:518-550` |
| Recuento de la vista | `total = totales.carpetas_utiles` (carpetas útiles, sin filtro); la frase global mezcla archivos A/B y sueltos | `web/pendientes.py:231`, `:240`; `templates/carpetas.html:49-51` |
| Paginación | Se rehace en una macro que conserva `limite` y, si hay, `serie`; **no** hay más estado | `templates/carpetas.html:4` |
| Página fuera de rango | 200 con «Esta página ya no existe» y enlaces a primera/última | `web/pendientes.py:232-236`; `templates/carpetas.html:77-87` |
| Serie inválida | 200 + aviso, nunca 422/500; se pinta la lista sin serie fijada | `web/pendientes.py:260-275` |
| Asistente: vuelta | «Volver a las carpetas» enlaza **sin parámetros**; «Elegir otra carpeta para esta serie» conserva solo `serie` | `_vinculacion_resultado.html:34,37,89,92`; `asistente_carpeta.html:7`; `asistente_vinculacion.html:5`; `_asistente_eleccion.html:15`; `asistente_alta.html:10`; `asistente_alta_resultado.html:8` |
| Resultado guardado | Pantalla de solo lectura que se puede reabrir con `ref`; sus vueltas tampoco llevan contexto | `asistente_resultado_guardado.html:12-18`; `web/asistente_vinculacion.py:575-610` |
| Privacidad | El registro de acceso de uvicorn **omite la query entera** (`?…`); la app solo registra el tipo de error | `utils/log_acceso.py:1-11,32-56`; `main.py:290-291`; `web/pendientes.py:318` |
| No-acciones | Una prueba prohíbe hoy **cualquier** `<form>`, `<button>`, `hx-*` o JS en la vista | `tests/test_web_carpetas_pg.py:288-299` |

**Qué no existe hoy:** ningún filtro; ningún recuento «N de M»; ningún estado vacío específico de filtro; ninguna
propagación de contexto por el asistente (se pierden página y serie, ficha §IGUALAR 1).

---

## 2. Alcance

### 2.1 En alcance

1. Filtro por **nombre de carpeta** (coincidencia parcial, «contiene», sin mayúsculas ni tildes).
2. Filtro por **estado** con selector excluyente: todas / sin serie / con serie sugerida / mixto.
3. Dos **marcas independientes**: «Por confirmar» y «En conflicto», combinables entre sí y con el estado.
4. Convivencia con `serie`, `limite` y `desplazamiento`; el filtro va en la URL y sobrevive a paginar.
5. Recuentos del conjunto filtrado, «N de M» y estado vacío con «Quitar el filtro».
6. Propagación del contexto por el asistente de carpetas (filtro, página y serie) al volver; sin parámetro de
   retorno.
7. Valores inválidos: 200 + aviso, nunca 422/500 (para los parámetros del filtro).
8. Privacidad: el valor del filtro no se registra en el log de acceso ni en los de la aplicación.

### 2.2 No-goals (explícitos)

| No-goal | Motivo |
|---|---|
| Filtro por **serie sugerida** o por **número de archivos** | Fuera de la primera versión (issue, decisiones del PO 2026-10-31) |
| Búsqueda **«exacta»** | Fuera de la primera versión; solo «contiene» |
| **Filtros guardados** en el navegador o en el servidor | Estado oculto que sorprende; la URL basta (ficha, resultado «Descartar por ahora») |
| **Prefiltro SQL** del nombre | Decisión del PO 2026-11-01: pliegue distinto Python/PostgreSQL, mismos totales, mismo coste (ficha §Resultado por idea) |
| Cambios en el **importador** o en el registro de archivos | Otra historia |
| Filtro en la **API JSON** (`/api/revision/carpetas`) ni en otras pantallas | Esta historia es la vista HTML; la API no recibe parámetros de filtro |
| **#283** (Biblioteca) | Historia hermana, no la misma; se toma como precedente, no se toca |
| Cambiar el **orden** de los grupos, el diseño de la tarjeta o la selección de la primera página | No hace falta para encontrar una carpeta |
| Chips individuales por filtro y «Limpiar todos» (patrón #283) | Se resuelve con un solo «Quitar el filtro»; los chips se dejan para después (§2.3) |
| Acciones que escriban, JS nuevo o HTMX nuevo en esta pantalla | La pantalla sigue siendo de solo lectura (el formulario es GET) |
| Dependencias, migraciones, variables de entorno o Ajustes nuevos | Sin modelo nuevo; RAM de la Pi |

### 2.3 Lo que se deja para después (anotado, no perdido)

- **Prefiltro SQL** del nombre: se reabriría con una medición en la Pi y una prueba de paridad de pliegue
  (ß, ø, æ, œ, đ, ł, ð, þ, ħ, ı, ½) contra PostgreSQL real (ficha, fila «Descartar por ahora»).
- **Chips de filtros activos** con retirada individual y «Limpiar todos», como #283.
- **Filtros guardados** (navegador o servidor) y **búsqueda exacta**.
- **Filtros por serie sugerida / número de archivos** y **filtro en la API**.
- **Medición en la Pi** del filtro en Python: no se hace aquí; el patrón de coste es lineal sobre los grupos ya
  cargados (hoy 108 carpetas de referencia; medida local de `carpetas()`: 2 consultas, p95 ≤ 2000 ms en ASGI,
  `tests/test_revision_carpetas_pg.py:594-640`). Si se quiere cifra de Pi, es otro encargo.

---

## 3. Contrato

### 3.1 Parámetros de `GET /ui/pendientes/carpetas`

| Parámetro | Tipo | Defecto | Valores admitidos | En la URL canónica |
|---|---|---|---|---|
| `nombre` | texto | `""` | texto libre; se recorta, se quitan controles y se limita a **200** caracteres | solo si no queda vacío tras recortar |
| `estado` | texto | `""` | `""` (= todas) · `todas` · `sin_serie` · `serie_sugerida` · `mixto` (se recorta; comparación exacta tras recortar) | solo si no es `""` ni `todas` |
| `por_confirmar` | texto | `""` | **solo** `1` activa; cualquier otro valor = inactiva | solo si `1` |
| `en_conflicto` | texto | `""` | **solo** `1` activa; cualquier otro valor = inactiva | solo si `1` |
| `serie` | texto | `""` | UUID de una serie existente; inválida o inexistente → 200 + aviso y se ignora (como hoy) | solo si es válida |
| `limite` | entero | `50` | 1–1000; fuera de rango o no entero → **422** (contrato actual, §3.5) | **siempre** |
| `desplazamiento` | entero | `0` | ≥0; no entero → **422** (contrato actual) | solo en enlaces de página y contexto de vuelta; **nunca** en el formulario |

Todos los parámetros de **filtro** son opcionales y se pueden combinar entre sí y con `serie` (AND). El
`nombre` se compara contra el **título visible de la carpeta** (`Grupo.clave`), que es el texto de la
tarjeta (`templates/carpetas.html:104`); incluye la tradición y los ascendentes tal como se muestran.

### 3.2 Validación y valores inválidos (siempre 200 + aviso, nunca 422/500)

| Caso | Comportamiento | Aviso exacto (§5.4) |
|---|---|---|
| `estado` fuera de la lista | 200; se descarta **solo ese valor**; el resto del filtro y la serie se aplican | «El estado de la carpeta no es válido; se muestran todos los estados.» |
| `por_confirmar` / `en_conflicto` distintos de `1` | 200; marca inactiva; **sin aviso** (el control solo emite `1`; el valor no es editable por la persona) | — |
| `nombre` con caracteres de control | 200; se quitan los controles y se aplica el texto limpio | «La búsqueda tenía caracteres no válidos; se han quitado.» |
| `nombre` de más de 200 caracteres | 200; se usan los primeros 200 | «La búsqueda era demasiado larga; se han usado los primeros 200 caracteres.» |
| `nombre` que normaliza a vacío (p. ej. «el», «los», «the», «¿?») | 200; **no** se aplica restricción de nombre; el filtro sigue activo para el recuento y el vacío | «El texto no contiene palabras que buscar; no se aplica el filtro de nombre.» |
| `serie` inválida o inexistente | 200 + aviso; lista sin serie fijada (comportamiento actual, regresión) | «No hemos encontrado esa serie. Se muestra la lista sin serie fijada. Puede que se haya borrado o que el enlace esté incompleto.» |
| Ninguna coincidencia | 200; estado vacío con salida (§5.3) | — |

**Nunca** un filtro produce 422 ni 500. Las excepciones de lectura ya existentes (503 con «No se han podido
leer los pendientes») se mantienen y su «Reintentar» conserva el filtro.

### 3.3 URL canónica

Se construye con `urlencode` y orden estable **`limite`, `serie`, `nombre`, `estado`, `por_confirmar`,
`en_conflicto`, `desplazamiento`**; los valores vacíos se omiten (`desplazamiento=0` también se omite; hoy
tampoco aparece). Esta regla conserva **literalmente** las URLs actuales cuando no hay filtro (p. ej.
`?limite=2`, `?limite=2&serie=<uuid>`, `?limite=2&desplazamiento=4`), que es lo que exige el criterio 6 y lo
que ya comprueban las pruebas (`tests/test_web_carpetas_pg.py:307-330,371-380,708-737`).

- **Formulario de filtro:** GET a `/ui/pendientes/carpetas`; incluye `limite`, `serie` (solo si es válida) y
  los **tres filtros visibles** (`nombre`, `estado`, `en_conflicto`); **no incluye `por_confirmar`** (solo se
  acepta por URL por compatibilidad y no tiene control) ni `desplazamiento` → aplicar un filtro vuelve a la
  página 1.
- **Quitar el filtro:** URL con `limite` y `serie` (si la hay), sin `desplazamiento` → página 1.
- **Quitar la serie:** URL con `limite` y los filtros, sin `serie` y sin `desplazamiento` → página 1.
- **Paginación:** conserva los filtros de la URL (incluido `por_confirmar` si venía), `serie` y `limite`, y añade `desplazamiento`.
- **Vuelta desde el asistente:** conserva los filtros de la URL (incluido `por_confirmar` si venía), `serie`, `desplazamiento` y `limite` si no es 50
  (la página es parte del contexto que se recupera, ficha MEJORAR 1). No hay parámetro de retorno (§6.4).

### 3.4 Respuesta del servicio y recuentos

`RevisionCarpetas.carpetas(...)` gana cuatro parámetros opcionales (`nombre`, `estado`, `por_confirmar`,
`en_conflicto`) y su respuesta informa de **dos números distintos**:

| Dato | Significado con filtro activo | Sin filtro |
|---|---|---|
| `totales.carpetas_utiles` | **M**: carpetas útiles totales, **sin filtrar** (no cambia de significado) | igual que hoy |
| `filtro.coinciden` (nuevo) | **N**: carpetas que pasan el filtro | `N = M`; el bloque se omite en el JSON (§3.5) |
| `pagina` | `limite`/`desplazamiento` de la petición | igual |
| `grupos` | rebanada de la lista **filtrada** (N) en ese desplazamiento | igual que hoy |
| Resto de `totales` | se mantiene sobre el conjunto sin filtrar (la vista no lo pinta cuando hay filtro) | igual que hoy |

- La **paginación** («Carpetas X–Y de N.») y la detección de página fuera de rango usan **N**.
- La frase **«N de M»** usa `filtro.coinciden` y `totales.carpetas_utiles`.
- El orden relativo de los grupos filtrados es el mismo que tenían (conflicto primero, luego más registros,
  luego clave; `revision_carpetas.py:334`): el filtro **no reordena**.
- El filtro se aplica **después** de `solo_utiles` (la vista pinta carpetas con contexto) y **antes** de
  paginar; los archivos sueltos no se filtran (no se pintan en esta pantalla).

### 3.5 Lo que no cambia

- `GET /api/revision/carpetas` no recibe parámetros de filtro y su JSON **no gana claves** sin filtro (el
  bloque `filtro` se omite cuando es `None`; ver AC-21). Sus campos existentes conservan significado.
- `contar_carpetas` (`web/pendientes.py:98-102`) sigue llamando sin filtro y contando lo mismo (el enlace
  «Verlos por carpeta (N carpetas)» de «Por revisar»).
- `limite` y `desplazamiento` conservan el 422 actual ante valores no enteros o fuera de rango
  (`tests/test_web_carpetas_pg.py:326-328`). **Precisión al criterio 4:** el «nunca 422» se refiere a los
  parámetros del filtro, no a la paginación, cuyo contrato no toca esta historia.

---

## 4. Modelo de estados: selector excluyente + dos marcas

### 4.1 Definiciones (derivadas del código vigente)

| Concepto | Definición exacta | Evidencia |
|---|---|---|
| `estado` | `mixto` si el grupo tiene archivos sin serie **y** con serie sugerida; `serie_sugerida` si solo sugeridos; `sin_serie` si solo sin serie | `revision_carpetas.py:518-526` |
| Etiquetas visibles del estado | «Sin serie» · «Serie sugerida, falta confirmar número y edición» · «Mezcla: archivos sin serie y con serie sugerida (falta confirmar número y edición)» | `revision_carpetas.py:49-55`; `templates/carpetas.html:106` |
| `por_confirmar` | Marca **no excluyente**: verdadera si el grupo tiene **algún** archivo con serie sugerida; por construcción, verdadera ⇔ `estado ∈ {serie_sugerida, mixto}`, falsa ⇔ `sin_serie` | `revision_carpetas.py:518-524,549` |
| `en_conflicto` | Marca **no excluyente**: verdadera si alguna señal del grupo tiene severidad `conflicto`; **independiente** del estado | `revision_carpetas.py:532`; `:46` |
| `mixto` | Es un **estado del selector** (la carpeta mezcla archivos sin serie y con serie sugerida). **No** es una marca y **no** tiene relación con «En conflicto». | `revision_carpetas.py:45,522-524` |

### 4.2 Semántica del filtro

1. **Selector excluyente** (un solo valor): `todas` (= sin restricción), `sin_serie`, `serie_sugerida`,
   `mixto`. Se compara con `Grupo.estado`.
2. **Marcas independientes** (cada una se puede activar o no): `por_confirmar` → `Grupo.por_confirmar`;
   `en_conflicto` → `Grupo.en_conflicto`.
3. **Combinación**: todos los criterios activos se combinan con **Y**. Con las dos marcas activas se exige
   que el grupo tenga **las dos** (intersección), no una u otra. «Por confirmar» selecciona, por definición,
   «Con serie sugerida» **o** «Mezcla» (no «Sin serie»).
4. **Combinaciones contradictorias** (p. ej. `estado=sin_serie` + `por_confirmar=1`) no son error: dan un
   conjunto vacío y se pinta el estado vacío de filtro (§5.3).
5. **`mixto` no es «en conflicto»**: una carpeta `mixto` sin señales de conflicto sale con
   `estado=mixto` y **no** sale con `en_conflicto=1`; una carpeta `sin_serie` con un conflicto sale con
   `en_conflicto=1` y **no** sale con `estado=mixto`. Se fija con AC-07.

---

## 5. Textos de UX (exactos)

### 5.1 Formulario de filtro

| Elemento | Texto exacto |
|---|---|
| Etiqueta del campo de nombre | «Nombre de la carpeta» |
| Placeholder del campo de nombre | «Parte del nombre» |
| Etiqueta del selector de estado | «Estado de la carpeta» |
| Opción «todas» | «Todas» |
| Opción sin serie | «Sin serie» |
| Opción con serie sugerida | «Con serie sugerida» |
| Opción mixto | «Mezcla (sin serie y con serie sugerida)» |
| Filtro de conflicto | «Solo carpetas con conflictos» |
| Botón de envío | «Filtrar» |
| Enlace de quitar (cuando hay filtro) | «Quitar el filtro» |

- **Revisión UI/UX del 2026-11-05:** la barra solo expone **«Solo carpetas con conflictos»**. `por_confirmar`
  sigue en el contrato del servicio y de la URL por compatibilidad, pero **no se ofrece** en la interfaz: por
  construcción equivale a «hay algún archivo con serie sugerida», que ya eligen «Con serie sugerida» o «Mezcla».
  Dos marcas con esa solapadura no ayudaban a un coleccionista no técnico; el conflicto sí aporta información
  distinta al estado.
- Formulario **GET** a `/ui/pendientes/carpetas`; sin HTMX, sin JavaScript; **un solo** `<form>` y **un solo**
  `<button type="submit">` en toda la pantalla (precisión de la regla «sin acciones», §10.2).
- La barra es una **rejilla** de campos con la etiqueta encima: **4 columnas** cuando el contenido deja sitio
  (desde 1241 px), **2** en los tramos en que el menú deja ancho suficiente (970–1240 px y 761–860 px, este último
  con la barra superior del móvil/tablet) y **1** en el resto (incluye 861–969 px, donde el menú lateral deja el
  contenido estrecho, y el móvil). Los anchos mínimos de columna son 200 px (nombre), 320 px (estado, para que
  «Mezcla (sin serie y con serie sugerida)» no se recorte), 275 px (conflicto, para que su texto quepa en una
  línea) y el del botón. Los campos y el botón comparten **44 px** de alto y base; el checkbox se centra con ellos.
  Antes el cambio a 2 columnas estaba en 900 px: a 960/901 px el botón se encogía hasta 10/0 px y la barra
  desbordaba; a 861–985 px el selector recortaba «Mezcla…».
- **Revisión PIXEL.ui (2026-11-05, Chrome 156 + Postgres real):** medido a 1722, 1280, 1241, 1240, 1100, 1000, 970,
  969, 960, 901, 861, 768, 761, 760 y 390 px, **sin desbordes horizontales en la barra** y con los textos de los
  controles completos en todos ellos. Se quitaron los dos `&nbsp;` `aria-hidden` que solo servían para alinear y se
  pasó a `align-items: end`: sin ellos la rejilla no necesita huecos fantasma y en móvil no deja dos líneas en
  blanco. Teclado: Tab `nombre → estado → conflicto → Filtrar`, foco visible de 3 px en todos (medido con teclado
  real, no programático); el `aria-label` del formulario es «Filtrar carpetas por nombre, estado y conflictos».
- El formulario no se presenta como una caja suelta de controles: la barra tiene su propio panel y el botón queda
  alineado con la base de los campos.
- **«Por confirmar» no se expone en la interfaz:** el servicio lo calcula como «hay algún archivo con serie sugerida»,
  que ya se selecciona con «Con serie sugerida» o «Mezcla». Exponerlo como marca duplicaba el filtro y confundía.
  El parámetro `por_confirmar` se conserva en el contrato del servicio por compatibilidad, pero la barra solo ofrece
  «Solo carpetas con conflictos», que sí aporta información distinta al estado.
- Los `hidden` `limite` y `serie` (si es válida) van **antes** de los campos visibles en el DOM: el GET
  serializa en ese orden y así el envío produce el orden canónico de §3.3.
- `nombre` se pinta en `value` escapado; `estado` con `selected`; las marcas con `checked`; `serie` (si es
  válida) y `limite` van en `hidden`; **`desplazamiento` no va** (§3.3).
- Los `value` del selector son los códigos internos de §3.1 (`sin_serie`, `serie_sugerida`, `mixto`); la
  persona solo ve las etiquetas de la tabla. No se muestra ningún código interno en pantalla.
- Las etiquetas son visibles (no `sr-only`) para que el campo se entienda; el formulario va después del `h1`
  y del aviso de serie (si lo hay), y antes del recuento.

### 5.2 Recuento con filtro activo

| Caso | Texto exacto |
|---|---|
| N > 1 | «{N} de {M} carpetas coinciden con el filtro.» |
| N = 1 | «1 de {M} carpetas coincide con el filtro.» |

`N` y `M` con el formato de miles de la pantalla (`{{ … | miles }}`, punto de millares). Se pinta donde hoy
va la frase global (`templates/carpetas.html:49-51`), que **se oculta** cuando hay filtro para no mezclar
recuentos globales con la lista filtrada. La línea de página («Carpetas X–Y de N.») se mantiene, con **N**
filtrado. Si N = 0 no se pinta el recuento: manda el estado vacío.

### 5.3 Estado vacío de filtro

| Caso | Texto exacto |
|---|---|
| Hay `nombre` | Título: «Ninguna carpeta coincide con «{nombre}».» |
| No hay `nombre` (solo estado/marcas) | Título: «Ninguna carpeta coincide con estos filtros.» |
| Cuerpo (siempre) | «Prueba a cambiar el filtro o a quitarlo.» |
| Acción | Enlace/botón «Quitar el filtro» (mismo destino que §3.3) |

Se usa el componente de estado vacío existente (`ui.estado_vacio`, `_componentes.html`), con el enlace como
acción principal de esa pantalla. `{nombre}` se escapa siempre. **Prioridad:** si hay filtro activo y N = 0,
se pinta **este** estado vacío aunque no haya ninguna pendiente en absoluto o aunque haya serie fijada; no se
pinta «Nada pendiente» ni el bloque de «no hay carpetas con contexto» (que ofrecería registrar la biblioteca,
que no es la causa).

### 5.4 Avisos (ámbar, encima del formulario)

| Situación | Texto exacto |
|---|---|
| `estado` inválido | «El estado de la carpeta no es válido; se muestran todos los estados.» |
| `nombre` con controles | «La búsqueda tenía caracteres no válidos; se han quitado.» |
| `nombre` > 200 | «La búsqueda era demasiado larga; se han usado los primeros 200 caracteres.» |
| `nombre` sin palabras tras normalizar | «El texto no contiene palabras que buscar; no se aplica el filtro de nombre.» |
| Serie inválida | El aviso actual, sin cambios (§3.2) |

Los de controles y longitud son **los mismos de #283** (`web/library.py:141-146`) para no inventar dos estilos
de aviso en la misma app; el de estado y el de «sin palabras» son nuevos. No se repite el valor inválido ni el
texto del filtro en el aviso.

### 5.5 Aviso de serie fijada (texto actualizado)

Hoy dice «…la lista no se filtra ni se reordena» (`templates/carpetas.html:40-42`), que **deja de ser cierto**
en cuanto hay filtro. Texto nuevo:

| Caso | Texto exacto |
|---|---|
| Sin filtro activo | «Se listan todas las carpetas con contexto. Las que encajan con esta serie llevan la marca «Sugerida para esta serie»; el orden no cambia.» |
| Con filtro activo | «Se listan las carpetas con contexto que coinciden con el filtro. Las que encajan con esta serie llevan la marca «Sugerida para esta serie»; el orden no cambia.» |

El enlace «Quitar la serie» **conserva el filtro** (pierde solo `serie` y la página, §3.3). El enlace «Ver la
ficha» no cambia.

---

## 6. Propagación y navegación

### 6.1 Regla

El **contexto de la lista** son siete valores: `nombre`, `estado`, `por_confirmar`, `en_conflicto`, `serie`,
`limite` y `desplazamiento`. `limite` viaja solo si **no** es el valor por defecto (50): omitirlo equivale a
llevarlo y evita ruido en el caso normal; `desplazamiento=0` también se omite. Viaja **siempre en la URL**
(GET) y en campos `hidden` de los formularios POST del asistente; **nunca** en servidor (sin sesión, sin
cookie: una recarga lo conserva, un reinicio no depende de nada). Es el mismo patrón que ya usa el asistente
para «volver sin perder la elección» (`web/asistente_carpetas.py:133,234`; `_asistente_eleccion.html:1-3`).

**Prohibido un parámetro de retorno** (`volver`, `next`, `return_to`, `url`, `redirect`): los enlaces se
reconstruyen con los valores del contexto, no con una URL arbitraria. Es la lección de `next` en el login
(`web/auth.py:31-45`). AC-13 lo comprueba.

### 6.2 Entrada de la lista al asistente (lleva el contexto)

| Enlace | Hoy | Nuevo |
|---|---|---|
| «Elegir la serie de esta carpeta» (`templates/carpetas.html:119`) | `asistente?clave=<clave>` | añade el contexto de §6.1 |
| «Preparar los archivos de esta carpeta para esta serie» (`templates/carpetas.html:116`) | `asistente/vinculacion?clave&series_id` | añade el contexto de §6.1 |

Los parámetros actuales (`clave`, `series_id`, `cursor`, `consulta`) se conservan **en el mismo orden**;
el contexto se añade detrás, para no romper las pruebas que cuentan enlaces por prefijo
(`tests/test_web_carpetas_pg.py:288-299`).

### 6.3 Enlaces del asistente que vuelven a la lista (conservan el contexto)

| Plantilla:línea | Texto del enlace | ¿Contexto? |
|---|---|---|
| `asistente_carpeta.html:7` | «← Volver a «Pendientes por carpeta»» | **Sí** |
| `_asistente_eleccion.html:15` | «Volver a las carpetas» | **Sí** |
| `asistente_vinculacion.html:5` | «← Volver a «Pendientes por carpeta»» | **Sí** (hoy solo `serie`) |
| `_vinculacion_resultado.html:34` | «Volver a las carpetas» (resultado normal) | **Sí** |
| `_vinculacion_resultado.html:89` | «Volver a las carpetas» (resultado normal) | **Sí** |
| `_vinculacion_resultado.html:37`, `:92` | «Elegir otra carpeta para esta serie» | **Sí** (contexto + `serie`) |
| `asistente_alta.html:10` | «Volver a «Pendientes por carpeta»» | **Sí** |
| `asistente_alta_resultado.html:8` | «← Volver a «Pendientes por carpeta»» | **Sí** |
| `asistente_resultado_guardado.html:14` | «Volver a las carpetas» | **No** (excepción del PO, §6.4) |
| `asistente_resultado_guardado.html:17` | «Elegir otra carpeta para esta serie» | **No** (solo `serie`, como hoy) |

*Salvedad:* las filas de `_vinculacion_resultado.html:34,37,89,92` conservan el contexto cuando la plantilla
se sirve en el flujo normal; cuando se sirve como fragmento del **resultado guardado** (`resultado=True`,
misma plantilla, §6.4) no lo conservan.

**Enlaces intermedios** (no vuelven a la lista pero forman la cadena): `_vinculacion_resultado.html:5`,
`_asistente_eleccion.html:14`, `asistente_alta.html:9`, `asistente_alta_resultado.html:30`,
`_alta_resultado.html:26-27`, `_alta_vista_previa.html:65`, `_asistente_resultados.html:38,45`,
`_asistente_locales.html:13`, `asistente_carpeta.html:56` y los formularios de
`asistente_carpeta.html:25,36`, `_vinculacion_revision.html:8,150`, `_asistente_macros.html:7`: **todos**
transportan el contexto (§6.1) para que la vuelta pueda reconstruirlo.

### 6.4 Excepción: el «resultado guardado» (decisión del PO)

El **resultado guardado** de una vinculación —`GET /ui/pendientes/carpetas/asistente/vinculacion/resultado?ref=…`
(`web/asistente_vinculacion.py:575-610`), plantilla `asistente_resultado_guardado.html` y su fragmento
`_vinculacion_resultado.html` con `resultado=True`— **no** propaga el contexto. Motivo: se puede reabrir
desde un enlace de 24 h sin la lista delante; el filtro no forma parte del resultado guardado y añadirlo
obligaría a meterlo en la referencia. Sus vueltas quedan como hoy: «Volver a las carpetas» sin parámetros
(`:14`) y «Elegir otra carpeta para esta serie» solo con `serie` (`:17`). Es la única excepción a §6.3 y está
fijada por el PO el 2026-11-01.

### 6.5 Paginación y desplazamiento

- Enlaces «Anteriores»/«Siguientes»/«Primera»/«Última» y la salida de página fuera de rango conservan el
  contexto (§6.1) y cambian solo `desplazamiento`.
- **Desplazamiento fuera de rango tras filtrar:** 200 con «Esta página ya no existe» y los mismos enlaces de
  salida, ahora **con filtro**; «Ir a la primera página» lleva a la primera del conjunto filtrado y «Ir a la
  última página válida» a la última del filtrado. No se pinta «Carpetas 99–99» ni una lista vacía normal.
- **Cambiar el filtro** (enviar el formulario) o **quitar el filtro/serie** vuelve a la **página 1**: no
  llevan `desplazamiento` (§3.3). La vuelta desde el asistente **no** cambia el filtro: recupera la misma
  página.

---

## 7. Privacidad

1. El valor de `nombre` (y el resto del filtro) aparece en la URL: es estado de la vista, no un dato que se
   registre. El **registro de acceso** de uvicorn omite la query completa desde #361 (`?…`), sea cual sea el
   parámetro (`utils/log_acceso.py:1-11,32-56`; instalado en `main.py:290-291`): `nombre` no añade nada.
2. **Los registros de la aplicación no llevan el valor**: el único aviso de la ruta es
   `pendientes.carpetas_fallo` con `error=type(exc).__name__` (`web/pendientes.py:318`), sin query ni texto; el
   código nuevo no añade ningún `logger` con `nombre`/`estado`. Un fallo de lectura no filtra el filtro al log.
3. La respuesta mantiene `Cache-Control: no-store` (`web/pendientes.py:328`), como hoy: una página
   personalizada no se cachea.
4. **Fuera de alcance:** el historial del navegador (la URL se ve y se guarda en el cliente) y los proxies
   inversos del operador. La spec **no** promete borrar la URL del historial.
5. Prueba: centinela en `nombre` y en un valor inválido de `estado`; ni el log de acceso ni los registros
   capturados de la app contienen el centinela (AC-22), también en el camino de error 503.

---

## 8. Requisitos no funcionales

| ID | NFR | Umbral / regla | Verificación |
|---|---|---|---|
| NFR-01 | **Una pasada, sin consultas nuevas** | El filtro no añade sentencias: **2 consultas** hoy (`_leer` + `_series`; `tests/test_revision_carpetas_pg.py:594-640`) y **2** con filtro, independiente del número de carpetas | Contador de sentencias con y sin filtro; AC-19 |
| NFR-02 | **Sin cargar más que hoy** | Se lee exactamente lo mismo que hoy (una lectura A∪B); el filtro se aplica en memoria sobre los grupos ya construidos; no se materializa una segunda lectura ni se recorre la BD por carpeta | Mismo contador + revisión del servicio; AC-19/AC-20 |
| NFR-03 | **Sin filtro, nada cambia** | Respuesta del servicio idéntica (totales, página, grupos y orden); API JSON sin claves nuevas; HTML con los mismos datos, recuentos, textos, paginación y tarjetas. Únicas diferencias: el formulario de filtro y los enlaces de vuelta del asistente, que conservan página/serie cuando existen (MEJORAR 1 de la ficha, dentro de la propagación; sin contexto no añaden parámetros). | Comparación de respuesta con y sin filtro; pruebas existentes; AC-21 |
| NFR-04 | **Coste en la Pi (512 MB)** | Sin proceso, hilo, dependencia, migración ni configuración nuevos; filtro O(n) en memoria sobre ≤ miles de grupos; el p95 local de `carpetas()` no empeora respecto a la medición existente (≤ 2000 ms ASGI, `tests/test_revision_carpetas_pg.py:594-640`) | Medición local con filtro y sin él; AC-19 |
| NFR-05 | **Latencia de la página** | No se añade I/O ni consulta; el HTML no crece con N (solo el bloque de filtro); la medición local de la vista (≤ 2000/1000 ms ASGI, `tests/test_web_carpetas_pg.py:405-445`) se mantiene con filtro | Misma prueba con `nombre`/`estado`; AC-19 |
| NFR-06 | **Solo lectura y sin JS** | Un `<form method="get">` y un `<button type="submit">`; **cero** `hx-*`, `<script>`, `onclick`/`onerror`, formularios POST o acciones que escriban; la pantalla no toca disco ni BD (lo que ya probaba `test_cero_escrituras_y_cero_disco`) | AC-21 + prueba de no-acciones actualizada (§10.2) |
| NFR-07 | **Presupuesto de texto (U21)** | La frase de entrada ≤ 20 palabras; ≤ 50 palabras visibles **antes de la primera acción**, que ahora es el formulario de filtro; el recuento con filtro ≤ 20 palabras | Pruebas U21 adaptadas (§10.2) |
| NFR-08 | **Sin dependencias ni esquema** | Solo stdlib + lo existente; `alembic/`, `pyproject.toml` y `config.py` sin cambios | `git diff --stat` |
| NFR-09 | **Determinismo** | Mismo filtro + misma base ⇒ misma lista, mismo orden y mismos N/M | Dos llamadas consecutivas; AC-19 |
| NFR-10 | **Accesibilidad** | Etiquetas visibles asociadas (`for`/`id`), leyenda de grupo de marcas, `type="search"` en el nombre; foco y envío con teclado; sin controles que dependan del ratón | Inspección del HTML + navegador real (fuera de CI) |

---

## 9. Criterios de aceptación (Given/When/Then)

> Un AC por comportamiento. `Verificación` indica cómo se demuestra: **pytest** (Postgres real o unitario),
> **inspección** (HTML/texto) o **navegador** (manual, NO RUN en CI). Los textos entre comillas son exactos.

### Criterio 1 — nombre: «contiene», sin mayúsculas ni tildes; recuentos filtrados y «cuántas coinciden»

**AC-01 — coincidencia parcial y sin mayúsculas**
Given una biblioteca con «Comics/Astérix el Galo» y «Comics/Batman (2019)»,
When se pide `?nombre=ast` y, en otra petición, `?nombre=ASTÉRIX`,
Then solo sale «Comics/Astérix el Galo» en ambos casos; «Comics/Batman (2019)» no sale; el campo muestra el
texto enviado (escapado).
*Verificación: pytest.*

**AC-02 — acentos y tildes**
Given «Comics/Astérix», «Comics/Año Cero» y «Comics/Doña Urraca»,
When se pide `nombre=asterix`, `nombre=ano` y `nombre=dona`,
Then cada uno encuentra su carpeta; `nombre=AÑO` también encuentra «Año Cero»; ninguna otra carpeta aparece
de más.
*Verificación: pytest (fija el pliegue de §13.1).*

**AC-03 — recuentos del conjunto filtrado y «N de M»**
Given 120 carpetas útiles y un filtro que coincide con 7, con `limite=50`,
When se abre la página,
Then el HTML dice «Carpetas 1–7 de 7.» y «7 de 120 carpetas coinciden con el filtro.»; la paginación no ofrece
«Siguiente»; el servicio informa `coinciden=7` y `totales.carpetas_utiles=120`.
*Verificación: pytest.*

**AC-04 — el nombre filtra sobre el título visible de la carpeta**
Given «Comics/Batman (2019)»,
When se pide `nombre=batman (2019)` o `nombre=comics batman`,
Then la carpeta sale (el filtro usa el texto visible de la tarjeta, `Grupo.clave`, con la tradición y los
ascendentes como se muestran); no se filtra por un campo oculto distinto.
*Verificación: pytest + inspección.*

### Criterio 2 — estado y combinaciones

**AC-05 — valores del selector excluyente**
Given grupos en los tres estados (sin serie, con serie sugerida, mixto),
When se pide `estado=sin_serie`, `estado=serie_sugerida` y `estado=mixto` en peticiones separadas,
Then cada uno devuelve **solo** los grupos de ese estado; `estado=todas`, `estado=` y sin parámetro devuelven
todos.
*Verificación: pytest.*

**AC-06 — nombre y estado se combinan con Y**
Given «Comics/Batman (2019)» con serie sugerida y «Comics/Batman Sin Serie» sin serie,
When se pide `nombre=batman&estado=sin_serie`,
Then solo sale «Comics/Batman Sin Serie»; los recuentos se refieren a esa combinación.
*Verificación: pytest.*

**AC-07 — modelo de estados: `mixto` no es «en conflicto»**
Given cuatro grupos: (a) mixto sin conflicto, (b) mixto con conflicto, (c) sin serie con conflicto, (d) sin
serie sin conflicto,
When se pide `estado=mixto`, `en_conflicto=1`, `estado=mixto&en_conflicto=1` y `por_confirmar=1` en
peticiones separadas,
Then: `estado=mixto` devuelve (a) y (b); `en_conflicto=1` devuelve (b) y (c); `estado=mixto&en_conflicto=1`
devuelve solo (b); `por_confirmar=1` devuelve (a) y (b) (nunca (c)/(d)); (c) no sale con `estado=mixto`.
*Verificación: pytest.*

**AC-08 — dos marcas independientes, combinadas con Y**
Given grupos con `por_confirmar` y `en_conflicto` en las cuatro combinaciones posibles,
When se piden `por_confirmar=1`, `en_conflicto=1` y los dos a la vez, y una combinación contradictoria
`estado=sin_serie&por_confirmar=1`,
Then: cada marca filtra por su booleano; las dos a la vez exigen **ambas** (intersección); la combinación
contradictoria devuelve 200 con el estado vacío de filtro (§5.3), nunca error.
*Verificación: pytest.*

### Criterio 3 — sin coincidencias

**AC-09 — estado vacío de filtro, no una lista vacía normal**
Given carpetas pendientes y un filtro `nombre=zzz-inexistente`,
When se abre la página,
Then 200; título «Ninguna carpeta coincide con «zzz-inexistente».»; cuerpo «Prueba a cambiar el filtro o a
quitarlo.»; enlace «Quitar el filtro»; **no** aparece «Nada pendiente» ni «No hay carpetas con contexto».
*Verificación: pytest + inspección.*

**AC-10 — el vacío de filtro manda sobre el vacío de serie**
Given una serie fijada (`serie=<uuid>`) y un filtro sin coincidencias,
When se abre la página,
Then 200 con el estado vacío de filtro (no el bloque `bloque_vacio_serie`, que ofrece registrar la
biblioteca); «Quitar el filtro» conserva la serie y quita solo el filtro.
*Verificación: pytest.*

### Criterio 4 — propagación, serie fijada y valores no válidos

**AC-11 — la paginación conserva el filtro**
Given 120 carpetas, `limite=10` y un filtro que coincide con 25,
When se abre la página 2,
Then dice «Carpetas 11–20 de 25.»; los enlaces «Anteriores» y «Siguientes» llevan `nombre`, `estado`, las
marcas, `serie` (si la hay) y `limite`, y cambian solo `desplazamiento`; «Siguiente» de la página 2 apunta a
`desplazamiento=20`.
*Verificación: pytest.*

**AC-12 — volver desde el asistente conserva filtro, página y serie**
Given la lista filtrada en la página 2 con una serie fijada,
When se entra al asistente por «Elegir la serie de esta carpeta» o «Preparar los archivos…» y se vuelve con
«Volver a las carpetas» (o «Elegir otra carpeta para esta serie») desde cualquier paso del asistente,
Then la URL de vuelta contiene los cuatro filtros, `serie`, `desplazamiento` y `limite` si no es 50; se ve la
misma página 2 filtrada y la misma serie; no se pierde nada de lo elegido.
*Verificación: pytest (recorrido de enlaces de §6.2/§6.3).*

**AC-13 — excepción del resultado guardado y prohibición de parámetro de retorno**
Given un resultado guardado abierto con `ref=…` (página completa o fragmento `resultado=True`),
When se pulsa «Volver a las carpetas» o «Elegir otra carpeta para esta serie»,
Then las URLs **no** llevan filtros ni página (la segunda conserva solo `serie`, como hoy); además, ningún
enlace de la lista o del asistente contiene `volver`, `next`, `return_to`, `url`, `redirect` ni una URL
absoluta como destino.
*Verificación: pytest (inspección de `href`).*

**AC-14 — serie fijada y filtro se respetan al quitar uno**
Given la lista con `serie=<uuid>` y `nombre=batman`,
When se pulsa «Quitar la serie»,
Then la lista sigue filtrada por nombre, sin serie y en página 1; y al pulsar «Quitar el filtro» la lista
sigue con la serie fijada y vuelve a página 1.
*Verificación: pytest.*

**AC-15 — valores inválidos: 200 + aviso, nunca 422/500**
Given peticiones con `estado=inventado`, con `estado=SIN_SERIE` (mayúsculas), con `por_confirmar=2` y con
`en_conflicto=abc`,
When se abren,
Then todas responden 200; el estado inválido se descarta y se muestra el aviso «El estado de la carpeta no es
válido; se muestran todos los estados.»; las marcas con valor distinto de `1` quedan inactivas sin aviso; si
además hay `nombre`, el nombre se sigue aplicando; nunca 422 ni 500.
*Verificación: pytest.*

**AC-16 — texto del nombre: controles, longitud y escape**
Given `nombre` con caracteres de control, `nombre` de 250 caracteres y `nombre=<script>alert(1)</script>`,
When se abre la página,
Then los controles se quitan con su aviso; a 200 caracteres se recorta con su aviso; el valor y el título del
vacío se pintan escapados (no se ejecuta nada, no se rompe el HTML); no hay 500.
*Verificación: pytest (escape) + inspección.*

**AC-17 — desplazamiento fuera de rango tras filtrar**
Given un filtro que coincide con 5 carpetas, `limite=2` y `desplazamiento=99`,
When se abre la página,
Then 200 con «Esta página ya no existe»; «Ir a la primera página» conserva el filtro sin `desplazamiento`;
«Ir a la última página válida» conserva el filtro con `desplazamiento=4`; no se pinta «Carpetas 99–99» ni una
lista vacía normal.
*Verificación: pytest.*

**AC-18 — cambiar el filtro vuelve a la página 1**
Given la página 2 filtrada y paginada,
When se envía el formulario con otro filtro (o se pulsa «Quitar el filtro» / «Quitar la serie»),
Then la URL resultante no lleva `desplazamiento`; se ve la página 1 del nuevo conjunto.
*Verificación: pytest (HTML del formulario y enlaces).*

### Criterio 5 — una sola pasada, sin consultas que crezcan con las carpetas

**AC-19 — mismas consultas con y sin filtro, y N/M deterministas**
Given la base de referencia con 1.322 A + 17 B y 108 carpetas útiles,
When se llaman `carpetas(limite=50, solo_utiles=True)` sin filtro y con `nombre`, `estado` y marcas,
Then las dos llamadas hacen **2** consultas (el contador no crece con el filtro ni con el número de carpetas);
la segunda no empeora el p95 local de la medición existente (≤ 2000 ms ASGI); dos llamadas con el mismo
filtro dan el mismo N, M, lista y orden.
*Verificación: pytest (contador de sentencias + medición local).*

**AC-20 — sin cargar más que hoy**
Given el mismo banco,
When se ejecuta con filtro,
Then no se lee de la base ninguna fila ni columna adicional (misma lectura A∪B); no hay una segunda lectura de
grupos ni una consulta por carpeta; el filtro se aplica sobre los grupos ya construidos.
*Verificación: pytest (contador y revisión del servicio).*

### Criterio 6 — sin filtro, nada cambia

**AC-21 — la pantalla y la API sin filtro son las de hoy (salvo el formulario y la vuelta del asistente)**
Given `GET /ui/pendientes/carpetas` y `GET /api/revision/carpetas` sin parámetros de filtro,
When se comparan con `main` `f6964ae`,
Then el servicio devuelve los mismos `totales`, `pagina`, `grupos` y orden; el JSON de la API no gana claves
(el bloque de filtro no aparece); la pantalla conserva los mismos datos, recuentos, textos, paginación y
tarjetas; las únicas diferencias son (a) el formulario de filtro y su botón (que no escribe, es GET, no usa
HTMX ni JS) y (b) los enlaces de vuelta del asistente, que desde esta historia conservan página y serie cuando
existen (MEJORAR 1 de la ficha, dentro de la propagación decidida por el PO); sin contexto (página 1, sin
serie, sin filtro, `limite` por defecto) no añaden ningún parámetro y son idénticos a hoy; las pruebas
existentes siguen pasando con los ajustes de §10.2.
*Verificación: pytest (comparación servicio/JSON y pruebas existentes) + inspección.*

### Criterio 7 — privacidad

**AC-22 — el valor del filtro no sale en los registros**
Given una petición a `/ui/pendientes/carpetas?nombre=CENTINELA-PRIV-9Q&estado=inventado` y, aparte, una
petición que fuerza el camino de error 503 con el mismo centinela,
When se capturan el registro de acceso de uvicorn (`uvicorn.access`) y los registros de la aplicación,
Then ni la query ni el valor «CENTINELA-PRIV-9Q» aparecen en ninguno de los dos (el acceso muestra la ruta
con `?…`); el aviso de invalidación no repite el valor; el resto de la petición no añade `logger` con el
texto.
*Verificación: pytest (captura de logs).*

### Pliegue del nombre (casos fijados)

**AC-23 — tabla de pliegue (ß, ø, æ, œ, đ, ł, ð, þ, ħ, ı, ½)**
Given carpetas sembradas con los nombres de la tabla, todas con la tradición `Q` (para que el prefijo no
contenga la letra buscada),
When se piden los `nombre` de la columna «consulta»,
Then el resultado es exactamente el de la columna «¿coincide?»:

| # | Carpeta (`clave`) | Consulta | ¿Coincide? | Por qué (pliegue de `normalize_title`) |
|---|---|---|---|---|
| 1 | `Q/Straße` | `ß` | **sí** | ß se conserva (no se pliega a «ss») |
| 2 | `Q/Straße` | `ss` | **no** | `normalize_title` usa `lower()`, no `casefold` |
| 3 | `Q/Strasse` | `ss` | **sí** | «ss» se conserva |
| 4 | `Q/Søren` | `ø` | **sí** | ø se conserva |
| 5 | `Q/Søren` | `o` | **no** | ø ≠ o |
| 6 | `Q/Æon` | `æ` | **sí** | æ se conserva |
| 7 | `Q/Æon` | `ae` | **no** | æ ≠ ae |
| 8 | `Q/Œuvre` | `œ` | **sí** | œ se conserva |
| 9 | `Q/Œuvre` | `oe` | **no** | œ ≠ oe |
| 10 | `Q/Đorđe` | `đ` | **sí** | đ se conserva |
| 11 | `Q/Đorđe` | `d` | **no** | đ ≠ d |
| 12 | `Q/Łódź` | `ł` | **sí** | ł se conserva; «ó» pliega a «o» |
| 13 | `Q/Łódź` | `l` | **no** | ł ≠ l |
| 14 | `Q/Guðrún` | `ð` | **sí** | ð se conserva; «ú» pliega a «u» |
| 15 | `Q/Guðrún` | `d` | **no** | ð ≠ d |
| 16 | `Q/Þór` | `þ` | **sí** | þ se conserva; «ó» pliega a «o» |
| 17 | `Q/Þór` | `th` | **no** | þ ≠ th |
| 18 | `Q/Ħal` | `ħ` | **sí** | ħ se conserva |
| 19 | `Q/Ħal` | `h` | **no** | ħ ≠ h |
| 20 | `Q/Kırmızı` | `ı` | **sí** | ı (i sin punto) se conserva |
| 21 | `Q/Kırmızı` | `i` | **no** | ı ≠ i |
| 22 | `Q/Istanbul` | `I` | **sí** | «I» minúscula → «i» |
| 23 | `Q/½` | `½` | **sí** | NFKD separa la fracción; queda «1 2» |
| 24 | `Q/½` | `1/2` | **sí** | «1/2» y «½» pliegan igual a «1 2» |
| 25 | `Q/½` | `12` | **no** | «1 2» ≠ «12» |

*Verificación: pytest parametrizado (25 casos) contra el servicio con Postgres real.*

**AC-24 — artículos, puntuación y texto sin palabras**
Given «Comics/Los Vengadores», «Comics/El Sandman» y «Comics/S.H.I.E.L.D.»,
When se pide `nombre=vengadores`, `nombre=sandman`, `nombre=shield`, `nombre=el`, `nombre=los`,
Then «vengadores», «sandman» y «shield» encuentran su carpeta (la puntuación se quita: «S.H.I.E.L.D.» →
«shield»); «el» y «los» normalizan a vacío, **no** restringen el nombre y muestran el aviso «El texto no
contiene palabras que buscar; no se aplica el filtro de nombre.»; no hay 422/500.
*Verificación: pytest.*

---

## 10. Plan de pruebas e impacto en las pruebas existentes

### 10.1 Pruebas nuevas

| Dónde | Qué fija |
|---|---|
| `tests/test_web_carpetas_pg.py` | AC-01…AC-18, AC-21 y AC-24 (HTML real, Postgres): filtros, recuentos N/M, vacío, paginación, propagación, inválidos, escape, fuera de rango |
| `tests/test_revision_carpetas_pg.py` | AC-19/AC-20: 2 consultas con y sin filtro, determinismo y p95 local; filtro en el servicio |
| `tests/test_revision_carpetas_pg.py` (parametrizado) | AC-23: 25 filas de pliegue |
| `tests/test_web_carpetas_pg.py` (captura de logs) | AC-22: centinela ausente del log de acceso y de la app; reutiliza el patrón de `tests/test_log_acceso.py` |
| `tests/test_web_carpetas_pg.py` (herencia de #283) | AC-16: avisos de controles y longitud con los textos exactos de `web/library.py:141-146` |

### 10.2 Pruebas existentes que hay que ajustar (mismo PR)

1. `tests/test_web_carpetas_pg.py::test_no_hay_ninguna_accion_ni_javascript_nuevo` (línea 288): hoy prohíbe
   **todo** `<form>`, `<button>` y `type="submit"`. La regla se afina: se permite **un** `<form method="get">`
   sin `hx-*` y **un** `<button type="submit">`; se siguen prohibiendo `<script>`, `hx-*`, `onclick`,
   `onerror=` y cualquier formulario que no sea GET. El «sin acciones» pasa a ser «sin acciones que
   escriban». Los enlaces por tarjeta conservan su prefijo (`href="…/asistente?clave=`), así que su recuento
   no cambia si el contexto se añade detrás (§6.2).
2. `tests/test_web_carpetas_pg.py::test_entrada_y_primera_accion_caben_en_50_palabras` y
   `test_la_cifra_de_46_es_reproducible…` (líneas 513-563): la primera acción ya no es la tarjeta sino el
   formulario de filtro. Se corta el recuento en el formulario y se conserva el umbral; la cifra exacta de 46
   se recalcula o se sustituye por el umbral (la composición de la cabecera no crece).
3. Los dobles de `RevisionCarpetas.carpetas` con firma fija (`tests/test_web_carpetas_pg.py:282-283,550-551`)
   ganan `**kwargs` o los parámetros nuevos; el servicio mantiene los nuevos opcionales para no romper llamadas
   existentes (`api/revision.py:103`, `web/pendientes.py:102`).
4. `test_el_subtitulo_no_pasa_de_20_palabras` (línea 567) se mantiene: el subtítulo sin filtro sigue siendo la
   frase de 18 palabras; con filtro se prueba además que el recuento «N de M» ≤ 20.
5. Las pruebas de paginación que comparan URLs exactas (`test_paginas_con_enlaces_correctos`,
   `test_una_pagina_que_ya_no_existe_tiene_salida`, `test_120_carpetas…`, `test_pagina_fuera_de_rango…`) no
   cambian: sin filtro la URL canónica es idéntica (§3.3).

### 10.3 Medición y navegador

- La medición local de la vista con filtro se añade a la existente (`tests/test_web_carpetas_pg.py:405-445`):
  mismas cotas (≤ 2000 ms primera, ≤ 1000 ms cambio), contador de sentencias ≤ 3 y sin accesos a disco.
- **Navegador real:** fuera de CI; comprobar teclado, foco, que el envío produce la URL canónica de §3.3 y que
  «Atrás» del navegador conserva el filtro (la URL lo lleva). Se marca **NOT RUN** si no se ejecuta. La
  verificación de la Pi del filtro en Python queda fuera de esta historia (§2.3).

---

## 11. Riesgos

| ID | Riesgo | Impacto | Mitigación / nota |
|---|---|---|---|
| R-01 | La propagación toca ~8 rutas y ~10 plantillas del asistente; es la mayor parte del esfuerzo de una S | Retraso de la estimación 4–6 h | Un único helper de URLs en el router (patrón `_qs` de `web/library.py:184-212`) y una prueba por enlace de §6.3; el contexto viaja con los mismos nombres, sin inventar un parámetro de retorno |
| R-02 | El criterio 6 del issue dice «el HTML … no cambia» y añadir el formulario lo cambia | Interpretación | Ratificado: sin filtro no cambian datos, recuentos, orden, paginación, tarjetas ni API; las únicas diferencias son el formulario y la vuelta del asistente, declaradas en AC-21/§13.3. Si el PO lo quiere literal, no puede haber formulario: decisión suya |
| R-03 | `normalize_title` recorta artículos iniciales: un texto que solo es artículo normaliza a vacío | «el»/«the» no restringen y avisan | Conducta fijada y probada (AC-24); si el PO quiere «el» buscable, exige cambiar la normalización compartida, fuera de esta historia (§13.1) |
| R-04 | El pliegue elegido no une ß con ss ni ø con o: una persona que busque «strasse» no encuentra «Straße» | Falsos negativos «razonables» para el PO hispanohablante; el caso alemán/nórdico es minoritario | Fijado por decisión «normalización de títulos existente»; tabla AC-23 y nota §13.1. Reabrir exigiría `casefold` compartido y otra prueba de paridad |
| R-05 | El filtro vive en la URL: queda en el historial del navegador | Privacidad local | Fuera de alcance declarado (§7.4); los logs del servidor sí están cubiertos (AC-22) |
| R-06 | El estado vacío compite con «Nada pendiente» y con el bloque de serie sin carpetas | Mensaje equivocado | Prioridad fijada (§5.3, AC-09/AC-10) y pruebas de las tres combinaciones |
| R-07 | M y N se confunden (recuento global vs filtrado) | Recuento que miente | Contrato de §3.4 y AC-03/AC-19; `totales` conserva su significado de M |
| R-08 | Un valor de filtro inválido o raro acaba en 422/500 | Fricción y pérdida de la lista | Validación en el router y avisos; AC-15/AC-16; `serie` ya tenía el patrón (`web/pendientes.py:260-275`) |
| R-09 | El formulario rompe la prueba de «sin acciones» y las de U21 | PR en rojo por pruebas desactualizadas | §10.2 lo deja previsto y acotado; el cambio de pruebas va en el mismo PR |
| R-10 | La paginación y el asistente se desincronizan del filtro (unas URLs sí y otras no) | Filtro que «salta» al navegar | URLs construidas en un solo sitio y AC-11/AC-12/AC-13 por enlace |

---

## 12. Trazabilidad: criterio del issue → FR → AC → prueba

| Criterio del issue #397 | FR | AC | Verificación |
|---|---|---|---|
| 1. Nombre «contiene», sin mayúsculas ni tildes; recuentos filtrados y cuántas coinciden | FR-01, FR-06 | AC-01, AC-02, AC-03, AC-04 | pytest |
| 2. Estado elegido; nombre y estado combinables | FR-02, FR-03, FR-04 | AC-05, AC-06, AC-07, AC-08 | pytest |
| 3. Sin coincidencias: se dice en llano y se ofrece quitar el filtro | FR-07 | AC-09, AC-10 | pytest + inspección |
| 4. Paginar, volver del asistente y la serie fijada conservan el filtro; inválido = 200 + aviso | FR-05, FR-08, FR-09, FR-13 | AC-11…AC-18 | pytest |
| 5. Una pasada; consultas que no crecen con las carpetas y orden estable | FR-10, FR-14 | AC-19, AC-20 | pytest (contador + medición) |
| 6. Sin filtro, HTML y comportamiento actuales no cambian | FR-11 | AC-21 | pytest (comparación + existentes) |
| 7. El texto del filtro no sale a los registros | FR-12 | AC-22 | pytest (logs) |
| Decisiones del PO 2026-11-01 (modelo de estados, «Volver» sin retorno, propagación, resultado guardado, pliegue) | FR-02…FR-09 | AC-07, AC-12, AC-13, AC-23, AC-24 | pytest + inspección |

### Requisitos funcionales (EARS)

| ID | Patrón | Requisito | Origen | Estado | AC |
|---|---|---|---|---|---|
| FR-01 | Ubicuo | El sistema mostrará las carpetas cuyo **título visible normalizado** contenga el texto normalizado de `nombre`, sin distinguir mayúsculas ni tildes. | Issue c.1; PO 2026-10-31 | pendiente | AC-01, AC-02, AC-04 |
| FR-02 | Ubicuo | El sistema filtrará por un **estado excluyente**: todas, sin serie, con serie sugerida o mixto. | Issue c.2; PO 2026-11-01 | pendiente | AC-05, AC-07 |
| FR-03 | Ubicuo | El sistema ofrecerá dos **marcas independientes** («Por confirmar», «En conflicto»), combinables con Y entre sí y con el estado. | PO 2026-11-01 | pendiente | AC-07, AC-08 |
| FR-04 | Ubicuo | El sistema combinará con **Y** todos los criterios activos (nombre, estado, marcas) y con `serie`. | Issue contrato | pendiente | AC-06, AC-14 |
| FR-05 | Por evento | CUANDO se envíe el formulario de filtro, el sistema navegará a la lista filtrada **en la página 1** (sin `desplazamiento`). | Issue c.4; ficha IGUALAR 4 | pendiente | AC-18 |
| FR-06 | Estado | MIENTRAS haya filtro activo, la lista y la paginación se referirán al conjunto filtrado y la pantalla dirá «N de M» carpetas coinciden. | Issue c.1/contrato | pendiente | AC-03, AC-11 |
| FR-07 | No deseado | SI ningún grupo pasa el filtro, ENTONCES el sistema mostrará el estado vacío de filtro con «Quitar el filtro», no una lista vacía normal. | Issue c.3 | pendiente | AC-09, AC-10 |
| FR-08 | No deseado | SI un parámetro de filtro no es válido, ENTONCES el sistema responderá 200 con aviso y descartará solo ese valor; nunca 422/500. | Issue c.4 | pendiente | AC-15, AC-16 |
| FR-09 | Ubicuo | El sistema conservará el contexto de la lista (filtros, serie, límite y página) al entrar y volver del asistente, salvo en el resultado guardado, y **sin** parámetro de retorno. | Issue c.4; PO 2026-11-01 | pendiente | AC-12, AC-13, AC-14 |
| FR-10 | Ubicuo | El sistema aplicará el filtro **en memoria** sobre los grupos ya construidos, sin consultas adicionales ni lecturas adicionales. | PO 2026-11-01 (revisa el «en SQL» del issue) | pendiente | AC-19, AC-20 |
| FR-11 | Ubicuo | Sin filtro, el sistema conservará el servicio, la API, los datos, los recuentos y la paginación actuales; las únicas diferencias visibles serán el formulario de filtro y la vuelta del asistente de AC-21. | Issue c.6 | pendiente | AC-21 |
| FR-12 | Ubicuo | El sistema no incluirá el valor del filtro en el registro de acceso ni en los de la aplicación. | Issue c.7; CLAUDE.md §5.4 | pendiente | AC-22 |
| FR-13 | Estado | SI el desplazamiento ya no existe tras filtrar, ENTONCES el sistema mostrará la salida de «Esta página ya no existe» con enlaces filtrados a primera/última. | Issue c.4; ficha IGUALAR 4 | pendiente | AC-17 |
| FR-14 | Ubicuo | El sistema mantendrá el orden relativo actual de los grupos (conflicto, más registros, clave) al filtrar. | Issue contrato | pendiente | AC-19 |

---

## 13. Precisión sobre la ficha y el issue (conciliación)

Lo que sigue **no contradice** las decisiones del PO: las aplica. Se anota porque la ficha o el issue lo
dejaban implícito.

### 13.1 Normalización: se reutiliza `normalize_title` tal cual (y sus consecuencias)

- El issue dice «con la normalización de títulos existente» y la ficha «en Python sobre la `clave`». La
  función existente es `core/matcher.normalize_title` (`core/matcher.py:79-104`): NFKD → quita diacríticos →
  quita abreviaturas con puntos → recorta artículo inicial/posfinal → quita puntuación → colapsa espacios →
  `lower()`. **No** usa `casefold`.
- **Artículos:** `normalize_title` recorta artículos *cuando encabezan la cadena* (`_ARTICLE_LEADING`,
  `core/matcher.py:67,71`). En el caso normal la clave empieza por la tradición (`core/carpetas.py:130`), así
  que ese recorte **no** actúa sobre el nombre de la carpeta; en una carpeta en la raíz sí podría. En el
  **texto buscado** sí actúa: un `nombre` que sea solo artículo («el», «los», «the») normaliza a vacío y se
  trata con aviso (AC-24). No se inventa una normalización paralela: se usa la misma.
- **Pliegue fijado:** ß/ø/æ/œ/đ/ł/ð/þ/ħ/ı se conservan (no equivalen a ss/o/ae/oe/d/l/d/th/h/i) y ½ → «1 2»
  (NFKD). Es el pliegue de Python, distinto del de PostgreSQL (ficha §IGUALAR 4); por eso el prefiltro SQL
  queda descartado y la prueba AC-23 fija el contrato.
- **Por qué no `texto_incluye` (`core/carpetas.py:141-149`):** hace `casefold` y luego descarta todo lo que no
  sea `[0-9a-z]`, así que «ø», «æ»… quedan fuera y la comparación es por palabras enteras. No sirve para
  «contiene» sin tildes sobre texto libre; se deja como está para las señales que ya lo usan.

### 13.2 El criterio 5 («se filtra en SQL») queda superado por la decisión del 2026-11-01

El issue (2026-10-31) decía «Se filtra en SQL». La ficha, actualizada el **2026-11-01** con las decisiones del
PO, registra «filtro del nombre en Python sin prefiltro SQL» y descarta el prefiltro («mismos totales, mismo
coste»). Esta spec ratifica la parte **verificable** del criterio 5: **el número de consultas no crece con las
carpetas** (AC-19) y no se carga más que hoy (AC-20). Si el PO quisiera volver al SQL, hace falta un benchmark
nuevo y la prueba de paridad de pliegue.

### 13.3 El criterio 6 («el HTML … no cambia») y el formulario

Añadir un formulario cambia el HTML por definición. Se ratifica así: sin filtro **no cambian** los datos,
recuentos, orden, paginación, textos existentes, tarjetas ni la API; las únicas diferencias son el bloque de
filtro y su botón (AC-21) y los **enlaces de vuelta del asistente**, que dejan de perder página y serie cuando
existen (MEJORAR 1 de la ficha, «Volver desde el asistente conservando filtro, página y serie»; es parte de la
propagación decidida por el PO). Sin contexto (página 1, sin serie, sin filtro, `limite` por defecto) esos
enlaces no añaden parámetros y son idénticos a hoy. También se afina «la pantalla no tiene acciones»: tiene
**un formulario GET de solo lectura**; ninguna acción escribe (obligatorio para no romper la promesa de la
pantalla, §10.2).

### 13.4 Los cuatro «estados» del issue son un selector de tres + dos marcas

El issue enumera «sin serie, con serie sugerida, por confirmar, en conflicto» como estados. La decisión del
PO del 2026-11-01 (modelo c) los separa: el selector excluyente tiene tres estados (más «todas») y
«Por confirmar»/«En conflicto» son **marcas** independientes. `por_confirmar` es, por construcción, «Con
serie sugerida» **o** «Mezcla» (`revision_carpetas.py:549`) y `en_conflicto` es ortogonal
(`revision_carpetas.py:532`). `mixto` ≠ `en_conflicto` (§4, AC-07).

### 13.5 El mapa de enlaces del asistente de la ficha era parcial

La ficha cita `_vinculacion_resultado.html:34,37,89,92`, pero la vuelta a la lista también está en
`asistente_carpeta.html:7`, `asistente_vinculacion.html:5`, `_asistente_eleccion.html:15`,
`asistente_alta.html:10`, `asistente_alta_resultado.html:8` y, como **excepción**, en
`asistente_resultado_guardado.html:14,17`. §6.3 completa el mapa; no es contradicción, era una lista no
exhaustiva.

### 13.6 Líneas de código

La ficha cita `web/pendientes.py:293-300` y `revision_carpetas.py:300-356,475-495`; hoy la ruta va de 292 a
329 y `_leer` de 475 a 506. El código es el mismo (no hubo commits en esos ficheros desde `9d7fedf`), solo
cambia el número de línea; esta spec usa los actuales.

### 13.7 La ficha dice «una sola consulta»; el servicio hace **dos**

La ficha (fila «Construir sobre lo propio») dice «Una sola consulta». El código vigente hace **dos**:
`_leer` (A∪B) y `_series` (solo si hay candidatas), y la medición existente lo fija en
`tests/test_revision_carpetas_pg.py:594-640` (`assert consultas == 2`). No es una contradicción de fondo: la
ficha se refería a la **lectura de pendientes** (una), no al total del servicio; el punto que importa se
mantiene: **el filtro no añade ninguna consulta** (AC-19). Esta spec usa la cifra real (2) en NFR-01/AC-19.

---

## 14. Auto-revisión

- [x] **Los 7 criterios del issue** están ratificados uno a uno y trazados (§12); el único que se acota es el
      5 («en SQL» → «sin consultas nuevas»), por la decisión posterior del PO, declarado en §13.2.
- [x] **Los números y estados salen del código**: `estado`/marcas (`revision_carpetas.py:45,518-550`), clave
      (`core/carpetas.py:130`), paginación y totales (`web/pendientes.py:206-257`), asistente (§6.3), logs
      (`utils/log_acceso.py`, `main.py:290-291`).
- [x] **Textos exactos** para etiqueta, placeholder, opciones, marcas, botón, quitar, avisos, vacío, «N de M»
      y banner de serie (§5); se prueban tal cual.
- [x] **Nada de requisitos no verificables**: cada AC tiene pytest, inspección o navegador; «N de M», «200 con
      aviso», «2 consultas», «sin claves nuevas» son comprobables.
- [x] **Privacidad**: el valor no va a logs; se reutiliza el filtro #361 y se prueba con centinela.
- [x] **Sin red, sin escritura, sin JS nuevo, sin dependencias, sin migración**; el formulario es GET.
- [x] **No se toca #283**: solo se reutilizan sus textos y su patrón de validación/URL, citados.
- [x] **Riesgos y pruebas existentes** que hay que ajustar están previstos (§10.2, §11).
- [x] **Si la ficha no cuadra con el código, se dice**: §13.1 (pliegue y artículos), §13.2 (SQL/Python),
      §13.5 (mapa de enlaces), §13.6 (líneas), §13.7 (una consulta vs dos).

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-05 | v1.0 | Primera especificación. Ratifica los 7 criterios del issue #397, las decisiones del PO del 2026-10-31 y del 2026-11-01 (modelo de estados, propagación, «Volver» sin retorno, resultado guardado, pliegue), el contrato de parámetros y valores inválidos, los textos exactos, la privacidad y los NFR. Base `f6964ae`; ficha `9d7fedf` sin cambios en los ficheros citados. |
