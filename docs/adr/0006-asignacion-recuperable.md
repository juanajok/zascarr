# ADR 0006: Asignación de archivos recuperable (mover sin perder la coherencia)

## Estado

**Propuesto** — 2026-10-03. El **contrato** lo fijó la revisión del 2026-10-03 (ver «Decisión»); este ADR
lo escribe, lo apoya en un prototipo de un archivo y en mediciones, y deja explícito qué **no** está
demostrado. Se acepta cuando se revise esa evidencia. Origen: criterio 1 de V6a (`docs/BACKLOG.md`) y la
auditoría `docs/design/auditoria-mover-y-sesion.md`. Ficha de benchmarking:
`docs/design/benchmark-V6a-asignacion.md`.

## Contexto

`ReviewService.assign_to_series` mueve el fichero y deja el `commit` a `get_db`, que se ejecuta **después de
enviar la respuesta**. Medido (auditoría): un fallo entre mover y confirmar deja el fichero movido y la BD
revertida por cuatro caminos (servicio, `commit`, respuesta, muerte del proceso); el cliente puede recibir
`200` con el `commit` fallido; y **no hay reconciliación automática** (el importador marca la fila como
«desaparecida» y nadie registra el destino).

Las opciones que parecían bastar se descartaron con argumentos concretos:

- **Confirmar justo después de mover (A)** elimina el éxito previo al `commit` y reduce la ventana, pero no
  la incoherencia si el proceso muere entre mover y confirmar.
- **Reintento idempotente (B)** necesita conocer *inequívocamente* el destino. El destino **canónico** no
  es el **efectivo** si estaba ocupado y se eligió un sufijo; y tras revertir la transacción pueden faltar
  en la BD los datos de la asignación pedida (serie, número, formato).
- **Hardlinks (C)** no funcionan entre sistemas de ficheros distintos ni en todos los montajes, y dos
  nombres enlazados **comparten contenido**: una escritura del etiquetador sobre uno altera el otro.
- Además hay un caso que ninguna cubría: el **`commit` de resultado desconocido** (la conexión se pierde
  tras enviar `COMMIT`). La aplicación no puede asumir `rollback` ni compensar borrando el destino.

## Decisión

El flujo por archivo, en este orden. **Nunca** se retira el origen antes de confirmar, **nunca** se borra el
destino por un fallo de resultado desconocido, y solo se informa `asignado` tras confirmar.

1. **Preparar una operación recuperable** (y confirmarla): `File.id`, origen (con tamaño y `mtime_ns`),
   **destino efectivo** (con sufijo si el canónico está ocupado), serie, número, formato y hash esperado.
   Reclamar el archivo y **reservar el destino** son la misma inserción atómica (índices únicos parciales).
2. **Materializar el destino sin retirar el origen:** copia a un temporal en la carpeta del destino,
   `fsync`, **verificación** (tamaño y `sha256`) y publicación por `rename` atómico.
3. **Confirmar en una transacción:** archivo, `Issue`, alias y la propia operación. Si el `commit` falla con
   resultado desconocido, **se consulta la BD con otra sesión**; si ni eso es posible, se conserva todo.
4. **Retirar el origen** como limpieza posterior, solo si la asignación está confirmada y el origen sigue
   siendo el preparado (tamaño y `mtime_ns`).
5. **Reconciliar:** repetir la operación o reiniciar continúa o reconoce lo ya hecho, **consultando solo la
   tabla de operaciones vivas** (índice parcial), sin escanear la biblioteca.

Resultados (conjunto cerrado, con motivo en español): `asignado`, `asignado_limpieza_pendiente` (la
asignación confirmada **no** pasa a fallida si falla el borrado del origen), `ya_asignado`, `ya_en_curso`,
`pendiente` (no se pudo confirmar; se reintenta), `pendiente_de_comprobar` (no se pudo ni preguntar a la BD),
`colision_edicion`, `no_encontrado`, `error`.

La ejecución no se cancela con el cliente (`asyncio.shield`) y se serializa por operación con un **candado
consultivo de Postgres**: una operación huérfana (su proceso murió) se distingue de una en curso sin
plazos ni reloj, porque Postgres libera el candado al caer la conexión.

**Los hardlinks quedan como optimización posterior, no como requisito de seguridad.** Antes de usarlos hay
que medir *desde el contenedor y sobre las rutas reales* y contemplar escrituras concurrentes del etiquetador.

### Dónde vive la operación: `File.metadata_` frente a una tabla propia

Se evaluó primero `File.metadata_` (JSONB existente, con índice GIN `idx_files_metadata`). **Se descarta**,
con evidencia:

| Criterio | `File.metadata_` | Tabla `asignacion_operaciones` |
|---|---|---|
| Coste de consultar «operaciones pendientes» | **bueno**: 5,2 ms con 50 000 filas (el GIN ya existe). *No* es el motivo del descarte. | 0,5 ms con 20 000 cerradas (índice parcial) |
| **Integridad ante otros escritores** | **No acreditable.** **Cinco** puntos reescriben la columna **entera** a partir de una lectura anterior (`tagger.py:334` y `:525`, `review.py:164`, `pendientes.py:115`, `importer.py:181`), y otros dos la crean (`importer.py:437`, `library_adopter.py:205`). Medido: un escritor con lectura obsoleta **borra el marcador** (`TestMetadataNoBasta`). Solo se arreglaría cambiando *todos* los escritores, presentes y futuros. | Ningún otro código la toca (prueba gemela) |
| **Reservar un destino único** | No hay forma de imponer «un destino, una operación viva» sin un índice único sobre una expresión: **es una migración igualmente**. | Índice único parcial por destino y por archivo |
| Reclamar el archivo (concurrencia) | `UPDATE … WHERE NOT metadata ? …` serviría | índice único parcial por archivo |

**Conclusión: la persistencia necesaria es esquema.** Se separa una historia con migración (`0017`), como se
acordó; V6a **no** se fusiona rebajando la garantía. El `DDL` propuesto está en `tests/prototipo_asignacion.py`.

## Lo demostrado (prototipo de un archivo, Postgres y ficheros reales)

`tests/prototipo_asignacion.py` + `tests/test_prototipo_asignacion_pg.py` (21 pruebas; cada defensa se
comprobó **por mutación**: quitar la verificación del hash, el escudo, el candado, la comprobación del
origen, la consulta tras un `commit` desconocido o la distinción «asignado con limpieza pendiente» hace
fallar exactamente la prueba que la protege).

| Requisito de la revisión | Prueba |
|---|---|
| Muerte tras preparar / tras copiar / tras publicar el destino, antes del `commit` | `TestMuerteDelProceso::test_antes_de_confirmar[…]` (subproceso real, `os._exit(137)`) |
| Muerte después del `commit`, antes de limpiar | `…::test_despues_de_confirmar_antes_de_limpiar` |
| Muerte durante la copia (temporal parcial) | `…::test_la_copia_a_medias_se_descarta_y_se_rehace` |
| `commit` confirmado cuya respuesta se pierde | `TestCommitDeResultadoDesconocido::test_commit_confirmado_cuya_respuesta_se_pierde` → `asignado`, nada borrado |
| `commit` no aplicado | `…::test_commit_no_aplicado_conserva_los_ficheros_y_se_reintenta` |
| Ni se puede comprobar | `…::test_si_ni_se_puede_comprobar_se_conserva_todo` → `pendiente_de_comprobar` |
| Destino ocupado, nombre con sufijo, recuperación respeta el **efectivo** | `TestDestinoOcupado` (dos pruebas) |
| Dos solicitudes del mismo archivo **con el `Issue` ya existente** | `TestSolicitudesSolapadas::test_dos_solicitudes_…` → `ya_en_curso` y `asignado`, un solo fichero |
| Una operación huérfana la continúa quien reintenta | `…::test_la_segunda_encuentra_una_operacion_huerfana_y_la_continua` |
| Fallo al borrar el origen | `TestFalloAlBorrarElOrigen` (no pasa a fallida; no borra un origen que cambió) |
| Reinicio que reconcilia sin escanear la biblioteca | `…::test_la_reconciliacion_no_recorre_la_biblioteca` (`rglob`, `iterdir` y `os.walk` prohibidos) |
| Cancelación del cliente mientras sigue el hilo de copia | `TestCancelacionDelCliente` |
| Copia corrupta | `TestCopiaVerificada` → no se publica, el origen intacto |

## Coste medido

`scripts/medicion/medir_asignacion.py`; resultados crudos en `docs/design/medicion-asignacion-2026-10-03.json`.
**Máquina de desarrollo** (Intel i5-8365U, 8 hilos, **NVMe con ntfs3**, caché caliente), no la Pi:

| Tamaño | rename (hoy) | copia + fsync + sha256 | solo sha256 | espacio temporal extra |
|---|---|---|---|---|
| 10 MB | ~0 s | 0,05 s | 0,04 s | 10 MB |
| 100 MB | ~0 s | 0,50 s | 0,38 s | 100 MB |
| 200 MB | ~0 s | 1,01 s | 0,75 s | 200 MB |

- **El hash domina** (~265 MB/s aquí): la copia es el 15 % y la verificación el 75 %. En una Pi sin
  extensiones criptográficas será peor; **no medido**.
- Asignar un archivo de 100 MB de extremo a extremo: **1,0-1,3 s** (frente a ~0 con `rename`).
- **Recuperar** una operación huérfana de 100 MB: **0,9 s**; listar operaciones vivas con 20 000 cerradas:
  **0,5 ms** (índice parcial).
- Espacio temporal: **1× el tamaño del archivo en curso** (el lote es secuencial).
- **Consecuencia para el lote:** 50 archivos de 100 MB serían ~1 min aquí, y minutos en una Pi o por CIFS:
  muy probablemente **no cabe en una petición**. El límite del lote debe fijarse **por bytes, no por número
  de archivos**, y la ejecución en segundo plano es **otra historia** (V6a criterio 4). Se fija tras medir en
  el hardware y los montajes reales.

## Lo que NO está demostrado

- **Corte eléctrico.** `os._exit` mide la muerte del **proceso**, no la durabilidad del sistema de ficheros.
  El prototipo hace `fsync` del fichero y, en mejor esfuerzo, del directorio; **no se ha probado** que un
  `rename` o una copia sobrevivan a un apagón (ni en ext4, ni NTFS, ni CIFS).
- **Montajes reales:** NVMe/ntfs3 local es lo único medido. Sin medir: CIFS, exFAT, ext4 en SD/USB y la Pi.
  La semántica de `fsync` y `rename` sobre CIFS es la gran incógnita.
- **Cancelación con uvicorn real:** probada a nivel de tarea (`asyncio`), no con una desconexión HTTP real.
- **Hardlinks:** sin medir ni probar (decididos como optimización posterior).
- **Importador:** un `commit` para todo `scan_and_import()` (`main.py:35`); el mismo riesgo a mayor escala,
  fuera de este ADR (su propia historia).
- **Arranque:** dónde y cuándo llamar a `reconciliar()` (tarea de fondo tras el *lifespan*, para no bloquear
  el healthcheck) está por diseñar e implementar.
- **Candado consultivo** retiene una conexión durante toda la copia; con el *pool* de la Pi (tamaño por
  confirmar) habrá que medir el efecto con varias operaciones.

## Consecuencias

- **Historias nuevas, en este orden:** (1) migración `0017` con `asignacion_operaciones`; (2) el servicio de
  un archivo, conectado a la asignación individual **conservando su contrato** (B13/B15); (3) el lote con
  límite por bytes; (4) ejecución en segundo plano si la medición lo exige; (5) el importador.
- La asignación individual actual **no cambia** hasta (2). Las pruebas de caracterización de la auditoría
  cambiarán entonces con el comportamiento, no se silenciarán.
- Cada asignación pasa de **0 ms a ~10 ms/MB** de E/S (cuanto mayor el archivo, más se nota); a cambio, el
  fallo en cualquier punto es recuperable y la respuesta ya no miente.
- Una tabla nueva y dos índices parciales: coste de RAM despreciable; una migración que no se reescribe una
  vez aplicada (`CLAUDE.md` §7).

## Alternativas descartadas

- **A + B solos:** no cierran la muerte entre mover y confirmar ni el destino efectivo.
- **`File.metadata_`:** ver la tabla: no acredita integridad (escritores que reescriben la columna entera) ni
  unicidad del destino.
- **Escanear la biblioteca para reconciliar (D):** recorrido completo en la Pi; se quiere evitar.
- **Hardlinks como requisito:** no funcionan entre sistemas de ficheros ni en todos los montajes.
