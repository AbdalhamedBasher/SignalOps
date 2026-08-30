"""
Storage schema.

These are deliberately separate from the Pydantic models in `models.py`. Those
describe the contract the API promises and the shape the rules operate on; these
describe how rows are laid out on disk. Letting one class do both jobs means a
storage decision silently becomes an API change, and vice versa.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UtcDateTime


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # The numeric half of the identifier, kept as an integer so the next one
    # can be found with MAX(). Sorting the string form would break the moment
    # the sequence passes four digits, because "INC-10000" sorts below
    # "INC-9999".
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    site_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    affected_subscribers: Mapped[int] = mapped_column(Integer)
    probable_cause: Mapped[str] = mapped_column(String(200))
    opened_at: Mapped[datetime] = mapped_column(UtcDateTime)

    alarms: Mapped[list["AlarmRow"]] = relationship(
        back_populates="incident",
        cascade="all, delete-orphan",
        # Loads every incident's alarms in one extra query instead of one per
        # incident. Listing the board would otherwise be a textbook N+1.
        lazy="selectin",
        # Arrival order, which is what a collector's ascending ids record, and
        # which is deliberately *not* the order the events happened in. An
        # unordered SELECT would leave this to the query planner and let the
        # API's behaviour drift between engines.
        order_by="AlarmRow.number",
    )


class AlarmRow(Base):
    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    site_id: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(400))
    severity: Mapped[str] = mapped_column(String(16))
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
    # The database, not the application, is what makes ingestion idempotent.
    # SQL permits many NULLs in a unique column, so alarms that arrive without
    # a collector identifier do not collide with each other.
    external_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )

    incident: Mapped[IncidentRow] = relationship(back_populates="alarms")
