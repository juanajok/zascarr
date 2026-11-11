# Benchmark — #628+/biblioteca: filtros, orden y vista en las apps del radar

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Es una
> comparación de **arquitectura de la página**, no de estética: filtros, estado
> activo, orden/vista, persistencia, móvil, búsqueda y accesibilidad. No
> implementa, no añade dependencias y no copia código ni diseños.
>
> - **Fecha:** 2026-11-11
> - **SHA de ZascArr:** `8b1969c` (worktree `.squad/wt-bench-bib`, rama
>   `docs/bench-biblioteca`, desde `origin/main`).
> - **Referencias:** Sonarr, Radarr, Kapowarr, Mylar3, Komga, Kavita, Suwayomi,
>   Calibre-Web, Whakoom y Metron. Versión/commit en §2.
> - **Método:** lectura de código y de plantillas; no se ejecutaron las apps.
>   Lo que no se pudo abrir va marcado `[sin verificar]`.
> - **Caducidad:** 2027-01-10 (~60 días), o antes si cambia la pantalla de
>   Biblioteca o alguna referencia.

---

## 1. Problema local fijado (ZascArr, `8b1969c`)

Hoy `biblioteca.html` tiene **dos barras densas** y ya una base buena de estado:

| Pieza actual | Evidencia |
|---|---|
| Barra 1: búsqueda de título, tradición, editorial, lectura, «Ordenar por» + botón «Aplicar orden» y etiqueta | `web/templates/biblioteca.html:8-59` |
| Barra 2: buscador de personaje y buscador de saga, separados de la barra 1 | `biblioteca.html:61-77` |
| El formulario ya hace `hx-get="/ui/biblioteca/resultados"` con `hx-target="#rejilla"` | `biblioteca.html:8-10` |
| Chips de filtros activos, «Quitar» por chip y «Limpiar todos» | `templates/_rejilla_biblioteca.html:29-55` |
| Recuento textual («X series coinciden…») dentro del fragmento | `_rejilla_biblioteca.html:20-22` |
| Vista Tarjetas/Lista y su estado en la URL | `_rejilla_biblioteca.html:73-80`; `web/library.py:506-507` |
| Estado canónico en URL (`q`, tradición, editorial, personaje, saga, etiquetas, leído, orden, página, vista) | `web/library.py:100-220,252-256`; docstring `:1-12` |
| El cambio de cualquier campo del formulario dispara la petición (`hx-trigger="change, submit"`), pero «Ordenar por» conserva un botón «Aplicar orden» | `biblioteca.html:10,37-45` |

**Problema de diseño, no de backend:** la pantalla pide al coleccionista
recordar siete controles repartidos en dos barras; el orden tiene un botón que
compite con el cambio automático; y la búsqueda de personaje/saga vive fuera
del flujo de «filtrar». La base (URL, chips, recuento, vista, HTMX) es correcta
y no se tira.

**Lo que hay que decidir:** jerarquía de controles, panel plegable, chips,
orden/vista y móvil. No se decide el backend de filtros, que ya existe.

---

## 2. Referencias y evidencia

| Referencia | Versión / commit | Evidencia principal |
|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` (v4.0.20.3014) | `Series/Index/SeriesIndex.tsx`, `Components/Menu/FilterMenu.tsx`, `Series/seriesOptionsStore.ts`, `Components/Page/Header/PageHeader.tsx` |
| **Radarr** | `7e3f80c98d01481430ab356f6d7322fc5dc381ee` (v6.4.4.10685) | `Movie/Index/MovieIndex.tsx`, `Movie/Index/Menus/MovieIndex*Menu.tsx` (misma familia `NzbDrone`) |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2) | `frontend/templates/volumes.html`, `frontend/static/js/volumes.js`, `frontend/static/css/volumes.css` |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (v0.8.3) | `data/interfaces/default/index.html`, `index-alphaindex.html`, `base.html` |
| **Komga** | `25c67d14eb748dd3fb9f6612c099959a077fc850` (commit de `develop`, 2026-10-30) | `komga-webui/src/views/BrowseLibraries.vue`, `components/FilterDrawer.vue`, `FilterPanels.vue`, `SortList.vue`, `SearchBox.vue` |
| **Kavita** | `a9cdf1cad9ae14f88a295c3a6fc7993f9823d59d` (develop; release v0.9.1.4) | `UI/Web/src/app/library-detail/library-detail.component.html`, `metadata-filter/metadata-filter.component.html`, `nav/_components/search-typeahead` |
| **Suwayomi WebUI** | `44b310ef409e6578ce674035c554df04bcaf2dd9` | `features/library/screens/Library.tsx`, `components/LibraryOptionsPanel.tsx`, `components/LibraryToolbarMenu.tsx` |
| **Calibre-Web** | `6e840acbda8d62fdd159bf3855c01872d629a914` | `cps/themes/standard/templates/index.html`, `layout.html`, `cps/web.py` |
| **Whakoom** | Web/PRO, sin código público abierto | [Ayuda de filtros PRO](https://whakoom.zendesk.com/hc/es/articles/207113059-Busca-en-tu-comicteca-y-usa-filtros-avanzados) y [petición de total/orden](https://whakoom.zendesk.com/hc/es/community/posts/12342764246684-Incluir-el-total-de-comics-buscados-y-ordenar-comics-buscados-por-fecha-de-publicaci%C3%B3n-y-por-colecciones); UI no comprobada (`[sin verificar]`) |
| **Metron** | `c6e1c48e54ab3c716febb3ae542de36ffd5e2dad` | `comicsdb/templates/comicsdb/partials/issue_filter.html`, `active_filters.html`, `issue_sort.html`, `card_grid_count.html` |

Enlaces de contraste: [Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
[Radarr](https://github.com/Radarr/Radarr/tree/7e3f80c98d01481430ab356f6d7322fc5dc381ee),
[Kapowarr](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2),
[Mylar3](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316),
[Komga](https://github.com/gotson/komga/tree/25c67d14eb748dd3fb9f6612c099959a077fc850),
[Kavita](https://github.com/Kareadita/Kavita/tree/a9cdf1cad9ae14f88a295c3a6fc7993f9823d59d),
[Suwayomi](https://github.com/Suwayomi/Suwayomi-WebUI/tree/44b310ef409e6578ce674035c554df04bcaf2dd9),
[Calibre-Web](https://github.com/janeczku/calibre-web/tree/6e840acbda8d62fdd159bf3855c01872d629a914),
[Metron](https://github.com/Metron-Project/metron/tree/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad).

---

## 3. Matriz referencia × decisión

Leyenda: **Sí** = implementado y visible; **Parcial** = existe pero esconde o
complica algo; **No** = no se encontró; **?** = `[sin verificar]`.

| Referencia | Arquitectura de filtros | Activos: chips/contador/limpiar | Dónde van orden y vista | Persistencia | Móvil | Búsqueda | Accesibilidad / teclado |
|---|---|---|---|---|---|---|---|
| **Sonarr** | Menú «Filter» en toolbar + **modal de custom filters** (constructor por campos); filtros predefinidos, no inline | **Parcial:** sin chips; el botón se marca con indicador; contador en el pie; «All» para limpiar; no «Limpiar todo» | **Toolbar** junto a filtro: menús de **vista** (tabla/posters/overview) y **orden**; aplican al elegir | **localStorage** por instancia (zustand persist); custom filters guardados en servidor; **no URL** de filtros | Toolbar con overflow «More»; sin hoja de filtros dedicada (`isSmallScreen`) | **Una** búsqueda global en cabecera (typeahead, worker); el constructor de filtros es aparte | `aria-label` en iconos, menús de teclado, atajo de búsqueda; sin chips no hay anuncio continuo del filtro |
| **Radarr** | Igual patrón: FilterMenu + modal de filtros custom; predefinidos | **Parcial:** sin chips; indicador en botón; contador en pie; «All» | Toolbar: ViewMenu (tabla/posters/overview) + SortMenu | Redux/store local; custom filters en servidor; **no URL** | Toolbar responsive; overflow | Búsqueda global en cabecera | Mismos componentes y límites que Sonarr |
| **Kapowarr** | **Tres selects** en toolbar: filtro (No Filter/Wanted/Monitored), vista y orden; sin panel | **No:** sin chips, sin contador de filtros, sin «Limpiar todo» | Toolbar, junto al filtro; aplican al cambiar | **localStorage** (`lib_filter`, `lib_view`, `lib_sorting`); sin URL | CSS responsive (860/535/442 px), pero toolbar sin patrón de sheet | **Una** búsqueda en cabecera | `aria-label` en los selects; sin chips ni estados anunciados |
| **Mylar3** | **DataTables**: un buscador «Filter:» + orden por columnas; sin panel de facetas | **Parcial:** `infoFiltered` de DataTables; sin chips; limpiar = vaciar buscador | **Orden** en cabeceras de tabla (sortable); **no hay cambio de vista** (solo tabla) | `stateSave: true` (localStorage de DataTables); sin URL | Tabla clásica; sin plugin responsive (`[sin verificar]` en móvil real) | **Una** búsqueda global de la tabla | Baja: buscador y cabeceras dependen de DataTables; sin etiquetas de filtros activos |
| **Komga** | **Drawer lateral** de filtros (lista rápida + paneles por campo, con búsqueda dentro de cada panel) y **sort** en el mismo drawer | **Parcial:** no chips; icono de filtro activo y botón de limpiar en el drawer; **contador** en chip junto al título | **Dentro del drawer**, bloque Sort; la vista de rejilla es fija | **Query params** (`page`, `pageSize`, `nav`, filtros/sort); se restaura al volver | Drawer temporal de Vuetify; en móvil ocupa pantalla; botón de filtro | **SearchBox global** (typeahead todas las bibliotecas) + búsquedas por campo dentro del drawer | Iconos sin `aria-label` en el botón de filtro/limpiar del drawer (fuente de mejora); paneles con teclado estándar |
| **Kavita** | **Panel lateral** en escritorio y **drawer** en móvil; constructor de metadatos (Filter V2) + sort; «Apply/Reset» y «Save» smart filter | **Parcial:** icono de filtro activo; contador de series en el subtítulo; no chips; reset en el panel | **Dentro del panel**, junto al límite y al sort | **URL** con el filtro; **smart filters guardados** con nombre en servidor | `isTabletOrAbove` → panel; si no, `app-drawer` a pantalla (600 px) | **Búsqueda global** typeahead en nav; filtros por campo en el constructor | `aria-label` y `visually-hidden` en el botón; foco en drawer; el propio código anota TODO de «botón Clear» |
| **Suwayomi** | **Modal/pestañas** «Filter / Sort / Display»; filtros por checks y selects; pestañas de categorías | **Parcial:** no chips; icono de filtro activo; botón «reset filters» (commits); contador por pestaña y opción de mostrar filtrados | **Dentro del modal**, pestañas Sort y Display | Filtros/sort/display **por categoría en servidor**; `q` y pestaña en URL; no vistas con nombre | Modal MUI responsive; FAB de selección; sin hoja específica | **Búsqueda en appbar** (sugerencias) + filtros por campo | Componentes MUI con labels; modal con foco; sin chips de estado |
| **Calibre-Web** | **Sidebar de categorías** (recientes, autores, series, etc.) + **búsqueda simple** y **Advanced Search** en páginas aparte; sin panel de facetas en la lista | **No:** sin chips, sin contador de filtros visibles; limpiar = cambiar de categoría o volver a la lista | **Fila de iconos de orden** arriba de la rejilla (`sort_param` en URL); **no hay cambio de vista** | Orden en **URL** y guardado por usuario (`set_view_property('stored')`); sin filtros guardados | Bootstrap: navbar colapsada; la fila de orden es `hidden-xs` → **en móvil no hay orden visible** | **Una** búsqueda simple en navbar + página Advanced Search | Iconos de orden solo con `title` (tooltip), sin texto visible ni `aria-label`; ocultos en móvil |
| **Whakoom** | Filtros **PRO** por grupos: lectura, valoración, opinión, estado, lugar, notas, autor, editorial; colecciones por estado | **?** Sin evidencia de chips/contador/limpiar; una petición comunitaria pide **total** y orden por fecha/colección (2 años, 4 votos) | **?** Orden por fecha/colección pedido; no confirmado; «Lo viejuno» existe como opción | **?** Web PRO; la ayuda no documenta URL/cookie/vistas guardadas | App iOS/Android; web móvil `[sin verificar]` | **Una** búsqueda por título + filtros PRO | **?** No verificable sin abrir la web (hoy no disponible; ayuda pública) |
| **Metron** | **Panel de filtros** con «Quick Search» + `<details>` **Advanced Filters** agrupados (Series, números, fechas, códigos/IDs); sin JS para abrir | **Sí:** **chips** «Active filters» con «Quitar» por chip y **Clear all**; **contador** (`card_grid_count`); etiqueta «Filters Active» | **Sort** en el mismo panel (`issue_sort`): campo + dirección; no hay vista alternativa | **Query params**; cada chip reconstruye la URL conservando el resto; **sin vistas guardadas** | Bulma responsive; panel `<details>` nativo; sin drawer JS | **Quick Search** por nombre de serie + campos avanzados separados | Muy buena: `aria-label` en cada campo, chips con «Remove … filter», `<details>` nativo y foco estándar |
| **ZascArr hoy** | **Dos barras** con 7+ controles; etiqueta/personaje/saga separados; sin panel plegable | **Sí:** chips, «Limpiar todos», recuento dentro del fragmento; URL canónica | **Orden** en barra 1 con botón «Aplicar orden» (redundante con `change`); **vista** Tarjetas/Lista debajo del resumen | **URL** completa; sin vistas guardadas; `vista` y `orden` en URL | Dos barras apiladas; no hay botón «Filtros»/sheet; controles de 40/44 px | **Una** búsqueda de título + **dos** buscadores extra (personaje, saga) + etiqueta | Chips con `aria-label`, `region_viva`, foco al quitar; el resto de campos tiene `<label class="sr">`; falta relación visual |

---

## 4. Qué hacen bien y qué les falla (commits y deuda)

### 4.1 Aciertos que merecen copiarse

- **Metron:** la combinación más cercana a lo que ZascArr necesita: **una
  búsqueda rápida + panel de filtros plegable con `<details>` + chips de filtros
  activos + “Clear all” + contador + sort en el mismo panel**. Sin JavaScript
  para abrir el panel (`issue_filter.html:8-52`;
  `active_filters.html:13-29`; `issue_sort.html:12-26`).
- **Komga:** el **drawer** de filtros/sort con botón de filtro activo y
  contador junto al título (`BrowseLibraries.vue:10-72`); el estado se restaura
  de la query (`:297-301`).
- **Kavita:** panel lateral/drawer móvil explícito (`metadata-filter.component.html:11-19`),
  **Apply/Reset** y **Save smart filter** (`:28-85`); contador en el subtítulo
  (`library-detail.component.html:3-21`).
- **Sonarr/Radarr:** orden y vista como **menús de toolbar** que aplican al
  cambiar, no como campos del formulario; búsqueda global separada
  (`SeriesIndex.tsx:293-393`; `FilterMenu.tsx:36-76`).
- **Suwayomi:** pestañas **Filter / Sort / Display** y persistencia por
  categoría; el reset y el contador de filtrados se añadieron después
  (`LibraryOptionsPanel.tsx:49-52,175-211`; commits `556d5552`, `c5703fb2`).
- **ZascArr:** ya tiene lo más caro: **URL canónica, chips, recuento,
  «Limpiar todos» y vista**; no se rehace.

### 4.2 Errores y deudas conocidas

- **Sonarr:** el filtro vive en un menú con constructor aparte; el indicador
  del botón no dice **qué** filtro está activo y no hay chips. Commit
  `c36f2298` («Give custom filter buttons more context») va justo a ese problema
  de contexto; `31ecc075` simplifica predicados de sort/filter. La navegación a
  la ficha conserva filtros/orden (`979fc5ae`), señal de que el estado importa.
- **Komga:** regresión de filtros de biblioteca restaurada en `dc064f20`
  («restore library filter for language and age rating»); los iconos del drawer
  de filtro/limpiar no llevan `aria-label` (`FilterDrawer.vue:8-22`), deuda de
  accesibilidad.
- **Kavita:** `9ee5821c` «Smart Filter UX» y `e608edea` «bugs and some new sort
  & filter options»; el propio template deja un TODO para un botón «Clear»
  (`metadata-filter.component.html:55-62`) y otro por un bug de instanciación
  del drawer (`:18`). Los smart filters guardados son potentes pero esconden la
  complejidad.
- **Suwayomi:** los commits `3d085f5a` y `556d5552` añaden **reset** a filtros
  colapsables; `c5703fb2` añade **contador filtrado**. Antes faltaban justo las
  dos cosas que el coleccionista necesita para entender un filtro activo.
- **Calibre-Web:** la fila de orden es `hidden-xs` (`index.html:69`): en móvil
  **no hay orden visible**; los iconos solo tienen tooltip, sin texto ni
  `aria-label` (`:71-84`). La búsqueda simple y Advanced Search están separadas
  (`layout.html:36-49`).
- **Mylar3:** DataTables con `stateSave` (`index.html:189-194`) resuelve la
  persistencia, pero no hay chips, contador de filtros ni panel; la tabla
  clásica no tiene un patrón móvil propio.
- **Kapowarr:** tres selects resuelven el mínimo, pero no explican qué está
  activo, no hay contador y el filtro es solo «Wanted/Monitored»
  (`volumes.html:79-99`); la persistencia es localStorage (`volumes.js:272-298`).
- **Whakoom:** la ayuda confirma filtros PRO por muchos ejes, pero la petición
  comunitaria pide **total de cómics y orden por fecha/colección**, y no hay
  evidencia de chips/limpiar; la web no estaba disponible para inspección
  (`[sin verificar]`).
- **Metron:** buena UX, pero **sin vistas guardadas**; el panel advanced es
  largo (14 campos) y depende de `<details>`; el sort no se ve fuera del panel.

---

## 5. Composición recomendada para ZascArr

Parte de lo que ya existe (HTMX, URL, chips, recuento, vista). La decisión es
**CONSTRUIR SOBRE LO PROPIO**, tomando de Metron la jerarquía, de Komga/Kavita
el panel y de Sonarr la separación orden/vista; **no** se copia una UI con
JavaScript ni se añade una librería.

### 5.1 Jerarquía de controles

1. **Cabecera de pantalla:** `H1 Biblioteca` + frase de entrada breve (ya
   existe; no se toca el presupuesto de texto de U21).
2. **Fila principal (siempre visible):**
   - **Buscador único** de título, ancho y con `hx-trigger="keyup changed
     delay:300ms"`; no hay un segundo buscador de personaje/saga en paralelo.
   - **Botón «Filtros»** con **contador** de filtros activos (`Filtros (2)`),
     `aria-expanded` y el mismo patrón visual que el botón de vista.
   - **Orden** como `<select>` compacto junto al recuento (sin botón
     «Aplicar orden»: aplica al cambiar, como el resto).
   - **Vista Tarjetas/Lista** como control segmentado (ya existe).
3. **Debajo, si hay filtros activos:** **chips** removibles + «Limpiar todos» y
   el recuento («X series coinciden con estos filtros»). Los chips no repiten
   «Orden» ni «Vista»: solo filtros de contenido.
4. **Panel plegable «Filtros»:** se abre bajo la fila principal; agrupa en
   secciones: *Tradición · Editorial · Lectura · Etiquetas · Personaje · Saga*.
   Cada sección con su `<label>` visible y ayuda de una línea; un `<details>`
   nativo (o `<dialog>` con foco atrapado) basta, sin JS de terceros.
5. **Dentro del panel:** los campos aplican al cambiar (HTMX), el panel no se
   cierra solo; al final, «Limpiar filtros» y «Cerrar». No hay botón «Aplicar»
   salvo que en el futuro se añada edición multi-campo; hoy no hace falta.

### 5.2 Panel y chips: reglas de estado

- **Una única fuente de verdad:** la URL (ya lo es). El panel solo refleja
  `filtros`; los chips se generan del mismo estado; quitar un chip no cierra el
  panel ni pierde los demás.
- **Contador en el fragmento** que se intercambia (ya está en `#rejilla`), no
  en la cabecera estática: nunca queda un recuento viejo.
- **«Limpiar todos»** a la vista y en el panel; conserva orden y vista (son
  preferencias de presentación, no filtros). La URL resultante no lleva
  parámetros vacíos.
- **Sin preselección:** el panel no marca «recomendado»; no hay puntuación.

### 5.3 Orden y vista

- **Orden** fuera del panel, junto al recuento; aplica al cambiar y conserva el
  valor en la URL. Eliminar el botón «Aplicar orden» redundante
  (`biblioteca.html:44`).
- **Vista** Tarjetas/Lista fuera del panel; `aria-current` en el botón activo
  (ya existe, `_rejilla_biblioteca.html:73-80`).
- Al cambiar de vista u orden no se pierde ningún filtro; al cambiar un filtro
  no se resetea el orden ni la vista.
- No se añaden «vistas guardadas» en v1: la URL ya permite compartir/volver.
  Si más adelante se añaden, el patrón de Kavita (smart filters con nombre) es
  la referencia, no un requisito de esta entrega.

### 5.4 Móvil

- Fila compacta: buscador + **«Filtros»** + vista; el orden puede plegarse en un
  `<select>` de ancho completo bajo la fila si no cabe.
- **El panel se abre a pantalla completa** (o sheet de 100 % de ancho) con
  foco atrapado, `aria-modal`, botón «Cerrar» y «Limpiar»; no un menú flotante
  diminuto.
- **Chips con `flex-wrap`**, texto visible y «Quitar» de 44 px; no solo icono.
- **Una sola columna** de controles en el panel; targets ≥ 44 px; nada de
  `hidden-xs` que esconda el orden (fallo de Calibre-Web).
- El resultado (recuento + chips + rejilla) sigue siendo el mismo fragmento
  HTMX; el panel no necesita otra petición.

### 5.5 Accesibilidad y teclado

- Botón «Filtros» con `aria-expanded`, `aria-controls` y nombre que incluya el
  número de filtros activos.
- Panel con foco al abrir, `Escape` para cerrar y devolución del foco al botón.
- Chips dentro de `aria-label="Filtros activos"` (ya está) y cada «Quitar» con
  el nombre del filtro (ya está); recuento en `aria-live` (ya está con
  `region_viva`).
- Orden y vista con `<label>` visible u oculto correctamente asociado; no
  iconos sin nombre.
- En teclado, `Tab` recorre buscador → Filtros → orden → vista → chips; el
  panel no atrapa el foco si es `<details>` nativo.

### 5.6 Las 5 reglas

1. **Una búsqueda, no cinco:** título arriba; personaje, saga y etiqueta dentro
   de «Filtros»; nada de campos duplicados en dos barras.
2. **Un botón «Filtros» con contador y panel plegable** que sustituya las dos
   barras; grupos con etiquetas visibles y «Limpiar».
3. **Orden y vista siempre a la vista y aplican al cambiar:** fuera del panel,
   sin botón «Aplicar orden», conservados en la URL.
4. **Chips + recuento + «Limpiar todos» en el fragmento**, generados del mismo
   estado URL; quitar uno no pierde los demás.
5. **Móvil de primera clase:** panel a pantalla completa, chips que envuelven,
   controles de 44 px y ninguna función escondida por `hidden-xs`.

---

## 6. Adoptar / adaptar / descartar

| Idea | Resultado | Motivo |
|---|---|---|
| Búsqueda rápida única + panel de filtros plegable + chips + contar + limpiar | **Adoptar** (patrón de Metron) | Es la combinación más legible y sin JS; encaja con HTMX |
| Panel/drawer lateral con filtros y sort | **Adaptar** de Komga/Kavita | En ZascArr cabe un panel desplegable nativo, no un drawer Vuetify |
| Orden y vista como controles de toolbar que aplican al cambiar | **Adoptar** de Sonarr/Radarr | Reduce fricción y elimina el «Aplicar orden» actual |
| Filtros personalizados guardados con nombre | **Descartar en v1** | La URL ya cubre el caso; añade modelo/UI sin datos de uso |
| Filtros como modal/pestañas con checks | **Descartar** para la Biblioteca | Metron demuestra que un panel agrupado es más directo; el modal de Suwayomi esconde el estado |
| Sidebar de categorías como único filtro | **Descartar** | Calibre-Web obliga a navegar a otra página; ZascArr necesita filtrar sin salir |
| Tabla con buscador DataTables y `stateSave` | **Descartar** como arquitectura | Mylar3 no ofrece chips/panel y su móvil es débil |
| Fila de iconos de orden solo con tooltip y `hidden-xs` | **Descartar** | Falla en móvil y accesibilidad (Calibre-Web) |
| Filtros PRO detrás de pago | **Descartar** | ZascArr es self-hosted y no gatea funciones básicas |
| Vistas guardadas / perfiles | **Descartar en v1** | Fuera de alcance; URL + localStorage de vista/orden bastan |
| Copiar código/diseños de las referencias | **Descartar** | Se copian patrones; las licencias se revisan si se reutiliza un fichero |

**Licencias:** Sonarr/Radarr/Kapowarr/Mylar3/Kavita y Metron son GPL-3.0;
Komga es MIT; Suwayomi WebUI declara MPL-2.0; Calibre-Web GPL-3.0. No se copia
código ni assets.

---

## 7. PASS / FAIL / NOT RUN

| Comprobación | Estado | Evidencia |
|---|---|---|
| Arquitectura de las 10 referencias documentada | **PASS** | Matriz §3 y evidencia §2; dos `[sin verificar]` explícitos (Whakoom UI, Mylar3 móvil) |
| Problema local fijado en ZascArr `8b1969c` | **PASS** | §1 con fichero:línea |
| Recomendación de composición y 5 reglas | **PASS** | §5 |
| Ejecución de las apps / navegador real | **NOT RUN** | Solo lectura de código/plantillas; no se abrió ninguna UI |
| Verificación de Whakoom (web caída el 2026-11-11) | **NOT RUN** | `503`; solo ayuda pública y petición comunitaria |
| Pruebas de usabilidad/teclado con personas | **NOT RUN** | Fuera del alcance de esta ficha; la spec debe probarlo |
| **FAIL** | — | Ninguno de la ficha; las referencias no se ejecutaron y lo no abierto está declarado |

---

## 8. Lo que esta ficha NO decide

- No implementa la pantalla ni toca `biblioteca.html`, `library.py`, CSS o
  tests; no añade dependencias.
- No decide el backend de filtros, la paginación ni el contenido de las facetas.
- No decide vistas guardadas, perfiles ni sincronización entre dispositivos.
- No cambia la identidad visual (marca, tipografía, tramas) ni el presupuesto de
  texto de U21.
- **Caduca:** 2027-01-10, o antes si cambia la pantalla de Biblioteca o alguna
  referencia.
