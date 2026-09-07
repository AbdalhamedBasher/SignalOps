"""
Storage schema.

These are deliberately separate from the Pydantic models in `models.py`. Those
describe the contract the API promises and the shape the rules operate on; these
describe how rows are laid out on disk. Letting one class do both jobs means a
storage decision silently becomes an API change, and vice versa.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
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


class UserRow(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(120), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), index=True)
    # Only ever the Argon2id hash. Nothing in this application stores, logs, or
    # returns a password.
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class RunbookRow(Base):
    __tablename__ = "runbooks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    # The file the text came from, so a citation can be traced back to the
    # reviewed document rather than stopping at a heading.
    source_name: Mapped[str] = mapped_column(String(200), unique=True)
    loaded_at: Mapped[datetime] = mapped_column(UtcDateTime)

    sections: Mapped[list["RunbookSectionRow"]] = relationship(
        back_populates="runbook",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RunbookSectionRow.position",
    )


class RunbookSectionRow(Base):
    __tablename__ = "runbook_sections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    runbook_id: Mapped[str] = mapped_column(
        ForeignKey("runbooks.id", ondelete="CASCADE"), index=True
    )
    heading: Mapped[str] = mapped_column(String(200))
    anchor: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    # Declared in the runbook itself with a `Requires: supervisor` line. The
    # authority to accept a procedure belongs with the people who wrote it, not
    # with this codebase.
    requires_supervisor: Mapped[bool] = mapped_column(Boolean, default=False)

    runbook: Mapped[RunbookRow] = relationship(back_populates="sections")
    codes: Mapped[list["RunbookSectionCodeRow"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RunbookSectionCodeRow(Base):
    """
    Which alarm codes a section applies to.

    A separate table rather than a comma-joined column, so retrieval is an
    indexed lookup on `code` instead of a substring match that would happily
    confuse POWER_UNSTABLE with SITE_POWER_UNSTABLE.
    """

    __tablename__ = "runbook_section_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    section_id: Mapped[str] = mapped_column(
        ForeignKey("runbook_sections.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(64), index=True)

    section: Mapped[RunbookSectionRow] = relationship(back_populates="codes")


class RecommendationRow(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("runbook_sections.id", ondelete="CASCADE"), index=True
    )
    rationale: Mapped[str] = mapped_column(String(400))
    matched_codes: Mapped[str] = mapped_column(String(400))
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    modified_steps: Mapped[str | None] = mapped_column(Text, nullable=True)

    section: Mapped[RunbookSectionRow] = relationship(lazy="selectin")

    __table_args__ = (
        # One incident should not accumulate the same section twice, however
        # many times recommendations are regenerated for it.
        UniqueConstraint("incident_id", "section_id", name="uq_recommendation_target"),
    )


class TriageRow(Base):
    """
    A triage report, kept because it was shown to an engineer.

    The model id and the cited sections are stored alongside the prose so that
    a decision made after reading it can be reconstructed later — including
    which version of which model wrote it.
    """

    __tablename__ = "triage_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    # What the agent concluded about real customer impact, after calling the
    # network APIs rather than trusting the alarms.
    verdict: Mapped[str] = mapped_column(String(16), default="unknown")
    summary: Mapped[str] = mapped_column(Text)
    # The network readings it relied on, and the tools it chose to call.
    evidence: Mapped[str] = mapped_column(Text, default="[]")
    trace: Mapped[str] = mapped_column(Text, default="[]")
    first_actions: Mapped[str] = mapped_column(Text)
    cited_section_ids: Mapped[str] = mapped_column(String(400))
    gaps: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)


class AuditEventRow(Base):
    """
    An append-only record of who decided what.

    Nothing in the application updates or deletes these rows. An audit trail
    that can be edited is not one.
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    recommendation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, index=True)
