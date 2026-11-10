# Etiquetas — diseño de la experiencia (Jinja2 + HTMX, sin SPA)

> **Estado (2026-11-07):** **leer primero §0**, que recoge las decisiones del PO (un solo espacio de
> nombres visible, `etiqueta`) y la reconciliación de Biblioteca con BL-IT01 (#283), re-verificada tras
> #284/#286, y manda sobre el resto. La v0.1 decía: el MVP usa los namespaces **`tema`**, **`motivo`** y
> **`etiqueta`**. **No implementado.** No autoriza cambios en `src/`, `tests/` ni migraciones. El modelo
> y el espacio único están ratificados por la especificación (v0.3, migración **0022**); este documento
> fija **qué ve y qué hace El Coleccionista**, con contratos verificables.
>
> **Base leída** (commit `61c85d6`, 2026-11-07): `CLAUDE.md` §3.1 y §6,
> `docs/design/ui-migracion.md`, `docs/design/propuesta-externa-etiquetas.md` §4,
> `docs/design/especificacion-etiquetas.md` §2/§7.1 (espacio único ratificado),
> `src/zascarr/web/templates/{base,biblioteca,series_detail,pendientes,_componentes,_rejilla_biblioteca,_resultados_serie}.html`,
> `src/zascarr/web/{library,componentes,iconos,menu}.py`, `src/zascarr/static/web.css`,
> `src/zascarr/models/__init__.py` (`tags`, `issue_tags`, `Series.genres`, `Issue.characters`),
> `src/zascarr/services/series.py`.
>
> **Entregables:** este documento y `docs/design/maqueta-etiquetas.html` (maqueta estática,
> verificada en navegador real; ver §12).


## 0. Enmienda 2026-11-06 — un solo espacio de nombres y Biblioteca sobre BL-IT01

**Manda sobre el resto del documento** donde lo contradiga; el cuerpo se conserva como historial. Detalle en `especificacion-etiquetas.md` §0.

1. **Un solo espacio de nombres visible (D-1).** La persona escribe y ve **el nombre** (`noir`, `space-opera`), sin prefijos. Donde este documento dice `tema:noir` o `motivo:escuela`, léase `noir` o `escuela`. Los grupos de facetas por espacio de nombres se reducen a **un solo grupo** («Etiquetas»). El aviso de etiqueta ambigua entre espacios desaparece. La migración es la **0022** (`down_revision="0021"`), no la 0021: BL-R9 ya ocupó esa revisión.
2. **Biblioteca, sobre el contrato de BL-IT01 (#283):**
   - **No se crea `#resultados-biblioteca`.** El destino sigue siendo **`#rejilla`**, y el fragmento de `/ui/biblioteca/resultados` es el de BL-IT01 (`_rejilla_biblioteca.html`), ampliado.
   - **No se crea otro `#filtros-activos`.** Las etiquetas activas son **más chips de la lista existente** (`FiltroActivo`), con su «Quitar» y dentro de «Limpiar todos». La exclusión se distingue con «Sin», borde discontinuo e icono `minus`.
   - **La URL la empuja el servidor** (`HX-Push-Url`), como en BL-IT01; nada de `hx-push-url="true"` en enlaces ni formularios.
   - El recuento sigue en `#resumen-biblioteca`. Los tokens desconocidos se dicen en los mismos avisos que los demás filtros descartados.
   - Las facetas van dentro del fragmento de `#rejilla`, tras los chips.

   Afecta a §1.2, §4.1, §5 F1–F3 y F6, §6.2–§6.4, §7.1, §7.4 y al Anexo C (cuyos fragmentos, orientativos, usan los ids antiguos).
3. **La ficha de serie no cambia:** `#etiquetas-serie`, sus rutas y su edición sin diálogos siguen como están. Se añade la acción explícita «Crear "…"» (D-6) cuando el nombre tecleado no existe.
4. **La maqueta** (`maqueta-etiquetas.html`, `etiquetas-maqueta.png`) es anterior a BL-IT01. Vale para el **aspecto** (chips, exclusión, ficha y textos), **no** para la estructura de regiones ni los ids de Biblioteca.

## 1. Resumen para decidir en un minuto

1. **Buscador booru dentro de Biblioteca, no una pantalla nueva.** La barra de filtros actual
   (`biblioteca.html`, `.filter-bar`) gana un campo «Buscar por etiqueta» con sugerencias. Las
   etiquetas activas se ven como chips; varias etiquetas **se suman** (AND) y una etiqueta con
   `-` delante **excluye**. Nunca se exige aprender sintaxis: cada sugerencia ofrece «Añadir» y
   «Excluir» como dos enlaces reales, y la sintaxis queda visible en el campo.
2. **Una sola región que se sustituye:** `#rejilla` (chips activos + facetas + recuento + rejilla +
   paginación), como en BL-IT01. Un solo viaje por cambio de filtro, no uno por cada pieza.
   Quitar un chip, pulsar una faceta y elegir una sugerencia apuntan a esa misma región.
3. **Edición en la ficha de serie, como la bandeja de pendientes:** cada etiqueta se quita con su
   propio `hx-post` y se añade con un buscador con sugerencias; el fragmento `#etiquetas-serie` se
   sustituye **sin diálogos** y sin recargar. Sin `hx-confirm`: quitar una etiqueta no destruye
   nada y se deshace volviéndola a añadir.
4. **Cero JavaScript propio nuevo.** Todo es HTMX declarativo: `delay` para el debounce,
   `hx-sync` para descartar respuestas viejas, `hx-swap-oob` para actualizar el campo de texto y
   el foco sin JS. Lo que un autocompletado «de librería» resolvería con flechas/`alt`-clic **no
   se diseña** (justificación en §7.6): se sustituye por dos acciones explícitas y teclado nativo
   (Tab/Enter).
5. **Metáfora Netflix solo para descubrir, no para buscar.** Las «estanterías» por etiqueta
   (filas de tarjetas) van a una fase posterior con carga diferida `hx-trigger="revealed"`;
   el MVP muestra un panel de facetas. No se copia la estética ni el motor de recomendación.
6. **Un solo espacio visible en el MVP: `etiqueta`** (D-1, spec §2/§7.1). `genero`, `personaje`,
   `universo`, `formato` y `publico` **no son tags**: viven en sus columnas/relaciones o se
   deciden aparte (§4.4). La UI no los ofrece en la barra ni en las facetas.

## 2. Lo que ya existe y se reutiliza (nada nuevo si ya está)

| Pieza real | Dónde vive | Uso en etiquetas |
|---|---|---|
| `ui.chip(estado, texto)` | `templates/_componentes.html` + `web/componentes.py` | chip neutro de faceta y de etiqueta; estados `ok/warn/amber` para avisos |
| `ui.aviso(tipo, texto)` | ídem | avisos de error/confirmación **dentro** del fragmento (nunca JSON) |
| `ui.estado_vacio(titulo, texto, accion)` | ídem | sin resultados, biblioteca sin etiquetas |
| `ui.region_viva(id)` | ídem (`aria-live="polite"`) | recuento y panel de etiquetas de la ficha |
| `ui.grupo(titulo, recuento)` | ídem | un solo grupo de facetas («Etiquetas») y etiquetas de la ficha |
| `ui.portada(...)` | ídem; `web/portada_marca.py` | tarjetas de la rejilla (marcador local, sin hotlinking) |
| `.filter-bar`, `.filter-search-box`, `.series-results`, `.series-list` | `web.css` | campo de etiqueta y lista de sugerencias con el estilo que ya usan personaje/saga |
| `.chip`, `.chip.ok/.warn/.amber/.info`, `.group`, `.ghead`, `.empty-state`, `.aviso`, `.muted` | `web.css` §16c | componentes de base |
| `.htmx-indicator`, `.indicador-diferido` | `web.css` | estado de carga sin JS; el diferido no parpadea en respuestas rápidas |
| `.library-grid`, `.library-card`, `.pagination`, `.page-link` | `web.css` §13 | rejilla y paginación (24 por página, ya existente) |
| Foco `:focus-visible` (`--cyan-t`), mínimos de 14 px, 40/44 px táctiles | `web.css` §2, §16a | se heredan; las clases nuevas no los anulan |
| Iconos SVG `icono(nombre)` | `web/iconos.py` (Lucide ISC) | `x`, `minus`, `plus`, `tag` **hay que añadirlos** (§Anexo B); nunca caracteres |
| Tokens de color `--ink/--paper/--*-t/--*-bg` | `web.css` §1 | todo el color; no se inventa ningún valor en línea |
| Patrón `hx-get` + `keyup changed delay:400ms` | `biblioteca.html` (personaje/saga) | base del autocompletado (aquí con `input changed delay:300ms`) |
| Patrón `hx-post` + `hx-target="#card-…" hx-swap="outerHTML"` | `pendientes.html`, `_tarjeta_pendiente.html` | base de añadir/quitar etiqueta en la ficha |
| `_rejilla_biblioteca.html` | plantilla existente | se amplía con chips/facetas; **la URL de paginación debe incluir `etiquetas`** (§11.5) |

**Lo que ya está ratificado por la especificación (§2 y §7.1) y esta UI no reabre:** conviven
`tags`/`issue_tags` (UUID) y se añade `series_tags` en la migración **0022**; `tags` gana `namespace`
con un único valor visible (`etiqueta`) y `issue_tags` queda **dormida**. `Series.genres` e
`Issue.characters` existen y **no** se convierten en tags (§4.4). El identificador de superficie es
siempre el **nombre** normalizado (p. ej. `noir`, `space-opera`), nunca un UUID ni un `id`; si una
fase posterior añade otro espacio, solo cambia el servicio que resuelve el texto, no las rutas ni
los fragmentos.

## 3. Patrones de referencia y anti-patrones

### 3.1 Qué se toma de cada referencia (y qué no)

| Referencia | Se adopta / adapta | Se descarta | Cómo se ve en esta UI |
|---|---|---|---|
| **Hydrus / boorus** (búsqueda de tags) | Lenguaje de consulta simple y **visible**: espacio = AND, `-` = exclusión, nombre sin prefijo. Sugerencias con recuento. | Sintaxis obligatoria, operadores OR/`~`/regex, paréntesis, «siblings» invisibles, teclado de poder. | Campo con la expresión (`noir -escuela`) + chips derivados. «Añadir»/«Excluir» explícitos. Nada de OR en el MVP. |
| **Kavita smart filters** | Recuentos junto al filtro; «limpiar filtros» a la vista; filtro = colección de condiciones. | Constructor de reglas con muchos campos, guardar filtros como objetos, vistas materializadas. | Un solo grupo de facetas con recuento (`noir · 34`); «Quitar etiquetas». Guardar filtros = fase posterior. |
| **Calibre-Web typeahead** | Escribir, ver pocas sugerencias, elegir con clic; el campo no pierde lo elegido. | Lista completa de la tabla de tags, orden alfabético ciego, autocompletado solo con ratón. | Sugerencias **máx. 8**, ordenadas por uso/similitud, con recuento; enlaces enfocables con Tab; Enter envía la expresión. |
| **Netflix (descubrimiento)** | Metáfora de **estanterías por tema**, sin busca: filas de carátulas que invitan a explorar. | Recomendación personalizada, hero gigante, autoplay, carrusel con flechas (exigiría JS), filas infinitas. | Fase 2: 3 filas («Noir», «Escuela», «Space opera»), 8 tarjetas, desplazamiento con CSS y carga por `hx-trigger="revealed"`. El MVP muestra facetas, no estanterías. |
| **LANraragi / Komga** (tan solo como contraste) | Idea de que las etiquetas conviven con filtros estructurados (editorial, tradición), no los sustituyen. | Sustituir los filtros cerrados por etiquetas libres. | Los filtros actuales (tradición, editorial, personaje, saga) **se quedan**; las etiquetas se suman. |
| **Repo (Sonarr/Radarr-style)** | Verbos y patrones ya usados: buscador con `delay`, fragmento que se sustituye, «no se mueve ni renombra nada» junto a acciones con efecto. | Pantallas nuevas, SPA, modales. | Todo dentro de Biblioteca y de la ficha de serie. |

### 3.2 Anti-patrones a evitar (accionables)

1. **No convertir el campo de título en un cajón de sintaxis.** `q` sigue buscando por título;
   las etiquetas tienen su campo. Un usuario que escribe `noir` en título no espera tags.
2. **No ocultar la lógica AND.** Si el recuento baja al añadir una etiqueta, el texto lo dice
   («34 series con `noir` y `escuela`»); nunca un «filtrando…» ambiguo.
3. **No usar solo el color para excluir.** La exclusión lleva borde discontinuo, icono `minus` y la
   palabra «Sin»; el nombre va **escrito**, no solo con un punto de color. (El color puede acompañar,
   nunca informar solo.)
4. **No pedir facetas por tecla.** El autocompletado pide sugerencias (1 consulta limitada);
   las facetas se recalculan **solo al cambiar un filtro** (§9).
5. **No dar de alta etiquetas nuevas desde el buscador principal.** Un `Enter` sobre texto libre
   no crea tags: elige una sugerencia existente. Crear/renombrar tags es una decisión de
   taxonomía (§11), no un efecto colateral de buscar.
6. **No editar etiquetas como una lista de texto separada por comas.** Es `PUT` encubierto,
   invita a errores y a mass assignment. Una etiqueta = una acción explícita con campo `etiqueta`
   validado.
7. **No devolver JSON ni códigos 4xx/5xx en rutas de fragmento.** Con htmx 4.0.0 (vendorizado)
   **todo estado distinto de 204/304 se intercambia** (`ui-migracion.md` §2.5): un `{"detail":…}`
   se pinta en crudo. Los fallos recuperables se pintan **dentro del fragmento con 200**.
8. **No añadir flechas del teclado ni `alt`-clic con JS a mano.** Detectarlos exige JS (o
   `accesskey`, que es peor); se sustituye por dos acciones visibles y Tab/Enter (§7.6).
9. **No copiar la estética de Netflix** (fondo oscuro de vídeo, hero, degradados) ni su motor de
   recomendación. El tema es «papel y tinta»; la metáfora es la estantería, no el catálogo.
10. **No hotlinking ni portadas externas.** La rejilla usa `/ui/series/{id}/portada` y el
    marcador local `ui.portada`; las etiquetas no traen imágenes.
11. **No anunciar el resultado dos veces.** El lector de pantalla oye el recuento en una región
    `aria-live`; la rejilla **no** es viva. El panel de la ficha sí es región viva (es corto).
12. **No prometer «sinónimos» ni «padres» en la UI del MVP.** Alias e implicaciones son
    taxonomía (§11); la UI solo muestra lo que hay.

## 4. Arquitectura de la experiencia

### 4.1 Biblioteca (pantalla principal, existente `/ui/biblioteca`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Biblioteca                                                               │
│ 34 series catalogadas. Filtra por lo que tratan.        (≤20 palabras)   │
│                                                                          │
│ [Buscar por título…] [Tradición ▾] [Editorial ▾]                          │
│ [Buscar por etiqueta: noir                 ] [Buscar]   ← NUEVO          │
│   ┌──────────────────────────────────────────────┐                       │
│   │ noir                   34   [Añadir][Excluir]│  ← sugerencias (≤8)   │
│   │ noir-back               3   [Añadir][Excluir]│                       │
│   └──────────────────────────────────────────────┘                       │
│ [noir ×] [Sin escuela ×]  Quitar etiquetas            ← chips activos    │
│                                                                          │
│ Etiquetas de tu biblioteca                    (faceta; solo al cambiar)  │
│ ┌ Etiquetas ────────────────────────────────────────────────┐            │
│ │ noir · 34   escuela · 18   clásico · 12   bolsillo · 7    │            │
│ └───────────────────────────────────────────────────────────┘            │
│                                                                          │
│ 34 series con noir. No se muestran las de escuela.                       │
│ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                              │
│ │card│ │card│ │card│ │card│ │card│ │card│                              │
│ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘                              │
│ [1] [2] [3]                                              ← paginación 24 │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Entrada en descubrimiento (fase 2, no MVP):** con la biblioteca sin filtros, tres filas
  («Noir», «Escuela», «Space opera») de 8 tarjetas con `hx-trigger="revealed"`;
  cabecera de fila = enlace a la búsqueda por esa etiqueta. Nunca más de 3 filas por pantalla.
- **Móvil:** la barra de filtros se apila; los chips siguen en una fila con salto; el recuento va
  antes de la rejilla. Nada de dos columnas nuevas.
- **Sin filtros de etiqueta:** el panel de facetas es la puerta de entrada (se ve el catálogo de
  tags con recuentos). No hace falta un buscador de etiquetas gigante.

### 4.2 Ficha de serie (`/ui/series/{id}`, existente `series_detail.html`)

La sección «Etiquetas» va **después** de la frase de huecos y **antes** de la política de
búsqueda; nunca tapa la acción principal de la pantalla («Añadir números del disco» sigue siendo
el único botón principal, CLAUDE.md §6).

```
Etiquetas                                                    ← h2
Lo que tratan tus tebeos. Se guarda al momento; no toca los archivos. (≤20 palabras)
┌ Etiquetas · 4 ──────────────────────────────────────────────────────────┐
│ [humor ×] [aventuras ×] [espionaje ×] [parodia ×]                       │
└─────────────────────────────────────────────────────────────────────────┘
[ Añadir una etiqueta… (sugerencias) ] [Añadir]       ← neutro, no amarillo
▸ ¿De dónde salen?                                    ← <details>, no compite
```

- Sin `hx-confirm` y sin `<dialog>`: quitar una etiqueta es reversible. No hay «Guardar»: cada
  acción se confirma sola con un `ui.aviso("ok", "Etiqueta añadida.")` dentro de la región viva.
- Si la serie no tiene etiquetas: `ui.estado_vacio(...)` compacto, con la misma caja que el resto
  de estados vacíos del repo, pero sin acción principal (la principal de la ficha es otra).

### 4.3 Sintaxis visible (la que el campo acepta y los chips reflejan)

| Escribes | Significa | Chip | Texto del recuento |
|---|---|---|---|
| `noir` | la serie **tiene** esa etiqueta | `noir ×` | «34 series con noir.» |
| `noir escuela` | las tiene **todas** (AND) | dos chips | «5 series con noir y escuela.» |
| `-escuela` | **excluye** esas series | `Sin escuela ×` | «No se muestran las de escuela.» |
| `space-opera` | nombre con guion interno | `space-opera ×` | «12 series con space-opera.» |

- Separación por **espacios**; no hay comillas, paréntesis, OR ni comodines en el MVP. Se
  documenta en `<details>` («¿Cómo busco?»), no como muro de texto.
- El servidor normaliza (minúsculas, sin acentos, espacios colapsados), limita a **12 tokens** y
  a 100 caracteres; un token desconocido no rompe la pantalla: se pinta un aviso con la salida.
- La URL canónica lleva la expresión en **un** parámetro `etiquetas` (URL-encoded):
  `/ui/biblioteca?etiquetas=noir+-escuela&page=1`.

### 4.4 Namespaces que **no** son tags en este MVP

La especificación (§2.3 y §7.1) ratifica un solo espacio visible, `etiqueta` (D-1). Estos nombres
**no** aparecen en la barra de etiquetas ni en las facetas de esta UI, y la maqueta ya no los inventa:

| Nombre que se ve en la app | Dónde vive de verdad | Por qué no es una etiqueta |
|---|---|---|
| Género | `Series.genres` (`series_genres`, modelo `Genre`) | duplicaría un atributo estructurado; primero hay que poblarlo (BL-ETQ3 / fase 2) |
| Personaje | `Issue.characters` (`issue_characters`, `Character`) | relación estructurada; los filtros de personaje/saga ya existen y se quedan como están |
| Universo | `Universe` | relación estructurada, fuera del MVP de etiquetas |
| Formato | `IssueFormat` / `FileFormat` | atributo del número/archivo, no descriptor libre |
| Público / edad | `AgeRating` (no existe aún) | decisión aparte; **nunca** un namespace de texto (spec D-3) |

Los filtros cerrados que ya existen (tradición, editorial, personaje, saga) **siguen** en Biblioteca
y la ficha no cambia; las etiquetas se suman, no los sustituyen. Exponer alguno de estos en una fase
posterior se hace desde su columna/relación, no como tag (spec §3, NO-goals).

## 5. Flujos críticos, paso a paso

Convención: «fragmento» es HTML parcial devuelto por una ruta `/ui/*`; **nunca JSON**. Carga =
lo que se ve mientras; éxito = lo que sustituye; error = fragmento con 200 y aviso dentro.

### F1. Buscar por etiqueta (autocompletado)

- **Entrada:** Biblioteca, campo «Buscar por etiqueta» vacío; debajo, panel de facetas con las
  etiquetas más usadas.
- **Acción:** escribe ≥2 letras (`noi`).
- **HTMX:** `hx-get="/ui/biblioteca/etiquetas/sugerir"` (la ruta recibe `etiquetas` = la expresión
  del campo; usa el **último token** como prefijo), `hx-trigger="input changed delay:300ms, search"`,
  `hx-target="#sugerencias-etiquetas"`, `hx-swap="innerHTML"`, `hx-sync="this:replace"`,
  `hx-indicator="#cargando-sugerencias"`, `hx-include="closest form"` (explícito: envía el resto de
  filtros; la ruta ignora los parámetros que no declara).
- **Carga:** a los 400 ms aparece «Buscando etiquetas…» (clase `indicador-diferido`); una
  respuesta rápida no parpadea. El campo no se bloquea.
- **Éxito:** lista de ≤8 sugerencias; cada fila: `noir` · `34 series` · enlaces
  «Añadir» y «Excluir». Tab llega a los enlaces; Enter sobre el campo envía la expresión.
- **Vacío:** «Sin coincidencias. Prueba con otras letras.»
- **Error de red:** el fragmento anterior se queda; el aviso del servidor (si llega) aparece
  dentro de la lista. No se inventa un mensaje de éxito.
- **Límites:** mínimo 2 caracteres; máximo 8 sugerencias; sin facetas en esta ruta.

### F2. Filtrar con chips: AND y exclusión

- **Entrada:** sugerencias visibles o panel de facetas.
- **Acción:** «Añadir» de una sugerencia (o clic en una faceta) = **AND**; «Excluir» = **NOT**.
  También se puede escribir `-escuela` y pulsar Enter/Buscar.
- **HTMX:** el enlace ya trae la URL resuelta por el servidor (con la expresión actual más el
  token); `hx-get` a `/ui/biblioteca/resultados`, `hx-target="#rejilla"`,
  `hx-swap="innerHTML"`, `hx-push-url="true"`, `hx-indicator="#cargando-resultados"`. El `href`
  es la misma URL: **sin JS funciona como navegación normal**.
- **Carga:** «Buscando…» junto al botón; la rejilla anterior sigue visible hasta que llega el
  fragmento (no se vacía antes: evita saltos de página).
- **Éxito:** chips actualizados, recuento en región viva, facetas recalculadas, rejilla nueva.
  El campo de texto se sincroniza con la expresión aplicada (swap fuera de banda, §7.4).
- **Error de etiqueta inexistente:** aviso ámbar en el fragmento: «No conocemos la etiqueta
  «noirx». Búscala en la lista de etiquetas.» Los filtros previos **no** se pierden.
- **Repetida:** si la etiqueta ya estaba, no se duplica el chip; se marca el chip existente y el
  recuento no cambia.
- **Exclusión sobre una etiqueta ya incluida:** es un cambio de signo, no un error: el chip pasa
  a «Sin …» (una etiqueta no puede estar incluida y excluida a la vez).

### F3. Quitar filtros

- **Entrada:** chips activos.
- **Acción A — quitar uno:** el chip es un enlace con el icono `x` (SVG); su `href` es la expresión sin ese
  token (los demás filtros intactos). **Acción B — quitar todas las etiquetas:** enlace «Quitar
  etiquetas»; conserva tradición/editorial/personaje/saga/búsqueda por título.
- **HTMX:** misma región `#rejilla`, `hx-push-url="true"`.
- **Carga:** igual que F2. **Éxito:** el chip desaparece, el foco va al campo de etiqueta
  (el fragmento devuelve el campo con `autofocus` en esta respuesta, §7.4), recuento actualizado.
- **Vacío resultante:** si al quitar se llega a «sin filtros de etiqueta», se ve el panel de
  facetas completo y el recuento de la biblioteca; no un estado vacío.
- **Texto exacto:** «Quitar etiquetas» (no «Limpiar», no «Reset»).

### F4. Editar las etiquetas de una serie (ficha)

- **Entrada:** ficha de serie, sección «Etiquetas».
- **Acción A — añadir:** escribe ≥2 letras en «Añadir una etiqueta…», elige una sugerencia
  (`hx-get /ui/series/{id}/etiquetas/sugerir`, mismo debounce, target
  `#sugerencias-etiqueta-serie`), y pulsa «Añadir» o Enter. También se puede escribir
  `noir` completo y pulsar «Añadir».
- **Acción B — quitar:** botón con el icono `x` de un chip (formulario con `input hidden name="etiqueta"`).
- **HTMX:** `hx-post="/ui/series/{id}/etiquetas"` / `…/etiquetas/quitar`, `hx-target="#etiquetas-serie"`,
  `hx-swap="innerHTML"`, `hx-disable="find button"` (evita doble envío), sin `hx-confirm`.
- **Marcado sin formularios anidados:** el campo se asocia al formulario de añadir con
  `form="anadir-etiqueta-serie"` (el input queda **fuera** del `<form>`, junto al desplegable). Cada
  sugerencia es un **formulario POST independiente** con su `input hidden name="etiqueta"` y su
  botón «Añadir»: así no se anidan formularios (HTML inválido) y todo funciona sin JS. La ruta de
  sugerencias recibe `etiqueta` = lo tecleado.
- **Carga:** el botón se deshabilita; la región conserva lo anterior.
- **Éxito:** región viva con los chips en un solo grupo («Etiquetas») + aviso `ok` breve («Etiqueta
  añadida.» / «Etiqueta quitada.»). El foco vuelve al campo de añadir (autofocus del fragmento).
- **Error de validación:** 200 con `ui.aviso("warn", …)` dentro de la región:
  «Esa etiqueta no existe. Elige una de las sugerencias.» / «Esa etiqueta ya estaba en la serie.»
- **Error de servidor:** «No se pudo guardar. Vuelve a intentarlo.»; los chips anteriores se
  mantienen (el fragmento de error incluye el estado actual para no perderlo).
- **Sin etiquetas:** estado vacío compacto + el formulario de añadir. No es un error.

### F5. Estado vacío

| Caso | Título (texto exacto) | Texto | Acción |
|---|---|---|---|
| Filtros de etiqueta sin resultados | «Ninguna serie con estas etiquetas» | «Quita una etiqueta o busca otra.» | «Quitar etiquetas» (enlace a `/ui/biblioteca` conservando el resto de filtros) |
| Biblioteca sin ninguna etiqueta | «Todavía no hay etiquetas» | «Se añaden desde la ficha de una serie. Mientras tanto, tu biblioteca sigue igual.» | «Ver la biblioteca» (ancla a la rejilla) |
| Serie sin etiquetas | «Sin etiquetas todavía» | «Añade una para encontrar esta serie por lo que trata.» | — (el formulario ya está debajo) |
| Búsqueda de etiqueta sin coincidencias | «Sin coincidencias» | «Prueba con otras letras.» | — |

El vacío **no** culpa al usuario ni dice «0 resultados»: dice qué hacer. Se pinta con
`ui.estado_vacio`, que ya tiene trama de esquina y contraste comprobados.

### F6. Errores

| Escenario | Qué ve el coleccionista | Cómo se pinta |
|---|---|---|
| Token desconocido | «No conocemos la etiqueta «{x}». Búscala en la lista de etiquetas.» | `ui.aviso("amber")` dentro del fragmento, 200. Los chips previos se conservan. |
| Demasiadas etiquetas (>12) | «Hay demasiadas etiquetas a la vez. Quita alguna.» | ídem; el servidor aplica las 12 primeras y lo dice. |
| Repetida | «Esa etiqueta ya está en el filtro.» | ídem; sin duplicar chip. |
| Fallo del servidor (500) | «No se pudieron cargar las etiquetas. Vuelve a intentarlo.» + «Volver a la biblioteca» | fragmento 200 con `ui.aviso("warn")`; **no** el JSON de FastAPI. |
| Sin conexión | lo anterior no llega; el navegador conserva la pantalla y el enlace normal del formulario permite reintentar | comportamiento estándar del navegador; sin mensaje inventado. |
| BD caída (E6) | riesgo conocido de `/ui/*` (§11.8); no se diseña aquí | declarado, no resuelto en esta entrega |

## 6. Inventario de rutas y fragmentos

### 6.1 Rutas de página (existentes o ampliadas)

| Método | Ruta | Parámetros | Responde | Estado |
|---|---|---|---|---|
| GET | `/ui/biblioteca` | `page, tradition, publisher_id, character_id, story_arc_id, q, etiquetas` | `biblioteca.html` (chips + facetas + rejilla) | **amplía** la existente (`web/library.py`) |
| GET | `/ui/series/{series_id}` | — | `series_detail.html` con sección «Etiquetas» | **amplía** la existente |

`etiquetas` es **una** cadena con la expresión; se transporta URL-encoded. Los demás parámetros
se conservan tal cual para no romper enlaces existentes.

### 6.2 Rutas de fragmento (nuevas, bajo `/ui`)

| Método | Ruta | Parámetros (Form/Query) | Fragmento | Uso |
|---|---|---|---|---|
| GET | `/ui/biblioteca/resultados` | los mismos que la página | `_rejilla_biblioteca.html` ampliado | sustituye `#rejilla` (1b) |
| GET | `/ui/biblioteca/etiquetas/sugerir` | `etiquetas` (expresión; el **último token** se usa como prefijo, ≥2) | `_sugerencias_etiquetas.html` | lista de ≤8 sugerencias |
| GET | `/ui/series/{series_id}/etiquetas/sugerir` | `etiqueta` (lo tecleado, ≥2) | `_sugerencias_etiqueta_serie.html` | sugerencias de la ficha |
| POST | `/ui/series/{series_id}/etiquetas` | `etiqueta`* (Form) | `_etiquetas_serie.html` | añade una etiqueta a la serie |
| POST | `/ui/series/{series_id}/etiquetas/quitar` | `etiqueta`* (Form) | `_etiquetas_serie.html` | quita una etiqueta de la serie |

Reglas de diseño de backend (no código aquí):

- Los routers son finos; la lógica va a `services/` (`CLAUDE.md` §3.1.1): `buscar_etiquetas`,
  `facetas`, `etiquetas_de_serie`, `anadir_etiqueta`, `quitar_etiqueta`. La plantilla **no**
  parsea la expresión ni resuelve nombres.
- Campos `Form(...)` explícitos, validados (nombre normalizado, ≤100 caracteres, 1 token);
  nada de `Model(**data)` ni `setattr` sobre cuerpo crudo (§3.1.3).
- Sin gate legal: etiquetar no descarga ni envía nada. Sin `hx-confirm`: no hay efecto
  destructivo.
- Respuestas de error recuperables: **200 + fragmento con aviso**. 404 solo si la serie no
  existe en la ruta de página; 422 solo si el formulario llega sin `etiqueta` o con un valor
  imposible (y aun así, la UI no lo provoca: el campo es `required` y hay validación).
- Los enlaces de sugerencia de Biblioteca los construye el **servidor** con la expresión actual
  más el token (`?etiquetas=<actual> <token>` o `-<token>`) y apuntan a
  `/ui/biblioteca/resultados`; la plantilla no concatena URLs de filtros.
- `Cache-Control: no-store` en fragmentos con estado (mismo criterio que las vistas previas del
  repo), para que el botón Atrás no mezcle filtros.

### 6.3 El fragmento `_rejilla_biblioteca.html` ampliado (1b)

Un solo fragmento, en este orden (los ids se usan como destino/region):

1. `#filtros-activos` — chips de etiqueta (`.chip-etiqueta`, `.excluir`) + «Quitar etiquetas».
2. `<h2>Etiquetas de tu biblioteca</h2>` + `#facetas-biblioteca` — **un solo** `ui.grupo`
   («Etiquetas», máx. 8 chips) con chips-enlace y recuento. El `h2` va **dentro**
   del fragmento para que no queden `h3` (`ui.grupo`) colgando del `h1` tras el intercambio.
3. `#estado-resultados` — `ui.region_viva`: recuento en español llano.
4. Rejilla o `ui.estado_vacio`.
5. Paginación (24 por página, `.pagination`), con `etiquetas` incluido en la URL.
6. **Fuera de banda:** `<input id="f-etiquetas" … hx-swap-oob="outerHTML">` con la expresión
   aplicada y (solo en respuestas a «quitar chip») `autofocus`. Es lo que sustituye al JS de
   sincronizar campo y chips.

El fragmento **no** repite layout, `<h1>`, nav ni pie (misma regla que `test_web_library`).

### 6.4 Atributos `hx-*` exactos por elemento

| Elemento | Atributos |
|---|---|
| `<form id="filtros">` | `action="/ui/biblioteca" method="get" hx-get="/ui/biblioteca/resultados" hx-target="#rejilla" hx-swap="innerHTML" hx-trigger="submit, change from:#f-tradition, change from:#f-publisher" hx-push-url="true" hx-indicator="#cargando-resultados" hx-sync="this:replace"` |
| `<input type="search">` de etiqueta | `name="etiquetas" hx-get="/ui/biblioteca/etiquetas/sugerir" hx-trigger="input changed delay:300ms, search" hx-target="#sugerencias-etiquetas" hx-swap="innerHTML" hx-sync="this:replace" hx-include="closest form" hx-indicator="#cargando-sugerencias" aria-describedby="ayuda-etiquetas"` |
| Enlace «Añadir»/«Excluir»/faceta/chip | `href` real + `hx-get` + `hx-target="#rejilla" hx-swap="innerHTML" hx-push-url="true"` |
| Formulario de quitar etiqueta (ficha) | `action="/ui/series/{id}/etiquetas/quitar" method="post"` + `hx-post=… hx-target="#etiquetas-serie" hx-swap="innerHTML" hx-disable="find button"` |
| Formulario de añadir (ficha) | `action="/ui/series/{id}/etiquetas" method="post"` + `hx-post=… hx-target="#etiquetas-serie" hx-swap="innerHTML" hx-disable="find button"`; el campo se asocia con `form="anadir-etiqueta-serie"` |
| Sugerencia de la ficha | formulario POST propio (`action`/`method` + `hx-post` + `input hidden name="etiqueta"` + botón «Añadir»); nunca dentro de otro `<form>` |
| Enlace «Añadir»/«Excluir» de sugerencia (biblioteca) | `href` real a `/ui/biblioteca/resultados?etiquetas=…` + `hx-get` a la misma URL + `hx-target="#rejilla" hx-swap="innerHTML" hx-push-url="true"` |
| Indicadores | `<span id="cargando-resultados" class="htmx-indicator" role="status">Buscando…</span>` y `<span id="cargando-sugerencias" class="htmx-indicator indicador-diferido" role="status">Buscando etiquetas…</span>` |

**Todos los controles tienen `href`/`action` reales.** Sin htmx (o sin JavaScript) la búsqueda y
los enlaces funcionan como navegación normal; los botones POST de la ficha son formularios
normales. Esto es requisito, no extra.

### 6.5 Límites de las sugerencias y de las facetas

| Límite | Valor | Motivo |
|---|---:|---|
| Mínimo de caracteres para sugerir | 2 | menos = ruido y consulta cara |
| Sugerencias por respuesta | 8 | se leen sin scroll; HTML ≤ ~4 KB |
| Grupos de facetas visibles | 1 («Etiquetas») en el MVP | es el único espacio ratificado (D-1, spec §2.3/§7.1); el resto de nombres no son tags (§4.4) |
| Etiquetas por grupo de faceta | 8 | el resto, tras «Ver todas las etiquetas» (fase 2) |
| Tokens de filtro por búsqueda | 12 | presupuesto de consulta y de URL |
| Resultados por página | 24 (existente) | no se cambia |
| Longitud de etiqueta | 64 caracteres (validación de la spec; la columna `Tag.name` sigue en 100, pero el CHECK limita a 64) | no se escribe ni se acepta más |

## 7. Contratos HTMX y comportamiento sin JS

### 7.1 Estado en la URL

La expresión vive en `?etiquetas=` (un parámetro, URL-encoded) y el resto de filtros en sus
parámetros actuales. **El estado canónico es la URL**, no el DOM: recargar, compartir o el botón
Atrás reconstruyen la pantalla. `hx-push-url="true"` en todo lo que cambie filtros; las
sugerencias **no** cambian la URL (son una ayuda de escritura).

### 7.2 Debounce y descarte de respuestas viejas

- `input changed delay:300ms` en el campo de etiqueta. `search` añade el evento de pulsar Intro
  en el campo de búsqueda (nativo de `type="search"`).
- `hx-sync="this:replace"` en el campo: si llega una respuesta de una consulta anterior, se
  descarta; una sola petición en vuelo. Evita el parpadeo de listas que se pisan.
- En el formulario, `hx-sync="this:replace"`: un cambio de filtro no se encola detrás de otro.

### 7.3 Estados de carga

- `htmx-indicator` + `role="status"`: «Buscando…» / «Buscando etiquetas…». El indicador **no**
  bloquea la pantalla y no se anuncia dos veces (el recuento final va a la región viva).
- La rejilla anterior se mantiene hasta que llega el fragmento; no se pinta un esqueleto que
  haga saltar la página en la Pi.
- El botón «Añadir» de la ficha se deshabilita mientras dura el POST (`hx-disable`), y el
  CSS global de `[disabled]` ya lo pinta atenuado (`web.css` §16c).

### 7.4 Sincronizar el campo y quitar el foco perdido, sin JS

- `hx-swap-oob` en el fragmento para reemplazar `#f-etiquetas` por su versión con la expresión
  aplicada. Así «Añadir» desde una sugerencia actualiza el campo sin que el usuario tenga que
  reescribirlo.
- **Foco:** al quitar un chip, el fragmento incluye el campo con `autofocus` (htmx lo enfoca tras
  el swap). Al añadir desde una sugerencia, el enlace pulsado **no** se elimina (la lista sigue
  abierta hasta la siguiente tecla), así que el foco se conserva. En la ficha, el fragmento
  devuelve el campo «Añadir una etiqueta…» con `autofocus` tras un quitar.
  - **A verificar en htmx 4.0.0** que `autofocus` en contenido OOB/intercambiado mueve el foco
    (marcado NOT RUN en §12; si no lo hiciera, se resuelve con `hx-focus` o dejando el foco en el
    destino, no con JS a mano).
- La lista de sugerencias **no** se limpia por swap fuera de banda: vive fuera de
  `#rejilla`, así que el fragmento no la sustituye; se queda hasta la siguiente
  pulsación de tecla (permite añadir varias etiquetas seguidas sin perder el foco).

### 7.5 Códigos y errores

- **200** siempre que el fragmento se pueda pintar (incluidos errores de validación y fallos
  controlados). htmx 4 intercambia cualquier estado ≠ 204/304 (`ui-migracion.md` §2.5); devolver
  `{"detail": …}` pintaría el JSON en la rejilla, el defecto ya documentado de `asignar`.
- **404** solo en rutas de página (serie inexistente) y lo pinta la página de error del repo.
- **403 legal** no aplica: no hay acción de riesgo.
- **Sin 204** en fragmentos con aviso: un 204 no intercambia y el usuario no vería nada.

### 7.6 Sin JavaScript propio nuevo (justificación y límites aceptados)

- Se usa HTMX declarativo y CSS; ninguna plantilla nueva lleva `<script>`, `onclick` ni
  `onerror` (ADR 0005).
- **No se implementa** el patrón ARIA combobox con flechas ni `alt`-clic: detectar `altKey`
  exige JS y `accesskey` choca con atajos del navegador. Se sustituye por:
  - dos enlaces explícitos «Añadir» / «Excluir» en cada sugerencia (enfocables con Tab),
  - el prefijo `-` escrito en el campo (Enter/Buscar lo aplica),
  - `search` nativo del input para enviar.
- **No** se usa `<datalist>`: no permite recuentos ni el control del orden por uso/similitud, y
  con miles de etiquetas obliga a servir toda la lista. [Decisión de diseño, no se ha medido en
  navegador.]
- Los formularios POST de la ficha funcionan sin htmx (envío normal); htmx solo mejora el
  refresco parcial.

## 8. Textos exactos y presupuesto de texto (CLAUDE.md §6 / U21)

### 8.1 Frase de entrada y presupuesto

- Biblioteca: `<h1>Biblioteca</h1>` + `«34 series catalogadas. Filtra por lo que tratan.»`
  (**8 palabras**; el número es dato, no frase). Antes de la primera acción: ≈ **38 palabras**
  visibles contando ayudas y controles (**47** si se suman las etiquetas solo de lector de
  pantalla); **≤50**.
- Ficha de serie: `«Lo que tratan tus tebeos. Se guarda al momento; no toca los archivos.»`
  (**13 palabras**). El resto, en `<details>`.
- Las explicaciones largas van en `<details>`: «¿Cómo busco?» y «¿De dónde salen las
  etiquetas?». Mayúsculas solo en rótulos de ≤3 palabras (h1/h2 de la pantalla).

### 8.2 Tabla de textos (usar literalmente)

| Clave | Texto |
|---|---|
| Etiqueta del campo | «Buscar por etiqueta» (visible solo para lector de pantalla; placeholder «Etiqueta, p. ej. noir») |
| Ayuda bajo el campo | «Separa con espacios. Pon «-» delante para excluir.» |
| Sugerencias | «Añadir» / «Excluir» (con `aria-label` «Añadir noir» / «Excluir noir») |
| Recuento sugerencia | «34 series» / «1 serie» |
| Chip de exclusión | «Sin escuela» (con icono `minus` y borde discontinuo) |
| Quitar chip | `aria-label` «Quitar etiqueta noir» / «Quitar la exclusión de escuela» |
| Quitar todas | «Quitar etiquetas» |
| Panel de facetas | «Etiquetas de tu biblioteca» |
| Recuento resultados | «34 series con noir.» / «5 series con noir y escuela.» / «No se muestran las de escuela.» |
| Cargando | «Buscando…» / «Buscando etiquetas…» |
| Sugerencias vacías | «Sin coincidencias. Prueba con otras letras.» |
| Etiqueta desconocida | «No conocemos la etiqueta «{x}». Búscala en la lista de etiquetas.» |
| Demasiadas | «Hay demasiadas etiquetas a la vez. Quita alguna.» |
| Repetida | «Esa etiqueta ya está en el filtro.» |
| Fallo de carga | «No se pudieron cargar las etiquetas. Vuelve a intentarlo.» + «Volver a la biblioteca» |
| Ficha, título de sección | «Etiquetas» |
| Ficha, introducción | «Lo que tratan tus tebeos. Se guarda al momento; no toca los archivos.» |
| Ficha, añadir | «Añadir una etiqueta…» / botón «Añadir» (neutro) |
| Ficha, quitar | `aria-label` «Quitar noir de esta serie» |
| Ficha, éxito | «Etiqueta añadida.» / «Etiqueta quitada.» |
| Ficha, duplicada | «Esa etiqueta ya estaba en la serie.» |
| Ficha, inexistente | «Esa etiqueta no existe. Elige una de las sugerencias.» |
| Ficha, error | «No se pudo guardar. Vuelve a intentarlo.» |
| Details biblioteca | «¿Cómo busco?» → «Escribe una etiqueta y elige una sugerencia. Varias etiquetas se suman: la serie tiene que tenerlas todas. Con «-» delante, la quitas del resultado.» (**24 palabras**) |
| Details ficha | «¿De dónde salen?» → «Pueden venir de la propia ficha, de ComicInfo o de las fuentes de metadatos. Aquí solo cambias las de esta serie.» (**21 palabras**) |

Nada de «token», «API», «filtro booleano», «namespace», «exit code», «error 500» ni códigos
internos en superficie. El único grupo del MVP se rotula en español llano (**Etiquetas**) y en la
sintaxis va el nombre en minúscula, sin prefijo (`noir`). `genero`, `personaje`, `universo`,
`formato` y `publico` no son tags en este MVP (§4.4).

## 9. Accesibilidad

### 9.1 Contraste (WCAG 2.x, calculado sobre los tokens de `web.css`)

| Par usado | Claro | Oscuro | Mínimo | Veredicto |
|---|---:|---:|---:|---|
| `--ink` sobre `--paper` (texto general) | 16,14:1 | 15,84:1 | 4,5 | PASS |
| `--ink` sobre `--paper-2` (tarjetas/facetas) | 14,91:1 | 14,65:1 | 4,5 | PASS |
| `--ink-faint` sobre `--paper` (texto secundario, ≥14 px) | 5,37:1 | 6,66:1 | 4,5 | PASS |
| `--ink-faint` sobre `--paper-2` | 4,96:1 | 6,16:1 | 4,5 | PASS |
| `--warn-t` sobre `--warn-bg` (chip/aviso de exclusión y error) | 5,50:1 | 6,55:1 | 4,5 | PASS |
| `--ok-t` sobre `--ok-bg` (aviso de éxito) | 5,57:1 | 7,41:1 | 4,5 | PASS |
| `--amber-t` sobre `--amber-bg` (aviso ámbar) | 5,60:1 | 9,87:1 | 4,5 | PASS |
| `--cyan-t` sobre `--info-bg` | 5,15:1 | 7,58:1 | 4,5 | PASS |
| `--paper` sobre `--ink` (foco/estado seleccionado) | 16,14:1 | 15,84:1 | 4,5 | PASS |

Cálculo reproducido con la fórmula de luminancia relativa de WCAG 2.x sobre los valores de
`web.css` (script de ~20 líneas, ver §12). Ninguna clase nueva de este diseño usa un relleno
(`--cyan`, `--ok`, `--warn`, `--magenta`, `--yellow`) como color de texto. La exclusión **no** se
transmite solo por color: borde discontinuo + icono `minus` + la palabra «Sin». El nombre va
escrito.

### 9.2 Foco y teclado

- `:focus-visible` global (outline `--cyan-t` 3 px, offset 2 px) se hereda; los enlaces-chip y
  los botones `×` no lo anulan. Las clases nuevas no ponen `outline: none`.
- **Orden de tabulación** en Biblioteca: salto al contenido → nav → h1/frase → campo de título →
  tradición → editorial → campo de etiqueta → enlaces «Añadir»/«Excluir» de las sugerencias (si
  están abiertas) → chips activos (quitar) → «Quitar etiquetas» → facetas → tarjetas → paginación.
- **Enter** en el campo de etiqueta = Buscar. **Tab** recorre sugerencias; **Enter** activa la
  enfocada. **Esc** no se necesita (no hay ventana modal); si las sugerencias molestan, seguir
  escribiendo o enviar.
- Quitar un chip devuelve el foco al campo (autofocus del fragmento, §7.4) para no dejar al
  teclado perdido. En la ficha, tras quitar, el foco va al campo de añadir.
- No hay trampas de foco, ni atajos de un solo carácter, ni `accesskey`.

### 9.3 Lector de pantalla

- Recuento y panel de etiquetas: `ui.region_viva` (`aria-live="polite"`, `aria-atomic="true"`),
  **corto** (una frase). La rejilla de tarjetas **no** es región viva (sería un muro de texto).
- Cada chip de quitar es un control con nombre accesible: «Quitar etiqueta noir». El
  icono `×` es `aria-hidden="true"`; el texto del chip es el nombre de la etiqueta.
- Las sugerencias son una `<ul aria-label="Sugerencias de etiquetas">` con enlaces; los recuentos
  se leen como parte del enlace («Añadir noir, 34 series»). No se usa `role="listbox"`
  porque no hay navegación con flechas: sería un rol que promete un teclado que no existe.
- El aviso de error es `ui.aviso("amber"|"warn")` (`role="status"`/`alert`), nunca un `div` mudo.
- Los iconos decorativos (`x`, `minus`, `tag`, `search`) son SVG `aria-hidden="true"`; los
  nombres los da el texto, nunca el icono.

### 9.4 Tamaño, táctil y tipografía

- Todo el texto informativo nuevo ≥ **14 px** (`.875rem`); el texto de los chips ya es `.875rem`;
  los campos, 16 px en móvil (regla U16 existente). No se introduce ninguna excepción nueva.
- Objetivos táctiles: controles de formulario ≥44 px en táctil (regla existente). El botón de
  quitar mide **24×24 CSS px** en escritorio (mínimo WCAG 2.2, 2.5.8) y **44×44** con
  `@media (max-width: 860px), (pointer: coarse)` (§Anexo A); medido en la maqueta. Los enlaces de
  sugerencia también suben a 44 px en ese caso. Los chips no son un objetivo de 44 px por sí
  solos: el control de quitar es un botón separado con su área y su `aria-label`.
- Anton solo en rótulos ≤3 palabras (h1 «Biblioteca», h2 «Etiquetas»); los textos y los chips van
  en Archivo (el chip ya fija `font-family: var(--font-body)` en `web.css`).
- Cifras de recuento con `font-variant-numeric: tabular-nums` para que las columnas de facetas no
  bailen.
- `prefers-reduced-motion`: sin animaciones nuevas (no hay transiciones en los chips nuevos).
  `prefers-contrast: more`/`forced-colors`: los chips usan tokens que ya se recomputan; no se
  añade trama nueva.
- **No depender solo del color:** ya cubierto (nombre escrito, borde discontinuo + icono en
  exclusión, `aria-current`/estado seleccionado además del relleno).

## 10. Rendimiento en la Pi (presupuesto)

| Interacción | Consultas | Límites duros | Notas |
|---|---:|---|---|
| Teclear en el campo de etiqueta | 1 por pausa de 300 ms; la anterior se descarta | `q` ≥2 chars; `LIMIT 8`; 1 consulta con `GROUP BY` | Sin facetas, sin contar la biblioteca entera. Índice trigram sobre el nombre (ya propuesto en el anexo; **sin verificar** que `pg_trgm`/`unaccent` estén en la instalación: lo comprueba `task-1`/`task-5`). |
| Enviar búsqueda / añadir / quitar chip / faceta | ≤3: resultados + total, facetas, (sin más) | 24 por página; facetas 1×8; `COUNT(DISTINCT)` solo si hay joins | Un solo viaje: chips+facetas+rejilla van en **el mismo** fragmento. Nada de una petición por chip. |
| Carga inicial de Biblioteca sin filtros | ≤2 (serie + facetas) | facetas 1×8 | Las «estanterías» de descubrimiento (fase 2) cargan por `hx-trigger="revealed"`: 3 filas × 1 consulta, **solo al entrar en pantalla**. |
| Añadir/quitar etiqueta en ficha | 1–2 (serie + etiquetas) | 1 etiqueta por envío | Sin mover archivos ni tocar el importador (`CLAUDE.md` §3.1.2 no aplica aquí). |
| Paginación | 1 (reutiliza el fragmento) | 24 | La URL de página **debe** conservar `etiquetas`; si se pierde, el bug es de datos, no de rendimiento. |

Reglas:

- **Nunca una consulta de facetas por tecla.** Las facetas solo se recalculan al cambiar un
  filtro (envío/ENLACE), no al escribir.
- El HTML de sugerencias va acotado (≤8 filas, ≤~4 KB). Sin imágenes, sin iconos repetidos: el
  icono `x` se sirve una vez como SVG en línea solo donde hace falta (o CSS con `mask` no: se
  mantiene igual que `icono()`).
- Sin vistas materializadas, sin caché externa (ADR-0011), sin nuevas dependencias. Si en la Pi
  `COUNT(*)` con filtros se nota, la salida es **«Ver más» sin recuento exacto** (fase 2), no una
  caché nueva.
- **Medido en la maqueta** (Chrome 156): el campo de etiqueta mide **380 px** en escritorio y
  **351 px** a 390 px de ancho; el desplegable se ajusta a esa caja. Ningún ancho revisado hace
  scroll horizontal (§12).
- La consulta de sugerencias debe usar el índice trigram y `ORDER BY similarity(...) DESC,
  usage DESC LIMIT 8`; la de facetas, `GROUP BY tag_id` con índice por `tag_id` (el anexo de la
  propuesta lo detalla; su verificación es de `task-1`). Esta UI no impone el plan de consulta,
  solo los topes.

## 11. Riesgos y lo que NO se diseña todavía

1. **Modelo ratificado (spec §2/§7.1), riesgo residual en la UI.** `tags` gana `namespace` y se
   añade `series_tags` en **0022**; `issue_tags` queda dormida. El contrato de superficie usa el
   **nombre** normalizado y **no** filtra UUIDs; si una fase posterior cambia el nivel, solo cambia
   el servicio que traduce, no las rutas.
2. **Etiquetado por número (fase posterior).** El MVP es a nivel de **serie** (spec §2.2) y no
   agrega etiquetas de número en silencio. Si se activa `issue_tags` en una fase posterior, el
   filtro pasa a `EXISTS` sobre números: más caro en la Pi y otra UX (¿qué número?). No diseñado.
3. **Sintaxis sin OR/alias/implicaciones.** Un token desconocido **no** se aplica: aviso (spec
   AC-09), nunca una elección silenciosa. Las sugerencias muestran el nombre normalizado; alias e
   implicaciones son fase posterior.
4. **Facetas y exclusiones (ratificado).** Los recuentos cuentan con los tokens positivos y las
   exclusiones **no** descuentan (spec FR-08/AC-08); el texto del recuento lo aclara.
5. **Paginación que pierde `etiquetas`.** `_rejilla_biblioteca.html::pagina_url` construye la URL a
   mano; hoy no incluye `etiquetas`. Si se implementa sin tocarla, la página 2 pierde los tags.
   Debe entrar en la misma historia y en su prueba de regresión.
6. **Foco tras intercambio.** Depende de que htmx 4 enfoque `autofocus` en el contenido
   intercambiado. **NOT RUN** aquí (no hay backend). Si no lo hace, plan B declarado en §7.4
   (dejar el foco en el destino o `hx-focus`), nunca JS a mano.
7. **Etiquetas de fuentes externas y ComicInfo.** En el MVP la UI solo muestra y asigna; leer
   `<Tags>`/`<Genre>` es fase 1b y escribir/exportar es fase 4 (spec §2.5/§3). La entrada de datos
   y su validación son de otras historias; aquí se exige autoescape y `urlencode` (nunca `|safe`
   con nombres de etiqueta).
8. **BD caída / `/ui/*` degradado.** De `ui-migracion.md` §2.1: con la BD caída, `/ui/*` puede
   responder `500`/`503` con HTML. En una ruta de fragmento, htmx 4 lo intercambiaría dentro de la
   rejilla. **Riesgo conocido, no se resuelve en esta entrega**; se anota para V9/errores.
9. **Biblioteca grande.** Sugerencias y facetas tienen topes, pero el recuento exacto de
   resultados puede ser caro con muchas series y joins. Plan B: «Ver más» sin total exacto.
10. **«Netflix» puede comerse el presupuesto.** Estanterías = más consultas y más imágenes. Van
    fuera del MVP y con carga diferida; si la Pi no da, no se hacen o se reducen a 2 filas.
11. **No se diseña todavía:** crear etiquetas nuevas desde la UI; renombrar/fusionar etiquetas;
    alias y «padres»/implicaciones visibles; filtros guardados («smart filters»); etiquetado
    masivo ni por lote; exportar a `ComicInfo.xml` (es B6 y tiene su contrato); botón «etiquetar
    automáticamente»; OR y comodines; orden configurable de la rejilla; recuentos exactos con
    exclusiones; estanterías personalizadas; administración de namespaces; etiquetas por número.
12. **`hx-include="closest form"` y formularios asociados.** El campo de Biblioteca pide las
    sugerencias incluyendo explícitamente su formulario (la ruta ignora los parámetros que no
    declara); en la ficha, el campo se asocia con `form="…"` y las sugerencias son formularios
    POST independientes para **no anidar formularios**. Esa estructura hay que probarla con htmx
    4 (NOT RUN aquí): que una sugerencia envía **solo** su `etiqueta` y que Enter en el campo
    envía lo tecleado.
13. **El desplegable tapa facetas o contenido** (comportamiento normal de autocompletar). Si en
    pruebas con El Coleccionista molesta, la alternativa es un panel fijo o `<details>`, no JS;
    se decide con datos.
14. **No se copian** textos, iconos ni diseños de Hydrus, Kavita, Calibre-Web o Netflix
    (`CLAUDE.md` §13): se copian patrones, y los iconos nuevos son de Lucide con su aviso.

## 12. Verificación de la maqueta (honesta)

> **Nota de vigencia (2026-11-07).** Las medidas de esta sección se tomaron sobre la maqueta con
> los tres espacios antiguos (`tema`, `motivo`, `etiqueta`). Siguen siendo válidas para el
> **aspecto**, el contraste, el tamaño táctil y el reflow; **no** para el número de grupos ni los
> prefijos, que la v0.3 reduce a un solo grupo («Etiquetas») sin prefijo. La maqueta no se
> regeneró para no reescribir la evidencia.

Entorno: **`google-chrome 156.0.8078.47`** headless, sin backend ni Postgres. La maqueta se sirvió
desde un `http.server` **temporal y de solo lectura** (script de ~20 líneas que sirve la raíz del
repo y enruta `/static/*` a `src/zascarr/static/`), solo para que resolvieran las fuentes y la
marca; también se abrió **directamente con `file://`** (sin servidor). Las capturas se guardan en
`/tmp` y **no se versionan**: el encargo solo permite escribir `docs/design/ui-etiquetas.md` y
`docs/design/maqueta-etiquetas.html`. Los comandos quedan aquí para reproducirlas.

La base de la maqueta se generó con el entorno Jinja del repo (`crear_templates()` +
`_componentes.html`): el shell (`base.html`, `ui.menu`), los avisos (`ui.aviso`), los vacíos
(`ui.estado_vacio`), las regiones vivas (`ui.region_viva`) y las portadas (`ui.portada`) son la
salida real de las macros. Tras ratificarse los namespaces del MVP, los bloques de **datos**
(chips, facetas y etiquetas de la ficha) se reescribieron sobre esa salida con `tema:`, `motivo:` y
`etiqueta:`. HTMX no se carga a propósito: la maqueta no envía peticiones.

```bash
# reproducción (los ficheros temporales viven en /tmp)
python3 /tmp/servidor_maqueta.py &              # raíz del repo + /static -> src/zascarr/static
google-chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=1280,4700 --virtual-time-budget=7000 \
  --screenshot=/tmp/biblioteca-etq-claro.png \
  http://127.0.0.1:8766/docs/design/maqueta-etiquetas.html
# oscuro: copia temporal con el conmutador marcado; móvil: dentro de un iframe de 390 px
# file:// sin servidor: la captura sale idéntica a la servida (mismo MD5)
```

| Comprobación | Resultado | Evidencia / medida |
|---|---|---|
| Namespaces de la barra y de las facetas | **PASS** | solo `tema:` (Temas), `motivo:` (Motivos) y `etiqueta:` (Etiquetas): **3 grupos**, 17 chips de faceta; 0 chips de `genero`/`personaje`/`publico` (solo se nombran en la nota «no son tags») |
| Ficha de serie | **PASS** | **3 grupos** (`Temas`, `Motivos`, `Etiquetas`) con 2+2+2 chips y sugerencias de esos tres namespaces |
| Recuento en región viva | **PASS** | «34 series con tema:humor. No se muestran las de motivo:viajes.» (medido en el DOM) |
| La maqueta abre con `web.css` real | **PASS** | fondo `rgb(246,243,236)`, Anton/Archivo y marca visibles |
| Se abre **sin servidor** (`file://`) | **PASS** | captura `file://` con **MD5 idéntico** a la servida (misma imagen byte a byte) |
| Variante oscura | **PASS** | fondo `rgb(19,19,22)` con el conmutador marcado |
| Escritorio 1280 px sin desplazamiento horizontal | **PASS** | `scrollWidth = clientWidth = 1265` |
| Móvil 390 px reales (iframe) sin desplazamiento | **PASS** | `scrollWidth = clientWidth = 375` |
| Texto informativo < 14 px | **PASS** | 0 elementos (excluida la excepción declarada `.nav-enlace`) |
| Objetivo de quitar etiqueta | **PASS** | 24×24 px en escritorio; 44×44 px con `max-width:860px`/táctil |
| Sin JS propio ni caracteres como iconos | **PASS** | 0 `<script>`, 0 atributos `on*`; `x`/`minus` son SVG en línea |
| Sin hotlinking | **PASS** | 0 `src`/`url()` http(s) externos; 0 `<img>` (marcadores locales de `ui.portada`) |
| HTML consistente | **PASS** | 31 `id` únicos; 11 formularios con `action` y `method`; 0 `<a>` sin `href`; 0 `input` sin etiqueta; 179 atributos `hx-*` inertes para revisar; encabezados h1→h2→h3 |
| Contraste de los pares usados ≥4,5:1 | **PASS** | cálculo WCAG §9.1 (mínimo 4,96:1 en claro y 6,16:1 en oscuro) |
| Teclado real, foco visible y lector de pantalla | **NOT RUN** | sin automatización de accesibilidad ni backend |
| Contratos HTMX (peticiones, swap, `autofocus`, OOB) | **NOT RUN** | la maqueta no carga htmx: `window.htmx === undefined` |
| Rendimiento en Raspberry Pi | **NOT RUN** | sin Pi ni datos reales; solo el presupuesto §10 |

**El PASS de la maqueta no es un PASS del producto.** Demuestra que el diseño cabe en el
CSS/tokens/macros reales, que los tres namespaces del MVP caben en la barra, las facetas y la ficha,
y que se ve en claro, oscuro y a 390 px; los flujos, el teclado y los contratos se verifican al
implementarlos.

## 13. Decisiones ratificadas y huecos que quedan

**Fijadas por `especificacion-etiquetas.md` (D-1…D-7 ratificadas por el PO el 2026-11-06; aquí no se reabren):**

1. **Espacio visible del MVP:** `etiqueta` (spec §2.3/§7.1, D-1). La persona escribe el nombre sin
   prefijo; `genero`, `personaje`, `universo`, `formato` y `publico` no son tags (§4.4).
2. **Nivel serie:** `series_tags`; `issue_tags` dormida (spec §2.2). La UI no agrega etiquetas de
   número.
3. **Facetas y exclusiones:** recuentos con los tokens positivos; las exclusiones no descuentan
   (spec FR-08/AC-08).
4. **Contratos:** rutas y parámetros de §6.2 son los de spec §7.2; 200 con aviso para errores
   recuperables; sin JS propio nuevo.
5. **Fuera del MVP:** alias, implicaciones, OR, smart filters y export a ComicInfo (spec §2.6/§3);
   las estanterías de descubrimiento quedan en fase 2.

**Huecos que siguen abiertos (no bloquean este diseño de UI):**

- **D-2 — idioma de las etiquetas de fuentes.** Afecta a textos y normalización, no al layout.
- **D-3 — `publico`/`AgeRating`.** Columna estructurada en historia aparte; nunca un namespace de
  texto.

**D-6 (ratificada el 2026-11-06):** crear etiquetas desde la ficha es una acción explícita
(«Crear «…»») con confirmación y `source='manual'`; forma parte de BL-ETQ1a. La maqueta anterior no
muestra «Crear» y no se regeneró.

## Anexo A — CSS propuesto (para `web.css`, sección nueva)

La maqueta lo incluye en línea para poder verse; **no se ha tocado `web.css`**. Todo sale de
tokens existentes; una prueba de contraste debe cubrirlo cuando entre.

```css
/* ── Etiquetas (propuesto para web.css) ────────────────────────────────────
   Todo sale de tokens existentes; no se añade ningún color nuevo. */

/* Filtros activos: chips que quitan su etiqueta (o su exclusión) */
.filtros-etiquetas { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-etiqueta {
  text-decoration: none; cursor: pointer; min-height: 24px;      /* WCAG 2.2, 2.5.8 */
  font-variant-numeric: tabular-nums;
}
.chip-etiqueta:hover { background: var(--caption-bg); color: var(--ink); }
.chip-etiqueta .quitar { width: 14px; height: 14px; flex: none; }  /* SVG hereda currentColor */
.chip-etiqueta.excluir {                                          /* no depende solo del color */
  background: var(--warn-bg); color: var(--warn-t); border-style: dashed;
}
.chip-prefijo { font-weight: 800; display: inline-flex; align-items: center; gap: 2px; }
.chip .cuenta { font-size: .875rem; font-weight: 700; color: var(--ink-faint); }
.chip-etiqueta:hover .cuenta { color: inherit; }

/* Facetas: reutiliza .group/.ghead con rejilla de chips */
.facetas { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--gutter); }
.facetas .group { margin-bottom: 0; }
.facetas-chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 12px 16px; }
.facetas-chips .chip { text-decoration: none; }
.facetas-chips .chip[aria-current="true"] { background: var(--ink); color: var(--paper); }
.facetas-chips .chip[aria-current="true"] .cuenta { color: var(--paper); }

/* Campo de búsqueda de etiquetas y desplegable de sugerencias:
   reutiliza .filter-search-box/.series-results; solo se fija el ancho */
.filter-search-box-etiquetas { flex: 0 1 380px; min-width: 320px; }
.filter-search-box-etiquetas input[type="search"] { width: 100%; }
.sugerencia-fila {
  display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; padding: 6px 0;
  border-bottom: 2px dashed color-mix(in srgb, var(--ink) 22%, transparent);
}
.sugerencia-fila:last-child { border-bottom: 0; }
.sugerencia-fila form { margin: 0; }
.sugerencia-fila button { min-height: 24px; padding: 2px 10px; box-shadow: none; }
.sugerencia-etiqueta { flex: 1 1 10rem; min-width: 0; font-weight: 700; overflow-wrap: anywhere; }
.sugerencia-fila .cuenta { color: var(--ink-faint); font-size: .875rem; font-variant-numeric: tabular-nums; }
.sugerencia-fila a { min-height: 40px; }

/* Ficha de serie: etiquetas en un solo grupo y formulario de añadir */
.etiquetas-serie { display: flex; flex-direction: column; gap: 12px; }
.etiquetas-lista { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; margin: 0; padding: 12px 16px; }
.etiquetas-lista form { margin: 0; display: inline-flex; align-items: center; gap: 2px; }
.chip-quitar {
  min-height: 24px; min-width: 24px; padding: 2px;
  background: transparent; border: 0; box-shadow: none; color: var(--ink-soft); cursor: pointer;
}
.chip-quitar:hover { color: var(--warn-t); transform: none; box-shadow: none; }
.etiquetas-anadir { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-start; }
.etiquetas-anadir .filter-search-box { flex: 0 1 440px; }
.etiquetas-anadir .filter-search-box .series-results { top: calc(100% + 4px); }

/* Táctil y pantallas estrechas: el control de quitar y las acciones de sugerencia a 44 px */
@media (max-width: 860px), (pointer: coarse) {
  .chip-quitar, .sugerencia-fila a, .sugerencia-fila button { min-height: 44px; min-width: 44px; }
}
@media (max-width: 860px) {
  .filter-search-box-etiquetas { flex: 1 1 100%; min-width: 0; }
}
@media (max-width: 480px) {
  .sugerencia-etiqueta { flex: 1 1 100%; }
}
```

## Anexo B — Iconos nuevos para `web/iconos.py`

Se copian de `lucide-static` 1.60.0 (ISC, aviso ya en `web/iconos.py`), como manda `CLAUDE.md`
§6; **no se usan caracteres**. En la maqueta van en línea con los mismos trazados que emitiría
`icono()`:

```python
"x":     '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',                       # lucide: x
"minus": '<path d="M5 12h14"/>',                                                # lucide: minus
"plus":  '<path d="M5 12h14"/><path d="M12 5v14"/>',                            # lucide: plus
"tag":   '<path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414'
         'l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/>'
         '<circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',              # lucide: tag
```

`icono("tag")` no se usa como decoración de texto (sería redundante); `plus`/`minus` acompañan a
«Añadir»/«Excluir» en la maqueta solo si el texto ya está presente (el icono es decorativo y va
`aria-hidden`). `buscar` ya existe como `descubrir` (lupa); no se duplica.

## Anexo C — Fragmentos de referencia (Jinja, orientativos)

Los ejemplos usan el nombre sin prefijo (`noir`, `space-opera`); la plantilla no concatena URLs de
filtros ni parsea la expresión: eso es del servicio.

`_rejilla_biblioteca.html` ampliado (esqueleto, 1b):

```jinja
<div id="filtros-activos" class="filtros-etiquetas" aria-label="Etiquetas activas">
  {% for t in filtros %}{{ chip_filtro(t) }}{% endfor %}
  {% if filtros %}<a class="btn ghost sm" href="{{ url_sin_etiquetas }}"
    hx-get="{{ url_sin_etiquetas }}" hx-target="#rejilla" hx-swap="innerHTML"
    hx-push-url="true">Quitar etiquetas</a>{% endif %}
</div>
<h2>Etiquetas de tu biblioteca</h2>
<div id="facetas-biblioteca" class="facetas">
  {% call ui.grupo("Etiquetas", facetas|length) %}
    <div class="facetas-chips">{% for e in facetas %}
      <a class="chip" href="{{ e.url }}" hx-get="{{ e.url }}"
         hx-target="#rejilla" hx-swap="innerHTML" hx-push-url="true"
         {% if e.activa %}aria-current="true"{% endif %}>{{ e.clave }} <span class="cuenta">{{ e.series }}</span></a>
    {% endfor %}</div>
  {% endcall %}
</div>
{% call ui.region_viva("estado-resultados") %}{{ resumen }}{% endcall %}
{% if not items %}{{ ui.estado_vacio("Ninguna serie con estas etiquetas", "Quita una etiqueta o busca otra.",
                                    ("Quitar etiquetas", url_sin_etiquetas)) }}
{% else %}{% include "_rejilla_biblioteca.html" %}{% endif %}
{% if aviso %}{{ ui.aviso(aviso.tipo, aviso.texto) }}{% endif %}
<input id="f-etiquetas" name="etiquetas" type="search" value="{{ expresion }}"
       class="tag-input" hx-swap-oob="outerHTML"{% if enfocar %} autofocus{% endif %}>
```

`_sugerencias_etiquetas.html` (fila; los `href` los construye el servidor, no la plantilla):

```jinja
<ul class="series-list" aria-label="Sugerencias de etiquetas">
  {% for s in sugerencias %}
  <li class="sugerencia-fila">
    <span class="sugerencia-etiqueta">{{ s.clave }}</span>
    <span class="cuenta">{{ s.series }} {{ "serie" if s.series == 1 else "series" }}</span>
    <a href="{{ s.url_and }}" hx-get="{{ s.url_and }}" hx-target="#rejilla"
       hx-swap="innerHTML" hx-push-url="true" aria-label="Añadir {{ s.clave }}">Añadir</a>
    <a href="{{ s.url_not }}" hx-get="{{ s.url_not }}" hx-target="#rejilla"
       hx-swap="innerHTML" hx-push-url="true" aria-label="Excluir {{ s.clave }}">Excluir</a>
  </li>
  {% endfor %}
</ul>
```

`_etiquetas_serie.html` (dentro de `{% call ui.region_viva("etiquetas-serie") %}` en la ficha;
el POST sustituye `#etiquetas-serie` con `innerHTML`). El campo va **fuera** del `<form>` y se
asocia con `form="anadir-etiqueta-serie"`; cada sugerencia es un formulario POST propio (sin
anidar formularios):

```jinja
{% if aviso %}{{ ui.aviso(aviso.tipo, aviso.texto) }}{% endif %}
{% if not etiquetas %}<p class="empty">Sin etiquetas todavía. Añade una para encontrar esta serie por lo que trata.</p>{% endif %}
{% if etiquetas %}{% call ui.grupo("Etiquetas", etiquetas|length) %}
  <ul class="etiquetas-lista">
    {% for e in etiquetas %}<li>
      <form action="/ui/series/{{ series_id }}/etiquetas/quitar" method="post"
            hx-post="/ui/series/{{ series_id }}/etiquetas/quitar"
            hx-target="#etiquetas-serie" hx-swap="innerHTML" hx-disable="find button">
        <input type="hidden" name="etiqueta" value="{{ e.clave }}">
        <span class="chip chip-etiqueta">{{ e.clave }}</span>
        <button type="submit" class="chip-quitar" aria-label="Quitar {{ e.clave }} de esta serie">
          {{ icono("x") }}</button>
      </form>
    </li>{% endfor %}
  </ul>
{% endcall %}{% endif %}
<div class="etiquetas-anadir">
  <div class="filter-search-box filter-search-box-etiquetas">
    <label class="sr" for="f-etiqueta-serie">Añadir etiqueta</label>
    <input id="f-etiqueta-serie" name="etiqueta" type="search" form="anadir-etiqueta-serie"
           placeholder="Añadir una etiqueta…"
           hx-get="/ui/series/{{ series_id }}/etiquetas/sugerir"
           hx-trigger="input changed delay:300ms, search"
           hx-target="#sugerencias-etiqueta-serie" hx-swap="innerHTML" hx-sync="this:replace">
    <div id="sugerencias-etiqueta-serie" class="series-results" aria-label="Sugerencias de etiquetas">
      <ul class="series-list">
        {% for s in sugerencias %}
        <li class="sugerencia-fila">
          <span class="sugerencia-etiqueta">{{ s.clave }}</span>
          <span class="cuenta">{{ s.series }} {{ "serie" if s.series == 1 else "series" }}</span>
          <form action="/ui/series/{{ series_id }}/etiquetas" method="post"
                hx-post="/ui/series/{{ series_id }}/etiquetas"
                hx-target="#etiquetas-serie" hx-swap="innerHTML" hx-disable="find button">
            <input type="hidden" name="etiqueta" value="{{ s.clave }}">
            <button type="submit" class="btn ghost sm">Añadir<span class="sr"> {{ s.clave }}</span></button>
          </form>
        </li>
        {% endfor %}
      </ul>
    </div>
  </div>
  <form id="anadir-etiqueta-serie" action="/ui/series/{{ series_id }}/etiquetas" method="post"
        hx-post="/ui/series/{{ series_id }}/etiquetas"
        hx-target="#etiquetas-serie" hx-swap="innerHTML" hx-disable="find button">
    <button type="submit">Añadir</button>
  </form>
</div>
```

Con este esqueleto, la implementación no decide UX: solo rellena datos y respeta los topes.
