# Ficha de benchmarking — #397 (BL-FILT1): filtrar «Pendientes por carpeta» por nombre y estado

> Ficha de **nivel 1** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): ≤ 2 referencias, sin matriz. Insumo, no aprobación; decide el PO.
> **Fecha:** 2026-11-01 · **SHA contrastado:** `9d7fedf` (`origin/main`). **Caduca:** ~60 días, o antes si cambia la historia o la ruta de carpetas.
> **Actualizada el 2026-11-01 tras las decisiones del PO** (filtro del nombre en Python sin prefiltro SQL; modelo de estados; «Volver» sin parámetro de retorno).

## Historia / problema observado
Hoy `/ui/pendientes/carpetas` solo pagina y admite `?serie=`; no filtra. Con 108 carpetas (referencia de la Pi) o más, encontrar una carpeta concreta exige recorrer las páginas.

## Comportamiento actual (contrastado en `9d7fedf`; leído en código, no ejecutado)
| Pieza | Hoy | Dónde |
|---|---|---|
| Ruta | `limite` (50 por defecto), `desplazamiento`, `serie`; sin filtro | `web/pendientes.py:293-300` |
| Servicio | `carpetas(limite, desplazamiento, solo_utiles)`: **una** consulta de todos los pendientes (`_leer`, sin `WHERE` por nombre), agrupa en Python por `clave` y pagina **después** de filtrar | `services/revision_carpetas.py:300-356, 475-495` |
| Estado del grupo | Derivado: `estado` ∈ {`sin_serie`, `serie_sugerida`, `mixto`} y dos marcas **no excluyentes**, `por_confirmar` y `en_conflicto` | `revision_carpetas.py:45, Grupo` |
| Recuento | La vista usa `carpetas_utiles`; muestra «desde–hasta» | `web/pendientes.py:_vista_carpetas` |
| Paginación | En la URL; los enlaces se rehacen con una macro que conserva `limite` y `serie` | `templates/carpetas.html:4` |
| **Volver desde el asistente** | «Volver a las carpetas» enlaza a `/ui/pendientes/carpetas` **sin parámetros**: se pierde la página y la serie; «Elegir otra carpeta para esta serie» conserva solo `serie` | `_vinculacion_resultado.html:34, 37, 89, 92` |
| Valor no válido de `serie` | 200 con aviso, sin 500 | `web/pendientes.py:_serie_del_filtro` |

## Referencias consultadas (versión/commit, 2026-11-01)
| Referencia | Versión / commit | Licencia | Nota |
|---|---|---|---|
| Komga | `25c67d1` (2026-10-30) | **MIT** (`LICENSE`) | El encargo decía GPL-3.0: es MIT. Solo se leyó la interfaz web (`komga-webui`) |
| Sonarr | `9a41dfc` (2026-10-31) | GPL-3.0 | Solo la interfaz (`frontend/src/Wanted`, `Helpers/Hooks`) |

Kavita no se examinó; Kapowarr solo se miró en lo que toca al almacenamiento del filtro de su biblioteca (`general.js`, `localStorage` con `lib_filter`) y no cuenta como referencia. Inspirarse en un patrón no es copiar código.

## Cómo lo resuelve cada una
- **Komga** (`views/BrowseLibraries.vue`).
  - Filtros en **paneles de selección múltiple**, con un modo por criterio (`allOf`: «todos» o «alguno»).
  - **El filtro vive en la URL**: `updateRoute()` escribe página, tamaño, orden, filtros y modo con `router.replace`. Al entrar, se **restaura desde la URL** y, si no hay filtros en ella, desde un valor guardado por biblioteca (`getLibraryFilter`; el medio de almacenamiento no se verificó).
  - Los valores de la URL se **validan** contra las opciones conocidas (`validateFilters` con `intersectionWith`): lo desconocido se ignora sin error.
  - **Estado vacío**: «The active filter has no matches» con un botón «Reset filters» (`locales/en.json:239, 274`).
  - El filtrado lo hace el servidor (la página pide condiciones a la API).
- **Sonarr** (`Wanted/Missing`).
  - **Selector único** de filtros predefinidos (`monitored`, `unmonitored`, `excludeSpecials`) más **filtros personalizados** construidos con condiciones (`FILTER_BUILDER`); no hay chips ni multiselección entre predefinidos.
  - `selectedFilterKey` y `pageSize` van en un almacén de opciones **persistido en el navegador** (`createOptionsStore('missing_options')` con `createPersist`; el medio exacto no se verificó). La página vive aparte (`usePage('missing')`).
  - Al cambiar el tamaño de página vuelve a la página 1 (`Missing.tsx:192`); para el cambio de filtro no lo comprobé.

*«No lo encontré» no equivale a «no existe».* No comprobé en ninguna: normalización de tildes y mayúsculas, tipo de coincidencia del texto («contiene» o exacta), contador «N de M», ni qué hacen al volver de un detalle por una vía distinta del retroceso del navegador.

## Respuestas a las preguntas del encargo
1. **Estados no excluyentes.** Komga usa multiselección con un modo «todos/alguno» por criterio; Sonarr, un selector único más filtros personalizados con condiciones. Ninguna separa un estado excluyente de marcas independientes. Para ZascArr encaja un **selector del estado excluyente** (todas / sin serie / con serie sugerida / mixto) **más dos marcas independientes** («por confirmar», «en conflicto») combinadas con «y»; con solo dos marcas no hace falta el modo «todos/alguno». *Resuelto por el PO (2026-11-01):* modelo (c), con «Por confirmar» = «Con serie sugerida» o «Mezcla».
2. **Conservar el filtro al entrar en un detalle y volver.** Komga lo hace guardándolo en la **URL** (más un valor guardado como respaldo). ZascArr ya pagina por URL, así que el filtro debe ir en la misma consulta. Lo que hoy rompe la vuelta es el enlace «Volver a las carpetas», que no lleva nada: el filtro debe propagarse por el asistente. *Decidido por el PO (2026-11-01):* «Volver» sin parámetro de retorno (ni URL ni ruta de vuelta), lo que evita la redirección abierta; propagación por el asistente salvo en el «resultado guardado».

## Resultado por idea (propuesta; decide el PO)
| Idea | Resultado | Motivo |
|---|---|---|
| Filtro en la URL, restaurado desde ella (Komga) | **Adaptar** | Encaja con la paginación y `serie` ya en URL; propagar el filtro por el asistente, sin parámetro de retorno |
| Validar los valores y no fallar (Komga) | **Adaptar** | ZascArr ya avisa con 200 en `serie` inválida; mejor un aviso que ignorar en silencio |
| Selección múltiple (Komga) sin el modo «todos/alguno» | **Adaptar** | Solo hacen falta dos marcas independientes |
| Estado vacío con «quitar filtros» (Komga) | **Adoptar** | Mismo problema, sin dependencia; texto en español llano |
| Guardar el filtro en el navegador como respaldo (Komga, Sonarr) | **Descartar** por ahora | Estado oculto que sorprende; la URL basta. Opción a decidir por el PO |
| Selector único + filtros personalizados con condiciones (Sonarr) | **Descartar** | Pensado para usuarios técnicos |
| «N de M» tras filtrar; mantener el filtro al volver desde el asistente | **Mejorar** | No lo encontré en las referencias examinadas; evidencia: hoy «Volver» pierde página y serie |
| Filtro del nombre en Python sobre la `clave`, sin prefiltro SQL (decisión del PO) | **Construir sobre lo propio** | Una sola consulta; totales y «M» intactos; el servicio ya lo carga todo |
| Prefiltro SQL del nombre | **Descartar** por ahora | Contradice los totales y el «M» con una única consulta; Python y PostgreSQL pliegan distinto (ß, ø, æ, œ, đ, ł, ð, þ, ħ, ı, ½); no ahorra memoria ni consultas. Para reabrirla: medir en la Pi, normalizar el patrón en la misma consulta SQL y una prueba de paridad con PostgreSQL real |

**Decisiones del PO del 2026-11-01:**
- **Modelo de estados (c):** un selector excluyente más dos marcas independientes, «Por confirmar» y «En conflicto». «Por confirmar» = «Con serie sugerida» o «Mezcla». Resuelve la duda sobre `mixto`.
- **«Volver» sin parámetro de retorno:** el enlace no lleva una URL ni una ruta de vuelta.
- **Propagación del filtro por el asistente**, salvo en el «resultado guardado».

## IGUALAR (mínimo competitivo)
1. El filtro sobrevive a paginar y a recargar (va en la URL).
2. Un valor no válido nunca da error: se avisa o se ignora.
3. Estado vacío que dice que ninguna carpeta coincide y ofrece quitar el filtro.
4. Cambiar el filtro vuelve al principio de la lista (sin páginas vacías). *(Sonarr lo hace al cambiar el tamaño de página; el cambio de filtro no se comprobó.)*

## MEJORAR (con evidencia)
1. **Volver desde el asistente conservando filtro, página y serie.** Hoy `_vinculacion_resultado.html:34, 89` enlaza sin parámetros. Sin parámetro de retorno: el filtro se propaga por el asistente, salvo en el «resultado guardado» (decisión del PO).
2. **Recuento «N de M»** tras filtrar. No lo encontré en las referencias.
3. **Estado excluyente y marcas independientes** en vez de una lista plana de cuatro estados.
4. **Nombre sin mayúsculas ni tildes** (decisión del PO). Ninguna referencia examinada lo documenta; se hace en Python sobre la `clave`; Python y PostgreSQL pliegan distinto (ß, ø, æ, œ, đ, ł, ð, þ, ħ, ı, ½), así que la prueba debe fijar el pliegue elegido.

## Invariantes de ZascArr
No mentir (el recuento y el vacío dicen la verdad) · no escribir (la lista sigue siendo solo lectura) · coste Pi (el servicio ya carga todo en una consulta; el filtro del nombre no añade consultas) · sin redirecciones abiertas · español llano.

## Casos de prueba antes de implementar (propuestos)
Filtro por nombre «sin tildes ni mayúsculas» devuelve la misma carpeta que con ellas · el filtro se conserva en los enlaces de página y en «Volver» del asistente · filtro sin coincidencias → estado vacío con «quitar filtro» y página 1 · desplazamiento fuera de rango tras filtrar → no hay página vacía · valor de estado desconocido → aviso, no 500 · el enlace «Volver» no lleva parámetro de retorno · prueba de pliegue con ß, ø, æ, œ, đ, ł, ð, þ, ħ, ı y ½.

## NOT RUN / no verificado
- Nada ejecutado: ni ZascArr, ni las referencias, ni la suite; todo es lectura de código.
- Komga: solo `komga-webui`, y no verifiqué el medio de almacenamiento del filtro de respaldo ni el comportamiento al volver de un detalle. Sonarr: solo la interfaz; no verifiqué el medio de `createPersist` ni el reinicio de página al cambiar de filtro. Kavita sin examinar.
- No medí en la Pi el filtro en Python ni, para reabrir el prefiltro SQL, su coste; las diferencias de pliegue entre Python y PostgreSQL son un dato aportado por el PO, no medido por mí.
- Ninguna queja de usuarios consultada.
