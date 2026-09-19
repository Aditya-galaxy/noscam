"""
Put the demo household into the state a real one would be in after a week of use:
limits set by whoever is calmest, and a few payees it has paid before.

Run:  python3 demo/seed.py
"""

from __future__ import annotations

import json
import urllib.request

SERVICE = "http://127.0.0.1:8787"

LIMITS = {
    "currency": "INR",
    "per_transaction_cap": 25_000,
    "daily_cap": 50_000,
    "new_payee_cooling_minutes": 10,
    "block_remote_access": True,
    "guardian_name": "Priya",
}

# People this household already pays: rent, the electricity board, the son.
KNOWN_PAYEES = ["Landlord", "Electricity Board", "Aarav"]


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{SERVICE}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def main() -> None:
    call("PUT", "/limits", LIMITS)
    call("POST", "/household/payees", {"payees": KNOWN_PAYEES})
    call("POST", "/household/reset")
    household = call("GET", "/household")
    print("Household ready:")
    print(f"  guardian        {household['limits']['guardian_name']}")
    print(f"  per-transaction ₹{household['limits']['per_transaction_cap']:,.0f}")
    print(f"  daily           ₹{household['limits']['daily_cap']:,.0f}")
    print(f"  new payee waits {household['limits']['new_payee_cooling_minutes']} minutes")
    print(f"  known payees    {', '.join(household['known_payees'])}")


if __name__ == "__main__":
    main()
