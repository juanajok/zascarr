# SecOps — Dictamen final del SHA `3aa4ec16` (OPS4/#443, rama limpia desde main)

**Rol:** SecOps · **Fase:** dictamen final de solo lectura del SHA que se fusiona (CLAUDE.md §5.8).
**Fecha:** 2026-11-22 (Europe/Madrid).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-b-limpia`; rama `feat/ops4-b-limpia-443`.
**SHA dictaminado:** `3aa4ec1646ffb97c310e16c1a4dded8ab6318c74` — PR #1233, «feat(ops): actualización manual desde UI OPS4 apagada (#443)».
**Base:** merge-base con `origin/main` local = `2c773e53c235812adabc76e76cd3b111d04d4026`; `origin/main` local = `9fe0be06` (el SHA está **1 commit delante / 12 detrás**; ningún fichero del PR se solapa con lo que cambió main desde la base — verificado con `comm`). Por tanto no hay conflicto de contenido, pero el árbol de un eventual merge no es idéntico al SHA: si la fusión produce un commit de merge o un rebase, aplica la regla del dictamen del SHA que se fusione.
**Entorno:** venv de pruebas del repo (Python 3.14.4, pytest 9.2.0, ruff 0.17.4); la imagen de producción es `python:3.11-slim` y `pyproject.toml` exige `>=3.11`. Sin `TEST_DATABASE_URL`, sin Docker, sin systemd instalado, sin Pi.
**Restricciones respetadas:** no se editó código, plantillas, unidades, instalador, Compose, `update.sh` ni `bootstrap.sh`; no se hizo commit ni push; no se ejecutó la Pi, Docker real, PostgreSQL real, systemd del host, el instalador con `--activar` ni `update.sh`. **El único fichero escrito es este informe.** El árbol rastreado estaba limpio al empezar; durante la sesión apareció un informe de QA no rastreado del mismo trabajo, ajeno a este dictamen.
**La actualización sigue DESHABILITADA por defecto.** Este dictamen **no autoriza habilitar, armar el socket, instalar en la Pi ni desplegar**, y **no sustituye** la revisión de habilitación.

---

## 0. Veredicto

1. **P0 de seguridad: ninguno.** Con la configuración por defecto (`OPS4_ACTUALIZACION_HABILITADA=false`, sin clave ni socket provisionados, unidades sin `[Install]`, instalador sin activación) no hay ruta que ejecute `update.sh`, ni bypass de la puerta de UI, ni fuga de clave/contraseña/testigo, ni confusión de clave/socket que ejecute algo.
2. **P1 nuevos de ejecución: ninguno.** El código de ejecución de OPS4 de este árbol es **byte a byte idéntico** al del HEAD de la rama antigua ya revisada (`9207d17a`); respecto del último dictamen (`48526e03`) el único delta de código es el de OCUPADA (5 líneas), que he verificado, y el resto del diff limpio es retirada de protocolo v3/experimentos, documentación y rebase sobre `main`. No hay regresión de comportamiento con la función apagada.
3. **P1 nuevo de verificación (P1-V): hay uno, y bloquea cerrar la Parte A.** La limpieza retiró ~640 pruebas de la selección OPS4/paridad (de las 1005 que declaraba la documentación de la rama antigua a las 364 de este árbol, 374 con paridad), y con ellas la suite dedicada del **registro de consumo durable** (27 funciones) y 19 de las 24 barreras de aislamiento (entre ellas las que exige la propia spec de cierre, CA-A-06/CA-A-08/TA-06). No es un defecto explotable con la bandera apagada ni un cambio de código, pero incumple los criterios de fusión A de la [especificación de cierre](especificacion-ops4-cierre.md) (su tabla marca «Bloquea fusión: Sí») y borra la red de regresión de un control de seguridad (consumo de un solo uso).
4. **Fusionar apagado: GO CON CONDICIONES, no incondicional.** No hay ninguna razón de seguridad de ejecución para no fusionar la función apagada, y la limpieza reduce superficie. Pero las condiciones **CF-1 (reponer/portar la cobertura perdida o aceptarla por escrito)**, **CF-2 (verdad documental A4/A5/A10)** y **CF-3 (SHA/merge)** no están cerradas en este árbol; mientras no lo estén, el árbol **no debe fusionarse tal cual** (CF-4/CF-5 son compromisos del acto de fusión). Todas las condiciones son de tests y documentación: no tocan código de ejecución.
5. **Habilitar (sacar la ruta del 404 con clave/socket provisionados, arrancar el socket, ejecutar el `update.sh` real) o desplegar: NO-GO.** Siguen abiertos P1-1-R, P1-6-R, P1-7-R (parcial), P1-8-R (parcial: el riesgo ya está en ADR 0026), P1-9-R (parcial: solo A1), B1–B10 e I-1…I-9, además de las condiciones CE que enumera §5.2. **No se autoriza ningún despliegue.**
6. **Caducidad:** vale **solo** para el árbol de `3aa4ec16` con la función deshabilitada y los valores por defecto. Caduca con cualquier commit, rebase o merge que cambie el SHA y con cualquier cambio de los ficheros de §8 o de los documentos de contrato que fijan el estado.

---

## 1. Alcance: qué es este SHA y qué se ha retirado

Un único commit, **58 ficheros** frente a `origin/main`:

| Grupo | Ficheros | Comentario |
|---|---|---|
| App (`src/zascarr`) | 13 | ruta, servicio v4, autorización, clave, transporte, estado, config, `main.py`, `estado.py`/plantillas |
| Host (`deploy/ops`, `deploy/systemd`) | 7 + 3 | auxiliar, protocolo v4, verificador, registro durable, admisión v4, escritor, finalizador; tres unidades |
| Instalador | 1 | `scripts/instalar_actualizacion_ops4.sh` |
| Tests | 16 + 2 | 15 de OPS4 + instalador; **2 ajenos** (estabilización de RAR y del arnés F1bis) |
| Documentación | 14 | ADR 0026, spec de cierre, benchmark y 11 documentos `ops4-*` |
| Wiring/documentación de proyecto | 2 | `CLAUDE.md` §3.2 y `docker-compose.yml` |

**Historia B limpia, sin protocolo v3 ni experimentos (verificado):** no quedan en el árbol `experimento_*_ops4.py`, `protocolo_actualizar_ops4.py` (v3), `admision_actualizar_ops4.py`, `admision_host_actualizar_ops4.py`, `ejecutor_actualizar_ops4.py`, `lector_credenciales_ops4.py`, `limite_intentos_actualizar_ops4.py`, `modelo_aprobacion_ops4.py`, `modelo_fases_actualizacion_ops4.py`, `prueba_viva_ops4.py`, `validar_inventario_ops4.py`, ni en la app `actualizacion_transporte.py`, `solicitud_actualizacion.py` u `ops_actualizacion_protocolo.py`. `grep` sobre `src/`, `deploy/` y `scripts/` no encuentra referencias a esos módulos retirados; [test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py) lo comprueba desde el árbol. La única superficie v3 que queda es documental (R5) y un ayudante muerto en el registro durable (R7), ambos en §3.2.

**No hay regresión de ejecución:** comparé SHA-256 de los 24 ficheros de ejecución/wiring de OPS4 del árbol con el HEAD de la rama antigua (`feat/ops4-seguridad-443`, `9207d17a`). **20 son idénticos**, incluidos auxiliar, protocolo, verificador, registro, escritor, finalizador, unidades, instalador, ruta web, transporte y servicio v4. Los 4 distintos son artefactos de la base nueva de `main`, no de OPS4: `estado.html` (una clase CSS de main), `config.py` (NAV_MOVIL_VARIANTE de main), `main.py` (routers de main; la inclusión de `actualizacion_ui_router` es idéntica) y `docker-compose.yml` (NAV_MOVIL_VARIANTE de main; las cuatro `OPS4_*` son idénticas). El único delta posterior al último dictamen es el de OCUPADA (§3.3), que no abre ninguna ruta.

**Alcance no del todo limpio (P2):** el diff incluye dos ficheros de tests ajenos a #443 (`tests/test_lector_rar.py` y `tests/test_ensayo_f1bis_arnes.py`, estabilizaciones de temporización) que la propia spec A2/CA-A-07 pedía no mezclar. No son de seguridad, pero impiden decir que el diff es «solo OPS4».

---

## 2. Controles de seguridad verificados (con la función apagada)

| # | Control | Evidencia en `3aa4ec16` | Resultado |
|---|---|---|---|
| 1 | **Bandera `false` por defecto** | `ops4_actualizacion_habilitada: bool = Field(default=False)` ([config.py:284-289](../../src/zascarr/config.py#L284-L289)); Compose inyecta `${OPS4_ACTUALIZACION_HABILITADA:-false}` y rutas dedicadas ([docker-compose.yml:163-167](../../docker-compose.yml#L163-L167)); sonda con `Settings(_env_file=None)` → `False` y las tres rutas esperadas | **PASA** |
| 2 | **La UI/BD no puede encenderla** | `RuntimeSettingsService` no tiene ningún campo `ops4_*` (`grep` vacío en `services/runtime_settings.py`, `web/ajustes.py`); `bootstrap.sh` y `scripts/update.sh` no mencionan OPS4; `scripts/instalar_ops.sh` no lo instala ([test_ops4_unidades.py:94-100](../../tests/test_ops4_unidades.py#L94-L100), [test_ops4_aislamiento.py:60-63](../../tests/test_ops4_aislamiento.py#L60-L63)) | **PASA** |
| 3 | **`POST /ui/actualizar` → 404 antes de leer clave/reautenticar** | Gate en [web/actualizacion.py:78-81](../../src/zascarr/web/actualizacion.py#L78-L81) antes de la lectura de clave (líneas 84-90); `/estado` sin `form` y botón `disabled` con la bandera falsa ([estado.html:13-30](../../src/zascarr/web/templates/estado.html#L13-L30), [test_ops4_ui_deshabilitada.py](../../tests/test_ops4_ui_deshabilitada.py)); ruta real 404 con `TestClient` ([test_ops4_ui_gate.py:88-93](../../tests/test_ops4_ui_gate.py#L88-L93)) y 404 sin efecto lateral ([test_ops4_ui_actualizacion.py:27-40](../../tests/test_ops4_ui_actualizacion.py#L27-L40)) | **PASA** |
| 4 | **Sesión y origen/CSRF cubiertos** | `AuthMiddleware` protege `/ui/*` (solo `/login`, `/api/health`, `/legal`, `/favicon.ico` y `/static/` son exentos); `_peticion_cross_site` corre antes de cualquier short-circuit y bloquea POST sin `Origin`/`Referer` en `/ui/` ([services/auth.py:234-263](../../src/zascarr/services/auth.py#L234-L263); el orden del middleware, en `:660-700`) | **PASA** |
| 5 | **Auxiliar y unidad de acción fija** | `UNIDAD = "zascarr-actualizar.service"` ([aux:63](../../deploy/ops/zascarr_actualizar_aux.py#L63)); `procesar` solo llama a `iniciar(UNIDAD)` y `_iniciar` ejecuta `["systemctl","start","--no-block",unidad]` con `PATH` fijo, `close_fds`, `stdin=DEVNULL` y timeout ([aux:199-209](../../deploy/ops/zascarr_actualizar_aux.py#L199-L209)); `ExecStart` fijo `/bin/bash @REPO@/scripts/update.sh --rama main`, sin rama/ruta/entorno del cliente; el auxiliar solo acepta el esquema v4 cerrado (`v,id,accion,creada,autorizacion,firma`) | **PASA** |
| 6 | **Clave dedicada y lectura estricta** | App y host leen una clave dedicada de 32 bytes (no `ops.key`), fichero regular, `O_NOFOLLOW|O_NONBLOCK`, uid 0 y modo exacto (`0440` host; `0440` desde app), 64 hex o 64+LF ([clave_autorizacion.py:14-61](../../src/zascarr/services/clave_autorizacion.py#L14-L61), [aux:151-178](../../deploy/ops/zascarr_actualizar_aux.py#L151-L178)); el instalador la crea `0440 root:<grupo>` con el grupo resuelto del `PGID` del `.env` y aborto si no existe ([instalar:20-29](../../scripts/instalar_actualizacion_ops4.sh#L20-L29); la clave, en `:102-113`) | **PASA** |
| 7 | **Consumo durable y ligadura por ID** | Testigo HMAC de 60 s ligado a `id` de la petición y a `accion=actualizar`; el host exige `id_esperado` obligatorio, ventana ≤300 s, tolerancia 120 s y consumo único con `autorizacion-<id>` en directorio dedicado root `0700` (separado de `solicitud-<id>` de v3), `O_EXCL` + `fsync` de fichero y directorio, sin borrar la marca si falla la sincronización ([verificador:50-121](../../deploy/ops/verificador_autorizacion_ops4.py#L50-L121), [registro:48-133](../../deploy/ops/registro_repeticiones_ops4.py#L48-L133); directorio y callback, en `:136-191`); el auxiliar consume antes de escribir estado y de arrancar; replay cubierto en [test_ops4_protocolo_v4.py](../../tests/test_ops4_protocolo_v4.py), [test_ops4_transporte_v4.py](../../tests/test_ops4_transporte_v4.py) y [test_ops4_autorizacion_compuesta.py](../../tests/test_ops4_autorizacion_compuesta.py) | **PASA en ejecución; con deuda de cobertura (P1-V)** |
| 8 | **Estado durable A1 (aceptada → terminal)** | El auxiliar escribe `aceptada` **antes** del `start` y no escribe nada después ([aux:132-148](../../deploy/ops/zascarr_actualizar_aux.py#L132-L148), tests T-17 en [test_ops4_auxiliar.py:179-264](../../tests/test_ops4_auxiliar.py#L179-L264)); el escritor publica temporal exclusivo, `0640`, `fchown(root, gid del directorio)`, `fsync`, `rename` y `fsync` del directorio ([escritor:83-134](../../deploy/ops/escritor_estado_actualizar_ops4.py#L83-L134)); la guarda de monotonía no pisa terminales, no cambia `id`/`inicio_epoch` y no baja `actualizado_epoch` ([escritor:204-240](../../deploy/ops/escritor_estado_actualizar_ops4.py#L204-L240)); la app lee el estado correlacionado por `id` al aceptar ([web/actualizacion.py:104-126](../../src/zascarr/web/actualizacion.py#L104-L126)) | **PASA (A1)** |
| 9 | **`ExecStopPost` único, con `-`, tabla honesta y sin `ExecStartPost`** | [zascarr-actualizar.service:13-18,40](../../deploy/systemd/zascarr-actualizar.service#L13-L18): solo una línea `ExecStopPost=-/bin/sh -c 'case … success:exited:0) r=hecha;; exit-code:exited:75) r=fallida;; *) r=incierta'`; la prueba ejecuta la **cadena real** de la unidad con `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` simulados y comprueba tabla, terminal, reloj invertido, `id`/`inicio` y fallo durable ([test_ops4_estado_final_unidad.py:53-217](../../tests/test_ops4_estado_final_unidad.py#L53-L217)) | **PASA** |
| 10 | **Instalador sin activar por defecto** | Sin `--activar` solo crea clave/dirs y copia módulos y unidades; `--activar` hace `systemctl start` (no `enable`) y avisa «no persistente» y de que la unidad fija puede ejecutar `update.sh` ([instalar:157-165](../../scripts/instalar_actualizacion_ops4.sh#L157-L165)); unidades sin `[Install]` ([socket:16](../../deploy/systemd/zascarr-actualizar.socket#L16), [service:40](../../deploy/systemd/zascarr-actualizar.service#L40)); prueba estática de que no hay `enable --now` ni `enable` ([test_instalar_ops4.py:139-146](../../tests/test_instalar_ops4.py#L139-L146)) | **PASA** |
| 11 | **Sin migración de BD** | `git diff --name-only origin/main...HEAD -- alembic/versions/` → 0 ficheros; el estado es un fichero del host, esquema 1 | **PASA** |
| 12 | **Regla CLAUDE.md §5.8 (frontera de contraseña)** | `git diff --stat origin/main...HEAD -- src/zascarr/services/seguridad.py src/zascarr/web/ajustes.py src/zascarr/services/reautenticacion.py` → vacío; no se dispara la pasada especial por esa frontera (la revisión OPS4 es preceptiva igualmente) | **PASA** |

**Sobre el «deshabilitado» y Compose (matiz que sigue abierto):** `docker-compose.yml` pasa las cuatro `OPS4_*` (incluida `OPS4_ACTUALIZACION_HABILITADA=${OPS4_ACTUALIZACION_HABILITADA:-false}`) y monta `${ZASCARR_DATA_DIR}/ops` en `/run/zascarr-ops:ro` siempre. Efecto: un `.env` de root (`600`, ADR 0012) **sí** puede encender la ruta de UI; sin clave/socket provisionados la ruta responde 503/«no disponible» y el host no ejecuta nada, y armar el socket exige root (`--activar` o `systemctl start`). Es la desviación que la spec A4/CF-R2 pedía registrar por escrito y **no está registrada** en ADR 0026 ni en `ops4-ui-integracion.md` (§3.2 R6, condición CF-2). No es una escalada desde la app.

---

## 3. Regresiones y deuda respecto de las revisiones previas

### 3.1 P1-V (nueva): regresión de verificación de la Parte A

La limpieza de la rama limpia retiró correctamente los módulos v3/experimentos, pero al hacerlo **se llevó por delante tests de controles que siguen en ejecución**. Comparación de la selección OPS4/paridad/instalador: **1005 pruebas declaradas para la rama antigua (`9207d17a`) → 364 en este árbol (374 con `test_ops_paridad.py`)**. Parte de la caída es legítima (tests de v3/experimentos retirados), pero hay pérdidas concretas:

- **R1 — Registro de consumo durable sin suite propia.** Se eliminó `tests/test_ops4_registro_repeticiones.py` (**409 líneas, 27 funciones de test**), que cubría: persistencia real de la marca, orden `fsync` fichero→directorio, fallo de `fsync` en cada etapa (no autoriza ni borra), disco lleno, errores de descriptor, concurrencia entre hilos y **procesos independientes/reapertura**, nombres preexistentes, directorio escribible por grupo, acreditación de `uid`/modo del directorio, y la separación de espacios `autorizacion-<id>` / `solicitud-<id>`. El fichero se retiró entero porque importaba módulos v3, pero **el registro v4 permanece instalado y es el control de un solo uso que usa el auxiliar**. Hoy quedan pruebas de camino feliz y replay en [test_ops4_protocolo_v4.py](../../tests/test_ops4_protocolo_v4.py), [test_ops4_transporte_v4.py](../../tests/test_ops4_transporte_v4.py) y [test_ops4_autorizacion_compuesta.py](../../tests/test_ops4_autorizacion_compuesta.py), pero **no** de los modos de fallo ni de la acreditación del directorio.
- **R2 — Barreras de aislamiento reducidas de 24 a 5 funciones.** El actual [test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py) comprueba que no vuelven los módulos muertos y que solo la ruta web usa el servicio v4, pero **ya no prohíbe que la app importe `deploy/ops`** (lo que la spec §A3/CA-A-08 y su lista de tests TA-06 exigen expresamente), ni mantiene las barreras «el emisor no hace E/S ni red», «el verificador no lee hashes/BD», «la UI no menciona ejecutar actualizaciones» o «la app no importa el auxiliar de copias». Hoy el runtime cumple esas propiedades (verificado con `grep`), pero **no hay red de regresión** que lo impida.
- **R3 — Cierre de imports del instalador sin prueba de cierre.** CA-A-06 pide un test que compare el cierre transitivo de imports de los entrypoints instalados con la lista que copia el instalador. [test_instalar_ops4.py:37-63](../../tests/test_instalar_ops4.py#L37-L63) comprueba una **lista fija** y omite `escritor_estado_actualizar_ops4.py`; el cierre real (auxiliar importa protocolo, verificador, registro y escritor; finalizador importa escritor; el instalador copia exactamente esos y no `admision_v4`) lo verifiqué con sonda de imports en modo `-I`, no con un test del repo.

No hay defecto de ejecución asociado: el código es el mismo que ya fue revisado y la función sigue apagada. Es una **regresión de verificación** que impide declarar la Parte A cerrada con los criterios de su propia spec (la tabla CA-A-06/CA-A-08 marca «Bloquea fusión: Sí») y que conviene reparar o aceptar por escrito antes de fusionar (CF-1).

### 3.2 P2 — residuos de alcance y documentación (nuevos o arrastrados)

- **R4 — Dos ficheros de tests ajenos al alcance**: `tests/test_lector_rar.py` (espera acotada de un nieto) y `tests/test_ensayo_f1bis_arnes.py` (sustituye margen temporal por centinela de `kill`), ambos de estabilización. A2/CA-A-07 pedía el diff solo de OPS4. Sin impacto de seguridad; conviene separarlos o declararlos en la PR.
- **R5 — Documentación que ya no es verdad / enlaces rotos (A5 y A10 sin cerrar).** La limpieza borró ~30 ficheros de test y ~10 documentos, pero la documentación del propio PR sigue citándolos y con recuentos contradictorios:
  - `docs/design/ops4-matriz-evidencia.md` enlaza a 24 tests y 4 documentos que ya no existen (`test_ops4_gate.py`, `test_ops4_registro_repeticiones.py`, `test_ops4_cliente_actualizacion.py`, `especificacion-BL-OPS4.md`, `ops4-diseno-ejecutor-vm.md`, `ops4-registro-repeticiones.md`, `ops4-verificacion-contrasena.md`…), y su frase «La historia B sigue NOT IMPLEMENTED» convive con un circuito integrado y apagado.
  - `docs/design/especificacion-ops4-cierre.md` cita `especificacion-BL-OPS4.md`, `ops4-plan-validacion-aislada.md` y `deploy/ops/modelo_fases_actualizacion_ops4.py`, retirados; su encabezado fija una base `07161e2a` que ya no es este SHA.
  - `docs/adr/0026-actualizacion-manual-confianza-main.md:51` enlaza `secops-ops4-verificacion-final-2026-11-21.md`, que no está en el árbol.
  - Recuentos: `ops4-auxiliar-unidad.md:46` y `ops4-ui-integracion.md:35` dicen «916 pruebas OPS4/paridad y 8906 passed»; `ops4-protocolo-v4.md:41` dice 853; `ops4-transporte-v4.md:29` 874; `ops4-solicitud-v4.md:30` 892; `ops4-autorizacion-app-host.md:93` 791/8880; `ops4-instalador.md:24` «8 casos» (hoy se recogen 11); y `ops4-matriz-evidencia.md:11`/`ops4-revision-pr1159…:60`/`ops4-validacion-suite…` dicen «364 pruebas OPS4 y paridad», cifra que es 364 **sin** paridad y 374 con ella. La cifra de suite completa (8922/2454) es de la rama antigua, no de este árbol (NOT RUN aquí).
  - Frases obsoletas de estado que la spec A5 pedía corregir y siguen ahí: `ops4-protocolo-v4.md:42` («No hay socket, ruta web, auxiliar ni unidad»), `ops4-transporte-v4.md:4` y `ops4-solicitud-v4.md:4` («No está conectado»), `ops4-autorizacion-app-host.md:6-7`; y docstrings de código (`estado_actualizacion.py` dice «no hay escritor ni operación implementados», `solicitud_actualizacion_v4.py` y `actualizacion_transporte_v4.py` dicen «no conectado», `clave_autorizacion.py` «no está conectada»). Ninguna altera la ejecución; la dirección del error es conservadora (dice «no implementado» cuando está apagado), pero una PR de operaciones no debe mentir sobre su propio estado (A5/A10).
- **R6 — Desviación de Compose sin registrar (A4/CF-R2).** Cuatro `OPS4_*` en Compose, default `false`; no consta la nota exigida («el `.env` de root puede encender la UI; la protección que queda es clave/socket no provisionados + instalador manual de root») en ADR 0026 ni en `ops4-ui-integracion.md` (§2, matiz). Condición documental, no defecto.
- **R7 — Residuos de v3 en el árbol limpio.** `deploy/ops/registro_repeticiones_ops4.py` conserva `PREFIJO_SOLICITUD_V3` y `reclamar_id()` (namespace experimental de v3) pese a que el auxiliar no los usa y su único test dedicado se retiró; y `deploy/ops/admision_v4_actualizar_ops4.py` se mantiene aunque la spec A3 lo listaba como retirable (hoy solo lo importan tests como doble de admisión; **no lo instala el instalador**). Ninguno está conectado; es ruido de alcance/deuda, no riesgo.
- **R8 — Tests del instalador poco discriminantes (arrastrado de P2-R1).** El test del grupo por defecto sigue inyectando `ENV_FILE` y usando el gid 1000; no cubre el `ENV_FILE` por defecto ni un `PGID ≠ 1000`. El código está bien (aborta si no resuelve; probado por el propio test de aborto), pero la cobertura es débil. Y `--quitar` sigue abortando si el grupo ya no resuelve (P2-R4).

### 3.3 Delta posterior al último dictamen (OCUPADA) — verificado sin hallazgos

El último dictamen de la rama antigua cubría `48526e03`; después hay un único commit de código, `9207d17a` («no tratar OCUPADA como incierta»), que este árbol incluye byte a byte: la ruta solo lee el fichero de estado si el resultado es `ACEPTADA` ([web/actualizacion.py:104-108](../../src/zascarr/web/actualizacion.py#L104-L108)) y hay test de regresión ([test_ops4_ui_actualizacion.py:256-278](../../tests/test_ops4_ui_actualizacion.py#L256-L278)). Sonda propia: línea real del auxiliar `{"resultado":"rechazada","codigo":"operacion_en_curso"}` → `OCUPADA` en transporte → `ResultadoSolicitudV4.OCUPADA` en servicio, sin presentarse como incierta. **Sin hallazgos de seguridad; mejora de mensaje.**

### 3.4 Lo que esta revisión confirma cerrado respecto de los dictámenes anteriores

- **CE-10/P2-1 (fallback al socket de copias): cerrado.** El transporte solo usa `ops4_socket_file` ([actualizacion_transporte_v4.py:74-76](../../src/zascarr/services/actualizacion_transporte_v4.py#L74-L76)) y hay regresión explícita `test_sin_socket_v4_no_cae_al_de_copias` ([test_ops4_transporte_v4.py:189-194](../../tests/test_ops4_transporte_v4.py#L189-L194)).
- **CE-3-R (grupo del instalador): cerrado en código** con `ENV_FILE` y `PGID` del `.env` y aborto si no resuelve ([instalar:20-29](../../scripts/instalar_actualizacion_ops4.sh#L20-L29), [test_instalar_ops4.py:101-128](../../tests/test_instalar_ops4.py#L101-L128)).
- **CE-4 (OCUPADA): cerrado en código y mensaje**; falta el E2E con el `procesar` real del auxiliar (P2-R5, habilitación).
- **CE-2 (sin `[Install]`, `start` no persistente, mensajes): cerrado**; prueba estática del comando presente ([test_instalar_ops4.py:139-146](../../tests/test_instalar_ops4.py#L139-L146)).
- **P1-8-R (riesgo residual de la clave compartida): registrado** en ADR 0026, que lo acepta solo con la función deshabilitada; la reducción de superficie sigue pendiente para habilitar.
- **P1-7-R (cerrojo en `ReadWritePaths`): parcialmente cerrado** con el prefijo `-` en `/run/zascarr-ops.lock` ([service:38](../../deploy/systemd/zascarr-actualizar.service#L38)); las rutas literales y el refresco de OPS1 bajo sandbox siguen abiertos (B3).
- **P1-9-R (estado/reconciliación): parcial**; A1 implementa estado inicial + terminal + lectura, pero no fases, `head0`/`S`, ni reconciliación (B1/B7).

### 3.5 Estado del código de ejecución

No cambia nada en ejecución respecto de la rama antigua revisada: mismo auxiliar, protocolo, verificador, registro, escritor, finalizador, unidades, instalador y ruta. La limpieza **reduce** superficie (v3/experimentos fuera) y no añade ninguna ruta nueva. Por eso P0/P1 de ejecución no cambian y el veredicto de «no habilitar» se mantiene por las condiciones de habilitación, no por una regresión nueva.

---

## 4. P1 heredados que bloquean habilitar (no fusionar)

| ID | Tema | Estado en `3aa4ec16` |
|---|---|---|
| **P1-1-R** | `--activar` sin confirmación explícita de que arma ejecución real como root; prompt genérico «¿Provisionar OPS4 (sin habilitar la UI)?» | **Abierto**; los mensajes posteriores ya distinguen socket/UI y avisan de la unidad fija |
| **P1-6-R** | Spec `ops4-especificacion-main.md` req. 7/8 (estado persistente con fases/HEAD0/S/resultado y reconciliación) frente a lo implementado | **Parcial**: la spec de cierre acota que es B1; el estado A1 no cumple req. 7/8 |
| **P1-7-R** | Sandbox de `zascarr-actualizar.service`: `ReadWritePaths` literales (`/opt/zascarr`, `/var/lib/zascarr`, `/var/backups/zascarr`), `ProtectHome=yes` con Git/Docker, refresco de OPS1 como aviso blando bajo `ProtectSystem=strict` | **Parcial**: cerrojo con `-`; resto = B3 |
| **P1-8-R** | Clave que autoriza `update.sh` como root vive montada en el contenedor; el host no acredita identidad humana | **Parcial**: riesgo registrado en ADR 0026 y aceptado solo con la función apagada; la habilitación debe decidirlo y reducir superficie (B9/CE-8) |
| **P1-9-R** | Estado durable completo y reconciliación tras `INCIERTA`/`aceptada` huérfana | **Parcial**: A1 (inicial+terminal+lectura); B1/B7 no implementados |
| **H-6/B2** | Cerrojo tanteado, no tomado; ventana entre comprobación y `systemctl start`; reserva atómica pendiente | **Abierto** |
| **B4/I-5** | `update.sh` real bajo la unidad en VM/Pi aislada; Docker/PostgreSQL/systemd reales | **NOT RUN** |
| **B5/H-8** | `ProtectHome` con Git/Docker sin `DOCKER_CONFIG`/`HOME` resueltos | **Abierto** |
| **B6/H-9** | `RuntimeMaxSec=5400` sin fases ni trap; SIGKILL a mitad puede dejar migración parcial sin estado | **Abierto** |
| **B8/CE-5** | Runbook de activación completo (grupo→clave→instalador→cerrojo→socket→bandera→compose) y verificaciones | **No existe** |
| **B9/CE-12** | Rotación/revocación de clave, retención/cuota del registro, paridad 0400/0440, tope de emisiones, plazo de lectura del auxiliar, `--quitar` conservador | **Abiertos** (P2 anteriores) |
| **I-1…I-9** | Clave dedicada, consumo conectado, transporte/envío único, guardas del host (S fijado), arnés aislado, reloj/TTL/NTP, UI, evidencia 3.11 y ADR, autorización explícita del PO | **Abiertos**: I-1/I-2/I-3/I-4 parciales; I-5 (arnés real), I-6 (NTP), I-8 (suite 3.11) e I-9 (autorización del PO) no; I-8 ADR 0026 ya existe |
| **P1-V** | Regresión de verificación de la Parte A (R1–R3 de §3.1) | **Nueva**; no es de ejecución, bloquea cerrar A |

---

## 5. Condiciones exactas

### 5.1 Para fusionar apagado — GO CON CONDICIONES (no incondicional)

- **CF-1 (pre-merge) — Cobertura de la Parte A.** Reponer o portar en este árbol, antes de fusionar (o aceptar por escrito como deuda caducable del PO):
  1. la suite del registro durable (`autorizacion-<id>`): `fsync` fallido en cada etapa, disco lleno, errores de descriptor, concurrencia entre procesos, reapertura, directorio escribible por grupo y acreditación `uid`/modo (R1);
  2. las barreras de aislamiento que exige la spec: la app no importa `deploy/ops`, el emisor no hace E/S/red, el verificador no lee BD/hashes, y el cierre de imports de los entrypoints coincide con la lista que copia el instalador (R2/R3, CA-A-06/CA-A-08/TA-06).
  Es un cambio **solo de tests**; si se añade un commit, el SHA cambia y exige re-dictamen de ese SHA final (CF-3).
- **CF-2 (pre-merge o deuda declarada en el merge) — Verdad documental A4/A5/A10.** (a) Registrar la desviación de Compose en ADR 0026 y/o `ops4-ui-integracion.md` (el `.env` de root puede encender la UI; default `false`; protección = clave/socket no provisionados + instalador manual); (b) actualizar o marcar como históricos los documentos con enlaces rotos y frases obsoletas de §3.2; (c) corregir recuentos con los números de **este** SHA (364 selección OPS4+instalador, 374 con paridad; 11 casos del instalador) y declarar NOT RUN la suite completa/3.11 en vez de heredar 8922/2454.
- **CF-3 (SHA y merge).** Este dictamen cubre exactamente `3aa4ec16` con árbol rastreado limpio. Si se añade cualquier commit (aunque sea solo de tests o documentación) o si la fusión produce un SHA distinto (merge commit/rebase sobre el `origin/main` vigente), hay que repetir este dictamen sobre el SHA que se fusione (CLAUDE.md §5.8). No hay solape con los cambios de main desde la base, así que el re-dictamen es de verificación, no de conflicto esperado.
- **CF-4 (no despliegue en el mismo acto).** La fusión no debe ejecutar `instalar_actualizacion_ops4.sh` (ni `--dry-run` sobre host real), ni `--activar`, ni `systemctl start/enable`, ni `update.sh`, ni tocar `.env`/Pi/Docker/systemd. No debe poner `OPS4_ACTUALIZACION_HABILITADA=true`.
- **CF-5 (evidencia).** Declarar en la PR: comandos, versiones, 364/374 y Ruff de esta revisión; NOT RUN de suite completa y Python 3.11; y que la función sigue **integrada, apagada por defecto**; B1–B10/CE-1…CE-12/I-1…I-9 no están implementados.

Con CF-1…CF-5 cerradas, no hay ninguna objeción de seguridad a fusionar la función **apagada**. Sin CF-1/CF-2, el árbol actual **no debería fusionarse tal cual** (es el sentido del «GO condicionado»).

### 5.2 Para habilitar o desplegar — NO-GO

No se concede ninguna aprobación. Siguen abiertas: **P1-1-R, P1-6-R, P1-7-R, P1-8-R, P1-9-R; H-6/B2, H-10/B3, B4, B5/B6, B7, B8, B9, B10; I-1…I-9**; y las CE de los dictámenes anteriores: **CE-1** (confirmación de `--activar`), **CE-5** (runbook), **CE-6** (estado/spec), **CE-7** (sandbox/refresco), **CE-8** (clave compartida y superficie), **CE-9** (reconciliación), **CE-11** (reserva atómica) y **CE-12** (resto de P2: plazo del auxiliar, retención/cuota, rotación, paridad, `--quitar`, runbook). **CE-2, CE-3-R, CE-4 y CE-10 están cerradas en código** (con los residuales de cobertura R1–R3 y P2-R5).

Se recuerda que `--activar` arma ejecución real como root (la unidad fija ejecuta `update.sh --rama main`) y que la bandera de UI no es la única puerta si el socket está arrancado con la clave legible por el grupo. **No se debe habilitar, instalar en la Pi ni desplegar a partir de este informe.**

---

## 6. Pruebas y lint ejecutados (evidencia)

Todas las pruebas desde este worktree, con `PYTHONPATH="$PWD/src:$PWD"` para no probar el checkout principal del venv. No se ejecutó la suite completa.

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-b-limpia

# 1) Selección dirigida OPS4 + instalador (sin suite completa)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" \
  /mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python -m pytest -q \
  -p no:cacheprovider --basetemp=/tmp/secops-op4blimpia-bt \
  tests/test_ops4_*.py tests/test_instalar_ops4.py
# → 364 passed, 1 warning in 16.92s

# 2) La misma selección + paridad
... tests/test_ops4_*.py tests/test_instalar_ops4.py tests/test_ops_paridad.py
# → 374 passed, 1 warning in 18.60s

# 3) Paridad/instaladores/cerrojo/compose (complementaria)
... tests/test_ops_paridad.py tests/test_instalar_ops.py \
    tests/test_cerrojo_operaciones.py tests/test_compose_env.py
# → 75 passed, 1 warning in 6.42s

# Ruff equivalente CI (pyproject target py311)
ruff check src/                                  # → All checks passed!
ruff check --select S src/                       # → All checks passed!
ruff check deploy/ops/<7 módulos OPS4>.py        # → All checks passed!
ruff check tests/test_ops4_*.py tests/test_instalar_ops4.py  # → All checks passed!
ruff check --select S deploy/ops/<7 módulos OPS4>.py
# → 2 hallazgos preexistentes: S603 y S607 en zascarr_actualizar_aux.py::_iniciar
#   (argv fijo y PATH fijo; CI solo escanea src/). No es regresión.
ruff format --check src/zascarr/services/{actualizacion_transporte_v4,autorizacion_actualizacion,
  clave_autorizacion,estado_actualizacion,ops_actualizacion_v4,solicitud_actualizacion_v4}.py \
  src/zascarr/web/actualizacion.py
# → 7 files would be reformatted (el CI no ejecuta `format`; preexistente, no bloquea)

bash -n scripts/instalar_actualizacion_ops4.sh    # → OK
git diff --check origin/main...HEAD               # → limpio
git diff --stat origin/main...HEAD -- src/zascarr/services/seguridad.py \
  src/zascarr/web/ajustes.py src/zascarr/services/reautenticacion.py   # → vacío (CM-4)
git diff --name-only origin/main...HEAD -- alembic/versions/ | wc -l   # → 0
git rev-parse HEAD                                # → 3aa4ec16… (árbol rastreado limpio)
```

**Sondas de solo lectura (sin efectos, temporales en `/tmp`):**

```text
Settings(_env_file=None)
  ops4_actualizacion_habilitada = False
  ops4_autorizacion_key_file    = /run/zascarr-ops/actualizar.key
  ops4_socket_file              = /run/zascarr-ops/actualizar.sock
  ops4_estado_file              = /run/zascarr-ops/actualizar-status.json

PyYAML docker-compose.yml
  environment OPS4: las 4 variables esperadas, flag con ${…:-false}
  volume: ${ZASCARR_DATA_DIR:-/var/lib/zascarr}/ops:/run/zascarr-ops:ro

Entrada del auxiliar real → transporte → servicio
  b'{"v":4,"id":"a"*32,"resultado":"rechazada","codigo":"operacion_en_curso"}\n'
  transporte: ocupada ; servicio: ResultadoSolicitudV4.OCUPADA   (P1-4-R OK)

Entrypoints instalados con python3 -I (sin systemd, stdin vacío, dirs en /tmp)
  zascarr-actualizar-aux → {"v":4,…,"codigo":"no_disponible"}, rc=0, no escribe
  zascarr-estado-actualizar-ops4 --ruta <ausente> --resultado hecha → rc=0, no crea
Cierre de imports vs instalador (sonda manual): aux importa protocolo/verificador/
  registro/escritor; finalizador importa escritor; el instalador copia exactamente
  esos 4 + entrypoints; admision_v4 no se instala (solo lo usan tests)
Python 3.11 estático: ast.parse(feature_version=(3,11)) OK en los 14 módulos OPS4
grep src/deploy/scripts: sin referencias a los módulos v3/experimentos retirados
```

**Contraste con la documentación del PR:** la cifra declarada «364 pruebas OPS4 y paridad» es en realidad 364 sin paridad / 374 con paridad; los demás recuentos de §3.2 son de la rama antigua y no de este árbol. La suite completa **no** se ha ejecutado aquí (NOT RUN).

---

## 7. NOT RUN (declarado, no PASS)

- **Suite completa** (`pytest -q -rs`) y **Python 3.11 en runtime** (la imagen de producción); solo 3.14.4 local.
- **systemd del host**, `systemd-analyze verify`, arranque real del socket/unidad, semántica real de `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS` para parada manual/timeout.
- **`update.sh` real** (ni una vez), instalador real como root, `--activar`, `systemctl start/enable`, `docker compose config` (solo parseo YAML con PyYAML), Docker/PostgreSQL reales, Pi/VM.
- **Socket Unix real contra el `procesar` real con cerrojo** (el E2E de la UI sigue usando `admitir_v4` como servidor de prueba); **respuesta perdida** extremo a extremo.
- **Cortes eléctricos/`fsync` reales**, supervivencia a reinicio, rotación/revocación de clave, NTP/TTL, retención/cuota del registro, `S == HEAD0`.
- **Ningún despliegue**: no se tocaron `.env`, `/etc`, `/usr/local`, systemd, la Pi, Docker ni datos reales.

---

## 8. Snapshot revisado (SHA-256)

`HEAD` = `3aa4ec1646ffb97c310e16c1a4dded8ab6318c74` (rama `feat/ops4-b-limpia-443`), árbol rastreado limpio; merge-base con `origin/main` = `2c773e53…`; `origin/main` local = `9fe0be06…`.

| Fichero | SHA-256 |
|---|---|
| `deploy/ops/zascarr_actualizar_aux.py` | `97e9552ae84ea4da638155642adb96cc9e106e76d5df0846d164a2a9282c15ab` |
| `deploy/ops/protocolo_actualizar_v4_ops4.py` | `72bf693e41af84ec1ddc29515a84022f5884635750d0a0b374a3e75012efa834` |
| `deploy/ops/verificador_autorizacion_ops4.py` | `96628781707ba14a15131b9c4cd71c0081b65dd18f39e66aa48db59cedff1b72` |
| `deploy/ops/registro_repeticiones_ops4.py` | `3221036741d3495859608dfc4bfa4426a0cfb11bcb3055be1a70a2ae33c6c354` |
| `deploy/ops/escritor_estado_actualizar_ops4.py` | `ad0845d5d1acb22999a40bdb01eca79575c4a9ab930c4f9473c38c44302f2e70` |
| `deploy/ops/estado_actualizar_ops4.py` | `862c76470ae53cb0aa64e89d4362ac806d76bec10b387eeaaa2ae5467685438d` |
| `deploy/ops/admision_v4_actualizar_ops4.py` | `21d0822e15f1bc365618a60a1d3ba57ba4d468c329cc2ade14d5c63fc4e1a6fc` |
| `deploy/systemd/zascarr-actualizar.service` | `fec6f269b61e2b58e732f5927fb7bf0c49a49b5efc062ba0122d0ae21d61c467` |
| `deploy/systemd/zascarr-actualizar.socket` | `9fbc6ce70f97f9f4afe5f7131da84e7176d47720bbeffc03e5a9b168f2f08a8c` |
| `deploy/systemd/zascarr-actualizar@.service` | `edd7e01151767bfdf3eb937c1c5e98f82953606c8687b72d7199f98d52c50ee6` |
| `scripts/instalar_actualizacion_ops4.sh` | `de85d88acbfd94f98cf794d66fd3d1683a8b78f8e552ac858b5d4677dc1a7fd8` |
| `src/zascarr/services/actualizacion_transporte_v4.py` | `97b6d6d6f5c7ebb0f14b95868785562a8b9ac06dd179993dad1ac875c8c16672` |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1bbdbb22ac83d0a2c65e0914359d0ccfa32d2b9d53379fb9125abff14` |
| `src/zascarr/services/clave_autorizacion.py` | `075a21d8d1cc7efae8e5dda0d2b36dc7fa6921619b352ce62ab5110d94a8ae0c` |
| `src/zascarr/services/estado_actualizacion.py` | `2296b02424df4c977cbe4d62b3a5910b79dca2e2918ac52e05e3d32a8ef30506` |
| `src/zascarr/services/ops_actualizacion_v4.py` | `94db06081ebb77fad91d31d3e959b2cbae5530ff42b3bf1b26455e0c71e43dc5` |
| `src/zascarr/services/solicitud_actualizacion_v4.py` | `bd12e358184955846c320c67029d149e8fab9f5e240a2c9e144f38c4a36bb6db` |
| `src/zascarr/web/actualizacion.py` | `c29d4e81e14893258fa8dd4e0835ea5b7095c5363b67ce8b6f9536a84853bc04` |
| `src/zascarr/web/estado.py` | `dc0eb311b32e32f1a463cbb07169d10afa9c780542c72a3fc913c8a75545b502` |
| `src/zascarr/config.py` | `8bf4f2082f0dd26b7df8c0728ad62c677e67088c0f1ef6f8ee4ff1f86ecb5c53` |
| `docker-compose.yml` | `82f2ffdfaecf45afa90a9fbd9a86b357f2a689f0e87ebf39f69d55e87a210913` |
| `tests/test_ops4_aislamiento.py` | `67a7703ac7a2dd345163724451b8612368875214b9fb6bcaa778bdad54953bbb` |
| `tests/test_instalar_ops4.py` | `32499e6c827a887b30e9b38d5aac7101f81001c85a444516aef1dcda82b5ded1` |

---

## 9. Vigencia

- Válido **solo** para `3aa4ec16` con la función deshabilitada y los valores por defecto. **Caduca** con cualquier commit, rebase o merge que cambie el SHA, y con cualquier cambio de los ficheros de §8, de las unidades, del auxiliar o de los documentos de contrato que fijan el estado (CLAUDE.md §5.8). El SHA que se fusione debe tener su propio dictamen si cambia algo de eso.
- Caducidad ordinaria: **2027-01-21** (60 días), o antes si cambia la decisión de autoridad, el protocolo v4, la clave, el registro durable, el instalador, el Compose o las unidades.
- Este informe se escribe como **fichero nuevo no rastreado**. Si se versiona, debe ser un commit **solo de documentación** que no altere el código dictaminado.
- **No autoriza** habilitar, instalar en la Pi, armar el socket, desplegar ni ejecutar `update.sh` real. La actualización sigue deshabilitada por defecto.

---

## 10. Resumen para el PO

- **No hay P0 ni P1 de ejecución** en el árbol apagado: la bandera es `false`, la ruta da 404 antes de leer clave, el auxiliar solo arranca una unidad fija, el `ExecStopPost` es único y honesto, el instalador no activa nada por defecto, y la clave/consumo de un solo uso mantienen las propiedades ya revisadas.
- **Sí hay una regresión de verificación (P1-V)** de la limpieza: se perdieron la suite del registro durable y casi todas las barreras de aislamiento, y no está el test de cierre de imports que exige la spec de cierre. No explota con la función apagada, pero incumple CA-A-06/CA-A-08/TA-06 y debe reponerse o aceptarse por escrito (CF-1).
- **La documentación del PR no dice la verdad del árbol** (enlaces rotos, recuentos de otra rama, desviación de Compose sin registrar, frases «no conectado» obsoletas). Es deuda documental, no de seguridad, pero bloquea A10/CF-2.
- **Fusionar apagado:** aceptable **con** CF-1…CF-5 cerradas; tal cual, no. **Habilitar o desplegar: NO-GO** hasta B1–B10, I-1…I-9 y las CE pendientes, con revisión del SHA final y autorización expresa separada. **Este informe no autoriza ningún despliegue.**
