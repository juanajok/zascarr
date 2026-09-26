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

## Deuda de seguridad conocida (A6)

- **La sesión no se invalida al cambiar la contraseña.** La cookie se firma solo con `secret_key`, no con la contraseña, así que una cookie emitida antes de un cambio de contraseña sigue siendo válida hasta que caduca (30 días) o hasta que `secret_key` se regenere. Aceptable para una herramienta de un solo operador en su propia LAN, pero es una de esas sorpresas que alguien descubrirá algún día ("cambié la clave y seguía entrando desde otra pestaña") — que quede escrito. Si algún día importa, cerrar sesión en todas partes = regenerar `secret_key`.
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
- **Backups**: `scripts/backup.sh` verifica cada dump (`gzip -t`) antes de
  darlo por bueno; un backup corrupto nunca se presenta como válido.
