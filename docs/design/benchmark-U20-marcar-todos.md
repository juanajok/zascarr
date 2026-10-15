# Ficha de benchmarking — U20: marcar todo lo vinculable y revisión sin jerga

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #207 (BL-U20, P0, MVP).
> Esfuerzo proporcional: la parte de **textos** es un arreglo evidente (no necesita investigación); la parte de
> **marcar/desmarcar todos** es comportamiento nuevo y es la que se compara aquí.

> **Honestidad sobre el orden.** Esta ficha se escribió **después** de un primer borrador de la implementación
> (sin commitear), no antes como exige el §13. Se detectó en la sesión (el responsable lo recordó mientras se
> codificaba) y se hizo el benchmarking antes de cualquier commit, dejando que pudiera cambiar el diseño. Lo que
> cambió está en «Decisión final».

## Historia / problema observado

Como coleccionista con carpetas de cientos de archivos, quiero marcar de una vez todo lo que se puede vincular y
leer la revisión en mi idioma. La revisión de #119 solo tiene una casilla por fila (`_vinculacion_revision.html`)
y una carpeta como `Flash (1987)` tiene 155 archivos, en páginas de hasta 100. Los textos del contrato
(«El token caducó…», «Lote preparado», «motivo: x») llegaban a la pantalla.

## Datos reales y medición de partida

- Caso de la instalación de referencia: `Flash (1987)`, 155 archivos (observación del responsable, 2026-10-15).
- Antes: marcar una página entera = una pulsación por fila. Después: una.
- Medido en `main` `e65e047`: las 26 pruebas nuevas de `tests/test_asistente_vinculacion_masivo_pg.py` dan **21
  fallos** contra su `src/` (las 5 que pasan comprueban que no hay efectos ni acciones inválidas). Las de jerga
  fallan porque la revisión y el resultado dicen «lote», «token» y «motivo: x» (`TestSinJerga*`).

## Referencias consultadas (código leído, no pantallas)

| Referencia | Commit | Licencia | Ficheros leídos |
|---|---|---|---|
| Sonarr, rama `v5-develop` | `d137dc5a19f46a8aa6d41e706143cad1f0af27af` | GPL-3.0 | `frontend/src/InteractiveImport/Interactive/InteractiveImportModalContent.tsx`, `InteractiveImportRow.tsx` |
| Kapowarr, rama `development` | `5b225cfed49d9eccf13e14cb2a947143477606ef` | GPL-3.0 | `frontend/static/js/library_import.js`, `backend/features/library_import.py`, `docs/src/general_info/library_import.md` |

**Solo como patrón: no se copia código** (barrera legal del §13). **No consultadas:** Radarr (su importación manual
comparte base con la de Sonarr, pero no se leyó), Mylar3 y Suwayomi — no se buscó en ellas un «seleccionar todo» de
importación, así que **no se afirma que no lo tengan**.

## Cómo lo resuelve cada una

**Sonarr (Importación interactiva).**
- «Seleccionar todo» (`selectAll()`) selecciona **todas** las filas, valgan o no.
- La validez se comprueba **por fila y después**: una fila seleccionada sin serie, temporada o episodios muestra un
  marcador de lo que falta (`showSeriesPlaceholder`, …) y el botón Importar se **desactiva mientras haya alguna**
  fila seleccionada inválida (`isDisabled={!selectedIds.length || !!invalidRowsSelected.length}`).
- Al enviar, si dos filas seleccionadas apuntan al mismo episodio, **no elige**: bloquea **toda** la importación con el
  mensaje `InteractiveImportDuplicateEpisodes`.
- Los rechazos (`rejections`) se muestran como columna informativa.

**Kapowarr (Library Import).**
- Al cargar la propuesta, «seleccionar todo» arranca **marcado** y `toggleSelectAll()` marca/desmarca todas las
  casillas **en el navegador** (JavaScript propio).
- Una fila **sin coincidencia** (`cv.id === null`) queda marcada igual y, al importar, **se descarta en
  silencio**: `importLibrary` la filtra con `.filter(i => rowidToFilepath[...].cv_id !== null)` y no avisa.
- No comprueba duplicados en la selección: agrupa por volumen (`cvid_to_filepath.setdefault(id, []).append(...)`).

## Supuestos de su modelo que NO valen en ZascArr

- **Marcar ≠ vincular.** En ellos seleccionar es parte de importar y el filtrado va al final. En ZascArr la revisión
  firma un token del subconjunto ejecutable (`incluido_en_token = marcado and marcable`); la persona ve qué entra
  **antes** de confirmar, y confirmar es otra acción.
- **Un destino por fila.** Ambas deciden la coincidencia (serie/episodio o volumen de ComicVine); aquí la serie ya
  la eligió la persona y la fila solo lleva un número editable.
- **Cliente rico.** Los dos hacen el «seleccionar todo» en JavaScript del navegador. ADR 0005 (decisión 3) lo
  excluye: sin JS propio, toda acción es una petición HTMX al servidor.
- **Descartar sin avisar.** Kapowarr lo hace; aquí rompería el invariante «nunca decir que algo está hecho cuando no
  lo está».

## Adoptar / adaptar / descartar

| Idea | Decisión | Motivo |
|---|---|---|
| «Seleccionar todo» y «Quitar la selección» como pareja simétrica (Sonarr `selectAll`/`unselectAll`) | **Adoptar** | La persona espera poder deshacer el marcado de una vez |
| Seleccionar **todas** las filas y validar después (ambas) | **Adaptar** | La tarjeta (criterio 1) pide marcar solo lo marcable. El servicio ya calcula `marcable`; marcar un bloqueado solo produciría «Marcado, pero no se puede vincular» |
| No elegir entre destinos duplicados (Sonarr) | **Adoptar y adaptar** | Mismo principio (nada decide por la persona). Sonarr **bloquea todo**; aquí se **dejan sin marcar** los repetidos y se cuentan, y el resto sigue |
| Filtrar en silencio lo que no se importa (Kapowarr) | **Descartar** | Miente por omisión. Aquí el recuento sale de la evaluación **final** y lo que acabe bloqueado se dice |
| «Seleccionar todo» en JS del cliente (Kapowarr) | **Descartar** | ADR 0005, decisión 3 |
| Selección por rango con Mayús (ambas) | **Descartar por ahora** | Fuera de alcance de U20; con 100 filas por página, «todos» cubre el caso |

## Invariantes de ZascArr

- **No mentir:** «Se marcaron N» cuenta lo que el servicio da por vinculable **tras** la última evaluación.
- **No decidir por la persona:** con números repetidos no se marca ninguno de los dos.
- **Solo la página que se ve:** los borradores de otras páginas no se tocan.
- **Sin efectos:** marcar y desmarcar no escriben en la BD ni en el disco; vincular sigue siendo la acción aparte de
  #120, con su vista previa.
- **Pi:** una página es como mucho 2 evaluaciones (`stat` de ≤ 100 archivos cada una) en vez de 1; **no medido en
  la Pi**.

## Casos de prueba (`tests/test_asistente_vinculacion_masivo_pg.py`, Postgres real)

El caso que motivó la historia y el límite que las referencias no cubren:
- Marcar solo lo marcable y devolver el recuento (el caso de la historia).
- No marcar ni tocar otras páginas ni sus borradores; no elegir entre repetidos; respetar el número recién escrito.
- **El límite que Kapowarr no cubre:** una marca que acaba bloqueada **no** se cuenta y **no** se oculta
  (`test_una_marca_que_acaba_bloqueada_no_se_cuenta_ni_se_deja_caer_en_silencio`).
- Sin efectos (BD y disco idénticos), sin `<script>` ni `onclick`, acción desconocida ignorada.
- Regresión de jerga: ninguna revisión ni resultado dice «token», «lote» ni «motivo:».

## Decisión final

**No cambia la arquitectura: sin ADR.** Qué cambió por el benchmarking, con honestidad:
1. **Cambió el recuento:** el borrador contaba lo que pretendía marcar; ahora cuenta lo que el servicio da por
   vinculable tras la segunda evaluación y avisa de lo demás (efecto directo del hallazgo sobre Kapowarr).
2. **Se confirmó, sin cambiarlo,** marcar solo lo marcable y no elegir entre repetidos.
3. **Límite conocido, no resuelto:** un número repetido entre **dos páginas** no se detecta al marcar (el servicio
   evalúa repetidos dentro de la página); lo atrapa `numero_ya_existe` cuando la primera ya está vinculada. Si hace
   falta, es otra historia.
