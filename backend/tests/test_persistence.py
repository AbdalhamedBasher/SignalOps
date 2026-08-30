"""
Tests for the thing Slice 4 actually bought: data that outlives a request.

The API tests would still pass against the old in-memory store, so they prove
nothing about persistence. These talk to the repository directly, across
separate sessions, which is where storage bugs actually show up.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from alembic import command
from app import tables  # noqa: F401  (imported so Base knows the tables)
from app.database import Base
from app.models import AlarmSubmission
from app.repository import IncidentRepository

BACKEND_DIR = Path(__file__).resolve().parents[1]


def submission(code: str, *, at: datetime, site_id: str = "DMM-052") -> AlarmSubmission:
    return AlarmSubmission(
        site_id=site_id,
        code=code,
        message=f"{code} raised during a test",
        occurred_at=at,
    )


def test_an_ingested_alarm_survives_into_a_new_session(engine: Engine) -> None:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fault_start = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    with factory() as session:
        IncidentRepository(session).ingest(
            submission("BACKHAUL_DOWN", at=fault_start)
        )
        session.commit()

    # A completely separate session, reading from storage rather than memory.
    with factory() as session:
        incidents = IncidentRepository(session).list_incidents()

    stored = next(incident for incident in incidents if incident.site_id == "DMM-052")
    assert stored.severity.value == "critical"
    assert len(stored.alarms) == 1


def test_correlation_works_across_separate_sessions(engine: Engine) -> None:
    """
    Two alarms arriving in two different requests still form one incident.

    In-memory this was guaranteed by a shared Python object. Now it depends on
    the second request actually reading the first one's committed row back.
    """
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    fault_start = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    with factory() as session:
        first = IncidentRepository(session).ingest(
            submission("BACKHAUL_DOWN", at=fault_start)
        )
        session.commit()

    with factory() as session:
        second = IncidentRepository(session).ingest(
            submission("VOLTE_REG_FAILURE", at=fault_start + timedelta(minutes=3))
        )
        session.commit()

    assert second.incident_created is False
    assert second.incident.id == first.incident.id
    assert len(second.incident.alarms) == 2


def test_timestamps_come_back_timezone_aware_in_utc(engine: Engine) -> None:
    """
    SQLite has no timezone-aware datetime type, so a stored aware timestamp
    would normally return naive — and the Pydantic models reject naive
    timestamps. Without UtcDateTime this test fails at the point of reading
    our own rows back.
    """
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    occurred = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    with factory() as session:
        IncidentRepository(session).ingest(submission("BACKHAUL_DOWN", at=occurred))
        session.commit()

    with factory() as session:
        incidents = IncidentRepository(session).list_incidents()

    stored = next(incident for incident in incidents if incident.site_id == "DMM-052")

    assert stored.opened_at.tzinfo is not None
    assert stored.opened_at.utcoffset() == timedelta(0)
    assert stored.opened_at == occurred
    assert stored.alarms[0].occurred_at == occurred


def test_the_migrations_produce_the_schema_the_models_describe(tmp_path: Path) -> None:
    """
    Catches the commonest persistence mistake: changing a model and forgetting
    to write the migration. Everything would pass locally, because the test
    database is built from the models, and then fail on deploy where the
    schema is built from the migrations.
    """
    database_path = (tmp_path / "migrated.db").as_posix()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    migrated_engine = create_engine(f"sqlite:///{database_path}")

    try:
        with migrated_engine.connect() as connection:
            differences = compare_metadata(
                MigrationContext.configure(connection), Base.metadata
            )
    finally:
        migrated_engine.dispose()

    assert differences == []
