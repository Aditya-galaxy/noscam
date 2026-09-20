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


def test_an_apk_sent_in_a_message_is_blocked() -> None:
    decision = decide(
        Action(type=ActionType.APP_INSTALL_FILE, host="challan-pay.example",
               file_name="traffic-challan.apk"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "install_after_message"


def test_software_you_went_and_got_yourself_is_left_alone() -> None:
    """Blocking every installer would break ordinary computer use, and a tool
    that does that gets uninstalled before it ever stops a scam."""
    decision = decide(
        Action(type=ActionType.APP_INSTALL_FILE, host="zoom.us",
               file_name="Zoom.pkg"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW


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


# --------------------------------------------------------------------------- #
# Personal data, and pages judged as they open
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", ["card number", "Aadhaar number", "PAN"])
def test_personal_data_is_refused_on_a_page_a_message_sent_you_to(kind: str) -> None:
    """A password can be changed afterwards. An Aadhaar number cannot."""
    decision = decide(
        Action(type=ActionType.SENSITIVE_DATA_ENTRY, host="kyc-update.example", data_kind=kind),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "sensitive_data_after_message"
    assert kind in decision.headline
    assert "can't change it afterwards" in decision.detail


def test_typing_your_card_number_into_a_site_you_opened_is_ordinary_life() -> None:
    decision = decide(
        Action(type=ActionType.SENSITIVE_DATA_ENTRY, host="shop.example",
               data_kind="card number"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW


def test_a_fake_page_opened_from_a_message_is_called_out_on_arrival() -> None:
    from service.policy import decide_arrival

    decision = decide_arrival(signal_codes=["brand_not_in_domain"], verdict="dangerous",
                              provenance=from_message(), host="hdfcbank.verify.example",
                              now=NOW)
    assert decision is not None
    assert decision.reason_code == "phishing_page_after_message"
    assert "WhatsApp" in decision.detail


def test_arrival_warnings_are_narrow_on_purpose() -> None:
    """A warning on every slightly-odd site is a warning nobody reads."""
    from service.policy import decide_arrival

    # Dangerous address, but the person went there themselves.
    assert decide_arrival(signal_codes=["lookalike_domain"], verdict="dangerous",
                          provenance=typed_myself(), host="x.example", now=NOW) is None
    # From a message, but nothing serious in the address.
    assert decide_arrival(signal_codes=["not_https"], verdict="suspicious",
                          provenance=from_message(), host="x.example", now=NOW) is None


def test_a_reported_site_is_called_out_however_you_reached_it() -> None:
    from service.policy import decide_arrival

    decision = decide_arrival(signal_codes=[], verdict="no_signals",
                              provenance=typed_myself(), host="bad.example", now=NOW,
                              host_reported=True)
    assert decision is not None and decision.reason_code == "reported_page_opened"


def test_the_app_name_is_not_mangled_when_a_sentence_is_capitalised() -> None:
    """str.capitalize() would render "WhatsApp" as "whatsapp"; a product that
    misspells the app in front of the person has told them it wasn't looking."""
    decision = decide(
        Action(type=ActionType.PAYMENT_KNOWN_PAYEE, amount=2_000, payee="Landlord"),
        from_message(), LIMITS, now=NOW,
    )
    assert "WhatsApp" in decision.detail


# --------------------------------------------------------------------------- #
# The other ways money leaves: gift cards and crypto
# --------------------------------------------------------------------------- #

def test_gift_cards_bought_because_of_a_message_are_refused_outright() -> None:
    """The clearest tell in the whole business: nobody legitimate is paid this
    way, so this one does not wait on a guardian being awake."""
    decision = decide(
        Action(type=ActionType.GIFT_CARD_PURCHASE, host="shop.example", amount=5_000),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "gift_cards_after_message"
    assert "gift cards" in decision.headline


def test_buying_a_gift_card_as_a_present_is_left_alone() -> None:
    decision = decide(
        Action(type=ActionType.GIFT_CARD_PURCHASE, host="shop.example", amount=2_000),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.ALLOW


def test_crypto_after_a_message_is_refused() -> None:
    decision = decide(
        Action(type=ActionType.CRYPTO_TRANSFER, host="exchange.example",
               amount=50_000, payee="0x8f2a55949038a501cb1bd0e2b3b0a2e2f0d3c111"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "crypto_after_message"
    assert "no chargeback" in decision.detail


def test_crypto_you_started_yourself_still_needs_a_second_pair_of_eyes() -> None:
    """Irreversible either way. The friction is the point, and it is honest
    about being friction rather than an accusation."""
    decision = decide(
        Action(type=ActionType.CRYPTO_TRANSFER, host="exchange.example", amount=5_000,
               payee="bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.NEEDS_APPROVAL
    assert decision.reason_code == "crypto_needs_second_pair_of_eyes"


def test_a_gift_card_code_is_treated_as_something_you_cannot_get_back() -> None:
    decision = decide(
        Action(type=ActionType.SENSITIVE_DATA_ENTRY, host="redeem.example",
               data_kind="gift card code"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED


def test_approving_a_collect_request_is_treated_as_paying() -> None:
    decision = decide(
        Action(type=ActionType.UPI_COLLECT_APPROVAL, host="upi", amount=9_500,
               payee="refund.dept@okaxis"),
        from_message(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.BLOCKED
    assert decision.reason_code == "upi_collect_after_message"
    assert "never needs your approval" in decision.detail


def test_a_collect_request_you_were_expecting_still_gets_a_second_look() -> None:
    decision = decide(
        Action(type=ActionType.UPI_COLLECT_APPROVAL, host="upi", amount=200,
               payee="chai.shop@oksbi"),
        typed_myself(), LIMITS, now=NOW,
    )
    assert decision.disposition is Disposition.NEEDS_APPROVAL
    assert decision.reason_code == "upi_collect_request"
