# ZascArr

**Orquestador inteligente de tebeoteca digital.** Un gestor automatizado de
bibliotecas de cómics y tebeos, inspirado en Sonarr/Radarr, pensado para
coleccionistas **hispanohablantes** y diseñado para correr en una
**Raspberry Pi 4/5**.

![Licencia](https://img.shields.io/badge/licencia-GPL--3.0--only-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Estado](https://img.shields.io/badge/estado-1.5.0-brightgreen.svg)

> ⚠️ **Aviso legal (postura Sonarr-style).** ZascArr es una herramienta
> **neutra** para gestionar tu biblioteca personal de tebeos: organiza,
> enriquece y completa el contenido que ya posees o tienes derecho a usar.
> **No incluye fuentes, indexadores ni enlaces de descarga por defecto**;
> cada integración (Prowlarr, Transmission, aMule, foros) nace desactivada y
> se activa de forma explícita y bajo tu responsabilidad. ZascArr **no
> distribuye ni facilita** contenido protegido por derechos de autor.
> Lee [`src/zascarr/LEGAL.md`](src/zascarr/LEGAL.md) antes de usarlo.

> 🔒 **Sin autenticación.** ZascArr no tiene login ni contraseña propios —
> por defecto solo escucha en `127.0.0.1`, lo cual es seguro sin ella, pero
> **si lo publicas en tu LAN o en internet, pon un reverse proxy con
> autenticación delante**. Detalle en [`SECURITY.md`](SECURITY.md).

---

## ¿Qué es?

Para **"El Coleccionista"**: alguien con cientos o miles de CBZ/CBR mezclando
grapa americana, manga y clásicos Bruguera, que quiere su colección ordenada,
enriquecida y completa — sin saber qué es Docker, PostgreSQL ni un indexador.
La interfaz web **es** el producto, no un extra.

El diferencial frente a [Kapowarr](https://github.com/Casvt/Kapowarr) y
[Mylar3](https://github.com/mylar3/mylar3): fuentes honestas de tebeo español
([Tebeosfera](https://www.tebeosfera.com) / Gran Catálogo de la Historieta)
y descarga por **eD2K** ([aMule](https://www.amule.org)) además de torrent.

## Estado del proyecto

✅ **v1.5.0.** Backend e interfaz web funcionales, verificados end-to-end
contra Docker + PostgreSQL reales (no solo la suite unitaria) — importador,
wishlist/orquestador, portadas, puerta legal, backup y el ciclo completo de
actualización/rollback destructivo. Detalle de la verificación en
[`CHANGELOG.md`](CHANGELOG.md) y `docs/TESTING_E2E.md`.

Queda deuda conocida y no bloqueante — sobre todo la falta de autenticación
propia (ver el aviso de seguridad arriba) — documentada en
[`docs/BACKLOG.md`](docs/BACKLOG.md), que sigue siendo el backlog canónico
del producto.

## Características

- **Importador automático** — organiza tu carpeta de descargas con matcher
  fuzzy (pg_trgm) y deduplicación por SHA256, con informe legible de cada ciclo.
- **Enriquecimiento multi-fuente** — enruta cada serie a su fuente según la
  tradición: Comic Vine (grapa americana/británica), AniList
  (manga/manhwa/manhua) y Tebeosfera (tebeo español / franco-belga), con caché
  negativa para no quemar rate limits.
- **Biblioteca web con filtros** — navega por tradición, editorial, personaje
  y saga, con portadas por cascada (primera página del CBZ → portada externa
  cacheada → placeholder) y **sin hotlinking** a CDNs externos.
- **Ficha de serie con huecos** — de un vistazo, qué números te faltan de cada
  serie.
- **Bandeja de pendientes** — clasifica con un clic lo que el sistema no supo
  identificar: "es esta serie" o "ignorar".
- **Wishlist estilo Sonarr** — marca una serie y olvídate: el orquestador busca
  (Prowlarr → Transmission/aMule), descarga e importa en bucle, con reintento
  automático del siguiente candidato y cierre del círculo
  "descargado → en tu biblioteca".
- **Dashboard de estado** — semáforos en español: VPN, disco, servicios.
- **Backup automático** — volcado de PostgreSQL a disco externo con retención.
- **Puerta legal** — wizard de aceptación que solo custodia las acciones de
  riesgo (búsqueda/descarga), no el resto de la aplicación.

## Stack

Python 3.11+ · **FastAPI** (async end-to-end) · SQLAlchemy async + asyncpg ·
**PostgreSQL 15** · Redis · Alembic · **Jinja2 + HTMX** (vendorizado, sin SPA
ni Node) · structlog.

La UI es server-side (Jinja2 + HTMX), siguiendo el
[ADR-0001](docs/adr/0001-ui-stack.md). Docstrings y textos de interfaz en
español.

## Requisitos

- **Raspberry Pi 4/5** (o cualquier Linux) con **Raspberry Pi OS (64-bit)** y
  conexión a internet. Docker y git se instalan solos si faltan; no necesitas
  saber qué son.
- Para desarrollo: **Python 3.11+**.

Opcional, fuera de Docker (baremetal): Transmission, aMule, Prowlarr y Kavita.

## Instalación

Pensada para **"El Coleccionista"**: no hace falta entender qué es Docker,
git ni una terminal más allá de pegar una línea. Un único comando deja todo
listo:

```bash
curl -fsSL https://raw.githubusercontent.com/juanajok/zascarr/main/bootstrap.sh | sudo bash
```

Instala git y Docker si te faltan, crea un usuario de servicio `media`
(igual que Sonarr/Radarr/Prowlarr si ya los tienes — código en `/opt`,
nunca mezclado con tu usuario personal), descarga ZascArr en
`/opt/zascarr/zascarr`, y te hace **3 preguntas** (pulsa `Intro` para
aceptar lo que va entre corchetes):

1. ¿Dónde están tus tebeos ya organizados?
2. ¿Dónde caen tus descargas (Transmission/aMule)?
3. ¿Idioma de la interfaz? (`es`/`en`)

Al terminar, ZascArr ya está funcionando. Ábrelo en:

**http://127.0.0.1:8000** — el panel de estado, en español.

Puedes volver a ejecutar `sudo bash /opt/zascarr/zascarr/bootstrap.sh`
cuando quieras: es idempotente (no duplica nada) y nunca toca los archivos
de tu colección.

> **¿Ya tienes el resto de la suite *arr en otra ruta?** El código va en
> `ZASCARR_ROOT` (por defecto `/opt/zascarr`), los datos de los
> contenedores en `ZASCARR_DATA_DIR` (por defecto `/var/lib/zascarr`), y el
> propietario en `ZASCARR_USER`/`ZASCARR_GROUP` (por defecto `media`).
> Cambia lo que necesites antes de instalar:
> ```bash
> export ZASCARR_ROOT=/opt/Zascarr ZASCARR_DATA_DIR=/var/lib/zascarr ZASCARR_USER=media ZASCARR_GROUP=media
> curl -fsSL https://raw.githubusercontent.com/juanajok/zascarr/main/bootstrap.sh | sudo -E bash
> ```

### Si prefieres revisar el script antes de ejecutarlo

Es buena práctica desconfiar de `curl | bash` a ciegas. Descárgalo y léelo
primero:

```bash
curl -fsSL -o bootstrap.sh https://raw.githubusercontent.com/juanajok/zascarr/main/bootstrap.sh
less bootstrap.sh          # revísalo
sudo bash bootstrap.sh
```

### Paso a paso, sin el comando único

Si prefieres controlar cada paso tú mismo (o ya tienes git y Docker):

```bash
sudo apt-get install -y git                       # si no lo tienes
curl -fsSL https://get.docker.com | sudo sh        # si no tienes Docker
sudo useradd --system --no-create-home --shell /usr/sbin/nologin media   # si no lo tienes

sudo mkdir -p /opt/zascarr && cd /opt/zascarr
sudo git clone https://github.com/juanajok/zascarr.git
sudo chown -R media:media /opt/zascarr
sudo bash zascarr/bootstrap.sh
```

### Qué hace el instalador

- Crea el usuario de servicio `media` si no existe, y deja el código y los
  datos a su nombre — no al tuyo personal ni a `root`.
- Crea la estructura de carpetas de la biblioteca (`Comics`, `Manga`, `BD`,
  `Tebeos`, …) **sin tocar tus archivos**.
- Levanta PostgreSQL, Redis y ZascArr como contenedores Docker.
- Aplica las migraciones de la base de datos y comprueba que todo está sano.

### Instalación manual (para quien prefiera Docker Compose)

El `.env` real vive en el **padre** del repo (`ZASCARR_ROOT`, `/opt/zascarr`
por defecto), no junto a `docker-compose.yml` — así el reset de código de un
rollback nunca puede tocarlo por accidente. Docker Compose, por defecto,
solo busca `.env` en el directorio desde el que se invoca — sin esto, un
`docker compose up -d` a secas ejecutado dentro del repo lo ignoraría en
silencio y arrancaría con los valores por defecto (incluida la contraseña
de la BD): exactamente el fallo real que dejó un contenedor en bucle de
reinicio la primera vez que alguien lo hizo así.

El instalador ya deja resuelto esto con un enlace simbólico
(`zascarr/.env -> ../.env`, no versionado) para que el descubrimiento por
defecto de Compose encuentre el `.env` real sin tener que acordarse de
`--env-file` cada vez. Si instalaste con `bootstrap.sh`, esto ya existe;
en una instalación manual desde cero, créalo tú mismo:

```bash
cp ../.env.example ../.env     # ajusta HOST_*_DIR y DB_PASSWORD
ln -sf ../.env .env            # una vez — Compose ya lo encontrará solo
docker compose up -d
docker compose run --rm zascarr alembic upgrade head
```

## Uso

| Qué | Dónde |
|---|---|
| Dashboard / estado | `http://127.0.0.1:8000` |
| Biblioteca / wishlist / pendientes | `http://127.0.0.1:8000` (navegación web) |
| API (OpenAPI/Swagger) | `http://127.0.0.1:8000/api/docs` |
| Comandos | `make help` (`logs`, `migrate`, `health`, `backup`, …) |

## Actualizar ZascArr

Cuando haya una versión nueva, ejecuta el script de actualización desde donde
instalaste ZascArr:

```bash
cd /opt/zascarr/zascarr     # o la carpeta donde clonaste el repo
sudo bash scripts/update.sh
```

El script hace, **en este orden** (el orden importa):

1. Comprueba Docker, Compose, git, curl y gzip, y que el árbol del repo esté limpio.
2. **Copia de seguridad de PostgreSQL** (obligatoria, atómica, verificada y con retención).
3. Actualiza el código con `git fetch` + `merge --ff-only` (si la rama ha divergido, aborta sin tocar la BD).
4. Reconstruye la imagen Docker (las dependencias viven en la imagen, no en el host).
5. Aplica las migraciones **dentro del contenedor** (`alembic upgrade head`).
6. Reinicia ZascArr y verifica el healthcheck en `http://127.0.0.1:8000`.

Antes de tocar nada, el script deja **dos cosas emparejadas**: una referencia de
git (`refs/zascarr/update/<fecha>`) apuntando al commit anterior, y el dump
`update_<la-misma-fecha>.sql.gz`. Esa pareja es la que usa el rollback, y **no se
borra al terminar bien**: si la actualización fue bien pero la app va rara tres
días después, el ancla sigue ahí. Las referencias cuyo dump ya ha caducado por
la retención se podan solas, así que no se acumulan sin límite.

> **Tiempo estimado:** 2-5 minutos. En una Raspberry Pi el paso 4 (rebuild de la
> imagen) puede tardar más, porque compila dependencias nativas.

### Si algo va mal (rollback)

Un rollback **no es solo cambiar el código**: si la actualización aplicó
migraciones nuevas, hay que restaurar también la base de datos, o el esquema
nuevo y el código viejo quedarán desacompasados. Está automatizado:

```bash
cd /opt/zascarr/zascarr
sudo bash scripts/rollback.sh              # añade --dry-run para ver el plan sin tocar nada
```

Qué hace:

1. Empareja el commit y el backup por la referencia que dejó `update.sh`. **No**
   coge «el backup más reciente»: `backup.sh` corre a diario a las 04:00, así que
   el más reciente puede tener ya el esquema nuevo y entonces no revertiría nada.
2. Comprueba que el árbol del repo está limpio (no descarta cambios locales sin
   avisar) y enseña el plan pidiendo confirmación (hay que escribir `SI`).
3. Hace **su propia copia de seguridad de la base de datos actual**
   (`rollback-safety_<fecha>.sql.gz`), por si el dump elegido no fuera el que creías.
4. Para ZascArr, comprueba que el dump es un gzip íntegro, lo restaura con
   `psql -v ON_ERROR_STOP=1` y verifica que la base de datos resultante es una
   BD de ZascArr de verdad (tablas `series`, `files`, `wishlist` y revisión de
   Alembic), no un HTTP 200 cualquiera del healthcheck.
5. Vuelve el código al commit anterior —dejando antes una referencia para poder
   **deshacer el rollback**—, vacía la caché de Redis, reconstruye y arranca.
   Verifica el healthcheck.

Si el commit al que vuelve es anterior a la existencia de `rollback.sh`, el
`reset` borra el script del repo: por eso guarda una copia en
`/tmp/zascarr-rollback-<fecha>.sh` y su ruta aparece en el informe final.

Opciones: `--sha <SHA>`, `--backup <ruta.sql.gz>`, `--dry-run`, `--yes` (para
automatizar) y `--forzar` (repetir un rollback ya hecho o descartar cambios
locales sin guardar — ambos destructivos a propósito).

### Restaurar a mano (plan B)

Si prefieres hacerlo tú, o el script no puede seguir, esto es lo que hace por
dentro:

```bash
cd /opt/zascarr/zascarr
COMPOSE="docker compose -f docker-compose.yml --env-file ../.env"

# 1. Copia de la base de datos ACTUAL antes de destruirla. No te la saltes.
$COMPOSE exec -T postgres pg_dump -U comics_admin zascarr | gzip > /tmp/antes.sql.gz
gzip -t /tmp/antes.sql.gz        # si falla, PARA: ese fichero no te vale

# 2. Comprobar el dump que vas a restaurar ANTES de borrar nada
gzip -t /var/backups/zascarr/postgres/update_AAAAMMDD_HHMMSS.sql.gz

# 3. Levantar la base de datos, vaciarla y restaurar
$COMPOSE up -d postgres
$COMPOSE exec -T postgres dropdb -U comics_admin --if-exists --force zascarr
$COMPOSE exec -T postgres createdb -U comics_admin zascarr
gunzip -c /var/backups/zascarr/postgres/update_AAAAMMDD_HHMMSS.sql.gz | \
  $COMPOSE exec -T postgres psql -q -v ON_ERROR_STOP=1 -U comics_admin zascarr

# 4. Volver al commit anterior, limpiar la caché y reconstruir
git reset --hard <SHA-anterior>
$COMPOSE exec -T redis redis-cli FLUSHDB
$COMPOSE build zascarr && $COMPOSE up -d zascarr
```

Dos detalles que no son opcionales: `psql` **sin** `ON_ERROR_STOP=1` devuelve
éxito aunque fallen sentencias sueltas (te quedaría una restauración a medias
con cara de haber ido bien), y `dropdb --force` evita el fallo típico de
«database is being accessed by other users» (necesita PostgreSQL 13+, que es el
que fija este repo). El `FLUSHDB` de Redis es seguro aquí porque Redis es
exclusivo de ZascArr (`zascarr-cache` en el compose); no copies ese patrón a
un Redis compartido con otras aplicaciones.

### Copia de seguridad manual

El script ya hace una automáticamente antes de actualizar. Si quieres una extra
en cualquier momento, usa el script de backup del proyecto (atómico y con
retención):

```bash
BACKUP_DIR=/var/backups/zascarr/postgres bash scripts/backup.sh
```

## Integraciones (todas opcionales y desactivadas por defecto)

| Tipo | Integración | Activación |
|---|---|---|
| Metadatos | [Comic Vine](https://comicvine.gamespot.com/api/) | clave de API desde `/ui/ajustes` (o `COMICVINE_API_KEY` en `.env`) |
| Metadatos | [AniList](https://anilist.co) | pública, sin clave |
| Metadatos | [Tebeosfera](https://www.tebeosfera.com) | scraping, sin clave |
| Metadatos | [GCD](https://www.comics.org) | pública, sin clave |
| Descarga | [Prowlarr](https://prowlarr.com) | URL + clave de API desde `/ui/ajustes` |
| Descarga | [Transmission](https://transmissionbt.com) | URL + usuario/contraseña desde `/ui/ajustes` |
| Descarga (eD2K) | [aMule](https://www.amule.org) | URL de amuleweb + contraseña desde `/ui/ajustes` |

No hay ninguna fuente preconfigurada: activar una integración es siempre una
decisión explícita del usuario. Los rate limits por fuente son conservadores y
los fallos de scraping degradan a "sin resultado" en vez de tumbar el ciclo.
Cada integración de descarga tiene un botón "Probar conexión" en `/ui/ajustes`
antes de guardar.

**Prowlarr/Transmission/aMule corren en la propia Raspberry Pi ("baremetal"),
fuera de Docker** — el contenedor los alcanza vía `host.docker.internal`. Si
"Probar conexión" falla con "no se pudo conectar" aunque la URL/credenciales
sean correctas, hay tres causas habituales — comprueba las tres:

1. **`host.docker.internal` puede resolver a la red de Docker equivocada.**
   Bug real de Docker, confirmado con datos reales: el valor mágico
   `host-gateway` (usado en `docker-compose.yml`) a veces resuelve a la
   puerta de enlace del puente **por defecto** (`docker0`) en vez de a la
   de la red **personalizada** que de verdad usa el contenedor de ZascArr
   (`docker-compose` siempre crea una propia) — dos redes Docker distintas,
   con gateways distintos. Desde v1.4.4, el propio contenedor se
   autocorrige esto en el arranque (`docker-entrypoint.sh`), así que si
   vienes de una versión anterior, un `git pull` + reinstalación basta.
   Puedes confirmarlo tú mismo:
   ```bash
   docker exec zascarr-orquestador getent hosts host.docker.internal
   docker inspect zascarr-orquestador --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
   ```
   Las dos IPs deben coincidir. Si no coinciden y ya estás en v1.4.4+, revisa
   `docker logs zascarr-orquestador` por si el arranque falló antes de
   llegar a corregirlo.

2. **Un cortafuegos (`ufw`/`iptables`) con reglas limitadas a tu LAN.** Si
   tienes reglas tipo "solo 192.168.1.0/24" para esos puertos (patrón
   habitual si ya proteges el resto de la suite *arr así), el puente de
   Docker no cuenta como LAN y la conexión se descarta antes de llegar al
   servicio — **esta fue una de las causas reales, confirmada**, en la
   primera instalación que lo reportó. Compruébalo con:
   ```bash
   sudo ufw status
   ```
   Y si hace falta, añade una regla que cubra cualquier red Docker del host
   (más robusta que apuntar a una subred exacta, que puede cambiar si
   Docker reasigna redes):
   ```bash
   sudo ufw allow from 172.16.0.0/12 to any port 9696 proto tcp comment 'Prowlarr desde Docker'
   sudo ufw allow from 172.16.0.0/12 to any port 9091 proto tcp comment 'Transmission desde Docker'
   sudo ufw allow from 172.16.0.0/12 to any port 4711 proto tcp comment 'aMule desde Docker'
   sudo ufw reload
   ```
   (`172.16.0.0/12` cubre todo el rango que Docker usa para sus redes por
   defecto — más robusto que una subred exacta tipo `172.17.0.0/16` o
   `172.18.0.0/16`, que puede cambiar si Docker reasigna redes).

3. **El servicio escucha solo en `127.0.0.1`, no en `0.0.0.0`.** El menos
   habitual de los tres, pero compruébalo también:
   ```bash
   ss -tlnp | grep -E ':9696|:9091|:4711'   # Prowlarr / Transmission / aMule
   ```
   Si ves `127.0.0.1:<puerto>` en vez de `0.0.0.0:<puerto>` o `*:<puerto>`,
   cámbialo en la configuración propia de ese servicio.

## Desarrollo

```bash
pip install -e ".[dev]"
pytest -x        # suite autosuficiente, sin Docker ni PostgreSQL
make lint
make format
```

La suite de tests es autosuficiente (`FakeSession` + `dependency_overrides`);
no levanta Docker ni PostgreSQL. Solo `tests/test_title_norm.py` toca
PostgreSQL real y se salta si no hay `TEST_DATABASE_URL`.

## Estructura del repositorio

```
src/zascarr/
  api/        # endpoints REST (/api/*)
  web/        # interfaz Jinja2 + HTMX (/ui/*)
  services/   # lógica de negocio (importer, enricher, orquestador, …)
  core/       # matcher y triage de importación
  models/     # ORM SQLAlchemy
  schemas/    # contratos Pydantic
  utils/      # naming, portadas, ComicInfo
  LEGAL.md    # aviso legal (blindaje legal)
alembic/      # migraciones (0001–0009)
docs/         # backlog y ADRs
tests/        # suite de tests autosuficiente
scripts/      # backup, VPN, Kavita
bootstrap.sh  # instalación de un solo comando
docker-compose.yml
```

## Documentación

- [`CHANGELOG.md`](CHANGELOG.md) — qué trae cada release y qué queda pendiente.
- [`SECURITY.md`](SECURITY.md) — postura de seguridad y cómo reportar una vulnerabilidad.
- [`docs/BACKLOG.md`](docs/BACKLOG.md) — backlog canónico del producto.
- [`docs/adr/`](docs/adr/) — decisiones de arquitectura registradas.
- [`docs/TESTING_E2E.md`](docs/TESTING_E2E.md) / [`docs/TESTING_NFR_Zascarr.md`](docs/TESTING_NFR_Zascarr.md) — planes de testing end-to-end y no funcional.
- [`src/zascarr/LEGAL.md`](src/zascarr/LEGAL.md) — aviso legal y marco de uso.
- Docstrings de cada módulo — explican el *por qué* de las decisiones.

## Atribuciones e inspiración

- UX inspirada en [Sonarr](https://sonarr.tv) / [Radarr](https://radarr.video)
  (solo la experiencia, no el stack — ver ADR-0001).
- Benchmarking contra [Kapowarr](https://github.com/Casvt/Kapowarr),
  [Mylar3](https://github.com/mylar3/mylar3) y
  [Suwayomi](https://github.com/Suwayomi/Suwayomi-Server).
- Metadatos de [Tebeosfera](https://www.tebeosfera.com) / Gran Catálogo de la
  Historieta, [Comic Vine](https://comicvine.gamespot.com) y
  [AniList](https://anilist.co).
- [HTMX](https://htmx.org) (BSD 2-Clause) vendorizado en
  `src/zascarr/static/vendor/`.

## Licencia

**GPL-3.0-only.** Consulta el texto completo en [`LICENSE`](LICENSE).

ZascArr es software libre: puedes usarlo, estudiarlo, modificarlo y
redistribuirlo bajo los términos de la GNU General Public License v3, **sin
ninguna garantía**.
