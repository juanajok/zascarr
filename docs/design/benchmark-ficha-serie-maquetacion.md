# Ficha de benchmarking — maquetación de la ficha de serie (2026-11-21)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Por el procedimiento sería
> **nivel 0** (maquetación y CSS), pero el PO pidió el benchmark y que la propuesta se contraste con el
> sistema de diseño (`docs/design/sistema-de-diseno-zascarr.md`); se entrega como ficha corta de nivel
> 1, dentro de la PR. Fecha: 2026-11-21. Contrastado con `main@294fa74f`.
>
> Continúa la auditoría del 2026-11-14 (`benchmark-ficha-serie.md`, #803), que sigue vigente: los
> números van justo después de la cabecera, la barra es de anclas sin estado y las pestañas siguen en
> «fase 2». Esta revisión cambia dos cosas que aquella dejó así: la portada del móvil (96 px sola
> arriba, «para que el índice quepa antes de la barra inferior») pasa a 88 px junto al título, y
> «Elegir portada» (pendiente de validar si distraía) pasa a «Sobre esta serie».

**Historia / problema observado:**
Revisión de la maquetación de la ficha de serie, equivalente a la de la ficha de número (PR #1177).
Caso real: «100 Balas» en la Pi (100 números, 100 archivos), a 1280 px y a 375 px, en los dos temas.

**Datos reales y medición de partida (Pi, antes del cambio):**

- Acciones de la cabecera en **cinco alturas**: «Marcar como tomo único» (plegado, lo primero), «Marcar
  como favorita» (44 px, borde de 1,6 px), «Editar la ficha» + «Añadir números del disco» (40 px),
  «Retirar» y «Aviso legal».
- Título **19 px por debajo** del canto de la portada (margen del `h1`). En el móvil, portada de 96 px
  sola arriba y el título 43 px más abajo.
- Barra de secciones con 11 enlaces (2 filas en escritorio, 4 filas y 188 px en el móvil), que **no
  seguía el orden de la página**, e incluía «Completar datos», que lleva a otra página.
- **Ninguna sección era una viñeta**; huecos sobre los títulos de 18 a 38 px.
- «Archivos por número» desplegaba los 100 números: **11.630 px de 14.632** (80 % de la página).
- Siete didascalias amarillas; tres eran ayuda. La de autores («Los que más números firman…») salía
  sin autores. Chip de seis palabras («Quizá no esté en el disco»). «Quitar» de cada etiqueta a 36 px.
  «la serie no tiene un total de números conocido», en minúscula, en Búsqueda y en Completitud.
- El tema claro no añade problemas propios.

**Referencias consultadas (copias locales en `.bench-refs`, salvo Suwayomi):**

| Referencia | Versión | Ficheros |
|---|---|---|
| Sonarr | `c018578` (2026-11-02) | `frontend/src/Series/Details/SeriesDetails.tsx` |
| Komga | `db2ad64` (2026-11-11) | `komga-webui/src/views/BrowseSeries.vue`, `components/menus/SeriesActionsMenu.vue` |
| Kapowarr | `c191dda` (2026-09-14) | `frontend/templates/view_volume.html` |
| Kaizoku | `fc86b7d` (2025-02-03) | `src/pages/manga/[id].tsx`, `src/components/mangaDetail.tsx`, `mangaCard.tsx` |
| Suwayomi-WebUI | `7168804` (2026-11-17), leído en GitHub | `src/features/manga/components/details/MangaDetails.tsx`, `MangaToolbarMenu.tsx` |

**Cómo lo resuelve cada una:**

- **Sonarr:** barra de herramientas única arriba; «Delete» al final, tras un separador. Cabecera con
  póster a la izquierda y, a su lado, título y datos en chips. Episodios plegados por temporada.
- **Komga:** póster y, a su lado, título, datos y un botón; lo poco frecuente (analizar, refrescar,
  colecciones, eliminar) en el menú «⋮». Libros paginados.
- **Kapowarr:** barra de herramientas con nueve botones con icono y texto; «Delete» el último. Los
  archivos de cada número se abren en un diálogo, no en la página.
- **Kaizoku:** la ficha no tiene acciones (editar y quitar viven en la tarjeta de la biblioteca, con
  confirmación). Cabecera con portada, título, datos y sinopsis; capítulos en una tabla de alto fijo.
- **Suwayomi:** portada y datos siempre uno junto al otro, también en el móvil; debajo, tres botones
  («En la biblioteca», «Seguimiento», «Abrir en el navegador»); migrar y categorías en el menú «⋮».
  Lista de capítulos virtualizada.

**Supuestos de su modelo que NO valen en ZascArr:**

- Menús «⋮», pestañas y tablas virtualizadas piden JavaScript propio: ADR 0001 (HTMX, sin SPA) y
  ADR 0021 (JavaScript propio solo en el lector).
- El coleccionista no técnico no busca acciones escondidas en un menú de iconos.
- La unidad es el número con sus archivos (y la garantía de no mover ni renombrar), no el capítulo.

**Resultado por idea:**

| # | Idea | Resultado | Regla del sistema de diseño |
|---|---|---|---|
| 1 | Una sola fila de acciones, la principal primero | **Adaptar** (las cinco) | Un botón principal por pantalla; `<a class="btn">` para navegar |
| 2 | Lo poco frecuente (tomo único, retirar, aviso legal) al final, plegado | **Adaptar** (Sonarr, Komga, Kapowarr), con `<details>` en vez de menú | Presupuesto de texto: lo demás, plegado |
| 3 | Título a ras de la portada | **Construir sobre lo propio** (ficha de número, #1177) | — |
| 4 | Portada junto al título en el móvil (88 px) | **Adaptar** (Suwayomi, Kaizoku) | PortadaSerie: siempre 2:3, sin marco propio en la `<img>` |
| 5 | «Completar datos» pasa a las acciones | **Construir sobre lo propio** | `<a class="btn">` para navegar |
| 6 | Acciones con el botón neutro (`.btn.sm`), no `ghost` repintado; también en Biblioteca y ficha de número | **Construir sobre lo propio** | Botón: `ghost` = subrayado y sin borde; neutro = borde, papel y sombra |
| 7 | Ayudas en texto secundario; procedencia solo con datos | **Adaptar** (decisión del PO del 2026-11-20 en «Tu lectura») | Didascalia: confirmación, procedencia o aviso legal |
| 8 | Archivos: 30 números a la vista y el resto plegado | **Adaptar** (las cinco pliegan, paginan o desplazan) | Presupuesto de texto (`<details>`) |
| 9 | La barra sigue el orden de la página | **Construir sobre lo propio** | — |
| 10 | «Elegir portada», «Otras fuentes» y «Revisar cambios» dentro de «Sobre esta serie» | **Adaptar** (Komga, Suwayomi agrupan los datos) | — |
| 11 | El motivo de «no se puede calcular», como frase | **Construir sobre lo propio** | Voz: frases completas |
| 12 | «Quitar» de las etiquetas a 40 px | **Construir sobre lo propio** | Objetivos táctiles ≥ 40 px |
| 13–14 | Cada sección, una viñeta (`.card`) con el mismo hueco | **Adaptar** | «La viñeta es la unidad»; Tarjeta |
| 15 | Chip «Por confirmar» + «Quizá no esté en el disco» al lado | **Construir sobre lo propio** | Chip: de una a tres palabras |
| 16 | Los botones del título de cada número fijan su fuente (heredaban Anton en mayúsculas: «VER PORTADA AMPLIADA»); hallado al verificar | **Construir sobre lo propio** | Rotulación: mayúsculas solo en rótulos de ≤ 3 palabras |
| — | Menú «⋮» (Komga, Suwayomi), pestañas (Sonarr) | **Descartar**: ocultan acciones y piden JavaScript | ADR 0001 / 0021 |
| — | Tabla de alto fijo (Kaizoku) | **Descartar**: un scroll dentro de otro, incómodo en el móvil | Nada desborda en horizontal |

**Lo que NO cambia (decisiones anteriores):**

- «Aviso legal» y la caja de atribución siguen en la cabecera (#447; la atribución, visible sin
  desplegar, SCR2/SCR7): van al final de lo poco frecuente.
- El fragmento de sagas no pintaba nada cuando la serie no estaba en ninguna saga, y el enlace «Sagas»
  de la barra quedaba sin destino. Decisión del PO (2026-11-22): se pinta con su estado vacío, como
  «Colecciones», con el enlace a «Sagas en orden» y sin botón principal.
- «No se puede calcular» es el término del glosario (§14, estado de la serie) y del filtro de la
  Biblioteca: tiene cuatro palabras, pero se conserva para no tener dos nombres para un concepto.
- Las didascalias de procedencia y garantía siguen en amarillo.

**Invariantes de ZascArr:** ningún cambio de comportamiento, rutas, contratos HTMX (`id` y
`hx-target` intactos) ni datos; sin JavaScript nuevo; nada de hotlinking.

**Casos de prueba:** `tests/test_ficha_serie_maquetacion.py` (una regresión por hallazgo) y las
pruebas existentes de presupuesto de texto (U21), botón principal único y favorita, adaptadas a la
estructura nueva.

**Verificado en navegador** (app local con Postgres efímero, serie de 40 números con archivos): 1280 px
en oscuro, 375 px en oscuro y 320 px en claro sin desplazamiento horizontal; acciones a 40 px (44 en
táctil) en una fila; título a ras de la portada; nueve viñetas con 16 px entre ellas; archivos con 30 a
la vista y «Ver los 10 números restantes», y el visor pasa del #30 al #31 a través del pliegue;
«Favorita» cambia de estado por HTMX, conserva el foco y se anuncia. La ficha de número y Biblioteca
se ven igual con `.btn.sm`.

**NOT RUN:** una serie con sagas, con datos de Fandom (atribución), con nota y con un archivo que falte
del disco (el chip «Por confirmar» lo cubre la prueba de plantilla); lector de pantalla; Suwayomi y
Kaizoku no se ejecutaron (lectura de código).

**Caduca:** 2027-01-20 (~60 días), o antes si cambia la ficha de serie.
