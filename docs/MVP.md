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

### Slice 3 — Create and correlate alarms

- Alarm ingestion endpoint
- Deterministic correlation rules
- Network-event simulator
- Incident timeline
- Integration tests for correlation behavior

### Slice 4 — Persistence

- PostgreSQL
- SQLAlchemy models and repositories
- Alembic migrations
- Transaction boundaries
- Seed data

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
