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
import secrets
from datetime import datetime, timedelta
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
from .relay import PairingManager, RelayClient
from .store import APPROVAL_TTL, Hold, State, Store, new_id, pairing_code

DATA_DIR = os.environ.get("NOSCAM_DATA", os.path.join(os.getcwd(), "data"))
store = Store(os.path.join(DATA_DIR, "household.json"))
audit = AuditLog(os.path.join(DATA_DIR, "audit.jsonl"))

pairing_mgr = PairingManager(DATA_DIR)


def apply_remote_verdict(hold_id: str, verdict: str) -> None:
    now = utcnow()
    holds = store.read().holds
    if hold_id not in holds:
        return
    hold = holds[hold_id]
    if hold.is_expired(now) or hold.status != "pending" or not hold.approvable:
        return
    if verdict not in ("approve", "deny"):
        return

    def mutate(s: State) -> None:
        target = s.holds[hold_id]
        target.status = "approved" if verdict == "approve" else "denied"
        target.decided_by = "remote_guardian (E2EE)"
        target.decided_at = now

    store.update(mutate)
    audit.record("hold_decision", {
        "hold_id": hold_id,
        "verdict": verdict,
        "by": "remote_guardian (E2EE)",
        "fingerprint": hold.fingerprint,
    }, at=now)


relay_client = RelayClient(pairing_mgr, on_verdict=apply_remote_verdict)
relay_client.start()

app = FastAPI(title="NoScam", version="1.1.0")
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

# Loopback-only is the default, and it is what makes the Origin check above
# sufficient: nothing outside this machine can reach the service at all. But the
# second device — the whole point of the product — is a *different* device, so
# the phone has to be able to connect, which means listening on the network.
#
# The moment it does, "a page cannot forge Origin" stops being enough, because
# anything else on that Wi-Fi is a legitimate client as far as the browser is
# concerned. So in LAN mode every request from off this machine carries a token
# that is printed once, at startup, and reaches the phone in the link it opens.
LAN_MODE = os.environ.get("NOSCAM_LAN") == "1"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def _token_path() -> str:
    return os.path.join(DATA_DIR, "token")


def household_token() -> str:
    """Stable for the life of the household: printed at startup, carried in the
    link the phone opens, then kept by the phone."""
    path = _token_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            existing = fh.read().strip()
        if existing:
            return existing
    token = secrets.token_urlsafe(18)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(token)
    os.chmod(path, 0o600)
    return token


def _off_machine(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return LAN_MODE and client not in LOOPBACK


def require_household_token(request: Request) -> None:
    """Every request from another device proves it belongs to this household."""
    if not _off_machine(request):
        return
    supplied = (request.headers.get("x-noscam-token")
                or request.query_params.get("t") or "")
    if not secrets.compare_digest(supplied, household_token()):
        raise HTTPException(
            status_code=401,
            detail="this device has not been paired with the household",
        )

EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")


def require_trusted_origin(request: Request) -> None:
    require_household_token(request)
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
            if hold.approvable:
                relay_client.publish_hold(hold.summary(now))
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
def list_holds(status: str = "pending",
               _: None = Depends(require_household_token)) -> list[dict[str, Any]]:
    now = utcnow()
    holds = [h for h in store.read().holds.values()
             if status == "all" or h.summary(now)["status"] == status]
    return [h.summary(now) for h in sorted(holds, key=lambda h: h.created_at, reverse=True)]


@app.get("/holds/{hold_id}")
def get_hold(hold_id: str,
             _: None = Depends(require_household_token)) -> dict[str, Any]:
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
def links_check(payload: LinkIn,
                _: None = Depends(require_household_token)) -> dict[str, Any]:
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


@app.get("/household/pairing")
def get_pairing(_: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    creds = pairing_mgr.get_credentials()
    return {
        "channel_id": creds["channel_id"],
        "shared_key": creds["shared_key"],
        "pairing_url": f"/app/?r={creds['channel_id']}&k={creds['shared_key']}",
        "created_at": creds.get("created_at"),
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


@app.delete("/household/payees/{payee}")
def forget_payee(payee: str, _: None = Depends(require_trusted_origin)) -> dict[str, Any]:
    """Stop treating someone as familiar. Removing a payee makes the next
    payment to them wait again, which is the right direction for a control: the
    forgetful choice is the safe one."""
    def mutate(s: State) -> None:
        s.household.known_payees = [p for p in s.household.known_payees
                                    if p.strip().lower() != payee.strip().lower()]

    store.update(mutate)
    audit.record("payee_removed", {"payee": payee})
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

# The reason codes are for the audit chain and for us. Nobody should have to
# read "new_payee_after_message" to find out what happened to their money.
REASON_WORDS = {
    "new_payee_after_message": "A payment to someone new, pushed by a message",
    "payment_after_message": "A payment prompted by a message",
    "new_payee_cooling": "A first payment to someone new",
    "over_transaction_cap": "A payment over the household limit",
    "over_daily_cap": "A payment over the daily limit",
    "credentials_after_message": "A password or code asked for after a message",
    "sensitive_data_after_message": "Personal details asked for after a message",
    "remote_access_blocked": "Remote-control software",
    "install_after_message": "An app sent in a message",
    "gift_cards_after_message": "Gift cards, asked for by a message",
    "crypto_after_message": "Crypto, asked for by a message",
    "crypto_needs_second_pair_of_eyes": "A crypto transfer",
    "upi_collect_after_message": "A collect request that takes money",
    "upi_collect_request": "A collect request",
    "mandate_after_message": "A repeating payment, set up by a message",
    "mandate_needs_second_pair_of_eyes": "A payment that repeats",
    "reported_link": "A site this household reported",
    "phishing_page_after_message": "A page pretending to be someone else",
    "reported_page_opened": "A site this household reported",
    "denied_by_guardian": "Something already declined",
}


@app.get("/history")
def history(days: int = 7, _: None = Depends(require_household_token)) -> dict[str, Any]:
    """What NoScam has actually done, in the household's own words.

    A hold expires after five minutes and disappears, which is right for the
    queue and wrong for everything else: a control nobody can look back at is a
    control nobody can judge. This is also what makes an override mean
    something — it is logged either way, but until somebody sees it, logging it
    was decoration.
    """
    cutoff = utcnow() - timedelta(days=max(1, days))
    items: list[dict[str, Any]] = []
    for record in audit.records():
        if "corrupt" in record:
            continue
        when = datetime.fromisoformat(record["ts"])
        if when < cutoff:
            continue
        payload = record.get("payload", {})
        kind = record.get("kind")
        action = payload.get("action", {}) or {}

        if kind == "gate_decision" and payload.get("disposition") != "allow":
            reason = payload.get("reason_code", "")
            items.append({
                "at": record["ts"],
                "what": REASON_WORDS.get(reason, reason.replace("_", " ")),
                "outcome": payload.get("disposition"),
                "reason": payload.get("reason_code"),
                "host": action.get("host") or payload.get("evidence", {}).get("host", ""),
                "amount": action.get("amount"),
                "payee": action.get("payee"),
            })
        elif kind == "page_blocked":
            items.append({"at": record["ts"], "outcome": "blocked",
                          "reason": payload.get("reason_code"),
                          "host": payload.get("host", ""), "what": "A fake page was stopped"})
        elif kind == "hold_decision":
            items.append({"at": record["ts"],
                          "outcome": "approved" if payload.get("verdict") == "approve"
                          else "declined",
                          "reason": "answered_on_another_device",
                          "who": payload.get("by", ""), "what": "Answered on another device"})
        elif kind == "override":
            items.append({"at": record["ts"], "outcome": "overridden", "reason": "override",
                          "what": "Someone continued anyway"})
        elif kind == "link_reported":
            items.append({"at": record["ts"], "outcome": "reported", "reason": "link_reported",
                          "host": payload.get("host", ""), "what": "A site was reported"})

    items.reverse()
    counted = [i["outcome"] for i in items]
    return {
        "days": days,
        "summary": {
            "stopped": sum(1 for o in counted if o in ("blocked", "needs_approval", "cool_off")),
            "approved": counted.count("approved"),
            "declined": counted.count("declined"),
            "overridden": counted.count("overridden"),
        },
        "items": items[:60],
    }


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
