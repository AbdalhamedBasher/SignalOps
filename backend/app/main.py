from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.data import list_incidents
from app.models import Incident

app = FastAPI(
    title="SignalOps API",
    version="0.1.0",
    description="Telecom incident-management API for the SignalOps AI MVP.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/incidents", response_model=list[Incident])
def get_incidents() -> list[Incident]:
    return list_incidents()
