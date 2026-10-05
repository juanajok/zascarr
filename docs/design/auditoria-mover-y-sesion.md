# Auditoría V6a: mover un fichero con la sesión de BD viva

> Criterio 1 de V6a: **antes de escribir el lote**, enumerar cada punto de fallo entre `safe_move_async` y
> el `commit`, qué estado deja en disco y en BD, y cómo se reconcilia. Cierra la anotación «pendiente de
> auditar» de `CLAUDE.md` §3.1.2. **No cambia ninguna lógica de producción**; las pruebas de
> `tests/test_asignacion_fronteras_pg.py` **caracterizan lo que ocurre hoy** (algunas fijan un
> comportamiento indeseable a propósito, para que el lote lo cambie de forma consciente).

## Método

Endpoint real (`POST /ui/pendientes/{id}/asignar`) con el `get_db` real, **Postgres 15.19 real** y
**ficheros reales** en un directorio temporal; un fallo inyectado por prueba en un punto distinto. El
«crash» es un subproceso que sale con `os._exit(137)` (sin `rollback` ni `finally`). Python 3.14.4,
FastAPI 0.142.2, SQLAlchemy 2.1.1, asyncpg 0.31.0. **Alcance:** `ReviewService.assign_to_series`
(medido). El importador se describe por lectura de código, **no se ha experimentado** (ver §«Fuera de
alcance»).

## La secuencia actual

```
POST /asignar ─ Depends(get_db) abre sesión
  1  SELECT File, Series                         (transacción abierta)
  2  SELECT Issue  → colisión de edición (B15)?  → 409 (commit explícito del motivo; sin mover nada)
  3  INSERT Issue + flush                        (sin commit)
  4  safe_move_async(origen → destino)           ← EL DISCO CAMBIA AQUÍ
  5  UPDATE File.file_path/issue_id + flush      (sin commit)
  6  _learn_alias (SELECT + INSERT/UPDATE + flush)
  7  return HTMLResponse("")                     ← la respuesta se envía
  8  get_db: session.commit()                    ← el COMMIT ocurre aquí, DESPUÉS de la respuesta
```

Entre el paso 4 (irreversible para el disco) y el 8 (único `commit`) hay **cuatro operaciones que pueden
fallar** y una respuesta ya enviada. Ninguna compensa el movimiento.

## Puntos de fallo medidos

| # | Fallo inyectado | Cliente | Disco | BD | ¿Reconcilia algo hoy? |
|---|---|---|---|---|---|
| 0 | ninguno | 200 | origen movido a su destino canónico | fila al destino, `Issue` y alias | — |
| 1 | `safe_move` falla **antes** de mover (destino de solo lectura) | 500 | **intacto** | **intacta** (el `Issue` del paso 3 se revierte) | sí: no hay nada que reconciliar |
| 2 | falla `_learn_alias` **después** de mover y actualizar la fila | 500 | **movido** | **revertida** (fila al origen, sin `Issue` ni alias) | **no** (ver §Reconciliación) |
| 3 | falla el `commit` de `get_db` | **200** (¡éxito!) | **movido** | **revertida** | **no** |
| 4 | falla algo tras el servicio y antes de responder (construir la respuesta) | 500 | **movido** | **revertida** | **no** |
| 5 | el proceso muere entre mover y confirmar (`os._exit(137)`: muerte del **proceso**) | sin respuesta | **movido** | **revertida** (la conexión cae) | **no** |
| 6 | cruce de discos: falla borrar el original tras colocar el destino | 500 | **dos copias** | **intacta** | **no** (el duplicado aparecerá en Duplicados) |
| 7 | dos envíos del mismo archivo a la vez, **cuando el `Issue` aún no existe** | uno 200, otro 500 | **un** fichero | **un** `Issue`, fila al destino | sí, por el índice único de `Issue` (solo en este escenario) |

**Hallazgo 3, el más importante:** en esta versión de FastAPI el cierre de una dependencia con `yield`
(`get_db`: `session.commit()`) se ejecuta **después de enviar la respuesta**. El cliente recibe un `200`
y la tarjeta desaparece de Pendientes **aunque el `commit` falle**, con el fichero ya movido. Medido con
ASGI de prueba; **no se ha repetido con uvicorn real** (la semántica de ASGI es la misma, pero no lo he
comprobado).

**Hallazgo 7 (parcial):** B espera al `commit` de A (el índice único de `Issue` se lo impone), después
falla con `IntegrityError` y se revierte. No hay duplicado. La protección es **accidental** (depende del
índice) y **solo está probada para la creación simultánea del `Issue`**. **No** acredita que cualquier
solapamiento sea seguro: con el `Issue` ya existente no hay nada que serialice a los dos envíos
(pendiente de probar; ver el ADR).

**Qué mide `os._exit` y qué no:** la **muerte del proceso** (OOM, `kill -9`): la base de datos sigue viva y
el sistema de ficheros conserva lo escrito. **No** mide la durabilidad ante un **corte eléctrico**: ahí
puede perderse lo que el sistema operativo aún no volcó a disco (un `rename` o una copia sin `fsync`
pueden no sobrevivir), y el estado resultante puede ser distinto al de la tabla.

## Reconciliación: lo que existe hoy y lo que no

Desde el estado inconsistente de los casos 2-5 (fichero en `Comics/Serie/…#012.cbz`, fila apuntando a
`_Unsorted/…`):

- `Importer._detectar_desaparecidos` (B7) ve que la ruta de la fila **ya no existe** y la marca
  `is_missing`. A los ojos del coleccionista, **«lo borraste a mano»**, que es falso. Medido.
- El fichero movido **no tiene fila en la BD**: ninguna rutina lo registra. El importador solo escanea
  las carpetas de **entrada** (`transmission_download_dir`, `amule_incoming_dir`, `downloads_path`),
  **no** la biblioteca; `LibraryAdopter` corre una sola vez. Medido.
- **Sí hay una recuperación manual por hash**: si el fichero vuelve a una carpeta de entrada, el
  importador lo reconoce (la fila está `is_missing` y el hash coincide) y lo **reenlaza** («recuperado»).
  Medido. Pero exige que alguien lo devuelva a mano; el estado de arriba no avisa de nada.

**Conclusión: hoy no hay reconciliación automática del movimiento interrumpido.** Los casos 2-5 son
pérdida de coherencia silenciosa (no pérdida de datos: el fichero está íntegro en el destino).

## Qué exige el lote (V6a, criterio 5)

El lote asigna N archivos con `commit` corto por archivo. Con la secuencia actual, un fallo en el 3.º
dejaría los dos primeros bien y el tercero en alguno de los estados 2-6. Primera evaluación de opciones
(**superada por el ADR 0006**, que es el contrato elegido; se conserva como registro del razonamiento):

| Opción | Idea | Por qué sola no basta |
|---|---|---|
| **A. Confirmar justo después de mover** | El servicio hace `commit` él mismo tras el `flush`. | Elimina el éxito HTTP previo al `commit` y reduce la ventana, **pero no la incoherencia si el proceso muere entre mover y confirmar**. Necesaria igualmente (hallazgo 3). |
| **B. Reintento idempotente** | Si el origen no existe y el destino canónico sí, con el mismo hash: reenlazar. | Necesita conocer **inequívocamente el destino**. El destino *canónico* no es el *efectivo* si estaba ocupado y se eligió un nombre con sufijo; y tras revertir la transacción pueden faltar en la BD los datos de la asignación pedida (serie, número, formato). |
| **C. Enlace → commit → borrar origen** | `os.link`, `commit`, `unlink(origen)`. | Los *hardlinks* no funcionan entre sistemas de ficheros distintos ni en todos los montajes, y dos nombres enlazados **comparten contenido** (una escritura del etiquetador sobre uno altera el otro). Como optimización posterior, no como requisito de seguridad. |
| **D. Registrar por escaneo del destino** | Como Kapowarr: reconciliar escaneando. | Recorrido de toda la biblioteca, que se quiere evitar en la Pi. |

**Una afirmación retirada.** La primera versión de esta auditoría decía que «ninguna opción requiere
persistir nada nuevo». **Eso no está demostrado**: recuperar automáticamente tras un reinicio exige que la
identidad de la operación y su destino efectivo sobrevivan, y eso *es* persistencia nueva. Si cabe en
`File.metadata_` o exige esquema es lo que evalúa el ADR 0006, con evidencia.

**Caso que faltaba: `commit` de resultado desconocido.** Si la conexión se pierde después de enviar
`COMMIT` y antes de recibir su confirmación, la aplicación no sabe si se confirmó. No puede asumir
`rollback` ni compensar borrando el destino: tiene que conservar los ficheros y consultar la BD.

## Fuera de alcance (anotado, no medido)

- **Importador:** `main.py` hace **un único `commit` para todo `scan_and_import()`** (línea 35). Cada
  fichero se mueve (`safe_move_async`) y su fila se `flush`ea; un crash a mitad de un ciclo deja **N**
  ficheros movidos sin fila. El mecanismo es el de aquí, a escala mayor. Por lectura de código, no
  experimentado; merece su propia historia.
- **Cancelación del cliente** a mitad de un movimiento largo (copia entre discos de un CBZ grande): la
  copia corre en un hilo (`asyncio.to_thread`) que no se cancela. No medido.
- **`safe_move` entre discos** acepta como verificación el **tamaño**, no el contenido (decisión
  documentada de A3). No se revisa aquí.
- Rendimiento y tope del lote (criterio 4): requieren ficheros grandes en un disco real; pendiente.

## Pruebas que dejan esto fijado

`tests/test_asignacion_fronteras_pg.py` (10): camino feliz; fallo antes de mover; fallos tras mover por
cuatro caminos (servicio, `commit`, respuesta, muerte del proceso); cruce de discos; solapamiento; y las
dos reconciliaciones existentes. Se saltan sin `TEST_DATABASE_URL`; las ejecuta el job de Postgres de la CI.
**Cuando el lote cambie el comportamiento, estas pruebas deben cambiar con él**, no ser silenciadas.

> **Actualización (conexión del endpoint al servicio recuperable, ADR 0006).** Tal como se anunció, las pruebas
> de `tests/test_asignacion_fronteras_pg.py` se cambiaron a propósito: conservan las mismas fronteras y nombres
> («antes …») y ahora afirman el comportamiento nuevo —el original nunca se pierde, el éxito que ve el cliente ya
> está confirmado, el doble clic produce una sola asignación—. El texto de arriba describe el estado **anterior**
> y se conserva como registro. La frontera «muerte del proceso» la cubren los subprocesos de
> `tests/test_asignacion_servicio_pg.py`.
