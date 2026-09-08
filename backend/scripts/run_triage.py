"""
Triage Runner Script for SignalOps AI.

Runs the CAMARA-orchestrated AI triage agent against an incident (default INC-1001).
Can be used to test Gemini output with a real GOOGLE_API_KEY.

Usage:
    python scripts/run_triage.py
    python scripts/run_triage.py --incident INC-1001 --api http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def login_engineer(api_url: str) -> str:
    """Obtain engineer access token using seed credentials."""
    request = urllib.request.Request(
        f"{api_url}/api/auth/login",
        data=json.dumps({
            "username": "nadia.k",
            "password": "engineer-dev-password",
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
        return data["access_token"]


def get_incident(api_url: str, token: str, incident_id: str) -> dict:
    request = urllib.request.Request(
        f"{api_url}/api/incidents",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        incidents = json.load(response)
        for inc in incidents:
            if inc["id"] == incident_id:
                return inc
        raise ValueError(f"Incident {incident_id} not found on server")


def ensure_recommendations(api_url: str, token: str, incident_id: str) -> list[dict]:
    """Retrieve runbook guidance if not already retrieved."""
    request = urllib.request.Request(
        f"{api_url}/api/incidents/{incident_id}/recommendations",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        existing = json.load(response)
        if existing:
            return existing

    post_request = urllib.request.Request(
        f"{api_url}/api/incidents/{incident_id}/recommendations",
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(post_request, timeout=10) as response:
        return json.load(response)


def trigger_triage(api_url: str, token: str, incident_id: str) -> dict:
    """Invoke the CAMARA triage agent."""
    request = urllib.request.Request(
        f"{api_url}/api/incidents/{incident_id}/triage",
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            parsed = json.loads(body)
            detail = parsed.get("detail", body)
        except Exception:
            detail = body
        raise RuntimeError(f"Triage failed with HTTP {error.code}: {detail}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000", help="FastAPI URL")
    parser.add_argument("--incident", default="INC-1001", help="Incident identifier to triage")
    args = parser.parse_args()

    print(f"Connecting to {args.api}...")
    try:
        token = login_engineer(args.api)
        print("Authenticated as Nadia Karim (Engineer).")
    except Exception as exc:
        print(f"Failed to authenticate: {exc}")
        return

    try:
        inc = get_incident(args.api, token, args.incident)
        print(
            f"Found incident {inc['id']}: '{inc['title']}' "
            f"at site {inc['site_id']} [{inc['severity']}]"
        )
    except Exception as exc:
        print(f"Could not fetch incident: {exc}")
        return

    try:
        recs = ensure_recommendations(args.api, token, args.incident)
        print(f"Matched {len(recs)} runbook recommendation(s).")
    except Exception as exc:
        print(f"Could not load runbooks: {exc}")
        return

    print(f"\nInvoking AI Triage Agent for {args.incident}...")
    try:
        triage = trigger_triage(args.api, token, args.incident)
    except Exception as exc:
        print(f"\n[!] Triage Error: {exc}")
        print("Tip: Ensure GOOGLE_API_KEY is set in backend/.env if testing live Gemini.")
        return

    print("\n" + "=" * 60)
    print(f"TRIAGE REPORT: {triage['id']}")
    print("=" * 60)
    print(f"Verdict : {triage['verdict'].upper()}")
    print(f"Model   : {triage['model']}")
    print(f"\nSummary:\n  {triage['summary']}")

    print("\nAgent Reasoning Trace:")
    for step in triage.get("trace", []):
        print(f"  -> {step}")

    print("\nNetwork Evidence (CAMARA):")
    for ev in triage.get("evidence", []):
        print(f"  * {ev}")

    print("\nRecommended First Actions:")
    for action in triage.get("first_actions", []):
        print(f"  1. {action}")

    if triage.get("gaps"):
        print(f"\nGaps / Unresolved:\n  {triage['gaps']}")

    print(f"\nCited Runbook Sections: {', '.join(triage.get('cited_section_ids', []))}")
    print("=" * 60)


if __name__ == "__main__":
    main()
