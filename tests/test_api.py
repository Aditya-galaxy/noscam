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


def test_a_phishing_page_from_a_message_is_held_on_arrival(api) -> None:
    client, _ = api
    body = client.post("/gate/arrival", json={
        "url": "https://hdfcbank.secure-verify.example/login",
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    }).json()
    assert body["disposition"] == "blocked"
    assert body["reason_code"] == "phishing_page_after_message"
    assert body["hold_id"]

    # It is the household's record, not just a banner: the phone sees it too.
    assert any(h["id"] == body["hold_id"] for h in client.get("/holds").json())


def test_an_ordinary_page_is_not_interrupted_on_arrival(api) -> None:
    client, _ = api
    body = client.post("/gate/arrival", json={
        "url": "https://hdfcbank.com/netbanking",
        "provenance": {"origin": "typed", "at": just_now()},
    }).json()
    assert body["disposition"] == "allow"
    assert body["hold_id"] is None


def test_card_numbers_are_refused_on_a_page_a_message_sent_you_to(api) -> None:
    client, _ = api
    body = client.post("/gate/check", json={
        "action": {"type": "sensitive_data_entry", "host": "kyc-update.example",
                   "data_kind": "card number"},
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    }).json()
    assert body["disposition"] == "blocked"
    assert "card number" in body["headline"]


def test_a_refusal_cannot_be_approved_by_anyone(api) -> None:
    """A one-time code on a page a message sent you to is refused, not
    requested. A guardian being pressured on their own phone is the next move
    in the same script, so there is no button for it."""
    client, _ = api
    body = client.post("/gate/check", json={
        "action": {"type": "otp_entry", "host": "hdfc-secure.example"},
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    }).json()
    assert body["disposition"] == "blocked"

    hold_id = body["hold_id"]
    assert client.get(f"/holds/{hold_id}").json()["approvable"] is False
    refused = client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve"})
    assert refused.status_code == 409

    # And the gate does not honour an approval even if one were forged in.
    from service.store import State

    def approve(state: State) -> None:
        state.holds[hold_id].status = "approved"

    import importlib
    import service.app as module
    importlib.reload  # keep the reference honest; store is the live one
    module.store.update(approve)
    again = client.post("/gate/check", json={
        "action": {"type": "otp_entry", "host": "hdfc-secure.example"},
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    }).json()
    assert again["disposition"] == "blocked"


def test_a_guardian_can_let_a_waiting_payment_through_early(api) -> None:
    """The cooling period exists so somebody can think. If the somebody has
    thought, it has done its job."""
    client, _ = api
    first = client.post("/gate/check", json={
        "action": {"type": "payment", "host": "bank.example", "amount": 2200,
                   "payee": "Plumber"},
        "provenance": {"origin": "typed", "at": just_now()},
    }).json()
    assert first["disposition"] == "cool_off"
    assert client.get(f"/holds/{first['hold_id']}").json()["approvable"] is True


# --------------------------------------------------------------------------- #
# The local service is reachable from every page in the browser
# --------------------------------------------------------------------------- #

SCAM_PAGE = {"origin": "http://scam.example"}


def test_a_web_page_cannot_approve_the_hold_raised_against_it(api) -> None:
    """The complete bypass this check exists to stop: the scam page raising a
    hold and then answering it in JavaScript, on the machine it is running on."""
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]

    refused = client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve"},
                          headers=SCAM_PAGE)
    assert refused.status_code == 403
    assert client.get(f"/holds/{hold_id}").json()["status"] == "pending"
    assert client.post("/gate/check", json=PAYMENT).json()["disposition"] == "needs_approval"


@pytest.mark.parametrize("method, path, body", [
    ("put", "/limits", {"per_transaction_cap": 10_000_000, "daily_cap": 10_000_000}),
    ("post", "/household/payees", {"payees": ["The Attacker"]}),
    ("post", "/household/reset", None),
    ("post", "/links/report", {"url": "https://hdfcbank.com"}),
    ("post", "/pair/start", None),
])
def test_a_web_page_cannot_change_the_household(api, method, path, body) -> None:
    """Raising the limits, adding themselves as a known payee, wiping the day's
    spending, or blocklisting the real bank — all from a page."""
    client, _ = api
    response = getattr(client, method)(path, json=body, headers=SCAM_PAGE)
    assert response.status_code == 403


def test_a_web_page_cannot_read_the_household(api) -> None:
    """Payees, limits and what has been spent today are nobody else's business."""
    client, _ = api
    assert client.get("/household", headers=SCAM_PAGE).status_code == 403


def test_the_phone_app_and_the_extension_are_allowed(api) -> None:
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]

    # The phone app is served by this service, so its Origin is our own host.
    phone = client.post(f"/holds/{hold_id}/decision", json={"verdict": "deny"},
                        headers={"origin": "http://testserver", "host": "testserver"})
    assert phone.status_code == 200

    # The extension has an extension origin.
    assert client.get("/household",
                      headers={"origin": "chrome-extension://abcdefghijklmnop"}
                      ).status_code == 200


def test_a_page_may_still_report_what_it_is_looking_at_to_the_gate(api) -> None:
    """Checking an action and overriding your own hold stay open: the hosted
    demo runs the content script inside an ordinary page, and neither lets a
    page do anything it could not do by simply proceeding."""
    client, _ = api
    body = client.post("/gate/check", json=PAYMENT, headers=SCAM_PAGE).json()
    assert body["disposition"] == "needs_approval"
    assert client.post(f"/holds/{body['hold_id']}/override", json={"reason": "x"},
                       headers=SCAM_PAGE).status_code == 200


def test_a_page_cannot_bury_the_real_request_under_invented_ones(api) -> None:
    """Flooding the queue is the oldest attack on any alerting system: make the
    guardian scroll past a hundred cards to find the one that matters."""
    client, module = api
    for index in range(40):
        client.post("/gate/check", json={
            "action": {"type": "payment", "host": "scam.example", "amount": 100 + index,
                       "payee": f"Decoy {index}"},
            "provenance": {"origin": "link", "source_host": "web.whatsapp.com",
                           "at": just_now()},
        })

    pending = client.get("/holds").json()
    assert len(pending) <= 25

    # The gate still decides and still refuses; only the queue is capped.
    flooded = client.post("/gate/check", json={
        "action": {"type": "payment", "host": "scam.example", "amount": 99_000,
                   "payee": "The Attacker"},
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    }).json()
    assert flooded["disposition"] == "needs_approval"
    assert "hold_queue_full" in [r["kind"] for r in client.get("/audit/recent?limit=60").json()]


def test_a_household_can_say_who_it_already_pays_and_change_its_mind(api) -> None:
    """Without this, every ordinary payment a real household makes is
    interrupted the first time — and a tool that does that gets switched off."""
    client, _ = api
    client.post("/household/payees", json={"payees": ["Landlord", "Aarav"]})
    assert client.get("/household").json()["known_payees"] == ["Landlord", "Aarav"]

    ordinary = {
        "action": {"type": "payment", "host": "bank.example", "amount": 2000,
                   "payee": "Landlord"},
        "provenance": {"origin": "typed", "at": just_now()},
    }
    assert client.post("/gate/check", json=ordinary).json()["disposition"] == "allow"

    # Forgetting someone makes the next payment to them wait again: the
    # forgetful direction is the safe one.
    client.delete("/household/payees/Landlord")
    assert client.get("/household").json()["known_payees"] == ["Aarav"]
    assert client.post("/gate/check", json=ordinary).json()["reason_code"] == "new_payee_cooling"


def test_a_web_page_cannot_forget_a_payee_for_you(api) -> None:
    client, _ = api
    client.post("/household/payees", json={"payees": ["Landlord"]})
    assert client.delete("/household/payees/Landlord",
                         headers=SCAM_PAGE).status_code == 403


# --------------------------------------------------------------------------- #
# The second device has to be able to reach the service — and only the right one
# --------------------------------------------------------------------------- #

@pytest.fixture
def lan(api, monkeypatch):
    """LAN mode, as a phone on the same Wi-Fi would see it."""
    client, module = api
    monkeypatch.setattr(module, "LAN_MODE", True)
    monkeypatch.setattr(module, "LOOPBACK", set())      # pretend this client is elsewhere
    return client, module


def test_another_device_on_the_wifi_cannot_answer_without_the_token(lan) -> None:
    """Origin proves a page is not lying about itself; it proves nothing about
    which device is asking. On a shared network that is the whole question."""
    client, _ = lan
    assert client.get("/holds").status_code == 401
    assert client.get("/household").status_code == 401
    assert client.post("/links/check", json={"url": "https://x.example", "fetch": False}
                       ).status_code == 401


def test_the_paired_phone_works(lan) -> None:
    client, module = lan
    headers = {"X-NoScam-Token": module.household_token()}
    assert client.get("/holds", headers=headers).status_code == 200
    assert client.get("/household", headers=headers).status_code == 200


def test_a_wrong_token_is_refused(lan) -> None:
    client, _ = lan
    assert client.get("/holds", headers={"X-NoScam-Token": "not-the-token"}
                      ).status_code == 401


def test_the_token_also_travels_in_the_link_the_phone_opens(lan) -> None:
    """It arrives once, in the URL, and the app keeps it from then on."""
    client, module = lan
    assert client.get(f"/holds?t={module.household_token()}").status_code == 200


def test_loopback_needs_no_token_so_the_extension_is_unaffected(api) -> None:
    """The extension talks to 127.0.0.1 from this machine. Making it carry a
    token would add a pairing step that protects nothing."""
    client, _ = api
    assert client.get("/holds").status_code == 200


def test_the_household_can_see_what_noscam_actually_did(api) -> None:
    """A hold disappears after five minutes. Without a record anyone can read,
    the overrides are logged for nobody and nothing can be judged."""
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    client.post(f"/holds/{hold_id}/decision", json={"verdict": "approve", "by": "Priya"})
    client.post("/gate/check", json={
        "action": {"type": "otp_entry", "host": "hdfc-secure.example"},
        "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": just_now()},
    })

    history = client.get("/history").json()
    assert history["summary"]["stopped"] >= 2
    assert history["summary"]["approved"] == 1
    outcomes = [item["outcome"] for item in history["items"]]
    assert "approved" in outcomes and "blocked" in outcomes
    # Newest first: someone opening this wants to know what just happened.
    assert history["items"][0]["at"] >= history["items"][-1]["at"]


def test_an_override_is_surfaced_rather_than_just_logged(api) -> None:
    client, _ = api
    hold_id = client.post("/gate/check", json=PAYMENT).json()["hold_id"]
    client.post(f"/holds/{hold_id}/override", json={"reason": "I'm sure"})
    assert client.get("/history").json()["summary"]["overridden"] == 1


def test_history_is_not_readable_by_a_web_page_or_an_unpaired_device(api, monkeypatch) -> None:
    client, module = api
    monkeypatch.setattr(module, "LAN_MODE", True)
    monkeypatch.setattr(module, "LOOPBACK", set())
    assert client.get("/history").status_code == 401


def test_history_is_written_for_a_person_not_for_us(api) -> None:
    """Nobody should have to read "new_payee_after_message" to find out what
    happened to their money."""
    client, _ = api
    client.post("/gate/check", json=PAYMENT)
    item = client.get("/history").json()["items"][0]
    assert item["what"] == "A payment to someone new, pushed by a message"
    assert "_" not in item["what"]
