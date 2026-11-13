# SPEC: «Hacer una copia ahora» desde la interfaz — proceso auxiliar del host (BL-OPS1, issue #443, historia 1) — v1.4

> **v1.4 (2026-11-12) — reconciliación con el estado actual de `main`, antes de construir (breve; detalle en §15).** (1) **ADR:** #455 (lector de RAR) ocupó el **0015**; ya existen el 0016 (publicación sin número) y el 0017 (apartar copias idénticas a una cuarentena: trata de **archivos duplicados**, no de copias de seguridad); el ADR de esta historia pasa del 0015 al **0018** (BL-OPS2 usa el 0019; los números definitivos son «el siguiente libre al fusionar»). (2) **Cerrojo:** FR-12 vive ahora en **`scripts/_cerrojo.sh`** (cargado por `_comun.sh` y, directamente, por `restaurar_datos.sh`, que **no** usa `_comun.sh`): **desviación aceptada por el PO (2026-11-12)**; corrige un error de v1.0 (E-14). (3) **Evidencia nueva:** los scripts operativos, `deploy/` y `docker-entrypoint.sh` **no han cambiado** desde la base de v1.1 (E-13); el compose de la app lleva ya `no-new-privileges` y `pids: 256` (E-6); `/estado` ha ganado secciones (E-15). BL-OPS3 (#508) está fusionada: la parte de G-1 que toca a Ajustes está **cumplida** (§13). **Base contrastada de v1.4:** `origin/main` = `ac108e214c54dd6e803baa966925b69afffe2989` (fetch del 2026-11-12). **El builder la empezó el 2026-11-12; ese trabajo no está en `origin/main`** y no lo he leído: lo que dice de `_cerrojo.sh` lo declara el Brain. v1.3 se conserva en `especificacion-BL-OPS1-v1.3.md` (sha256 `6b79b038…92d1`).


> **Decisiones del PO (2026-11-06):** aceptadas Q-1 (divergencia de A-1 solo para «copia», con G-1 como puerta de restaurar y actualizar), Q-11 (tope de 6 copias/24 h), Q-12 (`omitida.json` aparte), Q-13 aplazada y Q-2…Q-10 con la recomendación de este documento. Aprobada por SecOps (`dictamen-BL-OPS1-v1.2.md`) y revisada por UX. Construir requiere orden expresa aparte.

> **Estado:** v1.3 (2026-11-06): retoque mínimo pedido por SecOps sobre v1.2 (`dictamen-BL-OPS1-v1.2.md`, aprobable sin bloqueantes); v1.2 integró la pasada de SecOps y la revisión de UX sobre v1.1 (`dictamen-BL-OPS1-v1.1.md`); v1.1 integró el dictamen sobre v1.0 (`dictamen-BL-OPS1-especificacion.md`: A-1, A-2, A-3, M-1…M-4, B-1…B-4)
> y la revisión de UX (Q-2, Q-9, textos de §9). Registro de cambios por hallazgo en §15. v1.0 se conserva en `especificacion-BL-OPS1-v1.0.md`
> (sha256 `a4c20a20…cbf05`). Destino previsto: `docs/design/especificacion-BL-OPS1.md` (aquí vive en `encargos/` porque SPEC.writer no hace commits).
> **Sin código, sin PR, sin comentarios en GitHub, sin tablero, sin Pi.**
> **v1.3:** v1.2 se conserva en `especificacion-BL-OPS1-v1.2.md` (sha256 `9ac377b6…24df`). Base contrastada de v1.3: `origin/main` = `b1a9000f57a9eea43e6902ebe123e3e9fa7de000` (sin cambios).
> **v1.2:** v1.1 se conserva en `especificacion-BL-OPS1-v1.1.md` (sha256 `86eb6846…4170`). Base contrastada de v1.2: `origin/main` = `b1a9000f57a9eea43e6902ebe123e3e9fa7de000`
> (fetch del 2026-11-06; sin cambios en los ficheros que toca la historia respecto a v1.1).
> **Base contrastada v1.1:** `origin/main` = `b1a9000f57a9eea43e6902ebe123e3e9fa7de000` (fetch del 2026-11-06). Frente a `c48b1ff` (base de v1.0) solo cambia
> `scripts/medicion/banco_cobertura.py`; ninguno de los ficheros que toca esta historia (scripts operativos, `deploy/`, compose, entrypoint, `health.py`, `config.py`, `auth.py`, `estado.py`/`estado.html`, pruebas de copia) ha variado.
> (aquí vive en `encargos/` porque SPEC.writer no hace commits). **Sin código, sin PR, sin comentarios en GitHub, sin tablero, sin Pi.**
> **Base contrastada:** `origin/main` = `c48b1ff844f28febc39d95adb54e2364ec266885` (fetch del 2026-11-06). El dictamen de SecOps y la ficha
> de SCOUT se contrastaron con `4b09a6a`; `git diff --stat 4b09a6a origin/main` sobre `scripts/`, `docker-compose.yml`, `deploy/`,
> `services/auth.py`, `api/health.py`, `config.py`, `web/estado.py` y `docker-entrypoint.sh` está **vacío**: nada de lo que dictaminaron ha cambiado.
> **Entradas:** `encargos/specwriter-443-ops-desde-la-ui.md` (decisiones del PO del 2026-11-06), `ficha-443-actualizar-copiar-restaurar-ui.md`,
> `dictamen-443-modelo-de-privilegios.md` (C-1…C-14), `scripts/backup.sh`, `scripts/_comun.sh`, `deploy/systemd/*`, `docker-compose.yml`,
> `docker-entrypoint.sh`, `config.py`, `api/health.py`, `web/estado.py`, `services/auth.py`, `docs/design/backup-334.md`.
> **Notación:** EARS con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES, DONDE; «DEBERÁ»); criterios Given/When/Then; identificadores
> en inglés; textos de cara a la persona en español llano (CLAUDE.md §6). **PASS** = leído en código; **NOT RUN** = no ejecutado (§11).
> **Alcance:** solo la historia 1. Restaurar, aviso de versión y actualizar **no** se especifican; §13 dice qué deja preparado el canal y qué puertas
> exige antes de ampliarlo.

---

## 0. Resumen ejecutivo

**Qué cambia.** El coleccionista pulsa **«Hacer una copia ahora»** en la interfaz y ZascArr hace la misma copia verificada que ya hace cada noche.
Para ello se añade un **proceso auxiliar del host**: un socket de systemd (`Accept=yes`) por el que la app envía **una línea JSON firmada con HMAC, de
esquema cerrado y una única acción (`copia`)**. El auxiliar no ejecuta scripts ni toca Docker: **solo ordena a systemd iniciar la unidad ya existente
`zascarr-backup.service`** (la de la copia diaria). La app ve el resultado por los ficheros de solo lectura que ya usa (`status.json`) más dos nuevos
(`ops-status.json`, `copias.json`), y pinta solo códigos que conoce.

**Qué no cambia.** La copia diaria (mismo script, mismas verificaciones, misma retención de 14 días por referencia viva); `/api/health` (público: no
se le añade nada); la app sigue **sin socket de Docker, sin root, sin `.env` y sin montaje con escritura**; la biblioteca no se toca; no se sube ningún archivo.

**Lo que la historia deja cerrado de una vez** (el dictamen dice que el trabajo de seguridad cae aquí, no después): canal sin ficheros (M-1 desaparece),
esquema cerrado y firma (C-3, C-5), cerrojo único de operaciones en **todos** los scripts operativos (M-2, C-6), entorno limpio y argumentos fijos
(M-4, C-7), registro sin rutas ni credenciales (C-13), unidad endurecida (C-14) y solo `POST /ui/*` (C-2).

**Hallazgo que el PO debe ver (Q-1).** La condición A-1 («clave solo de root y del contenedor») **no se puede cumplir al pie de la letra** mientras la app
corra con el UID del usuario de servicio compartido con la suite *arr: la app tiene que *leer* la clave para firmar, así que cualquier proceso del
mismo grupo del host puede leerla. Para **copiar** el daño máximo es ocupar disco (300 s entre copias, 6 por 24 h y comprobación de espacio) y se acepta; para
**restaurar y actualizar** no basta, y §13 lo convierte en una puerta de entrada (G-1) de las historias 3 y 4.

**Lo que NO está probado** (§11): nada se ha ejecutado; systemd, el socket, el montaje `:ro`, `python3` en la Pi y el coste de copiar con la app sirviendo
son NOT RUN y se miden antes de dar la historia por buena (P-1…P-7).

---

## 1. Alcance

**Dentro:** (1) socket + auxiliar + unidades; (2) protocolo y validación; (3) cerrojo único de operaciones; (4) botón, estado y resultado en la UI;
(5) listado de copias propias, solo lectura; (6) instalador del auxiliar y su clave; (7) cambios mínimos de `backup.sh`, `_comun.sh`, el nuevo `_cerrojo.sh`, compose y `config.py`;
(8) pruebas sin systemd; (9) ADR y documentación de la postura.

**Fuera, siempre** (dictamen §5, no se reabre): subir archivos de copia; argumentos libres (rama, ruta, nombre, SHA, `--yes`, `--forzar`, entorno);
socket de Docker o root en la app; tocar credenciales, `.env`, puertos o exposición; acciones por nombre de script; actualizar sin que la persona lo pida;
tocar la biblioteca; restaurar `update_*` por la vía de «solo datos».

**Fuera de esta historia:** restaurar, aviso de versión, actualizar, borrar copias desde la UI, rotar la clave desde la UI, mostrar el estado de la
restauración de comprobación (ya existe en `/estado`).

## 2. Contexto y evidencia (PASS = leído en `c48b1ff`)

| # | Hecho | Dónde |
|---|---|---|
| E-1 | La copia ya existe, es verificada y corre por unidad systemd `Type=oneshot`, `TimeoutStartSec=30min`, `Nice=10`, con `EnvironmentFile=-/etc/default/zascarr`. | `deploy/systemd/zascarr-backup.service` |
| E-2 | `backup.sh` toma `flock -n` sobre `BACKUP_LOCK_FILE` (`/run/zascarr-backup.lock`); **ningún otro script operativo** lo toma (solo `backup.sh` contiene `flock`). | `backup.sh:33,56-57`; `git grep flock scripts` |
| E-3 | El `trap on_exit` (que escribe `status.json` de fallo) se instala **después** de `comprobar_requisitos`, `comprobar_env_legible`, `mkdir` y `flock`: un fallo en esas líneas termina sin escribir estado. | `backup.sh:46-62` |
| E-4 | `status.json` lo escribe el host (`0644`, atómico), el compose lo monta `:ro` en `/run/backup-status` y llega a `/api/health` y a `/estado` con un mapa cerrado de códigos a texto. | `backup.sh:75-120`, `docker-compose.yml` (volumen `backup-status:ro`), `api/health.py:61-180` |
| E-5 | El contenedor arranca como root y se degrada a `zascarr` con `PUID/PGID` del usuario de servicio (`groupmod`/`usermod` + `runuser`). Un fichero del host legible por ese **grupo** lo lee la app. | `docker-entrypoint.sh:~55-69` |
| E-6 | **El contenedor de la app no es `read_only`** (solo `credenciales` lo es) y no tiene `docker.sock`. **Desde #455 (ADR 0015, v1.4) lleva además `security_opt: [no-new-privileges:true]` y `deploy.resources.limits.pids: 256`** (este Compose rechaza `pids_limit` junto a `deploy.resources.limits`); nada de eso afecta al volumen `ops:ro` ni a FR-28. | `docker-compose.yml` (`read_only: true` una vez; `security_opt` y `pids` en el servicio de la app) |
| E-7 | El middleware aplica Origen/Host a POST/PUT/PATCH/DELETE con **cualquier** `auth_mode`; con `none` no hay sesión. Un POST a `/api/*` sin `Origin` **pasa**; a `/ui/*` no. `/api/health` y `/login` están exentos de sesión. | `services/auth.py:234-263, 625-700` |
| E-8 | `/estado` pinta la fila «Copias de seguridad» **en cliente** desde `/api/health`; la página está en las rutas de diagnóstico del arranque degradado. | `web/templates/estado.html:92,107`, `auth.py:122` |
| E-9 | `BACKUP_LOCK_FILE` lo fijan `tests/test_backup_script.py:179` y `tests/escenarios/identidades.sh:99`. | `git grep` |
| E-10 | `uninstall.sh` solo **avisa** de los timers systemd (no los quita). | `uninstall.sh:404-408` |
| E-11 | `update.sh` no usa `flock` ni `systemctl`. | `grep` |
| E-12 | Próximo ADR libre: **0018**. Existen hasta el 0017: `0015-lector-de-rar-con-unar` (#455), `0016-publicacion-sin-numero` y `0017-apartar-copias-a-cuarentena` (**copias idénticas de archivos**, sin relación con las copias de seguridad). *(v1.4; en v1.0 era el 0015.)* | `docs/adr/` en `origin/main` `ac108e214c54dd6e803baa966925b69afffe2989` |
| E-13 | **Los ficheros que toca esta historia no han cambiado** desde la base de v1.1 (`b1a9000`): `git diff --stat b1a9000 origin/main` sobre `scripts/backup.sh`, `_comun.sh`, `update.sh`, `rollback.sh`, `probar_restauracion.sh`, `restaurar_datos.sh`, `instalar_backup.sh`, `_espacio.sh`, `deploy/` y `docker-entrypoint.sh` está **vacío**. `docker-compose.yml` solo gana variables y los controles de E-6; el `Dockerfile` pasa a `python:3.11-slim-trixie` con `unar` 1.10.8 (#528/#530): **no afecta a OPS** (el auxiliar usa el `python3` del host, no el de la imagen). | `git diff --stat` (2026-11-12) |
| E-14 | **`restaurar_datos.sh` NO usa `_comun.sh`**: solo hace `source` de `_espacio.sh` y define su propio `die`/`info`. La v1.0–v1.3 pedían que `_comun.sh` ofreciera `tomar_cerrojo_operaciones` y que `restaurar_datos.sh` lo llamara: **imposible tal cual** (un script no puede llamar una función de un fichero que no carga). Por eso el cerrojo va en `scripts/_cerrojo.sh` (FR-12.8). | `restaurar_datos.sh` (cabecera), `probar_restauracion.sh` (`source _comun.sh`) |
| E-15 | `/estado` ha ganado secciones desde v1.3: «Qué información tengo» (cobertura, `web/estado.py`) y, tras ella, un enlace a la exportación CSV con la frase «Esto no es una copia de seguridad.». El bloque «Copias de seguridad» (FR-23) **sigue siendo una fila de `/api/health` pintada en cliente** (`CHECK_LABELS.backup`); su ubicación no cambia, pero el diseño debe convivir con esas secciones (UX). | `web/templates/estado.html`, `web/estado.py` |

**Correcciones a las entradas** (se dicen, no se resuelven en silencio): la issue y la ficha dan la app como `read_only` (falso, E-6); la ficha propone
«directorio de intercambio» (M4) y el PO decidió **socket** (D-1); el dictamen pide una clave «solo de root y del contenedor» (no realizable, Q-1).

## 3. Glosario

- **Auxiliar:** programa del host, de root, lanzado por systemd por cada conexión al socket (`zascarr-ops@.service`). No es un servicio residente.
- **Petición:** una línea JSON ≤ 512 bytes con `v`, `id`, `accion`, `creada`, `firma`.
- **Respuesta:** una línea JSON `{"v":1,"id":…,"resultado":"aceptada"|"rechazada","codigo":…}`.
- **Directorio de operaciones (`OPS_DIR`):** `${ZASCARR_DATA_DIR:-/var/lib/zascarr}/ops`, `root:<grupo>` `0750`; contiene `ops.sock` y `ops.key`. Se monta `:ro` en la app en `/run/zascarr-ops`.
- **Directorio de estado (`BACKUP_STATUS_DIR`):** el actual, `root` `0755`, montado `:ro`. **Root es el único que escribe en él.**
- **Cerrojo único:** `OPS_LOCK_FILE` (`/run/zascarr-ops.lock`), tomado con `flock -n` por todos los scripts operativos.

---

## 4. Requisitos funcionales

### 4.1 Canal y protocolo

- **FR-01 (canal)** El sistema DEBERÁ ofrecer un socket Unix de systemd en `OPS_DIR/ops.sock` con `Accept=yes`, `SocketUser=root`, `SocketGroup=<grupo del
  usuario de servicio>`, `SocketMode=0660`, `MaxConnections=4` y un límite de ráfaga de activaciones. No habrá directorio de peticiones ni ficheros de petición.
- **FR-02 (esquema)** CUANDO el auxiliar reciba una petición, DEBERÁ exigir **exactamente** las claves `v` (entero `1`), `id` (32 hex minúsculas), `accion`
  (cadena), `creada` (entero, época en segundos) y `firma` (64 hex minúsculas); UTF-8; una sola línea terminada en `\n`; ≤ 512 bytes. SI falta, sobra o
  se repite una clave, el tipo no es el exigido, el JSON no es un objeto o no hay `\n` en 5 s, ENTONCES responderá `esquema_invalido`. El auxiliar **no
  leerá más de 513 bytes** de la conexión.
- **FR-03 (firma)** DEBERÁ calcular `HMAC-SHA256(clave, "{v}|{id}|{accion}|{creada}")` en hexadecimal y compararlo en **tiempo constante** con `firma`.
  SI no coincide ENTONCES responderá `firma_invalida`. La clave son 32 bytes aleatorios en hexadecimal (64 caracteres) leídos de `OPS_DIR/ops.key`; SI falta
  o no tiene ese formato, el auxiliar responderá `no_disponible` a todo y lo dirá en el diario con un código genérico (`clave_ausente`).
- **FR-04 (orden de comprobación)** El auxiliar DEBERÁ comprobar en este orden y parar en el primer fallo: esquema → firma → caducidad → repetición →
  acción → frecuencia → cerrojo. Así quien no sabe firmar no averigua nada del estado.
- **FR-05 (caducidad)** DEBERÁ rechazar con `caducada` toda petición cuya `creada` difiera del reloj del host en más de **120 s** (pasado o futuro).
- **FR-06 (un solo uso)** DEBERÁ registrar cada `id` aceptado a firma en `/run/zascarr-ops/vistos/<id>` (creación `O_EXCL`, directorio de root `0700`) y
  rechazar con `repetida` un `id` ya visto; purgará lo más viejo de **300 s** en cada conexión (la caducidad es ±120 s, así que un `id` válido puede vivir hasta 240 s:
  los 300 s dejan 60 s de margen; SecOps B-1). Como `/run` es `tmpfs`, un reinicio vacía el registro y **no puede quedar ninguna orden pendiente** (no hay cola).
- **FR-07 (lista cerrada)** DEBERÁ aceptar solo `accion = "copia"`. Cualquier otro valor, incluidos `restaurar` y `actualizar`, responderá
  `accion_no_disponible`. La tabla acción → unidad systemd (`copia` → `zascarr-backup.service`) estará **en el código del auxiliar**: ni en la petición, ni en
  `/etc/default/zascarr`, ni en el entorno.
- **FR-08 (respuesta)** El auxiliar DEBERÁ contestar una línea JSON con `v=1`, `id` (el recibido, o `null` si no se pudo leer), `resultado` y `codigo`, y cerrar.
  Los códigos son una **lista cerrada**: `aceptada`, `esquema_invalido`, `firma_invalida`, `caducada`, `repetida`, `accion_no_disponible`, `demasiado_pronto`, `limite_diario`,
  `operacion_en_curso`, `no_disponible`. La respuesta **nunca** lleva texto libre ni rutas.

### 4.2 Ejecución, frecuencia y cerrojo

- **FR-09 (ejecución)** CUANDO la petición sea válida y pase FR-10 y FR-11, el auxiliar DEBERÁ ejecutar `systemctl start --no-block zascarr-backup.service` con
  lista de argumentos fija, sin shell y con **entorno vacío** (solo `PATH` fijo). NO ejecutará scripts del repositorio, NO invocará Docker, NO leerá el `.env`
  y NO pasará nada de la petición ni de su entorno a la unidad.
- **FR-10 (frecuencia y tope)** DEBERÁ rechazar con `demasiado_pronto` una `copia` si la última aceptada fue hace menos de **300 s**, y con `limite_diario` si ya se
  aceptaron **6** en las últimas 24 h (ventana móvil). Ambos valores son del auxiliar, no de la petición (Q-3, Q-11). Guardará las épocas aceptadas en
  `/run/zascarr-ops/aceptadas` (root, `0600`; se poda a 24 h). *Motivo (SecOps A-2):* la retención es por antigüedad (`aplicar_retencion`, `-mtime +14`), sin tope por número;
  solo con 300 s un proceso del grupo generaría hasta 288 copias/día. Con el tope, el máximo es **6 copias pedidas/24 h × 14 días ≈ 84 dumps** (más los diarios), locales y en el
  disco de respaldo. *Límite conocido:* `/run` es `tmpfs`, así que un reinicio pone el contador a cero; quien pueda reiniciar el equipo ya tiene más poder que este canal.
  **Contador ilegible (SecOps v1.1 A-2):** SI `aceptadas` **no existe**, se trata como vacío (primer uso o reinicio: es `tmpfs`); SI existe pero no se puede leer o interpretar (corrupto, tipos erróneos,
  épocas en el futuro **más allá de la tolerancia de 300 s**), el auxiliar **falla cerrado**: responde `no_disponible`, deja `contador_ilegible` en el diario y **nunca lo reinicia a 0** ni lo reescribe. *Efecto conocido (para el ADR 0018):*
  quien tenga el grupo puede agotar las 6 copias y dejar el botón inservible hasta 24 h; solo es disponibilidad, la copia nocturna sigue (R-12).
  **Tolerancia de reloj (SecOps v1.2 B-1):** una época anotada hasta **300 s** en el futuro (igual que la purga de FR-06) se acepta como válida, porque una Pi sin reloj de hardware puede corregir la hora
  hacia atrás al sincronizar con la red; más allá de eso, es ilegible. El auxiliar **no se autorrepara** por diseño: el ADR 0018 DEBERÁ recoger el procedimiento de recuperación para quien instaló
  ZascArr: **borrar `/run/zascarr-ops/aceptadas` como root** (el contador vuelve a vacío; se pierde, como mucho, el límite de las 6 de esa jornada).
- **FR-11 (cerrojo, aviso)** ANTES de aceptar, el auxiliar DEBERÁ comprobar **sin crear ni bloquear** (`open` de solo lectura, sin `O_CREAT`; `flock` no bloqueante y soltar al
  instante; un `ENOENT` significa «libre») la ruta constante del cerrojo (FR-12); SI está tomado, o si `systemctl is-active zascarr-backup.service` no dice `inactive`, ENTONCES
  responderá `operacion_en_curso`. **La autoridad es el cerrojo que toma el script** (FR-12); esta comprobación solo evita mentir a la persona. **La carrera residual** (otra operación
  toma el cerrojo entre esta comprobación y el arranque de `backup.sh`) **la cubre FR-33** (`omitida.json`), no FR-14 (corrección de A-3: v1.0 lo atribuía a FR-14).
- **FR-12 (cerrojo único)** **`scripts/_cerrojo.sh`** (fichero nuevo, v1.4) DEBERÁ ofrecer `tomar_cerrojo_operaciones`; lo DEBERÁ cargar `_comun.sh` (y con él `backup.sh`, `probar_restauracion.sh`, `update.sh` y `rollback.sh`) y lo DEBERÁ cargar **directamente** `restaurar_datos.sh` (que no usa `_comun.sh`, E-14); y lo DEBERÁN llamar al principio `backup.sh`, `probar_restauracion.sh`, `update.sh`,
  `rollback.sh` y `restaurar_datos.sh` (M-2/C-6). Reglas:
  1. **Ruta constante en producción:** `/run/zascarr-ops.lock`, fijada en `_cerrojo.sh` y repetida en el auxiliar; **no** se lee de `/etc/default/zascarr` ni del entorno. Solo se
     admite un cambio con `ZASCARR_PRUEBAS=1` + `OPS_LOCK_FILE=<ruta>` (las pruebas existentes pasan de `BACKUP_LOCK_FILE` a esto; E-9). Un `OPS_LOCK_FILE` o `BACKUP_LOCK_FILE`
     perdidos en `/etc/default/zascarr` **no tienen efecto** (SecOps M-3).
  2. **Descriptor fijo 9 y herencia padre→hijo (SecOps A-1):** el script toma `exec 9>"$ruta"; flock -n 9`. CUANDO un script operativo lo invoca otro que ya tiene el cerrojo
     (`update.sh` → `probar_restauracion.sh --dump`, `update.sh:192`), el hijo DEBERÁ comprobar que `/proc/self/fd/9` y la ruta constante tienen el mismo `dispositivo:inodo` y hacer
     `flock -n 9` **sobre el descriptor heredado**: sobre la misma descripción de fichero abierta es idempotente y no sale 75. SI el descriptor 9 no existe o apunta a otro fichero,
     abre y toma el cerrojo como un proceso independiente. *(Comprobado en el scratchpad con una prueba mínima de 6 líneas: heredado → «ok»; descriptor ajeno → «ocupado»; cerrojo de otro
     proceso → «ocupado (75)». Sigue siendo una hipótesis hasta el AC-33 con los scripts reales.)*
  3. SI el cerrojo está tomado por otro proceso, el script saldrá **sin tocar nada** (ni el árbol, ni dumps, ni `status.json`), con «Hay otra operación de ZascArr en marcha; espera a que
     termine.» y código **75**; en los scripts que corren como unidad, el mensaje va al diario (traza).
  4. **`SuccessExitStatus=75`** en `zascarr-backup.service` **y en `zascarr-restore.service`** (el restore mensual que choque con una copia o un `update.sh` no debe dejar la unidad
     `failed`; SecOps M-2a).
  5. **Quien sobreviva al padre mantiene el cerrojo** (la descripción de fichero se comparte; SecOps v1.1 A-1). Hoy ninguno de `backup.sh`, `update.sh`, `rollback.sh`, `restaurar_datos.sh` y
     `probar_restauracion.sh` lanza nada en segundo plano; se fija con una **prueba estática** (AC-42) y, si en el futuro se lanzara algo, con `9>&-` en ese proceso.
  6. **Sin root, mensaje en llano:** `tomar_cerrojo_operaciones` DEBERÁ capturar el fallo de apertura de `/run/zascarr-ops.lock` y decir «Ejecuta con sudo: hace falta para tomar el cerrojo de ZascArr.»
     (código de salida 1, no 75). La apertura se escribe `exec 9>"$ruta" || die …`, como ya hace `backup.sh`, porque un `exec` con redirección fallida no siempre aborta el script; el resultado es un mensaje en llano y no el error crudo de bash que ahora aparecería antes del chequeo de root de `comprobar_env_legible` (SecOps v1.1 P-2; AC-44).
  7. **Aviso del override:** CUANDO `ZASCARR_PRUEBAS=1` esté activo, el script imprimirá en `stderr` «ZASCARR_PRUEBAS activo: el cerrojo no es el de producción.», para no dejarlo olvidado.
  8. **Dónde vive (desviación aceptada por el PO, 2026-11-12):** en `scripts/_cerrojo.sh`, con un `source` desde `_comun.sh` y otro desde `restaurar_datos.sh`; el comportamiento descrito en los puntos 1–7 (ruta constante, descriptor 9, herencia padre→hijo, salida 75, «Ejecuta con sudo», aviso del override) **no cambia**. Los cinco scripts siguen llamándolo al principio. *(Lo declara el Brain: el builder ya lo hizo; **no está en `origin/main`** y no lo he leído. `restaurar_datos.sh` no usa `_comun.sh`: leído, E-14.)*
- **FR-13 (no encolar)** Una petición con el cerrojo tomado se **rechaza**; nunca se encola ni se reintenta sola.

### 4.3 Estado, resultado y listado (los escribe el host; la app solo lee)

- **FR-14 (`backup.sh`: orden y fallo con constancia)** `backup.sh` DEBERÁ ejecutar, **en este orden** (SecOps M-1): (1) `command -v flock`; (2) **tomar el cerrojo** (FR-12) —si está ocupado:
  FR-33, salir con 75 y **sin trap**, así que `status.json` no se toca—; (3) crear el directorio de estado y **leer `last_success_*` de `status.json`**; (4) **instalar `trap on_exit`**;
  (5) `comprobar_requisitos`, `comprobar_env_legible` y `mkdir` de `BACKUP_DIR`. Hasta terminar (5) vale `FASE=preparacion`: un `die` en esa fase hará que `on_exit` escriba
  `status=failed`, `error=precondition_failed` y **conserve** `last_success_*` (nunca a 0). Después de (5), `on_exit` mantiene `unexpected`. `precondition_failed` se añade a
  `api/health.py::_BACKUP_ERRORES` («no se pudo preparar la copia»). *Motivo:* sin trap temprano, una copia pedida que falla pronto deja la UI en «en marcha»; con el trap **antes** del cerrojo
  o de la lectura de `last_success_*`, el 75 escribiría `failed/unexpected` encima de la copia que sí corre y un fallo de precondición borraría la última copia buena.
  *Dependencia conocida (SecOps v1.1 P-3):* el paso (3) y `escribir_estado` usan `jq`; si **falta `jq`**, no se puede escribir `precondition_failed` y la UI espera los 35 min («Sin noticias»). No es nuevo
  ni grave; se documenta. Por eso `omitida.json` se escribe con `printf` (FR-33).
- **FR-15 (`ops-status.json`)** CUANDO el auxiliar acepte una petición DEBERÁ escribir en `BACKUP_STATUS_DIR/ops-status.json` (`0644`, desde un temporal del
  **mismo** directorio y `mv` atómico) `{"schema":1,"accion":"copia","id":…,"pedida_epoch":…,"resultado":"aceptada"}`. SOLO `aceptada` escribe: ninguna
  petición rechazada, ni siquiera la firmada, puede borrar el rastro de la que está en marcha.
- **FR-16 (listado)** `backup.sh` DEBERÁ escribir, tras la retención y de forma atómica, `BACKUP_STATUS_DIR/copias.json` (`0644`): `{"schema":1,"copias":[…]}`
  con hasta **30** entradas, las más recientes, solo de `backup_*` con manifiesto válido, cada una con `id` (`backup-YYYYMMDD_HHMMSS`), `creada_epoch`, `bytes`,
  `fuera_del_disco` (bool) y `verificada` (bool). **Sin rutas, sin nombres de fichero y sin hashes.** Excluye `update_*` y `rollback-safety_*` (dictamen §5.8).
  El listado es **informativo y no autoritativo**: una historia futura que restaure no podrá confiar en él (C-8).
- **FR-17 (retención)** La retención NO cambia (14 días, protegida por referencia viva, `backup-334.md`). Esta historia no ofrece borrar copias.

### 4.4 La aplicación (capa fina, §3.1)

- **FR-18 (configuración)** `config.py` DEBERÁ declarar `ops_socket_file` (`/run/zascarr-ops/ops.sock`), `ops_key_file` (`/run/zascarr-ops/ops.key`),
  `ops_status_file` (`/run/backup-status/ops-status.json`) y `copias_file` (`/run/backup-status/copias.json`); el compose los inyecta. Sin `os.environ` directo.
- **FR-19 (cliente)** Un servicio `services/ops_host.py` (lógica única; el router es fino) DEBERÁ construir la petición (`id = secrets.token_hex(16)`,
  `creada = int(time.time())`), firmarla con `hmac`/`hashlib`, conectar por `asyncio.open_unix_connection` con **tiempo total de 5 s**, leer ≤ 512 bytes y
  devolver un valor de enum `CodigoOps` (en `models/__init__.py`, junto a `OpsAccion`). SI el socket o la clave faltan, no son accesibles, hay *timeout*, la
  respuesta es ilegible o su `id` no es el enviado, ENTONCES devolverá `no_disponible`. **No lanzará excepciones al router, no usará dependencias nuevas
  y no registrará la clave, la firma ni el cuerpo.**
- **FR-20 (ruta de pedir)** DEBERÁ existir `POST /ui/copias/pedir` (router `web/copias.py`) **sin campos de formulario** (el cuerpo se ignora; nada de `Form`
  libre) que devuelva el bloque de copias actualizado como fragmento HTMX. Está protegida por el Origen/Sesión del middleware existente. **No habrá ninguna
  ruta equivalente bajo `/api/*`** (E-7). Con `auth_mode = none` la ruta funciona (decisión del PO nº 2, BR-04).
- **FR-21 (ruta de estado)** DEBERÁ existir `GET /ui/copias/estado` (fragmento) que lea **solo** `status.json`, `ops-status.json`, `omitida.json` y `copias.json`: sin base de
  datos y sin tocar el disco de la biblioteca. CUANDO haya una copia en curso, **solo el fragmento de estado** se refrescará con `hx-trigger="every 5s"`; si no la hay, **no hay sondeo**.
  El fragmento sondeado **no incluye** el `<details>` «Copias guardadas» (se carga una vez y tras pedir/terminar) y la zona `aria-live` que anuncia el cambio **queda fuera de lo que htmx
  recambia** (UX). No se toca el subtítulo «cada 10 segundos» de `/estado`. No se añade nada a `/api/health` (es público).
- **FR-22 (estados de la UI)** El fragmento DEBERÁ resolver el estado así (se evalúa de arriba abajo):

  | Condición | Estado que ve la persona | Botón |
  |---|---|---|
  | `ops.sock` inexistente o inaccesible | «No activado en este equipo» (§9) | no hay botón |
  | `omitida.json` con `omitida_epoch ≥ pedida_epoch` y `last_attempt_at_epoch < pedida_epoch` (la copia pedida no arrancó: había otra tarea) | «No se pudo hacer la copia: había otra tarea en marcha» (§9) | habilitado |
  | `ops-status.pedida_epoch` existe y `status.last_attempt_at_epoch < pedida_epoch` y han pasado ≤ 35 min | «Copia en marcha» | deshabilitado |
  | idem pero han pasado > 35 min | «Sin noticias de la copia» (§9) | habilitado |
  | `last_attempt_at_epoch ≥ pedida_epoch` y `status = ok` | «Copia hecha a las HH:MM y comprobada» | habilitado |
  | idem y `status = degraded` | «Copia hecha, con un aviso: <causa>» | habilitado |
  | idem y `status = failed` | «La copia falló: <causa>» | habilitado |
  | sin `ops-status` | último estado diario de siempre | habilitado |

  Las **causas** salen de un mapa cerrado (el de `api/health.py` más `precondition_failed`), y **cada causa lleva su acción corta** (§9.2). Un código que la app no conoce se pinta
  El mapa causa → (texto, acción) vive en **un solo sitio** (`services/ops_host.py::CAUSAS_COPIA`); `_BACKUP_ERRORES` de `api/health.py` conserva la frase corta de `/api/health`. Una **prueba de
  completitud** (AC-45) exige que **todo** código que los scripts pueden escribir y todo el de `_BACKUP_ERRORES` tenga fila en §9.2 (o la acción genérica) y que no sobre ninguna; `status_write_failed`
  figura como **reservado, no emitido** (ningún script lo escribe: cuando no se puede escribir el estado, `backup.sh` hace `die` y solo queda el diario).
  «causa desconocida» y la acción genérica; **nunca se pinta una cadena libre de un fichero** (C-13). La hora de «Copia hecha» se pinta **en la zona horaria configurada en la instalación**
  (`TZ` **del servidor**, no la del navegador ni la del equipo ni UTC; UX lo confirmó en v1.2) y, si no es de hoy, con el día («ayer a las 23:10», «el 4 de noviembre a las 23:10»).
- **FR-23 (bloque de copias en `/estado`)** DONDE el auxiliar esté disponible, el bloque «Copias de seguridad» de `/estado` DEBERÁ mostrar la frase de entrada,
  el botón, el estado (FR-22) y, en `<details>` «Copias guardadas (n)», el listado de `copias.json` (fecha, tamaño, «también en el disco de respaldo: sí/no»).
  El botón deshabilitado (copia en marcha) DEBERÁ quedar enlazado por `aria-describedby` al texto que explica por qué (UX). SI `copias.json` falta o no se puede leer, mostrará
  «Aún no hay lista de copias» y no fallará. Ubicación: bloque «Copias de seguridad» de `/estado` (Q-2, **de acuerdo con UX**).
- **FR-24 (la app, antes de enviar)** MIENTRAS el estado sea «Copia en marcha», `POST /ui/copias/pedir` NO enviará petición al auxiliar y devolverá el
  estado actual (el botón deshabilitado es comodidad; esto es la garantía).
- **FR-25 (registro de la app)** La app DEBERÁ registrar con `structlog` solo `ops.copia_pedida` con `id` y `codigo`, y `ops.no_disponible` con la clase del
  error. Nunca la clave, la firma, la petición, rutas ni el contenido de los ficheros de estado (§5.4).

### 4.5 Instalación, clave y unidades

- **FR-26 (instalador)** DEBERÁ existir `scripts/instalar_ops.sh`, idempotente, con `--dry-run` y `--yes`, solo para root, en el estilo de `instalar_backup.sh`. Hará:
  comprobar `python3` (≥ 3.9) y `systemctl`, **abortando sin instalar nada** si faltan; crear `OPS_DIR` (`root:<grupo>` `0750`); **crear `ops.key` solo si no existe**
  (32 bytes aleatorios, escritura atómica, `0440 root:<grupo>`, **sin imprimirla nunca**); copiar el auxiliar a `/usr/local/lib/zascarr/zascarr-ops` (root,
  `0755`; se copia, no se ejecuta desde el árbol del repositorio, para que un `git merge` no lo cambie en pleno uso); instalar `zascarr-ops.socket` y `zascarr-ops@.service`
  desde `deploy/systemd/`; `systemctl enable --now zascarr-ops.socket`. Con una segunda ejecución no cambia la clave ni deja duplicados. `--quitar` retira unidades y
  auxiliar y conserva la clave salvo `--quitar --borrar-clave`.
  Tras instalar `tmpfiles.d` ejecutará `systemd-tmpfiles --create` (no basta con esperar al arranque; SecOps v1.1 M-4a).
- **FR-27 (refresco)** `update.sh` DEBERÁ, SI el auxiliar ya está instalado, volver a copiar el auxiliar y las unidades solo cuando su hash cambie y reiniciar el socket; SI no
  está instalado, NO lo instalará y escribirá una línea informativa («Puedes activar "Hacer una copia ahora": sudo bash scripts/instalar_ops.sh»). (Q-5.)
- **FR-28 (compose)** `docker-compose.yml` DEBERÁ añadir **un único** volumen `${ZASCARR_DATA_DIR:-/var/lib/zascarr}/ops:/run/zascarr-ops:ro` y las variables de FR-18. NO añadirá
  `docker.sock`, `privileged`, `cap_add`, servicios ni cambios de `read_only`. SI el directorio `ops` no existe, la app DEBERÁ arrancar igual y mostrar «No activado en este equipo».
- **FR-29 (unidad del auxiliar)** `zascarr-ops@.service` DEBERÁ llevar al menos: `StandardInput=socket`, `StandardOutput=socket`, `StandardError=journal`,
  `NoNewPrivileges=yes`, `ProtectSystem=strict` con `ReadWritePaths=` solo `BACKUP_STATUS_DIR` y `/run/zascarr-ops`, `ProtectHome=yes`, `PrivateTmp=yes`, `PrivateNetwork=yes`,
  `RestrictAddressFamilies=AF_UNIX`, `MemoryMax=64M`, `TimeoutStartSec=15s`; y `CapabilityBoundingSet=` reducido a lo mínimo que permita iniciar la unidad (valor exacto a
  fijar y comprobar en la Pi, P-5). Sin presumir de que lo haga seguro: root con acceso a systemd sigue siendo root (C-14). Puntos que **P-5 debe verificar** (SecOps M-4, B-2):
  (a) `/run/zascarr-ops/` lo crea `tmpfiles.d` (`d /run/zascarr-ops 0700 root root`, instalado por `instalar_ops.sh`) o `RuntimeDirectory=` con `RuntimeDirectoryPreserve=yes` (sin
  `Preserve`, la carpeta se borraría al parar cada instancia `Accept=yes`); (b) con `ProtectSystem=strict` `/run` es de solo lectura fuera de `ReadWritePaths`: el cerrojo se abre
  **solo en lectura y sin `O_CREAT`** (FR-11); (c) `systemctl` habla con `/run/systemd/private` y funciona con `PrivateNetwork=yes`; (d) `Requires=docker.service` en la unidad de copia
  hace que `start` pueda **arrancar Docker** si está parado; SI Docker no puede arrancar, la unidad **no llega a lanzar `backup.sh`**: no hay `status.json` nuevo ni `omitida.json`, y la UI cae en «Sin noticias» a
  los 35 min (FR-22). No es un fallo de precondición del script; se documenta; (e) **saturación del socket**: quien
  tenga el grupo puede abrir `MaxConnections` conexiones ociosas (5 s cada una) o superar el límite de activaciones, tras lo cual systemd deja el socket en `failed` y la app muestra
  «No activado»; solo afecta al propio grupo y a la disponibilidad; `TriggerLimitIntervalSec`/`TriggerLimitBurst` y `Restart` se fijan en P-5 y se documenta en el ADR.
- **FR-30 (diario del auxiliar)** Por cada conexión escribirá **una** línea en el diario: `accion=<…|-> id=<…|-> uid=<número del par, SO_PEERCRED> resultado=<…> codigo=<…> ms=<n>`.
  Nunca el cuerpo, la firma, la clave, rutas, `docker compose config`, `set -x` ni `env` (C-13).

### 4.6 Pruebas (CI sin systemd)

- **FR-31 (diseño probable)** El auxiliar DEBERÁ ser un único fichero Python de **solo biblioteca estándar**, con una función pura
  `procesar(linea: bytes, ahora: int, clave: bytes, estado: EstadoOps, lanzador) -> Respuesta` y un `main()` mínimo que lee `stdin`/escribe `stdout`; `lanzador` y
  los relojes se inyectan para probar sin systemd (Q-4).
- **FR-32 (paridad de protocolo)** DEBERÁ existir una prueba que compare la app y el auxiliar en: lista de acciones, lista de códigos, orden de la firma, límites (512 B, 120 s, purga a 300 s, 300 s entre copias, 6 por 24 h) y la ruta del cerrojo — mismo patrón que `test_credenciales_lista.py` — para que no diverjan.

### 4.7 Trazas de lo omitido y causas desconocidas (añadido en v1.1)

- **FR-33 (`omitida.json`)** CUANDO `backup.sh` encuentre el cerrojo ocupado (FR-14 paso 2) DEBERÁ escribir, con `printf` (**no `jq`**: debe poder escribirse aunque falte `jq`), de forma atómica (temporal + `mv`) y con `|| true`, `BACKUP_STATUS_DIR/omitida.json`
  (`0644`) con `{"schema":1,"omitida_epoch":…,"motivo":"operacion_en_curso"}` y salir con 75 **sin tocar `status.json` ni `ops-status.json`**. Es el **único** escritor de ese fichero y no
  rompe la regla de que solo el auxiliar escribe `ops-status.json` (resuelve A-3 y deja traza de la copia diaria omitida, M-2b; **quién escribe el «pedida y no arrancó»: Q-12**).
  La UI lo usa en FR-22 (fila «no arrancó») y, además, muestra en el bloque una línea «La copia de la noche del <día> se omitió: había otra tarea en marcha» cuando `omitida_epoch` es
  más reciente que `last_attempt_at_epoch` y no corresponde a una petición.
- **FR-34 (`api/health.py`)** `_BACKUP_ERRORES` DEBERÁ incluir `precondition_failed` («no se pudo preparar la copia») y un código **no mapeado** DEBERÁ pintarse «causa desconocida» en lugar de
  la cadena del fichero (hoy `.get(error, error or …)` la devuelve tal cual por un endpoint público; `api/health.py:157`; B-3). Las pruebas que fijen el comportamiento anterior
  (`test_health.py`, `test_estado_copia_fallida.py`) se adaptan.

---

## 5. Reglas de negocio

- **BR-01** «Hacer una copia ahora» es **la misma copia** que la diaria (misma unidad, mismas verificaciones, mismo destino, misma retención). Nada nuevo que pueda salir distinto.
- **BR-02** No toca la biblioteca, el `.env`, las credenciales, el puerto ni la exposición.
- **BR-03** La petición no lleva datos de la persona ni de la biblioteca; no se sube nada.
- **BR-04** *(decisión del PO nº 2)* **Pedir copia puede ir sin contraseña**; el daño máximo es ocupar disco y está **acotado de verdad** por FR-10: 300 s entre copias **y 6 por 24 h**
  (≈ 84 dumps por 14 días de retención, más los diarios; A-2), además de la comprobación de espacio que `backup.sh` ya hace por dump. Con `auth_mode = none`, cualquier proceso local podría
  lanzarla igualmente; **se documenta** (ADR 0018, `SECURITY.md`, y una línea en el `<details>` del bloque) y la petición se firma con HMAC en todos los casos.
- **BR-05** Mientras hay una operación en marcha no se acepta otra (FR-11…FR-13). La app avisa; la autoridad es el cerrojo.
- **BR-06** Ningún texto de cara a la persona dice «exit code», «token», «socket», «HMAC» ni códigos internos; el vocabulario técnico va solo en `<details>`.

## 6. Requisitos no funcionales (la Pi, 512 MB)

- **NFR-01 (RAM del auxiliar)** Vive solo lo que dura la conexión (< 1 s); sin proceso residente. Objetivo: pico ≤ 30 MiB RSS por instancia (**hipótesis, NOT RUN**), `MemoryMax=64M`.
- **NFR-02 (copiar con la app sirviendo)** Una copia pedida con la app atendiendo una rejilla no deberá provocar muerte por OOM (sin entradas `oom-kill` en `dmesg`) ni
  hacer que `/api/health` tarde más de su margen (`_EXTERNAL_CHECK_TIMEOUT_S`, 3 s). Es la misma carga que la copia de las 04:00 pero con tráfico: **se mide en la Pi** (P-4).
- **NFR-03 (latencia)** Respuesta del auxiliar ≤ 1 s en el 95 % de los casos (local; **hipótesis**). La copia en sí la mide `backup.sh`.
- **NFR-04 (dependencias)** Cero dependencias nuevas: la app usa `asyncio`, `hmac`, `hashlib`, `secrets`; el auxiliar, la biblioteca estándar de `python3` del host.
- **NFR-05 (sin red)** Ni la app (más allá del socket Unix) ni el auxiliar (`PrivateNetwork=yes`) abren conexiones de red nuevas.
- **NFR-06 (sondeo)** Sin sondeo permanente: `every 5s` solo mientras hay copia en curso (FR-21).

---

## 7. Criterios de aceptación (Given / When / Then)

**Canal y validación**

- **AC-01** *Dado* el auxiliar con clave y reloj válidos y `zascarr-backup.service` inactivo, *cuando* llega una petición firmada de `copia`, *entonces* responde `aceptada`, systemd inicia
  `zascarr-backup.service` y `ops-status.json` contiene el `id` y `pedida_epoch`. (FR-02…FR-09, FR-15)
- **AC-02** *Cuando* la firma es errónea, ausente o de otra clave, *entonces* `firma_invalida`, no se inicia ninguna unidad, `ops-status.json` no cambia y el diario lleva una línea sin cuerpo ni firma. (FR-03, FR-15, FR-30)
- **AC-03** *Cuando* `creada` es de hace 10 min, de hace 121 s o de dentro de 121 s, *entonces* `caducada`; con 120 s exactos *entonces* se acepta. (FR-05)
- **AC-04** *Cuando* se reenvía una petición ya aceptada (mismo `id`), *entonces* `repetida` y la unidad no se inicia otra vez. (FR-06)
- **AC-05** *Cuando* la petición tiene una clave extra, una clave repetida, un tipo erróneo, un array en vez de objeto, JSON inválido, binario, 513 bytes o 1 MB, o no acaba en `\n`,
  *entonces* `esquema_invalido` y el auxiliar no lee más de 513 bytes. (FR-02)
- **AC-06** *Cuando* llega firmada una `accion` `restaurar`, `actualizar`, `copia ` (con espacio), `COPIA`, `../x` o vacía, *entonces* `accion_no_disponible` y no se inicia nada. (FR-07)
- **AC-07** *Cuando* `OPS_LOCK_FILE` está tomado (otra copia, el temporizador, `update.sh`), *entonces* `operacion_en_curso`. (FR-11)
- **AC-08** *Cuando* dos peticiones válidas llegan a la vez, *entonces* solo una produce `aceptada` y se hace **una** copia (la otra, `operacion_en_curso` o `demasiado_pronto`). (FR-10, FR-11)
- **AC-09** *Cuando* se acepta una copia y 299 s después llega otra válida, *entonces* `demasiado_pronto`; a los 300 s, `aceptada` (si no hay copia en marcha). (FR-10)
- **AC-34** *Cuando* ya hay 6 copias aceptadas en las últimas 24 h y llega otra válida (pasados 300 s de la última), *entonces* `limite_diario` y no se inicia nada; al salir la más antigua de la
  ventana, se acepta; tras un reinicio del equipo el contador vuelve a 0. (FR-10; *tope propuesto, decide el PO: Q-11*)
- **AC-10** *Dado* un entorno envenenado en el proceso del auxiliar (`BRANCH`, `BACKUP_DIR`, `ENV_FILE`, `REPO_DIR`, `PATH` ajeno), *cuando* se acepta una copia, *entonces* el entorno con el que se inicia
  la unidad **no contiene** ninguna de esas variables (el auxiliar lanza con entorno vacío) y la unidad usa solo `/etc/default/zascarr`. (FR-09)
- **AC-11** *Dado* un usuario del host **fuera del grupo**, *cuando* intenta conectar a `ops.sock` o leer `ops.key`, *entonces* `EACCES`; el socket es `root:<grupo>` `0660`, `OPS_DIR` `0750` y `ops.key` `0440`. (FR-01, FR-26)
- **AC-12** *Dado* el auxiliar con `ops.key` ausente o corrupta, *cuando* llega cualquier petición, *entonces* `no_disponible` y una línea `clave_ausente` en el diario. (FR-03)

**La aplicación**

- **AC-13** *Dado* `ops.sock` inexistente (auxiliar no instalado, directorio `ops` ausente), *cuando* se abre `/estado`, *entonces* la página responde 200, **no hay botón** y se lee «No activado en este equipo» más el `<details>`. (FR-22, FR-28)
- **AC-14** *Dado* el auxiliar disponible, *cuando* se pulsa el botón, *entonces* se envía **una** petición firmada, el fragmento muestra «Copia en marcha», el botón queda deshabilitado y se refresca cada 5 s. (FR-19…FR-22)
- **AC-15** *Cuando* el auxiliar no contesta en 5 s, cierra sin responder, contesta basura, un `id` distinto o más de 512 B, *entonces* la ruta responde 200 con «No se pudo pedir la copia» y registra `ops.no_disponible`; **nunca** 500. (FR-19)
- **AC-16** *Cuando* se hace `POST /ui/copias/pedir` desde otro origen, *entonces* 403 del middleware; con contraseña activada y sin sesión, redirección a `/login`; y `POST /api/copias/pedir` (o cualquier `/api/…` equivalente) **no existe** (404/405). (FR-20)
- **AC-17** *Dado* `auth_mode = none` y mismo origen, *cuando* se pulsa el botón, *entonces* se pide la copia sin contraseña, y el `<details>` dice que cualquier persona con acceso a este equipo puede hacerlo. (BR-04)
- **AC-18** *Dado* «Copia en marcha», *cuando* se fuerza un `POST` a mano, *entonces* **no** se envía petición y se devuelve el estado actual. (FR-24)
- **AC-19** *Dado* `pedida_epoch` de hace 36 min sin que `last_attempt_at_epoch` lo alcance, *entonces* «Sin noticias de la copia» y el botón vuelve a estar habilitado. (FR-22)
- **AC-20** *Dado* un `status.json`, `ops-status.json`, `omitida.json` o `copias.json` con cadenas largas, HTML, códigos desconocidos, tipos erróneos o épocas en el futuro, *entonces* la UI muestra solo textos
  del catálogo («causa desconocida» para lo no conocido), no pinta ninguna cadena del fichero y no falla. (FR-22, C-13)
- **AC-21** *Cuando* el listado trae 30 copias, *entonces* se muestran fecha, tamaño y «fuera del disco» por copia, sin ruta ni hash; con el fichero ausente o corrupto, «Aún no hay lista de copias». (FR-16, FR-23)

**Cerrojo, copia y estado**

- **AC-22** *Dado* el cerrojo tomado por **otro proceso**, *cuando* se ejecuta `update.sh`, `rollback.sh`, `restaurar_datos.sh`, `probar_restauracion.sh` o `backup.sh`, *entonces* salen con código 75 y el
  mensaje en llano **sin tocar nada** (ni el árbol, ni los dumps, ni `status.json`; **única excepción:** `backup.sh` escribe `omitida.json`, FR-33); y ni el temporizador de las 04:00 ni el restore mensual dejan su unidad en `failed` (`SuccessExitStatus=75` en las dos). (FR-12, FR-13)
- **AC-23** *Dado* que falta una precondición de `backup.sh` (por ejemplo, `.env` ilegible) y un `status.json` previo con `last_success_at_epoch` bueno, *cuando* se ejecuta, *entonces* `status.json`
  pasa a `failed` con `precondition_failed`, **conserva** `last_success_*` y la UI dice «La copia falló: ZascArr no pudo prepararla» con su acción (§9.2). (FR-14, M-1)
- **AC-24** *Dado* `ops-status.json` con una copia pedida y un `status.json` posterior `ok`, *entonces* la UI dice «Copia hecha a las HH:MM y comprobada». (FR-22)
- **AC-33** *Dado* un `update.sh` real (o una prueba de script que lo reproduzca) que ya tiene el cerrojo, *cuando* invoca `probar_restauracion.sh --dump`, *entonces* este **no** sale con 75 y
  se ejecuta; con el descriptor 9 ausente o apuntando a otro fichero, el hijo toma el cerrojo por su cuenta; con el cerrojo en manos de **otro** proceso, sale con 75. (FR-12.2, A-1)
- **AC-35** *Dado* que el cerrojo lo toma otra operación entre la comprobación del auxiliar y el arranque de `backup.sh`, *cuando* `backup.sh` sale con 75, *entonces* escribe `omitida.json`, **no**
  toca `status.json` ni `ops-status.json`, y la UI deja de decir «Copia en marcha» **sin esperar a los 35 min** y muestra «No se pudo hacer la copia: había otra tarea en marcha». (FR-33, A-3)
- **AC-36** *Dado* un `status.json` previo bueno, *cuando* `backup.sh` sale 75 por cerrojo, *entonces* `status.json` queda **byte a byte igual**; y *cuando* falla una precondición, conserva `last_success_*`. (FR-14, M-1)
- **AC-37** *Dado* un `OPS_LOCK_FILE` o `BACKUP_LOCK_FILE` definido en `/etc/default/zascarr` **sin** `ZASCARR_PRUEBAS=1`, *entonces* los scripts y el auxiliar siguen usando `/run/zascarr-ops.lock`; y la
  ruta coincide en `_cerrojo.sh` y en el auxiliar (T-17). (FR-12.1, M-3)
- **AC-38** *Dado* un `status.json` con un código de error desconocido, *entonces* `/api/health` devuelve «causa desconocida», y con `precondition_failed` devuelve «no se pudo preparar la copia». (FR-34, B-3)
- **AC-39** *Dado* un `id` aceptado con `creada = T+120`, *entonces* sigue contando como visto hasta T+300 y su reenvío en T+240 da `repetida`. (FR-06, B-1)
- **AC-40** *Dada* una copia hecha a las 23:10 del día anterior en la zona configurada, *entonces* la UI dice «ayer a las 23:10»; con `TZ` distinta de UTC y de la del equipo, la hora y el «ayer» cambian
  según la zona configurada (prueba con dos zonas en torno a medianoche). (FR-22, UX)
- **AC-41** *Entonces* el fragmento sondeado no contiene el `<details>` del listado; la zona `aria-live` no está dentro del contenedor recambiado; el botón deshabilitado tiene `aria-describedby` hacia su
  explicación; y el subtítulo «cada 10 segundos» de `/estado` no cambia. (FR-21, FR-23, UX)
- **AC-42** *Entonces* una prueba estática comprueba que `backup.sh`, `update.sh`, `rollback.sh`, `restaurar_datos.sh` y `probar_restauracion.sh` **no lanzan nada en segundo plano** (sin `&` final de orden,
  `nohup`, `disown`, `setsid` ni `coproc`; la prueba **excluye** `&&`, `2>&1`, `>&2` y `&>`, que no lanzan nada en segundo plano, para no dar falsos positivos), para que ningún hijo sobreviva al padre reteniendo el cerrojo. (FR-12.5, SecOps v1.1 A-1)
- **AC-43** *Dado* un `aceptadas` corrupto, con tipos erróneos o con épocas **más de 300 s** en el futuro, *cuando* llega una petición válida, *entonces* `no_disponible`, `contador_ilegible` en el diario, el fichero **no se reescribe** y no
  se inicia nada; con `aceptadas` ausente se trata como vacío y se acepta; con épocas **hasta 300 s** en el futuro se interpreta con normalidad (tolerancia de reloj). (FR-10)
- **AC-44** *Dado* que `backup.sh` (o cualquiera de los otros cuatro) se lanza sin ser root, *entonces* imprime «Ejecuta con sudo: …», sale con código 1 y **no** muestra un error crudo de bash. (FR-12.6)
- **AC-45** *Entonces* una prueba exige que **todo** código de error que los scripts pueden escribir (extraídos de `backup.sh`/`_comun.sh`: `escribir_estado`, `OFFSITE_ERROR`, `ANCHOR_ERROR`, `VERIFY_ERROR_CODE` **y los que escribe `on_exit` con la variable de fase: `precondition_failed` y `unexpected`**, que no aparecen como literal en `escribir_estado`) y todo
  el de `_BACKUP_ERRORES` tenga fila en `CAUSAS_COPIA`/§9.2 y que no sobre ninguna, con `status_write_failed` como único «reservado»; y que un código fuera de la tabla caiga en la acción genérica. (FR-22, SecOps v1.1 P-5)

**Instalación y compose**

- **AC-25** *Cuando* se ejecuta dos veces `instalar_ops.sh --yes`, *entonces* `ops.key` conserva su contenido, no hay unidades duplicadas y la segunda ejecución no cambia nada; con `--dry-run` no se escribe nada; sin `python3` aborta antes de crear nada; la clave no aparece en la salida. (FR-26)
- **AC-26** *Dado* el compose de la historia, *entonces* no contiene `docker.sock`, `privileged`, `cap_add` ni `network_mode: host`; el volumen `ops` es `:ro`; la app arranca sin el directorio. (FR-28)
- **AC-27** *Cuando* se reinicia el equipo o el socket (`systemctl restart zascarr-ops.socket`), *entonces* no se ejecuta ninguna petición anterior y el botón sigue funcionando **sin reiniciar el contenedor**. (FR-06, E-5; P-6)
- **AC-28** *Dado* el auxiliar instalado y un `update.sh`, *cuando* las unidades o el auxiliar del repositorio cambiaron, *entonces* se refrescan y el socket se reinicia; si no estaba instalado, solo se imprime la línea informativa. (FR-27)

**Registro, texto y coste**

- **AC-29** *Dado* un centinela en clave, firma, cuerpo y ruta, *entonces* no aparece en el diario del auxiliar, en la salida de `instalar_ops.sh`, ni en los registros de la app. (FR-25, FR-30)
- **AC-30** *Entonces* el bloque cumple el presupuesto de texto: frase de entrada ≤ 20 palabras, ≤ 50 palabras visibles antes de la primera acción, garantía junto al botón, 14 px mínimo (`test_web_css_contraste`),
  sin «exit code», «token», «socket» ni «HMAC» fuera de `<details>`; los textos coinciden con el catálogo de §9; y el «5 minutos» de `demasiado_pronto` sale de la **constante** (300 s ÷ 60), no escrito a mano. (BR-06)
- **AC-31** *Entonces* `procesar` de la app y del auxiliar coinciden en acciones, códigos, firma y límites (FR-32), y las pruebas de §8 pasan con el directorio temporal en el mismo dispositivo que `/` (CLAUDE.md §8).
- **AC-32** *(NOT RUN hasta medir)* En la Pi, con la app sirviendo una rejilla, una copia pedida cumple NFR-01, NFR-02 y NFR-03. (P-4)

---

## 8. Casos de prueba

**Pruebas adversas obligatorias** (dictamen §6, adaptadas al socket; las de «enlace simbólico, FIFO, enlace duro y sustitución» **desaparecen porque ya no hay ficheros de petición**; se dice
en el ADR):

| # | Caso | Esperado | Dónde |
|---|---|---|---|
| T-01 | firma errónea, ausente, repetida | `firma_invalida` / `repetida` | unitaria sobre `procesar` |
| T-02 | petición de hace 10 min / 121 s / futuro 121 s / 120 s | `caducada` / aceptada | unitaria (reloj inyectado) |
| T-03 | acción fuera de lista, mayúsculas, espacio, `../`, vacía | `accion_no_disponible` | unitaria |
| T-04 | 513 B, 1 MB, sin `\n`, JSON inválido, binario, clave repetida | `esquema_invalido`, lectura ≤ 513 B | unitaria + `socketpair` |
| T-05 | dos peticiones concurrentes | una `aceptada`, una rechazada, **un** `start` | integración (lanzador falso con cuenta) |
| T-06 | cerrojo tomado por un `flock` externo | `operacion_en_curso` | integración con fichero temporal |
| T-07 | entorno envenenado | lanzador recibe `env={}` salvo `PATH` | unitaria (el lanzador captura `env`) |
| T-08 | cliente con servidor `asyncio.start_unix_server` en proceso | formato real de línea; `no_disponible` ante *timeout*/basura/`id` distinto | integración |
| T-09 | `ops-status.json`: solo `aceptada` escribe; rechazada firmada no lo pisa | contenido intacto | unitaria |
| T-10 | `status.json`, `ops-status.json`, `omitida.json` y `copias.json` con HTML, cadena larga, código desconocido, tipos erróneos o época futura | solo catálogo | unitaria + render |
| T-11 | `copias.json` con 31 entradas, ruta en un campo, tipos erróneos | ≤ 30, sin rutas, sin fallo | unitaria |
| T-12 | `backup.sh`: cerrojo ocupado → 75, `omitida.json`, `status.json` intacto; precondición → `failed/precondition_failed` con `last_success_*` conservado; orden cerrojo → último éxito → trap → requisitos | AC-22/23/35/36 | `tests/test_backup_script.py` ampliada (dos regresiones: una por caso) |
| T-13 | los otros 4 scripts con cerrojo ocupado por otro proceso → 75; **`update.sh` → `probar_restauracion.sh` con cerrojo heredado → no 75** (AC-33) | 75 / ok | pruebas de script con `ZASCARR_PRUEBAS=1` y `OPS_LOCK_FILE` temporal |
| T-14 | texto de la unidad: claves de endurecimiento presentes; `SuccessExitStatus=75`; `systemd-analyze verify` si existe | — | prueba estática (se salta si falta la herramienta) |
| T-15 | compose sin `docker.sock`/`privileged`/`cap_add`; volumen `ops:ro` | — | prueba de compose existente, ampliada |
| T-16 | centinela de secretos en registros y salida del instalador | no aparece | unitaria + shell |
| T-17 | paridad de protocolo app↔auxiliar **y de constantes**: acciones, códigos (con `limite_diario`), orden de la firma, límites (512 B, 120 s, 300 s de purga, 300 s entre copias, 6/24 h) y **ruta del cerrojo** entre `_cerrojo.sh`, el auxiliar y la app | iguales | unitaria (FR-32) |
| T-18 | `instalar_ops.sh` idempotente, `--dry-run`, sin python3 | AC-25 | prueba de shell con raíz falsa |
| T-19 | tope diario: 6 aceptadas, la 7.ª `limite_diario`; poda de la ventana; contador a 0 al reiniciar | AC-34 | unitaria (reloj inyectado) |
| T-20 | `/api/health` con código desconocido y con `precondition_failed` | AC-38 | `test_health.py` |
| T-21 | zona horaria: «ayer a las 23:10» con dos `TZ` **fijadas explícitamente en la prueba** (p. ej. `Europe/Madrid` y `America/Mexico_City`), nunca la del equipo que ejecuta la CI | AC-40 | unitaria de render |
| T-22 | estructura del fragmento: sin `<details>` en el sondeado, `aria-live` fuera, `aria-describedby` | AC-41 | prueba de plantilla |
| T-23 | `aceptadas` ausente / corrupto / futuro > 300 s: vacío / `no_disponible` sin reescribir; futuro ≤ 300 s: se interpreta | AC-43 | unitaria |
| T-24 | los cinco scripts sin ser root → mensaje en llano, código 1 | AC-44 | prueba de script |
| T-25 | prueba estática de «nada en segundo plano», con las exclusiones `&&`, `2>&1`, `>&2`, `&>` | AC-42 | `tests/` (grep de las cinco órdenes) |
| T-26 | completitud de la tabla de causas contra los scripts y `_BACKUP_ERRORES` | AC-45 | unitaria |

**Se prueba a mano / en la Pi** (NOT RUN, §11): activación por socket de systemd, `SocketGroup`/`SocketMode` reales, `connect()` a través de un montaje `:ro`, lectura de `ops.key` por grupo desde
el contenedor, reinicio del socket sin reiniciar el contenedor, `systemctl start --no-block` sobre una unidad `oneshot` ya activa, efecto de `SuccessExitStatus=75`, y todas las mediciones de NFR.

## 9. Textos de cara a la persona (catálogo cerrado; revisados por UX en v1.1)

### 9.1 Estados y mensajes

| Código / estado | Texto |
|---|---|
| Frase de entrada (≤ 20 palabras) | «ZascArr guarda una copia de tus datos cada noche. Puedes hacer una ahora.» (15) |
| Botón | «Hacer una copia ahora» (neutro, no `.primary`) |
| Garantía, junto al botón | «No toca tus tebeos: solo copia lo que ZascArr tiene anotado.» |
| Copia en marcha | «Copia en marcha. Puede tardar unos minutos.» (+ «Puede ir algo más lento mientras tanto» **solo si P-4 lo mide**) |
| Hecha | «Copia hecha hoy a las 10:35 y comprobada.» / «…ayer a las 23:10…» / «…el 4 de noviembre a las 23:10…» (zona configurada, FR-22) |
| Con aviso / fallo | «Copia hecha, con un aviso: …» / «La copia falló: …», cada causa con su acción (§9.2) |
| `operacion_en_curso` | «ZascArr está haciendo otra tarea de mantenimiento. Espera a que termine.» |
| `demasiado_pronto` | «Acabas de pedir una copia. Prueba otra vez dentro de **5 minutos**.» (el número sale de la constante, AC-30) |
| `limite_diario` *(UX v1.2)* | «Has pedido ya el máximo de copias en un día. La de esta noche se hará igualmente; prueba otra vez más tarde.» |
| `no_disponible`, `firma_invalida`, `caducada`, `repetida`, `esquema_invalido`, `accion_no_disponible` | «No se pudo pedir la copia. Inténtalo otra vez; si sigue igual, avisa a quien instaló ZascArr. Mira Estado, arriba.» (misma frase; el código va al diario, no a la pantalla) |
| La copia pedida no arrancó (`omitida.json`) | «No se pudo hacer la copia: había otra tarea en marcha. Vuelve a pedirla cuando termine.» |
| Copia diaria omitida (FR-33) | «La copia de la noche del <día> se omitió: había otra tarea en marcha.» |
| Sin noticias (> 35 min) | «No hay noticias de la copia. Revisa el resumen de arriba; si no dice nada, avisa a quien instaló ZascArr.» |
| Sin auxiliar | «Hacer copias desde aquí no está activado en este equipo. Las copias de cada noche siguen funcionando.» |
| Listado | «Copias guardadas (n)»; por copia: fecha, tamaño y «también en el disco de respaldo: sí/no» |
| `<details>` | Rótulo **«Para quien instaló ZascArr»**: «Para activarlo, en el equipo donde corre ZascArr: `sudo bash scripts/instalar_ops.sh`. Sin contraseña en ZascArr, **cualquiera que pueda abrir ZascArr** puede pedir una copia. Una copia solo ocupa disco; no cambia nada más.» |

### 9.2 Causas de fallo, cada una con su acción corta (propuesta; UX la revisa)

| Código(s) de `status.json` | Texto «causa → qué hacer» |
|---|---|
| `offsite_mount_missing` | «El disco de respaldo no está conectado. Conéctalo y vuelve a pedir la copia.» |
| `offsite_same_device` | «El disco de respaldo es el mismo que el de los datos. Avisa a quien instaló ZascArr.» |
| `offsite_copy_failed` | «No se pudo guardar en el disco de respaldo. Comprueba que tiene sitio y vuelve a probar.» |
| `offsite_verify_failed`, `anchor_sync_failed` | «La copia en el disco de respaldo no salió bien. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.» |
| `disk_full` | «No hay sitio en el disco. Libera espacio y vuelve a pedir la copia.» |
| `pg_dump_failed` (también si no se pudo medir el espacio: base parada o disco sin montar) | «ZascArr no pudo leer sus datos. Prueba otra vez dentro de unos minutos.» |
| `gzip_invalid`, `header_missing`, `tables_missing`, `decompress_failed`, `empty`, `not_found`, `verify_failed` (la copia **sí** se descartó) | «La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.» |
| `manifest_failed` (la copia **existe y es válida**; falta anotarla, también si falla el manifiesto del disco de respaldo) | «La copia se hizo, pero no se pudo anotar. Avisa a quien instaló ZascArr.» |
| `status_write_failed` | **Reservado, no emitido** por ningún script (solo está en `api/health.py`): cae en la acción genérica; la situación real («copia hecha, estado no escrito») solo se ve en el diario |
| `precondition_failed` | «ZascArr no pudo preparar la copia. Avisa a quien instaló ZascArr.» |
| `unexpected` o código desconocido | «No se sabe por qué falló. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.» |

*Regla de UX:* «avisa a quien instaló ZascArr» solo donde la persona no puede actuar (desconexión del disco, espacio y reintentos sí los puede hacer ella).


## 10. Riesgos

| # | Riesgo | Mitigación en esta historia | Residual |
|---|---|---|---|
| R-1 | **Quien comparta el grupo de la app (suite *arr comprometida) puede conectar y firmar** (A-1 no realizable al pie de la letra; E-5) | Acción única `copia`; **300 s entre copias y 6 por 24 h** (≈ 84 dumps en 14 días); espacio comprobado; lista cerrada; el auxiliar no ejecuta nada suyo | **Acotado a ocupar un volumen finito de disco y algo de CPU.** Para restaurar/actualizar es inaceptable sin G-1 |
| R-2 | Reloj del host y del contenedor distintos ⇒ `caducada` | Mismo reloj (contenedor comparte el del núcleo); mensaje genérico; diario con el código | Bajo |
| R-3 | Socket obsoleto tras recrear el directorio (bind de directorio ≠ bind de fichero) | El volumen es el **directorio**, estable; el socket se recrea dentro (AC-27, P-6) | A medir |
| R-4 | `precondition_failed` cambia el contrato de `status.json` | Código nuevo y mapeado; `schema` sigue en 1 | Bajo |
| R-5 | El cerrojo único hace que `update.sh` rechace durante una copia y que **una copia diaria o el restore mensual se omitan** si chocan con otra operación | Mensaje en llano, código 75, `SuccessExitStatus=75` en ambas unidades y traza (`omitida.json` para la copia; diario para el restore); `Persistent=true` **no** repone la omitida | Cambio de comportamiento a anunciar; sin recuperación automática (Q-6) |
| R-6 | Una copia pedida llena el disco de datos | `backup.sh` mide espacio antes de volcar (E-1) **y** el tope de FR-10 limita cuántas pueden pedirse | Bajo |
| R-7 | `python3` ausente en el host | `instalar_ops.sh` aborta sin instalar; la UI dice «No activado» | Verificar en la Pi (P-1) |
| R-8 | La clave se filtra a una copia de seguridad del directorio de datos | `ops.key` vive en `OPS_DIR`; `backup.sh` hace `pg_dump`, no copia ficheros del directorio | Verificar que ninguna otra copia lo recoge |
| R-9 | Que alguien amplíe el canal (más acciones) sin revisión | FR-07: la tabla vive en código y un valor nuevo exige cambiar `v` o el código; §13 | Proceso |
| R-10 | `update.sh` copia el auxiliar desde el repositorio y reinicia el socket: **el código del auxiliar pasa a ser lo que diga el remoto** (B-4) | Misma confianza que `update.sh` ya exige como root; el repositorio es de root (ADR 0012); el ADR 0018 lo dice y entra en C-12 de la historia de actualizar | Aceptado, documentado |
| R-11 | Saturación del socket por un miembro del grupo (B-2) | `MaxConnections`, `TriggerLimit*`, tiempo de lectura de 5 s; P-5 | Solo disponibilidad, solo del grupo |
| R-12 | Un miembro del grupo agota las 6 copias y deja el botón inservible hasta 24 h (SecOps v1.1 A-2) | Solo disponibilidad; la copia nocturna sigue; el contador ilegible falla cerrado y no se reinicia (FR-10); tolerancia de reloj de 300 s; el ADR 0018 anota la recuperación (borrar `/run/zascarr-ops/aceptadas` como root) | Aceptado, documentado |

**Riesgo residual global (para escribirlo en el ADR tal cual):** un proceso con el grupo del usuario de servicio puede pedir copias a ritmo limitado. No obtiene root arbitrario, ni rutas libres, ni el socket
de Docker, ni el `.env`.

## 11. NOT RUN y supuestos

**Nada de esto se ha ejecutado:** ni systemd, ni el socket, ni los scripts, ni la Pi, ni una copia pedida.

- **P-1** `python3` (versión) y systemd (versión; `Accept=yes`, `SocketGroup`, `MaxConnections`) en la Pi. *Supuesto:* Raspberry Pi OS los trae.
- **P-2** `connect()` a un socket Unix a través de un montaje `:ro` del directorio. *Supuesto:* Linux lo permite (el modo de solo lectura del montaje no impide `connect`). Si falla, se monta con escritura el directorio **de root `0750`**, que la app no puede modificar por permisos.
- **P-3** Comportamiento de `systemctl start --no-block` con la unidad `oneshot` ya activa y de `SuccessExitStatus=75`.
- **P-4** Mediciones: RAM pico del auxiliar y de la copia con la app sirviendo; `dmesg` sin OOM; `/api/health` durante la copia; duración de la copia.
- **P-5** Revisión de SecOps de `zascarr-ops@.service` y del auxiliar: valor de `CapabilityBoundingSet`, `ReadWritePaths`, y los puntos (a)–(e) de FR-29 (`/run/zascarr-ops`, apertura de solo lectura del cerrojo, `systemctl` con `PrivateNetwork=yes`, `Requires=docker.service`, saturación del socket).
- **P-6** El contenedor lee `ops.key` por grupo (E-5) y sigue conectando tras `systemctl restart zascarr-ops.socket`.
- **P-7** Quién corre realmente cada servicio de la suite *arr en esa Pi (el dictamen tampoco lo comprobó; condiciona el alcance real de R-1).
- **Supuesto:** el grupo del usuario de servicio tiene nombre resoluble; si no, se usa el GID numérico en `SocketGroup=`.
- **Supuesto:** `escribir_estado` del `trap` puede ejecutarse antes de `comprobar_requisitos` porque usa solo variables definidas en las líneas 25-37 y `|| true` ya cubre sus fallos; el implementador lo comprueba.

## 12. Decisiones para el PO (lista corta; recomendación primero)

| # | Decisión | Recomendación | Alternativa |
|---|---|---|---|
| **Q-1** | **A-1:** la clave no separa a la app de otros procesos del mismo grupo (hace falta que la app la lea). ¿Se acepta para `copia`? | **Sí**, con el riesgo residual escrito en el ADR y **G-1 como puerta de entrada** de restaurar/actualizar (§13). | Exigir ya un UID propio para la app (cambio grande de ADR 0012; fuera de esta historia) |
| **Q-2** | ¿Dónde va el botón? | **Bloque «Copias de seguridad» de `/estado`** (ya hay una fila ahí; se pinta en servidor). Botón neutro, no `.primary`. UX decide. | Ajustes (no es una opción de configuración) |
| **Q-3** | Intervalo mínimo entre copias pedidas | **300 s** (y tope diario, Q-11) | 60 s, o sin límite (solo el cerrojo) |
| **Q-4** | Lenguaje del auxiliar | **Python 3 estándar** (permite firma sin la clave en `argv`, límites de lectura y pruebas unitarias) | bash + `jq` + `openssl`: la clave iría en la línea de órdenes, visible en `ps` ⇒ **descartada** |
| **Q-5** | Quién instala y refresca | **`instalar_ops.sh` explícito** + `update.sh` refresca solo si ya está instalado (FR-27) | Instalarlo siempre desde `bootstrap.sh`/`update.sh` (más cómodo, menos explícito) |
| **Q-6** | Cerrojo único en los cinco scripts ahora | **Sí**, con herencia padre→hijo, ruta constante y `SuccessExitStatus=75` en copia y restore (v1.1). Cambia el comportamiento (R-5): una copia diaria omitida **no se repone sola**; queda traza | Solo `backup.sh` y la comprobación del auxiliar (deja M-2 sin cerrar) |
| **Q-7** | Listado de copias en esta historia | **Sí** (FR-16; es solo lectura y lo pide el encargo) | Aplazarlo a la historia 3 |
| **Q-8** | ADR **0018** («Operaciones del host desde la interfaz»: canal, postura, riesgo residual, R-10, R-11 y R-12, y que ya no hay pruebas de enlace/FIFO por no haber ficheros) y línea en `SECURITY.md` | **Sí**, en la misma PR (CLAUDE.md §3.1.5) | — |
| **Q-9** | Sondeo `every 5s` solo mientras hay copia en curso | **Sí** | Botón «Actualizar» manual |
| **Q-10** | Rotar la clave | **Fuera de esta historia**; procedimiento manual documentado (`instalar_ops.sh --quitar --borrar-clave` y reinstalar) | Opción en el instalador |
| **Q-11** | **Tope de copias pedidas por 24 h** (propuesta de SecOps A-2; decide el PO) | **≤ 6 por 24 h además de 300 s** (≈ 84 dumps en 14 días) | Intervalo mínimo ≥ 1 h (24/día, ≈ 336 dumps) · o retención que cuente aparte las manuales (toca `aplicar_retencion`) |
| **Q-12** | **Quién escribe el «pedida y no arrancó»** (A-3; decide el PO) | **`backup.sh` escribe `omitida.json`**, un fichero **aparte** que no es `ops-status.json` (FR-33); sirve también para la copia diaria omitida | La UI comprueba que la unidad estuvo activa (la app no puede leer el estado de systemd) · o `backup.sh` escribe en `ops-status.json` (rompe «solo el auxiliar escribe ahí») |
| **Q-13** | ¿`limite_diario` dice cuándo se podrá volver a pedir (HH:MM)? *(opcional de UX)* | **No ahora**: exigiría un número más en la respuesta del auxiliar (cerrada) y en la paridad (T-17); el texto ya dice «prueba otra vez más tarde» | Añadir `reintentar_epoch` a la respuesta |

## 13. Canal preparado para las historias siguientes (sin ampliarlo)

La historia 1 **no define** campos, códigos ni acciones de restaurar o actualizar: `accion` ≠ `copia` se rechaza (FR-07) y las claves desconocidas se rechazan (FR-02). Lo que **sí** deja
fijo y reutilizable: socket, `v`, firma, caducidad, un solo uso, orden de comprobación, límite, cerrojo único, `ops-status.json`, diario y unidad endurecida. Ampliarlo exigirá un `v` nuevo o un cambio
revisado del auxiliar, **no** un valor en configuración.

**Puertas de entrada de las historias 3 y 4 (no se especifican aquí):**
- **G-1** Una prueba que solo la persona pueda dar (contraseña reintroducida **verificada por el auxiliar o por un proceso que el grupo compartido no controle**), porque la firma no basta (Q-1).
- **G-2** La resolución del identificador de copia contra la lista que el **auxiliar** construye, nunca contra `copias.json` (C-8); y la prueba previa de A-4/C-10 con base desechable.
- **G-3** El camino de restauración de producción (C-9) y la revisión del compose traído (C-12) con su propio dictamen.
- *(v1.4)* **Estado de G-1:** la parte que toca a **Ajustes** —que cambiar la contraseña, el usuario, el modo o la dirección exija la contraseña actual— está **cumplida** por BL-OPS3 (#508, `services/reautenticacion.py` y `services/seguridad.py`, fusionada). La comprobación **por el auxiliar** (BL-OPS2 FR-12) sigue **sin construir**.

## 14. Trazabilidad con el dictamen

| Condición | Cómo queda | Dónde |
|---|---|---|
| A-1 / C-3 | **Parcial:** HMAC sí; «solo root y contenedor» no (Q-1) | FR-03, R-1 |
| A-2 / C-1 / C-2 | `copia` sin contraseña por decisión del PO; solo `POST /ui/*`; nada en `/api/*`; reautenticación no aplica a `copia` | FR-20, BR-04, AC-16/17 |
| C-4 | Socket de systemd (opción A); sin escritura de root en directorios que la app pueda modificar | FR-01, FR-15 |
| C-5 | Esquema cerrado, 120 s, un solo uso, purga por `tmpfs`; lenguaje con lectura acotada | FR-02, FR-05, FR-06, Q-4 |
| C-6 / M-2 | Cerrojo único, rechazo y no cola | FR-11…FR-13 |
| A-1, A-2, A-3, M-1…M-4, B-1…B-4 del dictamen de v1.0 | Ver §15 | FR-06, FR-10, FR-11, FR-12, FR-14, FR-29, FR-33, FR-34 |
| Dictamen sobre v1.2 (B-1 y dos notas de implementación) | Ver §15 (v1.3) | FR-10, FR-12.6, AC-42, AC-43, AC-45, T-23, T-25, R-12 |
| Dictamen sobre v1.1 (A-1 nota, A-2 condiciones, Q-12, FR-29d, P-1…P-5) y revisión de UX | Ver §15 (v1.2) | FR-10, FR-12.5…12.7, FR-14, FR-22, FR-26, FR-29, FR-33, AC-42…AC-45, R-12, Q-13 |
| C-7 / M-4 | Entorno vacío, argumentos fijos, unidad por nombre | FR-09 |
| C-8 / B-1 | `copias.json` informativo y no autoritativo; solo `backup_*` | FR-16, G-2 |
| C-13 / B-3 | Códigos y números; mapa cerrado; diario sin rutas ni firma | FR-22, FR-25, FR-30 |
| C-14 / B-4 | Unidad endurecida | FR-29 |
| M-1 | Desaparece (no hay ficheros) | FR-01 |
| M-6 | Corregido en las entradas: la app no es `read_only` | §2 |
| C-9…C-12, M-3, M-5, A-3, A-4 | **No aplican a la historia 1** (restaurar/actualizar/aviso) | §13 |

## 15. Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| v1.0 | 2026-11-06 | Primera versión. Contrastada con `c48b1ff`. Q-1…Q-10 abiertas; ninguna bloquea redactar el plan de construcción salvo Q-1 (riesgo residual) y Q-2 (ubicación del botón, que UX debe validar). |
| **v1.1** | 2026-11-06 | Integra el dictamen de SecOps y la revisión de UX. **A-1** → FR-12.2 (herencia del descriptor 9 padre→hijo) + AC-33 + T-13; **A-2** → FR-10 (tope 6/24 h, código `limite_diario`), BR-04, R-1, R-6, AC-34, T-19, Q-11 (*propuesta, decide el PO*); **A-3** → FR-11 corregido (la carrera la cubre FR-33), FR-33 (`omitida.json`), FR-22 (fila «no arrancó»), AC-35, Q-12; **M-1** → FR-14 (orden cerrojo → último éxito → trap → requisitos, fase `preparacion`), AC-23/36; **M-2** → `SuccessExitStatus=75` también en `zascarr-restore.service` (FR-12.4), traza de la copia omitida (FR-33), R-5; **M-3** → ruta constante del cerrojo (FR-12.1), AC-37, T-17; **M-4** → FR-29 (a)–(e), P-5; **B-1** → purga a 300 s (FR-06), AC-39; **B-2** → FR-29(e), R-11; **B-3** → FR-34, AC-38, T-20; **B-4** → R-10. **UX:** Q-2 de acuerdo (`aria-describedby`, AC-41); Q-9 de acuerdo con las tres condiciones (FR-21, AC-41); textos de §9 sustituidos y causas con acción (§9.2); día y zona horaria en «Hecha» (FR-22, AC-40); «5 minutos» desde la constante (AC-30). Los AC nuevos (AC-33…AC-41) van junto a su tema, no al final. Sin cambios: FR-01…FR-05, FR-07, FR-09, FR-13, FR-15…FR-20, FR-24…FR-28, FR-30…FR-32. |
| **v1.2** | 2026-11-06 | Integra la pasada de SecOps sobre v1.1 y la revisión de UX. **A-1 (nota)** → FR-12.5 + AC-42 + T-25 (prueba estática de que los cinco scripts no lanzan nada en segundo plano; `9>&-` si algún día); **A-2** → FR-10: `aceptadas` ilegible ⇒ `no_disponible` y nunca a 0, ausente ⇒ vacío (AC-43, T-23); R-12 y ADR 0018 anotan que el grupo puede agotar las 6 y dejar el botón inservible 24 h; **Q-12** conforme (`omitida.json` aparte); **FR-29(d)** corregido (si `systemctl start` no lanza el script, no hay estado ni `omitida.json`: «Sin noticias» a los 35 min); **P-1** → AC-22 con la excepción de `omitida.json`, escrita con `printf` (FR-33); **P-2** → FR-12.6 + AC-44 + T-24 (sin root: «Ejecuta con sudo», código 1); **P-3** → nota en FR-14 (sin `jq` no hay `precondition_failed`); **P-4** → `omitida.json` en AC-20 y T-10 (tipos erróneos, cadenas largas, época futura); **P-5** → AC-45 + T-26 + `CAUSAS_COPIA` como fuente única (FR-22); M-3 (opinión) → FR-12.7 (aviso del override); M-4a → FR-26 (`systemd-tmpfiles --create`). **UX/SecOps:** zona horaria = `TZ` del servidor, fijada explícitamente en T-21 (FR-22); `limite_diario` con el texto de UX y HH:MM aplazado (Q-13); §9.2: `pg_dump_failed`, `offsite_verify_failed`+`anchor_sync_failed` separados de «comprueba que tiene sitio», `precondition_failed`, **`manifest_failed` separado** («La copia se hizo, pero no se pudo anotar…»; la copia existe), **`status_write_failed` reservado** y fuera del grupo «se descartó», que queda solo con los siete códigos de `verificar_dump`. Sin cambios en el resto. |
| **v1.3** | 2026-11-06 | Retoque mínimo de SecOps sobre v1.2. **B-1** → FR-10: tolerancia de reloj de 300 s para las épocas futuras de `aceptadas` (más allá, ilegible ⇒ falla cerrado) y el ADR 0018 recoge la recuperación (borrar `/run/zascarr-ops/aceptadas` como root); AC-43, T-23, R-12. **Nota 1** → AC-45 extrae también `precondition_failed` y `unexpected` (los escribe `on_exit` con la variable de fase). **Nota 2** → AC-42/T-25 excluyen `&&`, `2>&1`, `>&2` y `&>`; FR-12.6 usa `exec 9>… || die`. Sin otros cambios. |
| **v1.4** | 2026-11-12 | **Reconciliación con `main` (`ac108e2`), sin cambios de comportamiento salvo FR-12.** ADR **0015 → 0018** (0015, 0016 y 0017 ocupados; E-12, Q-8, FR-10, R-10, BR-04) · **cerrojo en `scripts/_cerrojo.sh`** (FR-12, FR-12.8, AC-37, T-17, §1; E-14: `restaurar_datos.sh` no usa `_comun.sh`; desviación aceptada por el PO) · E-6 (compose con `no-new-privileges` y `pids: 256`), E-13 (scripts y `deploy/` sin cambios desde `b1a9000`; imagen en trixie, sin efecto en OPS), E-15 (nuevas secciones de `/estado`) · §13: G-1 cumplida en su parte de Ajustes (BL-OPS3). Migraciones 0030 y 0031 ocupadas: **esta spec no nombra ninguna**. Sin otros cambios. |
