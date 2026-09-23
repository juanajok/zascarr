# ZascArr

**Orquestador inteligente de tebeoteca digital.** Un gestor automatizado de
bibliotecas de cómics y tebeos, inspirado en Sonarr/Radarr, pensado para
coleccionistas **hispanohablantes** y diseñado para correr en una
**Raspberry Pi 4/5**.

![Licencia](https://img.shields.io/badge/licencia-GPL--3.0--only-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Estado](https://img.shields.io/badge/estado-pre--1.0%20(desarrollo)-orange.svg)

> ⚠️ **Aviso legal (postura Sonarr-style).** ZascArr es una herramienta
> **neutra** para gestionar tu biblioteca personal de tebeos: organiza,
> enriquece y completa el contenido que ya posees o tienes derecho a usar.
> **No incluye fuentes, indexadores ni enlaces de descarga por defecto**;
> cada integración (Prowlarr, Transmission, aMule, foros) nace desactivada y
> se activa de forma explícita y bajo tu responsabilidad. ZascArr **no
> distribuye ni facilita** contenido protegido por derechos de autor.
> Lee [`src/zascarr/LEGAL.md`](src/zascarr/LEGAL.md) antes de usarlo.

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

🚧 **Pre-1.0, en desarrollo activo.** El backend y la interfaz web están
funcionales y verificados end-to-end, pero quedan piezas por cerrar antes del
release 1.0. El backlog canónico con el detalle y el orden de prioridades está
en [`docs/BACKLOG.md`](docs/BACKLOG.md).

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
  conexión a internet. Docker se instala en el paso 1; no necesitas saber qué es.
- Para desarrollo: **Python 3.11+**.

Opcional, fuera de Docker (baremetal): Transmission, aMule, Prowlarr y Kavita.

## Instalación

Pensada para **"El Coleccionista"**: no hace falta entender qué es Docker ni
una terminal. Son tres pasos de copiar y pegar, y el instalador solo te hace 3
preguntas.

### Paso 1 — Instala Docker (una sola vez)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

Cierra la sesión y vuelve a entrar (o reinicia) para que el grupo `docker`
haga efecto.

### Paso 2 — Descarga ZascArr

```bash
mkdir -p ~/tebeoteca && cd ~/tebeoteca
git clone https://github.com/juanajok/zascarr.git
```

### Paso 3 — Ejecuta el instalador

```bash
sudo bash zascarr/bootstrap.sh
```

`bootstrap.sh` te hace **3 preguntas** (pulsa `Intro` para aceptar lo que va
entre corchetes):

1. ¿Dónde están tus tebeos ya organizados?
2. ¿Dónde caen tus descargas (Transmission/aMule)?
3. ¿Idioma de la interfaz? (`es`/`en`)

Al terminar, ZascArr ya está funcionando. Ábrelo en:

**http://127.0.0.1:8000** — el panel de estado, en español.

Puedes volver a ejecutar `sudo bash zascarr/bootstrap.sh` cuando quieras: es
idempotente (no duplica nada) y nunca toca los archivos de tu colección.

### Qué hace el instalador

- Crea la estructura de carpetas de la biblioteca (`Comics`, `Manga`, `BD`,
  `Tebeos`, …) **sin tocar tus archivos**.
- Levanta PostgreSQL, Redis y ZascArr como contenedores Docker.
- Aplica las migraciones de la base de datos y comprueba que todo está sano.

### Instalación manual (para quien prefiera Docker Compose)

```bash
cp .env.example .env        # edita .env (contraseña de BD, claves opcionales)
docker compose up -d
make migrate                # aplica las migraciones de Alembic
```

## Uso

| Qué | Dónde |
|---|---|
| Dashboard / estado | `http://127.0.0.1:8000` |
| Biblioteca / wishlist / pendientes | `http://127.0.0.1:8000` (navegación web) |
| API (OpenAPI/Swagger) | `http://127.0.0.1:8000/api/docs` |
| Comandos | `make help` (`logs`, `migrate`, `health`, `backup`, …) |

## Integraciones (todas opcionales y desactivadas por defecto)

| Tipo | Integración | Activación |
|---|---|---|
| Metadatos | [Comic Vine](https://comicvine.gamespot.com/api/) | API key en `COMICVINE_API_KEY` |
| Metadatos | [AniList](https://anilist.co) | pública, sin clave |
| Metadatos | [Tebeosfera](https://www.tebeosfera.com) | scraping, sin clave |
| Descarga | [Prowlarr](https://prowlarr.com) | `PROWLARR_API_KEY` |
| Descarga | [Transmission](https://transmissionbt.com) | usuario/contraseña |
| Descarga (eD2K) | [aMule](https://www.amule.org) | contraseña |

No hay ninguna fuente preconfigurada: activar una integración es siempre una
decisión explícita del usuario. Los rate limits por fuente son conservadores y
los fallos de scraping degradan a "sin resultado" en vez de tumbar el ciclo.

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
alembic/      # migraciones (0001–0008)
docs/         # backlog y ADRs
tests/        # suite de tests autosuficiente
scripts/      # backup, VPN, Kavita
bootstrap.sh  # instalación de un solo comando
docker-compose.yml
```

## Documentación

- [`docs/BACKLOG.md`](docs/BACKLOG.md) — backlog canónico del producto.
- [`docs/adr/`](docs/adr/) — decisiones de arquitectura registradas.
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
