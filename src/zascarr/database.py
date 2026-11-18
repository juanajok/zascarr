"""Motor de base de datos async (SQLAlchemy 2.0 + asyncpg)."""
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from zascarr.config import get_settings
from zascarr.utils.credenciales import url_bd_compose


class Base(DeclarativeBase):
    pass


settings = get_settings()

password_compose = os.environ.get("ZASCARR_DB_PASSWORD")
database_url = (
    url_bd_compose(password_compose)
    if password_compose is not None and not os.environ.get("DATABASE_URL")
    else settings.database_url
)

engine = create_async_engine(
    database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
    echo=settings.debug,
)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection para FastAPI."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
