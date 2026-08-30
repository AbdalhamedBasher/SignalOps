import pytest

from app.data import SEED_INCIDENTS
from app.main import store


@pytest.fixture(autouse=True)
def reset_incident_store() -> None:
    """
    Give every test a clean board.

    The store is process-local and mutable, so an ingestion test would
    otherwise leak incidents into whatever runs next and make failures depend
    on test order.
    """
    store.reset(SEED_INCIDENTS)
