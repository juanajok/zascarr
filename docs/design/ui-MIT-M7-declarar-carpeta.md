# UX — Declarar el significado de una carpeta (MIT-M7-US01, #130, rebanada 130-b)

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas,
> plantillas, migraciones ni servicios. Fija el flujo, el copy, los estados y las condiciones de
> accesibilidad; la implementación los lleva al código.
> **Base:** `origin/main` = `a7598cab948f71e890544629bea80e1ea4860a3f` (2026-11-10), worktree
> `.squad/wt-130b-ui`, rama `docs/130-ui`.
> **Insumos:** issue #130 (9 AC) y la ratificación del PO del 2026-11-10;
> `docs/design/especificacion-MIT-M7-contexto-declarado.md` (modelo y contrato);
> `docs/design/benchmark-MIT-M7-contexto-declarado.md`; `CLAUDE.md` §6; la pantalla
> `web/pendientes.py` / `web/templates/carpetas.html`; el asistente M3
> (`web/asistente_carpetas.py`, `templates/asistente_carpeta.html`) y el servicio 130-a
> `services/declaraciones_carpeta.py` (rama `feat/130-declaracion`, no fusionada al escribir esto).
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**; el documento fija lo que la
> implementación debe verificar.

---

## 0. Resumen

La pantalla de revisión ya agrupa los pendientes por carpeta y ofrece «Elegir la serie de esta
carpeta» (M3). **No dice qué significa la carpeta.** 130-b añade una acción y una pantalla para
**declararlo explícitamente**, sin inferirlo del nombre y sin tocar nada:

1. **Entrada:** en cada grupo de «Pendientes por carpeta», la acción **«Declarar esta carpeta»**,
   con el aviso de que no crea series, no mueve archivos y no vincula nada. En la cabecera, un
   enlace a **«Contexto declarado»**
2. **Declaración:** elegir **Por autor** o **Por publicación**, ver la **ruta relativa** (no
   editable) y decidir si se **incluyen las subcarpetas**. Si el alcance se amplía, una pantalla de
   **confirmación explícita**.
3. **No hace:** el aviso junto a la acción y el panel de efectos lo dicen antes de guardar: solo
   orienta próximas interpretaciones. No afecta a lo ya decidido.
4. **Ciclo de vida:** **Cambiar** (versión nueva y aviso de que la anterior deja de aplicarse),
   **Desactivar** (reversible), **Reactivar**, **Retirar** (terminal, con confirmación y aviso de
   historial). Estados y origen local/importación visibles; no solo por color.
5. **Pantalla «Contexto declarado»:** lista las declaraciones por estado, con tipo, origen, alcance,
   versión y efectos previstos; vacío, conflictos de alias visibles y errores de ruta.

**La regla de oro:** una declaración **local** es una decisión versionada, no una vinculación; una
declaración de **importación** es una sugerencia visible, nunca una decisión local. Declarar no
confirma una serie, no elige una publicación y no cambia nada del pasado.

**Presupuesto de entrada:** las frases de entrada nuevas están entre 6 y 13 palabras; el aviso de la
acción de grupo, con la aclaración de que no cambia lo ya decidido, tiene 18. Ninguna supera 20.

---

## 1. Entrada desde la revisión por carpeta

### 1.1 En la cabecera de «Pendientes por carpeta»

- Se añade un enlace neutro, no un botón principal:
  **«Contexto declarado»** → `/ui/pendientes/carpetas/contexto`.
- Va en una fila de acciones propias, cerca del título y del enlace de vuelta, para que la persona
  pueda consultar lo ya declarado sin pasar por una carpeta.
- Si no hay declaraciones, el enlace sigue visible: lleva al vacío explicativo con la vuelta.

### 1.2 En cada grupo de carpeta

- En la tarjeta del grupo, junto a la acción M3 existente, se añade:
  **«Declarar esta carpeta»**
- Debajo, en texto pequeño y visible (no en un `title` ni en un tooltip):

  > **No crea series, no mueve archivos, no vincula nada; solo orienta próximas interpretaciones.
  > No cambia lo ya decidido.**

  (18 palabras)
- La acción es un enlace a la pantalla de declaración de **esa** carpeta; la ruta viaja en la URL
  (`?clave=…`) y se valida en servidor. No hay un campo de ruta libre en la revisión.
- El enlace M3 y el de declaración conviven en la misma zona de acciones, pero son dos acciones
  distintas. A 320 px envuelven sin scroll lateral.
- **Si la carpeta ya tiene una declaración**, la tarjeta no necesita saberlo para pintar la acción:
  al abrir la pantalla de declaración se muestra la declaración existente y sus acciones, sin crear
  otra. No se hace una consulta por grupo (evita N+1); la comprobación se hace en la pantalla de
  declaración, que es una sola consulta.
- La tarjeta **no** cambia su orden, sus chips ni el resto de acciones; solo gana una acción más y su
  aviso.

Wireframe de la tarjeta a 320/360 px:

```
┌─ 360 px ─────────────────────────────────────┐
│ CÓMICS / CARLOS GIMÉNEZ                      │
│ [Sin serie] [por confirmar]                  │
│ 52 registros · Sin serie sugerida            │
│                                              │
│ [Elegir la serie de esta carpeta]            │
│ No se crea ni se asigna nada hasta que       │
│ confirmes.                                   │
│                                              │
│ [Declarar esta carpeta]                      │
│ No crea series, no mueve archivos, no        │
│ vincula nada; solo orienta próximas          │
│ interpretaciones. No cambia lo ya decidido.  │
│                                              │
│ ▸ Ver datos y observaciones                  │
│ ▸ Ver registros (52)                         │
└──────────────────────────────────────────────┘
```

- Ambos enlaces son `.btn ghost` neutros; **no se añade un botón principal** a la revisión.
- El aviso se repite en cada tarjeta porque la acción se toma ahí; si la lista es muy larga, sigue
  siendo una frase corta y no un párrafo nuevo por tarjeta.

---

## 2. Pantalla «Contexto declarado»

### 2.1 Estructura

- **H1 «Contexto declarado»** (2 palabras, Anton).
- Entrada: **«Consulta y cambia el significado que has dado a tus carpetas.»** (11 palabras).
- Línea de efectos, visible y breve:
  **«Las declaraciones solo orientan; no crean series ni tocan archivos.»** (10 palabras).
- Enlace de vuelta: **«← Volver a «Pendientes por carpeta»»**, conservando los filtros de la lista
  cuando se llegue desde ella (mismo patrón de contexto que usa el asistente M3).
- La pantalla lista **las versiones vigentes** de cada declaración, agrupadas por estado:
  **Activas**, **Desactivadas**, **Retiradas**. Las retiradas se quedan visibles: retirar no borra
  el historial.
- El historial completo de versiones anteriores no se desarrolla en 130-b; la tarjeta muestra
  **«Versión N»** y el copy dice que el historial se conserva. El inventario/historial completo es
  #132.
- Dentro de cada sección, las tarjetas se ordenan por **ruta ascendente** y, a igualdad, por versión.
  El orden no depende del color ni del estado: las secciones ya separan los estados.

Wireframe a 360 px:

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Pendientes por carpeta»          │
│ CONTEXTO DECLARADO                           │
│ Consulta y cambia el significado que has     │
│ dado a tus carpetas.                         │
│ Las declaraciones solo orientan; no crean    │
│ series ni tocan archivos.                    │
│                                              │
│ ACTIVAS (2)                                  │
│ ┌──────────────────────────────────────────┐ │
│ │ CÓMICS / CARLOS GIMÉNEZ                  │ │
│ │ [Por autor] [Local] [Activa] [Versión 2] │ │
│ │ Alcance: solo esta carpeta.              │ │
│ │ Solo orienta; no crea series ni toca     │ │
│ │ archivos.                                │ │
│ │ [Cambiar] [Desactivar] [Retirar]         │ │
│ └──────────────────────────────────────────┘ │
│ ...                                          │
│ DESACTIVADAS (1)                             │
│ ...                                          │
│ RETIRADAS (1)                                │
│ ...                                          │
└──────────────────────────────────────────────┘
```

### 2.2 Tarjeta de declaración

Cada tarjeta es un `<li>` dentro de una lista por estado; **no una tabla** (a 320 px una tabla de
seis columnas desborda). El título es la **ruta relativa** en `.titulo-frase` (Archivo, no
mayúsculas), con `overflow-wrap: anywhere`.

Elementos, en este orden:

1. **Ruta relativa** (identidad de la declaración). No se muestra una ruta absoluta.
2. **Chips de estado semántico**, siempre con texto:
   - tipo: **«Por autor»** / **«Por publicación»**;
   - origen: **«Local»** / **«Importación»**;
   - estado: **«Activa»** / **«Desactivada»** / **«Retirada»**;
   - versión: **«Versión 2»** (dato, no chip de color).
3. **Alcance:** **«Solo esta carpeta»** o **«Esta carpeta y sus subcarpetas»**
   - Si incluye subcarpetas: «También los archivos que aparezcan después.»
4. **Efectos previstos:** **«Solo orienta: no crea series ni publicaciones, no vincula archivos, no
   los mueve ni renombra.»** y, en una línea aparte, **«No cambia lo ya decidido.»**
5. **Origen/importación:** si es local, no hace falta una frase extra; el chip «Local» basta. Si es
   de importación: **«Sugerencia importada; no es una decisión local.»** Las declaraciones de
   importación **no se cambian ni se retiran desde esta pantalla**; se muestran, pero su gestión es
   de #132. No se presentan como si fueran locales.
6. **Conflicto visible**, si consta: chip **«Conflicto visible»** y un `<details>`:
   - resumen **«Ver las interpretaciones en conflicto»**;
   - **«Hay otra interpretación para esta carpeta. No se elige ninguna aquí.»**;
   - instrucciones de precedencia: la declaración local tiene prioridad; el alias no se borra y
     sigue visible; no se activa ni se aplica ningún alias desde esta pantalla;
   - alternativas identificadas (alias de importación, alias aprendido, otra declaración) con su
     origen; **sin radios ni botones para elegir**.
7. **Acciones**, todas neutras salvo que la pantalla sea de confirmación:
   - **Activa:** «Cambiar» (enlace), «Desactivar» (formulario POST), «Retirar» (enlace a
     confirmación).
   - **Desactivada:** «Cambiar» (enlace), «Reactivar» (formulario POST), «Retirar» (enlace).
     Cambiar una desactivada crea una versión nueva que **sigue desactivada**; el aviso lo dice.
   - **Retirada:** sin acciones. Texto: **«Retirada: no se aplica a nuevas interpretaciones. El
     historial se conserva.»**
   - **Importación:** sin acciones locales; «Se muestra, no se gestiona desde aquí.».
8. Las acciones de varias tarjetas son botones neutros; **no hay botón principal en la lista**
   (el botón principal es el de una pantalla de formulario o confirmación, no una acción repetida).

### 2.3 Estados vacíos y secciones

- Si no hay ninguna declaración: se muestra el vacío (no secciones vacías).
- Si no hay activas pero sí desactivadas o retiradas, se pintan las secciones que existan; no se
  dice «no hay declaraciones».
- Cada sección lleva su recuento: «Activas (2)», «Desactivadas (1)», «Retiradas (1)».
- El vacío total:

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Pendientes por carpeta»          │
│ CONTEXTO DECLARADO                           │
│ Consulta y cambia el significado que has     │
│ dado a tus carpetas.                         │
│                                              │
│ Todavía no has declarado ninguna carpeta.    │
│ Las declaraciones orientan cómo se interpreta│
│ una carpeta; no crean series ni tocan        │
│ archivos.                                    │
│                                              │
│ [Volver a «Pendientes por carpeta»]          │
└──────────────────────────────────────────────┘
```

- Texto exacto del vacío:
  - **«Todavía no has declarado ninguna carpeta.»**
  - **«Las declaraciones orientan cómo se interpreta una carpeta; no crean series ni tocan
    archivos.»**
  - Botón/enlace: **«Volver a «Pendientes por carpeta»»** No hay un «Declarar» sin carpeta:
    la declaración nace desde un grupo.

---

## 3. Pantalla «Declarar esta carpeta»

### 3.1 Estructura y campos

- **H1 «Declarar esta carpeta»** (3 palabras, Anton).
- Entrada: **«Elige qué significa esta carpeta y hasta dónde alcanza.»** (9 palabras).
- Vuelta: **«← Volver a «Pendientes por carpeta»»** (conserva contexto/filtros).
- **Ruta relativa**, visible y **no editable**:
  - etiqueta «Ruta relativa»; valor en texto normal, con `overflow-wrap: anywhere`;
  - nota: **«Se toma desde la raíz de tu biblioteca. La ruta no se cambia aquí.»**
  - No se ofrece un campo de texto libre: evita rutas inventadas y deja claro que la identidad es
    la ruta. Para otra carpeta, se declara desde su grupo.
- **¿Qué significa esta carpeta?** `<fieldset>` con dos radios, **ninguno marcado por defecto**:
  - **Por autor**:
    - **«La carpeta reúne obras de un autor. Orienta búsquedas y filtros; no elige ni crea una
      serie.»**
  - **Por publicación**:
    - **«La carpeta corresponde a una publicación. Puede proponer su serie o publicación; no la
      confirma ni vincula archivos.»**
  - No se preselecciona por el nombre de la carpeta ni por alias, por los AC1/AC9.
  - Error si no se elige: **«Elige qué significa la carpeta antes de guardar.»**
- **Alcance** `<fieldset>`:
  - Casilla **«Incluir también las subcarpetas»**, sin marcar por defecto.
  - Explicación visible, sin depender de JavaScript para cambiar de texto; se explican las dos
    posibilidades:
    - **«Sin esta opción: solo esta carpeta; las subcarpetas quedan fuera.»**
    - **«Con esta opción: esta carpeta y todas sus subcarpetas, también los archivos que aparezcan
      después.»**
  - `<details>` **«Qué alcanza y qué no»**:
    - **«No alcanza a carpetas hermanas ni a la carpeta de arriba.»**
    - **«No sigue una carpeta que se renombra o se mueve: la ruta es la identidad.»**
    - **«No reinterpreta lo ya vinculado ni cambia series, archivos o vínculos existentes.»**
    - **«Los archivos futuros que caigan dentro se interpretan con esta declaración.»**
- **Efectos previstos**, panel visible antes del botón:
  - **«Solo orientará cómo se interpretan las próximas evaluaciones de esta carpeta.»**
  - **«No crea series, no mueve archivos, no vincula nada; solo orienta.»**
  - **«No cambia lo ya decidido ni reinterpreta el pasado.»**
- **Único botón principal:** **«Guardar declaración»**
- Si el alcance incluye subcarpetas, el envío **no guarda todavía**: abre la confirmación de
  alcance (§3.3). Si no, guarda directamente.

Wireframe a 360 px:

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Pendientes por carpeta»          │
│ DECLARAR ESTA CARPETA                        │
│ Elige qué significa esta carpeta y hasta     │
│ dónde alcanza.                               │
│                                              │
│ Ruta relativa                                │
│ Cómics/Carlos Giménez                        │
│ Se toma desde la raíz de tu biblioteca. La   │
│ ruta no se cambia aquí.                      │
│                                              │
│ ¿QUÉ SIGNIFICA ESTA CARPETA?                 │
│ ( ) Por autor                                │
│     La carpeta reúne obras de un autor…      │
│ ( ) Por publicación                          │
│     La carpeta corresponde a una publicación…│
│                                              │
│ ALCANCE                                      │
│ [ ] Incluir también las subcarpetas          │
│ Sin esta opción: solo esta carpeta; las      │
│ subcarpetas quedan fuera.                    │
│ Con esta opción: esta carpeta y todas sus    │
│ subcarpetas…                                 │
│ ▸ Qué alcanza y qué no                       │
│                                              │
│ EFECTOS PREVISTOS                            │
│ Solo orientará próximas interpretaciones.    │
│ No crea series, no mueve archivos, no        │
│ vincula nada; solo orienta.                  │
│ No cambia lo ya decidido.                    │
│                                              │
│ [ Guardar declaración ]   ← único principal  │
└──────────────────────────────────────────────┘
```

### 3.2 Si la carpeta ya tiene declaración

La pantalla no crea otra. Según la versión vigente:

| Estado | Qué se muestra | Acciones |
|---|---|---|
| **Activa** | Aviso **«Esta carpeta ya tiene una declaración activa.»** + resumen (ruta, tipo, alcance, versión) | «Cambiar declaración», «Desactivar», «Retirar», «Ver en Contexto declarado» |
| **Desactivada** | Aviso **«Esta carpeta tiene una declaración desactivada.»** + resumen | «Cambiar», «Reactivar», «Retirar», «Ver en Contexto declarado» |
| **Retirada** | Aviso **«La última declaración de esta carpeta está retirada.»** + **«Puedes crear una declaración nueva; la retirada se conserva en el historial.»** | Formulario nuevo; la anterior no se reactiva |
| **Solo importación** | Aviso **«Esta carpeta tiene una declaración de importación; no es una decisión local.»** + conflicto si difiere | Se puede crear una local; la importada no se sobrescribe; las alternativas quedan visibles |

- No se muestran dos formularios ni dos botones principales a la vez.
- Si la persona llega aquí con una declaración ya existente, la pantalla conserva la ruta y no
  permite cambiarla.

### 3.3 Confirmación al ampliar el alcance (AC3)

Se usa cuando:

- se crea una declaración con **«Incluir también las subcarpetas»** marcado (se amplía desde el
  alcance mínimo), o
- se cambia una declaración de **sin subcarpetas a con subcarpetas**.

No se usa al reducir el alcance (`true → false`) ni al cambiar solo el significado. La reducción
avisa de la nueva versión, pero no pide una segunda pantalla.

**Pantalla «Confirmar el alcance»**:

- **H1 «Confirmar el alcance»**
- Entrada: **«Vas a incluir también las subcarpetas.»**
- Resumen: ruta, significado elegido y, si es un cambio, versión actual y nueva.
- Texto:
  - **«La nueva versión alcanzará esta carpeta y todas sus subcarpetas, también los archivos que
    aparezcan después.»**
  - **«No alcanza a carpetas hermanas ni a la carpeta de arriba.»**
  - **«No crea series, no mueve archivos ni vincula nada.»**
  - **«La versión anterior dejará de aplicarse; el historial se conserva.»** — solo en cambio.
- Botones:
  - principal: **«Sí, incluir subcarpetas»**;
  - neutro: **«Volver sin cambiar»**, que vuelve al formulario con los valores elegidos y **no
    escribe nada**.
- La pantalla no tiene campos editables; es una confirmación. No hay diálogo nativo ni
  `hx-confirm`.
- Si es la primera declaración: en lugar de la frase de versión anterior, **«Será la primera
  declaración de esta carpeta; no hay versión anterior.»**

Wireframe:

```
┌─ 360 px ─────────────────────────────────────┐
│ CONFIRMAR EL ALCANCE                         │
│ Vas a incluir también las subcarpetas.       │
│                                              │
│ Ruta: Cómics/Carlos Giménez                  │
│ Significado: Por autor                       │
│ Alcance nuevo: esta carpeta y sus            │
│ subcarpetas.                                 │
│                                              │
│ La nueva versión alcanzará esta carpeta y    │
│ todas sus subcarpetas, también los archivos  │
│ que aparezcan después.                       │
│ No alcanza a carpetas hermanas ni a la       │
│ carpeta de arriba.                           │
│ No crea series, no mueve archivos ni         │
│ vincula nada.                                │
│ La versión anterior dejará de aplicarse; el  │
│ historial se conserva.                       │
│                                              │
│ [ Sí, incluir subcarpetas ]  ← único primary │
│ [ Volver sin cambiar ]                       │
└──────────────────────────────────────────────┘
```

---

## 4. Cambiar, desactivar, reactivar y retirar

### 4.1 Cambiar

- **H1 «Cambiar declaración»**
- Entrada: **«La versión actual dejará de aplicarse cuando guardes. El historial se conserva.»**
- Se muestran ruta (no editable), **versión actual** y los mismos campos de la declaración
  (significado y alcance) precargados.
- Aviso visible antes del botón:
  - **«Se creará una versión nueva. La anterior deja de aplicarse en cuanto guardes.»**
  - **«No se reinterpreta lo que ya está decidido.»**
  - Si la declaración estaba **desactivada**: **«La nueva versión seguirá desactivada. Reactívala
    para que se aplique.»**
- Si no se ha cambiado nada: **«No has cambiado nada.»**; no se crea versión nueva.
- Si el cambio amplía el alcance: pasa por «Confirmar el alcance» (§3.3). Si lo reduce, aviso:
  **«El alcance se reduce: las subcarpetas que salgan dejarán de heredar esta declaración.»**
- **Único principal:** **«Guardar cambios»**
- Tras guardar: **«Declaración actualizada. La versión anterior deja de aplicarse.»**
- No se permite cambiar la ruta: **«La ruta no se cambia. Para otra carpeta, crea otra
  declaración desde su grupo.»** Cambiar de carpeta es otra identidad.

### 4.2 Desactivar y reactivar

- **Desactivar** es reversible y no pide confirmación:
  - acción en la tarjeta de una declaración activa; formulario POST;
  - tras guardar: **«Declaración desactivada. Puedes reactivarla cuando quieras.»**;
  - estado «Desactivada» y la frase **«No se aplica a nuevas interpretaciones.»**;
  - no se borra nada, no se mueve ningún archivo, el historial se conserva.
- **Reactivar** es reversible:
  - acción en la tarjeta de una desactivada; POST;
  - tras guardar: **«Declaración reactivada.»**;
  - el estado vuelve a «Activa»; no se reinterpreta el pasado.
- Ninguna de las dos acciones es principal en la lista: son botones neutros repetidos por tarjeta.
- No se usa un diálogo nativo. La desactivación no requiere confirmación porque es reversible; el
  texto lo dice.

### 4.3 Retirar

- **Retirar es terminal**. Se accede desde la tarjeta activa o desactivada a una **pantalla de
  confirmación**, nunca a un `hx-confirm`:
  - **H1 «Retirar la declaración»**;
  - **«Dejará de aplicarse para nuevas interpretaciones.»**;
  - **«Es definitivo: una declaración retirada no se puede reactivar.»**;
  - **«El historial se conserva. No se mueve, renombra ni borra ningún archivo.»**;
  - resumen de ruta, significado, alcance y versión;
  - principal: **«Sí, retirar la declaración»**;
  - neutro: **«Volver sin retirar»**
- Tras retirar: **«Declaración retirada. El historial se conserva y no se ha tocado ningún
  archivo.»**; la tarjeta pasa a la sección **Retiradas**, sin acciones de reactivar.
- Para volver a declarar esa carpeta se crea una **declaración nueva** (identidad nueva) desde su
  grupo; la retirada se queda en el historial. La UI no ofrece «Reactivar» en una retirada.

Wireframe de retirada:

```
┌─ 360 px ─────────────────────────────────────┐
│ RETIRAR LA DECLARACIÓN                       │
│ Dejará de aplicarse para nuevas              │
│ interpretaciones.                            │
│                                              │
│ Es definitivo: una declaración retirada no   │
│ se puede reactivar.                          │
│ El historial se conserva. No se mueve,       │
│ renombra ni borra ningún archivo.            │
│                                              │
│ Ruta: Cómics/Carlos Giménez                  │
│ Significado: Por autor · Versión 2           │
│ Alcance: solo esta carpeta                   │
│                                              │
│ [ Sí, retirar la declaración ]  ← primary    │
│ [ Volver sin retirar ]                       │
└──────────────────────────────────────────────┘
```

### 4.4 Qué nunca hace el ciclo de vida

- No crea series ni publicaciones.
- No vincula archivos, no reasigna `issue_id`, no enriquece ni cambia metadatos.
- No mueve, renombra, copia ni borra archivos o carpetas.
- No revierte decisiones ya confirmadas ni reinterpreta el pasado.
- No toca los alias B13 ni los activa.
- No escribe fuera de `declaraciones_carpeta` (y su versión).
- Desactivar y retirar solo cambian lo que se aplicará a **nuevas** evaluaciones.

---

## 5. Conflictos visibles (AC9 / AC6)

### 5.1 Dónde aparece

- En la tarjeta de una declaración, si el servicio entrega alias o interpretaciones alternativas que
  contradicen su significado o alcance.
- En la pantalla de declaración, antes de elegir el significado, si esa carpeta tiene un alias de
  importación o un alias aprendido que propone otra lectura.
- En esta rebanada **no se crean ni se activan alias**; si existen, se **muestran**. La gestión de
  alias es #132.

### 5.2 Cómo se muestra

- Chip textual **«Conflicto visible»**; nunca solo un color.
- `<details>` con resumen **«Ver las interpretaciones en conflicto»**
- Texto:
  - **«Hay otra interpretación para esta carpeta. No se elige ninguna aquí.»**
  - **«La declaración local tiene prioridad; el alias no se borra y sigue visible.»**
  - **«No se activa ni se aplica el alias desde esta pantalla.»**
- Alternativas, cada una con su origen:
  - **Alias de importación:** **«Sugiere otra lectura; no es una decisión local ni se aplica
    mientras la local esté activa.»**
  - **Alias aprendido:** **«Corrección anterior de un título; no tiene alcance de carpeta.»**
  - **Otra declaración:** tipo, origen y estado.
- No hay radios, botones ni enlaces para «elegir» una alternativa. La pantalla no decide la
  precedencia; solo la hace visible. El sistema la aplica al evaluar, no aquí.
- Si existe una **declaración local activa** para la misma ruta, no se crea otra: se muestra la
  existente (§3.2). Si existe una de importación, la local puede crearse y la importada queda como
  alternativa visible, sin sobrescribirse.

### 5.3 Copy del conflicto en la pantalla de declaración

```
┌─ 360 px ─────────────────────────────────────┐
│ Hay otra interpretación para esta carpeta.   │
│ No se elige ninguna aquí.                    │
│                                              │
│ Alias de importación: por publicación.       │
│ No se aplica mientras la declaración local   │
│ esté activa.                                 │
│                                              │
│ La declaración local tiene prioridad; el     │
│ alias no se borra y sigue visible.           │
└──────────────────────────────────────────────┘
```

---

## 6. Errores y estados límite

### 6.1 Ruta inválida

La ruta se valida en servidor; no se confía en la URL ni en el nombre. Pantalla de error sin
formulario:

- **H1 «Declarar carpeta»** (2, Anton). El problema se explica en el mensaje, no en el titular.
- Mensaje según el caso:
  - vacía/no reconocida: **«No sabemos qué carpeta quieres declarar. Vuelve a «Pendientes por
    carpeta» y elige una.»**
  - no relativa/fuera de la biblioteca: **«La carpeta tiene que estar dentro de tu biblioteca y ser
    una ruta relativa.»**
  - demasiado larga: **«La ruta es demasiado larga.»**
  - ruta inválida genérica: **«La ruta de esta carpeta no es válida. Vuelve a «Pendientes por
    carpeta» y elige la carpeta desde ahí.»**
- **No se muestra la ruta absoluta ni una ruta que pueda escapar de la biblioteca.**
- Enlace: **«← Volver a «Pendientes por carpeta»»**; no hay botón principal.

### 6.2 Raíz de la biblioteca (P3, rechazada)

- Mismo H1 «Declarar carpeta».
- Mensaje:
  **«No se puede declarar la raíz de la biblioteca: alcanzaría todas las carpetas. Elige una
  carpeta dentro de ella.»**
- No hay formulario. No se ofrece «continuar de todos modos»: la raíz está prohibida por el
  contrato.
- Se explica el porqué: una declaración con subcarpetas sobre la raíz abarcaría todo y ampliaría el
  alcance de golpe.

### 6.3 Sin declaraciones

- Vacío de §2.3; no se muestran secciones vacías ni un formulario sin ruta.

### 6.4 La carpeta ya está declarada

- Si está **activa**: no se crea otra; se muestra el resumen y las acciones de §3.2.
- Si está **desactivada**: resumen y acciones; «Reactivar» es la acción para volver a aplicarla.
- Si está **retirada**: se puede crear una nueva; la retirada se conserva; no hay «reactivar».
- Si solo hay **importación**: se puede crear una local; no se sobrescribe la importada; conflicto
  visible.

### 6.5 Acción sobre una declaración que ya no existe o no admite la operación

- No encontrada: **«Esa declaración ya no existe. Vuelve a «Contexto declarado».»**
- Retirada: **«Una declaración retirada no se puede reactivar. Crea una declaración nueva desde la
  carpeta.»**
- Cambio de una retirada: **«Una declaración retirada no se puede cambiar.»**
- Se muestra un aviso `role="alert"` y el enlace de vuelta; no se pinta un formulario que vaya a
  fallar.

### 6.6 Error al guardar

- Fallo de base de datos o de validación del servidor: se conserva el formulario con los valores y
  se muestra un aviso:
  **«No se ha podido guardar la declaración. No se ha cambiado nada. Vuelve a intentarlo.»**
- No se redirige a la lista como si hubiera funcionado; el foco va al aviso y luego al campo.
- La validación de significado/alcance se hace en servidor además de la UI.

---

## 7. Accesibilidad y 320 px

### 7.1 Semántica y formularios

- Significado: `<fieldset>` + `<legend>` visible («¿Qué significa esta carpeta?») y dos
  `<input type="radio">` con `<label>`; **ninguno marcado por defecto**.
- Alcance: `<fieldset>` + `<legend>` («Alcance»), casilla con `<label>` y descripción asociada
  (`aria-describedby`).
- Ruta: texto, no control; se anuncia como «Ruta relativa: …».
- Errores de validación: resumen `role="alert"` al principio del formulario, enlaces al campo; el
  foco va al primer campo con error. Los mensajes están en español y no llevan códigos internos.
- Confirmaciones: H1 y resumen; botón principal y vuelta neutra; no hay diálogos nativos.
- Acciones de ciclo de vida: `<form method="post">` con `<button>` real; no hay `div` clicables ni
  formularios anidados.
- Chip de estado con texto; nombre accesible completo (no solo color).
- `<details>` nativo para «Qué alcanza y qué no» e interpretaciones en conflicto.

### 7.2 Teclado y foco

- Tab recorre radios, casilla, detalles, enlaces y botones en orden de lectura; flechas cambian
  radios cuando el grupo tiene el foco.
- El foco visible usa el estilo de la app; no se oculta con `outline: none`.
- En errores, el foco va al resumen o al primer campo inválido; en confirmaciones, al H1.
- En la lista, cada tarjeta tiene sus acciones como controles independientes; el orden no salta
  entre tarjetas.
- Tras una acción correcta, el aviso `role="status"` se anuncia; no se roba el foco al principio de
  la página de forma silenciosa.
- No hay atajos propios, ni trampas, ni diálogos que capturen el foco.

### 7.3 320 px y contraste

- Todo en una columna a ≤ 480 px: ruta, chips, alcance, efectos y acciones.
- Rutas largas con `overflow-wrap: anywhere`; no se trunca el final de la ruta (es la identidad).
- Chips y acciones con `flex-wrap`; ninguna fila provoca scroll horizontal.
- Texto informativo ≥ 14 px. Títulos de tarjeta de ruta con `.titulo-frase` (Archivo), H1 en Anton
  de ≤ 3 palabras.
- Estados y conflictos se distinguen por texto + chip, no solo por color.
- Los botones de acción tienen objetivo táctil; no se apilan en una sola línea forzada.
- Sin tablas de datos: lista de tarjetas y `<dl>`; si se usara una tabla, llevaría `caption` y
  `scope`, pero no es la recomendación.
- Se usan los tokens de `web.css`; no se añaden colores.

---

## 8. Tabla de estados y textos finales

| # | Pantalla / situación | Texto visible exacto | Comportamiento |
|---|---|---|---|
| 1 | Revisión, grupo sin declaración | «Declarar esta carpeta» + «No crea series, no mueve archivos, no vincula nada; solo orienta próximas interpretaciones.» | Abre la declaración de esa ruta |
| 2 | Revisión, cabecera | «Contexto declarado» | Abre la lista |
| 3 | Lista sin declaraciones | «Todavía no has declarado ninguna carpeta.» + «Las declaraciones orientan cómo se interpreta una carpeta; no crean series ni tocan archivos.» | «Volver a «Pendientes por carpeta»» |
| 4 | Lista, tarjeta activa | «Por autor» / «Por publicación» · «Local» · «Activa» · «Versión N» · alcance · efectos | Cambiar, Desactivar, Retirar |
| 5 | Lista, tarjeta desactivada | «Desactivada» + «No se aplica a nuevas interpretaciones.» | Cambiar, Reactivar, Retirar |
| 6 | Lista, tarjeta retirada | «Retirada: no se aplica a nuevas interpretaciones. El historial se conserva.» | Sin acciones |
| 7 | Lista, tarjeta de importación | «Sugerencia importada; no es una decisión local.» | Sin acciones locales |
| 8 | Lista, conflicto | «Conflicto visible» + «Hay otra interpretación para esta carpeta. No se elige ninguna aquí.» | Detalles con alternativas; sin botones de elegir |
| 9 | Declaración, sin significado | «Elige qué significa la carpeta antes de guardar.» | 200 con error; foco al campo |
| 10 | Declaración, sin subcarpetas | «Sin esta opción: solo esta carpeta; las subcarpetas quedan fuera.» | Guarda directo |
| 11 | Declaración, con subcarpetas | «Con esta opción: esta carpeta y todas sus subcarpetas, también los archivos que aparezcan después.» | Pasa a «Confirmar el alcance» |
| 12 | Confirmar alcance | «Vas a incluir también las subcarpetas.» + «La nueva versión alcanzará esta carpeta y todas sus subcarpetas…» | «Sí, incluir subcarpetas» / «Volver sin cambiar» |
| 13 | Confirmar alcance, creación | «Será la primera declaración de esta carpeta; no hay versión anterior.» | Igual |
| 14 | Confirmar alcance, cambio | «La versión anterior dejará de aplicarse; el historial se conserva.» | Igual |
| 15 | Guardado inicial | «Declaración guardada.» | Vuelve a la lista con la tarjeta visible |
| 15b | Cambio guardado | «Declaración actualizada. La versión anterior deja de aplicarse.» | Vuelve a la lista con la versión nueva |
| 16 | Cambio | «La versión actual dejará de aplicarse cuando guardes. El historial se conserva.» | Formulario precargado |
| 17 | Cambio sin diferencias | «No has cambiado nada.» | No crea versión |
| 18 | Cambio de significado | «Se creará una versión nueva. La anterior deja de aplicarse en cuanto guardes.» | Aviso; sin segunda pantalla |
| 19 | Cambio que reduce alcance | «El alcance se reduce: las subcarpetas que salgan dejarán de heredar esta declaración.» | Aviso; sin segunda pantalla |
| 20 | Desactivar | «Declaración desactivada. Puedes reactivarla cuando quieras.» | Estado desactivado |
| 21 | Reactivar | «Declaración reactivada.» | Estado activo |
| 22 | Retirar, confirmación | «Es definitivo: una declaración retirada no se puede reactivar.» + «El historial se conserva. No se mueve, renombra ni borra ningún archivo.» | «Sí, retirar la declaración» |
| 23 | Retirada correcta | «Declaración retirada. El historial se conserva y no se ha tocado ningún archivo.» | Tarjeta en Retiradas |
| 24 | Ruta inválida | «La ruta de esta carpeta no es válida. Vuelve a «Pendientes por carpeta» y elige la carpeta desde ahí.» | Sin formulario |
| 25 | Raíz de biblioteca | «No se puede declarar la raíz de la biblioteca: alcanzaría todas las carpetas. Elige una carpeta dentro de ella.» | Sin formulario |
| 26 | Ya activa | «Esta carpeta ya tiene una declaración activa.» | Resumen y acciones; sin duplicar |
| 27 | Ya desactivada | «Esta carpeta tiene una declaración desactivada.» | Resumen y acciones |
| 28 | Ya retirada | «La última declaración de esta carpeta está retirada.» + «Puedes crear una declaración nueva; la retirada se conserva en el historial.» | Formulario nuevo |
| 29 | Declaración no encontrada | «Esa declaración ya no existe. Vuelve a «Contexto declarado».» | Aviso y vuelta |
| 30 | Retirada no reactivable | «Una declaración retirada no se puede reactivar. Crea una declaración nueva desde la carpeta.» | Aviso y vuelta |
| 31 | Error al guardar | «No se ha podido guardar la declaración. No se ha cambiado nada. Vuelve a intentarlo.» | Conserva formulario; foco al aviso |
| 32 | Conflicto con alias | «Hay otra interpretación para esta carpeta. No se elige ninguna aquí.» + «La declaración local tiene prioridad; el alias no se borra y sigue visible.» | Sin elección ni activación |

---

## 9. Decisiones de copy

1. **«Declaración»**, no «perfil» ni «regla»: el modelo ratificado habla de declaraciones; «perfil»
   se confunde con otras cosas y no aparece en la UI.
2. **«Por autor» / «Por publicación»**: los dos valores ratificados (P2). No se ofrece «otro» ni
   «colección» en v1.
3. **«Ruta relativa»**, siempre visible; **no editable**. La ruta es la identidad (P4). Para otra
   carpeta, se crea otra declaración; cambiar de carpeta no es una versión.
4. **«Incluir también las subcarpetas»**, no «descendientes» ni « recursivo»: lenguaje del
   coleccionista. El alcance por defecto es **solo la carpeta**.
5. **Ampliar alcance = confirmación explícita**; reducir alcance = aviso, sin segunda pantalla. Una
   ampliación nunca ocurre en silencio (AC3).
6. **«La versión anterior deja de aplicarse»** se dice al cambiar; el historial se conserva. No se
   borra la fila anterior.
7. **Desactivar es reversible; retirar es terminal.** La UI no ofrece «Reactivar» en una retirada y
   no llama «borrar» a retirar.
8. **No crea series, no mueve archivos, no vincula nada; solo orienta** junto a la acción y en el
   panel de efectos. **No afecta retroactivamente** se dice en el formulario y en la lista.
9. **Local vs importación:** el origen se muestra; una importación nunca se presenta como decisión
   confirmada ni se convierte en local. La declaración local no se sobrescribe.
10. **Conflicto visible:** se muestran las alternativas y la precedencia, pero **la pantalla no
    elige**; no hay botón «usar alias» en 130-b.
11. **Raíz de biblioteca:** prohibida con explicación (P3); no hay opción de continuar.
12. **Vacío honesto:** sin declaraciones se dice que no hay ninguna y se vuelve a la revisión; no se
    pinta un formulario sin ruta.
13. **Sin ids internos:** no aparecen `declaracion_id`, `version` en bruto, `origen`, `estado` como
    valores de enum, ni «uuid». La versión se muestra como **«Versión N»**; el origen como
    «Local»/«Importación».
14. **Sin promesas de efecto:** no se dice que la declaración «se aplicará» a los archivos
    existentes; se dice que orienta **próximas** interpretaciones. Los efectos ya decididos no se
    tocan.
15. **El historial no se desarrolla aquí:** se muestra la versión vigente y se avisa que el
    historial se conserva; la pantalla de historial/inventario completo es #132.

---

## 10. Lo que deja fuera

- **Correspondencias carpeta → serie/publicación** (#131): esta pantalla no elige destinos ni crea
  propuestas.
- **Inventario y administración de alias** (#132): no se crean, activan, desactivan ni retiran
  alias desde aquí; solo se muestran si existen.
- **Historial completo de versiones**: la lista muestra la versión vigente y avisa de que el
  historial se conserva; su pantalla es #132.
- **Importación masiva de declaraciones**, migración o backfill.
- **Mover, renombrar, copiar o borrar** archivos/carpetas; **crear series o publicaciones**;
  **vincular archivos**.
- **Cambiar la ruta** de una declaración; para otra carpeta se crea otra declaración.
- **Editar una declaración retirada** o reactivarla.
- **Red, fuentes, enriquecimiento, metadatos, `locked_fields`**.
- **Nuevo JS, nueva dependencia o migración**; los formularios son POST con `Form(...)` explícito y
  PRG.
- **Medición real** de navegador, lector, 320 px y Pi: **NOT RUN**.

---

## 11. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Entrada desde la revisión | Cada grupo tiene «Declarar esta carpeta»; cabecera con «Contexto declarado» |
| 2 | Significado explícito | Dos radios sin preselección; no se infiere del nombre; error si falta |
| 3 | Alcance visible | Ruta relativa, «Solo esta carpeta» / «y sus subcarpetas»; archivos futuros explicados |
| 4 | Confirmación al ampliar | Creación/cambio a subcarpetas pasa por «Confirmar el alcance»; no escribe antes |
| 5 | No efectos | Aviso junto a la acción y panel de efectos; ningún botón crea/mueve/vincula |
| 6 | Cambio versionado | «Cambiar» avisa de que la anterior deja de aplicarse; nueva versión en lista |
| 7 | Desactivar/reactivar | Reversible, sin confirmación; estados visibles; no borra |
| 8 | Retirar | Pantalla de confirmación; terminal; historial conservado; sin archivos |
| 9 | Origen local/importación | Chips y nota; importada no se presenta como local ni se sobrescribe |
| 10 | Conflicto visible | Chip + detalles con alternativas y precedencia; sin elección automática |
| 11 | Estados vacíos/errores | Sin declaraciones, ruta inválida, raíz, ya declarada, no encontrada; textos de §8 |
| 12 | Accesibilidad/320 | Radios/labels, teclado, foco, 14 px, sin scroll lateral, sin color único |
| 13 | Sin efectos laterales | No se mueve/crea/vincula; solo escribe la declaración/versión |

**PASS de este documento:** flujo, pantallas, textos, estados, ciclo de vida y condiciones de
accesibilidad decididos y coherentes con el modelo ratificado de #130, el benchmark y `CLAUDE.md`
§6.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos y
Pi. No se declaran.
