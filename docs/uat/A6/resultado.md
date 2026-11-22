# A6 · Recuperación real en candidata aislada (UATP-06/07)

| Campo | Valor |
|---|---|
| Historias | UATP-06 [#1144](https://github.com/juanajok/zascarr/issues/1144), UATP-07 [#1145](https://github.com/juanajok/zascarr/issues/1145), épica [#1141](https://github.com/juanajok/zascarr/issues/1141) |
| Fecha/hora | 2026-11-22T13:13:39+01:00 (pasada 1); 2026-11-22T13:23:06+01:00 (pasada 2) |
| Entorno | E-A6 (alias; host local aislado; sin hostname, IP ni ruta). **No** se usó la Pi ni datos reales. |
| Candidata | tag `uat-candidata-20261122`, tag_commit `2c773e53c235812adabc76e76cd3b111d04d4026`, head `2c773e53c235812adabc76e76cd3b111d04d4026`, BUILD_SHA `2c773e53c235812adabc76e76cd3b111d04d4026`, `app_version=1.15.1`, alembic `0052`, image_id `sha256:7be671c1a4dae062db856b70f2f1a457f494cff2624e4f6388796f86864d82b2` |
| Baseline | T1 `uat-base-20261122`, tag_commit `ab33c14737a6cdb204c6b989705306303de75c91`, head `ab33c14737a6cdb204c6b989705306303de75c91`, BUILD_SHA `ab33c14737a6cdb204c6b989705306303de75c91`, app_version `1.15.1`, alembic `0052`, image_id `sha256:9bcda20caae3467dc8681420594f2e82fd697d4a6d7ae9e949ee31fa5401e504` (definido en la pasada 2 con autorización del PO) |
| Tag antiguo | `v1.15.1` (`4f6ccdd310f5a644d19bdc1293327ac60d531b00`): sin lector ni restauración; Alembic llega a `0016` |
| Decisión D-3 | **Aprobada por el PO** (task-68): T1 = main previo a #1221, con lector y restauración. V-03 ejecutado. |
| Resultado global | **PASS de las 25 comprobaciones obligatorias del catálogo §7.4.** UATP-06 acreditable; UATP-07: R-01…R-05 y V-03 PASS, y N-01 por interfaz PASS en ensayo con las costuras documentadas. `N-01-systemd-host` NOT RUN (`sin_root_systemd`). |

## Resumen

Se creó el tag anotado `uat-candidata-20261122` sobre `2c773e53` y se levantó **E-A6**, un
proyecto Docker aislado (`zascarr-a6`, puertos 15432/18000, volúmenes y estado propios) con la
imagen construida con `BUILD_SHA=2c773e53c235812adabc76e76cd3b111d04d4026`. La matriz negativa (SHA incorrecto, gzip
truncado, `series` ausente y `issues` ausente) se ejecutó por `restaurar_datos.sh --produccion`:
las cuatro filas salieron con `rc=1`, `copia_no_valida`, la `comprobacion` correcta,
`base_en_su_sitio=true` y **cero eventos de contenedor provocados por el intento**; B0, su
manifiesto, `copias.json`, la base viva, las filas testigo y el CBZ quedaron idénticos. Después se
restauró B0 (control positivo: `hecha`, recuentos 2/2/2) y se comprobó la ficha y el lector en la
página guardada (P=3 de 6) con Chrome real. La copia manual de la biblioteca a un volumen Docker
vacío en otro sistema de archivos conservó inventario, mtime con nanosegundos y SHA-256. En la **pasada 2 (task-68)**, con autorización del PO, se definió el baseline T1 `uat-base-20261122`
sobre `ab33c147` (main previo a #1221, con lector y restauración) y se ejecutó V-03: T1 arrancó con
el catálogo restaurado conservando recuentos, testigo, progreso y la reapertura en la página 3.
También se ejecutó N-01 desde la interfaz con el auxiliar ops real (tres costuras de arnés por no
haber systemd/root): la persona ve «Esa copia está dañada… Elige otra.» y la base/copia quedan
intactas. Con eso las 25 comprobaciones obligatorias del catálogo quedan en PASS. La única pieza
**NOT RUN** es el arranque real de la unidad systemd del host (`N-01-systemd-host`, `motivo=sin_root_systemd`), que no se puede ejecutar en este host aislado.

## Tabla de comprobaciones

Evidencia canónica: [`evidencia/resultado.txt`](evidencia/resultado.txt); datos estructurados:
[`evidencia/negativas.json`](evidencia/negativas.json),
[`evidencia/instantaneas.json`](evidencia/instantaneas.json).

| ID | Qué comprueba | Esperado | Obtenido | Resultado | Evidencia |
|---|---|---|---|---|---|
| V-01 | Identidad de C | tag_commit == head == BUILD_SHA; app_version coincide; alembic coincide | Las cuatro igualdades se cumplen; image_id registrado | **PASS** | `resultado.txt` §V |
| V-02 | T0 `v1.15.1` sin lector ni restore | ausencia verificada | `web/lector.py` y `services/ops_host.py` ausentes; Alembic máx. `0016` | **PASS** | `resultado.txt` §V |
| V-03 | T1 arranca con el catálogo restaurado | T1 definido por el PO (D-3) | `uat-base-20261122` en `ab33c147`: arranca con B0' y conserva recuentos 2/2/2, testigo, progreso pág. 3, ficha y lector | **PASS** | [`evidencia/pasada2/t1-arranque.txt`](evidencia/pasada2/t1-arranque.txt) |
| N-01-interfaz | N-01 desde la acción «Restaurar…» | acción de interfaz | confirmar=200; POST aceptado; `copia_no_valida/sha256_copia`; base y B0' intactas; UI «Esa copia está dañada… Elige otra.» | **PASS (ensayo)** | [`evidencia/pasada2/n01-ui-resumen.txt`](evidencia/pasada2/n01-ui-resumen.txt) |
| N-01 | SHA incorrecto | `copia_no_valida`/`sha256_copia`/base `true`/0 eventos | rc=1; estado correcto; eventos del intento=0 | **PASS** | `evidencia/negativas.json`, `eventos-resumen.txt` |
| N-02 | gzip truncado | `copia_no_valida`/`gzip_cabecera`/base `true`/0 eventos | rc=1; estado correcto; eventos del intento=0 | **PASS** | `evidencia/negativas.json` |
| N-03a | Falta `series` | `copia_no_valida`/`tablas_dump`/base `true`/0 eventos | rc=1; estado correcto; eventos del intento=0 | **PASS** | `evidencia/negativas.json` |
| N-03b | Falta `issues` (D-6a) | ídem | rc=1; estado correcto; eventos del intento=0 | **PASS** | `evidencia/negativas.json` |
| N-04 | Control positivo con B0 | `hecha`, recuentos, base `true` | rc=0; `hecha`; series=2 issues=2 files=2 | **PASS** | `evidencia/ops-restaurar-n04.json` |
| S-01 | Instantánea antes/después | idéntica en N-01…N-03 | 8/8 grupos idénticos, salud incluida | **PASS** | `evidencia/instantaneas.json` |
| S-02 | `copias.json` sigue ofreciendo B0 | B0 presente, SHA-256 igual | B0 presente; SHA y manifiesto sin cambios | **PASS** | `resultado.txt` §S/D |
| S-03 | Sin eventos ni escrituras del intento | 0 eventos propios | 0 eventos propios (4 filas); los crudos son sondas de HEALTHCHECK | **PASS** | [`evidencia/eventos-resumen.txt`](evidencia/eventos-resumen.txt) |
| D-01 | B0 y manifiesto intactos | mismos SHA-256 | idénticos antes y después de cada fallo | **PASS** | `resultado.txt` §S/D |
| F-01 | Raíces, destino vacío/distinto, espacio | 1 raíz; D1 vacío; otro FS; espacio | 1 raíz (`/biblioteca`); D1 vacío; st_dev 66309≠66310; 11,2 GB libres | **PASS** | [`evidencia/copia-archivos.txt`](evidencia/copia-archivos.txt) |
| F-02 | Mtime e inventario | idénticos | inventario `7bb7359ab4230628…` idéntico; `st_mtime_ns` idéntico | **PASS** | `evidencia/copia-archivos.txt` |
| F-03 | SHA testigo CBZ y página P | idénticos | CBZ `9a6edec49594b4d2…`; página 3 `5dea59a8fe6656de…` idénticos | **PASS** | `evidencia/copia-archivos.txt`, `resultado.txt` §R |
| F-04 | SHA-256 de toda la raíz (opcional) | idéntico o NOT RUN | R1=D1=`b0a892374b76a3a7…` | **PASS** | `evidencia/F04-y-espacio.txt` |
| R-01 | Ficha ofrece «Continuar (pág. 3)» | presente | presente (HTTP y captura) | **PASS** | `resultado.txt` §R, `evidencia/capturas/` |
| R-02 | Lector abre en P=3 | `data-pagina="3"`, `data-total="6"` | presente; contador «Página 3 de 6» | **PASS** | `resultado.txt` §R, `evidencia/capturas/` |
| R-03 | Página P con SHA testigo; archivo restaurado | coinciden | página 3 `5dea59a8fe6656de…`; archivo `9a6edec49594b4d2…` | **PASS** | `resultado.txt` §R |
| R-04 | Relaciones y progreso | coinciden, sin huérfanos | `current_page=3`, `status=reading`, huérfanos 0 | **PASS** | `resultado.txt` §R |
| R-05 | Recuentos y Alembic del catálogo restaurado | coinciden con B0 | alembic 0052; series=2 issues=2 files=2 library_roots=1 | **PASS** | `resultado.txt` §R |
| A-01 | `resultado.md` y `resultado.txt` existen | presentes y enlazados | presentes; mtime igualado | **PASS** | este documento / `evidencia/resultado.txt` |
| A-02 | Saneado | grep sin coincidencias | 0 coincidencias | **PASS** | `resultado.txt` §A |
| A-03 | Diagnóstico por intento | `intento`/`comprobacion`/`copia_version` | 5 intentos en `.jsonl`; estado con las tres claves | **PASS** | `evidencia/intentos-restauracion.jsonl` |
| A-04 | Línea `CHECK` por comprobación | todas las obligatorias | 25 obligatorias con `CHECK` (V-03 incluida) | **PASS** | `evidencia/resultado.txt` |

## Instantánea antes/después

| Grupo | Qué se comparó | N-01…N-03 (S0 vs S1) |
|---|---|---|
| Código | `HEAD`, árbol limpio | idéntico |
| BD | `alembic_version` y recuentos `series/issues/files/reading_progress/runtime_settings/library_roots` | idéntico |
| Testigo | `file_size_bytes`, `file_mtime_ns`, `sha256_hash`, `issue_id` | idéntico |
| Progreso | `current_page`, `status`, `file_id`, `last_read_at` | idéntico |
| Salud | `status`, `version`, `checks.*` | idéntico (incluido `checks.restore`, que no cambió en esta ejecución; se declara volátil por diseño) |
| Copias | SHA-256 de B0, manifiesto, `status.json`, `copias.json`; B0 ofrecida | idéntico |
| Archivos | SHA-256 y `mtime_ns` del CBZ testigo | idéntico |
| Contenedores | `State.Status`, `RestartCount`, `StartedAt` de app y PostgreSQL | idéntico |

En el cambio de montaje para montar el destino restaurado (F) y en N-04 el contenedor de la app se
recrea/reinicia de forma controlada; por eso `StartedAt` cambia entre S2 y S3. Es el único campo que
cambia; `checks.restore` se declara volátil por diseño aunque en esta ejecución no cambió. Los grupos
de datos siguen idénticos (ver `evidencia/instantaneas.json`).

## Versión declarada

| Campo | Valor | Regla |
|---|---|---|
| tag | `uat-candidata-20261122` (anotado) | `git cat-file -t` = `tag` |
| tag_commit | `2c773e53c235812adabc76e76cd3b111d04d4026` | = HEAD en la ejecución |
| head | `2c773e53c235812adabc76e76cd3b111d04d4026` | = tag_commit |
| build_sha | `2c773e53c235812adabc76e76cd3b111d04d4026` | = head (BUILD_SHA de la imagen) |
| app_version | `1.15.1` | = `pyproject.toml` = `/api/health.version` |
| alembic | `0052` | = manifiesto B0 = BD restaurada |
| image_id | `sha256:7be671c1a4dae062db856b70f2f1a457f494cff2624e4f6388796f86864d82b2` | informativo |

No se declara la copia solo como «1.15.1»: la identidad es la tupla completa. B0
(`backup-20261122_130727`, `sha256 974d82c1d673760b…`, 17837 bytes) se creó con `backup.sh`;
sin disco offsite terminó con `offsite_mount_missing` (copia local y manifiesto ya escritos), lo
que se registra y **no** invalida B0.

## Copia de archivos (UATP-07, D-1)

- **R1**: única raíz de biblioteca del ensayo, `path=/biblioteca`, `enabled=true`, `is_default=true`.
- **D1**: volumen Docker `zascarr-a6-biblioteca`, **vacío** antes de copiar, montado en la misma ruta
  de contenedor (`/biblioteca`), en otro sistema de archivos (`st_dev` 66309 frente a 66310).
- **Copia**: `rsync -aH --numeric-ids` en un contenedor auxiliar (el host no tiene un destino
  escribible en otro dispositivo); `rsync_rc=0`. Se usó `-aH` porque el destino no admite los xattrs
  `$LX*` sintéticos del origen NTFS; la spec permite `-aH` en ese caso.
- **Inventario**: 2 ficheros, 4229 bytes; hash `mtime+tamaño` idéntico R1/D1 (`7bb7359ab4230628…`);
  SHA-256 completo de la raíz idéntico (`b0a892374b76a3a7…`); `st_mtime_ns` del testigo idéntico
  (`1795349115750528900`); SHA-256 del CBZ `9a6edec49594b4d2…`.
- Tras restaurar el catálogo, D1 conserva el mismo inventario y el mismo SHA del CBZ.

## Reapertura en la página guardada

`file_id=a6000000-0000-4000-8000-000000000021`, `issue_id=a6000000-0000-4000-8000-000000000011`,
P=3, total=6. La ficha muestra «Continuar (pág. 3)»; el lector abre con `data-pagina="3"` y sirve la
página 3 con `sha256=5dea59a8fe6656de…`; `files.sha256_hash` coincide con el archivo restaurado y el
progreso (`current_page=3`, `status=reading`) sobrevive a la restauración. Capturas con Chrome real
(`evidencia/capturas/`):

![Ficha con Continuar pág. 3](evidencia/capturas/captura-ficha-pag3-movil.png)
![Lector en la página guardada](evidencia/capturas/captura-lector-pag3-movil.png)

## Pendientes y bloqueos

| Qué | Estado | Motivo / qué falta |
|---|---|---|
| V-03 (T1 baseline) | PASS (pasada 2) | `uat-base-20261122` en `ab33c147`; T1 arranca con B0' y conserva recuentos/testigo/progreso |
| N-01 desde la interfaz | PASS (ensayo, pasada 2) | auxiliar ops real con 3 costuras de arnés (sin systemd/root); la persona ve la causa y la base/copia no cambian |
| N-01 en systemd real del host | NOT RUN | `sin_root_systemd`: no hay root ni systemd en el host aislado para instalar/arrancar la unidad |
| Health `backup`/`restore` = `error` | esperado en E-A6 | no hay timer de copias ni dispatcher de restauración; `checks.database=ok` |
| Offsite de `backup.sh` | `offsite_mount_missing` | E-A6 no monta disco offsite; la copia local B0 quedó válida |

El único NOT RUN (`N-01-systemd-host`) es una pieza de infraestructura del host, no una
comprobación del catálogo §7.4: las 25 obligatorias están en PASS. Nada NOT RUN se convierte en
PASS: la sustitución de las tres costuras del arnés queda declarada y no se oculta.

## Ampliación (pasada 2, task-68): V-03 y N-01 por interfaz

Con autorización del PO se cierra el hueco de **D-3** y se ejecutan las dos comprobaciones que
faltaban. Entorno E-A6 nuevo y aislado (mismo proyecto `zascarr-a6`, misma disciplina: nunca la Pi
ni datos reales), con B0' propia `backup-20261122_131744` (`sha256 3e4de7c3a3cf6b59…`, manifiesto `6de889a2b615a7eb…`) y
la misma semilla sintética.

### T1 baseline y V-03 (PASS)

- Tag anotado **`uat-base-20261122`** en `ab33c14737a6cdb204c6b989705306303de75c91` (main previo a #1221, **con** lector y
  restauración). `build_sha = head = tag_commit = ab33c14737a6cdb204c6b989705306303de75c91`, `app_version=1.15.1`, `alembic=0052`,
  `image_id=sha256:9bcda20caae3467dc8681420594f2e82fd697d4a6d7ae9e949ee31fa5401e504`.
- Condición de V-03: T1 y C comparten revisión de Alembic (`0052`).
- Se restauró B0' con la candidata (`hecha`, 2/2/2) y se arrancó T1 sobre ese catálogo. T1 conserva
  los recuentos (2/2/2/1 + 1 raíz), la fila testigo (`2812|1795349854081043900|9a6edec4…`), el
  progreso (`página 3`, `reading`), la ficha («Continuar (pág. 3)») y el lector
  (`data-pagina="3"`, página 3 `5dea59a8…`). T1 montó R1 (la raíz de biblioteca del ensayo): V-03 es
  sobre el catálogo restaurado y su estado; la copia de archivos a D1 ya se acreditó en la pasada 1.
  Evidencia: [`evidencia/pasada2/t1-arranque.txt`](evidencia/pasada2/t1-arranque.txt) y
  [`evidencia/pasada2/versiones-t1.txt`](evidencia/pasada2/versiones-t1.txt).

### N-01 desde la interfaz (PASS de ensayo; `N-01-systemd-host` NOT RUN)

- Flujo real: la app (cliente `services/ops_host.py`) envía la petición firmada al socket; el
  auxiliar `deploy/ops/zascarr_ops.py` real valida esquema, firma HMAC, caducidad, topes, cerrojo y
  contraseña (PBKDF2) y **acepta**; se ejecuta el wrapper real `restaurar-produccion.sh` y el script
  real `restaurar_datos.sh --produccion`, que rechaza.
- Obtenido: confirmación de la interfaz 200; POST 200 «Restauración en marcha»; resultado
  `fallida / copia_no_valida / sha256_copia`, `base_en_su_sitio=true`; la persona ve en Estado
  **«Esa copia está dañada, así que no se ha usado. Elige otra.»**; antes/después idénticos (base,
  B0', `copias.json`, testigo, progreso, contenedores); el script no genera eventos de contenedor
  (los 2 crudos son la verificación de contraseña del auxiliar, `psql` de solo lectura).
- **Limitación documentada:** el host aislado no tiene systemd/root, así que el arnés sustituye tres
  costuras: `systemctl` por un lanzador que ejecuta el wrapper; el nombre del contenedor del
  verificador `zascarr-db` por `zascarr-a6-db`; y la lista de copias (el auxiliar real exige ficheros
  de root) por la lista del ensayo. **No** se sustituyen la app, el socket, la firma, el auxiliar
  (`procesar`/`EstadoOps`/PBKDF2), el wrapper ni el script. Evidencia:
  [`evidencia/pasada2/n01-ui-resumen.txt`](evidencia/pasada2/n01-ui-resumen.txt).
- `N-01-systemd-host` (arranque real de la unidad `zascarr-restaurar@…`): **NOT RUN**
  (`motivo=sin_root_systemd`).

## Anexo UAT-31 (UATP-08) — pasada 3: ejecución real (FAIL parcial)

Ejecución de **UAT-31** sobre la rama `feat/uatp08-momento-recuperacion` (SHA `a6849c2cd5c31e0d192c79fff66b45c3f13eddff`), tag
anotado **`uat-candidata-20261122b`**. Entorno E-UAT31 aislado (proyecto `zascarr-uat31`, puertos
15432/18000, sin Pi ni datos reales). Semilla 2/2/2, B0 `backup-20261122_172016` y **una fila añadida
después de la copia** (una `series`), de modo que antes de restaurar hay 3/2/2.

| Comprobación | Resultado | Evidencia |
|---|---|---|
| A. El resumen explica que la fila añadida queda fuera (`recuentos_previos`/`fuera`) | **PASS**: «Antes de restaurar había 3 series, 2 números y 2 archivos anotados. Esta copia trae 2, 2 y 2…» y «Quedan fuera 1 series, 0 números y 0 archivos…» | [`uat31/uat31-resultado.txt`](evidencia/uat31/uat31-resultado.txt) |
| B. Versión que arrancó | **FAIL**: la UI dice «Versión no consta.» aunque `ops-restaurar.json` lleva `version_arrancada={"version":"1.15.1","build_sha":"a6849c2cd5c31e0d192c79fff66b45c3f13eddff"}`; en la identidad solo se pinta `build=…` y `app=no consta` | [`uat31/defecto-version.txt`](evidencia/uat31/defecto-version.txt) |
| C. Comprobaciones | **PASS**: 14 comprobaciones visibles (`existencia_copia`…`health`; `codigo_manifest` = `no_ejecutada`) | [`uat31/comprobaciones-uat31.txt`](evidencia/uat31/comprobaciones-uat31.txt) |
| D. Captura de navegador | **PASS**: Chrome real a 1280×1100 y 390×844 (resumen con detalles abiertos) y confirmación previa | [`uat31/capturas/`](evidencia/uat31/capturas/) |
| E. Soporte (13.10 1/2/4) | **PASS**: `/api/health` publica `build_sha`; resumen `no-store`; lista «Versión 1.15.1 · revisión 0052» y «Las horas son del servidor»; confirmación con fecha absoluta y alcance | [`uat31/lista-y-confirmacion.txt`](evidencia/uat31/lista-y-confirmacion.txt) |

**Resultado:** **UAT-31 FAIL parcial**; UATP-08 **no acreditable** hasta corregir B. El defecto es
una discrepancia de forma: `scripts/restaurar_datos.sh::leer_version_arrancada` escribe
`{version, build_sha}`, mientras `src/zascarr/services/ops_host.py::_version_copia`/`version_llana`
esperan `{head, build_sha, app_version, alembic}`; la prueba `tests/test_web_uatp08.py` usa una
forma sintética con `app_version` y no cubre la real. La suite de la rama da **46 passed** y no lo
detecta. **No se corrige código en esta tarea de evidencia.** No se fabrica PASS.

![Resumen UAT-31 con la fila fuera y la versión no consta](evidencia/uat31/capturas/resumen-detalles-escritorio.png)

## Enlaces

- Issues: [#1144](https://github.com/juanajok/zascarr/issues/1144), [#1145](https://github.com/juanajok/zascarr/issues/1145), [#1141](https://github.com/juanajok/zascarr/issues/1141).
- Especificación: [`docs/design/uatp06-07-recuperacion.md`](../../design/uatp06-07-recuperacion.md).
- Runbook E2E: [`docs/TESTING_E2E.md` §17](../../TESTING_E2E.md).
- Pruebas PG del flujo: [`tests/test_restaurar_produccion_pg.py`](../../../tests/test_restaurar_produccion_pg.py).
- Evidencia: [`evidencia/resultado.txt`](evidencia/resultado.txt), [`evidencia/versiones.txt`](evidencia/versiones.txt),
  [`evidencia/comandos.txt`](evidencia/comandos.txt), [`evidencia/instantaneas.json`](evidencia/instantaneas.json),
  [`evidencia/copia-archivos.txt`](evidencia/copia-archivos.txt), [`fixture/`](fixture/).
