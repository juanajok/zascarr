"""
Configuración centralizada de ZascArr.
Todas las variables se leen del entorno (o .env). Validación estricta al arranque.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": el .env real también lleva variables de infraestructura
    # que solo consume docker-compose.yml (HOST_LIBRARY_DIR, ZASCARR_DATA_DIR,
    # APP_LOCALE, TZ...), no la app Python. El comportamiento por defecto de
    # BaseSettings es rechazar cualquier variable del .env que no sea un
    # campo declarado aquí — sin este "ignore", cualquier ejecución que vea
    # el .env real (p. ej. "alembic upgrade head" en el host durante el
    # bootstrap) revienta con "Extra inputs are not permitted".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False,
        extra="ignore",
    )

    # ── Base de datos ──────────────────────────────────────────────
    # Fallback deliberadamente inválido: en producción el compose inyecta
    # DATABASE_URL y en local el .env. Si se llega a usar este valor, la
    # conexión falla de forma obvia en vez de usar una credencial "de ejemplo".
    database_url: str = Field(
        default="postgresql+asyncpg://INVALID:INVALID@127.0.0.1:5432/INVALID"
    )
    db_pool_size: int = 5
    db_max_overflow: int = 2
    db_pool_recycle: int = 1800

    # ── Redis ──────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://127.0.0.1:6379/0")
    redis_cache_ttl: int = 3600

    # ── Comic Vine API ─────────────────────────────────────────────
    comicvine_api_key: str = Field(default="")
    comicvine_base_url: str = "https://comicvine.gamespot.com/api"
    comicvine_rate_limit: float = 1.0

    # ── AniList API (manga/manhwa/manhua) ────────────────────────────
    # Sin API key: es pública. 1.5s es conservador a propósito — AniList
    # ha tenido temporadas en modo degradado (30 req/min en vez de 90).
    anilist_rate_limit: float = 1.5

    # ── Tebeosfera (scraping — tebeo/BD en español) ──────────────────
    # Sin API ni contrato de rate limit: es scraping de un sitio ajeno,
    # no una API pública. Más conservador que Comic Vine/AniList a
    # propósito, y encima cada búsqueda de serie hace 2 peticiones
    # (colecciones + sagas), el doble que las otras fuentes.
    tebeosfera_rate_limit: float = 2.0

    # ── Prowlarr (baremetal) ───────────────────────────────────────
    # Blindaje legal: deshabilitado por defecto a propósito (igual que
    # forum_enabled) — el usuario tiene que activar cada integración de
    # descarga explícitamente, no viene "encendida" de fábrica.
    prowlarr_url: str = Field(default="http://127.0.0.1:9696")
    prowlarr_api_key: str = Field(default="")
    prowlarr_enabled: bool = Field(default=False)

    # ── Transmission (baremetal) ───────────────────────────────────
    transmission_url: str = Field(default="http://127.0.0.1:9091")
    transmission_username: str = Field(default="")
    transmission_password: str = Field(default="")
    transmission_download_dir: str = Field(default="/media/downloads/comics")
    transmission_enabled: bool = Field(default=False)

    # ── aMule (baremetal) ──────────────────────────────────────────
    amule_url: str = Field(default="http://127.0.0.1:4711")
    amule_password: str = Field(default="")
    amule_incoming_dir: str = Field(default="/media/incoming")
    amule_enabled: bool = Field(default=False)

    # ── Forum scraper ──────────────────────────────────────────────
    # Blindaje legal: sin URL por defecto — antes apuntaba a un foro
    # real concreto de fábrica, lo más cercano a "facilitación
    # organizada" que tenía el proyecto. Es un plugin IPB genérico: la
    # URL la aporta el usuario, el proyecto no incluye ni recomienda
    # ningún foro concreto.
    forum_url: str = Field(default="")
    forum_username: str = Field(default="")
    forum_password: str = Field(default="")
    forum_rate_limit: float = Field(default=2.0)
    forum_enabled: bool = Field(default=False)

    # ── Filesystem (rutas DENTRO del contenedor — genéricas y estables) ──
    # El contenedor monta los discos reales del usuario en estas rutas
    # (ver docker-compose.yml); los discos en sí se configuran en .env con
    # HOST_LIBRARY_DIR / HOST_DOWNLOADS_DIR / HOST_AMULE_INCOMING_DIR.
    library_path: Path = Field(default=Path("/media/library"))
    downloads_path: Path = Field(default=Path("/media/downloads"))
    # C1: caché unificada de portadas (extraídas de CBZ o descargadas de
    # fuentes externas una sola vez) — ver utils/cover.py.
    covers_cache_path: Path = Field(default=Path("/config/covers"))

    # ── VPN state (fichero escrito por un script del host) ────────
    # Fichero JSON escrito por scripts/vpn-state.sh (baremetal, fuera del
    # contenedor) y montado read-only. Ver fix C2 del peer review.
    vpn_state_file: str = Field(default="/run/vpn-state/wg0.json")

    # ── Orquestador ────────────────────────────────────────────────
    scan_interval_minutes: int = 60
    import_interval_minutes: int = 15
    max_concurrent_downloads: int = 2
    # D1: cuánto esperar antes de reintentar un item sin resultados o cuya
    # descarga falló (mismo patrón que enrichment_attempted_at del enricher,
    # pero mucho más corto: la disponibilidad en un indexer/foro cambia en
    # horas, no en meses).
    orchestrator_retry_cooldown_hours: int = 6

    # ── Enricher (Comic Vine) ────────────────────────────────────────
    # Intervalo largo a propósito: Comic Vine limita a ~1 req/s y el
    # enricher procesa por lotes pequeños en cada ciclo (ver enricher.py).
    enrich_interval_minutes: int = 120
    enrich_batch_size: int = 20

    # ── App ────────────────────────────────────────────────────────
    app_name: str = "ZascArr"
    app_version: str = "1.2.6"
    log_level: str = "INFO"
    log_json: bool = True
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
