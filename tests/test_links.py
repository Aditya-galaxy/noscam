"""
The link checker: every signal, and every refusal to fetch.

The SSRF tests matter as much as the scam-detection ones. A "check this link"
service that will fetch anything is a way into the network it runs on, and
shipping that inside a security tool would be its own headline.
"""

from __future__ import annotations

import pytest

from service.links import (
    UnsafeTarget, assert_public_target, check_url, normalize_url,
)


def codes(raw: str, **kwargs) -> set[str]:
    return {s.code for s in check_url(raw, fetch=False, **kwargs).signals}


def test_a_lookalike_bank_domain_is_dangerous() -> None:
    verdict = check_url("https://hdfcbamk.com/login", fetch=False)
    assert "lookalike_domain" in {s.code for s in verdict.signals}
    assert verdict.verdict == "dangerous"


def test_a_brand_hidden_in_a_subdomain_is_named_for_what_it_is() -> None:
    verdict = check_url("https://hdfcbank.secure-verify.example/login", fetch=False)
    signal = next(s for s in verdict.signals if s.code == "brand_not_in_domain")
    # The explanation has to be usable out loud, to someone being pressured.
    assert "secure-verify.example" in signal.plain
    assert verdict.verdict == "dangerous"


def test_the_real_bank_domain_raises_nothing() -> None:
    assert codes("https://hdfcbank.com/netbanking") == set()


def test_punycode_is_flagged() -> None:
    assert "punycode_host" in codes("https://xn--hdfcbnk-w1a.com/login")


def test_a_raw_ip_address_is_flagged() -> None:
    assert "ip_literal_host" in codes("http://203.0.113.9/pay")


def test_an_apk_link_is_flagged_without_fetching() -> None:
    assert "installer_download" in codes("https://challan-pay.example/traffic-challan.apk")


def test_remote_access_software_is_named() -> None:
    assert "remote_access_tool" in codes("https://downloads.example/AnyDesk.exe")


def test_plain_http_is_a_medium_signal_not_a_verdict() -> None:
    verdict = check_url("http://example.com/page", fetch=False)
    assert {s.code for s in verdict.signals} == {"not_https"}
    assert verdict.verdict == "suspicious"


def test_a_household_report_is_enough_on_its_own() -> None:
    verdict = check_url("https://ordinary.example/pay", fetch=False,
                        blocklist=["ordinary.example"])
    assert verdict.verdict == "dangerous"
    assert "reported_by_household" in {s.code for s in verdict.signals}


def test_a_shortener_is_flagged_as_hiding_its_destination() -> None:
    assert "shortened_link" in codes("https://bit.ly/3xYz")


def test_links_without_a_scheme_are_understood() -> None:
    assert normalize_url("hdfc-secure.example/login").startswith("http://")
    with pytest.raises(ValueError):
        normalize_url("   ")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8787/limits",
    "http://localhost/admin",
    "http://169.254.169.254/latest/meta-data/",       # cloud credentials endpoint
    "http://10.0.0.5/router",
    "http://[::1]/",
])
def test_the_checker_refuses_to_reach_inside_the_network(url: str) -> None:
    with pytest.raises(UnsafeTarget):
        assert_public_target(url)


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "https://example.com:22/",
])
def test_only_ordinary_web_addresses_are_fetched(url: str) -> None:
    with pytest.raises(UnsafeTarget):
        assert_public_target(url)


def test_an_unsafe_target_is_reported_rather_than_fetched() -> None:
    """check_url must not raise at the person — it explains instead."""
    verdict = check_url("http://169.254.169.254/latest/meta-data/")
    assert verdict.verdict == "dangerous"
    assert "unsafe_target" in {s.code for s in verdict.signals}
    assert verdict.fetch_error


# --------------------------------------------------------------------------- #
# UPI collect requests: which way does the money actually go?
# --------------------------------------------------------------------------- #

def test_a_upi_request_is_explained_as_money_leaving() -> None:
    """The whole collect-request scam is the victim believing they are being
    paid. UPI has no flow where receiving needs your approval."""
    verdict = check_url("upi://pay?pa=plumber@oksbi&pn=Plumber&am=2200")
    assert verdict.kind == "upi"
    assert verdict.headline == "Check which way this money goes"
    plain = " ".join(s.plain for s in verdict.signals)
    assert "sends ₹2200 from your account" in plain
    assert "never needs your approval" in plain


def test_a_blank_amount_makes_a_upi_request_dangerous() -> None:
    verdict = check_url("upi://pay?pa=refund.dept@okaxis&pn=Refund&am=")
    assert verdict.verdict == "dangerous"
    assert verdict.headline == "Don't approve this"
    assert "upi_open_amount" in {s.code for s in verdict.signals}


def test_a_upi_request_claiming_to_be_a_bank_is_checked_against_the_handle() -> None:
    verdict = check_url("upi://pay?pa=refund.dept@okaxis&pn=HDFC%20Bank%20Refund&am=9500")
    signal = next(s for s in verdict.signals if s.code == "upi_payee_mismatch")
    assert "HDFC Bank" in signal.plain and "refund.dept@okaxis" in signal.plain


def test_an_ordinary_upi_payment_is_not_called_dangerous() -> None:
    """Paying someone on UPI is ordinary life; only a blank amount or a payee
    who isn't who they claim raises it."""
    assert check_url("upi://pay?pa=plumber@oksbi&pn=Plumber&am=2200").verdict == "suspicious"
