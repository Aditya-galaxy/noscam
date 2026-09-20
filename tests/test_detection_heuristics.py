"""
The heuristics that decide whether a button is a payment button.

These live in JavaScript because they run in the page, which normally puts them
out of reach of this suite — and they are exactly the part most likely to rot,
because every real payment page words its buttons differently. So the regexes
are read out of the shipped file and executed with node against labels taken
from real sites, including the ones that caught two bugs:

  * "Yes, I'll donate $25 each month" is a standing instruction, not a payment.
    The mandate pattern originally missed it, so a recurring charge would have
    been waved through as a one-off.
  * A payment button with no text at all — an icon — was skipped entirely.

If node is not installed the tests skip rather than lie about having run.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CONTENT_JS = Path(__file__).resolve().parent.parent / "extension" / "content.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def pattern(name: str) -> str:
    """The regex as it is actually shipped, not a copy of it."""
    source = CONTENT_JS.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = /(.+)/i;", source)
    assert match, f"{name} is no longer defined the way this test reads it"
    return match.group(1)


def matches(regex: str, labels: list[str]) -> dict[str, bool]:
    script = (f"const R = /{regex}/i;"
              f"console.log(JSON.stringify({json.dumps(labels)}.map(l => R.test(l))));")
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return dict(zip(labels, json.loads(result.stdout)))


PAYMENT_LABELS = [
    "Pay now", "Transfer now", "Donate by credit/debit card", "Send money",
    "Confirm payment", "Buy gift card", "Proceed to pay",
]
NOT_PAYMENT_LABELS = ["Search", "Go", "Read more", "Sign in", "Filter results"]


def test_real_payment_button_labels_are_recognised() -> None:
    found = matches(pattern("PAY_WORDS"), PAYMENT_LABELS)
    assert all(found.values()), [label for label, hit in found.items() if not hit]


def test_ordinary_buttons_are_left_alone() -> None:
    """A false positive here interrupts someone searching a website, which is
    how a security tool earns its uninstall."""
    found = matches(pattern("PAY_WORDS"), NOT_PAYMENT_LABELS)
    assert not any(found.values()), [label for label, hit in found.items() if hit]


def test_recurring_charges_are_told_apart_from_one_off_payments() -> None:
    """Taken from a live donation page: the recurring button reads "each month"
    and nothing in the original pattern matched it."""
    found = matches(pattern("MANDATE_WORDS"), [
        "Yes, I'll donate $25 each month",     # the one that was missed
        "Donate monthly",
        "Subscribe and pay",
        "Set up AutoPay",
        "Pay now",                             # one-off
        "Transfer now",                        # one-off
    ])
    assert found["Yes, I'll donate $25 each month"] is True
    assert found["Donate monthly"] is True
    assert found["Subscribe and pay"] is True
    assert found["Set up AutoPay"] is True
    assert found["Pay now"] is False
    assert found["Transfer now"] is False


def test_an_icon_button_inside_a_payment_form_is_still_gated() -> None:
    """Plenty of real payment buttons carry an icon and no text. The rule that
    catches them — a submit inside a form that takes an amount — is asserted
    here against the shipped source rather than described in a comment."""
    source = CONTENT_JS.read_text(encoding="utf-8")
    assert 'const submits = button.type === "submit"' in source
    assert "!(submits && !label.trim())" in source
