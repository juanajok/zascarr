# Benchmark — OPS4: autorización app→host para actualizar (#443)

> **Snapshot previo a la fase de desarrollo (55baba87).** Los recuentos de tests de este documento son los de entonces; el estado final está en [QA](qa-ops4-autorizacion-2026-11-20.md) y en la matriz: 49 casos de contrato, 59 de composición, 791 OPS4/paridad y 8781 de suite completa.

> Ficha de [benchmark-referencias.md](benchmark-referencias.md) (CLAUDE.md §13), **nivel 2** por tocar seguridad y autenticación. Base: rama `feat/ops4-seguridad-443`, commit `55baba87`, 2026-11-20. Es **insumo, no aprobación**: el PO ya eligió la autoridad el 2026-11-20. No edita código ni habilita OPS4; la actualización sigue deshabilitada en UI, auxiliar, `main.py` y unidad, y `update.sh` no se instaló ni se ejecutó.

## 1. Historia / problema observado

- **Historia #443 B:** pedir desde la UI una actualización a `main` con migraciones, sin aprobación por SHA; la función permanece deshabilitada hasta cumplir las puertas de [ops4-especificacion-main.md](ops4-especificacion-main.md#L68-L73).
- **Decisión vigente (2026-11-20):** la app reautentica la contraseña actual y emite una autorización corta de un solo uso; el host **no** vuelve a leer el hash de la BD para esta comprobación ([ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L3-L7), [ops4-concordancia-seguridad.md](ops4-concordancia-seguridad.md#L5-L8)).
- **Problema que cierra:** una coincidencia de hash no acredita la configuración efectiva de la app; overrides de `runtime_settings`, publicación en memoria antes del commit, recuperación CLI y restauración generan divergencias ([ops4-concordancia-seguridad.md](ops4-concordancia-seguridad.md#L26-L50)).
- **Código vigente:** el emisor construye `cuerpo.firma_hex` con HMAC-SHA256 y dominio `zascarr-ops4-autorizacion-v1`, sin contraseña/hash/usuario ([autorizacion_actualizacion.py](../../src/zascarr/services/autorizacion_actualizacion.py#L15-L20)); el verificador comprueba esquema cerrado, acción, ID de 32 hex, ventana 1–300 s, tolerancia de 120 s y consumo por callback ([verificador_autorizacion_ops4.py](../../deploy/ops/verificador_autorizacion_ops4.py#L45-L110)). **No hay composición del emisor con reautenticación** y nada lo importa desde web, API, `main` ni auxiliar ([test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py#L129-L149)).
- **Resultado deseado:** el host acepta solo un testigo emitido tras `Reauth.OK`, de un uso, con vida de minutos y ligado a petición y operación; sin recibir la contraseña; sin que el testigo sustituya las guardas de instalación, cerrojo, estado y unidad.

## 2. Datos reales y medición de partida

- **Contrato aislado:** hoy coleccionan **38 casos** en `tests/test_ops4_autorizacion.py` (comprobado con `--collect-only`); la ficha [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L77-L79) dice 38 y la [matriz](ops4-matriz-evidencia.md#L37) dice 33: la matriz está desactualizada y debe corregirse antes de habilitar.
- **Suite y medición:** el árbol declara 710 pruebas OPS4/paridad verdes y una suite completa previa de 8660 passed/2431 skipped ([ops4-matriz-evidencia.md](ops4-matriz-evidencia.md#L11)); no se repitió aquí porque esta fase no cambia comportamiento. No se ejecutó la actualización, ni host, ni Pi, ni competidores: sin latencia, carga ni durabilidad medidas.

## 3. Referencias consultadas

- **Locales:** [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md) (decisión, límites y pendientes), [ops4-concordancia-seguridad.md](ops4-concordancia-seguridad.md) (divergencias app/BD), [ops4-especificacion-main.md](ops4-especificacion-main.md) (puertas y requisitos), [ops4-registro-repeticiones.md](ops4-registro-repeticiones.md) (consumo durable), [ops4-propuesta-epoca.md](ops4-propuesta-epoca.md) (fencing), [ops4-verificacion-contrasena.md](ops4-verificacion-contrasena.md) (límites del PBKDF2 del host), [especificacion-BL-OPS2.md](especificacion-BL-OPS2.md#L95-L107) (patrón opuesto: reauth en app + hash en host) y [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md#L21-L27) (socket, `ops.key` y grupo).
- **Producto:** [benchmark-referencias.md](benchmark-referencias.md#L127-L134) remite a Sonarr/Radarr para operación y Kapowarr para ficheros; sus fichas locales citan commits (Sonarr `a8a82905e7` y Kapowarr `c191dda661`, [benchmark-A11-exposicion.md](benchmark-A11-exposicion.md#L25-L26)) pero **solo documentan autenticación de UI y defaults, no un actualizador app→host con reautenticación**; no se infiere soporte ni ausencia. El `X-Api-Key` estático de Prowlarr ([ficha local](benchmark-busqueda-deseados-prowlarr-2026-11-11.md#L40)) es contraejemplo de capability estática, no de este patrón.
- **Externa:** OWASP Authentication Cheat Sheet, «Require Re-authentication for Sensitive Features», <https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html> (consultada 2026-11-20): exige la credencial actual antes de operaciones sensibles; no prescribe el mecanismo app→host.

## 4. Cómo lo resuelve cada alternativa («autorización firmada» = aprobador externo, no el testigo de la app)

| Mecanismo | Aporta | Límite aquí | Veredicto |
|---|---|---|---|
| **App reautentica y emite autorización HMAC corta de un uso** (elegido) | No expone la contraseña; no depende del hash de la BD; frescura, acción e ID verificables; un solo uso | Confía en la app y en su clave; exige composición real, consumo durable y transporte | **Adoptar** con las condiciones de §§6–9 |
| **Verificación de hash en el host** (patrón OPS2) | El host no cree un booleano de la app; límites/bloqueo propios | Divergencia de fuentes ya auditada; nuevo poder de leer la BD vía Docker; PBKDF2 duplicado; contraseña por el canal | **Descartar** como autoridad en OPS4; conservar en OPS2 |
| **Autorización firmada por un aprobador root** (`A` de C-12) | Separa la aprobación de código de la persona; resiste una app comprometida | Exige aprobación por SHA, retirada por el PO; no autentica a la persona ni sustituye la reauth | **Descartar** como puerta de esta política; adoptar su consumo durable/época como referencia |
| **Token de capacidad opaco** (bearer de un uso) | Simple; revocable si hay registro host; no comparte clave de firma | Sin firma no liga emisor, acción e instante; requiere emisión/almacén previos; interceptado vale | **Descartar** como sustituto; conservar la semántica de ID de un uso |
| **Reautenticación compartida** (solo app o con contraseña al host) | Un único contador/bloqueo y la misma UX de OPS3 | Solo app no prueba nada al host; reenviar la contraseña repite exposición y dependencia del hash | **Adoptar** como requisito previo en la app; **descartar** el reenvío en la ruta nueva |

## 5. Supuestos de las referencias que NO valen en ZascArr

- «Una coincidencia con el hash de PostgreSQL acredita la contraseña efectiva»: no, por las divergencias de configuración ya auditadas.
- «Un HMAC con `ops.key` acredita identidad o reautenticación»: no; acredita pertenencia al grupo del auxiliar, no que la app haya reautenticado ([ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md#L21-L27)).
- «La prueba de hilos demuestra exclusión entre procesos»: no; comparten proceso y no sustituyen un registro durable ([ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L42-L47)).
- «`fsync` exitoso certifica hardware o supervivencia a corte»: no; los tres cortes de QEMU son evidencia acotada, no pérdida eléctrica ([ops4-registro-repeticiones.md](ops4-registro-repeticiones.md#L108-L112)).
- «Basta una API key de larga vida, como la de los *arr»: no verificado y no equivalente: una clave de larga vida no aporta frescura, reauth ni un solo uso; las fichas locales solo cubren autenticación de UI.

## 6. Resultado por pieza: adoptar / adaptar / descartar

| Pieza | Veredicto | Condición o motivo |
|---|---|---|
| Autoridad de la app tras `comprobar_contrasena_actual` | **Adoptar** | Decisión del PO; falta la composición real y su prueba |
| Reautenticación compartida de OPS3 (retraso, bloqueo, cola) | **Adoptar** | Un solo contador para Ajustes/Restaurar/Actualizar; no es prueba para el host |
| Composición reauth→emitir solo con `Reauth.OK` | **Construir sobre lo propio** | Ya existe patrón y pruebas en [solicitud_actualizacion.py](../../src/zascarr/services/solicitud_actualizacion.py#L74-L128): reutilizar orden, manejo de `INCORRECTA`/`OCUPADA`/`BLOQUEADA`, ID con `secrets.token_hex(16)` y lectura de clave sin seguir enlaces |
| HMAC-SHA256 con prefijo de dominio, esquema cerrado y comparación en tiempo constante | **Adoptar** | Patrón de OPS1/OPS2; el token no lleva contraseña, hash ni usuario |
| Clave dedicada de 32 bytes (no `ops.key`) | **Adaptar** | `ops.key` es del grupo; provisión, permisos, rotación y separación de copias **no implementados** ([ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L56-L62)) |
| TTL de 60 s (máx. 300) y tolerancia de reloj de 120 s | **Adaptar** | Acota replay; validar reloj/NTP de la Pi y si 300 s es demasiado para la operación |
| ID de 32 hex + `id_esperado` ligado a petición y operación | **Adoptar con condición** | El emisor no genera el ID: el llamador debe usar CSPRNG y no reutilizarlo en otra acción |
| Consumo único por callback | **Adaptar a registro durable** | Hoy es un callback inyectado; debe usar el registro con `O_EXCL` + `fsync` antes de cualquier efecto |
| Registro durable del consumo | **Adoptar** de `ops4-registro-repeticiones.md` | Faltan retención, cuota, aprovisionamiento confiable y anclaje a la instalación; borrar marcas puede reabrir replay |
| Época/fencing tras reinicio o `fsync` incierto | **Descartar por ahora** como mecanismo | Hipótesis no probada; sí adoptar su regla: no confirmar antes de `fsync` y no reintentar a ciegas |
| Aprobación root `A` por SHA (C-12) | **Descartar** como requisito | El PO retiró la aprobación por SHA; no confundirla con el testigo de la app |
| Petición v3 con contraseña al host | **Descartar** en esta ruta | [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L64-L75) ya prevé retirar la contraseña; evitar dos protocolos vivos |

## 7. Riesgos registrados

- **Clave dedicada:** no reutilizar `ops.key`; 32 bytes, lectura por app y host, permisos mínimos, rotación/revocación y separación de copias. Si un proceso del grupo la lee, puede forjar testigos; la provisión no está implementada y bloquea la integración. Revisión SecOps del SHA final (CLAUDE.md §5, punto 8).
- **Replay y durabilidad:** TTL corto, `id_esperado` opcional y callback único; pero el callback es in-memory, el registro durable no está conectado, las marcas son permanentes (disco lleno deniega) y borrarlas puede reabrir la ventana. El ID no debe reutilizarse en otra acción. Confirmar solo tras `fsync` de fichero y directorio, fallo cerrado si es incierto y nunca reintento ciego; un `rename` sin `fsync` puede revivir estado previo ([ops4-propuesta-epoca.md](ops4-propuesta-epoca.md#L12-L44)).
- **Modelo de confianza y UI:** app o clave comprometidas pueden emitir un testigo; el HMAC prueba posesión, no salud de la app. El host debe seguir validando instalación, rutas, cerrojo, estado y unidad. La UI permanece inerte y sin importaciones ([test_ops4_ui_deshabilitada.py](../../tests/test_ops4_ui_deshabilitada.py#L32-L80)).
- **Contratos divergentes:** [ops4-especificacion-main.md](ops4-especificacion-main.md#L22) aún exige comprobación viva del hash en el host, contra la decisión de 2026-11-20; la ruta v3 con contraseña sigue en el árbol. Deben reconciliarse antes de habilitar.

## 8. Invariantes de ZascArr

- **No mentir / no borrar:** ante duda, `no_disponible` o denegación; nunca aceptar por un callback dudoso ni afirmar «actualizado» sin verificación. Sin contraseña, hash ni firma en logs, token, estado o responses. Las marcas de un solo uso no se borran para reabrir replay; la retención debe impedir esa ventana.
- **Confirmación / coste Pi:** reautenticación y confirmación explícita antes de emitir; nunca un GET ni una emisión silenciosa. HMAC de la stdlib, sin residente nuevo; el host no repite PBKDF2 en esta ruta (la reauth de la app ya lo paga).

## 9. Casos de prueba antes de implementar

- **Ya verdes (38 casos) y barreras:** aceptación única y repetición, ventana y tolerancia de reloj, formas/firmas inválidas, campos extra, duplicados, token sobredimensionado, callback que lanza o no devuelve `True`, 32 hilos con un solo consumo, token sin literales sensibles, clave/reloj inválidos ([test_ops4_autorizacion.py](../../tests/test_ops4_autorizacion.py#L35-L214)); UI con un botón deshabilitado, sin form/hx/script ni ruta POST; emisor y verificador fuera de web/API/`main`/auxiliar; emisor sin E/S ([test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py#L129-L149)).
- **Faltan (NOT RUN):** composición con reautenticación real y con cada resultado no-OK; doble consumo entre procesos con el registro real; inyección de fallo en `fsync`; provisión, propietario y modo de la clave; rotación/revocación; ID con CSPRNG; vínculo a operación e instalación; transporte; reinicio de la app; reloj real; extremo a extremo en host/VM; SecOps del SHA final.
- **Criterio comprobable de «mejor»:** ningún testigo sin `Reauth.OK`; exactamente una aceptación entre N procesos; fallo cerrado con `fsync`, clave o registro dudosos; replay imposible tras reinicio; ningún secreto en observables.

## 10. Matriz (nivel 2, orientativa; no reabre la decisión del PO)

Pesos por defecto de [benchmark-referencias.md](benchmark-referencias.md#L82-L87): encaje 25 · Pi 20 · seguridad 20 · cobertura 15 · stack 10 · mantenimiento 5 · salida 5. Puntuación 1–5; total sobre 500.

| Mecanismo | 25 | 20 | 20 | 15 | 10 | 5 | 5 | Total |
|---|---|---|---|---|---|---|---|---|
| App reautentica + HMAC corto de un uso | 4 | 5 | 3 | 3 | 5 | 4 | 5 | **400** |
| Verificación de hash en el host | 3 | 2 | 4 | 2 | 3 | 4 | 3 | **290** |
| Aprobación root `A` por SHA | 1 | 5 | 4 | 2 | 1 | 3 | 1 | **265** |
| Token de capacidad opaco | 3 | 4 | 2 | 2 | 3 | 4 | 4 | **295** |

## 11. IGUALAR / MEJORAR (con evidencia)

- **IGUALAR:** ventana corta, tolerancia, esquema cerrado, tiempo constante, un solo uso en proceso y ausencia de secretos; ya están en el contrato aislado.
- **MEJORAR:** composición del testigo nuevo con reautenticación (no existe: ningún import de `autorizacion_actualizacion`), consumo entre procesos y reinicios (callback in-memory), provisión de la clave dedicada (no implementada, [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md#L56-L62)). No se compara con competidores porque no hay ficha equivalente verificada.

## 12. Decisión final / ADR

- **Mantener** el patrón elegido, condicionado a clave dedicada, consumo durable, composición probada, transporte cerrado y revisión SecOps del SHA final; **no habilitar** antes de cumplirlo. No requiere ADR nuevo: al integrar, ampliar [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md) o crear uno de autorización app→host y corregir `ops4-especificacion-main.md:22`.

## 13. NOT RUN y caducidad

- **NOT RUN:** Pi, Docker de producción, systemd instalado, datos reales, `update.sh`, extremo a extremo host/VM y ejecución de Sonarr/Radarr/Kapowarr; este benchmark es lectura de código y documentos, sin ejecución. **Caduca:** 2027-01-19 (~60 días), o antes si cambia la decisión, el contrato de autorización o la referencia de producto.
