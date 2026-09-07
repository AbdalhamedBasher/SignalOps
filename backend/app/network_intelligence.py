"""
CAMARA network APIs, as consumed by SignalOps.

These are the trusted, real-time signals the triage agent reasons over. Two are
implemented, both available on the Nokia Network as Code platform:

- **Device Reachability Status** — can a device at this site still be reached?
  This is what turns "1,240 subscribers affected" from a number in a table into
  a claim with evidence behind it.
- **Congestion Insights** — is the network at this site actually degraded?
  An independent second opinion on alarms that claim degradation.

Both are behind one protocol with two implementations. The simulator is the
default because Nokia's sandbox needs an account, because a live call failing
mid-demo is the classic hackathon disaster, and because a deterministic
simulator makes the whole system testable. Which one answered is recorded on
every reading, so nothing here can quietly pass simulated data off as real.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)

CAMARA_REACHABILITY_PATH = "/device-reachability-status/v1/retrieve"
CAMARA_CONGESTION_PATH = "/congestion-insights/v1/query"


class ReachabilityStatus(StrEnum):
    """CAMARA device reachability values."""

    CONNECTED_DATA = "CONNECTED_DATA"
    CONNECTED_SMS = "CONNECTED_SMS"
    NOT_CONNECTED = "NOT_CONNECTED"
    # Not a CAMARA value: ours, for when the network could not tell us.
    UNKNOWN = "UNKNOWN"


class CongestionLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class DataSource(StrEnum):
    NOKIA_NETWORK_AS_CODE = "nokia-network-as-code"
    SIMULATOR = "simulator"


class DeviceReachability(BaseModel):
    device_id: str
    status: ReachabilityStatus
    source: DataSource
    checked_at: datetime


class SiteReachability(BaseModel):
    """What the network says about every known device at one site."""

    site_id: str
    devices: list[DeviceReachability]
    source: DataSource

    @property
    def unreachable(self) -> list[DeviceReachability]:
        return [
            device
            for device in self.devices
            if device.status is ReachabilityStatus.NOT_CONNECTED
        ]

    @property
    def summary(self) -> str:
        if not self.devices:
            return "No devices are registered at this site, so reachability says nothing."

        unreachable = len(self.unreachable)

        return (
            f"{unreachable} of {len(self.devices)} known devices at {self.site_id} "
            f"are unreachable."
        )


class CongestionInsight(BaseModel):
    site_id: str
    level: CongestionLevel
    detail: str
    source: DataSource
    checked_at: datetime


class NetworkIntelligence(Protocol):
    """The CAMARA surface the agent is allowed to reach for."""

    def device_reachability(self, site_id: str) -> SiteReachability: ...

    def congestion(self, site_id: str) -> CongestionInsight: ...


# Devices known to sit behind each site. In a real deployment this comes from
# network inventory and would be far larger; here it is a small, fixed set of
# simulator numbers of the kind Nokia's sandbox issues.
SITE_DEVICES: dict[str, list[str]] = {
    "RUH-104": ["+966500000101", "+966500000102", "+966500000103"],
    "RUH-207": ["+966500000201", "+966500000202"],
    "RUH-315": ["+966500000301", "+966500000302", "+966500000303"],
    "JED-031": ["+966500000401"],
    "JED-118": ["+966500000501", "+966500000502"],
    "DMM-052": ["+966500000601", "+966500000602"],
}


def devices_at(site_id: str) -> list[str]:
    return SITE_DEVICES.get(site_id, [])


def _stable_fraction(*parts: str) -> float:
    """
    A deterministic pseudo-random number in [0, 1) from the given strings.

    Deterministic on purpose: the same site must give the same answer every
    time, so a demo can be rehearsed and a test can assert on the result.
    """
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    return int(digest[:8], 16) / 0xFFFFFFFF


class SimulatedNetwork:
    """
    A stand-in for the operator network, used when no CAMARA credentials exist.

    It is not random. Readings are derived from the site identifier and from
    what the site is currently reporting, so the picture it paints is
    internally consistent — a site with a critical fault has devices that
    cannot be reached, and one with none does not.
    """

    def __init__(self, degraded_sites: dict[str, str] | None = None) -> None:
        # site_id -> severity of its worst open incident, injected by the caller
        # so the simulation agrees with the incident board.
        self.degraded_sites = degraded_sites or {}

    def device_reachability(self, site_id: str) -> SiteReachability:
        severity = self.degraded_sites.get(site_id, "")
        now = datetime.now(UTC)

        # How much of the site is expected to be dark, given what it reports.
        outage_share = {
            "critical": 1.0,
            "high": 0.5,
            "medium": 0.2,
        }.get(severity, 0.0)

        devices: list[DeviceReachability] = []

        for device_id in devices_at(site_id):
            unreachable = _stable_fraction(site_id, device_id) < outage_share

            devices.append(
                DeviceReachability(
                    device_id=device_id,
                    status=(
                        ReachabilityStatus.NOT_CONNECTED
                        if unreachable
                        else ReachabilityStatus.CONNECTED_DATA
                    ),
                    source=DataSource.SIMULATOR,
                    checked_at=now,
                )
            )

        return SiteReachability(
            site_id=site_id, devices=devices, source=DataSource.SIMULATOR
        )

    def congestion(self, site_id: str) -> CongestionInsight:
        severity = self.degraded_sites.get(site_id, "")

        level = {
            "critical": CongestionLevel.HIGH,
            "high": CongestionLevel.HIGH,
            "medium": CongestionLevel.MEDIUM,
        }.get(severity, CongestionLevel.LOW)

        return CongestionInsight(
            site_id=site_id,
            level=level,
            detail=(
                f"Simulated congestion for {site_id}, consistent with the site's "
                f"reported condition."
            ),
            source=DataSource.SIMULATOR,
            checked_at=datetime.now(UTC),
        )


class NokiaNetworkAsCode:
    """
    The live client against Nokia's Network as Code CAMARA endpoints.

    NOT YET VERIFIED against the real platform — see docs/MVP.md. It is written
    to the CAMARA specifications and will need checking against a real sandbox
    account before it can be claimed to work.
    """

    def __init__(self, *, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        import httpx  # noqa: PLC0415

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
        )

    def device_reachability(self, site_id: str) -> SiteReachability:
        now = datetime.now(UTC)
        readings: list[DeviceReachability] = []

        for device_id in devices_at(site_id):
            readings.append(
                DeviceReachability(
                    device_id=device_id,
                    status=self._reachability_of(device_id),
                    source=DataSource.NOKIA_NETWORK_AS_CODE,
                    checked_at=now,
                )
            )

        return SiteReachability(
            site_id=site_id,
            devices=readings,
            source=DataSource.NOKIA_NETWORK_AS_CODE,
        )

    def _reachability_of(self, device_id: str) -> ReachabilityStatus:
        try:
            response = self._client.post(
                CAMARA_REACHABILITY_PATH,
                json={"device": {"phoneNumber": device_id}},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            # One unreachable API must not stop the triage. Reporting UNKNOWN
            # lets the agent say "I could not establish this" instead of
            # inventing a reading.
            logger.exception("Reachability lookup failed for %s", device_id)

            return ReachabilityStatus.UNKNOWN

        raw = payload.get("reachabilityStatus") or payload.get("status")

        try:
            return ReachabilityStatus(raw)
        except ValueError:
            return ReachabilityStatus.UNKNOWN

    def congestion(self, site_id: str) -> CongestionInsight:
        now = datetime.now(UTC)

        try:
            response = self._client.post(
                CAMARA_CONGESTION_PATH, json={"area": {"siteId": site_id}}
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception("Congestion lookup failed for %s", site_id)

            return CongestionInsight(
                site_id=site_id,
                level=CongestionLevel.UNKNOWN,
                detail="The congestion API could not be reached.",
                source=DataSource.NOKIA_NETWORK_AS_CODE,
                checked_at=now,
            )

        raw = str(payload.get("congestionLevel", "")).lower()

        try:
            level = CongestionLevel(raw)
        except ValueError:
            level = CongestionLevel.UNKNOWN

        return CongestionInsight(
            site_id=site_id,
            level=level,
            detail=str(payload.get("description", "")) or f"Congestion at {site_id}.",
            source=DataSource.NOKIA_NETWORK_AS_CODE,
            checked_at=now,
        )
