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

### Reversed: the decision to park the CAMARA network APIs

Recorded because the reasoning was wrong, and the record should say so.

On 2026-08-31 these APIs were evaluated and **parked**. The argument: Location
Retrieval could not improve `affected_subscribers` — true, it is per-device and
consent-bound, with no "which devices are near this site" operation — and
anything CAMARA was blocked on Slice 7's authentication work.

That was sound reasoning for a learning MVP and wrong for this project, which is
a hackathon submission whose rules make a CAMARA integration **mandatory**. The
mistake was optimising the engineering sequence while ignoring the constraint
that actually governed the work. It cost about a week.

Adopted instead, in Slice 8: **Device Reachability Status** and **Congestion
Insights**, which answer the impact question Location Retrieval could not; and
**Location Verification**, which does the engineer-dispatch job the original
note itself identified as the one genuine fit.

### Slice 6a — Runbook retrieval and the approval gate ✅

- [x] Parse approved runbooks (Markdown in `backend/runbooks/`)
- [x] Retrieve relevant sections
- [x] Cited recommendations
- [x] Human approval, rejection, and modification
- [x] Audit trail
- [ ] Upload endpoint — runbooks are version-controlled and loaded at startup
      instead, which is how approved procedures actually reach production

Decisions worth knowing:

- **Retrieval is deterministic, and that is the point.** An engineer at three
  in the morning has to be able to check *why* a procedure was put in front of
  them. "Your incident raised BACKHAUL_DOWN and this section says it covers
  BACKHAUL_DOWN" is checkable in a second.
- **Ranked by coverage.** A section matching more of the incident's distinct
  alarm codes outranks one matching a single symptom, because a procedure
  written for the combination in front of you is more use.
- **Nothing reaches an engineer uncited.** Every recommendation carries the
  runbook title, the heading, and the source file. The frontend guard rejects a
  payload whose citation is malformed rather than rendering it without a
  source.
- **Silence beats guessing.** An incident whose alarms match no runbook gets no
  recommendations. A procedure that does not apply costs time during an outage.
- **Regeneration is additive.** A unique constraint on (incident, section)
  means new alarms can pull in newly relevant guidance without resetting a
  decision an engineer already made.
- **Section codes live in their own indexed table**, so matching cannot confuse
  `POWER_UNSTABLE` with `SITE_POWER_UNSTABLE`.
- **Markdown is reflowed on parse.** Runbooks are hard-wrapped at eighty
  columns to diff well; rendered into a narrow panel those breaks land
  mid-sentence, so continuation lines are folded back.

Known limit, and it is a real one: **the audit trail is unauthenticated.** The
engineer's name is whatever the caller typed. Nothing verifies it, so this
records intent, not identity — it is not yet evidence. It becomes an audit
trail when Slice 7 puts authentication behind it.

### Slice 6b — The AI agent ✅

- [x] An agent that decides which signals an incident needs
- [x] Grounded: every cited section verified against what it was given
- [x] Stored with the model that wrote it, and its reasoning trace
- [x] Degrades cleanly when unconfigured or unreachable
- [x] **Verified against the live Gemini API**
- [ ] Evals for output quality

Runs `gemini-flash-lite-latest` through **Pydantic AI**. Both are named in the
hackathon's Resource & Tooling Guide — Gemini under LLMs and Model APIs,
Pydantic AI under code-first agent frameworks.

**On the provider change.** This slice originally used Anthropic's model API.
That is *not* on the approved list — Claude appears only under coding
assistants — so the path was removed rather than argued for, and its SDK is no
longer installed.

Model choice was measured, not assumed:

| Model | Run 1 | Run 2 | Verdicts |
| --- | --- | --- | --- |
| `gemini-2.5-flash` | 404 — retired for new API keys | | |
| `gemini-3.6-flash` | 22s | 92s | correct |
| `gemini-flash-lite-latest` | 6.0s | 6.1s | correct |

The lite model reached the same conclusions on a four-alarm cascade and on a
false alarm, so the slower model bought nothing and its variance would have hurt
a live demo.

**A fault the simulator had hidden.** On a site whose devices were all
reachable, the agent returned `confirmed` while its own evidence said nothing
was unreachable — the verdict scale was described in prose and left to
inference, and medium congestion was enough to tip it. The rule is now
mechanical, with reachability the only input and congestion demoted to context.

### Slice 8 — CAMARA network APIs as agent tools ✅

- [x] Device Reachability Status
- [x] Congestion Insights
- [x] Location Verification
- [x] Called through Nokia's official `network-as-code` SDK
- [x] Deterministic local simulator as fallback
- [x] **Verified live against Nokia Network as Code**

This is the slice that makes the product's central claim real.
`affected_subscribers` was a hardcoded lookup table; the agent now checks it
against the network and can contradict the alarms.

Two things had to be found by trying, because neither is documented anywhere
reachable without an account:

- The SDK's own default host, `network-as-code.p-eu.rapidapi.com`, returns
  RapidAPI's `{"message": "API doesn't exists"}` for a console-issued key. Those
  keys route through `network-as-code.nokia.rapidapi.com`.
- The simulator holds fixed device populations that cannot be configured from
  the API: `+36371234xx` always answers `reachable: false`, `+367012345x`
  always `true`. Sites are registered against whichever population tells their
  true story.

The first hand-written client guessed both endpoint paths wrong — reachability
lives under `device-status/`, and congestion is `v0`, not `v1` — which is why it
was rebuilt on the vendor SDK.

**Measured limits, stated rather than hidden.** In Nokia's Simulator mode,
Location Verification returns `TRUE` for Riyadh, Sydney and Reykjavik alike. A
reading carries a `discriminating` flag, its summary says so, and the agent is
instructed never to report an engineer on site on that basis. On the first live
run it complied, leaving the reading out of its evidence entirely.

### Slice 7 — Authentication and roles ✅

- [x] Engineer, supervisor and collector roles
- [x] Secure API access — every route except `/health` requires a token
- [x] The audit trail records verified identity
- [ ] Operational metrics
- [ ] Deployment and observability

The audit trail previously recorded whatever name the caller typed, which made
it a log of claims rather than evidence. Identity now comes from the access
token and `decided_by` is not a field the API reads.

Decisions worth knowing:

- **Argon2id over bcrypt** — the current OWASP recommendation, and no silent
  72-byte truncation.
- **The JWT decode algorithm is pinned**, so the classic `alg: none` forgery is
  refused rather than believed.
- **Three principals, not two.** A collector is a machine that may only push
  alarms, so a stolen engineer token cannot fabricate network events and a
  stolen collector token cannot approve anything.
- **Supervisor authority comes from the runbook text.** A section carrying
  `Requires: supervisor` cannot be approved by an engineer — the rule sits with
  the people who wrote the procedure.
- **No default signing secret.** A shipped one is the same as no authentication,
  so an unset `JWT_SECRET` generates a random one and says so loudly.

Known limit: the demo operator passwords ship in the frontend bundle so role
switching is one click. Good for judging, not a production posture, and the
deployed app should not be described as production-secure.

### Slice 9 — Streaming the agent's reasoning ✅

A live triage takes ten to thirty seconds, most of it real round-trips to Nokia.
Delivered as one silent wait it looks broken. Tool calls now stream as they
happen over newline-delimited JSON — not Server-Sent Events, because the
browser's `EventSource` cannot send an Authorization header.

Measured: steps landed at 7.7s, 8.5s and 9.5s with the report at 11s.

### Remaining

- **Deployment** — `render.yaml` is ready and the build path is verified, but
  nothing has been deployed. This gates the demo video.
- **Frontend tests** — still none. The socket hook and triage panel are the most
  intricate code in the project and the least covered.
- **Evals** — whether the agent's output is *good* is unmeasured. Grounded is
  not the same as useful.

## Engineering principles

- Begin with deterministic business rules; add AI only where language understanding is useful.
- Treat all data crossing process or network boundaries as untrusted.
- Keep route handlers thin and domain behavior testable outside the framework.
- Prefer one deployable modular application until scale proves otherwise.
- Never let the AI execute network changes autonomously in the MVP.
