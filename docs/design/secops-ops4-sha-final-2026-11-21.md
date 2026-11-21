# SecOps — Dictamen final del SHA `87b87a34` (OPS4, #443)

**Rol:** SecOps · **Fase:** dictamen final de solo lectura del SHA que se fusiona (CLAUDE.md §5.8).
**Fecha:** 2026-11-21 (Europe/Madrid).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443`, rama `feat/ops4-seguridad-443`.
**SHA dictaminado (árbol limpio):** `87b87a340a173402e046a02571c3db83410dbbd7` (`git status --porcelain` vacío
al empezar la revisión). Este informe se añade después como fichero nuevo **no rastreado**; si se
versiona, debe ser un commit **solo de documentación** que no altera el contenido de código dictaminado.
**Commit padre / SHA anterior dictaminado:** `ff49a7fcde25a9ea087da121e3c67b464faef0e9`.
**Informe previo:** [secops-ops4-integracion-final-2026-11-21.md](secops-ops4-integracion-final-2026-11-21.md) (revisión de `ff49a7fc` + addendum que anuncia las correcciones de este SHA).
**Base frente a `origin/main`:** `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9` (97 commits).
**Entorno:** venv de pruebas del repo (Python 3.14.4, pytest 9.2, ruff 0.17.4); la imagen de producción es
`python:3.11-slim` y `pyproject.toml:5` exige `>=3.11`. Sin `TEST_DATABASE_URL`, sin Docker,
sin systemd instalado, sin Pi.

**Restricciones respetadas:** no se editó código, plantillas, unidades, instalador, compose ni `update.sh`;
no se hizo commit ni push. No se ejecutó la Pi, Docker real, systemd del host, el instalador con
`--activar` ni `update.sh`. **El único fichero escrito es este informe.** La actualización sigue
**DESHABILITADA por defecto**. Este dictamen **no autoriza habilitar, desplegar, instalar en la Pi ni
ejecutar `update.sh` real**, y no sustituye la revisión de habilitación.

---

## 0. Veredicto

1. **Hallazgos P0: ninguno.** Con los valores por defecto y sin una acción explícita de root no he
   encontrado una ruta que ejecute `update.sh`, ni un bypass de la puerta de UI, ni fuga de
   contraseña/clave/testigo, ni un replay práctico.
2. **Fusionar el incremento con la función deshabilitada: GO CON CONDICIONES** (§6.1). Las condiciones
   `CF-1…CF-5` son de documentación, traza y aceptación explícita de una desviación deliberada de
   CM-1; no hay ningún defecto explotable con la función apagada y las dos correcciones de
   documentación pendientes no tocan código en servicio.
3. **Habilitar (abrir la ruta, arrancar el socket, ejecutar el `update.sh` real) o desplegar:
   NO-GO.** Siguen abiertas `P1-1`, `P1-3` (con una **regresión nueva y concreta** en el instalador,
   §5.2), `P1-4` (parcial), `P1-6`, `P1-7`, `P1-8`, `P1-9` e `I-1…I-9` del informe previo. Ninguna
   corrección de este SHA convierte un P1 en aprobado de habilitación.
4. **Dictamen del SHA final:** este informe cubre **exactamente** `87b87a34` con árbol limpio y solo
   es válido con la función **deshabilitada**. **Caduca** con cualquier commit, rebase o cambio de los
   ficheros de §8 (o de los documentos de contrato que fijan el estado) y no es válido para habilitar.

---

## 1. Alcance: qué cambia respecto del informe previo

El commit `87b87a34` («fix(ops): aplicar condiciones de integración de SecOps (#443)») toca 8
ficheros: 3 de código/configuración y 5 de documentación (incluido el informe previo como adición).

| Fichero | Cambio | Relevancia de seguridad |
|---|---|---|
| `src/zascarr/services/actualizacion_transporte_v4.py` | `+ "operacion_en_curso"` en `_CODIGOS` | Baja: amplía el conjunto cerrado de respuestas aceptadas (CM-3). |
| `scripts/instalar_actualizacion_ops4.sh` | resolución de grupo + mensajes + `start` en vez de `enable --now` | **Alta**: solo se ejecuta como root; el cambio de grupo tiene un defecto (P1-3-R). |
| `docker-compose.yml` | pasa `OPS4_ACTUALIZACION_HABILITADA` (default `false`), `OPS4_AUTORIZACION_KEY_FILE`, `OPS4_SOCKET_FILE` | **Media**: quita una salvaguarda previa («el `.env` no llega al contenedor»); no activa nada por sí mismo. |
| `CLAUDE.md`, `docs/design/ops4-especificacion-main.md`, `ops4-instalador.md`, `ops4-ui-integracion.md` | reconciliación de contrato (CM-2) | Documental; parcial (ver §2). |
| `docs/design/secops-ops4-integracion-final-2026-11-21.md` | informe previo + addendum | Documental. |

**Los demás ficheros revisados son byte a byte los mismos que en `ff49a7fc`.** Los SHA-256 de
`web/actualizacion.py`, `estado.html`, `autorizacion_actualizacion.py`, `clave_autorizacion.py`,
`solicitud_actualizacion_v4.py`, `ops_actualizacion_v4.py`, el auxiliar `zascarr_actualizar_aux.py`,
`protocolo_actualizar_v4_ops4.py`, `verificador_autorizacion_ops4.py`, `registro_repeticiones_ops4.py`,
`admision_v4_actualizar_ops4.py`, las tres unidades systemd, `config.py`, `main.py` y `web/estado.py`
coinciden con la tabla §7 del informe previo (ver §8). Por tanto, el análisis técnico previo de esa
superficie sigue vigente sin cambios; este informe se concentra en el delta y en lo que el delta
puede haber roto.

**CM-4 respetado:** `git diff --stat origin/main...HEAD -- src/zascarr/services/seguridad.py
src/zascarr/web/ajustes.py src/zascarr/services/reautenticacion.py` → **vacío**. El commit de
correcciones no toca la frontera de «qué exige la contraseña actual»; no hace falta una pasada
completa adicional por esa regla, aunque este informe la cubre igualmente para el SHA final.

---

## 2. Verificación de CM-1…CM-4

| Condición | Qué pedía | Evidencia en `87b87a34` | Resultado |
|---|---|---|---|
| **CM-1** No añadir cableado de activación | instalador fuera de `bootstrap.sh`/`update.sh`; **no pasar `OPS4_*` por compose**; no enlazar la bandera a Ajustes/BD | `bootstrap.sh` y `scripts/update.sh` no mencionan OPS4 (grep sin resultados); `scripts/instalar_ops.sh` no instala unidades OPS4 (`tests/test_ops4_unidades.py:54-62`); `RuntimeSettingsService` sigue sin campos `ops4_*` (`src/zascarr/services/runtime_settings.py:38-113`); **pero** `docker-compose.yml:163-166` pasa las tres `OPS4_*` | **PARCIAL — desviación deliberada** |
| **CM-2** Reconciliar documentación de contrato | `CLAUDE.md:101`, `ops4-auxiliar-unidad.md:75`, `ops4-protocolo-v4.md`, `ops4-ui-integracion.md:4,10-12`, relación con `ops4-especificacion-main.md:22,28,59` | Corregidos `CLAUDE.md:101-103`, `ops4-especificacion-main.md:22,59`, `ops4-ui-integracion.md:11`, `ops4-instalador.md:13-18`; **quedan sin corregir** `ops4-auxiliar-unidad.md:75-77`, `ops4-protocolo-v4.md:3-5`, `ops4-matriz-evidencia.md:37` y las referencias cruzadas de §5.3 | **PARCIAL** |
| **CM-3** Corregir o anotar P1-4 (`operacion_en_curso`) | añadir el código al conjunto cerrado en el mismo cambio | `actualizacion_transporte_v4.py:25-28` lo incluye; sonda directa: `operacion_en_curso → rechazada` (ya **no** `respuesta_invalida`); **falta** el mapeo al mensaje «ocupada» y la regresión con el `procesar` real del auxiliar | **PARCIAL** (el fallo de contrato está cerrado) |
| **CM-4** Dictamen del SHA final | este informe cubre el SHA que se fusiona; cambios posteriores invalidan; el commit de correcciones no toca los 3 ficheros sensibles | Este informe; `git diff` de los 3 ficheros vacío | **CUMPLE** |

### 2.1 Sobre la desviación de CM-1 (compose pasa `OPS4_*`)

`docker-compose.yml:163-166` añade:

```yaml
# OPS4: apagado por defecto; la ruta de clave/socket dedicada ya está en el volumen ops.
- OPS4_ACTUALIZACION_HABILITADA=${OPS4_ACTUALIZACION_HABILITADA:-false}
- OPS4_AUTORIZACION_KEY_FILE=/run/zascarr-ops/actualizar.key
- OPS4_SOCKET_FILE=/run/zascarr-ops/actualizar.sock
```

Esto contradice literalmente CM-1, pero atiende CE-5 del informe previo y P1-5 («la activación
documentada no funciona: el `.env` no llega al contenedor»). El efecto es que **una bandera puesta en
el `.env` ahora sí llega al contenedor**; la salvaguarda adicional que el informe previo describía
(«aunque un operador ponga la bandera en `.env`, el contenedor no la recibe») **desaparece
deliberadamente**. No es una escalada:

- el `.env` es de root `600` (ADR 0012) y lo escribe el instalador; la app no lo edita;
- el valor por defecto es `false`: sin la variable, el contenedor recibe `false` (probado, §7);
- con la bandera en `true` y sin clave/socket provisionados, la ruta responde 503 y el transporte
  `no_disponible`: no hay efecto en el host;
- el socket/auxiliar siguen sin instalarse solos y sin `[Install]`; nada arranca `update.sh` sin que
  root ejecute el instalador con `--activar`.

Conclusión: la desviación es **aceptable si se decide y registra explícitamente** (CF-2) o se revierte
antes de fusionar. Como está, no crea un P0/P1 nuevo mientras la clave no esté provisionada y el
socket no exista.

---

## 3. Verificación de las correcciones aplicadas

### 3.1 Transporte: `operacion_en_curso`

- **Aplicado:** `_CODIGOS` incluye ahora `operacion_en_curso`
  (`src/zascarr/services/actualizacion_transporte_v4.py:25-28`). La respuesta real del auxiliar
  (`deploy/ops/zascarr_actualizar_aux.py:80-81`) ya no se convierte en `RESPUESTA_INVALIDA`:
  - sonda: `{"resultado":"rechazada","codigo":"operacion_en_curso"}` → `CodigoTransporteV4.RECHAZADA`
    (antes `RESPUESTA_INVALIDA`);
  - `repetida`, `caducada`, `no_disponible`, `esquema_invalido` → `rechazada`; `aceptada/aceptada` →
    `aceptada`; `respuesta_invalida` sigue para esquemas inválidos.
- **Residual (P1-4-R):** el código se mapea a `ResultadoSolicitudV4.RECHAZADA` y la UI muestra
  «La solicitud fue rechazada. No se ha actualizado nada.»
  (`src/zascarr/web/actualizacion.py:35`) en vez del mensaje de ocupada
  (`:31`), que solo se alcanza por el bloqueo local de reautenticación
  (`src/zascarr/services/solicitud_actualizacion_v4.py:62,133-135`). No es de seguridad (falla
  cerrado), pero es la mitad de CE-4.
- **Cobertura:** no hay caso nuevo en `tests/test_ops4_transporte_v4.py` para el código añadido, y el
  E2E de UI sigue usando `admitir_v4` como servidor de prueba
  (`tests/test_ops4_ui_actualizacion.py:115-183`), no el `procesar` real. La regresión que pedía CE-4
  sigue pendiente.

### 3.2 Compose: `OPS4_*`

- **Aplicado y coherente con la configuración real:**
  - `OPS4_AUTORIZACION_KEY_FILE=/run/zascarr-ops/actualizar.key` coincide con el default de
    `src/zascarr/config.py:283`, con la clave que crea el instalador
    (`DATA_DIR/ops/actualizar.key`, `scripts/instalar_actualizacion_ops4.sh:93-113`) y con el montaje
    `docker-compose.yml:214` (`${ZASCARR_DATA_DIR}/ops:/run/zascarr-ops:ro`).
  - `OPS4_SOCKET_FILE=/run/zascarr-ops/actualizar.sock` coincide con `config.py:284` y con
    `ListenStream=@ZASCARR_DATA_DIR@/ops/actualizar.sock` (`deploy/systemd/zascarr-actualizar.socket:6`).
  - `docker-compose.yml` parsea como YAML válido (PyYAML 6.0.3) y `tests/test_compose_env.py` pasa
    (no exige ni prohíbe las nuevas claves).
  - Sonda de `Settings`: con `OPS4_ACTUALIZACION_HABILITADA=true` → `True`; `false` → `False`; sin
    variable → `False` (default de `config.py:282`).
- **Residual (P2-13):** el instalador y su doc siguen imprimiendo «La UI sigue deshabilitada por
  defecto (`OPS4_ACTUALIZACION_HABILITADA=false`)» de forma incondicional
  (`scripts/instalar_actualizacion_ops4.sh:149,156`; `docs/design/ops4-instalador.md:14`). Esa frase
  **puede ser falsa** si el `.env` ya tiene la bandera en `true` (ahora llega al contenedor). No
  activa nada, pero conviene condicionarla.

### 3.3 Grupo y mensajes del instalador

- **Mensajes mejorados (P1-1/P1-2, parcial):** con `--activar` usa `systemctl start` y avisa de que
  no es persistente y de que la unidad fija puede ejecutar `update.sh`
  (`scripts/instalar_actualizacion_ops4.sh:147-149`); sin `--activar` dice «NO activadas»
  (`:151`). La doc lo recoge (`docs/design/ops4-instalador.md:15-18`). **CE-2 queda satisfecho en
  código** (unidad sin `[Install]` + `start`), si bien no hay prueba estática del comando
  (`tests/test_instalar_ops4.py` solo ejercita `--sin-systemd`) y `--quitar` sigue usando
  `systemctl disable --now` (`:109`), inocuo.
- **Regresión real en la resolución del grupo (P1-3-R, ver §5.2):** el código añadido en
  `scripts/instalar_actualizacion_ops4.sh:18-24` **no lee el `.env`**, porque `ENV_FILE` no está
  definido en el script (solo aparece dentro de `leer_env` en la línea 18; a diferencia de
  `scripts/instalar_ops.sh:15,62-90`, que lo define y aborta si no resuelve el grupo). Consecuencia:
  `gid` es siempre `1000`, el grupo es el del gid 1000 (no el `PGID` del `.env`) y, si ese grupo no
  existe, cae a `id -gn`, que bajo `sudo` es **`root`**. El `OPS4_GROUP` explícito sigue funcionando y
  los tests lo inyectan siempre (`tests/test_instalar_ops4.py:23`), por eso no se detecta.

### 3.4 Spec y ruta de la clave

- **Spec reconciliada en lo de autoridad app→host:** `docs/design/ops4-especificacion-main.md:22`
  (requisito 2) y `:59` (AC-03) ya describen el testigo HMAC y la decisión del 2026-11-20; se retira
  la exigencia de contraseña viva en el host.
- **Pendiente (P1-6-R):** el requisito 7 (`:27`, cerrojo/estado) y el requisito 8 (`:28`, estado host
  persistente, fases, reconciliación) **siguen exigiendo** lo que el auxiliar no implementa. La
  contradicción documental no está cerrada, solo la del requisito 2/AC-03. Además, los documentos que
  señalaban esa contradicción no se han actualizado (§5.3).
- **Ruta de la clave corregida:** `docs/design/ops4-ui-integracion.md:11` ya da
  `/run/zascarr-ops/actualizar.key` (contenedor) y el fichero real
  `/var/lib/zascarr/ops/actualizar.key`. Es correcta para el `ZASCARR_DATA_DIR` por defecto; la frase
  «fichero real» no menciona que se mueve si `ZASCARR_DATA_DIR` se personaliza (matiz menor).

---

## 4. «Deshabilitado por defecto» en este SHA (verificado)

| Capa | Evidencia | Resultado |
|---|---|---|
| Bandera de producto | `config.py:282` `default=False`; `config.py:283-284` rutas dedicadas | **OFF por defecto** |
| Ajustes en caliente | `runtime_settings.py:38-113` lista blanca sin campos `ops4_*` | La UI/BD **no puede** encenderla |
| Variables del contenedor | `docker-compose.yml:164` `${OPS4_ACTUALIZACION_HABILITADA:-false}`; el resto de rutas son literales | **OFF por defecto**; si root pone `true` en el `.env` (root `600`), llega al contenedor (cambio respecto de `ff49a7fc`) |
| Botón de Estado | `web/estado.py:52-53`; `templates/estado.html:15-25` (disabled sin `form`) | **Inerte** con la bandera falsa |
| Ruta POST | `web/actualizacion.py:52-53`: 404 **antes** de leer clave o reautenticar; pruebas en `tests/test_ops4_ui_gate.py` y `tests/test_ops4_ui_actualizacion.py` | **404** |
| Sesión / origen | `AuthMiddleware` cubre `/ui/*`; `_peticion_cross_site` rechaza POST sin `Origin`/`Referer` en `/ui/` (`services/auth.py:234-264, 673`) | Sin sesión no hay POST |
| Instalador no automático | `bootstrap.sh`/`scripts/update.sh` sin referencias a OPS4 (grep); `instalar_ops.sh` no instala OPS4 (`tests/test_ops4_unidades.py:54-62`) | **No se ejecuta solo** |
| Unidades | socket/servicio sin `[Install]` (`deploy/systemd/zascarr-actualizar.socket:16`, `.service:32`) | No arrancan al boot |
| Ejecución real | `zascarr-actualizar.service` ejecuta `update.sh` real, pero solo existe en disco y solo arranca si root ejecuta el instalador con `--activar` y llega una petición válida | **Sin efecto por defecto** |

**Conclusión §4:** con los valores por defecto de `87b87a34` la actualización **sigue
deshabilitada**, y nada la ejecuta. La diferencia con `ff49a7fc` es que ahora el `.env` (solo root)
**sí** puede encender la ruta de UI; sigue haciendo falta que root provisione la clave/socket y que
root arranque el socket. No hay escalada desde la app.

---

## 5. Hallazgos

### 5.1 P0 — ninguno

No he encontrado ejecución de `update.sh` por defecto, bypass de la puerta, fuga de secreto,
confusión de claves/sockets que ejecute algo, ni replay práctico. La función sigue apagada (§4).

### 5.2 P1 — bloquean **habilitar**; inertes con la función apagada

**P1-3-R (regresión nueva del commit de correcciones) — el instalador no lee el `.env` y puede
concluir grupo `root`.**

- **Evidencia:** `scripts/instalar_actualizacion_ops4.sh:18-24`:
  ```bash
  leer_env() { [[ -f "${ENV_FILE:-}" ]] && sed -n "s/^$1=//p" "${ENV_FILE}" | ... || true; }
  GRUPO="${OPS4_GROUP:-${OPS_GROUP:-}}"
  if [[ -z "${GRUPO}" ]]; then
      gid="$(leer_env PGID)"; gid="${gid:-1000}"
      GRUPO="$(getent group "${gid}" | cut -d: -f1)"
  fi
  GRUPO="${GRUPO:-$(id -gn)}"
  ```
  `ENV_FILE` **no se define en todo el script** (grep: solo aparece en la línea 18). Por tanto
  `leer_env` devuelve siempre vacío, `gid` es `1000` y `GRUPO` es el grupo del gid 1000, no el
  `PGID` del `.env`. Si no hay grupo con gid 1000, `GRUPO="$(id -gn)"`, que bajo `sudo` es **`root`**.
- **Comparación con el patrón correcto:** `scripts/instalar_ops.sh:15` define
  `ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"`, `:76-90` resuelve desde `PGID` y `:159-162` **aborta
  sin instalar** si no lo resuelve. El texto de la corrección dice seguir ese patrón, pero no lo hace.
- **Comprobación de solo lectura:** `env -u OPS4_GROUP -u OPS_GROUP -u ENV_FILE ZASCARR_PRUEBAS=1
  OPS4_DATA_DIR=/tmp/secops4-dry bash scripts/instalar_actualizacion_ops4.sh --dry-run --yes` → en
  esta máquina resuelve `GRUPO=juanjo` (grupo del gid 1000), **sin leer ningún `.env`**. No escribió
  nada (`/tmp/secops4-dry` no existe tras el dry-run).
- **Cobertura:** `tests/test_instalar_ops4.py:23` inyecta siempre `OPS4_GROUP`; no hay caso por
  defecto, que es exactamente lo que pedía CE-3.
- **Impacto:** en instalaciones con `PGID != 1000` (o sin grupo 1000), la clave queda
  `0440 root:<grupo ajeno>` y el socket `0660 root:<grupo ajeno>`: la app no puede leer la clave
  (503) ni conectar. Con el fallback `root`, falla cerrado. No es escalada (root ya podía todo), pero
  es un «activar que no funciona» silencioso y contradice el patrón OPS1. **No bloquea fusionar
  apagado** (el instalador no se ejecuta solo). **Condición CE-3-R.**

**P1-1-R (residual) — no hay confirmación explícita al armar el host.**

- **Evidencia:** el único prompt sigue siendo genérico («¿Provisionar OPS4 (sin habilitar la
  UI)?», `scripts/instalar_actualizacion_ops4.sh:127-130`); `--activar` no pide confirmación aparte.
  La línea final `:156` sigue afirmando «La actualización sigue deshabilitada por defecto» después de
  armar, aunque la nueva línea `:148` ya avisa de que la unidad puede ejecutar `update.sh`.
- **Impacto:** el mensaje ya distingue mejor «UI apagada» de «host armado» (mejora real), pero no hay
  confirmación inequívoca antes de una acción privilegiada. CE-1 sigue abierta para habilitar.

**P1-4-R (residual) — `operacion_en_curso` se acepta pero se presenta como «rechazada» y sin
regresión con el auxiliar real.** Ver §3.1. Fallo cerrado; afecta a mensaje y a la cobertura exigida
por CE-4.

**P1-6-R / P1-9-R (sin cambios) — estado durable y reconciliación no implementados.** El requisito 7
(`docs/design/ops4-especificacion-main.md:27`) y el 8 (`:28`) siguen exigiendo estado host
persistente, fases, `HEAD0/S`, resultado y reconciliación tras `INCIERTA`; el auxiliar no escribe
estado (`deploy/ops/zascarr_actualizar_aux.py:62-104`) y `INCIERTA` no tiene lectura de estado
(`web/actualizacion.py:36-39`). Los módulos de estado/ejecutor siguen desconectados
(`tests/test_ops4_aislamiento.py`). Bloquea habilitar.

**P1-7-R (sin cambios) — sandbox de `zascarr-actualizar.service`.** `ReadWritePaths` incluye
`/run/zascarr-ops.lock` (`deploy/systemd/zascarr-actualizar.service:30`) y ese fichero lo crea el
tmpfiles de **OPS1**, no el instalador OPS4; `ProtectSystem=strict`/`ProtectHome=yes`
(`:19-20`) sigue pudiendo denegar el refresco de OPS1 que `update.sh:224` ejecuta con `|| warn`.
Byte-idéntico a `ff49a7fc`; CE-7 abierta.

**P1-8-R (sin cambios) — la clave que autoriza `update.sh` como root vive montada en el contenedor.**
`docker-compose.yml:214` monta `${ZASCARR_DATA_DIR}/ops` **siempre** (`:ro`); el host no comprueba
identidad (decisión de 2026-11-20). Riesgo residual aceptado por decisión, **pero no consta
registrado en ADR** ni con superficie reducida. CE-8 abierta.

**Cerradas o mejoradas por este SHA (para que no se arrastren como si siguieran abiertas):**

- **P1-2:** cerrada en código y doc (unidad sin `[Install]` + `systemctl start` + «no persistente»).
  Falta solo la prueba estática del comando (P2-15).
- **P1-5:** cerrada en lo esencial (compose pasa las tres variables; ruta de clave correcta en la
  doc). Queda el runbook de activación (P2-10).

### 5.3 P2 — documentación, endurecimiento y deuda (no bloquean fusionar apagado)

- **P2-13 (nuevo):** mensajes incondicionales «La UI sigue deshabilitada por defecto» en
  `scripts/instalar_actualizacion_ops4.sh:149,156` y `docs/design/ops4-instalador.md:14`; desde el
  cambio de compose pueden ser falsos si el `.env` tiene la bandera en `true`. Condicionar el texto.
- **P2-14 (nuevo):** traza de la desviación de CM-1. El addendum del informe previo dice que se
  aplicaron CM-1…CM-3, pero CM-1 prohibía pasar `OPS4_*` por compose y este commit lo hace. Hay que
  registrar la decisión (CF-2) o revertir; tal cual, el informe previo y el árbol se contradicen.
- **P2-15 (nuevo):** no hay prueba estática del comando `systemctl start` ni de que el instalador no
  vuelva a `enable --now`; el único ejercicio del camino `--activar` es la VM, que además usó
  `OPS4_GROUP=root` (evidencia fuera del árbol: `fuera-de-zascarr/ops4-vm-evidencia/…`), por lo que
  **no cubre** la resolución por defecto del grupo.
- **CM-2 pendiente (P2-16):** `docs/design/ops4-auxiliar-unidad.md:75-77` sigue diciendo «No hay
  instalador de estas unidades todavía» y que no se han copiado/arrancado, cuando el propio documento
  acredita una VM con unidades instaladas y el instalador existe. `docs/design/ops4-protocolo-v4.md:3-5`
  sigue diciendo «No está conectado al auxiliar, la UI, systemd ni el transporte de socket», cuando el
  SHA tiene el circuito cableado (apagado). `docs/design/ops4-matriz-evidencia.md:37` dice «UI, red,
  clave provisionada y ejecución siguen sin conectar»: parcialmente obsoleto. Y las referencias que
  señalaban la contradicción del requisito 2 ya corregido quedan desfasadas:
  `docs/design/benchmark-ops4-autorizacion.md:66,97`,
  `docs/design/especificacion-ops4-autorizacion.md:31,783-784,847`.
- **P2-17:** `ops4-ui-integracion.md:11` da la ruta real como `/var/lib/zascarr/ops/...` sin matizar
  que depende de `ZASCARR_DATA_DIR`; y no hay runbook de activación con el orden exacto y la
  verificación posterior (P2-10 del informe previo).
- **P2-1 (fallback de socket):** `actualizacion_transporte_v4.py:73-76` sigue cayendo a
  `ops_socket_file` (OPS1) si falta `ops4_socket_file`. En el despliegue por compose ya no ocurre
  porque la variable es literal, pero el fallback no debería existir y los tests lo usan para inyectar
  el socket. Sin confusión explotable (OPS1 rechaza v4, firma y clave distintas). CE-10 abierta.
- **P2-3 (admisión duplicada):** el auxiliar reimplementa la admisión inline
  (`zascarr_actualizar_aux.py:62-104`) en lugar de usar `admision_v4_actualizar_ops4.py`; es la causa
  estructural de P1-4-R. CE-4/CE-12.
- **P2-4 (DoS del socket), P2-5 (retención/cuota), P2-6 (rotación de clave), P2-7 (paridad
  0400/0440), P2-9 (`--quitar` conservador), P2-11 (mensajes de UI), P2-12 (entorno del
  instalador):** sin cambios respecto del informe previo. CE-12.
- **Formato:** `ruff format --check` sobre `actualizacion_transporte_v4.py` sigue diciendo que se
  reformatearía; el CI no ejecuta `format` (§7), así que no bloquea. `ruff check src/` y
  `ruff check --select S src/` (lo que corre CI) pasan.

---

## 6. Condiciones exactas

### 6.1 Para fusionar apagado — GO con estas condiciones

- **CF-1 — Fusionar exactamente este SHA o un commit posterior solo de documentación.** Cualquier
  commit que toque los ficheros de código/configuración de §8 (o las unidades/auxiliar) **invalida**
  este dictamen y exige repetirlo sobre el SHA que se fusione (CLAUDE.md §5.8). El merge no debe
  ejecutar `--activar`, no debe tocar la Pi y no debe poner la bandera en el `.env`.
- **CF-2 — Aceptar y registrar explícitamente la desviación de CM-1** (`docker-compose.yml:163-166`
  pasa `OPS4_*`, default `false`), o revertir esas cuatro líneas antes de fusionar. Si se acepta, la
  nota debe decir que el `.env` (root `600`) **sí** puede encender la ruta de UI y que la protección
  que queda es la clave/socket no provisionados + el instalador manual de root.
- **CF-3 — Cerrar CM-2 en el mismo merge o como deuda declarada caducable:** corregir
  `docs/design/ops4-auxiliar-unidad.md:75-77` y `docs/design/ops4-protocolo-v4.md:3-5` (y, si se
  puede, `ops4-matriz-evidencia.md:37` y las referencias cruzadas de §5.3) para que digan la verdad
  del árbol: «integrado, deshabilitado por defecto; habilitar exige CE-1…CE-12». Es documentación sin
  efecto en ejecución.
- **CF-4 — Anotar como deuda de habilitación (no de merge) los residuales P1-3-R, P1-4-R, P1-6-R y
  P1-9-R**, con sus CE correspondientes. No impiden fusionar apagado porque el instalador/auxiliar no
  se ejecutan sin root.
- **CF-5 — No autorizar despliegue en el mismo acto:** la fusión apagada no arranca el socket, no
  instala unidades, no escribe la bandera y no cambia la política de despliegue.

Estas condiciones son **de documentación/traza y de decisión**, no de código en servicio. Con ellas
cumplidas, la fusión con la función deshabilitada es aceptable desde Seguridad.

### 6.2 Para habilitar (CE) — NO concedidas

Además de `I-1…I-9` de [secops-ops4-autorizacion-2026-11-20.md](secops-ops4-autorizacion-2026-11-20.md)
(arnés real, Pi/VM con `update.sh` real, NTP/TTL, estado fiable, suite en 3.11, ADR y autorización
explícita del PO), siguen abiertas:

> **CE-2 se da por cerrada en código y doc** (`systemctl start`, mensaje «no persistente», unidad sin
> `[Install]`). Solo falta la prueba estática que impida volver a `enable --now` (P2-15), que no
> reabre el bloqueo por sí sola.

1. **CE-1 (P1-1-R):** confirmación explícita e inequívoca de `--activar` (arma ejecución real como
   root, no hay vuelta atrás automática) y mensaje final coherente; no presentar «sigue
   deshabilitada» cuando el host queda armado.
2. **CE-3-R (nuevo, P1-3-R):** resolver el grupo **desde `PGID` del `.env`** como OPS1 —definir
   `ZASCARR_ROOT`/`ENV_FILE`, `resolver_grupo` que **aborte** si no lo encuentra—, documentar
   `OPS4_GROUP` como escape y añadir el test del caso por defecto (sin `OPS4_GROUP`).
3. **CE-4 (P1-4-R):** mapear `operacion_en_curso` a un mensaje de «ocupada» y añadir la regresión que
   use el `procesar` real del auxiliar (no solo `admitir_v4`); idealmente, admisión única compartida.
4. **CE-5 (resto):** runbook de activación con el orden exacto (grupo → clave → instalador →
   cerrojo/tmpfiles → socket → bandera → `.env`/compose) y verificación posterior (clave legible por
   el grupo de la app, socket `LISTEN` con el grupo correcto, 404/503, prueba de repetición y de
   cerrojo).
5. **CE-6 (P1-6-R):** decidir y actualizar la spec sobre el estado host persistente (requisitos 7 y 8)
   o implementarlo; sin eso no puede declararse §7/§8 cumplido.
6. **CE-7 (P1-7-R):** resolver `ReadWritePaths`/`/run/zascarr-ops.lock` (prefijar `-` y crear el
   fichero desde el instalador, o instalar el tmpfiles de OPS1 como dependencia declarada); decidir si
   el refresco de OPS1 y la prueba de restauración son fallos duros o blandos; validar el `update.sh`
   real bajo la unidad en VM aislada.
7. **CE-8 (P1-8-R):** registrar en ADR el riesgo residual de la clave compartida con el contenedor y
   reducir superficie (montar `ops` solo al habilitar o equivalente); la habilitación debe
   autorizarlo explícitamente.
8. **CE-9 (P1-9-R):** conectar el escritor/lector de estado durable y la reconciliación tras
   `INCIERTA`; no relanzar a ciegas.
9. **CE-10 (P2-1):** eliminar el fallback al socket de OPS1.
10. **CE-11 (P2-2):** reserva/inicio atómico respecto del cerrojo.
11. **CE-12 (P2-4…P2-10, P2-13…P2-17):** plazo de lectura y tope de fallos del auxiliar,
    retención/cuota y tope de emisiones, rotación/revocación de clave, paridad 0400/0440, prueba
    estática del comando del instalador, textos incondicionales, limpieza documental restante y
    runbook; suite en 3.11 y autorización explícita del PO (I-8/I-9).

**No se concede ninguna aprobación de habilitación ni de despliegue.** Cualquier activación real exige
ventana autorizada, copia previa verificada, revisión de este mismo SHA final y ejecución en entorno
aislado primero (VM/Pi desechable), nunca en producción a partir de este dictamen.

---

## 7. Pruebas y lint ejecutados (evidencia)

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443

# Conjunto dirigido: OPS4 completo + paridad/instaladores/cerrojo + compose
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/secops-final-bt \
  tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ops_paridad.py \
  tests/test_instalar_ops.py tests/test_cerrojo_operaciones.py tests/test_compose_env.py
# → 987 passed, 1 warning in 18.14s

# Equivalente CI de lint
ruff check src/                          # → All checks passed!
ruff check --select S src/               # → All checks passed!
ruff check src/ deploy/ tests/test_ops4_transporte_v4.py   # → All checks passed!
ruff format --check src/zascarr/services/actualizacion_transporte_v4.py
# → 1 file would be reformatted (el CI no ejecuta format; ya ocurría en ff49a7fc)

bash -n scripts/instalar_actualizacion_ops4.sh   # → OK
git diff --check origin/main...HEAD              # → limpio
git status --porcelain                           # → vacío antes de escribir este informe
```

**Sondas de solo lectura (sin efectos):**

```text
# Compose: YAML válido y claves OPS4 presentes
PyYAML parse docker-compose.yml → services.zascarr.environment contiene:
  OPS4_ACTUALIZACION_HABILITADA=${OPS4_ACTUALIZACION_HABILITADA:-false}
  OPS4_AUTORIZACION_KEY_FILE=/run/zascarr-ops/actualizar.key
  OPS4_SOCKET_FILE=/run/zascarr-ops/actualizar.sock
volumen: ${ZASCARR_DATA_DIR:-/var/lib/zascarr}/ops:/run/zascarr-ops:ro

# Settings: env → bandera
OPS4_ACTUALIZACION_HABILITADA=true  → True
OPS4_ACTUALIZACION_HABILITADA=false → False
sin variable                        → False
ops4_autorizacion_key_file=/run/zascarr-ops/actualizar.key
ops4_socket_file=/run/zascarr-ops/actualizar.sock

# Transporte v4 con la respuesta del auxiliar
operacion_en_curso -> rechazada        (antes: respuesta_invalida)   ← CM-3
repetida           -> rechazada
caducada           -> rechazada
no_disponible      -> rechazada
aceptada/aceptada  -> aceptada
esquema_invalido   -> rechazada

# Instalador, resolución de grupo por defecto (dry-run, no escribe)
env -u OPS4_GROUP -u OPS_GROUP -u ENV_FILE ZASCARR_PRUEBAS=1 \
  OPS4_DATA_DIR=/tmp/secops4-dry bash scripts/instalar_actualizacion_ops4.sh --dry-run --yes
# → resuelve el grupo del gid 1000 de esta máquina (juanjo), sin leer .env; P1-3-R
# → /tmp/secops4-dry no existe después

# Python 3.11 estático
ast.parse(actualizacion_transporte_v4.py, feature_version=(3, 11))  → OK
```

**NOT RUN (declarado, no PASS):** suite completa; Python 3.11 en runtime; `docker compose config`
(solo parseo de YAML con PyYAML); Docker real; systemd/Pi/VM; instalador real (ni `--activar` ni
instalación con escritura); `update.sh` real; PostgreSQL real; cortes eléctricos/`fsync` reales;
extremo a extremo HTTP contra el auxiliar real (el E2E usa `admitir_v4`); rotación de clave; NTP/TTL.
No se modificó ni añadió ningún ADR en la rama (`git diff origin/main...HEAD -- docs/adr/` vacío):
el riesgo residual de P1-8-R sigue sin registrar.

---

## 8. Snapshot revisado (SHA-256)

`HEAD` = `87b87a340a173402e046a02571c3db83410dbbd7` (rama `feat/ops4-seguridad-443`), árbol limpio.
Merge-base con `origin/main` = `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9`.

| Fichero | SHA-256 | ¿Cambia vs `ff49a7fc`? |
|---|---|---|
| `src/zascarr/web/actualizacion.py` | `2663c04f0f5a24180d519cc429e88d454cdc5c57faad7aa5bce4b059bd8135ed` | no |
| `src/zascarr/web/templates/estado.html` | `4213191843085a2b723f2344c3b61aa06a546b0fc783b1bc49ab2b962f530513` | no |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1bbdbb22ac83d0a2c65e0914359d0ccfa32d2b9d53379fb9125abff14` | no |
| `src/zascarr/services/clave_autorizacion.py` | `075a21d8d1cc7efae8e5dda0d2b36dc7fa6921619b352ce62ab5110d94a8ae0c` | no |
| `src/zascarr/services/solicitud_actualizacion_v4.py` | `9334d5ca34e74b1dfadd7aaf30112df7f9f541a01acacaf33ae3e4bdfd4ccd6c` | no |
| `src/zascarr/services/actualizacion_transporte_v4.py` | `a6c763314a295b84964df1bf178928687c24be01467f8b885be54e3d7e07ca73` | **sí** (CM-3) |
| `src/zascarr/services/ops_actualizacion_v4.py` | `94db06081ebb77fad91d31d3e959b2cbae5530ff42b3bf1b26455e0c71e43dc5` | no |
| `deploy/ops/zascarr_actualizar_aux.py` | `7b33544d80c7ea4035035105e9eceb40ed781785e96970ef7a529e858d37a68c` | no |
| `deploy/ops/protocolo_actualizar_v4_ops4.py` | `72bf693e41af84ec1ddc29515a84022f5884635750d0a0b374a3e75012efa834` | no |
| `deploy/ops/verificador_autorizacion_ops4.py` | `96628781707ba14a15131b9c4cd71c0081b65dd18f39e66aa48db59cedff1b72` | no |
| `deploy/ops/registro_repeticiones_ops4.py` | `3221036741d3495859608dfc4bfa4426a0cfb11bcb3055be1a70a2ae33c6c354` | no |
| `deploy/ops/admision_v4_actualizar_ops4.py` | `21d0822e15f1bc365618a60a1d3ba57ba4d468c329cc2ade14d5c63fc4e1a6fc` | no |
| `deploy/systemd/zascarr-actualizar.service` | `a95ba462563a20b141e2f0cdd0a6bcdb8580b99bddf628f7ff20252d90884165` | no |
| `deploy/systemd/zascarr-actualizar@.service` | `edd7e01151767bfdf3eb937c1c5e98f82953606c8687b72d7199f98d52c50ee6` | no |
| `deploy/systemd/zascarr-actualizar.socket` | `9fbc6ce70f97f9f4afe5f7131da84e7176d47720bbeffc03e5a9b168f2f08a8c` | no |
| `scripts/instalar_actualizacion_ops4.sh` | `48528fa0fe192d4ab7d928a3638dd721b407af39c75bb58465ac5437131d2deb` | **sí** (grupo/mensajes) |
| `src/zascarr/config.py` | `ffd4a087d2925db71ab3b8858ed891c643ee432abdd30dd0b6475522ea054d2a` | no |
| `src/zascarr/main.py` | `3b0ad894cef62b7ea7f119f0782b00390c03297a886edef22344145e788b94ac` | no |
| `src/zascarr/web/estado.py` | `dc0eb311b32e32f1a463cbb07169d10afa9c780542c72a3fc913c8a75545b502` | no |
| `docker-compose.yml` | `2bc3cd340dd073b68849dafcf1526497849a50add8c80278b3b0a09294c3c1a1` | **sí** (OPS4_*) |
| `CLAUDE.md` | `65e68f72c308549e5a2d94a916a3525da1c2ff37c3d82dc4ec0db32457592567` | **sí** (estado) |
| `docs/design/ops4-especificacion-main.md` | `4d6bef80028b28f20566d28449e33694bf31b9713b41cea5b0091e70075bb10a` | **sí** (req. 2/AC-03) |
| `docs/design/ops4-instalador.md` | `5f1e75f1c94cb7410ba05f321ecdab1b67b5f24c6b24db97737601544d3d39fa` | **sí** |
| `docs/design/ops4-ui-integracion.md` | `dde9cb04c3478de290eca999731aca3f204f1a3b914b0d62780a191e5c98e211` | **sí** (ruta clave) |

---

## 9. Vigencia

- Válido **solo** para `87b87a34` con la función deshabilitada y con los valores por defecto. **Caduca**
  con el primer commit, rebase o cambio de cualquiera de los ficheros de §8, de las unidades, del
  auxiliar o de los documentos de contrato que fijan el estado (CLAUDE.md §5.8); el SHA que se fusione
  debe tener su propio dictamen si cambia algo de eso.
- Caducidad ordinaria: 2027-01-20 (60 días), o antes si cambia la decisión de autoridad, el protocolo
  v4, la clave, el registro durable, el instalador, el compose o las unidades.
- **Resumen para el PO:** con la función apagada **no hay hallazgos P0** y **no hay razón de
  seguridad para no fusionar** `87b87a34`, con CF-1…CF-5 (documentación/traza). **No se debe
  habilitar ni desplegar**: el SHA aplica bien CM-3 y la ruta de la clave y CM-2 en parte, pero
  introduce un defecto nuevo en la resolución del grupo del instalador (P1-3-R), deja `operacion_en_curso`
  sin mensaje de «ocupada», y mantiene abiertas P1-6/P1-7/P1-8/P1-9 e I-1…I-9. Este informe **no
  autoriza** habilitar, instalar en la Pi, arrancar el socket ni ejecutar `update.sh` real.

---

## Addendum de continuidad

- Este dictamen **sustituye** como SHA final al de `ff49a7fc` para efectos de la fusión de la rama
  `feat/ops4-seguridad-443`. El informe previo sigue siendo válido como análisis de esa base y de la
  superficie que aquí no ha cambiado.
- Siguiente paso, si el PO quiere habilitar: corregir CE-3-R y CE-4 (pequeñas), y abordar CE-1,
  CE-6/CE-7/CE-8/CE-9/CE-10…CE-12 con sus ensayos aislados; después, un **nuevo** dictamen del SHA
  resultante.


---

## Addendum: correcciones posteriores

Tras este dictamen se corrigieron P1-3-R (`ENV_FILE` definido y grupo resuelto
desde `PGID`, con aborto si no existe), el mapeo de `operacion_en_curso` a
«ocupada» en el transporte/servicio, los mensajes del instalador y varias
referencias documentales obsoletas. El SHA resultante **no está cubierto por
este informe**; requiere un dictamen nuevo antes de fusionar. Sigue siendo
**NO-GO para habilitar o desplegar**.
