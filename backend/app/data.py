"""
Seed incidents used to start the application with a believable board.

These stand in for history that a real deployment would have in its database.
Alarm severity is looked up from the catalog rather than written out here, so
the fixtures cannot drift away from the rules the running system applies.
"""

from datetime import UTC, datetime

from app.catalog import alarm_definition
from app.models import Alarm, Incident, IncidentSeverity, IncidentStatus


def seed_alarm(
    alarm_id: str,
    site_id: str,
    code: str,
    message: str,
    occurred_at: datetime,
) -> Alarm:
    return Alarm(
        id=alarm_id,
        site_id=site_id,
        code=code,
        message=message,
        severity=alarm_definition(code).severity,
        occurred_at=occurred_at,
    )


SEED_INCIDENTS: tuple[Incident, ...] = (
    Incident(
        id="INC-1001",
        site_id="RUH-104",
        title="Backhaul connectivity loss",
        severity=IncidentSeverity.CRITICAL,
        status=IncidentStatus.INVESTIGATING,
        affected_subscribers=1240,
        probable_cause="Fiber backhaul interruption",
        opened_at=datetime(2026, 7, 21, 8, 14, 3, tzinfo=UTC),
        # Stored out of chronological order on purpose: alarms reach a real
        # collector in arrival order, not event order. Ordering is a
        # presentation concern, so the frontend sorts them.
        alarms=[
            seed_alarm(
                "ALM-5003",
                "RUH-104",
                "S1_LINK_FAILURE",
                "S1 control-plane link to the core network was lost",
                datetime(2026, 7, 21, 8, 15, 12, tzinfo=UTC),
            ),
            seed_alarm(
                "ALM-5001",
                "RUH-104",
                "BACKHAUL_DOWN",
                "Fiber backhaul link is unavailable",
                datetime(2026, 7, 21, 8, 14, 3, tzinfo=UTC),
            ),
            seed_alarm(
                "ALM-5004",
                "RUH-104",
                "VOLTE_REG_FAILURE",
                "VoLTE registrations are failing for attached subscribers",
                datetime(2026, 7, 21, 8, 16, 41, tzinfo=UTC),
            ),
            seed_alarm(
                "ALM-5002",
                "RUH-104",
                "CELL_OUT_OF_SERVICE",
                "Cell RUH-104-C2 stopped carrying subscriber traffic",
                datetime(2026, 7, 21, 8, 14, 58, tzinfo=UTC),
            ),
        ],
    ),
    Incident(
        id="INC-1002",
        site_id="RUH-207",
        title="Elevated packet loss",
        severity=IncidentSeverity.HIGH,
        status=IncidentStatus.ACTIVE,
        affected_subscribers=430,
        probable_cause="Microwave link degradation",
        opened_at=datetime(2026, 7, 21, 9, 4, 22, tzinfo=UTC),
        alarms=[
            seed_alarm(
                "ALM-5011",
                "RUH-207",
                "PACKET_LOSS_HIGH",
                "Packet loss exceeded the operational threshold",
                datetime(2026, 7, 21, 9, 4, 22, tzinfo=UTC),
            ),
            seed_alarm(
                "ALM-5012",
                "RUH-207",
                "MW_SNR_DEGRADED",
                "Microwave signal-to-noise ratio fell below the design margin",
                datetime(2026, 7, 21, 9, 6, 5, tzinfo=UTC),
            ),
        ],
    ),
    Incident(
        id="INC-0998",
        site_id="JED-031",
        title="Site power instability",
        severity=IncidentSeverity.MEDIUM,
        status=IncidentStatus.RESOLVED,
        affected_subscribers=95,
        probable_cause="Backup battery degradation",
        opened_at=datetime(2026, 7, 20, 18, 39, tzinfo=UTC),
        alarms=[
            seed_alarm(
                "ALM-4998",
                "JED-031",
                "POWER_UNSTABLE",
                "Site voltage changed outside the stable range",
                datetime(2026, 7, 20, 18, 39, tzinfo=UTC),
            ),
        ],
    ),
)
