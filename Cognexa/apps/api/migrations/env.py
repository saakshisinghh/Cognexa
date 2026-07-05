
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make "apps.api...." imports resolve when Alembic is invoked from repo root.
import os
import sys

sys.path.insert(0, os.getcwd())

from apps.api.config import settings  # noqa: E402
from apps.api.db import Base  # noqa: E402

# Import all model modules so they register on Base.metadata before autogenerate.
from apps.api import models  # noqa: E402, F401
from apps.api.models import conversation  # noqa: E402, F401
from apps.api.models import incident  # noqa: E402, F401

# this is the Alembic Config object, which provides access to values within
# the .ini file in use.
config = context.config

# Override the sqlalchemy.url from alembic.ini with the app's real settings
# (so a single source of truth - .env / config.py - drives migrations too).
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()