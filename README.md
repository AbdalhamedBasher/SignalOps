# SignalOps AI

A learning-first telecom incident-management MVP built with React, TypeScript, and FastAPI.

## Current vertical slice

The first slice proves the complete data flow:

```text
FastAPI in-memory incident data
        ↓ JSON over HTTP
React API client
        ↓ typed state
Dashboard metrics + incident cards
```

The backend validates every outgoing incident with Pydantic. The frontend treats network data as untrusted and validates its shape before putting it into React state.

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
- Interactive documentation: `http://localhost:8000/docs`

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
