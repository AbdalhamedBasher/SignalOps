from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import tables  # noqa: F401  (imported so Base knows the tables)
from app.database import Base, get_session
from app.main import app
from app.runbook_repository import RunbookRepository
from app.seed import seed_if_empty


@pytest.fixture
def engine() -> Iterator[Engine]:
    """
    A private in-memory database per test.

    StaticPool keeps every connection pointing at the same in-memory database;
    without it SQLite would hand each connection its own empty one and the
    schema created here would be invisible to the request under test.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def _enable_foreign_keys(connection: object, _record: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(test_engine)

    yield test_engine

    test_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(
    session_factory: sessionmaker[Session], seeded_app: None
) -> Iterator[Session]:
    """
    A session on the seeded test database.

    Depends on `seeded_app` so the board and the runbooks are already loaded;
    tests that talk to a repository directly want the same starting state the
    HTTP tests get.
    """
    del seeded_app

    with session_factory() as open_session:
        yield open_session


@pytest.fixture(autouse=True)
def seeded_app(
    engine: Engine,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Point the application at the test database and give it the seed board."""
    factory = session_factory

    # The lifespan checks the schema and seeds using these directly rather than
    # through the dependency, so overriding get_session alone would leave it
    # reading the developer's own database — and failing outright on a clone
    # where nobody has run the migrations yet.
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.main.SessionFactory", factory)

    with factory() as session:
        seed_if_empty(session)
        RunbookRepository(session).load_from_disk()
        session.commit()

    def override_get_session() -> Iterator[Session]:
        session = factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session

    yield

    app.dependency_overrides.clear()
