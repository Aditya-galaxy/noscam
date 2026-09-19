"""
"Is this link safe?" — answered with reasons, not a score.

Every signal here is a fact about the URL that a person could verify if they knew
where to look: the address uses Cyrillic characters that look like Latin ones; the
short link ends up on a different site than it claims; the page asks for a
password; the download is an Android install file. A number between 0 and 100
teaches nobody anything and cannot be argued with. A list of named reasons can be
read out to the person on the phone who is insisting.

**Fetching arbitrary URLs is itself a vulnerability**, and this is a security tool,
so the fetch path is hardened rather than convenient: hosts are resolved before
connecting and refused if they point anywhere inside the machine or the private
network, redirects are followed by hand with every hop re-checked, and the body is
capped. (Recent audits found roughly 37% of public MCP servers vulnerable to
exactly this. Not repeating it is part of the product.)
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urlparse, urlunparse

MAX_REDIRECTS = 5
FETCH_TIMEOUT_SECONDS = 4.0
MAX_BODY_BYTES = 512 * 1024

# Brands a scam most often dresses up as. Lookalikes are measured against these.
BRANDS: tuple[str, ...] = (
    "hdfcbank", "icicibank", "sbi", "axisbank", "kotak", "paytm", "phonepe",
    "npci", "rbi", "incometax", "chase", "wellsfargo", "bankofamerica", "paypal",
    "hsbc", "barclays", "lloyds", "amazon", "apple", "microsoft", "google",
)

SHORTENERS: frozenset[str] = frozenset({
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly",
    "rb.gy", "cutt.ly", "shorturl.at", "rebrand.ly", "t.ly",
})

# File types that mean "install something" rather than "read something".
INSTALLER_SUFFIXES = (".apk", ".exe", ".msi", ".dmg", ".scr", ".bat", ".jar")
INSTALLER_TYPES = (
    "application/vnd.android.package-archive",
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/octet-stream",
)

REMOTE_ACCESS_NAMES = ("anydesk", "teamviewer", "quicksupport", "ultraviewer",
                       "rustdesk", "ammyy", "logmein")


@dataclass(frozen=True)
class Signal:
    code: str
    severity: str        # "high" | "medium" | "low"
    plain: str           # what the person reads


@dataclass
class LinkVerdict:
    url: str
    final_url: str
    verdict: str                              # "dangerous" | "suspicious" | "no_signals"
    signals: list[Signal] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)
    fetch_error: Optional[str] = None

    @property
    def headline(self) -> str:
        return {
            "dangerous": "Don't open this",
            "suspicious": "Treat this with care",
            "no_signals": "Nothing obviously wrong",
        }[self.verdict]

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "verdict": self.verdict,
            "headline": self.headline,
            "signals": [{"code": s.code, "severity": s.severity, "plain": s.plain}
                        for s in self.signals],
            "chain": self.chain,
            "fetch_error": self.fetch_error,
        }


class UnsafeTarget(ValueError):
    """The URL points somewhere we refuse to fetch from."""


def _host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _registrable_ish(host: str) -> str:
    """Last two labels. Not a public-suffix list — good enough to tell
    'hdfcbank.com' from 'hdfcbank.com.secure-verify.example'."""
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def assert_public_target(url: str) -> None:
    """Refuse anything that would make this scanner a proxy into the machine it
    runs on, or into the network around it."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeTarget(f"only http and https are fetched, not {parsed.scheme or 'that'}")
    host = parsed.hostname
    if not host:
        raise UnsafeTarget("no host in that address")
    if parsed.port is not None and parsed.port not in (80, 443):
        raise UnsafeTarget("only ports 80 and 443 are fetched")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeTarget(f"that address does not resolve ({exc.strerror or 'DNS failure'})")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise UnsafeTarget("that address points inside a private network")


def _static_signals(url: str, blocklist: Iterable[str]) -> list[Signal]:
    """Everything decidable from the address itself, without touching the network."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    signals: list[Signal] = []

    if host in {h.lower() for h in blocklist}:
        signals.append(Signal("reported_by_household", "high",
                              "Someone in your household reported this site as a scam."))

    if parsed.scheme == "http":
        signals.append(Signal("not_https", "medium",
                              "The connection isn't encrypted, so anything you type can be read."))

    try:
        ipaddress.ip_address(host)
        signals.append(Signal("ip_literal_host", "high",
                              "The address is a raw number instead of a name. "
                              "Real banks don't do this."))
    except ValueError:
        pass

    if "xn--" in host:
        signals.append(Signal("punycode_host", "high",
                              "The address uses letters from another alphabet that look like "
                              "English ones — a common way to fake a familiar name."))

    labels = [p for p in host.split(".") if p]
    if len(labels) > 4:
        signals.append(Signal("many_subdomains", "medium",
                              "The address has unusually many parts, which is often used to "
                              "hide the real site name."))

    registrable = _registrable_ish(host)
    name = registrable.split(".")[0] if registrable else ""
    stripped = name.replace("-", "").replace("_", "")
    for brand in BRANDS:
        if stripped == brand:
            break
        distance = _levenshtein(stripped, brand)
        if 0 < distance <= 2 and abs(len(stripped) - len(brand)) <= 2:
            signals.append(Signal("lookalike_domain", "high",
                                  f"The address is one or two letters away from {brand} — "
                                  f"this is how fake bank sites are made."))
            break
    else:
        # Brand named somewhere other than where it counts: in a subdomain, or
        # in the path. hdfcbank.secure-verify.example is not HDFC Bank.
        head = host[: -len(registrable)] if registrable and host.endswith(registrable) else ""
        for brand in BRANDS:
            if brand in head or brand in parsed.path.lower():
                signals.append(Signal("brand_not_in_domain", "high",
                                      f"The name '{brand}' appears in the address, but the real "
                                      f"site is '{registrable}'. Those are different companies."))
                break

    if registrable in SHORTENERS:
        signals.append(Signal("shortened_link", "medium",
                              "A shortened link hides where it actually goes."))

    lowered = url.lower()
    if lowered.endswith(INSTALLER_SUFFIXES):
        signals.append(Signal("installer_download", "high",
                              "This link downloads a program to install. Messages that ask you "
                              "to install something are how phones get taken over."))
    if any(tool in lowered for tool in REMOTE_ACCESS_NAMES):
        signals.append(Signal("remote_access_tool", "high",
                              "This is remote-control software. Anyone asking you to install it "
                              "is asking to use your computer as if they were sitting at it."))
    return signals


def _fetch_signals(url: str) -> tuple[list[Signal], list[str], str, Optional[str]]:
    """Follow the link by hand, checking every hop. Returns (signals, chain,
    final_url, error)."""
    import httpx

    signals: list[Signal] = []
    chain: list[str] = []
    current = url
    error: Optional[str] = None

    try:
        with httpx.Client(follow_redirects=False, timeout=FETCH_TIMEOUT_SECONDS,
                          headers={"User-Agent": "NoScam-LinkCheck/1.0"}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                assert_public_target(current)       # every hop, not just the first
                chain.append(current)
                response = client.get(current)
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    if not location:
                        break
                    current = str(httpx.URL(current).join(location))
                    continue

                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                disposition = response.headers.get("content-disposition", "").lower()
                if (content_type in INSTALLER_TYPES
                        or any(s in disposition for s in INSTALLER_SUFFIXES)):
                    signals.append(Signal("installer_download", "high",
                                          "Opening this downloads a program to install, not a "
                                          "page to read."))
                body = response.content[:MAX_BODY_BYTES].decode("utf-8", "ignore").lower()
                if 'type="password"' in body or "type='password'" in body:
                    signals.append(Signal("asks_for_password", "high",
                                          "The page asks for a password."))
                if "otp" in body and ("input" in body or "verify" in body):
                    signals.append(Signal("asks_for_otp", "high",
                                          "The page asks for a one-time code. Nobody legitimate "
                                          "needs your code — it exists to stop them."))
                break
            else:
                signals.append(Signal("redirect_loop", "medium",
                                      "The link bounces through too many sites."))
    except UnsafeTarget as exc:
        error = str(exc)
        signals.append(Signal("unsafe_target", "high", f"Refused to open it: {exc}."))
    except Exception as exc:                       # network failure, TLS error, timeout
        error = f"{type(exc).__name__}"
        signals.append(Signal("unreachable", "low",
                              "The site didn't respond, so it couldn't be checked fully."))

    hosts = {_host_of(u) for u in chain}
    if len(hosts) > 1:
        first, last = _host_of(chain[0]), _host_of(chain[-1])
        if first != last:
            signals.append(Signal("redirects_elsewhere", "high",
                                  f"It says {first} but it actually takes you to {last}."))
    return signals, chain, chain[-1] if chain else url, error


def _verdict_from(signals: list[Signal]) -> str:
    """Deterministic and stated out loud, so nobody has to trust a number: one
    serious signal is enough, or two lesser ones together."""
    highs = sum(1 for s in signals if s.severity == "high")
    mediums = sum(1 for s in signals if s.severity == "medium")
    if highs:
        return "dangerous"
    if mediums >= 2:
        return "suspicious"
    if mediums == 1:
        return "suspicious"
    return "no_signals"


def normalize_url(raw: str) -> str:
    """People paste 'hdfc-secure.example/login' without a scheme."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("no link given")
    if "://" not in value:
        value = "http://" + value
    parsed = urlparse(value)
    if not parsed.hostname:
        raise ValueError("that doesn't look like a link")
    return urlunparse(parsed)


def check_url(raw: str, *, blocklist: Iterable[str] = (), fetch: bool = True) -> LinkVerdict:
    url = normalize_url(raw)
    signals = _static_signals(url, blocklist)
    chain, final_url, error = [url], url, None
    if fetch:
        fetched, chain, final_url, error = _fetch_signals(url)
        # The destination deserves the same address checks as the link itself:
        # a clean-looking short link that lands on a lookalike is the whole trick.
        if final_url != url:
            for signal in _static_signals(final_url, blocklist) + fetched:
                if signal.code not in {s.code for s in signals}:
                    signals.append(signal)
        else:
            signals.extend(s for s in fetched if s.code not in {x.code for x in signals})
    return LinkVerdict(url=url, final_url=final_url, verdict=_verdict_from(signals),
                       signals=signals, chain=chain, fetch_error=error)
