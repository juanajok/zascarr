# ADR 0004: Exposición de red por defecto (solo localhost)

## Estado

Aceptado — 2026-10-01.

## Contexto

Las aplicaciones *arr (Sonarr, Radarr) suelen quedar expuestas en la LAN. Nacieron
como gestores domésticos administrados desde otro equipo o desde el móvil, y su
configuración habitual escucha en todas las interfaces (`*`). En Docker pasa lo
mismo: `ports: - "8000:8000"` publica el puerto en todas las interfaces del host
(`0.0.0.0`), mientras que `ports: - "127.0.0.1:8000:8000"` lo limita al propio
host. **No es una diferencia de la aplicación, sino del valor por defecto
elegido** — y por tanto es una decisión nuestra, no una herencia inevitable.

ZascArr reúne en una sola interfaz operaciones sensibles:

- configuración de Prowlarr, Transmission y aMule;
- lanzamiento y seguimiento de búsquedas y descargas;
- títulos, nombres de fichero y estructura de la biblioteca;
- acciones administrativas: importación, adopción, etiquetado ComicInfo, ajustes
  y desinstalación.

El producto es de **un solo operador**, sin usuarios ni roles, y la autenticación
propia se añadió **después** (A6). Publicar la interfaz en la LAN al instalar
habría dejado todo eso al alcance de cualquier dispositivo de la red.

## Decisión

**Los tres servicios escuchan en `127.0.0.1` por defecto**: la aplicación en el
8000, y Postgres (5432) y Redis (6379), que además **no deben ser alcanzables
desde la red en ningún caso** — no son para el operador, son de la aplicación.

Abrir a la LAN es una acción **explícita** del operador, con un modelo de acceso
escalonado:

1. **Solo esta máquina** (por defecto): nada que configurar.
2. **LAN**: requiere contraseña (A6).
3. **Exterior**: proxy inverso con TLS y `BASE_URL`/`ALLOWED_HOSTS` explícitos.

No se copia el valor por defecto de *arr. La comodidad de administrar desde el
móvil o la tablet se resuelve con una decisión consciente, no con una puerta
abierta por defecto.

## Consecuencias

- **A favor:** es seguro desde la primera instalación, sin configurar nada; quien
  no necesita móvil ni tablet no abre superficie de red jamás.
- **En contra:** usar ZascArr desde otro dispositivo exige un paso extra (cambiar
  la publicación del puerto y activar contraseña). Es el precio aceptado, y está
  escrito para que no sorprenda.
- La decisión **no** impide exponer: se documenta como opción consciente, y A6 ya
  cubre la autenticación y el proxy inverso.
- **Hecho (A11, 2026-10-01):** la elección se ofrece de forma explícita en el
  **instalador** (`bootstrap.sh`, con las funciones de `scripts/_exposicion.sh`),
  no en Ajustes: el puerto publicado es propiedad de Docker en el host y la
  aplicación no puede abrir ni cerrar el suyo. Las dos opciones que abren **exigen
  contraseña, que se fija antes de publicar el puerto**; si no se consigue, no se
  abre nada. Detalle y verificación en
  `docs/design/benchmark-A11-exposicion.md`.

## Referencias

- `docker-compose.yml` — Postgres y Redis fijos en `127.0.0.1`; el de la aplicación
  vale `${ZASCARR_BIND_ADDRESS:-127.0.0.1}` (A11).
- ADR 0001 (`docs/adr/0001-ui-stack.md`) — mismo patrón de decisión.
- A6 y A11 en `docs/BACKLOG.md` — autenticación/reverse proxy y la elección
  explícita pendiente.
