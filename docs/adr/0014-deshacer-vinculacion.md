# ADR 0014: Deshacer una vinculación — comprobante e historial (D2)

- Estado: **Aceptado** · 2026-10-20 (propuesto y aceptado el mismo día tras la revisión final del revisor/PO). Cierra **D2** de la épica BL-R (#228) para BL-R1 (#230). **No autoriza
  código ni migración por sí mismo**: la implementación de #253 requiere además la orden expresa del PO. Contrato técnico: `docs/design/bl-r1-deshacer-vinculacion.md`.
- Relacionado: ADR 0006 (asignación recuperable), ADR 0007 (vincular en su sitio), `docs/design/benchmark-reconciliacion-plex.md` (ficha BL-R0, §8 D1–D7).
- **Enmienda 2026-10-23 (D9 revisada por el PO):** se deshace **cualquier** vínculo, conste o no cómo se hizo (ver «Enmienda: D9» al final). El comprobante (opción C) no cambia.

## Contexto

BL-R1 pide que «deshacer» una vinculación sea **idempotente y deje un comprobante duradero** (criterio 8) y que lo anterior quede **anotado sin perder la procedencia**
(criterio 7). Hechos verificados en `main` (`6001555`):

| Hecho | Dónde |
|---|---|
| El informe de una vinculación es **inmutable**: un disparador `BEFORE UPDATE` rechaza todo `UPDATE`; `DELETE` sí (purga a las 24 h **y** token caducado) | migración 0019, `VinculacionOperacion` |
| El alta de serie usa una tabla **mutable** (`alta_operaciones`, estados `creada`/`deshecha`) como comprobante de reintentos, también purgada; `series_id` no es clave foránea | migración 0018, `AltaOperacion` |
| La procedencia de una vinculación vive en `files.metadata.vinculo` (`operacion_id`, `fecha`, `serie_id`, `numero`, `formato`, `issue_creado`, `previo.{match_status,review_motivo}`), escrita **por fusión JSONB** | `services/vinculacion.py::_vincular_archivo` |
| **Nadie fuera de `vinculacion.py` lee `metadata.vinculo`**, y los demás escritores de `File.metadata_` **fusionan** (`{**(file.metadata_ or {}), …}` o `||`); ninguno la sustituye entera | `grep` en `src/` (tagger, importer, review, asignación) |
| «Pendiente» = `issue_id IS NULL` **y** `review_dismissed` falso **y** `metadata.match_status = 'unsorted'` | `services/review.py::_condiciones_pendientes` |
| La vinculación **no** guarda el `metadata_source` previo (solo pone `'manual'`) | `_vincular_archivo` |

## Opciones para el comprobante

| | A. Tabla nueva (`desvinculacion_operaciones`) | B. Reutilizar `vinculacion_operaciones` (solo `INSERT`) | **C. En el propio archivo** (`files.metadata`) |
|---|---|---|---|
| Migración | Sí (0021) + modelo + purga + pruebas de migración | No | **No** |
| Atomicidad con el cambio | Misma transacción | Misma transacción | **Misma fila, misma transacción** |
| Acoplamiento | Simétrico a 0018/0019 | Mezcla «informe de vinculación» y «de deshacer» en una tabla con `resultado` de forma fija y `leer_resultado` que da por hecho `archivos[]` | Ninguno con otras tablas |
| Historial duradero (criterio 7) | **No**: se purga a las 24 h; haría falta además guardarlo en el archivo | Ídem | **Sí**: es lo mismo que el comprobante |
| Operación sobre varios archivos | Sí | Sí | **No** (v1 es de **un** archivo; un lote sería otro contrato) |
| Si se borra la fila del archivo | El comprobante sobrevive (sin sentido: no hay nada que reintentar) | Ídem | Se pierde con él (aceptable: el reintento recibe «archivo ya no existe») |
| Coste | Alto (≈ +2 pts) | Medio | **Bajo** |

## Decisión propuesta

**Opción C: sin tabla nueva, sin migración.** El deshacer deja el comprobante y el historial **en `files.metadata`**, en la misma fila y la misma transacción que el cambio:

1. Se quita `metadata.vinculo` (el archivo ya no está vinculado) y se **añade** a `metadata.vinculo_historial` (array, solo `append`) una entrada con **la procedencia anterior íntegra** más
   `deshecho: {operacion_id, fecha}`. Nada se pierde: ni la serie y número, ni `issue_creado`, ni `previo`.
2. El **comprobante de idempotencia** es esa entrada: repetir la operación (mismo `operacion_id`) **reconoce** la entrada y devuelve el mismo resultado sin escribir nada; un fallo incierto se
   resuelve **leyendo la fila** (`issue_id` nulo + entrada con ese `operacion_id`).
3. Todas las escrituras son **fusión JSONB** (`||` / `-`), nunca sustitución del objeto (los demás escritores de `metadata` ya fusionan).
4. Una **vinculación posterior** crea un `vinculo` nuevo; las entradas de `vinculo_historial` no se tocan. La cadena «vinculado a X → deshecho → vinculado a Y» queda reconstruible.

**Límites aceptados:** v1 es de un archivo; si algún día hay lotes (BL-R1 los excluye) o M5 necesita un registro a nivel de operación, se abrirá otra decisión y una migración con su propio ADR. El historial crece
una entrada por acción humana (despreciable); no se pone tope en v1 (**sub-decisión abierta** si el revisor lo pide).

## Lo que esta decisión NO resuelve (se plantea aparte en el contrato)

- Qué `metadata_source` deja el archivo tras deshacer (**D8**), porque hoy no se guarda el previo.
- Qué vínculos pueden deshacerse en v1 (**D9**): solo los de «vincular en su sitio» (tienen procedencia) o también los de «organizar» (V6a) y los automáticos del importador.
- Dónde entra la persona (**D10**): hoy **no existe** una ficha de archivo ni la ficha de la serie lista sus archivos.

## Consecuencias

- Sin migración: BL-R1 no toca el esquema ni exige despliegue de base de datos.
- El historial es **datos del usuario en `files.metadata`**: lo copian los backups de PostgreSQL como cualquier otro dato del archivo.
- Reversible: pasar a una tabla (A) más tarde es solo añadirla y copiar `vinculo_historial`; no se pierde nada.

## Enmienda: D9 revisada (2026-10-23)

**Qué se decidió el 2026-10-20 (D9, opción a):** deshacer solo los vínculos de «vincular en su sitio» (los que llevan `metadata.vinculo`); el resto salía sin botón y con una explicación.

**Qué se decide ahora (PO, a la vista de la ficha de serie con 10 archivos «En el disco» de los que unos tenían botón y otros no):** se deshace **cualquier** archivo vinculado, **conste o no cómo se vinculó** (opción c de D9). Para quien colecciona, el origen del vínculo es un detalle interno; que dos archivos de la misma serie se comporten distinto parecía un fallo. Un vínculo equivocado del importador o hecho uno a uno desde «Por revisar» es justo el que más se quiere corregir.

**Qué cambia en el mecanismo (sin migración, sin tabla nueva):**
- La vista previa ya no bloquea con `sin_procedencia` (el código desaparece). Solo bloquean `no_vinculado` y `en_curso`. La respuesta añade `procedencia` (`registrada` | `desconocida`) y `aviso_procedencia`.
- Sin `metadata.vinculo` no hay `operacion_id` que firmar: el token firma el **UUID nulo** (`SIN_PROCEDENCIA`); versión 1 y tamaño fijo intactos, los tokens ya emitidos valen. Un `vinculo` **mal formado o de otra serie** cuenta como procedencia desconocida.
- Lo que se firma y se vuelve a comprobar con las filas bloqueadas es el **estado actual**: `issue_id`, huella `(ruta, tamaño, hash)`, la serie del número y que la procedencia sea la vista (registrada con su `operacion_id`, o ausente). Si cambia cualquier cosa (también si aparece una procedencia que no había) → `cambio_desde_la_vista_previa`.
- El comprobante sigue siendo una entrada de `vinculo_historial`. Sin procedencia es `{procedencia: "desconocida", serie_id, issue_id, numero, formato, previo: {match_status, metadata_source}, vinculo_no_valido?, deshecho: {operacion_id, fecha}}`: queda dicho **qué había** aunque no hubiera procedencia. D8: `metadata_source` vuelve a `NULL` (no consta lo anterior); el valor que tenía queda en `previo`.
- `en_curso` (asignación V6a viva) **sigue bloqueando**. Un archivo que movió V6a se puede desvincular pero **no se devuelve a su carpeta anterior** (como ya decía D9).

**Riesgo que se abrió y cómo se acotó.** Un vínculo **automático** desvinculado podría volver a vincularse solo. El importador y el adoptador solo crean filas para contenido **nuevo**: con el mismo contenido y el fichero presente, la fila ya registrada cuenta como copia presente y el archivo se descarta como duplicado (`_triage_and_match` → `duplicate_of`); no hay otro camino que ponga `File.issue_id` fuera de la vinculación, la asignación y la revisión manual. Una prueba con Postgres real lo fija (`test_el_importador_no_lo_vuelve_a_vincular…`).

**No cambia:** una sola operación por archivo, sin lotes; el número creado por la vinculación se conserva (D1); el fichero no se toca; nada vuelve a vincularse solo.
