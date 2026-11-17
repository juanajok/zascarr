# Benchmark y rediseño de `/ui/pendientes` (Por revisar)

> **Procedimiento:** `docs/design/benchmark-referencias.md` (nivel 2). **Fecha:** 2026-11-17.
> **Base contrastada:** `origin/main` `3cb7f9f`. **Caduca:** ~2027-01-16.
> **Diseño:** `docs/design/sistema-de-diseno-zascarr.md`; esta pantalla **no** estaba en la
> auditoría UI/UX del 2026-11-15.

## 1. Problema local y datos reales

La pantalla resuelve una cola de **666 archivos sin clasificar**, pero se pintaba como una
galería de tarjetas de 200 px: 50 por página, 5 columnas en 1240 px y tarjetas de 500–600 px
de alto. En 2002×838 solo se veía una fila; el resto quedaba debajo y a la derecha sobraba
espacio. Además, **567/666 (85,1 %)** no pueden dar portada y reservaban 120×180 px de
marcador; solo **44 (6,6 %)** tenían sugerencia.

| Dato | Valor |
|---|---:|
| Pendientes | 666 |
| Página / páginas de cursor | 50 / 14 |
| CBR / CBZ / PDF / CB7 | 575 / 87 / 3 / 1 |
| Con contenido ZIP/tebeo (puede dar portada) | 99 (14,9 %) |
| Sin posibilidad de portada | 567 (85,1 %) |
| Con sugerencia guardada | 44 (6,6 %) |

## 2. Referencias

| Referencia | Versión / commit | Qué se leyó |
|---|---|---|
| Sonarr en vivo | 4.0.17.2952, `97e85a9` | Wanted/Missing, pager, tabla, importación manual, selector de serie |
| Radarr en vivo | 6.1.1.10360, `df8f82c` | mismo contrato con películas |
| Kapowarr | `c191dda` (V1.3.2) | Library Import, tabla y límites |
| Mylar3 | `cdc94a4` (v0.8.3) | importresults/manage |
| Suwayomi | v2.4.2366 | no tiene cola de revisión de archivos; no aplica |

La evidencia de Sonarr/Radarr es API en vivo + código de la versión instalada, no una sesión
de UI. No se copia código (GPL-3.0/MPL-2.0); solo patrones.

## 3. Decisión

**Opción A: lista horizontal de viñetas**, 1 fila por archivo, ancho completo, portada de
64 px **solo si `con_portada`** y chip de formato si no. Una sola lectura del número; la
acción de organizar es neutral (la única acción principal de la pantalla es «Revisar por
carpeta»); vincular y especial viven en desplegables; «Elegir otra serie» e «Ignorar» en el
pie. Se conserva el cursor y el rango de U12; sin JS ni migración.

Matriz ponderada (densidad 25 · coste Pi 20 · identidad 15 · seguridad 15 · HTMX/accesibilidad
15 · evidencia 10): **A 4,50**, B tabla 4,10, C parche 3,65, actual 2,55, modal 2,35.

## 4. IGUALAR / MEJORAR

- **IGUALAR** densidad de Sonarr/Radarr: más filas visibles, estados explícitos, acción por
  fila y confirmación de lo destructivo.
- **MEJORAR**: no reservar portada para quien no puede tenerla (567 casos), mostrar la
  confianza de la sugerencia y no duplicar formularios/inputs. El cursor propio se conserva
  frente al `OFFSET` de Sonarr.

## 5. Límites / NOT RUN

No se abrió una sesión autenticada de Sonarr/Radarr ni de ZascArr, no hay captura propia de
la UI, no se midió el render a 1280/375 px ni el DOM/tiempo en la Pi. El benchmark no decide
filtros/orden ni tamaño de página: quedan como siguiente iteración si el PO los pide.

## 6. Segunda iteración (2026-11-17)

Se añaden, sin cambiar el cursor:

- **Filtro «Solo con sugerencia»** (`?solo_sugerencia=1`), aplicado a la lista, al rango y a la posición con el mismo `_condiciones_pendientes`; no cambia qué es un pendiente para el menú.
- **Tamaño de página 25/50** (`?tamano=25|50`), conservado en los enlaces de cursor e inicio.
- **Indicador «Preparando la previa…»** con `hx-indicator`, sin JS propio.

El orden por nombre/formato queda fuera de esta iteración: exige una clave de cursor distinta y no se adopta el `OFFSET` de Sonarr/Radarr.
