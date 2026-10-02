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
| Entorno | stack de Compose **aislado** (`zascarr-uibase`, app en `127.0.0.1:18000`), ver «Aislamiento» |
| Fuentes tipográficas | las del sistema que hace la captura (Impact no está instalada: la tipografía de cartel cae a la sustituta) |

## Aislamiento: el ensayo NO puede tocar una instalación real

El `docker-compose.yml` del proyecto fija `container_name` (`zascarr-db`, `zascarr-cache`,
`zascarr-orquestador`) y publica los puertos 5432, 6379 y 8000. **Esos nombres son globales en el
daemon de Docker**: un *worktree* y unas carpetas de datos distintas no bastan, y un
`docker stop zascarr-db` o un `docker restart zascarr-orquestador` actuaría sobre la instalación real
si existe. Por eso el ensayo **no usa ninguno de esos nombres**:

| | Producción (compose del proyecto) | Ensayo (`compose.ensayo.yml`) |
|---|---|---|
| Proyecto de Compose | `zascarr` | `zascarr-uibase` (también red e imagen) |
| Contenedores | `zascarr-db`, `zascarr-cache`, `zascarr-orquestador` | `zascarr-uibase-db`, `-cache`, `-app` |
| Puertos publicados | 5432, 6379, 8000 | **ninguno** para Postgres y Redis; **`127.0.0.1:18000`** para la app |
| Datos | `ZASCARR_DATA_DIR` y las carpetas `HOST_*` reales | carpeta **nueva** de ensayo, marcada con `.ui-baseline` |

`ensayo.sh` lo impone, no lo recomienda: antes de arrancar **resuelve el Compose combinado** y aborta si
algún `container_name` es global o no empieza por `zascarr-uibase-`, si algún puerto publicado no es
`127.0.0.1:18000`, si algún montaje cae fuera de la carpeta de ensayo o si la red es global; rechaza
carpetas de datos relativas, dentro del repositorio, bajo `/var/lib/zascarr`, `/opt/zascarr`, `/media`,
`/srv` o `/home/media`, o que existan, no estén vacías y no tengan la marca `.ui-baseline`; y rechaza
arrancar si el puerto 18000 está ocupado o si ya hay un stack de ensayo. **Todas las operaciones sobre
contenedores se hacen con `ensayo.sh dc …`** (que repite esas comprobaciones); el procedimiento no
contiene ningún `docker stop|start|restart <nombre>` global.

**Ruta escrita frente a ruta efectiva** (la misma distinción que A9): `mkdir -p`, `: >` y los montajes
de Docker **siguen los enlaces simbólicos**, así que comparar el texto de una ruta no basta. Antes de
crear ninguna carpeta o marca, `ensayo.sh` rechaza: una `UI_BASE_DATOS` que pase por un enlace; cualquier
subruta que vaya a crearse o montarse (`data`, `lib`, `dl`, la marca…) que sea un enlace —también roto— o
cuyo destino efectivo salga de la carpeta de ensayo; y **cualquier enlace dentro** del entorno (un
`lib/_Unsorted` enlazado haría que `sembrar.py` escribiera fuera). Además, el Compose resuelto se valida
con el destino **real** de cada montaje, no con su texto.

**Un solo ensayo por máquina.** El proyecto `zascarr-uibase` es único: si otra carpeta de datos (otra
sesión, otro *worktree*) tiene su stack en marcha, `preparar` se niega (puerto ocupado / stack existente)
y `dc` y `bajar` comprueban que los montajes del stack vivo cuelguen de **esta** carpeta, o abortan sin
tocarlo. `bajar` valida el Compose resuelto igual que cualquier otra operación antes de ejecutar `down`.
Regresión: `tests/test_ensayo_aislamiento.py` (16 casos, con un `docker` de pega que registra cada
llamada; comprueban qué **no** se ejecuta y qué **no** se escribe fuera: `lib` enlazada a una carpeta
externa no recibe ni marca ni archivos, un Compose no aislado no llega a `down`, un stack ajeno no se
toca).

Las dos herramientas que escriben o hacen `POST` se protegen además por su cuenta:

- `sembrar.py` **se niega a escribir** salvo que se cumplan las tres cosas: `ZASCARR_UI_BASELINE=ensayo`
  en el entorno del contenedor (lo pone `compose.ensayo.yml`), la marca `/media/library/.ui-baseline`
  (la crea `ensayo.sh`) y una **base de datos vacía** (0 series y 0 ficheros).
- `capturar.py` solo acepta un destino local, **rechaza el puerto 8000** y, en la fase con `POST`
  (`principal`), comprueba antes que el servidor contiene los datos sintéticos de `sembrar.py`.

Dentro del ensayo: **fuentes externas de metadatos desactivadas** en Ajustes antes de arrancar la app,
integraciones de descarga desactivadas (por defecto) y sus URL apuntadas a `127.0.0.1:1` (el
contenedor, no el equipo) para que ni se intente tocar un Transmission o un aMule. El aviso legal se
acepta **a mano** durante la captura (con un `POST` real), como lo haría un usuario.

Comprobado antes de publicarlo: los siete rechazos de carpeta de datos (más los de enlaces, arriba), los dos de `sembrar.py` (base
no vacía; sin marca de entorno) y los dos de `capturar.py` (puerto 8000; destino no local); y el
procedimiento completo se **repitió con este stack** (no con el anterior): resultados HTTP y cuerpo del
409 idénticos, y 31 de las 37 capturas idénticas píxel a píxel. De las otras 6, cinco difieren solo en
la hora de «Última comprobación» de `/estado` y una —`pendientes--movil`— en el orden de las tarjetas
(se sembraron todas en una misma transacción, con la misma `imported_at`: probablemente el orden por
`imported_at` es indeterminado entre empates). **Las capturas publicadas son las de esa repetición.**

## Cómo repetirlo

Desde un *worktree* limpio con esta rama (o con `docs/design/ui-baseline/` copiada sobre el commit
`ab49c76`); **no toca tu `.env` ni tus datos** y puede convivir con una instalación real:

```bash
git worktree add --detach /tmp/ui-base <esta-rama> && cd /tmp/ui-base
export UI_BASE_DATOS=/tmp/ui-base-datos          # carpeta NUEVA (se comprueba)
S=docs/design/ui-baseline; U=http://127.0.0.1:18000; OUT=/tmp/ui-base-capturas
$S/ensayo.sh preparar                              # comprueba el aislamiento, levanta y siembra
python3 $S/capturar.py principal $U $OUT           # pantallas, aviso legal y caso 409
$S/ensayo.sh dc stop postgres                      # BD caída con la app EN MARCHA
python3 $S/capturar.py bd-caida-en-marcha $U $OUT
$S/ensayo.sh dc restart zascarr                    # arranque con la BD caída (E6)
python3 $S/capturar.py bd-caida-arranque $U $OUT
$S/ensayo.sh dc start postgres && $S/ensayo.sh dc up -d --force-recreate zascarr
printf '%s\n' "una contraseña de prueba" | $S/ensayo.sh dc run --rm -T zascarr \
    python -m zascarr.cli.seguridad fijar-contrasena
$S/ensayo.sh dc up -d --force-recreate zascarr
python3 $S/capturar.py login $U $OUT
$S/ensayo.sh bajar                                 # al terminar (los datos se quedan en UI_BASE_DATOS)
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

**Alcance de lo medido:** el `500` se observó **en `/ui/` (el panel)**; no se probaron las demás rutas
`/ui/*`. Que las demás se comporten igual es una **deducción** (el único manejador de excepciones de
BD de `main.py` cubre `ProgrammingError` con SQLSTATE `42P01`, no una conexión perdida) y **no está
medida**.

Consecuencia para V3 (fragmento de contadores del menú), como **requisito futuro** y no como medición:
no basta con el caso E6; con htmx 4 **intercambiando** los cuerpos de error, el fragmento debe devolver
`204`/vacío ante cualquier fallo, no solo en modo degradado. Se registra además como **defecto
operativo independiente** (`docs/BACKLOG.md`, «V0: la BD cae con la app en marcha»).

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
