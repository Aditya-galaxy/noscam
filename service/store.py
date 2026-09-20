"""
Household state on disk: limits, who you've paid before, what's been reported,
and the payments currently on hold.

One JSON file, written atomically. No database and no accounts — a product that
opens with "create an account" never reaches the person it is meant to protect,
and the whole state here is small enough to read with your own eyes, which is the
right property for something that decides whether your money moves.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
from datetime import date, datetime, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field

from .policy import Limits
from .provenance import utcnow

# An approval is worth nothing if it can be reused on the next payment, so it
# expires quickly and is bound to one action.
APPROVAL_TTL = timedelta(minutes=5)


class Hold(BaseModel):
    """One action stopped at the gate, waiting for a person or a clock."""

    id: str
    created_at: datetime
    fingerprint: str
    action: dict[str, Any]
    provenance: dict[str, Any]
    decision: dict[str, Any]
    status: str = "pending"        # pending | approved | denied | released | overridden | expired
    expires_at: datetime
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    release_at: Optional[datetime] = None    # for cool-off holds
    # False for a refusal: something the household is told about, not asked
    # about. Nothing on any screen offers to approve one.
    approvable: bool = True

    def is_expired(self, now: datetime) -> bool:
        return self.status == "pending" and now >= self.expires_at

    def summary(self, now: datetime) -> dict[str, Any]:
        remaining = max(0, int((self.expires_at - now).total_seconds()))
        return {
            "id": self.id,
            "status": "expired" if self.is_expired(now) else self.status,
            "approvable": self.approvable,
            "action": self.action,
            "decision": self.decision,
            "arrival": self.provenance.get("arrival", ""),
            "seconds_remaining": remaining,
            "created_at": self.created_at.isoformat(),
        }


class Household(BaseModel):
    name: str = "Home"
    limits: Limits = Field(default_factory=Limits)
    known_payees: list[str] = Field(default_factory=list)
    reported_hosts: list[str] = Field(default_factory=list)
    pairing_code: str = ""
    paired_devices: list[str] = Field(default_factory=list)
    spent_by_day: dict[str, float] = Field(default_factory=dict)


class State(BaseModel):
    household: Household = Field(default_factory=Household)
    holds: dict[str, Hold] = Field(default_factory=dict)


class Store:
    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def read(self) -> State:
        if not os.path.exists(self._path):
            return State()
        try:
            with open(self._path, encoding="utf-8") as fh:
                return State.model_validate(json.load(fh))
        except (json.JSONDecodeError, ValueError):
            # Unlike a cache, this file decides whether payments are held. If it
            # is unreadable we start from defaults, which are the *strict* ones —
            # failing open here would silently switch the product off.
            return State()

    def write(self, state: State) -> None:
        directory = os.path.dirname(os.path.abspath(self._path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(json.loads(state.model_dump_json()), fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def update(self, mutate) -> State:
        """Read-modify-write under a lock. The extension polls while the phone
        writes, so 'last writer wins' would lose approvals."""
        with self._lock:
            state = self.read()
            mutate(state)
            self.write(state)
            return state

    # --- convenience used by the API ---

    def spent_today(self, now: Optional[datetime] = None) -> float:
        key = (now or utcnow()).date().isoformat()
        return self.read().household.spent_by_day.get(key, 0.0)

    def add_spend(self, amount: float, now: Optional[datetime] = None) -> None:
        key = (now or utcnow()).date().isoformat()

        def mutate(state: State) -> None:
            state.household.spent_by_day[key] = round(
                state.household.spent_by_day.get(key, 0.0) + amount, 2)
            # Keep a week; this is a safety limit, not an accounting ledger.
            cutoff = (date.fromisoformat(key) - timedelta(days=7)).isoformat()
            for day in [d for d in state.household.spent_by_day if d < cutoff]:
                state.household.spent_by_day.pop(day, None)

        self.update(mutate)


def new_id(prefix: str = "hold") -> str:
    return f"{prefix}_{secrets.token_urlsafe(9)}"


def pairing_code() -> str:
    """Six digits, spoken across a room rather than typed from an email."""
    return f"{secrets.randbelow(1_000_000):06d}"
