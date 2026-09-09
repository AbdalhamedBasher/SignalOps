# SignalOps AI

Autonomous telecom incident triage. Raw network alarms are correlated into
incidents, an AI agent consults live CAMARA network APIs to establish whether
subscribers are genuinely affected, and approved runbook procedures reach an
engineer with citations and a decision to make.

Built for the **GSMA MENA Ignite Hackathon** under the *Industrial & Enterprise
AI Automation* theme, on **Nokia Network as Code**.

---

## What problem it solves

One fibre cut at a cell site does not produce one alarm. It produces a cascade —
backhaul down, cells out of service, control-plane link lost, VoLTE
registrations failing — arriving out of order, within seconds. A legacy NOC
board shows four tickets and a subscriber-impact number read from a static
inventory table written months ago.

SignalOps collapses the cascade into one incident, then asks the network the
question the inventory table cannot answer: **are subscribers actually cut off
right now?**

That answer can contradict the alarm, and that is the point. An incident whose
equipment is alarming while every device stays reachable is a callout that did
not need to happen.

---

## How it works

```text
Alarms POSTed to /api/alarms  (collector role only)
        │
        ▼  deterministic correlation — same site, still open, sliding 15-minute window
   One incident, severity derived from its worst alarm
        │
        ▼  retrieval — alarm codes matched against approved runbooks
   Cited procedures, supervisor-gated where the runbook says so
        │
        ▼  the AI agent decides which network signals it needs
   ┌──────────────────────────────────────────────────────┐
   │  CAMARA Device Reachability Status   ← are they cut off?
   │  CAMARA Congestion Insights          ← is the site degraded?
   │  CAMARA Location Verification        ← has the engineer arrived?
   └──────────────────────────────────────────────────────┘
        │
        ▼  verdict + evidence + cited actions, streamed as it works
   Engineer approves or rejects. Nothing touches the network without them.
```

The agent is a **Google Gemini** model driven by **Pydantic AI**. The CAMARA
APIs are tools it chooses to call, not buttons a user presses.

---

## The three CAMARA APIs

All called through Nokia's official `network-as-code` SDK. Every reading records
which source answered.

| API | Question it answers | Endpoint |
| --- | --- | --- |
| Device Reachability Status | Can devices at this site still be reached? | `device-status/device-reachability-status/v1/retrieve` |
| Congestion Insights | Is the site congested, over what window? | `congestion-insights/v0/query` |
| Location Verification | Is the dispatched engineer within 2 km of the site? | `location/verify` |

**On honesty.** A free Network as Code account runs in Nokia's *Simulator
mode*: the API integration is real, the network data behind it is Nokia's
simulation. We do not claim live commercial subscriber telemetry.

We also measured which readings actually discriminate. In Simulator mode,
Location Verification returns `TRUE` for Riyadh, Sydney and Reykjavik alike — so
that reading marks itself non-discriminating, and the agent is instructed never
to report an engineer as on site on the strength of it.

Without a Nokia key, a deterministic local simulator answers instead, seeded
from the incident board so its readings stay consistent with what the board
reports. Every reading is labelled on screen, so simulated and platform data can
never be confused.

---

## Quick start

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

`alembic upgrade head` is required before the first start — the API refuses to
boot without a schema rather than failing later with a confusing SQL error.
Seed incidents, users and runbooks are inserted automatically into an empty
database.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:5173`. It signs in automatically as the
demo engineer; use the operator switcher in the header to act as the supervisor.

### Demo logins

| Username | Role | Can do |
| --- | --- | --- |
| `nadia.k` | engineer | View the board, retrieve guidance, run triage, approve ordinary procedures |
| `sam.o` | supervisor | Everything an engineer can, plus approve supervisor-gated procedures |
| `collector-01` | collector | Post alarms only — a machine principal, cannot approve anything |

Passwords are the `SEED_*_PASSWORD` settings in `app/config.py`. They are
development credentials for a demo; this is not a production auth posture.

### Watch it work

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\simulate.py --site RUH-315 --retry-last
```

Four alarms seconds apart collapse into one critical incident; the redelivered
final alarm is recognised rather than counted twice. Leave the dashboard open —
the incident appears and climbs in severity without a reload. Kill the API and
the header indicator turns red and retries; restart it and the dashboard
reconnects and re-reads the board on its own.

---

## Optional: the AI agent and live network

Both are off unless configured, and the product works without either.

```powershell
# Google AI Studio issues a free key with no credit card
$env:GOOGLE_API_KEY = "..."

# Nokia Network as Code — register free at networkascode.nokia.io
$env:NOKIA_API_KEY = "..."
```

With no `GOOGLE_API_KEY`, triage returns `503` with an explanation and nothing
else changes. With no `NOKIA_API_KEY`, the CAMARA calls run against the local
simulator.

Put both in `backend/.env` (gitignored) rather than exporting them.

---

## Endpoints

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | none | Liveness. Deliberately open — load balancers have no credentials |
| `POST` | `/api/auth/login` | none | Exchange credentials for a bearer token |
| `GET` | `/api/auth/me` | any | Who the current token belongs to |
| `GET` | `/api/incidents` | any | The incident board, newest first |
| `POST` | `/api/alarms` | collector | Ingest one alarm; `201` recorded, `200` recognised redelivery |
| `GET` | `/ws/incidents` | any | WebSocket push of incident changes. Token in the query string |
| `POST` | `/api/incidents/{id}/recommendations` | engineer | Match alarms against approved runbooks |
| `POST` | `/api/recommendations/{id}/approve` \| `/reject` | engineer¹ | Record a decision |
| `POST` | `/api/incidents/{id}/triage` | engineer | Run the agent; returns the finished report |
| `POST` | `/api/incidents/{id}/triage/stream` | engineer | Same, streaming each tool call as it happens |
| `GET` | `/api/incidents/{id}/audit` | engineer | Append-only record of who decided what |

¹ A runbook section carrying a `Requires: supervisor` line can only be approved
by a supervisor. Rejection stays open to engineers — declining to act is always
safe.

Interactive documentation at `http://localhost:8000/docs`.

---

## Runbooks

Approved procedures live in `backend/runbooks/` as Markdown, version-controlled
alongside the code, and are imported at startup.

```markdown
## Never reset equipment blind
Applies to: CELL_OUT_OF_SERVICE, POWER_UNSTABLE
Requires: supervisor

1. A reset destroys the diagnostic state that explains the fault.
```

`## Heading` starts a section, `Applies to:` names the alarm codes it covers,
and `Requires: supervisor` gates its approval. Import is keyed on filename and
skips files already imported — so **editing a runbook after first deploy has no
effect** until the database is reset.

---

## Design decisions worth knowing

- **Alarm timestamps must carry a UTC offset.** A naive timestamp is ambiguous,
  and this system exists to establish the order events happened in. Guessing UTC
  could invert the apparent cause of a cascade, so `422` instead.
- **Ingestion is idempotent** on the sender's `external_id`, enforced by a unique
  index rather than application code. Collectors retry; that is correct
  behaviour, not an error.
- **Identity comes from the access token, never the request body.** A caller who
  can name themselves can name anyone.
- **Nothing generated reaches an engineer uncited.** Every runbook section the
  agent cites is verified against what it was actually given; a report citing
  anything else is refused outright rather than shown with the bad citation
  removed.
- **The AI never touches the network.** Its output is a recommendation a human
  approves or rejects.

---

## Verify

```powershell
cd backend
pytest                       # 98 tests
python -m ruff check .

cd ../frontend
npm run typecheck
npm run build
```

No test calls Gemini or Nokia. The agent is driven by Pydantic AI's `TestModel`,
which exercises every tool it exposes — proving the CAMARA APIs are wired and
callable without spending quota.

---

## Deployment

`render.yaml` at the repo root provisions the API, the static dashboard and a
managed Postgres. Render prompts for the only two secrets it cannot invent —
`GOOGLE_API_KEY` and `NOKIA_API_KEY`. `JWT_SECRET` is generated once at provision
time and persisted, so tokens survive a restart; the app deliberately has no
default for it, because a signing secret shipped in source is the same as no
authentication at all.

Two things are normalised on the way in, both of which otherwise fail only once
deployed:

- `DATABASE_URL` — Render injects `postgres://`, which SQLAlchemy 2.0 no longer
  accepts. Alembic normalises it too, not just the app: migrations run *first*
  on Render, so a fix in only one place still dies on boot.
- `VITE_API_URL` — Render's `property: host` yields a bare hostname. Without a
  scheme, `fetch` reads it as a relative path, and the WebSocket feed must be
  upgraded to `wss://` or the browser refuses it from an https page.

On the free plan the API sleeps after inactivity and takes roughly 50 seconds to
wake. Open the dashboard once before any demo.
