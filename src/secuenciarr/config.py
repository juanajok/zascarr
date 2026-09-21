"""
Configuración centralizada de SecuenciArr.
Todas las variables se leen del entorno (o .env). Validación estricta al arranque.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # ── Base de datos ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://comics_admin:changeme@127.0.0.1:5432/tebeoteca"
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
    prowlarr_url: str = Field(default="http://127.0.0.1:9696")
    prowlarr_api_key: str = Field(default="")

    # ── Transmission (baremetal) ───────────────────────────────────
    transmission_url: str = Field(default="http://127.0.0.1:9091")
    transmission_username: str = Field(default="")
    transmission_password: str = Field(default="")
    transmission_download_dir: str = Field(default="/media/DiscoDuro/downloads/comics")

    # ── aMule (baremetal) ──────────────────────────────────────────
    amule_url: str = Field(default="http://127.0.0.1:4711")
    amule_password: str = Field(default="")
    amule_incoming_dir: str = Field(default="/media/DiscoDuro/aMule/Incoming")

    # ── Forum scraper ──────────────────────────────────────────────
    forum_url: str = Field(default="http://lamansion-crg.net/forum")
    forum_username: str = Field(default="")
    forum_password: str = Field(default="")
    forum_rate_limit: float = Field(default=2.0)
    forum_enabled: bool = Field(default=False)

    # ── Filesystem ────────────────────────────────────────────────
    library_path: Path = Field(default=Path("/media/WDElements/Tebeos"))
    downloads_path: Path = Field(default=Path("/media/DiscoDuro/downloads"))

    # ── VPN state (Confiraspa) ──────────────────────────────────────
    # Fichero JSON escrito por scripts/vpn-state.sh (baremetal, fuera del
    # contenedor) y montado read-only. Ver fix C2 del peer review.
    vpn_state_file: str = Field(default="/run/vpn-state/wg0.json")

    # ── Orquestador ────────────────────────────────────────────────
    scan_interval_minutes: int = 60
    import_interval_minutes: int = 15
    max_concurrent_downloads: int = 2

    # ── Enricher (Comic Vine) ────────────────────────────────────────
    # Intervalo largo a propósito: Comic Vine limita a ~1 req/s y el
    # enricher procesa por lotes pequeños en cada ciclo (ver enricher.py).
    enrich_interval_minutes: int = 120
    enrich_batch_size: int = 20

    # ── App ────────────────────────────────────────────────────────
    app_name: str = "SecuenciArr"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = True
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
