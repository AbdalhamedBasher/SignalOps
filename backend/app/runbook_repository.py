"""
Storage and workflow for runbooks, recommendations, and the audit trail.
"""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.generation import deserialise_actions, serialise_actions
from app.models import (
    AuditEvent,
    GeneratedBriefing,
    Incident,
    Recommendation,
    RecommendationDecision,
    RecommendationStatus,
    RunbookSection,
    StoredBriefing,
)
from app.retrieval import retrieve_for_incident
from app.runbooks import ParsedRunbook, load_runbook_directory
from app.tables import (
    AuditEventRow,
    BriefingRow,
    RecommendationRow,
    RunbookRow,
    RunbookSectionCodeRow,
    RunbookSectionRow,
)

RUNBOOK_DIRECTORY = Path(__file__).resolve().parents[1] / "runbooks"


def to_section(row: RunbookSectionRow) -> RunbookSection:
    return RunbookSection(
        id=row.id,
        runbook_id=row.runbook_id,
        runbook_title=row.runbook.title,
        source_name=row.runbook.source_name,
        heading=row.heading,
        anchor=row.anchor,
        body=row.body,
        applies_to=[code.code for code in row.codes],
    )


def to_recommendation(row: RecommendationRow) -> Recommendation:
    return Recommendation(
        id=row.id,
        incident_id=row.incident_id,
        section=to_section(row.section),
        rationale=row.rationale,
        matched_codes=[code for code in row.matched_codes.split(",") if code],
        status=RecommendationStatus(row.status),
        created_at=row.created_at,
        decided_at=row.decided_at,
        decided_by=row.decided_by,
        decision_note=row.decision_note,
        modified_steps=row.modified_steps,
    )


def to_briefing(row: BriefingRow) -> StoredBriefing:
    return StoredBriefing(
        id=row.id,
        incident_id=row.incident_id,
        summary=row.summary,
        first_actions=deserialise_actions(row.first_actions),
        cited_section_ids=[
            section_id for section_id in row.cited_section_ids.split(",") if section_id
        ],
        gaps=row.gaps,
        model=row.model,
        generated_at=row.generated_at,
    )


def to_audit_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        incident_id=row.incident_id,
        recommendation_id=row.recommendation_id,
        action=row.action,
        actor=row.actor,
        detail=row.detail,
        occurred_at=row.occurred_at,
    )


class RunbookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------------------------------------------------------- runbooks

    def load_from_disk(self, directory: Path = RUNBOOK_DIRECTORY) -> int:
        """
        Import the approved runbooks, skipping any file already imported.

        Keyed on the source file name rather than the content, so re-running
        this on every start does not duplicate sections. Re-importing a changed
        file is deliberately not handled here: replacing guidance that
        recommendations already cite is a versioning problem, not a load-time
        one, and pretending otherwise would silently rewrite history.
        """
        if not directory.exists():
            return 0

        known = set(
            self._session.scalars(select(RunbookRow.source_name)).all()
        )

        imported = 0

        for source_name, parsed in load_runbook_directory(directory):
            if source_name in known:
                continue

            self._insert_runbook(source_name, parsed)
            imported += 1

        return imported

    def _insert_runbook(self, source_name: str, parsed: ParsedRunbook) -> RunbookRow:
        runbook_number = self._next_number(RunbookRow)
        # Taken once and then counted up locally: these rows are not flushed
        # until the end, so asking the database again inside the loop would
        # return the same answer every time.
        first_section_number = self._next_number(RunbookSectionRow)

        runbook = RunbookRow(
            id=f"RB-{runbook_number:04d}",
            number=runbook_number,
            title=parsed.title,
            source_name=source_name,
            loaded_at=datetime.now(UTC),
        )

        for offset, parsed_section in enumerate(parsed.sections):
            section_number = first_section_number + offset

            runbook.sections.append(
                RunbookSectionRow(
                    id=f"RBS-{section_number:04d}",
                    number=section_number,
                    heading=parsed_section.heading,
                    anchor=parsed_section.anchor,
                    body=parsed_section.body,
                    position=parsed_section.position,
                    codes=[
                        RunbookSectionCodeRow(code=code)
                        for code in parsed_section.applies_to
                    ],
                )
            )

        self._session.add(runbook)
        self._session.flush()

        return runbook

    def list_sections(self) -> list[RunbookSection]:
        rows = self._session.scalars(
            select(RunbookSectionRow).order_by(RunbookSectionRow.number)
        ).all()

        return [to_section(row) for row in rows]

    # --------------------------------------------------------- recommendations

    def recommendations_for(self, incident_id: str) -> list[Recommendation]:
        rows = self._session.scalars(
            select(RecommendationRow)
            .where(RecommendationRow.incident_id == incident_id)
            .order_by(RecommendationRow.number)
        ).all()

        return [to_recommendation(row) for row in rows]

    def propose_for(self, incident: Incident) -> list[Recommendation]:
        """
        Retrieve applicable runbook sections and record them as proposals.

        Sections already proposed for this incident are left untouched, so
        regenerating after new alarms arrive adds what is newly relevant without
        resetting a decision an engineer has already made.
        """
        existing = {
            row.section_id: row
            for row in self._session.scalars(
                select(RecommendationRow).where(
                    RecommendationRow.incident_id == incident.id
                )
            ).all()
        }

        for retrieved in retrieve_for_incident(incident, self.list_sections()):
            if retrieved.section.id in existing:
                continue

            number = self._next_number(RecommendationRow)
            row = RecommendationRow(
                id=f"REC-{number:04d}",
                number=number,
                incident_id=incident.id,
                section_id=retrieved.section.id,
                rationale=retrieved.rationale,
                matched_codes=",".join(retrieved.matched_codes),
                status=RecommendationStatus.PROPOSED.value,
                created_at=datetime.now(UTC),
            )

            self._session.add(row)
            self._session.flush()

            self.record(
                incident_id=incident.id,
                recommendation_id=row.id,
                action="recommendation.proposed",
                actor="signalops",
                detail=(
                    f"Proposed {retrieved.section.citation} "
                    f"({retrieved.rationale})"
                ),
            )

        return self.recommendations_for(incident.id)

    def decide(
        self,
        recommendation_id: str,
        *,
        approved: bool,
        decision: RecommendationDecision,
    ) -> Recommendation | None:
        row = self._session.get(RecommendationRow, recommendation_id)

        if row is None:
            return None

        row.status = (
            RecommendationStatus.APPROVED.value
            if approved
            else RecommendationStatus.REJECTED.value
        )
        row.decided_at = datetime.now(UTC)
        row.decided_by = decision.decided_by
        row.decision_note = decision.note
        row.modified_steps = decision.modified_steps if approved else None

        was_modified = approved and decision.modified_steps is not None
        action = "recommendation.rejected"

        if approved:
            action = (
                "recommendation.approved_with_modification"
                if was_modified
                else "recommendation.approved"
            )

        self.record(
            incident_id=row.incident_id,
            recommendation_id=row.id,
            action=action,
            actor=decision.decided_by,
            detail=decision.note or to_section(row.section).citation,
        )

        self._session.flush()

        return to_recommendation(row)

    # ---------------------------------------------------------------- briefings

    def latest_briefing(self, incident_id: str) -> StoredBriefing | None:
        row = self._session.scalars(
            select(BriefingRow)
            .where(BriefingRow.incident_id == incident_id)
            .order_by(BriefingRow.number.desc())
            .limit(1)
        ).first()

        return None if row is None else to_briefing(row)

    def store_briefing(
        self, incident_id: str, briefing: GeneratedBriefing
    ) -> StoredBriefing:
        number = self._next_number(BriefingRow)
        row = BriefingRow(
            id=f"BRF-{number:04d}",
            number=number,
            incident_id=incident_id,
            summary=briefing.summary,
            first_actions=serialise_actions(briefing.first_actions),
            cited_section_ids=",".join(briefing.cited_section_ids),
            gaps=briefing.gaps,
            model=briefing.model,
            generated_at=datetime.now(UTC),
        )

        self._session.add(row)
        self._session.flush()

        self.record(
            incident_id=incident_id,
            recommendation_id=None,
            action="briefing.generated",
            actor=briefing.model,
            detail=(
                f"Generated a briefing citing "
                f"{', '.join(briefing.cited_section_ids) or 'no sections'}"
            ),
        )

        return to_briefing(row)

    # ------------------------------------------------------------------- audit

    def record(
        self,
        *,
        incident_id: str,
        recommendation_id: str | None,
        action: str,
        actor: str,
        detail: str,
    ) -> AuditEvent:
        number = self._next_number(AuditEventRow)
        row = AuditEventRow(
            id=f"AUD-{number:04d}",
            number=number,
            incident_id=incident_id,
            recommendation_id=recommendation_id,
            action=action,
            actor=actor,
            detail=detail,
            occurred_at=datetime.now(UTC),
        )

        self._session.add(row)
        self._session.flush()

        return to_audit_event(row)

    def audit_for(self, incident_id: str) -> list[AuditEvent]:
        rows = self._session.scalars(
            select(AuditEventRow)
            .where(AuditEventRow.incident_id == incident_id)
            .order_by(AuditEventRow.number)
        ).all()

        return [to_audit_event(row) for row in rows]

    # --------------------------------------------------------------- internals

    def _next_number(self, model: type) -> int:
        return (self._session.scalar(select(func.max(model.number))) or 0) + 1
