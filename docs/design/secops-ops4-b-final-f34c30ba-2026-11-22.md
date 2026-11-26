# SecOps — Dictamen final del SHA `f34c30ba` (OPS4/#443, PR #1233, delta de cierre)

**Rol:** SecOps · **Fase:** dictamen final de solo lectura del SHA que se fusiona (CLAUDE.md §5.8).
**Fecha:** 2026-11-22 (Europe/Madrid).
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-b-limpia`; rama `feat/ops4-b-limpia-443`.
**SHA dictaminado:** `f34c30baae79da05f1077b0594c206945b6cb413` — PR #1233, «test(ops): reponer cobertura durable y cerrar alcance apagado (#443)».
**Delta revisado:** `3aa4ec1646ffb97c310e16c1a4dded8ab6318c74` (SHA del [dictamen SecOps anterior](secops-ops4-b-limpia-2026-11-22.md)) → `f34c30ba` (1 commit).
**Base:** merge-base con `origin/main` local = `2c773e53c235812adabc76e76cd3b111d04d4026`; `origin/main` local = `3ce1bd5e` (el SHA está **2 commits delante / 28 detrás**; `git merge-tree` contra `3ce1bd5e` da árbol limpio, pero el merge commit tendría **otro SHA** y exigiría re-dictamen — condición C5).
**Entorno:** venv de pruebas del repo (Python 3.14.4, pytest 9.2.0, ruff 0.17.4); la imagen de producción es `python:3.11-slim` y `pyproject.toml` exige `>=3.11`. Sin `TEST_DATABASE_URL`, sin Docker, sin systemd del host, sin Pi.
**Restricciones respetadas:** no se editó código, plantillas, unidades, instalador, Compose, `update.sh` ni `bootstrap.sh`; no se hizo commit ni push; no se ejecutó la Pi, Docker real, PostgreSQL real, systemd del host, el instalador con `--activar` ni `update.sh`. **El único fichero escrito es este informe** (nuevo, no rastreado). El árbol rastreado estaba limpio al empezar y sigue limpio salvo este informe.
**La actualización sigue DESHABILITADA por defecto.** Este dictamen **no autoriza habilitar, armar el socket, instalar en la Pi ni desplegar**, y **no sustituye** la revisión de habilitación.

---

## 0. Veredicto

1. **P0 de seguridad: ninguno.** Con los valores por defecto (`OPS4_ACTUALIZACION_HABILITADA=false`, sin clave ni socket provisionados, unidades sin `[Install]`, instalador sin activación) no hay ruta que ejecute `update.sh`, ni bypass de la puerta de UI, ni fuga de clave/contraseña/testigo.
2. **P1 de ejecución: ninguno nuevo.** El delta **no toca ni una línea de código de producción**: `git diff --name-status 3aa4ec16..f34c30ba -- src/ deploy/ scripts/ docker-compose.yml alembic/` devuelve **solo** el borrado de `deploy/ops/admision_v4_actualizar_ops4.py`, un módulo que **no estaba instalado, no lo importaba ningún entrypoint y no lo usaba la app** (verificado en el árbol base y en el final, §3). Los 20 ficheros de ejecución/wiring de OPS4 conservan **byte a byte** el SHA-256 del dictamen anterior.
3. **P1-V de verificación: queda residual, no cerrada del todo.** El commit repone lo esencial de lo que la limpieza había borrado —la suite de fallos del **registro durable** (15 funciones / 28 casos, portadas sin cambios) y tres barreras de aislamiento—, pero **no cierra literalmente** las condiciones CF-1/CF-2 del dictamen anterior: faltan las pruebas negativas de acreditación `uid`/modo de `abrir_directorio_autorizaciones`, las barreras «el emisor no hace E/S ni red» / «el verificador no lee hashes ni BD», el test de **cierre transitivo de imports** que exige CA-A-06/CA-A-08, y dos de los seis puntos de TA-09. Nada de esto cambia la ejecución con la bandera apagada; es deuda de verificación/documentación (§4, §5.2).
4. **Fusionar apagado: GO CON CONDICIONES (GO en seguridad).** No hay objeción de seguridad a fusionar la función **integrada y apagada**; el delta reduce superficie y repone red de regresión. Las condiciones **C1–C5** de §6 son de verificación/documentación o del acto de fusión, **ninguna abre una ruta de ejecución**, y deben cerrarse o aceptarse por escrito en la PR antes del merge.
5. **Habilitar (bandera `true`, socket/unidad, `update.sh` real) o desplegar: NO-GO.** Siguen abiertos los P1 heredados P1-1-R, P1-6-R, P1-7-R, P1-8-R, P1-9-R, H-6/B2, B4–B10, I-1…I-9, las CE pendientes y el runbook de activación. **No se autoriza ningún despliegue.**
6. **Caducidad:** vale **solo** para `f34c30ba` con la función deshabilitada y los valores por defecto. Caduca con cualquier commit, rebase o merge que cambie el SHA (incluida la fusión real sobre el `origin/main` actual, `3ce1bd5e`) y con cualquier cambio de los ficheros de §9 o de los documentos de contrato que fijan el estado.

---

## 1. Alcance del delta

Un commit, **19 ficheros** (+852/−136): **ningún fichero de producción** salvo el borrado del módulo muerto. Sin migración Alembic, sin cambios en `docker-compose.yml`, `.env.example`, `scripts/update.sh`, `scripts/instalar_ops.sh`, `scripts/_cerrojo.sh`, `deploy/systemd/` ni en el instalador.

| Grupo | Ficheros | Comentario |
|---|---|---|
| Rename (retirada de producción) | `deploy/ops/admision_v4_actualizar_ops4.py` → [`tests/_host_v4.py`](../../tests/_host_v4.py) | 95 % de similitud (`3 +/1 -`: solo el docstring «Doble de host para tests; no se instala»); ya no vive en `deploy/ops`. |
| Tests nuevos | [`test_ops4_alcance_apagado.py`](../../tests/test_ops4_alcance_apagado.py) (32 líneas, 3 casos, TA-09), [`test_ops4_registro_repeticiones.py`](../../tests/test_ops4_registro_repeticiones.py) (216 líneas, 15 funciones / 28 casos) | Cobertura repuesta y prueba estática de alcance. |
| Tests adaptados | [`test_ops4_protocolo_v4.py`](../../tests/test_ops4_protocolo_v4.py) (‑9 casos: solo protocolo; las pruebas de `admitir_v4` se retiran con el módulo muerto), [`test_ops4_transporte_v4.py`](../../tests/test_ops4_transporte_v4.py), [`test_ops4_ui_actualizacion.py`](../../tests/test_ops4_ui_actualizacion.py) (importan el doble de `tests`), [`test_ops4_aislamiento.py`](../../tests/test_ops4_aislamiento.py) (+3 barreras: 5 → 8) | Deltas solo de tests. |
| Documentación | 10 `ops4-*` + ADR 0026 (recuentos y nota de Compose) + los dos informes previos de SecOps/QA de `3aa4ec16` ahora versionados | Ver §5.2: los recuentos ya cuadran, pero quedan enlaces y frases obsoletas. |

**Retirada segura (probada en el árbol base):** en `3aa4ec16`, `git grep -n admision_v4` solo devolvía tests y documentación; el instalador no lo copiaba (`grep` en `instalar_actualizacion_ops4.sh` sin coincidencias) y ni `src/` ni `deploy/` ni `scripts/` lo mencionaban. En el árbol final ya no queda ninguna referencia en código; solo el enlace roto de la documentación que cita §5.2.

**El doble de host no se instala ni se ejecuta:** [`tests/_host_v4.py`](../../tests/_host_v4.py#L1-L10) importa únicamente `protocolo_actualizar_v4_ops4` y `verificador_autorizacion_ops4`, no abre sockets, no persiste y no ejecuta; el instalador copia una lista **explícita** de `deploy/ops` (no `tests/`), el paquete se construye con `packages.find where=["src"]`, y pytest **no recoge** el fichero (nombre con `_`; verificado: 0 coincidencias de `_host_v4` en la colección de `tests/`).

---

## 2. No se ha colado ejecución ni habilitación (árbol final)

Mismo estado por defecto que el SHA anterior, reverificado directamente en el árbol final:

| # | Control | Evidencia en `f34c30ba` | Resultado |
|---|---|---|---|
| 1 | **Bandera `false` por defecto** | [`config.py:286`](../../src/zascarr/config.py#L286) `Field(default=False)`; sonda `Settings(_env_file=None)` → `False` y las tres rutas `/run/zascarr-ops/...` esperadas | **PASA** |
| 2 | **La UI/BD no puede encenderla** | `RuntimeSettingsService` y `web/ajustes.py` sin campos `ops4_*`; `.env.example` sin `OPS4_*`; ningún script escribe la bandera | **PASA** |
| 3 | **`POST /ui/actualizar` → 404 antes de leer clave/reautenticar** | [`web/actualizacion.py:80-81`](../../src/zascarr/web/actualizacion.py#L80-L81) devuelve 404 **antes** de `leer_clave_autorizacion` (`:86`); petición real probada en tests de UI (selección verde) | **PASA** |
| 4 | **Auxiliar y unidad de acción fija** | [`zascarr_actualizar_aux.py:63`](../../deploy/ops/zascarr_actualizar_aux.py#L63) `UNIDAD = "zascarr-actualizar.service"`; `_iniciar` ([`:199-209`](../../deploy/ops/zascarr_actualizar_aux.py#L199-L209)) solo ejecuta `systemctl start --no-block` con argv fijo; `ExecStart` fijo `update.sh --rama main` ([service:12](../../deploy/systemd/zascarr-actualizar.service#L12)) | **PASA** |
| 5 | **Instalador sin activar por defecto** | `--activar` solo hace `systemctl start` del socket, no `enable` ([instalar:159-164](../../scripts/instalar_actualizacion_ops4.sh#L159-L164)); unidades sin `[Install]` ([service:40](../../deploy/systemd/zascarr-actualizar.service#L40), [socket:16](../../deploy/systemd/zascarr-actualizar.socket#L16)); el borrado de módulo no altera su lista de copia | **PASA** |
| 6 | **Sin migración de BD** | `git diff --name-only 3aa4ec16..f34c30ba -- alembic/versions/` → vacío; 52 versiones, igual que antes | **PASA** |
| 7 | **`update.sh`, `instalar_ops.sh`, `_cerrojo.sh`, unidades y Compose intactos** | `git diff --name-only 3aa4ec16..f34c30ba --` sobre esas rutas → vacío | **PASA** |
| 8 | **Compose: bandera con default `false` y montaje `ro`** | [`docker-compose.yml:164`](../../docker-compose.yml#L164) `${OPS4_ACTUALIZACION_HABILITADA:-false}`; [`docker-compose.yml:217`](../../docker-compose.yml#L217) `/run/zascarr-ops:ro`; parseado YAML propio: 4 variables y volumen esperados | **PASA** |
| 9 | **Sin migración de la bandera a «encendida»** | `grep -rn OPS4_ACTUALIZACION_HABILITADA` no encuentra ningún `true` persistido; solo docs/tests y el default de Compose | **PASA** |
| 10 | **Los tests añadidos no ejecutan nada del host** | `test_ops4_alcance_apagado.py` es lectura de ficheros; `test_ops4_registro_repeticiones.py` usa `tmp_path` y, para concurrencia, subprocesos Python sobre directorios temporales; ni systemd, ni docker, ni `/run`, ni `update.sh`, ni red | **PASA** |
| 11 | **Sin secretos ni `.env`** | Ningún `.env` rastreado; sin claves ni sockets versionados en el delta; el informe previo no aporta ninguno | **PASA** |
| 12 | **Regla CLAUDE.md §5.8** | El delta no toca `services/seguridad.py`, `web/ajustes.py` ni `services/reautenticacion.py` (diff vacío en esos paths) | **PASA** |

---

## 3. Producción sigue igual

**Hashes de producción del árbol final, idénticos a los del dictamen de `3aa4ec16`** (los 20 ficheros de ejecución/wiring de la tabla del informe previo, más `scripts/update.sh`, también sin cambios):

| Fichero | SHA-256 (sin cambios) |
|---|---|
| `deploy/ops/zascarr_actualizar_aux.py` | `97e9552ae84ea4da638155642adb96cc9e106e76d5df0846d164a2a9282c15ab` |
| `deploy/ops/protocolo_actualizar_v4_ops4.py` | `72bf693e41af84ec1ddc29515a84022f5884635750d0a0b374a3e75012efa834` |
| `deploy/ops/verificador_autorizacion_ops4.py` | `96628781707ba14a15131b9c4cd71c0081b65dd18f39e66aa48db59cedff1b72` |
| `deploy/ops/registro_repeticiones_ops4.py` | `3221036741d3495859608dfc4bfa4426a0cfb11bcb3055be1a70a2ae33c6c354` |
| `deploy/ops/escritor_estado_actualizar_ops4.py` | `ad0845d5d1acb22999a40bdb01eca79575c4a9ab930c4f9473c38c44302f2e70` |
| `deploy/ops/estado_actualizar_ops4.py` | `862c76470ae53cb0aa64e89d4362ac806d76bec10b387eeaaa2ae5467685438d` |
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
| `scripts/update.sh` | `07d16002da4f083d3875bca7d28bbe09e7d3433843a72a17d2b3c937fd2ec098` |

- **No hay regresión de comportamiento:** el único cambio en rutas de producción es el borrado de un módulo no instalado. El cierre de imports de lo instalado sigue siendo auxiliar → {protocolo, verificador, registro, escritor}; finalizador → escritor; el instalador copia exactamente esos cuatro módulos y los dos entrypoints, y no copia `admision_v4` ni `tests/` (sonda de imports sobre las dos ramas `try/except` del auxiliar y el finalizador).
- **El E2E de UI sigue simulando el host** con el doble `admitir_v4` (antes en `deploy/ops`, ahora en `tests/_host_v4.py`); el `procesar` real del auxiliar y el socket real **siguen NOT RUN** (son fase de habilitación, no de este dictamen).
- **Dos matices no nuevos, sin efecto con la bandera apagada:** Compose inyecta las cuatro `OPS4_*` y monta `${ZASCARR_DATA_DIR}/ops:ro` siempre (un `.env` de root `600` puede encender la UI; sin clave/socket la ruta responde 404/503 y el host no ejecuta nada; armar el socket exige root). La nota exigida ya está registrada en [ADR 0026, «Desviación de Compose»](../adr/0026-actualizacion-manual-confianza-main.md#desviación-de-compose).

---

## 4. Cobertura perdida: qué se ha repuesto y qué no

### 4.1 Registro durable (CF-1.1): repuesto en lo esencial

La suite dedicada vuelve a existir y **los 15 primeros tests son portados sin cambios** respecto de la rama antigua (`9207d17a`): el `diff` solo quita los imports v3 y los 12 tests finales. Cubre, con 28 casos sobre directorios temporales:

| Requisito de CF-1 (R1) | Test restaurado |
|---|---|
| Persistencia real, nombre, modo `0600`, repetición | [`test_reclamacion_real_persiste_y_no_contiene_secretos`](../../tests/test_ops4_registro_repeticiones.py#L28) |
| Orden `fsync` fichero→directorio | [`test_orden_de_sincronizacion_fichero_luego_directorio`](../../tests/test_ops4_registro_repeticiones.py#L37) |
| Fallo de `fsync` en cada etapa: no autoriza **ni borra** la marca | [`test_fallo_fsync_no_autoriza_ni_borra_marca`](../../tests/test_ops4_registro_repeticiones.py#L49) |
| Callback que no acredita sincronización | [`test_callback_que_no_acredita_sync_deniega`](../../tests/test_ops4_registro_repeticiones.py#L65) |
| ID inválido / nombre preexistente (enlace, FIFO, directorio) sin seguirlo | [`:72`](../../tests/test_ops4_registro_repeticiones.py#L72), [`:79`](../../tests/test_ops4_registro_repeticiones.py#L79) |
| Directorio escribible por grupo | [`test_directorio_escribible_por_grupo_deniega`](../../tests/test_ops4_registro_repeticiones.py#L93) |
| Descriptores inválidos / de fichero / errores en `dup`, `fstat`, `close` | [`:101`](../../tests/test_ops4_registro_repeticiones.py#L101), [`:106`](../../tests/test_ops4_registro_repeticiones.py#L106), [`:179`](../../tests/test_ops4_registro_repeticiones.py#L179) |
| Disco lleno (`ENOSPC`) | [`test_disco_lleno_deniega_sin_inventar_consumo`](../../tests/test_ops4_registro_repeticiones.py#L113) |
| Renombrado del directorio: no redirige operaciones | [`:125`](../../tests/test_ops4_registro_repeticiones.py#L125) |
| Concurrencia entre hilos y entre **procesos independientes/reapertura** | [`:140`](../../tests/test_ops4_registro_repeticiones.py#L140), [`:149`](../../tests/test_ops4_registro_repeticiones.py#L149) |
| Sin fugas de descriptores en éxitos/repite/fallos | [`:204`](../../tests/test_ops4_registro_repeticiones.py#L204) |

**Lo que sigue sin cubrirse de R1 (residual de CF-1):**
- **Acreditación `uid`/modo de `abrir_directorio_autorizaciones`** (el punto que CF-1 nombraba expresamente): no se portaron `test_abrir_directorio_durable_acredita_uid_y_modo`, ni los 5 casos `test_abrir_directorio_rechaza_origen_no_acreditado` (modo 0755, `uid` ajeno, fichero, enlace, inexistente), ni los 4 `test_abrir_directorio_parametros_invalidos`. Hoy la función solo se ejerce en **camino feliz** por el E2E de transporte/UI; sus rechazos no tienen prueba automática.
- Separación explícita de namespaces `autorizacion-<id>` / `solicitud-<id>` (el test antiguo `test_prefijos_distintos_no_se_satisfacen_entre_si`): solo cubierta indirectamente (el E2E de [autorizacion_compuesta](../../tests/test_ops4_autorizacion_compuesta.py) comprueba el nombre `autorizacion-` y que una marca de `vistos` no reabre; no que ambos prefijos no se satisfagan entre sí).
- `test_el_registro_de_autorizacion_no_vive_en_run_ni_en_vistos` (aserción documental): no portado.
- Los 12 tests no portados incluyen 2 del módulo v3 retirado (`admitir`) —legítimamente fuera—; el resto está cubierto de forma indirecta por `test_ops4_autorizacion_compuesta.py` (aceptada/repetida, ID distinto no consume, otra clave, replay tras reapertura, fallo del registro no acepta) y por el E2E de transporte.

**Matiz de diseño:** la suite restaurada ejercita `reclamar_id` (namespace v3 `solicitud-`) mientras producción usa `reclamar_autorizacion` (`autorizacion-`); ambas comparten `_reclamar_marca`, y el E2E sí acredita el prefijo de producción, por lo que los modos de fallo quedan cubiertos de forma equivalente, no literal. El resto v3 (`PREFIJO_SOLICITUD_V3`/`reclamar_id`) sigue en el módulo instalado, sin llamadores (R7 del informe previo, P2 sin riesgo).

### 4.2 Barreras de aislamiento (CF-1.2): +3, pero no todas las pedidas

[`test_ops4_aislamiento.py`](../../tests/test_ops4_aislamiento.py) pasa de 5 a 8 funciones. Nuevas: la app no importa `deploy.ops` ni `from deploy` ([`:66`](../../tests/test_ops4_aislamiento.py#L66)); el instalador menciona los 4 módulos que importa el auxiliar y el finalizador ([`:73`](../../tests/test_ops4_aislamiento.py#L73)); unidad/auxiliar con `python3 -I`, sin `PYTHONPATH` y con `ReadWritePaths` de ops4/ops ([`:87`](../../tests/test_ops4_aislamiento.py#L87)).

**Siguen faltando** las barreras que el dictamen anterior nombró expresamente para módulos que **sí siguen** en el árbol: «el emisor de autorización no hace E/S ni red» (`autorizacion_actualizacion.py`), «el emisor no usa la clave del auxiliar ni registra», «el verificador no lee hashes ni la BD» (`verificador_autorizacion_ops4.py`) y «la UI no menciona ejecutar actualizaciones». Las demás barreras antiguas se retiraron con razón (comprobaban módulos v3 ya eliminados o «no conectado» ahora obsoleto por el cableado apagado).

### 4.3 TA-09: parcial

[`test_ops4_alcance_apagado.py`](../../tests/test_ops4_alcance_apagado.py) recoge **3 de los 6 puntos** de TA-09 ([spec, TA-09](../design/especificacion-ops4-cierre.md#L1157)): bandera `false` en `config.py` y Compose ([`:9`](../../tests/test_ops4_alcance_apagado.py#L9)); unidades sin `[Install]` e instalador sin `enable` ([`:26`](../../tests/test_ops4_alcance_apagado.py#L26)); y un `test_no_se_invoca_update_sh_ni_se_instala_la_unidad` cuya aserción es **vacua para el instalador** (la excepción `or "instalar" in ruta.name` lo deja pasar siempre), por lo que no añade garantía real. **No hay prueba automática** de: ausencia de `ExecStartPost` (cubierta por otros dos tests, no por TA-09), **ausencia de migración Alembic nueva** y **ausencia de `.env` de producción**. Son dos comprobaciones manuales de este informe y del anterior, no red de regresión.

### 4.4 CA-A-06/CA-A-08 (cierre de imports): aproximación estática, no cierre transitivo

[`test_el_instalador_copia_todo_lo_que_importa_el_auxiliar`](../../tests/test_ops4_aislamiento.py#L73) comprueba que auxiliar contiene `from <módulo> import` para 4 módulos fijos y que el instalador los menciona, y que el instalador menciona el finalizador. **No** calcula el cierre transitivo ni compara listas/modos, no incluye el import del finalizador → escritor y una línea de comentario en el script también satisfaría la aserción. La sonda manual de este dictamen confirma que **hoy** el cierre real coincide, pero CA-A-06/CA-A-08 tal como están redactados **no quedan acreditados por un test**; sigue vigente parte de R3 del informe previo.

### 4.5 Conteos: cuadran con el árbol

- Selección dirigida OPS4/instalador: **389 recogidas / 389 passed** (364 + 25: +28 registro, +3 aislamiento, +3 alcance, −9 protocolo por el módulo muerto). Con `test_ops_paridad.py`: **399**.
- Colección de la suite completa (solo `--collect-only`, no ejecutada): **11401 = 8947 + 2454**, exactamente la aritmética de los documentos actualizados; la cifra de la suite completa sigue siendo **declarada, no reproducida aquí** (NOT RUN).
- Instalador: `test_instalar_ops4.py` recoge **11 casos**, pero [ops4-instalador.md:24](../design/ops4-instalador.md#L24) sigue diciendo «8 casos» (deuda de recuento).
- [ops4-matriz-evidencia.md:11](../design/ops4-matriz-evidencia.md#L11) dice «389 pruebas seleccionadas de OPS4 **y paridad**»: son 389 sin paridad y 399 con ella; el resto de documentos ya usan «389 OPS4/instalador».

**Conclusión de §4:** la cobertura perdida **se ha repuesto en lo esencial** (modos de fallo del consumo durable + tres barreras), pero **CF-1 no se cierra literalmente**; por eso P1-V queda residual (§5.1) y pasa a condición C1.

---

## 5. Hallazgos

### 5.1 P1-V residual — verificación, no ejecución (`P1`, sin ruta abierta)

Lo anterior no introduce ningún defecto explotable con la bandera apagada (el código de ejecución es idéntico al ya revisado y sigue apagado). Se mantiene como **P1-V residual** porque los criterios de fusión de la propia especificación —CA-A-06, CA-A-08, la lista CF-1 y TA-09— **no quedan literalmente acreditados** en este SHA (faltan: pruebas negativas de acreditación del directorio durable; barreras emisor/verificador; test de cierre transitivo de imports; 2 puntos de TA-09). Es deuda de tests/documentación que no bloquea la seguridad de fusionar apagado si se acepta por escrito (C1), pero sí impide declarar «Parte A cerrada» con sus propios criterios.

### 5.2 P2 — documentación que aún no cuenta la verdad del SHA (CF-2 parcial)

El commit **sí** corrigió los recuentos principales (389 y 8947/2454, coherentes con la colección) y **registró la desviación de Compose en ADR 0026**; pero quedan contradicciones, incluidas dos introducidas por este delta:

- **Enlace roto nuevo** en [ops4-protocolo-v4.md:25](../design/ops4-protocolo-v4.md#L25): sigue apuntando a `deploy/ops/admision_v4_actualizar_ops4.py`, que este commit acaba de retirar. Debería apuntar a [`tests/_host_v4.py`](../../tests/_host_v4.py) o al auxiliar real.
- **Frases de estado obsoletas** que el propio commit no tocó: [protocolo-v4.md:42](../design/ops4-protocolo-v4.md#L42) «No hay socket, ruta web, auxiliar ni unidad»; [transporte-v4.md:4](../design/ops4-transporte-v4.md#L4); [solicitud-v4.md:4](../design/ops4-solicitud-v4.md#L4); [autorizacion-app-host.md:6-7 y 96-97](../design/ops4-autorizacion-app-host.md#L90-L100); y docstrings de módulos instalados que dicen «no instalado/no conectado» ([registro:1](../../deploy/ops/registro_repeticiones_ops4.py#L1), [aux:7](../../deploy/ops/zascarr_actualizar_aux.py#L7)) o «no está conectada» en `clave_autorizacion.py` / `estado_actualizacion.py`.
- **Matriz de evidencia desactualizada** además de sus enlaces muertos: [matriz:40](../design/ops4-matriz-evidencia.md#L40) describe `test_ops4_protocolo_v4.py` como si todavía probara «replay y admisión con consumo durable real» —este commit retiró esas pruebas— y mantiene «NOT IMPLEMENTED» ([`:9`](../design/ops4-matriz-evidencia.md#L9)) y **36 enlaces rotos** (tests y documentos retirados: `test_ops4_gate.py`, `test_ops4_cliente_actualizacion.py`, `especificacion-BL-OPS4.md`, `ops4-diseno-ejecutor-vm.md`, `ops4-registro-repeticiones.md`…).
- **Enlace roto arrastrado** en [ADR 0026:51](../adr/0026-actualizacion-manual-confianza-main.md#L51): cita `secops-ops4-verificacion-final-2026-11-21.md`, que no está en el árbol (CF-2(b) del informe previo sigue abierto).
- **Narrativa de recuentos incoherente** en [ops4-matriz-evidencia.md:11](../design/ops4-matriz-evidencia.md#L11): dos repeticiones históricas distintas dicen ahora ambas «8947/2454»; [ops4-validacion-suite-2026-11-20.md](../design/ops4-validacion-suite-2026-11-20.md) mezcla «8947» con el «8880/2431» de la corrección anterior. Son cifras históricas reescritas, no las de este SHA.
- [ops4-instalador.md:24](../design/ops4-instalador.md#L24) «8 casos» frente a 11 recogidos; [ops4-autorizacion-app-host.md:93](../design/ops4-autorizacion-app-host.md#L93) sigue hablando de «47 de registro durable».

Ninguna de estas frases altera la ejecución; la dirección del error es conservadora, pero A5/CA-A-10 y CF-2(b) **no se cierran** en este SHA (condición C2).

### 5.3 P2 — una regla de estilo nueva en tests (Ruff E501, no bloqueante de CI)

`ruff check tests/test_ops4_aislamiento.py` falla con **E501 (102 > 100)** en la línea nueva [`test_ops4_aislamiento.py:88`](../../tests/test_ops4_aislamiento.py#L88). El CI **solo ejecuta `ruff check src/` + `--select S src/`** (ambos verdes), y el directorio `tests/` ya tiene 613 hallazgos preexistentes (520 E501), así que no es una regresión de la política de CI; aun así, el árbol del dictamen anterior tenía esa selección limpia y este commit la ensucia (C3, cosmético).

### 5.4 P2 — residuos de alcance ya conocidos (sin riesgo)

- `deploy/ops/registro_repeticiones_ops4.py` conserva `PREFIJO_SOLICITUD_V3` y `reclamar_id` sin llamadores; la suite repuesta los prueba precisamente a ellos (ver §4.1). R7 sigue abierto como ruido/deuda, no como riesgo.
- Los informes de QA y SecOps de `3aa4ec16` quedan **versionados dentro de este commit**: son instantáneas históricas correctas de su SHA; quien lea el árbol debe saber que describen `3aa4ec16`, no `f34c30ba` (este informe es el del SHA final).

### 5.5 Sin hallazgos (positivo)

- Ninguna ruta de ejecución nueva, ninguna habilitación, ningún cambio de permisos/claves/sockets, ninguna migración, ningún secreto añadido.
- Reducción real de superficie: un módulo de `deploy/ops` que no se instalaba deja de estar en el árbol de producción y pasa a tests, con el fichero de tests que lo usaba adaptado (sin pérdida de los E2E que lo usan como doble de host).
- El cierre de imports real coincide hoy con la lista del instalador (sonda manual); el doble de host no se colecta como test ni se empaqueta.

---

## 6. Condiciones

### Para fusionar apagado — GO CON CONDICIONES

- **C1 (pre-merge o aceptación escrita del PO) — verificación.** Completar el residual de CF-1, **o** aceptar por escrito como deuda caducable en la PR:
  1. portar las pruebas negativas de `abrir_directorio_autorizaciones` (`uid`/modo/enlace/fichero/inexistente/parámetros inválidos) y la separación explícita de prefijos `autorizacion-`/`solicitud-` (R1);
  2. añadir las barreras «el emisor no hace E/S ni red», «el emisor no usa la clave del auxiliar ni registra», «el verificador no lee hashes ni BD» (CF-1.2);
  3. sustituir la comprobación estática por un test que **calcule el cierre transitivo** de imports de los entrypoints y lo compare con la lista/modos del instalador (CA-A-06/CA-A-08), o declarar la deuda;
  4. completar TA-09 con `ExecStartPost`, ausencia de migración Alembic y ausencia de `.env` de producción, o declararlo.
  Es un cambio **solo de tests**; si se añade un commit, el SHA cambia y exige re-dictamen (C5).
- **C2 (pre-merge o deuda declarada en el merge) — verdad documental (CF-2).** Corregir el enlace roto nuevo de [ops4-protocolo-v4.md:25](../design/ops4-protocolo-v4.md#L25), actualizar o marcar como históricas las frases y la matriz de §5.2, corregir «8 casos»/«389 y paridad», y arreglar el enlace roto de ADR 0026. Alternativa admitida por el informe previo: declarar la deuda documental en el mensaje/PR.
- **C3 (cosmético) — Ruff.** Corregir el E501 de [test_ops4_aislamiento.py:88](../../tests/test_ops4_aislamiento.py#L88) o declarar que CI no lintea `tests/`. No bloquea.
- **C4 (acto de fusión, no despliegue).** La fusión no debe ejecutar `instalar_actualizacion_ops4.sh` (ni `--dry-run` sobre host real), ni `--activar`, ni `systemctl start/enable`, ni `update.sh`, ni tocar `.env`/Pi/Docker/systemd, ni poner `OPS4_ACTUALIZACION_HABILITADA=true`.
- **C5 (SHA y merge).** Este dictamen cubre exactamente `f34c30ba` con árbol rastreado limpio (salvo este informe). `origin/main` local ya está en `3ce1bd5e` (28 commits por delante de la base); `git merge-tree HEAD origin/main` da árbol limpio, pero si la fusión produce **merge commit o rebase**, el SHA que se fusiona es otro y exige re-dictamen de verificación (CLAUDE.md §5.8). No se ha re-ejecutado CI sobre el merge ref nuevo (NOT RUN).
- **C6 (evidencia).** Declarar en la PR: comandos/versiones, 389/399, 11401 de colección, Ruff de §7, NOT RUN de suite completa y Python 3.11, y que la función sigue **integrada, apagada por defecto**; B1–B10, CE e I-1…I-9 no están implementados.

### Para habilitar o desplegar — NO-GO

No se concede ninguna aprobación. Siguen abiertas: **P1-1-R, P1-6-R, P1-7-R, P1-8-R, P1-9-R; H-6/B2, H-10/B3, B4, B5/B6, B7, B8, B9, B10; I-1…I-9**; **CE-1, CE-5, CE-6, CE-7, CE-8, CE-9, CE-11, CE-12** (CE-2, CE-3-R, CE-4 y CE-10 cerradas en código), y el runbook de activación no existe. `--activar` arma ejecución real como root y la bandera de UI no es la única puerta si el socket está arrancado con la clave legible por el grupo. **No se debe habilitar, instalar en la Pi ni desplegar a partir de este informe.**

---

## 7. Pruebas y lint ejecutados (evidencia)

Todas las pruebas desde este worktree, con `PYTHONPATH="$PWD/src:$PWD"` y `PYTHONDONTWRITEBYTECODE=1`, temporales en `/tmp`; sin suite completa.

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-b-limpia
PY=/mnt/Datos/Documentos/Repos/zascarr/.venv-test/bin/python

# 1) Selección dirigida OPS4 + instalador (la que documentan los docs)
$PY -m pytest -q -p no:cacheprovider --basetemp=/tmp/secops-final-bt \
  tests/test_ops4_*.py tests/test_instalar_ops4.py
# → 389 passed, 1 warning in 12.94s

# 2) Ficheros cambiados por el delta (registro/aislamiento/alcance/protocolo/
#    transporte/UI)
$PY -m pytest -q -p no:cacheprovider --basetemp=/tmp/secops-final-bt3 \
  tests/test_ops4_registro_repeticiones.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_alcance_apagado.py tests/test_ops4_protocolo_v4.py \
  tests/test_ops4_transporte_v4.py tests/test_ops4_ui_actualizacion.py
# → 81 passed, 1 warning in 3.14s

# 3) Complementaria (paridad, instaladores OPS1, cerrojo, Compose, env)
$PY -m pytest -q -p no:cacheprovider --basetemp=/tmp/secops-final-bt2 \
  tests/test_ops_paridad.py tests/test_instalar_ops.py \
  tests/test_cerrojo_operaciones.py tests/test_compose_env.py \
  tests/test_env_consumidores.py
# → 87 passed, 1 warning in 5.83s

# 4) Conteos (collect-only, sin ejecutar la suite)
$PY -m pytest --collect-only -q tests/test_ops4_*.py tests/test_instalar_ops4.py
# → 389 tests collected
#   + tests/test_ops_paridad.py → 399 tests collected
$PY -m pytest --collect-only -q tests/
# → 11401 tests collected (= 8947 + 2454 de los docs; solo colección)

# 5) Ruff equivalente CI
ruff check src/                       # → All checks passed!
ruff check --select S src/            # → All checks passed!
ruff check tests/test_ops4_*.py tests/test_instalar_ops4.py
# → 1 error: E501 en tests/test_ops4_aislamiento.py:88 (nuevo; CI no lintea tests/)
ruff check tests/                     # → 613 errores preexistentes (520 E501), no política de CI
ruff format --check <tests cambiados> # → 7 files would be reformatted (preexistente; CI no ejecuta format)

# 6) Estáticas
bash -n scripts/instalar_actualizacion_ops4.sh && bash -n scripts/update.sh  # → OK
git diff --check 3aa4ec16..f34c30ba                                          # → limpio
git diff --name-only 3aa4ec16..f34c30ba -- scripts/update.sh scripts/instalar_ops.sh \
  scripts/_cerrojo.sh deploy/systemd/ docker-compose.yml .env.example alembic/  # → vacío
git diff --name-status 3aa4ec16..f34c30ba -- src/ deploy/ scripts/ docker-compose.yml alembic/
# → solo D deploy/ops/admision_v4_actualizar_ops4.py
git status --porcelain                                                       # → vacío (antes de este informe)
```

**Sondas de solo lectura (sin efectos, temporales en memoria/proceso):**

```text
Settings(_env_file=None) → ops4_actualizacion_habilitada=False;
  key=/run/zascarr-ops/actualizar.key; socket=.../actualizar.sock; estado=.../actualizar-status.json
PyYAML docker-compose.yml → servicio zascarr: las 4 OPS4_* (flag con ${…:-false}) y el
  volumen ${ZASCARR_DATA_DIR}/ops:/run/zascarr-ops:ro
Cierre de imports real (AST, dos ramas del auxiliar y finalizador):
  aux → protocolo, verificador, registro, escritor; finalizador → escritor;
  instalador copia exactamente esos 4 + 2 entrypoints; no admision_v4; no tests/
Cadena git: 3aa4ec16 (base) → f34c30ba (1 commit); origin/main local 3ce1bd5e;
  merge-base 2c773e53; 2 delante / 28 detrás; merge-tree limpio con 2 ficheros
  solapados (src/zascarr/main.py, web/templates/estado.html) que no toca el delta
Pytest: `_host_v4` no aparece en la colección (0 coincidencias); módulo en tests/, no empaquetado
```

---

## 8. NOT RUN (declarado, no PASS)

- **Suite completa** (`pytest -q -rs`) y **Python 3.11 en runtime** (la imagen de producción); solo 3.14.4 local y la colección de 11401. Las cifras de suite de los documentos (**8947/2454**) son consistentes con la colección pero **no reproducidas aquí**.
- **CI de la PR sobre `f34c30ba` / nuevo merge ref** (el `mergeStateStatus` previo era del SHA anterior; `main` ha avanzado 16 commits desde entonces). No ejecutado.
- **systemd del host**, `systemd-analyze verify`, arranque real del socket/unidad, semántica real de `SERVICE_RESULT`/`EXIT_CODE`/`EXIT_STATUS`.
- **`update.sh` real** (ni una vez), instalador real como root, `--activar`, `systemctl start/enable`, `docker compose config` (solo parseo YAML), Docker/PostgreSQL reales, Pi/VM.
- **Socket Unix real contra el `procesar` real con cerrojo** (el E2E sigue usando el doble `admitir_v4`); respuesta perdida extremo a extremo.
- **Cortes eléctricos/`fsync` reales**, supervivencia a reinicio, rotación/revocación de clave, NTP/TTL, retención/cuota del registro, `S == HEAD0`.
- **Pruebas negativas de acreditación del directorio durable** (no existen en el árbol; ver C1) y cierre transitivo de imports (solo sonda manual).
- **Ningún despliegue**: no se tocaron `.env`, `/etc`, `/usr/local`, systemd, la Pi, Docker ni datos reales.

---

## 9. Snapshot revisado (SHA-256)

`HEAD` = `f34c30baae79da05f1077b0594c206945b6cb413` (rama `feat/ops4-b-limpia-443`), árbol rastreado limpio; base del delta `3aa4ec16`; merge-base con `origin/main` = `2c773e53…`; `origin/main` local = `3ce1bd5e…`.

Producción: tabla de §3 (21 ficheros, sin cambios respecto de `3aa4ec16`).

Cambiados por el delta:

| Fichero | SHA-256 |
|---|---|
| `tests/_host_v4.py` | `27f567b51a0dc3431a75ca956da2e5ac0fa7e67c9877c48f8856218a418e0928` |
| `tests/test_ops4_alcance_apagado.py` | `a166e2c2c5c70ec25834775bfa03a15464b63719d1a5abe7a64c82f17b293068` |
| `tests/test_ops4_registro_repeticiones.py` | `efcfc81c5419503bc6811346af9481bafdf415d81df72915fc522da66d93a1e0` |
| `tests/test_ops4_aislamiento.py` | `d4e509da2de80fd9046cf487f8af5abe645c1d2b812ed4254ce91a43884cf13e` |
| `tests/test_ops4_protocolo_v4.py` | `431d8644390aaeb33584db5c638d39073f2ef06d661604ccb61814dbd1180d37` |
| `tests/test_ops4_transporte_v4.py` | `886105e4c2e7a0d07096bc13f7da3d5b83503b5c987a0e8f1f84354e86ce3340` |
| `tests/test_ops4_ui_actualizacion.py` | `7d520a3d4f30e63727f0713efebffa067e1b73747bc08e564edd5c520c132e8d` |
| `docs/design/secops-ops4-b-limpia-2026-11-22.md` | `5c1e8164e5963523494489bbe135c40fb00aade77644b184e932a790e587d844` |
| `docs/design/qa-ops4-b-limpia-2026-11-22.md` | `f3ba9ded9c88ef237e8077aa4bcfd5efa6f8a662732babcd17fe30b92455b315` |

---

## 10. Vigencia

- Válido **solo** para `f34c30ba` con la función deshabilitada y los valores por defecto. **Caduca** con cualquier commit, rebase o merge que cambie el SHA, y con cualquier cambio de los ficheros de §3/§9, de las unidades, del auxiliar o de los documentos de contrato que fijan el estado (CLAUDE.md §5.8). El merge actual sobre `origin/main` (`3ce1bd5e`) produciría otro SHA: requiere re-dictamen (C5).
- Caducidad ordinaria: **2027-01-21** (60 días), o antes si cambia la decisión de autoridad, el protocolo v4, la clave, el registro durable, el instalador, el Compose o las unidades.
- Este informe se escribe como **fichero nuevo no rastreado**. Si se versiona, debe ser un commit **solo de documentación** que no altere el código dictaminado.
- **No autoriza** habilitar, instalar en la Pi, armar el socket, desplegar ni ejecutar `update.sh` real. La actualización sigue deshabilitada por defecto.

---

## 11. Resumen para el PO

- **No hay P0 ni P1 de ejecución en el árbol apagado.** El delta de cierre no toca ni una línea de producción: solo retira de `deploy/ops` un módulo muerto que nunca se instaló ni se importó (pasa a `tests/_host_v4.py`), añade tests y corrige recuentos. La bandera sigue `false`, la ruta da 404 antes de leer la clave, el auxiliar solo arranca la unidad fija, la unidad no se habilita y el instalador no activa nada por defecto.
- **La cobertura perdida se ha repuesto en lo esencial:** vuelve la suite de fallos del registro durable (15 funciones / 28 casos, portada sin cambios) y tres barreras de aislamiento, además de la prueba de alcance apagado. El árbol pasa de 364 a **389 pruebas OPS4/instalador, todas verdes**.
- **No queda cerrada del todo la verificación (P1-V residual):** faltan las pruebas negativas de acreditación `uid`/modo del directorio durable, tres barreras de aislamiento (emisor/verificador) y el test de cierre transitivo de imports de CA-A-06/CA-A-08; TA-09 está a medias (2 de sus 6 puntos sin automatizar). No afecta a la ejecución apagada, pero impide declarar la Parte A cerrada con sus criterios.
- **La documentación aún no es autodescriptiva:** este commit introdujo un enlace roto (el módulo movido), dejó frases «no está conectado» obsoletas, la matriz con 36 enlaces muertos y recuentos históricos incoherentes («8 casos» frente a 11; «389 y paridad» frente a 399), y el enlace roto de ADR 0026.
- **Fusionar apagado: GO CON CONDICIONES C1–C6** (verificación y documentación; ninguna abre ruta de ejecución). **Habilitar o desplegar: NO-GO** hasta B1–B10, CE e I-1…I-9, runbook y revisión/autorización expresa aparte. **Este informe no autoriza ningún despliegue.**
