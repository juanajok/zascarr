# ADR 0006: Asignación de archivos recuperable (mover sin perder la coherencia)

## Estado

**Aceptado** — 2026-10-05 (propuesto el 2026-10-03). Se acepta como **decisión de arquitectura**: el
contrato de «Decisión», la tabla propia en lugar de `File.metadata_` y el orden de historias de
«Consecuencias». **No certifica** apagones, CIFS, la desconexión HTTP real, un lote real ni la integración
de producción: el prototipo es de **un archivo** y vive en `tests/` (ver «Lo que NO está demostrado»). El
**contrato** lo fijó la revisión del 2026-10-03. Origen: criterio 1 de V6a (`docs/BACKLOG.md`) y la auditoría
`docs/design/auditoria-mover-y-sesion.md`. Ficha de benchmarking: `docs/design/benchmark-V6a-asignacion.md`.

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
   `fsync`, **verificación** (tamaño y `sha256`) y publicación **que nunca reemplaza**:
   `renameat2(RENAME_NOREPLACE)` o, si el sistema de ficheros no lo admite, `link` + `unlink`. Si el
   montaje no ofrece ninguna de las dos, **se rechaza** el montaje: no hay un tercer camino «comprobar
   `exists()` y luego `replace`», porque deja una ventana en la que otro escritor puede crear el destino y
   `os.replace` lo sustituiría en silencio (el índice de operaciones solo protege a quien usa esa tabla,
   no a los demás escritores del disco). Si el destino lo ocupó un ajeno, **no se toca**: la operación
   se cancela (`destino_ocupado`) y el reintento reserva el siguiente nombre libre.
3. **Confirmar en una transacción:** archivo, `Issue`, alias y la propia operación. Si el `commit` falla con
   resultado desconocido, **se consulta la BD con otra sesión**; si ni eso es posible, se conserva todo.
4. **Retirar el origen** como limpieza posterior, y **solo si no se puede perder la última copia válida**:
   (a) el destino existe y es íntegro: tamaño y `sha256` **siempre releídos**, también en la misma ejecución
   que lo publicó (no hay exclusión de escritores que sostenga «ya lo verifiqué antes»: lo probó un cambio de
   igual tamaño entre publicar y limpiar); (b) la BD sigue apuntando a ese destino con el `Issue` esperado;
   (c) el origen es, **por contenido** (`sha256`), la copia verificada: tamaño y `mtime_ns` **no** bastan
   (se probó una sustitución de igual tamaño y fecha). Si (a) o (b) fallan: **se conserva el origen** y el
   resultado es `reparacion_pendiente`. Si (c) falla: `asignado_limpieza_pendiente`, sin borrar. Y (d) el
   ejecutor **sigue siendo el dueño** de la operación (ver «Propiedad»).
5. **Reconciliar:** repetir la operación o reiniciar continúa o reconoce lo ya hecho, **consultando solo la
   tabla de operaciones vivas** (índice parcial), sin escanear la biblioteca.

Resultados (conjunto cerrado, con motivo en español): `asignado`, `asignado_limpieza_pendiente` (la
asignación confirmada **no** pasa a fallida si falla el borrado del origen), `reparacion_pendiente` (el
destino falta o está dañado: se conserva el origen), `ya_asignado`, `ya_en_curso`, `pendiente` (no se pudo
confirmar; se reintenta), `pendiente_de_comprobar` (no se pudo ni preguntar a la BD), `destino_ocupado`,
`colision_edicion`, `no_encontrado`, `error`.

La ejecución no se cancela con el cliente (`asyncio.shield`) y se serializa por operación con un **candado
consultivo de TRANSACCIÓN** (`pg_try_advisory_xact_lock`) en una **conexión dedicada**: una operación
huérfana (su proceso murió) se distingue de una en curso sin plazos ni reloj, porque Postgres lo libera al
terminar esa transacción o caer la conexión. **No es un candado de sesión**: esos sobreviven al `rollback` y
duran hasta un `pg_advisory_unlock` explícito o el fin de la sesión de Postgres, de modo que un fallo del
desbloqueo con un *pool* reutilizable dejaría la conexión devuelta al pool reteniéndolo. Con el de
transacción **no existe un desbloqueo que pueda fallar** (`TestCandadoYPoolReutilizable`, con un *pool* real:
operación normal, cancelación directa, fallo al cerrar la sesión y terminación de la conexión por Postgres).
**Coste:** cada operación en curso retiene una conexión del *pool* durante toda la copia (en una transacción
inactiva: `idle_in_transaction_session_timeout` debe permitirlo) y necesita otra para el trabajo corto, así
que el *pool* debe tener **al menos 2 × operaciones simultáneas** (con 1 conexión y 1 operación habría
interbloqueo; se probó con un *pool* de 2).

### Propiedad: perder el candado no detiene el trabajo, así que se vallan los efectos

Perder la conexión **libera** el candado, pero el código Python de ese ejecutor sigue vivo y puede seguir
publicando, confirmando o borrando mientras otro ya ha tomado la operación. Que al final haya cero candados
no lo impide. Por eso:

- Cada ejecutor que consigue el candado incrementa y confirma la **`epoca`** de la fila de la operación (su
  ficha de vallado). **Toda escritura en la BD** de un ejecutor lleva `AND epoca = <la suya>`: la confirmación
  empieza por reclamar la fila con esa época (y la mantiene bloqueada hasta el `commit`), y el cierre
  (`limpiada`/`cancelada`) es condicional. Un ejecutor antiguo **no puede** confirmar ni cerrar nada.
- **Antes de cada efecto** (copiar, publicar, confirmar, borrar el origen) comprueba que **su conexión sigue
  sosteniendo el candado** (`pg_locks` sobre su propia conexión; sin conexión = sin propiedad).
- El temporal lleva la época en el nombre: un ejecutor no pisa ni borra el de otro. El nuevo descarta los de
  épocas anteriores sin listar directorios.
- **Ventana residual:** entre la comprobación y el efecto en disco no hay exclusión posible. Su efecto es
  inocuo por construcción: lo único que se publica es un fichero verificado y con `NOREPLACE`, y solo se
  borra un origen cuyo contenido ya es la copia íntegra del destino confirmado.
- **`max_simultaneas` es por instancia del servicio**, no global. Al integrarlo, el límite debe compartirse
  entre **todas** las instancias que usan el mismo pool (p. ej. un semáforo ligado al motor); una prueba con
  una sola instancia no demuestra un límite global, y aquí no se ha demostrado.

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

`tests/prototipo_asignacion.py` + `tests/test_prototipo_asignacion_pg.py` (43 pruebas) +
`tests/test_prototipo_publicar.py` (6, sin Postgres). Cada defensa se comprobó **por mutación**: quitar la
verificación del hash de la copia, el escudo, el candado, la comprobación del origen por contenido, la del
destino o la de la BD antes de borrar, la consulta tras un `commit` desconocido, la distinción «asignado con
limpieza pendiente», la publicación sin reemplazo (volver a `exists()` + `os.replace`) el candado de
transacción (volver al de sesión), la relectura del destino al limpiar, cada comprobación de propiedad
(antes de publicar, de confirmar y de borrar) o cada vallado de época en la BD hace fallar exactamente las
pruebas que lo protegen. (Una primera ronda de mutaciones mostró que los vallados de la BD **no** estaban
cubiertos: faltaban las pruebas directas de `TestValladoDeEpocaEnLaBd`.)

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
| **No borrar la última copia** (revisión de #76): destino ausente, corrupto (mismo y distinto tamaño) o BD que ya no apunta, tras confirmar | `TestNoBorrarLaUltimaCopia` → `reparacion_pendiente`, origen conservado |
| Origen sustituido por otro de **igual tamaño y fecha** | `…::test_un_origen_sustituido_con_igual_tamano_y_fecha_no_se_borra` → no se borra |
| **Publicar sin reemplazar** (revisión de #76): ajeno que aparece tras la comprobación y antes de publicar | `test_prototipo_publicar.py::…aparece_justo_antes_de_publicar` y `TestPublicarEnElServicio` → ajeno intacto, `destino_ocupado`, el reintento usa el sufijo |
| Montaje sin ninguna publicación segura | `…::test_si_el_montaje_no_ofrece_ninguna_garantia…` y `…rechaza_la_operacion` → rechazado, nada tocado |
| **Candado y pool real** (revisión de #76) | `TestCandadoYPoolReutilizable` (5): ninguna conexión vuelve al pool reteniéndolo |
| **Integridad en la misma ejecución**: destino alterado con igual tamaño entre publicar/confirmar y limpiar | `TestIntegridadEnLaMismaEjecucion` (2) → `reparacion_pendiente`, origen conservado |
| **Una segunda ejecución entra mientras la primera sigue activa** y la antigua no publica / no confirma / no borra | `TestPerdidaDelCandadoMientrasSigueElTrabajo` (3): dos «procesos» (dos motores), Postgres termina la conexión del candado con la primera **pausada, no terminada**; se cuentan las publicaciones, las confirmaciones y los borrados de la antigua (0) |
| Vallado de época aunque la comprobación del candado mintiera | `…::test_aunque_la_comprobacion_de_candado_fallara…` (2) y `TestValladoDeEpocaEnLaBd` (2) |

## Coste medido

`scripts/medicion/medir_asignacion.py`; resultados crudos en `docs/design/medicion-asignacion-2026-10-03.json`.
**Máquina de desarrollo** (Intel i5-8365U, 8 hilos, **NVMe con ntfs3**, caché caliente), no la Pi:

| Tamaño | rename (hoy) | copia + fsync + sha256 | solo sha256 | espacio temporal extra |
|---|---|---|---|---|
| 10 MB | ~0 s | 0,05 s | 0,04 s | 10 MB |
| 100 MB | ~0 s | 0,50 s | 0,38 s | 100 MB |
| 200 MB | ~0 s | 1,01 s | 0,75 s | 200 MB |

- **En esta máquina el hash aislado ocupa la mayor parte del tiempo combinado** (~265 MB/s: 0,38 s de 0,50 s por
  100 MB; mediciones aisladas, no fases de una misma ejecución). **Eso no se
  generaliza:** la medición en la Pi (más abajo) lo desmiente, y la predicción «en una Pi será peor» que figuraba
  aquí se **retira**.
- Asignar un archivo de 100 MB de extremo a extremo: **1,0-1,3 s** con la primera versión del prototipo,
  **1,4-1,7 s** al verificar el origen **por contenido**, y **2,0-2,3 s (~47 MB/s sostenidos)** con la versión
  actual, que además **relee el destino** al limpiar: **tres hashes** de cada archivo (la copia, el destino y
  el origen, ~0,4 s por 100 MB cada uno) más la copia con `fsync`. Es el precio de no borrar jamás la última
  copia válida sin exclusión de escritores; frente a ~0 con `rename`. Optimizable (identidad por inodo y
  `ctime` como pre-filtro) pero **no fiable en CIFS**, así que no se asume.
- **Recuperar** una operación huérfana de 100 MB: **0,9-1,7 s** (según la versión); listar operaciones vivas con 20 000 cerradas:
  **0,5 ms** (índice parcial).
- Espacio temporal: **1× el tamaño del archivo en curso** (el lote es secuencial).
- **Consecuencia para el lote:** 50 archivos de 100 MB serían ~1,8 min aquí (~47 MB/s de rendimiento
  sostenido), y minutos en una Pi o por CIFS: muy probablemente **no cabe en una petición**.
- **Límites del lote (propuesta, a fijar tras medir en el hardware y los montajes reales):** (1) **por
  bytes** (acota la E/S), (2) **por cantidad** (acota el trabajo de BD y el tamaño del informe), y (3) un
  **límite de operaciones simultáneas** (acota las conexiones retenidas). «1× el archivo en curso» describe
  el camino normal, **no el espacio acumulado**: cada `asignado_limpieza_pendiente` o
  `reparacion_pendiente` deja otra copia completa hasta que se repare, así que el lote debe **dejar de
  encolar trabajo cuando el volumen de copias pendientes de limpieza supere un umbral** (a fijar), y el
  informe debe contarlas. La ejecución en segundo plano es **otra historia** (V6a criterio 4).

### Medición en la Pi (2026-10-04, ejecutada por el operador desde el contenedor)

**Evidencia en el repositorio** (informes JSON originales, sin modificar, y las tablas recalculadas):
`docs/design/medicion-pi-ext4-2716ef4-2026-10-04.json`, `docs/design/medicion-pi-cruzado-4ab2b07-2026-10-04.json`,
`docs/design/medicion-pi-asignaciones-2026-10-04.csv` (las **35** asignaciones) y
`docs/design/medicion-pi-resumen-2026-10-04.csv`. Las estadísticas de abajo las **recalculé desde el CSV** y
coinciden con el resumen; los datos de capacidades, hash, copia y recuperación salen de los JSON.

Dos ejecuciones **separadas**, que no deben mezclarse:

| | Código | Lanzador | Asignaciones |
|---|---|---|---|
| **1.ª** | `2716ef4` | **ajuste local** del operador (espera TCP, 120 s), no presente en el repositorio | 15 (3 dispositivos × 5) |
| **2.ª** | `4ab2b07` | el **del repositorio** (sin parche local) | 15 individuales + 5 cruzadas |

El JSON **no registra el commit**: se identifica por el nombre del fichero y la declaración del operador. En
ambas: ARM64 (`aarch64`), 4 núcleos, Python 3.11.17, kernel `6.18.50+rpt-rpi-2712` (la familia `rpi-2712` es la
de la Pi 5; es una inferencia, el JSON no dice el modelo), glibc 2.36; tres **ext4** (`rw,noatime`):
`/ensayo/1` = `/dev/nvme0n1p2`, `/ensayo/2` = `/dev/sdc1` (Descargas), `/ensayo/3` = `/dev/sdb1` (WDElements).
Postgres efímero en **tmpfs**, caché caliente. La carga de memoria previa **no consta** en los informes.

**Asignar un archivo sintético de 100 MB** (camino completo del prototipo, cinco por trayecto):

| Commit | Trayecto | Media | Mediana | Rango | Rendimiento | 50 archivos (lineal) |
|---|---|---:|---:|---:|---:|---:|
| `2716ef4` | NVMe | 1,164 s | 1,147 s | 1,036–1,362 s | 85,9 MB/s | ~58 s |
| `2716ef4` | Descargas | 1,412 s | 1,449 s | 1,264–1,518 s | 70,8 MB/s | ~71 s |
| `2716ef4` | WDElements | 2,919 s | 2,857 s | 2,525–3,340 s | 34,3 MB/s | ~146 s |
| `4ab2b07` | NVMe | 1,075 s | 1,136 s | 0,828–1,163 s | 93,0 MB/s | ~54 s |
| `4ab2b07` | Descargas | 1,193 s | 1,185 s | 1,128–1,274 s | 83,8 MB/s | ~60 s |
| `4ab2b07` | WDElements (mismo disco) | 3,272 s | 3,440 s | 2,434–3,872 s | 30,6 MB/s | ~164 s |
| `4ab2b07` | **Descargas → WDElements** | **1,579 s** | **1,575 s** | 1,411–1,766 s | 63,3 MB/s | ~79 s |

(El banco publica 93,1 y 85,9 con sus tiempos sin redondear; recalcular desde los redondeados da décimas de
diferencia.) Las proyecciones a 50 archivos son **lineales sobre cinco muestras, no un lote medido**.

- **Copia entre dispositivos** (`mismo_dispositivo: false`, `/dev/sdc1` → `/dev/sdb1`): las cinco asignaciones
  suman 7,897 s y la recuperación terminó en `asignado` en 0,594 s. Es **~2,07× más rápida** que asignar dentro
  de WDElements en esta ejecución. **Es un resultado medido, no una garantía**: con origen y destino en el
  mismo disco las lecturas y las escrituras compiten por él; es una **hipótesis plausible que este banco no
  aísla**. El cruce sigue siendo ~32 % más lento que asignar dentro de Descargas.
- **Variación entre ejecuciones:** WDElements pasó de 2,919 s a 3,272 s (+12 %) mientras NVMe y Descargas
  mejoraron. **No se atribuye** al cambio de lanzador ni se trata como regresión sin un ensayo controlado.
- **Recuperar** una operación huérfana de 100 MB: 0,611 / 0,699 / 0,981 s (1.ª) y 0,635 / 0,644 / 0,904 s (2.ª)
  para NVMe / Descargas / WDElements.
- **Predicción retirada.** Se esperaba que el hash dominara y que la Pi lo agravara. Hashear 100 MB tarda
  **0,082–0,099 s** en la Pi (frente a 0,38 s en la máquina de desarrollo); copiar + `fsync` + verificar tarda
  **0,458–1,880 s**. El hash es barato aquí.
- **Residuales aritméticos exploratorios (no son una atribución).** Restar de «copia + fsync + sha256» los
  tiempos aislados de copia y de hash deja ≈ 0,18–0,21 s (NVMe), ≈ 0,08–0,26 s (Descargas) y ≈ 1,2–1,3 s
  (WDElements) por 100 MB (rangos entre las dos ejecuciones), y en WDElements la asignación completa excede en
  ≈ 1 s lo que suman esas fases. Pero las mediciones aisladas **no son fases instrumentadas de una misma
  ejecución**: cambian la caché de páginas, las escrituras pendientes y el trabajo efectuado, y restar medianas
  no equivale, en general, a obtener la mediana del coste restante. La diferencia entre el tiempo combinado y
  los tiempos aislados **sugiere investigar la sincronización y la E/S**; **no permite cuantificar su
  contribución ni identificar el componente dominante**. No se instrumenta más por ahora.
- **Los tiempos de BD no representan producción:** Postgres en `tmpfs` guarda sus datos en memoria. La
  consulta de `File.metadata_` con 50 000 filas: 4,2–4,7 ms; operaciones vivas con 20 000 cerradas: 0,32–0,33 ms.
- **Capacidades** (ambos informes, los tres ext4): `renameat2(RENAME_NOREPLACE)` ok con el destino libre y
  `EEXIST` con el ocupado, `link` ok, `fsync` de fichero y de directorio ok, y la publicación del prototipo con
  un ajeno presente lo deja intacto. `replace` **sí reemplazó** (por eso no se usa para publicar).
- **Límite síncrono:** **no se fija todavía**. Se mantiene **una operación simultánea inicial**, con límites
  por bytes, por cantidad y por copias pendientes.
- **Qué cubre y qué no:** completa esta ronda de medición local del prototipo (los tres dispositivos por
  separado y Descargas → WDElements) y confirma que el lanzador del repositorio funciona sin el parche local.
  **No amplía** la evidencia a apagones (que `fsync` devuelva éxito no prueba que el nombre sobreviva), a CIFS, a
  la desconexión HTTP real, ni a las fronteras de fallo **durante** una copia cruzada. CIFS queda pendiente: no
  forma parte de la instalación real.

### Lanzador: lo que la Pi destapó

La primera ejecución en la Pi necesitó un **ajuste local del lanzador** (espera por TCP y plazo de 120 s) que **no
estaba en el repositorio**. La espera por socket podía detectar el servidor temporal de inicialización (la imagen de Postgres
arranca primero uno que solo escucha en el socket de Unix). Es una **causa probable** del fallo observado; **no se
capturaron los logs del intento original**, así que no está demostrada. La espera por TCP con un margen de 120 s
completó la segunda ejecución. Esta rama lo **reimplementa** (`pg_isready -h 127.0.0.1`, plazo de 120 s configurable con `MEDICION_ESPERA_PG`, con
aborto y limpieza si no llega) y añade **`--cruzado ORIGEN,DESTINO`** (posiciones de los `--dir`) para medir la
copia entre dispositivos. No es el parche local del operador. **La segunda ejecución (`4ab2b07`) lo usó en la
Pi y completó sin necesitar el parche.**

### Capacidades del montaje (medido en el contenedor)

`scripts/medicion/medir_asignacion.sh` lanza el banco **desde la imagen del proyecto**, con una Postgres propia
y efímera (tmpfs, sin puertos), montando **solo** las carpetas que se le indiquen. Resultado en
`docs/design/medicion-asignacion-contenedor-2026-10-04.json` para el único montaje probado:

| Montaje (visto desde el contenedor) | `renameat2` sin reemplazo (libre / ocupado) | `link` | `fsync` fichero / directorio | `_publicar` con un ajeno |
|---|---|---|---|---|
| NVMe local, `ntfs3`, bind mount | ok / `EEXIST` | ok | ok / ok | ajeno intacto |
| **Pi, NVMe** (ext4, `/ensayo/1`) | ok / `EEXIST` | ok | ok / ok | ajeno intacto |
| **Pi, Descargas** (ext4, `/ensayo/2`) | ok / `EEXIST` | ok | ok / ok | ajeno intacto |
| **Pi, WDElements** (ext4, `/ensayo/3`) | ok / `EEXIST` | ok | ok / ok | ajeno intacto |
| **CIFS** | **sin medir** (pendiente; no forma parte de la instalación real) | | | |

En los tres, `replace` **sí reemplazó** un destino existente (lo registra el banco): por eso la publicación
usa `NOREPLACE`/`link` y **nunca** `replace`. La conclusión vale para **estos dispositivos, este kernel y esta
ejecución desde el contenedor**: que `fsync` devuelva éxito **no es** una prueba de supervivencia a un apagón,
ni verificar solo los datos del archivo acredita la persistencia de su nombre.

Cada montaje nuevo se **acepta o se rechaza** según esta tabla. Que el banco corra desde el contenedor
importa porque la semántica de un *bind mount* puede diferir de la del anfitrión.

## Lo que NO está demostrado

- **Corte eléctrico.** `os._exit` mide la muerte del **proceso**, no la durabilidad del sistema de ficheros.
  El prototipo hace `fsync` del fichero y, en mejor esfuerzo, del directorio; **no se ha probado** que un
  `rename` o una copia sobrevivan a un apagón (ni en ext4, ni NTFS, ni CIFS).
- **Montajes reales:** medidos NVMe/ntfs3 local (desarrollo) y los tres ext4 de la Pi (NVMe, Descargas,
  WDElements) y la copia Descargas → WDElements. **Sin medir:** CIFS, exFAT, ext4 en SD, un lote real de varios
  archivos, y ningún fallo inyectado **durante** una copia cruzada en la Pi. Estos resultados fijan **límites y
  estrategia de ejecución**, **no sustituyen** las garantías anteriores ni validan el servicio de producción
  (hay un prototipo de un archivo, sin lote ni integración).
- **Cancelación con uvicorn real:** probada a nivel de tarea (`asyncio`), no con una desconexión HTTP real.
- **Hardlinks:** sin medir ni probar (decididos como optimización posterior).
- **Importador:** un `commit` para todo `scan_and_import()` (`main.py:35`); el mismo riesgo a mayor escala,
  fuera de este ADR (su propia historia).
- **Arranque:** dónde y cuándo llamar a `reconciliar()` (tarea de fondo tras el *lifespan*, para no bloquear
  el healthcheck) está por diseñar e implementar.
- **Tamaño del *pool* en la Pi** (por confirmar): el candado de transacción retiene una conexión por
  operación; el límite de simultáneas debe respetar `2 × simultáneas ≤ pool`.

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
