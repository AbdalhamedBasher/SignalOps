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

# Matches the SDK's own default environment,
# https://network-as-code.p-eu.rapidapi.com
DEFAULT_RAPIDAPI_HOST = "network-as-code.p-eu.rapidapi.com"

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
    The live client, built on Nokia's own `network-as-code` SDK.

    Written against the SDK's published surface rather than hand-rolled HTTP,
    because a first attempt at guessing the CAMARA paths got both of them
    wrong: reachability lives under `device-status/`, and congestion is v0, not
    v1. The vendor's client already knows all of that, and it carries the
    RapidAPI authentication these endpoints sit behind.

    Two APIs are used, both synchronous:

    - `device_status.retrieve_reachability_status` -> `reachable` plus the
      connectivity kinds (DATA, SMS) currently available to the device.
    - `congestion_insights.query` -> congestion over a time window. This one is
      per *device*, not per site, so the site's first registered device stands
      in for the cell.

    Still unverified against a live account: the shapes below come from the
    SDK's own types, but nothing here has met the real network.
    """

    def __init__(self, *, api_key: str, rapidapi_host: str | None = None) -> None:
        from network_as_code import NetworkAsCodeApi  # noqa: PLC0415

        self._client = NetworkAsCodeApi(
            api_key=api_key,
            rapidapi_host=rapidapi_host or DEFAULT_RAPIDAPI_HOST,
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
            result = self._client.device_status.retrieve_reachability_status(
                device={"phone_number": device_id}
            )
        except Exception:
            # One unreachable API must not stop the triage. UNKNOWN lets the
            # agent say "I could not establish this" instead of inventing a
            # reading, which is the whole point of the verdict having an
            # `unknown` value.
            logger.exception("Reachability lookup failed for %s", device_id)

            return ReachabilityStatus.UNKNOWN

        if not getattr(result, "reachable", False):
            return ReachabilityStatus.NOT_CONNECTED

        connectivity = [str(item) for item in (getattr(result, "connectivity", None) or [])]

        # A device reachable only by SMS has lost data service, which for a
        # subscriber means the site is not carrying their traffic.
        if "DATA" in connectivity or not connectivity:
            return ReachabilityStatus.CONNECTED_DATA

        return ReachabilityStatus.CONNECTED_SMS

    def congestion(self, site_id: str) -> CongestionInsight:
        now = datetime.now(UTC)
        devices = devices_at(site_id)

        if not devices:
            return CongestionInsight(
                site_id=site_id,
                level=CongestionLevel.UNKNOWN,
                detail=f"No device is registered at {site_id} to query congestion for.",
                source=DataSource.NOKIA_NETWORK_AS_CODE,
                checked_at=now,
            )

        try:
            insights = self._client.congestion_insights.query(
                device={"phone_number": devices[0]}
            )
        except Exception:
            logger.exception("Congestion lookup failed for %s", site_id)

            return CongestionInsight(
                site_id=site_id,
                level=CongestionLevel.UNKNOWN,
                detail="The congestion API could not be reached.",
                source=DataSource.NOKIA_NETWORK_AS_CODE,
                checked_at=now,
            )

        if not insights:
            return CongestionInsight(
                site_id=site_id,
                level=CongestionLevel.UNKNOWN,
                detail=f"The network returned no congestion data for {site_id}.",
                source=DataSource.NOKIA_NETWORK_AS_CODE,
                checked_at=now,
            )

        # The API returns a series over time; the most recent window is what an
        # engineer looking at a live incident cares about.
        latest = insights[-1]
        raw = str(getattr(latest, "congestion_level", "") or "").lower()

        try:
            level = CongestionLevel(raw)
        except ValueError:
            level = CongestionLevel.UNKNOWN

        confidence = getattr(latest, "confidence_level", None)
        confidence_note = f" (confidence {confidence}%)" if confidence is not None else ""

        return CongestionInsight(
            site_id=site_id,
            level=level,
            detail=(
                f"Congestion reported as {raw or 'unknown'} for the device "
                f"standing in for {site_id}{confidence_note}."
            ),
            source=DataSource.NOKIA_NETWORK_AS_CODE,
            checked_at=now,
        )
