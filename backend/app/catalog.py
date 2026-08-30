"""
Reference data used to interpret raw alarms.

This is the deterministic business-rules layer the MVP principles call for.
An alarm arrives as a bare code; everything an engineer needs to read on the
dashboard — how bad it is, what to call the incident, what probably caused it,
how many subscribers sit behind the site — is looked up here, not inferred.

Keeping it as plain data (rather than branching logic scattered through the
correlation code) means a new alarm type is a one-line change and is trivially
reviewable by a network engineer who does not read Python.
"""

from dataclasses import dataclass

from app.models import IncidentSeverity


@dataclass(frozen=True)
class AlarmDefinition:
    severity: IncidentSeverity
    # Used only when this alarm is the first of an incident, because the first
    # signal is the one that explains what went wrong.
    incident_title: str
    probable_cause: str


ALARM_CATALOG: dict[str, AlarmDefinition] = {
    "BACKHAUL_DOWN": AlarmDefinition(
        severity=IncidentSeverity.CRITICAL,
        incident_title="Backhaul connectivity loss",
        probable_cause="Fiber backhaul interruption",
    ),
    "CELL_OUT_OF_SERVICE": AlarmDefinition(
        severity=IncidentSeverity.CRITICAL,
        incident_title="Cell outage",
        probable_cause="Radio unit or transport fault",
    ),
    "S1_LINK_FAILURE": AlarmDefinition(
        severity=IncidentSeverity.HIGH,
        incident_title="Core signalling link failure",
        probable_cause="S1 control-plane transport interruption",
    ),
    "VOLTE_REG_FAILURE": AlarmDefinition(
        severity=IncidentSeverity.HIGH,
        incident_title="VoLTE service degradation",
        probable_cause="IMS registration failure",
    ),
    "PACKET_LOSS_HIGH": AlarmDefinition(
        severity=IncidentSeverity.HIGH,
        incident_title="Elevated packet loss",
        probable_cause="Microwave link degradation",
    ),
    "MW_SNR_DEGRADED": AlarmDefinition(
        severity=IncidentSeverity.MEDIUM,
        incident_title="Microwave link degradation",
        probable_cause="Signal-to-noise margin loss",
    ),
    "POWER_UNSTABLE": AlarmDefinition(
        severity=IncidentSeverity.MEDIUM,
        incident_title="Site power instability",
        probable_cause="Backup battery degradation",
    ),
    "TEMPERATURE_HIGH": AlarmDefinition(
        severity=IncidentSeverity.MEDIUM,
        incident_title="Site temperature alarm",
        probable_cause="Cooling system fault",
    ),
}


# An uncatalogued code is shown rather than dropped: a network element emitting
# something we have not classified yet is still evidence. Medium is chosen so an
# unknown alarm neither disappears among low-priority noise nor triggers a
# false critical.
UNKNOWN_ALARM = AlarmDefinition(
    severity=IncidentSeverity.MEDIUM,
    incident_title="Unclassified site alarm",
    probable_cause="Unrecognised alarm code, manual triage required",
)


# Subscribers served by each site. In a real deployment this comes from network
# inventory; here it is static so that impact figures stay deterministic.
SITE_SUBSCRIBERS: dict[str, int] = {
    "RUH-104": 1240,
    "RUH-207": 430,
    "RUH-315": 880,
    "JED-031": 95,
    "JED-118": 610,
    "DMM-052": 320,
}


def alarm_definition(code: str) -> AlarmDefinition:
    return ALARM_CATALOG.get(code, UNKNOWN_ALARM)


def subscribers_at(site_id: str) -> int:
    """Zero means "unknown site", not "nobody affected"."""
    return SITE_SUBSCRIBERS.get(site_id, 0)
