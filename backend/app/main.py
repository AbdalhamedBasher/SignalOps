from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database import SessionFactory, engine, get_session
from app.models import AlarmIngestResult, AlarmSubmission, Incident
from app.repository import IncidentRepository
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if not inspect(engine).has_table("incidents"):
        raise RuntimeError(
            "The database has no schema yet. Run 'alembic upgrade head' from "
            "the backend directory before starting the API."
        )

    with SessionFactory() as session:
        seed_if_empty(session)

    yield


app = FastAPI(
    title="SignalOps API",
    version="0.3.0",
    description="Telecom incident-management API for the SignalOps AI MVP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_repository(session: Session = Depends(get_session)) -> IncidentRepository:
    return IncidentRepository(session)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/incidents", response_model=list[Incident])
def get_incidents(
    repository: IncidentRepository = Depends(get_repository),
) -> list[Incident]:
    return repository.list_incidents()


@app.post("/api/alarms", response_model=AlarmIngestResult)
def ingest_alarm(
    submission: AlarmSubmission,
    response: Response,
    repository: IncidentRepository = Depends(get_repository),
) -> AlarmIngestResult:
    """
    Accept one raw alarm and return the incident it belongs to.

    The status code distinguishes the two outcomes a caller cares about: 201
    when the alarm was recorded, 200 when it was recognised as a redelivery of
    one already held. Both are successes — a retrying collector should not be
    made to treat a duplicate as an error.
    """
    result = repository.ingest(submission)

    response.status_code = (
        status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
    )

    return result
