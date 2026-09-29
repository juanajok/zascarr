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
  recomendada para PBKDF2-HMAC-SHA256 es **600.000** iteraciones, no 260.000.
  `https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html`
- **`hmac.compare_digest`** (documentación Python, aportada por la revisión):
  solo admite `str` ASCII o tipos *bytes-like*; con `str` no-ASCII lanza
  `TypeError`. `https://docs.python.org/3/library/hmac.html`
- **Sin referencia comparable verificada** sobre el mecanismo exacto de
  Origen/Host en Sonarr/Radarr/Kavita: no se cita de memoria. El diseño de abajo
  sale del invariante propio («nada de estado sin confirmación explícita del
  dueño») y del patrón estándar de *double-submit*/*Origin check* sin
  dependencias.

## Supuestos que NO valen en ZascArr

- **«`SameSite=Lax` ya cubre CSRF».** Solo si hay cookie; con `auth_mode=none`
  no la hay y el middleware deja pasar todo.
- **«CORS es CSRF».** Son cosas distintas: un `<form>` POST cross-site no se
  bloquea por CORS.
- **«El hash de la contraseña es fijo».** El formato
  `pbkdf2_sha256$<iter>$<salt>$<digest>` ya guarda el número de iteraciones: se
  puede subir a 600.000 y rehashear al iniciar sesión sin romper hashes viejos.
- **«Cambiar la contraseña es suficiente para cerrar sesiones».** No mientras la
  cookie dependa solo de `secret_key` y una marca de tiempo.

## Adoptar / adaptar / descartar, con motivo

### 1. Middleware `Origen`/`Host`, en dos comprobaciones

- **Adoptar:** para los métodos que **cambian estado** (`POST`/`PATCH`/`DELETE`
  /`PUT`), rechazar si `Origin` **o** `Referer` presentes no coinciden con el
  `Host` de la petición. Sin cabecera `Origin`/`Referer` (clientes no
  navegador), se permite — la cookie/Basic ya cubren ese camino.
- **Adoptar:** validar que `Host` está en una lista permitida: `localhost`,
  `127.0.0.1`, las IP locales del equipo y el `base_url` configurado si existe.
  Esto cubre también **DNS rebinding** (un dominio ajeno que resuelve a
  `127.0.0.1` y envía `Host` malicioso).
- **Descartar:** añadir una dependencia CSRF (p. ej. `starlette-csrf`). Se
  resuelve con stdlib y dos `if`, coherente con CLAUDE.md §2 (cada dependencia
  es RAM y superficie).

### 2. Autenticación en tres pasos

- **Paso 1 — `to_thread` y bytes UTF-8.** `verify_password` (PBKDF2) corre en
  `asyncio.to_thread`; `credenciales_validas`/`_basic_auth_valido` pasan a ser
  corrutinas que lo llaman así. El nombre de usuario se compara en bytes:
  `hmac.compare_digest(username.encode(), settings.auth_username.encode())`.
- **Paso 2 — verificar una vez por ventana corta + límite de fallos.** La
  verificación Basic exitosa se cachea por HMAC de la cabecera `Authorization`
  durante una ventana corta (decenas de segundos), para que un script que hace
  N peticiones con las mismas credenciales no pague PBKDF2 N veces. Los fallos
  se cuentan por IP en memoria (sin dependencias ni Redis) y se bloquean pasado
  un umbral.
- **Paso 3 — subir a 600.000 y rehashear al iniciar sesión.** `hash_password`
  pasa a `600_000`; `verify_password` sigue leyendo las iteraciones del hash
  almacenado (compatibilidad con hashes viejos). Al validar correctamente un
  hash con menos iteraciones, se **regenera** con la cifra nueva y se guarda.
- **Vincular la cookie a la versión de credenciales.** La cookie pasa a incluir
  una versión derivada de `auth_password_hash` (o un contador que cambia con la
  contraseña); al cambiarla, las cookies existentes dejan de valer. `secret_key`
  sigue para firmar, pero la validez ya no depende solo de una marca de tiempo.
- **Corregir `next`:** codificar `next` en el redirect del middleware
  (`urllib.parse.quote`), manteniendo la guarda anti open-redirect de
  `_next_seguro` que ya existe.

### 3. Comprobación real de dependencias (respuesta al check rojo)

- **Adoptar:** `pip-audit` como paso de CI (informativo, `continue-on-error`,
  igual que ruff), instalado **solo en CI** — no es dependencia de aplicación.
  Da una señal real de CVEs en dependencias, que hoy no existe: el repositorio
  no tiene ningún análisis de seguridad (`code-scanning/alerts` → «no analysis
  found») y NFR-17 (`pip-audit`/`trivy`) está registrado como `NOT RUN`.
- **Opcional:** reglas `S` de ruff (`--select S`) en modo informativo, para
  detectar patrones peligrosos en el código propio.
- **Descartar por ahora:** `trivy` (escaneo de imagen) y arreglar el escáner de
  IA de GitHub. `trivy` queda como NFR pendiente; el escáner de IA
  (`Code scanning AI findings`) falla por «The requested model is not supported»
  (HTTP 400) — es un fallo de servicio de GitHub, no una señal. Silenciarlo o
  desactivarlo es decisión de configuración del repo, no de código.

## Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi)

- **No mentir:** un check de seguridad que falla sin decir nada no da cobertura;
  por eso entra `pip-audit` con salida real. Los motivos de bloqueo de auth
  (`401`, `403`) dicen la causa, nunca detalles internos.
- **Coste Pi:** el PBKDF2 sale del bucle de eventos (`to_thread`) y se cachea la
  verificación Basic; nada de esto añade RAM relevante (el límite de fallos y la
  caché son en memoria, acotados).
- **Sin dependencias nuevas de aplicación:** `pip-audit` vive en CI; el resto es
  stdlib (`hmac`, `hashlib`, `asyncio`, `urllib.parse`).
- **`auth_mode=none` sigue siendo el valor por defecto y no rompe la suite:** el
  middleware sigue siendo no-op cuando no hay autenticación configurada.

## Casos de prueba antes de implementar (deben fallar contra `main`)

1. **Usuario con ñ/acento en `user_password`:** un intento con nombre no-ASCII
   responde 401 (o valida si coincide), nunca 500. *(Falla hoy: `TypeError`.)*
2. **La cookie no sobrevive al cambio de contraseña:** login → cookie válida →
   cambiar `auth_password_hash` → la cookie es rechazada. *(Falla hoy.)*
3. **`next` con `&` no se trunca:** un redirect del middleware para
   `/ui/wishlist?q=a&b=2` produce un `next` que, descodificado, vale
   `/ui/wishlist?q=a&b=2`. *(Falla hoy: se trunca.)*
4. **POST con `Origin` ajeno se rechaza:** un `POST` a `/ui/ajustes/...` con
   `Origin: https://mal.example` recibe 403. *(Falla hoy: no hay comprobación.)*
5. **`Host` fuera de la lista permitida se rechaza:** petición con
   `Host: atacante.example` recibe 400/403 (cubre DNS rebinding). *(Falla hoy.)*
6. **PBKDF2 sale del bucle de eventos:** `credenciales_validas` delega en
   `asyncio.to_thread` (prueba estructural: no llama a `pbkdf2_hmac`
   directamente en la corrutina). *(Falla hoy.)*
7. **Límite de fallos:** N intentos fallidos desde la misma IP bloquean los
   siguientes durante la ventana. *(Falla hoy: no hay límite.)*
8. **La verificación Basic se cachea:** dos peticiones con la misma cabecera no
   ejecutan PBKDF2 dos veces (contador/monkeypatch). *(Falla hoy.)*
9. **Subir a 600.000 y rehashear:** `hash_password` usa 600.000; un hash de
   260.000 que valida correctamente se regenera a 600.000. *(Falla hoy.)*
10. **GETs siguen sin cookie/Origin:** un `GET` legítimo (health, estáticos,
    biblioteca) no exige `Origin`. *(No debe romper nada de lo existente.)*

## Orden de commits sugerido

1. Pruebas 1–5 y 7 (las que pueden fallar sin tocar la firma de las funciones)
   más la 6 y la 8 estructurales.
2. Paso 1 (bytes UTF-8 + `to_thread`), que cierra 1 y 6 sin cambiar el coste.
3. Middleware `Origen`/`Host` (comprobación doble) + prueba 4 y 5.
4. Paso 3 (600.000 + rehashear al iniciar sesión + cookie versionada) + pruebas
   2 y 9.
5. Límite de fallos + caché de verificación Basic + pruebas 7 y 8.
6. `next` codificado + prueba 3.
7. `pip-audit` (y `ruff S` opcional) en CI + nota en `docs/BACKLOG.md`.

## Lo que no está verificado

- **La cifra exacta de OWASP (600.000)** se cita de la revisión, no re-obtenida
  del enlace en esta sesión; es una recomendación externa y se marcará como tal.
- **El tamaño real del riesgo CSRF** depende de si el dueño navega con
  `auth_mode=none` y de cuántas webs abre a la vez: no medible aquí.
- **`pip-audit` sobre las dependencias reales del proyecto** aún no se ha
  ejecutado (no está instalado en este entorno); su salida se verá al añadirlo a
  CI.

## Decisión final / ADR

No requiere ADR (endurecimiento de una pieza existente, sin cambio de
arquitectura). Entregable: middleware `Origen`/`Host` + auth en tres pasos +
`pip-audit` en CI + las diez pruebas, en una PR separada de la ficha.
