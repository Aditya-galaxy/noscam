"""
The service end to end: a held payment, an approval from another device, and
every way an approval must not work.

The replay tests are the security-relevant ones. An approval that can be reused,
or stretched to cover a different payment, is worse than no approval at all —
it would let the scammer convert one moment of a guardian's inattention into
everything in the account.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("NOSCAM_DATA", str(tmp_path))
    import service.app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.app), app_module


def just_now() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()


PAYMENT = {
    "action": {"type": "payment", "host": "hdfc-secure.example",
               "amount": 18000, "payee": "Rahul Verma"},
    "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
}


def test_a_scam_payment_is_held_and_a_hold_is_raised(api) -> None:
    client, _ = api
    body = client.post("/gate/check", json=PAYMENT).json()
    assert body["disposition"] == "needs_approval"
    assert body["reason_code"] == "new_payee_after_message"
    assert body["hold_id"]
    assert "WhatsApp" in body["detail"]

    pending = client.get("/holds").json()
    assert len(pending) == 1 and pending[0]["id"] == body["hold_id"]


def test_the_same_attempt_reuses_one_hold_rather_than_spamming_the_guardian(api) -> None:
    client, _ = api
    first = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    second = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    assert first == second
    assert len(client.get("/holds").json()) == 1


def test_an_approval_from_the_other_device_releases_exactly_that_payment(api) -> None:
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve", "by": "Priya"})

    released = client.post("/gate/check", json=PAYMENT).json()
    assert released["disposition"] == "allow"
    assert released["reason_code"] == "approved_out_of_band"


def test_an_approval_does_not_carry_to_a_different_payment(api) -> None:
    """The scam's next move after a guardian says yes to something small."""
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve", "by": "Priya"})

    bigger = {**PAYMENT, "action": {**PAYMENT["action"], "amount": 180000}}
    assert client.post("/gate/check", json=bigger).json()["disposition"] != "allow"

    elsewhere = {**PAYMENT, "action": {**PAYMENT["action"], "payee": "Someone Else"}}
    assert client.post("/gate/check", json=elsewhere).json()["disposition"] != "allow"


def test_an_approval_cannot_be_given_twice(api) -> None:
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    first = client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve"})
    second = client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve"})
    assert first.status_code == 200
    assert second.status_code == 409


def test_an_expired_request_cannot_be_approved(api) -> None:
    client, module = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]

    def age_it(state):
        state.holds[hold_id].expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    module.store.update(age_it)
    assert client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve"}).status_code == 409
    # And the gate does not honour it either.
    assert client.post("/gate/check", json=PAYMENT).json()["disposition"] == "needs_approval"


def test_a_denial_stops_the_payment_and_says_who_declined(api) -> None:
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    client.post(f"/holds/{hold_id}/decision", json={"verdict": "deny", "by": "Priya"})
    after = client.post("/gate/check", json=PAYMENT).json()
    assert after["disposition"] == "blocked"
    assert after["reason_code"] == "denied_by_guardian"


def test_an_ordinary_payment_is_untouched_and_remembers_the_payee(api) -> None:
    client, _ = api
    ordinary = {
        "action": {"type": "payment", "host": "bank.example", "amount": 1500,
                   "payee": "Landlord"},
        "provenance": {"origin": "typed", "at": just_now()},
    }
    first = client.post("/gate/check", json=ordinary).json()
    assert first["disposition"] == "cool_off"          # first time to a new payee
    assert first["reason_code"] == "new_payee_cooling"

    hold_id = first["hold_id"]
    client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve", "by": "self"})
    second = client.post("/gate/check", json=ordinary).json()
    assert second["disposition"] == "allow"

    # Now they are a known payee, and the next payment sails through.
    assert "Landlord" in client.get("/household").json()["known_payees"]
    third = client.post("/gate/check", json=ordinary).json()
    assert third["disposition"] == "allow" and third["reason_code"] == "ok"


def test_spending_accumulates_against_the_daily_cap(api) -> None:
    client, _ = api
    client.put("/limits", json={"per_transaction_cap": 30000, "daily_cap": 40000,
                                "new_payee_cooling_minutes": 0, "guardian_name": "Priya"})
    payment = {
        "action": {"type": "payment", "host": "bank.example", "amount": 25000,
                   "payee": "Landlord"},
        "provenance": {"origin": "typed", "at": just_now()},
    }
    assert client.post("/gate/check", json=payment).json()["disposition"] == "allow"
    second = client.post("/gate/check", json=payment).json()
    assert second["reason_code"] == "over_daily_cap"


def test_an_override_is_allowed_and_recorded(api) -> None:
    """A control nobody can override is a control that gets uninstalled — but
    the override is evidence, not a secret."""
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    body = client.post(f"/holds/{hold_id}/override", json={"reason": "I'm sure"}).json()
    assert body["status"] == "overridden"
    kinds = [r["kind"] for r in client.get("/audit/recent").json()]
    assert "override" in kinds


def test_reporting_a_link_protects_the_whole_household(api) -> None:
    client, _ = api
    client.post("/links/report", json={"url": "https://fake-bank.example/login"})
    checked = client.post("/links/check", json={"url": "https://fake-bank.example/login",
                                                "fetch": False}).json()
    assert checked["verdict"] == "dangerous"
    assert "reported_by_household" in [s["code"] for s in checked["signals"]]

    blocked = client.post("/gate/check", json={
        "action": {"type": "payment", "host": "fake-bank.example", "amount": 100,
                   "payee": "Whoever"},
        "provenance": {"origin": "typed", "at": just_now()},
    }).json()
    assert blocked["reason_code"] == "reported_link"


def test_every_decision_lands_in_a_verifiable_audit_chain(api) -> None:
    client, module = api
    client.post("/gate/check", json=PAYMENT)
    client.post("/links/check", json={"url": "https://hdfcbamk.com", "fetch": False})
    assert client.get("/audit/verify").json() == {"ok": True, "first_broken_line": None,
                                                  "records": 2}

    # Tamper with the log; verification must name the line. The edit is asserted
    # to have applied — a search-and-replace that quietly matches nothing would
    # make this test pass for the wrong reason.
    lines = open(module.audit.path).read().splitlines()
    tampered = lines[0].replace('"gate_decision"', '"nothing_happened"')
    assert tampered != lines[0], "the tamper did not apply"
    lines[0] = tampered
    open(module.audit.path, "w").write("\n".join(lines) + "\n")
    verdict = client.get("/audit/verify").json()
    assert verdict["ok"] is False and verdict["first_broken_line"] == 1


def test_pairing_needs_the_code_from_the_other_device(api) -> None:
    client, _ = api
    assert client.post("/pair/claim", json={"code": "000000"}).status_code == 403
    code = client.post("/pair/start").json()["code"]
    assert len(code) == 6
    assert client.post("/pair/claim", json={"code": code, "device": "Chrome"}).json()["paired"]
    # Single use: the code is spent.
    assert client.post("/pair/claim", json={"code": code}).status_code == 403
