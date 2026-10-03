# Ficha de benchmarking — V6a: asignación manual y orden «mover / confirmar»

> Procedimiento: `docs/design/benchmark-referencias.md`. Complementa `auditoria-mover-y-sesion.md`.

**Historia / problema observado.** `ReviewService.assign_to_series` mueve el fichero y deja el `commit` a
`get_db`, después de responder. Medido en la auditoría: el fallo en esa ventana deja el fichero movido y
la BD revertida, y el cliente puede haber recibido un `200`.

**Referencias consultadas** (ambas GPL-3.0; **solo como patrón, no se copia código**):

| Referencia | Versión | Ficheros leídos |
|---|---|---|
| Kapowarr | `main` @ `c191dda` | `backend/base/files.py` (`rename_file`), `backend/implementations/naming.py` (renombrado masivo), `backend/features/library_import.py`, `backend/internals/db_models.py` (`FilesDB.update_filepaths`) |
| Mylar3 | `master` @ `cdc94a4` | `mylar/PostProcessor.py` (operación de fichero, actualización de estado) |

**Cómo lo resuelve cada una (por lectura de código; no se ejecutaron).**
- **Kapowarr, renombrado masivo:** renombra **todos** los ficheros en disco en un bucle y **después** hace
  **una** llamada `FilesDB.update_filepaths(renames)` (`executemany`). Disco primero, BD después, **sin
  compensación**: un fallo a mitad deja la misma incoherencia que ZascArr, en lote.
- **Kapowarr, importar biblioteca:** hace `commit()` tras dar de alta el volumen, **mueve** los ficheros y
  llama a `scan_files(volume_id, filepath_filter=files)` para **registrarlos escaneando el destino**: la BD
  se reconcilia **desde el disco**, así que una interrupción se repara en el siguiente escaneo.
- **Mylar3:** la operación de fichero es **configurable** (`FILE_OPTS`: `copy` o `move`); tras ella
  comprueba `os.path.isfile(dst)` y solo entonces hace `myDB.upsert` del estado «Downloaded» (una escritura
  corta). Con `copy`, un fallo deja el original: **no destruye**.

**Supuestos de su modelo que NO valen en ZascArr.** Ambas son SQLite de un solo proceso con escritura
inmediata (sin la separación sesión/`commit` posterior a la respuesta de FastAPI); ninguna distingue
«respuesta enviada» de «datos confirmados»; ninguna tiene el estado de pendiente del coleccionista
(`_Unsorted`) ni la colisión de ediciones (B15).

**Adoptar / adaptar / descartar.**
- **Adaptar (Kapowarr, importar):** reconciliar por **escaneo del destino** → opción D de la auditoría.
- **Adaptar (Mylar3):** operación **no destructiva primero** (copiar/enlazar) y comprobar el destino antes
  de escribir en la BD → opción C (enlace → commit → borrar origen).
- **Descartar:** «disco primero, BD después, sin compensar» (Kapowarr, renombrado): es exactamente el
  riesgo medido.
- **No inferido:** no se sabe, sin ejecutarlas, cómo se comportan ante un fallo real; la tabla describe su
  **diseño**, no una garantía. «No encontré compensación» no equivale a «no existe».

**Invariantes de ZascArr.** No mentir (no responder `200` sin haber confirmado), no borrar (el original solo
desaparece cuando el destino está confirmado), commit corto por archivo, coste en la Pi (hashear un CBZ
grande solo en la rama de recuperación).

**Casos de prueba.** `tests/test_asignacion_fronteras_pg.py` (caracterización del estado actual).

**Decisión final.** Pendiente: elegir entre las opciones A-D de la auditoría con el equipo; es una decisión
de arquitectura (el orden mover/confirmar) y, al decidirse, irá a un **ADR**.
