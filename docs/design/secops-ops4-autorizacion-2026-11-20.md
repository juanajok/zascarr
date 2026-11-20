# SecOps — Revisión adversarial de la autorización app→host de OPS4 (#443)

**Rol:** SecOps · **Fase:** revisión adversarial de solo lectura del trabajo del desarrollador
**Fecha:** 2026-11-20 (Europe/Madrid)
**Worktree:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443` (rama `feat/ops4-seguridad-443`,
`HEAD = 55baba8767779fa98ac40b0974a307cd412f34f5`).
**Objeto revisado:** árbol **sin commitear** sobre ese HEAD — 6 ficheros modificados
(`deploy/ops/registro_repeticiones_ops4.py`, `deploy/ops/verificador_autorizacion_ops4.py`,
`src/zascarr/services/autorizacion_actualizacion.py`, y 3 de tests) y 3 nuevos
(`docs/design/benchmark-ops4-autorizacion.md`, `docs/design/especificacion-ops4-autorizacion.md`,
`tests/test_ops4_autorizacion_compuesta.py`). No existe SHA final: los hashes del snapshot están en §7.
**Entorno:** `PYTHONPATH=.:src` con el venv de pruebas del repo (Python 3.14, pytest 9.2, ruff 0.17.5).
La imagen de producción es `python:3.11-slim-trixie` (`Dockerfile:16,29`) y `pyproject.toml:5` exige
`>=3.11`. Sin `TEST_DATABASE_URL`.
**Restricciones respetadas:** no se editó código, UI, auxiliar, unidad ni instalador; no se hicieron
commits ni push; no se ejecutó Docker, VM, Pi, systemd instalado, socket real, `update.sh` ni se tocaron
datos reales. **El único fichero escrito es este informe.** La actualización sigue **DESHABILITADA**.

---

## 0. Veredicto

1. **Fusión del contrato aislado tal como está (función deshabilitada): FAVORABLE CON CONDICIONES.**
   No hay bloqueantes ni defectos de seguridad explotables hoy: la composición y el verificador **no se
   importan desde web, API, `main.py`, auxiliar, instalador ni unidad**, no hay ruta, transporte, unidad
   ni `update.sh` conectado, y la UI conserva un único botón `disabled`. Las condiciones C-1…C-6 de §5.1
   deben cumplirse **en el mismo cambio o antes de fusionarlo** (sobre todo C-1, documentación del
   contrato, y C-2/C-3, endurecimiento trivial y barrera de aislamiento).
2. **Integrar/habilitar la ruta app→host (conectar UI, auxiliar, unidad, transporte, clave): NO-GO en
   este estado.** Bloqueada por M-1 (clave dedicada no exigible y sin provisión/rotación), M-2 (directorio
   durable no acreditado ni separado de `vistos`) y M-3 (transporte, envío único y ligadura real sin
   implementar), además de las condiciones I-1…I-9 de §5.2. Es coherente con la puerta de la propia SPEC
   (§12.3) y con `docs/design/ops4-estado-bloqueo-2026-11-20.md`.
3. **§5.8 (CLAUDE.md) — pasada final de seguridad:** aplicable por el espíritu de la regla (el cambio
   compone y consume «qué exige la contraseña actual» vía `services/reautenticacion.py`, aunque no
   modifique ese fichero). **Este dictamen es de un árbol sin commitear y no puede valer como dictamen
   del SHA final.** Cualquier commit/rebase posterior exige repetir esta revisión sobre el SHA exacto que
   se fusione (C-6).

**Ningún hallazgo crítico. Ningún bypass explotable por la superficie actual**, porque no existe
superficie: nada del contrato está conectado. Los hallazgos mayores bloquean la integración, no la
fusión del contrato aislado.

---

## 1. Qué se ha revisado

- Diff completo de los 6 ficheros modificados (`git diff`, incluido `--check`: sin problemas de
  espacios) y los 3 ficheros nuevos íntegros.
- SPEC (`docs/design/especificacion-ops4-autorizacion.md`), benchmark
  (`docs/design/benchmark-ops4-autorizacion.md`) y documentos de decisión pendientes
  (`ops4-autorizacion-app-host.md`, `ops4-concordancia-seguridad.md`,
  `ops4-registro-repeticiones.md`, `ops4-especificacion-main.md`) solo como contraste de contrato.
- Código de alrededor: `services/reautenticacion.py`, `services/auth.py`,
  `services/solicitud_actualizacion.py`, `services/ops_host.py`, `deploy/ops/zascarr_ops.py`
  (`UNIDADES`, `EstadoOps.marcar_visto`/`purgar_vistos`), `scripts/instalar_ops.sh`,
  `scripts/backup.sh`, `estado.html`, `pyproject.toml`, `Dockerfile` y `.github/workflows/ci.yml`.
- Pruebas focalizadas y Ruff (§6). **No** se repitió la suite completa (instrucción de la tarea; no es
  evidencia de ella).
- No se ha ejecutado nada fuera de pytest/Ruff locales.
- **Nota de concurrencia:** durante esta revisión aparecieron en el mismo worktree
  `docs/design/qa-ops4-autorizacion-2026-11-20.md` y `docs/design/ui-ops4-autorizacion-2026-11-20.md`
  (informes de otras revisiones de la fase). No forman parte de este dictamen, no se han usado como
  evidencia y no se han tocado; el snapshot de código y pruebas que se dictamina es el de §7.

---

## 2. Verificación por criterio del encargo

| Eje | Resultado | Evidencia / matiz |
|---|---|---|
| **Clave dedicada vs grupo** | **PARCIAL — hallazgo M-1** | La composición recibe `clave` como argumento y solo exige `bytes` de 32; el emisor puro no lee ficheros, no usa `ops_key_file` ni `ops.key` (`autorizacion_actualizacion.py:96,178`). Pero nada impide que el **futuro llamador** pase los bytes de `ops.key`, que es `0440 root:<grupo>` (`scripts/instalar_ops.sh:180-184`) y que la app ya lee (`services/ops_host.py:141,165`; `solicitud_actualizacion.py:120`). El test actual solo busca literales en el módulo del emisor (`test_ops4_aislamiento.py:168-172`), no en el futuro llamador. |
| **Dominio y rotación** | **PASS dominio / NOT RUN rotación** | Dominio propio `zascarr-ops4-autorizacion-v1\n` en emisor y verificador (`:43`/`:26`), distinto del v3 (`zascarr-ops/actualizar/v3\x00`) y de la firma textual v1/v2 del auxiliar (`zascarr_ops.py:116-124`). La rotación (sustituir clave, testigos viejos inválidos, sin `kid`) no está implementada ni probada; el módulo no cachea clave, así que una lectura por emisión futura la haría efectiva (condición I-1). |
| **Composición reauth** | **PASS con doble / NOT RUN servicio real (m-3)** | Orden correcto y fail-closed (`autorizacion_actualizacion.py:142-197`): puerta → confirmación → forma de contraseña → `auth_mode` → **una** llamada a `comprobar_contrasena_actual` → clave/ID/emisión. `INCORRECTA`/`OCUPADA`/`BLOQUEADA`/excepción/valor no esperado/`None` → código cerrado sin leer clave, sin ID y sin emitir. Pruebas de composición con doble (`tests/test_ops4_autorizacion_compuesta.py:110-245`). La llamada contra el servicio **real** no se ejercita. |
| **Replay / consumo durable** | **PASS mecánica / integración pendiente (M-2)** | `_reclamar_marca` usa `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, modo `0600`, dos `fsync` (fichero y directorio) y no borra la marca si falla la sincronización (`registro_repeticiones_ops4.py:48-93`). Namespace propio `autorizacion-<id>` (`:32-35,96-115`). 6 subprocesos → exactamente una `aceptada` (`test_ops4_autorizacion_compuesta.py:481-521`); reapertura y fallo de registro → `REPETIDA`/`NO_DISPONIBLE`. Falta acreditar directorio dedicado/persistente/propietario y la separación real de `vistos` (M-2). |
| **Ligadura de ID** | **PASS en función / bypass de borde (m-1) / transporte NOT RUN (M-3)** | `id_esperado` pasa a **obligatorio** en la función aislada (`verificador_autorizacion_ops4.py:50-56,96-101`); si falta, no es 32 hex o no coincide ⇒ `INVALIDA` y **sin consumo**. Se comprueba antes de la ventana y del callback. El testigo no sustituye el ID de la petición. Falta el mensaje v4 y la garantía de que el ID de la petición parseada sea el `id_esperado` (M-3). |
| **Errores fail-closed** | **PASS** | Clave/reloj malos ⇒ `NO_DISPONIBLE`; token inválido/caducado ⇒ `INVALIDA`/`CADUCADA`; callback que lanza ⇒ `NO_DISPONIBLE`; callback distinto de `True` ⇒ `REPETIDA`; registro no fiable ⇒ `NO_DISPONIBLE` sin aceptar (`verificador_autorizacion_ops4.py:67-121`; `registro_repeticiones_ops4.py:74-84`). Composición: excepciones y resultados inesperados ⇒ `NO_DISPONIBLE`; sin emisión parcial. |
| **Tokens y secretos en logs** | **PASS (con residual del llamador)** | El emisor no registra nada: ni `logging`/`logger`/`print` en el módulo (`test_ops4_aislamiento.py:168-172`); `PreparacionAutorizacion.autorizacion` tiene `repr=False` (`autorizacion_actualizacion.py:64-74`) y el test comprueba que el token y la contraseña no aparecen en `repr`/`str` (`test_ops4_autorizacion_compuesta.py:323-329`). El testigo no contiene `prueba`/`password`/`pbkdf2`; el verificador no devuelve token ni datos. Residual no exigible al contrato: un futuro llamador podría registrar `.autorizacion`; condición I-3/I-7. |
| **Python / StrEnum** | **PASS** | `from enum import StrEnum` ya se usaba en el verificador (`:21,33`) y en `services/reautenticacion.py:35`; `requires-python >=3.11` (`pyproject.toml:5`), imagen 3.11 (`Dockerfile:16,29`), objetivo Ruff `py311` (`pyproject.toml:51`). Sin dependencias nuevas (stdlib). `ruff check --select S src/zascarr/services/autorizacion_actualizacion.py` pasa (regla de bandit de CI, `.github/workflows/ci.yml:130-133`). |
| **UI/auxiliar/`main.py`/unidad deshabilitados** | **PASS** | Ver §3. La actualización sigue sin superficie: solo botón `disabled` y texto «aún no está disponible» (`estado.html:14-17`), `UNIDADES` sin `actualizar` (`zascarr_ops.py:42-45`), sin unidad de actualización (`deploy/systemd/`), `scripts/update.sh` preexistente (`a93f437d`) y sin modificar ni ejecutar. |
| **Pruebas y lint** | **PASS focalizado** | 164 pruebas OPS4/aislamiento/UI focalizadas verdes; 974 de todo el conjunto OPS/OPS4/paridad verdes; Ruff del cambio y bandit-S verdes (§6). Suite completa: **NOT RUN** por instrucción. |

---

## 3. Estado de «deshabilitado» verificado

- **Árbol:** `git status --short` solo muestra los 6 modificados y 3 nuevos del contrato/documentación/
  pruebas. **No** cambian `config.py`, `docker-compose.yml`, `Dockerfile`, `deploy/systemd/**`,
  `scripts/**` ni plantillas.
- **Sin imports desde runtime:** búsqueda de `autorizacion_actualizacion`, `preparar_autorizacion`,
  `verificador_autorizacion_ops4`, `registro_repeticiones_ops4` en `src/`, `deploy/` y `scripts/`
  (excluidos los propios módulos y tests): **sin resultados**. `services/__init__.py` está vacío.
- **UI:** `estado.html:14-17` con `<section id="actualizacion">`, un solo botón
  `type="button" disabled`, sin `form`, `hx-*`, `script`, enlace ni POST; lo prueba
  `tests/test_ops4_ui_deshabilitada.py` (incluido en las 164/974 verdes).
- **Auxiliar:** `UNIDADES` solo `copia` y `restaurar`; `actualizar` no existe. `tests/test_ops_paridad.py`
  y el conjunto OPS verdes.
- **Unidad e instalador:** no hay unidad de actualización; `scripts/instalar_ops.sh` no se modifica y no
  menciona el registro de autorización (test `test_el_registro_de_autorizacion_no_se_conecta...`).
  `update.sh` existe en el árbol desde `a93f437d`, no se ha modificado ni ejecutado.
- **Observación:** `estado.html` sigue siendo el único punto de UI; la barrera estática no impide que un
  futuro commit la conecte, pero hoy no hay ruta ni import.

---

## 4. Hallazgos por criticidad

### 4.1 Bloqueantes para la fusión del contrato aislado

**Ninguno.** Con la función deshabilitada y sin imports desde runtime, el cambio es código y pruebas
aisladas. Las condiciones C-1…C-6 de §5.1 son requisitos de calidad/contrato antes de fusionar, no
defectos explotables.

### 4.2 Mayores — bloquean la integración/habilitación de la ruta app→host

#### M-1 — La clave dedicada no es exigible; provisión, grupo y rotación pendientes

- **Qué:** `preparar_autorizacion` acepta cualquier `bytes` de 32 (`autorizacion_actualizacion.py:178`).
  El emisor puro no usa `ops.key` ni lee ficheros (correcto), pero la garantía «clave dedicada» descansa
  **solo en el futuro llamador**. Hoy la app ya lee `ops.key` para OPS1/OPS2
  (`services/ops_host.py:72,141,165`; `solicitud_actualizacion.py:120`) y ese fichero es
  `0440 root:<grupo>` (`scripts/instalar_ops.sh:180-184`). Si el llamador de integración reutiliza
  `ops_key_file` (32 bytes) la composición emitiría sin quejarse; el prefijo de dominio evita
  reutilizar firmas de otros protocolos, **no** convierte una clave de grupo en prueba de reautenticación.
- **Impacto:** un proceso del grupo con lectura de `ops.key` podría forjar testigos de actualización
  (el host seguiría aplicando sus guardas, pero la autoridad de reautenticación quedaría anulada). Es el
  riesgo residual que la decisión del PO acepta solo con clave dedicada y permisos mínimos.
- **Evidencia:** grep sin `ops_key_file` en el módulo (test `:168-172`), pero el test no cubre al
  llamador ni el origen de la clave; no existe `OPS4_AUTORIZACION_KEY_FILE` ni provisión
  (`docs/design/ops4-autorizacion-app-host.md` §«Clave» y §«Pendiente para integrar» 1).
- **Condición:** I-1. Antes de conectar: clave de 32 bytes `secrets` propia, fichero `root:grupo-dedicado`
  `0440` (o permisos mínimos app+host), lectura `O_RDONLY|O_NOFOLLOW` en `asyncio.to_thread`, rotación y
  revocación probadas, exclusión de backups/restauración, y un test que acredite que la ruta de
  autorización **nunca** lee `settings.ops_key_file`. Alternativa aceptable: derivar una subclave
  etiquetada con `hkdf`/HMAC de dominio **solo si** el PO lo decide; hoy no está y no se presume.

#### M-2 — El consumo durable no acredita directorio propio, persistente ni ajeno a `vistos`

- **Qué:** `crear_reclamador_durable(directorio_fd)` recibe un descriptor de confianza y
  `_reclamar_marca` solo comprueba que sea directorio y que no tenga escritura de grupo/otros
  (`registro_repeticiones_ops4.py:55-63`). **No** comprueba propietario `root`, modo `0700` exacto, que
  no sea tmpfs/`/run` ni que no sea el directorio `vistos` del auxiliar; su docstring lo delega al
  llamador (`:141-147`, y `docs/design/ops4-registro-repeticiones.md` §«Límites antes de integrar»).
- **Por qué importa el prefijo no basta:** `EstadoOps.purgar_vistos` (`zascarr_ops.py:229-243`) borra
  toda entrada cuyo contenido no sea un entero (marca vacía ⇒ `anotado = 0` ⇒ `ahora - 0 > 300` ⇒
  `unlink`). Si el futuro llamador reutilizara el directorio de `vistos` (o un tmpfs), las marcas
  `autorizacion-<id>` vacías se purgarían o se perderían al reiniciar, **reabriendo el replay**; el test
  de prefijos en el mismo directorio (`tests/test_ops4_registro_repeticiones.py:279-290`) demuestra que
  no se satisfacen entre sí, pero **no** demuestra separación de directorio ni supervivencia a la purga.
- **Impacto:** replay dentro de la ventana del testigo si el cableado es incorrecto; hoy no hay cableado,
  por eso es bloqueante de integración y no de fusión.
- **Condición:** I-2. Directorio dedicado y persistente `root:root 0700` (nunca `/run`, nunca `vistos`),
  provisión idempotente, comprobación runtime al menos de propietario/modo y de que no es el directorio
  de `vistos` (p. ej. marcador de instalación propio o comprobación de dispositivo/FS), retención/cuota
  decididas (hoy marcas permanentes; disco lleno deniega, correcto), pruebas con `EstadoOps.purgar_vistos`
  real, reapertura y reinicio, y `ReadWritePaths` en la unidad futura.

#### M-3 — Transporte, envío único y ligadura real petición↔testigo sin implementar (NOT RUN)

- **Qué:** el contrato deja `id_esperado` obligatorio y devuelve el ID CSPRNG (`:184-196`), pero **no
  existe** mensaje v4, parseo único, envío único, ni retirada de la contraseña de la vía v3
  (`docs/design/especificacion-ops4-autorizacion.md:528-561,815-817`). Nada impide hoy que la futura app
  pase como `id_esperado` el ID que afirme el testigo en lugar del de la petición parseada.
- **Impacto:** sin transporte cerrado y envío único, el testigo no queda ligado de forma verificable a
  una sola petición autenticada; es el requisito central de la decisión (evitar replay y «booleano de la
  app»).
- **Condición:** I-3 (v4, un solo parseo, un solo envío, `id_esperado` del mensaje parseado, retirada de
  v3 con contraseña o rechazo explícito, reconciliación de resultado incierto; AC-AUT-16).

#### M-4 — Documentación del propio cambio desincronizada con el código

- **Qué:** el benchmark afirma «No hay composición … y nada lo importa» (`benchmark…:10`) y «38 casos»
  (`:15`); la SPEC se declara «especificación de contrato. No implementa» (`especificacion…:3-4`), deja
  Q-AUT-7 abierta («¿`id_esperado` … en la función aislada o solo en la integración?», `:842`) y dice
  que el registro «no se conecta en esta fase» (`:463-466`), cuando el diff **sí** añade composición,
  `id_esperado` obligatorio en la función y la API durable `crear_reclamador_durable`.
  El documento de decisión tracked dice «acepta **opcionalmente** un `id_esperado`»
  (`ops4-autorizacion-app-host.md:17-18`) y atribuye «38 tests» al fichero (`:77`), que hoy tiene 45.
  Además, los códigos que la SPEC §9.2 prescribe (`autorizacion_invalida`, `autorizacion_caducada`,
  `autorizacion_repetida`, `autorizacion_no_disponible`) no son los que devuelve
  `CodigoAutorizacion` (`invalida`, `caducada`, `repetida`, `no_disponible`,
  `verificador_autorizacion_ops4.py:33-38`).
- **Impacto:** no es un defecto de seguridad en ejecución, pero el contrato que se va a integrar queda
  ambiguo (códigos distintos en capas distintas, obligatoriedad de `id_esperado`, estado del componente);
  la trazabilidad y el dictamen del SHA final se apoyan en esos documentos.
- **Condición:** C-1. Reconciliar en el mismo cambio (o anotar expresamente): estado implementado pero
  desconectado; `id_esperado` obligatorio (Q-AUT-7 resuelta en la función aislada); recuentos; mapa de
  códigos SPEC §9.2 ↔ implementación; y corregir `ops4-especificacion-main.md` §3.2/AC-03 y
  `ops4-matriz-evidencia.md` en el cambio de integración. No se edita la SPEC histórica.

### 4.3 Menores (endurecimiento; no bloquean la fusión del contrato aislado)

#### m-1 — `id_esperado` puede burlarse con una subclase de `str`

- **Qué:** el verificador comprueba `isinstance(id_esperado, str)` y luego `datos["id"] != id_esperado`
  (`:96-101`). Una subclase de `str` que sobrescriba `__ne__`/`__eq__` pasa `_ID.fullmatch` (el contenido
  puede ser otro ID válido) y la desigualdad devuelve falso. **Sonda ejecutada en este entorno:** un
  `IdEsperadoFalso("b"*32)` con `__ne__ → False` sobre un testigo de `id="a"*32` devuelve
  `CodigoAutorizacion.ACEPTADA`.
- **Alcance:** no es explotable desde JSON (el parser produce `str` plano) ni desde la superficie actual
  (no hay llamador); sí es una debilidad del contrato si el llamador llegara a pasar un objeto no
  confiable. Endurecimiento barato: `type(id_esperado) is str` y comparar con
  `hmac.compare_digest(datos["id"].encode(), id_esperado.encode())` (o `datos["id"] == str.__str__(id_esperado)`).
  Añadir test con subclase hostil.
- **Condición:** C-2.

#### m-2 — El verificador no comprueba propietario/modo del directorio durable

- Ya cubierto en M-2; se anota aparte por claridad: `st_mode & 0o022` solo rechaza escritura de
  grupo/otros. Un directorio `0700` propiedad de un usuario no privilegiado pasaría el filtro y ese
  usuario podría borrar marcas (`fsync` no protege de un `unlink`). Endurecer con `st_uid == 0` (o UID
  esperado de la instalación) y `0700`, o con el marcador de instalación de I-2.

#### m-3 — La composición no se ejercita contra el servicio real de reautenticación

- El doble `ComprobarFalso` (`test_ops4_autorizacion_compuesta.py:41-52`) replica la forma
  `(str, Settings) -> Awaitable[ResultadoReauth]` y el binding por defecto
  (`autorizacion_actualizacion.py:16-18,126`) no se ejecuta en ninguna prueba. Si mañana cambia
  `services/reautenticacion.py`, la suite seguiría verde y la composición rompería en producción.
- **Condición:** C-4. Añadir una prueba de contrato que parchee `intentar_credenciales`
  (o `services.auth.credenciales_validas`) y llame a `preparar_autorizacion` **sin** doble `comprobar`,
  verificando `OK`→emite y `INCORRECTA`→no emite; o una comprobación de firma compatible de
  `comprobar_contrasena_actual`. Alternativa: mover el contrato de tipos a un `Protocol` compartido.

#### m-4 — Debilitamientos y puntos ciegos en las pruebas

- `test_campos_estrictos_sin_consumo` acepta `(INVALIDA, CADUCADA)`
  (`tests/test_ops4_autorizacion.py` diff) aunque **todas** las mutaciones de la tabla devuelven
  `INVALIDA` en la sonda de este entorno; la aserción exacta evitaría enmascarar un cambio de
  clasificación.
- `test_la_composicion_de_autorizacion_no_se_importa_desde_runtime` (`test_ops4_aislamiento.py:153-165`)
  solo escanea `src/zascarr/**`, `main.py`, el auxiliar e `instalar_ops.sh`; **no** `deploy/ops/**`
  (otros experimentos) ni el resto de `scripts/**`.
- `test_el_registro_de_autorizacion_no_vive_en_run_ni_en_vistos`
  (`tests/test_ops4_registro_repeticiones.py`) comprueba texto del **propio módulo**, no el cableado del
  llamador; combinado con M-2, una futura integración con `/run/…/vistos` pasaría todos los tests
  actuales.
- **Condición:** C-3/C-4. Ampliar la barrera estática y acreditar separación de directorio en la prueba
  de integración, no por búsqueda de literales.

#### m-5 — La puerta `habilitada` es un parámetro del llamador, no una configuración de producto

- `preparar_autorizacion(habilitada=False)` por defecto es correcto y el test lo fija
  (`test_la_funcion_esta_deshabilitada_por_defecto`), pero el único impedimento para habilitar es que un
  futuro endpoint pase `habilitada=True`. Recomendación de integración: derivar la puerta de **una** flag
  de config/UI con default deshabilitado y añadir una prueba estática de que ninguna ruta runtime pasa
  `habilitada=True` sin la puerta. No requiere cambio ahora (nada lo llama).

### 4.4 Observaciones y riesgos residuales (documentados o NOT RUN)

- **O-1 — Reloj/NTP y TTL:** `creada` sale de `time.time()` de la app y la tolerancia es ±120 s
  (`autorizacion_actualizacion.py:186`; `verificador…:111`). Q-AUT-3 sigue abierta: validar NTP y decidir
  60 s/300 s. Reloj retrocedido degrada retención y ventana (SPEC §14.1-4).
- **O-2 — Retención/cuota/poda:** marcas permanentes; disco lleno deniega (correcto); sin política de
  poda segura (Q-AUT-4). No podar por reloj de pared sin ancla monotónica.
- **O-3 — Tope de emisiones y auditoría:** no hay tope de emisiones por sesión/intento (Q-AUT-8) ni
  observable de auditoría de emisiones; el host anota el consumo, no la autorización concedida. No es
  bloqueante; decidir en integración.
- **O-4 — Identidad/rotación/época:** sin `kid` ni ligadura explícita a build/instalación (la clave por
  instalación es la ligadura implícita); Q-AUT-5 (época/fencing) y Q-AUT-6 (formato v2) sin decidir.
- **O-5 — Entorno de pruebas:** `pytest` usó el `tmp_path` por defecto sobre `/tmp`, que en esta máquina
  es **tmpfs** (`/` es ext4 en solo lectura), así que la convención de CLAUDE.md §8 de `--basetemp` en el
  mismo dispositivo que `/` no se pudo cumplir aquí. Las pruebas del registro acreditan la mecánica
  (`O_EXCL` + dos `fsync` + reapertura + procesos), **no** persistencia ante corte eléctrico ni en el
  dispositivo de la Pi: eso es NOT RUN y así se declara en `ops4-registro-repeticiones.md`.
  El venv de pruebas es Python 3.14 y la imagen 3.11: compatibilidad comprobada por `StrEnum` (3.11+) y
  `pyproject`/Dockerfile; aun así, la integración debe ejecutar su suite completa en 3.11.
- **O-6 — Secretos en el testigo:** el formato no incluye contraseña/hash/usuario/`prueba`; la sonda de
  tests lo comprueba. Residual: el llamador no debe registrar `.autorizacion` ni `asdict()`; el `repr`
  ya lo oculta.

---

## 5. Condiciones

### 5.1 Para fusionar el contrato aislado (actualización deshabilitada)

- **C-1 (obligatoria) — Reconciliar documentación y contrato** (M-4): benchmark/SPEC/`ops4-autorizacion-app-host.md`
  deben reflejar el estado real (composición y API durable implementadas pero desconectadas;
  `id_esperado` obligatorio; Q-AUT-7 resuelta en la función aislada; recuentos 45/59; mapa de códigos
  SPEC §9.2 ↔ implementación) **en el mismo cambio** o con una nota explícita de que se corrige al
  integrar. No dejar dos contratos contradictorios.
- **C-2 — Endurecer `id_esperado`** (m-1): tipo exacto `str` y comparación en tiempo constante; test con
  subclase hostil.
- **C-3 — Ampliar la barrera de aislamiento** (m-4, M-1): escanear `deploy/ops/**` y `scripts/**`
  completos (excluidos los módulos del propio contrato) y prohibir que ninguna ruta runtime lea
  `ops_key_file` para autorización. Sin conectar nada: solo barrera.
- **C-4 — Pruebas de contrato y exactitud** (m-3, m-4): composición contra el servicio real con
  `intentar_credenciales` parcheado; aserciones exactas de código por causa; prueba de que la marca
  durable no se crea cuando se rechaza.
- **C-5 — No relajar la deshabilitación:** mantener `UNIDADES` sin `actualizar`, sin unidad, sin
  `update.sh` instalado/ejecutado, sin import desde runtime y con la UI `disabled`. El diff actual lo
  cumple; no introducir excepciones en el commit.
- **C-6 — Dictamen del SHA final (§5.8):** repetir esta pasada sobre el SHA exacto que se fusione
  (cualquier commit/rebase invalida este informe). Este informe es de un árbol sin commitear y no
  sustituye la regla de §5.8 ni la revisión QA.

### 5.2 Para integrar/habilitar la ruta app→host (además de C-1…C-6)

1. **I-1 — Clave dedicada** (M-1): provisión idempotente y permisos mínimos; grupo dedicado o
   `root:app` `0440`; lectura `O_NOFOLLOW` en hilo; rotación/revocación y testigos viejos inválidos;
   clave fuera de backups/restauración; prueba que acredite que **no** se lee `ops_key_file`; procedimiento
   documentado en instalador/ADR.
2. **I-2 — Consumo durable conectado** (M-2): directorio propio persistente `root:root 0700`, no `/run`
   ni `vistos`; verificación runtime de propietario/modo/dispositivo o marcador de instalación;
   retención/cuota decididas; pruebas con `EstadoOps.purgar_vistos`, reapertura, reinicio y procesos;
   `ReadWritePaths` en la unidad futura. Nunca borrar marcas para reabrir replay.
3. **I-3 — Transporte cerrado y envío único** (M-3): versión v4 (o equivalente) con un solo parseo y una
   sola petición; `id_esperado` = ID de la petición parseada (no el del testigo); contraseña retirada de
   la ruta y retirada/desactivación de v3 con prueba de rechazo; sin reintento con el mismo testigo ni
   reemisión silenciosa; resultado incierto reconciliado en el host (AC-AUT-16).
4. **I-4 — Guardas del host intactas:** instalación, rutas, propiedad, cerrojo, estado, unidad y fijación
   de `S` antes de cualquier efecto; la aceptación es de admisión, no de ejecución (AC-AUT-15).
5. **I-5 — Arnés aislado** (root/systemd/Docker/Postgres/VM desechables): casos que pytest no cubre;
   NOT RUN actual: unidad, cortes eléctricos, restauración de host, Pi.
6. **I-6 — Reloj/TTL/abuso:** NTP validado, decisión 60 s/300 s y tolerancia, tope de emisiones (Q-AUT-8),
   auditoría/observable de emisión y decisiones de época/identidad (Q-AUT-5/6) o su descarte expreso.
7. **I-7 — UI/UX:** confirmación, textos llanos sin códigos ni «token», y que la contraseña no se refleje
   en un 422 (Q-AUT-9). El botón sigue deshabilitado hasta todo lo anterior.
8. **I-8 — Evidencia y ADR:** suite completa verde en Python 3.11, paridad v1/v2, Ruff (incl. `--select S`),
   corrección de `ops4-especificacion-main.md` §3.2/AC-03 y `ops4-matriz-evidencia.md`, y ADR de
   autorización app→host (ampliación de ADR 0021 o nuevo).
9. **I-9 — Autorización explícita del PO** y separada: solo entonces se plantea conectar UI, auxiliar,
   unidad e instalador. Nada de Pi, Docker de producción, systemd instalado ni datos reales sin ella.

---

## 6. Pruebas y lint ejecutados (evidencia)

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443

# Focalizado (autorización, composición, registro, aislamiento, UI deshabilitada)
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest \
  tests/test_ops4_autorizacion.py tests/test_ops4_autorizacion_compuesta.py \
  tests/test_ops4_registro_repeticiones.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_ui_deshabilitada.py -q
# → 164 passed in 4.11s

# Conjunto OPS/OPS4/paridad (sin suite completa)
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest \
  tests/test_ops4_*.py tests/test_ops_paridad.py tests/test_ops_auxiliar.py \
  tests/test_ops_auxiliar_endurecimiento.py tests/test_copias_ops.py tests/test_instalar_ops.py \
  tests/test_restauracion_ops2.py -q
# → 974 passed in 19.43s

# Recuento de casos
# test_ops4_autorizacion.py     → 45 tests
# test_ops4_autorizacion_compuesta.py → 59 tests
# test_ops4_registro_repeticiones.py  → 37 tests

/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/ruff check \
  deploy/ops/verificador_autorizacion_ops4.py deploy/ops/registro_repeticiones_ops4.py \
  src/zascarr/services/autorizacion_actualizacion.py tests/test_ops4_autorizacion.py \
  tests/test_ops4_autorizacion_compuesta.py tests/test_ops4_registro_repeticiones.py \
  tests/test_ops4_aislamiento.py
# → All checks passed!

/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/ruff check --select S \
  src/zascarr/services/autorizacion_actualizacion.py
# → All checks passed!   (regla de bandit del CI)
```

**No ejecutado (NOT RUN):** suite completa, `TEST_DATABASE_URL`, Docker de producción, host/VM, Pi,
systemd instalado, socket del auxiliar, `update.sh`, cortes eléctricos, restauración de host y extremo a
extremo app→host. No se han usado datos reales. `git diff --check` limpio. La ejecución de pytest genera
`__pycache__` ignorados por git; no se ha añadido ningún otro fichero al árbol.

---

## 7. Hashes del snapshot revisado

`HEAD` = `55baba8767779fa98ac40b0974a307cd412f34f5` (`feat/ops4-seguridad-443`).

| Fichero | SHA-256 |
|---|---|
| `git diff` completo (6 modificados) | `4d901321b5bcd33f79b0606663859df91a99fe2ed9beef093fa79155705f6c03` |
| `src/zascarr/services/autorizacion_actualizacion.py` | `78e638e1bbdbb22ac83d0a2c65e0914359d0ccfa32d2b9d53379fb9125abff14` |
| `deploy/ops/verificador_autorizacion_ops4.py` | `bd0a653bdc95437e47f2802213d13c700090d3617e8e2a9d206a85216188d629` |
| `deploy/ops/registro_repeticiones_ops4.py` | `d68ba8fccd11630361b7139fa40def50f1a0b0dd1b90785ed6332d1c5398c191` |
| `tests/test_ops4_autorizacion_compuesta.py` (nuevo) | `7b3de1a10176c4e3f70c27f69611638701cf11c98627b11bd975ce32b81ba887` |
| `docs/design/especificacion-ops4-autorizacion.md` (nuevo) | `9b12b9b20a485c5213733b0a2a6ad4b31b2f9dba788f1195f9e8ff5212584aad` |
| `docs/design/benchmark-ops4-autorizacion.md` (nuevo) | `a3302f3afa74a44e7ccdbd1b3864c2b4a044b2086fafb873e5fa696c8698bdb1` |

(El `git diff` no incluye los ficheros nuevos; sus hashes van aparte.)

---

## 8. Vigencia

- **Vigente para el snapshot de §7** y solo con la función deshabilitada. **Caduca** al primer commit,
  rebase o cambio de cualquiera de esos ficheros; §5.8 exige repetir el dictamen sobre el SHA final.
- **Caducidad ordinaria:** 2027-01-19 (~60 días), o antes si cambia la decisión, el formato del testigo,
  la clave, el protocolo de transporte o el registro durable.
- **Resumen para el PO:** el contrato aislado está bien construido y las salvaguardas de «deshabilitado»
  se mantienen; **no se habilite** hasta cumplir I-1…I-9. Fusionar el contrato con las condiciones
  C-1…C-6 es aceptable desde SecOps.
