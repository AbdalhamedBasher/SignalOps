import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Alembic is normally invoked from the backend directory; make sure the `app`
# package is importable regardless of where it was started from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.database import Base, UtcDateTime  # noqa: E402
from app import tables  # noqa: E402,F401  (imported so Base knows the tables)

config = context.config

# The database is chosen by the application's settings, not by alembic.ini, so
# there is exactly one place that decides where data lives. An explicit
# override still wins, which is how the migration test points at a scratch
# database without touching the developer's own.
if not config.get_main_option("sqlalchemy.url", ""):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return get_settings().database_url.startswith("sqlite")


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """
    Keep application types out of generated migration scripts.

    A migration is a permanent record of one schema change and has to keep
    working years later. If it imported `app.database.UtcDateTime`, renaming or
    deleting that class would break every historical migration. UtcDateTime
    only converts values in Python — the DDL it emits is an ordinary DATETIME —
    so the script can record exactly that and stay self-contained.
    """
    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime()"

    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        render_item=render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_item=render_item,
            # SQLite cannot ALTER most things in place. Batch mode rewrites the
            # table instead, so the same migration script works on both engines.
            render_as_batch=_is_sqlite(),
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
