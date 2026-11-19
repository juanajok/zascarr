"""Alembic env.py — async SQLAlchemy 2.0."""
import asyncio, os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from zascarr.models import Base
from zascarr.utils.credenciales import url_bd_compose

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Usar la URL directamente, sin la interpolación de % de ConfigParser.
valor = os.environ.get("DATABASE_URL")
password_compose = os.environ.get("ZASCARR_DB_PASSWORD")
if valor:
    db_url = make_url(valor)
    if db_url.drivername == "postgresql":
        db_url = db_url.set(drivername="postgresql+asyncpg")
elif password_compose is not None:
    db_url = url_bd_compose(password_compose)
else:
    raise RuntimeError(
        "Define DATABASE_URL para ejecutar las migraciones fuera de Docker Compose."
    )


def run_migrations_offline() -> None:
    context.configure(url=db_url, target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
