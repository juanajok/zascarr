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

    # ── Orquestador ────────────────────────────────────────────────
    scan_interval_minutes: int = 60
    import_interval_minutes: int = 15
    max_concurrent_downloads: int = 2

    # ── App ────────────────────────────────────────────────────────
    app_name: str = "SecuenciArr"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = True
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
