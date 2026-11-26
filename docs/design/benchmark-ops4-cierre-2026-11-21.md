# Benchmark — cierre de OPS4/#443: actualización manual desde la UI

> **Ficha de benchmarking, no aprobación.** Este documento es insumo para el PO y para
> quien especifique. **No autoriza fusionar, habilitar, desplegar, instalar ni ejecutar**
> nada. La fusión con la función apagada exige la revisión de SecOps del SHA final; la
> habilitación exige las puertas de §12.2 y una decisión expresa distinta.
>
> **Ficha de [benchmark-referencias.md](benchmark-referencias.md) (CLAUDE.md §13), nivel 2**
> por tocar seguridad, ficheros, migraciones y operación del host. Base: rama
> `feat/ops4-seguridad-443`, HEAD **`07161e2a`** (2026-11-21 20:26 +0100); durante
> esta fase la rama avanzó desde `9646aaec` al commitearse la fase final de estado, y
> el benchmark se cierra sobre `07161e2a`. `origin/main` local `02d3817`, merge-base
> `61f4d53`: la rama está apilada y lejos de `main`. La PR #1159 está apilada y la
> función sigue deshabilitada (`OPS4_ACTUALIZACION_HABILITADA=false`, unidad sin
> `[Install]`).
>
> **Fecha:** 2026-11-21 (Europe/Madrid). **Solo lectura de código**: no se ejecutó
> `update.sh`, Docker real, systemd del host, la Pi, el instalador con `--activar` ni
> ningún despliegue. Se ejecutaron únicamente pruebas dirigidas con dobles (§2.2). El
> único fichero escrito es este.

## 0. Resumen ejecutivo

1. **Sonarr y Radarr resuelven un problema parecido, pero desde otra arquitectura.**
   Actualizan una instalación autocontenida, guardan el estado de la operación en su
   propia base de datos (*command queue*) y, en Docker, **desactivan el actualizador
   interno** y delegan en la imagen. ZascArr es una app Docker con `update.sh` de host:
   el patrón que se puede tomar es el de **operación exclusiva + estado persistente +
   reconciliación al arrancar**, no el de sustituir ficheros ni el de ejecutar Git desde
   el contenedor.
2. **Lo que ya está bien en ZascArr no se reescribe.** El cerrojo único, el respaldo
   PostgreSQL verificado con manifiesto y la prueba de restauración posterior son más
   fuertes que lo que hace la referencia para PostgreSQL. Se propone **construir sobre
   lo propio** y copiar de Sonarr/Radarr solo las ideas que faltan: fases, historial de
   versión instalada, huérfanos y no reintento ciego.
3. **Los cinco bloqueantes del revisor siguen siendo reales** y el benchmark los
   confirma: (1) el refresco de auxiliares dentro de `ProtectSystem=strict`; (2) estado
   durable incompleto y sin reconciliación; (3) cerrojo tanteado, no tomado; (4)
   `RuntimeMaxSec=5400` puede matar una migración; (5) `ProtectHome=yes` con `git` y
   `docker`. Además aparece un sexto punto local: `ReadWritePaths` exige
   `/run/zascarr-ops.lock` sin `-` y el instalador OPS4 no instala el `tmpfiles` de OPS1
   que lo crea, por lo que la unidad puede no arrancar (§1.2).
4. **Para fusionar apagado** no hace falta resolver el actualizador real: hace falta
   cerrar la fase final de estado ya commiteada sin dejar medias verdades, reducir
   alcance (módulos muertos y protocolo v3), registrar la desviación de Compose,
   actualizar la documentación y pasar la revisión SecOps del SHA que se fusione
   (§12.1).
5. **Para habilitar** el orden correcto es: estado durable + reconciliación → reserva
   atómica del cerrojo → sandbox y refresco → `update.sh` real en VM con Docker/Postgres
   → `ProtectHome`/Docker/Git → plazo y fases → UI de último intento → activación y
   runbook. Sin las cuatro primeras no se puede afirmar que la actualización sea
   recuperable ni que no haya dos operaciones a la vez (§12.2).

---

## 1. Problema local fijado

### 1.1 Historia, caso real y resultado deseado

- **Historia #443 B:** el coleccionista pide desde la UI una actualización a `main` con
  migraciones, sin pasar por la terminal, aceptando que no hay vuelta atrás automática
  (decisión del PO registrada en [ADR 0026](../adr/0026-actualizacion-manual-confianza-main.md)).
- **Caso real:** Pi 4/5 compartida con Transmission, aMule, Prowlarr y Kavita; la app corre
  en Docker; el usuario de la historia no abre terminales. La actualización puede incluir
  construcción de imagen, migraciones Alembic, reinicio y comprobación de salud; en la Pi
  puede durar muchos minutos (§2.2). La actualización manual actual es
  `sudo bash scripts/update.sh --rama main`.
- **Comportamiento actual:** la acción está **deshabilitada**. La UI solo muestra el
  formulario si `OPS4_ACTUALIZACION_HABILITADA` es verdadero
  ([web/estado.py:52-53](../../src/zascarr/web/estado.py#L52-L53), plantilla
  `estado.html`); el POST devuelve 404 con la bandera en falso
  ([web/actualizacion.py:78-81](../../src/zascarr/web/actualizacion.py#L78-L81)). El
  instalador es manual y sin `--activar` no arranca el socket; la unidad fija no tiene
  `[Install]` ([instalar_actualizacion_ops4.sh:154-162](../../scripts/instalar_actualizacion_ops4.sh#L154-L162)).
- **Resultado deseado:** una acción fija del host, con autorización corta de la app,
  reserva atómica, estado durable legible, un solo intento, sin reintento ciego ni
  rollback automático; tras un corte, el operador debe poder saber qué quedó instalado y
  qué hacer. Es exactamente el contrato de
  [ops4-especificacion-main.md](ops4-especificacion-main.md#L20-L28) (requisitos 7 y 8).
- **Qué no decide este documento:** no decide si se habilita, ni el diseño final de la
  clave, ni el runbook de activación, ni si se cambia el comportamiento de `S=HEAD0`
  (hoy `update.sh` reconstruye y migra también cuando no hay cambio de código;
  [update.sh:133-140](../../scripts/update.sh#L133-L140)). Eso es del PO y de la
  especificación.

### 1.2 Hallazgos del revisor, contrastados con el código actual

El punto de partida es [ops4-revision-pr1159-2026-11-21.md](ops4-revision-pr1159-2026-11-21.md).
Esta tabla fija cada problema local, su evidencia y su consecuencia; el benchmark de §4
es la respuesta, no la corrección.

| # | Hallazgo del revisor | Evidencia en el árbol | Consecuencia actual |
|---|---|---|---|
| 1 | `update.sh` dentro de `ProtectSystem=strict` no puede refrescar auxiliares | La unidad declara `ProtectSystem=strict` y `ReadWritePaths=/opt/zascarr /var/lib/zascarr /var/backups/zascarr /run/zascarr-ops.lock` ([zascarr-actualizar.service:21,32](../../deploy/systemd/zascarr-actualizar.service#L21-L32)). `update.sh` llama a `instalar_ops.sh --refrescar` ([update.sh:222-224](../../scripts/update.sh#L222-L224)), que escribe `/usr/local/lib/zascarr`, `/etc/systemd/system` y `/etc/tmpfiles.d` ([instalar_ops.sh:192-208](../../scripts/instalar_ops.sh#L192-L208)). | El refresco falla; `update.sh` lo trata como aviso blando (rama `warn`) y la actualización puede darse por buena con el auxiliar de OPS1 viejo. Es un fallo funcional silencioso, no un efecto de la actualización sobre la BD. |
| 2 | Estado durable incompleto y sin reconciliación | El auxiliar escribe `aceptada` antes del `start`, `en_curso` después y `fallida` si no arranca ([zascarr_actualizar_aux.py:102-117](../../deploy/ops/zascarr_actualizar_aux.py#L102-L117)); el lector exige `id` y un objeto de cinco campos ([estado_actualizacion.py:32,93-140](../../src/zascarr/services/estado_actualizacion.py#L32-L140)); `/estado` solo pasa la bandera, no lee el estado ([web/estado.py:48-56](../../src/zascarr/web/estado.py#L48-L56)); el POST solo lo lee con el `id` de esa petición ([web/actualizacion.py:103-110](../../src/zascarr/web/actualizacion.py#L103-L110)). El commit `07161e2a` añade un finalizador (`ExecStartPost`/`ExecStopPost`, [zascarr-actualizar.service:13-14](../../deploy/systemd/zascarr-actualizar.service#L13-L14)) que marca `hecha` o `fallida` al terminar la unidad, pero **no fases intermedias, ni HEAD0/S, ni reconciliación, ni vista en `/ui/estado`**. | Tras reiniciar, la app no puede enseñar el último intento. Un `en_curso` antiguo no distingue «sigue en marcha» de «murió»; no hay forma de saber si se avanzó código, se migró la BD o quedó a medias. Bloquea habilitar. |
| 3 | Cerrojo tanteado, no tomado | El auxiliar comprueba el `flock` y lo libera antes de `systemctl start --no-block` ([zascarr_actualizar_aux.py:84-87,108-115,151-172](../../deploy/ops/zascarr_actualizar_aux.py#L84-L172)); `update.sh` lo toma después ([update.sh:58-59](../../scripts/update.sh#L58-L59), [_cerrojo.sh:35-64](../../scripts/_cerrojo.sh#L35-L64)). | La petición puede aceptarse y la unidad no ejecutar la actualización porque otra copia/restauración/actualización entró en la ventana. No hay dos operaciones a la vez, pero sí una aceptación engañosa y una autorización consumida sin efecto. La reserva debe ser atómica respecto del cerrojo. |
| 4 | `RuntimeMaxSec=5400` puede matar la migración | La unidad fija `RuntimeMaxSec=5400`, `TimeoutStopSec=60`, `KillMode=control-group`, `SendSIGKILL=yes` ([zascarr-actualizar.service:15-18](../../deploy/systemd/zascarr-actualizar.service#L15-L18)). `update.sh` no tiene `trap` ni escritura de fases; las migraciones son `docker compose run --rm zascarr alembic upgrade head` ([update.sh:171-177](../../scripts/update.sh#L171-L177)). | `RuntimeMaxSec` termina el servicio y lo deja en estado *failed* (systemd.service(5)); con `KillMode=control-group` alcanza al bash y a sus hijos. Un `SIGKILL` a mitad de migración no ejecuta guardas: puede quedar código avanzado, BD a medias y servicio parado, y la UI no lo sabe. |
| 5 | `ProtectHome=yes` con `git` y `docker` | La unidad fija `ProtectHome=yes` ([zascarr-actualizar.service:22](../../deploy/systemd/zascarr-actualizar.service#L22)) y no define `DOCKER_CONFIG`; en cambio la unidad de restauración, ya probada en VM, define `DOCKER_CONFIG=/run/zascarr-ops/docker` precisamente porque el cliente Docker lo necesita con `ProtectHome` ([zascarr-restaurar@.service:11-13](../../deploy/systemd/zascarr-restaurar@.service#L11-L13)). `update.sh` usa `docker info`, `docker compose build/up/run` y `git fetch` ([update.sh:61-63,123-131,158-177,179-204](../../scripts/update.sh#L61-L204)). | El cliente Docker puede fallar o degradarse; un remoto Git por SSH o una credencial en `/root` no serán accesibles. No se ha probado el `update.sh` real bajo la unidad: las pruebas de VM usaron un `update.sh` falso ([ops4-auxiliar-unidad.md:48-71](ops4-auxiliar-unidad.md#L48-L71)). |
| 6 | **Observación local nueva:** la unidad puede no arrancar si falta el cerrojo | `ReadWritePaths` incluye `/run/zascarr-ops.lock` **sin prefijo `-`** ([zascarr-actualizar.service:32](../../deploy/systemd/zascarr-actualizar.service#L32)); ese fichero lo crea el `tmpfiles` de OPS1 ([zascarr-ops.tmpfiles.conf:3](../../deploy/systemd/zascarr-ops.tmpfiles.conf#L3)), que el instalador OPS4 **no instala** ni declara como dependencia ([instalar_actualizacion_ops4.sh:112-152](../../scripts/instalar_actualizacion_ops4.sh#L112-L152)). | En un host sin OPS1, el *namespacing* de systemd puede fallar antes de `ExecStart`; con OPS1 instalado, el refresco de OPS1 sí crea el fichero. Debe declararse dependencia o usar `-`/`RuntimeDirectory`/`StateDirectory`. |

**Cerrado por el revisor y no se reabre aquí:** el fallback al socket de copias está
corregido; la respuesta del POST ya está dentro del layout; el ADR 0026 existe. El
benchmark los toma como dados y no propone revertirlos.

### 1.3 Lo que este benchmark no es

- No es una auditoría de seguridad de OPS4: eso es SecOps.
- No es la especificación de la habilitación: eso es `ops4-especificacion-main.md` y el
  runbook que falta.
- No es una aprobación de la decisión de confiar en `main`: ADR 0026 ya la registra y este
  documento no la reabre.
- No afirma que Sonarr/Radarr sean mejores: su problema y su unidad de datos son otros.

---

## 2. Datos reales y medición de partida

### 2.1 Estado exacto del árbol contrastado

- Rama `feat/ops4-seguridad-443`, HEAD **`07161e2a`** («feat(ops): fases de estado de la
  unidad de actualización (#443)», 2026-11-21 20:26 +0100). `origin/main` local
  **`02d3817`**; merge-base **`61f4d53`**: la rama está apilada, con ~100 commits de
  diferencia. El rebase sigue pendiente.
- **La rama avanzó durante el benchmark**: al empezar, HEAD era `9646aaec`; el trabajo
  que estaba sin commitear (finalizador de estado y su instalación) se commitó como
  `07161e2a`. El árbol queda limpio salvo este documento. El benchmark se cierra sobre
  `07161e2a`; si la rama sigue avanzando, este documento sigue siendo insumo pero el SHA
  de revisión debe volver a fijarse.
- El commit `07161e2a` añade `deploy/ops/estado_actualizar_ops4.py`, el
  `ExecStartPost`/`ExecStopPost` de la unidad, su copia en el instalador y
  `tests/test_ops4_estado_final_unidad.py`. **No** añade fases intermedias, HEAD0/S,
  reconciliación ni lectura en `/ui/estado`.
- Diferencia frente a `main`: 142 ficheros, ~17.067 inserciones, incluidas piezas de
  #443 A (aviso de versión) y OPS4. El alcance de la PR no está separado por historias:
  es una condición de fusión (§12.1).
- La revisión del propietario y la validación SecOps se hicieron sobre `9e97aa9f` y
  `ee809327`; después hay tres commits de código (`4c07e49e`, `9646aaec`, `07161e2a`).
  El dictamen de SecOps **no cubre** el SHA que se fusionaría hoy.

### 2.2 Pruebas y ejecución real

- **Ejecutado en esta fase** (solo lectura de código + tests con dobles, sobre
  `07161e2a`): `tests/test_ops4_estado_final_unidad.py`,
  `test_ops4_estado_actualizacion.py`, `test_ops4_unidades.py`,
  `test_instalar_ops4.py`, `test_ops4_auxiliar.py`, `test_ops4_ui_actualizacion.py`
  → **74 passed, 1 warning** (5,63 s).
- **Citado de la revisión, no repetido aquí:** suite completa **8928 passed, 2431
  skipped, 0 failed**; selección OPS4/paridad/instalador **937 passed**
  ([ops4-revision-pr1159-2026-11-21.md:51-54](ops4-revision-pr1159-2026-11-21.md#L51-L54)).
  No se repite la suite completa en esta fase para no convertir el benchmark en una
  validación.
- **NOT RUN:** `update.sh` real, Docker real, PostgreSQL, systemd del host, Pi, VM con
  `update.sh` real, instalador con `--activar`, migración, build, reinicio real. La VM
  citada en la documentación usó un `update.sh` falso y no acredita el actualizador real
  ([ops4-auxiliar-unidad.md:66-71](ops4-auxiliar-unidad.md#L66-L71)).
- **Consecuencia:** no hay medición de tiempo real de una actualización en Pi. El
  `RuntimeMaxSec=5400` no está justificado por una medición: es un número de la
  propuesta, no un p95 observado. En Sonarr/Radarr la actualización se ejecuta como
  comando dentro de la app y la unidad de servicio de la app no le impone un
  `RuntimeMaxSec`; eso apoya revisar el plazo antes de habilitar.

---

## 3. Referencias consultadas (versión/commit)

| Referencia | Versión / commit | Qué se leyó | Licencia |
|---|---|---|---|
| **Sonarr** | develop `51a2412af235197ce15d7d4a17c053a8e2c26609` (2026-11-17); contraste con la release **v4.0.20.3014**, commit `c018578e4b79ee048575c02d7a8aa2b929e4b837` (2026-09-16) | `src/NzbDrone.Core/Update/InstallUpdateService.cs`; `src/NzbDrone.Update/UpdateEngine/{InstallUpdateService,BackupAndRestore,TerminateNzbDrone,StartNzbDrone}.cs`; `src/NzbDrone.Core/Backup/{BackupService,MakeDatabaseBackup}.cs`; `src/NzbDrone.Core/Messaging/Commands/{CommandQueueManager,CommandRepository,CommandQueue,Command,CommandExecutor,CommandStatus}.cs`; `src/NzbDrone.Core/Update/History/UpdateHistoryService.cs`; `src/NzbDrone.Core/Update/UpdateVerification.cs`; `src/NzbDrone.Host/SingleInstancePolicy.cs`; `distribution/debian/install.sh`; `src/Sonarr.Api.V5/Commands/CommandController.cs` | GPL-3.0 |
| **Radarr** | develop `25a2124d7d5bb10aae6b89726577303f4bd60f75` (2026-11-20; posterior a la release v7.0.3.10918, 2026-11-16) | Misma familia: `Update/InstallUpdateService.cs`, `Update/History/*`, `Backup/{BackupService,MakeDatabaseBackup}.cs`, `Messaging/Commands/{CommandQueueManager,CommandRepository,CommandQueue}.cs`, `Host/SingleInstancePolicy.cs` | GPL-3.0 |
| **ZascArr (propio)** | Rama `07161e2a` (la rama avanzó desde `9646aaec`; ver §2.1); `origin/main` `02d3817` | `scripts/update.sh`; `scripts/instalar_ops.sh`; `scripts/instalar_actualizacion_ops4.sh`; `scripts/_cerrojo.sh`; `scripts/backup.sh`; `scripts/restaurar_datos.sh`; `deploy/ops/zascarr_actualizar_aux.py`; `deploy/ops/escritor_estado_actualizar_ops4.py`; `deploy/ops/estado_actualizar_ops4.py`; `deploy/systemd/zascarr-actualizar*.{service,socket}`; `deploy/systemd/zascarr-ops.tmpfiles.conf`; `deploy/systemd/zascarr-restaurar@.service`; `src/zascarr/services/{estado_actualizacion,solicitud_actualizacion_v4}.py`; `src/zascarr/web/{actualizacion,estado}.py` | GPL-3.0 |
| **systemd** | `systemd.service(5)` y `systemd.exec(5)` actuales (consultados 2026-11-21) | `RuntimeMaxSec`, `Type=exec`, `KillMode`, `ProtectSystem=strict`, `ProtectHome`, `ReadWritePaths` | — |

**Cómo se leyó:** código fuente en los commits exactos (no la UI ni la documentación del
producto como prueba de comportamiento). No se ejecutó Sonarr ni Radarr. No se copia
código: la barrera legal de [benchmark-referencias.md](benchmark-referencias.md#L165-L180)
sigue vigente. Un «no lo encontré» no equivale a «no existe»; los puntos marcados como
límite se marcan como tales.

---

## 4. Cómo lo resuelve cada una

### 4.1 Actualización

| Paso | Sonarr / Radarr (código leído) | ZascArr hoy |
|---|---|---|
| Quién actualiza | La app, con un **actualizador externo** `Sonarr.Update`/`Radarr.Update` que corre fuera del proceso: verifica requisitos, para la app, copia el paquete sobre la instalación y la reinicia; si la copia falla, restaura la instalación anterior (`UpdateEngine/InstallUpdateService.cs`, `BackupAndRestore.cs`). En Linux espera 10 s a que un servicio externo la reinicie (`StartNzbDrone`/`TerminateNzbDrone`). | El **host**, con `scripts/update.sh` fijo. La app no tiene Docker socket, root ni escritura del repo (ADR 0026); solo pide al auxiliar. Es la frontera correcta para ZascArr. |
| Docker | Si `UpdateMechanism=BuiltIn` y el despliegue es Docker, **no actualiza**: registra «Built-In updater disabled inside a docker container. Please update the container image» (`Core/Update/InstallUpdateService.cs::GetUpdatePackage`). Para Docker el mecanismo es externo. | El despliegue es Docker Compose: el equivalente correcto es la unidad fija del host que reconstruye la imagen y recrea el contenedor. **No** se debe trasladar el actualizador dentro del contenedor. |
| Verificación del paquete | Descarga un paquete y comprueba SHA-256 contra el hash publicado (`UpdateVerification.cs`); si no coincide, aborta antes de instalar. | No hay paquete: se confía en `main` por decisión del PO. Lo equivalente es **fijar y registrar el SHA** (`PREV_SHA`/`NEW_SHA`) y la ascendencia; hoy `update.sh` hace `fetch` + `merge --ff-only origin/main` sobre una ref móvil y no verifica firma ni paquete ([update.sh:123-131](../../scripts/update.sh#L123-L131)). No se debe presentar el SHA como firma. |
| Precondiciones | Comprueba carpeta de instalación/UI escribible, espacio temporal, app data fuera de la carpeta de instalación y que no haya otra instancia (`EnsureAppDataSafety`, `SingleInstancePolicy`). | Comprueba requisitos, credenciales, árbol limpio rastreado y espacio para el dump; no comprueba no rastreados interferentes ni espacio de build/migración ([update.sh:61-121](../../scripts/update.sh#L61-L121)). La guarda de árbol limpio no cubre `--untracked-files=all` (solo `git diff` y `--cached`). |
| No-op | Si no hay actualización, no hace nada. | Si `NEW_SHA == PREV_SHA`, descarta el backup/ref pero **sigue reconstruyendo, migrando y recreando** el servicio ([update.sh:133-140,158-204](../../scripts/update.sh#L133-L204)). Es una diferencia de comportamiento que el PO debe decidir antes de habilitar. |
| Fallo de copia de ficheros | Si la copia del paquete falla, intenta restaurar la instalación anterior (`BackupAndRestore.Restore`) y arranca. | No hay restauración automática de código: `update.sh` deja ancla y dump y pide `rollback.sh` manual. Es la política correcta (el ADR 0026 prohíbe rollback automático); no se copia la restauración de ficheros de Sonarr. |

**Lectura para ZascArr.** Sonarr/Radarr confirman dos ideas: (a) una actualización es una
operación **exclusiva** con estado persistente y no un script suelto; (b) el actualizador
debe ser un artefacto **fijo y separado** del proceso que se actualiza. No confirman el
tope global de tiempo (no lo tienen para el comando de actualización) ni el estado en la
BD de la app (ZascArr reinicia la app y migra su BD: el estado debe vivir fuera).

### 4.2 Backup

| Aspecto | Sonarr / Radarr | ZascArr hoy |
|---|---|---|
| Cuándo | Antes de instalar, justo después de verificar el paquete y antes de lanzar el actualizador: `_backupService.Backup(BackupType.Update)` (`Core/Update/InstallUpdateService.cs::InstallUpdate`). | Antes de tocar código o BD: `update.sh` crea ancla y dump PostgreSQL, lo verifica y escribe manifiesto ([update.sh:90-121](../../scripts/update.sh#L90-L121)). |
| Qué guarda | `BackupService.Backup`: `Config.xml`, base de datos (según motor), `INFO` con versión/fecha; zip en carpeta `backup/update`. | `pg_dump` gzip + verificación de gzip/cabecera/tablas + SHA-256 + manifiesto con commit/Alembic/fecha, retención ligada a refs vivas ([backup.sh](../../scripts/backup.sh); `_comun.sh::verificar_dump`). No es un zip de configuración: el `.env` no se copia (ADR 0012). |
| Retención | `CleanupOldBackups` por antigüedad, salvo backup manual. | `aplicar_retencion` y `podar_refs_huerfanas`; no borra un dump con ref de rescate viva. |
| Verificación | La copia es un zip; la restauración valida cabecera SQLite (`BackupService.Restore`/`ValidateDatabase`). No hay `fsync` ni prueba de restauración antes de actualizar. | `verificar_dump` antes de seguir; `probar_restauracion.sh --dump` **después** de una actualización real (aviso blando si falla) ([update.sh:206-214](../../scripts/update.sh#L206-L214)). |
| PostgreSQL | En el código leído, `BackupService.BackupDatabase` **solo** ejecuta la copia si `DatabaseType.SQLite`; no se encontró rama PostgreSQL en esa ruta. No se infiere soporte externo; se marca como límite de la referencia. | `pg_dump` real, con `volcar_postgres` y verificación; cubre el motor que usa ZascArr. |

**Lectura para ZascArr.** La copia previa obligatoria y verificada ya es más fuerte que la
de la referencia para PostgreSQL; **no se sustituye**. Se toma de Sonarr/Radarr la idea de
**etiquetar el backup como de actualización** y conservar su retención junto al ancla (ya
existe `update_<TS>` + `refs/zascarr/update/<TS>`), y la comprobación de carpeta/espacio
antes de empezar (ya existe para el dump; falta para build/migración).

### 4.3 Estado de operación

| Aspecto | Sonarr / Radarr | ZascArr hoy |
|---|---|---|
| Dónde vive | Tabla `Commands` en la BD principal (`CommandRepository`), con `Status` (`Queued`, `Started`, `Completed`, `Failed`, `Aborted`, `Cancelled`, `Orphaned`), `QueuedAt`, `StartedAt`, `EndedAt`, `Duration`, `Exception`, `Message`, `Result` (`CommandModel`). | Fichero `ops/actualizar-status.json` (root, montado ro en la app) con `schema`, `id`, `estado`, `inicio_epoch`, `actualizado_epoch`; escritor atómico con `fsync` de fichero y directorio ([escritor_estado_actualizar_ops4.py](../../deploy/ops/escritor_estado_actualizar_ops4.py)). |
| Quién lo escribe | La app, en el mismo proceso que ejecuta el comando. | El host (auxiliar/unidad), no la app. Correcto: la app se reinicia y puede migrar su BD durante la operación. |
| Reconciliación al arrancar | `Handle(ApplicationStartedEvent)`: `_repo.OrphanStarted()` marca como `Orphaned` todo `Started` y `Requeue()` vuelve a encolar solo los `Queued` (`CommandQueueManager.cs`). No se reintenta un `Started` huérfano. | No existe. El commit `07161e2a` solo añade la fase final por systemd; no hay fases intermedias, ni comparación HEAD0/S, ni marca de huérfano. |
| Historial de versión | `UpdateHistoryService.Handle(ApplicationStartedEvent)`: si la versión instalada difiere de la última registrada, inserta `Installed` con versión y fecha en la BD de logs. | No existe. `update.sh` conoce `PREV_SHA`/`NEW_SHA` y los pone en el manifiesto del backup, pero no en el estado que lee la app. |
| Visibilidad | API `CommandController` (`GET /command`, SignalR) muestra los comandos en curso/terminados; el frontend los pinta. | Solo la página de resultado del POST lee el estado con el `id` de esa petición; `/ui/estado` no lo lee. Tras reiniciar, se pierde la posibilidad de mostrarlo. |
| Estados de la UI | `Queued/Started/Completed/Failed/Orphaned` + mensaje del comando. | `aceptada/en_curso/hecha/fallida/incierta`; `incierta` también si un `aceptada/en_curso` supera 7200 s sin actualizar ([estado_actualizacion.py:30,139-140](../../src/zascarr/services/estado_actualizacion.py#L30-L140)). |

**Lectura para ZascArr.** El patrón de Sonarr que sí vale es **estado persistente + huérfano
al arrancar + no reintento ciego + historial de versión**. Se **adapta** a fichero del host
(no BD de la app) porque el actualizador reinicia la app. La fase final de `07161e2a` no
basta: un `ExecStartPost`/`ExecStopPost` no sustituye fases, HEAD0/S ni reconciliación.

### 4.4 Bloqueo y exclusión

| Aspecto | Sonarr / Radarr | ZascArr hoy |
|---|---|---|
| Unidad de exclusión | Una sola instancia de la app (`SingleInstancePolicy`, por nombre de proceso) y una **cola de comandos exclusiva**: `ApplicationUpdateCommand.IsExclusive = true`; `CommandQueue.TryGet` no inicia otro comando mientras haya uno exclusivo y no arranca un exclusivo si hay comandos en curso. | Un `flock` común `/run/zascarr-ops.lock` entre `update.sh`, `backup.sh`, `restaurar_datos.sh`, `rollback.sh` y `probar_restauracion.sh` ([_cerrojo.sh](../../scripts/_cerrojo.sh)). Es el mecanismo correcto para un host con varios scripts y operadores. |
| Deduplicación | `Push`/`PushMany` buscan un comando igual ya en cola o en ejecución y devuelven el existente. | El registro de autorizaciones de un solo uso impide repetir el mismo `id`, pero no hay una reserva atómica de «operación en curso» entre aceptación y `systemctl start`. |
| Cerrojo ocupado | La cola espera o salta; el comando exclusivo se ejecuta en orden. | `backup.sh` deja `omitida.json` y sale 75 sin pisar el estado de la copia que corre ([backup.sh:51-70](../../scripts/backup.sh#L51-L70)); `update.sh` sale 75. El auxiliar, en cambio, solo **tantea** y devuelve `operacion_en_curso`; no toma el cerrojo. |
| Transferencia del cerrojo al trabajador | No aplica (misma app). | `_cerrojo.sh` permite heredar el descriptor 9 a hijos (`probar_restauracion.sh`, `instalar_ops.sh`) y lo re-`flock`ea de forma idempotente. Ese es el camino para que la unidad tome el cerrojo **antes** de `update.sh`, no para que el auxiliar lo retenga. |
| Operación externa | No hay un `flock` frente a operadores manuales; la app asume que nadie toca su carpeta. | El cerrojo solo coordina a quien lo respeta; Git/Docker/root externos pueden interferir. El estado y la reconciliación deben detectar discrepancias, no prometer exclusión total. |

**Lectura para ZascArr.** Se **adopta** la semántica de «una operación exclusiva, sin
reintento ciego», pero el cerrojo debe **tomarse antes del `start`** y mantenerse durante
todo `update.sh`. El auxiliar no puede retener el descriptor y transferirlo a systemd; la
solución no es «esperar al trabajador» con el cerrojo en la mano (interbloqueo), sino
hacer que el trabajador adquiera el cerrojo como primera acción y que la aceptación no se
considere completa hasta ver `en_curso` (o una reserva durable equivalente).

### 4.5 Los instaladores del propio repo (`instalar_ops.sh` / `instalar_actualizacion_ops4.sh`)

| Aspecto | `instalar_ops.sh` (OPS1, ya probado) | `instalar_actualizacion_ops4.sh` (OPS4) |
|---|---|---|
| Activación | `--refrescar` se usa desde `update.sh` si OPS1 ya estaba instalado; `--quitar` retira. Instala `zascarr-ops.tmpfiles.conf` y hace `systemctl enable --now zascarr-ops.socket` (`instalar_ops.sh:192-208`). | Manual; sin `--activar` deja unidades en disco y no persiste. `--activar` hace solo `systemctl start zascarr-actualizar.socket`, no `enable` (`instalar_actualizacion_ops4.sh:154-162`). |
| Rutas | Crea `ops/ops.key`, `tmpfiles` y el estado de copias; el refresco reescribe el auxiliar y las unidades. | Crea `ops/actualizar.key`, copia auxiliar/módulos/unidades. **No** instala `tmpfiles`; no crea `/run/zascarr-ops.lock`. |
| Relación con `update.sh` | El paso 9 de `update.sh` lo invoca con `--refrescar`; si falla, aviso blando. | No se invoca desde `update.sh`; el operador lo ejecuta antes de activar. |
| Efecto en el sandbox | Es la escritura que `ProtectSystem=strict` deniega en la unidad de actualización (hallazgo 1). | Si la unidad OPS4 necesita el cerrojo, depende del `tmpfiles` de OPS1; el instalador OPS4 no lo declara (hallazgo 6). |

**Lectura:** el patrón bueno ya está en `instalar_ops.sh` (idempotente, rutas estrechas,
tmpfiles, activación explícita). El problema no es el instalador: es que `update.sh` hace
un refresco de OPS1 **dentro** de una unidad que no puede escribir esas rutas. Para la
fusión apagada basta con documentarlo; para habilitar, separar el refresco en una unidad
fija (B3) o declarar el paso manual.

---

## 5. Supuestos de las referencias que NO valen en ZascArr

- **«La app puede sustituir sus propios binarios».** Sonarr/Radarr corren desde una carpeta
  escribible y lanzan un actualizador externo que para y reinicia la app. ZascArr corre en
  un contenedor inmutable; actualizar es reconstruir la imagen y recrear el contenedor con
  `update.sh`. No se traslada el *file swap*.
- **«El estado puede vivir en la BD de la app».** En Sonarr la app es el actualizador y
  sigue viva; en ZascArr la app se reinicia y su BD puede estar migrando. El estado debe
  vivir en el host, como ya hace `actualizar-status.json`.
- **«La copia de la BD es un zip de SQLite».** ZascArr usa PostgreSQL; su backup es
  `pg_dump` verificado. La copia SQLite de Sonarr/Radarr no es aplicable.
- **«Una sola instancia = exclusión suficiente».** ZascArr tiene varios scripts root,
  systemd, copias, restauración y operadores manuales; necesita el `flock` común y, además,
  reserva atómica.
- **«El actualizador interno funciona en Docker».** Sonarr/Radarr lo desactivan
  explícitamente cuando el despliegue es Docker. ZascArr debe mantener la separación
  app/host y no dar a la app Docker socket ni root.
- **«Los comandos en cola se reintentan».** Sonarr reencola los `Queued`, pero **no** los
  `Started` huérfanos. En ZascArr una actualización privilegiada nunca se relanza sola: un
  huérfano se muestra incierto y se reconcilia a mano.
- **«Hay un tope global de tiempo razonable».** En Sonarr/Radarr el comando de
  actualización vive dentro de la app y no lo limita un `RuntimeMaxSec` de unidad; el
  estado lo gestiona la propia app. ZascArr debe medir y decidir fases/plazos, no matar
  una migración a ciegas.
- **«El hash del paquete acredita autoría».** Sonarr verifica el SHA-256 del paquete; eso
  acredita integridad de descarga, no autoría. ZascArr confía en `main` (ADR 0026); el SHA
  es trazabilidad, no firma.
- **«La UI de Sonarr/Radarr es el contrato».** Su UI muestra comandos en curso; la de
  ZascArr tiene que mostrar el último intento del host y no prometer éxito sin estado.
- **«La Pi se comporta como el servidor de referencia».** Memoria, SD, build y migraciones
  son el límite real; las referencias no miden eso.

---

## 6. Resultado por idea (adoptar / adaptar / mejorar / construir sobre lo propio / descartar)

| Idea (referencia) | Veredicto | Aplicación local y motivo | Fase |
|---|---|---|---|
| Actualizador **fijo y separado** del proceso actualizado (`Sonarr.Update`/unidad fija) | **Adoptar** | Ya existe `zascarr-actualizar.service` + auxiliar + socket; conservar la acción fija. No añadir parámetros de rama/ruta/entorno a la petición web. | (a) y (b) |
| En Docker, el actualizador interno se desactiva y se actualiza la imagen (`GetUpdatePackage`, `PackageUpdateMechanism == Docker`) | **Adoptar como principio / adaptar** | No llevar `update.sh` al contenedor. La UI pide al host; el host reconstruye la imagen. Documentar que la app no se auto-modifica. | (a) |
| Comprobar que la instalación/carpetas son escribibles y que hay espacio antes de instalar | **Adoptar** | `update.sh` ya comprueba requisitos y espacio del dump; añadir comprobación de espacio para build/migración y de las rutas que la unidad permite escribir. | (b) |
| Verificar el paquete por SHA-256 antes de instalar | **Adaptar** | No hay paquete: registrar `PREV_SHA`/`NEW_SHA` y la ascendencia; no presentar el SHA como firma ni como autoría. No añadir verificación de paquete. | (b) |
| Backup antes de cualquier efecto (`BackupType.Update`) | **Construir sobre lo propio** | Ya es más fuerte: `pg_dump` verificado + manifiesto + ancla. Añadir etiqueta/tipo «actualización» al estado y conservar la retención; no sustituir por zip. | (b) |
| Retención de backups de actualización y limpieza de temporales | **Adoptar** | Ya hay retención ligada a refs vivas; revisar que un backup de actualización no se borre mientras su ref exista y que los temporales no queden en la Pi. | (b) |
| Restauración de la instalación anterior si falla la copia del paquete | **Descartar** | ZascArr no cambia binarios in-place; su vuelta atrás es `rollback.sh` manual. Copiar `BackupAndRestore` introduciría una segunda política de rollback. | — |
| Estado persistente de la operación con estados cerrados | **Adoptar + adaptar** | Adoptar la semántica; adaptar el soporte a fichero del host (ya existe el escritor atómico). No moverlo a la BD de la app. | (b) |
| Huérfano al arrancar: `Started` → `Orphaned`, no reintentar | **Adoptar + adaptar** | Adaptar a: `aceptada`/`en_curso` sin señal → `incierta`; nunca relanzar. La reconciliación de efectos (HEAD, imagen, BD) es manual/operador, como exige FR-12. | (b) |
| Historial de versión instalada (`UpdateHistory`) | **Adoptar + adaptar** | Guardar `HEAD0`, `S`/`NEW_SHA`, fecha y resultado en el mismo estado (o fichero de historial del host). La UI puede enseñar «actualizado de X a Y» sin depender de la BD de la app. | (b) |
| Comando exclusivo y deduplicación en cola | **Adoptar el principio** | Una sola operación; el `flock` propio ya es la exclusión. Añadir la reserva atómica que hoy falta y no reintentar un `Started` huérfano. | (b) |
| Cerrojo único de operaciones entre scripts | **Construir sobre lo propio** | `_cerrojo.sh` ya cubre `update.sh`, `backup.sh`, `restaurar_datos.sh` y `rollback.sh`. La unidad debe tomar el cerrojo **antes** de `ExecStart` (wrapper/`ExecStartPre`) y `update.sh` debe detectar el descriptor heredado (ya lo hace `_cerrojo.sh:43-58`). | (a) y (b) |
| Reserva atómica entre aceptación y `systemctl start` | **Adaptar / mejorar** | No basta con tántear: o la unidad toma el `flock` como primera acción y la aceptación espera a `en_curso`, o se escribe una reserva durable bajo el `flock`. Ocupado no debe consumir la autorización ni pisar el estado en curso. | (b) |
| Poner un tope global (`RuntimeMaxSec`) a la actualización | **Descartar tal cual / adaptar** | Sustituir por plazos por fase (backup, build, migración, health) y estado; si se conserva un tope global, debe ser holgado, medido y marcar `incierta`/`sin noticias`, no `fallida` sin diagnóstico. | (b) |
| Matar el grupo y reiniciar la app con `KillMode=control-group` | **Adoptar con condiciones** | Sirve para no dejar procesos; pero un SIGKILL a mitad de migración exige estado y reconciliación. No usar `ExecStartPost` como única fuente de verdad. | (b) |
| `DOCKER_CONFIG` fuera del home para `ProtectHome` | **Adoptar** | Copiar el patrón ya probado de `zascarr-restaurar@.service`: `DOCKER_CONFIG=/run/zascarr-ops/docker` + `ReadWritePaths` y tmpfiles; validar `git`/`docker` reales bajo la unidad. | (b) |
| Refresco de auxiliares dentro del script actualizador | **Adaptar / separar** | No ampliar el sandbox a `/usr/local` y `/etc` sin más. Separar el refresco en una unidad fija con sus rutas estrechas (o declararlo paso manual documentado). `update.sh` no debe ocultar un fallo de refresco como si todo hubiera ido bien. | (a) y (b) |
| UI de estado de la operación (comandos/estado) | **Adoptar + adaptar** | Mostrar el último intento en `/estado` tras reiniciar, con fecha y estado; no ofrecer reintento ciego; no pintar cadenas libres del fichero. | (b) |
| Instancia única por nombre de proceso | **Descartar** | No es el mecanismo de ZascArr (systemd + `flock`). No añadir comprobaciones de proceso. | — |
| `update_required` y autoactualización al arrancar | **Descartar** | ZascArr no se autoactualiza ni al arrancar; la actualización es una acción manual autorizada. | — |
| Backup SQLite/integridad de cabecera | **Descartar** | No aplica a PostgreSQL; la verificación propia (`gzip`, cabecera, tablas, SHA-256, restauración) es la buena. | — |
| Reintento automático de la actualización | **Descartar** | Prohibido por el contrato y por el ADR 0026; un fallo posterior al `start` es incierto y exige reconciliación. | — |

---

## 7. Invariantes de ZascArr (no negociables en la implementación)

1. **No mentir.** La UI no dice «actualizado» si no hay estado/verificación; un `aceptada`
   no es éxito; un `en_curso` sin noticias es «sin noticias/incierta», no «hecha».
2. **No borrar ni reintentar a ciegas.** Un fallo posterior al inicio no se reetiqueta como
   rechazo previo; no se relanza otra actualización sin reconciliar unidad, HEAD, imagen,
   contenedor y BD ([ops4-especificacion-main.md:48](ops4-especificacion-main.md#L48)).
3. **No hay rollback automático.** Se conservan ancla, dump y evidencia; `rollback.sh` es
   una decisión manual. Una copia verificada no garantiza restauración sin pérdida.
4. **Un solo cerrojo y una sola operación.** Copia, restauración, actualización manual y
   actualización UI no se solapan. El cerrojo se toma antes de cualquier efecto y se
   mantiene hasta el final.
5. **Sin secretos en estado, logs, argv, entorno ni URL.** La contraseña y el testigo no
   cruzan al host ni se escriben; el estado es solo observación.
6. **Coste Pi.** Nada de procesos residentes nuevos ni dependencias nuevas; el estado es un
   JSON pequeño y el actualizador solo corre cuando se pide. El build/migración ya es el
   coste real.
7. **Fallar cerrado.** Estado ilegible, cerrojo dudoso, `fsync` incierto, `start` ambiguo,
   clave ausente o host no disponible ⇒ no se inicia o se marca incierto; nunca se
   inventa un éxito.
8. **La app no recibe root, Docker socket, escritura del repo ni la política del host.**
   Sigue el límite de ADR 0021/0026.

---

## 8. Casos de prueba antes de implementar (criterio comprobable)

Los casos con estado **PASS** son los ya ejecutados en esta fase o en la revisión; el resto
es **NOT RUN** y no se puede contar como aprobado. El arnés de host (Git, Docker/Postgres,
systemd, usuario sin privilegios, cortes) sigue siendo una puerta separada.

| ID | Caso | Observable esperado | Estado |
|---|---|---|---|
| T-01 | Dos peticiones válidas simultáneas | Como máximo una reserva y una unidad; la otra recibe ocupada; no se consumen dos autorizaciones | NOT RUN |
| T-02 | Petición mientras corre copia/restauración/manual | Ocupada sin escribir estado de la operación en curso; la autorización no se consume | NOT RUN |
| T-03 | La unidad no puede tomar el cerrojo | `update.sh` sale 75 antes de backup/build; estado final `fallida`/`omitida` sin afirmar éxito | NOT RUN |
| T-04 | Carrera entre tanteo del auxiliar y `systemctl start` | La aceptación solo se devuelve si el trabajador tomó el cerrojo (o reserva durable); si no, ocupada | NOT RUN |
| T-05 | Corte antes/después de `aceptada`, `en_curso`, backup, avance, build, migración, health | Estado persistente con fase y HEAD0/S; sin reintento ni rollback; «sin noticias» si procede | NOT RUN |
| T-06 | Reinicio de la app tras actualización | `/estado` muestra último intento y resultado; no depende de la BD ni de la petición original | NOT RUN |
| T-07 | Estado con `id` de otra operación, JSON corrupto, campos extra, duplicados, tamaño >4 KiB | Lector falla cerrado; no pinta rutas ni cadenas libres | PASS (`tests/test_ops4_estado_actualizacion.py`) |
| T-08 | Fichero de estado sustituido por symlink/FIFO/directorio | No se sigue el enlace, no se bloquea; incierto | PASS |
| T-09 | Escritura de estado con `fsync`/rename fallido | No se afirma durabilidad; el actualizador no finge éxito | PASS parcial (`escritor_estado_actualizar_ops4.py`; falta prueba de fallo inyectado en el flujo real) |
| T-10 | `ExecStartPost` falla tras una actualización correcta | La unidad no debe pasar a `fallida` por el finalizador; el resultado bueno se conserva | NOT RUN (la fase final actual devuelve 1 si falla la escritura: riesgo) |
| T-11 | `RuntimeMaxSec` durante migración | Estado `incierta`/`sin noticias`, no `hecha`; no se ejecuta un segundo intento; se conserva evidencia | NOT RUN |
| T-12 | `update.sh` real bajo la unidad, con Docker/Postgres, `--rama main` | Build, migración, `up` y health reales; el refresco de OPS1 y `probar_restauracion` se comportan como se decida | NOT RUN; la VM usó `update.sh` falso |
| T-13 | `git fetch` y `docker compose` con `ProtectHome=yes` | Funcionan con `DOCKER_CONFIG`/`HOME` explícitos o fallan cerrado antes de tocar nada | NOT RUN |
| T-14 | Host sin OPS1: falta `/run/zascarr-ops.lock` | La unidad arranca (con `-`/tmpfiles/dependencia) o falla con causa clara, no con error de namespacing | NOT RUN |
| T-15 | `S == HEAD0` | Según decida el PO: «Ya está actualizado» sin build/migración, o comportamiento manual documentado | NOT RUN (hoy reconstruye y migra) |
| T-16 | Respuesta perdida tras `systemctl start` | `incierta`; la UI no invita a reintentar; reconciliación manual | NOT RUN |
| T-17 | Estado final: `aceptada`/`en_curso` tardío después de `hecha` | Las escrituras son monótonas; un `en_curso` tardío no pisa `hecha` | NOT RUN (el auxiliar escribe `en_curso` después del `start`; hay carrera) |
| T-18 | UI con bandera falsa / clave ausente / socket caído | 404 sin formulario; 503 con mensaje claro; no se filtra la clave | PASS (`test_ops4_ui_deshabilitada.py`, `test_ops4_ui_actualizacion.py`) |
| T-19 | Instalador sin `--activar` / con `--activar` | Sin activación por defecto; `--activar` solo inicia socket, no persiste ni enciende la UI; `--quitar` limpia | PASS parcial (`test_instalar_ops4.py`; falta prueba del comando `systemctl` exacto) |
| T-20 | Suite en Python 3.11 (imagen de producción) | Verde en la versión de producción, no solo en la del venv local | NOT RUN |

**Criterio de «mejor» si se declara MEJORAR:** una instalación PostgreSQL puede restaurar
la BD previa tras un fallo de actualización, y la UI puede decir qué quedó instalado sin
depender de que la app esté sana. Se comprueba con T-12/T-05/T-06, no con una captura de
pantalla.

---

## 9. Matriz nivel 2 (orientativa; no reabre la decisión del PO)

Pesos por defecto de [benchmark-referencias.md](benchmark-referencias.md#L82-L87): encaje
con el flujo del coleccionista 25 · coste en Pi 20 · seguridad/legalidad 20 · cobertura del
requisito 15 · adaptabilidad al stack 10 · mantenimiento 5 · lock-in 5. Puntuación 1–5;
total sobre 500. Se comparan **mecanismos**, no aplicaciones enteras.

| Mecanismo | 25 | 20 | 20 | 15 | 10 | 5 | 5 | Total |
|---|---|---|---|---|---|---|---|---|
| **A. Servicio fijo del host + estado en fichero + cerrojo común** (lo actual, con las correcciones de §12.2) | 4 | 4 | 4 | 4 | 5 | 4 | 5 | **415** |
| **B. Actualizador dentro de la app** (patrón BuiltIn de Sonarr/Radarr, con cola en BD y updater propio) | 2 | 2 | 1 | 3 | 1 | 2 | 2 | **185** |
| **C. Solo operación manual documentada; UI informativa sin botón** | 2 | 5 | 5 | 2 | 5 | 5 | 5 | **380** |

**Lectura:** B no es viable en ZascArr: exigiría dar a la app Docker socket/root o
ejecutar scripts descargados como root dentro del contenedor, justo lo que ADR 0021/0026
evitan. C es seguro pero no cumple la historia (el coleccionista no usa consola). A es la
base correcta; su nota no es una aprobación: sigue necesitando las puertas de §12.2.
La matriz no cambia la decisión de confiar en `main` (ADR 0026).

---

## 10. IGUALAR / MEJORAR

**IGUALAR (mínimo competitivo):**

- Backup obligatorio y verificado antes de tocar código/BD.
- Operación exclusiva: una actualización a la vez; ocupado no pisa el estado en curso.
- Estado persistente con resultado y fase; huérfano al arrancar sin reintento ciego.
- No prometer éxito sin verificación; mostrar el último intento tras reiniciar.
- Comprobación de precondiciones (espacio, rutas, credenciales, árbol limpio).
- Sin secretos en estado/logs; fallo cerrado ante duda.

**MEJORAR (con evidencia y criterio comprobable):**

- **Copia PostgreSQL real y restauración comprobada.** En el código leído,
  `BackupService.BackupDatabase` de Sonarr/Radarr solo cubre SQLite; ZascArr hace
  `pg_dump`, verifica gzip/cabecera/tablas y prueba la restauración después. Criterio: una
  instalación PostgreSQL puede volver al estado previo tras un fallo de actualización,
  verificado por T-12. **Ya está en ZascArr; no se copia la referencia.**
- **Estado legible mientras la app está caída o migrando.** El estado de Sonarr vive en la
  BD de la app; el de ZascArr puede leerse del fichero del host aunque la app no esté
  sana. Criterio: T-06/T-11. **Construir sobre lo propio**, no importar la cola de
  comandos.
- **Ventana de reserva atómica.** Sonarr no tiene el problema porque su cola vive en un
  proceso; ZascArr sí. Criterio: T-01/T-04 con dos procesos reales. Es una mejora sobre lo
  que la referencia resuelve por arquitectura, no una copia.

---

## 11. Decisión final / ADR

- **No se requiere un ADR nuevo para este benchmark.** La decisión de confiar en `main`
  está en [ADR 0026](../adr/0026-actualizacion-manual-confianza-main.md); el patrón de
  auxiliar/socket, en [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md).
- **Antes de habilitar, ADR 0026 debe actualizarse** (o añadirse una nota) para registrar:
  (a) que el estado durable es un fichero del host y no la BD de la app; (b) la
  reconciliación de huérfanos y el no reintento; (c) el riesgo residual de la clave
  compartida con el contenedor **en estado habilitado** (hoy el ADR lo acepta solo mientras
  la función esté apagada); (d) el refresco de auxiliares y su unidad separada, si se
  adopta. La habilitación no puede apoyarse en una lectura ampliada del ADR actual.
- **Este documento no aprueba** ni la fusión ni la habilitación. La fusión apagada la
  decide el PO con la revisión SecOps del SHA final; la habilitación exige las puertas de
  §12.2 y una autorización expresa separada.

---

## 12. Lista priorizada de cambios necesarios

### 12.1 (a) Para fusionar con la función apagada, sin habilitar

Ordenados por lo que bloquea la fusión. Ninguno enciende la UI ni ejecuta `update.sh`.

| # | Cambio | Por qué / criterio de hecho |
|---|---|---|
| **A1** | **Revisar y cerrar la fase final de estado ya commiteada** (`07161e2a`: `estado_actualizar_ops4.py`, `ExecStartPost`/`ExecStopPost`) o retirarla del alcance de esta PR. Si se conserva: prefijo `-` para que un fallo de escritura no convierta en fallida una actualización correcta; `ExecStopPost` debe leer el estado y mapear `SERVICE_RESULT` (`timeout`/`signal` ⇒ `incierta`; `exit-code` ⇒ `fallida`; `success` no debe pisar `hecha` ni dejar `en_curso` si la unidad se paró a mano); el `en_curso` del auxiliar no puede escribirse después de un posible `hecha`; pruebas de T-10/T-17. | Es la parte más delicada del árbol: una media verdad de estado es peor que no tener el finalizador. Si no se puede cerrar con pruebas, **fuera de la PR apagada** y se pospone a la habilitación. |
| **A2** | **Reducir el alcance apilado**: separar #443 A / OPS4 / cambios ajenos; rebasar sobre `origin/main` actual y resolver conflictos. | La PR mezcla 142 ficheros y ~17k líneas; el dictamen de SecOps es de otro SHA. El rebase y la separación son condición de revisión, no cosmética. |
| **A3** | **Retirar o aislar módulos muertos y el protocolo v3** que no se instalan ni usa el auxiliar (experimentos, aprobación C-12, admisión/cliente v3). Dejar solo lo que el auxiliar/instalador usan. | Reduce la superficie privilegiada y el ruido de revisión. Criterio: el instalador copia exactamente lo que el auxiliar importa; grep de imports y prueba de aislamiento. |
| **A4** | **Registrar o revertir la desviación de Compose** (`OPS4_*` inyectadas con default `false`, [docker-compose.yml:163-167](../../docker-compose.yml#L163-L167)). | Condición CF-R2 de SecOps: el `.env` de root puede encender la UI; debe quedar aceptado por escrito o revertido antes de fusionar. |
| **A5** | **Actualizar documentación a la verdad del SHA**: los textos que aún dicen «no hay unidad/transporte» o «UI sin conectar»; el estado de la fase final y sus límites; los recuentos de pruebas; los límites de la VM con `update.sh` falso. | Una PR de ops que miente sobre su propio estado es deuda de habilitación y confunde la revisión. |
| **A6** | **Revisión SecOps del SHA exacto que se fusione** (CLAUDE.md §5.8), con árbol limpio y `git status` vacío, incluidos los tests y la unidad. | El dictamen actual es de `9e97aa9f`; después hay tres commits de código (`4c07e49e`, `9646aaec`, `07161e2a`). Sin esto no hay GO. |
| **A7** | **Suite completa y selección OPS4/paridad/instalador** en el árbol rebasado; `ruff check src/`; prueba estática de que el instalador no hace `enable` y de que la unidad no tiene `[Install]`. | Criterio: 0 fallos; no se acepta «la suite pasó en otro SHA». |
| **A8** | **No desplegar en el mismo acto**: no `--activar`, no tocar Pi, no poner la bandera en `.env`, no ejecutar `update.sh`; dejar constancia en la PR. | Condición CF-R4 de SecOps; la fusión apagada no cambia la política de despliegue. |

**No son condiciones de fusión** (pero sí de habilitación): el estado completo, la reserva
atómica, el sandbox, el plazo o `ProtectHome`. Se pueden dejar documentados como
pendientes; lo que no se puede es presentarlos como resueltos.

### 12.2 (b) Para habilitar (después de la fusión apagada)

Ordenados por riesgo y dependencia. **B1–B4 son P0**: sin ellos no hay habilitación
defendible. B5–B7 son P1; B8–B10, P2.

| # | Cambio | Referencia / por qué | Verificación |
|---|---|---|---|
| **B1 (P0)** | **Estado durable completo + fases + reconciliación.** Extender el contrato del fichero (nueva versión de esquema) con `head0`, `sha_destino`/`sha_actual`, `fase`, `codigo`/`resultado`, `unidad`/`inicio`; escribirlo solo el host, de forma atómica y monótona. `update.sh` escribe fases cuando lo invoca la unidad (variable de entorno fija, sin cambiar la acción); `ExecStartPost`/`ExecStopPost` son solo el cierre de último recurso. Al arrancar, un `aceptada`/`en_curso` sin señal se marca `incierta`; reconciliación de HEAD/imagen/BD por el operador. `/estado` lee el último intento sin `id` de petición. | Sonarr/Radarr: `Commands` persistidos + `OrphanStarted`/`Requeue` + `UpdateHistory`; aquí se **adapta** a fichero del host porque la app se reinicia. | T-05, T-06, T-07, T-08, T-09, T-16, T-17; inyección de fallos en cada fase; estado sin secretos. |
| **B2 (P0)** | **Reserva atómica y cerrojo tomado antes del efecto.** Que la unidad adquiera el `flock` como primera acción (wrapper `flock`/`ExecStartPre` con fd heredado 9, que `_cerrojo.sh` ya reconoce) y que la aceptación del auxiliar solo se complete cuando el estado pasa a `en_curso`; o una reserva durable bajo el mismo `flock`. Ocupado: no consumir la autorización, no pisar el estado en curso. | Sonarr/Radarr: comando exclusivo y deduplicado; ZascArr ya tiene el cerrojo común, falta la atomicidad. | T-01, T-02, T-03, T-04; dos procesos reales; cruce con copia/restauración/manual. |
| **B3 (P0)** | **Sandbox y rutas de escritura coherentes.** Decidir el refresco de OPS1: unidad separada de acción fija con `ReadWritePaths` estrechos (`/usr/local/lib/zascarr`, `/etc/systemd/system`, `/etc/tmpfiles.d`) o paso manual documentado; no ampliar el sandbox de `update.sh` sin análisis. Incluir en `ReadWritePaths` todo lo que el script escribe de verdad (`@REPO@`, `@BACKUP_DIR@`, `@ZASCARR_DATA_DIR@`, cerrojo) y resolver `ReadWritePaths=/run/zascarr-ops.lock` (prefijo `-`, `RuntimeDirectory`/`StateDirectory` o dependencia del tmpfiles de OPS1). | Sonarr/Radarr separan el actualizador del sandbox de la app; OPS2 ya usa una unidad estrecha. La lección es **separar**, no ampliar. | T-12, T-14; `systemd-analyze verify`; prueba real en VM con Docker/Postgres; refresco correcto o fallo duro declarado. |
| **B4 (P0)** | **Validar el `update.sh` real bajo la unidad en VM aislada**, con Docker y PostgreSQL desechables: éxito, no-op, cerrojo ocupado, fallo de build, fallo de migración, corte de energía, reinicio, timeout y estado final. Sin `update.sh` falso. | La VM actual solo acreditó socket→auxiliar→unidad con script inocuo ([ops4-auxiliar-unidad.md:48-71](ops4-auxiliar-unidad.md#L48-L71)); no acredita el actualizador real. | Evidencia firmada por fase; NOT RUN no cuenta como PASS. |
| **B5 (P1)** | **`ProtectHome` con Docker y Git.** `DOCKER_CONFIG=/run/zascarr-ops/docker` + `ReadWritePaths`/tmpfiles (patrón de `zascarr-restaurar@.service`); `HOME`/`GIT_CONFIG_GLOBAL` explícitos o política clara para remotos SSH/credenciales; validar `docker compose build/up/run`, `docker info` y `git fetch` bajo la unidad. | La unidad de restauración ya documenta el problema; `update.sh` no lo tiene resuelto. | T-13, T-12; sin `/root` accesible; fallo claro si el remoto exige credencial de home. |
| **B6 (P1)** | **Plazo por fases, no `SIGKILL` ciego.** Medir en Pi el p95 de backup/build/migración/health; poner plazos a cada paso y un tope global holgado (o `infinity`) con estado `incierta`/`sin noticias` si se agota; `ExecStopPost` no debe escribir `hecha`. | Sonarr/Radarr no ponen tope global al comando; la Pi sí necesita acotar, pero por fase y con estado. | T-11, T-12; migración lenta simulada; no se declara éxito parcial. |
| **B7 (P1)** | **UI de último intento y estados.** `/estado` muestra el último intento (fecha, estado, si hay operación en curso) leído del fichero del host, sin `id` de petición; `en_curso` antiguo ⇒ «sin noticias»; `incierta` no ofrece reintento ciego; `hecha` no se pinta si el estado no lo acredita. La página de resultado ya está en layout: conservarla. | Sonarr/Radarr muestran comandos en curso/terminados; ZascArr necesita la versión host-side. | T-06, T-11, T-18; pruebas de plantilla con ficheros reales; sin cadenas libres. |
| **B8 (P2)** | **Activación y runbook.** Confirmación explícita de `--activar` (arma ejecución root real, no persistente, sin rollback automático); orden exacto grupo→clave→instalador→tmpfiles/cerrojo→socket→bandera; verificaciones posteriores (clave legible por el grupo, socket `LISTEN`, 404/503, repetición, cerrojo); prueba estática del `systemctl start` y de que no hay `enable`. | CE-1/CE-5 de SecOps; la habilitación no puede ser un `--activar` genérico. | Ensayo en VM; no en la Pi. |
| **B9 (P2)** | **Ciclo de vida de la clave y del registro durable.** Rotación/revocación, retención/cuota de `ops4/consumidos`, paridad 0400/0440, y decisión sobre la clave montada en el contenedor **con la función habilitada** (separar claves o endurecer el socket; actualizar ADR 0026). | El ADR 0026 acepta el riesgo residual solo mientras esté deshabilitada; CE-8/CE-12. | Revisión SecOps + ADR; pruebas de rotación y de registro lleno. |
| **B10 (P2)** | **Cierre documental y de comportamiento**: decidir `S=HEAD0` («Ya está actualizado» sin build/migración o comportamiento manual documentado), actualizar recuentos, contratos v4, runbook, límites de la VM y de la Pi; suite en Python 3.11; smoke en Pi autorizado por separado. | Evita que el comportamiento real contradiga la especificación; hoy `update.sh` reconstruye y migra en no-op. | Suite 3.11; smoke en Pi con ventana autorizada; documentación sin contradicciones. |

**Puerta final:** con B1–B4 verdes y B5–B10 cerrados o declarados como deuda aceptada por
el PO, la habilitación sigue exigiendo autorización expresa separada, revisión SecOps del
SHA final y ventana autorizada. Este benchmark no la concede.

---

## 13. NOT RUN, caducidad y trazabilidad

- **NOT RUN:** ejecución real de `update.sh`, Docker, PostgreSQL, systemd del host, Pi,
  VM con `update.sh` real, migración, build, reinicio, activación del socket, instalador
  con `--activar`, pruebas de cortes de energía. La única ejecución de esta fase son los
  tests con dobles de §2.2.
- **Caducidad:** ~60 días desde 2026-11-21, o antes si cambia la historia, `update.sh`,
  `instalar_ops.sh`, las unidades, el auxiliar, el lector/escritor de estado o los commits
  de Sonarr/Radarr citados. Si cambia el SHA que se fusiona, este documento sigue siendo
  insumo, pero la revisión de seguridad debe repetirse.
- **Trazabilidad:** cada afirmación de código propio lleva ruta y línea; cada referencia
  externa lleva commit y fichero. La documentación de OPS4 citada
  (`ops4-revision-pr1159-2026-11-21.md`, `secops-ops4-*.md`) conserva el estado anterior;
  este documento no la sustituye.
