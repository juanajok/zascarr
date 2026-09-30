# Política de seguridad

ZascArr es una herramienta de **un solo operador**, pensada para correr en
tu propia Raspberry Pi. No implementa usuarios ni roles — un único par de
credenciales para toda la instalación, sin más ambición que esa (Épica
**A6**, hecha).

## Postura por defecto

- **Sin contraseña de fábrica** (`auth_mode="none"`): el aislamiento por
  defecto sigue siendo no exponer el puerto, igual que antes de A6 — activar
  una contraseña es una decisión tuya desde `/ui/ajustes` → Seguridad, nunca
  algo que la instalación te obligue a configurar de entrada.
- El contenedor solo publica `127.0.0.1:8000` en el host (`docker-compose.yml`).
  Sin acción explícita tuya, ZascArr **no es alcanzable** desde tu LAN ni
  desde internet.
- PostgreSQL y Redis publican en `127.0.0.1`, nunca en `0.0.0.0`.
- Las integraciones P2P (Prowlarr, Transmission, aMule, foro) nacen
  **desactivadas** y piden activación explícita.

## Si quieres acceder desde fuera de la Pi

Activa una contraseña en `/ui/ajustes` → Seguridad antes de publicar el
puerto 8000 en tu LAN o en internet — "Solo contraseña" o "Usuario y
contraseña", a elegir. La contraseña se guarda como hash PBKDF2-SHA256
(nunca en claro) y protege tanto la interfaz web (cookie de sesión, 30
días) como la API (HTTP Basic Auth, para `curl`/scripts). `/api/health`
queda exenta a propósito, para que un healthcheck de Docker o de
monitorización externa no necesite credenciales.

Sigue siendo buena práctica poner un reverse proxy (Caddy, nginx, Traefik)
delante si expones ZascArr fuera de tu LAN — TLS de verdad es su trabajo,
no el de esta contraseña —, pero ya no es la ÚNICA capa: sin activar nada
aquí, cualquiera con la URL puede leer tu biblioteca, activar integraciones
de descarga y disparar búsquedas.

**Condición para el proxy inverso:** ZascArr rechaza las peticiones que
cambian estado (`POST`/`PUT`/`PATCH`/`DELETE`) cuyo `Origin`/`Referer` no
coincida con su propio `Host` ni con `base_url` — es la defensa CSRF, porque
con `auth_mode="none"` no hay cookie que valga. Un proxy que **no conserve
`Host`** (nginx lo cambia por defecto) hace que `Origin` sea tu dominio
público y `Host` el interno, y sin nada más recibirías **403 en todos los
POST**, incluido el de Ajustes. Define `BASE_URL` en el `.env` (o en
Ajustes) con tu dominio público — es una de las vías pensadas para recuperar
el acceso sin depender de la interfaz. El 403 explica en español el origen
recibido y esta misma salida.

**Si entras por el nombre del equipo** (`raspberrypi.local`, `pi`, …) con
`auth_mode="none"`, añádelo a `ALLOWED_HOSTS` (lista separada por comas en el
`.env`): con la contraseña desactivada el middleware valida el `Host` en
**todas** las peticiones — también los `GET` —, porque un DNS rebinding
permitiría *leer* tu biblioteca o tus ajustes, no solo escribirlos. Se aceptan
siempre `localhost`, cualquier IP literal (IPv4 o IPv6) y el host de
`base_url`.

**Proxy con TLS que sí conserva `Host`:** si tu Caddy/nginx termina el TLS y
reenvía a ZascArr por HTTP interno, el navegador manda `Sec-Fetch-Site:
same-origin` (una cabecera que calcula el navegador y una página no puede
falsificar) y el middleware la acepta como señal positiva, así que no hace
falta `BASE_URL` para ese caso. Con `auth_mode="none"` la comprobación de
`Host` sigue aplicándose de todos modos — en un rebinding el navegador también
manda `same-origin`.

## Deuda de seguridad conocida (A6)

- **La cookie viaja sin `Secure`, decidido a propósito.** Con `secure=True` el navegador no enviaría la cookie por HTTP plano y el login en la LAN dejaría de funcionar, así que sin TLS activado rompería el caso de uso principal. Es la decisión correcta hoy, pero es deuda deliberada: cuando ZascArr viva tras un reverse proxy con TLS de verdad, ese flag debería activarse (o hacerse condicional a `base_url` empezando por `https://`). Entra de oficio con la futura historia de reverse proxy.

## Reportar una vulnerabilidad

Abre un [security advisory privado](https://github.com/juanajok/zascarr/security/advisories/new)
en GitHub, o escribe a **juanajok@gmail.com**. No abras un issue público
para vulnerabilidades sin parchear.

Al reportar, incluye: versión afectada, pasos para reproducir, y el
impacto que ves (qué se puede leer, modificar o ejecutar).

## Qué SÍ está cubierto por diseño

- **Mass assignment**: todos los endpoints de escritura usan esquemas
  Pydantic con `extra="forbid"` — un campo no declarado en el body se
  rechaza con `422`, nunca se cuela al ORM.
- **Sin hotlinking**: las portadas siempre se sirven desde caché local o
  extracción del propio CBZ, nunca `src` externo directo.
- **XSS**: las plantillas Jinja2 escapan por defecto; `|safe` solo se usa
  para el Markdown del propio `LEGAL.md`, ya controlado.
- **CORS**: sin middleware CORS — UI y API viven en el mismo origen, cero
  peticiones cross-origin legítimas.
- **La sesión se cierra al cambiar las credenciales.** La cookie lleva, firmado,
  un `auth_session_version` que sube al cambiar la contraseña, el usuario o el
  modo de autenticación: las cookies emitidas antes dejan de valer y hay que
  volver a entrar. El rehasheo por subida de iteraciones **no** sube la versión
  (no debe cerrar sesiones a quien ya está dentro). Las cookies del formato
  anterior (sin versión) caducan al actualizar — un único inicio de sesión.
- **CSRF / Origen / Host**: las peticiones que cambian estado se rechazan con
  `403` si `Sec-Fetch-Site: cross-site`, si `Origin: null`, o si `Origin`/
  `Referer` no coinciden (esquema+host+puerto normalizados) con el `Host` de la
  petición ni con `base_url`. En `/ui/*` se bloquea además cuando no hay ni
  `Origin` ni `Referer` (un navegador siempre manda `Origin` en un POST); en
  `/api/*` se permite su ausencia, para scripts con `curl`/Basic. `Sec-Fetch-Site:
  same-origin` se acepta como señal positiva (cubre el proxy con TLS). Con
  `auth_mode="none"` se valida el `Host` en **todos** los métodos — un rebinding
  permite leer, no solo escribir — aceptando `localhost`, IP literal, el host de
  `base_url` y los nombres de `ALLOWED_HOSTS`.
- **Backups**: `scripts/backup.sh` verifica cada dump (`gzip -t`) antes de
  darlo por bueno; un backup corrupto nunca se presenta como válido.
