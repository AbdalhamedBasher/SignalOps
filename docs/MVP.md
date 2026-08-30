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

### Slice 5 — Real-time operations

- WebSocket incident updates
- Reconnect behavior
- Live event feed
- Optimistic engineer actions where appropriate

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
