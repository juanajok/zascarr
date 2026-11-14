# Benchmark y auditoría UX/UI — ficha de serie (2026-11-14)

> **Estado:** auditoría y corrección de los cinco puntos pendientes de #803.
> **Método:** lectura de plantilla/CSS, medición de la biblioteca real, revisión contra el
> sistema de diseño y benchmark de referencias. **NOT RUN:** navegador real, tableta/móvil
> físico, lector de pantalla y validación con personas. Los PASS son de plantilla/CSS/pruebas.

## 1. Problema local

La ficha mezclaba en una sola columna:

1. cabecera con portada, sinopsis, acciones, fuentes y atribución;
2. datos editoriales, autores y procedencia;
3. etiquetas, colecciones, búsqueda automática y notas;
4. completitud (D8), otras fuentes y enriquecimiento;
5. **números que faltan**, números en la biblioteca y archivos, al final.

En una serie de 31 números había que atravesar más de diez secciones antes de llegar a
lo que más se consulta. Además, «Estado de la colección» (completitud D8) y
«Colecciones» (agrupaciones M:N) usaban la misma palabra para dos conceptos distintos.
La medición real de la biblioteca mostró el caso extremo: **426 números** en una serie;
**17 series con ≥ 50** y **6 con ≥ 100**.

### Hallazgos y estado

| Prioridad | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| **P0** | Números tras ~10 secciones; en móvil sin atajo | orden de `series_detail.html` | **Corregido**: números tras la cabecera + anclas |
| **P0** | «Estado de la colección» se confunde con las colecciones M:N | dos bloques con «colección» | **Corregido**: «Completitud» |
| **P1** | Acción destructiva «Retirar» compite con la acción principal | `.series-acciones` | **Corregido**: `<details>` secundario |
| **P1** | Serie con 426 números pinta cientos de chips | `present`/`missing` sin límite | **Corregido**: primeras 30 + «Ver el resto» |
| **P1** | «Otras fuentes» mostraba un botón deshabilitado sin fuente | bloque siempre visible | **Corregido**: se oculta sin fuente |
| **P2** | La frase de entrada aparecía después del bloque de datos | `.series-intro` | **Corregido**: antes de los datos |
| **P2** | Sin navegación entre secciones en tableta/móvil | no había índice | **Corregido**: `ficha-nav` |
| **P2** | «Elegir portada» compite en la primera pantalla | detalle plegado | **Aceptado**: es un control |
| **P2** | Portada 120 px en móvil | `.series-cover` | **Aceptado**: legible |

## 2. Benchmark

| Referencia | Cómo estructura una ficha larga | Qué se adopta / adapta / descarta |
|---|---|---|
| **Sonarr/Radarr** ([Library](https://wiki.servarr.com/en/sonarr/library)) | Pestañas y acciones contextuales; no apila todo | Adoptar separación por áreas; descartar pestañas con estado |
| **Komga** ([Collections](https://komga.org/docs/guides/collections/)) | Paneles plegables y acciones contextuales | Adoptar lo plegable; descartar modo de edición global |
| **Kavita** ([series-detail](https://git.azen-sgg.ru/AZEN-SGG/Kavita/src/commit/4c44dbf3e205d6b8946d29b20e58fbeabcdb748b/UI/Web/src/app/series-detail/_components/series-detail/series-detail.component.html)) | Pestañas: Storyline, Volumes/Chapters, Specials, Related, Details, con contenido diferido | Adoptar «números como sección principal»; adaptar a anclas sin SPA |
| **Jellyfin/Plex** ([Item details](https://deepwiki.com/jellyfin/jellyfin-web/3.2-library-and-list-views)) | Héroe + acción principal + secciones/subpestañas | Adoptar acción principal clara; descartar menú de tres puntos |
| **Calibre-Web / estanterías** | Metadatos y acciones en la ficha; estanterías aparte | Adoptar no mezclar «completitud» con «colección» |
| **ZascArr, sistema de diseño** ([sistema](sistema-de-diseno-zascarr.md)) | Lo secundario plegado; ≤ 50 palabras antes de la primera acción; objetivos ≥ 40 px; sin diálogos | Adoptar `<details>`, anclas y botones existentes; descartar tabs con estado |

### Opciones evaluadas

| Opción | Ventaja | Problema | Veredicto |
|---|---|---|---|
| A. Dejar la columna actual | Cero coste | Números inaccesibles; ambigüedad | **Descartar** |
| B. Pestañas con estado (Kavita) | Muy compacto | Estado, URLs, caché, HTMX y foco | **Fase 2**, no ahora |
| C. Navegación por anclas + números arriba | Nativa, sin JS, teclado, URLs compartibles | No reduce la longitud de datos, pero prioriza la tarea | **Adoptar** |
| D. Reordenar todo a datos primero | Estructura editorial clásica | Vuelve a esconder números | **Descartar** |
| E. Colapsar rejillas de números | Evita 426 chips de golpe | Un clic extra para el resto | **Adoptar con umbral 30** |

## 3. Solución implementada

- **Números inmediatamente después de la cabecera y la intro**, antes de portada, datos,
  etiquetas, búsqueda, colecciones y completitud.
- **`ficha-nav`** con anclas a Números, Búsqueda, Etiquetas, Colecciones, Completitud,
  Datos y Archivos (si existe). Sin estado ni JS propio.
- **«Estado de la colección» → «Completitud»**.
- **«Retirar de mi biblioteca»** pasa a `<details class="series-retirar">`; el enlace real
  sigue dentro y la garantía de no tocar archivos le acompaña.
- **«Otras fuentes»** solo se renderiza si la serie tiene `comic_vine_id`, `anilist_id`,
  `tebeosfera_slug` o `gcd_id`.
- **Rejillas largas**: primeras 30 chips visibles y `<details>` «Ver los N números que
  faltan / tienes» para el resto. Se aplica por encima de 30; con 100 números se evitan
  200 chips de golpe.
- La frase de entrada va antes del bloque de datos.
- Sin componentes nuevos: `.btn.ghost.sm`, `<details>` y tokens existentes.

### Medición real usada para decidir el umbral

- Una serie con **426 números** (Batman Vol 1), **137** (Superman), **133** (The Flash),
  **110** (Death Note), **100** (100 Balas).
- **17 series con ≥ 50** números y **6 con ≥ 100**.
- `total_issues` de la fuente no basta (máximo declarado 13): la decisión se toma por
  `present|length`/`missing|length` reales, no por el metadato.

### Móvil y tableta

- Los números aparecen en la primera pantalla tras la cabecera; no hay que recorrer datos.
- La navegación envuelve en varias filas, sin scroll horizontal; enlaces de ≥ 40 px.
- Las rejillas de 30 chips caben en pocas filas y el resto queda a un toque.
- La portada móvil baja a 96 px para que el índice completo quepa antes de la barra inferior.
- La acción destructiva deja de competir con «Añadir números del disco».
- No se toca la barra inferior de navegación de la app.

## 4. Lo que sigue pendiente

1. Validar con 3–5 coleccionistas reales en tableta y móvil; la simulación y las capturas
   están en `validacion-ux-ficha-serie.md`, pero no cierran el P0 de producto.
2. Valorar pestañas con estado si la ficha sigue siendo demasiado larga tras la validación.
3. Medir si el umbral 30 es el adecuado con series de 400+ números.
4. Revisar el orden de «Elegir portada» si la validación muestra que distrae.

## 5. Criterios de aceptación

- `#numeros-serie` aparece antes de `#datos-serie`, `#wishlist_policy`, etiquetas, colecciones
  y completitud.
- La ficha contiene navegación por anclas; «Archivos» solo si existe la sección.
- «Completitud» sustituye a «Estado de la colección».
- «Retirar de mi biblioteca» está dentro de un `<details>` y conserva su enlace.
- «Otras fuentes» no aparece sin fuente asociada.
- Con 100 presentes y 100 ausentes se muestran 30 + 30 y dos «Ver los 70…».
- La suite de ficha, componentes y tokens de CSS sigue verde.

## 6. PASS / FAIL / NOT RUN

- **PASS (código/pruebas):** orden, anclas, «Completitud», retirada plegada, fuentes
  ocultas, colapso de rejillas, presupuesto de texto y estilos con tokens.
- **FAIL (previo, corregido):** números al final, ambigüedad «colección», acción destructiva
  a la vista, rejillas sin límite.
- **NOT RUN:** navegador real, tableta/móvil, lector de pantalla y validación con personas.
