"""
The service every other part of NoScam talks to.

The browser extension asks it what to do at the moment of an irreversible action;
the phone app answers approvals and checks links; both read the same household
limits. It runs on the person's own machine — nothing about a payment leaves it —
and it holds no model, no account system and no cloud.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .audit import AuditLog
from .explain import coach
from .links import check_url
from .policy import (
    Action, ActionType, Decision, Disposition, Limits, cool_off_expires, decide,
    decide_arrival, guardian_line,
)
from .provenance import Origin, Provenance, normalize_host, utcnow
from .store import APPROVAL_TTL, Hold, State, Store, new_id, pairing_code

DATA_DIR = os.environ.get("NOSCAM_DATA", os.path.join(os.getcwd(), "data"))
store = Store(os.path.join(DATA_DIR, "household.json"))
audit = AuditLog(os.path.join(DATA_DIR, "audit.jsonl"))

app = FastAPI(title="NoScam", version="1.0")
# The extension (chrome-extension://…), the phone app and the demo pages are all
# different origins talking to a service on this machine.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


# --------------------------------------------------------------------------- #
# Who is allowed to change things
#
# The service listens on loopback, which is not the same as being private: every
# page in the browser can reach it. Without this check, the scam page itself
# could approve the hold raised against it, raise the household's limits, or
# blocklist the real bank — a complete bypass, from JavaScript, on the page the
# person is already looking at.
#
# Origin is the right discriminator because a page cannot forge it: the browser
# sets it on every cross-origin request. Allowed are the extension
# (chrome-extension://…), the phone app (served by this service, so same-origin)
# and requests with no Origin at all, which come from local tools rather than a
# page. Everything else — any web page anywhere — is refused.
# --------------------------------------------------------------------------- #

# A page can ask the gate about itself as often as it likes, and each refusal
# raises a hold the guardian sees. Left uncapped, a scam page could bury the one
# real request under a hundred invented ones — the oldest trick against any
# alerting system. Beyond this many pending at once, the gate still decides and
# still refuses; it simply stops adding to the queue.
MAX_PENDING_HOLDS = 25

EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def require_trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return                                    # a local CLI, not a web page
    if origin.startswith(EXTENSION_SCHEMES):
        return
    host = request.headers.get("host", "")
    if origin.split("://")[-1] == host:
        return                                    # the phone app we serve ourselves
    raise HTTPException(
        status_code=403,
        detail="a web page may not change this household's settings",
    )


# --------------------------------------------------------------------------- #
# Wire types
# --------------------------------------------------------------------------- #

class ProvenanceIn(BaseModel):
    origin: str = "unknown"
    source_host: Optional[str] = None
    at: Optional[datetime] = None


class ActionIn(BaseModel):
    type: str
    host: str = ""
    amount: Optional[float] = None
    payee: Optional[str] = None
    file_name: Optional[str] = None
    data_kind: Optional[str] = None
    recurrence: Optional[str] = None


class CheckIn(BaseModel):
    action: ActionIn
    provenance: ProvenanceIn = Field(default_factory=ProvenanceIn)


class DecisionOut(BaseModel):
    disposition: str
    reason_code: str
    headline: str
    detail: str
    release: Optional[str] = None
    wait_seconds: int = 0
    button: str = ""
    hold_id: Optional[str] = None
    guardian: str = ""


def fingerprint(action: Action) -> str:
    """What an approval is an approval *of*. Binding it to the exact action stops
    a nod for a ₹500 payment being reused for a ₹50,000 one."""
    raw = "|".join([
        action.type.value, normalize_host(action.host), f"{action.amount or 0:.2f}",
        (action.payee or "").strip().lower(), (action.file_name or "").lower(),
        (action.data_kind or "").lower(), (action.recurrence or "").lower(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _to_action(payload: ActionIn, household) -> Action:
    """Resolve a generic 'payment' into new-payee or known-payee. The client
    doesn't decide this: who you have paid before is household state."""
    raw_type = payload.type
    if raw_type == "payment":
        known = {p.strip().lower() for p in household.known_payees}
        raw_type = ("payment_known_payee" if (payload.payee or "").strip().lower() in known
                    else "payment_new_payee")
    try:
        action_type = ActionType(raw_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown action type '{payload.type}'")
    return Action(type=action_type, host=payload.host, amount=payload.amount,
                  payee=payload.payee, file_name=payload.file_name,
                  data_kind=payload.data_kind, recurrence=payload.recurrence)


def _to_provenance(payload: ProvenanceIn) -> Provenance:
    try:
        origin = Origin(payload.origin)
    except ValueError:
        origin = Origin.UNKNOWN
    return Provenance(origin=origin, source_host=payload.source_host, at=payload.at)


def _decision_out(decision: Decision, limits: Limits, hold_id: Optional[str]) -> DecisionOut:
    return DecisionOut(
        disposition=decision.disposition.value,
        reason_code=decision.reason_code,
        headline=decision.headline,
        detail=decision.detail,
        release=decision.release,
        wait_seconds=decision.wait_seconds,
        button=guardian_line(decision, limits),
        hold_id=hold_id,
        guardian=limits.guardian_name,
    )


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #

@app.post("/gate/check", response_model=DecisionOut)
def gate_check(payload: CheckIn) -> DecisionOut:
    now = utcnow()
    state = store.read()
    household = state.household
    action = _to_action(payload.action, household)
    provenance = _to_provenance(payload.provenance)
    action_fingerprint = fingerprint(action)

    # An approval or an elapsed wait from a previous attempt at *this same
    # action* is what releases it. Anything else is a fresh decision.
    approved = False
    released_by_wait = False
    for hold in state.holds.values():
        if hold.fingerprint != action_fingerprint or hold.is_expired(now):
            continue
        if hold.status == "approved":
            approved = True
        if hold.status == "denied":
            return _decision_out(
                Decision(disposition=Disposition.BLOCKED, reason_code="denied_by_guardian",
                         headline="This was declined",
                         detail=f"{household.limits.guardian_name} declined this payment.",
                         evidence={}),
                household.limits, hold.id)
        if (hold.status == "pending" and hold.release_at is not None
                and now >= hold.release_at):
            released_by_wait = True

    decision = decide(
        action, provenance, household.limits, now=now,
        spent_today=store.spent_today(now),
        host_reported=normalize_host(action.host) in
        {normalize_host(h) for h in household.reported_hosts},
        approved=approved,
    )

    if released_by_wait and decision.disposition is Disposition.COOL_OFF:
        decision = Decision(
            disposition=Disposition.ALLOW, reason_code="cooling_period_elapsed",
            headline="Wait finished", detail="The waiting period has passed.",
            evidence=decision.evidence)

    hold_id: Optional[str] = None
    if decision.stops_the_action:
        existing = next((h for h in state.holds.values()
                         if h.fingerprint == action_fingerprint and h.status == "pending"
                         and not h.is_expired(now)), None)
        if existing is not None:
            hold_id = existing.id
        elif sum(1 for h in state.holds.values()
                 if h.summary(now)["status"] == "pending") >= MAX_PENDING_HOLDS:
            audit.record("hold_queue_full", {"host": action.host,
                                             "reason_code": decision.reason_code}, at=now)
        else:
            hold = Hold(
                id=new_id(), created_at=now, fingerprint=action_fingerprint,
                action=payload.action.model_dump(), decision={
                    "disposition": decision.disposition.value,
                    "reason_code": decision.reason_code,
                    "headline": decision.headline,
                    "detail": decision.detail,
                },
                provenance={"arrival": provenance.describe(now),
                            "source": provenance.source_host,
                            "tainted": provenance.is_tainted(now)},
                expires_at=now + APPROVAL_TTL,
                release_at=cool_off_expires(decision, now),
                # A wait can be let through early by the person who would have
                # been asked anyway; a refusal has no such door.
                approvable=decision.release is not None,
            )
            hold_id = hold.id
            store.update(lambda s: s.holds.__setitem__(hold.id, hold))
    elif action.type.is_payment and action.amount:
        # It went through, so it counts against today, and this payee is now one
        # the household has paid before.
        store.add_spend(action.amount, now)
        if action.payee:
            def remember(s: State) -> None:
                if action.payee not in s.household.known_payees:
                    s.household.known_payees.append(action.payee)
            store.update(remember)

    audit.record("gate_decision", {
        "action": payload.action.model_dump(),
        "resolved_type": action.type.value,
        "disposition": decision.disposition.value,
        "reason_code": decision.reason_code,
        "evidence": decision.evidence,
        "hold_id": hold_id,
    }, at=now)
    return _decision_out(decision, household.limits, hold_id)


class ArrivalIn(BaseModel):
    url: str
    provenance: ProvenanceIn = Field(default_factory=ProvenanceIn)


@app.post("/gate/arrival", response_model=DecisionOut)
def gate_arrival(payload: ArrivalIn) -> DecisionOut:
    """Judge a page the moment it opens, before anything is typed into it.

    Address-only: no request is made to the site, both because it must be
    instant and because fetching a page the person is already looking at tells
    us nothing they aren't about to find out anyway.
    """
    now = utcnow()
    household = store.read().household
    provenance = _to_provenance(payload.provenance)
    host = normalize_host(payload.url)
    reported = host in {normalize_host(h) for h in household.reported_hosts}

    try:
        verdict = check_url(payload.url, blocklist=household.reported_hosts, fetch=False)
    except ValueError:
        raise HTTPException(status_code=400, detail="that doesn't look like a page")

    decision = decide_arrival(
        signal_codes=[s.code for s in verdict.signals], verdict=verdict.verdict,
        provenance=provenance, host=host, now=now, host_reported=reported,
    )
    if decision is None:
        return _decision_out(
            Decision(disposition=Disposition.ALLOW, reason_code="ok", headline="",
                     detail="", evidence={}), household.limits, None)

    hold = Hold(
        id=new_id("page"), created_at=now,
        fingerprint=hashlib.sha256(f"arrival|{host}".encode()).hexdigest()[:32],
        action={"type": "page_opened", "host": host},
        decision={"disposition": decision.disposition.value,
                  "reason_code": decision.reason_code,
                  "headline": decision.headline, "detail": decision.detail},
        provenance={"arrival": provenance.describe(now), "source": provenance.source_host,
                    "tainted": provenance.is_tainted(now)},
        expires_at=now + APPROVAL_TTL,
        approvable=False,
    )
    store.update(lambda st: st.holds.__setitem__(hold.id, hold))
    audit.record("page_blocked", {"host": host, "reason_code": decision.reason_code,
                                  "signals": [s.code for s in verdict.signals]}, at=now)
    return _decision_out(decision, household.limits, hold.id)


class HoldDecisionIn(BaseModel):
    verdict: str                       # "approve" | "deny"
    by: str = "guardian"


@app.get("/holds")
def list_holds(status: str = "pending") -> list[dict[str, Any]]:
    now = utcnow()
    holds = [h for h in store.read().holds.values()
             if status == "all" or h.summary(now)["status"] == status]
    return [h.summary(now) for h in sorted(holds, key=lambda h: h.created_at, reverse=True)]


@app.get("/holds/{hold_id}")
def get_hold(hold_id: str) -> dict[str, Any]:
    hold = store.read().holds.get(hold_id)
    if hold is None:
        raise HTTPException(status_code=404, detail="no such hold")
    return hold.summary(utcnow())


@app.post("/holds/{hold_id}/decision")
def decide_hold(hold_id: str, payload: HoldDecisionIn,
                _: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    """The out-of-band answer. Time-limited, single-use, and bound to the one
    action it was raised for — the scammer on the phone cannot supply it."""
    now = utcnow()
    state = store.read()
    hold = state.holds.get(hold_id)
    if hold is None:
        raise HTTPException(status_code=404, detail="no such hold")
    if hold.is_expired(now):
        raise HTTPException(status_code=409, detail="that request has expired")
    if hold.status != "pending":
        raise HTTPException(status_code=409, detail=f"already {hold.status}")
    if not hold.approvable:
        raise HTTPException(
            status_code=409,
            detail="this was refused, not held for permission — nobody can approve it")
    if payload.verdict not in ("approve", "deny"):
        raise HTTPException(status_code=400, detail="verdict must be approve or deny")

    def mutate(s: State) -> None:
        target = s.holds[hold_id]
        target.status = "approved" if payload.verdict == "approve" else "denied"
        target.decided_by = payload.by
        target.decided_at = now

    store.update(mutate)
    audit.record("hold_decision", {"hold_id": hold_id, "verdict": payload.verdict,
                                   "by": payload.by, "fingerprint": hold.fingerprint}, at=now)
    return store.read().holds[hold_id].summary(now)


@app.get("/holds/{hold_id}/advice")
def hold_advice(hold_id: str) -> dict[str, Any]:
    """What to do right now, phrased for this situation by a language model.

    Deliberately a second request: the decision and its explanation are already
    on the screen before this is asked for, so a slow or missing model delays
    nothing and changes nothing. If it returns nothing, nothing is shown.
    """
    hold = store.read().holds.get(hold_id)
    if hold is None:
        raise HTTPException(status_code=404, detail="no such hold")
    advice = coach(hold.decision, hold.action)
    if advice:
        audit.record("advice_shown", {"hold_id": hold_id, "advice": advice})
    return {"advice": advice}


class OverrideIn(BaseModel):
    reason: str = ""


@app.post("/holds/{hold_id}/override")
def override_hold(hold_id: str, payload: OverrideIn) -> dict[str, Any]:
    """The escape hatch, and the reason this is a handbrake rather than a cage.

    Deliberately not origin-locked: the hosted demo runs the content script
    inside an ordinary page, and overriding is the person's own decision about
    their own hold. A page that overrides the hold raised against itself has
    gained nothing — it could simply have proceeded — and the override is
    written to the audit chain either way.
    Always available, always recorded — including in the weekly summary a
    guardian sees, which is what makes the override meaningful rather than a
    silent way around the control."""
    now = utcnow()
    if hold_id not in store.read().holds:
        raise HTTPException(status_code=404, detail="no such hold")

    def mutate(s: State) -> None:
        s.holds[hold_id].status = "overridden"
        s.holds[hold_id].decided_by = "person at the keyboard"
        s.holds[hold_id].decided_at = now

    store.update(mutate)
    audit.record("override", {"hold_id": hold_id, "reason": payload.reason}, at=now)
    return store.read().holds[hold_id].summary(now)


# --------------------------------------------------------------------------- #
# Links
# --------------------------------------------------------------------------- #

class LinkIn(BaseModel):
    url: str
    fetch: bool = True


@app.post("/links/check")
def links_check(payload: LinkIn) -> dict[str, Any]:
    household = store.read().household
    try:
        verdict = check_url(payload.url, blocklist=household.reported_hosts,
                            fetch=payload.fetch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit.record("link_check", {"url": verdict.url, "verdict": verdict.verdict,
                                "signals": [s.code for s in verdict.signals]})
    return verdict.as_dict()


@app.post("/links/report")
def links_report(payload: LinkIn,
                 _: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    """One person getting targeted protects everyone else in the household."""
    host = normalize_host(payload.url)
    if not host:
        raise HTTPException(status_code=400, detail="that doesn't look like a link")

    def mutate(s: State) -> None:
        if host not in s.household.reported_hosts:
            s.household.reported_hosts.append(host)

    store.update(mutate)
    audit.record("link_reported", {"host": host})
    return {"host": host, "reported_hosts": store.read().household.reported_hosts}


# --------------------------------------------------------------------------- #
# Household
# --------------------------------------------------------------------------- #

@app.get("/household")
def get_household(_: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    household = store.read().household
    return {
        "name": household.name,
        "limits": household.limits.model_dump(),
        "known_payees": household.known_payees,
        "reported_hosts": household.reported_hosts,
        "paired_devices": household.paired_devices,
        "spent_today": store.spent_today(),
    }


@app.put("/limits")
def put_limits(limits: Limits,
               _: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    def mutate(s: State) -> None:
        s.household.limits = limits

    store.update(mutate)
    audit.record("limits_changed", limits.model_dump())
    return limits.model_dump()


class PayeesIn(BaseModel):
    payees: list[str]


@app.post("/household/payees")
def add_payees(payload: PayeesIn,
               _: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    """Tell NoScam who you already pay. Everyone else is a first-time payee and
    waits — which is the friction this product is honest about."""
    def mutate(s: State) -> None:
        for payee in payload.payees:
            if payee and payee not in s.household.known_payees:
                s.household.known_payees.append(payee)

    store.update(mutate)
    audit.record("payees_added", {"payees": payload.payees})
    return {"known_payees": store.read().household.known_payees}


@app.post("/household/reset")
def reset_household(_: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    """Clear holds and today's spending, keeping limits and payees. Used to run
    the demo twice without restarting anything."""
    def mutate(s: State) -> None:
        s.holds.clear()
        s.household.spent_by_day.clear()

    store.update(mutate)
    audit.record("household_reset", {})
    return {"ok": True}


class PairIn(BaseModel):
    code: str = ""
    device: str = "device"


@app.post("/pair/start")
def pair_start(_: None = Depends(require_trusted_origin)) -> dict[str, str]:
    code = pairing_code()

    def mutate(s: State) -> None:
        s.household.pairing_code = code

    store.update(mutate)
    return {"code": code}


@app.post("/pair/claim")
def pair_claim(payload: PairIn) -> dict[str, Any]:
    household = store.read().household
    if not household.pairing_code or payload.code != household.pairing_code:
        raise HTTPException(status_code=403, detail="that code doesn't match")

    def mutate(s: State) -> None:
        if payload.device not in s.household.paired_devices:
            s.household.paired_devices.append(payload.device)
        s.household.pairing_code = ""

    store.update(mutate)
    audit.record("device_paired", {"device": payload.device})
    return {"paired": True, "devices": store.read().household.paired_devices}


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #

@app.get("/audit/verify")
def audit_verify() -> dict[str, Any]:
    ok, first_broken = audit.verify()
    return {"ok": ok, "first_broken_line": first_broken,
            "records": len(audit.records())}


@app.get("/audit/recent")
def audit_recent(limit: int = 25) -> list[dict[str, Any]]:
    return audit.records()[-limit:][::-1]


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "noscam"}


# The phone app and the demo pages are plain static files served from here, so
# there is one thing to run. Paths are resolved from the repository rather than
# the working directory: the service is started from editors, shells and the
# demo script, and "wherever you happened to be" is not a location.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for route, folder in (("/app", "web"), ("/demo", "demo")):
    directory = os.path.join(ROOT, folder)
    if os.path.isdir(directory):
        app.mount(route, StaticFiles(directory=directory, html=True), name=folder)
