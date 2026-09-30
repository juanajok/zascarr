# Ficha — Lote de seguridad: autenticación, Origen/Host y comprobación real de dependencias

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Es un
> **arreglo de seguridad**, así que lleva ficha antes de código. El riesgo no es
> el volumen de código: es **dejar una puerta que no se ve** (un formulario
> cross-site, una cookie que no se invalida, un PBKDF2 que congela la Pi) o
> creer que un check rojo protege cuando no protege nada.

**Estado:** propuesta para validar. No hay código escrito.

## Historia / problema observado

Revisión de deuda técnica (2026-09-29), dos hallazgos P0:

1. **Sin protección CSRF ni comprobación de `Origin`/`Host`.** Con
   `auth_mode = "none"` (el valor por defecto), `AuthMiddleware` es un no-op y
   **no hay cookie de sesión**, así que `SameSite=Lax` no protege nada: una web
   cualquiera abierta en el navegador puede enviar un `<form>` POST a
   `127.0.0.1:8000` y el navegador lo deja salir (SOP bloquea *leer* la
   respuesta, no *enviar* la petición). Los formularios de ajustes
   (`web/ajustes.py::guardar_*`) no llevan token CSRF: un tercero puede activar
   una contraseña ajena (dejando fuera al dueño) o apuntar el webhook a otro
   destino.
2. **Paquete de fallos de autenticación** (detalle abajo), todos vivos en el
   código.

## Datos reales y medición de partida

Verificado en el código (`main` en `7f6f637`):

- `services/auth.py:41` — `_PBKDF2_ITERATIONS = 260_000`; el comentario la
  atribuye a OWASP 2023.
- `services/auth.py:100` — en modo `user_password`:
  `usuario_ok = hmac.compare_digest(username, settings.auth_username)`. Si
  `username` lleva tilde o ñ, `compare_digest` lanza `TypeError` (solo admite
  `str` ASCII o bytes), que sube por el middleware y llega como **500**.
- `services/auth.py:73` — `verify_password` ejecuta
  `hashlib.pbkdf2_hmac(...)` **síncrono**; lo llama `credenciales_validas`
  (líneas 96 y 99) y éste `_basic_auth_valido` (línea 155), dentro del
  middleware, en **cada** petición `/api/*` con Basic Auth. Bloquea el bucle de
  eventos de la Pi.
- `services/auth.py:129-143` — la cookie es `sign_token(str(int(time.time())),
  secret_key)`: solo una marca de tiempo firmada. Cambiar la contraseña cambia
  `auth_password_hash`, **no** `secret_key`, así que la cookie sigue valiendo 30
  días.
- `services/auth.py:198-200` — `siguiente = f"{path}{query}"` seguido de
  `RedirectResponse(f"/login?next={siguiente}")` **sin codificar `next`**: una
  URL con `&` se trunca (el resto se parsea como parámetros del propio
  redirect).
- `services/auth.py:48` — `_RUTAS_EXENTAS` incluye `/legal` por ruta exacta.
  **Comprobado: no es un agujero.** Los `POST` de aceptación son
  `/ui/legal/accept` (`web/legal.py:37`) y `/api/legal/accept`
  (`api/legal.py:28`), que **no** están exentos, así que quedan detrás de auth;
  lo exento es solo el GET `/legal` (texto, solo lectura).
- **No existe ninguna** comprobación de `Origin`/`Host`/`Referer` ni token CSRF
  en todo `src/` (búsqueda exhaustiva). `main.py` documenta que no hay CORS
  porque UI y API viven en el mismo origen — pero CORS no es CSRF.
- `web/auth.py:76` — la cookie sale con `samesite="lax"`, `httponly=True`
  (correcto, pero inerte sin cookie).
- `config.py:155-161` — `auth_mode`/`auth_username`/`auth_password_hash`/
  `secret_key`; `secret_key` se autogenera y persiste, independiente de la
  contraseña.

## Referencias consultadas

- **OWASP Password Storage Cheat Sheet** (aportada por la revisión): la cifra
  recomendada para PBKDF2-HMAC-SHA256 es **600.000** iteraciones. OWASP
  recomienda **Argon2id** como primera opción y deja PBKDF2 para cuando se exige
  FIPS; aquí se mantiene PBKDF2 porque Argon2id obligaría a una dependencia
  nueva (CLAUDE.md §2). También pide que el hash tarde **menos de un segundo** y
  avisa de que un coste alto es un vector de agotamiento de CPU.
  `https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html`
- **OWASP CSRF Prevention Cheat Sheet** (aportada por la revisión): recomienda
  `Sec-Fetch-Site` como señal principal, con `Origin`/`Referer` como **respaldo
  obligatorio**, y bloquear cuando faltan ambas en un POST de navegador. Ojo
  documentado: los navegadores **no** envían `Sec-Fetch-*` sobre HTTP plano
  hacia una IP de LAN (solo HTTPS y `localhost`), así que en ese caso `Origin`
  es la única defensa.
  `https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html`
- **`hmac.compare_digest`** (documentación Python, aportada por la revisión):
  solo admite `str` ASCII o tipos *bytes-like*; con `str` no-ASCII lanza
  `TypeError`. `https://docs.python.org/3/library/hmac.html`
- **Sin referencia comparable verificada** sobre el mecanismo exacto de
  Origen/Host en Sonarr/Radarr/Kavita: no se cita de memoria. El diseño de abajo
  sale del invariante propio («nada de estado sin confirmación explícita del
  dueño») y del patrón estándar sin dependencias.

## Supuestos que NO valen en ZascArr

- **«`SameSite=Lax` ya cubre CSRF».** Solo si hay cookie; con `auth_mode=none`
  no la hay y el middleware deja pasar todo.
- **«CORS es CSRF».** Son cosas distintas: un `<form>` POST cross-site no se
  bloquea por CORS.
- **«El hash de la contraseña es fijo».** El formato
  `pbkdf2_sha256$<iter>$<salt>$<digest>` ya guarda el número de iteraciones: se
  puede subir a 600.000 y rehashear al iniciar sesión sin romper hashes viejos.
- **«La versión de la cookie puede derivarse del hash».** No: al rehashear en el
  login (260.000 → 600.000) el hash cambia y cerraría todas las sesiones sin
  motivo. La versión debe ser un contador propio.
- **«Bloquear por IP es seguro».** Detrás de un proxy inverso o del NAT de
  Docker, todas las peticiones llegan con la misma IP; un bloqueo duro deja
  fuera también al dueño.

## Adoptar / adaptar / descartar, con motivo

### 1. Middleware `Origen`/`Host`

- **Adoptar: `Sec-Fetch-Site` como señal principal, `Origin`/`Referer` como
  respaldo** (OWASP). En un POST de navegador, `Sec-Fetch-Site: cross-site` se
  rechaza directamente. Como los navegadores no lo envían sobre HTTP plano hacia
  una IP de LAN, el respaldo por `Origin`/`Referer` es obligatorio y lleva su
  propia prueba.
- **Adoptar: comparar por esquema + host + puerto normalizados**, no con
  `startswith`. `Origin` (o `Referer`) se acepta si coincide con el `Host` de la
  petición **o** con `base_url` — detrás de un proxy inverso que no conserva
  `Host` (nginx lo cambia por defecto), `Origin` es el dominio público y `Host`
  el interno, y sin este caso toda la UI daría 403.
- **Adoptar: rechazar `Origin: null`** (sandboxes, redirecciones) y `Referer`
  tipo `example.org.attacker.com` (sufijo engañoso) — la comparación es de
  origen normalizado completo, no de sufijo.
- **Adoptar: en `/ui/*`, si no hay `Origin` NI `Referer`, bloquear** (un
  navegador siempre manda `Origin` en un POST). En `/api/*` se permite la
  ausencia, por los scripts con `curl`/Basic.
- **Adoptar: aplicar también a `/api/*`.** Un formulario cross-site puede enviar
  cuerpos `text/plain`, y OWASP lo cita como vía de CSRF contra APIs.
- **Adoptar (Host): permitir `localhost` y cualquier `Host` que sea una IP
  literal, más los nombres de `base_url` o de un ajuste nuevo.** «Las IP locales
  del equipo» no funciona dentro del contenedor: solo ve sus propias IP, no la
  de la LAN que teclea el usuario (`http://192.168.1.50:8000`). Un ataque de DNS
  rebinding necesita un **nombre de dominio**, no una IP, así que dejar pasar
  las IP literales no lo habilita.
- **Adaptar (cuándo comprobar `Host`): solo con `auth_mode = none`.** Con
  contraseña activa, una página atacante no tiene ni cookie ni credenciales de
  ZascArr, así que la comprobación de `Host` es redundante y añade riesgo de
  bloqueo. Con contraseña queda la comprobación de `Origin`.
- **Adoptar (orden):** el middleware corre **antes** de las rutas exentas de
  autenticación (`/login` está exenta y también es un POST de estado).
- **Descartar:** añadir una dependencia CSRF (p. ej. `starlette-csrf`). Se
  resuelve con stdlib, coherente con CLAUDE.md §2.
- **Ajustar el texto de Ajustes:** hoy dice que `base_url` «no cambia nada»; pasa
  a explicar que participa en la validación de `Origin`/`Host` para quien expone
  ZascArr tras un proxy.
- **Riesgo de bloqueo (detectado en revisión):** quien esté detrás de un proxy
  inverso que no conserve `Host` (nginx lo cambia por defecto) y no haya
  rellenado `base_url` verá `403` en todos los POST — incluido el de Ajustes
  donde se rellena `base_url`, así que no puede arreglarlo desde la interfaz.
  Dos medidas: (a) el `403` se explica en español, con el origen recibido y la
  salida concreta («si accedes tras un proxy, define BASE_URL en el .env»); y
  (b) `BASE_URL` se lee del `.env` (ya lo hace pydantic-settings), como vía de
  recuperación sin interfaz. Nota: el `403` lleva el origen recibido tal cual —
  es una cabecera que manda el cliente, no un secreto, y verla es lo que permite
  diagnosticar; no se registra en logs por defecto.

**Correcciones tras la revisión de la implementación (2026-09-29):**

- **`ALLOWED_HOSTS`** (lista separada por comas en el `.env`): sin ella, quien
  entra por el nombre del equipo (`raspberrypi.local`, `pi`) recibía 403 en
  todo con `auth_mode="none"`. Ahora esos nombres se declaran sin necesidad de
  una URL completa, y el 403 del `Host` (mensaje aparte del de origen) dice el
  nombre recibido y cómo permitirlo.
- **El `Host` se valida en TODOS los métodos**, no solo en los que cambian
  estado: un DNS rebinding permite **leer** (biblioteca, wishlist, ajustes), no
  solo escribir. El healthcheck no necesita excepción porque va por
  `localhost`/`127.0.0.1` (IP literal).
- **IPv6:** el hostname se extrae con `urlsplit("//" + host).hostname`, no con
  `split(":")` — `[::1]:8000` daba `"["` y se rechazaba.
- **Puerto inválido:** `http://x:99999` hacía que `urlsplit(...).port` lanzara
  `ValueError` fuera del `try` → 500. Ahora se captura y el `Origin` se
  rechaza con 403.
- **`Sec-Fetch-Site: same-origin`** se acepta como señal positiva (la calcula
  el navegador, una página no puede falsificarla): cubre el proxy con TLS que
  conserva `Host` pero la app ve por `http` (`Origin` `https://…` vs URL
  `http://…`). Con `auth_mode="none"` la comprobación de `Host` sigue
  aplicándose aparte, porque en un rebinding el navegador también manda
  `same-origin`.
- **`base_url` vacío en la BD no pisa el `BASE_URL` del `.env`**
  (`apply_overrides` lo omite): si un guardado previo de Ajustes dejó
  `base_url=""`, la vía de recuperación del `.env` seguiría funcionando.

**Segunda revisión (2026-09-29):**

- Borrar `base_url` desde Ajustes **no se aplicaba hasta reiniciar**: `apply_overrides`
  lo saltaba y dejaba el valor anterior en memoria (y Ajustes decía «guardado y
  aplicado, sin reiniciar»). Ahora se **restaura la copia del `.env`** tomada al
  arrancar (`capturar_valores_base()` en el `lifespan`), no se ignora.
- Los 403 llevan `Content-Type: text/plain; charset=utf-8` y
  `X-Content-Type-Options: nosniff`, y los valores reflejados van escapados con
  `html.escape` (HTMX intercambia el cuerpo como `innerHTML` aunque sea
  `text/plain`).
- **El 403 se ve con HTMX:** verificado en el `htmx.min.js` vendorizado (v4.0.0,
  `noSwap:[204,304]`) — los 4xx **sí** se intercambian en el `hx-target`, y no hay
  ningún `hx-status` que lo desactive, así que el texto llega a
  `#resultado-seguridad`. No se pudo comprobar en un navegador real desde este
  entorno.

### 2. Autenticación en pasos

- **Paso 1 — `to_thread` y bytes UTF-8.** `verify_password` (PBKDF2) corre en
  `asyncio.to_thread`; `credenciales_validas`/`_basic_auth_valido` pasan a ser
  corrutinas que lo llaman así. El nombre de usuario se compara en bytes:
  `hmac.compare_digest(username.encode(), settings.auth_username.encode())`.
- **Paso 2 — retraso progresivo, no bloqueo duro.** Los fallos se cuentan **por
  cuenta** (no por IP: contar por IP se esquiva rotando direcciones y crece sin
  límite — OWASP) y producen un retraso creciente (con tope) antes de responder,
  en vez de bloquear. Un bloqueo duro dejaría fuera también al dueño; un retraso
  castiga el martilleo sin impedir un login correcto posterior. Los intentos se
  **serializan** para que una ráfaga en paralelo no lo esquive. Ojo: con la cola
  acotada, un ataque sostenido sí puede dejar nuevos logins en 429 (ver
  implementación).
- **Paso 3 — subir a 600.000 y rehashear solo en `/login`.** `hash_password` pasa
  a `600_000`; `verify_password` sigue leyendo las iteraciones del hash
  almacenado (compatibilidad). El rehasheo (260.000 → 600.000) se hace **solo en
  el manejador de `/login`**, que tiene sesión de base de datos; el camino de
  Basic Auth del middleware no rehashea (no tiene dónde persistir).
- **Vincular la cookie a `auth_session_version`.** Un contador que **solo sube
  cuando la persona cambia la contraseña** (no al rehashear): la cookie lo
  incluye y, al cambiarla, las sesiones existentes dejan de valer. `secret_key`
  sigue firmando, pero la validez ya no depende solo de una marca de tiempo.
- **Caché de Basic:** indexada por HMAC de la cabecera `Authorization`, con
  tamaño acotado y **vaciada al cambiar la contraseña**.
- **Corregir `next`:** codificar `next` en el redirect del middleware
  (`urllib.parse.quote`), manteniendo la guarda anti open-redirect de
  `_next_seguro` que ya existe.

**Implementado (2026-09-29) — `auth_session_version`:**

- Vive como `secret_key`: campo interno de `runtime_settings`
  (`_CAMPOS_INTERNOS`), **sin migración**; por defecto 0 y se aplica al arrancar
  con `load_overrides_at_startup`.
- **Sube** al cambiar la contraseña (se escribe una nueva), el nombre de usuario
  o el modo de autenticación. **No sube** en el rehasheo por iteraciones ni al
  guardar sin cambios.
- La cookie pasa a ser `sign_token(f"{emitida_en}.{version}", secret)`; una
  cookie del formato anterior (solo el timestamp) ya no vale — cierre de sesión
  único, anotado en el CHANGELOG.
- El rehasheo (260.000 → las iteraciones actuales) se hace **solo en `/login`**,
  tras validar la contraseña, con `hash_password_async` en el ejecutor propio.
  `guardar_seguridad` también hashea con el ejecutor, no en el bucle de eventos.
- Pruebas: el rehasheo no invalida la sesión; cambiar contraseña/usuario/modo sí;
  dos logins simultáneos que rehashean no se pisan (la versión no se toca, el
  hash final valida la misma contraseña).

**Implementado (2026-09-29) — retraso, caché y tope:**

- **Retraso progresivo por CUENTA** (no por IP), en memoria:
  `min(0.5 · 2^(n-1), 8) s`, ventana de 15 min. OWASP recomienda contar por
  cuenta: contar por IP se esquiva rotando direcciones y crece sin límite.
  ZascArr tiene una sola cuenta, así que el contador es global. Se aplica antes
  de validar en `/login` y en Basic Auth (`intentar_credenciales`), con
  `asyncio.sleep` — no bloquea el bucle, y una credencial correcta entra tras la
  espera y limpia el contador. No es un bloqueo duro, pero tampoco garantiza
  disponibilidad bajo ataque sostenido (ver «cola acotada» abajo). Esto elimina
  `X-Forwarded-For`/`TRUSTED_PROXY` de este mecanismo (y el ajuste se retiró: ya
  no tenía otro uso).
- **Serialización:** un candado (`asyncio.Lock`) cubre el ciclo
  espera→valida→anota, para que una ráfaga en paralelo no lea el contador a la
  vez y esquive el retraso (antes el límite real pasaba a ser el ejecutor).
- **Cola acotada:** como mucho `_INTENTOS_MAX_EN_COLA` (3) intentos en vuelo;
  el resto recibe **429** con `Retry-After` sin encolarse. Ese rechazo **no
  cuenta como fallo**. El dueño con sesión abierta o con Basic en caché no pasa
  por aquí. **Límite honesto:** quien mantenga ocupadas las tres plazas puede
  dejar los nuevos inicios de sesión en 429 de forma sostenida (cada plaza
  espera hasta 8 s + la verificación). El retraso no bloquea por sí mismo, pero
  esto no es una promesa de disponibilidad: la salida es cortar el ataque en el
  cortafuegos o el proxy.
- **Tope del semáforo de PBKDF2:** se adquiere con `asyncio.wait_for` (2 s); si
  no hay hueco, `ColaDeVerificacionLlenaError` → 429. Hay prueba de equilibrio:
  tras muchos timeouts, los dos huecos siguen disponibles.
- **Caché de aciertos de Basic:** clave `HMAC(secret, versión + cabecera)`, TTL
  60 s, máximo 256 entradas (se purga y, si hace falta, se vacía). Solo aciertos;
  un fallo nunca se cachea; cambiar las credenciales la vacía.
- **Longitud mínima de contraseña:** 12 caracteres (< 12 no se guarda; 12-14
  avisa). OWASP recomienda 15 sin segundo factor.

**Pendiente de la ficha (cambio aparte, sin migración):** subir de `260_000` a
`600_000` iteraciones. El hash guarda su contador, así que los hashes viejos
siguen validando y se regeneran al iniciar sesión — no hay migración ni cierre
de sesiones. **Se decide con la medición real en la Pi** (5 veces en reposo y 1
durante una importación): mediana < ~0,8 s → `600_000`; ~1 s o más (o entre 0,8
y 1) → se queda `260_000`, porque con la cola de tres intentos cada verificación
lenta alarga lo que un atacante puede mantener las plazas ocupadas. Queda
registrado aquí con fecha y modelo de Pi cuando se mida.

### 3. Comprobación real de dependencias (respuesta al check rojo)

- **Adoptar:** `pip-audit` como paso de CI (informativo, `continue-on-error`,
  igual que ruff), instalado **solo en CI** — no es dependencia de aplicación.
  Da una señal real de CVEs en dependencias, que hoy no existe: el repositorio
  no tiene ningún análisis de seguridad (`code-scanning/alerts` → «no analysis
  found») y NFR-17 (`pip-audit`/`trivy`) está registrado como `NOT RUN`.
  **Implementado:** job `pip-audit` en `.github/workflows/ci.yml` (informativo),
  y reglas `S` de ruff como paso extra del job de lint. NFR-17 pasa a
  ejecutarse en CI (sigue sin `trivy` de imagen).
- **Descartar por ahora:** `trivy` (escaneo de imagen) y arreglar el escáner de
  IA de GitHub. El escáner de IA falla por «The requested model is not
  supported» (HTTP 400) — fallo de servicio, no señal. Silenciarlo/desactivarlo
  es decisión de configuración del repo, no de código.

## Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi)

- **No mentir:** un check de seguridad que falla sin decir nada no da cobertura;
  por eso entra `pip-audit` con salida real. Los motivos de bloqueo de auth
  (`401`, `403`) dicen la causa, nunca detalles internos.
- **No dejar fuera al dueño:** el retraso progresivo (no bloqueo), el `Host` por
  IP literal y el `Origin` por `base_url` existen para que quien expone ZascArr
  en su LAN o tras un proxy siga entrando.
- **Coste Pi:** el PBKDF2 sale del bucle de eventos (`to_thread`) y se cachea la
  verificación Basic; el límite de fallos y la caché son en memoria, acotados.
- **Sin dependencias nuevas de aplicación:** `pip-audit` vive en CI; el resto es
  stdlib (`hmac`, `hashlib`, `asyncio`, `urllib.parse`).
- **`auth_mode=none` sigue siendo el valor por defecto y no rompe la suite:** el
  middleware sigue siendo no-op cuando no hay autenticación configurada.

## Casos de prueba antes de implementar (deben fallar contra `main`)

1. **Usuario con ñ/acento en `user_password`:** un intento con nombre no-ASCII
   responde 401 (o valida si coincide), nunca 500. *(Falla hoy: `TypeError`.)*
2. **La cookie no sobrevive al cambio de contraseña:** login → cookie válida →
   subir `auth_session_version` (cambio de contraseña) → la cookie es rechazada.
   *(Falla hoy.)*
3. **El rehasheo NO invalida las sesiones:** login con un hash de 260.000 →
   rehasheo a 600.000 → la cookie sigue válida. *(Falla hoy si la versión
   derivara del hash.)*
4. **`next` con `&` no se trunca:** un redirect del middleware para
   `/ui/wishlist?q=a&b=2` produce un `next` que, descodificado, vale
   `/ui/wishlist?q=a&b=2`. *(Falla hoy: se trunca.)*
5. **POST cross-site con `Sec-Fetch-Site` se rechaza** y **`Origin: null` se
   rechaza**. *(Falla hoy.)*
6. **POST con `Origin` ajeno se rechaza;** **`Origin` igual a `base_url` se
   acepta con `Host` distinto** (proxy inverso). *(Falla hoy.)*
7. **`Host` con IP literal se permite; `Host` con nombre ajeno se rechaza**
   (DNS rebinding), con `auth_mode = none`. *(Falla hoy.)*
8. **`Referer` tipo `example.org.attacker.com` no pasa** (comparación de origen
   normalizado, no de sufijo). *(Falla hoy.)*
9. **PBKDF2 sale del bucle de eventos:** monkeypatchea `hashlib.pbkdf2_hmac`
   para registrar el hilo y comprueba que **no es el del bucle de eventos**.
   *(Falla hoy: corre en el bucle.)*
10. **Fallos repetidos desde una IP retrasan pero no impiden** un login correcto
    posterior (retraso progresivo, no bloqueo). *(Falla hoy: no hay retraso.)*
11. **La verificación Basic se cachea** por HMAC de cabecera, tamaño acotado y
    se vacía al cambiar la contraseña. *(Falla hoy.)*
12. **Subir a 600.000 y rehashear solo en `/login`:** `hash_password` usa
    600.000; un hash de 260.000 se regenera a 600.000 **en el flujo de
    `/login`**, no en el camino de Basic. *(Falla hoy.)*
13. **GETs siguen sin cookie/Origin:** un `GET` legítimo (health, estáticos,
    biblioteca) no exige `Origin`. *(No debe romper nada de lo existente.)*

## Orden de commits sugerido

1. Pruebas que fallan contra `main` (1, 2, 4–8, 10) más las estructurales 9, 11
   y 12.
2. Paso 1 (bytes UTF-8 + `to_thread`), que cierra 1 y 9 sin cambiar el coste.
3. Middleware `Origen`/`Host`/`Sec-Fetch-Site` + pruebas 5–8, 13.
4. `auth_session_version` + rehasheo en `/login` + pruebas 2, 3 y 12.
5. Retraso progresivo + caché de Basic + pruebas 10 y 11.
6. `next` codificado + prueba 4.
7. `pip-audit` (y `ruff S` opcional) en CI + texto de Ajustes + nota en
   `docs/BACKLOG.md`.

## Lo que no está verificado

- **El tiempo real del PBKDF2 a 600.000 en la Pi** (OWASP pide < 1 s y avisa del
  agotamiento de CPU): hay que medirlo en la Pi real antes de fijar la cifra.
- **El tamaño real del riesgo CSRF** depende de si el dueño navega con
  `auth_mode=none` y de cuántas webs abre a la vez: no medible aquí.
- **`pip-audit` sobre las dependencias reales del proyecto** aún no se ha
  ejecutado (no está instalado en este entorno); su salida se verá al añadirlo a
  CI.
- **La cifra exacta de OWASP (600.000) y la recomendación de `Sec-Fetch-Site`**
  se citan de la revisión, no re-obtenidas de los enlaces en esta sesión.

## Decisión final / ADR

No requiere ADR (endurecimiento de una pieza existente, sin cambio de
arquitectura). Entregable: middleware `Origen`/`Host` + auth en pasos +
`pip-audit` en CI + las trece pruebas, en una PR separada de la ficha.
