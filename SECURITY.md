# Política de seguridad

ZascArr es una herramienta de **un solo operador**, pensada para correr en
tu propia Raspberry Pi. No implementa usuarios, roles ni autenticación
(Épica A6 del backlog, pendiente) — el aislamiento se apoya en no exponerla
fuera de tu red.

## Postura por defecto

- El contenedor solo publica `127.0.0.1:8000` en el host (`docker-compose.yml`).
  Sin acción explícita tuya, ZascArr **no es alcanzable** desde tu LAN ni
  desde internet.
- PostgreSQL y Redis publican en `127.0.0.1`, nunca en `0.0.0.0`.
- Las integraciones P2P (Prowlarr, Transmission, aMule, foro) nacen
  **desactivadas** y piden activación explícita.

## Si quieres acceder desde fuera de la Pi

**No publiques el puerto 8000 a tu LAN o a internet sin autenticación
delante.** Pon un reverse proxy (Caddy, nginx, Traefik) con su propia
autenticación (Basic Auth, OAuth, lo que prefieras) por delante de ZascArr.
Sin eso, cualquiera con la URL puede leer tu biblioteca, activar
integraciones de descarga y disparar búsquedas.

Cerrar esto de forma nativa (login/contraseña en la propia app) es la
historia **A6** del backlog (`docs/BACKLOG.md`), priorizada P1 y aún sin
construir a fecha de este release.

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
