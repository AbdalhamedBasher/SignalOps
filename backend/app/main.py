import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database import SessionFactory, engine, get_session
from app.events import broadcaster
from app.models import (
    AlarmIngestResult,
    AlarmSubmission,
    AuditEvent,
    Incident,
    IncidentEvent,
    IncidentEventType,
    Recommendation,
    RecommendationDecision,
)
from app.repository import IncidentRepository
from app.runbook_repository import RunbookRepository
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

        # Approved runbooks are version-controlled alongside the code, so they
        # are imported at start rather than uploaded. Already-imported files
        # are skipped, making this safe on every restart.
        RunbookRepository(session).load_from_disk()
        session.commit()

    # Request handlers run in a thread pool; this is the loop they have to hand
    # outbound events back to.
    broadcaster.bind(asyncio.get_running_loop())

    yield


app = FastAPI(
    title="SignalOps API",
    version="0.4.0",
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


def get_runbooks(session: Session = Depends(get_session)) -> RunbookRepository:
    return RunbookRepository(session)


def require_incident(
    incident_id: str, repository: IncidentRepository
) -> Incident:
    incident = repository.find_incident(incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail=f"Unknown incident {incident_id}")

    return incident


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
    session: Session = Depends(get_session),
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

    if not result.duplicate:
        # Commit before announcing. Telling dashboards about an incident that a
        # later failure rolls back would leave every connected screen showing
        # something that does not exist, and nothing would arrive to correct
        # it. FastAPI resolves `session` and `repository` to the same session,
        # so this is the transaction the repository just wrote into.
        session.commit()

        broadcaster.publish(
            IncidentEvent(
                type=(
                    IncidentEventType.OPENED
                    if result.incident_created
                    else IncidentEventType.UPDATED
                ),
                incident=result.incident,
            )
        )

    response.status_code = (
        status.HTTP_200_OK if result.duplicate else status.HTTP_201_CREATED
    )

    return result


@app.get(
    "/api/incidents/{incident_id}/recommendations",
    response_model=list[Recommendation],
)
def get_recommendations(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
) -> list[Recommendation]:
    require_incident(incident_id, repository)

    return runbooks.recommendations_for(incident_id)


@app.post(
    "/api/incidents/{incident_id}/recommendations",
    response_model=list[Recommendation],
)
def propose_recommendations(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
) -> list[Recommendation]:
    """
    Retrieve the runbook sections that apply to this incident.

    Safe to call repeatedly: sections already proposed keep whatever an
    engineer decided about them, and only newly relevant ones are added.
    """
    incident = require_incident(incident_id, repository)

    return runbooks.propose_for(incident)


@app.post(
    "/api/recommendations/{recommendation_id}/approve",
    response_model=Recommendation,
)
def approve_recommendation(
    recommendation_id: str,
    decision: RecommendationDecision,
    runbooks: RunbookRepository = Depends(get_runbooks),
) -> Recommendation:
    """
    Record an engineer accepting a procedure, optionally with changes.

    Approval is the only thing this endpoint does. SignalOps does not execute
    the steps, by design: nothing here should be able to touch the network
    without a human doing it.
    """
    recommendation = runbooks.decide(
        recommendation_id, approved=True, decision=decision
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown recommendation {recommendation_id}"
        )

    return recommendation


@app.post(
    "/api/recommendations/{recommendation_id}/reject",
    response_model=Recommendation,
)
def reject_recommendation(
    recommendation_id: str,
    decision: RecommendationDecision,
    runbooks: RunbookRepository = Depends(get_runbooks),
) -> Recommendation:
    recommendation = runbooks.decide(
        recommendation_id, approved=False, decision=decision
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown recommendation {recommendation_id}"
        )

    return recommendation


@app.get("/api/incidents/{incident_id}/audit", response_model=list[AuditEvent])
def get_audit_trail(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
) -> list[AuditEvent]:
    require_incident(incident_id, repository)

    return runbooks.audit_for(incident_id)


@app.websocket("/ws/incidents")
async def incident_feed(websocket: WebSocket) -> None:
    """
    Push incident changes to a dashboard for as long as it stays connected.

    Deliberately send-only. A socket carries what happened while the client was
    listening and nothing more, so a client that reconnects re-fetches the full
    board over HTTP rather than expecting this to replay anything it missed.
    """
    await websocket.accept()

    with broadcaster.subscribe() as queue:
        try:
            while True:
                payload = await queue.get()
                await websocket.send_text(payload)
        except WebSocketDisconnect:
            return
