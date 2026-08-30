from datetime import UTC, datetime

from app.models import Alarm, Incident, IncidentSeverity, IncidentStatus


INCIDENTS: tuple[Incident, ...] = (
    Incident(
        id="INC-1001",
        site_id="RUH-104",
        title="Backhaul connectivity loss",
        severity=IncidentSeverity.CRITICAL,
        status=IncidentStatus.INVESTIGATING,
        affected_subscribers=1240,
        probable_cause="Fiber backhaul interruption",
        opened_at=datetime(2026, 7, 21, 8, 15, tzinfo=UTC),
        # Stored out of chronological order on purpose: alarms reach a real
        # collector in arrival order, not event order. Ordering is a
        # presentation concern, so the frontend sorts them.
        alarms=[
            Alarm(
                id="ALM-5003",
                code="S1_LINK_FAILURE",
                message="S1 control-plane link to the core network was lost",
                occurred_at=datetime(2026, 7, 21, 8, 15, 12, tzinfo=UTC),
            ),
            Alarm(
                id="ALM-5001",
                code="BACKHAUL_DOWN",
                message="Fiber backhaul link is unavailable",
                occurred_at=datetime(2026, 7, 21, 8, 14, 3, tzinfo=UTC),
            ),
            Alarm(
                id="ALM-5004",
                code="VOLTE_REG_FAILURE",
                message="VoLTE registrations are failing for attached subscribers",
                occurred_at=datetime(2026, 7, 21, 8, 16, 41, tzinfo=UTC),
            ),
            Alarm(
                id="ALM-5002",
                code="CELL_OUT_OF_SERVICE",
                message="Cell RUH-104-C2 stopped carrying subscriber traffic",
                occurred_at=datetime(2026, 7, 21, 8, 14, 58, tzinfo=UTC),
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
        opened_at=datetime(2026, 7, 21, 9, 5, tzinfo=UTC),
        alarms=[
            Alarm(
                id="ALM-5011",
                code="PACKET_LOSS_HIGH",
                message="Packet loss exceeded the operational threshold",
                occurred_at=datetime(2026, 7, 21, 9, 4, 22, tzinfo=UTC),
            ),
            Alarm(
                id="ALM-5012",
                code="MW_SNR_DEGRADED",
                message="Microwave signal-to-noise ratio fell below the design margin",
                occurred_at=datetime(2026, 7, 21, 9, 6, 5, tzinfo=UTC),
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
        opened_at=datetime(2026, 7, 20, 18, 40, tzinfo=UTC),
        alarms=[
            Alarm(
                id="ALM-4998",
                code="POWER_UNSTABLE",
                message="Site voltage changed outside the stable range",
                occurred_at=datetime(2026, 7, 20, 18, 39, tzinfo=UTC),
            )
        ],
    ),
)


def list_incidents() -> list[Incident]:
    """Return a fresh list so callers cannot mutate the stored tuple."""
    return list(INCIDENTS)
