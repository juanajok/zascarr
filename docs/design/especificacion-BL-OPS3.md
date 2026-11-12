# SPEC: Pedir la contraseña actual para cambiar la seguridad en Ajustes (BL-OPS3, issue #456, condición de «Restaurar…», #443) — v1.2

> **v1.2 (2026-11-12) — retoque mínimo (pedido por el Brain tras la fusión de #508).** BL-OPS3 está **fusionada** (`services/reautenticacion.py`, `services/seguridad.py`, `web/ajustes.py`). (1) **AC-06 alineado con §9 y con el código:** el texto de la cola llena es «ZascArr está ocupado. Espera unos segundos e inténtalo otra vez.» (`MENSAJE_COLA_LLENA`); AC-06 decía «ZascArr está comprobando otras contraseñas…» (resto de v1.0, nunca actualizado). (2) El ADR de BL-OPS2 pasa del **0016 al 0019** (0015, 0016 y 0017 ocupados). **Base contrastada:** `origin/main` = `ac108e214c54dd6e803baa966925b69afffe2989` (fetch del 2026-11-12). v1.1 se conserva en `especificacion-BL-OPS3-v1.1.md` (sha256 `76827c05…7404`; la copia de `docs/design/` lleva además la cabecera de decisiones del PO). Sin otros cambios.


> **Decisiones del PO (2026-11-07):** aceptadas las recomendaciones de Q-1 a Q-11 de este documento (alcance con contraseña nueva, modo, usuario y `base_url`; bloqueo de 30 min tras 5 fallos en 15 con servicio único; campo siempre visible; `/logout` fuera; «Repite la contraseña nueva»; sin «te queda 1 intento» ni frase en `/login` en esta historia). Aprobada por SecOps (`dictamen-BL-OPS3-v1.0.md`), revisada por UX y con nota de benchmark de SCOUT. Construir requiere orden expresa aparte, y esta historia va **antes** de activar «Restaurar…» (BL-OPS2).

> **Decisión del PO (2026-11-06, no se reabre):** cambiar la contraseña, pasar a un modo de acceso más débil o apagarlo en Ajustes **exige la contraseña actual**, con mensajes en llano y **sin repetir lo escrito** en los errores; es un arreglo propio, en **PR aparte**, que se **fusiona antes** de activar «Restaurar…» en producción (FR-39 de BL-OPS2, #454). Lo que esta spec añade a esa decisión (el alcance exacto, el bloqueo, el servicio compartido con BL-OPS2) va marcado como **propuesta, decide el PO** (§12).
>
> **Estado:** v1.1 (2026-11-07): integra el dictamen de SecOps (`dictamen-BL-OPS3-v1.0.md`, aprobable sin bloqueantes, **con su adenda §6**, y su prueba `prueba-p2-eco-422.py`), la revisión de UX y la nota de benchmark de SCOUT (`nota-456-contrasena-actual.md`). **Pendiente del PO:** Q-1…Q-10 (SecOps lee favorable las recomendaciones). Registro de cambios por hallazgo en §15. v1.0 se conserva en `especificacion-BL-OPS3-v1.0.md` (sha256 `941e4c1c…8dc4`). Destino previsto: `docs/design/especificacion-BL-OPS3.md` (aquí vive en `encargos/` porque SPEC.writer no hace commits). **Sin código, sin PR, sin comentarios en GitHub, sin tablero, sin Pi.**
> **Base contrastada:** `origin/main` = `042ac49219b9d2993170e7d5aac4cbe33a9c664f` (fetch del 2026-11-07; **sin cambios** frente a `f4df6a4` en los ficheros de esta historia). La lectura se hizo sobre `c91ac78206cfd9ff3903e2d9898ee5c034cb211f`; entre ambas solo cambian el rescan de la biblioteca (BL-R9) y los candidatos de AniList/Tebeosfera (#135): **ninguno** de los ficheros que toca esta historia (`web/ajustes.py`, `services/seguridad.py`, `services/auth.py`, `web/auth.py`, `cli/seguridad.py`, `ajustes.html`, `tests/test_seguridad.py`, `tests/test_web_ajustes.py`) ha variado (`git diff --stat c91ac78 f4df6a4` sobre ellos, vacío).
> **Entradas:** el encargo del Brain (por orden del PO); issue #456; `docs/design/especificacion-BL-OPS2.md` (FR-39, R-1, Q-11; borrador en #454, leída la v1.2 de `encargos/`); `dictamen-BL-OPS2-v1.0.md` (A-1, M-3); código de `origin/main`: `web/ajustes.py`, `services/seguridad.py`, `services/auth.py`, `web/auth.py`, `cli/seguridad.py`, `web/templates/ajustes.html`, `_ajustes_guardado.html`, `tests/test_seguridad.py`, `tests/test_web_ajustes.py`.
> **Notación:** EARS con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES, DONDE; «DEBERÁ»); Given/When/Then; identificadores en inglés; textos de cara a la persona en español llano (CLAUDE.md §6). **PASS** = leído en código; **NOT RUN** = no ejecutado (§11).

---

## 0. Resumen ejecutivo

**El problema (HECHO, leído).** `POST /ui/ajustes/guardar/seguridad` llama a `fijar_seguridad`, que cambia contraseña, usuario o modo **sin pedir la contraseña actual**. Con una **cookie de sesión robada**, quien la tenga puede poner una contraseña propia (cerrando de paso las sesiones de la persona) y, cuando exista, «restaurar» con ella: la reautenticación de BL-OPS2 quedaría **cosmética** (dictamen A-1).

**Qué cambia.** Con una contraseña en vigor, el formulario de Seguridad lleva un campo **«Tu contraseña actual»** y el servicio `fijar_seguridad` **la exige** para cualquier cambio que pueda debilitar o secuestrar el acceso (§4, FR-01). Se comprueba con un servicio nuevo y compartido, `services/reautenticacion.py`, con **retraso progresivo y bloqueo** si se falla varias veces. Los errores salen en llano, con texto fijo, y **no repiten nada de lo escrito**; de paso se cierra el 422 de FastAPI que hoy puede devolver el campo `auth_password` en `input` (M-3 del dictamen).

**Qué no cambia.** Activar la contraseña por primera vez (no hay «actual» que pedir); guardar sin cambiar nada; el instalador y `python -m zascarr.cli.seguridad` (vía de recuperación si se olvida la contraseña: se ejecuta en el equipo, como root); el rehash silencioso al iniciar sesión; qué sesiones se cierran (`auth_session_version`); `/logout`.

**Lo que el PO debe ver (§12).** (1) **Alcance:** la issue dice «contraseña, modo más débil, apagar»; la spec propone **también** cambiar el usuario, **cualquier** cambio de modo y la dirección pública (`base_url`), porque los tres permiten secuestrar el acceso o la comprobación de Origen con una sesión robada (Q-1). (2) **Bloqueo:** se propone el mismo que el de BL-OPS2 (5 fallos en 15 min ⇒ 30 min) en un servicio compartido, **lo que obliga a un cambio menor en BL-OPS2 FR-03.4** (Q-2). (3) **Benchmark (hecho por SCOUT, E-10):** solo **Kavita** pide la actual para cambiar la contraseña; Sonarr y Radarr permiten cambiar el modo o apagar la autenticación con solo una sesión; el bloqueo en login de las referencias es de 5 fallos ⇒ 5 min (Sonarr, por IP) o 10 min (Kavita, por cuenta): **30 min es más largo** que la referencia (Q-2, alternativa de 10 min).

**Lo que NO está probado** (§11): nada se ha ejecutado; el eco de la contraseña en el 422 era una hipótesis y SecOps la **descartó con una prueba** (E-8): con la firma actual un `auth_mode` ausente da 422 con `input: null`, sin eco; solo aparece si se incumple una **restricción de campo**, que FR-04 prohíbe. Queda por probar la **ruta real** y con la versión de FastAPI instalada (P-2).

---

## 1. Alcance

**Dentro:** (1) regla «qué cambios exigen la contraseña actual» en `services/seguridad.py`; (2) servicio de reautenticación con retraso y bloqueo; (3) campo en el formulario y textos; (4) validación manual y sin eco en el router; (5) pruebas; (6) línea en `SECURITY.md`.

**Fuera:** pedir la actual en **otros** formularios de Ajustes (Prowlarr, Transmission, aMule, Comic Vine, avisos: son claves de integraciones, no el acceso a ZascArr); **«cerrar sesión en todos los aparatos»** y que `/logout` suba `auth_session_version` (Q-4); cambiar `/login`; segundo factor; recuperación de contraseña por correo; **BL-OPS2** y la activación de «Restaurar…» (esta historia es solo su condición de orden).

## 2. Contexto y evidencia (PASS = leído en `c91ac78`, sin cambios en `f4df6a4`)

| # | Hecho | Dónde |
|---|---|---|
| E-1 | `guardar_seguridad` recibe `auth_mode: str = Form(...)` (**obligatorio**), `auth_username`, `auth_password`, `base_url`; modo fuera de `MODOS` ⇒ `HTTPException(400)` con texto fijo; llama a `fijar_seguridad`; los errores de servicio salen como **200 con fragmento** (`_ajustes_guardado.html`). Si hubo cambio de credenciales, **re-emite la cookie del solicitante**. | `web/ajustes.py` |
| E-2 | `fijar_seguridad(db, *, modo, usuario, password, base_url)` **no pide la contraseña actual**: rechaza activar un modo sin contraseña (`MENSAJE_SIN_CONTRASENA`) o sin usuario, valida la longitud **de la nueva** (mínimo 12, aviso < 15; **sin máximo**), guarda `auth_mode`, `auth_username`, (si `password`) el hash PBKDF2 y `base_url.rstrip("/")`, y **sube `auth_session_version`** si cambia modo, usuario o contraseña; vacía la caché de Basic. «Contraseña vacía = conservar la que hay». | `services/seguridad.py` |
| E-3 | `hay_contrasena(s)` = modo con contraseña **y** hash guardado: es el criterio con el que el middleware exige credenciales. `MODOS = ("none", "password", "user_password")`. | `services/seguridad.py` |
| E-4 | `intentar_credenciales(username, password, settings)` verifica con **retraso progresivo global** (0,5 s doblando hasta 8 s; los fallos caducan a los 15 min; **sin bloqueo duro**), serializado por un candado y con cola acotada a 3 (`ColaDeVerificacionLlenaError`, que no cuenta como fallo). El contador es de la cuenta, no de la IP. | `services/auth.py` |
| E-5 | Otros llamadores de `fijar_seguridad`: `cli/seguridad.py` (`fijar-contrasena`, el instalador A11, **en el equipo y como root**, la contraseña por stdin). Otras escrituras de campos de acceso: `cli/seguridad.py retirar-base-url` (`save({"base_url": ""})`) y el **rehash** de `web/auth.py` al iniciar sesión (mismo secreto, más iteraciones, **sin** subir la versión). | `cli/seguridad.py`, `web/auth.py` |
| E-6 | El formulario de Seguridad (`ajustes.html`) tiene modo, usuario, contraseña (`autocomplete="new-password"`) y dirección desde Internet; **no** tiene campo de contraseña actual; el resultado va a `#resultado-seguridad`; los campos **no se vacían** tras responder. | `ajustes.html`, `_ajustes_guardado.html` |
| E-7 | La comprobación de Origen y de Host usa `settings.base_url`: quien la cambie decide qué orígenes se aceptan (E-7 de BL-OPS2). | `services/auth.py` |
| E-8 | `main.py` **no tiene manejador de `RequestValidationError`** (E-15 de BL-OPS2). **HECHO (SecOps, réplica de la firma con FastAPI 0.162.0 y pydantic 2.14.3, `prueba-p2-eco-422.py`):** con `auth_mode: str = Form(...)` y el resto `Form(default="")`, un `auth_mode` ausente da **422 con `"input": null` y sin eco** de la contraseña; el eco **sí** aparece cuando se incumple una **restricción de campo** (`max_length`…). Con la firma propuesta (sin restricciones) probó además multipart roto, multipart sin boundary, JSON en vez de formulario, campo repetido y 10 000 bytes: ninguno repite el valor. *Límites:* es una réplica, no la ruta real, y `pyproject` pide `fastapi>=0.115.0` **sin tope**. | `main.py`, `encargos/prueba-p2-eco-422.py` |
| E-9 | Pruebas existentes que fijan el comportamiento actual: `tests/test_seguridad.py` (llama a `fijar_seguridad` directamente) y `tests/test_web_ajustes.py` (`TestGuardarSeguridad`: modo desconocido ⇒ 400; sube la versión; `auth_mode="none"` en el estado previo para que el middleware deje pasar el POST). | `tests/` |
| E-10 | **Benchmark (SCOUT, nivel 1, solo lectura; Sonarr `c018578`, Radarr `5c31e55`, Kavita `c78f8a8`):** solo Kavita exige la actual (`OldPassword` en `account/reset-password`, también para el correo); Sonarr y Radarr piden doble tecleo de la nueva y permiten cambiar el modo sin reautenticar; bloqueo en login de 5 fallos ⇒ 5 min por IP (Sonarr) o 10 min por cuenta (Kavita), y Kavita **parece** no bloquear en el cambio (no verificado); sesiones tras el cambio **no verificadas** en las tres; recuperación con acceso a la máquina (Sonarr: token en el registro). Kapowarr y Mylar3 no examinados. | `nota-456-contrasena-actual.md` |

**Correcciones a las entradas** (se dicen, no se resuelven en silencio): la issue pide la actual para «cambiar la contraseña, pasar a un modo más débil o apagarlo»; leído el código, **cambiar el usuario**, **pasar a un modo más fuerte con otro usuario** y **cambiar `base_url`** permiten el mismo secuestro con una sesión robada (Q-1); y la interfaz **no puede** distinguir «más débil» de «distinto» sin una escala de modos: se usa «cualquier cambio de modo» (Q-1).

## 3. Glosario

- **Contraseña en vigor:** `hay_contrasena(settings)` (E-3). Si no la hay, **no existe una «actual»** que pedir.
- **La actual:** la contraseña con la que se entra hoy; se verifica contra `auth_password_hash` (en `user_password`, con `settings.auth_username`).
- **Reautenticación:** comprobar la actual con retraso y bloqueo, sin guardarla ni registrarla.

---

## 4. Requisitos funcionales

- **FR-01 (qué cambios exigen la actual — propuesta de alcance, Q-1)** DEBERÁ existir en `services/seguridad.py` una función pura `exige_contrasena_actual(settings, *, modo, usuario, password, base_url) -> bool` que sea `True` **si y solo si** hay contraseña en vigor **y** ocurre alguno de: (a) `password` **no vacía** (contraseña nueva); (b) `modo != settings.auth_mode` (cualquier cambio de modo: apagar, debilitar o añadir usuario); (c) `usuario != settings.auth_username` (*razón confirmada por SecOps: cambiar solo el usuario **sube `auth_session_version`** y echaría a la persona con una sesión robada, aunque en modo `password` el usuario no sirva para entrar*); (d) `base_url is not None` y la dirección **normalizada difiere de la vigente normalizada**, con **`rstrip("/")` aplicado a los dos lados** (un `BASE_URL` del `.env` con «/» final no debe hacer pedir la actual al guardar sin cambios, BR-03; SecOps N-1). Es la **única** fuente de la regla (CLAUDE.md §3.1.1); el router no la repite. *Quedan fuera, sin pedir nada:* activar la contraseña desde «sin contraseña» (no hay actual), guardar sin cambios (idempotente) y un modo `none` con un hash sobrante.
- **FR-02 (el servicio exige y comprueba; dos funciones, no una puerta booleana)** `services/seguridad.py` DEBERÁ ofrecer **dos funciones públicas** sobre una privada común: (a) **`fijar_seguridad(db, *, modo, usuario, password, base_url, contrasena_actual="")`**, la de la web, que **exige y comprueba**; (b) **`fijar_seguridad_desde_el_equipo(db, *, modo, usuario, password, base_url)`**, que **no** pide la actual y es **solo para `cli/seguridad.py`** (el instalador, en el equipo y como root). **No habrá un parámetro booleano que salte la comprobación** (SecOps N-3: una puerta booleana en un servicio compartido invita al mal uso; con dos nombres, el `grep` y la revisión lo ven). En (a), SI `exige_contrasena_actual(...)`: sin `contrasena_actual` ⇒ `ResultadoSeguridad(error=MENSAJE_FALTA_ACTUAL)`; con ella ⇒ `comprobar_contrasena_actual` (FR-03) y, si no es `ok`, el error que corresponda (§9); **en todos los fallos no se guarda nada, no se sube la versión y no se vacía ninguna caché**. **Orden:** primero las reglas de forma que no dependen de secretos (modo conocido, `MENSAJE_SIN_CONTRASENA`, `MENSAJE_SIN_USUARIO`, longitud de la nueva), **después** la comprobación de la actual y, solo si pasa, el guardado: un formulario mal rellenado **no gasta intentos**. `MENSAJE_FALTA_ACTUAL` cubre también el **formulario desactualizado** (la página se abrió sin contraseña en vigor, alguien la activó y el campo no existe): el texto manda a recargar (§9, N-4).
- **FR-03 (reautenticación compartida, Q-2)** DEBERÁ existir `services/reautenticacion.py::comprobar_contrasena_actual(password, settings) -> ResultadoReauth` con valores `ok`, `incorrecta`, `bloqueada` (con `hasta_epoch`), `ocupada`. Usa `intentar_credenciales(settings.auth_username, password, settings)` (E-4) y **añade un bloqueo duro propio**: al **5.º fallo en 15 min**, `bloqueada` durante **30 min desde el último fallo** (valor propuesto; alternativa de 10 min en Q-2), **sin calcular PBKDF2** ni anotar nada mientras dure, y guardando **la hora de fin** para poder decirla (§9); un acierto lo pone a cero. `ColaDeVerificacionLlenaError` ⇒ `ocupada` (no cuenta como fallo). **Qué se comparte y qué no (SecOps N-2):** el **retraso progresivo** sigue siendo **el contador global de la cuenta, compartido con `/login`** (los fallos de reautenticación lo alimentan y los de `/login`, también; quien martillea desde una sesión robada retrasa el acceso igual que quien martillea `/login`), mientras que el **bloqueo duro es solo de reautenticación**: bloquear una no impide entrar con `/login` ni al revés. **Ráfaga:** la comprobación del bloqueo se hace **antes** de entrar en la cola (de 3), así que en una ráfaga pueden colarse como mucho **2 intentos de más** (AC-21). Constantes (5 fallos, 15 min y **la duración del bloqueo**) en un solo sitio, **como parámetros del servicio**; **5 fallos/15 min coinciden con el auxiliar de BL-OPS2** (FR-13) y la **duración** (30 min) también *mientras el PO no la acorte*; si la acorta (Q-2), la duración **deja de exigir paridad** con el auxiliar (que protege a otro atacante: el que tiene la clave del canal sin sesión) y se conserva la de 5/15 (AC-15). **BL-OPS2 FR-03.4 deberá usar este mismo servicio** (cambio menor a esa spec: Q-2).
- **FR-04 (router: campos, validación manual, sin eco)** `POST /ui/ajustes/guardar/seguridad` DEBERÁ declarar `auth_mode`, `auth_username`, `auth_password`, `auth_password_actual` y `base_url` como **`str = Form(default="")` y sin ninguna restricción de campo** (`min_length`, `max_length`, `Literal`…): es la **defensa frente a restricciones futuras** (con una restricción incumplida el 422 sí devuelve el valor, E-8) y una **simplificación** (todas las respuestas del router, con texto fijo); **no** es necesaria hoy para evitar un eco que no existe (Q-7). `auth_mode` vacío o fuera de `MODOS` ⇒ `HTTPException(400)` con el **texto fijo** de hoy (la prueba `test_modo_desconocido_da_400` se mantiene; el modo **ausente** pasa de 422 a 400). Los errores de servicio siguen saliendo como **200 con fragmento** (patrón actual). **Ninguna respuesta** —éxito, error de servicio, 400 ni 422— repite el valor de `auth_password`, `auth_password_actual`, `auth_username` ni `base_url`.
- **FR-05 (formulario y respuesta, UX y adenda de SecOps §6)** DONDE haya contraseña en vigor, `ajustes.html` DEBERÁ mostrar el campo «Tu contraseña actual» (`type="password"`, `name="auth_password_actual"`, `autocomplete="current-password"`, **sin `value`**) **justo encima de «Guardar», después del `<details>` «Detalle técnico»**, con la ayuda de §9; la etiqueta de la contraseña nueva pasa de «Contraseña» a **«Contraseña nueva»** y **mantiene `autocomplete="new-password"`** (para que el gestor de contraseñas no la rellene con la antigua). SI no hay contraseña en vigor, el campo **no** aparece. **Ningún campo de contraseña se repuebla nunca desde el servidor** (ni `value` ni eco en un fragmento de error; AC-07). **Vaciado:** en **éxito** y ante **`bloqueada`** se vacían **los dos** campos; ante `falta`, `incorrecta` y `ocupada` basta vaciar **la actual** (la nueva sigue escrita en el navegador de quien la teclea; el servidor no la devuelve). **Respuesta de éxito de un cambio de credenciales:** DEBERÁ **sustituir toda la tarjeta de Seguridad**, con estas condiciones: (a) se renderiza **después** de aplicar el cambio, **desde el estado nuevo** (`hay_contrasena`), con **todos** los campos de contraseña sin `value` y sin repetir usuario ni dirección más que como los muestra la página; (b) se sustituye **solo si hay cambio de credenciales**: los **errores** (falta, incorrecta, bloqueo, cola, forma) siguen yendo a `#resultado-seguridad` y **no** recargan la tarjeta, o se perdería la contraseña nueva que se deja escrita; (c) el `Set-Cookie` de la sesión del solicitante viaja **en la misma respuesta**; (d) tras **activar la contraseña por primera vez**, la tarjeta nueva **trae** el campo de la actual (un segundo cambio sin recargar ya lo encuentra) y tras **apagar** la contraseña **lo quita**. Un `HX-Refresh` perdería el mensaje y no vale. **Accesibilidad:** `aria-live="polite"` en `#resultado-seguridad` y `aria-invalid="true"` en el campo de la actual cuando falta o es incorrecta. Sin librerías nuevas (ADR-0001). *Pendiente (N-4):* la sustitución **no** arregla el formulario desactualizado de **otra pestaña u otro aparato**; para eso vale el texto de «falta la actual» (FR-02).
- **FR-06 (sesiones)** **Sin cambios** respecto a hoy: un cambio de contraseña, usuario o modo sube `auth_session_version` y vacía la caché de Basic; las cookies emitidas antes dejan de valer **salvo la del solicitante, que se re-emite**. Un cambio solo de `base_url` no sube la versión. Un intento **rechazado** no toca nada. Tras un cambio de credenciales, el aviso de éxito DEBERÁ decir que las sesiones de otros aparatos se cerraron (§9).
- **FR-07 (`/logout`)** **Sin cambios y fuera de alcance:** `/logout` borra la cookie del navegador y **no** sube la versión (LEÍDO en el informe C-10 §4.9); una cookie robada sigue valiendo hasta cambiar las credenciales o 30 días. Esta historia **no lo corrige** (Q-4); la spec lo dice para que nadie crea que «cerrar sesión» cierra las demás.
- **FR-08 (caminos que NO piden la actual)** (a) `cli/seguridad.py` (`fijar-contrasena`) DEBERÁ llamar a **`fijar_seguridad_desde_el_equipo`**: es el instalador y la **vía de recuperación si se olvida la contraseña**, y exige estar en el equipo como root; (b) el **rehash** al iniciar sesión (`web/auth.py`) no es un cambio de credenciales (misma contraseña, sin versión) y no pasa por `fijar_seguridad`; (c) `retirar-base-url` de la CLI (en el equipo). **Ningún otro punto** del código puede pasar `auth_*`, `secret_key` o `base_url` a `RuntimeSettingsService.save()` (AC-12), **ni llamar a `fijar_seguridad_desde_el_equipo` salvo `cli/seguridad.py`** (y las pruebas): el router **nunca** (AC-12).
- **FR-09 (registro)** El router DEBERÁ registrar con `structlog`: `ajustes.seguridad_rechazada` con `motivo ∈ {falta_actual, actual_incorrecta, bloqueada, ocupada}` y, **en cada cambio aplicado**, `ajustes.seguridad_cambiada` con `cambios` ⊆ `{contrasena, modo, usuario, direccion}` (**qué** cambió, para poder reconstruir un robo de sesión; SecOps N-5). **Jamás** valores de campos, la contraseña ni su hash.
- **FR-10 (documentación)** `SECURITY.md` DEBERÁ llevar una línea: «Cambiar la contraseña, el usuario, el modo de acceso o la dirección pública en Ajustes exige la contraseña actual; si se olvida, se restablece con el instalador, **lo que exige poder ejecutar la herramienta en el equipo** (`docker compose run … zascarr`)» — sin prometer más (SecOps). Si BL-OPS2 aporta el ADR 0019, un párrafo allí (Q-5).

---

## 5. Reglas de negocio

- **BR-01** Una sesión por sí sola **no basta** para cambiar cómo se entra: hace falta además saber la contraseña.
- **BR-02** No hay «actual» que pedir donde no hay contraseña: activarla por primera vez sigue siendo libre (con la regla de longitud de siempre).
- **BR-03** Guardar sin cambiar nada **no** pide la actual (no se castiga el «Guardar» de costumbre).
- **BR-04** La vía de recuperación es **estar en el equipo**: la persona que olvida la contraseña no queda fuera para siempre (FR-08).
- **BR-05** Ningún texto de cara a la persona dice «hash», «PBKDF2», «versión de sesión» ni «token» (CLAUDE.md §6).

## 6. Requisitos no funcionales (la Pi, 512 MB)

- **NFR-01 (coste)** Una comprobación = un PBKDF2 (600 000 iteraciones hoy). Con el candado y la cola acotada a 3 no se acumula; el bloqueo duro **ahorra** CPU durante un ataque. Medido en la Pi con `scripts/medir-pbkdf2.sh` (existe; **no lo he ejecutado**, P-5).
- **NFR-02 (memoria)** El estado del bloqueo son dos números en memoria; sin ficheros, sin dependencias nuevas.
- **NFR-03 (un proceso)** El contador vive en el proceso (`uvicorn --workers 1`, CLAUDE.md §4): un reinicio de la app lo pone a cero (R-2).

---

## 7. Criterios de aceptación (Given / When / Then)

- **AC-01** *Dada* una contraseña en vigor, *cuando* se envía una contraseña nueva **sin** la actual, *entonces* respuesta 200 con «Para cambiar esto, escribe tu contraseña actual. Si no ves el campo, recarga la página.», `auth_password_hash` y `auth_session_version` **intactos** y ninguna caché vaciada. (FR-01, FR-02)
- **AC-02** *Cuando* se envía con la actual **correcta**, *entonces* se guarda, la versión sube en 1, la cookie del solicitante se re-emite y el aviso dice que las sesiones de otros aparatos se cerraron. (FR-02, FR-06)
- **AC-03** *Cuando* la actual es **incorrecta**, *entonces* «La contraseña actual no es correcta.», nada cambia, y avanzan el retraso progresivo y el contador de reautenticación. (FR-02, FR-03)
- **AC-04** *Matriz con contraseña en vigor (modo y datos de partida fijos en la prueba):*

| Cambio pedido | ¿Exige la actual? |
|---|---|
| contraseña nueva | **sí** |
| `password` → `none` (apagar) | **sí** |
| `user_password` → `password` (debilitar) | **sí** |
| `password` → `user_password` (con usuario nuevo) | **sí** |
| usuario distinto en `user_password` | **sí** |
| `base_url` distinta (tras `rstrip("/")`) | **sí** (Q-1) |
| `base_url` con «/» final **solo en un lado** (el `BASE_URL` del `.env` la lleva, el formulario no) y el mismo valor | no (se normalizan los dos lados, N-1) |
| guardar **sin ningún cambio** | no |
| contraseña en blanco (conservar) y nada más distinto | no |
| partiendo de `none` (activar contraseña por primera vez) | no |
| partiendo de `none` con hash sobrante (reactivar) | no |

  (FR-01, BR-02, BR-03)
- **AC-05** *Dados* 5 fallos en 15 min, *cuando* llega un 6.º intento —**aunque sea la contraseña correcta**—, *entonces* «Has fallado la contraseña varias veces. Espera media hora e inténtalo otra vez.», **no se calcula PBKDF2** y no se anota otro fallo; a los 30 min desde el último fallo vuelve a comprobarse; un acierto antes del 5.º pone el contador a cero; y el bloqueo de reautenticación **no** impide entrar por `/login` ni al revés. (FR-03)
- **AC-06** *Cuando* la cola de verificaciones está llena, *entonces* «ZascArr está ocupado. Espera unos segundos e inténtalo otra vez.» y **no** cuenta como fallo. (FR-03)
- **AC-07** *Dado* un **centinela** en `auth_password`, `auth_password_actual`, `auth_username` y `base_url`, *entonces* **no aparece** en ninguna respuesta —éxito, error de servicio, 400, y los casos «campo ausente», «campo repetido», «campo de 10 000 bytes», multipart roto y cuerpo JSON— ni en los registros; y **ninguna** respuesta es un 422 que repita el valor. **La prueba corre contra la ruta real y con la versión de FastAPI instalada** (`pyproject` no fija tope, E-8). (FR-04, FR-09)
- **AC-08** *Entonces* una prueba estática comprueba que los cinco parámetros del router son `str = Form(default="")` **sin** restricciones de campo. (FR-04)
- **AC-09** *Entonces* con contraseña en vigor el formulario muestra «Tu contraseña actual» (`autocomplete="current-password"`, sin `value`) antes de «Guardar», la nueva sigue en `new-password`, y **sin** contraseña en vigor el campo no aparece; tras cada respuesta los campos de contraseña quedan vacíos (*esto último, NOT RUN en navegador: P-3*). (FR-05)
- **AC-10** *Entonces* `python -m zascarr.cli.seguridad fijar-contrasena` y `retirar-base-url` **siguen funcionando sin la actual** (la primera llama a `fijar_seguridad_desde_el_equipo`), y una prueba falla si `fijar-contrasena` deja de hacerlo. (FR-08, FR-02)
- **AC-11** *Entonces* el **rehash** al iniciar sesión (`web/auth.py`) sigue sin pedir la actual y sin subir la versión (la prueba existente no cambia). (FR-08)
- **AC-12** *Entonces* una prueba estática comprueba que (a) las únicas llamadas a `RuntimeSettingsService.save()` con `auth_mode`, `auth_username`, `auth_password_hash`, `auth_session_version`, **`secret_key`** o `base_url` están en las funciones de `fijar_seguridad*`, `ensure_secret_key`, el rehash de `web/auth.py` y `cli/seguridad.py`; y (b) **solo `cli/seguridad.py`** (y las pruebas) llama a `fijar_seguridad_desde_el_equipo`, y **el router no la importa**; una nueva ruta que escriba esas claves o que use esa función **rompe la prueba**. (FR-08, N-3)
- **AC-13** *Dado* un formulario mal rellenado (activar un modo sin contraseña, `user_password` sin usuario, contraseña nueva de menos de 12 caracteres), *entonces* se devuelve el error de forma **antes** de comprobar la actual y **no** se consume ningún intento. (FR-02)
- **AC-14** *Dada* una cookie emitida **antes** del cambio, *cuando* se cambia la contraseña con la actual correcta, *entonces* esa cookie deja de valer en otro aparato y la del solicitante sigue valiendo. (FR-06)
- **AC-15** *Entonces* el umbral (5 fallos en 15 min) y la duración del bloqueo están definidos **una sola vez**, como parámetros del servicio; el **umbral** coincide siempre con el del auxiliar de BL-OPS2 (prueba de paridad cuando exista) y la **duración** coincide **mientras valga 30 min**: si el PO la acorta (Q-2), la prueba deja de exigir paridad de **duración** y conserva la de 5/15. (FR-03)
- **AC-16** *Entonces* `tests/test_seguridad.py`, `tests/test_web_ajustes.py` y `tests/test_auth*.py` **pasan sin cambios**, salvo las **adaptaciones listadas en la PR** (hoy: ninguna conocida; `test_seguridad.py` llama a `fijar_seguridad` con modo `none`, donde no se pide la actual). (FR-04)
- **AC-17** *(NOT RUN hasta construir)* En un navegador real, el flujo «cambiar contraseña con la actual», «sin la actual», «con la actual errónea» y «bloqueo» se ve como dice §9 y los campos quedan vacíos. (P-3)
- **AC-18** *Cuando* un cambio de credenciales sale bien, *entonces* la respuesta **sustituye toda la tarjeta de Seguridad** con el mensaje de éxito dentro y el formulario re-renderizado: si **antes no había contraseña y ahora sí**, el formulario nuevo **ya trae** el campo «Tu contraseña actual» y un **segundo** cambio sin recargar la página lo encuentra; tras **apagar** la contraseña, la tarjeta nueva **no** trae ese campo; **ningún** campo de contraseña lleva `value`; el `Set-Cookie` del solicitante viaja en la **misma** respuesta; y una respuesta de error solo recambia `#resultado-seguridad` (la tarjeta **no** se recarga y la contraseña nueva escrita no se pierde). (FR-05, UX, SecOps §6.3)
- **AC-19** *Entonces* el campo de la actual lleva `aria-invalid="true"` cuando falta o es incorrecta, `#resultado-seguridad` lleva `aria-live="polite"`, la etiqueta de la nueva es «Contraseña nueva», el campo de la actual va justo encima de «Guardar» tras el `<details>` «Detalle técnico», y se vacía **solo la actual** ante «falta», «incorrecta» y «ocupada», y **las dos** ante «bloqueada» y en éxito; ninguna respuesta repuebla un campo de contraseña. (FR-05, UX, SecOps §6.1)
- **AC-20** *Cuando* se aplica un cambio, *entonces* se registra `ajustes.seguridad_cambiada` con `cambios` ⊆ `{contrasena, modo, usuario, direccion}` y **ningún valor**; un rechazo registra `ajustes.seguridad_rechazada` con su `motivo`. (FR-09, N-5)
- **AC-21** *Dada* una ráfaga de intentos incorrectos simultáneos con el contador en 4, *entonces* se cuelan **como mucho 2** intentos más allá del 5.º antes de que el bloqueo entre en vigor y el resto reciben `bloqueada` sin PBKDF2. (FR-03, N-2)
- **AC-22** *Cuando* hay bloqueo, *entonces* el texto dice **la hora de fin** en la zona horaria del servidor (`TZ`), que `/login` sigue funcionando y quién puede poner una contraseña nueva; y un acierto de `/login` **no** levanta el bloqueo de reautenticación ni al revés, aunque el **retraso progresivo** sí es compartido. (FR-03, §9)

---

## 8. Casos de prueba

| # | Caso | Esperado | Dónde |
|---|---|---|---|
| T-01 | `exige_contrasena_actual` sobre la matriz de AC-04 (incluida la normalización de `base_url`) | AC-04 | unitaria pura, `tests/test_seguridad.py` |
| T-02 | `fijar_seguridad` con y sin `contrasena_actual`, `desde_el_equipo`, orden de comprobaciones, nada guardado en el rechazo | AC-01…AC-03, AC-13 | `tests/test_seguridad.py` (ampliada) con `FakeSession` |
| T-03 | reautenticación: retraso, 5/15/30, acierto que reinicia, hora de fin, **retraso global compartido con `/login` y bloqueo independiente**, cola llena, ráfaga (≤ 2 de más), reloj inyectado | AC-03, AC-05, AC-06, AC-21, AC-22 | `tests/test_reautenticacion.py` (nuevo) |
| T-04 | router con centinela en los cuatro campos y casos de «ausente», «repetido» y «10 000 bytes»; nunca 422 | AC-07 | `tests/test_web_ajustes.py` (ampliada) |
| T-05 | estática: parámetros del router sin restricciones; únicas escrituras de `auth_*`/`secret_key`/`base_url`; solo `cli/seguridad.py` usa `fijar_seguridad_desde_el_equipo` y el router no la importa | AC-08, AC-12 | `tests/` (lectura del código) |
| T-06 | plantilla: campo actual con y sin contraseña en vigor, `autocomplete`, sin `value` | AC-09 | prueba de plantilla |
| T-07 | CLI: `fijar-contrasena` sigue sin pedir la actual y usa `fijar_seguridad_desde_el_equipo` | AC-10 | prueba existente de la CLI, ampliada |
| T-08 | sesiones: cookie vieja inválida, la del solicitante válida, versión +1 | AC-14 | `tests/test_web_ajustes.py` |
| T-09 | paridad de constantes con BL-OPS2 | AC-15 | unitaria (cuando exista el auxiliar) |
| T-10 | tarjeta de Seguridad: éxito que la sustituye entera con el campo de la actual ya presente (activar y cambiar otra vez sin recargar); error que solo toca `#resultado-seguridad`; tras activar por primera vez la respuesta trae el campo de la actual y tras apagar lo quita; `Set-Cookie` en la misma respuesta; sin `value` en ningún campo de contraseña; vaciado por caso; `aria-invalid`, `aria-live`, etiqueta y orden | AC-18, AC-19 | prueba de plantilla + `TestClient` |
| T-11 | registro de `seguridad_cambiada` y `seguridad_rechazada`, sin valores | AC-20 | `caplog`/`structlog` capturado |

**Se prueba a mano** (NOT RUN, §11): el navegador (htmx, campos vaciados) y el coste de PBKDF2 en la Pi.

## 9. Textos de cara a la persona (catálogo cerrado; propuesta, UX la revisa)

| Situación | Texto |
|---|---|
| Etiqueta del campo / de la nueva | «Tu contraseña actual» / «Contraseña nueva» |
| Ayuda del campo | «Hace falta para cambiar la contraseña, el modo, el usuario o la dirección.» |
| Falta la actual (y formulario desactualizado) | «Para cambiar esto, escribe tu contraseña actual. Si no ves el campo, recarga la página.» |
| Actual incorrecta | «La contraseña actual no es correcta.» |
| Bloqueo | «Has fallado la contraseña varias veces. Por seguridad, no se pueden cambiar estos ajustes hasta las HH:MM. Puedes seguir usando ZascArr con normalidad. Si la has olvidado, quien instaló ZascArr puede poner una nueva.» (HH:MM en la zona horaria del servidor, `TZ`; sale de `hasta_epoch`, FR-03) |
| Cola llena | «ZascArr está ocupado. Espera unos segundos e inténtalo otra vez.» |
| Éxito con cambio de credenciales | «Seguridad: guardado y aplicado — ya activo, sin reiniciar.» + «Tu sesión sigue abierta; las de otros aparatos se han cerrado.» |
| Éxito sin cambio de credenciales (p. ej. solo la dirección) | «Seguridad: guardado y aplicado — ya activo, sin reiniciar.» (como hoy) |
| `<details>` «¿La has olvidado?» (convención «Para quien instaló ZascArr») | «Para quien instaló ZascArr: se puede poner una contraseña nueva desde el equipo, con el instalador. Más detalle en `SECURITY.md`.» |
| Aviso de intentos restantes (**opcional**, Q-9) | «Te queda 1 intento antes del bloqueo.» (solo con ≤ 2 restantes) |
| Las dos contraseñas nuevas no coinciden (**solo si el PO acepta Q-11**) | «Las dos contraseñas nuevas no coinciden.» (etiquetas: «Contraseña nueva» y «Repite la contraseña nueva»; error de forma: no gasta intentos; se vacían ambos campos de contraseña nuevos) |

*Regla de UX heredada:* la frase de ayuda es única; el vocabulario técnico solo va en `<details>`. Los errores de forma de hoy (`MENSAJE_SIN_CONTRASENA`, `MENSAJE_SIN_USUARIO`, `MENSAJE_CORTA`, `MENSAJE_DEBIL`) **no cambian**.

---

## 10. Riesgos

| # | Riesgo | Mitigación | Residual |
|---|---|---|---|
| R-1 | **El bloqueo permite molestar:** quien tenga una sesión robada puede agotar los 5 intentos y bloquear 30 min **a la persona** para cambiar la seguridad (no para entrar ni para usar ZascArr). | Es solo disponibilidad de una acción poco frecuente; independiente de `/login`; mismo criterio que BL-OPS2 (R-4 de esa spec) | Aceptado |
| R-2 | El contador está en memoria: un reinicio de la app lo pone a cero. | Quien reinicia la app ya tiene el equipo; el retraso progresivo y la cola acotada siguen aplicando | Aceptado, mismo límite que `/login` |
| R-3 | **Fuerza bruta de la actual con una sesión robada:** el atacante ya está dentro y adivina la contraseña por esta vía. | 5 fallos/15 min y bloqueo de 30 min ≤ ~240 intentos/día; PBKDF2 de 600 000; mínimo de 12 caracteres (sin máximo ni lista de contraseñas comunes) | Depende de la longitud real de la contraseña |
| R-4 | **Modo `none`:** no existe una «actual», así que cualquiera que llegue a ZascArr sin contraseña puede **activar** una y dejar fuera a la persona. | Fuera de esta historia (BR-02); en `none` el aviso de exposición ya existe; la CLI del equipo lo deshace | Aceptado: sin contraseña no hay nada que proteger |
| R-5 | **Fricción** de pedir la actual para `base_url` a quien la cambia a menudo. | Solo cuando **cambia** el valor; guardar sin cambios no la pide (BR-03); alternativa en Q-1 | Bajo |
| R-6 | ~~El 422 con eco existe hoy.~~ **CERRADO (SecOps, HECHO):** con la firma actual un `auth_mode` ausente da 422 sin eco (E-8); el eco solo aparece con restricciones de campo, que FR-04 prohíbe. | FR-04 y AC-07 (contra la ruta real y la versión instalada de FastAPI) | Cerrado; queda P-2 |
| R-7 | Dos lógicas de reautenticación divergen (Ajustes y BL-OPS2). | Un solo servicio (FR-03) y una sola constante (AC-15) | Requiere el cambio menor a BL-OPS2 (Q-2) |
| R-8 | Quien olvida la contraseña necesita acceso al equipo. | Es la vía de recuperación decidida (BR-04); el texto de §9 la nombra | Aceptado |
| R-9 | **Formulario desactualizado** (la página se abrió sin contraseña en vigor y alguien la activó): el envío pide la actual sin campo donde escribirla. | Texto de «falta la actual» con «Si no ves el campo, recarga la página» (FR-02, N-4); tras un cambio de credenciales la tarjeta se sustituye entera (FR-05) | Bajo |
| R-10 | Una **puerta que salta la comprobación** en un servicio compartido se usa mal en el futuro. | Dos funciones con nombre distinto (FR-02) y prueba estática de quién las llama (AC-12) | Bajo |

## 11. NOT RUN y supuestos

**Nada de esto se ha ejecutado:** ni la aplicación, ni las pruebas, ni la Pi.

- **P-1** No he ejecutado nada de lo leído; todo es lectura de `origin/main`.
- **P-2** ~~Hipótesis del eco en el 422~~ **DESCARTADA (HECHO, SecOps; E-8).** Queda por hacer: correr AC-07 contra la **ruta real** y con la versión de FastAPI instalada (`pyproject` pide `fastapi>=0.115.0` sin tope).
- **P-3** Conducta en navegador real: sustitución del fragmento por htmx, vaciado de los campos de contraseña y `autocomplete`.
- **P-4** **Benchmark hecho por SCOUT** (E-10). Lo que **no** verificó y sigue abierto: cómo tratan las **sesiones** tras el cambio las tres referencias, si Kavita bloquea en `reset-password`, y Kapowarr y Mylar3 (no examinados). No cambia la regla de la decisión del PO.
- **P-5** Coste de un PBKDF2 en la Pi (existe `scripts/medir-pbkdf2.sh`; no lo he ejecutado) y cuánto tarda el flujo completo con la cola llena.
- **P-6** Qué pruebas existentes fijan hoy un **422** para un campo ausente en este formulario (he leído `TestGuardarSeguridad`: ninguna lo fija; no he leído todo el fichero ni otros).
- **Supuesto:** el instalador A11 se ejecuta en el equipo como root y no pasa por la interfaz (E-5).

## 12. Decisiones para el PO (lista corta; recomendación primero)

| # | Decisión | Recomendación | Alternativa |
|---|---|---|---|
| **Q-1** | **Alcance** de «exige la actual» (la issue pide: contraseña, modo más débil, apagar). | **Contraseña nueva, cualquier cambio de modo, cambio de usuario y cambio de `base_url`**: los tres últimos también permiten secuestrar el acceso o el Origen con una sesión robada (E-7). Sin cambios no se pide nada. | Solo lo de la issue (contraseña, debilitar, apagar): deja abierto «pasar a `user_password` con un usuario que la persona no conoce» y la dirección pública · o sin `base_url` (menos fricción; deja `base_url` como vía de persistencia del atacante) |
| **Q-2** | **Bloqueo y servicio compartido** con BL-OPS2. *SecOps de acuerdo, con la precisión de FR-03 (retraso global compartido con `/login`, bloqueo duro solo de reautenticación).* | **Servicio único `services/reautenticacion.py`** con retraso progresivo + bloqueo de **30 min** tras 5 fallos en 15 min (constantes del auxiliar de BL-OPS2); **BL-OPS2 FR-03.4 pasa a usarlo** (cambio menor, v1.3 o al construir). | **10 min** (**SecOps prefiere mantener 30**, porque el mismo servicio protege «Restaurar…», una acción destructiva; la diferencia de intentos por día, ≈160 frente a ≈290, **no es material** con 12 caracteres y PBKDF2 de 600 000: es una decisión de molestia, R-1; si se acorta, la duración es **parámetro del servicio** y AC-15 no exige paridad de duración con BL-OPS2). Más cerca de la referencia: Sonarr 5 min por IP, Kavita 10 min por cuenta, E-10; 30 min es más largo y agrava R-1 sin ganar mucho con PBKDF2) · o solo el retraso progresivo global de hoy (sin bloqueo duro) |
| **Q-3** | Cómo se pide. | **Campo siempre visible** cuando hay contraseña en vigor, con su ayuda (una sola pantalla, sin JavaScript nuevo). | Dos pasos (se envía y, si hace falta, se pide): más código en el router y estado en la respuesta |
| **Q-4** | **`/logout` y «cerrar sesión en todos los aparatos».** | **Fuera**: queda como limitación escrita (FR-07). Historia aparte, con reautenticación, si el PO la quiere. | Que `/logout` suba la versión (cierra las sesiones de **todos** los aparatos: sorprende) |
| **Q-5** | Dónde se documenta. | Línea en `SECURITY.md` + párrafo en el **ADR 0019** de BL-OPS2 si está; si no, en el cuerpo de la PR. | ADR propio para una regla tan pequeña (más ruido) |
| **Q-6** | **Benchmark.** | **Hecho** (nota de SCOUT, E-10, P-4): sin decisión pendiente. | — |
| **Q-7** | Un campo ausente en este formulario pasa de **422 a 400** con texto fijo (FR-04). **Motivo corregido:** no hace falta para evitar un eco (no existe, E-8); es una **simplificación** y la **defensa frente a restricciones de campo futuras**. | **Sí.** | Mantener el 422 (no repite el valor hoy) |
| **Q-8** | **Dos funciones** (`fijar_seguridad` y `fijar_seguridad_desde_el_equipo`) en lugar de un booleano `desde_el_equipo` (SecOps N-3). | **Dos funciones** + prueba estática de quién las llama. | Un booleano + la misma prueba estática (más corto, más fácil de usar mal) |
| **Q-9** | «Te queda 1 intento antes del bloqueo» con ≤ 2 restantes (propuesta de UX; **SecOps aún no la ha dictaminado**: ¿es filtración?). | **No incluirlo hasta que SecOps lo diga** (quien tiene la sesión ya ve el contador probando; ayuda más a quien se equivoca). | Incluirlo |
| **Q-10** | Mencionar la recuperación también en `/login` (SCOUT: Sonarr lo ofrece como enlace en el login). *SecOps la acepta si es una frase neutra **sin comandos ni rutas**, porque `/login` es público.* | **No en esta historia** (toca `/login`, fuera de alcance, §1). | Una frase neutra en `/login`: «Quien instaló ZascArr puede poner una nueva desde el equipo.» |
| **Q-11** | Un campo **«Repite la contraseña nueva»** (opinión de SecOps para UX, sin implicación de seguridad: la nueva se teclea **a ciegas y sin repetición**, un error de tecleo deja a la persona con una contraseña que no conoce y el remedio es la CLI en el equipo; Sonarr y Radarr lo piden según la nota de SCOUT). | **Sí**: es barato (un campo, una comparación en el servicio antes de comprobar la actual, error de forma sin gastar intentos) y evita dejar fuera a la persona. Texto de §9; **sin eco** (el campo nunca se repuebla). | No (menos fricción; más riesgo de error de tecleo) |

## 13. Orden y relación con BL-OPS2

- **Orden (decisión del PO):** esta PR se **fusiona antes** de activar «Restaurar…» en producción; es **independiente** de BL-OPS1 y no necesita el auxiliar. BL-OPS2 puede construirse en paralelo pero **no se activa** hasta que esta esté en `main`.
- **Lo que comparte con BL-OPS2:** el servicio de reautenticación (FR-03) y la regla de «sin eco» (M-3). Si el PO acepta Q-2, BL-OPS2 FR-03.4 sustituye «`intentar_credenciales`» por «`comprobar_contrasena_actual`» y hereda el bloqueo.
- **Lo que NO hace:** no toca el auxiliar, ni el socket, ni `restaurar_datos.sh`.

## 14. Trazabilidad

| Origen | Cómo queda | Dónde |
|---|---|---|
| Decisión del PO (#456) | Contraseña actual para cambiar contraseña, debilitar o apagar | FR-01, FR-02, AC-01…AC-04 |
| Dictamen A-1 de BL-OPS2 | La reautenticación deja de ser cosmética frente a sesión robada | FR-01…FR-03, R-3 |
| Dictamen M-3 de BL-OPS2 | `Form(default="")` sin restricciones, validación manual, sin eco | FR-04, AC-07, AC-08, E-8 |
| BL-OPS2 FR-39 / Q-11 / R-1 | Esta spec es su condición de orden | §13, Q-2 |
| BL-OPS2 FR-13 (5/15/30) | Misma política, un solo servicio | FR-03, AC-15, Q-2 |
| Informe C-10 §4.9 (`/logout`) | Limitación escrita, fuera de alcance | FR-07, Q-4 |
| CLAUDE.md §3.1.1 (services única fuente) | La regla vive en `services/seguridad.py` | FR-01, FR-02 |
| CLAUDE.md §6 (español llano, sin eco) | Catálogo de §9 | §9, BR-05 |
| Dictamen SecOps de v1.0 (N-1…N-5, P-2, Q-7) y prueba P-2 | Ver §15 (v1.1) | FR-01…FR-04, FR-09, FR-10, AC-04, AC-07, AC-10, AC-12, E-8, R-6, R-10, Q-7, Q-8 |
| Revisión de UX de v1.0 | Ver §15 (v1.1) | FR-05, §9, AC-18, AC-19, AC-22, Q-9 |
| Nota de SCOUT (#456) | Ver §15 (v1.1) | E-10, P-4, Q-2, Q-6, Q-10 |

## 15. Registro de cambios

| Versión | Fecha | Cambio |
|---|---|---|
| **v1.0** | 2026-11-06 | Primera versión. Leída sobre `origin/main` `c91ac78` y contrastada con `f4df6a4`. D del PO: la issue #456 (alcance mínimo). Q-1…Q-7 abiertas; ninguna bloquea redactar el plan de construcción salvo Q-1 (alcance) y Q-2 (bloqueo y cambio menor a BL-OPS2). Pendiente de SecOps y de UX (§9). Benchmark **no hecho** (P-4, Q-6). |
| **v1.1** | 2026-11-07 | Integra el dictamen de SecOps (aprobable), la revisión de UX y la nota de SCOUT. **Q-1** de acuerdo, con su razón (cambiar solo el usuario sube la versión). **Q-2** de acuerdo con la precisión de **N-2** (retraso global compartido con `/login`, bloqueo duro independiente) → FR-03, AC-22, T-03; **ráfaga ≤ 2 de más** → AC-21; alternativa de **10 min** por la referencia (E-10). **P-2 descartada** (HECHO: sin eco con la firma actual) → E-8, R-6 cerrado, P-2, Q-7 con el motivo corregido (simplificación y defensa futura), AC-07 contra la ruta real y la versión instalada de FastAPI. **N-1** (normalizar `base_url` por los dos lados) → FR-01, AC-04. **N-3** (sin puerta booleana) → FR-02 con **dos funciones**, FR-08, AC-10, AC-12 (+ `secret_key`), T-05, T-07, Q-8, R-10. **N-4** (formulario desactualizado) → FR-02, §9, R-9. **N-5** (rastro de cambios) → FR-09, AC-20, T-11. `SECURITY.md` → FR-10 (la recuperación exige poder ejecutar la herramienta en el equipo). **UX:** respuesta de éxito que sustituye toda la tarjeta (FR-05, AC-18, T-10); campo de la actual encima de «Guardar» tras «Detalle técnico», etiqueta «Contraseña nueva», `aria-invalid`/`aria-live`, vaciado selectivo (FR-05, AC-19); textos de §9 (ayuda, bloqueo con la hora de fin y «`/login` sigue funcionando», cola llena, `<details>` «¿La has olvidado?»); aviso de intentos restantes como **opcional** pendiente de SecOps (Q-9). **SCOUT:** E-10, P-4, Q-6 cerrada, Q-10. Sin otros cambios. **Adenda de SecOps (§6 del dictamen):** vaciado por caso (la actual ante falta/incorrecta/ocupada; las dos ante éxito y bloqueada) y ningún campo de contraseña repoblado nunca (FR-05, AC-19); **Q-11** nueva («Repite la contraseña nueva», recomendación: sí); bloqueo: SecOps prefiere mantener 30 min y, si el PO lo acorta, la duración es parámetro y AC-15 no exige paridad de duración (FR-03, AC-15, Q-2); tarjeta sustituida con las condiciones (a)…(d) (FR-05, AC-18, T-10); Q-10 con la frase neutra aceptada por SecOps; N-4 sigue pendiente para otra pestaña u otro aparato. |
| **v1.2** | 2026-11-12 | Retoque mínimo tras la fusión de #508: **AC-06** con el texto de §9 y del código (`MENSAJE_COLA_LLENA`); ADR de BL-OPS2 **0016 → 0019**. Sin otros cambios. |
