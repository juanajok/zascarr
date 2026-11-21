# Especificación de cierre de OPS4/#443 — actualización manual desde la UI

> **Estado: especificación de implementación. No es aprobación, ni habilitación, ni
> despliegue, ni autorización para ejecutar nada.** La función sigue apagada y ninguna
> parte de este documento la enciende.
>
> **Fase 2 del pipeline (SPEC.writer).** Solo lectura de código y de documentación. No se
> ejecutó `update.sh`, ni Docker real, ni PostgreSQL, ni systemd del host, ni la Pi, ni el
> instalador con `--activar`, ni ningún despliegue. No se ejecutaron pruebas: todas las
> cifras que se citan son del [benchmark](benchmark-ops4-cierre-2026-11-21.md) y de la
> [revisión de la PR #1159](ops4-revision-pr1159-2026-11-21.md), no de esta sesión. El
> único fichero escrito es este.
>
> **Base:** rama `feat/ops4-seguridad-443`, HEAD **`07161e2a`** (2026-11-21 20:26 +0100).
> `origin/main` local en el momento de escribir: **`2e568293`** (2026-11-21 20:28),
> merge-base **`61f4d53`**; diferencia de **125 ficheros, +16 148 / −23 líneas**, 102
> commits por delante y 118 por detrás. El benchmark se cerró sobre `02d3817` con 142
> ficheros; `origin/main` se movió mientras se redactaba esta fase. **Al ejecutar esta
> spec hay que volver a fijar el SHA y repetir la revisión SecOps.**
>
> **Insumos normativos:** [benchmark de cierre](benchmark-ops4-cierre-2026-11-21.md),
> [revisión PR #1159](ops4-revision-pr1159-2026-11-21.md),
> [ADR 0026](../adr/0026-actualizacion-manual-confianza-main.md),
> [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md),
> [propuesta de actualización a main](ops4-especificacion-main.md),
> [spec histórica BL-OPS4](especificacion-BL-OPS4.md),
> [autorización app-host](ops4-autorizacion-app-host.md),
> [auxiliar y unidad](ops4-auxiliar-unidad.md),
> [transporte v4](ops4-transporte-v4.md),
> [UI](ops4-ui-integracion.md),
> [plan de validación aislada](ops4-plan-validacion-aislada.md) y los dictámenes SecOps
> `secops-ops4-{integracion,sha,verificacion}-final-2026-11-21.md`.
> **El código vigente manda sobre la documentación** cuando discrepan; las
> contradicciones se listan en §2.2 y se cierran en A5.

---

## 0. Resumen y mapa de decisión

Este documento tiene dos partes que **no se pueden mezclar**:

| Bloque | Qué es | Qué autoriza | Qué NO hace |
|---|---|---|---|
| **A — fusión apagada limpia** (§1, §3) | El trabajo mínimo para fusionar OPS4 con la función apagada sin dejar medias verdades. | Fusionar una PR que no enciende la UI ni ejecuta `update.sh`. | No habilita, no despliega, no completa el actualizador, no implementa los contratos de B. |
| **B — condiciones de habilitación** (§4) | Contratos implementables de estado durable, reconciliación, cerrojo/reserva, sandbox/refresco, UI de último intento, migración de estado y validación real. | Nada por sí solo: son el diseño que hay que implementar y verificar **antes** de habilitar. | No enciende nada. Implementarlas con la bandera apagada sigue siendo "sin habilitar". |

**Decisiones que fija esta spec:**

1. **A1 se cierra retirando el `ExecStartPost` actual y dejando un `ExecStopPost`
   correcto, no "arreglando a medias" la fase final.**
   El `ExecStartPost` vigente escribe `hecha` **cuando el proceso de `ExecStart` acaba de
   arrancar**, no cuando termina (systemd.service(5), `ExecStartPost=`: se ejecuta cuando
   el proceso "has been invoked successfully, as determined by `Type=`"; con `Type=exec`
   eso es inmediatamente después del `exec`, [unit:8-14](../../deploy/systemd/zascarr-actualizar.service#L8-L14)).
   Es una media verdad: durante toda la actualización el estado dice `hecha`; si el cierre
   no llega a escribir (disco lleno, unidad parada) o si systemd reporta una parada manual
   como `success`, se queda así; y cuando el `ExecStopPost` sí escribe, el mapeo actual solo
   puede bajar a `fallida`, no a la categoría correcta (`incierta` en timeout/señal). Se
   retira el `ExecStartPost`
   y queda **un** `ExecStopPost`, con prefijo `-`, mapeado por `SERVICE_RESULT`/
   `EXIT_CODE`/`EXIT_STATUS` y con guarda de monotonía. La fase final *correcta* (que recibe
   el código de salida de `update.sh` y escribe terminal) pertenece a B1.
2. **El estado durable completo, el `head0`/`S`, las fases, la reconciliación, la reserva
   atómica, el sandbox y la UI de último intento son B, no A.** A no los implementa y la
   spec no los presenta como resueltos.
3. **El estado pasa a esquema 2 en B; A mantiene el esquema 1.** A no cambia el contrato
   de datos que hoy lee la app; B lo versiona y define la migración (§B1.7).
4. **No hay cambio de protocolo v4 en B.** La reserva y la reconciliación se expresan con
   los códigos de respuesta ya cerrados (`operacion_en_curso`, `no_disponible`) y con el
   estado durable; la app añade contexto leyendo el estado (B7). No se añaden códigos
   libres ni una v5.
5. **El cerrojo de operaciones no se "tantea": se toma como primera acción del
   trabajador** (fd 9 heredado por `exec`, reconocido por
   [_cerrojo.sh:43-58](../../scripts/_cerrojo.sh#L43-L58)) y la aceptación del auxiliar
   solo se completa cuando ve la fase de reserva escrita por el trabajador (§B2).
6. **El refresco de auxiliares sale de `update.sh` bajo la unidad** hacia una unidad fija
   separada de acción fija, o se declara paso manual documentado; en ningún caso un fallo
   de refresco se oculta como actualización completa (§B3).
7. **La UI de último intento solo se pinta con la bandera encendida** y no ofrece reintento
   ciego; lee una proyección cerrada del fichero del host, nunca cadenas libres (§B7).
8. **La habilitación sigue NO-GO** hasta cerrar B1–B4 (P0), B5–B10 y las condiciones
   CE-1…CE-12 / I-1…I-9, con revisión SecOps del SHA final y autorización expresa del PO
   (§7).

**Hallazgos locales nuevos de esta fase** (no estaban en el benchmark; evidencia en §2.2):

- **H-1.** El `ExecStartPost` vigente marca `hecha` al **arrancar**, no al terminar.
- **H-5.** El escritor de estado crea el fichero en **`0600 root:root`** y la app corre como
  `PUID:PGID` sobre un montaje **ro**; aunque existiera el estado, la app no podría leerlo
  (la UI diría siempre "sin noticias"). B1 debe fijar modo `0640 root:<grupo>` y directorio
  `0750 root:<grupo>`.
- **H-13.** `update.sh` sale con **1** tanto antes como después de tocar código/BD; sin fases
  **no se puede distinguir** "falló sin efecto" de "falló con efectos". Por eso A mapea
  "código de salida ≠ 0" a `incierta` salvo el 75 del cerrojo, que por contrato es
  pre-efecto.
- **H-7.** `ReadWritePaths` usa rutas literales `/opt/zascarr`, `/var/lib/zascarr`,
  `/var/backups/zascarr` y el instalador solo sustituye `@REPO@`, `@ZASCARR_DATA_DIR@` y
  `@GRUPO@`; un repo o un directorio de datos no estándar dejan el sandbox incoherente
  (§B3).
- **Nota de SHA:** `origin/main` avanzó durante la redacción (`02d3817` → `2e568293`);
  cualquier cifra de "diferencia frente a main" caduca; vale el SHA que se re-fije al
  ejecutar.

---

## 1. Alcance exacto de esta fase [A]

### 1.1 Qué significa "sin habilitar"

Una fusión "apagada" no es una promesa de seguridad: es la ausencia de una vía de
ejecución. Para esta fase, "sin habilitar" es **todo** lo siguiente, y cada punto tiene
prueba estática o checklist en A7/A8:

| Invariante | Estado exigido a la fusión |
|---|---|
| Bandera de UI | `ops4_actualizacion_habilitada` por defecto `False` ([config.py:281-285](../../src/zascarr/config.py#L281-L285)); Compose inyecta `${OPS4_ACTUALIZACION_HABILITADA:-false}` ([docker-compose.yml:163-167](../../docker-compose.yml#L163-L167)). |
| Ruta web | `POST /ui/actualizar` responde 404 antes de leer clave, reautenticar o tocar el socket ([web/actualizacion.py:78-81](../../src/zascarr/web/actualizacion.py#L78-L81)). |
| Unidad de actualización | Sin `[Install]`; no se habilita al boot ([unit:34](../../deploy/systemd/zascarr-actualizar.service#L34)). |
| Socket | Sin `[Install]`; el instalador no hace `enable` ni `enable --now` ([instalar_actualizacion_ops4.sh:154-162](../../scripts/instalar_actualizacion_ops4.sh#L154-L162)). |
| Instalador | Por defecto provisiona ficheros y **no** activa; `--activar` solo hace `systemctl start` no persistente; no toca la bandera de UI ni `.env`. |
| Clave | No se provisiona en producción en esta fase; si existe en un host de laboratorio, no se usa para ejecutar nada. |
| Host | No se toca la Pi, ni systemd del host, ni Docker/PostgreSQL reales, ni `update.sh`, ni `/etc`, ni `/usr/local`, ni `.env`. |
| Datos | Ninguna migración Alembic nueva; el estado sigue siendo fichero del host, no tabla de la app. |

### 1.2 Dentro y fuera del alcance

**Dentro [A]:** A1–A10 de §3 (limpieza de la fase final, reducción de alcance y rebase,
módulos muertos y protocolo v3, desviación de Compose, documentación a la verdad del SHA,
revisión SecOps del SHA final, suite/lint/pruebas estáticas, no despliegue, no migración de
BD, registro de evidencia).

**Fuera [A]:** todo B (§4): estado durable completo, fases, `head0`/`S`, reconciliación,
reserva atómica, sandbox/refresco, UI de último intento, migración de estado, validación
real, runbook, ciclo de vida de la clave. **Implementar B mientras la bandera está apagada
es legítimo, pero es otra PR y no convierte A en "función terminada".** El benchmark es
explícito: esos puntos "no son condiciones de fusión" pero tampoco se pueden presentar como
resueltos (§12.1, cierre).

### 1.3 Criterio de hecho de esta fase

La fase A termina cuando:

1. existe una PR (o dos PR separadas, A2) cuyo diff es solo el alcance A1–A10;
2. todas las CA-A de §3 están verdes en el SHA rebasado;
3. el SHA final tiene dictamen SecOps (A6) y `git status` vacío;
4. la evidencia (recuentos de suite, NOT RUN, SHA, fecha) queda registrada en la PR y en
   este documento;
5. **la bandera sigue apagada y no se ha desplegado nada**. La fusión no cambia la
   política de despliegue.

### 1.4 Regla de separación A/B

- Un criterio de A se cumple con lo que está en el árbol a la fusión; no se puede cerrar
  citando diseño de B.
- Un criterio de B no se puede cerrar citando A: A no implementa estado durable, ni
  reserva, ni sandbox, ni UI de último intento.
- Ningún texto de la PR de A dirá "actualización implementada", "lista para habilitar" o
  "estado durable resuelto". La fórmula correcta: "integrada, apagada por defecto;
  habilitar exige B1–B10, CE-1…CE-12 y autorización expresa".

---

## 2. Estado de partida normativo

### 2.1 Árbol

- Rama `feat/ops4-seguridad-443`; HEAD `07161e2a`; `origin/main` `2e568293` al escribir;
  merge-base `61f4d53`; 102 commits delante / 118 detrás; 125 ficheros y ~16,1k líneas de
  diferencia. La rama está **apilada y lejos de main**; el rebase sigue pendiente (A2).
- La función sigue apagada: bandera `false`, unidades sin `[Install]`, instalador sin
  activación por defecto, cero despliegues.
- Commits que importan a A1: `9646aaec` (estado inicial y resultado UI), `07161e2a`
  (finalizador y su instalación). La revisión SecOps vigente es de `9e97aa9f`/`ee809327`;
  después hay tres commits de código (`4c07e49e`, `9646aaec`, `07161e2a`), por lo que
  **no cubre el SHA que se fusionaría** (A6).

### 2.2 Hallazgos que la implementación debe tratar

| # | Hallazgo | Evidencia en el árbol | Consecuencia |
|---|---|---|---|
| H-1 | `ExecStartPost` escribe `hecha` al arrancar | [unit:13](../../deploy/systemd/zascarr-actualizar.service#L13); systemd.service(5) (`ExecStartPost=` se ejecuta cuando `ExecStart=` "has been invoked successfully, as determined by `Type=`"; `Type=exec` ⇒ tras el `exec`) | Un fallo posterior puede quedar como `hecha` si el `ExecStopPost` no lo corrige. **No se puede conservar tal cual.** |
| H-2 | `ExecStopPost` mapea todo lo que no es `success` a `fallida` | [unit:14](../../deploy/systemd/zascarr-actualizar.service#L14) | `timeout` y señal (SIGKILL a mitad de migración) se declaran `fallida`, que es una mentira: hay efectos parciales ⇒ debe ser `incierta`. |
| H-3 | El auxiliar escribe `en_curso` **después** de `systemctl start` | [zascarr_actualizar_aux.py:102-118](../../deploy/ops/zascarr_actualizar_aux.py#L102-L118) | Carrera T-17: una unidad que falla rápido y deja terminal puede ser pisada por `en_curso`; un `en_curso` puede pisar un `hecha` si el finalizador escribiera antes. |
| H-4 | El lector exige `id` y exactamente 5 campos | [estado_actualizacion.py:28-32,93-140](../../src/zascarr/services/estado_actualizacion.py#L28-L140) | No hay lectura de "último intento" sin `id`; `/estado` solo pasa la bandera ([web/estado.py:48-56](../../src/zascarr/web/estado.py#L48-L56)). No hay `fase`, `head0`, `S` ni reconciliación. |
| H-5 | El escritor crea el estado en `0600 root:root` | [escritor_estado_actualizar_ops4.py:58-73](../../deploy/ops/escritor_estado_actualizar_ops4.py#L58-L73) (temp `0o600`, rename, sin `chmod`/`chown`); `ops/` es `0750 root:grupo` ([instalar_ops.sh:173](../../scripts/instalar_ops.sh#L173)); la app corre como `PUID:PGID` ([docker-compose.yml:205-206](../../docker-compose.yml#L205-L206)) y el montaje es `ro` ([docker-compose.yml:215](../../docker-compose.yml#L215)) | Aunque B escribiera estado, la app no podría leerlo: "sin noticias" permanente. B1 fija `0640 root:<grupo>`. |
| H-6 | Cerrojo tanteado, no tomado | [zascarr_actualizar_aux.py:84-87,151-166](../../deploy/ops/zascarr_actualizar_aux.py#L84-L166) libera antes de `systemctl start`; [update.sh:58-59](../../scripts/update.sh#L58-L59) lo toma después | Aceptación engañosa y autorización consumida sin efecto si otra operación entra en la ventana. B2. |
| H-7 | `ReadWritePaths` literal y cerrojo sin `-` | [unit:32](../../deploy/systemd/zascarr-actualizar.service#L32): `/opt/zascarr /var/lib/zascarr /var/backups/zascarr /run/zascarr-ops.lock`; el `tmpfiles` que crea el lock lo instala OPS1 ([zascarr-ops.tmpfiles.conf:3](../../deploy/systemd/zascarr-ops.tmpfiles.conf#L3)), no OPS4 ([instalar_actualizacion_ops4.sh:112-152](../../scripts/instalar_actualizacion_ops4.sh#L112-L152)) | Repo/datos no estándar rompen el sandbox; host sin OPS1 puede fallar al arrancar la unidad. B3. |
| H-8 | `ProtectHome=yes` con `git` y `docker`, sin `DOCKER_CONFIG` | [unit:22](../../deploy/systemd/zascarr-actualizar.service#L22); el patrón ya probado está en [zascarr-restaurar@.service:11-13](../../deploy/systemd/zascarr-restaurar@.service#L11-L13) | `docker compose` puede degradarse y un remoto Git con credenciales de home no estar accesible. B5. |
| H-9 | `RuntimeMaxSec=5400` sin trap ni fases | [unit:15-18](../../deploy/systemd/zascarr-actualizar.service#L15-L18); [update.sh:171-177](../../scripts/update.sh#L171-L177) no escribe fases; no hay `trap` | Un SIGKILL a mitad de migración deja código/BD a medias y el estado no lo sabe. B6. |
| H-10 | El paso 9 de `update.sh` (refresco OPS1) falla dentro del sandbox y es aviso blando | [update.sh:222-224](../../scripts/update.sh#L222-L224); `instalar_ops.sh --refrescar` escribe `/usr/local/lib/zascarr`, `/etc/systemd/system`, `/etc/tmpfiles.d` ([instalar_ops.sh:192-208](../../scripts/instalar_ops.sh#L192-L208)) | Actualización "correcta" con auxiliar viejo. B3. |
| H-11 | Alcance apilado y módulos muertos | 125 ficheros; protocolo v3, experimentos, aprobación C-12 y admisión v3 siguen en el árbol aunque el auxiliar/instalador no los usen | Superficie privilegiada y ruido de revisión. A2/A3. |
| H-12 | La ruta de estado es coherente, pero solo en la ruta nominal | Unidad escribe `@ZASCARR_DATA_DIR@/ops/actualizar-status.json` ([unit:13-14](../../deploy/systemd/zascarr-actualizar.service#L13-L14)); Compose monta `${ZASCARR_DATA_DIR:-/var/lib/zascarr}/ops` en `/run/zascarr-ops:ro` ([docker-compose.yml:215](../../docker-compose.yml#L215)); config del contenedor `/run/zascarr-ops/actualizar-status.json` ([config.py:285](../../src/zascarr/config.py#L285)) | Correcto hoy; B1 lo fija como contrato y prohíbe rutas libres. |
| H-13 | `update.sh` usa el código 1 para fallos previos y posteriores a efectos | `die` sale 1 ([_comun.sh:57](../../scripts/_comun.sh#L57)); `set -e` propaga el código del comando que falla; solo el 75 del cerrojo es pre-efecto por contrato | Sin fases no se puede distinguir "falló sin efecto" de "falló con efectos"; el finalizador debe usar `incierta` por defecto (A1). |

### 2.3 Ya cerrado por la revisión: no se reabre

- El fallback al socket de copias está corregido; el POST devuelve un `TemplateResponse`
  dentro de `base.html`; el ADR 0026 existe; la fase final está instalada por el
  instalador; la bandera y las unidades no se activan solas. Esta spec los da por dados.
- **No es una auditoría de seguridad**: eso es SecOps. **No es una aprobación** de la
  decisión de confiar en `main`: eso es ADR 0026. **No es un runbook**: eso es B8.

---

## 3. Parte A — cierre apagado limpio

> A no cambia el comportamiento visible. Quita medias verdades, reduce superficie y deja
> el árbol revisable. Ninguno de estos cambios enciende la función.

### A1 — Cerrar la fase final de estado sin mentir

**Decisión:** se **retira** `ExecStartPost` (H-1) y se sustituye el `ExecStopPost` actual
por **uno solo**, con prefijo `-`, que mapea el resultado real de systemd y nunca inventa
éxito. La fase final definitiva (con fases, `head0`/`S` y reconciliación) es B1 y **no
entra en A**.

**Cambio exacto en `deploy/systemd/zascarr-actualizar.service`:**

- Eliminar la línea `ExecStartPost=...` entera.
- Sustituir la línea `ExecStopPost=` por una única línea equivalente a:

```ini
ExecStopPost=-/bin/sh -c 'case "$SERVICE_RESULT:$EXIT_CODE:$EXIT_STATUS" in \
  success:exited:0) r=hecha;; \
  exit-code:exited:75) r=fallida;; \
  *) r=incierta;; \
esac; exec /usr/bin/python3 -I /usr/local/lib/zascarr/zascarr-estado-actualizar-ops4 \
  --ruta @ZASCARR_DATA_DIR@/ops/actualizar-status.json --resultado "$r"'
```

La unidad exacta (con el salto de línea resuelto o en una sola línea) la valida A7. Las
variables `SERVICE_RESULT`, `EXIT_CODE` y `EXIT_STATUS` las define systemd para
`ExecStopPost`; `EXIT_CODE=exited` + `EXIT_STATUS=0` es el único caso de éxito limpio.
`75` es el único código de `update.sh` que por contrato ocurre **antes** de cualquier
efecto (cerrojo ocupado, [update.sh:58-59](../../scripts/update.sh#L58-L59),
[_cerrojo.sh:59-62](../../scripts/_cerrojo.sh#L59-L62)); el resto de códigos (1 incluido,
`die`, fallo de build/migración/health) no permiten distinguir pre-efecto de
post-efecto ⇒ `incierta` (H-13). Cualquier `timeout`, señal, OOM, parada manual o estado
incoherente ⇒ `incierta`. **Nunca se escribe `hecha` desde otro sitio.**

**Cambio exacto en `deploy/ops/estado_actualizar_ops4.py`:**

1. Añadir una función pura `resultado_final(service_result, exit_code, exit_status)` que
   devuelva `hecha|fallida|incierta|None` con la tabla de arriba, para probarla sin systemd;
   el CLI sigue aceptando `--ruta` y `--resultado` cerrados.
2. Antes de escribir, leer el estado con un lector estricto (no `open()` directo, para no
   seguir enlaces): si no hay estado válido ⇒ salir `0` sin crear nada; si el estado ya es
   **terminal** ⇒ salir `0` sin escribir (monotonía); si `int(time.time()) < inicio_epoch`
   ⇒ salir `0` sin escribir (reloj invertido; el lector lo dará `incierta`).
3. Al escribir, conservar `id` e `inicio_epoch`, actualizar `actualizado_epoch`, y solo
   aceptar la transición si el resultado es coherente con el estado actual
   (`aceptada`/`en_curso` → terminal; terminal no se toca).
4. Devolver `0` cuando no hay nada que escribir y `1` solo si la escritura durable no se
   pudo confirmar. Con el prefijo `-` de la unidad, un fallo del finalizador no convierte
   en fallida una actualización correcta (T-10).

**Cambio exacto en el auxiliar (`deploy/ops/zascarr_actualizar_aux.py`):**

- Mantener `aceptada` **antes** de `systemctl start`; **eliminar la escritura de
  `en_curso` posterior al start** ([líneas 116-118](../../deploy/ops/zascarr_actualizar_aux.py#L116-L118)).
  Si el start falla, escribir `fallida`; si el start devuelve éxito, no volver a escribir
  (el finalizador cerrará). Así no hay ninguna escritura del auxiliar que pueda pisar un
  terminal (T-17).
- Añadir una guarda de monotonía reutilizable en
  `deploy/ops/escritor_estado_actualizar_ops4.py` (p. ej. `publicar_transicion(ruta,
  nuevo, ahora) -> ResultadoEscritura|...`): usa el lector estricto, rechaza
  terminal→no-terminal, rechaza bajar `actualizado_epoch` y rechaza cambiar `id` e
  `inicio_epoch`; devuelve `INCIERTO`/`INVALIDO` cerrados y nunca lanza. La usan el
  auxiliar y el finalizador.
- Mantener el orden de admisión existente (esquema → firma → frescura → cerrojo → testigo
  → consumo → estado → start) **sin consumir la autorización en el tanteo de cerrojo**;
  B2 cambiará el orden definitivo (reserva/confirmación), no A.

**CA-A de A1:**

| CA | Observable | Prueba |
|---|---|---|
| CA-A-01 | La unidad instalada no contiene `ExecStartPost=` y contiene **una** `ExecStopPost=` con prefijo `-` y las tres variables de systemd. | `tests/test_ops4_unidades.py` (contrato estático sobre la unidad sustituida). |
| CA-A-02 | Ejecutando la cadena real de `ExecStopPost` con `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` simulados: `success:exited:0` ⇒ `hecha`; `exit-code:exited:75` ⇒ `fallida`; `exit-code:exited:1` ⇒ `incierta`; `timeout:*` ⇒ `incierta`; `signal:*`/`killed`/`TERM` ⇒ `incierta`; sin estado ⇒ no crea y sale 0; estado terminal ⇒ no cambia; reloj invertido ⇒ no escribe. | `tests/test_ops4_estado_final_unidad.py` (ampliado, ejecutando el comando). |
| CA-A-03 | `id` e `inicio_epoch` se conservan; `actualizado_epoch` no baja; un estado terminal no se sobrescribe. | Mismas pruebas + unidad del escritor. |
| CA-A-04 | Un finalizador que falla al escribir no convierte en `fallida` una unidad correcta (prefijo `-`); un finalizador sin estado sale 0. | `tests/test_ops4_estado_final_unidad.py`. |
| CA-A-05 | El auxiliar no escribe ninguna instantánea después de un `start` correcto; un terminal escrito por el finalizador antes de que el auxiliar vuelva no se pisa (T-17). | `tests/test_ops4_auxiliar.py` (regresión explícita con `iniciar` que escribe terminal de forma síncrona). |
| CA-A-06 | El instalador copia exactamente los módulos que la unidad/auxiliar importan y el finalizador de A1, con los modos previstos; ningún módulo retirado se instala; el test compara la lista del instalador con el cierre de imports. | `tests/test_instalar_ops4.py` + `tests/test_ops4_unidades.py`. |

### A2 — Reducir el alcance apilado y rebasar

**Cambio:** rebasar la rama sobre el `origin/main` vigente al ejecutar (no sobre
`02d3817` ni `2e568293` sin re-fetch) y resolver conflictos; separar en PRs por historia:

1. **#443 A** — aviso de versión observacional (ADR 0025), si aún no está en main.
2. **OPS4** — solo el cierre apagado de esta spec.

Si la separación no es viable sin reescribir historia, como mínimo cada commit debe tener
un alcance único y la PR debe declararlo. **No se rebasa "a la fuerza" con cambios de
otros**; los conflictos se resuelven a mano y se re-ejecuta A7.

**CA-A-07:** `git status` vacío; diff A1–A10 sin ficheros ajenos; `git log --oneline
origin/main..HEAD` agrupable en las historias declaradas; el SHA final es el que revisa
SecOps (A6).

### A3 — Retirar o aislar módulos muertos y el protocolo v3

**Criterio de hecho, no lista cerrada de memoria:** en la PR de OPS4 debe quedar solo el
**cierre de importaciones del auxiliar y del instalador, más lo que importa la app para la
ruta apagada**. Todo lo demás se retira de esta PR (puede vivir en otra rama/PR de B).

Conjunto mínimo que debe quedar (verificado por importación, no por nombre):

- Host: `zascarr_actualizar_aux.py`, `protocolo_actualizar_v4_ops4.py`,
  `verificador_autorizacion_ops4.py`, `registro_repeticiones_ops4.py`,
  `escritor_estado_actualizar_ops4.py` y el finalizador `estado_actualizar_ops4.py`
  (A1), más los módulos que importan.
- App: `clave_autorizacion.py`, `estado_actualizacion.py`, `autorizacion_actualizacion.py`,
  `solicitud_actualizacion_v4.py`, `actualizacion_transporte_v4.py`,
  `ops_actualizacion_v4.py`, `web/actualizacion.py`,
  `templates/actualizacion_resultado.html` y la sección apagada de `estado.html`.
- Instalador: `instalar_actualizacion_ops4.sh`, unidades y socket.

**Se retiran de la PR de OPS4** (provisional; el implementador confirma con el grafo de
importaciones y `grep`): `admision_actualizar_ops4.py`, `admision_host_actualizar_ops4.py`,
`admision_v4_actualizar_ops4.py` (el auxiliar no la importa), `ejecutor_actualizar_ops4.py`,
`experimento_*_ops4.py`, `lector_credenciales_ops4.py`,
`limite_intentos_actualizar_ops4.py`, `modelo_aprobacion_ops4.py`,
`modelo_fases_actualizacion_ops4.py` (se reintroduce en B1),
`protocolo_actualizar_ops4.py`, `prueba_viva_ops4.py`, `validar_inventario_ops4.py`;
`actualizacion_transporte.py`, `solicitud_actualizacion.py`,
`ops_actualizacion_protocolo.py` y sus tests. `test_ops4_aislamiento.py` se adapta para
prohibir que la app importe `deploy/ops` y para que los módulos retirados no se
reintroduzcan por la puerta de atrás.

**CA-A-08:** un script/test de comprobación calcula el cierre transitivo de imports de los
entrypoints instalados y lo compara con la lista de ficheros que copia el instalador;
cualquier diferencia hace fallar la prueba. `grep` de los módulos retirados sin
referencias. Suite verde sin los tests retirados.

### A4 — Registrar la desviación de Compose

**Decisión:** se conserva la inyección de `OPS4_*` en Compose con
`OPS4_ACTUALIZACION_HABILITADA=${OPS4_ACTUALIZACION_HABILITADA:-false}`
([docker-compose.yml:163-167](../../docker-compose.yml#L163-L167)) porque las rutas de
clave/socket/estado solo se usan con la bandera encendida, **pero se registra por
escrito** (condición CF-R2 de SecOps): nota en
[ADR 0026](../adr/0026-actualizacion-manual-confianza-main.md) (sección "Desviaciones de
despliegue") y en `ops4-ui-integracion.md`: el `.env` de root puede encender la UI; el
valor por defecto es `false`; encenderla es una decisión de habilitación con puertas
(§7), no una configuración inocua. Alternativa permitida: revertir la inyección y dejar
las rutas por defecto en `config.py`; entonces A5 lo dice.

**CA-A-09:** prueba estática de que el valor por defecto efectivo es `false` y de que el
ADR/doc contienen la nota; ninguna otra variable `OPS4_*` cambia de valor.

### A5 — Documentación a la verdad del SHA

Actualizar los textos que aún describen un árbol anterior (contradicciones ya señaladas
por SecOps/revisión):

- `docs/design/ops4-protocolo-v4.md:42` — dice "No hay socket, ruta web, auxiliar ni
  unidad de actualización": ya hay auxiliar, unidades y ruta cableada detrás de la
  bandera.
- `docs/design/ops4-transporte-v4.md` (sección "Límites") — dice "no hay ruta UI ni
  unidad": corregir y listar qué falta (estado durable, reserva, sandbox, validación
  real).
- `docs/design/ops4-verificacion-contrasena.md:53` — "todavía sin conectar": la ruta está
  cableada y apagada; la concordancia efectiva de la contraseña sigue pendiente.
- `docs/design/ops4-autorizacion-app-host.md` (cola) — "el contrato permanece sin
  importar desde web/API/main ni el auxiliar" y "No habilitar la UI ni instalar
  unidad/auxiliar": actualizar a "cableado detrás de bandera apagada; unidades
  instalables sin activación".
- `docs/design/ops4-matriz-evidencia.md` — recuentos de pruebas y afirmaciones de
  "sin conectar"/"no hay socket" que ya no son ciertas.
- `docs/design/ops4-ui-integracion.md` y `ops4-auxiliar-unidad.md` — estado real de la
  fase final y sus límites (incluido A1), y que la VM usó `update.sh` falso.
- `CLAUDE.md` (§3.2) — la frase del estado de OPS4 debe coincidir con el SHA: "integrada,
  deshabilitada por defecto; habilitar exige …".
- Recuentos de pruebas: los del SHA rebasado, no los de un árbol anterior.

**CA-A-10:** checklist de docs revisada; `grep` de las frases obsoletas sin resultados
relevantes; toda afirmación de capacidad tiene ruta/línea o SHA; recuentos actualizados;
las secciones "Límites"/"NOT RUN" distinguen lo ejecutado de lo no ejecutado.

### A6 — Revisión SecOps del SHA exacto que se fusiona

**Cambio/procedimiento:** árbol limpio (`git status` vacío), SHA final fijado, y dictamen
de SecOps **del SHA que se fusiona**, no de `9e97aa9f`. Se revisan los tres commits
posteriores y A1–A10. Si el rebase cambia el SHA, se repite el dictamen. Se deja
constancia de si aplica la regla de CLAUDE.md §5.8 ("una fusión que toque qué exige la
contraseña actual espera la pasada final de seguridad"): comprobar si el diff toca
`services/seguridad.py`, `web/ajustes.py` o `services/reautenticacion.py`; si los toca, el
dictamen es del SHA final aunque hubiera uno anterior. Si no los toca, la revisión de
OPS4 sigue siendo preceptiva por el benchmark, pero no por esa regla; decirlo en la PR.

**CA-A-11:** dictamen nuevo en `docs/design/secops-ops4-*-2026-11-21.md` (o fecha de
revisión) con SHA completo y árbol limpio; la PR enlaza el dictamen; no hay commits de
código después del dictamen salvo que se repita.

### A7 — Suite, lint y pruebas estáticas

Ejecutar en el árbol rebasado, Python de producción (3.11) además del venv local:

1. `pytest -q -rs` completo: **0 fallos**.
2. Selección OPS4/paridad/instalador: **0 fallos**.
3. `ruff check src/` y `ruff check --select S src/` (CI:
   [.github/workflows/ci.yml](../../.github/workflows/ci.yml) líneas 130-133).
4. Pruebas estáticas nuevas de A: unidad sin `ExecStartPost`/sin `[Install]`; instalador
   sin `enable`; `--activar` solo `systemctl start`; bandera por defecto `false`; Compose
   por defecto `false`; imports del cierre A3.
5. `python -m compileall` sobre los módulos host copiados si el proyecto lo usa; al menos
   importación limpia con `python3 -I` de los entrypoints (sin ejecutarlos).
6. Si hay `systemd-analyze verify` disponible, pasarlo sobre las unidades sustituidas con
   rutas de prueba (no instala nada).

**CA-A-12:** evidencia pegada en la PR: comandos, versiones, recuentos, 0 fallos, 0
`NOT RUN` presentados como PASS. Un NOT RUN se declara NOT RUN.

### A8 — No desplegar en el mismo acto

Condición CF-R4 de SecOps: la fusión apagada no cambia la política de despliegue. En esta
fase **no** se ejecuta:

- `scripts/instalar_actualizacion_ops4.sh` (ni con `--dry-run` sobre el host real);
- `--activar`, `systemctl start/enable` del socket ni de la unidad;
- `update.sh --rama main` (ni una vez);
- Docker/PostgreSQL reales de la instalación;
- cambios de `.env`, Compose desplegado, systemd del host, Pi;
- provisión de `actualizar.key` en producción;
- ningún despliegue.

**CA-A-13:** la PR declara "no se ha desplegado nada"; `git status` vacío; no hay ficheros
de estado, claves ni sockets nuevos en el host; el `.env` de producción no se toca.

### A9 — Sin migración de base de datos

OPS4 no introduce tablas ni columnas: el estado es un fichero del host. **A no añade
ninguna migración Alembic** y el comportamiento de `alembic upgrade head` de `update.sh`
no cambia. La migración que sí existe es la del **formato del fichero de estado**, que es
B1.7 (y no toca la BD).

**CA-A-14:** `git diff origin/main...HEAD -- alembic/versions/` vacío; `alembic heads` no
cambia; ninguna prueba de A toca la BD.

### A10 — Evidencia y registro

Guardar en la PR (y actualizar este documento en una sección de estado si el PO lo pide):

- SHA base y SHA final; fecha; rama; `origin/main` usado.
- Comandos y recuentos de A7; dictamen A6; lista de NOT RUN.
- Diff de alcance y separación A2/A3.
- Declaración expresa de que la función sigue apagada y de que B1–B10 no están
  implementados.

**CA-A-15:** con A1–A10 verdes, el SHA final puede fusionarse; **la habilitación sigue en
§7**.

### Resumen de criterios de aceptación de A

| CA | Tema | Bloquea fusión |
|---|---|---|
| CA-A-01 | Unidad sin `ExecStartPost`; `ExecStopPost` único con `-` | Sí |
| CA-A-02 | Mapeo `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` probado | Sí |
| CA-A-03 | Monotonía, `id`/`inicio` conservados | Sí |
| CA-A-04 | Fallo del finalizador no marca fallida una actualización buena | Sí |
| CA-A-05 | Auxiliar no pisa terminal (T-17) | Sí |
| CA-A-06 | Instalador copia exactamente lo importado | Sí |
| CA-A-07 | Rebase y separación de alcance | Sí |
| CA-A-08 | Módulos muertos/protocolo v3 fuera; aislados | Sí |
| CA-A-09 | Compose por defecto `false` y desviación registrada | Sí |
| CA-A-10 | Documentación a la verdad del SHA | Sí |
| CA-A-11 | SecOps del SHA final | Sí |
| CA-A-12 | Suite/lint/pruebas estáticas verdes | Sí |
| CA-A-13 | No despliegue | Sí |
| CA-A-14 | Sin migración de BD | Sí |
| CA-A-15 | Evidencia registrada y declaración de apagado | Sí |

---

## 4. Parte B — contratos para habilitar

> **Nada de esta parte está implementado ni autorizado.** Los contratos son
> implementables y verificables; la implementación puede hacerse con la bandera apagada y
> en PRs separadas, pero **no habilita**: la habilitación es §7.

### B1 — Estado durable y reconciliación

#### B1.1 Fichero, propiedad y atomicidad

- **Ruta única:** `<ZASCARR_DATA_DIR>/ops/actualizar-status.json` en el host;
  `/run/zascarr-ops/actualizar-status.json` en el contenedor, por el montaje `ro`
  ([docker-compose.yml:215](../../docker-compose.yml#L215)). La ruta no la elige la
  petición web.
- **Directorio:** `ops` `0750 root:<grupo del servicio>` (patrón de
  [instalar_ops.sh:173](../../scripts/instalar_ops.sh#L173)); el instalador OPS4 lo
  garantiza; si existe con otro dueño/modo, el instalador aborta o corrige con
  confirmación (nunca en silencio).
- **Fichero:** JSON UTF-8 canónico, ≤ 4096 bytes, **`0640 root:<grupo>`** (H-5), regular,
  sin enlaces. El escritor crea temporal exclusivo del mismo directorio, escribe, `fsync`
  del fichero, `fchmod(0640)`, `fchown(root, gid)`, `rename` y `fsync` del directorio;
  cualquier fallo ⇒ resultado incierto y **no** se interpreta como éxito.
- **Lectores:** nunca siguen enlaces, nunca abren FIFO/dispositivo (patrón
  [estado_actualizacion.py:54-141](../../src/zascarr/services/estado_actualizacion.py#L54-L141)),
  comprueban tamaño, `st_size`/`mtime`/`ctime` estables durante la lectura y rechazan
  ficheros con bits de escritura de grupo u otros. La app no escribe este fichero.

#### B1.2 Esquema 2 (contrato cerrado)

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `schema` | entero | Sí | `2`. El lector acepta `1` como legado (B1.7). |
| `id` | 32 hex minúsculas | Sí | Igual al de la petición autorizada; inmutable. |
| `estado` | enum | Sí | `aceptada`, `en_curso`, `hecha`, `fallida`, `incierta`. |
| `fase` | enum | Sí | `preparando`, `reservada`, `copiando`, `avanzando`, `construyendo`, `migrando`, `arrancando`, `verificando`, `hecha`, `fallida`, `incierta` (alineado con [modelo_fases_actualizacion_ops4.py:14-28](../../deploy/ops/modelo_fases_actualizacion_ops4.py#L14-L28), que se reintroduce en B1). |
| `head0` | 40 hex o `null` | Sí | Commit antes del intento; lo fija la entrada de la unidad en P9, antes de efectos, y no cambia. |
| `sha_destino` | 40 hex o `null` | Sí | `S` fijado antes de efectos; inmutable dentro del `id`. |
| `sha_actual` | 40 hex o `null` | Sí | Solo se escribe tras un avance de código confirmado. |
| `unidad` | cadena | Sí | Exactamente `zascarr-actualizar.service`. |
| `inicio_epoch` | entero 63 bits | Sí | ≤ `actualizado_epoch` ≤ ahora. Inmutable. |
| `actualizado_epoch` | entero 63 bits | Sí | No decrece. |
| `codigo` | enum cerrado | Sí o `null` | Códigos de §5; sin texto libre. |
| `avisos` | lista de enum cerrado | Sí | 0–8, únicos, sin texto libre. |
| `alembic_despues` | `[A-Za-z0-9_-]{1,64}` o `null` | Sí | Revisión confirmada tras `alembic upgrade head`. |

**Invariantes `estado` ↔ `fase`** (cualquier combinación fuera de la tabla ⇒ lector
devuelve `incierta`):

| `estado` | `fase` permitida |
|---|---|
| `aceptada` | `preparando` |
| `en_curso` | `reservada`, `copiando`, `avanzando`, `construyendo`, `migrando`, `arrancando`, `verificando` |
| `hecha` | `hecha` |
| `fallida` | `fallida` |
| `incierta` | `incierta` |

**Prohibiciones del contrato:** rutas, nombres de archivo, mensajes de error, salida de
comandos, SHA de proveedores, contraseñas, testigos, firmas, ramas, URLs, nombres de
contenedores o datos del coleccionista. Todo lo que no sea un campo de la tabla ⇒
`incierta` y no se pinta.

#### B1.3 Quién escribe cada fase

| Escritor | Fase que puede escribir | Condición |
|---|---|---|
| Auxiliar (pre-start) | `aceptada`/`preparando` | Tras verificar firma, frescura, admisión y cerrojo; antes de `systemctl start`. |
| Auxiliar (start fallido) | `fallida`/`fallida`, `codigo=inicio_fallido` | Solo si `systemctl start` devuelve fallo y no hay evidencia de unidad. |
| Entrada de la unidad (wrapper, B2) | `en_curso`/`reservada` | primera acción tras tomar el `flock` fd 9; antes de `exec update.sh`; solo si la reserva es vigente y del mismo `id`. |
| `update.sh` (helper de fases) | `en_curso`/{`copiando`,`avanzando`,`construyendo`,`migrando`,`arrancando`,`verificando`} | Solo con `ZASCARR_ACTUALIZAR_UNIDAD=1`; escritura best-effort; no aborta la actualización por no poder anotar una fase (anota aviso `estado_degradado`). |
| Finalizador (último recurso) | terminal desde no-terminal | Lees el estado, aplica la tabla de A1 y la monotonía; nunca escribe `hecha` sin éxito limpio. |
| Reconciliador (B1.5) | `incierta` → `hecha`/`fallida`/`incierta` | Solo root, manual, con evidencia y `codigo=reconciliada`; nunca automático. |

**Ningún otro proceso escribe el fichero.** La app solo lo lee. El auxiliar no conserva el
`flock` de operaciones (B2).

#### B1.4 Reglas de transición (monotonía)

- **M1.** Terminal no vuelve a no-terminal. Terminal no cambia de valor salvo
  `incierta`→terminal por el reconciliador.
- **M2.** `actualizado_epoch` nunca decrece; `inicio_epoch` e `id` nunca cambian.
- **M3.** `sha_destino` no cambia dentro de un `id`; `sha_actual` solo se fija una vez, tras
  avance confirmado.
- **M4.** `avisos` es solo de adición, sin duplicados, máximo 8.
- **M5.** Una escritura que no puede demostrar la transición devuelve incierto y **no
  escribe**. No se "repara" un fichero corrupto sobrescribiéndolo con éxito.
- **M6.** Fichero ilegible, ausente o con esquema desconocido ⇒ el lector devuelve
  `incierta`; el escritor no inventa estado.
- **M7.** Un `id` distinto en el fichero que el del intento que escribe ⇒ rechazo
  (`estado_ajeno`); no se pisa el intento de otro.
- **M8.** Reloj no fiable o invertido ⇒ no se escribe; el lector devuelve `incierta`.

#### B1.5 Reconciliación

**Definición:** determinar, a partir de evidencia **de solo lectura** del host, qué efectos
de un intento quedaron, y anotar un terminal honesto. No es reintentar, no es "arreglar",
no es un rollback. La reconciliación de efectos de código/BD la decide una persona; el
comando solo deja el estado en una categoría cerrada y verificable.

**Comando fijo:** `sudo zascarr-reconciliar-actualizar-ops4` (instalado `0755 root:root`,
sin argumentos libres; como máximo `--si` para confirmar y `--estado <ruta>` de prueba con
`ZASCARR_PRUEBAS=1`). Nunca lo invoca la app, ni el socket, ni un temporizador.

**Evidencia que consulta (solo lectura, comandos fijos):**

1. Unidad: `systemctl show -p ActiveState,SubState,Result,ExecMainCode,ExecMainStatus
   zascarr-actualizar.service`. Si está activa ⇒ **no reconcilia**; avisa de que hay una
   operación en marcha.
2. Cerrojo: prueba `flock -n` sobre `/run/zascarr-ops.lock`; si está ocupado ⇒ no
   reconcilia.
3. Código: `git -C @REPO@ rev-parse HEAD` y comparación con `head0`/`sha_destino`/
   `sha_actual`.
4. Imagen: `docker inspect` del contenedor `zascarr` para leer `BUILD_SHA` del entorno
   (o `docker compose ... exec -T zascarr printenv BUILD_SHA`), comparado con `sha_destino`.
5. Servicio: estado y salud con `docker inspect` / `curl` al healthcheck local con plazo
   corto, sin red externa.
6. BD: `docker compose ... exec -T zascarr alembic current`, comparado con
   `alembic_despues` si está presente; sin ejecutar migraciones.
7. Consumo: si el intento llegó a reserva, comprueba la marca de intento
   `ops4/intentos/<id>` (debe existir; si falta, el intento no arrancó) y crea, si falta,
   la marca durable `ops4/consumidos/autorizacion-<id>` (idempotente) **antes** de escribir
   terminal; si no puede crear la de consumo, aborta sin escribir y deja el intento como
   está. La de intento bloquea el replay aunque la de consumo falte (B2).

**Clasificación (cerrada; se evalúa en este orden y manda la primera fila que encaja):**

| # | HEAD | Imagen `BUILD_SHA` | Servicio | BD | Resultado |
|---|---|---|---|---|---|
| 1 | `= head0` | `≠ sha_destino` | sano | sin migración confirmada (`alembic_despues` ausente) | `fallida` (no se avanzó código; nada que reconciliar) |
| 2 | `= head0` | cualquiera | cualquiera | `alembic_despues` presente o `alembic current` inesperado | `incierta` (contradicción: código sin avanzar pero BD con migración) |
| 3 | `= sha_destino` | `= sha_destino` | healthy | `alembic current == alembic_despues` (o no requerida) | `hecha` (reconciliada) |
| 4 | `= sha_destino` | `≠ sha_destino` | cualquiera | cualquiera | `incierta` (código avanzado, imagen no confirmada) |
| 5 | `= head0` | — | unhealthy/parado | cualquiera | `incierta` (pudo quedar el servicio parado) |
| 6 | cualquiera | cualquiera | unidad activa | — | **no escribe**; esperar o parar a mano |
| 7 | cualquier otra combinación | — | — | — | `incierta` (no se puede afirmar éxito ni ausencia de efectos) |
| 8 | evidencia ilegible/incompleta | — | — | — | `incierta` con `codigo=evidencia_insuficiente` |

Solo el reconciliador puede cambiar un terminal; y solo `incierta`→terminal. Antes de
escribir exige confirmación (`--si`) y deja en el estado `codigo=reconciliada` y el
`actualizado_epoch` del momento. **No borra** el estado anterior sin haber escrito el
nuevo; no toca código, BD, imagen ni contenedor.

**Prohibiciones:** no reintenta una actualización, no ejecuta `rollback.sh`, no restaura
dumps, no hace `git reset`, no borra el estado, no lo llama la UI, no se ejecuta solo al
arrancar. Tras reconciliar, una nueva actualización sigue exigiendo una petición nueva con
su autorización (el cerrojo y la bandera no cambian).

#### B1.6 Lector de la app (proyección cerrada)

- `leer_ultimo_intento(path, *, ahora_epoch=None) -> UltimoIntento` **sin `id`**: devuelve
  un `dataclass(frozen=True)` con `disponible`, `estado`, `fase`, `codigo`, `inicio_epoch`,
  `actualizado_epoch`, `head0`, `sha_destino`, `sha_actual`, `avisos`, `sin_noticias`,
  `legado`; todos cerrados o `None`. No devuelve el `id` a la UI.
- `leer_estado_actualizacion(path, *, id_esperado)` se conserva para la respuesta del POST
  (correlación por `id`); comparte parser con el anterior.
- Deriva `sin_noticias` si el estado es activo y `ahora - actualizado_epoch` supera el
  umbral de la fase (tabla provisional; se fija con medidas en B4):

| Fase | Umbral de "sin noticias" |
|---|---|
| `preparando` | 600 s |
| `reservada` | 120 s |
| `copiando` | 1800 s |
| `avanzando` | 300 s |
| `construyendo` | 5400 s |
| `migrando` | 3600 s |
| `arrancando` | 300 s |
| `verificando` | 600 s |
| desconocida/legado activo | 7200 s |

- Cualquier fallo (OSError, JSON, tipos, tamaño, invariantes) devuelve "no disponible /
  incierta", **nunca lanza** y **nunca** pinta cadenas del fichero. La lectura se hace con
  `asyncio.to_thread` en la vista; la página `/estado` no se cae por esto.

#### B1.7 Migración de estado

No hay migración de base de datos. La migración es del **formato del fichero** y de la
**compatibilidad entre versiones de app y host**:

| Fichero | Lector | Resultado |
|---|---|---|
| esquema 1 (5 campos) | app A (v1) | igual que hoy |
| esquema 1 | app B (v2) | se acepta como **legado**: se proyecta `estado`, `fase=null`, `head0/S=null`, `legado=true`; si está activo y viejo ⇒ `sin_noticias`; no se reescribe desde la app |
| esquema 2 | app A (v1) | `incierta` (campos extra; falla cerrado) — **no es un fallo de la app**, es incompatibilidad conocida |
| esquema 2 | app B (v2) | completo |
| esquema 3 o desconocido | cualquiera | `incierta`; no se interpreta |
| JSON corrupto / enlaces / FIFO | cualquiera | `incierta`; no se toca |

Reglas:

1. El escritor v2 **siempre** escribe esquema 2; nunca "baja" a 1.
2. La primera escritura sobre un fichero legado lo reemplaza atómicamente; no hay
   conversión in-place ni ficheros temporales persistentes.
3. **Skew app/host:** una app vieja con host nuevo dirá "no se puede comprobar" (honesto).
   `rollback.sh` revierte código de la app pero **no** los binarios host de
   `/usr/local/lib/zascarr`; el runbook de B8 debe reinstalar/refrescar el host o retirar
   el socket y apagar la bandera antes de un rollback, y comprobarlo. Mientras la función
   esté apagada esto no se da en producción; se prueba en B4.
4. El estado no guarda historial de intentos anteriores (solo el último). Es un límite
   declarado: el "historial de versión instalada" del benchmark es P2 y no bloquea la
   habilitación; si se añade, será un fichero aparte con su propio contrato, fuera de B1.
5. Un intento con `id` distinto al del fichero no se "migra" ni se atribuye.

**CA-B1:**

| CA | Observable |
|---|---|
| CA-B1-01 | Esquema 2 válido con todos los campos e invariantes: se lee exacto; un campo de tipo incorrecto, extra, duplicado o fuera de límite ⇒ `incierta`. |
| CA-B1-02 | Invariantes `estado`↔`fase`: cada par de la tabla se acepta; cualquier otro ⇒ `incierta`. |
| CA-B1-03 | Monotonía M1–M8 probada con escritor y lector (terminal no se pisa, `id`/`inicio` inmutables, avisos acotados, reloj invertido). |
| CA-B1-04 | Fichero `0640 root:<grupo>` y directorio `0750 root:<grupo>` verificados en instalación/prueba de host; lector rechaza grupo/otros con escritura; la app puede leer el fichero real (prueba de integración de permisos, no solo lógica). |
| CA-B1-05 | Reconciliador: unidad activa o cerrojo ocupado ⇒ no escribe; la matriz ordenada de B1.5 se respeta (incluidas unidad activa, combinación no prevista y evidencia insuficiente) con dobles; comprueba/crea la marca de intento y crea la de consumo antes del terminal; no toca código/BD/imagen. |
| CA-B1-06 | `leer_ultimo_intento` sin `id` funciona para `hecha`, `fallida`, `incierta`, activo fresco, activo viejo (`sin_noticias`), legado y fichero ilegible; no revela el `id` a la UI. |
| CA-B1-07 | Umbrales por fase: cada fase activa con `ahora` justo por debajo/encima del umbral produce "sin noticias" solo cuando corresponde. |
| CA-B1-08 | Migración: matriz de B1.7 completa (esquema 1/2/3, app v1/v2) sin excepciones ni caídas; el escritor v2 no escribe esquema 1. |
| CA-B1-09 | Sin secretos: estado no contiene rutas, salida de comandos, testigo, contraseña, firma, URL ni datos del coleccionista; test de lista negra sobre el JSON. |
| CA-B1-10 | `/estado` sigue sirviéndose si el fichero falta, está corrupto o el disco falla; no bloquea la página ni consulta la BD por esto. |

---

### B2 — Cerrojo y reserva: secuencia exacta

**Componentes:**

1. **Cerrojo de operaciones** `/run/zascarr-ops.lock` (`flock`, fd 9), el mismo de
   [_cerrojo.sh](../../scripts/_cerrojo.sh). Lo toman `update.sh`, `backup.sh`,
   `rollback.sh`, `restaurar_datos.sh` y `probar_restauracion.sh`.
2. **Cerrojo de admisión** `<ZASCARR_DATA_DIR>/ops4/admision.lock` (`flock`, fd propio):
   solo serializa **auxiliares** (dos peticiones simultáneas no pueden escribir dos
   reservas). No es el cerrojo de operaciones y **no** se mantiene durante la actualización.
3. **Entrada de la unidad** `zascarr-actualizar-entrada` (wrapper fijo, `0755 root:root`,
   instalado por el instalador): primera acción = abrir/crear el cerrojo de operaciones,
   `flock -n` en fd 9; si está ocupado ⇒ sale 75 **sin efectos**; si lo toma, escribe la
   fase `reservada` con el estado vigente y hace `exec bash @REPO@/scripts/update.sh
   --rama main` conservando fd 9 (el `exec` de bash no cierra el descriptor; `_cerrojo.sh`
   lo reconoce por dispositivo:inodo y re-`flock`ea idempotente).
4. **Reserva** = la instantánea durable `aceptada`/`preparando` con `id`, escrita por el
   auxiliar **antes** del `start`, más la confirmación de la fase `reservada` escrita por
   la entrada. La reserva no es el `flock` (no se puede transferir a systemd) ni un
   descriptor en memoria: es el estado durable + el cerrojo tomado por el trabajador.
5. **Marca de intento**: `ops4/intentos/<id>` (`O_EXCL` + dos `fsync`, `0600 root`),
   creada junto con la reserva **antes** del `start`. Acredita que la petición llegó a
   admitirse; si no se puede crear, no se arranca. Es la que impide el replay de un
   intento que arrancó aunque la marca de consumo posterior no llegara a escribirse.
6. **Consumo de la autorización**: marca durable `ops4/consumidos/autorizacion-<id>`
   (`O_EXCL` + dos `fsync`, ya existente). **Orden nuevo:** no se consume en el tanteo;
   se consume **después** de confirmar que el trabajador arrancó con la reserva (paso P11),
   o al reconciliar un intento que llegó a reserva y quedó sin confirmar. La marca de
   intento (5) es independiente y no sustituye al consumo: una ceremonia de admisión no es
   una autorización, y viceversa.
7. **Verificador en dos fases**: el módulo actual `verificar_autorizacion` valida formato,
   firma, campos, ligadura por `id`, ventana y **reclama** el consumo en una sola llamada
   ([verificador_autorizacion_ops4.py](../../deploy/ops/verificador_autorizacion_ops4.py)).
   B2 debe separarlo en `verificar_testigo_sin_consumo(...)` (misma validación, sin callback
   de consumo) y `reclamar_consumo(id)` (solo crea la marca durable). El segundo solo se
   admite en el mismo proceso y tras el primero; no se re-decodifica ni se acepta un
   testigo no verificado. Ambas funciones mantienen los códigos cerrados actuales.

**Secuencia (P0–P14):**

| Paso | Quién | Acción | Escritura durable | Si falla |
|---|---|---|---|---|
| P0 | UI | `POST /ui/actualizar` con contraseña y confirmación; la app reautentica y emite testigo v4. | — | respuesta de error; no hay testigo |
| P1 | App | envía la línea v4 por el socket dedicado. | — | `no_disponible` (no se prueba nada) |
| P2 | Auxiliar | valida línea, esquema, firma HMAC y frescura (≤ 120 s); **no consume**. | — | `esquema_invalido`/`firma_invalida`/`caducada` |
| P3 | Auxiliar | toma el **cerrojo de admisión** (no bloqueante, ≤ 2 s). | — | `operacion_en_curso`; sin estado, sin consumo |
| P4 | Auxiliar | comprueba el **cerrojo de operaciones** sin tomarlo. Si ocupado ⇒ responde ocupada. | — | `operacion_en_curso`; sin estado, sin consumo |
| P5 | Auxiliar | lee el estado con lector estricto: si hay un intento activo (mismo u otro `id`) o un no-terminal ilegible ⇒ rechaza. Si el `id` de la petición ya aparece en el estado o en la marca de intento `intentos/<id>` ⇒ `repetida`. | — | `no_disponible`/`repetida`; sin consumo |
| P6 | Auxiliar | verifica el testigo con `verificar_testigo_sin_consumo` (formato, firma, dominio, `id`, ventana); los directorios `intentos` y `consumidos` se abren al inicio del proceso (como hoy `consumidos`). | — | `autorizacion_invalida`/`caducada`/`no_disponible`; sin consumo |
| P7 | Auxiliar | crea la **marca de intento** `ops4/intentos/<id>` y escribe la **reserva** `aceptada`/`preparando` con `id`, `inicio` y `unidad`. `head0` aún es `null`. | Sí (`fsync` de ambos) | `no_disponible`; no arranca, no consume, no queda intento |
| P8 | Auxiliar | `systemctl start --no-block zascarr-actualizar.service` (fijo, plazo 5 s). | — | si el `start` falla: escribe `fallida`/`inicio_fallido`; no consume; `no_disponible` |
| P9 | Entrada | toma el `flock` fd 9. Si ocupado ⇒ sale 75 **sin efectos** (el `ExecStopPost` dejará `fallida`/`ocupada`). Si lo toma: valida reserva vigente (`id` presente, estado `aceptada`/`preparando`, `inicio` dentro de `RESERVA_VIGENCIA_S=300`); calcula `head0` con `git rev-parse HEAD` y escribe `en_curso`/`reservada` con `head0`; `exec update.sh`. | Sí | sale 75/2 antes de efectos |
| P10 | Auxiliar | espera hasta 5 s (medido en B4; el auxiliar tiene `RuntimeMaxSec=45 s`) a ver el `id` + `en_curso`/`reservada` (o un terminal) en el estado. | — | sin confirmación ⇒ P12 |
| P11 | Auxiliar | confirmado: **consume** la autorización con `reclamar_consumo(id)` y responde `aceptada`. | Sí | si el consumo falla: escribe `incierta`/`consumo_no_confirmado` si puede; responde `incierta` (nunca `rechazada`); la marca de intento de P7 sigue bloqueando el replay |
| P12 | Auxiliar | no confirmado: si hay evidencia de unidad/terminal ⇒ consume y responde `ocupada`/`incierta` según el terminal; si es ambiguo ⇒ escribe `incierta`/`arranque_ambiguo`, consume si puede y responde `incierta`. | Sí | siempre falla cerrado; nunca "rechazada" si pudo arrancar algo; la marca de intento bloquea el replay |
| P13 | Trabajador | `update.sh` escribe fases (helper) y termina; el finalizador escribe terminal (A1/B1). | Sí | terminal honesto o queda activo ⇒ UI "sin noticias" |
| P14 | Auxiliar | libera el cerrojo de admisión. | — | — |

**Reglas de ocupado y consumo (resuelven T-01/T-02/T-04):**

- Ocupado **detectado en P4** (copia/restauración/manual en curso): respuesta
  `operacion_en_curso`; **no** se escribe estado ni se consume la autorización (T-02).
- Ocupado **descubierto por el trabajador en P9** (carrera P4→P9): el `start` se hizo; se
  marca `fallida`/`ocupada` (sin efectos) y **sí** se consume la autorización en P12,
  porque la petición ya se admitió y no debe poder repetirse (T-04). La UI recibe "otra
  operación en curso"; el usuario puede pedir una autorización nueva.
- Dos peticiones simultáneas: el cerrojo de admisión serializa P3–P14; la segunda recibe
  `operacion_en_curso` sin escribir estado ni consumir (T-01).
- Un `id` repetido se rechaza por la **marca de intento** (cualquier petición que llegó a
  reserva) o por el `id` del estado (P5); nunca se ejecuta dos veces. La marca de intento
  se crea **solo** después de P5–P7; un ocupado detectado en P4 no la crea y por tanto no
  quema la autorización.

**Ventanas de caída y resultado (T-05/T-16):**

| Ventana | Estado persistido | Efectos posibles | Próxima petición | Salida |
|---|---|---|---|---|
| Antes de P7 | ninguno | ninguno | normal | puede admitirse (nada ocurrió) |
| Entre P7 y P8 | reserva + marca de intento | ninguno | P5 ve activo y el intento ⇒ rechaza; tras umbral ⇒ "sin noticias"; reconciliar cierra | no se relanza solo |
| Entre P8 y P9 | reserva + marca de intento (unidad puede estar arrancando) | posible unidad arrancando | P5 rechaza; reconciliar decide | incierta/fallida según evidencia |
| Entre P9 y P13 (trabajador vivo) | fases | actualización en curso | ocupada hasta que termine | terminal |
| Durante P10 (auxiliar muerto) | fases | actualización continúa | P5 rechaza; terminal la escribe el trabajador; marca de intento bloquea replay | el auxiliar no responde: transporte `incierto` |
| Tras P11 y antes de responder | terminal/en curso + intento + consumo | los reales | replay ⇒ `repetida` | el usuario ve `incierta`/sin respuesta; no reintenta |
| Consumo no confirmado (P11) | terminal/en curso + intento, sin consumo | los reales | replay bloqueado por la marca de intento | incierta; reconciliar consume si falta |
| Tras P12 ambiguo | `incierta` + intento | posibles | P5 rechaza activo/no-terminal; reconciliador cierra | incierta |

**Reglas del trabajador:** la toma del cerrojo es **siempre** la primera acción; ninguna
escritura de estado ni efecto ocurre antes; si la reserva no es vigente (caducada,
`id` ajeno, terminal) sale sin efectos. `update.sh` conserva el descriptor 9 y `set -e`;
el `trap` de B6 anota `incierta`/`senal` si puede.

**CA-B2:**

| CA | Observable |
|---|---|
| CA-B2-01 | Dos auxiliares concurrentes: como máximo una reserva y una unidad; la otra recibe ocupada sin escribir estado ni consumir (procesos reales, socket temporal). |
| CA-B2-02 | Petición mientras corre copia/restauración/manual: ocupada, sin estado nuevo y sin consumo. |
| CA-B2-03 | Carrera P4→P9: el trabajador sale 75 antes de efectos; el estado queda `fallida`/`ocupada`; la autorización no se reutiliza. |
| CA-B2-04 | Orden de escrituras verificable: marca de intento y reserva antes de `start`; `reservada` + `head0` tras `flock` y antes de `exec`; consumo después de la confirmación. |
| CA-B2-05 | Un `id` repetido no ejecuta una segunda vez: marca de intento, marca de consumo o `id` del estado; un ocupado en P4 no crea intento ni quema la autorización. |
| CA-B2-06 | Corte simulado en cada ventana de la tabla: estado y siguiente petición según lo esperado; nunca se relanza solo. |
| CA-B2-07 | `update.sh` invocado a mano (sin unidad) sigue funcionando y no escribe estado (no hay `ZASCARR_ACTUALIZAR_UNIDAD`). |
| CA-B2-08 | El trabajador hereda fd 9 y `_cerrojo.sh` no crea uno nuevo; un segundo `update.sh` sale 75. Prueba con dos procesos reales y `OPS_LOCK_FILE` de pruebas. |
| CA-B2-09 | `verificar_testigo_sin_consumo` y `reclamar_consumo` separados: la primera no crea marcas; la segunda solo funciona tras la primera y en el mismo proceso; un testigo no verificado no consume. |
| CA-B2-10 | La marca de intento no se puede crear (disco lleno/permisos) ⇒ no hay `start`, no hay estado activo y no se consume; una marca de intento existente bloquea el replay aunque falte la de consumo. |

---

### B3 — Sandbox y refresco de auxiliares

#### B3.1 Unidad de actualización (contrato exacto)

| Directiva | Valor exigido | Motivo |
|---|---|---|
| `Type` | `exec` | Supervisa bash; `ExecStopPost` al terminar. |
| `ExecStart` | `/usr/local/lib/zascarr/zascarr-actualizar-entrada` | Acción fija + cerrojo antes de efectos (B2). |
| `ExecStartPost` | **ninguno** | A1. |
| `ExecStopPost` | uno, con `-`, mapeado (A1/B6) | Cierre de último recurso. |
| `Environment` | `ZASCARR_ACTUALIZAR_UNIDAD=1`, `ZASCARR_OPS_DIR=@ZASCARR_DATA_DIR@/ops`, `ZASCARR_OPS4_DIR=@ZASCARR_DATA_DIR@/ops4`, `ZASCARR_OPS_GRUPO=@GRUPO@`, `HOME=@ZASCARR_DATA_DIR@/ops/home`, `DOCKER_CONFIG=/run/zascarr-ops/docker` | B1/B5; sin `EnvironmentFile` que pueda alterar la acción. `GIT_CONFIG_GLOBAL` lo exporta el wrapper solo si el fichero existe (un valor a una ruta ausente puede hacer fallar a Git). |
| `WorkingDirectory` | `@REPO@` | Fijo. |
| `ReadWritePaths` | `@REPO@ @ZASCARR_DATA_DIR@ @BACKUP_DIR@ -/run/zascarr-ops.lock /run/zascarr-ops/docker @ZASCARR_DATA_DIR@/ops/home` | Todo lo que el script escribe de verdad; `-` para el lock (H-7); el instalador sustituye `@BACKUP_DIR@` (nuevo). |
| `ProtectSystem` | `strict` | Se mantiene. |
| `ProtectHome` | `yes` (con B5) | Se mantiene; no se amplía a `/root`. |
| `RuntimeMaxSec` | `infinity` hasta medir en B4; después, un valor holgado medido (nunca 5400 sin evidencia) | H-9/B6. |
| `TimeoutStopSec` | `120` | Dar tiempo a guardar estado antes de SIGKILL. |
| `KillMode`/`SendSIGKILL` | `control-group` / `yes` | No dejar hijos; con estado/fases. |
| `[Install]` | ausente | No se habilita solo. |

El instalador sustituye **todas** las apariciones de `@REPO@`, `@ZASCARR_DATA_DIR@`,
`@BACKUP_DIR@` y `@GRUPO@` y aborta si queda un `@...@` ([instalar_actualizacion_ops4.sh:67-79](../../scripts/instalar_actualizacion_ops4.sh#L67-L79)).
`systemd-analyze verify` sobre la unidad sustituida debe pasar.

#### B3.2 Refresco de auxiliares (hallazgo H-10)

**Decisión de esta spec:** el refresco de OPS1 (`instalar_ops.sh --refrescar`) sale de
`update.sh` bajo la unidad y se ejecuta en una **unidad fija separada** de acción fija:

```ini
# zascarr-refrescar-auxiliares.service (propuesta; no instalar hasta B3)
[Service]
Type=oneshot
User=root
ExecStart=/bin/bash @REPO@/scripts/instalar_ops.sh --refrescar
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
ReadWritePaths=/usr/local/lib/zascarr /etc/systemd/system /etc/tmpfiles.d /run/zascarr-ops
RestrictAddressFamilies=AF_UNIX
# sin [Install]
```

- `update.sh`, cuando corre bajo la unidad (`ZASCARR_ACTUALIZAR_UNIDAD=1`), invoca
  `systemctl start --wait zascarr-refrescar-auxiliares.service` **después** de que la app
  esté sana. Si falla, **no** convierte la actualización en fallida: añade
  `avisos=["refresco_auxiliares_fallido"]` y sigue. La UI (B7) lo muestra con su texto.
- Si el PO prefiere no añadir unidad, la alternativa admitida es **paso manual
  documentado** en el runbook (B8) y `update.sh` **no** intenta refrescar bajo la unidad:
  detecta `ZASCARR_ACTUALIZAR_UNIDAD=1`, salta el paso 9 y anota aviso. Lo que no se admite
  es el estado actual: intentar escribir fuera del sandbox y tratar el fallo como "todo
  bien".
- `probar_restauracion.sh --dump` (post-actualización) sigue siendo aviso blando en el
  flujo manual; bajo la unidad, un fallo añade `avisos=["restauracion_no_verificada"]` y un
  texto en la UI. No se convierte en fallo duro de la actualización, pero tampoco se
  oculta.

#### B3.3 Instalador y tmpfiles

- Instalar `deploy/systemd/zascarr-actualizar.tmpfiles.conf` con, como mínimo:
  `d /run/zascarr-ops 0750 root @GRUPO@ -`, `f /run/zascarr-ops.lock 0600 root root -`,
  `d /run/zascarr-ops/docker 0700 root root -`. Si OPS1 ya define las mismas líneas, son
  idempotentes; OPS4 no puede depender de que OPS1 esté instalado (T-14).
- El instalador crea `ops4/admision.lock` (`0600 root`) y `ops/home` (`0700 root`), y
  ejecuta `systemd-tmpfiles --create` de su fichero.
- Añadir preflight en `update.sh` **antes del backup**: comprobar escritura en `@REPO@`,
  `@BACKUP_DIR@`, `@ZASCARR_DATA_DIR@` y espacio para build/migración (umbral medido en
  B4, provisional 2 GB o 2× el tamaño de la imagen); si falla ⇒ `fallida` con
  `codigo=precondiciones`/`sin_espacio` **sin efectos**.
- Mantener `--dry-run` y la no activación por defecto; `--activar` no instala ni habilita
  la UI.

**CA-B3:**

| CA | Observable |
|---|---|
| CA-B3-01 | `systemd-analyze verify` pasa con la unidad sustituida; no quedan marcadores; no hay `ExecStartPost`; `ReadWritePaths` incluye exactamente las rutas escritas (incluido `-` del lock y `@BACKUP_DIR@`). |
| CA-B3-02 | Host sin OPS1: la unidad arranca con lock/dirs creados por OPS4 (o falla con causa clara antes de `ExecStart`, nunca con error de namespacing). |
| CA-B3-03 | Repo/datos en rutas no estándar: las sustituciones son las reales y el sandbox permite escribir; prueba en VM. |
| CA-B3-04 | Refresco: éxito ⇒ sin aviso; fallo ⇒ `hecha` con `avisos=["refresco_auxiliares_fallido"]` y texto; nunca se pierde el resultado de la actualización. |
| CA-B3-05 | `probar_restauracion` fallido ⇒ aviso en estado/UI, no fallo de actualización. |
| CA-B3-06 | Preflight sin espacio/rutas: `fallida`/`precondiciones` antes de backup; no se consumen más recursos. |
| CA-B3-07 | `update.sh` manual (sin unidad) conserva el refresco actual y no intenta la unidad de refresco. |

---

### B4 — Validación real en host aislado (VM/Pi desechable)

**Prohibido:** usar la Pi de producción, datos reales, `update.sh` falso, el socket de
producción o root del host real. La VM usa overlay desechable, Docker/PostgreSQL
desechables y repositorio de prueba; la única diferencia con producción es el tamaño.

**Matriz obligatoria (cada fila con evidencia firmada por fase: fecha, comando, estado
persistido, HEAD, imagen, BD, salud):**

| Escenario | Resultado esperado |
|---|---|
| Éxito con migración | S instalado, imagen `S`, BD migrada, healthy, estado `hecha`, fases completas. |
| Éxito sin cambios (`S == HEAD0`) | Según decisión del PO (B10); no se declara "hecha" si no se verificó; nunca mezcla. |
| Cerrojo ocupado | `fallida`/`ocupada` sin efectos; sin consumo reusable. |
| Fallo de build | Código avanzado, imagen no; estado `incierta`/`fallida` según fase; no `hecha`. |
| Fallo de migración | BD a medias; estado `incierta`; no hay reintento ni rollback automático; evidencia conservada. |
| Fallo de salud | Servicio no sano; estado `incierta`/`fallida` según fase; texto manual. |
| Corte de energía / reboot | Estado persistido honesto; sin relanzamiento; reconciliación manual cierra. |
| Timeout de unidad | Estado `incierta`; nunca `hecha`; no segundo intento. |
| Parada manual | Estado `incierta`; reconciliación manual. |
| Fichero de estado corrupto/ilegible | Nada se sobrescribe con éxito; UI "no se puede comprobar"; reconciliador exige decisión. |
| Refresco de auxiliares falla | Actualización `hecha` con aviso; texto correcto. |
| `git fetch`/`docker` con `ProtectHome` | Funcionan con B5 o fallan cerrado antes de tocar nada. |
| Host sin OPS1 | Arranca o falla con causa clara; no error de namespacing. |
| Suite en Python 3.11 | Verde (no solo el venv local). |
| Repetición/replay | Rechazado; no se ejecuta dos veces. |

**CA-B4-01:** cada fila tiene evidencia; un NOT RUN no cuenta como PASS. **CA-B4-02:** no
se usó `update.sh` falso en ninguna fila que se declare PASS. **CA-B4-03:** ningún secreto
en logs/estado. **CA-B4-04:** la evidencia va firmada y enlazada desde la PR de
habilitación.

---

### B5 — `ProtectHome` con Docker y Git

- `DOCKER_CONFIG=/run/zascarr-ops/docker` + `d /run/zascarr-ops/docker 0700 root root -`
  (patrón probado de [zascarr-restaurar@.service:11-13](../../deploy/systemd/zascarr-restaurar@.service#L11-L13)).
- `HOME=@ZASCARR_DATA_DIR@/ops/home` (`0700 root`, en `ReadWritePaths`).
- `GIT_CONFIG_GLOBAL` **no** se fija en la unidad: el wrapper de entrada lo exporta a
  `/etc/zascarr/gitconfig` **solo si el fichero existe** (el instalador puede dejarlo con
  `safe.directory`); si no existe, Git usa su comportamiento por defecto sin depender de
  `/root`. Un valor apuntando a una ruta ausente no debe hacer fallar el `fetch`.
- **Política de remoto:** HTTPS para el `origin` autorizado; si el remoto exige
  credenciales de `/root` (SSH, helper, credential store), **falla cerrado antes de tocar
  nada** con `codigo=git_remoto_no_disponible`; no se amplía `ProtectHome`.
- Preflight `git ls-remote` con plazo fijo (30 s) y `docker info` con plazo; errores claros
  y sin secretos.
- Validar `docker compose build/up/run` y `git fetch` **bajo la unidad** (no solo a mano).

**CA-B5:** `git fetch`, `docker info`, `compose build/up/run` y la migración funcionan bajo
la unidad en VM; sin acceso a `/root`; un remoto que lo exija falla cerrado; `docker`
nunca recibe `/var/run/docker.sock` desde la app (la app no lo tiene en ningún caso).

---

### B6 — Plazos por fase, no SIGKILL ciego

- **Medir** en la Pi (o VM representativa) p95 de: backup/dump, build, migración,
  arranque/health, refresco. Con esos datos, fijar `RuntimeMaxSec` (holgado, p99×2 o
  `infinity`) y, si se pone, mapear timeout a `incierta`/`sin_noticias` (nunca `hecha`).
- Fases con `actualizado_epoch` por fase y umbrales de B1.6; la UI dice "sin noticias" y
  **no** ofrece reintento.
- `trap` en `update.sh` para `TERM`/`INT`: intentar escribir `incierta`/`senal` antes de
  salir (best-effort; SIGKILL no se atrapa, lo cubre el finalizador). El `trap` no debe
  convertir un fallo de escritura en éxito.
- `KillMode=control-group` y `TimeoutStopSec=120`; no se mata una migración a los 90 min
  por un número no medido (H-9).
- **CA-B6:** timeout simulado durante migración ⇒ `incierta`, no `hecha`; no hay segundo
  intento; evidencia conservada; los umbrales de fase se respetan.

---

### B7 — UI de último intento

**Servicio:** `leer_ultimo_intento` (B1.6) leído en `web/estado.py` con
`asyncio.to_thread`, en un bloque nuevo de la plantilla, **solo si
`ops4_actualizacion_habilitada` es verdadero**. Con la bandera apagada no se pinta nada
nuevo (A no añade UI).

**Contrato de la vista (cerrado, sin cadenas libres):**

| Condición leída | Texto (llano, es) | Notas |
|---|---|---|
| sin fichero | "Todavía no hay ninguna actualización desde la interfaz." | Al habilitar. |
| activo fresco | "Actualización en marcha desde el <fecha>: <fase llana>." | Sin botón de reintento. |
| activo viejo (`sin_noticias`) | "No hay noticias de la última actualización desde el <fecha>. No vuelvas a intentarlo: revisa el estado del sistema antes de actuar." | Es `incierta`, no `hecha`. |
| `hecha` | "Última actualización terminada el <fecha>: de <head0:7> a <sha_actual:7>." | Solo si los SHA existen; si no, sin "de X a Y". |
| `hecha` + aviso refresco | El anterior + "No se pudo refrescar el auxiliar de copias; vuelve a ejecutar el instalador." | `avisos`. |
| `hecha` + aviso restauración | El anterior + "La comprobación de restauración posterior no pasó; revisa el estado." | `avisos`. |
| `fallida` | "La última actualización no llegó a ejecutarse: <causa llana>. No se cambió nada." | Solo si `head0` sigue siendo HEAD; si no, se usa `incierta`. |
| `incierta` | "No se puede confirmar qué quedó instalado. No vuelvas a intentarlo: revisa el estado del host antes de actuar." | Nunca invita a reintentar. |
| legado | "Hay un intento anterior del que no se guardó el detalle." | Sin fases. |
| fichero ilegible | "No se puede comprobar el estado de la última actualización." | La página sigue. |

- **Sin JavaScript nuevo, sin SPA, sin `hx-confirm`**: render en servidor, misma página.
- **Accesibilidad y diseño:** `ui.aviso` del sistema de diseño
  ([sistema-de-diseno-zascarr.md](sistema-de-diseno-zascarr.md)); texto ≥ 14 px; sin
  depender solo del color; `aria-live` no es necesario (no se actualiza en vivo); sin
  botón principal nuevo.
- **Privacidad:** no se pinta `id`, ni rutas, ni salida de comandos, ni rutas de backup, ni
  secretos. Solo fechas, fase llana, SHA cortos y avisos cerrados.
- **Rendimiento:** una lectura de fichero pequeño por visita a `/estado`; si falla, no
  bloquea la página; sin consultas a BD ni red.
- La página de resultado del POST (ya dentro de `base.html`) se conserva y, si el estado
  es `incierta`, muestra el texto de "no reintentar" (ya existe) además del bloque.

**CA-B7:** tabla de estados→texto probada con ficheros reales; bandera apagada ⇒ no
aparece bloque; fichero ausente/corrupto ⇒ texto de no disponible y página sana; sin
secretos; sin JS; el POST de un estado `incierta` no invita a reintentar; prueba de que no
se muestra `id` ni rutas.

---

### B8 — Activación y runbook

- **Orden exacto:** (1) grupo del servicio resuelto desde `PGID` (CE-3-R); (2) clave
  `actualizar.key` `0440 root:<grupo>`; (3) `instalar_actualizacion_ops4.sh --yes` (sin
  `--activar`) + tmpfiles + dirs + `admision.lock`; (4) verificar cerrojo y rutas; (5)
  `--activar` con **confirmación explícita e inequívoca** (arma ejecución root real, **no
  persistente**, sin rollback automático) o la decisión explícita de persistencia (hoy no,
  CE-1/CE-2); (6) comprobar socket `LISTEN` y grupo; (7) encender
  `OPS4_ACTUALIZACION_HABILITADA` en el `.env` (root 600) y reiniciar la app; (8)
  comprobaciones: 404 con bandera falsa, formulario con bandera verdadera, 503 con socket
  caído, repetición, cerrojo ocupado, clave ilegible.
- **Nunca** en la misma operación que la fusión; nunca en la Pi sin ventana autorizada.
- Documentar qué pasa tras reiniciar el host (socket no persistente si `--activar` solo
  hace `start`): decidir y escribir si la habilitación exige `enable` explícito con
  confirmación; hoy no se hace.
- **CA-B8:** ensayo en VM: orden, confirmaciones, verificaciones y mensajes exactos;
  ninguna operación `enable`/`enable --now` en el instalador; la bandera sigue apagada
  hasta el paso 7 y solo con autorización.

---

### B9 — Ciclo de vida de la clave y del registro durable

- Rotación/revocación de `actualizar.key` (`0440 root:<grupo>`, sin seguir enlaces) y
  paridad `0400/0440`; documento y procedimiento.
- Retención/cuota de `ops4/consumidos` (marcas de un solo uso): retención ≥ TTL máximo del
  testigo (300 s) con enorme margen (p. ej. 90 días o 1000 marcas); límite de entradas y
  comportamiento con registro lleno (`no_disponible`, sin ejecutar).
- Decisión expresa sobre la **clave montada en el contenedor con la función habilitada**:
  separar claves o endurecer el socket; el ADR 0026 acepta el riesgo residual **solo
  mientras la función está apagada**, así que habilitar exige actualizar el ADR (B10).
- **CA-B9:** pruebas de rotación, clave ausente/ilegible, registro lleno y paridad de
  modos; revisión SecOps; ADR actualizado.

---

### B10 — Cierre documental y de comportamiento

- **Decisión del PO sobre `S == HEAD0`:** recomendación de esta spec: informar "Ya está
  actualizado" y **no** reconstruir ni migrar, moviendo el `fetch` antes del backup (o
  detectando el no-op antes de tocar nada) y validándolo en B4 (T-15). Si el PO prefiere
  conservar el comportamiento manual (reconstruye y migra), el estado y la UI deben
  decirlo ("ya estabas en la última versión; se ha verificado y recreado el servicio") y
  probarse. No se puede dejar la contradicción actual sin decidir.
- Actualizar recuentos, contratos v4, runbook, límites de la VM y de la Pi; ADR 0026 con
  (a) estado durable en fichero del host, (b) reconciliación y no reintento, (c) riesgo
  residual de la clave **en estado habilitado**, (d) refresco en unidad separada si se
  adopta.
- Suite en Python 3.11; smoke en Pi **autorizado por separado**; nunca a partir de este
  documento.
- **CA-B10:** documentación sin contradicciones; `S == HEAD0` decidido y probado; suite
  3.11; smoke con evidencia; ADR al día.

---

## 5. Casos de error (contrato cerrado)

### 5.1 Reglas generales

- **Fallo cerrado:** estado ilegible, cerrojo dudoso, `fsync` incierto, `start` ambiguo,
  clave ausente, host no disponible ⇒ no se inicia o se marca `incierta`; **nunca** se
  inventa un éxito.
- **Sin datos libres:** ni rutas, ni salida de comandos, ni testigo, ni contraseña, ni
  firmas, ni ramas/URLs, ni nombres de contenedores, ni datos del coleccionista, ni en el
  estado, ni en logs, ni en la UI.
- **Sin reintento automático ni rollback automático.** Un fallo posterior al inicio es
  incierto; la reparación es manual y revisada.
- **Mensajes para el coleccionista:** causa y acción en llano; nada de "exit code 1".

### 5.2 Códigos de estado (`codigo`, cerrados)

`ok`, `ya_actualizado`, `ocupada`, `admision_ocupada`, `autorizacion_repetida`,
`inicio_fallido`, `arranque_ambiguo`, `consumo_no_confirmado`, `precondiciones`,
`sin_espacio`, `credenciales`, `copia_fallida`, `copia_no_verificada`, `avance_fallido`,
`build_fallido`, `migracion_fallida`, `arranque_fallido`, `salud_fallida`,
`refresco_fallido`, `restauracion_no_verificada`, `timeout`, `senal`, `parada_manual`,
`estado_ilegible`, `estado_ajeno`, `git_remoto_no_disponible`, `docker_no_disponible`,
`origen_invalido`, `sha_incoherente`, `evidencia_insuficiente`, `reconciliada`,
`estado_degradado`, `consumo_registro_no_disponible`.

### 5.3 Respuesta del auxiliar (protocolo v4, sin cambios)

Códigos existentes y significado: `aceptada`, `esquema_invalido`, `firma_invalida`,
`caducada`, `autorizacion_invalida`, `repetida`, `operacion_en_curso`, `no_disponible`.
**No se añaden códigos nuevos en B** (decisión 4 de §0). La app traduce y, cuando
corresponde, lee el estado para dar contexto:

| Situación | Respuesta host | Resultado app | Texto/acción |
|---|---|---|---|
| Bandera falsa | (no se envía) | 404 | no hay formulario |
| Clave ausente/ilegible | `no_disponible` | `NO_DISPONIBLE` | "El servicio de actualización no está disponible." |
| Firma/caducidad | `firma_invalida`/`caducada` | `RECHAZADA` | "La solicitud fue rechazada…" |
| Cerrojo ocupado (P4) | `operacion_en_curso` | `OCUPADA` | "Hay otra operación en marcha; espera a que termine." |
| Carrera P4→P9 | `operacion_en_curso` | `OCUPADA` | ídem; sin reintento automático |
| Reconciliación pendiente | `no_disponible` | `NO_DISPONIBLE` + estado `incierta` | "No se pudo iniciar: hay un intento anterior sin cerrar. No vuelvas a intentarlo: revisa el estado del host." |
| Inicio ambiguo | `no_disponible` | `INCIERTA` (transporte) + estado `incierta` | "No se pudo confirmar el resultado. No vuelvas a intentarlo…" |
| Replay | `repetida` | `RECHAZADA` | "La solicitud ya se usó." |

`INCIERTA` **nunca** se presenta como éxito ni invita a reintentar (la app ya lo cumple
hoy). El botón de reintento no existe.

En los casos de reconciliación pendiente y arranque ambiguo, la app lee
`leer_ultimo_intento` **aunque la respuesta no traiga `id`** (el transporte puede no
correlacionar) y añade el contexto del estado a la página de resultado; no depende solo de
`estado_file` + `id` como hoy ([web/actualizacion.py:103-110](../../src/zascarr/web/actualizacion.py#L103-L110)).

### 5.4 Casos que la implementación debe probar explícitamente

| Caso | Detección | Resultado |
|---|---|---|
| Estado corrupto/duplicado/grande/tipo raro | lector estricto | `incierta`; no se pisa |
| Esquema desconocido | lector | `incierta`; no se interpreta |
| Reloj invertido/salto | escritores/lector | no se escribe; `incierta` |
| Disco lleno/`fsync` fallido | escritor | incierto; no se declara durable |
| `rename` fallido | escritor | incierto; no se declara durable |
| Estado sustituido por symlink/FIFO/directorio | lector | `incierta`; no se bloquea |
| Pérdida de respuesta tras `start` | transporte | `INCIERTA`; sin reintento |
| `systemctl start` falla | auxiliar | `fallida`/`inicio_fallido`; sin unidad |
| Unidad no puede tomar cerrojo | entrada | 75 antes de efectos; `fallida`/`ocupada` |
| Fallo de build/migración/health/timeout/señal | finalizador/fases | `incierta` o `fallida` honesto; nunca `hecha` |
| Refresco/restauración posterior falla | avisos | `hecha` + aviso; no se oculta |
| Clave con modo/dueño incorrectos | lector host | rechazo; `no_disponible` |
| Registro de consumo lleno | auxiliar | `no_disponible`; no ejecuta |
| Repetición de `id` | consumo/estado | `repetida` |

---

## 6. Tests obligatorios

### 6.1 Reglas

- Un caso **NOT RUN** se declara NOT RUN; nunca PASS. Un PASS de un SHA anterior no vale
  para el SHA que se fusiona/habilita.
- CI con dobles: **no** arranca unidades, Docker, systemd, PostgreSQL de producción, ni
  usa root/red externa. La validación con host real es B4, con evidencia firmada.
- Python 3.11 (imagen de producción) además del venv local.
- Sin dependencias nuevas para probar (CLAUDE.md §8). `FakeSession`/dobles cuando aplique;
  procesos/sockets reales solo en tmp y sin privilegios.
- Cada regresión de una carrera o de una mentira de estado lleva test nombrado por el
  mecanismo (p. ej. `test_auxiliar_no_pisa_terminal_tras_start`).

### 6.2 Tests de A (obligatorios en la PR apagada)

| ID | Fichero | Qué debe probar |
|---|---|---|
| TA-01 | `tests/test_ops4_unidades.py` | Unidad sin `ExecStartPost`; `ExecStopPost` único con `-` y variables; sin `[Install]`; `ReadWritePaths` coherente (A). |
| TA-02 | `tests/test_ops4_estado_final_unidad.py` | Tabla completa de `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS`; ejecución de la cadena real; sin estado; terminal; reloj invertido; `id`/`inicio` conservados; fallo de escritura. |
| TA-03 | `tests/test_ops4_auxiliar.py` | No hay escritura post-`start`; terminal no se pisa (T-17); start fallido ⇒ `fallida`; escritura de reserva fallida ⇒ no arranca. |
| TA-04 | `tests/test_ops4_escritor_estado.py` | Guarda de monotonía; transiciones terminales; fallos de `fsync`/`rename`; no publica inválidos. |
| TA-05 | `tests/test_instalar_ops4.py` | Copia exactamente los módulos importados; no `enable`; `--activar` solo `systemctl start`; tmpfiles/unidades. |
| TA-06 | `tests/test_ops4_aislamiento.py` | La app no importa `deploy/ops`; módulos retirados no vuelven; auxiliar sin imports de app. |
| TA-07 | `tests/test_ops4_ui_deshabilitada.py` + `test_ops4_ui_actualizacion.py` | 404 sin leer clave/servicio; sin estado leído con bandera falsa; sin secretos; `INCIERTA` sin invitación a reintentar. (Debe seguir verde.) |
| TA-08 | `tests/test_ops4_estado_actualizacion.py` | Contrato del lector actual (esquema 1) sigue intacto; T-07/T-08. |
| TA-09 | `tests/test_ops4_alcance_apagado.py` (nuevo) | Bandera `false` en config y Compose; sin `[Install]`; instalador sin `enable`; sin `ExecStartPost`; sin migración Alembic nueva; sin `.env` de producción. |
| TA-10 | `tests/test_instalar_ops4.py` | `--quitar` limpia; `--dry-run` no escribe; sin activación por defecto (T-19 parcial). |

### 6.3 Tests de B (obligatorios antes de habilitar)

| ID | Fichero/entorno | Qué debe probar |
|---|---|---|
| TB-01 | `tests/test_ops4_estado_actualizacion.py` (v2) | Esquema 2 completo, invariantes, tipos, límites, legado, esquema desconocido, permisos, `sin_noticias` por fase. |
| TB-02 | `tests/test_ops4_escritor_estado.py` (v2) | Transiciones, modo `0640`, dueño/grupo, monotonía, `fsync`/rename/reloj, fichero ajeno. |
| TB-03 | `tests/test_ops4_reconciliacion.py` (nuevo) | Evidencia solo lectura; clasificación; no escribe con unidad activa/cerrojo; marca de consumo; no toca código/BD; `--si`. |
| TB-04 | `tests/test_ops4_auxiliar.py` (B2) | Procesos reales: concurrencia, orden P3–P12, ocupado sin consumo, carrera, replay, ventanas de caída. |
| TB-05 | `tests/test_ops4_entrada_unidad.py` (nuevo) | fd 9 heredado, `exec` conserva el descriptor, reserva caducada/ajena ⇒ sin efectos, `systemctl` no invocado. |
| TB-06 | `tests/test_ops4_unidades.py` (B3) | Contrato de B3.1/B3.2/B3.3: directivas, `ReadWritePaths`, `RuntimeMaxSec`, refresco, tmpfiles; `systemd-analyze verify` si está. |
| TB-07 | `tests/test_ops4_ui_ultimo_intento.py` (nuevo) | Tabla de textos, bandera apagada, fichero ausente/corrupto/legado, sin secretos, página sana; POST con `incierta` no invita a reintentar. |
| TB-08 | `tests/test_ops4_pi_optin.py`/B4 | Host real desechable: matriz de B4, evidencia por fase. |
| TB-09 | `tests/test_ops4_fases_actualizacion.py` | Modelo de fases reincorporado: transiciones, terminales, no reintento. |
| TB-10 | Suite en Python 3.11 | Verde en la versión de producción. |

### 6.4 Trazabilidad con el benchmark (T-01…T-20)

| T | Caso | Fase | Test |
|---|---|---|---|
| T-01 | Dos peticiones simultáneas | B2 | TB-04 |
| T-02 | Petición con copia/restauración en curso | B2 | TB-04 |
| T-03 | Unidad no puede tomar el cerrojo | B2 | TB-04/TB-05 |
| T-04 | Carrera tanteo→start | B2 | TB-04 |
| T-05 | Cortes en cada fase | B1/B2/B4 | TB-01/TB-04/TB-08 |
| T-06 | Reinicio tras actualización | B1/B7 | TB-01/TB-07/TB-08 |
| T-07 | Estado ajeno/corrupto/extra/grande | B1 | TB-01 |
| T-08 | Symlink/FIFO/directorio | B1 | TB-01 |
| T-09 | `fsync`/rename fallidos | B1 | TB-02 |
| T-10 | `ExecStopPost` falla tras éxito | A/B1 | TA-02 |
| T-11 | Timeout durante migración | B6/B4 | TB-08 |
| T-12 | `update.sh` real bajo unidad (Docker/Postgres) | B4 | TB-08 |
| T-13 | `git`/`docker` con `ProtectHome` | B5 | TB-08 |
| T-14 | Host sin OPS1 (falta lock) | B3 | TB-06/TB-08 |
| T-15 | `S == HEAD0` | B10 | TB-08 |
| T-16 | Respuesta perdida tras start | B2 | TB-04 |
| T-17 | Terminal pisado por `en_curso` | A | TA-03 |
| T-18 | Bandera falsa/clave ausente/socket caído | A | TA-07 |
| T-19 | Instalador sin/con `--activar` | A | TA-05/TA-10 |
| T-20 | Suite en Python 3.11 | B10 | TB-10 |

### 6.5 Comandos de referencia

```bash
# En el árbol rebasado, con el venv del proyecto
pytest -q -rs
pytest -q -rs tests/test_ops4_unidades.py tests/test_ops4_estado_final_unidad.py \
  tests/test_ops4_auxiliar.py tests/test_ops4_escritor_estado.py \
  tests/test_instalar_ops4.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_ui_deshabilitada.py tests/test_ops4_ui_actualizacion.py
ruff check src/
ruff check --select S src/
# Host aislado (B4; nunca la Pi ni producción)
# ver ops4-diseno-ejecutor-vm.md y ops4-plan-validacion-aislada.md
```

---

## 7. NO-GO y puertas

### 7.1 Prohibiciones absolutas después de fusionar A

- **NO** poner `OPS4_ACTUALIZACION_HABILITADA=true` en `.env`/Compose.
- **NO** ejecutar `instalar_actualizacion_ops4.sh --activar` ni `systemctl start/enable`
  del socket o de la unidad en producción.
- **NO** instalar, habilitar, provisionar clave ni desplegar en la Pi.
- **NO** conectar `update.sh` a la UI, ni ejecutarlo desde la app, ni darle a la app root,
  Docker socket o escritura del repo.
- **NO** presentar la fusión como "actualización disponible para el usuario", ni A como
  "estado durable resuelto".
- **NO** usar la Pi ni datos reales para probar; **NO** un `update.sh` falso como evidencia
  del actualizador real.

### 7.2 Qué sigue siendo NO-GO (resumen por contrato)

| Contrato | Estado a la fusión A | ¿Bloquea habilitar? |
|---|---|---|
| Estado durable completo, `head0`/`S`, fases, monotonía | Especificado en B1, **no implementado** | **Sí (P0)** |
| Reconciliación verificable | Especificada en B1.5, **no implementada** | **Sí (P0)** |
| Reserva/cerrojo atómico | Especificado en B2, **no implementado** | **Sí (P0)** |
| Sandbox/refresco y rutas reales | Especificado en B3, **no implementado** | **Sí (P0)** |
| UI de último intento | Especificada en B7, **no implementada** | **Sí (P1)** |
| Migración de estado 1→2 y skew app/host | Especificada en B1.7, **no implementada** | **Sí (P1)** |
| Validación con `update.sh` real, Docker/PostgreSQL/systemd | **NOT RUN** | **Sí (P0, B4)** |
| `ProtectHome`/Git/Docker | **NOT RUN** | Sí (P1, B5) |
| Plazos medidos/fases | **NOT RUN** | Sí (P1, B6) |
| Activación/runbook | **NO** | Sí (P2, B8) |
| Clave/registro durable/ADR | **NO** | Sí (P2, B9) |
| `S == HEAD0`, Python 3.11, smoke en Pi | **NO / NOT RUN** | Sí (B10) |

### 7.3 Puerta de habilitación (no la concede este documento)

Con **B1–B4 verdes** (P0), **B5–B10 cerrados o deuda aceptada por el PO**, **CE-1…CE-12**
y **I-1…I-9** resueltas o declaradas, revisión SecOps del SHA final, runbook B8 y
**autorización expresa separada del PO**, se podrá proponer la habilitación. Esta spec no
la concede, no la fecha y no autoriza ningún despliegue. Hasta entonces, la función sigue
apagada, sin clave de producción, sin socket activo y sin acción visible en la UI.

---

## 8. Decisiones abiertas del PO (bloquean B, no A)

| # | Decisión | Recomendación de esta spec | Bloquea |
|---|---|---|---|
| D-1 | `S == HEAD0`: ¿no-op informativo o reconstruir/migrar como hoy? | No-op informativo con `fetch` antes del backup, probado en B4; el manual actual se documenta como comportamiento distinto. | B10 |
| D-2 | Refresco de auxiliares: unidad fija separada o paso manual documentado | Unidad fija separada (B3.2); el fallo es aviso de estado, no éxito completo. | B3 |
| D-3 | Persistencia de la activación (`--activar` no persistente) | Mantener no persistente por defecto; decidir `enable` explícito solo con B8/B9 y confirmación. | B8 |
| D-4 | Visibilidad de la UI de último intento con la bandera apagada | No pintar nada nuevo hasta habilitar (A no añade UI). | B7 |
| D-5 | Historial de intentos anteriores | Fuera de B1; P2, no bloquea la habilitación. | B10 |
| D-6 | Tope global de tiempo | Medir en B4; `infinity` hasta entonces; nunca 5400 a ciegas. | B6 |

---

## 9. Trazabilidad, caducidad y mantenimiento

- **Trazabilidad:** cada afirmación de código lleva ruta y línea; cada referencia externa
  lleva commit (Sonarr `51a2412a…`, Radarr `25a2124d…`) o documento. Las citas de
  `systemd.service(5)` son de la página actual del host (2026-11-21).
- **Caducidad:** ~60 días desde 2026-11-21, o antes si cambia la historia, `update.sh`,
  `instalar_ops.sh`, las unidades, el auxiliar, el lector/escritor de estado o el SHA que
  se fusiona. Si cambia el SHA, la revisión SecOps se repite (A6).
- **Mantenimiento:** al cerrar cada punto A/B se actualiza este documento con la evidencia
  (SHA, commands, recuentos, NOT RUN) sin reescribir la historia. El documento vivo de la
  decisión sigue siendo el ADR 0026; esta spec es el contrato de implementación del cierre.
- **Relación con otros documentos:** no sustituye a
  [ops4-especificacion-main.md](ops4-especificacion-main.md) (política y AC históricos), a
  [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) (FR/AC históricos) ni a los
  dictámenes SecOps; los complementa para el cierre concreto sobre `07161e2a` y la
  habilitación pendiente.
