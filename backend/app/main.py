from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.data import SEED_INCIDENTS
from app.models import AlarmIngestResult, AlarmSubmission, Incident
from app.store import IncidentStore

app = FastAPI(
    title="SignalOps API",
    version="0.2.0",
    description="Telecom incident-management API for the SignalOps AI MVP.",
)

# Module-level for now because the store is in-memory and process-local.
# When persistence lands this becomes a request-scoped dependency instead.
store = IncidentStore(SEED_INCIDENTS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/incidents", response_model=list[Incident])
def get_incidents() -> list[Incident]:
    return store.list_incidents()


@app.post("/api/alarms", response_model=AlarmIngestResult)
def ingest_alarm(submission: AlarmSubmission, response: Response) -> AlarmIngestResult:
    """
    Accept one raw alarm and return the incident it belongs to.

    The status code distinguishes the two outcomes a caller cares about: 201
    when the alarm was recorded, 200 when it was recognised as a redelivery of
    one already held. Both are successes — a retrying collector should not be
    made to treat a duplicate as an error.
    """
    result = store.ingest(submission)

    response.status_code = (
        status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
    )

    return result
