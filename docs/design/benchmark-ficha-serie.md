# Benchmark y auditoría UX/UI — ficha de serie (2026-11-14)

> **Estado:** auditoría de la ficha `series_detail.html` y adaptación del patrón de navegación
> por secciones. **NOT RUN:** navegador real, tableta/móvil físico, lector de pantalla y
> validación con coleccionistas. Los PASS son de plantilla, CSS y pruebas.

## 1. Problema local

La ficha mezcla en una sola columna:

1. cabecera con portada, sinopsis, acciones, fuentes y atribución;
2. datos editoriales, autores y procedencia;
3. etiquetas, colecciones del coleccionista, búsqueda automática y notas;
4. completitud (D8), otras fuentes y enriquecimiento;
5. **números que faltan**, números en la biblioteca y archivos, al final.

En una serie de 31 números, el coleccionista tiene que atravesar **más de diez secciones**
antes de llegar a lo que más consulta: sus números. En móvil la portada y el resumen ocupan
la primera pantalla; el resto es una sucesión de bloques sin un índice que permita saltar.
Además, «Estado de la colección» (completitud D8) y «Colecciones» (agrupaciones del
coleccionista) usan la misma palabra para dos conceptos distintos.

### Hallazgos

| Prioridad | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| **P0** | Los números quedan tras ~10 secciones; en móvil no hay atajo | orden de `series_detail.html` | **Mitigado**: navegación por anclas |
| **P0** | «Estado de la colección» se confunde con las colecciones M:N | dos bloques con «colección» | **Corregido**: «Completitud» |
| **P1** | La frase de entrada aparece después del bloque de datos | `.series-intro` tras `ficha-serie-datos` | **Corregido**: antes de los datos |
| **P1** | Cabecera con 4 acciones (editar, añadir, retirar, fuentes) y texto explicativo largo | `.series-acciones` | **Pendiente**: mover «Retirar» a detalles |
| **P1** | Sin navegación entre secciones en tableta/móvil | no había índice | **Corregido**: `ficha-nav` |
| **P2** | «Otras fuentes» muestra un botón deshabilitado cuando no hay fuente | bloque condicional | **Pendiente**: ocultar o plegar |
| **P2** | Rejillas de números sin límite visual para series de 100+ | `.issue-grid` | **Pendiente**: medir y valorar paginación |
| **P2** | «Elegir portada» y «Fuentes y atribución» compiten en la primera pantalla | detalles antes de datos | **Aceptado**: son controles plegados |
| **P2** | Portada 120 px en móvil + título y acciones dejan poco espacio | `.series-cover` | **Aceptado**: portada legible |

## 2. Benchmark

| Referencia | Cómo estructura una ficha larga | Qué se adopta / adapta / descarta |
|---|---|---|
| **Sonarr/Radarr** ([Library](https://wiki.servarr.com/en/sonarr/library)) | Ficha de serie con pestañas (serie, temporadas, historial…) y acciones en menú contextual; el detalle no apila todo en una columna | **Adoptar** la separación por áreas y la acción principal; **descartar** pestañas con estado para no introducir SPA |
| **Komga** ([Collections](https://komga.org/docs/guides/collections/)) | Detalle con paneles plegables y acciones contextuales; la información de colección se despliega solo al pulsar | **Adoptar** los paneles plegables ya usados en portada/fuentes; **descartar** el modo de edición global |
| **Kavita** ([series-detail.component.html](https://git.azen-sgg.ru/AZEN-SGG/Kavita/src/commit/4c44dbf3e205d6b8946d29b20e58fbeabcdb748b/UI/Web/src/app/series-detail/_components/series-detail/series-detail.component.html)) | Pestañas: Storyline, Volumes/Chapters, Specials, Related, Recommendations, Reviews, Details; contenido diferido (`@defer`) | **Adoptar** el principio de que los números son una sección de primer nivel; **adaptar** a anclas, sin JS de pestañas ni estado |
| **Jellyfin/Plex** ([Item details](https://deepwiki.com/jellyfin/jellyfin-web/3.2-library-and-list-views)) | Héroe + acción principal + secciones; el resto se consulta en subpestañas o menús | **Adoptar** una acción principal clara; **descartar** el menú de tres puntos como única vía (poco descubrible) |
| **Calibre-Web / estanterías** | Ficha de libro con metadatos y acciones; las estanterías se gestionan aparte | **Adoptar** no mezclar «completitud» con «colección» |
| **ZascArr, sistema de diseño** ([sistema](sistema-de-diseno-zascarr.md)) | Lo secundario va plegado; ≤ 50 palabras antes de la primera acción; objetivos ≥ 40 px; sin diálogos; un solo principal | **Adoptar** `<details>`, anclas y botones; **descartar** tabs con estado y nuevos componentes |

### Opciones evaluadas

| Opción | Ventaja | Problema | Veredicto |
|---|---|---|---|
| A. Dejar la columna actual | Cero coste | Números inaccesibles en móvil; ambigüedad conceptual | **Descartar** |
| B. Pestañas con estado (Kavita) | Muy compacto | Estado, URLs, caché, HTMX y foco; más superficie de test | **Fase 2**, no ahora |
| C. Navegación por anclas | Nativa, sin JS, teclado, URLs compartibles | No reduce la longitud; requiere buenos ids | **Adoptar** |
| D. Mover números al primer bloque | Prioriza la tarea principal | Cambia la jerarquía editorial y muchas pruebas; el resto sigue siendo largo | **Recomendado como siguiente paso** |
| E. Menú lateral de secciones | Buen acceso en escritorio | En móvil compite con la barra inferior; más CSS | **Descartar** ahora |

## 3. Solución implementada

- **`ficha-nav`** bajo la cabecera, con anclas: Números, Búsqueda, Etiquetas, Colecciones,
  Completitud, Datos y Archivos (esta última solo si hay archivos).
- Cada destino tiene `id` y `scroll-margin-top`; no hay estado ni peticiones adicionales.
- «Estado de la colección» pasa a **«Completitud»** para no confundirse con las colecciones
  del coleccionista.
- La frase «Consulta tus números y ajusta la búsqueda automática» pasa **antes** del bloque
  de datos, no después.
- Los números se agrupan en `<section id="numeros-serie">` para que el ancla sea estable.
- La navegación no entra en el presupuesto de texto de entrada: es un control, no copy.
- Sin nuevos componentes visuales: usa `.btn.ghost.sm` (≥ 40 px) y los tokens existentes.

### Móvil y tableta

- La navegación envuelve en varias filas; no hay scroll horizontal.
- Cada enlace mantiene 40 px de alto y foco visible; se puede usar con teclado.
- El salto a «Números» evita recorrer datos, etiquetas, política y notas.
- No se toca la barra inferior de navegación de la app.

## 4. Lo que queda propuesto (no implementado)

1. **Mover el bloque de números justo después de la cabecera**, antes de datos y etiquetas;
   la navegación ya lo hace accesible, pero la jerarquía sigue siendo datos-first.
2. **Plegar «Retirar de mi biblioteca»** en un `<details>` o menú secundario: es una acción
   destructiva que hoy compite con «Añadir números del disco».
3. **Ocultar «Otras fuentes»** cuando no hay ninguna fuente asociada, o integrarlo en el bloque
   de datos.
4. Medir una serie de 100+ números para decidir si las rejillas necesitan paginación o un
   resumen «Ver los 100».
5. Validar con 3–5 coleccionistas en tableta y móvil; sin esa validación no se cierra el P0.

## 5. Criterios de aceptación

- La ficha contiene una navegación con anclas a Números, Búsqueda, Etiquetas, Colecciones,
  Completitud y Datos; Archivos solo si existe la sección.
- «Completitud» sustituye a «Estado de la colección» en la ficha de serie.
- La frase de entrada aparece antes del bloque de datos.
- No se introducen nuevos componentes, JS propio ni diálogos.
- La suite de ficha, componentes y tokens de CSS sigue verde.

## 6. PASS / FAIL / NOT RUN

- **PASS (código/pruebas):** navegación por anclas, ids estables, «Completitud», entrada
  movida, presupuesto de texto y estilos con tokens.
- **FAIL (previo, corregido/mitigado):** números sin atajo, ambigüedad «colección».
- **NOT RUN:** navegador real, tableta/móvil, lector de pantalla y validación con personas.
