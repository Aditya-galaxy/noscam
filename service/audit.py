"""
A tamper-evident record of every decision.

Two reasons this exists in a consumer product. The first is the victim's: after a
scam, the single hardest question is "what actually happened?", and a log that can
be quietly edited answers nothing. The second is ours: NoScam blocks people's
payments, so the claim "it only ever stops what the policy says it stops" has to
be checkable rather than trusted.

Each line carries the hash of the line before it, so changing or deleting any
record breaks verification of every record after it, and `verify()` names the
first line that broke.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from typing import Any, Optional

from .provenance import utcnow

GENESIS = "0" * 64


def _digest(previous_hash: str, payload: str) -> str:
    return hashlib.sha256(f"{previous_hash}{payload}".encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained JSONL."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> str:
        return self._path

    def _last_hash(self) -> str:
        records = self.records()
        return records[-1]["hash"] if records else GENESIS

    def record(self, kind: str, payload: dict[str, Any], *,
               at: Optional[datetime] = None) -> dict[str, Any]:
        with self._lock:
            previous = self._last_hash()
            body = {
                "ts": (at or utcnow()).isoformat(),
                "kind": kind,
                "payload": payload,
                "previous": previous,
            }
            # Sorted keys so the hash is over a canonical form: re-serialising a
            # record must produce the same digest, or verification is theatre.
            serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
            entry = {**body, "hash": _digest(previous, serialized)}
            directory = os.path.dirname(os.path.abspath(self._path)) or "."
            os.makedirs(directory, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return entry

    def records(self) -> list[dict[str, Any]]:
        if not os.path.exists(self._path):
            return []
        out = []
        with open(self._path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # A corrupt line is itself a break in the chain; keep it as a
                    # marker so verify() reports where rather than skipping past.
                    out.append({"corrupt": line})
        return out

    def verify(self) -> tuple[bool, Optional[int]]:
        """(ok, first_broken_line_number). Line numbers are 1-based, as a person
        reading the file would count them."""
        previous = GENESIS
        for number, entry in enumerate(self.records(), start=1):
            if "corrupt" in entry:
                return False, number
            body = {k: entry[k] for k in ("ts", "kind", "payload", "previous") if k in entry}
            if len(body) != 4 or entry.get("previous") != previous:
                return False, number
            serialized = json.dumps(body, sort_keys=True, separators=(",", ":"))
            if _digest(previous, serialized) != entry.get("hash"):
                return False, number
            previous = entry["hash"]
        return True, None
