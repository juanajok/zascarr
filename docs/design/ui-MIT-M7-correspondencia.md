# UX — Correspondencias locales versionadas (MIT-M7-US02, #131, rebanada 131-b)

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas,
> plantillas, migraciones ni servicios. Fija el flujo, el copy, los estados y las condiciones de
> accesibilidad; la implementación los lleva al código.
> **Base:** `origin/main` = `048bb05469e57018a96109cbe7f16c9ccd74a3cc` (2026-11-10), worktree
> `.squad/wt-131b-ui`, rama `docs/131-ui`.
> **Insumos:** issue #131 (11 AC) y la ratificación P1–P10 del PO;
> `docs/design/especificacion-MIT-M7-contexto-declarado.md`;
> `docs/design/ui-MIT-M7-declarar-carpeta.md` (130-b, ya en `main`);
> `docs/design/benchmark-MIT-M7-contexto-declarado.md`; `CLAUDE.md` §6; el servicio 131-a
> `services/correspondencias_contexto.py` (rama `feat/131-correspondencia`, en revisión); la
> revisión por carpeta (`web/pendientes.py`, `templates/carpetas.html`) y el asistente M3.
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**; el documento fija lo que la
> implementación debe verificar.

---

## 0. Resumen

131-b **no crea destinos ni aplica nada**. Añade correspondencias locales versionadas entre una
declaración **Por publicación** y una **serie o publicación existente**, y una pantalla de
propuestas que enseña qué prepararía esa regla, sin confirmarla.

1. **Entrada:** la pantalla «Contexto declarado» (130-b) gana un enlace **«Correspondencias»** y, en
   cada declaración activa **Por publicación**, la acción **«Crear correspondencia»**. En la
   revisión por carpeta, cada grupo gana **«Ver propuesta de contexto»**.
2. **Crear correspondencia:** se elige el destino en el **catálogo local** (nunca se crea), el
   `tipo_de_registro` opcional y se ve el **alcance heredado** de la declaración. Una pantalla de
   **confirmación** dice que solo prepara propuestas: no vincula, no mueve, no aplica metadatos.
3. **Propuesta:** una `propuesta_disponible` enseña destino, alcance y `correspondencia_id` +
   `version_de_regla` en una traza plegada. Se distingue de una decisión: **no hay botón de aplicar**
   ni de confirmar. Los otros cinco estados de evaluación tienen su propio texto y, en conflicto,
   **solo se ven las reglas**.
4. **Ciclo de vida:** lista de correspondencias **Activas / Desactivadas / Retiradas**; cambiar crea
   una versión nueva y avisa de que la anterior deja de aplicarse; desactivar es reversible;
   reactivar vuelve a preparar propuestas; retirar es terminal y se confirma en pantalla.
5. **Efectos:** ninguna operación crea series o publicaciones, vincula archivos, mueve archivos,
   aplica metadatos ni reescribe lo ya confirmado.

**La regla de oro:** una correspondencia **prepara una propuesta**, no es una vinculación. La
propuesta no autoriza el paso siguiente: ese paso conserva su propio consentimiento.

**Presupuesto de entrada:** las frases de entrada nuevas están entre 4 y 11 palabras (lista 9,
formulario 10, propuesta 11, cambio 10, confirmación 10, retirada 4); ninguna supera 20.

---

## 1. Dónde se entra

### 1.1 Desde «Contexto declarado» (130-b)

La pantalla de declaraciones ya existe en el diseño 130-b. 131-b la toca solo para añadir:

- **Enlace de cabecera «Correspondencias»** (1 palabra; neutro) → lista de correspondencias.
- **En una declaración activa con significado «Por publicación»:** acción
  **«Crear correspondencia»** Si ya hay correspondencias, la persona las ve en la lista; la
  acción sigue disponible y el formulario avisa de que otra correspondencia puede producir un
  conflicto.
- **En una declaración «Por autor»:** no hay acción de crear correspondencia. Se explica:
  **«Una carpeta por autor solo orienta; no puede tener un destino único.»**
- **En una declaración desactivada o retirada:** no hay acción de crear; si hay correspondencias
  asociadas, se ven en la lista y se marcan como desactualizadas si la declaración ya no es la
  vigente.

La tarjeta de la declaración no gana un botón principal: sigue siendo una acción neutra, como en
130-b.

### 1.2 Desde la revisión por carpeta

En cada tarjeta de grupo de «Pendientes por carpeta», junto a las acciones existentes:

**«Ver propuesta de contexto»**, enlace neutro.

- Está siempre visible, sin consultar nada al pintar la lista (no N+1). Al abrirlo, se evalúa **ese**
  grupo.
- No sustituye a «Elegir la serie de esta carpeta» (M3) ni a «Declarar esta carpeta» (130-b): es una
  consulta de solo lectura.
- En la pantalla de propuesta se explica que **se evalúan los archivos de esta carpeta**; si una
  correspondencia se limita a otro tipo de registro, el estado será «Fuera de alcance» con motivo.

### 1.3 Pantalla «Correspondencias»

- **H1 «Correspondencias»** (1 palabra, Anton).
- Entrada: **«Consulta las reglas que preparan propuestas para tus carpetas.»** (9 palabras).
- Efectos visibles: **«Solo preparan propuestas; no vinculan archivos ni aplican metadatos.»**
- Vuelta: **«← Volver a «Contexto declarado»»**; se conserva el contexto de la lista cuando
  corresponda.
- Lista agrupada por estado: **Activas**, **Desactivadas**, **Retiradas**; las retiradas se quedan
  visibles. Historial completo/inventario: #132.
- Sin botón principal: las acciones se repiten por tarjeta y son neutras.
- La lista se sirve con un número fijo de consultas: destinos y declaraciones se cargan en bloque,
  no una consulta por tarjeta.

---

## 2. Crear una correspondencia

### 2.1 Entrada y resumen de la declaración

Se llega desde una declaración activa **Por publicación**. La pantalla recibe la versión exacta de
la declaración y muestra, sin editarla:

- **Ruta relativa:** `Cómics/Batman - Saga de Scott Snyder (2019)` (ruta de la declaración).
- **Significado:** **«Por publicación»**.
- **Versión de la declaración:** **«Versión 2»**.
- **Alcance heredado:** **«Solo esta carpeta»** o **«Esta carpeta y sus subcarpetas»**.
- Aviso: **«La ruta y las subcarpetas se heredan de la declaración y no se editan aquí.»**
  **«Si la declaración cambia, esta correspondencia dejará de aplicarse.»**

Si la declaración no es activa o no es **Por publicación**, no se pinta el formulario:

- **«Esta declaración ya no está activa; no se puede usar para una correspondencia.»**
- **«Una carpeta por autor solo orienta; no puede tener un destino único.»**
- Vuelta a «Contexto declarado»; sin botón principal.

### 2.2 Destino: serie o publicación existente

- **H1 «Crear correspondencia»** (2 palabras, Anton).
- Entrada: **«Elige a qué serie o publicación existente apunta esta carpeta.»** (10 palabras).
- **Tipo de destino:** `<fieldset>` con dos radios, **ninguno marcado por defecto**:
  - **Serie**
  - **Publicación** — ayuda **«Una publicación es un número o tomo de tu biblioteca.»**
- **Buscador local:** etiqueta **«Buscar en tu biblioteca»**, campo de búsqueda y botón neutro
  **«Buscar»**
  - Copia: **«Solo busca en tu biblioteca; no consulta fuentes ni crea nada.»**
  - Resultados en una lista de tarjetas/radios, con el patrón de búsqueda local del asistente M3:
    - Serie: «Título · año · tradición» (sin consultas por fila).
    - Publicación: «Serie · Número N · título del número · año» (sin una consulta por resultado).
  - Ningún resultado se preselecciona; elegir es un acto explícito.
  - Si no hay resultados:
    **«No hay ninguna serie o publicación que coincida en tu biblioteca.»**
    **«Prueba otro título; no se consultan fuentes.»**
  - Si no se ha buscado: **«Escribe un título para buscar en tu biblioteca.»**
  - Si no hay tipo: **«Elige si el destino es una serie o una publicación.»**
  - Si no hay elección: **«Elige una serie o publicación de la lista.»**
- **El destino elegido** se resume antes de continuar:
  - Serie: «Serie «Título» (año)».
  - Publicación: «Publicación «Serie» · Número N · «título»».
- **Nunca** hay un botón «Crear serie/publicación», ni un enlace a fuentes externas.

### 2.3 `tipo_de_registro` y alcance heredado

- **Se aplica a** (etiqueta visible; `select`):
  - **Cualquier registro** (`NULL`)
  - **Archivos**
  - **Series**
  - **Publicaciones**
- Ayuda: **«Limita a qué registros se aplica; no cambia el destino.»**
- El **tipo de registro es opcional y se elige aquí**; no forma parte de la declaración. Sirve para
  limitar a qué registros se aplica la correspondencia.
- La **ruta y las subcarpetas** se heredan de la declaración y **no se editan aquí**. Si se necesita
  otro alcance de carpeta, se cambia la declaración; esta correspondencia quedará desactualizada y
  habrá que crear otra. La pantalla lo dice antes de guardar.

### 2.4 Efectos y confirmación explícita

Antes del botón, panel visible:

- **«Solo prepara propuestas.»**
- **«No crea series ni publicaciones, no vincula archivos, no los mueve ni aplica metadatos.»**
- **«La confirmación de una propuesta es otro paso.»**
- Si ya hay una correspondencia activa para la carpeta:
  **«Ya hay una correspondencia activa para esta carpeta. Si creas otra, la evaluación mostrará un
  conflicto y no elegirá ninguna.»**
  - No se bloquea la creación; el conflicto se muestra al evaluar y no se resuelve solo.

**Botón principal: «Revisar y crear»** No escribe todavía: abre la pantalla de confirmación.

**Pantalla «Confirmar correspondencia»:**

- **H1 «Confirmar correspondencia»**
- Entrada: **«Vas a crear una correspondencia; todavía no se aplica nada.»** (10 palabras).
- Resumen: ruta, destino, alcance, tipo de registro, versión de la declaración.
- Texto:
  - **«Solo prepara propuestas. No crea series ni publicaciones, no vincula archivos, no los mueve
    ni aplica metadatos.»**
  - **«La confirmación de una propuesta es otro paso.»**
- Botones:
  - principal: **«Sí, crear correspondencia»**;
  - neutro: **«Volver sin crear»**, que vuelve al formulario con los valores elegidos y no
    escribe.
- Un solo botón principal; sin diálogo nativo.

### 2.5 Después de crear

- Se vuelve a **«Correspondencias»** con un aviso `role="status"`:
  **«Correspondencia creada. Solo prepara propuestas; no se ha vinculado nada.»**
- La tarjeta aparece en **Activas**, con su versión 1 y su alcance.
- Si el destino desapareció entre la selección y el guardado:
  **«El destino elegido ya no existe. Elige otra serie o publicación.»**; no se crea nada.
- Si la declaración cambió:
  **«La declaración ha cambiado. Vuelve a empezar desde la declaración vigente.»**
- Si falla el guardado:
  **«No se ha podido crear la correspondencia. No se ha cambiado nada. Vuelve a intentarlo.»**

Wireframe a 360 px:

```
┌─ 360 px ─────────────────────────────────────┐
│ CREAR CORRESPONDENCIA                        │
│ Elige a qué serie o publicación existente    │
│ apunta esta carpeta.                         │
│                                              │
│ Declaración: Cómics/Batman - Saga…           │
│ Por publicación · Versión 2                  │
│ Alcance: solo esta carpeta                   │
│ La ruta y las subcarpetas se heredan y no    │
│ se editan aquí.                              │
│                                              │
│ ¿A QUÉ APUNTA?                               │
│ ( ) Serie      ( ) Publicación               │
│ Una publicación es un número o tomo de tu    │
│ biblioteca.                                  │
│                                              │
│ Buscar en tu biblioteca                      │
│ [ Título…                        ] [Buscar]  │
│ Solo busca en tu biblioteca; no consulta     │
│ fuentes ni crea nada.                        │
│                                              │
│ Resultados                                   │
│ ( ) Batman: La saga de Scott Snyder (2019)   │
│ ( ) Batman: El tribunal de los búhos (2012)  │
│                                              │
│ Se aplica a  [ Cualquier registro ▾ ]        │
│ Limita a qué registros se aplica; no cambia  │
│ el destino.                                  │
│                                              │
│ EFECTOS                                      │
│ Solo prepara propuestas.                     │
│ No crea series ni publicaciones, no vincula  │
│ archivos, no los mueve ni aplica metadatos.  │
│ La confirmación de una propuesta es otro     │
│ paso.                                        │
│                                              │
│ [ Revisar y crear ]  ← único principal       │
└──────────────────────────────────────────────┘
```

---

## 3. Pantalla «Propuesta de contexto»

### 3.1 Entrada y estructura

- Se abre desde **«Ver propuesta de contexto»** en un grupo de la revisión.
- Ruta propuesta: `GET /ui/pendientes/carpetas/contexto/propuesta?clave=…`; conserva el contexto de
  la lista.
- **H1 «Propuesta de contexto»**
- Entrada: **«Consulta qué propone el contexto para los archivos de esta carpeta.»** (11 palabras).
- Efectos: **«No vincula archivos ni aplica metadatos.»**
- Ruta de la carpeta visible, con `overflow-wrap`.
- Se evalúan **los archivos de esta carpeta** (`tipo=archivo`); si una regla se limita a otro tipo
  de registro, no hay propuesta y se explica en el estado.
- La evaluación es una lectura de conjunto, no una consulta por archivo.
- La pantalla muestra **exactamente uno** de los seis resultados de la evaluación:
  `propuesta_disponible`, `fuera_de_alcance`, `destino_no_disponible`,
  `conflicto_de_correspondencias`, `evidencia_incompatible` o `regla_desactualizada`.
- **No hay botón de aplicar, vincular ni confirmar.** El paso posterior conserva su propio
  consentimiento; esta pantalla solo informa.

### 3.2 `propuesta_disponible`

- Chip textual **«Propuesta disponible»**
- **Destino:**
  - Serie: «Serie «Título» (año)»; enlace a la ficha de la serie si existe.
  - Publicación: «Publicación «Serie» · Número N · «título»»; enlace a la ficha del número si
    existe.
- **Alcance:** **«Solo esta carpeta»** o **«Esta carpeta y sus subcarpetas»**
- **Se aplica a:** **«Cualquier registro»**, **«Archivos»**, **«Series»** o **«Publicaciones»**
- **Distinción de decisión**, visible:
  - **«Esto es una propuesta, no una decisión.»**
  - **«No se ha vinculado ni cambiado nada.»**
  - **«La confirmación de la serie o publicación es otro paso.»**
- **Traza** en un `<details>` **«Identidad y versión de la regla»**:
  - **«Código de la correspondencia: …»** (`correspondencia_id`)
  - **«Versión de la regla: …»** (`version_de_regla`)
  - **«Declaración: versión …»**
  - **«Origen: Local»**
- No hay acción de aplicar; solo vuelta.

### 3.3 `fuera_de_alcance`

- Chip **«Fuera de alcance»**
- **«Ninguna correspondencia activa cubre los archivos de esta carpeta.»**
- **«No se usa el parecido del nombre ni una regla vecina.»**
- Si no hay declaración de esa carpeta:
  **«Puedes declarar esta carpeta o crear una correspondencia desde una declaración por
  publicación.»** + enlaces neutros a «Contexto declarado» / «Pendientes por carpeta».
- Si la regla existe pero se limita a otro tipo de registro:
  **«La correspondencia se limita a otro tipo de registro; no se aplica a estos archivos.»**
- Sin propuesta; sin elegir nada.

### 3.4 `destino_no_disponible`

- Chip **«Destino no disponible»**
- **«La correspondencia existe, pero su serie o publicación de destino ya no está.»**
- **«No se crea ni se sustituye otro destino.»**
- Muestra la identidad/versión de la regla y el destino que falta (si consta); no aplica.
- Sin acción de aplicar; puede enlazar a «Correspondencias» para gestionarla.

### 3.5 `conflicto_de_correspondencias`

- Chip **«Conflicto de correspondencias»**
- **«Hay varias correspondencias activas para esta carpeta. No se elige ninguna.»**
- **«No se ordenan por fecha ni por origen para elegir.»**
- Se listan **todas** las reglas involucradas, cada una con:
  - destino (o «Destino no disponible»);
  - `contexto_raiz` y alcance;
  - **«Versión de la regla: N»** y **«Código: …»** (en traza plegada);
  - origen.
- **Sin radios, botones ni enlaces de «elegir»** Solo se ven las reglas; no se aplica ninguna.
- **No hay precedencia implícita** en la UI; si el contrato no la define, la pantalla no la inventa.

### 3.6 `evidencia_incompatible`

- Chip **«Regla incompatible»**
- **«La correspondencia no es coherente con su declaración o su destino.»**
- Motivo en llano, según el caso:
  - **«La declaración de esta correspondencia ya no existe.»**
  - **«La regla referencia una versión de la declaración que ya no es la vigente.»**
  - **«El destino existe, pero no es del tipo que declara la regla.»**
  - **«Una declaración por autor no puede tener un destino único.»**
- **«No se aplica ni se repara sola.»**
- Muestra la regla y su versión; sin aplicar.

### 3.7 `regla_desactualizada`

- Chip **«Desactualizada»**
- **«La declaración cambió, se desactivó o se retiró después de crear esta correspondencia.»**
- **«La regla anterior no se aplica; hay que reevaluar o crear una nueva.»**
- Muestra la versión antigua de la regla y la versión vigente de la declaración si consta. No se
  aplica la versión antigua ni se actualiza sola.
- Enlace a «Correspondencias» para gestionar; sin aplicar.

Wireframe de propuesta disponible:

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Pendientes por carpeta»          │
│ PROPUESTA DE CONTEXTO                        │
│ Consulta qué propone el contexto para los    │
│ archivos de esta carpeta.                    │
│ No vincula archivos ni aplica metadatos.     │
│                                              │
│ Cómics/Batman - Saga de Scott Snyder (2019)  │
│                                              │
│ [Propuesta disponible]                       │
│                                              │
│ Destino                                      │
│ Serie «Batman: La saga de Scott Snyder»      │
│ (2019)                                       │
│                                              │
│ Alcance: solo esta carpeta                   │
│ Se evalúan: archivos                         │
│ La regla se aplica a: cualquier registro     │
│                                              │
│ Esto es una propuesta, no una decisión.      │
│ No se ha vinculado ni cambiado nada.         │
│ La confirmación de la serie o publicación    │
│ es otro paso.                                │
│                                              │
│ ▸ Identidad y versión de la regla            │
│                                              │
│ [ Volver a «Pendientes por carpeta» ]        │
└──────────────────────────────────────────────┘
```

Wireframe de conflicto:

```
┌─ 360 px ─────────────────────────────────────┐
│ PROPUESTA DE CONTEXTO                        │
│ Cómics/Batman - Saga de Scott Snyder (2019)  │
│                                              │
│ [Conflicto de correspondencias]              │
│ Hay varias correspondencias activas para     │
│ esta carpeta. No se elige ninguna.           │
│ No se ordenan por fecha ni por origen para   │
│ elegir.                                      │
│                                              │
│ Regla 1 · Versión 2 · Código …               │
│ Destino: Serie «Batman (2019)»               │
│ Alcance: solo esta carpeta                   │
│                                              │
│ Regla 2 · Versión 1 · Código …               │
│ Destino: Publicación «Batman» · Número 1     │
│ Alcance: solo esta carpeta                   │
│                                              │
│ Solo se muestran las reglas; no se aplica    │
│ ninguna.                                     │
└──────────────────────────────────────────────┘
```

---

## 4. Lista de correspondencias y ciclo de vida

### 4.1 Tarjeta

Cada correspondencia es una tarjeta en una lista, **no una tabla** (a 320 px una tabla de siete
columnas desborda). La ruta es `.titulo-frase` (Archivo), con `overflow-wrap: anywhere`.

1. **Ruta de la declaración** (`contexto_raiz`).
2. **Destino:** «Serie «Título» (año)» o «Publicación «Serie» · Número N»; si falta,
   **«Destino no disponible»**
3. **Chips textuales:** estado (**Activa / Desactivada / Retirada**), origen
   (**Local / Importación**), **«Versión N»**, y si procede **«Desactualizada»**,
   **«Destino no disponible»** o **«Conflicto visible»**
4. **Alcance heredado:** **«Solo esta carpeta»** / **«Esta carpeta y sus subcarpetas»**
5. **Se aplica a:** **«Cualquier registro»**, **«Archivos»**, **«Series»** o **«Publicaciones»**
6. **Declaración:** **«Declaración · Versión 2»** + enlace a «Contexto declarado».
7. **Efectos:** **«Solo prepara propuestas: no crea series ni publicaciones, no vincula archivos,
   no los mueve ni aplica metadatos.»**
8. **Acciones** (neutras; no hay botón principal en la lista):
   - **Activa:** «Cambiar», «Desactivar», «Retirar».
   - **Desactivada:** «Cambiar», «Reactivar», «Retirar».
   - **Retirada:** sin acciones; texto **«Retirada: no prepara propuestas. El historial se
     conserva.»**
   - **Importación:** sin acciones locales; se muestra, no se gestiona desde aquí (#132).
   - **Desactualizada:** sin «Cambiar»; **«La declaración cambió o dejó de estar activa. Esta regla
     no se aplica.»** + «Desactivar»/«Retirar»; para volver, **«Crea una correspondencia nueva
     desde la declaración vigente.»**
   - **Destino no disponible:** «Cambiar» (a otro destino), «Desactivar»/«Retirar»;
     **«No se sustituye el destino automáticamente.»**

### 4.2 Wireframe de la lista

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a «Contexto declarado»              │
│ CORRESPONDENCIAS                             │
│ Consulta las reglas que preparan propuestas  │
│ para tus carpetas.                           │
│ Solo preparan propuestas; no vinculan        │
│ archivos ni aplican metadatos.               │
│                                              │
│ ACTIVAS (1)                                  │
│ ┌──────────────────────────────────────────┐ │
│ │ CÓMICS/BATMAN - SAGA DE SCOTT SNYDER     │ │
│ │ [Activa] [Local] [Versión 2]             │ │
│ │ Destino: Serie «Batman: La saga…» (2019) │ │
│ │ Alcance: solo esta carpeta               │ │
│ │ Se aplica a: archivos                    │ │
│ │ Solo prepara propuestas; no vincula      │ │
│ │ archivos ni aplica metadatos.            │ │
│ │ [Cambiar] [Desactivar] [Retirar]         │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ (Las secciones sin correspondencias no se    │
│  pintan.)                                    │
└──────────────────────────────────────────────┘
```

### 4.3 Conflicto entre varias correspondencias

- Si la lista detecta varias correspondencias activas para la misma carpeta, muestra un aviso
  superior:
  **«Hay varias correspondencias activas para la misma carpeta. La evaluación mostrará un conflicto;
  no se elige ninguna.»**
- Cada tarjeta sigue siendo gestionable (cambiar, desactivar, retirar). La UI **no elige** ni ordena
  por fecha/origen.
- No hay un botón «Resolver» que decida: resolver es una acción explícita de la persona sobre cada
  regla.

### 4.4 Cambiar

- **H1 «Cambiar correspondencia»**
- Entrada: **«La versión actual dejará de aplicarse; el historial se conserva.»** (10 palabras).
- Se muestran ruta y versión actual, el destino actual, el `tipo_de_registro` y el alcance de
  carpeta heredado (no editable). Se puede cambiar el destino y el tipo de registro; la declaración
  de referencia se mantiene.
- Aviso visible:
  **«Se creará una versión nueva. La anterior deja de aplicarse en cuanto guardes.»**
  **«No se reinterpreta lo que ya está decidido.»**
  Si la correspondencia estaba desactivada:
  **«La nueva versión seguirá desactivada. Reactívala para que prepare propuestas.»**
- Si no se cambia nada: **«No has cambiado nada.»**; no se crea versión.
- **Único principal: «Guardar cambios»** Sin segunda pantalla: el aviso ya explica la versión.
- Tras guardar: **«Correspondencia actualizada. La versión anterior deja de aplicarse.»**
- Si la declaración de referencia ya no es la vigente, no se ofrece «Cambiar»; hay que crear una
  correspondencia nueva desde la declaración vigente.

### 4.5 Desactivar, reactivar y retirar

- **Desactivar** es reversible y no pide confirmación:
  - acción en la tarjeta activa; POST;
  - **«Correspondencia desactivada. Puedes reactivarla cuando quieras.»**;
  - estado **Desactivada**; **«No prepara propuestas.»**; no se borra nada.
- **Reactivar** es reversible:
  - acción en una desactivada; POST;
  - **«Correspondencia reactivada.»**;
  - vuelve a **Activa**; no se reinterpreta el pasado.
  - Si la declaración ya no está activa, no se ofrece reactivar; se muestra la regla como
    desactualizada y se indica crear una nueva.
- **Retirar** es terminal. Pantalla de confirmación, nunca `hx-confirm`:
  - **H1 «Retirar la correspondencia»**;
  - **«Dejará de preparar propuestas.»** (4 palabras).
  - **«Es definitivo: una correspondencia retirada no se puede reactivar.»**;
  - **«El historial se conserva. No se mueve ni se borra nada.»**;
  - resumen de ruta, destino, alcance y versión;
  - principal **«Sí, retirar la correspondencia»**;
  - neutro **«Volver sin retirar»**
- Tras retirar: **«Correspondencia retirada. El historial se conserva y no se ha tocado nada.»**
  Pasa a **Retiradas**, sin reactivar.
- Para volver a preparar propuestas para esa carpeta hace falta **crear una correspondencia nueva**
  desde una declaración vigente; la retirada no se reactiva.

### 4.6 Vacío

- **«Todavía no has creado ninguna correspondencia.»**
- **«Una correspondencia solo prepara propuestas; no vincula archivos.»**
- **«Crea una desde una declaración por publicación.»**
- Enlace **«Ir a «Contexto declarado»»**
- Si no hay declaraciones, el enlace lleva al vacío de 130-b; no se ofrece crear una
  correspondencia sin declaración.

### 4.7 Qué nunca hace el ciclo de vida

- No crea series ni publicaciones.
- No vincula archivos, no reasigna `issue_id`, no enriquece ni aplica metadatos.
- No mueve, renombra, copia ni borra archivos o carpetas.
- No confirma ni aplica una propuesta; no elige en un conflicto.
- No actualiza ni reinterpreta reglas desactualizadas.
- No resuelve conflictos por fecha, origen ni «la más específica».
- No toca alias B13 ni los activa.
- No escribe fuera de `correspondencias_contexto` (y sus versiones).

---

## 5. Accesibilidad y 320 px

### 5.1 Semántica y formularios

- Tipo de destino: `<fieldset>` + `<legend>` visible («¿A qué apunta?») + dos radios con
  `<label>`; ninguno marcado por defecto.
- Búsqueda: `<label>` visible, campo y botón; resultados en una región `aria-live="polite"`; cada
  resultado es un radio con etiqueta; no se preselecciona nada.
- `tipo_de_registro`: `<label>` visible y `<select>` con opciones en llano.
- Alcance heredado: texto y `<dl>`, no controles editables.
- Confirmación: H1, resumen y dos botones; no diálogo nativo.
- Lista: tarjetas con `<ul>`/`<li>`; no tabla. Acciones como `<form method="post">` con `<button>`
  real; no formularios anidados.
- Estados con texto y chip; no solo color.
- `<details>` nativo para la traza y las reglas en conflicto.

### 5.2 Teclado y foco

- Tab recorre tipo, búsqueda, resultados, select, enlaces y botones en orden.
- Flechas cambian los radios de tipo cuando el grupo tiene foco.
- Errores de búsqueda/validación: resumen `role="alert"` y foco al campo o al grupo.
- Confirmación: H1 y resumen; foco al H1; botón principal y vuelta neutra.
- Propuesta: H1; sin acciones que capturen el foco; `<details>` con teclado nativo.
- Tras una acción correcta, el aviso `role="status"` se anuncia; no se roba el foco de forma
  silenciosa.
- Sin atajos propios, sin trampas, sin diálogos nativos.

### 5.3 320 px y contraste

- Una columna a ≤480 px: resumen, búsqueda, resultados, alcance, efectos y acciones.
- Rutas, títulos de serie y destinos largos con `overflow-wrap: anywhere`; los UUID de la traza
  también.
- Chips y acciones con `flex-wrap`; no hay scroll lateral.
- Texto informativo ≥14 px; H1 de pantalla en Anton de ≤3 palabras; rutas y frases en
  `.titulo-frase` (Archivo).
- Estados y conflictos con texto + chip, no solo color.
- Sin tablas de siete columnas; si se usara una, `caption` + `scope`, pero no es la recomendación.
- Se usan los tokens de `web.css`; no se añaden colores.

---

## 6. Tabla de estados y textos finales

### 6.1 Evaluación (`propuesta_disponible` + cinco estados de no aplicación)

| # | Estado interno | Chip visible | Texto principal | Qué hace / no hace |
|---|---|---|---|---|
| 1 | `propuesta_disponible` | «Propuesta disponible» | Destino + alcance; «Esto es una propuesta, no una decisión.» + «No se ha vinculado ni cambiado nada.» | Muestra `correspondencia_id`/`version_de_regla` en traza; **no aplica ni confirma** |
| 2 | `fuera_de_alcance` | «Fuera de alcance» | «Ninguna correspondencia activa cubre los archivos de esta carpeta.» + «No se usa el parecido del nombre ni una regla vecina.» | Sin propuesta; no elige una regla vecina |
| 3 | `destino_no_disponible` | «Destino no disponible» | «La correspondencia existe, pero su serie o publicación de destino ya no está.» + «No se crea ni se sustituye otro destino.» | Sin propuesta; no crea/sustituye |
| 4 | `conflicto_de_correspondencias` | «Conflicto de correspondencias» | «Hay varias correspondencias activas para esta carpeta. No se elige ninguna.» + «No se ordenan por fecha ni por origen para elegir.» | Lista todas las reglas; sin elección |
| 5 | `evidencia_incompatible` | «Regla incompatible» | «La correspondencia no es coherente con su declaración o su destino.» + motivo | Muestra la regla; no repara ni aplica |
| 6 | `regla_desactualizada` | «Desactualizada» | «La declaración cambió, se desactivó o se retiró después de crear esta correspondencia.» + «La regla anterior no se aplica; hay que reevaluar o crear una nueva.» | Muestra versiones; no aplica la vieja |

### 6.2 Creación, lista y ciclo de vida

| # | Situación | Texto visible exacto | Comportamiento |
|---|---|---|---|
| 7 | Declaración activa por publicación | «Crear correspondencia» | Abre el formulario |
| 8 | Declaración por autor | «Una carpeta por autor solo orienta; no puede tener un destino único.» | Sin formulario de correspondencia |
| 9 | Declaración no activa | «Esta declaración ya no está activa; no se puede usar para una correspondencia.» | Sin formulario |
| 10 | Crear, sin tipo | «Elige si el destino es una serie o una publicación.» | Error; no guarda |
| 11 | Crear, sin búsqueda | «Escribe un título para buscar en tu biblioteca.» | Sin resultados |
| 12 | Crear, sin resultados | «No hay ninguna serie o publicación que coincida en tu biblioteca.» + «Prueba otro título; no se consultan fuentes.» | Sin resultados; no crea |
| 13 | Crear, sin destino elegido | «Elige una serie o publicación de la lista.» | Error; no guarda |
| 14 | Crear, ya hay otra activa | «Ya hay una correspondencia activa para esta carpeta. Si creas otra, la evaluación mostrará un conflicto y no elegirá ninguna.» | Aviso; no bloquea |
| 15 | Confirmar creación | «Vas a crear una correspondencia; todavía no se aplica nada.» | Pantalla de confirmación |
| 16 | Crear correcto | «Correspondencia creada. Solo prepara propuestas; no se ha vinculado nada.» | Vuelve a la lista |
| 17 | Destino desaparecido | «El destino elegido ya no existe. Elige otra serie o publicación.» | Error; no crea |
| 18 | Declaración cambiada | «La declaración ha cambiado. Vuelve a empezar desde la declaración vigente.» | Error; no crea |
| 19 | Error al guardar | «No se ha podido crear la correspondencia. No se ha cambiado nada. Vuelve a intentarlo.» | Conserva el formulario |
| 20 | Lista vacía | «Todavía no has creado ninguna correspondencia.» + «Una correspondencia solo prepara propuestas; no vincula archivos.» + «Crea una desde una declaración por publicación.» | «Ir a «Contexto declarado»» |
| 21 | Tarjeta activa | «Activa» + «Versión N» + alcance + efectos | Cambiar, Desactivar, Retirar |
| 22 | Tarjeta desactivada | «Desactivada» + «No prepara propuestas.» | Cambiar, Reactivar, Retirar |
| 23 | Tarjeta retirada | «Retirada: no prepara propuestas. El historial se conserva.» | Sin acciones |
| 24 | Tarjeta desactualizada | «Desactualizada: la declaración cambió o dejó de estar activa.» + «Crea una correspondencia nueva desde la declaración vigente.» | Desactivar/Retirar; sin Cambiar |
| 25 | Tarjeta con destino ausente | «Destino no disponible» + «No se sustituye el destino automáticamente.» | Cambiar, Desactivar/Retirar |
| 26 | Conflicto en lista | «Hay varias correspondencias activas para la misma carpeta. La evaluación mostrará un conflicto; no se elige ninguna.» | Solo aviso; sin resolver automático |
| 27 | Cambiar | «La versión actual dejará de aplicarse; el historial se conserva.» + «Se creará una versión nueva. La anterior deja de aplicarse en cuanto guardes.» | Formulario; sin segunda pantalla |
| 28 | Cambiar sin diferencias | «No has cambiado nada.» | No crea versión |
| 29 | Cambiar correcto | «Correspondencia actualizada. La versión anterior deja de aplicarse.» | Vuelve a la lista |
| 30 | Desactivar correcto | «Correspondencia desactivada. Puedes reactivarla cuando quieras.» | Estado desactivado |
| 31 | Reactivar correcto | «Correspondencia reactivada.» | Estado activo |
| 32 | Retirar, confirmación | «Dejará de preparar propuestas.» + «Es definitivo: una correspondencia retirada no se puede reactivar.» + «El historial se conserva. No se mueve ni se borra nada.» | «Sí, retirar la correspondencia» |
| 33 | Retirar correcto | «Correspondencia retirada. El historial se conserva y no se ha tocado nada.» | Tarjeta en Retiradas |
| 34 | Acción sobre retirada | «Una correspondencia retirada no se puede reactivar.» | Aviso; sin acción |
| 35 | No encontrada | «Esa correspondencia ya no existe. Vuelve a «Correspondencias».» | Aviso y vuelta |

---

## 7. Decisiones de copy

1. **«Correspondencia»** es la regla local que une una declaración con un destino; **«propuesta»**
   es su resultado al evaluar. No se llaman «vínculo», «asignación» ni «decisión».
2. **«Serie» / «Publicación»**: una publicación es **un número o tomo de tu biblioteca**; no se usa
   «edición» ni se promete crear entidades.
3. **«Se aplica a»** es el `tipo_de_registro` opcional; «destino» es la serie o publicación. No se
   mezclan: una regla puede aplicarse a archivos y apuntar a una serie.
4. **Alcance heredado:** la ruta y las subcarpetas vienen de la declaración y **no se editan aquí**;
   cambiarlas exige otra declaración y otra correspondencia. El **tipo de registro** (`Se aplica a`)
   es opcional y se elige en la correspondencia; no se hereda de la declaración.
5. **«Solo prepara propuestas»** junto al botón y en la confirmación. **No crea series ni
   publicaciones, no vincula archivos, no los mueve ni aplica metadatos.** La propuesta **no es una
   decisión** y el paso posterior conserva su consentimiento.
6. **Nunca se crea un destino:** la búsqueda es local y muestra lo que ya existe; no hay botón de
   crear ni de consultar fuentes.
7. **Conflicto sin elección:** se muestran las reglas y sus versiones; no se ordenan por fecha,
   origen ni «la más específica». La pantalla no aplica ninguna.
8. **Regla desactualizada:** no se aplica la versión vieja ni se actualiza sola; se avisa y se
   ofrece crear una correspondencia nueva desde la declaración vigente.
9. **Desactivar es reversible; retirar es terminal.** No se llama «borrar» a retirar; el historial se
   conserva.
10. **La traza no se esconde:** en la propuesta disponible y en las reglas en conflicto se muestran
    `correspondencia_id` y `version_de_regla` en un `<details>`; en el resto de la tarjeta basta
    «Versión N». No se usan como texto principal.
11. **Sin jerga:** no aparecen `destino_tipo`, `declaracion_version_id`, `contexto_raiz` ni
    `tipo_de_registro` como valores internos; se traducen a etiquetas.
12. **Sin promesas de efecto:** la correspondencia solo prepara propuestas; no se dice que «se
    aplicará» ni que «vinculará» archivos. La confirmación posterior no está autorizada por crearla.

---

## 8. Lo que deja fuera

- **La confirmación de una propuesta y la vinculación real**: 131-b solo muestra; el paso posterior
  (M3/confirmación) conserva su propio consentimiento y no se implementa aquí.
- **Crear series, publicaciones o ediciones**: no existe ese camino en esta UI.
- **Mover, renombrar, copiar o borrar archivos/carpetas**; **aplicar metadatos**; **vincular**.
- **Inventario/historial completo y gestión de alias** (#132): la lista muestra versiones vigentes;
  el historial completo es #132.
- **Resolución automática de conflictos** o elección por antigüedad/precedencia.
- **Declaraciones** (130-b): se asumen existentes; esta pantalla no las crea.
- **Importación de correspondencias** o fuentes externas; todo es local.
- **Migración, red, JS nuevo, dependencias nuevas**.
- **Medición real** de navegador, lector, 320 px y Pi: **NOT RUN**.

---

## 9. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Crear desde una declaración vigente | Solo activa `publicacion`; ruta/versión/alcance visibles; autor/inactiva sin formulario |
| 2 | Destino cerrado y local | Radios Serie/Publicación; resultados del catálogo local; sin crear ni fuentes |
| 3 | `tipo_de_registro` opcional | Select «Se aplica a»; `NULL` = cualquier; copy distingue destino |
| 4 | Alcance heredado visible | Ruta + subcarpetas; no editable; el tipo de registro se elige aparte; aviso de que un cambio de declaración la desactualiza |
| 5 | Confirmación sin efectos | Pantalla «Confirmar correspondencia» antes de escribir; copy de no vincular/aplicar |
| 6 | Propuesta con identidad/versión | Destino, alcance, `correspondencia_id` y `version_de_regla` en traza; sin botón de aplicar |
| 7 | Seis estados | Propuesta + cinco de no aplicación, con motivo y sin elegir en conflicto |
| 8 | Lista y ciclo de vida | Activas/Desactivadas/Retiradas; cambiar/desactivar/reactivar/retirar; retiro confirmado |
| 9 | Desactualizada/destino ausente | Estados visibles, sin auto-actualizar ni sustituir |
| 10 | Sin efectos | No crea/vincula/mueve/aplica metadatos; copy en formulario/propuesta/ciclo |
| 11 | Accesible y 320 | Radios/labels, teclado, foco, 14 px, sin scroll lateral, sin color único |
| 12 | Sin jerga | Buscar en render `correspondencia_id`, `version_de_regla`, `destino_tipo`, `declaracion_version_id` fuera de la traza/expresiones de diseño |

**PASS de este documento:** flujo, pantallas, textos, seis estados, ciclo de vida y condiciones de
accesibilidad decididos y coherentes con #131, la spec MIT-M7 y `CLAUDE.md` §6.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos y
Pi. No se declaran.
