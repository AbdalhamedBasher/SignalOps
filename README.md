# SignalOps AI

A learning-first telecom incident-management MVP built with React, TypeScript, and FastAPI.

## Current vertical slice

Raw alarms arrive, get grouped into incidents by deterministic rules, and reach
the dashboard as one actionable story:

```text
Alarm posted to /api/alarms
        ↓ catalog lookup (severity, title, probable cause)
Correlation rules: same site, still open, inside the window?
        ↓ join an incident, or open a new one
In-memory incident store
        ↓ JSON over HTTP
React API client (validates every field it relies on)
        ↓ typed state
Dashboard metrics, incident cards, alarm timeline
```

The backend validates every outgoing incident with Pydantic. The frontend treats network data as untrusted and validates its shape before putting it into React state.

## Watch correlation happen

With both servers running, replay a fault:

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\simulate.py --site RUH-315 --retry-last
```

Four alarms are posted seconds apart. They collapse into a single critical
incident, and the redelivered final alarm is recognised rather than counted
twice.

Leave the dashboard open while it runs: the incident appears, climbs in
severity, and lands in the live activity feed without a reload. Kill the API
and the header indicator turns red and starts retrying; bring it back and the
dashboard reconnects and re-reads the board on its own.

## Project structure

```text
signalops-ai/
├── backend/        FastAPI application and API tests
├── frontend/       React + TypeScript dashboard
└── docs/           MVP scope and implementation roadmap
```

## Run the backend on Windows

```powershell
cd backend
C:\Python314\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

`alembic upgrade head` creates the schema and is required before the first
start; the API refuses to boot without it rather than failing later with a
confusing SQL error. The seed incidents are inserted automatically the first
time the database is found empty.

Data lives in `backend/signalops.db` (SQLite) by default. To use PostgreSQL
instead, set `DATABASE_URL` and run the same migrations:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/signalops"
alembic upgrade head
```

The API runs at `http://localhost:8000`. Useful endpoints:

- `GET /health`
- `GET /api/incidents`
- `POST /api/alarms` — ingest one alarm; returns the incident it was correlated
  into, with `201` when recorded and `200` when recognised as a redelivery
- `GET /ws/incidents` — WebSocket that pushes each incident as it opens or
  changes. Send-only; clients re-read `/api/incidents` whenever they connect
- `POST /api/incidents/{id}/recommendations` — match the incident's alarms
  against the approved runbooks; `GET` the same path to read what was matched
- `POST /api/recommendations/{id}/approve` and `/reject` — record an engineer's
  decision, optionally with modified steps
- `GET /api/incidents/{id}/audit` — the append-only record of who decided what
- Interactive documentation: `http://localhost:8000/docs`

- `POST /api/incidents/{id}/briefing` — write a short orientation over the
  already-retrieved sections; `GET` returns the most recent one, or `null`

### Generated briefings (optional)

Off by default. To switch on, install the extra and provide Claude credentials:

```powershell
python -m pip install -e ".[dev,ai]"
$env:ENABLE_BRIEFINGS = "true"
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # or run `ant auth login`
```

The model is only ever given the runbook sections retrieval already matched,
and every section it cites is checked against that list — a briefing citing
anything else is refused rather than shown. With the feature off, the endpoint
returns `503` with an explanation and nothing else changes.

Runbooks live in `backend/runbooks/` as Markdown and are imported at startup.
A `## Heading` starts a section and an `Applies to: CODE_A, CODE_B` line under
it says which alarms it covers. Add a file, restart, and it is searchable.

Alarm timestamps must carry a UTC offset. A timestamp without one is rejected
with `422`, because ordering events correctly is the whole point of the system.

## Run the frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:5173` and calls the FastAPI server at `http://localhost:8000`.

## Verify the project

Backend:

```powershell
cd backend
pytest
```

Frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

## Learning rule

Do not rush to copy code. For every slice, be able to explain:

1. Where the data originates.
2. Which type or model describes it.
3. Which boundary validates it.
4. Which component owns the state.
5. What the user sees during loading, failure, emptiness, and success.
