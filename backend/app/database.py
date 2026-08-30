"""
Engine, session lifecycle, and the column type that keeps timestamps honest.

Everything here is infrastructure. The correlation rules never import it.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class UtcDateTime(TypeDecorator[datetime]):
    """
    A datetime column that is always timezone-aware UTC on both sides.

    SQLite has no timezone-aware datetime type: it stores whatever it is given
    and hands back a naive value. Without this, a timestamp written as
    aware-UTC would come back naive, and the Pydantic models — which reject
    naive timestamps on purpose — would refuse to load our own stored rows.

    Normalising to UTC on the way in and re-attaching UTC on the way out keeps
    that guarantee true regardless of engine, and means PostgreSQL and SQLite
    behave identically here.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("refusing to store a timestamp without a UTC offset")

        return value.astimezone(UTC)

    def process_result_value(
        self, value: datetime | None, dialect: Any
    ) -> datetime | None:
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)


def build_engine(database_url: str) -> Engine:
    settings_is_sqlite = database_url.startswith("sqlite")

    engine = create_engine(
        database_url,
        # FastAPI runs synchronous handlers across a thread pool, and SQLite
        # otherwise refuses to reuse a connection on a different thread.
        connect_args={"check_same_thread": False} if settings_is_sqlite else {},
    )

    if settings_is_sqlite:
        # SQLite ignores foreign keys unless asked, per connection. Without
        # this an alarm could reference an incident that does not exist and
        # nothing would complain.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection: Any, _record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = build_engine(get_settings().database_url)

SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    # Keeps attributes readable after commit, so a handler can still serialise
    # the object it just wrote without triggering another query.
    expire_on_commit=False,
)


def get_session() -> Iterator[Session]:
    """
    One transaction per request.

    Committing here rather than inside the repository means a handler that
    does two writes cannot leave half of them behind: either the request
    succeeds and everything lands, or it raises and nothing does.
    """
    session = SessionFactory()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
