# SignalOps AI MVP

## Product promise

Turn a noisy stream of telecom alarms into clear incidents that show probable cause, customer impact, recommended runbook steps, and resolution progress.

## Demonstration story

1. A simulated backhaul failure begins at site `RUH-104`.
2. Several raw alarms arrive within seconds.
3. SignalOps groups them into one critical incident.
4. The dashboard shows the affected site and estimated subscriber impact.
5. The system retrieves an approved troubleshooting procedure.
6. An engineer reviews and approves the suggested actions.
7. A recovery event closes the incident and updates resolution metrics.

## Vertical slices

### Slice 1 — Incident list and API contract ✅

- [x] FastAPI health endpoint
- [x] Pydantic incident response model
- [x] In-memory telecom incidents
- [x] React loading, error, empty, and success states
- [x] Runtime validation at the frontend HTTP boundary
- [x] Dashboard metrics and reusable incident cards

### Slice 2 — Filtering and incident details 🚧

- [x] Filter by severity and status
- [x] Select an incident
- [x] Dedicated incident-detail view
- [x] Model related alarms inside an incident
- [ ] Add frontend component tests

Notes on the alarm slice:

- The API returns alarms in arrival order and makes no ordering promise.
  Chronological sorting is a presentation concern and lives in
  `IncidentDetails`.
- The HTTP boundary rejects an entire payload if any alarm is malformed. That
  is deliberate while the API and the dashboard ship together, because a shape
  mismatch is a bug worth surfacing loudly. Revisit in Slice 4/5: once the API
  deploys independently, hiding every incident because one alarm is malformed
  becomes an operational hazard rather than a useful signal.
- Timestamps are validated as parseable, not merely as strings, so consumers
  can sort and format them without guarding against `Invalid Date`.

### Slice 3 — Create and correlate alarms ✅

- [x] Alarm ingestion endpoint (`POST /api/alarms`)
- [x] Deterministic correlation rules
- [x] Network-event simulator (`backend/scripts/simulate.py`)
- [x] Incident timeline
- [x] Integration tests for correlation behavior

The correlation rule, stated once so it does not have to be reverse-engineered
from code:

> An alarm joins an open incident at the same site whose most recent alarm it
> lands within `CORRELATION_WINDOW` of. Otherwise it opens a new incident.

Decisions worth knowing:

- **The window slides** along the incident's latest alarm rather than being
  fixed at its opening time, so a fault lasting longer than one window stays a
  single incident instead of splitting in two.
- **Severity is derived, never sent.** An alarm code maps to a severity through
  `catalog.py`; an incident is as severe as its worst alarm. A later, milder
  alarm cannot talk an incident down.
- **The earliest alarm names the incident.** Because delivery is out of order,
  this is recomputed on every attach: an alarm that turns out to predate the
  rest changes both the incident's start time and its explanation.
- **Ingestion is idempotent** on the sender's `external_id`. Retries are normal
  in telemetry; a redelivery returns 200 with `duplicate: true` and records
  nothing, while a newly recorded alarm returns 201.
- **Uncatalogued alarm codes are kept, not dropped**, and classified medium —
  an unrecognised signal is still evidence.
- **Unknown sites report zero affected subscribers**, which means "impact
  unknown" rather than "nobody affected". Worth revisiting: the dashboard
  currently cannot tell those two apart.

### Slice 4 — Persistence ✅

- [x] SQLAlchemy models and repositories
- [x] Alembic migrations
- [x] Transaction boundaries
- [x] Seed data
- [x] Engine chosen by `DATABASE_URL`
- [ ] Actually run against PostgreSQL

**On the database choice.** The schema, queries, and migrations are portable and
the engine is a single setting. Development runs on SQLite because it needs
nothing installed; moving to PostgreSQL is:

```text
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/signalops
alembic upgrade head
```

That last box stays unticked until someone has genuinely run the suite against
Postgres. Portable-by-construction is not the same as verified.

Decisions worth knowing:

- **Two model layers, on purpose.** `models.py` is the API contract and what
  the rules operate on; `tables.py` is how rows sit on disk. Merging them makes
  every storage decision an API change.
- **One transaction per request.** `get_session` commits on success and rolls
  back on any exception, so a handler cannot leave half its writes behind.
- **Uniqueness is enforced by the database.** The in-memory version deduplicated
  with a Python dict under a lock. That protected one process; a unique index on
  `alarms.external_id` protects all of them.
- **`UtcDateTime` keeps timestamps aware.** SQLite has no timezone-aware type
  and would return naive values, which the models reject by design — so the
  application would fail to read back rows it had just written.
- **Alarm order is now promised**, and promised to be *arrival* order rather
  than chronological. Once a database is involved, "no promised order" means
  "whatever the query planner returns", which is not a contract.
- **Migrations never import application code.** `UtcDateTime` renders as
  `sa.DateTime()` so a migration written today still runs after that class is
  renamed or deleted.

### Slice 5 — Real-time operations ✅

- [x] WebSocket incident updates (`GET /ws/incidents`)
- [x] Reconnect behavior
- [x] Live event feed
- [ ] Optimistic engineer actions — **deliberately not built**

There is nothing to be optimistic about yet. Optimistic updates exist to hide
latency on an action a user takes, and the dashboard is still read-only: an
engineer cannot acknowledge, assign, or resolve anything. This belongs with the
first engineer action, not before it.

Decisions worth knowing:

- **Publish after commit, never before.** Announcing an incident that a later
  failure rolls back would leave every connected screen showing something that
  does not exist, with no correcting message to follow.
- **Whole incidents travel, not patches.** Payloads are small, and a
  self-contained object cannot leave a client half-updated if a message is
  dropped — the next one it receives is still complete.
- **Every connection re-reads the board over HTTP.** A socket only carries what
  happened while it was open, so the snapshot is what closes the gap after a
  disconnection. The socket is for freshness; HTTP is for truth.
- **Socket messages are validated exactly like HTTP responses.** They cross the
  same trust boundary and reuse the same guards.
- **Duplicate alarms are not announced**, because nothing changed. Broadcasting
  them would flash an update on every screen for an event that did not happen.
- **Slow clients lose messages rather than memory.** Each connection holds a
  bounded buffer; a dashboard nobody is watching cannot grow the server's heap.
- **The connection indicator reports the real socket state.** It previously
  claimed "online" unconditionally, including with the API switched off.

Known limit: the broadcaster is in-process, so events reach only dashboards
connected to the worker that handled the alarm. Running more than one worker
needs a shared bus (Redis pub/sub or similar) before this holds.

### Evaluated and parked: Nokia Network as Code / CAMARA device-location APIs

Considered 2026-08-31. Not adopted for the MVP.

`POST /retrieve` (CAMARA Location Retrieval, offered by Nokia Network as Code)
returns where **one** device is, given an identifier the caller already holds,
as a circle with a centre and an accuracy radius.

- It cannot improve `affected_subscribers`. That is the tempting use, and the
  API forbids it by design: it is strictly per-device, requires a three-legged
  token carrying that subscriber's consent, and has no "which devices are near
  this site" operation — that is precisely the capability the consent model
  exists to prevent. Real subscriber-impact figures come from operator-internal
  cell attach counts, not from a public network API.
- Where it would genuinely fit is confirming that a **dispatched engineer** has
  reached a site, because an employee can meaningfully consent. For that,
  Location *Verification* ("is this device inside this circle?") is the better
  choice than Retrieval, since it answers the question without handing back
  coordinates.
- Blocked on Slice 7 regardless: it needs OAuth2/OIDC client infrastructure
  that does not exist yet. Nokia's SIMULATOR plan would allow building it
  without real subscribers once that is in place.

### Slice 6 — Runbook-assisted recommendations

- Upload and parse approved runbooks
- Retrieve relevant sections
- Generate cited recommendations
- Human approval, rejection, and modification
- Audit trail

### Slice 7 — Authentication and presentation

- Engineer and supervisor roles
- Secure API access
- Operational metrics
- Polished demo scenario
- Deployment and observability

## Engineering principles

- Begin with deterministic business rules; add AI only where language understanding is useful.
- Treat all data crossing process or network boundaries as untrusted.
- Keep route handlers thin and domain behavior testable outside the framework.
- Prefer one deployable modular application until scale proves otherwise.
- Never let the AI execute network changes autonomously in the MVP.
