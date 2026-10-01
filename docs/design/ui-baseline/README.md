# Línea base de la UI actual (V0)

Capturas **reproducibles** de la UI tal como está, **sin modificarla**, para comparar antes/después en
la Épica V (`docs/BACKLOG.md`) y para comprobar con datos —no con suposiciones— cómo se comporta
htmx 4 y `/estado`. Inventario asociado: `docs/design/ui-migracion.md`.

## Qué se capturó, y sobre qué

| Dato | Valor |
|---|---|
| Código de la aplicación | `main` en `ab49c76` (ZascArr **1.15.1** + A11; `/api/health` → `"version": "1.15.1"`). La rama de esta PR solo añade documentación encima. |
| Navegador | Google Chrome **154.0.8037.92**, *headless*, por el protocolo CDP (`capturar.py`). **No** es el Chromium de la Pi (V13 lo pide aparte). |
| Escritorio | viewport **1280 × 800** |
| Móvil | viewport **390 × 844** con `mobile=true` (emulación de *viewport*; no es un móvil real ni cambia el agente de usuario) |
| Zoom | **100 %** (factor de escala del dispositivo 1) |
| Tema | claro (todas las pantallas) y **oscuro** (panel, Pendientes, Estado, Ajustes y login, en escritorio), con `prefers-color-scheme` emulado |
| Captura | página completa (hasta 6.000 px de alto); los pasos del caso 409 son del *viewport* |
| Datos | **sintéticos** (`sembrar.py`): 3 series inventadas, 6 pendientes, 5 deseados, un duplicado exacto en disco. Nada procede de la biblioteca de nadie. |
| Fuentes tipográficas | las del sistema que hace la captura (Impact no está instalada: la tipografía de cartel cae a la sustituta) |

Aislamiento: Postgres y Redis propios en contenedores con el *compose* del repo; **fuentes externas de
metadatos desactivadas** en Ajustes antes de arrancar la app (`sembrar.py`), integraciones de
descarga desactivadas (por defecto) y sus URL apuntadas a `127.0.0.1:1` para que ni siquiera se
intente tocar un Transmission o un aMule del equipo. El aviso legal se acepta **a mano** durante la
captura (con un `POST` real), como lo haría un usuario.

## Cómo repetirlo

Desde un *worktree* limpio en el commit inventariado (no toca tu `.env` ni tus datos):

```bash
git worktree add --detach /tmp/ui-base ab49c76 && cd /tmp/ui-base
B=/tmp/ui-base-datos; mkdir -p $B/data/{postgres,redis,covers,vpn-state} $B/lib $B/dl
cat > $B/.env <<EOT
DB_PASSWORD=linea_base_local_no_usar
ZASCARR_DATA_DIR=$B/data
HOST_LIBRARY_DIR=$B/lib
HOST_DOWNLOADS_DIR=$B/dl
HOST_AMULE_INCOMING_DIR=$B/dl
PUID=$(id -u)
PGID=$(id -g)
TZ=Europe/Madrid
APP_LOCALE=es
FORUM_ENABLED=false
TRANSMISSION_URL=http://127.0.0.1:1
AMULE_URL=http://127.0.0.1:1
PROWLARR_URL=http://127.0.0.1:1
EOT
DC="docker compose --env-file $B/.env"
$DC build zascarr && $DC up -d postgres redis
$DC run --rm -T zascarr alembic upgrade head
$DC run --rm -T zascarr python - < docs/design/ui-baseline/sembrar.py    # siembra + desactiva fuentes
$DC up -d zascarr
```

(El *worktree* debe tener también `docs/design/ui-baseline/` de esta rama: cópialo o usa la rama.)

```bash
S=docs/design/ui-baseline; U=http://127.0.0.1:8000; OUT=/tmp/ui-base-capturas
python3 $S/capturar.py principal $U $OUT          # pantallas, aviso legal y caso 409
docker stop zascarr-db                             # BD caída con la app EN MARCHA
python3 $S/capturar.py bd-caida-en-marcha $U $OUT
docker restart zascarr-orquestador                 # arranque con la BD caída (E6)
python3 $S/capturar.py bd-caida-arranque $U $OUT
docker start zascarr-db && $DC up -d --force-recreate zascarr
printf '%s\n' "una contraseña de prueba" | $DC run --rm -T zascarr python -m zascarr.cli.seguridad fijar-contrasena
$DC up -d --force-recreate zascarr
python3 $S/capturar.py login $U $OUT
```

`capturar.py` solo necesita `google-chrome` y el paquete `websockets` del Python del sistema; **no es
parte del paquete ni añade ninguna dependencia al proyecto**. Cada fase escribe `datos-<fase>.json`
con lo observado (versión del navegador, respuestas HTTP, HTML antes y después).

## Resultados que importan

### 1. Caso 409 (colisión de ediciones al asignar) — hipótesis de V0 **confirmada**

Se asigna con «Sí, es esta» el archivo `Los Guardianes del Alba Omnigold 12 [CRG].cbz` (un ómnibus)
a la serie que ya tiene un nº 12 **como grapa**. Observado en `datos-principal.json`:

| | |
|---|---|
| Petición | `POST /ui/pendientes/{id}/asignar` con `series_id` e `issue_number=12` (prellenado) |
| Respuesta | **`409`**, `content-type: application/json`, cuerpo `{"detail":"El número 12 ya existe en esta serie como otra edición (single_issue) — número compartido entre ediciones. El archivo '…Omnigold 12 [CRG].cbz' se queda en Pendientes sin asignar."}` |
| Intercambio de htmx 4.0.0 | **se intercambia el cuerpo del error** (la tarjeta tenía `hx-swap="outerHTML"`) |
| Lo que queda visible | **la tarjeta desaparece y en su sitio aparece el JSON en crudo**, como texto suelto en la primera columna de la rejilla (`caso-409-2-despues…png`, `caso-409-3-despues-pagina…png`) |
| Estado real | correcto: el archivo **no se movió**, sigue sin `issue` y la BD guarda el motivo (`review_motivo`: «número compartido entre ediciones»; comprobado en la BD). Por el código de `pendientes.html`, al recargar la tarjeta vuelve mostrando ese motivo; **no se recargó en esta captura**. |

Es decir: **el servidor se comporta bien y la interfaz lo muestra mal** (el coleccionista ve
`{"detail": …}` donde estaba su archivo y puede creer que lo ha perdido). Hoy lo mismo ocurre con
cualquier `4xx`/`5xx` de las rutas `hx-*` que no devuelvan un fragmento. **No se ha corregido aquí**
(esta PR no toca producción): la decisión de diseño está en V6b (el lote no depende de
`HTTPException`) y conviene un arreglo propio de la ruta individual.

### 2. `/estado` con la BD caída — conserva su función de diagnóstico

| Situación | `/estado` | `/api/health` | `/ui/` |
|---|---|---|---|
| BD caída, app **ya en marcha** | `200`, la página y su sondeo funcionan; «Error · Base de datos, Transmission, aMule, VPN» | `200` | **`500`** con el cuerpo `Internal Server Error` (texto plano) |
| BD caída, app **arrancada así** (E6) | `200`, igual | `200` | **`503`** «Base de datos no lista … Consulta el estado del sistema» |

Consecuencia para V3 (fragmento de contadores del menú): **no basta con el caso E6**. Con la BD caída
y la app en marcha un `/ui/*` responde un `500` de texto plano, y htmx 4 **intercambia** los cuerpos
de error: el fragmento debe devolver siempre `204`/vacío ante cualquier fallo, no solo en modo
degradado (ver los criterios de V3).

### 3. Otras observaciones

- `GET /login` con la autenticación **desactivada** responde `307` (redirige); el login solo se ve con
  contraseña activada, por eso su captura es la última fase.
- Con la autenticación activada, `/ui/` sin sesión responde `303` a `/login?next=%2Fui%2F`.
- `/api/health` da `"status": "degraded"` en este entorno (Transmission y aMule sin conectar a
  propósito): es el estado esperado de la línea base, no un fallo.
- Las portadas sintéticas son 400×600 generadas con Pillow: el aspecto de las tarjetas con portada
  (grandes, coloreadas) es del dato de prueba, no de la UI.

## Índice de capturas

Nombre: `<pantalla>--<escritorio|movil>-<ancho>x<alto>-<claro|oscuro>.png`.

| Pantalla | Ruta |
|---|---|
| `panel` | `/ui/` |
| `biblioteca` | `/ui/biblioteca` |
| `ficha-de-serie` | `/ui/series/{id}` |
| `descubrir` | `/ui/descubrir` |
| `pendientes` | `/ui/pendientes` |
| `deseados-sin-aviso-legal` / `deseados` | `/ui/wishlist` antes / después de aceptar el aviso legal |
| `mi-biblioteca` | `/ui/auditoria` |
| `ajustes` | `/ui/ajustes` |
| `estado` | `/estado` |
| `aviso-legal-asistente` / `aviso-legal-texto` | `/ui/legal` y `/legal` |
| `login` | `/login` (con contraseña activada) |
| `caso-409-1-antes`, `-2-despues`, `-3-despues-pagina` | colisión al asignar (§1) |
| `bd-caida-en-marcha-*`, `bd-caida-arranque-*` | `/estado` y `/ui/` con la BD caída (§2) |

## Límites

- Una sola pasada, un solo navegador y un solo equipo; **no sustituye la verificación en la Pi** (V13).
- El móvil es emulación de *viewport*, sin pantalla táctil real ni el Chromium de la Pi.
- Los datos son sintéticos y pequeños; no dicen nada del rendimiento con 1.500 archivos.
- Las capturas **fijan lo que hay hoy**, defectos incluidos; no son un modelo de lo deseable.
