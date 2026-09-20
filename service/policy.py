"""
The gate.

This is the whole product in one function. Everything else — the extension, the
phone app, the link checker — exists to feed it or to carry out what it says.

Two rules govern its design:

  **It is deterministic.** No model input reaches it. A language model decides
  how to phrase the outcome and never what the outcome is, because a system
  where prose can change the decision can be argued into changing the decision,
  and the whole point is to face an attacker whose entire skill is argument.

  **It is about authorization, not detection.** It never asks "is this a scam?"
  It asks "did this action's instruction arrive through a channel that is allowed
  to authorize it?" A scammer can rewrite the message until it is perfect; they
  cannot make the message stop being a message.

The dispositions are deliberately four, not two. `BLOCKED` is rare and reserved
for things with no legitimate version mid-call. Most friction is `COOL_OFF` (the
same wait a bank puts on a new payee) or `NEEDS_APPROVAL` (someone else, on
another device, says yes). Every one of them can be overridden by the person at
the keyboard, and every override is written to the audit log — a handbrake, not
a cage. A control that cannot be overridden is a control that gets uninstalled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .provenance import Provenance, pretty_source


class ActionType(str, Enum):
    """The irreversible moves. Deliberately short: every entry here is something
    that loses money, credentials or control of the machine, and cannot be
    undone by closing the tab."""

    PAYMENT_NEW_PAYEE = "payment_new_payee"
    PAYMENT_KNOWN_PAYEE = "payment_known_payee"
    OTP_ENTRY = "otp_entry"
    CREDENTIAL_ENTRY = "credential_entry"
    REMOTE_ACCESS_DOWNLOAD = "remote_access_download"
    APP_INSTALL_FILE = "app_install_file"
    SENSITIVE_DATA_ENTRY = "sensitive_data_entry"
    GIFT_CARD_PURCHASE = "gift_card_purchase"
    CRYPTO_TRANSFER = "crypto_transfer"

    @property
    def is_payment(self) -> bool:
        return self in (ActionType.PAYMENT_NEW_PAYEE, ActionType.PAYMENT_KNOWN_PAYEE)

    @property
    def hands_over_control(self) -> bool:
        return self in (ActionType.REMOTE_ACCESS_DOWNLOAD, ActionType.APP_INSTALL_FILE)


class Disposition(str, Enum):
    ALLOW = "allow"
    COOL_OFF = "cool_off"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


class Limits(BaseModel):
    """What this household has decided can happen without a second opinion.

    Set once, by whoever is calmest, and enforced at the moment when nobody is
    calm. Defaults are deliberately generous: a product that blocks ordinary
    life gets switched off, and a switched-off handbrake stops nothing.
    """

    currency: str = "INR"
    per_transaction_cap: float = Field(default=25_000, ge=0)
    daily_cap: float = Field(default=50_000, ge=0)
    new_payee_cooling_minutes: int = Field(default=10, ge=0)
    block_remote_access: bool = True
    guardian_name: str = "your guardian"


@dataclass(frozen=True)
class Action:
    """What the person is about to do, as observed on the page."""

    type: ActionType
    host: str = ""
    amount: Optional[float] = None
    payee: Optional[str] = None
    file_name: Optional[str] = None
    # "card number", "Aadhaar number", "PAN". The value never leaves the page:
    # the page tells NoScam what kind of thing is being typed, not what it says.
    data_kind: Optional[str] = None


@dataclass(frozen=True)
class Decision:
    disposition: Disposition
    reason_code: str
    headline: str
    detail: str
    release: Optional[str] = None          # "approval" | "wait" | None
    wait_seconds: int = 0
    evidence: dict = field(default_factory=dict)

    @property
    def stops_the_action(self) -> bool:
        return self.disposition is not Disposition.ALLOW


def _sentence(text: str) -> str:
    """Capitalise the first letter only. `str.capitalize()` lowercases the rest,
    which turns "WhatsApp" into "whatsapp" — and a product that misspells the
    app someone is looking at has just told them it doesn't know what it saw."""
    return text[:1].upper() + text[1:]


def _money(amount: Optional[float], limits: Limits) -> str:
    if amount is None:
        return "this payment"
    symbol = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}.get(limits.currency, "")
    return f"{symbol}{amount:,.0f}"


def decide(
    action: Action,
    provenance: Provenance,
    limits: Limits,
    *,
    now: datetime,
    spent_today: float = 0.0,
    host_reported: bool = False,
    approved: bool = False,
) -> Decision:
    """The single decision point. Pure: same inputs, same answer, no clock of its
    own, no network, no model.

    `approved` is a fact established elsewhere — the caller has already checked
    the approval's nonce, expiry and action fingerprint. Keeping that check out
    of here is what lets this function be exhaustively tested as a truth table.
    """
    tainted = provenance.is_tainted(now)
    arrival = provenance.describe(now)
    evidence = {
        "tainted": tainted,
        "arrival": arrival,
        "source": provenance.source_host,
        "host": action.host,
        "amount": action.amount,
        "payee": action.payee,
    }

    # 1. Handing someone else live control of the machine. There is no version of
    #    this that a real bank or a real police officer asks for, and unlike a
    #    payment it cannot be reversed once the session is open — so it does not
    #    become acceptable just because a guardian is asleep and says yes.
    if action.type is ActionType.REMOTE_ACCESS_DOWNLOAD and limits.block_remote_access:
        what = action.file_name or "this program"
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="remote_access_blocked",
            headline="This would let someone else control your computer",
            detail=(f"{what} gives another person live control of this machine. "
                    f"Real banks and real police never ask for this. "
                    f"The download has been stopped."),
            evidence=evidence,
        )

    # 1b. Any other installer, when a message is what sent you to it. This is the
    #     APK-in-a-WhatsApp-message scam, which ends with the attacker reading
    #     every SMS on the phone. Installing software you went looking for
    #     yourself is ordinary computer use and is left alone.
    if action.type is ActionType.APP_INSTALL_FILE and tainted:
        what = action.file_name or "this file"
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="install_after_message",
            headline="Don't install this",
            detail=(f"{what} arrived through a message — {arrival}. Apps sent in "
                    f"messages are how phones and computers get taken over. "
                    f"The download has been stopped."),
            evidence=evidence,
        )

    # 2. Somebody in this household already reported this site.
    if host_reported:
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="reported_link",
            headline="This site was reported as a scam",
            detail=(f"Someone in your household reported {action.host or 'this site'} "
                    f"as a scam. Nothing has been sent."),
            evidence=evidence,
        )

    # 3. An approval that was granted out of band, on another device, for exactly
    #    this action. Checked by the caller; honoured here.
    #
    #    Only for money leaving, because those are the cases where a second
    #    opinion is the designed way through. The refusals below — a one-time
    #    code on a page a message sent you to, gift cards, an identity document
    #    — are not requests awaiting permission, and a guardian being pressured
    #    on their own phone is simply the next move in the same script.
    if approved and (action.type.is_payment or action.type is ActionType.CRYPTO_TRANSFER):
        return Decision(
            disposition=Disposition.ALLOW,
            reason_code="approved_out_of_band",
            headline="Approved",
            detail=f"{limits.guardian_name} approved this on their own device.",
            evidence=evidence,
        )

    # 4. Credentials and one-time codes, entered on a page a message sent you to.
    #    The OTP is the last thing standing between the attacker and the account,
    #    and it is worth nothing if it is typed on their page.
    if action.type in (ActionType.OTP_ENTRY, ActionType.CREDENTIAL_ENTRY) and tainted:
        thing = "one-time code" if action.type is ActionType.OTP_ENTRY else "password"
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="credentials_after_message",
            headline=f"Don't type your {thing} here",
            detail=(f"This page asked for your {thing}, and {arrival}. "
                    f"That is what a fake bank page looks like. "
                    f"Open your bank yourself instead of using the link."),
            evidence=evidence,
        )

    # 4b. Identity documents and card numbers, typed into a page a message sent
    #     you to. These are not recoverable: a card can be reissued, an Aadhaar
    #     or PAN number is yours for life and is the raw material for opening
    #     accounts in someone else's name.
    if action.type is ActionType.SENSITIVE_DATA_ENTRY and tainted:
        kind = action.data_kind or "personal details"
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="sensitive_data_after_message",
            headline=f"Don't put your {kind} into this page",
            detail=(f"This page is collecting your {kind}, and {arrival}. "
                    f"Real organisations don't ask for it this way, and unlike a "
                    f"password you can't change it afterwards."),
            evidence=evidence,
        )

    # 4c. Gift cards. The FTC has been saying it for years and it is still the
    #     single clearest tell in the whole business: no government department,
    #     bank, utility or police force is ever paid in gift cards. Buying one
    #     as a present is ordinary, so only a message-driven purchase is
    #     refused — but that refusal needs no second opinion.
    if action.type is ActionType.GIFT_CARD_PURCHASE and tainted:
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="gift_cards_after_message",
            headline="Nobody legitimate is ever paid in gift cards",
            detail=(f"Someone messaged you and now you're buying gift cards — {arrival}. "
                    f"No tax office, bank, police force or utility takes payment this "
                    f"way. Whoever asked is stealing from you."),
            evidence=evidence,
        )

    # 4d. Crypto. Irreversible by design: once it is sent there is no bank, no
    #     chargeback and no dispute. That is true of a legitimate transfer too,
    #     which is why a clean one still gets a second pair of eyes.
    if action.type is ActionType.CRYPTO_TRANSFER:
        where = action.payee or "that wallet"
        if tainted:
            return Decision(
                disposition=Disposition.BLOCKED,
                reason_code="crypto_after_message",
                headline="This money cannot be got back",
                detail=(f"You're sending cryptocurrency to {where}, and {arrival}. "
                        f"Crypto has no chargeback and no dispute process — this is "
                        f"why investment and romance scams ask for it."),
                evidence=evidence,
            )
        return Decision(
            disposition=Disposition.NEEDS_APPROVAL,
            reason_code="crypto_needs_second_pair_of_eyes",
            headline="Crypto can't be reversed",
            detail=(f"You're sending cryptocurrency to {where}. There is no way to undo "
                    f"it, so it needs a second pair of eyes."),
            release="approval",
            evidence=evidence,
        )

    if action.type.is_payment:
        amount = action.amount or 0.0
        payee = action.payee or "someone new"

        # 5. The headline case: a payment to a brand-new payee, on a page a
        #    message sent you to. This is the shape of nearly every "move your
        #    money to a safe account" loss.
        if action.type is ActionType.PAYMENT_NEW_PAYEE and tainted:
            return Decision(
                disposition=Disposition.NEEDS_APPROVAL,
                reason_code="new_payee_after_message",
                headline="This payment is on hold",
                detail=(f"You're about to send {_money(action.amount, limits)} to {payee}, "
                        f"who you've never paid before — and {arrival}. "
                        f"Nothing has been sent yet."),
                release="approval",
                evidence=evidence,
            )

        # 6/7. Size. Above the household's own caps, someone else says yes.
        if amount > limits.per_transaction_cap:
            return Decision(
                disposition=Disposition.NEEDS_APPROVAL,
                reason_code="over_transaction_cap",
                headline="This is larger than your limit",
                detail=(f"{_money(action.amount, limits)} is above the "
                        f"{_money(limits.per_transaction_cap, limits)} limit your household set."),
                release="approval",
                evidence=evidence,
            )
        if spent_today + amount > limits.daily_cap:
            return Decision(
                disposition=Disposition.NEEDS_APPROVAL,
                reason_code="over_daily_cap",
                headline="This would go over today's limit",
                detail=(f"Today's payments would reach "
                        f"{_money(spent_today + amount, limits)}, above the "
                        f"{_money(limits.daily_cap, limits)} daily limit."),
                release="approval",
                evidence=evidence,
            )

        # 8. A payment to someone you already pay, but a message brought you
        #    here. Lower risk — the money goes where it has gone before — so a
        #    short pause rather than waking somebody up.
        if tainted:
            return Decision(
                disposition=Disposition.COOL_OFF,
                reason_code="payment_after_message",
                headline="Take two minutes",
                detail=(f"{_sentence(arrival)}. The payment is to {payee}, who you've paid "
                        f"before, so this is just a pause. If someone is on the phone telling "
                        f"you to hurry, that is the scam."),
                release="wait",
                wait_seconds=120,
                evidence=evidence,
            )

        # 9. A first payment to a new payee, reached under your own steam. Banks
        #    have put a delay here for years, for the same reason.
        if action.type is ActionType.PAYMENT_NEW_PAYEE and limits.new_payee_cooling_minutes:
            return Decision(
                disposition=Disposition.COOL_OFF,
                reason_code="new_payee_cooling",
                headline=f"First payment to {payee}",
                detail=(f"New payees wait {limits.new_payee_cooling_minutes} minutes in your "
                        f"household. Nothing else is wrong with this payment."),
                release="wait",
                wait_seconds=limits.new_payee_cooling_minutes * 60,
                evidence=evidence,
            )

    # 10. Everything else: the ordinary day, untouched.
    return Decision(
        disposition=Disposition.ALLOW,
        reason_code="ok",
        headline="Allowed",
        detail="Nothing about this looked unusual.",
        evidence=evidence,
    )


def decide_arrival(
    *, signal_codes: list[str], verdict: str, provenance: Provenance, host: str,
    now: datetime, host_reported: bool = False,
) -> Optional[Decision]:
    """Judge a page as it opens, before anything has been typed into it.

    Deliberately narrow. A warning on every slightly-odd site is a warning
    nobody reads, so this fires only when the address itself carries a serious
    signal *and* a message is what sent the person here — or when the household
    has already reported the site. Everything else is left to the gate, at the
    moment something irreversible is actually attempted.
    """
    if host_reported:
        return Decision(
            disposition=Disposition.BLOCKED,
            reason_code="reported_page_opened",
            headline="This is the site you reported",
            detail=f"Someone in your household marked {host} as a scam.",
            evidence={"host": host, "signals": signal_codes},
        )
    if verdict != "dangerous" or not provenance.is_tainted(now):
        return None
    return Decision(
        disposition=Disposition.BLOCKED,
        reason_code="phishing_page_after_message",
        headline="This page is pretending to be someone else",
        detail=(f"{_sentence(provenance.describe(now))}, and the address itself gives "
                f"it away. Close it and open the real site yourself."),
        evidence={"host": host, "signals": signal_codes},
    )


def cool_off_expires(decision: Decision, started: datetime) -> Optional[datetime]:
    if decision.disposition is not Disposition.COOL_OFF:
        return None
    return started + timedelta(seconds=decision.wait_seconds)


def guardian_line(decision: Decision, limits: Limits) -> str:
    """The button text on the block screen."""
    if decision.release == "approval":
        return f"Ask {limits.guardian_name} to approve"
    if decision.release == "wait":
        minutes = max(1, decision.wait_seconds // 60)
        return f"Wait {minutes} minute{'s' if minutes != 1 else ''}"
    return "Go back to safety"


__all__ = [
    "Action", "ActionType", "Decision", "Disposition", "Limits",
    "decide", "decide_arrival", "cool_off_expires", "guardian_line", "pretty_source",
]
