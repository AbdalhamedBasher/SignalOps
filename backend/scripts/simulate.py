"""
Network event simulator.

Replays a realistic alarm cascade against a running SignalOps API so the
correlation rules can be watched doing their job on the dashboard.

    python scripts/simulate.py
    python scripts/simulate.py --site JED-118 --scenario power

Uses only the standard library so it can be run without installing anything
beyond the backend itself.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class SimulatedAlarm:
    # Seconds after the start of the fault, so a scenario reads as a timeline.
    offset_seconds: int
    code: str
    message: str


SCENARIOS: dict[str, tuple[SimulatedAlarm, ...]] = {
    "backhaul": (
        SimulatedAlarm(0, "BACKHAUL_DOWN", "Fiber backhaul link is unavailable"),
        SimulatedAlarm(
            55, "CELL_OUT_OF_SERVICE", "Cell stopped carrying subscriber traffic"
        ),
        SimulatedAlarm(
            69, "S1_LINK_FAILURE", "S1 control-plane link to the core network was lost"
        ),
        SimulatedAlarm(
            158,
            "VOLTE_REG_FAILURE",
            "VoLTE registrations are failing for attached subscribers",
        ),
    ),
    "power": (
        SimulatedAlarm(0, "POWER_UNSTABLE", "Site voltage left the stable range"),
        SimulatedAlarm(94, "TEMPERATURE_HIGH", "Cabinet temperature above threshold"),
        SimulatedAlarm(
            210, "CELL_OUT_OF_SERVICE", "Cell stopped carrying subscriber traffic"
        ),
    ),
}


def authenticate_collector(
    api_url: str,
    username: str = "collector-01",
    password: str = "collector-dev-password",
) -> str | None:
    """Log in with the seed collector credentials to obtain a Bearer token."""
    request = urllib.request.Request(
        f"{api_url}/api/auth/login",
        data=json.dumps({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.load(response)
            return body.get("access_token")
    except Exception as error:
        print(f"Warning: collector login failed ({error}); sending unauthenticated")
        return None


def post_alarm(
    api_url: str, payload: dict[str, str], token: str | None = None
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{api_url}/api/alarms",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)



def run(api_url: str, site_id: str, scenario: str, *, retry_once: bool) -> None:
    token = authenticate_collector(api_url)
    alarms = SCENARIOS[scenario]
    fault_start = datetime.now(UTC) - timedelta(seconds=alarms[-1].offset_seconds)

    print(f"Replaying '{scenario}' at {site_id} against {api_url}\n")

    last_payload: dict[str, str] | None = None

    for simulated in alarms:
        payload = {
            "site_id": site_id,
            "code": simulated.code,
            "message": simulated.message,
            "occurred_at": (
                fault_start + timedelta(seconds=simulated.offset_seconds)
            ).isoformat(),
            # A real collector stamps each delivery with its own identifier so
            # retries can be recognised. uuid4 stands in for that here.
            "external_id": f"sim-{uuid.uuid4()}",
        }
        last_payload = payload

        status_code, body = post_alarm(api_url, payload, token=token)

        if status_code >= 400:
            print(f"  {simulated.code:<22} rejected ({status_code}): {body}")
            continue

        incident = body["incident"]
        outcome = "opened" if body["incident_created"] else "joined"

        print(
            f"  {simulated.code:<22} {outcome} {incident['id']} "
            f"[{incident['severity']}] {len(incident['alarms'])} alarm(s)"
        )

    if retry_once and last_payload is not None:
        status_code, body = post_alarm(api_url, last_payload, token=token)
        print(
            f"\n  redelivering the last alarm -> HTTP {status_code}, "
            f"duplicate={body.get('duplicate')}, "
            f"{len(body['incident']['alarms'])} alarm(s) (unchanged)"
        )


    print("\nOpen the dashboard and reload to see the incident.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--site", default="RUH-315")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="backhaul")
    parser.add_argument(
        "--retry-last",
        action="store_true",
        help="resend the final alarm to demonstrate duplicate handling",
    )

    arguments = parser.parse_args()

    run(
        arguments.api,
        arguments.site,
        arguments.scenario,
        retry_once=arguments.retry_last,
    )


if __name__ == "__main__":
    main()
