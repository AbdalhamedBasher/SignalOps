"""Put the demonstration incidents into an empty database."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.data import SEED_INCIDENTS
from app.repository import to_incident_row
from app.tables import IncidentRow


def seed_if_empty(session: Session) -> int:
    """
    Insert the seed incidents, but only into a database with none.

    Guarding on emptiness rather than on individual ids means restarting the
    application never resurrects an incident somebody deliberately removed, and
    never collides with ids the running system has since handed out.

    Returns how many incidents were inserted.
    """
    existing = session.scalar(select(func.count()).select_from(IncidentRow)) or 0

    if existing:
        return 0

    for incident in SEED_INCIDENTS:
        session.add(to_incident_row(incident))

    session.commit()

    return len(SEED_INCIDENTS)
