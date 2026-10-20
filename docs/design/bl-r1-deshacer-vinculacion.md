# BL-R1 — Deshacer una vinculación: contrato técnico y estimación refinada (propuesta)

> **Estado: PROPUESTA para el revisor y el PO. Sin código, sin migración, sin tocar el backlog.** Cierra la parte de **diseño** de la Definition of Ready de #230
> (contratos, efectos, dependencias, riesgos y estimación) y plantea **D8–D10**. Decisión de comprobante e historial: `docs/adr/0014-deshacer-vinculacion.md` (**Propuesto**).
> Verificado sobre `main` `6001555` (2026-10-20). Benchmark: `docs/design/benchmark-reconciliacion-plex.md` (BL-R0, fusionada).

## 1. Alcance (D5, decidida por el PO)

**Sí:** deshacer la vinculación de **un** archivo (vuelve a «Por revisar») y, **después y aparte**, volver a vincular con el recorrido existente. «Corregir» es esa secuencia, no una sustitución atómica.
**No (v1):** corrección de edición o publicación (M5), lotes, mover o renombrar el fichero, aprender alias, retirar el número creado (D1: **se conserva siempre**), reasignación atómica.

## 2. Hallazgos que cambian el diseño (verificados)

| # | Hallazgo | Consecuencia |
|---|---|---|
| H1 | El informe de vinculación es **inmutable** (0019) | El deshacer no puede reescribirlo; ADR 0014 propone guardar comprobante e historial **en el propio archivo** (sin migración) |
| H2 | «Pendiente» exige `match_status = 'unsorted'` además de `issue_id` nulo (`review.py::_condiciones_pendientes`); la vinculación **no cambia** `match_status` | Tras deshacer hay que **fijar** `match_status='unsorted'` y `review_dismissed=false` (contrato **actual** de Pendientes, criterio 3) en vez de restaurar `previo` a ciegas |
| H3 | La vinculación guarda `previo.{match_status, review_motivo}` pero **no** `metadata_source` (solo escribe `'manual'`) | **D8**: qué `metadata_source` queda tras deshacer |
| H4 | `metadata.vinculo` solo existe en vínculos hechos con «vincular en su sitio» (2d). Los de «organizar» (V6a, que además **mueve** el fichero) y los automáticos del importador no la tienen | **D9**: qué vínculos se pueden deshacer en v1 |
| H5 | **No existe ficha de archivo** y `series_detail.html` solo pinta los números poseídos (`present`/`missing`), no los archivos | **D10**: el criterio 1 («desde la ficha de la serie y la de un archivo») exige crear una superficie nueva; sube el coste |
| H6 | Nadie fuera de `vinculacion.py` lee `metadata.vinculo` y los demás escritores de `File.metadata_` **fusionan** | Seguro guardar el historial en `files.metadata` |
| H7 | `check_completions` solo revisa deseados aún abiertos; uno ya `IMPORTED` no se reabre | Deshacer no provoca por sí mismo una nueva búsqueda de lo ya cerrado; sí vuelve a salir como **hueco** y puede afectar a un deseado aún abierto (a probar) |

## 3. Contrato

### 3.1 Vista previa (solo lectura; no escribe nada)
Entrada: `file_id`. Calcula, sin candados largos:
- De qué **serie y número** sale (`issue_id` → `Issue`), y si esa vinculación **creó** el número (`vinculo.issue_creado`).
- Si el número **se queda sin archivos** (otros `File` con ese `issue_id`), y qué **depende** de él: `reading_progress`, deseados (`wishlist.issue_id`/número), otros archivos.
- Qué se **conserva**: ruta, nombre, tamaño y hash (la fila no se borra, el fichero no se toca).
- Qué pasará **después**: el archivo aparece en «Por revisar»; **volver a vincular es una operación aparte** que puede cancelarse o fallar, y entonces el archivo **sigue pendiente** (criterio 6, se dice **antes** de confirmar).
- Bloqueos con código: `no_vinculado` (`issue_id` nulo), `en_curso` (asignación viva en `asignacion_operaciones`), `archivo_inexistente` (fila borrada). `is_missing` **sí** se puede deshacer. Si el archivo lo movió una asignación (V6a), la pantalla dice que **no se devuelve** a su carpeta anterior.
Salida: un **token firmado** nuevo (propósito `desvincular`, distinto de `vincular`/`alta`, mismo TTL de 15 min) con: `file_id`, `issue_id`, `series_id`, `numero`, `vinculo_operacion` (el `operacion_id` del vínculo, o `null`), la **huella** del vínculo `(file_path, file_size_bytes, sha256_hash)` y un `operacion` nuevo (UUID).

### 3.2 Confirmación (una transacción; recibe **solo** el token)
Orden de bloqueos, el mismo que alta/vinculación: **operación** (candado consultivo `pg_advisory_xact_lock` sobre `operacion`) › **serie** (`FOR SHARE`) › **archivo** (`FOR UPDATE`) › **issue** (`FOR SHARE`).
1. Si la entrada de `vinculo_historial` con ese `operacion` ya existe → **`ya_deshecho`**: se devuelve **el mismo resultado**, sin escribir.
2. Con la fila bloqueada se **vuelve a comprobar** todo: `issue_id` = el del token, `vinculo.operacion_id` = el del token, huella igual, sin asignación viva. Si algo cambió → `cambio_desde_la_vista_previa` (exige vista previa nueva; **nunca** sobrescribe cambios posteriores).
3. Una sola sentencia `UPDATE files … WHERE id = :f AND issue_id = :i` (rowcount debe ser 1, si no → rollback y error inesperado) que: pone `issue_id = NULL`; **quita** `metadata.vinculo`; **añade** a `metadata.vinculo_historial` la procedencia anterior íntegra + `deshecho:{operacion_id, fecha}`; fija `match_status='unsorted'` y `review_dismissed=false` (H2); aplica D8 a `metadata_source`. Todo por **fusión JSONB** (`||` y `-`), nunca sustituyendo el objeto.
4. **No se toca**: el `Issue` (D1), el fichero, `file_path`/`file_name`/hash, lecturas, deseados.
5. Un fallo tras pedir el `commit` es **incierto** (`ResultadoInciertoError`): se resuelve **releyendo la fila** (3.1 paso 1), no reintentando a ciegas.
Respuesta: `deshecho` | `ya_deshecho` | `omitido` con motivo (`no_vinculado`, `en_curso`, `cambio_desde_la_vista_previa`, `archivo_inexistente`).

### 3.3 Volver a vincular
Sin cambios en el servicio de 2d: el archivo ya cumple el contrato de Pendientes y entra por el recorrido existente (#119/#120) con su propia vista previa y confirmación.

## 4. Decisiones nuevas (para el PO / revisor)

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **D8** | `metadata_source` tras deshacer | (a) dejar `'manual'`; (b) restaurar el previo si consta y, si no, `NULL`; (c) siempre `NULL` | **(b)**, y que la vinculación **guarde** `previo.metadata_source` en los vínculos **nuevos** (cambio aditivo en `_vincular_archivo`). Para los antiguos: `NULL` (el origen `'manual'` queda en el historial) |
| **D9** | Qué vínculos se deshacen en v1 | (a) solo los de «vincular en su sitio» (tienen procedencia); (b) además los de V6a; (c) cualquiera con `issue_id` | **(a)** para v1: es lo que tiene procedencia verificable y el caso de MVP. Los demás se muestran **sin** el botón y con la razón. (c) exigiría una «huella» alternativa y decidir qué significa deshacer un movimiento |
| **D10** | Dónde entra la persona | (a) añadir a `series_detail` una lista de archivos por número con «Deshacer»; (b) una ficha de archivo nueva; (c) solo desde el informe de la vinculación recién hecha | **(a)**: es donde la persona ve «tengo el #5»; (c) no cubre el caso «lo vi mal días después». Es **trabajo de UI nuevo** (ver estimación) y toca el contrato HTMX de `series_detail` (consultar `docs/design/ui-migracion.md`) |

## 5. Pruebas (definidas; **NOT RUN**)

Postgres real salvo lo indicado; cada bug real, un test de regresión con el nombre del mecanismo.
1. **Deshacer feliz:** `issue_id` nulo, `vinculo` fuera, entrada en `vinculo_historial` completa, aparece en Pendientes (mismo filtro que la lista y el recuento), **ni un byte** del fichero tocado (hash y mtime iguales), `Issue` intacto.
2. **Idempotencia y recuperación:** repetir con el mismo token devuelve lo mismo y **no escribe**; fallo antes y después del `commit`; resultado incierto resuelto leyendo la fila.
3. **Cambio entre vista previa y confirmación:** otro vínculo, otro `file_path`, otro tamaño/hash → `cambio_desde_la_vista_previa`, sin escribir.
4. **Concurrencia:** doble envío simultáneo; deshacer frente a vincular el mismo archivo; deshacer frente a borrar la serie; frente a una asignación V6a (`en_curso`); orden de bloqueos sin interbloqueo.
5. **Cadena:** vincular → deshacer → vincular a otro número: `vinculo` nuevo, historial con la primera procedencia, sin pérdida.
6. **Historial no se pisa:** los demás escritores de `metadata` (tagger, importer, review) no borran `vinculo_historial` (regresión de H6).
7. **Efectos colaterales:** número sin archivos reaparece como hueco; deseado aún abierto; lecturas intactas; `is_missing` se puede deshacer; V6a: aviso de que no se devuelve la carpeta.
8. **Mutaciones:** sin comprobar la huella, sin fijar `match_status='unsorted'`, sin quitar `vinculo`, sustituyendo el objeto `metadata` en vez de fusionar, sin el candado de operación, `UPDATE` sin `WHERE issue_id`.
9. **Navegador real** (entrada, vista previa, resultado, el archivo en «Por revisar») y **sin JS**. PASS, FAIL y NOT RUN separados.

## 6. Estimación refinada (por quien implementaría; **no calibrada, no es un compromiso**)

La tarjeta propone **8 pts, L, confianza Baja**. Con lo anterior:

| Parte | Pts | Nota |
|---|---|---|
| Servicio (vista previa + confirmación + token + historial) | 3 | Calca 2d (`vinculacion.py`, `tokens_revision.py`), con menos E/S (no hace `stat` de ficheros) |
| Superficie de usuario (H5/D10: lista de archivos en la serie, vista previa, resultado, mensajes en español) | 3 | **Trabajo nuevo**: hoy no existe |
| Pruebas (Postgres real, concurrencia, mutaciones, navegador) | 3 | El grueso del riesgo |
| Documentación, ADR y regresiones | 1 | |
| **Total** | **≈ 10** (rango 8–13) | Confianza **Media-Baja**: D8–D10 pueden moverlo |

**Propuesta: partir en dos entregas** para no tener una historia de 10: **BL-R1a** (servicio + API + pruebas, ≈ 6) y **BL-R1b** (superficie + navegador, ≈ 4). Es una propuesta de organización, **no** se aplica al tablero sin orden.

## 7. Riesgos

- **R1** Perder historial si un escritor futuro sustituye `metadata` entera → prueba 6 y nota en el contrato de `File.metadata_`.
- **R2** Dejar un archivo «ni vinculado ni pendiente» por un `match_status` raro → H2 + prueba 1 con los tres valores posibles.
- **R3** El deseado abierto que depende de ese número vuelve a «no lo tengo» → se avisa en la vista previa y se prueba (prueba 7).
- **R4** Superficie nueva en `series_detail`: toca un contrato HTMX documentado → revisar `docs/design/ui-migracion.md` antes.
- **R5** `previo.metadata_source` solo existirá en vínculos nuevos → los antiguos se tratan con `NULL` (D8 b).

## 8. Qué NO autoriza este documento

Código, migraciones, fuentes reales, despliegue, cambios del tablero ni la partición de la tarjeta. Pendiente: revisión del ADR 0014 y decisión de D8–D10.
