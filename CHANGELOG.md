# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/),
versionado según [SemVer](https://semver.org/lang/es/). Fechas en `AAAA-MM-DD`.

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
