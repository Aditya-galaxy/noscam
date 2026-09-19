"""
The gate's truth table.

Every test here is a claim NoScam makes to the person using it. The two that
matter most are opposites: a payment pushed by a message is held, and an ordinary
payment the person started themselves is not touched. A product that only got the
first one right would be a product nobody keeps installed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from service.policy import (
    Action, ActionType, Disposition, Limits, cool_off_expires, decide,
)
from service.provenance import Origin, Provenance

NOW = datetime(2026, 9, 19, 18, 30, tzinfo=timezone.utc)


def from_message(seconds_ago: int = 40, host: str = "web.whatsapp.com") -> Provenance:
    return Provenance(origin=Origin.LINK, source_host=host,
                      at=NOW - timedelta(seconds=seconds_ago))


def typed_myself() -> Provenance:
    return Provenance(origin=Origin.TYPED, at=NOW - timedelta(seconds=5))


LIMITS = Limits(guardian_name="Priya")


def test_a_new_payee_payment_pushed_by_a_message_is_held() -> None:
    """The shape of nearly every 'move your money to a safe account' loss."""
    decision = decide(
        Action(type=ActionType.PAYMENT_NEW_PAYEE, host="hdfc-secure.example",
               amount=18_000, payee="Rahul Verma"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.NEEDS_APPROVAL
    assert decision.reason_code == "new_payee_after_message"
    assert decision.release == "approval"
    # The person must be able to check the claim against their own memory.
    assert "WhatsApp" in decision.detail and "40 seconds ago" in decision.detail
    assert "Nothing has been sent" in decision.detail


def test_an_ordinary_payment_to_a_known_payee_is_not_touched() -> None:
    decision = decide(
        Action(type=ActionType.PAYMENT_KNOWN_PAYEE, host="bank.example",
               amount=2_000, payee="Landlord"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW
    assert decision.reason_code == "ok"


def test_a_first_payment_to_a_new_payee_waits_but_is_not_blocked() -> None:
    decision = decide(
        Action(type=ActionType.PAYMENT_NEW_PAYEE, host="bank.example",
               amount=2_000, payee="Plumber"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.COOL_OFF
    assert decision.wait_seconds == 600
    assert cool_off_expires(decision, NOW) == NOW + timedelta(minutes=10)
    # Friction, not accusation: the copy must not imply the payee is a fraud.
    assert "Nothing else is wrong" in decision.detail


def test_remote_access_is_blocked_whatever_the_provenance() -> None:
    """Rule with no exception: a session someone else controls cannot be undone
    by closing the tab, so it does not wait on a guardian being awake."""
    for provenance in (typed_myself(), from_message()):
        decision = decide(
            Action(type=ActionType.REMOTE_ACCESS_DOWNLOAD, host="anydesk.com",
                   file_name="AnyDesk.exe"),
            provenance, LIMITS, now=NOW,
        )
        assert decision.disposition is Disposition.BLOCKED
        assert decision.reason_code == "remote_access_blocked"
        assert "AnyDesk.exe" in decision.detail


def test_an_apk_download_is_the_same_rule() -> None:
    decision = decide(
        Action(type=ActionType.APP_INSTALL_FILE, host="challan-pay.example",
               file_name="traffic-challan.apk"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED


def test_remote_access_can_be_permitted_by_the_household() -> None:
    """Some households legitimately use remote support. The limit is theirs."""
    decision = decide(
        Action(type=ActionType.REMOTE_ACCESS_DOWNLOAD, file_name="AnyDesk.exe"),
        typed_myself(), Limits(block_remote_access=False), now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW


@pytest.mark.parametrize("action_type, word", [
    (ActionType.OTP_ENTRY, "one-time code"),
    (ActionType.CREDENTIAL_ENTRY, "password"),
])
def test_credentials_are_refused_on_a_page_a_message_sent_you_to(action_type, word) -> None:
    decision = decide(Action(type=action_type, host="hdfc-secure.example"),
                      from_message(), LIMITS, now=NOW)
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "credentials_after_message"
    assert word in decision.headline


def test_the_same_credential_page_reached_by_typing_is_fine() -> None:
    """Otherwise NoScam would break logging into your own bank."""
    decision = decide(Action(type=ActionType.CREDENTIAL_ENTRY, host="bank.example"),
                      typed_myself(), LIMITS, now=NOW)
    assert decision.disposition is Disposition.ALLOW


def test_a_large_payment_needs_approval_even_when_nothing_is_suspicious() -> None:
    decision = decide(
        Action(type=ActionType.PAYMENT_KNOWN_PAYEE, amount=40_000, payee="Landlord"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.NEEDS_APPROVAL
    assert decision.reason_code == "over_transaction_cap"


def test_the_daily_cap_counts_what_has_already_gone_today() -> None:
    action = Action(type=ActionType.PAYMENT_KNOWN_PAYEE, amount=20_000, payee="Landlord")
    assert decide(action, typed_myself(), LIMITS, now=NOW,
                  spent_today=10_000).disposition is Disposition.ALLOW
    over = decide(action, typed_myself(), LIMITS, now=NOW, spent_today=45_000)
    assert over.disposition is Disposition.NEEDS_APPROVAL
    assert over.reason_code == "over_daily_cap"


def test_a_known_payee_after_a_message_only_pauses() -> None:
    """Money going where it has gone before is a smaller risk than money going
    somewhere new, and the friction should match."""
    decision = decide(
        Action(type=ActionType.PAYMENT_KNOWN_PAYEE, amount=2_000, payee="Landlord"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.COOL_OFF
    assert decision.wait_seconds == 120
    assert "that is the scam" in decision.detail


def test_a_reported_site_is_blocked_for_the_whole_household() -> None:
    decision = decide(
        Action(type=ActionType.PAYMENT_KNOWN_PAYEE, host="bad.example", amount=100),
        typed_myself(), LIMITS, now=NOW, host_reported=True,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "reported_link"


def test_an_out_of_band_approval_releases_the_payment() -> None:
    decision = decide(
        Action(type=ActionType.PAYMENT_NEW_PAYEE, amount=18_000, payee="Rahul Verma"),
        from_message(), LIMITS, now=NOW, approved=True,
    )
    assert decision.disposition is Disposition.ALLOW
    assert decision.reason_code == "approved_out_of_band"
    assert "Priya" in decision.detail


def test_an_approval_cannot_unlock_remote_access() -> None:
    """The hard block sits above approvals on purpose: a guardian pressured on
    their own phone is exactly the next step in the script."""
    decision = decide(
        Action(type=ActionType.REMOTE_ACCESS_DOWNLOAD, file_name="AnyDesk.exe"),
        from_message(), LIMITS, now=NOW, approved=True,
    )
    assert decision.disposition is Disposition.BLOCKED


def test_taint_expires_so_the_product_stays_usable() -> None:
    """Someone who clicked a link twenty minutes ago and has been reading since
    is not mid-scam."""
    stale = from_message(seconds_ago=20 * 60)
    decision = decide(
        Action(type=ActionType.PAYMENT_NEW_PAYEE, amount=2_000, payee="Plumber"),
        stale, LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.COOL_OFF      # not approval
    assert decision.reason_code == "new_payee_cooling"


def test_a_link_from_an_ordinary_site_is_not_a_message() -> None:
    """Only messaging and webmail count. Clicking through from a news article is
    not someone instructing you."""
    from_news = Provenance(origin=Origin.LINK, source_host="www.thehindu.com",
                           at=NOW - timedelta(seconds=10))
    decision = decide(
        Action(type=ActionType.CREDENTIAL_ENTRY, host="bank.example"),
        from_news, LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW


def test_no_decision_depends_on_prose() -> None:
    """The scammer's copy is not an input. Same action, same provenance, wildly
    different payee text: identical disposition and reason."""
    urgent = Action(type=ActionType.PAYMENT_NEW_PAYEE, amount=18_000,
                    payee="URGENT RBI SAFE ACCOUNT — DO NOT DELAY")
    plain = Action(type=ActionType.PAYMENT_NEW_PAYEE, amount=18_000, payee="Rahul Verma")
    a = decide(urgent, from_message(), LIMITS, now=NOW)
    b = decide(plain, from_message(), LIMITS, now=NOW)
    assert (a.disposition, a.reason_code) == (b.disposition, b.reason_code)
