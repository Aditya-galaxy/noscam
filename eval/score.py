"""
Score NoScam on both axes at once.

A defence that stops every scam is trivial to build: block everything. A defence
that never interrupts anyone is equally trivial: block nothing. The only honest
measurement puts both numbers in the same table, and prints the name of every
case it got wrong — including ordinary payments it slowed down, which are the
cost the household actually pays.

Run:  python3 eval/score.py
Exit code is 1 if any scam gets through, so this can gate a change.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service.policy import Action, ActionType, Disposition, Limits, decide   # noqa: E402
from service.provenance import Origin, Provenance, utcnow                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# The household these scenarios are scored against: the defaults, with the
# payees an ordinary home would already have.
LIMITS = Limits(guardian_name="Priya")


def load() -> list[dict]:
    with open(os.path.join(HERE, "scenarios.json"), encoding="utf-8") as fh:
        return json.load(fh)["scenarios"]


def run_one(scenario: dict) -> tuple[str, str]:
    now = utcnow()
    spec = scenario["provenance"]
    provenance = Provenance(
        origin=Origin(spec.get("origin", "unknown")),
        source_host=spec.get("source_host"),
        at=now - timedelta(seconds=spec.get("seconds_ago", 0)),
    )
    payload = scenario["action"]
    action = Action(
        type=ActionType(payload["type"]), host=payload.get("host", ""),
        amount=payload.get("amount"), payee=payload.get("payee"),
        file_name=payload.get("file_name"),
    )
    decision = decide(action, provenance, LIMITS, now=now,
                      spent_today=scenario.get("spent_today", 0.0),
                      host_reported=scenario.get("host_reported", False))
    outcome = {
        Disposition.ALLOW: "went through",
        Disposition.COOL_OFF: "delayed",
        Disposition.NEEDS_APPROVAL: "held for approval",
        Disposition.BLOCKED: "blocked",
    }[decision.disposition]
    return outcome, decision.reason_code


def main() -> int:
    scenarios = load()
    scams = [s for s in scenarios if s["kind"] == "scam"]
    ordinary = [s for s in scenarios if s["kind"] == "ordinary"]

    stopped, got_through = [], []
    untouched, delayed, obstructed = [], [], []

    print("\n  NoScam — scored on twenty situations\n")
    print(f"  {'':2} {'situation':52} {'outcome':18} why")
    print("  " + "─" * 100)

    for scenario in scenarios:
        outcome, reason = run_one(scenario)
        is_scam = scenario["kind"] == "scam"
        if is_scam:
            (stopped if outcome != "went through" else got_through).append(scenario["name"])
            mark = "✓" if outcome != "went through" else "✗"
        else:
            if outcome == "went through":
                untouched.append(scenario["name"])
                mark = "✓"
            elif outcome == "delayed":
                delayed.append(scenario["name"])
                mark = "~"
            else:
                obstructed.append(scenario["name"])
                mark = "✗"
        print(f"  {mark:2} {scenario['name'][:52]:52} {outcome:18} {reason}")

    print("\n  " + "─" * 100)
    print(f"\n  Scams stopped                      {len(stopped)}/{len(scams)}")
    print(f"  Ordinary actions left alone        {len(untouched)}/{len(ordinary)}")
    print(f"  Ordinary actions delayed           {len(delayed)}/{len(ordinary)}")
    print(f"  Ordinary actions wrongly stopped   {len(obstructed)}/{len(ordinary)}")

    if got_through:
        print("\n  Scams that got through:")
        for name in got_through:
            print(f"    ✗ {name}")
    if delayed:
        print("\n  Ordinary actions that were delayed (the cost this household pays):")
        for name in delayed:
            print(f"    ~ {name}")
    if obstructed:
        print("\n  Ordinary actions wrongly stopped:")
        for name in obstructed:
            print(f"    ✗ {name}")

    print("\n  Twenty hand-written situations are a regression test, not a measured\n"
          "  accuracy claim. A real number needs real households, and nobody has\n"
          "  used this in one yet.\n")
    return 1 if got_through or obstructed else 0


if __name__ == "__main__":
    raise SystemExit(main())
