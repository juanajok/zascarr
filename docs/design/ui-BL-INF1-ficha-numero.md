# UX — Ver la información de una serie y de cada número (BL-INF1, #447)

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas ni
> plantillas nuevas. Fija el contenido, el copy, los estados, la procedencia y las condiciones de
> accesibilidad; la implementación los lleva al código.
> **Base:** `origin/main` = `caaca10a80739934153503c67b4005fc3649eeed` (2026-11-09), worktree
> `.squad/wt-447-ui`, rama `docs/447-ui`.
> **Insumos:** issue #447 (AC 1-7), `CLAUDE.md` §6, `docs/design/ui-migracion.md`, la ficha actual
> `src/zascarr/web/templates/series_detail.html`, `docs/design/procedencia-127.md`,
> `utils/texto_html.py::texto_plano` y la cascada actual de portada (`web/series.py::portada`).
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**; este documento describe lo
> que la implementación tendrá que verificar.

---

## 0. Resumen

BL-INF1 **solo enseña** lo que ya está en la base, sin red y sin escribir. Se entrega en dos piezas:

1. **Bloque «Sobre esta serie»** dentro de la ficha actual: sinopsis en llano, editorial, años y
   **autores principales** (guion y dibujo, por número que firman), con su procedencia.
2. **Ficha de número** nueva: sinopsis, fecha de portada, páginas, autores por papel y archivos,
   enlazada desde cada número que la ficha ya lista, sin convertir la fila entera en un enlace.

**El recorrido en cuatro líneas:**

1. Ficha de serie → bloque **«Sobre esta serie»** para saber de qué va y quién la firma.
2. En **«En tu biblioteca»** o en **«Archivos por número»**, el número es un enlace.
3. Se abre **«Número 12»** con lo que consta: sinopsis, fecha, páginas, autores y archivos.
4. Cada bloque tiene **«De dónde sale cada dato»**; lo que falta dice **«No consta todavía»**.

**Lo que no hace:** no edita, no enriquece, no rellena desde fuentes ni desde los CBZ, no pide nada
a la red, no mueve ni abre archivos y no cambia el orden de las secciones actuales de la ficha.

---

## 1. Decisiones de estructura

### 1.1 Dónde va «Sobre esta serie»

**Recomendación: justo después de la cabecera de la serie y antes de «Consulta tus números y ajusta
la búsqueda automática».**

- La sinopsis y los autores son lo que la persona espera al abrir una ficha; ponerlos después de la
  política de búsqueda los esconde.
- Insertar un bloque nuevo **no reordena** las secciones existentes: todas siguen en su orden, solo
  que empiezan más abajo.
- El único traslado es el `<details id="procedencia-serie">` de «De dónde sale cada dato», que se
  mueve **dentro del bloque nuevo** para que el dato y su origen no queden separados. No se mueve
  ningún otro contenido.
- Si el equipo prefiere no mover el `<details>`, la alternativa es dejarlo donde está y enlazarlo
  desde el bloque; **no se duplica** el panel. La recomendación es moverlo.

No se añade ningún botón principal: el único de la ficha sigue siendo «Añadir números del disco»;
el bloque nuevo es informativo y la ficha del número no tiene acciones de escritura.

Orden resultante (las secciones existentes conservan su orden relativo):

```
cabecera de la serie (título, acciones, fuentes y atribución)
→ SOBRE ESTA SERIE (nuevo)
    sinopsis · editorial · años · autores principales
    ▸ De dónde sale cada dato   (el details existente, ampliado)
→ «Consulta tus números y ajusta la búsqueda automática.»
→ etiquetas
→ Búsqueda automática
→ Otras fuentes
→ Revisar cambios de datos
→ Te faltan / En tu biblioteca
→ Archivos por número
```

### 1.2 Dónde se enlaza cada número

- **«En tu biblioteca»**: cada chip `#N` pasa de `<span>` a `<a>` a la ficha de ese número. El
  enlace es solo el chip, no un contenedor de fila; los chips de «Te faltan» no son enlaces (no hay
  ficha de número que abrir).
- **«Archivos por número»**: el `#N` del `<h3>` es un enlace a la ficha del número. Las filas de
  archivos **no** se convierten en enlaces ni se envuelven en un `<a>`: conservan sus textos y su
  botón «Desvincular» como hasta ahora.
- **Ruta propuesta:** `GET /ui/series/{series_id}/numero/{issue_id}`. Anidada bajo la serie para
  que la miga de pan y el 404 sean inequívocos. Si el número no existe o no pertenece a esa serie,
  `404` (página de error existente, sin filtrar datos de otra serie).
- Los números de la serie que **no tienen ficha de `Issue`** (huecos de «Te faltan») no tienen
  página; no se inventa un número para enlazar.
- Un número con **varios volúmenes** (dos filas de `Issue` con el mismo `issue_number`) se enlaza
  desde cada fila de «Archivos por número», que ya distingue por `issue_id`; el chip de «En tu
  biblioteca» enlaza a la ficha que tiene el archivo y no intenta representar las dos. Resolver esa
  ambigüedad visual es otra historia, no BL-INF1.

---

## 2. Bloque «Sobre esta serie»

### 2.1 Wireframe a 360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Biblioteca                                 │
│ [portada] THE WICKED + THE DIVINE (2014)     │
│           Editorial · géneros                │
│           [Añadir números del disco]         │
│           [Retirar de mi biblioteca]         │
│                                              │
│ SOBRE ESTA SERIE                             │
│                                              │
│ Una guerra entre dioses que vuelven cada     │
│ noventa años… [texto en llano, 2-3 líneas]   │
│ ▸ Leer la sinopsis completa                  │
│                                              │
│ Editorial       Panini Cómics                │
│ Año de inicio   2014                         │
│ Año de fin      2019                         │
│                                              │
│ Autores principales                          │
│ Los que más números firman, según los datos  │
│ de la serie.                                 │
│                                              │
│ Guion           Kieron Gillen (30 números)   │
│ Dibujo          Jamie McKelvie (28 números)  │
│                                              │
│ ▸ De dónde sale cada dato                    │
│                                              │
│ Consulta tus números y ajusta la búsqueda…   │
└──────────────────────────────────────────────┘
```

- El bloque es una `<section aria-labelledby>` con `<h2>`; la sinopsis es un `<p>` normal, no una
  caja de aviso.
- «Leer la sinopsis completa» es un `<details>` nativo que solo aparece si el texto se recorta.
- Los autores son un `<dl>`: papel como término, nombres como valor. No es una tabla: a 320 px una
  lista de dos columnas se lee mejor y no necesita `scope`.

### 2.2 Sinopsis

- Se toma de `Series.description` y se convierte con `texto_plano` (nunca se interpreta HTML de la
  fuente, nunca se enlaza lo que venga dentro).
- **Regla de recorte:** se muestran hasta **40 palabras** (o el texto entero si es más corto). Si
  hay más, el resto va en `<details><summary>Leer la sinopsis completa</summary>`. El recorte no
  parte una palabra por la mitad y no añade «…» dentro del `<summary>`.
- Si no hay sinopsis: **«No consta todavía la sinopsis. Puede venir de una fuente de datos o de la
  ficha de tus archivos.»** (19 palabras; no se pinta un hueco vacío).
- El texto no se atribuye a nadie en el párrafo; la atribución va en «De dónde sale cada dato».

### 2.3 Editorial y años

| Dato | Cuándo | Texto exacto |
|---|---|---|
| Editorial | `Series.publisher` con nombre | etiqueta «Editorial» + nombre |
| Editorial | sin editorial | etiqueta «Editorial» + «No consta todavía.» |
| Año de inicio | `Series.start_year` | etiqueta «Año de inicio» + cuatro cifras |
| Año de inicio | sin dato | etiqueta «Año de inicio» + «No consta todavía.» |
| Año de fin | `Series.end_year` | etiqueta «Año de fin» + cuatro cifras |
| Año de fin | sin dato | **la fila no se pinta**; el fin no se inventa ni se deduce de `status` |

- No se dice «en curso» ni «serie completa» por la ausencia de `end_year`: el dato que no consta no
  se convierte en una afirmación.
- La cabecera conserva el título y el año de inicio como contexto; el bloque es la lectura completa
  (incluido el fin). La pequeña duplicación del año de inicio es deliberada: evita que la cabecera
  tenga que cambiar y mantiene la orientación al volver desde el número.
- La editorial se repite en el bloque aunque la cabecera ya la enseñe; es el dato que el AC pide en
  el bloque y no se puede garantizar que la cabecera la mantenga en el futuro. Si se decide
  eliminar la de la cabecera, no cambia el bloque.

### 2.4 Autores principales

- Se calculan **solo con los créditos de los números de esta serie** (`IssueCreator` unido a
  `Issue`), no con una ficha de autor ni con la red.
- **Papeles que entran en el bloque: «Guion» y «Dibujo»**, únicamente. Traducción y edición se
  enseñan en la ficha del número, no como «autores principales» de la serie.
- **Tope: 3 personas por papel.** Orden: número de números distintos en que firman, de mayor a
  menor; a igualdad, nombre en orden natural (determinista). Si hay menos de 3, se muestran los que
  hay.
- Cada nombre lleva el número de números en que consta ese papel: «(30 números)»; en singular,
  «(1 número)». El contador se puede comprobar en los números; no es una puntuación inventada.
- Si un autor firma con dos papeles, aparece en las dos filas (es correcto: son dos trabajos).
- Si no hay ningún crédito de Guion ni de Dibujo:

  > «No constan todavía los autores. Pueden venir de una fuente o de los datos de la serie.»

  (17 palabras; se mantiene «No consta todavía» para el caso de campo ausente).

- El bloque **no** dice «creadores», «autores originales» ni «obra original». La explicación va en
  la procedencia: «Se cuenta cada número en el que aparece el nombre con ese papel. No dice quién
  creó la obra ni de qué edición es cada crédito.»

### 2.5 Procedencia del bloque

Se reutiliza el `<details class="procedencia-serie" id="procedencia-serie">` que ya existe:

- **Se mueve** al final de «Sobre esta serie» (único movimiento de la ficha; ver §1.1).
- **Se amplía** con las filas nuevas: «Editorial», «Año de fin» y «Autores principales». Las filas
  existentes (Título, Año de inicio, Sinopsis, Portada, Números en total, Identificador) se quedan
  como están y no se convierten en otra cosa.
- El contenido sigue la regla de #127: **solo se atribuye lo que consta**, y si no consta, «Origen
  no registrado»; nunca se adivina por parecido.

| Campo nuevo | Origen que se muestra |
|---|---|
| Editorial | «Origen no registrado» (hoy no hay un registro por campo de la editorial; no se atribuye a Comic Vine solo porque la serie tenga `metadata_source`) |
| Año de fin | «Origen no registrado» (no se escribe por el enriquecimiento actual; si en el futuro se registra, se actualiza esta tabla) |
| Autores principales | Si todos los créditos constan de la misma fuente conocida: esa fuente («Comic Vine», «el propio archivo», «puesto a mano»). Si hay mezcla: «Varias fuentes». Si no consta: «Origen no registrado». |

- No se añade un segundo panel de procedencia ni un `<details>` por autor. Un solo panel para el
  bloque, como hoy.
- Las filas sin valor no se convierten en una fila de origen vacía; se comportan como hoy (la fila
  muestra el valor «Sin dato» y el origen que conste o «Origen no registrado»).

### 2.6 Estado vacío o parcial del bloque

| Situación | Qué se pinta |
|---|---|
| Todo completo | Sinopsis + editorial + años + autores. |
| Falta un campo | El campo con «No consta todavía.»; el resto normal. |
| Falta la sinopsis | «No consta todavía la sinopsis. Puede venir de una fuente de datos o de la ficha de tus archivos.» |
| Faltan autores | «No constan todavía los autores. Pueden venir de una fuente o de los datos de la serie.» |
| No hay sinopsis, editorial, años ni autores | Una sola frase, sin filas vacías: **«Todavía no hay información de esta serie. Puede venir de las fuentes de Ajustes o de la ficha de tus archivos.»** (21 palabras) |

En el caso «no hay información en absoluto» el bloque conserva el título «Sobre esta serie» y la
frase; **no** pinta cinco «No consta» seguidos ni un details de procedencia lleno de «Sin dato»: el
detalle de procedencia se pinta solo si hay algún dato con valor (o si hay datos protegidos/manuales
que #127 ya mostraba).

### 2.7 Presupuesto del bloque

| Medida | Palabras |
|---|---:|
| Título de sección y rótulos fijos («Editorial», «Año de inicio», «Año de fin», «Autores principales») | 3 + 1 + 2 + 2 + 2 = **10** (sin contar valores) |
| Frase de sinopsis ausente | 19 |
| Frase de autores ausentes | 17 |
| Frase de bloque sin datos | 21 |
| Sinopsis visible | hasta 40 palabras (dato recortado; el resto en `<details>`) |

El bloque va **después** del botón principal de la ficha («Añadir números del disco»), por lo que no
compite con el presupuesto de ≤ 50 palabras antes de la primera acción.

---

## 3. Ficha de número

### 3.1 Ruta y 404

- `GET /ui/series/{series_id}/numero/{issue_id}`.
- Si el número no existe o no pertenece a esa serie: `404` con la página de error existente. No se
  muestra la serie del otro dueño ni un número de otra serie.
- Sin JavaScript nuevo: un enlace normal, página servida en servidor.
- `Cache-Control: no-store` como la ficha de serie (el contenido puede cambiar con el enriquecimiento
  y con el disco).
- **Coste:** un número fijo de consultas (la serie con su editorial, el número con créditos y
  archivos, y el agregado de autores de la serie). **No hay una consulta por archivo ni por autor**;
  el AC 5 lo comprueba con el contador de sentencias. Sin red y sin disco más allá de la portada.

### 3.2 Wireframe a 360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← The Wicked + The Divine                    │
│                                              │
│ [portada 120]  NÚMERO 12                     │
│                El panteón                    │
│                Todo lo que ZascArr sabe de   │
│                este número.                  │
│                                              │
│ Serie           The Wicked + The Divine      │
│ Formato         grapa                        │
│ Fecha de portada 1 de septiembre de 2014     │
│ Páginas         32 páginas                   │
│                                              │
│ SINOPSIS                                     │
│ Una guerra entre dioses…                     │
│ ▸ Leer la sinopsis completa                  │
│                                              │
│ AUTORES                                      │
│ Los que constan para este número.            │
│                                              │
│ Guion           Kieron Gillen                │
│ Dibujo          Jamie McKelvie               │
│ Color           Matt Wilson                  │
│ Rotulación      Clayton Cowles               │
│ Portada         Jamie McKelvie               │
│ Edición         …                            │
│ Traducción      …                            │
│ ▸ Qué significan estos papeles               │
│                                              │
│ ARCHIVOS                                     │
│ The Wicked + The Divine 012 (2014).cbz       │
│ CBZ · En el disco                            │
│                                              │
│ ▸ De dónde sale cada dato                    │
└──────────────────────────────────────────────┘
```

- La cabecera se apila a ≤ 480 px (portada arriba, datos debajo). A 320 px no hay dos columnas
  forzadas.
- El H1 es **«Número 12»** (2 palabras, rótulo Anton). El título del número, si existe, va debajo
  como subtítulo en Archivo; **no** se mete en el H1 (sería una frase de más de 3 palabras).
- «Serie» enlaza de vuelta a la ficha de la serie; es el mismo destino que el enlace «←».
- No hay botón principal: la pantalla es de lectura. Las acciones de gestión («Desvincular»,
  vincular) siguen en la ficha de la serie, no se duplican aquí.

### 3.3 Portada

- Se usa **la misma cascada que la ficha de serie** (`/ui/series/{series_id}/portada` actual:
  archivo/caché local, nunca una URL externa directa, marcador `ui.portada` si no hay).
- La imagen se muestra con `alt=""` y el nombre accesible lo da la cabecera (serie + número). En este
  corte **no se añade una caché de portada por número**: la imagen es la de la serie, servida por la
  cascada actual, y se rotula **«Portada de la serie»** (4 palabras) en texto pequeño bajo la imagen.
  No se finge una portada del número; si en el futuro hay una cascada por número, se quita el rótulo.
- Si la cascada falla: marcador de `ui.portada` (tinta, trama e inicial), no `<img>` roto ni
  `onerror=`.
- Sin salto de maquetación: el contenedor reserva 2:3 como en la ficha actual.

### 3.4 Datos del número

| Etiqueta | Valor | Si falta |
|---|---|---|
| «Serie» | enlace con el título de la serie | no aplica: la serie es obligatoria para abrir la página |
| «Formato» | `FORMATOS_LEGIBLES` («grapa», «tomo en rústica», «ómnibus»…) | «No consta todavía.» (nunca el enum interno) |
| «Fecha de portada» | `Issue.release_date` en llano («1 de septiembre de 2014») | «No consta todavía.» |
| «Páginas» | `Issue.page_count` + «páginas» («32 páginas», «1 página») | «No consta todavía.» |

- **Nunca se dice «edición»** para el número ni para el formato. «Edición» solo existe como papel
  de crédito y se explica en el glosario (§3.6).
- La fecha se presenta con el mes en palabras y sin depender del locale del sistema (la app ya
  tiene filtros de fecha sin locale; reutilizarlos o usar nombres de mes explícitos).
- El formato no se deduce del nombre del archivo ni de la extensión; se usa `Issue.format`.
- No se inventa un dato a partir de otro: si no hay fecha, no se usa `created_at`; si no hay
  páginas, no se cuentan las del archivo.

### 3.5 Sinopsis del número

- `Issue.synopsis` convertida con `texto_plano`; mismas reglas que §2.2 (hasta 40 palabras visibles;
  resto en `<details>`; sin HTML).
- Si no hay: «No consta todavía la sinopsis.» (4 palabras) cuando hay otros datos; si no hay ningún
  dato del número, se usa la frase global de §3.8.
- La sinopsis no se atribuye en el párrafo; la procedencia va en el `<details>`.

### 3.6 Autores por papel

- Orden fijo y en español:
  **Guion · Dibujo · Tinta · Color · Rotulación · Portada · Edición · Traducción.**
- Solo se pinta cada papel si tiene al menos un nombre; no se listan ocho «No consta» seguidos.
- Los nombres van en un `<dl>` (papel / personas), separados por comas si hay varios, con
  `overflow-wrap: anywhere` para nombres largos. No se enlazan a fichas de autor: no existen en esta
  entrega.
- Si no hay ningún crédito:

  > «No constan todavía los autores. Pueden venir de la fuente o de la ficha del archivo.»

  (16 palabras)

- **Glosario plegado** (`<details><summary>Qué significan estos papeles</summary>`), porque «Edición»
  y «Traducción» pueden confundirse con una edición distinta del número:

  > Guion: quién escribe el texto. Dibujo: quién dibuja las páginas. Tinta: quién entinta el dibujo.
  > Color: quién da el color. Rotulación: quién rotula el texto. Portada: quién hizo la portada.
  > Edición: quién coordina la publicación; no es una edición distinta del número. Traducción: quién
  > traduce esta versión.

- **No se inventa la autoría de la obra original.** La página muestra los créditos que constan para
  **este número**, no una atribución de la obra; si la fuente solo trae la edición española, se
  enseña eso y no se completa con nombres de la obra original por deducción.

### 3.7 Archivos del número

- Se listan los `File` vinculados a ese `Issue`, ordenados por nombre natural (determinista).
- Cada archivo, en una lista (no una tabla de 4 columnas que a 320 px desborde):
  - nombre completo del archivo, con `overflow-wrap: anywhere`;
  - formato del archivo (CBZ/CBR/PDF…) en mayúsculas y `.muted`;
  - chip «En el disco» o «Quizá no esté en el disco» (el mismo texto de la ficha de serie);
  - no se muestra la ruta, ni el hash, ni el tamaño si no se pide; el dato de identidad es el
    nombre.
- Si no hay archivos:

  > «No hay ningún archivo vinculado a este número. Puedes vincularlo desde la ficha de la serie.»

  (16 palabras) + enlace «Ir a la serie».

- Las acciones sobre archivos (**Desvincular**, etc.) no se duplican aquí: esta página informa. La
  ficha de la serie sigue siendo el sitio de gestión, enlazado desde «Serie» y desde el aviso de
  archivos.

### 3.8 Estado vacío o parcial del número

| Situación | Qué se pinta |
|---|---|
| Número con datos | Cabecera + datos + sinopsis + autores + archivos + procedencia. |
| Faltan campos sueltos | El campo con «No consta todavía.»; el resto normal. |
| Faltan autores | «No constan todavía los autores. Pueden venir de la fuente o de la ficha del archivo.» |
| Faltan archivos | «No hay ningún archivo vinculado…» + «Ir a la serie». |
| Sin ningún dato del número ni archivos | Una sola frase tras la cabecera: **«Todavía no hay información de este número ni archivos vinculados. Puede venir de una fuente de datos o de la ficha del archivo.»** (23 palabras); no se pintan secciones vacías ni el details de procedencia. |
| Sin portada | Marcador de `ui.portada`; no hay texto de error. |
| Número inexistente o de otra serie | Página 404 existente; no se muestra nada del otro dueño. |
| Número sin `issue_number` | H1 «Número» y, debajo, «Sin número»; los datos se muestran igual. |

**Solo serie / solo número:**

- **Solo serie** (la serie tiene datos, el número no): la ficha del número muestra la cabecera y la
  frase global de este apartado; la ficha de la serie muestra su bloque completo. No se rellena el
  número con datos de la serie.
- **Solo número** (el número tiene datos, la serie no): la ficha de la serie muestra la frase de
  bloque sin datos (§2.6); la ficha del número muestra sus datos. No se copian los del número a la
  serie.

### 3.9 Presupuesto del número

| Medida | Palabras |
|---|---:|
| Frase de entrada («Todo lo que ZascArr sabe de este número.») | **8** (≤ 20) |
| Copy fija antes de la primera acción de la pantalla (H1 + entrada + etiquetas de datos) | **16** (≤ 50) |
| Frase de sinopsis ausente | 4 |
| Frase de autores ausentes | 16 |
| Frase de archivos ausentes | 16 |
| Frase global sin datos | 23 |

La primera acción de la pantalla es el enlace «Serie» / «←» (navegación); la pantalla no tiene
acción de escritura. Para este presupuesto **no se cuentan los enlaces de navegación, los valores
variables ni el contenido de los `<details>`**; se cuentan la frase de entrada y las etiquetas de la
tarea, que es lo que la persona lee para entender la pantalla.

---

## 4. Procedencia (patrón #127)

### 4.1 Qué se muestra y qué no

- Todo origen visible usa el mismo `<details>` de la ficha (#127): `summary` «De dónde sale cada
  dato», `<dl>` de campo → origen y la explicación de «Manual»/«Protegido» cuando exista.
- **Solo se atribuye un dato a una fuente si consta que esa fuente lo escribió.** No se infiere por
  parecido, ni por `metadata_source` de la serie cuando el campo no es de los que escribe el
  enriquecimiento.
- Vocabulario visible y fijo:
  - «Comic Vine», «AniList», «Tebeosfera», «GCD»;
  - «el propio archivo» (ComicInfo.xml, cadena de la portada extraída, archivos vinculados);
  - «puesto a mano» (cuando el registro dice manual);
  - «Origen no registrado» (hay dato, pero no consta quién lo escribió);
  - «No consta todavía de dónde sale este dato» solo si el dato en sí falta y aun así se pinta la
    fila (se prefiere no pintar filas de campos sin valor).
- No se usa «token», «operación», «huella», «id externo» ni el valor de un identificador interno.
  La ficha de serie ya decidió no pintar ids en #127; se mantiene.
- `locked_fields` se sigue mostrando como «Protegido» y con la explicación de que el enriquecimiento
  no lo sobrescribe. **Protegido no significa «puesto a mano»**: si no consta el origen, se dice
  «Origen no registrado».

### 4.2 Tabla de orígenes por campo

| Bloque | Campo | Origen visible |
|---|---|---|
| Serie | Título, año de inicio, sinopsis, portada, números, identidad | Los que ya calcula `procedencia_de_serie` (#127), sin cambios. |
| Serie | Editorial | «Origen no registrado» (no hay registro por campo). |
| Serie | Año de fin | «Origen no registrado» (no lo escribe el enriquecimiento actual). |
| Serie | Autores principales | «Comic Vine» / «el propio archivo» / «puesto a mano» si **todos** los créditos constan de una sola procedencia; «Varias fuentes» si se mezclan; «Origen no registrado» si no consta. |
| Número | Sinopsis | La fuente que conste para el número; si no consta, «Origen no registrado». |
| Número | Fecha de portada | La fuente que conste; hoy el enriquecimiento no la escribe, así que lo normal es «Origen no registrado» hasta que una fuente lo haga. |
| Número | Páginas | Igual que la fecha. |
| Número | Autores | La fuente de los créditos; si se mezclan, «Varias fuentes»; si no consta, «Origen no registrado». |
| Número | Archivos | «el propio archivo». |

Esta tabla es una **guía de honestidad**, no una promesa de que hoy haya datos en todas las filas:
la mayoría de fechas y páginas estarán en «No consta todavía» hasta que una fuente las escriba.

### 4.3 Dónde va cada panel

- **Serie:** el `<details>` existente se mueve dentro de «Sobre esta serie» (§1.1) y se amplía con
  las filas nuevas. No se crea un segundo panel.
- **Número:** un `<details>` con la misma estructura al final de la ficha del número, después de
  archivos. Si no hay ningún dato con valor, no se pinta (no hay nada que atribuir).
- No se muestran propuestas ni valores «que podrían venir»: eso es BL-INF2, fuera de alcance.

---

## 5. Navegación desde la ficha de serie

```
En tu biblioteca
[✓ #1] [✓ #2] [✓ #3] …        ← cada chip es <a href="/ui/series/{id}/numero/{issue_id}">
                                (solo el chip; el resto de la fila no es enlace)
Te faltan
[#4] [#5] …                   ← no son enlaces: no hay ficha de número

Archivos por número
#1  ← <a> en el <h3>, con nombre accesible «Ver información del número 1»
  Archivo uno.cbz  CBZ  ✓ En el disco  [Desvincular]
#2  ← <a> en el <h3>
  …
```

- El chip enlace conserva el estilo `.issue-chip` y el tamaño táctil: `min-height: 40px` o
  `padding` suficiente; el enlace no se distingue solo por color (foco visible y subrayado en
  `:hover`/`:focus-visible`).
- Nombre accesible: «Número 1: ver información» (texto visible `#1` + `<span class="sr">` con
  «ver información del número 1»). No se repite el título de la serie dentro de cada chip.
- En «Archivos por número», el enlace del `<h3>` no convierte la fila de archivos en un enlace: el
  botón «Desvincular» sigue siendo un control independiente y se puede pulsar sin abrir la ficha del
  número.
- Si un número no tiene ficha (`Issue`), no hay enlace: se queda como chip o como hueco, sin URL
  inventada.
- A 320 px los chips envuelven; el foco no queda oculto por la barra inferior (la app ya tiene
  `scroll-padding-bottom`).

---

## 6. Tabla de estados y textos finales

| # | Pantalla / bloque | Situación | Texto exacto | Acción / nota |
|---|---|---|---|---|
| 1 | Serie · «Sobre esta serie» | Todo completo | (sin frase de estado; datos) | — |
| 2 | Serie · sinopsis ausente | sin `Series.description` | «No consta todavía la sinopsis. Puede venir de una fuente de datos o de la ficha de tus archivos.» | — |
| 3 | Serie · autores ausentes | sin créditos de Guion/Dibujo | «No constan todavía los autores. Pueden venir de una fuente o de los datos de la serie.» | — |
| 4 | Serie · campo sin dato | editorial/año sin valor | «No consta todavía.» | La fila se muestra con su etiqueta |
| 5 | Serie · sin ningún dato | sin sinopsis, editorial, años ni autores | «Todavía no hay información de esta serie. Puede venir de las fuentes de Ajustes o de la ficha de tus archivos.» | No se pintan filas vacías ni el details de procedencia |
| 6 | Serie · autor único | 1 crédito | «Guion» + «Nombre (1 número)» | Sin «principales» inventados: es el único |
| 7 | Serie · un solo papel | solo Guion o solo Dibujo | Solo la fila del papel con nombres | El otro papel no se pinta |
| 8 | Número · completo | datos + autores + archivos | (sin frase de estado; datos) | — |
| 9 | Número · parcial | falta fecha/páginas/sinopsis | «No consta todavía.» en el campo que falte | El resto normal |
| 10 | Número · sin autores | sin créditos | «No constan todavía los autores. Pueden venir de la fuente o de la ficha del archivo.» | — |
| 11 | Número · sin archivos | sin `File` | «No hay ningún archivo vinculado a este número. Puedes vincularlo desde la ficha de la serie.» | Enlace «Ir a la serie» |
| 12 | Número · sin nada | sin datos ni archivos | «Todavía no hay información de este número ni archivos vinculados. Puede venir de una fuente de datos o de la ficha del archivo.» | No secciones vacías ni procedencia |
| 13 | Número · sin portada | cascada sin imagen | — | Marcador `ui.portada`; sin texto de error |
| 14 | Número · sin número | `issue_number` nulo | H1 «Número» + subtítulo «Sin número» | Resto de datos normal |
| 15 | Número · 404 | no existe / otra serie | Página 404 existente | No se filtra la serie ajena |
| 16 | Serie · solo serie | serie con datos, número sin datos | Serie normal; número con #12 | No se copian datos de la serie al número |
| 17 | Número · solo número | número con datos, serie sin datos | Número normal; serie con #5 | No se copian datos del número a la serie |

---

## 7. Accesibilidad y 320 px

### 7.1 Semántica

- Ficha de serie: el bloque es `<section aria-labelledby>`, con `<h2>` «Sobre esta serie»; los
  autores son `<dl>` con `<dt>` de papel.
- Ficha de número: `<article>` o `<section>` con `<h1>` «Número 12»; los datos son `<dl>`; los
  autores, otro `<dl>`; los archivos, una `<ul>`.
- No se usan tablas de datos en estas dos piezas. Si la implementación prefiere tabla para los
  archivos, lleva `<caption>` y `scope="col"`/`scope="row"`, y a 320 px se sustituye por lista para
  no provocar scroll lateral. La recomendación es lista.
- La portada va en el contenedor `ui.portada` existente, con `img alt=""`; el nombre accesible lo da
  el título. No hay imágenes externas ni `src` de la fuente.
- Los `<details>` son nativos: foco, Enter y Espacio estándar. No hay `aria-expanded` manual ni
  `onclick`.

### 7.2 Teclado y foco

- Los enlaces de los números son `<a>` reales, alcanzables con Tab y activables con Enter.
- En «Archivos por número» el enlace del número y el botón «Desvincular» son focos distintos; el
  orden de tabulación no salta del número al botón de otra fila.
- Tras abrir la ficha de un número (navegación normal) el foco sigue el orden del documento; no se
  fuerza un foco que robe contexto. El primer enlace es «←», como en la ficha de serie.
- Si se usa HTMX en alguna actualización, el foco va al `<h2>` de la región actualizada
  (`tabindex="-1"`) y el cambio se anuncia con `role="status"`; **ninguna de estas dos páginas lo
  necesita en la propuesta actual**, porque son páginas completas de solo lectura.
- No hay atajos propios, ni trampas, ni elementos clicables que no sean enlaces/botones.

### 7.3 Lectores de pantalla

- El `<h1>` de la ficha del número es «Número 12»; el título del número, si existe, es un `<p>` de
  subtítulo y se anuncia después, no dentro del H1.
- «No consta todavía» se lee como texto; las filas que no constan no se pintan vacías.
- El `<details>` de procedencia tiene un `summary` significativo («De dónde sale cada dato») y su
  contenido usa `<dt>`/`<dd>`. No hay diálogos nativos ni `hx-confirm`: no hay acciones que
  confirmar en estas dos piezas.
- El chip de número enlazado tiene `<span class="sr">` para que el lector no anuncie solo «#12» sin
  decir qué hace.
- No se usa color como único indicador: el chip de disco lleva texto («En el disco»/«Quizá no esté
  en el disco»), no solo verde/ámbar.

### 7.4 Móvil (320 px)

- Una columna en el bloque de serie y en la cabecera del número a ≤ 480 px; la portada no fuerza
  ancho (120 px como máximo en móvil).
- Nombres de autores, títulos y nombres de archivo con `overflow-wrap: anywhere`; contadores
  `font-variant-numeric: tabular-nums`.
- Sin scroll horizontal de página: `document.documentElement.scrollWidth == clientWidth`; no se
  usan tablas de 4 columnas en 320 px. La comprobación es condición de aceptación, no una medición
  hecha aquí.
- Objetivos táctiles: los enlaces de número y cualquier enlace de la ficha, ≥ 40 px de alto
  (los chips enlazados incluidos).

### 7.5 Tipografía y contraste

- Textos informativos ≥ 14 px (`.875rem`); títulos de pantalla en Anton solo si son rótulos de ≤ 3
  palabras; las frases de más de 3 palabras que actúen como título usan `.titulo-frase` (Archivo
  negrita, sin mayúsculas).
- Se reutilizan los tokens de `web.css`; no se añaden colores. La prueba de contraste existente
  cubre los textos nuevos si se usan las clases de la app.
- Las cifras comparables (números de grapa, contadores de autor) usan `tabular-nums`.

---

## 8. Riesgos de copy: decisiones explícitas

1. **«Número», no «edición».** El objeto es una grapa/tomo/número (`Issue`); la página se llama
   «Número 12». «Edición» solo es un papel de crédito y se explica: «trabajo de edición, no una
   edición distinta del número». No se usa «edición» para el formato ni para la fila de archivos.
2. **«Autores» no es «creadores de la obra».** El bloque de serie dice «Autores principales» y
   explica que cuenta números firmados; la ficha del número dice «Autores» y muestra los créditos
   de **ese** número. Nunca se etiqueta «autor original», «creador» ni «obra original» por
   deducción.
3. **Autoría de la obra original vs. edición española.** Los papeles «Traducción» y «Edición» se
   muestran separados y explicados; no se suman a «Guion»/«Dibujo» de la serie. Si la fuente solo
   acredita la edición española, se enseña esa y no se rellena con nombres de la obra original.
4. **Lo que no consta no se inventa.** Campo ausente = «No consta todavía.»; dato presente sin
   origen conocido = «Origen no registrado.»; no se usa «—», «None», ni una celda vacía. No se
   deduce el formato del nombre del archivo, ni la fecha de `created_at`, ni las páginas del CBZ.
5. **«Año de fin» ausente no significa «en curso».** La fila no se pinta; no se usa `status` para
   afirmar nada. La cabecera conserva el año de inicio como contexto; el bloque no duplica
   afirmaciones de estado.
6. **Portada.** La imagen es la de la serie y se rotula «Portada de la serie»; no se llama «portada
   de este número». Nunca se hotlinkea una URL externa ni se pinta un `<img>` roto.
7. **Contadores de autores.** «30 números» es el número de números distintos en que consta el
   nombre con ese papel, no una estimación; el tope de 3 y el desempate por nombre hacen que la
   lista sea reproducible. No se llama «los mejores» ni «los favoritos».
8. **Procedencia actual, no promesa.** La tabla de orígenes enseña lo que consta; que la mayoría de
   fechas y páginas estén en «No consta todavía» hoy es correcto, no un fallo.
9. **La página es de solo lectura.** No hay botones de editar, vincular, descargar ni abrir el
   archivo; las acciones de gestión siguen en la ficha de la serie. No se duplican ni se insinúan.
10. **Sin jerga interna.** No aparecen `single_issue`, `issue_id`, `metadata_source`, `None`,
    «token» ni nombres de columnas; el número de ficha no se enseña porque aquí no hace falta.

---

## 9. Lo que este corte deja fuera

- **Editar o rellenar datos** desde fuentes o desde los CBZ: BL-INF2.
- **Cifras de cobertura** (cuánto falta, porcentaje): BL-INF3.
- **Lector o descarga** de archivos, y cualquier acción sobre ellos desde la ficha del número.
- **Páginas de autor, editorial, personaje o saga**; los nombres no son enlaces.
- **Catálogo completo de números**: solo se enlazan números que la ficha ya lista (`En tu
  biblioteca` y `Archivos por número`). Un número que no tiene archivo ni aparece hoy en esas
  listas no gana entrada en BL-INF1; no se añade una consulta ni una sección nueva para él.
- **Portada por número**: se reutiliza la cascada/imagen actual de la serie; una caché por número
  sería otro corte.
- **Ordenación, filtros y búsqueda** de números; **multi-volumen** con el mismo número (se enlaza
  cada fila de archivos, no se resuelve la ambigüedad del chip).
- **Cambios de esquema o migraciones**, y cualquier petición a la red.
- **Verificación real** de navegador, lector de pantalla, 320 px y Pi: este documento solo fija las
  condiciones; la implementación debe medirlas.

---

## 10. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba al implementar |
|---|---|---|
| 1 | Bloque de serie con sinopsis, editorial, años y autores principales | Render con texto exacto; autores con tope 3 y contadores; campos ausentes con «No consta todavía» |
| 2 | Ficha de número con sinopsis, fecha, páginas, autores por papel y archivos | Render del número; roles en el orden fijo; archivos del `Issue` correcto |
| 3 | Procedencia en un `<details>` | Serie: el details existente ampliado y movido; número: details propio; orígenes solo si constan |
| 4 | Ausencias honestas | «No consta todavía» en campos; frase global cuando no hay datos; nunca celdas vacías |
| 5 | Solo lectura y barato | Sin POST, sin red; número fijo de consultas (lo comprueba el contador de sentencias) |
| 6 | Accesible y móvil | Teclado, foco, 14 px, títulos-frase, `scrollWidth == clientWidth` a 320 px |
| 7 | Enlaces desde la ficha | Chips de números y `#N` de «Archivos por número» son `<a>`; las filas de archivo no |
| 8 | Copy sin jerga | Buscar en render `single_issue`, `issue_id`, `metadata_source`, `None`, «token», «obra original», «creador» |
| 9 | No duplicar procedencia | Un solo `<details id="procedencia-serie">`; un solo panel en número |
| 10 | Sin cambios en el orden actual | El resto de secciones de `series_detail` conserva su orden; solo se inserta el bloque y se mueve el details de procedencia |

**PASS de este documento:** el contenido, los textos, los estados y las condiciones de accesibilidad
están decididos y son coherentes con #447/#127/CLAUDE.md §6.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos,
fuentes reales y Pi. No se declaran.
