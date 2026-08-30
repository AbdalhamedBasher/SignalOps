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
twice. Reload the dashboard to see it.

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
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`. Useful endpoints:

- `GET /health`
- `GET /api/incidents`
- `POST /api/alarms` — ingest one alarm; returns the incident it was correlated
  into, with `201` when recorded and `200` when recognised as a redelivery
- Interactive documentation: `http://localhost:8000/docs`

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
