# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
versionado según [SemVer](https://semver.org/lang/es/). Fechas en `AAAA-MM-DD`.

## [1.3.3] — 2026-09-25

### Añadido

- **Tarjetas visuales con portada en `/ui/descubrir`** (reportado con un pantallazo de referencia, estilo Sonarr): cada resultado ahora muestra la portada real, no solo texto. Nuevo proxy `/ui/descubrir/portada` — nunca hotlinking directo del navegador al CDN externo (regla permanente, §3.1.4): valida el host contra una lista blanca por fuente antes de descargar (si no, sería un proxy abierto de imágenes arbitrarias, SSRF real) y cachea en disco por hash de la URL, reutilizando `utils/cover.py` tal cual. Tras crear la serie, la confirmación pasa a usar el cascade de portadas ya existente (`/ui/series/{id}/portada`) en vez del proxy nuevo.

### Corregido

- **AniList dejaba `<br>` literal en la sinopsis** (visible en la propia captura de pantalla que motivó esta mejora) pese a pedir `description(asHtml: false)` — Jinja2 lo escapaba a `&lt;br&gt;` en vez de un salto de línea. Limpiado en el origen (`services/anilist.py`), con test de regresión.

## [1.3.2] — 2026-09-25

### Añadido

- **Grand Comics Database (GCD) como cuarta fuente en `/ui/descubrir`.** Reabre parcialmente ADR-0002: su premisa de 2026-09-23 ("GCD no tiene API pública") ya no es cierta — verificado en vivo, GCD publica una API REST anónima en `/api/`, datos bajo CC BY-SA 4.0 (atribución + enlace de vuelta, ya cumplido por el enlace a la ficha original). No cambia el alcance del enricher (B4 sigue igual: esa API no trae sinopsis ni portada a nivel de serie). Nueva columna `series.gcd_id` (migración `0010`).
- **Aviso visible cuando una fuente no participó en la búsqueda**, reportado ("sospecho que no está entrando en Comic Vine a buscar"): antes, sin `COMICVINE_API_KEY` configurada, Comic Vine se saltaba en silencio — indistinguible de "no hay resultados". Ahora `/ui/descubrir` muestra el motivo explícito.

### Corregido

- **GCD devolvía HTML en vez de JSON** (`Expecting value: line 5 column 1`), encontrado en la primera verificación en vivo del cliente nuevo: sin la cabecera `Accept: application/json`, Django REST Framework (lo que usa GCD) sirve su interfaz navegable HTML. Corregido añadiendo la cabecera; parseo envuelto en su propio manejo de errores, mismo criterio que Tebeosfera.

## [1.3.1] — 2026-09-25

### Añadido

- **Enlace a la ficha original en cada resultado de `/ui/descubrir`**, reportado tras la primera prueba en vivo: buscar "Thorgal" devuelve 10 ediciones españolas distintas (Distrinovel 1981, Zinco 1986, varias sub-colecciones de Norma) y no había forma de confirmar cuál era cuál antes de darla de alta. Cada resultado lleva ahora un enlace "↗" a su página real (Tebeosfera/Comic Vine/AniList, se abre en pestaña nueva) — no es hotlinking de imagen, es un enlace de texto de salida, igual que una cita. Comic Vine añade `site_detail_url` al `field_list` que ya pedía; AniList se construye con su patrón de URL estable (`anilist.co/manga/{id}`); Tebeosfera reutiliza el `href` real ya extraído del HTML.

## [1.3.0] — 2026-09-25

### Añadido

- **Descubrir y dar de alta series desde fuentes externas (C0)** — nueva pantalla `/ui/descubrir`, enlazada desde la navegación. Cierra un círculo vicioso real de producto, confirmado en una instalación nueva: con la tabla `series` vacía, Wishlist no tenía nada que buscar y el importador mandaba todo a `_Unsorted` aunque el nombre del archivo se extrajera perfecto — no eran bugs de ninguno de los dos, faltaba el paso de alta que los alimenta a ambos.

  `DiscoveryService` reutiliza los mismos clientes que ya usa el enricher (Comic Vine, AniList, Tebeosfera) solo para buscar — nunca los toca para nada de descarga —, con búsqueda concurrente y tolerante a que una fuente falle. Al elegir un candidato se crea la `Series` local (tradición editable, año, portada, descripción, ID externo) sin duplicar si ya existía; "Añadir a deseados" reutiliza tal cual el endpoint de wishlist ya existente, con su aviso legal intacto — dar de alta una serie en sí mismo NO lo exige, porque catalogar metadatos no es una acción de riesgo.

  Sin hotlinking en los resultados de búsqueda (solo texto hasta que la serie existe y el cascade de portadas ya existente entra en juego). Verificado en vivo contra Postgres real y una búsqueda real a Tebeosfera (sin API key): alta de una serie confirmada en la base de datos y visible de inmediato en la búsqueda local de Wishlist.

## [1.2.9] — 2026-09-25

### Cambiado

- **Las migraciones de Alembic ya no corren en el host — corren dentro del contenedor.** `bootstrap.sh` hacía `pip install --break-system-packages --ignore-installed -e .` y `alembic upgrade head` directamente sobre el Python del sistema de la Pi — origen de la clase de bugs más cara de esta sesión (conflicto `typing_extensions` de Debian/apt, M3, v1.2.2). Ahora: `docker compose build zascarr` (explícito, antes de migrar) seguido de `docker compose run --rm zascarr alembic upgrade head` — nada de pip en el host, `DATABASE_URL` lo resuelve el propio `docker-compose.yml` desde `.env` igual que para el servicio real (por nombre `postgres`, no `127.0.0.1`, eliminando de paso el parseo manual de `DB_PASSWORD` del `.env`, M6). El chequeo de "Python 3.11 o superior" en el host **desaparece entero**: ya no hace falta ningún Python fuera del contenedor.

  Verificado en Docker-en-Docker: instalación completa de punta a punta en un host **sin Python 3 instalado en ningún momento** (`command -v python3` confirmado ausente antes, durante y después del bootstrap) — migraciones (`0001` → `0009`) aplicadas dentro del contenedor, app arrancada y sana. Suite completa sin regresiones (262 tests).

## [1.2.8] — 2026-09-25

### Corregido

- **"Estado" seguía sin migas de pan y con un look distinto al resto de la app** tras el fix de v1.2.7 (que solo le añadió un enlace de vuelta): reportado de nuevo por un usuario. Causa real: era un fichero estático (`static/dashboard.html`) fuera de `base.html`, con su propio CSS inline y su propia paleta de colores — el enlace de vuelta no arreglaba la inconsistencia visual ni daba navegación real. Convertido en una vista Jinja2 más (`web/estado.py` + `templates/estado.html`), con el mismo `topnav` (que hace de navegación consistente en las 4 pantallas) y las mismas clases/tokens de `web.css` que el resto de la app — mismo `fetch()` a `/api/health` de siempre, sin JS nuevo. `static/dashboard.html` eliminado (muerto).

### Añadido

- **Parser de nombres de archivo (`naming.py`) ampliado para releases en español (CRG y similares)**, tras los 14 archivos reales de un usuario que quedaron en `_Unsorted` por no extraerse ni título ni número: tags de release entre corchetes (`[CRG]`, `[MQ]`, `[DI]`, `[ML]`) ahora se limpian como ruido (antes solo se limpiaba ruido entre paréntesis); líneas editoriales de reedición delante del nombre real ("Marvel Gold - La Patrulla-X Original 1.cbr") ya no se confunden con el título; "Omnigold N"/"Integral N"/"Edición Integral N" se reconocen como marcador de tomo; y un número suelto de 1-3 cifras al final del nombre (sin "#", sin "T", sin año) ya no se pierde. Alcance deliberadamente acotado a la extracción sintáctica (Fase 1 de un diseño en 3 fases): el matcher sigue sin crear series nuevas ni asignar con baja confianza — con la BD vacía, estos archivos seguirán en `_Unsorted`, correctamente, hasta que exista una `Series` con la que comparar (ver **C0** en `docs/BACKLOG.md`). Fases 2 (sugerencia con confirmación) y 3 (alias aprendidos localmente) quedan registradas como **B12**/**B13**, no implementadas en esta pasada. 8 fixtures existentes sin regresión + 4 nuevas con los nombres reales.

## [1.2.7] — 2026-09-25

### Corregido

- **"Estado" (E1) era un callejón sin salida — sin navegación, sin forma de volver.** Reportado por un usuario: es un fichero estático fuera de `base.html`/la barra de navegación a propósito (página única sin dependencias, ver docstring de `dashboard()`), pero eso significaba que quien entraba ahí se quedaba sin cómo salir salvo el botón "atrás" del navegador. Añadido un enlace "← Volver a la biblioteca" (`src/zascarr/static/dashboard.html`).
- **`http://.../` mandaba a Estado en vez de a la biblioteca.** La raíz servía directamente el panel de semáforos técnico (E1) — quien entra por primera vez espera ver su colección, no un panel de estado. Ahora `/` redirige (307) a `/ui/` (Biblioteca); Estado se muda a su propia URL, `/estado`, enlazada desde la navegación.

## [1.2.6] — 2026-09-25

### Corregido

- **Reejecutar `bootstrap.sh` tras un `git pull` (manual o autoactualizado) nunca aplicaba el código nuevo si el contenedor ya existía.** `docker compose up -d zascarr` sin `--build` reutiliza la imagen ya construida — Compose solo construye sola cuando la imagen todavía no existe. Encontrado mientras se preparaba la instrucción de actualización de v1.2.5: la recomendación de "haz `git pull` y vuelve a correr `bootstrap.sh`" dada para v1.2.4 no habría aplicado ese fix en una instalación ya existente. Corregido con `up -d --build zascarr`. Verificado en Docker-en-Docker: instalación limpia, luego un cambio de versión simulado + `git commit` + reejecución de `bootstrap.sh` sin tocar nada a mano — el contenedor queda con el código nuevo.

## [1.2.5] — 2026-09-25

### Corregido

- **`PermissionError: [Errno 13]` al importar tebeos reales, en cada archivo, siempre.** El contenedor corre fijo como UID 1000 desde el `Dockerfile`, pero `ZASCARR_USER` (por defecto `media`, desde v1.2.0) es un usuario de **sistema** creado con `useradd --system` — Debian le asigna el UID que tenga libre en su rango, casi nunca 1000. El importador podía **copiar** el archivo a la biblioteca (lectura vía "otros", el `.cbr` tiene `-rw-rw-r--`) pero no **borrar el original** en descargas: borrar exige permiso de escritura en el directorio, y ese directorio (`rwxrwsr-x`, propiedad de `media:media`) no se lo da a "otros". Confirmado en vivo contra la Pi real del usuario (usuario `media` con UID 996 en su sistema) — cada uno de sus 15 `.cbr` reales fallaba igual.

  Arreglo estructural, mismo patrón que usa toda imagen *arr de LinuxServer.io (**PUID/PGID**): `docker-entrypoint.sh` (nuevo) ajusta el UID/GID internos del contenedor en cada arranque con `usermod`/`groupmod` y baja privilegios con `runuser` antes de ejecutar la app — nunca corre como root. `bootstrap.sh` resuelve `PUID`/`PGID` automáticamente a partir del UID/GID real de `ZASCARR_USER`/`ZASCARR_GROUP` (`id -u`/`getent group`) y los escribe en `.env`; el coleccionista no tiene que saber qué es un UID. Los `chown` que ya hacía el instalador sobre sus propios directorios (subcarpetas nuevas de biblioteca, `covers`, descargas si las crea él) pasan de `1000:1000` fijo al UID/GID resuelto.

  Sin dependencia nueva: `usermod`/`groupmod` (paquete `passwd`) y `runuser` (paquete `util-linux`) ya vienen en `python:3.11-slim-bookworm`.

  Verificado en Docker-en-Docker desde cero: usuario de sistema `media` (UID 996/GID 995, igual que en la Pi real) dueño de una carpeta de descargas con los permisos exactos del caso real; tras el bootstrap, `/proc/<pid>/status` del proceso real de `uvicorn` confirma `Uid: 996 Gid: 995` (no root, no 1000); el `.cbr` de prueba se importa y el original desaparece de descargas sin error. Suite completa sin regresiones (257 tests).

## [1.2.4] — 2026-09-25

### Corregido

- **Bug de diseño real: el `.env` vive en `ZASCARR_ROOT` (el padre del
  repo), pero Docker Compose por defecto solo busca `.env` en el
  directorio desde el que se invoca** — cualquier `docker compose ...`
  manual ejecutado dentro del repo, sin `--env-file` explícito, lo
  ignoraba en silencio y arrancaba con los valores por defecto de
  `docker-compose.yml` (incluida la contraseña de la BD). Así es como un
  `docker compose down/up zascarr` manual dejó un contenedor real en
  bucle de reinicio. Arreglo estructural, no solo documentación:
  `bootstrap.sh` ahora crea un symlink `SCRIPT_DIR/.env -> ZASCARR_ROOT/.env`
  (no versionado, recreado en cada ejecución) para que el descubrimiento
  **por defecto** de Compose ya encuentre el `.env` real sin que nadie
  tenga que acordarse de `--env-file`; `scripts/_comun.sh` lo
  autorrepara en cada uso por si se pierde. Verificado en sandbox:
  `docker compose config` sin `--env-file` resuelve ya la contraseña
  real, no la de fábrica.
- **Ese symlink, a su vez, destapó un bug latente**: en cuanto
  `Settings()` empezó a ver el `.env` real (antes, ejecutándose con cwd
  en el repo, nunca lo encontraba), `pydantic-settings` reventaba con
  `Extra inputs are not permitted` — las variables de infraestructura
  del `.env` (`HOST_LIBRARY_DIR`, `ZASCARR_DATA_DIR`, `APP_LOCALE`, `TZ`)
  no son campos de `Settings`, y su comportamiento por defecto es
  rechazarlas, no ignorarlas. Corregido con `extra="ignore"` en
  `Settings.model_config` (`src/zascarr/config.py`): esas variables las
  consume `docker-compose.yml`, no la app Python.
- **`HOST_DOWNLOADS_DIR`/`HOST_AMULE_INCOMING_DIR` añadían `/downloads`
  y `/aMule/Incoming` a la ruta que daba el usuario**, asumiendo que
  siempre sería una raíz genérica para organizar debajo. Un usuario con
  Transmission/aMule ya apuntando sus descargas reales a esa carpeta (el
  caso normal, no la excepción — así lo reportó un usuario con ~15GB de
  cómics reales sin detectar) se encontraba con una subcarpeta nueva y
  vacía en vez de sus archivos. Ahora se usa la ruta exacta que da el
  usuario, tal cual, para las dos — el importador ya escanea de forma
  recursiva y no necesita subcarpetas concretas.
- **Ese mismo cambio expone un caso normal, no un edge case: si
  descargas y aMule comparten disco (una sola respuesta a la pregunta
  de descargas), el mismo archivo aparece bajo `/media/downloads` y
  `/media/incoming` — dos bind-mounts distintos del mismo inodo — y el
  importador lo escaneaba dos veces por ciclo**; la segunda pasada
  fallaba porque el archivo ya se había movido en la primera
  (`errores=1` confuso en cada ciclo, sin pérdida de datos pero
  ruidoso). La deduplicación existente comparaba rutas resueltas
  (`Path.resolve()`), que no detecta dos bind-mounts distintos del mismo
  disco; ahora compara `(st_dev, st_ino)` (`services/importer.py`).
  Regresión: `tests/test_importer.py::TestScanDedupePorInodo`
  (hard-link real entre dos directorios, sin symlinks, para reproducir
  el bind-mount).

Verificación: contenedor Docker-en-Docker desde cero (Debian 12, sin
Docker/git preinstalados, usuario `pi` con sudo real) — instalación
completa de punta a punta con un `.cbr` puesto directamente en la
carpeta de descargas (sin subcarpeta), confirmado `importer.imported
dest=.../\_Unsorted/... status=unsorted` en los logs del orquestador;
suite completa (257 tests, 20 skips esperados) sin regresiones.

## [1.2.3] — 2026-09-24

### Corregido

- **Reinvocar el instalador (`curl | sudo bash` de nuevo, o `sudo bash
  bootstrap.sh` directo sobre el clon ya existente) nunca traía las
  correcciones publicadas** — el script reutilizaba el clon en disco tal
  cual, sin actualizarlo, así que cualquiera que reintentara tras un fallo
  se quedaba viendo el mismo error ya corregido en GitHub, para siempre.
  Confirmado en vivo por un usuario: tres reintentos seguidos del bug de
  `typing_extensions` (ya corregido en v1.2.2) porque su clon en
  `/opt/zascarr/zascarr` nunca se actualizaba. Ahora el instalador se
  autoactualiza (fetch + merge `--ff-only`, el mismo patrón seguro que
  `scripts/update.sh`) tanto si se reinvoca desde cero como si se
  reejecuta el script ya clonado directamente — si hay una versión nueva,
  se reinicia solo con ella.
- **Esa autoactualización habría fallado en silencio por "dubious
  ownership"**: los `git` de `bootstrap.sh` corren como `root`, pero el
  repo pertenece a `media` (v1.2.0) — git rechaza tocar un repo de otro
  propietario salvo que se autorice explícitamente
  (`git config --global --add safe.directory`), igual que ya resolvían
  `scripts/update.sh`/`rollback.sh`. Corregido en el mismo commit que la
  autoactualización, antes de que llegara a publicarse sin esto.

## [1.2.2] — 2026-09-24

### Corregido

- **El instalador se paraba en "Corriendo migraciones Alembic..." en
  Raspberry Pi OS real** con `error: uninstall-no-record-file — Cannot
  uninstall typing_extensions... installed by debian`. Raspberry Pi OS trae
  paquetes Python instalados vía `apt` (sin fichero `RECORD` de pip); al
  intentar actualizarlos, `pip install -e .` aborta en vez de instalar por
  delante. Corregido con `--ignore-installed` (deuda **M3** en
  `docs/BACKLOG.md`: el parche mínimo es este flag, el cierre de fondo es
  mover la migración a un contenedor efímero en vez de instalar en el
  host).
- El mensaje de error de ese mismo paso, si aun así falla, ahora incluye
  el `cd` al directorio correcto — antes decía "ejecuta a mano" sin más,
  y ejecutarlo desde el directorio equivocado (p.ej. el `$HOME` del
  usuario) daba un segundo error distinto y confuso ("neither setup.py
  nor pyproject.toml found").

## [1.2.1] — 2026-09-24

### Corregido

- **El instalador fallaba en cascada si el shell que lo invocaba tenía un
  `cwd` borrado bajo los pies** (reportado por un usuario en una Raspberry
  Pi real: `cd ~/zascarr` + `rm -rf ~/zascarr` en el mismo terminal —
  exactamente lo que este mismo proyecto recomienda para reintentar una
  instalación fallida). `getcwd()` falla para cualquier proceso que lo
  resuelva en ese estado; reproducido en sandbox: no solo `git clone`
  abortaba (`fatal: Unable to read current working directory`), el propio
  instalador oficial de Docker también fallaba en cada paso (`sh: 0:
  getcwd() failed`). Corregido con un `cd /tmp` al principio del script,
  antes de cualquier otra cosa, para no heredar un `cwd` inválido del
  proceso padre.

## [1.2.0] — 2026-09-24

### Cambiado

- **Rutas de instalación coherentes con el resto de la suite *arr**
  (Sonarr/Radarr/Prowlarr...), a petición de un usuario que ya los tiene
  instalados así. Antes ZascArr vivía en el `HOME` del usuario que ejecutaba
  `sudo`; ahora:
  - **Código** en `ZASCARR_ROOT` (por defecto `/opt/zascarr`).
  - **Datos** de los contenedores (Postgres, Redis, portadas, estado VPN)
    en `ZASCARR_DATA_DIR`, **separados del código** (por defecto
    `/var/lib/zascarr`) — antes vivían mezclados dentro de `ZASCARR_ROOT`.
  - **Propietario** `ZASCARR_USER`/`ZASCARR_GROUP` (por defecto `media`,
    creado como usuario de sistema si no existe), no el usuario personal
    que invocó `sudo`.
  - Las tres son variables de entorno que se pueden fijar antes de instalar
    (`export ZASCARR_ROOT=... && curl ... | sudo -E bash`) para quien
    prefiera otra convención.
  - Verificado que Postgres/Redis no se ven afectados por este cambio: sus
    contenedores arrancan como root y se autocorrigen el propietario de su
    propio directorio de datos, así que el `chown` del host a `media` no
    interfiere. `config/covers` (y la biblioteca del usuario) siguen fijos
    en `uid 1000`: los escribe el contenedor de ZascArr, que corre como ese
    usuario sin privilegios para autocorregirse — restricción técnica, no
    parte de la convención `media`.

## [1.1.1] — 2026-09-24

### Corregido

- **El instalador de un solo comando rompía las 3 preguntas en instalación
  real** (reportado por un usuario en una Raspberry Pi limpia, reproducido
  en sandbox antes de corregir). Tras `curl -fsSL .../bootstrap.sh | sudo
  bash`, el proceso hace `exec` hacia el script ya clonado para continuar —
  pero heredaba el `stdin` original, que todavía podía tener restos sin
  consumir del propio código fuente del script (bash lee el pipe de curl
  por bloques). El primer `read` (la pregunta del idioma) se tragaba esos
  restos como si fueran la respuesta del usuario — en el caso real, un
  comentario del propio `bootstrap.sh` — y el `sed` posterior reventaba con
  `unknown option to 's'`. Corregido reconectando `stdin` a `/dev/tty`
  antes de relanzarse.

## [1.1.0] — 2026-09-24

### Añadido

- **Instalación de un solo comando de verdad**:
  `curl -fsSL .../bootstrap.sh | sudo bash` instala `git` y Docker si
  faltan, crea la carpeta de trabajo en el `HOME` del usuario real (no en
  `/root`), clona el repo y continúa con la configuración habitual — antes
  eran 3 pasos manuales (instalar Docker, `git clone`, `bootstrap.sh`), y
  el usuario tenía que teclear `git clone` sin que nadie le explicara qué
  es `git`.

### Corregido

- **`bootstrap.sh` fallaba en toda instalación real desde cero** en el
  paso de migraciones: la comprobación `python3 -c "import alembic"` daba
  siempre positivo (aunque `pip install` nunca se hubiera ejecutado) porque
  el cwd en ese punto es la raíz del repo, que tiene su propia carpeta
  `alembic/` (las migraciones) — Python la confundía con el paquete
  instalado. Corregido a `command -v alembic`. Encontrado y verificado
  ejecutando `bootstrap.sh` de verdad por primera vez, no solo el camino
  vía contenedor que ya se había probado en la 1.0.0.

### Cambiado

- **Renombrada toda la infraestructura de `tebeoteca` a `zascarr`**
  (proyecto Docker Compose, contenedores, red, base de datos, variable
  `TEBEOTECA_ROOT` → `ZASCARR_ROOT`): resto del nombre original del
  proyecto ("Tebeoteca Digital", anterior a SecuenciArr y a ZascArr) que
  sobrevivió a los dos renames previos sin que nadie lo tocara. Se hace
  ahora, el mismo día del primer release, porque no hay instalaciones
  reales todavía — después habría sido un cambio incompatible con
  `update.sh`.

## [1.0.0] — 2026-09-24

Primera release estable. Backend e interfaz web funcionales y verificados
end-to-end contra Docker + PostgreSQL reales (no solo contra la suite
unitaria con `FakeSession`) — ver `docs/TESTING_E2E.md` y
`docs/TESTING_NFR_Zascarr.md` para el runbook completo, y `docs/BACKLOG.md`
para el detalle de cada hallazgo y su corrección.

### Añadido

- **Instalador de un solo comando** (`bootstrap.sh`): 3 preguntas, sin
  terminal ni JSON para el usuario final; errores mapeados a causa y acción
  en español llano.
- **Importador automático**: organiza `/downloads` con matcher fuzzy
  (`pg_trgm`) y deduplicación por SHA256; nunca borra el original hasta
  verificar la copia (A3).
- **Enriquecimiento multi-fuente**: Comic Vine (grapa americana/británica),
  AniList (manga/manhwa/manhua), Tebeosfera (tebeo español/franco-belga),
  con caché negativa y rate limits corteses.
- **Biblioteca web** con filtros por tradición, editorial, personaje y saga;
  portadas en cascada (CBZ → URL externa cacheada → placeholder), **sin
  hotlinking**.
- **Ficha de serie con huecos** (`missing`) y **bandeja de pendientes**
  (clasificación manual con un clic).
- **Wishlist + orquestador**: búsqueda en cascada (Prowlarr → foro
  opcional), descarga vía Transmission/aMule, cierre automático del círculo
  "descargado → en tu biblioteca", con cooldown y reintento de candidato.
- **Dashboard de estado** con semáforos en español sobre `/api/health`.
- **Blindaje legal**: wizard de aceptación (`/ui/legal`) que custodia solo
  las acciones de riesgo (búsqueda/descarga); integraciones P2P
  deshabilitadas por defecto; `LEGAL.md` versionado por hash de contenido.
- **Backup + restore automatizados**: `scripts/backup.sh` (dump atómico
  verificado, con retención) y el ciclo `scripts/update.sh` /
  `scripts/rollback.sh` (referencias de rescate en git, backup obligatorio
  antes de cada actualización, `dropdb --force` + `ON_ERROR_STOP=1` en el
  rollback, verificación de esquema tras restaurar).

### Corregido (release-blocking, encontrado y cerrado el 2026-09-24)

Los cuatro hallazgos siguientes se encontraron en la primera ejecución real
de `docs/TESTING_E2E.md`/`docs/TESTING_NFR_Zascarr.md` contra Docker y
PostgreSQL reales — ninguno era visible en la suite unitaria porque ninguno
tiene cobertura de integración contra Docker/Postgres reales:

- **El `Dockerfile` no compilaba nunca**: el stage `builder` ejecutaba
  `pip install .` antes de copiar `src/` (layout `src`). Bloqueaba
  cualquier build desde el primer commit del repo.
- **El importador fallaba al 100%** con el `docker-compose.yml` real: dos
  bugs independientes — `safe_move()` no manejaba `EXDEV` entre bind mounts
  distintos con el mismo `st_dev`, y `HOST_DOWNLOADS_DIR`/
  `HOST_AMULE_INCOMING_DIR` estaban montados `:ro` (el importador necesita
  borrar el origen tras copiar, A3).
- **La restauración de cualquier backup fallaba siempre**: `pg_dump` vacía
  `search_path` en el restore, y `f_title_norm()` llamaba a `f_unaccent()`
  sin cualificar el esquema (migración `0009_fix_title_norm_search_path`).
  Verificado con el ciclo destructivo completo `update.sh` → `rollback.sh
  --forzar` con una conexión PostgreSQL concurrente abierta.
- **`GET /api/health` tardaba 60-90s** cuando Transmission/aMule no
  respondían rápido (llamadas secuenciales con timeout de 30s cada una),
  provocando `unhealthy` casi permanente en Docker. Ahora corren en
  paralelo con timeout de 3s.

### Conocido — deuda documentada, no bloqueante para este release

- **Sin autenticación (Épica A6, P1, pendiente).** ZascArr no tiene login ni
  contraseña. El modo por defecto (`127.0.0.1` únicamente, sin publicar en
  la LAN) es seguro sin ella, pero **cualquier despliegue accesible desde
  fuera de la Pi necesita un reverse proxy con su propia autenticación**
  delante — ver [`SECURITY.md`](SECURITY.md).
- Sin ejecutar por tiempo/recursos en esta pasada: carga sintética a escala,
  20 ciclos de restart, concurrencia/doble-procesamiento real, abuso con
  peticiones simultáneas, escaneo de dependencias/imagen (`trivy`/
  `pip-audit`), y portabilidad ARM64 explícita (validado en x86_64; el
  target de producción es Raspberry Pi 4/5, sin probar en este release).
  Detalle completo en `docs/BACKLOG.md`.
- 10 historias P1/P2 abiertas sin afectar al camino principal (desinstalar
  sin restos, escritura de `ComicInfo.xml`, detección de borrados manuales,
  toggle runtime de fuentes, marcar leído/puntuar, listas de lectura,
  completar serie con un botón, colecciones, novedades semanales, webhook
  de aviso) — ver `docs/BACKLOG.md` para el detalle y prioridad de cada una.
