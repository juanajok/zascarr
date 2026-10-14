# Auditoría de UI, aspecto visual y usabilidad — ZascArr

**Fecha:** 2026-10-15 · **Versión auditada:** `main` en `a5369ef` (v1.15.1), desplegada en la Raspberry Pi del responsable (acceso por LAN, con contraseña)
**Alcance:** UI web en vivo (`/login`, `/ui/*`, `/estado`) + maqueta `docs/design/maqueta-ui.html`
**Plataformas:** Chrome escritorio, Android/Chrome, iPhone/Safari (este último **emulado**, ver §7)
**Método:** evaluación experta (10 heurísticas de Nielsen + WCAG 2.2 AA), medición automática en el DOM real
(contraste, tamaños, objetivos, etiquetas, reflow a 360 px) sobre 11 pantallas en tema claro y oscuro.
**No es un test con usuarios.**

Cada hallazgo lleva **[C] confirmado** (observado en vivo o medido) o **[P] plausible** (deducido, verificar).

---

## 0. Resumen ejecutivo

1. **La épica V ha funcionado donde se ha aplicado.** Contraste: **0 fallos** de texto en 11 pantallas, en
   claro y oscuro (V1). El menú agrupado con `aria-current` y la barra inferior en móvil (V3) y el Inicio guiado (V4)
   son sólidos.
2. **El problema principal ya no es visual, es de escala.** La maqueta y U1 se diseñaron con **14 archivos**.
   La instalación real tiene **1.322 pendientes en 108 carpetas**, y el Inicio manda al coleccionista a
   resolverlos «uno a uno» en una rejilla que enseña 50, no dice que hay más y gasta casi toda la tarjeta
   en un hueco de portada vacío. Es la tarea nº 1 del producto («Toca ahora») y hoy no se puede terminar.
3. **Tres fallos de accesibilidad concretos y baratos de arreglar:** foco invisible en los buscadores
   en tema oscuro, scroll horizontal en la ficha de serie a 360 px y campos con el placeholder como única etiqueta.
4. **Las pantallas aún sin migrar (Deseados, Estado, Ajustes, Duplicados, Descubrir)** siguen enseñando
   estados contradictorios, jerga técnica y contenido sin procesar (HTML crudo de Comic Vine en Descubrir).
   La maqueta ya resuelve bien casi todo esto, salvo Descubrir, que quedó fuera de ella.

| Severidad | Nº | IDs |
|---|---|---|
| Crítico | 2 | C1, MQ1 |
| Mayor | 8 | M1–M7, MQ2 |
| Menor | 12 | m1–m9, MQ3–MQ5 |

---

## 1. Lo que ya está bien (no tocar)

| Qué | Evidencia |
|---|---|
| Contraste AA en ambos temas | 0 pares texto/fondo < 4,5:1 medidos en 11 pantallas. `--ink-faint` ahora 5,37:1 (claro) y 6,16:1 (oscuro) |
| Navegación | `<nav aria-label>`, grupos con `role="group"`, `aria-current="page"`, contadores con texto `sr-only`, enlace «Saltar al contenido» |
| Inicio (V4) | Checklist derivado del estado real, **una** acción primaria («Revisar ahora»), estados «Hecho / Toca ahora» con texto, no solo color |
| Rendimiento | Por revisar: TTFB 43 ms, `load` 285 ms, 16 KB de recursos + 67 KB de HTML. Holgado para la Pi |
| Sin hotlinking | Las portadas de Descubrir pasan por el proxy `/ui/descubrir/portada` con lista de hosts |
| Mensajes que dan confianza | «Solo mira: no borra, no mueve y no renombra nada» (Duplicados), «Es una sugerencia: no está elegida ni asignada» (Carpetas) |
| Reflow | Sin scroll horizontal a 360 px en 8 de 9 pantallas |

---

## 2. Hallazgos en la app desplegada

### Crítico

**C1 — «Por revisar» no escala a una colección real.** [C] · Nielsen 1, 7, 8 · U1/V5
- Hay 1.322 pendientes y la página pinta **50 tarjetas sin decir «50 de 1.322»**, sin paginar y sin
  enlace a «siguientes». Inicio dice «Puedes decirnos de qué serie son, **uno a uno**».
- Cada tarjeta reserva un hueco de portada 2:3 (~350 px) que, sin miniatura, queda **vacío y sin icono**:
  `web.css:621-628` (`.cover-missing { visibility: hidden }` oculta la imagen pero **conserva el hueco**).
  A 375 px, **el primer pantallazo no muestra ningún nombre de archivo**.
- El nombre del archivo se corta con elipsis (`.filename { white-space: nowrap }`, `web.css:630-633`):
  «La Imposible Patrulla X (144-1…», justo lo que U1 pedía no hacer.
- 50 buscadores con el **mismo nombre accesible** («Buscar serie…»): un lector de pantalla no sabe a qué archivo
  pertenece cada uno.
- La vista que sí escala («Pendientes por carpeta»: 108 carpetas, paginada, con serie sugerida) existe, pero
  es un enlace secundario.
- **Impacto:** la tarea principal que propone el producto es inviable a mano (1.322 decisiones). Esto aumenta la probabilidad de abandono en
  el primer uso (hipótesis: medir la tasa de finalización del paso 2 del Inicio).

### Mayores

**M1 — Foco invisible en los buscadores en tema oscuro.** [C] · WCAG 2.4.7 (AA), 2.4.13 (AAA, como referencia)
`web.css:602-607` quita el `outline` y lo sustituye por `box-shadow: var(--shadow-ink-sm)`, que en oscuro
es negro al 55 % sobre `--paper-2`: **1,14:1**. El borde no cambia. Medido con el foco puesto: la tarjeta
enfocada es indistinguible de las demás. Afecta a Por revisar, Biblioteca, Deseados e Inicio.

**M2 — Ficha de serie con scroll horizontal a 360 px.** [C] · WCAG 1.4.10 Reflow
El `<select id="wishlist_policy">` (`_politica_serie.html:19`) llega a 487 px: 127 px de desbordamiento.

**M3 — Descubrir: espera muda, contenido sin procesar y sugerencia engañosa.** [C] · Nielsen 1, 2, 5, 8
- Buscar «Mortadelo» tardó **15-20 s sin ningún indicador**. No hay `hx-indicator` en `descubrir.html`.
  El usuario no sabe si ha funcionado.
- Las descripciones de Comic Vine salen como **HTML escapado y visible**:
  `<p>Mortadelo was a monthly… <a href="/editorial-bruguera/4010-2965/" …>Bruguera</a>…</p>`. Es seguro
  porque se escapa, pero ilegible. Hay que convertirlo a texto en el servidor.
- La fuente sale como valor interno: `COMIC_VINE` (`_resultados_descubrir.html:21`, `{{ r.fuente }}`).
- «La fuente sugiere: **Grapa americana**» para *Mortadelo*. La sugerencia se deriva de la fuente, no
  de la obra, e induce a un error que luego contamina el enriquecimiento (ADR 0002).
- 29 resultados, cada uno con su `<select>` de 10 tradiciones (Hick-Hyman) y un **select nativo gris claro
  (#efefef) dentro de una tarjeta oscura**, sin estilo del sistema.
- El enlace externo `↗` tiene como nombre accesible solo «↗» y abre una pestaña nueva sin avisar (WCAG 2.4.4).

**M4 — Estados que se contradicen.** [C] · Nielsen 1, 2 · U3/V8, U6/V9 (pendientes)
- Deseados: chip «**BUSCANDO…**» junto a «**No se encontró nada en las fuentes activas**» en las dos filas.
- Estado: «**Todo bien**» en verde y debajo un aviso en mayúsculas con ruta interna:
  «FICHERO /RUN/VPN-STATE/WG0.JSON AUSENTE — EL HOST AÚN NO HA ESCRITO EL ESTADO (O EL TIMER NO CORRE)».
  El subtítulo dice «Semáforos en vez de JSON crudo», que está escrito para el desarrollador, no para el coleccionista.

**M5 — El placeholder es la única etiqueta.** [C] · WCAG 1.3.1, 2.4.6, 3.3.2, 4.1.2
- Por revisar: 50 `input` (`_tarjeta_pendiente.html:32`), además del campo «nº» (`:23`).
- Biblioteca: 3 buscadores y **2 `select` sin nombre accesible** (`biblioteca.html:10,30,36`).
- Deseados: el placeholder se corta a la vista: «Buscar serie para añad» (`wishlist.html:16`).
- Es incoherente con Descubrir, que sí lleva `aria-label`, y con el componente `ui.*` de V2.

**M6 — Ajustes habla en lenguaje de administrador de sistemas.** [C] · Nielsen 2, 4, 8 · U5/V10 (pendiente)
- Términos que el coleccionista no conoce: `.env`, API, «enricher», `host.docker.internal`, `127.0.0.1`,
  «reverse proxy», 403, `BASE_URL`, JSON, «caché», «Chat ID».
- **8 botones «Guardar» independientes** en una página de 2.800 px: no se ve qué hay sin guardar ni qué guarda cada uno.
- El aviso legal reutilizado dice «Añadir una serie **aquí**…» en una pantalla donde no se añaden series.
- Los `select` de Seguridad y Avisos miden **22 px** de alto: por debajo del mínimo de 24 px de WCAG 2.5.8 y
  distintos de los demás campos (40 px).

**M7 — Párrafos largos en MAYÚSCULAS y girados.** [C] · Nielsen 8; legibilidad
La didascalia (`web.css:495-507`: `text-transform: uppercase; transform: rotate(-1.2deg)`) se usa para
**textos de 2-4 líneas que hay que entender**: el aviso legal de Deseados y Ajustes, los avisos de Estado y las notas
de la ficha de serie («GUARDAR APLICA LA RETIRADA AL MOMENTO (LO QUE SOBRA DEJA DE BUSCARSE)…»). En mayúsculas
se pierde la forma de la palabra y la lectura es más lenta. Girado, se lee peor en móvil. Es bonito en
rótulos de 1-3 palabras y contraproducente en párrafos, sobre todo los legales.

### Menores

| ID | Hallazgo | Evid. | Referencia |
|---|---|---|---|
| m1 | El login dice «**Usuario** o contraseña incorrectos» en un formulario que **solo pide contraseña** (`web/auth.py:93`) | C | Nielsen 2, 9 |
| m2 | Campos a **14,4 px** (14 px en Ajustes): **iOS Safari amplía la página al enfocarlos** (< 16 px). Inicio, Por revisar, Biblioteca, Deseados, Ajustes | P (medido el tamaño; el zoom, verificar en iPhone) | HIG; 1.4.4 |
| m3 | Objetivos de toque < 44 px: 51 en Por revisar y 37 en Ajustes. Enlaces de texto de 18 px de alto («tebeos sin clasificar →», «Aviso legal»). Cumple el mínimo AA de 24 px (WCAG 2.5.8) salvo los `select` de M6, pero no los 44 px de las HIG ni los 48 dp de Material | C | 2.5.8; HIG; MD3 |
| m4 | Biblioteca: «Todas las editoriales» es un `select` **sin opciones**. Los contenedores de resultados vacíos se ven con borde. La tarjeta enseña el valor interno `tebeo` y no la etiqueta «Tebeo español» | C | Nielsen 4, 8 |
| m5 | Vocabulario inestable: «Por revisar» (menú) / «Pendientes por carpeta» (título) / «registros» / «archivos» / «tebeos» para lo mismo. «Carpetas» dice «registros pendientes de verificar… lee la base de datos y no comprueba el disco» | C | Nielsen 2, 4 · U7 |
| m6 | Duplicados: **27.400 px** de página sin resumen ni índice. Rutas completas del contenedor (`/media/library/Comics/…`) que el usuario no asocia a su disco | C | Nielsen 6, 8 · U8/V11 |
| m7 | Por revisar lanza **50 peticiones `/portada` por carga, casi todas 404**, para acabar en `onerror` (JS en línea). Hoy es rápido, pero cada 404 cuesta trabajo a la Pi y el servidor ya sabe que no hay portada | C | Rendimiento; CSP |
| m8 | `.htmx-indicator { opacity: 0 }` (`web.css:562`) **sigue en el árbol de accesibilidad**: el lector de pantalla anuncia «Buscando…» aunque no se esté buscando | C | WCAG 1.3.1 |
| m9 | En este PC (Linux), `system-ui` resuelve a una **monoespaciada** (medido: 10×«i» = 10×«M» = 96 px). Respeta el escritorio del usuario, pero las líneas salen ~30 % más largas. No afecta a Android/iOS | C (en este equipo) | Tipografía |

---

## 3. Las 10 heurísticas de Nielsen, una por una

| # | Heurística | Estado | Dónde falla / dónde acierta |
|---|---|---|---|
| 1 | Visibilidad del estado del sistema | ❌ | C1 (50 de 1.322 sin decirlo), M3 (búsqueda muda 15-20 s), M4 («Todo bien» + aviso). ✓ Inicio, contadores del menú |
| 2 | Relación con el mundo real | ⚠️ | M6 (jerga), M3 (`COMIC_VINE`, HTML crudo), m5 (registros/archivos/tebeos), m1. ✓ «tebeos», «grapa», «Deseados» |
| 3 | Control y libertad | ⚠️ | «Ignorar» usa `hx-confirm` nativo y avisa «No volverá a aparecer aquí» (sin papelera: V7 pendiente) |
| 4 | Consistencia y estándares | ⚠️ | Etiquetas: Descubrir sí, el resto no (M5). Select nativo en Descubrir. 8 «Guardar» (M6). Valor interno frente a etiqueta (m4) |
| 5 | Prevención de errores | ⚠️ | Sugerencia de tradición equivocada (M3). ✓ Asignación con confirmación previa, vinculación con revisión |
| 6 | Reconocer antes que recordar | ⚠️ | Duplicados sin resumen ni orden (m6). Rutas internas que hay que interpretar |
| 7 | Flexibilidad y eficiencia | ❌ | Sin acciones por lotes en Por revisar (C1). La vista por carpetas, que es la eficiente, está escondida |
| 8 | Diseño estético y minimalista | ⚠️ | Huecos vacíos (C1), párrafos en mayúsculas (M7), avisos legales a pantalla completa. ✓ El lenguaje «papel y tinta» tiene identidad |
| 9 | Ayudar a reconocer y recuperarse de errores | ⚠️ | m1. Deseados no dice qué hacer cuando no encuentra nada (M4) |
| 10 | Ayuda y documentación | ✓/⚠️ | Hay textos de ayuda en contexto, pero son **largos y defensivos** (Carpetas, Ajustes) en lugar de breves y orientados a la acción |

---

## 4. Auditoría de la maqueta (`docs/design/maqueta-ui.html`)

> Está en el repo desde la PR #60. ADR 0005 ya la declara «no es un producto». Esta sección dice
> qué tomar de ella y qué no para las historias pendientes: V5–V11.

**MQ1 (crítico) — Diseñada para 14 archivos; la realidad son 1.322 en 108 carpetas.**
«Seleccionar todo» + «Agrupar por patrón de nombre» + barra «Asignar…» está pensada para una pantalla.
Con 1.322 archivos, «seleccionar todo» y asignar a una serie es una **acción masiva peligrosa**, y agrupar
por patrón de nombre repite lo que ya hacen mejor las carpetas (ADR 0007/0008 y la vista «Pendientes por carpeta»).
→ **V5 debe partir de las carpetas, no de la lista de archivos** (variantes en §5).

**MQ2 (mayor) — Serie de destino con `<datalist>`** (línea 301-302). No busca en el servidor, en iOS Safari
y Android se muestra de forma inconsistente y no distingue entre «Patrulla-X (1985)» y «(1963)» con su editorial.
Hay que usar el buscador HTMX que ya existe (`buscar-serie`) con resultados que muestren año y editorial.

**MQ3 (menor) — Emojis como iconos de estado** (⏳ 🔎 ∅ ⬇ ✓ 🖼 🔔 🔒). Cómo se ven depende de la fuente de emoji
del sistema: es de suponer que el Chromium de Raspberry Pi OS no la trae de serie [P]. La UI actual usa símbolos
Unicode monocromos (⌂ ✎ ▤ ⚖), que son más predecibles. Hay que mantener eso o pasar a un *sprite* SVG en línea.

**MQ4 (menor) — Le faltan estados.** No tiene carga (Descubrir tarda 15-20 s), error, vacío a escala ni nombres
de 90 caracteres. Biblioteca y **Descubrir están «fuera del alcance»**, y Descubrir es justo donde están los peores
hallazgos en vivo (M3).

**MQ5 (menor, decisión de producto) — Aviso legal plegado en `<details>`** en Deseados. Resuelve M7, pero choca
con la postura legal (LEGAL.md, CLAUDE.md §5). Hay dos posturas legítimas:
- **(a) Plegar** para que la pantalla respire.
- **(b) Dejar una frase visible** en caja normal con enlace a «Aviso legal», sin mayúsculas ni giro.

Recomiendo **(b)**, pero **la decisión es tuya**.

**Qué adoptar tal cual** (ya validado en la maqueta y pendiente en el producto):

| Pantalla | Patrón de la maqueta | Resuelve |
|---|---|---|
| Estado | Estado global = el peor de los parciales; «Qué pasa / Por qué importa / Qué hacer»; ruta interna en «Detalle técnico» plegado; «No uso VPN: silenciar» | M4, M7 |
| Deseados | Leyenda de estados mutuamente excluyentes + siguiente paso con enlace a la causa + agrupar duplicados | M4 |
| Ajustes | «¿Qué quieres conectar?» con 4 objetivos en lenguaje del usuario; lo técnico en «Avanzado» | M6 |
| Duplicados | Resumen arriba (7,5 GB recuperables…), orden por ahorro, **nombre del archivo primero** y rutas cortas | m6 |

---

## 5. Decisión abierta: cómo rediseñar «Por revisar» (V5)

| | **A. Carpetas primero** ⭐ | B. Lista compacta + lotes (maqueta) | C. Cola de uno en uno |
|---|---|---|---|
| Idea | `/ui/pendientes` abre en la vista por carpetas (108 grupos) → asistente por carpeta. Los archivos sueltos van a una sección aparte | Filas compactas por archivo, agrupadas por patrón de nombre, selección múltiple y «Asignar…» | Un archivo cada vez con su sugerencia; «Aceptar / Otra serie / Ignorar», con teclado |
| Decisiones para 1.322 archivos | ~108 + sueltos (Hick: un orden de magnitud menos) | 1.322 elementos que paginar; los grupos ayudan pero no son la estructura real | 1.322 pasos |
| Riesgo de asignar mal | Bajo: el asistente ya revisa conflictos (año, subtítulo) | **Alto**: «seleccionar todo» sobre 1.322 | Bajo |
| Coste | **Bajo**: la vista y el asistente existen (ADR 0007/0008). Es reordenar y compactar | Alto (V5 + V6b completos) | Medio |
| Cuándo brilla | Colecciones reales organizadas en carpetas | Bandejas pequeñas (≤ 50) | Lo que queda al final |

**Recomendación: A como entrada principal + C para los sueltos.** B se descarta como pantalla principal.
Razones: encaja con la forma real de los datos, reutiliza trabajo ya revisado y reduce el riesgo de una asignación
masiva equivocada (Nielsen 5). La lista por archivo se queda como vista secundaria, ya compacta: sin hueco
de portada, con el nombre entero y un buscador con nombre accesible propio.

---

## 6. Propuesta de tokens y reglas (implementables en `web.css`, sin JS)

| Token / regla | Claro | Oscuro | Por qué |
|---|---|---|---|
| `--focus` (nuevo) | `#0a6a96` (= `--cyan-t`) · 5,39:1 sobre `--paper`, 4,98:1 sobre `--paper-2` | `#5cc4f0` · 9,37:1 / 8,67:1 | M1: anillo de foco ≥ 3:1 en ambos temas |
| `--input-font` (nuevo) | `1rem` (16 px) | igual | m2: evita el zoom de iOS al enfocar |
| `--target` (nuevo) | `44px` alto mínimo en controles primarios con `pointer: coarse` | igual | m3: HIG/MD3 |
| `.caption` | `text-transform: none; transform: none` cuando el texto ocupa más de una línea. Las mayúsculas y el giro quedan para rótulos de ≤ 3 palabras (clase `.caption--rotulo`) | igual | M7 |

```css
/* M1: el foco de los buscadores vuelve a ser un anillo visible en ambos temas */
:root { --focus: var(--cyan-t); --input-font: 1rem; --target: 44px; }
.series-search:focus-visible,
.filter-bar input[type="search"]:focus-visible,
.filter-bar select:focus-visible,
.search-input:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 2px;
}

/* m2: los campos no bajan de 16 px (Safari en iOS amplía la página por debajo) */
input, select, textarea { font-size: max(var(--input-font), 1em); }

/* C1: sin miniatura no se reserva hueco; el nombre se lee entero */
.pending-card .cover.cover-missing { display: none; }
.pending-card .filename { white-space: normal; overflow-wrap: anywhere; }

/* M2: ningún select empuja la página más allá del ancho */
select { max-width: 100%; }

/* m8: el indicador oculto tampoco existe para el lector de pantalla */
.htmx-indicator { visibility: hidden; }
.htmx-request .htmx-indicator, .htmx-request.htmx-indicator { visibility: visible; }
```

```html
<!-- M5 + C1: cada buscador dice a qué archivo pertenece -->
<label class="sr" for="q-{{ p.id }}">Serie de «{{ p.filename }}»</label>
<input id="q-{{ p.id }}" type="search" class="series-search" placeholder="Buscar serie…" …>

<!-- C1: decir cuántos hay y cuántos se ven -->
<p class="subtitle" role="status">Mostrando 50 de 1.322 · <a href="/ui/pendientes/carpetas">Verlos por carpeta (108)</a></p>
```

---

## 7. Checklist WCAG 2.2 AA aplicado

| Criterio | Resultado | Notas |
|---|---|---|
| 1.1.1 Contenido no textual | ✓ | Portadas decorativas con `alt=""` dentro de enlaces con texto |
| 1.3.1 Información y relaciones | ✗ | M5 (sin `label`), m8 |
| 1.4.3 Contraste mínimo | ✓ | 0 fallos medidos, claro y oscuro |
| 1.4.4 Cambio de tamaño del texto | ⚠️ | m2 (zoom forzado en iOS, por verificar) |
| 1.4.10 Reflow | ✗ | M2 (ficha de serie, +127 px a 360 px) |
| 1.4.11 Contraste no textual | ✗ | M1 (indicador de foco 1,14:1) |
| 2.1.1 Teclado | ✓ (parcial) | Todo alcanzable. No he probado los diálogos `hx-confirm` (limitación aceptada en B2) |
| 2.4.1 Saltar bloques | ✓ | `.skip` |
| 2.4.4 Propósito de los enlaces | ⚠️ | `↗` en Descubrir |
| 2.4.6 Encabezados y etiquetas | ✗ | 50 campos con el mismo nombre (C1/M5) |
| 2.4.7 Foco visible | ✗ | M1 |
| 2.5.8 Tamaño del objetivo (mínimo) | ⚠️ | `select` de 22 px en Ajustes (M6) |
| 3.3.2 Etiquetas o instrucciones | ✗ | M5 |
| 4.1.2 Nombre, función, valor | ✗ | `select` sin nombre en Biblioteca (M5) |
| 4.1.3 Mensajes de estado | ⚠️ | El resultado de Descubrir no se anuncia (sin `aria-live`); el asistente de carpetas sí |

---

## 8. Riesgos y validación pendiente

- **Safari en iOS no se ha probado en un dispositivo real.** Hay que verificar m2 (zoom), el comportamiento de la barra inferior
  con `safe-area-inset-bottom`, MQ2 (`datalist`) y `hx-confirm` en un iPhone.
- **«Carpetas primero» (§5) es una hipótesis.** Hay que validarla con **U10** antes de fusionar V5/V6 (puerta G1 de
  ADR 0005).
- **La sugerencia de tradición de Descubrir (M3)** puede ser un problema de datos y no solo de UI. Hay que confirmarlo con más
  búsquedas de tebeo español (*Zipi y Zape*, *Capitán Trueno*) antes de tocar la presentación.
- **MQ5 (aviso legal plegado)** es una decisión de postura legal, no de diseño.

## 9. Próximos pasos de testeo

1. **Test moderado con 5 coleccionistas (U10)**, 30 min, con dos tareas: «Clasifica las 3 carpetas con más tebeos»
   (variantes A y B en prototipo HTML estático) y «Averigua por qué BPRD no se descarga». Métricas: tasa de
   éxito, tiempo hasta terminar, errores de asignación y SEQ (1-7). Con 5 usuarios se detectan problemas, no
   se miden diferencias: no hay que sacar porcentajes.
2. **First-click test** (15-20 personas, no moderado) en Inicio y Ajustes: ¿dónde pulsa uno para «que se descarguen
   solos»? Valida el diseño por objetivos de V10 frente a las 7 tarjetas actuales.
3. **Regresión automática:** ampliar `test_web_css_contraste` con la comprobación de foco (M1) y añadir una prueba
   que falle si una plantilla tiene un `input`/`select` visible sin `label`/`aria-label` (M5), siguiendo el patrón
   de pruebas de V1.
4. **Ronda en dispositivo:** iPhone (Safari) y Android de gama baja (Chrome) contra la Pi, a 360/390/414 px,
   repitiendo el recorrido de esta auditoría.
