# ADR 0007: Vincular en su sitio y organizar son operaciones distintas

- Estado: **Aceptado** · 2026-10-07 (aprobado y fusionado en #91; el diseño gobierna las rebanadas siguientes y **sigue sin implementarse**)
- Relacionado: ADR-0006 (asignación recuperable), ADR-0003 (identidad editorial), `docs/design/rebanada-2-elegir-serie-y-vincular.md`, `docs/design/ficha-propuestas-desde-carpetas.md`
- Decisión de producto de la revisión (2026-10-07): *para archivos adoptados, clasificar no puede implicar reorganizar la biblioteca.*

## Contexto

Registrar una biblioteca existente promete **no mover nada** (`LibraryAdopter`: «nunca se mueve; `file_path` es la ruta real donde el coleccionista ya tenía el archivo»). Hasta hoy, **clasificar** un archivo (darle serie y número) y **moverlo** eran la misma operación. Hechos verificados en el código de `main`:

| Hecho | Dónde |
|---|---|
| `AsignacionService.asignar` calcula el destino con `build_library_path` (`{tradición}/{Serie (Año)}/{Serie #NNN.ext}`), **copia, verifica, publica y retira el origen** | `services/asignacion.py::_preparar`, `_confirmar` |
| El botón «Sí, es esta» de «Por revisar» llama a ese servicio: **mueve y renombra** cualquier archivo, también uno registrado «en su sitio» | `web/pendientes.py`, `POST /ui/pendientes/{id}/asignar` |
| Hay un segundo camino que también mueve, hoy solo ejercitado por pruebas | `services/review.py::ReviewService.assign_to_series` |
| `_preparar` devuelve `ya_asignado` si `file.issue_id == issue.id` | `services/asignacion.py:330` |
| Lo que escribe `_confirmar` en la BD: `Issue` (si falta, con `locked_fields=["series_id","issue_number"]` y el `format` del nombre), `file.issue_id`, **`file.file_path` y `file.file_name`**, `file.metadata_source = 'manual'`, y el alias si se pidió | `services/asignacion.py::_confirmar` |
| La bandera `metadata_["adopted"] = True` solo la pone `LibraryAdopter` al **crear** una fila; un reenlace (`_reenlazar_fila`, `services/importer.py:200`) no la lleva | `services/library_adopter.py:450` |
| Nada en la aplicación recalcula la ruta de un archivo ya registrado a partir de su serie: `build_library_path` solo se usa al crear (importer) o al asignar | `grep build_library_path` |

La ficha de propuestas daba por buena la premisa «asignar mueve y renombra (ADR 0006), así que se muestra el destino». Era **incompleta**: para un archivo adoptado, mover es una reorganización de la biblioteca de la persona que **nadie le ha pedido** y que cambia las rutas que ven Kavita u otros lectores.

## Decisión

1. **Son dos operaciones, con dos nombres y dos consentimientos:**
   - **Vincular en su sitio** (`vincular`): identifica la serie y el número de un archivo **conservando su nombre y su ruta**. No toca el fichero.
   - **Organizar** (`organizar`): mueve y renombra a la ruta canónica, **con vista previa de rutas y consentimiento específico**. Es lo que hace hoy `AsignacionService`.
2. **El camino previsto para los archivos adoptados es vincular.** Organizar nunca es el efecto lateral de clasificar ni el valor por defecto.
3. **Qué es «adoptado».** No se infiere de una bandera frágil (ver tabla): se decide por la **ubicación**. Un archivo bajo `{biblioteca}/_Unsorted/` es **material en tránsito** del importador (donde organizar es lo natural y no cambia); **cualquier otro** se trata como adoptado y se propone `vincular`. La pantalla muestra siempre la ruta actual.
4. **No se modifica `AsignacionService`** para esto. «Organizar» sigue siendo ese servicio, sin cambios, para archivos **no vinculados**.

## Contrato de «vincular» (diseño; sin implementar)

**Por archivo, antes de escribir** (y **otra vez dentro de la transacción**):
- `issue_id IS NULL`, o ya vinculado a **ese mismo** `Issue` → resultado `ya_vinculado` (idempotente, no es un error).
- Sin operación de asignación **viva** para ese archivo (`asignacion_operaciones`) → si la hay, `en_curso`.
- **El origen existe** (`stat`): un registro cuyo fichero no está **no se vincula** (`origen_no_encontrado`, «registro pendiente de verificar»).
- Número no vacío y **no repetido dentro del lote**; sin colisión de edición (B15: mismo número con otro `Issue.format`).
- La huella `(tamaño, mtime_ns)` coincide con la de la vista previa (`cambio_desde_la_vista_previa` si no).

**Efectos, en UNA transacción** — los mismos efectos de BD que `_confirmar` **menos la ruta**:
- Crear el `Issue` si falta (`locked_fields=["series_id","issue_number"]`, `format` deducido del nombre).
- `file.issue_id = issue.id`; `file.metadata_source = 'manual'`.
- **`file.file_path` y `file.file_name` no cambian.**
- Alias: **solo** si la persona lo pidió expresamente (D7).
- Procedencia en `File.metadata_["vinculo"]` (esquema **v1**): `{"version": 1, "operacion_id", "fecha", "serie_id", "numero", "formato", "issue_creado": bool, "previo": {"match_status", "review_motivo"}}`. **No** se guarda el token ni ningún identificador de sesión.

**Atomicidad y concurrencia.** El lote (≤ N archivos, hipótesis 100) se hace en **una sola transacción**: bloqueo `SELECT … FOR UPDATE` de las filas `files` **en orden de id** (evita interbloqueos), reverificación de las precondiciones ya con el bloqueo, y confirmación **de todo o nada**. Los fallos **por archivo** se deciden **antes** del commit y se informan; lo aceptado se confirma junto.
Como **no hay ficheros de por medio**, no existe estado intermedio que recuperar: **no hace falta segundo plano, ni progreso, ni reconciliación**. La petición responde con el resultado completo.
Si una operación `organizar` naciera después sobre el mismo archivo, su `_confirmar` (`with_for_update` sobre la misma fila) espera al commit y **su resultado prevalece** (acción explícita y posterior).

**Idempotencia.** Cada confirmación lleva un `operacion_id` (dentro del token firmado, ver la ficha). Repetirla con el mismo token **no ejecuta otro lote**: devuelve el resultado reconstruido (los archivos con ese `operacion_id` en `metadata_["vinculo"]` están vinculados; el resto del conjunto que lleva el token, no). Si el token ya caducó, se puede saber **qué quedó vinculado** pero **no qué se pretendía**: se dice así.

**Deshacer** (contrato futuro): `desvincular(operacion_id | file_id)` pone `issue_id = NULL`, restaura `previo` y borra el `Issue` **solo si** `issue_creado`, no tiene otros archivos y `enrichment_attempted_at IS NULL`. **No mueve nada.**

**Lo que vincular nunca hace:** mover, copiar, renombrar ni borrar ficheros; leer su contenido (**sin hash**); usar la red.

## Contrato de «organizar»

- **Para archivos no vinculados:** exactamente lo de hoy (ADR 0006), sin cambios.
- **Para archivos ya vinculados** el servicio actual responde `ya_asignado`: no se pueden organizar **después** de vincularlos. Hace falta una operación nueva —**«reubicar»**: el mismo mecanismo recuperable, sin crear `Issue`, cuyo `_confirmar` solo cambia la ruta—. **No se diseña aquí.** Antes de implementarla hay que decidir si es una ampliación del ADR 0006 o un ADR propio.
- **Lotes de organizar:** un informe completo **tras un reinicio** exige una relación durable lote ↔ operaciones (por ejemplo `lote_id` en `asignacion_operaciones`, con migración). Mientras no exista, **no se promete**: solo consta lo que consta por operación.
- **Consentimiento específico:** texto propio («Se moverán *N* archivos de su carpeta actual a la de la biblioteca»), vista previa de las rutas de destino y confirmación **separada**. Límites iniciales (hipótesis, sin validar): 100 archivos y 4 GB.

## Consecuencias

- **Bibliotecas con dos disposiciones.** Los adoptados conservan sus carpetas; las descargas nuevas que procesa el importador siguen entrando en la ruta canónica. Una serie puede quedar repartida entre su carpeta original y la canónica. No es un error; hay que **decirlo**, no ocultarlo. Kavita lee por carpetas, así que puede mostrarlo como dos series. B20 (exportación a un árbol limpio **sin tocar el origen**) sigue aparcado y es el sitio natural para ordenarlo.
- **El botón de «Por revisar» hoy organiza** para cualquier archivo, también adoptados. Eso contradice esta decisión: debe cambiar (modos y textos) **en la PR que implemente vincular**. **Hasta entonces es el comportamiento vigente y hay que advertirlo.** Los dos caminos que mueven hoy son `AsignacionService` y el heredado `ReviewService.assign_to_series`.
- **Vincular es reversible sin tocar disco**; organizar no se deshace automáticamente.
- La serie **no tiene carpeta propia** en el modelo: portada, auditoría y demás leen `file_path`, así que vincular no rompe nada que dependa de la ruta (comprobado: ninguna otra pieza la recalcula).

## Alternativas descartadas

- **Una sola operación con una casilla «mover».** La opción por defecto decide por la persona, y «clasificar» seguiría pareciendo inocuo.
- **Usar `AsignacionService` con destino = origen.** El servicio asume copiar a **otra** ruta (temporales, `renameat2` sin reemplazo, retirada del origen): forzarlo sería un cambio apresurado sobre el código más delicado del proyecto.
- **Crear enlaces simbólicos o duros en la ruta canónica.** Introduce un segundo árbol que nadie pidió; es el terreno de B20.
- **Inferir «adoptado» de `metadata_["adopted"]`.** Solo existe en las filas creadas por `LibraryAdopter`; los reenlaces y los archivos de registros anteriores no la llevan.

## Pruebas que deben existir antes de implementar vincular

Postgres real y ficheros reales en un directorio temporal:
1. **Nombre y ruta intactos** tras vincular (`file_path`, `file_name`, contenido y `mtime` del fichero).
2. **Una transacción:** si falla un archivo después de decidir el resto (p. ej. una restricción única), **no queda ninguno vinculado**.
3. **`origen_no_encontrado`** no se vincula.
4. **Colisión de edición** (B15) y **número repetido en el lote**.
5. **`ya_vinculado`** es idempotente; el mismo `operacion_id` no ejecuta dos veces y devuelve el mismo resultado.
6. **Concurrencia:** dos confirmaciones solapadas sobre los mismos archivos; vincular a la vez que `organizar` (gana el segundo, sin fila rota).
7. **Operación viva** en el archivo ⇒ `en_curso`, sin escribir.
8. **Sin ficheros ni red ni hash:** con `stat` como único acceso a disco.
9. **Procedencia** guardada con el esquema v1 y **sin token ni sesión**.
10. **Deshacer** restaura el estado previo y respeta `issue_creado`.
11. **Un archivo bajo `_Unsorted/`** propone `organizar`; el resto, `vincular`.
12. **Regresión de `organizar`:** `tests/test_asignacion_*` no cambian y siguen pasando.

## Preguntas abiertas

- **Q1.** ¿Se admite vincular un archivo cuyo origen **no** se pudo comprobar por un fallo de lectura del disco (disco desmontado)? *Recomendación:* no; es `origen_no_encontrado` con el motivo. **Resuelta en 2c:** no se admite, y con un estado propio `origen_no_verificable` (permiso, error de lectura, biblioteca no accesible, no es un archivo), distinto de `origen_no_encontrado`; el texto no afirma que el archivo haya desaparecido.
- **Q2.** «Reubicar» un archivo ya vinculado: ¿ampliación del ADR 0006 o ADR propio? *Recomendación:* ADR propio.
- **Q3.** ¿El botón único de «Por revisar» pasa a dos botones («Vincular» y «Organizar») o a un selector de modo? *Recomendación:* dos acciones separadas y con textos distintos; **ninguna** por defecto.
