# SecOps — Verificación final del SHA `9e97aa9f` (OPS4, #443)

**Rol:** SecOps · **Fase:** verificación final de solo lectura de las correcciones al
dictamen anterior (CLAUDE.md §5.8).
**Fecha:** 2026-11-21 (Europe/Madrid).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443`, rama `feat/ops4-seguridad-443`.
**SHA verificado (árbol limpio):** `9e97aa9fa1d7632f7d49a1740877358e0ff8b5ae` (`git status
--porcelain` vacío al empezar). Commit: «fix(ops): corregir regresión del instalador y mapeo
ocupado (#443)», 2026-11-21 17:35 +0100.
**Commit padre / SHA del dictamen anterior:** `87b87a34` (no se revisa aquí como SHA final; queda
como antecedente).
**Informe previo:** [secops-ops4-sha-final-2026-11-21.md](secops-ops4-sha-final-2026-11-21.md),
que dictaminó **GO para fusionar apagado / NO-GO para habilitar**, con `P1-3-R` (regresión del
grupo/`ENV_FILE` del instalador), `P1-4-R` (mapeo de `operacion_en_curso`) y `CM-3` parcial. Ese
informe lleva un addendum que anuncia estas correcciones y declara que el SHA resultante exige un
dictamen nuevo; **este es ese dictamen**.
**Base frente a `origin/main`:** merge-base `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9`; 98 commits.
`origin/main` = `d5f26df57830d11b42a24c1e5bd4b60a96a2b9d0`; `9e97aa9f` **no** está en `origin/main`.
**Entorno:** venv de pruebas del repo (Python 3.14.4, pytest 9.2.0, ruff 0.17.4); la imagen de
producción es `python:3.11-slim` y `pyproject.toml` exige `>=3.11`. Sin `TEST_DATABASE_URL`, sin
Docker, sin systemd instalado, sin Pi.

**Restricciones respetadas:** no se editó código, plantillas, unidades, instalador, compose ni
`update.sh`; no se hizo commit ni push; no se ejecutó la Pi, Docker real, systemd del host, el
instalador con `--activar` ni `update.sh`. **El único fichero escrito es este informe** (nuevo, no
rastreado). La actualización sigue **DESHABILITADA por defecto**. Este dictamen **no autoriza
habilitar, desplegar, instalar en la Pi, armar el socket ni ejecutar `update.sh` real**.

---

## 0. Veredicto

1. **Hallazgos P0: ninguno.** No hay ruta que ejecute `update.sh` con los valores por defecto, ni
   bypass de la puerta de UI, ni fuga de secreto, ni replay práctico. Las correcciones de este
   SHA no abren ninguna ruta nueva: el único cambio de comportamiento en la app es mapear un
   rechazo del host (`operacion_en_curso`) a un mensaje de «ocupada», y el resto es instalador
   (solo root, manual) y documentación.
2. **`P1-3-R` (instalador: grupo/`ENV_FILE`): CERRADA en código y verificada por sonda.** `ENV_FILE`
   se define y el grupo se deriva de `PGID` del `.env`; si no resuelve, el instalador **aborta antes
   de escribir nada**. Quedan las observaciones residuales P2-R1 (test débil), P2-R2 (escape sin
   documentar), P2-R3 (fallback a gid 1000) y P2-R4 (`--quitar` aborta), ninguna de seguridad con
   la función apagada.
3. **`P1-4-R` / `CM-3` (`operacion_en_curso` → «ocupada»): CERRADA en código.** La cadena
   `rechazo del host → CodigoTransporteV4.OCUPADA → ResultadoSolicitudV4.OCUPADA → mensaje de la UI`
   está verificada con la serialización real del auxiliar y una sonda del servicio y de la ruta. La
   cobertura de test solo llega a la capa de transporte; la regresión de extremo a extremo que pedía
   `CE-4` (con el `procesar` real del auxiliar y el mensaje de UI) **sigue pendiente** (P2-R5).
4. **Fusionar el incremento con la función deshabilitada: GO CON CONDICIONES** (§6.1). Las
   condiciones `CF-R1…CF-R5` son de alcance, traza y documentación; ninguna es un defecto
   explotable con la función apagada y ninguna toca código en servicio.
5. **Habilitar (abrir la ruta, armar el socket, ejecutar el `update.sh` real) o desplegar:
   NO-GO.** Siguen abiertas las condiciones de habilitación del dictamen anterior (`P1-1-R`,
   `P1-6-R`, `P1-7-R`, `P1-8-R`, `P1-9-R`, `I-1…I-9`) y `CE-4` en su parte de regresión.
   Este SHA **no** convierte ninguna en aprobada. **No se autoriza despliegue.**
6. **Alcance exacto:** este informe cubre **exactamente `9e97aa9f`** con árbol limpio y solo es
   válido con la función **deshabilitada** y los valores por defecto. **Caduca** con cualquier
   commit, rebase o cambio de los ficheros de §8. Un commit **solo de documentación** que añada este
   informe no lo invalida; cualquier cambio de código/configuración sí.

---

## 1. Alcance: qué cambia entre `87b87a34` y `9e97aa9f`

`git diff --stat 87b87a34..9e97aa9f` — **11 ficheros, 602 inserciones, 18 borrados**, y ni uno más:

| Fichero | Cambio | Relevancia de seguridad |
|---|---|---|
| `scripts/instalar_actualizacion_ops4.sh` | `+ ZASCARR_ROOT`/`ENV_FILE`; grupo desde `PGID` del `.env` con **aborto** si no resuelve; mensajes de la bandera de UI menos categóricos | **Alta** (root, manual): corrige `P1-3-R`; sin ejecución automática |
| `src/zascarr/services/actualizacion_transporte_v4.py` | `+ CodigoTransporteV4.OCUPADA`; `rechazada/operacion_en_curso → OCUPADA` | Baja: sigue fallando cerrado; ya no etiqueta como «rechazada» genérica |
| `src/zascarr/services/solicitud_actualizacion_v4.py` | `_MAPA_TRANSPORTE`: `OCUPADA → ResultadoSolicitudV4.OCUPADA` | Baja: el mensaje correcto llega a la UI |
| `tests/test_ops4_transporte_v4.py` | +1 aserción para `operacion_en_curso → OCUPADA` | Trazabilidad de `CM-3` (solo capa de transporte) |
| `tests/test_instalar_ops4.py` | `sin_grupo`; +2 casos (grupo desde `.env`/`PGID`; aborto sin grupo); mensaje actualizado | Trazabilidad de `P1-3-R` (ver calidad en §2.1) |
| `docs/design/ops4-auxiliar-unidad.md` | Límites: el instalador ya existe y no activa por defecto | Corrige documentación obsoleta (`CM-2`/`P2-16`) |
| `docs/design/ops4-protocolo-v4.md` | Ya no dice «no conectado»: rama cableada detrás de bandera apagada | Ídem |
| `docs/design/ops4-matriz-evidencia.md` | Recuento 922→924; fila de autorización ya no dice «sin conectar» | Ídem |
| `docs/design/ops4-validacion-suite-2026-11-20.md` | 922→924 pruebas OPS4/paridad | Ídem (recuento reproducido, §2.4) |
| `docs/design/especificacion-ops4-autorizacion.md` | Fila de la matriz: el «33 pruebas» pasa a dato histórico | Ídem |
| `docs/design/secops-ops4-sha-final-2026-11-21.md` | **Añadido** (535 líneas): el dictamen anterior y su addendum, ahora versionado | Trazabilidad; sin efecto en ejecución |

**No cambia** `docker-compose.yml`, `config.py`, `main.py`, `web/actualizacion.py`,
`web/estado.py`, la plantilla de Estado, las tres unidades systemd, el auxiliar, el protocolo, el
verificador, el registro, la admisión, `bootstrap.sh`, `scripts/update.sh`, `web/ajustes.py` ni
`services/runtime_settings.py`. La tabla de SHA-256 de §8 lo acredita: los ficheros sensibles son
**byte a byte** los del SHA dictaminado en el informe previo.

**`CM-4` respetado:** `git diff --stat origin/main...HEAD -- src/zascarr/services/seguridad.py
src/zascarr/web/ajustes.py src/zascarr/services/reautenticacion.py` → **vacío**. La rama no toca la
frontera de «qué exige la contraseña actual».

---

## 2. Verificación de las correcciones

### 2.1 `ENV_FILE` y grupo del instalador (`P1-3-R`)

**Código (`scripts/instalar_actualizacion_ops4.sh`):**

```bash
12: ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
13: ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"
20: leer_env() { [[ -f "${ENV_FILE}" ]] && sed -n "s/^$1=//p" "${ENV_FILE}" | ... || true; }
21: GRUPO="${OPS4_GROUP:-${OPS_GROUP:-}}"
22: if [[ -z "${GRUPO}" ]]; then
23:     gid="$(leer_env PGID)"; gid="${gid:-1000}"
24:     GRUPO="$(getent group "${gid}" 2>/dev/null | cut -d: -f1 || true)"
25: fi
26: if [[ -z "${GRUPO}" ]] || ! getent group "${GRUPO}" >/dev/null 2>&1; then
27:     echo "No se pudo resolver el grupo de servicio (PGID/.env u OPS4_GROUP); no se instala nada." >&2
28:     exit 1
29: fi
```

- `ZASCARR_ROOT` es el padre del repo y el `.env` vive en `ZASCARR_ROOT`, exactamente la convención
  de `bootstrap.sh:174-180`, `scripts/_comun.sh` y `scripts/instalar_ops.sh:14-15`.
- El grupo se valida **dos veces** (si se deriva de `PGID`, se comprueba que el nombre exista;
  después, en general, que `getent group` lo resuelva), y el **aborto ocurre antes** de
  `--dry-run`/destinos de pruebas, de `crear_dirs`, de `crear_clave` y de copiar nada.
- La comparación con OPS1 (`scripts/instalar_ops.sh::resolver_grupo`) se cumple en lo sustancial
  (misma fuente `PGID`, escape explícito, mismo aborto), con las diferencias menores anotadas en
  §5.2 (P2-R2…P2-R4).

**Sondas de solo lectura (destinos bajo `/tmp`, `ZASCARR_PRUEBAS=1`, sin systemd):**

| Sonda | Resultado |
|---|---|
| `.env` con `PGID=24` (grupo `cdrom`), sin `OPS4_GROUP` | `rc=0`; la unidad generada lleva `SocketGroup=cdrom` (no el grupo del gid 1000) |
| `.env` con `PGID=424242` (grupo inexistente) | `rc=1`, «No se pudo resolver el grupo de servicio…»; **no se crea** el directorio de datos |
| `OPS4_GROUP=noexiste` | `rc=1`, mismo aborto; no se escribe nada |
| `--dry-run` (con y sin `.env`) | no escribe nada |
| sin `.env` y sin `OPS4_GROUP` (esta máquina) | `SocketGroup=juanjo` = grupo del gid 1000 (mismo fallback que OPS1; P2-R3) |
| **antes/después**: sin `ENV_FILE`, con `ZASCARR_ROOT/.env` `PGID=24` | **nuevo**: `SocketGroup=cdrom`; **script de `87b87a34`**: `SocketGroup=juanjo` → el defecto queda demostrado y corregido |

La sonda «antes/después» se hizo con el script antiguo extraído con
`git show 87b87a34:scripts/instalar_actualizacion_ops4.sh` en `/tmp` (no se tocó el repo).

**Tests (`tests/test_instalar_ops4.py`):**

- `test_grupo_no_resuelto_aborta` (`:114-124`): lanza el instalador con `PGID=424242`, espera
  `rc=1`, el mensaje de aborto y que **no exista** el directorio de datos. Es un test de regresión
  **efectivo**: con el script antiguo, el mismo entorno terminaba con `rc=2` (salida de `set -e` al
  fallar `getent`) y sin mensaje, de modo que el test falla contra el código viejo.
- `test_grupo_por_defecto_desde_env_pgid` (`:97-111`): **débil** como regresión. Inyecta `ENV_FILE`
  en el entorno (con lo que el script viejo, que leía `${ENV_FILE:-}`, también lo habría leído) y
  escribe `PGID` = `id -g` (1000 en esta máquina, es decir el mismo grupo que el fallback antiguo).
  Lo comprobé: el script de `87b87a34` con el **mismo entorno del test** genera
  `SocketGroup=juanjo`, que es lo que el test espera, así que el test **habría pasado con el código
  defectuoso** en máquinas donde el gid 1000 es el grupo del usuario. No ejercita el `ENV_FILE` por
  defecto (el `ZASCARR_ROOT/.env`) ni un `PGID ≠ 1000`. La corrección real la acreditan las sondas
  de arriba; recomiendo reforzar el test (P2-R1) antes de dar `CE-3-R` por cerrada del todo.
- Los 8 tests del fichero pasan (`--sin-systemd`, directorios temporales; no tocan systemd/root).

**Conclusión `P1-3-R`:** defecto corregido y comportamiento verificado. El hueco es de **cobertura
de test**, no de código.

### 2.2 `operacion_en_curso` → «ocupada» (`P1-4-R` / `CM-3`)

**Cadena verificada, capa por capa:**

1. **Host (sin cambios en este SHA):** `deploy/ops/zascarr_actualizar_aux.py:80-81` responde
   `rechazo("operacion_en_curso")` cuando el cerrojo está tomado; `Respuesta.linea()` serializa
   `{"v":4,"id":…,"resultado":"rechazada","codigo":"operacion_en_curso"}`. `_CODIGOS` ya lo
   aceptaba desde `87b87a34`.
2. **Transporte:** `actualizacion_transporte_v4.py:27` (conjunto cerrado), `:34`
   (`OCUPADA = "ocupada"`) y `:125-126`:
   `rechazada` + `operacion_en_curso → CodigoTransporteV4.OCUPADA` (antes caía en `RECHAZADA`).
3. **Servicio:** `solicitud_actualizacion_v4.py:136`: `OCUPADA → ResultadoSolicitudV4.OCUPADA`
   (antes el diccionario no tenía la clave y el `get` devolvía `NO_DISPONIBLE`).
4. **UI:** `web/actualizacion.py:31` ya tenía el mensaje
   «Hay otra comprobación en curso; espera un momento.» (el fichero **no cambia** en este commit;
   su SHA-256 es el mismo que en `87b87a34`). La puerta de la ruta sigue en `:52-53` (404 antes de
   leer clave o reautenticar).

**Sonda de la cadena completa (sin socket real; serialización del auxiliar real):**

```text
host line: b'{"v":4,"id":"aaaa…","resultado":"rechazada","codigo":"operacion_en_curso"}\n'
transporte: ocupada
servicio:   SolicitudV4(resultado=ResultadoSolicitudV4.OCUPADA, id="aaaa…")
UI:         status 200, body "<p>Hay otra comprobación en curso; espera un momento.</p>"
```

- El host se simuló **con la clase `Respuesta` del auxiliar real** (`deploy.ops.zascarr_actualizar_aux`),
  no con JSON inventado; el servicio se probó con `preparar`/`construir` inyectados y un
  `conversar` que devuelve esa línea; la ruta de UI se probó con el servicio inyectado (mismo patrón
  que sus tests actuales). **No** se ejecutó el socket ni el `procesar` real con cerrojo (NOT RUN).
- No hay reintento automático: `OCUPADA` es un **rechazo** (no se inició nada), y el texto invita a
  esperar, no a reintentar en bucle. Falla cerrado igual que antes; solo mejora el mensaje.

**Cobertura de tests:**

- `tests/test_ops4_transporte_v4.py:56-61` añade la aserción
  `operacion_en_curso → CodigoTransporteV4.OCUPADA`. Cubre la capa que estaba mal.
- **No hay test** de `_MAPA_TRANSPORTE` (servicio) ni del mensaje de la UI para `OCUPADA`; tampoco
  de la cadena con el `procesar` real del auxiliar. Es exactamente la mitad que `CE-4` dejó
  pendiente en el dictamen anterior y sigue pendiente (P2-R5). `test_ops4_auxiliar.py:85` cubre que
  el auxiliar emite `operacion_en_curso`, y este commit cubre que el transporte lo entiende; el
  empalme probado es mi sonda, no un test del repo.

**Conclusión `P1-4-R`:** cerrado a nivel de código y de mensaje. `CM-3` pasa a **CUMPLE en código**;
la regresión exigida por `CE-4` queda como deuda de habilitación (P2-R5).

### 2.3 Mensajes del instalador (`P2-13`, parte script)

Las dos frases incondicionales «La actualización sigue deshabilitada por defecto
(`OPS4_ACTUALIZACION_HABILITADA=false`)» pasan a la forma condicional y verdadera:

```bash
154: say "La bandera de UI depende de OPS4_ACTUALIZACION_HABILITADA (por defecto false)."
161: say "La bandera de UI es OPS4_ACTUALIZACION_HABILITADA (por defecto false)."
```

`tests/test_instalar_ops4.py:59` actualiza la aserción. **`--activar` sigue usando `systemctl
start`** (no `enable`), y sin `--activar` no se arranca nada. El grep de `enable` en el instalador
no devuelve coincidencias (el único `disable` está en la retirada, `:114`).

Queda desactualizada la **documentación**: `docs/design/ops4-instalador.md:14` mantiene «la UI sigue
con `OPS4_ACTUALIZACION_HABILITADA=false`» (puede ser falso si el `.env` —root `600`— la pone en
`true`) y `:24` dice «**6 casos**» cuando el fichero tiene **8 tests** (`--collect-only` = 8). Es
documentación sin efecto en ejecución; P2-R6.

### 2.4 Documentación obsoleta (`CM-2` / `P2-16`)

**Corregido y verificado como verdadero a este SHA:**

- `docs/design/ops4-auxiliar-unidad.md:75-77`: «El instalador ya instala estas unidades sin
  activarlas por defecto y `--activar` inicia el socket sin persistencia. Se probó en la VM con
  `update.sh` falso; no se ha probado el actualizador real ni la Pi.» → coherente con la evidencia
  de VM y con `deploy/systemd/`.
- `docs/design/ops4-protocolo-v4.md:3-6`: «En la rama hay transporte y servicio app, y la
  UI/auxiliar están conectados **solo detrás de la bandera apagada**; no se ha habilitado ni
  desplegado.» → verdadero.
- `docs/design/ops4-matriz-evidencia.md:11` y `:37`: 922→924 pruebas y «la UI, el auxiliar y el
  transporte están conectados detrás de la bandera apagada…» → verdadero; el recuento 924 lo
  reproduje (§7).
- `docs/design/ops4-validacion-suite-2026-11-20.md:89,98`: 924 OPS4/paridad → reproducido.
- `docs/design/especificacion-ops4-autorizacion.md:787`: la fila de «33 pruebas» pasa a dato
  histórico del snapshot → correcto.

**Sigue obsoleto (P2-R7, solo documentación; no cambia el veredicto):**

- `docs/design/ops4-solicitud-v4.md:4`: «**No está conectado** a la web, al auxiliar, a `main.py` ni
  a systemd». El servicio se importa desde `src/zascarr/web/actualizacion.py` y se usa detrás de la
  bandera (apagada). Obsoleto desde la integración de UI.
- `docs/design/ops4-transporte-v4.md:4`: «**No está conectado** a la UI, al auxiliar ni a `main`; no
  existe una unidad de actualización». La UI está conectada a través del servicio y las unidades
  existen en `deploy/systemd/` (el instalador las copia sin activarlas).
- `docs/design/ops4-autorizacion-app-host.md:6-7`: «este contrato no está conectado a la web, el
  auxiliar ni systemd». Mismo caso.
- `docs/design/benchmark-ops4-autorizacion.md:66`: «`ops4-especificacion-main.md#L22` **aún exige**
  comprobación viva del hash». Ese requisito ya se reescribió en `87b87a34`
  (`ops4-especificacion-main.md:22` describe el testigo HMAC); referencia desfasada.
- `docs/design/especificacion-ops4-autorizacion.md:31` y `:783-784`: filas que afirman que el
  requisito 2/AC-03 de `ops4-especificacion-main.md` «contradice la decisión» y «debe corregirse
  antes de habilitar». Ese texto ya se reescribió en `87b87a34`; las filas quedan como registro
  desfasado (la fila de `:787` sí se actualizó; estas no). La fila `:785` sí sigue siendo cierta y
  señala otro documento aún sin corregir:
  `docs/design/ops4-alternativa-actualizador-manual.md:11` sigue diciendo «el auxiliar del host
  comprueba de nuevo la contraseña viva», contra la decisión del 2026-11-20.
- `docs/design/ops4-instalador.md:14,24` (P2-13/P2-R6, arriba).

Ninguna de estas frases altera el comportamiento ni la seguridad; no bloquean fusionar apagado.
Se propone corregirlas o declararlas deuda caducable en el mismo merge o antes de habilitar.

---

## 3. «Deshabilitado por defecto» en `9e97aa9f` (verificado)

| Capa | Evidencia | Resultado |
|---|---|---|
| Bandera de producto | `src/zascarr/config.py:282` `default=False` (SHA-256 idéntico al del dictamen anterior) | **OFF por defecto** |
| Variables del contenedor | `docker-compose.yml:164` `${OPS4_ACTUALIZACION_HABILITADA:-false}` (sin cambios en este SHA) | **OFF por defecto** |
| Ajustes en caliente / BD | `runtime_settings.py` sin campos `ops4_*`; `web/ajustes.py` sin OPS4 (grep) | La UI/BD **no puede** encenderla |
| Botón de Estado | `web/estado.py` lee la bandera (default `False`); `templates/estado.html:13-27` pinta botón deshabilitado y sin `form` cuando está falsa | **Inerte** |
| Ruta POST | `web/actualizacion.py:52-53`: 404 **antes** de leer clave o reautenticar; `tests/test_ops4_ui_gate.py` y `test_ops4_ui_actualizacion.py:28-41` | **404** |
| Arranque / actualización de la app | `bootstrap.sh` y `scripts/update.sh` **sin** referencias a OPS4 (grep); tampoco `src/zascarr/main.py` | **No se ejecuta solo** |
| Instalador de OPS1 | `tests/test_ops4_unidades.py:54-60` exige que `instalar_ops.sh` no instale unidades OPS4 | **No se instala solo** |
| Unidades | `zascarr-actualizar.service` y `zascarr-actualizar.socket` sin `[Install]`; `--activar` usa `systemctl start`, nunca `enable` | No arrancan al boot |
| Ejecución real | `zascarr-actualizar.service` ejecuta `update.sh` real, pero solo se copia con el instalador manual de root y solo corre si root arranca el socket y llega una petición válida | **Sin efecto por defecto** |
| Rama | `9e97aa9f` está en `origin/feat/ops4-seguridad-443` y **no** en `origin/main` (`merge-base --is-ancestor` → no) | **No fusionado ni desplegado** |

**Conclusión §3:** con los valores por defecto de `9e97aa9f` la actualización **sigue
deshabilitada** y nada la ejecuta. Este SHA **no añade** activación a `bootstrap.sh`, `update.sh`,
Ajustes, config, compose ni unidades: solo elimina obstáculos del instalador manual y mejora el
mensaje de un rechazo. La diferencia con `87b87a34` en esta materia es **ninguna**.

---

## 4. No regresión

- **Diff acotado:** solo los 11 ficheros de §1. `git diff --stat 87b87a34..9e97aa9f --
  bootstrap.sh scripts/update.sh src/zascarr/web/ajustes.py
  src/zascarr/services/runtime_settings.py src/zascarr/config.py docker-compose.yml
  deploy/systemd/` → **vacío**.
- **Ficheros sensibles byte a byte iguales** a los del dictamen anterior (§8): `web/actualizacion.py`,
  `autorizacion_actualizacion.py`, `clave_autorizacion.py`, `ops_actualizacion_v4.py`, auxiliar,
  protocolo, verificador, registro, admisión, las tres unidades, `config.py`, `main.py`,
  `web/estado.py`, `docker-compose.yml`, `CLAUDE.md`, `ops4-especificacion-main.md`.
- **Tests dirigidos:** 924 passed en la selección OPS4/paridad
  (`tests/test_ops4_*.py tests/test_ops_paridad.py tests/test_instalar_ops4.py`); 989 passed en la
  selección más amplia del dictamen anterior (antes 987: los +2 son los tests nuevos), 0 fallos.
  No se ejecutó la suite completa.
- **Ruff:** `ruff check src/` → All checks passed!; `ruff check --select S src/` → All checks
  passed!; `ruff check src/ deploy/ tests/test_ops4_transporte_v4.py
  tests/test_instalar_ops4.py` → All checks passed!.
- **Formato:** `ruff format --check` sigue reformateando los mismos 4 ficheros que ya ocurría en
  `87b87a34` (comprobado fichero a fichero extrayendo la versión anterior); el CI no ejecuta
  `format`, así que **no hay regresión de formato**. `bash -n` del instalador → OK;
  `git diff --check origin/main...HEAD` → limpio.
- **Comportamiento nuevo:** las sondas de §2.1/§2.2 muestran que el grupo correcto se usa, que el
  aborto no deja restos y que el rechazo ocupado llega al mensaje; no he encontrado un caso en que
  el cambio abra una ruta, ejecute algo ni degrade un fallo cerrado.
- **No P1 nuevo.** Los `P1` que siguen abiertos son los del dictamen anterior y están **sin
  cambios** en ficheros byte-idénticos (§5.3).

---

## 5. Hallazgos

### 5.1 P0 — ninguno

No hay ejecución de `update.sh` por defecto, bypass de la puerta, fuga de secreto, confusión de
claves/sockets que ejecute algo, ni replay práctico. La función sigue apagada (§3) y los dos
cambios de comportamiento (grupo del instalador y mapeo de `operacion_en_curso`) no crean rutas
nuevas ni amplían privilegios: el instalador lo ejecuta root a mano y el mapeo convierte un
rechazo ya existente en un mensaje más preciso.

### 5.2 P2 — residuales (no bloquean fusionar apagado)

- **P2-R1 — test del grupo por defecto poco discriminante.** `test_grupo_por_defecto_desde_env_pgid`
  inyecta `ENV_FILE` y usa `PGID = id -g` (1000); con el script defectuoso de `87b87a34` habría
  pasado en esta máquina (lo comprobé: genera `SocketGroup=juanjo`). No cubre el `ENV_FILE` por
  defecto ni un `PGID ≠ 1000`. El código sí está corregido (sondas §2.1). Antes de habilitar,
  añadir un caso con `ENV_FILE` sin definir y un `PGID` de un grupo con gid distinto del 1000
  (p. ej. `getent group cdrom`).
- **P2-R2 — escape `OPS4_GROUP` sin documentar en el runbook.** El mensaje de aborto lo menciona y
  el código lo acepta, pero `docs/design/ops4-instalador.md` no lo explica. `CE-3-R` pedía
  documentarlo como escape; queda pendiente.
- **P2-R3 — fallback a gid 1000 si el `.env` no trae `PGID`.** `gid="${gid:-1000}"` es el mismo
  fallback que OPS1; si el grupo 1000 existe pero el servicio corre con otro `PGID`, el grupo del
  socket/clave puede ser incorrecto en silencio. Es improbable (el `.env` de `bootstrap.sh` escribe
  `PGID`), y es el patrón vigente del repo, no una regresión de este SHA. No se considera bloqueo.
- **P2-R4 — `--quitar` también aborta si el grupo no resuelve.** La comprobación de grupo se hace
  antes del modo `--quitar`; si la cuenta/grupo de servicio desapareció, el script no retira las
  unidades (verificado: `rc=1`, unidad sin borrar). Falla cerrado; limpieza manual posible
  (`rm` + `systemctl daemon-reload`). Mismo comportamiento en OPS1. Aceptable, pero conviene
  documentarlo.
- **P2-R5 — regresión de `CE-4` incompleta.** El test nuevo cubre transporte; faltan servicio +
  mensaje de UI y, sobre todo, un test que empalme el `procesar` real del auxiliar con el
  transporte (el E2E de UI sigue usando `admitir_v4` como servidor de prueba). No es un fallo
  funcional (la cadena funciona, §2.2), es cobertura. Deuda de habilitación.
- **P2-R6 — documentación del instalador desactualizada:** `ops4-instalador.md:14` (frase
  incondicional sobre la bandera) y `:24` («6 casos» vs 8 tests). Deriva de `P2-13`.
- **P2-R7 — documentación obsoleta residual** (§2.4): `ops4-solicitud-v4.md:4`,
  `ops4-transporte-v4.md:4`, `ops4-autorizacion-app-host.md:6-7`,
  `benchmark-ops4-autorizacion.md:66`, `especificacion-ops4-autorizacion.md:31,783-784` y
  `ops4-alternativa-actualizador-manual.md:11`.
- **P2-R8 — desviación de `CM-1` sin decisión registrada (`P2-14` del dictamen anterior).**
  `docker-compose.yml:163-166` sigue pasando las tres `OPS4_*` (con default `false`). El efecto es
  que un `.env` de root puede encender la ruta de UI; no activa nada por sí mismo, pero la
  salvaguarda «el `.env` no llega al contenedor» ya no existe y no consta en el árbol ADR ni
  decisión del PO que lo registre. Es condición de traza/proceso (`CF-R2`), no defecto explotable
  con la función apagada.

### 5.3 P1 que siguen abiertos (bloquean habilitar, no fusionar apagado)

Sin cambios respecto del dictamen anterior, y en ficheros byte-idénticos a `87b87a34`:

- **P1-1-R:** `--activar` no tiene confirmación explícita e inequívoca de que se arma ejecución real
  como root; el prompt sigue siendo genérico.
- **P1-6-R / P1-9-R:** estado host persistente y reconciliación tras `INCIERTA` no implementados; los
  requisitos 7 y 8 de `ops4-especificacion-main.md` siguen exigiéndolos.
- **P1-7-R:** sandbox de `zascarr-actualizar.service` (`ReadWritePaths=/run/zascarr-ops.lock`,
  `ProtectSystem=strict`/`ProtectHome=yes`) puede denegar el refresco de OPS1 que `update.sh`
  ejecuta con `|| warn`.
- **P1-8-R:** la clave que autoriza `update.sh` como root vive montada en el contenedor; riesgo
  residual aceptado por decisión, sin ADR que lo registre (la rama sigue sin tocar `docs/adr/`).
- **`I-1…I-9`** del informe `secops-ops4-autorizacion-2026-11-20.md` (arnés real, Pi/VM con
  `update.sh` real, NTP/TTL, suite en 3.11, autorización explícita del PO, etc.), sin cambios.

---

## 6. Condiciones exactas

### 6.1 Para fusionar con la función deshabilitada — GO con estas condiciones

- **CF-R1 — Fusionar exactamente `9e97aa9f`, o un commit posterior solo de documentación** (por
  ejemplo, este informe). Cualquier commit que toque código, tests, unidades, compose o instalador
  **invalida** este dictamen y exige repetirlo sobre el SHA que se fusione (CLAUDE.md §5.8). El
  merge no debe ejecutar `--activar`, no debe tocar la Pi y no debe poner la bandera en el `.env`.
- **CF-R2 — Registrar y aceptar explícitamente la desviación de `CM-1`** (`docker-compose.yml:163-166`
  pasa `OPS4_*`, default `false`) o revertir esas líneas antes de fusionar. Si se acepta, la nota
  debe decir que el `.env` (root `600`) **sí** puede encender la ruta de UI y que la protección que
  queda es la clave/socket no provisionados + el instalador manual de root. Procede del `CF-2`
  anterior y sigue abierta.
- **CF-R3 — Cerrar o declarar deuda caducable la documentación residual** de `P2-R6/P2-R7` en el
  mismo merge (o antes de habilitar). Es documentación sin efecto en ejecución.
- **CF-R4 — No autorizar despliegue en el mismo acto:** la fusión apagada no arranca el socket, no
  instala unidades, no escribe la bandera y no cambia la política de despliegue.
- **CF-R5 — Antes de habilitar, reforzar la cobertura** de `P2-R1` (test con `ENV_FILE` por defecto
  y `PGID ≠ 1000`), `P2-R5` (`CE-4`: `procesar` real → transporte → servicio → mensaje de UI) y
  documentar `OPS4_GROUP` (`P2-R2`).

Estas condiciones son de alcance, traza y documentación; ninguna es un defecto explotable con la
función apagada.

### 6.2 Para habilitar/desplegar — NO-GO

Además de `I-1…I-9`, siguen abiertas `CE-1` (confirmación de `--activar`), `CE-5` (runbook de
activación completo), `CE-6` (estado durable), `CE-7` (sandbox/`ReadWritePaths`), `CE-8` (clave
montada en el contenedor y ADR), `CE-9` (reconciliación tras `INCIERTA`), `CE-10` (fallback al
socket de OPS1), `CE-11` (reserva/inicio atómico) y `CE-12` (resto de P2 de habilitación).

Actualización de estado respecto del dictamen anterior:

- **`CE-3-R`: cerrada en código** (grupo desde `PGID` del `.env`, aborto si no resuelve; verificado
  por sonda y antes/después). Quedan los residuales de test/documentación P2-R1/P2-R2.
- **`CE-4`: cerrada en código, abierta en regresión.** El mapeo a «ocupada» funciona; falta el test
  de extremo a extremo con el `procesar` real y el mensaje de UI (P2-R5).
- **`CE-2`: cerrada en código y doc** (sin `[Install]`, `systemctl start`, mensaje «no persistente»);
  sigue faltando la prueba estática del comando (P2-15 anterior), que no reabre el bloqueo sola.
- **Resto sin cambios.**

**No se concede ninguna aprobación de habilitación ni de despliegue.** Cualquier activación real
exige ventana autorizada, copia previa verificada, revisión de este mismo SHA final y ejecución en
entorno aislado primero (VM/Pi desechable), nunca en producción a partir de este dictamen.

---

## 7. Pruebas, lint y sondas ejecutadas (evidencia)

Entorno: `/mnt/Datos/Documentos/Repos/zascarr/.venv-test` (Python 3.14.4, pytest 9.2.0, ruff
0.17.4). El sandbox de esta sesión tiene `/var/tmp` de solo lectura, así que `--basetemp` se puso en
`/tmp` (tmpfs). Los tests dirigidos usados no dependen del dispositivo; la recomendación de
CLAUDE.md de basetemp en el mismo dispositivo que `/` aplica a la suite completa, que **no** se
ejecutó.

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443

# Selección OPS4/paridad (la que cita la matriz: 924)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/secops-924-bt \
  tests/test_ops4_*.py tests/test_ops_paridad.py tests/test_instalar_ops4.py
# → 924 passed, 1 warning in 26.67s      (--collect-only: 8 tests en test_instalar_ops4.py)

# Selección ampliada del dictamen anterior (+2 tests nuevos)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/secops-final-bt-main \
  tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ops_paridad.py \
  tests/test_instalar_ops.py tests/test_cerrojo_operaciones.py tests/test_compose_env.py
# → 989 passed, 1 warning in 35.19s      (antes de este commit: 987)

# Ruff (equivalente CI: check y check --select S)
ruff check src/                                            # → All checks passed!
ruff check --select S src/                                 # → All checks passed!
ruff check src/ deploy/ tests/test_ops4_transporte_v4.py tests/test_instalar_ops4.py
                                                           # → All checks passed!
ruff format --check <4 ficheros py tocados>                # → reformatearía; idéntico a 87b87a34

bash -n scripts/instalar_actualizacion_ops4.sh             # → OK
git diff --check origin/main...HEAD                        # → limpio
git status --porcelain                                     # → vacío antes de escribir este informe
git diff --stat origin/main...HEAD -- src/zascarr/services/seguridad.py \
  src/zascarr/web/ajustes.py src/zascarr/services/reautenticacion.py   # → vacío (CM-4)
git merge-base --is-ancestor 9e97aa9f origin/main          # → NO (no fusionado)
```

**Sondas de solo lectura (sin efectos; destinos bajo `/tmp`, `ZASCARR_PRUEBAS=1`, `--sin-systemd`):**

```text
# Instalador, grupo desde PGID del .env
.env PGID=24 (cdrom), sin OPS4_GROUP   → rc 0; SocketGroup=cdrom
.env PGID=424242, sin OPS4_GROUP       → rc 1; "No se pudo resolver el grupo…"; data/ no existe
OPS4_GROUP=noexiste                    → rc 1; data/ no existe
--dry-run (con y sin .env)             → no escribe nada
sin .env, sin OPS4_GROUP               → SocketGroup=juanjo (fallback gid 1000, como OPS1)
ANTES/DESPUÉS (zascarr 87b87a34 vs 9e97aa9f), sin ENV_FILE, ZASCARR_ROOT/.env PGID=24:
  nuevo → SocketGroup=cdrom ; antiguo → SocketGroup=juanjo
--quitar con PGID irresoluble          → rc 1; unidad NO retirada (P2-R4)

# Cadena «ocupada» (serialización del auxiliar real, sin socket)
Respuesta("rechazada","operacion_en_curso").linea() → transporte: ocupada
servicio con preparar/construir inyectados             → ResultadoSolicitudV4.OCUPADA
ruta de UI con ese resultado                           → 200, "Hay otra comprobación en curso…"
```

**NOT RUN (declarado, no PASS):** suite completa; Python 3.11 en runtime; `docker compose config`
(solo se cotejaron los ficheros y hashes); Docker real; systemd/Pi/VM; instalador real como root
(ni `--activar` ni instalación con escritura en `/etc`/`/usr`/`/var`); `update.sh` real; socket
Unix real contra el auxiliar con `procesar` y cerrojo; PostgreSQL real; cortes eléctricos/`fsync`
reales; rotación de clave; NTP/TTL; extremo a extremo HTTP con la clave provisionada. No se
modificó ni añadió ningún ADR (`git diff origin/main...HEAD -- docs/adr/` vacío): el riesgo residual
de `P1-8-R` sigue sin registrar.

---

## 8. Snapshot revisado (SHA-256)

`HEAD` = `9e97aa9fa1d7632f7d49a1740877358e0ff8b5ae`, rama `feat/ops4-seguridad-443`, árbol limpio
antes de escribir este informe. Merge-base con `origin/main` = `61f4d53a…`.

**Ficheros que cambian en `9e97aa9f` (vs `87b87a34`):**

| Fichero | SHA-256 |
|---|---|
| `scripts/instalar_actualizacion_ops4.sh` | `ecfee0e0a46f8343e34bb20a74ac898e23adebcc611165c75f8f4df76c822303` |
| `src/zascarr/services/actualizacion_transporte_v4.py` | `dcf1ca9f9fda0397f1ab72b94a799801de2eee67e0f8a8b7f1e2287ec231a922` |
| `src/zascarr/services/solicitud_actualizacion_v4.py` | `bd12e358184955846c320c67029d149e8fab9f5e240a2c9e144f38c4a36bb6db` |
| `tests/test_instalar_ops4.py` | `b15252031e4949bf44c106cd8aba1324915e87503db074a9e96ca8c9cce26143` |
| `tests/test_ops4_transporte_v4.py` | `edc3065480181c5d32d2943b478a12704aca3796ace602be756a4ee1561d3995` |
| `docs/design/especificacion-ops4-autorizacion.md` | `af76a11c65967cba4ff3c61625886c8c8c7f961d8887a0ff03c7e5caec9df8ea` |
| `docs/design/ops4-auxiliar-unidad.md` | `66d52fc49a1a15bd28f98c34f952a63fb2248cd02022eb216956acd6e764a1f1` |
| `docs/design/ops4-matriz-evidencia.md` | `bde70bcf361fa4fd17ee175c9d6968c1a5b993a4d017f484f0b49fc6118a9542` |
| `docs/design/ops4-protocolo-v4.md` | `98bc2d426c767633a5909753ebe213026b8d59de554a59408243548f50a6e2ec` |
| `docs/design/ops4-validacion-suite-2026-11-20.md` | `dbbe3693f43a4e38c3d9dfc5b636d96a045a566d24bf4345a34547a31a7776fa` |
| `docs/design/secops-ops4-sha-final-2026-11-21.md` (añadido) | (informe previo, 535 líneas) |

**Ficheros que NO cambian (byte a byte iguales a `87b87a34`; misma tabla del dictamen anterior):**

| Fichero | SHA-256 |
|---|---|
| `src/zascarr/web/actualizacion.py` | `2663c04f0f5a24180d519cc429e88d454cdc5c57faad7aa5bce4b059bd8135ed` |
| `src/zascarr/web/templates/estado.html` | `4213191843085a2b723f2344c3b61aa06a546b0fc783b1bc49ab2b962f530513` |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1bbdbb22ac83d0a2c65e0914359d0ccfa32d2b9d53379fb9125abff14` |
| `src/zascarr/services/clave_autorizacion.py` | `075a21d8d1cc7efae8e5dda0d2b36dc7fa6921619b352ce62ab5110d94a8ae0c` |
| `src/zascarr/services/ops_actualizacion_v4.py` | `94db06081ebb77fad91d31d3e959b2cbae5530ff42b3bf1b26455e0c71e43dc5` |
| `deploy/ops/zascarr_actualizar_aux.py` | `7b33544d80c7ea4035035105e9eceb40ed781785e96970ef7a529e858d37a68c` |
| `deploy/ops/protocolo_actualizar_v4_ops4.py` | `72bf693e41af84ec1ddc29515a84022f5884635750d0a0b374a3e75012efa834` |
| `deploy/ops/verificador_autorizacion_ops4.py` | `96628781707ba14a15131b9c4cd71c0081b65dd18f39e66aa48db59cedff1b72` |
| `deploy/ops/registro_repeticiones_ops4.py` | `3221036741d3495859608dfc4bfa4426a0cfb11bcb3055be1a70a2ae33c6c354` |
| `deploy/ops/admision_v4_actualizar_ops4.py` | `21d0822e15f1bc365618a60a1d3ba57ba4d468c329cc2ade14d5c63fc4e1a6fc` |
| `deploy/systemd/zascarr-actualizar.service` | `a95ba462563a20b141e2f0cdd0a6bcdb8580b99bddf628f7ff20252d90884165` |
| `deploy/systemd/zascarr-actualizar@.service` | `edd7e01151767bfdf3eb937c1c5e98f82953606c8687b72d7199f98d52c50ee6` |
| `deploy/systemd/zascarr-actualizar.socket` | `9fbc6ce70f97f9f4afe5f7131da84e7176d47720bbeffc03e5a9b168f2f08a8c` |
| `src/zascarr/config.py` | `ffd4a087d2925db71ab3b8858ed891c643ee432abdd30dd0b6475522ea054d2a` |
| `src/zascarr/main.py` | `3b0ad894cef62b7ea7f119f0782b00390c03297a886edef22344145e788b94ac` |
| `src/zascarr/web/estado.py` | `dc0eb311b32e32f1a463cbb07169d10afa9c780542c72a3fc913c8a75545b502` |
| `docker-compose.yml` | `2bc3cd340dd073b68849dafcf1526497849a50add8c80278b3b0a09294c3c1a1` |
| `CLAUDE.md` | `65e68f72c308549e5a2d94a916a3525da1c2ff37c3d82dc4ec0db32457592567` |
| `docs/design/ops4-especificacion-main.md` | `4d6bef80028b28f20566d28449e33694bf31b9713b41cea5b0091e70075bb10a` |
| `docs/design/ops4-instalador.md` | `5f1e75f1c94cb7410ba05f321ecdab1b67b5f24c6b24db97737601544d3d39fa` |
| `docs/design/ops4-ui-integracion.md` | `dde9cb04c3478de290eca999731aca3f204f1a3b914b0d62780a191e5c98e211` |

---

## 9. Vigencia

- Válido **solo** para `9e97aa9f` con la función deshabilitada y con los valores por defecto.
  **Caduca** con el primer commit, rebase o cambio de cualquiera de los ficheros de §8 (o de las
  unidades, el auxiliar o los documentos de contrato que fijan el estado; CLAUDE.md §5.8). El SHA
  que se fusione debe tener su propio dictamen si cambia algo de eso.
- Caducidad ordinaria: **2027-01-20** (60 días), o antes si cambia la decisión de autoridad, el
  protocolo v4, la clave, el registro durable, el instalador, el compose o las unidades.
- Este informe se escribe como **fichero nuevo no rastreado**. Si se versiona, debe ser un commit
  **solo de documentación** (CF-R1) que no altere el código verificado.
- **No autoriza** habilitar, instalar en la Pi, armar el socket, desplegar ni ejecutar `update.sh`
  real. La actualización sigue deshabilitada por defecto.
