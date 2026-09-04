"""
The persistence-backed replacement for the in-memory store.

The correlation rules stay exactly where they were: this class loads rows,
converts them to the domain models the rules understand, asks the rules what
to do, and writes the answer back. No rule logic lives here.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog import alarm_definition
from app.correlation import attach_alarm, find_correlated_incident, open_incident
from app.models import (
    Alarm,
    AlarmIngestResult,
    AlarmSubmission,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from app.tables import AlarmRow, IncidentRow


def to_alarm(row: AlarmRow) -> Alarm:
    return Alarm(
        id=row.id,
        site_id=row.site_id,
        code=row.code,
        message=row.message,
        severity=IncidentSeverity(row.severity),
        occurred_at=row.occurred_at,
        external_id=row.external_id,
    )


def to_incident(row: IncidentRow) -> Incident:
    return Incident(
        id=row.id,
        site_id=row.site_id,
        title=row.title,
        severity=IncidentSeverity(row.severity),
        status=IncidentStatus(row.status),
        affected_subscribers=row.affected_subscribers,
        probable_cause=row.probable_cause,
        opened_at=row.opened_at,
        alarms=[to_alarm(alarm) for alarm in row.alarms],
    )


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_incidents(self) -> list[Incident]:
        # Newest fault first, which is what an operator scanning the board
        # wants. `number` breaks ties so the order is total and stable rather
        # than left to the query planner.
        rows = self._session.scalars(
            select(IncidentRow).order_by(
                IncidentRow.opened_at.desc(), IncidentRow.number.desc()
            )
        ).all()

        return [to_incident(row) for row in rows]

    def find_incident(self, incident_id: str) -> Incident | None:
        row = self._session.get(IncidentRow, incident_id)

        return None if row is None else to_incident(row)

    def ingest(self, submission: AlarmSubmission) -> AlarmIngestResult:
        already_seen = self._find_by_external_id(submission.external_id)
        if already_seen is not None:
            return AlarmIngestResult(
                incident=to_incident(already_seen.incident),
                incident_created=False,
                duplicate=True,
            )

        alarm = Alarm(
            id=self._next_identifier(AlarmRow, "ALM-"),
            site_id=submission.site_id,
            code=submission.code,
            message=submission.message,
            severity=alarm_definition(submission.code).severity,
            occurred_at=submission.occurred_at,
            external_id=submission.external_id,
        )

        candidate_rows = self._open_rows_at(submission.site_id)
        candidates = [to_incident(row) for row in candidate_rows]

        match = find_correlated_incident(candidates, alarm)
        incident_created = match is None

        try:
            # Every write happens inside a savepoint so that losing a race on
            # external_id rolls back exactly this attempt. Opening it *before*
            # adding anything is the point: a savepoint only undoes work done
            # after it was taken.
            with self._session.begin_nested():
                if match is None:
                    incident = open_incident(
                        self._next_identifier(IncidentRow, "INC-"), alarm
                    )
                    incident_row = self._insert_incident(incident)
                else:
                    incident_row = next(
                        row for row in candidate_rows if row.id == match.id
                    )
                    incident = attach_alarm(match, alarm)
                    self._apply_incident_fields(incident_row, incident)
                    incident_row.alarms.append(
                        self._build_alarm_row(alarm, incident.id)
                    )

                self._session.flush()
        except IntegrityError as error:
            return self._resolve_lost_race(submission, error)

        return AlarmIngestResult(
            incident=to_incident(incident_row),
            incident_created=incident_created,
            duplicate=False,
        )

    def _resolve_lost_race(
        self, submission: AlarmSubmission, error: IntegrityError
    ) -> AlarmIngestResult:
        """
        Another request inserted this same alarm while we were deciding.

        The unique constraint is what actually prevents the double insert; this
        only reports the outcome the caller would have got had it arrived a
        moment later.
        """
        winner = self._find_by_external_id(submission.external_id)

        if winner is None:
            # The constraint fired for some other reason, which is a real bug
            # rather than a duplicate delivery.
            raise error

        return AlarmIngestResult(
            incident=to_incident(winner.incident),
            incident_created=False,
            duplicate=True,
        )

    def _find_by_external_id(self, external_id: str | None) -> AlarmRow | None:
        if external_id is None:
            return None

        return self._session.scalar(
            select(AlarmRow).where(AlarmRow.external_id == external_id)
        )

    def _open_rows_at(self, site_id: str) -> list[IncidentRow]:
        return list(
            self._session.scalars(
                select(IncidentRow).where(
                    IncidentRow.site_id == site_id,
                    IncidentRow.status != IncidentStatus.RESOLVED.value,
                )
            ).all()
        )

    def _next_identifier(self, model: type, prefix: str) -> str:
        highest = self._session.scalar(select(func.max(model.number))) or 0

        return f"{prefix}{highest + 1:04d}"

    def _insert_incident(self, incident: Incident) -> IncidentRow:
        row = to_incident_row(incident)
        self._session.add(row)

        return row

    def _build_alarm_row(self, alarm: Alarm, incident_id: str) -> AlarmRow:
        return to_alarm_row(alarm, incident_id)

    def _apply_incident_fields(self, row: IncidentRow, incident: Incident) -> None:
        """Copy back the fields the correlation rules may have changed."""
        row.title = incident.title
        row.severity = incident.severity.value
        row.probable_cause = incident.probable_cause
        row.opened_at = incident.opened_at


def to_alarm_row(alarm: Alarm, incident_id: str) -> AlarmRow:
    return AlarmRow(
        id=alarm.id,
        number=number_of(alarm.id),
        incident_id=incident_id,
        site_id=alarm.site_id,
        code=alarm.code,
        message=alarm.message,
        severity=alarm.severity.value,
        occurred_at=alarm.occurred_at,
        external_id=alarm.external_id,
    )


def to_incident_row(incident: Incident) -> IncidentRow:
    return IncidentRow(
        id=incident.id,
        number=number_of(incident.id),
        site_id=incident.site_id,
        title=incident.title,
        severity=incident.severity.value,
        status=incident.status.value,
        affected_subscribers=incident.affected_subscribers,
        probable_cause=incident.probable_cause,
        opened_at=incident.opened_at,
        alarms=[to_alarm_row(alarm, incident.id) for alarm in incident.alarms],
    )


def number_of(identifier: str) -> int:
    """`INC-1003` -> 1003. Identifiers are always prefix plus digits."""
    return int(identifier.rsplit("-", 1)[1])
