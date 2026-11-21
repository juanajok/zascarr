# SecOps — Revisión adversarial de la integración final de OPS4 (#443)

**Rol:** SecOps · **Fase:** revisión adversarial de solo lectura del SHA final de la rama.
**Fecha:** 2026-11-21 (Europe/Madrid).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443`, rama `feat/ops4-seguridad-443`.
**SHA revisado (árbol limpio):** `ff49a7fcde25a9ea087da121e3c67b464faef0e9` (`git status --porcelain` vacío).
**Base frente a `origin/main`:** `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9` (96 commits).
**Entorno:** venv de pruebas del repo (Python 3.14, pytest 9.2, ruff 0.17.5); la imagen de
producción es `python:3.11-slim` y `pyproject.toml:5` exige `>=3.11`. Sin `TEST_DATABASE_URL`,
sin Docker, sin systemd instalado, sin Pi.

**Objeto:** `src/zascarr/web/actualizacion.py`, `src/zascarr/web/templates/estado.html`,
`src/zascarr/services/{autorizacion_actualizacion,clave_autorizacion,solicitud_actualizacion_v4,actualizacion_transporte_v4,ops_actualizacion_v4}.py`,
`deploy/ops/{zascarr_actualizar_aux,protocolo_actualizar_v4_ops4,verificador_autorizacion_ops4,registro_repeticiones_ops4,admision_v4_actualizar_ops4}.py`,
`scripts/instalar_actualizacion_ops4.sh` y `deploy/systemd/zascarr-actualizar*`.
Se revisó también el contexto que decide la puerta (`config.py`, `main.py`, `web/estado.py`,
`services/runtime_settings.py`, `services/auth.py`, `services/reautenticacion.py`,
`docker-compose.yml`, `scripts/update.sh`, `scripts/_cerrojo.sh`, `scripts/instalar_ops.sh`).

**Restricciones respetadas:** no se editó código, plantillas, unidades, instalador ni compose; no se
hizo commit ni push; no se ejecutó Docker, Pi, systemd instalado, socket real ni `update.sh`. **El
único fichero escrito es este informe.** La actualización sigue **DESHABILITADA por defecto**.
Este dictamen **no aprueba habilitar ni desplegar** OPS4.

---

## 0. Veredicto

1. **Hallazgos P0: ninguno.** Con el valor por defecto y sin una acción explícita de root, no he
   encontrado una ruta que ejecute `update.sh`, ni un bypass de la puerta de UI, ni una fuga de
   contraseña/clave/testigo, ni un replay práctico. El estado deshabilitado está bien
   cimentado (§2) y se puede mantener.
2. **Integrar (fusionar) el incremento con la función deshabilitada: GO CON CONDICIONES.**
   Las condiciones CM-1…CM-4 de §5.1 son de contrato/documentación (pequeñas) y deben quedar
   resueltas en este mismo cambio o antes de fusionarlo. No hay defecto explotable mientras la
   bandera siga apagada y el instalador no se ejecute con `--activar`.
3. **Habilitar (sacar la UI del 404, arrancar el socket, ejecutar el `update.sh` real):
   NO-GO.** Bloqueado por P1-1…P1-9 (§4.1), además de las condiciones I-1…I-9 todavía abiertas
   de la revisión anterior (arnés real, Pi/VM con `update.sh` real, NTP/TTL, estado fiable,
   suite en 3.11, ADR y autorización explícita del PO). Nada de esto es una aprobación de
   despliegue.
4. **Dictamen del SHA final (§5.8 de CLAUDE.md):** este informe cubre exactamente `ff49a7fc`
   con árbol limpio. **Caduca** con cualquier commit, rebase o cambio de los ficheros de §7, y
   **solo es válido con la función deshabilitada**; no sustituye la revisión de habilitación.

---

## 1. Qué se ha revisado y cómo

- Lectura completa de los 18 ficheros del objeto, más los módulos y scripts que deciden la puerta,
  el grupo, el socket, el cerrojo y la reautenticación (ver cabecera).
- `git diff --stat origin/main...HEAD`, `git diff --check`: sin problemas de espacios; el árbol de
  trabajo no tiene cambios.
- Pruebas dirigidas y Ruff (§6). **No** se ejecutó la suite completa (instrucción de la tarea; no
  es evidencia de ella), **no** se ejecutó Python 3.11 en runtime, ni systemd real, ni Docker, ni
  la Pi, ni `update.sh`.
- Sondas de solo lectura: dry-run del instalador, `systemctl --root` (offline, sin tocar el
  systemd del host) para comprobar la semántica de `enable` sobre una unidad sin `[Install]`, y
  una llamada directa al transporte con respuestas del auxiliar (§6).
- Sondas sin red; no se ha escrito ningún fichero del repositorio fuera de este informe
  (solo temporales de pytest y de la sonda offline en `/tmp`).

---

## 2. Estado de «deshabilitado»: qué sostiene la garantía (verificado)

| Capa | Evidencia | Resultado |
|---|---|---|
| Bandera de producto | `ops4_actualizacion_habilitada: bool = Field(default=False)` (`../../src/zascarr/config.py:282`) | **OFF por defecto** |
| Ajustes en caliente | `_ALL_FIELDS` de `RuntimeSettingsService` es lista blanca y **no incluye** ningún campo `ops4_*` (`../../src/zascarr/services/runtime_settings.py:38-113, 223-240`) | La UI de Ajustes/BD **no puede** encenderla |
| Variables de entorno al contenedor | El servicio `zascarr` no usa `env_file:`; solo pasa variables listadas. Pasa `OPS_SOCKET_FILE`/`OPS_KEY_FILE` (OPS1) en `../../docker-compose.yml:157-158`, pero **ninguna `OPS4_*`** | Poner `OPS4_ACTUALIZACION_HABILITADA=true` en `.env` **no llega** al contenedor hoy |
| Botón de Estado | Con la bandera falsa, `estado` pasa `actualizacion_habilitada=False` (`../../src/zascarr/web/estado.py:51-54`) y la plantilla pinta el botón `disabled` sin `form` (`../../src/zascarr/web/templates/estado.html:15,24-25`) | **Inerte** |
| Ruta POST | `if not settings.ops4_actualizacion_habilitada: raise HTTPException(404)` antes de leer clave o reautenticar (`../../src/zascarr/web/actualizacion.py:52-53`); probado en `tests/test_ops4_ui_gate.py` y `tests/test_ops4_ui_actualizacion.py` | **404** |
| Sesión / origen | `AuthMiddleware` cubre `/ui/*` (cookie/Basic) y `_peticion_cross_site` rechaza POST de estado sin `Origin`/`Referer` en `/ui/` (`../../src/zascarr/services/auth.py:234-264, 635+`) | Sin sesión no hay POST; CSRF cubierto |
| Sistema de ficheros host | Nada en `bootstrap.sh` ni en `scripts/update.sh` invoca `instalar_actualizacion_ops4.sh`; `update.sh:224` solo refresca OPS1 | El instalador OPS4 **no** se ejecuta solo |
| Unidades | `zascarr-actualizar.socket` y `.service` sin `[Install]` (`../../deploy/systemd/zascarr-actualizar.socket:16`, `../../deploy/systemd/zascarr-actualizar.service:32`); el instalador sin `--activar` solo copia | No arrancan al boot |
| Cercojo/efecto real | `update.sh` no se ha modificado ni ejecutado; el auxiliar solo lo arranca tras verificar HMAC/testigo/consumo, y la unidad solo existe en disco si un root ejecutó el instalador | **No hay ejecución automática** |

**Conclusión §2:** en el estado por defecto del SHA `ff49a7fc`, la actualización **sigue
deshabilitada**, y además está doblemente cerrada: aunque un operador ponga la bandera en `.env`,
el contenedor no la recibe. Lo único que arma el host es ejecutar el instalador **con `--activar`**
(y con el grupo correcto); eso es una decisión de habilitación de root, no del producto.

**Matiz importante (ver P1-1):** el script y la documentación presentan `--activar` como «solo el
socket» y rematan con «la actualización sigue deshabilitada». Tras `--activar`, el host **sí**
queda armado: cualquier proceso del grupo que pueda leer la clave (el usuario de la app ya la lee
por el montaje `ops`) puede enviar una petición v4 válida y arrancar el `update.sh` real como root,
aunque la bandera de UI siga en `false`. La bandera de UI no es la única puerta.

---

## 3. Resumen por eje del encargo

| Eje | Resultado | Comentario |
|---|---|---|
| Bypass de UI/puerta | **PASS** (condicionado por P1-1) | La bandera no es seteable por UI/BD/`.env` del contenedor; ruta 404; sesión + origen + reautenticación; no hay GET que ejecute. |
| Manejo de clave/secreto | **PARCIAL — P1-3, P1-8** | Clave dedicada, `O_NOFOLLOW`, propietario/modo exactos, sin `repr` del testigo, sin logs de contraseña/testigo. Falla el grupo por defecto del instalador y el modelo de confianza (la app es depositaria de la clave). |
| Binding de socket | **PARCIAL — P1-3, P2-1** | Socket dedicado, `0660 root:<grupo>`, sin escritura para el grupo en el directorio; `PrivateNetwork`/`AF_UNIX` en el auxiliar. Falla el fallback al socket de OPS1 y el grupo por defecto `root`. |
| Orden cerrojo/testigo/consumo | **PASS en el orden; PARCIAL en atomicidad** | `procesar` hace esquema → firma → frescura → cerrojo → testigo → **consumo durable** → `systemctl start`. Consumo antes de efecto (bien). El cerrojo solo se **sondea** y se libera; no se transfiere (P2-2). |
| Replay | **PASS** | Frescura ±120 s, TTL app 60 s/host ≤300 s, ligadura testigo↔`id` de la petición firmada, marca `O_EXCL` + dos `fsync` en directorio persistente validado (`0700`, uid 0), no se borra si falla la sincronización. |
| Fallos de systemd | **PARCIAL — P1-2, P1-7** | Endurecimiento razonable; `enable --now` sin `[Install]`; `ReadWritePaths` exige que exista `/run/zascarr-ops.lock`; el sandbox bloquea pasos del `update.sh` real; fallos secundarios se tapan con `warn`. |
| Permisos de unidades | **PASS con matiz** | Unidades `0644` root; servicio `User=root`; auxiliar sin capacidades; socket root:grupo. El matiz es el grupo por defecto (P1-3) y que instalar la unidad de acción fija es, por sí mismo, preparar una ejecución root. |
| Inyección en installer | **PASS con matices** | Sin `eval`, `"$@"`, `install -D`, sustitución de plantillas con `patsub_replacement` desactivado y rechazo de marcadores sobrantes; sin rutas del cliente. Entradas de entorno (`ZASCARR_OPS4_DIR`/`OPS4_DATA_DIR`, `OPS4_GROUP`) son de root; no se validan formato absoluto/sin saltos de línea (P3). |
| Python 3.11 | **PASS estático / NOT RUN runtime** | `ast.parse(feature_version=(3,11))` OK en los 11 módulos; solo stdlib; `StrEnum` (3.11+), `zip(strict=)` (3.10+). La suite se ejecutó en 3.14, no en 3.11. |
| Riesgo de `update.sh` real | **ALTO (documentado; no ejecutado)** | La unidad ejecuta `/bin/bash /opt/zascarr/zascarr/scripts/update.sh --rama main` como root: fetch de `origin/main`, build, migraciones, recreación y health; sin fijación de S persistida. Sigue siendo una acción de root disparada por una petición con posesión de clave. |
| ¿Contradice que siga deshabilitada? | **Parcial** | Por defecto no. Pero `--activar` + grupo de app arma la ejecución real y los mensajes dicen lo contrario; `CLAUDE.md:101` dice «El contrato está aislado, sin conectar ni habilitar», y en este SHA ya está conectado (aunque apagado). P1-1 y CM-1. |

---

## 4. Hallazgos priorizados

### 4.1 P1 — bloquean la habilitación; varios deben corregirse/documentarse ya

#### P1-1 — `--activar` arma la ejecución real y el script lo presenta como «sigue deshabilitada»

- **Evidencia:** `GRUPO="${OPS4_GROUP:-${OPS_GROUP:-root}}"` (`../../scripts/instalar_actualizacion_ops4.sh:18`);
  con `--activar` hace `systemctl enable --now zascarr-actualizar.socket` (`:141`) y dice
  «Socket habilitado en esta máquina» (`:142`); después **siempre** imprime «La actualización
  sigue deshabilitada por defecto (OPS4_ACTUALIZACION_HABILITADA=false)» (`:149`). El prompt
  interactivo solo advierte «¿Provisionar OPS4 (sin habilitar la UI)?». El socket es
  `0660 root:<GRUPO>` (`../../deploy/systemd/zascarr-actualizar.socket:9-10`), y el contenedor
  monta `${ZASCARR_DATA_DIR}/ops` de solo lectura (`../../docker-compose.yml:210`), es decir, la
  app (usuario `zascarr`, grupo del servicio) **puede leer la clave y conectar**.
- **Impacto:** con `--activar` y el grupo correcto, cualquier proceso con acceso a la clave
  (el propio contenedor de la app tiene permiso de lectura del montaje `ops`, o una ejecución
  de código no autorizada en él) puede enviar
  una petición v4 firmada y que el host arranque `update.sh` real como root. La bandera de UI
  apagada no impide nada por el lado del host. La frase «sigue deshabilitada» induce a error en
  el momento más delicado (antes de armar una operación privilegiada).
- **Condición (CE-1):** antes de habilitar, `--activar` debe pedir una confirmación explícita e
  inequívoca («arma la ejecución real de scripts del repo como root; no hay vuelta atrás
  automática»), y el mensaje final debe distinguir «UI apagada» de «host armado». Recomendado
  además: no instalar ni arrancar las unidades en el mismo paso que provisiona la clave, o
  separar el «provisionar» del «armar».

#### P1-2 — `systemctl enable --now` sobre una unidad sin `[Install]`: no persiste y el mensaje es falso

- **Evidencia:** el socket no tiene sección `[Install]`
  (`../../deploy/systemd/zascarr-actualizar.socket:16`, y `tests/test_ops4_unidades.py:47-55`
  lo exige así); el instalador usa `enable --now` (`:141`) y anuncia «Socket habilitado» (`:142`).
- **Comprobación (sin tocar el systemd del host):** con `systemctl --root=<tmp> enable
  zascarr-actualizar.socket` (systemd 259 del host de revisión) el cliente devuelve **0** pero
  avisa: «The unit files have no installation config (…). This means they are not meant to be
  enabled or disabled using systemctl». En systemd más antiguos ese `enable` puede devolver
  código distinto de 0 y abortar el instalador (`set -euo pipefail`).
- **Impacto:** `--activar` como mucho **arranca** el socket en esa sesión; no queda habilitado
  tras un reinicio ni crea el enlace `.wants`. El mensaje y la doc (`ops4-instalador.md` §Comportamiento)
  prometen persistencia que la unidad no puede dar. La VM pudo ver el socket `LISTEN` porque
  `--now` lo arranca; eso no acredita persistencia.
- **Condición (CE-2):** o se usa `systemctl start` y el texto dice «iniciado, no persistente», o
  se añade `[Install] WantedBy=sockets.target` (y se actualizan los tests de contrato y la doc)
  si de verdad se quiere habilitar al boot. En ambos casos, la prueba estática del instalador
  debe casar el comando con el contrato de la unidad.

#### P1-3 — Grupo por defecto `root` en el instalador: la app no podrá leer/ni conectar (fail-closed), y el activar queda roto en silencio

- **Evidencia:** `GRUPO="${OPS4_GROUP:-${OPS_GROUP:-root}}"` (`:18`) y `OPS4_GROUP` **no aparece**
  en `docs/design/*.md`, `.env.example` ni el runbook; en cambio, OPS1 resuelve el grupo real del
  usuario de servicio desde `PGID` del `.env` y **nunca** usa root por defecto
  (`../../scripts/instalar_ops.sh:73-90, 158-164`; comentario explícito). La clave se crea
  `0440 root:${GRUPO}` (`:94`) y el socket `SocketGroup=@GRUPO@`
  (`../../deploy/systemd/zascarr-actualizar.socket:9`).
- **Impacto:** un operador que ejecute `sudo bash scripts/instalar_actualizacion_ops4.sh --activar`
  sin `OPS4_GROUP` deja la clave `0440 root:root` y el socket `0660 root:root`: el contenedor
  (`PUID/PGID` del `.env`, por defecto el usuario de sistema del host) **no puede leer la clave
  ni conectar**, y la ruta devuelve 503. Falla cerrado, pero es un activar-que-no-funciona sin
  diagnóstico, y contradice el patrón OPS1. No es escalada: root ya podía todo.
- **Condición (CE-3):** resolver el grupo como OPS1 (desde `PGID` del `.env`), abortar si no se
  resuelve, documentar `OPS4_GROUP` como escape, y añadir test del caso por defecto (hoy los
  tests solo pasan `OPS4_GROUP` explícito).

#### P1-4 — El auxiliar emite `operacion_en_curso` y el transporte de la app lo rechaza como «respuesta no válida»

- **Evidencia:** el auxiliar hace `return rechazo("operacion_en_curso", id_)`
  (`../../deploy/ops/zascarr_actualizar_aux.py:81`); el conjunto cerrado de la app
  `_CODIGOS` **no incluye** ese código
  (`../../src/zascarr/services/actualizacion_transporte_v4.py:25-32`), y `_interpretar` lo
  convierte en `RESPUESTA_INVALIDA` (`:110-126`). Sonda directa sobre el transporte con una
  respuesta `{"resultado":"rechazada","codigo":"operacion_en_curso"}` → **`respuesta_invalida`**
  (§6). El E2E de UI usa `admitir_v4` como servidor de prueba
  (`tests/test_ops4_ui_actualizacion.py`, `test_ruta_hasta_socket_real_con_consumo_durable`), no
  el `procesar` real del auxiliar, y `CodigoV4` tampoco genera ese código, por eso no se detecta.
- **Impacto:** cuando el host esté ocupado (copia/restauración/otra actualización en curso), el
  usuario verá «El host devolvió una respuesta no válida» en vez de «Hay otra operación en curso».
  No es de seguridad (falla cerrado) pero es una incongruencia real entre las dos mitades del
  contrato; es el síntoma de que la admisión está duplicada (P2-3).
- **Condición (CE-4):** añadir `operacion_en_curso` al conjunto cerrado y mapearlo a un mensaje de
  «ocupada»; añadir regresión que use la respuesta real del auxiliar (no solo `admitir_v4`);
  idealmente, que el auxiliar llame a una única función de admisión compartida.

#### P1-5 — El contenedor no recibe `OPS4_*` y la doc de activación da una ruta de clave equivocada

- **Evidencia:** `docker-compose.yml` no pasa `OPS4_ACTUALIZACION_HABILITADA`,
  `OPS4_AUTORIZACION_KEY_FILE` ni `OPS4_SOCKET_FILE` (solo OPS1 en `:157-158`); el servicio no
  usa `env_file:`. La app lee la clave en `/run/zascarr-ops/actualizar.key`
  (`../../src/zascarr/config.py:283`), que por el montaje `:210` corresponde a
  `/var/lib/zascarr/ops/actualizar.key` (lo que crea el instalador). Pero
  `docs/design/ops4-ui-integracion.md:11` documenta la clave por defecto como
  `/var/lib/zascarr/ops4/autorizacion.key` — **ruta que no está montada en el contenedor**.
- **Impacto:** (a) la activación documentada «poner `OPS4_ACTUALIZACION_HABILITADA=true`» **no
  funciona** hoy: hay que editar el compose o inyectar la variable; (b) quien provisione la clave
  donde dice la doc obtendrá 503 para siempre; (c) el `ops4_socket_file` tampoco es configurable
  desde `.env`. Para el estado deshabilitado es una salvaguarda, no un riesgo; para activar, un
  bloqueo.
- **Condición (CE-5):** actualizar la doc (ruta de clave correcta y dependencia del compose),
  decidir si se pasan las tres variables por compose cuando se habilite, y añadir a la doc de
  activación el orden exacto (clave → grupo → socket → bandera → compose), con comprobación
  `is-enabled`/`is-active`.

#### P1-6 — Contradicción entre la especificación «main» (contraseña viva en el host, estado persistente) y esta implementación

- **Evidencia:** `docs/design/ops4-especificacion-main.md:22` exige «Además de la reautenticación
  compartida en la app, el auxiliar verifica independientemente la contraseña contra
  `auth_mode`/`auth_password_hash` de la BD viva (…) HMAC solo acredita acceso a la clave
  compartida, no identidad de la persona: incluso una petición firmada exige la comprobación
  viva»; `:59` (AC-03) exige «HMAC válido sin contraseña correcta no inicia»; `:28` §8 exige
  estado host persistente con fases/HEAD0/S/resultado. El auxiliar revisado **no** hace
  comprobación viva (solo HMAC + testigo) y **no** escribe estado. La decisión de autoridad
  registrada el 2026-11-20 (`docs/design/ops4-concordancia-seguridad.md:3-8`, `CLAUDE.md:96-101`)
  sí deja la autoridad en la app, de modo que P1-6 es una contradicción **documental** entre dos
  documentos tracked, no un fallo de implementación contra la decisión vigente.
- **Impacto:** un revisor o auditor posterior puede leer AC-03 y concluir que el SHA no cumple
  los criterios de la propia spec; y la spec §8 no está cubierta por nada. Confunde el dictamen
  y la trazabilidad.
- **Condición (CE-6):** decidir cuál manda y dejar una única spec/ADR: o se actualiza
  `ops4-especificacion-main.md` (y su matriz) para reflejar la autoridad app + clave dedicada, o
  se implementa la comprobación viva y el estado. Hasta entonces, no puede declararse «AC-03
  cumplido».

#### P1-7 — El sandbox de `zascarr-actualizar.service` no encaja con todos los pasos del `update.sh` real

- **Evidencia:** la unidad corre `ExecStart=/bin/bash /opt/zascarr/zascarr/scripts/update.sh
  --rama main` con `ProtectSystem=strict`
  (`../../deploy/systemd/zascarr-actualizar.service:12,19`) y `ReadWritePaths=/opt/zascarr
  /var/lib/zascarr /var/backups/zascarr /run/zascarr-ops.lock` (`:30`).
  - El `update.sh` real, al final, lanza `bash "${SCRIPT_DIR}/instalar_ops.sh" --refrescar`
    (`../../scripts/update.sh:224`), que escribe en `/etc/tmpfiles.d`, `/etc/systemd/system` y
    `/usr/local/lib` y llama a systemctl: bajo `ProtectSystem=strict` **se deniega**; el
    `update.sh` lo tapa con `|| warn` (el fallo secundario no se convierte en fallo de la
    actualización, en contra del requisito de `ops4-especificacion-main.md:26` de no ocultar un
    fallo secundario como éxito completo).
  - `ReadWritePaths=/run/zascarr-ops.lock` exige que la ruta **exista**: systemd documenta
    (`systemd.exec(5)`) que las rutas de `ReadWritePaths=` sin prefijo `-` no se ignoran si
    faltan. Ese fichero lo crea al boot el tmpfiles de **OPS1**
    (`../../scripts/instalar_ops.sh:197-204`), que el instalador OPS4 **no** instala; la
    dependencia no está documentada. Si OPS1 no está instalado, la unidad no arranca (falla
    cerrado, pero rompe la feature).
  - `ProtectHome=yes` (`:20`) oculta `/root`, donde `git` guarda el `safe.directory`
    (`../../scripts/_comun.sh:117-130`); si el repo no es de root (instalaciones no estándar),
    el `update.sh` real puede morir en `comprobar_git_utilizable`. En la instalación estándar el
    repo es de root, así que no ocurre; queda como condición de instalación no estándar.
  - `probar_restauracion.sh --dump` (`../../scripts/update.sh:211`) escribe su estado en
    `/var/lib/zascarr/backup-status`, que **sí** está dentro de `ReadWritePaths`; ese paso
    debería funcionar. `PrivateTmp` cubre `/tmp`.
- **Impacto:** un `--activar` con el `update.sh` real podría terminar con la actualización hecha
  pero OPS1 sin refrescar y con un `warn` que no distingue «todo bien» de «secundario fallido»;
  y sin OPS1/tmpfiles, la unidad ni arranca. Todo falla cerrado; nada ejecuta de más.
- **Condición (CE-7):** antes de habilitar: (a) decidir explícitamente si el refresco OPS1 y la
  prueba de restauración son fallos duros o blandos y documentarlo; (b) garantizar
  `/run/zascarr-ops.lock` (prefijar `-` en `ReadWritePaths` **y** crear el fichero desde el
  instalador OPS4, o instalar el tmpfiles de OPS1 como dependencia declarada); (c) validar
  `update.sh` real bajo esta unidad en una VM aislada (NOT RUN hoy).

#### P1-8 — La clave que autoriza `update.sh` como root vive en el contenedor de la app: la reautenticación no es un factor independiente del host

- **Evidencia:** la app lee la clave dedicada (no la del auxiliar) en
  `../../src/zascarr/web/actualizacion.py:55-66` y firma petición + testigo con el mismo secreto
  de 32 bytes (`../../src/zascarr/services/autorizacion_actualizacion.py:96-132`,
  `../../src/zascarr/services/ops_actualizacion_v4.py:35-58`). El host solo verifica posesión de
  clave y consumo único (`../../deploy/ops/verificador_autorizacion_ops4.py:50-121`); **no**
  comprueba identidad (decisión de autoridad del 2026-11-20). El directorio `ops` con la clave
  se monta en el contenedor **siempre** (`docker-compose.yml:210`), no solo cuando se habilita.
- **Impacto:** una ejecución de código no autorizada en el contenedor (o una lectura de fichero
  arbitraria en `src/`) permite leer la clave y forjar una petición v4 completa. Con el socket
  arrancado (`--activar`), eso se traduce en `update.sh` real como **root** en el host; sin
  socket, no (fallo cerrado). Es el riesgo residual que la decisión del PO acepta al confiar en
  la app, pero «reautentico la contraseña» **no** añade un factor que el host pueda comprobar:
  el host no puede distinguir «la app reautenticó» de «quien tiene la clave». Compárese con OPS1,
  donde el host resuelve la restauración con verificación adicional (contraseña contra BD viva)
  y la clave sola no basta.
- **Condición (CE-8):** registrar en el ADR/limitaciones como riesgo residual aceptado; reducir
  superficie (montar `ops` solo cuando la función esté habilitada, o con `O_NOFOLLOW` ya
  cubierto; grupo mínimo; considerar secreto de ida y otro de vuelta; no rotar sin procedimiento);
  y que la decisión de habilitación lo incluya explícitamente. No es un defecto del código
  revisado, pero **sí** debe impedir que se describa la habilitación como «solo reautenticar en
  la app».

#### P1-9 — No hay estado durable de la operación ni reconciliación de `INCIERTA`/`aceptada`

- **Evidencia:** el auxiliar consume y hace `systemctl start --no-block`; devuelve
  `aceptada` (= admisión) y no escribe ningún estado
  (`../../deploy/ops/zascarr_actualizar_aux.py:62-104`). La unidad no declara `ExecStartPost` ni
  escritura de estado; los módulos `escritor_estado_actualizar_ops4.py`,
  `modelo_fases_actualizacion_ops4.py` y `ejecutor_actualizar_ops4.py` existen **desconectados**
  (`tests/test_ops4_aislamiento.py`). La UI solo muestra mensajes fijos, y `INCIERTA` dice «no
  vuelvas a intentarlo» pero no hay forma de consultar qué pasó
  (`../../src/zascarr/web/actualizacion.py:37-40`).
- **Impacto:** un `systemctl start` puede fallar después de responder «aceptada»; el usuario no
  puede distinguir «en curso», «terminada», «fallida» ni «sin noticias», en contra de la spec §8
  y de AC-07. Para una operación que puede dejar código/migraciones a medias, esto es una
  carencia de operación real, no un adorno.
- **Condición (CE-9):** antes de habilitar, conectar un escritor de estado persistente y
  atómico (fases, HEAD0/S, resultado, evidencia no sensible) y un lector en la app; definir la
  reconciliación manual tras `INCIERTA` (no relanzar a ciegas). Mientras eso no exista, la UI no
  debe prometer «se está preparando» sin estado que lo respalde.

### 4.2 P2 — endurecimiento y deuda, no bloquean la fusión deshabilitada

- **P2-1 — Fallback al socket de OPS1.** `actualizacion_transporte_v4.py:73-76` usa
  `ops4_socket_file` y, si falta o está vacío, cae a `ops_socket_file` (el de copias/restauración,
  `/run/zascarr-ops/ops.sock`). Viola la regla «socket dedicado, no se reutiliza el de
  copia/restauración» de `config.py:281` y de la doc. OPS1 rechaza la línea (`v=4` no es 1/2,
  `firma_de` v1 es texto y la clave es otra), así que no hay confusión explotable, pero el
  fallback no debería existir: si no hay socket v4 → `no_disponible`. Los tests
  (`tests/test_ops4_transporte_v4.py:24,135,171`) usan ese fallback para inyectar un socket
  falso; deben pasar `ops4_socket_file` explícito.
- **P2-2 — El cerrojo se comprueba y se suelta; no se retiene ni se transfiere.** El auxiliar
  hace `_cerrojo_ocupado()` y libera (`:137-151`); `update.sh` vuelve a tomar el cerrojo en el
  paso 0 (`scripts/update.sh:59` vía `_cerrojo.sh`). La ventana entre comprobación y adquisición está
  documentada en `ops4-especificacion-main.md:32-37`; el daño máximo es una unidad que arranca y
  muere con 75 (sin doble ejecución, porque la unidad es singleton y `update.sh` toma el
  cerrojo), pero dos IDs válidos distintos pueden consumirse y ambos recibir «aceptada». Para
  habilitar, reservar/iniciar de forma atómica (o mantener el fd 9 del cerrojo).
- **P2-3 — Admisión duplicada y no usada por el auxiliar.** `admision_v4_actualizar_ops4.py`
  implementa la admisión y solo la usan tests; el auxiliar la reimplementa inline en `procesar`
  (y su docstring dice que las guardas «siguen pendientes», ya no es cierto). Es la causa
  estructural de P1-4 (deriva de códigos). Unificar en una sola función/constantes de códigos.
- **P2-4 — DoS de la operación por el grupo/socket.** `MaxConnections=2` y
  `TriggerLimitIntervalSec=10s/TriggerLimitBurst=10`
  (`deploy/systemd/zascarr-actualizar.socket`) permiten que un miembro del grupo abra dos
  conexiones lentas (el auxiliar usa `os.read` bloqueante sin plazo propio; solo lo corta
  `RuntimeMaxSec=45s`) o provoque 10 activaciones en 10 s y deje el socket en `failed`. No es
  elevación (es el mismo grupo que ya puede leer la clave), pero es una vía de DoS del mantenimiento.
  Añadir plazo de lectura y un tope de fallos propio.
- **P2-5 — Retención/cuota y tope de emisiones.** Las marcas `autorizacion-<id>` son permanentes
  y no hay política de poda (Q-AUT-4) ni tope de emisiones (Q-AUT-8). Disco lleno deniega
  (correcto). Para habilitar, decidir retención/cuota y un tope de emisiones por sesión.
- **P2-6 — Sin rotación/revocación de clave.** No hay `kid` ni procedimiento de rotación; la doc
  lo reconoce (`ops4-instalador.md` §Límites). Al rotar, los testigos viejos caducan por TTL pero
  no hay invalidación explícita ni runbook. Añadir antes de habilitar.
- **P2-7 — Paridad de lectura de la clave.** El auxiliar exige exactamente `0440`
  (`zascarr_actualizar_aux.py:107-134`) y la app acepta `0400` o `0440`
  (`clave_autorizacion.py:30-31`). El instalador crea `0440`, así que hoy no hay problema, pero
  dos criterios distintos para el mismo secreto invitan a provisionar mal. Unificar.
- **P2-8 — Documentación desactualizada (M-4 recurrente).** `CLAUDE.md:101` dice «El contrato
  está aislado, sin conectar ni habilitar» y en este SHA ya hay ruta, transporte, auxiliar y
  unidades (apagados). `docs/design/ops4-auxiliar-unidad.md:75` dice «No hay instalador de estas
  unidades todavía» (sí lo hay). `docs/design/ops4-protocolo-v4.md` y `ops4-ui-integracion.md`
  siguen diciendo «no conectado a la UI/auxiliar/socket» y `ops4-ui-integracion.md:11` da la ruta
  de clave equivocada. Actualizar en el mismo cambio o con nota explícita; dejar una única fuente
  de verdad de activación.
- **P2-9 — `--quitar` conservador a medias.** Deshabilita/para el socket, pero no para instancias
  `zascarr-actualizar@*` en vuelo, no valida la clave existente al reinstalar («se conserva» sin
  comprobar modo/propietario) y no retira el fichero de socket si systemd no lo limpia. Falla
  cerrado; endurecer el runbook.
- **P2-10 — Sin runbook de activación completo.** No existe el orden exacto
  (grupo → clave → `OPS4_GROUP` → instalador → tmpfiles/cerrojo → socket → bandera → compose) ni
  la verificación posterior (socket `LISTEN` con el grupo correcto, `is-enabled`, 503/404,
  prueba de repetición y de cerrojo). Necesario antes de habilitar.
- **P2-11 — Mensajes/estado de la UI.** La ruta responde 200 con un fragmento `<p>` sin plantilla
  para todos los rechazos (`web/actualizacion.py:68-74`), y los mensajes son de una lista cerrada
  (bien, sin filtrar secretos). En una activación real conviene una página/fragmento con el
  estado y el siguiente paso; hoy no puede decir más que «aceptada/rechazada/incierta».
- **P2-12 — Entorno del instalador.** `ZASCARR_PRUEBAS=1` salta la comprobación de root y permite
  `OPS4_DEST_*` (`instalar_actualizacion_ops4.sh:19-24, 41-44`); es correcto para tests, pero un
  operador con esa variable en el entorno podría instalar en rutas no estándar. `DATA_DIR`/`GRUPO`
  van a plantillas de systemd sin validar formato absoluto/sin saltos de línea; solo root controla
  el entorno, así que el riesgo es bajo.

### 4.3 P3 / notas

- **Formato:** `ruff check` (CI) y `ruff check --select S` pasan; `ruff format --check` **no**
  (11 de los ficheros revisados se reformatearían). El CI no ejecuta `ruff format`, así que no
  bloquea; si el proyecto usa `make format`, hacerlo en un commit aparte sin mezclar.
- **Python 3.11:** sintaxis compatible (`ast.parse(feature_version=(3,11))` OK) y dependencias
  stdlib; la evidencia de ejecución es 3.14. Iniciar la suite/CI en 3.11 antes de habilitar
  (I-8).
- **Cambios de tests ajenos al objeto** en la rama (`tests/test_ensayo_f1bis_arnes.py`,
  `tests/test_lector_rar.py`, `tests/test_restaurar_produccion_pg.py`, `tests/test_restore_script.py`):
  son estabilizaciones y opt-in de PostgreSQL; no afectan a esta revisión, pero conviene que no
  se mezclen con el commit de integración final.
- **Secretos en la ruta:** no hay `logging`, `print` ni `repr` de contraseña/testigo en los
  módulos revisados; `PreparacionAutorizacion.autorizacion` es `repr=False`
  (`autorizacion_actualizacion.py:64-74`); no aparece el cuerpo del POST en logs de middleware.
- **Información revelada:** el 503 «La clave de actualización no está disponible» y el 404
  revelan el estado de aprovisionamiento a un usuario ya autenticado; riesgo negligible.
- **Sin caché explícita:** `/estado` en `GET` no lleva `Cache-Control` en la rama de la sección
  de actualización; no contiene secretos (solo el formulario vacío). El POST no se cachea.

---

## 5. Condiciones exactas

### 5.1 Para fusionar/integrar (CM) — con la función deshabilitada

- **CM-1 — No añadir cableado de activación en esta fusión:** no incluir el instalador OPS4 en
  `bootstrap.sh`/`update.sh`, no pasar `OPS4_*` por `docker-compose.yml`, no enlazar la bandera a
  Ajustes/BD. Verificado en `ff49a7fc`; mantenerlo. El merge no debe ejecutar `--activar` ni
  tocar la Pi.
- **CM-2 — Reconciliar documentación de contrato en el mismo cambio (o con nota explícita
  caducable):** `CLAUDE.md:101` («sin conectar ni habilitar»), `ops4-auxiliar-unidad.md:75`,
  `ops4-protocolo-v4.md` (estado «no conectado»), `ops4-ui-integracion.md:4,10-12` (ruta de clave
  y `OPS4_*`), y la relación con `ops4-especificacion-main.md:22,28,59` (§1.4 y P1-6). Una única
  frase de estado: «integrado en el árbol, deshabilitado por defecto; habilitar requiere
  CE-1…CE-12».
- **CM-3 — Corregir o anotar P1-4** (`operacion_en_curso`) en el mismo cambio: es trivial y evita
  que el contrato app/host se fusione divergente. Si no se corrige, debe quedar como DEUDA
  declarada y CE-4 bloqueante.
- **CM-4 — Dictamen del SHA final:** este informe cubre `ff49a7fc` con árbol limpio. Cualquier
  commit/rebase posterior (incluido el commit de correcciones de CM-2/CM-3) invalida el dictamen
  y exige repetirlo sobre el SHA que se fusione (CLAUDE.md §5.8). El commit de correcciones no
  debe tocar `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py`; si los
  toca, aplica la pasada final de seguridad completa.

### 5.2 Para habilitar (CE) — NO concedidas

Además de I-1…I-9 de `docs/design/secops-ops4-autorizacion-2026-11-20.md` §5.2 (que siguen
abiertas: arnés real, Pi/VM con `update.sh` real, NTP/TTL, estado fiable, suite 3.11, ADR y
autorización explícita del PO):

1. **CE-1 (P1-1):** separar «provisionar» de «armar»; confirmación explícita de que `--activar`
   arma la ejecución real como root; mensaje final que distinga UI apagada de host armado.
2. **CE-2 (P1-2):** `start` con mensaje «no persistente» o `[Install]` + doc/tests de contrato.
3. **CE-3 (P1-3):** resolver el grupo como OPS1 desde `PGID`; abortar si no existe; documentar
   `OPS4_GROUP`; test del caso por defecto.
4. **CE-4 (P1-4/P2-3):** código cerrado único app/host, `operacion_en_curso` incluido y mapeado;
   regresión con el `procesar` real; preferiblemente admisión única compartida.
5. **CE-5 (P1-5):** compose pasa las tres `OPS4_*` (o se documenta que la activación requiere
   editar compose); doc con la ruta real de la clave; runbook completo.
6. **CE-6 (P1-6):** decidir y actualizar spec/ADR sobre contraseña viva, autoridad app y estado
   persistente. Sin esto no puede declararse AC-03/§8 cumplidos.
7. **CE-7 (P1-7):** resolver `ReadWritePaths`/lock (prefijar `-` + crear el fichero desde el
   instalador o instalar tmpfiles de OPS1), decidir si el refresco OPS1 y la prueba de
   restauración son fallos duros o blandos, y validar `update.sh` real bajo la unidad en VM
   aislada.
8. **CE-8 (P1-8):** registrar en ADR el riesgo residual de la clave compartida con el contenedor
   y reducir superficie (montar `ops` solo al habilitar o equivalente, grupo mínimo); la
   habilitación debe autorizarlo explícitamente.
9. **CE-9 (P1-9):** conectar el escritor/lector de estado durable (fases, HEAD0/S, resultado,
   «sin noticias»/reconciliación) y no relanzar a ciegas tras `INCIERTA`.
10. **CE-10 (P2-1):** eliminar el fallback al socket de OPS1.
11. **CE-11 (P2-2):** reserva/inicio atómico respecto del cerrojo (mantener fd 9 o equivalente).
12. **CE-12 (P2-4…P2-10):** plazo de lectura y tope de fallos del auxiliar, retención/cuota y
    tope de emisiones, rotación/revocación de clave, paridad 0400/0440, actualización documental
    restante y runbook de activación con verificación posterior. Suite en 3.11 y autorización
    explícita del PO (I-8/I-9).

**No se concede ninguna aprobación de despliegue.** Cualquier activación real exige ventana
autorizada, copia previa verificada, revisión del SHA final y ejecución en entorno aislado
primero (VM/Pi desechable), nunca en producción directamente desde este dictamen.

---

## 6. Pruebas y lint ejecutados (evidencia)

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443

# Conjunto dirigido al objeto + puerta/aislamiento (361 casos)
PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/secops-ops4-bt \
  tests/test_ops4_ui_actualizacion.py tests/test_ops4_ui_gate.py \
  tests/test_ops4_ui_deshabilitada.py tests/test_ops4_auxiliar.py \
  tests/test_ops4_protocolo_v4.py tests/test_ops4_transporte_v4.py \
  tests/test_ops4_solicitud_v4.py tests/test_ops4_clave_autorizacion.py \
  tests/test_ops4_autorizacion.py tests/test_ops4_autorizacion_compuesta.py \
  tests/test_ops4_registro_repeticiones.py tests/test_instalar_ops4.py \
  tests/test_ops4_unidades.py tests/test_ops4_gate.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_estado_actualizacion.py tests/test_ops4_admision_actualizar.py
# → 361 passed

# Conjunto OPS4 completo + paridad/instalador/cerrojo (975 casos, sin PG/Docker)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .../pytest -q -p no:cacheprovider \
  --basetemp=/tmp/secops-ops4-bt2 tests/test_ops4_*.py tests/test_ops_paridad.py \
  tests/test_instalar_ops.py tests/test_cerrojo_operaciones.py
# → 975 passed in 19.13s

# Ruff (equivalente CI)
ruff check src/                                     # → All checks passed!
ruff check --select S src/                          # → All checks passed!
ruff check <11 módulos revisados>                   # → All checks passed!
ruff format --check <11 módulos revisados>          # → 11 files would be reformatted (CI no lo exige)

bash -n scripts/instalar_actualizacion_ops4.sh      # → OK
git diff --check origin/main...HEAD                 # → limpio
# Python 3.11 estático: ast.parse(feature_version=(3,11)) OK en los 11 módulos.
```

**Sondas de solo lectura (sin ficheros ni host):**

```text
# Semántica de enable sobre unidad sin [Install] (systemd 259, offline)
$ systemctl --root=/tmp/secops-sysd-root enable zascarr-actualizar.socket
rc=0 + aviso «The unit files have no installation config (…) not meant to be enabled…»

# Respuesta del auxiliar → transporte de la app
operacion_en_curso -> respuesta_invalida   # P1-4
repetida           -> rechazada
caducada           -> rechazada
no_disponible      -> rechazada

# Dry-run del instalador con --activar
$ ZASCARR_PRUEBAS=1 OPS4_DATA_DIR=/tmp/ops4-dry OPS4_GROUP=root \
  bash scripts/instalar_actualizacion_ops4.sh --dry-run --activar
[dry-run] systemctl enable --now zascarr-actualizar.socket
Socket habilitado en esta máquina.
La actualización sigue deshabilitada por defecto (OPS4_ACTUALIZACION_HABILITADA=false).
```

**NOT RUN (declarado, no PASS):** suite completa; Python 3.11 en runtime; systemd/Pi/VM con el
`update.sh` real; instalación real del socket/auxiliar/unidad; Docker; PostgreSQL real; cortes
eléctricos/`fsync` reales; extremo a extremo HTTP completo contra el auxiliar real (el E2E de UI
usa un servidor de prueba con `admitir_v4`, no el `procesar` del auxiliar); rotación de clave;
NTP/TTL en la Pi.

---

## 7. Snapshot revisado

`HEAD` = `ff49a7fcde25a9ea087da121e3c67b464faef0e9` (rama `feat/ops4-seguridad-443`), árbol limpio.
Merge-base con `origin/main` = `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9`.

| Fichero | SHA-256 |
|---|---|
| `src/zascarr/web/actualizacion.py` | `2663c04f0f5a24180d519cc429e88d454cdc5c57faad7aa5bce4b059bd8135ed` |
| `src/zascarr/web/templates/estado.html` | `4213191843085a2b723f2344c3b61aa06a546b0fc783b1bc49ab2b962f530513` |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1bbdbb22ac83d0a2c65e0914359d0ccfa32d2b9d53379fb9125abff14` |
| `src/zascarr/services/clave_autorizacion.py` | `075a21d8d1cc7efae8e5dda0d2b36dc7fa6921619b352ce62ab5110d94a8ae0c` |
| `src/zascarr/services/solicitud_actualizacion_v4.py` | `9334d5ca34e74b1dfadd7aaf30112df7f9f541a01acacaf33ae3e4bdfd4ccd6c` |
| `src/zascarr/services/actualizacion_transporte_v4.py` | `90162f1237639e7fccbd80664613ab5449d8d76ee4336c3836b0bf038d4990a1` |
| `src/zascarr/services/ops_actualizacion_v4.py` | `94db06081ebb77fad91d31d3e959b2cbae5530ff42b3bf1b26455e0c71e43dc5` |
| `deploy/ops/zascarr_actualizar_aux.py` | `7b33544d80c7ea4035035105e9eceb40ed781785e96970ef7a529e858d37a68c` |
| `deploy/ops/protocolo_actualizar_v4_ops4.py` | `72bf693e41af84ec1ddc29515a84022f5884635750d0a0b374a3e75012efa834` |
| `deploy/ops/verificador_autorizacion_ops4.py` | `96628781707ba14a15131b9c4cd71c0081b65dd18f39e66aa48db59cedff1b72` |
| `deploy/ops/registro_repeticiones_ops4.py` | `3221036741d3495859608dfc4bfa4426a0cfb11bcb3055be1a70a2ae33c6c354` |
| `deploy/ops/admision_v4_actualizar_ops4.py` | `21d0822e15f1bc365618a60a1d3ba57ba4d468c329cc2ade14d5c63fc4e1a6fc` |
| `deploy/systemd/zascarr-actualizar.service` | `a95ba462563a20b141e2f0cdd0a6bcdb8580b99bddf628f7ff20252d90884165` |
| `deploy/systemd/zascarr-actualizar@.service` | `edd7e01151767bfdf3eb937c1c5e98f82953606c8687b72d7199f98d52c50ee6` |
| `deploy/systemd/zascarr-actualizar.socket` | `9fbc6ce70f97f9f4afe5f7131da84e7176d47720bbeffc03e5a9b168f2f08a8c` |
| `scripts/instalar_actualizacion_ops4.sh` | `d41013ac260130f55e969b7a8dcda71d70bbdf1f1e73cbecd2d0746804907368` |
| `src/zascarr/config.py` | `ffd4a087d2925db71ab3b8858ed891c643ee432abdd30dd0b6475522ea054d2a` |
| `src/zascarr/main.py` | `3b0ad894cef62b7ea7f119f0782b00390c03297a886edef22344145e788b94ac` |
| `src/zascarr/web/estado.py` | `dc0eb311b32e32f1a463cbb07169d10afa9c780542c72a3fc913c8a75545b502` |
| `docker-compose.yml` | `dc6cd0c5a013ca19304c8461ecb070fa4aced6a84da57819cbda5ac4ad5f2819` |

---

## 8. Vigencia

- Válido **solo** para `ff49a7fc` con la función deshabilitada. **Caduca** con el primer commit,
  rebase o cambio de cualquiera de los ficheros de §7; el SHA que se fusione debe tener su propio
  dictamen (CLAUDE.md §5.8).
- Caducidad ordinaria: 2027-01-20 (60 días), o antes si cambia la decisión de autoridad, el
  protocolo v4, la clave, el registro durable, el instalador o las unidades.
- **Resumen para el PO:** el SHA está bien construido para seguir deshabilitado; **no hay
  hallazgos P0 y no hay razón de seguridad para no fusionarlo apagado**, con CM-1…CM-4. **No se
  debe habilitar** hasta CE-1…CE-12, I-1…I-9 y autorización explícita separada; este informe no
  autoriza desplegar, instalar en la Pi ni ejecutar `update.sh` real.

---

## Addendum posterior a `ff49a7fc`

En el commit que acompaña a este addendum se aplicaron CM-1…CM-3: no se
añadió cableado de activación a bootstrap/update, se reconciliaron la
especificación main, la ruta de clave, Compose y los mensajes del instalador,
y `operacion_en_curso` se añadió al código cerrado del transporte. CM-4 sigue
vigente: **este informe no cubre el SHA nuevo**; se requiere un dictamen del
SHA final antes de fusionar, y sigue siendo **NO-GO para habilitar o
desplegar**. No se ha ejecutado el instalador en la Pi ni `update.sh` real.
