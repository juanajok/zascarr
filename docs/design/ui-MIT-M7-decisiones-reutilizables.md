# UX — Decisiones reutilizables (MIT-M7-US03, #132, rebanada 132-b)

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas,
> plantillas, migraciones ni servicios. Fija el inventario, las filas, los filtros, las acciones y
> las condiciones de accesibilidad; la implementación los lleva al código.
> **Base:** `origin/main` = `f2884eac722c268b552c840902217afef7b96345` (2026-11-10), worktree
> `.squad/wt-132b-ui`, rama `docs/132-ui`.
> **Insumos:** issue #132 (9 AC); `docs/design/especificacion-MIT-M7-US03-revision.md`; la UI real de
> #130 (`web/contexto_declarado.py`, `templates/contexto_declarado.html`) y el diseño de #131
> (`docs/design/ui-MIT-M7-correspondencia.md`); `docs/design/ui-MIT-M7-declarar-carpeta.md`;
> `CLAUDE.md` §6; `services/declaraciones_carpeta.py`, `services/correspondencias_contexto.py`,
> `models/__init__.py` (`LocalAlias`, `CorrespondenciaContexto`).
> **Decisiones ratificadas que asume este documento (P-A…P-G):** los alias aprendidos existentes
> pasan a **`propuesto`** (P-A); `LocalAlias` usa versión + historial JSONB (P-B); el alias importado
> **solo se administra**, no se consume en #132 (P-C); las declaraciones y correspondencias de
> importación son **solo lectura** (P-D); un alias aprendido **activo** sigue alimentando el matcher
> tras consentimiento (P-E); **sin activación masiva** (P-F); se permite alias importado global
> (P-G). Si alguna no se ratificó así, el copy de estados/efectos debe ajustarse antes de implementar.
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**; el documento fija lo que la
> implementación debe verificar.

---

## 0. Resumen

Hoy las decisiones reutilizables están repartidas: «Contexto declarado» lista declaraciones, la UI
de correspondencias (131-b) listará correspondencias, y los alias aprendidos de B13 **no tienen
pantalla ni ciclo de vida**. 132-b añade **una sola pantalla**, «Decisiones reutilizables», que une
las cuatro fuentes y permite entender qué se aplica, qué es una sugerencia y qué está pendiente de
consentimiento, sin crear ni ejecutar nada.

1. **Inventario único** con declaraciones de carpeta, correspondencias, alias aprendidos y alias
   importados.
2. **Fila** con naturaleza (confirmada / sugerencia / pendiente), tipo, origen, estado, alcance,
   destino, efectos previstos, versión, fecha y conflicto visible.
3. **Acciones** de ciclo: activar, desactivar, reactivar y retirar aliases de uno en uno con
   consentimiento explícito; navegación al detalle de declaraciones y correspondencias.
4. **Conflictos** con la prioridad visible (local > importación > aprendido), sin sobrescribir ni
   elegir.
5. **Sin efectos destructivos:** no crea series, no vincula, no mueve archivos, no aplica metadatos y
   no reescribe lo ya confirmado.

**La regla de oro:** el inventario **muestra y administra**, no ejecuta. Un alias pendiente no se
aplica; una sugerencia no es una decisión; una desactivación no borra; una retirada no deshace.

**Presupuesto de entrada:** las frases de entrada nuevas están entre 8 y 12 palabras (inventario 10,
activar 12, reactivar 11, retirar 8); ninguna supera 20.

---

## 1. Entrada y estructura

### 1.1 Desde «Contexto declarado» (130-b, ya en `main`)

- En la cabecera de «Contexto declarado», junto a los enlaces de vuelta, se añade:
  **«Decisiones reutilizables»** (2 palabras; neutro) → `/ui/pendientes/carpetas/decisiones`.
- No se añade un botón principal a «Contexto declarado»; sigue siendo una pantalla de lectura.
- Si la UI de #131-b está presente, «Correspondencias» añade el mismo enlace en su cabecera.
- **Vuelta:** la pantalla de inventario enlaza a **«Contexto declarado»** y, si existe, a
  **«Correspondencias»**; no inventa una URL de retorno arbitraria.

### 1.2 Cabecera del inventario

- **H1 «Decisiones reutilizables»** (2 palabras, Anton).
- Entrada: **«Consulta y administra lo que ZascArr reutiliza en nuevas interpretaciones.»** (10 palabras).
- Línea de efectos: **«Desactivar o retirar no deshace nada ya decidido; no mueve archivos.»**
- Segunda línea, breve: **«Nada se activa solo: los alias pendientes necesitan tu confirmación.»**
- **Sin botón principal**: la pantalla es de administración, no de creación. No hay acciones
  masivas, ni «Activar todos», ni selección múltiple.

### 1.3 Columnas conceptuales y presentación

La fila tiene estas **columnas conceptuales**; a 320 px se presentan como **tarjetas**, no como una
tabla de nueve columnas:

| Columna | Qué contiene |
|---|---|
| **Naturaleza** | «Decisión confirmada» / «Sugerencia» / «Pendiente de activar» |
| **Tipo** | «Declaración de carpeta» / «Correspondencia» / «Alias aprendido» / «Alias importado» |
| **Origen** | «Local» / «Importación» / «Aprendido» |
| **Estado** | «Activa» / «Desactivada» / «Retirada»; en alias, «Pendiente de activar» |
| **Alcance** | carpeta y subcarpetas / global; para correspondencia, también «Se aplica a» |
| **Destino** | serie o publicación, cuando existe |
| **Efectos previstos** | qué afecta a nuevas evaluaciones y qué no |
| **Versión y fecha** | «Versión 2 · 10 nov 2026»; fecha si consta |
| **Conflicto** | chip «Conflicto visible» y alternativas, si consta |
| **Acciones** | ciclo de vida y «Ver detalle» en declaraciones/correspondencias |

- **No se usa una tabla** en 320 px. Cada fila es un `<li>` de una lista, con `<dl>` para los pares
  etiqueta/valor. El tipo y el origen se distinguen con **texto**, no solo con color.
- Las tarjetas se pueden leer sin desplazamiento horizontal; la ruta, el nombre reconocido y el
  destino tienen `overflow-wrap: anywhere`.

---

## 2. Naturaleza: confirmada, sugerencia o pendiente

Toda fila empieza con una etiqueta textual visible; es la primera distinción de AC1:

| Naturaleza | Cuándo | Texto de apoyo |
|---|---|---|
| **Decisión confirmada** | Declaración/correspondencia local; alias aprendido que ya fue activado (activo, desactivado o retirado) | «La has decidido tú.» |
| **Sugerencia** | Declaración/correspondencia de importación; alias importado | «Sugerencia; no es una decisión local.» |
| **Pendiente de activar** | Alias aprendido/importado en estado `propuesto` | «No se aplica hasta que lo actives.» |

- La etiqueta va en una línea propia, con tipografía de texto (no un color): se puede distinguir en
  blanco y negro y con `forced-colors`.
- Los chips de **tipo** y **origen** acompañan a la naturaleza; no la sustituyen.
- Una declaración local retirada sigue siendo «Decisión confirmada» (histórica) aunque su estado sea
  «Retirada»: la naturaleza dice quién la tomó, no si está vigente.
- Un alias importado activo sigue siendo «Sugerencia»: activarlo no lo convierte en decisión local.
- Una sugerencia importada **no se presenta nunca** como si fuera local.

---

## 3. Agrupación, orden y filtros

### 3.1 Agrupación por estado

La lista se agrupa en secciones por estado, de arriba abajo:

1. **Pendientes de activar (N)** — solo alias con estado `propuesto`.
2. **Activas (N)**.
3. **Desactivadas (N)**.
4. **Retiradas (N)**.

- Las secciones sin filas no se pintan.
- La sección pendiente es la primera para que el consentimiento esté a la vista; no se activa sola.
- Si no hay ninguna fila, se pinta el vacío total (§8.1), no cuatro secciones vacías.
- Si hay filtros y no hay resultados, se pinta el vacío de filtros (§8.2).

### 3.2 Orden dentro de cada sección

Dentro de una sección, las filas se ordenan por **prioridad explícita** y, a igualdad, por tipo y
ruta/nombre:

1. **Decisiones locales** (declaraciones y correspondencias locales).
2. **Sugerencias de importación** (declaraciones/correspondencias importadas y alias importados).
3. **Alias aprendidos**.

Así el orden de la lista también enseña la prioridad contractual (local > importación > aprendido),
sin depender del color. Ante un conflicto, la fila local queda por delante de la sugerencia o del
alias.

### 3.3 Filtros

Un formulario GET, sin JavaScript nuevo, con etiquetas visibles:

- **Tipo:** Todas / Declaraciones de carpeta / Correspondencias / Alias aprendidos / Alias importados.
- **Estado:** Todos / Pendientes de activar / Activas / Desactivadas / Retiradas.
- **Origen:** Todos / Local / Importación / Aprendido.
- **Carpeta:** texto que contiene, comparado sin mayúsculas ni tildes (mismo criterio que #397).
  Ayuda: **«Filtra por carpeta. Los alias globales no tienen carpeta.»**.
- **Incluir historial** (checkbox): añade las versiones cerradas dentro de cada fila, en un
  `<details>`; por defecto solo se ve la versión vigente.
- **Filtrar** (botón neutro) y **Limpiar filtros** (enlace).

- Los filtros son combinables y viven en la URL (GET); no hay estado de servidor.
- Un valor inválido se descarta y se avisa en la misma página con 200, nunca 422/500:
  - **«El filtro de tipo no es válido; se ha quitado.»**
  - **«El filtro de estado no es válido; se ha quitado.»**
  - **«El filtro de origen no es válido; se ha quitado.»**
  - **«La carpeta del filtro es demasiado larga; se ha recortado.»**
- El recuento de cada sección es el de las filas que pasan los filtros.
- No hay paginación compleja: se limita la lista (por ejemplo, 200 filas) y se avisa:
  **«Se muestran las primeras 200 decisiones. Acota con los filtros.»**.
- **No hay botón principal** en la pantalla; el botón «Filtrar» es neutro.

### 3.4 Wireframe del inventario

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Contexto declarado»              │
│ DECISIONES REUTILIZABLES                     │
│ Consulta y administra lo que ZascArr         │
│ reutiliza en nuevas interpretaciones.        │
│ Desactivar o retirar no deshace nada ya      │
│ decidido; no mueve archivos.                 │
│ Nada se activa solo: los alias pendientes    │
│ necesitan tu confirmación.                   │
│                                              │
│ Tipo   [ Todas ▾ ]   Estado [ Todas ▾ ]      │
│ Origen [ Todos ▾ ]   Carpeta [ ………… ]        │
│ [ ] Incluir historial       [ Filtrar ]      │
│                                              │
│ PENDIENTES DE ACTIVAR (1)                    │
│ ┌──────────────────────────────────────────┐ │
│ │ PENDIENTE DE ACTIVAR                     │ │
│ │ [Alias aprendido] [Aprendido] [Pendiente]│ │
│ │ Coincide con «batman»                    │ │
│ │ Destino: Serie «Batman (2019)»           │ │
│ │ Sin carpeta: nombres nuevos              │ │
│ │ No se aplica hasta que lo actives.       │ │
│ │ [Activar] [Retirar]                      │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ ACTIVAS (2)                                  │
│ ┌──────────────────────────────────────────┐ │
│ │ DECISIÓN CONFIRMADA                      │ │
│ │ [Declaración de carpeta] [Local] [Activa]│ │
│ │ CÓMICS / CARLOS GIMÉNEZ                  │ │
│ │ Por autor · Solo esta carpeta · Versión 2│ │
│ │ 10 nov 2026                              │ │
│ │ [Ver detalle] [Cambiar] [Desactivar]     │ │
│ │ [Retirar]                                │ │
│ └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### 3.5 Historial

- Con **Incluir historial** marcado, cada fila muestra un `<details>` **«Historial (N versiones)»** con las versiones cerradas: versión, fecha, estado y, en alias, el evento/motivo.
- Sin esa marca, el historial no se carga en la página.
- Para alias aprendidos, el historial es la lista de eventos del JSONB (`aprendizaje`, `migración`,
  `activación`, `desactivación`, `retirada`, `conflicto`); para el resto, las versiones del servicio.
- Si no hay versiones anteriores: **«No hay versiones anteriores.»**.
- El historial es solo lectura; no se borra ni se edita desde la UI.
- La pantalla se sirve con un **número fijo de consultas** (una por fuente, más destinos e historial
  en bloque si se piden); no hay una consulta por fila.

---

## 4. La fila

### 4.1 Campos comunes

```
┌─ 360 px ─────────────────────────────────────┐
│ DECISIÓN CONFIRMADA                          │
│ [Declaración de carpeta] [Local] [Activa]    │
│ CÓMICS / CARLOS GIMÉNEZ                      │
│ Por autor · Solo esta carpeta · Versión 2    │
│ 10 nov 2026                                  │
│                                              │
│ Efectos: solo orienta; no crea series ni     │
│ vincula archivos. No cambia lo ya decidido.  │
│                                              │
│ [Ver detalle] [Cambiar] [Desactivar]         │
│ [Retirar]                                    │
└──────────────────────────────────────────────┘
```

Elementos, en este orden:

1. **Naturaleza** (§2).
2. **Chips de tipo, origen y estado**.
3. **Identidad:** ruta de carpeta o nombre reconocido (alias).
4. **Alcance:** «Solo esta carpeta» / «Esta carpeta y sus subcarpetas» / «Global, sin carpeta».
5. **Destino**, si aplica: «Serie «…»» / «Publicación «…»».
6. **Efectos previstos**, en una o dos líneas.
7. **Versión y fecha:** «Versión N · fecha»; si no consta, «Fecha no registrada».
8. **Conflicto visible**, si consta.
9. **Acciones**, todas neutras.
10. **Historial** plegado si se pidió.

### 4.2 Según el tipo

| Tipo | Identidad y alcance | Destino | Efectos visibles (ejemplo) |
|---|---|---|---|
| **Declaración de carpeta** | Ruta + «Por autor»/«Por publicación» + solo carpeta/subcarpetas | — | **«Solo orienta; no crea series ni vincula archivos. No cambia lo ya decidido.»** |
| **Correspondencia** | Ruta heredada + «Se aplica a» | Serie o publicación | **«Solo prepara propuestas; no vincula ni aplica metadatos. No cambia lo ya decidido.»** |
| **Alias aprendido** | «Coincide con «…»»; «Sin carpeta: nombres nuevos»; la decisión local manda | Serie | **«Afecta a cómo se reconocen nombres nuevos; no cambia lo ya decidido.»** |
| **Alias importado** | «Coincide con «…»»; global o ruta | Serie | **«Sugerencia importada; subordinada a la decisión local. No se aplica automáticamente en esta entrega.»** |

- **Alias aprendido en estado `propuesto`:** **«No se aplica hasta que lo actives.»**.
- **Alias desactivado o retirado:** **«No se aplica a nuevas interpretaciones.»**.
- **Declaración/correspondencia importada:** **«Sugerencia importada; se muestra, no se gestiona desde aquí.»**.
- **Alias importado activo:** se muestra como «Sugerencia»; su efecto no es ejecutar, sino quedar
  disponible para una integración posterior (P-C). No se promete que el matcher lo use.
- **Alias aprendido activo:** si no hay una decisión local que lo bloquee, puede afectar a nuevas
  interpretaciones; nunca a lo ya decidido (P-E).
- **Sin lenguaje interno:** no se dice «matcher», «precedencia», «patrón», «metadata_source» ni
  nombres de columnas.

### 4.3 Versión, fecha y conflicto

- **Versión:** «Versión 2»; no se muestra el identificador interno.
- **Fecha:** «10 nov 2026»; si no consta, **«Fecha no registrada»**. No se inventa con
  `created_at` cuando el dato no corresponde.
- **Conflicto visible:** chip **«Conflicto visible»** y un `<details>`:
  - resumen **«Ver la otra decisión»**;
  - **«Hay otra decisión para esta carpeta.»**
  - **«Manda la decisión local; no se sobrescribe.»**
  - **«No se elige ninguna aquí.»**
  - alternativas con tipo, origen, estado y destino; **sin radios ni botones de elegir**.
- Si el conflicto es entre alias importado y aprendido:
  **«El alias importado tiene prioridad sobre el aprendido.»**, sin borrar el aprendido.
- Si el conflicto es entre local y alias:
  **«Este alias no se aplica en carpetas con decisión local.»**.
- **La UI no decide ni reordena por color**; solo pinta la prioridad del contrato y deja las
  acciones de ciclo.

```
┌─ 360 px ─────────────────────────────────────┐
│ [Conflicto visible]                          │
│ ▸ Ver la otra decisión                       │
│                                              │
│ Hay otra decisión para esta carpeta.         │
│ Manda la decisión local; no se sobrescribe.  │
│ No se elige ninguna aquí.                    │
│                                              │
│ Otra decisión: Declaración local · Activa    │
│ Destino: Serie «Batman (2019)»               │
└──────────────────────────────────────────────┘
```

### 4.4 Acciones por fila

Todas neutras; **no hay botón principal en la lista**.

| Tipo / estado | Acciones |
|---|---|
| Declaración local activa | «Ver detalle», «Cambiar», «Desactivar», «Retirar» |
| Declaración local desactivada | «Ver detalle», «Cambiar», «Reactivar», «Retirar» |
| Declaración local retirada | «Ver detalle» (historial); sin ciclo |
| Declaración de importación | «Ver detalle» solo lectura; sin ciclo (P-D) |
| Correspondencia local activa | «Ver detalle», «Cambiar», «Desactivar», «Retirar» |
| Correspondencia local desactivada | «Ver detalle», «Cambiar», «Reactivar», «Retirar» |
| Correspondencia retirada | «Ver detalle»; sin ciclo |
| Correspondencia de importación | Solo lectura (P-D) |
| Alias aprendido **pendiente** | «Activar», «Retirar» |
| Alias aprendido **activo** | «Desactivar», «Retirar» |
| Alias aprendido **desactivado** | «Reactivar», «Retirar» |
| Alias aprendido **retirado** | Sin acciones; historial |
| Alias importado **pendiente** | «Activar», «Retirar» |
| Alias importado **activo** | «Desactivar», «Retirar» |
| Alias importado **desactivado** | «Reactivar», «Retirar» |
| Alias importado **retirado** | Sin acciones; historial |

- **Nunca** «Borrar», «Activar todos», «Seleccionar todo» ni una acción que afecte a varias filas.
- **Activar** y **Reactivar** siempre pasan por una pantalla de confirmación (§5).
- **Desactivar** no pide confirmación: es reversible.
- **Retirar** pide confirmación y avisa de que es terminal y de que el historial se conserva (§6).
- «Ver detalle» lleva a la pantalla de declaración/correspondencia ya existente o a la de 131-b;
  no se duplican formularios.
- Las acciones de declaración/correspondencia reutilizan los servicios y formularios de #130/#131;
  al terminar vuelven al inventario con un aviso. No se crea una segunda lógica de negocio.
- No se edita el nombre ni el destino de un alias: solo se activa, desactiva, reactiva o retira.

---

## 5. Activar un alias: consentimiento explícito

### 5.1 Cuándo

- Alias aprendido o importado en estado **`propuesto`**: acción «Activar».
- Alias **`desactivado`**: acción «Reactivar»; misma pantalla de confirmación adaptada.
- Un alias **`retirado`** no se activa ni se reactiva.
- **Ninguna otra acción activa un alias**: guardar una declaración/correspondencia, confirmar una
  vinculación, aceptar un alta o abrir el inventario no activa nada. Tampoco se activa por
  coincidencia de nombre, frecuencia o por estar en la lista.
- **No hay activación masiva** (P-F): no hay checkbox de selección ni botón «Activar todos».

### 5.2 Pantalla «Activar alias»

- **H1 «Activar alias»** (2 palabras).
- Entrada: **«Este alias se usará en nuevas interpretaciones; no cambia lo ya decidido.»** (12 palabras).
- Resumen:
  - **«Coincide con «…»»**;
  - **«Destino: Serie «…»»**;
  - **«Origen: Aprendido / Importación»**;
  - **«Alcance: Global, sin carpeta»** o la carpeta;
  - **«Versión: 2»**.
- Texto:
  - **«Activar este alias no activa ningún otro.»**
  - **«No se aplica a lo ya decidido ni mueve archivos.»**
  - Si es importado: **«Sugerencia importada. En esta entrega no se aplica automáticamente; queda
    disponible para una integración posterior.»**
- Botones:
  - principal **«Sí, activar este alias»**;
  - neutro **«Cancelar»**, que vuelve sin cambiar nada.
- Tras confirmar: **«Alias activado. Solo afecta a nuevas interpretaciones.»**; vuelve al
  inventario con el estado actualizado.

```
┌─ 360 px ─────────────────────────────────────┐
│ ACTIVAR ALIAS                                │
│ Este alias se usará en nuevas                │
│ interpretaciones; no cambia lo ya decidido.  │
│                                              │
│ Coincide con «batman»                        │
│ Destino: Serie «Batman (2019)»               │
│ Origen: Aprendido · Versión 2                │
│ Alcance: Global, sin carpeta                 │
│                                              │
│ Activar este alias no activa ningún otro.    │
│ No se aplica a lo ya decidido ni mueve       │
│ archivos.                                    │
│                                              │
│ [ Sí, activar este alias ]  ← único primary  │
│ [ Cancelar ]                                 │
└──────────────────────────────────────────────┘
```

### 5.3 Reactivar

- **H1 «Reactivar alias»**.
- Entrada: **«Volverá a aplicarse a nuevas interpretaciones; no cambia lo ya decidido.»** (11 palabras).
- Mismo resumen, mismos avisos y **misma confirmación individual**; principal
  **«Sí, reactivar este alias»**.
- Tras confirmar: **«Alias reactivado.»**.
- Un alias desactivado no se reactiva por abrir la pantalla ni por otra acción.

### 5.4 Desactivar

- No pide confirmación: es reversible.
- Acción en la fila; tras guardar: **«Alias desactivado. Puedes reactivarlo cuando quieras.»**
; estado **Desactivada**; **«No se aplica a nuevas interpretaciones.»**.
- No borra el historial ni el alias; no mueve nada.

---

## 6. Retirar

Se aplica a declaraciones, correspondencias y alias locales/importados (los de importación de
declaraciones/correspondencias son solo lectura, P-D). Pantalla de confirmación, nunca un diálogo
nativo:

- **H1 «Retirar la decisión»** o, si el tipo es alias, **«Retirar alias»**.
- Entrada: **«Dejará de aplicarse y no se podrá reactivar.»** (8 palabras).
- **«El historial se conserva. No se mueve ni se borra nada.»**.
- Resumen: tipo, identidad, estado, versión y, si aplica, destino.
- Principal **«Sí, retirar»**; neutro **«Cancelar»**.
- Tras retirar: **«Decisión retirada. El historial se conserva.»**; la fila pasa a
  **Retiradas**, sin acciones de reactivar. Para volver a usarla hay que crear una decisión nueva;
  no se «des-retira».
- **No hay borrado** en la UI; retirar conserva filas, versiones e historial.
- Imported alias: retirar permitido (solo se administra); imported declaration/correspondence: sin
  acciones (P-D).

---

```
┌─ 360 px ─────────────────────────────────────┐
│ RETIRAR LA DECISIÓN                          │
│ Dejará de aplicarse y no se podrá reactivar. │
│                                              │
│ El historial se conserva. No se mueve ni se  │
│ borra nada.                                  │
│                                              │
│ Alias aprendido · «batman»                   │
│ Destino: Serie «Batman (2019)» · Versión 2   │
│                                              │
│ [ Sí, retirar ]  ← único primary             │
│ [ Cancelar ]                                 │
└──────────────────────────────────────────────┘
```

## 7. Conflictos y prioridad

- La pantalla muestra una **leyenda** visible bajo la entrada:
  **«Si hay conflicto, manda la decisión local; después el alias importado; después el aprendido.»**
  **«El orden de la lista sigue esa prioridad.»**
- Las filas conflictivas llevan chip **«Conflicto visible»** y el `<details>` de §4.3.
- **No se sobrescribe** ninguna decisión local: ni un alias importado ni uno aprendido la sustituyen.
- **No se elige** ninguna alternativa: no hay radios, ni botón «usar esta», ni una acción que
  convierta un alias en decisión local.
- Resolver es explícito: desactivar/retirar el alias que no se quiere, o cambiar/retirar la
  decisión local desde su detalle. La UI no hace esa elección por la persona.
- **No se extiende por parecido:** ni por nombre, ni por carpeta vecina, ni por destino parecido.

---

## 8. Estados vacíos y errores

### 8.1 Inventario vacío

- **«Todavía no hay decisiones reutilizables.»**
- **«Aquí verás declaraciones, correspondencias y alias cuando existan.»**
- **«Nada se aplica solo: los alias pendientes necesitan tu confirmación.»**
- Enlaces neutros: **«Ir a «Contexto declarado»»** y **«Volver a «Pendientes por carpeta»»**
- No hay botón de crear: el inventario no crea declaraciones, correspondencias ni alias.

### 8.2 Sin resultados de filtros

- **«Ninguna decisión coincide con estos filtros.»**
- **«Quitar filtros»** devuelve a la lista completa.
- No se pinta el vacío total como si no hubiera decisiones.

### 8.3 Error de lectura

- **«No se han podido leer las decisiones reutilizables. No se muestra nada a medias. Vuelve a
  intentarlo.»**
- 503, sin recuentos parciales; enlace **«Reintentar»**.

### 8.4 Errores de acción

- Alias ya no pendiente: **«Ese alias ya no está pendiente de activar. Vuelve al inventario.»**
- Alias retirado: **«Un alias retirado no se puede activar.»**
- Alias inexistente: **«Ese alias ya no existe. Vuelve a «Decisiones reutilizables».»**
- Acción sobre una decisión retirada: **«Una decisión retirada no se puede reactivar.»**
- Declaración/correspondencia no encontrada: **«Esa decisión ya no existe. Vuelve al inventario.»**
- Error al guardar: **«No se ha podido guardar el cambio. No se ha cambiado nada. Vuelve a
  intentarlo.»**
- Los errores conservan la fila y los filtros; el foco va al aviso `role="alert"`.

### 8.5 Fuente vacía

- Si no hay alias importados, su sección no se pinta; no es un error.
- Si no hay historial para una fila: **«No hay versiones anteriores.»**.
- Si no hay fecha: **«Fecha no registrada»**, no una fecha inventada.

---

## 9. Accesibilidad y 320 px

- **Formulario de filtros:** etiquetas visibles, selects nativos, campo de texto y checkbox con
  `<label>`; a 320 px se apilan sin scroll horizontal.
- **Lista:** `<ul>`/`<li>` con `<dl>` para los pares; **no tabla** en 320 px. Cada fila conserva
  orden de lectura: naturaleza → tipo/origen/estado → identidad → alcance/destino → efectos →
  versión/fecha → conflicto → acciones.
- **Acciones:** `<button>`/`<a>` reales; no `<div>` clicables ni formularios anidados. Las acciones
  repetidas son neutras; el botón principal solo existe en las pantallas de confirmación.
- **Teclado:** Tab recorre filtros, filas y acciones; `<details>` se abre con Enter/Espacio; foco
  visible en enlaces y botones.
- **Foco:** tras una acción correcta, el aviso `role="status"` se anuncia y el foco vuelve a un punto
  estable de la lista; tras un error, va al `role="alert"`. En las confirmaciones, al H1.
- **Estado sin color:** naturaleza, tipo, origen y estado son texto; los chips no son el único
  indicador.
- **Textos ≥14 px**; H1 en Anton (≤3 palabras); rutas, nombres y frases en `.titulo-frase` (Archivo).
- **Contraste:** tokens de `web.css`; sin colores nuevos; se comprueba con la prueba existente.
- **320 px:** rutas, nombres reconocidos y destinos largos con `overflow-wrap: anywhere`; chips y
  acciones con `flex-wrap`; sin tabla ni scroll lateral.
- **Sin diálogos nativos, sin `hx-confirm`, sin JS nuevo**: filtros GET, acciones POST con
  redirección (PRG), confirmaciones en pantalla completa.

---

## 10. Tabla de estados y textos finales

| # | Pantalla / situación | Texto visible | Comportamiento |
|---|---|---|---|
| 1 | Inventario vacío | «Todavía no hay decisiones reutilizables.» + «Aquí verás declaraciones, correspondencias y alias cuando existan.» | Enlaces a Contexto declarado y Pendientes |
| 2 | Filtros sin resultados | «Ninguna decisión coincide con estos filtros.» | «Quitar filtros» |
| 3 | Filtro inválido | «El filtro de tipo no es válido; se ha quitado.» | 200 con aviso |
| 4 | Fila confirmada local | «Decisión confirmada» + tipo/origen/estado + alcance + efectos + versión/fecha | Acciones locales |
| 5 | Fila sugerencia importada | «Sugerencia» + «Sugerencia importada; se muestra, no se gestiona desde aquí.» | Solo detalle, sin ciclo (P-D) |
| 6 | Fila pendiente de activar | «Pendiente de activar» + «No se aplica hasta que lo actives.» | «Activar», «Retirar» |
| 7 | Alias aprendido activo | «Decisión confirmada» + «Afecta a cómo se reconocen nombres nuevos; no cambia lo ya decidido.» | Desactivar, Retirar |
| 8 | Alias aprendido desactivado | «Desactivada» + «No se aplica a nuevas interpretaciones.» | Reactivar, Retirar |
| 9 | Alias aprendido retirado | «Retirada: no se aplica a nuevas interpretaciones. El historial se conserva.» | Sin acciones |
| 10 | Alias importado activo | «Sugerencia» + «Sugerencia importada; subordinada a la decisión local. No se aplica automáticamente en esta entrega.» | Desactivar, Retirar |
| 11 | Alias importado pendiente | «Pendiente de activar» + «No se aplica hasta que lo actives.» | Activar, Retirar |
| 12 | Conflicto local/alias | «Conflicto visible» + «Hay otra decisión para esta carpeta.» + «Manda la decisión local; no se sobrescribe.» | Detalles con alternativas; sin elegir |
| 13 | Conflicto importado/aprendido | «Conflicto visible» + «El alias importado tiene prioridad sobre el aprendido.» | Sin elegir; sin borrar |
| 14 | Activar alias | «Activar alias» + «Este alias se usará en nuevas interpretaciones; no cambia lo ya decidido.» | «Sí, activar este alias» / «Cancelar» |
| 15 | Activar alias importado | «Sugerencia importada. En esta entrega no se aplica automáticamente; queda disponible para una integración posterior.» | Confirmación individual |
| 16 | Activar correcto | «Alias activado. Solo afecta a nuevas interpretaciones.» | Estado «Activa» |
| 17 | Reactivar alias | «Reactivar alias» + «Volverá a aplicarse a nuevas interpretaciones; no cambia lo ya decidido.» | «Sí, reactivar este alias» |
| 18 | Reactivar correcto | «Alias reactivado.» | Estado «Activa» |
| 19 | Desactivar alias | «Alias desactivado. Puedes reactivarlo cuando quieras.» | Estado «Desactivada» |
| 20 | Retirar | «Retirar alias» / «Retirar la decisión» + «Dejará de aplicarse y no se podrá reactivar.» | Confirmación |
| 21 | Retirar correcto | «Decisión retirada. El historial se conserva.» | Estado «Retirada»; sin reactivar |
| 22 | Historial | «Historial (N versiones)» + versiones/fechas/estados | Solo lectura |
| 23 | Sin historial | «No hay versiones anteriores.» | — |
| 24 | Fecha ausente | «Fecha no registrada» | No se inventa |
| 25 | Error de lectura | «No se han podido leer las decisiones reutilizables. No se muestra nada a medias. Vuelve a intentarlo.» | 503 + Reintentar |
| 26 | Alias ya no pendiente | «Ese alias ya no está pendiente de activar. Vuelve al inventario.» | Aviso; sin cambio |
| 27 | Alias retirado | «Un alias retirado no se puede activar.» | Sin cambio |
| 28 | Acción sobre retirada | «Una decisión retirada no se puede reactivar.» | Sin cambio |
| 29 | Guardar falla | «No se ha podido guardar el cambio. No se ha cambiado nada. Vuelve a intentarlo.» | Conserva fila |
| 30 | Límite de lista | «Se muestran las primeras 200 decisiones. Acota con los filtros.» | Sin paginación compleja |

---

## 11. Decisiones de copy

1. **«Decisiones reutilizables»** es el nombre de la pantalla; **«decisión confirmada»**,
   **«sugerencia»** y **«pendiente de activar»** son las tres naturalezas. No se usa «perfil»,
   «regla global» ni «aprendizaje invisible».
2. **Tipos en llano:** «Declaración de carpeta», «Correspondencia», «Alias aprendido», «Alias
   importado». El tipo y el origen son chips separados; no se mezclan.
3. **Origen:** «Local», «Importación», «Aprendido». Una importación nunca se presenta como decisión
   local; un alias aprendido no se presenta como importado.
4. **Efectos explícitos:** qué afecta a nuevas evaluaciones y qué no. **No cambia lo ya decidido**,
   **no mueve archivos**, **no crea series**, **no vincula**, **no aplica metadatos**.
5. **Prioridad en llano:** «manda la decisión local; después el alias importado; después el
   aprendido». Se muestra como leyenda y como orden de lista; no se usa la palabra «precedencia» en
   la superficie.
6. **Conflicto sin elección:** se ven las dos decisiones; no hay radio, botón de «usar» ni
   sobrescritura. Resolver es desactivar/retirar o cambiar la otra decisión explícitamente.
7. **Activar es individual y consentido:** pantalla propia, un alias cada vez, sin selección
   múltiple ni «activar todos». Ninguna otra acción activa un alias.
8. **Alias importado:** se administra, pero **no se aplica automáticamente en esta entrega** (P-C);
   no se promete un efecto que no existe. Su activación lo deja disponible para una integración
   posterior.
9. **Alias aprendido activo:** puede afectar a nuevas interpretaciones (P-E), pero no a lo ya
   decidido; la decisión local manda. Los existentes migrados quedan **pendientes** (P-A).
10. **Desactivar reversible; retirar terminal:** no se llama «borrar» a retirar; el historial se
    conserva y no se mueve nada.
11. **Historial visible pero plegado:** versión/fecha en la fila; versiones cerradas dentro de
    `<details>` cuando se pide. No se llena la pantalla de versiones.
12. **Sin jerga:** no aparecen «matcher», «patrón normalizado», «metadata_source», «precedencia»,
    `uuid` ni nombres de columnas. «Coincide con» sustituye a «patrón»; «manda» a «precedencia».
13. **Sin fechas inventadas:** si el dato no consta, «Fecha no registrada»; no se usa `created_at`
    como si fuera la fecha de la decisión.
14. **Sin acciones destructivas:** no hay borrar, no hay revertir vinculaciones, no hay activación
    masiva.

---

## 12. Lo que deja fuera

- Crear declaraciones, correspondencias o alias; el inventario solo lee y administra.
- Crear series, publicaciones o ediciones; vincular o mover archivos; aplicar metadatos.
- Resolver conflictos automáticamente, elegir por prioridad, fecha, frecuencia o parecido.
- Consumir el alias importado en el matcher (P-C; sería 132-c).
- Revertir vinculaciones, asignaciones, series o archivos ya confirmados.
- Borrar historial o fusionar alias.
- Importar catálogos o alias; la tabla de importados la llena una importación externa.
- Paginación compleja; la lista se acota con filtros y un límite.
- Pantalla de detalle de alias: su historial va en la fila; el detalle de declaraciones y
  correspondencias es el de #130/#131-b.
- Migración, red, JS nuevo o dependencias nuevas.
- **Medición real** de navegador, lector, 320 px y Pi: **NOT RUN**.

---

## 13. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Inventario único de cuatro fuentes | Una pantalla lista declaraciones, correspondencias, alias aprendidos e importados |
| 2 | Tipo/origen sin jerga y naturaleza visible | Chips separados; «Decisión confirmada» / «Sugerencia» / «Pendiente de activar» |
| 3 | Fila con alcance/efectos/versión/fecha | Cada tarjeta muestra los campos y la fecha o «Fecha no registrada» |
| 4 | Agrupación y filtros | Secciones por estado; filtros tipo/estado/origen/carpeta; historial |
| 5 | Activación individual con consentimiento | Pantalla «Activar alias»; sin selección múltiple ni activación por otra acción |
| 6 | Desactivar/reactivar/retirar | Estados y acciones; retirar terminal con confirmación; historial conservado |
| 7 | Conflicto visible y prioridad | Leyenda, orden y `<details>`; local > importación > aprendido; sin elegir |
| 8 | Efectos previstos/no retroactivos | Copy de fila y de confirmación; no se mueve/crea/vincula |
| 9 | Importadas solo lectura | Filas importadas sin acciones de ciclo (P-D) |
| 10 | Accesibilidad/320 | Teclado, foco, 14 px, sin tabla ni scroll lateral, no solo color |
| 11 | Sin JS nuevo | GET de filtros y POST/PRG de acciones; sin script nuevo |
| 12 | Sin jerga/ids internos | Buscar en render los términos internos fuera de la traza/copy de diseño |

**PASS de este documento:** inventario, filas, agrupación, filtros, acciones, conflictos,
confirmaciones y condiciones de accesibilidad decididos y coherentes con #132, la spec MIT-M7-US03 y
`CLAUDE.md` §6.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos y
Pi. No se declaran.