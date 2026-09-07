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

from app.auth import SIGNING_SECRET, current_user, require_role, seed_users_if_empty
from app.config import get_settings
from app.database import SessionFactory, engine, get_session
from app.events import broadcaster
from app.generation import (
    BriefingUnavailable,
    UngroundedBriefing,
    build_generator,
)
from app.models import (
    AccessToken,
    AlarmIngestResult,
    AlarmSubmission,
    AuditEvent,
    AuthenticatedUser,
    Credentials,
    Incident,
    IncidentEvent,
    IncidentEventType,
    Recommendation,
    RecommendationDecision,
    StoredBriefing,
)
from app.repository import IncidentRepository
from app.runbook_repository import RunbookRepository
from app.security import (
    InvalidToken,
    Role,
    issue_token,
    read_token,
    satisfies,
    verify_password,
)
from app.seed import seed_if_empty
from app.tables import UserRow


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if not inspect(engine).has_table("incidents"):
        raise RuntimeError(
            "The database has no schema yet. Run 'alembic upgrade head' from "
            "the backend directory before starting the API."
        )

    with SessionFactory() as session:
        seed_if_empty(session)
        seed_users_if_empty(session)

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

# Built once at import: constructing the Anthropic client per request would
# open a new connection pool every time. Tests replace this attribute.
briefing_generator = build_generator(
    enabled=get_settings().enable_briefings,
    model=get_settings().briefing_model,
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
    """Deliberately unauthenticated: load balancers have no credentials."""
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=AccessToken)
def login(
    credentials: Credentials, session: Session = Depends(get_session)
) -> AccessToken:
    row = session.get(UserRow, credentials.username)

    # The same answer whether the account is unknown or the password is wrong.
    # Distinguishing them turns this endpoint into a way to enumerate accounts.
    if row is None or not verify_password(credentials.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = AuthenticatedUser(
        username=row.username, display_name=row.display_name, role=row.role
    )

    return AccessToken(
        access_token=issue_token(
            username=row.username, role=Role(row.role), secret=SIGNING_SECRET
        ),
        user=user,
    )


@app.get("/api/auth/me", response_model=AuthenticatedUser)
def read_current_user(
    user: AuthenticatedUser = Depends(current_user),
) -> AuthenticatedUser:
    return user


@app.get("/api/incidents", response_model=list[Incident])
def get_incidents(
    repository: IncidentRepository = Depends(get_repository),
    _: AuthenticatedUser = Depends(current_user),
) -> list[Incident]:
    return repository.list_incidents()


@app.post("/api/alarms", response_model=AlarmIngestResult)
def ingest_alarm(
    submission: AlarmSubmission,
    response: Response,
    session: Session = Depends(get_session),
    repository: IncidentRepository = Depends(get_repository),
    # A collector is a machine principal. Requiring that role here means a
    # stolen engineer token cannot fabricate network events, and a stolen
    # collector token cannot approve anything.
    _: AuthenticatedUser = Depends(require_role(Role.COLLECTOR)),
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
    _: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
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
    _: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
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
    user: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
) -> Recommendation:
    """
    Record an engineer accepting a procedure, optionally with changes.

    Approval is the only thing this endpoint does. SignalOps does not execute
    the steps, by design: nothing here should be able to touch the network
    without a human doing it.
    """
    existing = runbooks.find_recommendation(recommendation_id)

    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown recommendation {recommendation_id}"
        )

    # Some procedures carry a `Requires: supervisor` line — resets that destroy
    # diagnostic state, anything touching emergency calling. The runbook
    # authors decided that, not this codebase, and it is enforced here rather
    # than left to the engineer to remember at three in the morning.
    if existing.section.requires_supervisor and not satisfies(
        Role(user.role), Role.SUPERVISOR
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{existing.section.citation} requires a supervisor to approve it."
            ),
        )

    recommendation = runbooks.decide(
        recommendation_id,
        approved=True,
        decision=decision,
        decided_by=user.username,
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
    user: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
) -> Recommendation:
    """
    Decline a procedure. No supervisor gate: declining to act is always safe,
    and requiring escalation to say "not this one" would slow an outage down.
    """
    recommendation = runbooks.decide(
        recommendation_id,
        approved=False,
        decision=decision,
        decided_by=user.username,
    )

    if recommendation is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown recommendation {recommendation_id}"
        )

    return recommendation


@app.get("/api/incidents/{incident_id}/briefing", response_model=StoredBriefing | None)
def get_briefing(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
    _: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
) -> StoredBriefing | None:
    require_incident(incident_id, repository)

    return runbooks.latest_briefing(incident_id)


@app.post("/api/incidents/{incident_id}/briefing", response_model=StoredBriefing)
def generate_briefing(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
    # This one spends money on every call, so it is not left open.
    _: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
) -> StoredBriefing:
    """
    Summarise the already-retrieved runbook sections for this incident.

    The model never decides which procedures are relevant — retrieval does that
    deterministically first, and the model only writes the orientation over
    what it is handed. A briefing citing anything it was not given is refused.
    """
    incident = require_incident(incident_id, repository)
    recommendations = runbooks.recommendations_for(incident_id)

    try:
        briefing = briefing_generator.generate(incident, recommendations)
    except UngroundedBriefing as error:
        # 502: the upstream model produced something we will not pass on.
        raise HTTPException(status_code=502, detail=str(error)) from error
    except BriefingUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return runbooks.store_briefing(incident_id, briefing)


@app.get("/api/incidents/{incident_id}/audit", response_model=list[AuditEvent])
def get_audit_trail(
    incident_id: str,
    repository: IncidentRepository = Depends(get_repository),
    runbooks: RunbookRepository = Depends(get_runbooks),
    _: AuthenticatedUser = Depends(require_role(Role.ENGINEER)),
) -> list[AuditEvent]:
    require_incident(incident_id, repository)

    return runbooks.audit_for(incident_id)


@app.websocket("/ws/incidents")
async def incident_feed(websocket: WebSocket, token: str = "") -> None:
    """
    Push incident changes to a dashboard for as long as it stays connected.

    Deliberately send-only. A socket carries what happened while the client was
    listening and nothing more, so a client that reconnects re-fetches the full
    board over HTTP rather than expecting this to replay anything it missed.

    The token arrives as a query parameter because browsers cannot set headers
    on a WebSocket handshake. That is a real cost: query strings end up in
    access logs and proxy logs in a way Authorization headers do not. The
    production fix is a short-lived single-use ticket fetched over HTTP and
    exchanged here; this is the honest MVP version of that.
    """
    try:
        read_token(token, secret=SIGNING_SECRET)
    except InvalidToken:
        # Refuse before accepting, so an unauthenticated client never becomes
        # a subscriber at all.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    with broadcaster.subscribe() as queue:
        try:
            while True:
                payload = await queue.get()
                await websocket.send_text(payload)
        except WebSocketDisconnect:
            return
