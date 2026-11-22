# SecOps — Revisión acotada del SHA `48526e03` (OPS4/#443, Parte A, ronda 2)

> **Revisión de solo lectura. La actualización desde la UI sigue DESHABILITADA y no se
> autoriza ningún despliegue.** No se editó código, unidades, instalador, Compose, plantillas
> ni `update.sh`; no se hizo commit ni push; no se ejecutó la Pi, Docker real, PostgreSQL real,
> systemd del host, `update.sh` real, el instalador con `--activar` ni ningún despliegue.
> **El único fichero escrito es este informe** (nuevo, no rastreado). No autoriza habilitar,
> armar el socket, instalar en producción ni desplegar.

**Rol:** SecOps · **Fase:** revisión acotada de los controles de la Parte A (spec de cierre §1/§3,
A1) en su ronda 2. **Fecha:** 2026-11-22 (Europe/Madrid).
**SHA revisado (árbol limpio al empezar):** `48526e036d0fefb91a3f5b02280e5d3e0bbe3b7f`
(`fix(ops): cerrar P1 de UI-UX de OPS4 (#443)`, 2026-11-22 12:05 +0100).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443`; rama
`feat/ops4-seguridad-443`. `git status --porcelain` **vacío** al empezar; el único cambio
posterior es este documento no rastreado (si se versiona, debe ser un commit **solo de
documentación**).
**Base:** `origin/main` local (sin re-fetch) = `ab33c14737a6cdb204c6b989705306303de75c91`;
merge-base `61f4d53ab8813526a32a6724c8dee9d10ba2f3a9`; **105 commits delante / 129 detrás**.
El rebase de A2 sigue pendiente; cualquier re-fetch/rebase cambia el SHA y caduca este informe.
**Entorno de pruebas:** venv del repo `.venv-test` (Python 3.14.4, pytest 9.2.0, ruff 0.17.4).
La imagen de producción es `python:3.11-slim` y `pyproject.toml` exige `>=3.11`; **Python 3.11
NO se ha ejecutado**.

**Insumos leídos:** [revisión de la PR #1159](ops4-revision-pr1159-2026-11-21.md) y **Parte A**
de [la especificación de cierre](especificacion-ops4-cierre.md) (§1, §3), contrastados con
`deploy/systemd/zascarr-actualizar.service`, `deploy/ops/{estado,zascarr_actualizar_aux,
escritor_estado}_actualizar_ops4.py`, `scripts/instalar_actualizacion_ops4.sh`,
`src/zascarr/{config.py,web/actualizacion.py,services/estado_actualizacion.py}`,
`docker-compose.yml` y los tests OPS4.

---

## 0. Veredicto

1. **P0: ninguno.** Con la bandera por defecto (`false`) no he encontrado ruta que ejecute
   `update.sh`, ni bypass de la puerta de UI, ni fuga de clave/contraseña/testigo, ni escritura
   del estado fuera del directorio `ops` previsto.
2. **P1 nuevos en la superficie revisada: ninguno.** Los controles pedidos (A1/T-10, T-17,
   H-5, lector estricto/monotonía, H-7, bandera y 404) están implementados y cubiertos por
   pruebas que he reproducido (§1 y §3). No hay defecto explotable con la función apagada.
   **Los bloqueantes de habilitación del dictamen anterior siguen abiertos** (H-6, H-10,
   B1/B7, B5/B6, B3): no se convierten en aprobados por este SHA (§5.2).
3. **Fusionar el incremento con la función apagada: GO CON CONDICIONES** (CF-1…CF-5, §5.1).
   Las condiciones son de rebase, alcance (A2–A5) y evidencia (A7/A10), no defectos del código
   revisado. **Este dictamen no cubre el SHA final tras el rebase**: al cambiar el SHA hay que
   repetir la revisión (CA-A-11).
4. **Habilitar (abrir la ruta, armar el socket, ejecutar el `update.sh` real) o desplegar:
   NO-GO** (§5.2). Este SHA **no** cierra ninguna condición de habilitación y **no se autoriza
   despliegue**.
5. **Caducidad:** este informe cubre **exactamente** `48526e03` con árbol limpio y la función
   deshabilitada. Caduca con cualquier commit, rebase o cambio de los ficheros revisados. Un
   commit solo de documentación que añada este informe no lo invalida; cualquier cambio de
   código/configuración/unidades/instalador sí.

---

## 1. Controles verificados

| # | Control exigido | Evidencia en `48526e03` | Resultado |
|---|---|---|---|
| 1 | **`ExecStopPost` único, con prefijo `-` y mapeo `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS`** | Unidad: una sola línea, `ExecStopPost=-/bin/sh -c 'case "$SERVICE_RESULT:$EXIT_CODE:$EXIT_STATUS" in success:exited:0) r=hecha;; exit-code:exited:75) r=fallida;; *) r=incierta;; esac; exec /usr/bin/python3 -I … --resultado "$r"'` ([unit:18](../../deploy/systemd/zascarr-actualizar.service#L18)). Tabla pura `resultado_final()` ([estado_actualizar_ops4.py:49-66](../../deploy/ops/estado_actualizar_ops4.py#L49-L66)) y CLI cerrado (`--resultado` ∈ {hecha,fallida,incierta}, [79-96](../../deploy/ops/estado_actualizar_ops4.py#L79-L96)). La prueba ejecuta **la cadena real de la unidad** sustituyendo solo la ruta instalada del programa ([test_ops4_estado_final_unidad.py:53-77](../../tests/test_ops4_estado_final_unidad.py#L53-L77), tabla en [115-134](../../tests/test_ops4_estado_final_unidad.py#L115-L134)). | **PASA** |
| 2 | **Sin `ExecStartPost`** | `grep '^ExecStartPost='` en la unidad → 0 líneas (solo queda el comentario explicativo [unit:13](../../deploy/systemd/zascarr-actualizar.service#L13)); test estático [test_ops4_unidades.py:38-42](../../tests/test_ops4_unidades.py#L38-L42). | **PASA** |
| 3 | **El auxiliar escribe estado tras consumo durable y no después del `start`** | Orden real: consumo durable (`verificar_autorizacion` → marca `O_EXCL` + `fsync` de fichero y directorio) en [aux:121-131](../../deploy/ops/zascarr_actualizar_aux.py#L121-L131); escritura de `aceptada` en [132-137](../../deploy/ops/zascarr_actualizar_aux.py#L132-L137); `systemctl start` en [138-141](../../deploy/ops/zascarr_actualizar_aux.py#L138-L141); **ninguna escritura tras el start** ([146-148](../../deploy/ops/zascarr_actualizar_aux.py#L146-L148)); si el start devuelve fallo se intenta `fallida` por `publicar_transicion` ([142-145](../../deploy/ops/zascarr_actualizar_aux.py#L142-L145)). Tests: [test_ops4_auxiliar.py:182-205](../../tests/test_ops4_auxiliar.py#L182-L205) y las dos carreras T-17 ([225-264](../../tests/test_ops4_auxiliar.py#L225-L264)). | **PASA** |
| 4 | **Escritor `0640` y dueño `root:<grupo>`** | `MODO_ESTADO = 0o640`; temporal `0600` → `fchmod(0640)` y `fchown(root, gid del directorio ops)` si corre como root ([escritor:35](../../deploy/ops/escritor_estado_actualizar_ops4.py#L35), [68-80](../../deploy/ops/escritor_estado_actualizar_ops4.py#L68-L80), [107-118](../../deploy/ops/escritor_estado_actualizar_ops4.py#L107-L118)). Instalador: `ops` `0750`, `chown root:GRUPO` **sin `|| true`** (aborta si no puede fijar dueño) ([instalar_actualizacion_ops4.sh:91-101](../../scripts/instalar_actualizacion_ops4.sh#L91-L101)). Tests: [test_ops4_escritor_estado.py:119-147](../../tests/test_ops4_escritor_estado.py#L119-L147), [test_instalar_ops4.py:131-146](../../tests/test_instalar_ops4.py#L131-L146) y el lector de la app aceptando el `0640` real del host ([test_ops4_estado_actualizacion.py:155-159](../../tests/test_ops4_estado_actualizacion.py#L155-L159)). | **PASA** |
| 5 | **Lector estricto y monotonía** | Host: `leer_estado_estricto` sin seguir enlaces, sin FIFO/dispositivos, tamaño ≤ 4096, JSON sin claves duplicadas, esquema 1 y campos/tipos cerrados, rechazo de escritura de grupo/otros y detección de cambios entre `fstat`s ([escritor:137-201](../../deploy/ops/escritor_estado_actualizar_ops4.py#L137-L201)); `publicar_transicion` no pisa terminal, conserva `id`/`inicio_epoch`, no baja `actualizado_epoch` y rechaza reloj invertido ([204-240](../../deploy/ops/escritor_estado_actualizar_ops4.py#L204-L240)). El finalizador usa ese lector y esa guarda, y sale `0` sin escribir si no hay estado/terminal/reloj invertido ([estado_actualizar_ops4.py:79-96](../../deploy/ops/estado_actualizar_ops4.py#L79-L96)). Lector de la app: sin seguir enlaces componente a componente, `/proc/self/fd` anclado, `id_esperado` obligatorio, tiempos ordenados y no futuros ([estado_actualizacion.py:54-143](../../src/zascarr/services/estado_actualizacion.py#L54-L143)). Tests: [test_ops4_escritor_estado.py:153-278](../../tests/test_ops4_escritor_estado.py#L153-L278) y [test_ops4_estado_final_unidad.py:149-217](../../tests/test_ops4_estado_final_unidad.py#L149-L217). | **PASA** |
| 6 | **`-` en el cerrojo dentro de `ReadWritePaths`** | `ReadWritePaths=/opt/zascarr /var/lib/zascarr /var/backups/zascarr -/run/zascarr-ops.lock` ([unit:38](../../deploy/systemd/zascarr-actualizar.service#L38)); test [test_ops4_unidades.py:62-70](../../tests/test_ops4_unidades.py#L62-L70) y comprobación de la unidad instalada [test_instalar_ops4.py:149-158](../../tests/test_instalar_ops4.py#L149-L158). **Nota:** las tres rutas literales (`/opt`, `/var/lib`, `/var/backups`) **no** se resuelven por instalador; repo/datos no estándar siguen rompiendo el sandbox (H-7 resto → B3, §5.2). | **PASA (solo cerrojo)** |
| 7 | **Bandera `false` por defecto y `POST /ui/actualizar` → 404 antes de leer clave/reautenticar** | `ops4_actualizacion_habilitada: bool = Field(default=False)` ([config.py:282](../../src/zascarr/config.py#L282)); Compose inyecta `${OPS4_ACTUALIZACION_HABILITADA:-false}` ([docker-compose.yml:164](../../docker-compose.yml#L164)); la ruta comprueba la bandera y lanza `404` **antes** de leer la clave, reautenticar o tocar el socket ([web/actualizacion.py:78-81](../../src/zascarr/web/actualizacion.py#L78-L81)); unidades e instalador sin `[Install]`/`enable`; `--activar` solo hace `systemctl start` no persistente ([instalar_actualizacion_ops4.sh:157-164](../../scripts/instalar_actualizacion_ops4.sh#L157-L164)). Tests: 404 de ruta real con `TestClient` ([test_ops4_ui_gate.py:88-93](../../tests/test_ops4_ui_gate.py#L88-L93)) y 404 sin efecto colateral ([test_ops4_ui_actualizacion.py:28-39](../../tests/test_ops4_ui_actualizacion.py#L28-L39)); `/estado` sin formulario y botón `disabled` ([test_ops4_ui_deshabilitada.py:40-76](../../tests/test_ops4_ui_deshabilitada.py#L40-L76)). | **PASA** |
| 8 | **Sin migración Alembic (A9)** | `git diff --name-only origin/main...HEAD -- alembic/versions/` → **0 ficheros**. El estado es un fichero del host (esquema 1); no hay tabla nueva. | **PASA** |
| 9 | **Entrypoints instalados importan/arrancan con `python3 -I` (A7 punto 5, parcial)** | Sonda en `/tmp` con el instalador en modo pruebas (`ZASCARR_PRUEBAS=1 --sin-systemd`): `python3 -I <lib>/zascarr-estado-actualizar-ops4 --ruta <ausente> --resultado hecha` → `0` sin crear estado; `python3 -I <lib>/zascarr-actualizar-aux` con stdin vacío → `{"v":4,…,"codigo":"no_disponible"}` y `0`, sin escribir estado. La instalación por defecto deja auxiliar y módulos en el **mismo** directorio (`/usr/local/lib/zascarr`), que es el que usa el fallback de import. | **PASA (sonda)** |

**Nota de implementación:** `resultado_final()` es la referencia pura, pero la ruta instalada
real es la tabla `case` de la unidad; la prueba que manda ejecuta esa cadena real (no solo la
función Python), de modo que una divergencia entre ambas hace fallar el test.

---

## 2. Hallazgos

### 2.1 P0 — ninguno

No hay ruta de ejecución ni de escritura con la configuración por defecto: la bandera es
`false`, la ruta responde `404` antes de tocar clave/socket y el instalador no activa nada por
defecto.

### 2.2 P1 nuevos — ninguno en la superficie revisada

Los P1 de habilitación del dictamen anterior **siguen abiertos y sin cambios**; este SHA no los
toca ni los empeora (§5.2). No he encontrado un P1 que bloquee la fusión apagada de estos
controles.

### 2.3 P2 — observaciones no bloqueantes

| Id | Observación | Evidencia | Impacto |
|---|---|---|---|
| P2-1 | Si `iniciar()` **lanza** una excepción (en vez de devolver `False`), el auxiliar responde `no_disponible` pero **no** escribe `fallida`: el estado queda en `aceptada` hasta el siguiente intento o hasta que el lector lo dé `incierta` por antigüedad. `_iniciar()` ya captura `OSError`/`SubprocessError`, así que no es alcanzable por un fallo normal de `systemctl`; es robustez, no un fallo reproducible. | [aux:138-145](../../deploy/ops/zascarr_actualizar_aux.py#L138-L145), [aux:199-209](../../deploy/ops/zascarr_actualizar_aux.py#L199-L209) | Bajo; cubrir también una excepción inesperada del callback `iniciar` y añadir test, en la fase de habilitación. |
| P2-2 | El lector/escritor no autentican el **dueño** del fichero de estado ni del directorio: solo exigen que no haya escritura de grupo/otros. La garantía real es `ops` `0750 root:<grupo>` del instalador. El estado es informativo y no autoriza acciones (la autorización es la clave/testigo), así que no hay escalada con la bandera apagada. | [escritor:137-201](../../deploy/ops/escritor_estado_actualizar_ops4.py#L137-L201); [instalar:91-101](../../scripts/instalar_actualizacion_ops4.sh#L91-L101) | Bajo; al habilitar (B1.6/B7) fijar dueño/modo esperados y no proyectar el estado como prueba de éxito. |
| P2-3 | `ruff check --select S` sobre `deploy/ops` (fuera del CI, que solo escanea `src/`) da **6 hallazgos preexistentes**: S603 en `ejecutor_actualizar_ops4.py` y `lector_credenciales_ops4.py`; S324 en `experimento_objetos_ops4.py`; S603/S607 en `zascarr_actualizar_aux.py` (`_iniciar`, argv fijo y `PATH` fijo) y S101 en `lector_credenciales_ops4.py`. Los dos del auxiliar son preexistentes y no están en el escritor/finalizador nuevos de A1; A3 retiraría la mayoría de los demás. | Salida de Ruff §3 | Bajo; el CI equivalente (`src/`) está limpio. |

---

## 3. Evidencia ejecutada

Todas las pruebas se ejecutaron **desde este worktree** con
`PYTHONPATH="$PWD/src:$PWD"`: el venv compartido tiene `zascarr` instalado en modo editable
apuntando al checkout principal, así que sin ese `PYTHONPATH` se habría probado otro árbol. No
se ejecutó la suite completa.

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443
PY=/mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python
RUFF=/mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/ruff

# SHA, árbol y base (al empezar; después solo se añade este informe)
git rev-parse HEAD          # 48526e036d0fefb91a3f5b02280e5d3e0bbe3b7f
git status --porcelain      # (vacío)
# origin/main local ab33c147…; merge-base 61f4d53…; 105 delante / 129 detrás
git diff --name-only origin/main...HEAD -- alembic/versions/   # (vacío)

# 1) Selección documentada OPS4/paridad/instalador
PYTHONPATH="$PWD/src:$PWD" $PY -m pytest -q \
  tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ops_paridad.py
# 1004 passed, 1 warning

# 2) Bloque dirigido de la Parte A (unidades, finalizador, auxiliar, escritor,
#    instalador, lector de la app, UI deshabilitada/gate, aislamiento)
PYTHONPATH="$PWD/src:$PWD" $PY -m pytest -q \
  tests/test_ops4_unidades.py tests/test_ops4_estado_final_unidad.py \
  tests/test_ops4_auxiliar.py tests/test_ops4_escritor_estado.py \
  tests/test_instalar_ops4.py tests/test_ops4_estado_actualizacion.py \
  tests/test_ops4_ui_actualizacion.py tests/test_ops4_ui_deshabilitada.py \
  tests/test_ops4_ui_gate.py tests/test_ops4_aislamiento.py
# 186 passed, 1 warning

# 3) Ruff CI (pyproject target py311)
$RUFF check src/                    # All checks passed!
$RUFF check --select S src/         # All checks passed!
$RUFF check deploy/ops/estado_actualizar_ops4.py \
            deploy/ops/escritor_estado_actualizar_ops4.py \
            deploy/ops/zascarr_actualizar_aux.py   # All checks passed!
$RUFF check --select S src/ deploy/ops  # 6 hallazgos preexistentes (P2-3), CI no escanea deploy/

# 4) Sonda de layout instalado en /tmp (instalador en ZASCARR_PRUEBAS=1 --sin-systemd):
#    finalizer con python3 -I y estado ausente → 0 y no crea; aux con stdin vacío →
#    respuesta v4 no_disponible y 0, sin crear estado.
```

También se ejecutaron 5 pruebas nombradas de comprobación directa (`test_unico_execstoppost…`,
`test_la_ruta_de_actualizacion_existe_solo_tras_la_puerta`,
`test_deshabilitada_da_404_sin_leer_clave_ni_servicio`,
`test_fichero_queda_0640_para_que_la_app_pueda_leerlo`,
`test_cadena_real_sin_estado_no_crea_ni_falla`): **5 passed**.

**Contraste documental:** la cifra **1004** de OPS4/paridad/instalador coincide con la que
registran [ops4-matriz-evidencia.md](ops4-matriz-evidencia.md) y
[ops4-validacion-suite-2026-11-20.md](ops4-validacion-suite-2026-11-20.md) para el árbol de
Parte A. La ejecución de esta sesión es Python 3.14.4, no la 3.11 de producción.

---

## 4. NOT RUN (declarado, no presentado como PASS)

- **Suite completa** (`pytest -q -rs`) y **Python 3.11** de producción.
- **systemd del host**, `systemd-analyze verify`, arranque real de la unidad y del socket,
  semántica real de `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` con una parada manual o un
  `timeout` reales.
- **`update.sh` real** (ni una vez), incluido el paso 9 (`instalar_ops.sh --refrescar`) dentro
  del sandbox.
- **Instalador sobre host real** y `--activar`; solo se ejecutó en modo pruebas sobre `/tmp` y
  sin systemd.
- **Docker/PostgreSQL reales**, Pi, navegador real, lector de pantalla.
- **Ningún despliegue**; no se tocaron `.env`, `/etc`, `/usr/local`, systemd ni la bandera.
- **`ReadWritePaths` de repo/datos no estándar** (B3) y `ProtectHome` con Git/Docker (B5): no
  verificados; siguen siendo condiciones de habilitación.

---

## 5. Condiciones

### 5.1 Para fusionar la Parte A apagada

- **CF-1 (rebase y re-dictamen).** El SHA revisado está **105 delante / 129 detrás** de
  `origin/main` local (A2 pendiente). Rebasear sobre el `main` vigente **re-fetcheado**, y
  repetir esta revisión acotada sobre el SHA final: este dictamen caduca con el rebase
  (CA-A-07, CA-A-11). No se autoriza fusionar "este SHA tal cual" como final sin esa repetición.
- **CF-2 (alcance Parte A).** Antes de presentar la fusión como Parte A completa, cerrar
  A3 (retirar módulos muertos y protocolo v3: siguen en el árbol `ejecutor_actualizar_ops4.py`,
  `experimento_*`, `lector_credenciales_ops4.py`, `modelo_*`, `protocolo_actualizar_ops4.py`,
  `prueba_viva_ops4.py`, `validar_inventario_ops4.py`, y en la app `actualizacion_transporte.py`,
  `solicitud_actualizacion.py`, `ops_actualizacion_protocolo.py`), A4 (registrar por escrito la
  desviación de Compose; hoy no hay la nota "Desviaciones de despliegue" exigida en ADR 0026 ni
  en `ops4-ui-integracion.md`) y A5 (frases obsoletas todavía presentes en
  `ops4-protocolo-v4.md:42`, `ops4-transporte-v4.md:34`, `ops4-verificacion-contrasena.md:53`,
  `ops4-autorizacion-app-host.md:96`). Son CA-A-08/09/10.
- **CF-3 (suite final).** Ejecutar en el árbol rebasado la suite completa y Ruff en Python 3.11
  además del venv local (CA-A-12); pegar comandos, recuentos y NOT RUN en la PR. Esta sesión
  solo reproduce la selección dirigida de 1004 pruebas, no la suite completa.
- **CF-4 (evidencia y traza).** SHA final, fecha, `origin/main` usado, diff de alcance,
  dictamen A6 enlazado y declaración expresa de que la función sigue **integrada, apagada por
  defecto** y de que B1–B10 no están implementados (CA-A-15). Si este informe se versiona, que
  sea un commit **solo de documentación** posterior al SHA dictaminado.
- **CF-5 (no despliegue).** La fusión no cambia la política de despliegue: sin instalar,
  sin `--activar`, sin `systemctl start/enable`, sin `update.sh`, sin tocar `.env` ni Pi
  (A8/CA-A-13).

**Si el coordinador exige "Parte A completa" como unidad de fusión**, CF-1…CF-5 no están
cerradas y la respuesta operativa es **NO-GO hasta completarlas**; los controles de código
revisados en §1 no añaden ningún bloqueo propio.

### 5.2 Para habilitar o desplegar: NO-GO

Este SHA **no habilita** ni convierte en aprobado ninguna condición de habilitación. Siguen
abiertas, como mínimo:

1. **H-6 / B2 — cerrojo tanteado, no tomado:** el auxiliar suelta el `flock` antes de
   `systemctl start` y `update.sh` lo toma después; hay ventana para aceptar una operación que no
   se ejecuta o para dos operaciones. Requiere reserva atómica.
2. **H-10 / B3 — `update.sh` dentro del sandbox:** `ProtectSystem=strict` no permite el paso 9
   (`instalar_ops.sh --refrescar` escribe `/usr/local/lib/zascarr`, `/etc/systemd/system`,
   `/etc/tmpfiles.d`); el refresco falla como aviso blando o se oculta. `ReadWritePaths` sigue
   con rutas literales (H-7 resto) y `-` solo en el cerrojo.
3. **B1/B7 — estado durable incompleto:** hay estado inicial, terminal de A1 y lectura en la
   respuesta, pero no reconciliación, ni vista de último intento en `/estado` tras reinicio, ni
   proyección cerrada de fases; un `aceptada` huérfano no se cierra en la UI.
4. **B5/B6 — `ProtectHome` con Git/Docker y plazo de 5400 s:** no validados; un SIGKILL a mitad
   de migración no ejecuta guardas (H-9) y el estado no lo sabrá.
5. **B4 — validación real en host aislado:** sin `update.sh` real, sin unidad endurecida real y
   sin socket real; nada de esto se ha probado (NOT RUN, §4).
6. **Reglas de `CLAUDE.md` §5.8:** el diff desde el último dictamen **no** toca
   `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py` (diff vacío), así
   que no dispara la pasada especial por esa regla; la revisión de OPS4 del SHA final sigue
   siendo preceptiva por el benchmark y por CA-A-11.

**No se autoriza habilitar, armar el socket, instalar la clave en producción ni desplegar.**

---

## 6. Límites del informe

- Revisión **acotada** a los controles de §1; no es una auditoría completa del actualizador, del
  protocolo v4 ni de la autorización app-host (eso lo cubren los dictámenes previos y B1–B10).
- No sustituye la revisión de habilitación ni el dictamen del SHA final tras el rebase.
- No certifica la ejecución en la Pi: todo lo que depende del host, de systemd real, de Docker/
  PostgreSQL reales, del `update.sh` real o de Python 3.11 queda **NOT RUN**.
