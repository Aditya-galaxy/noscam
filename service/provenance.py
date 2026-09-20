"""
Where did this action come from?

The scam chain always starts in a channel the victim trusts — a WhatsApp message,
an email, an SMS — and ends on a page that looks like a bank. Nothing about the
page is unusual; what is unusual is *how the person got there*. NoScam records
that, the way an agent framework records which of its inputs came from untrusted
data, and the gate refuses to let an instruction that arrived through a messaging
app authorize an irreversible action.

Two deliberate limits, stated here because they shape the product:

  * A link that arrives by SMS and is typed into a desktop browser by hand looks
    "clean" here. That is the honest answer: the browser cannot see the SMS. The
    phone-side link checker exists for exactly that gap.
  * Taint decays. Someone who clicked a link twenty minutes ago and has been
    reading since is not mid-scam, and a system that treats them as though they
    were will be turned off. Fifteen minutes is the window the scam script
    actually operates in: urgency is the scammer's core tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

# How long a click from a messaging app keeps colouring what follows.
TAINT_TTL = timedelta(minutes=15)

# Hosts whose links are, for this purpose, instructions from someone else.
# Webmail and messengers only: these are where the scam script is delivered.
# A link from a search engine or a news site is not the same thing, and
# treating it as such would make the product unusable.
MESSAGING_HOSTS: frozenset[str] = frozenset({
    "web.whatsapp.com",
    "web.telegram.org",
    "messenger.com",
    "www.messenger.com",
    "mail.google.com",
    "outlook.live.com",
    "outlook.office.com",
    "outlook.office365.com",
    "mail.yahoo.com",
    "mail.proton.me",
    "web.skype.com",
    "discord.com",
    # The local stand-in used in the demo and the eval, so the same code path
    # is exercised there as in real life.
    "localhost:8790",
    "127.0.0.1:8790",
})


class Origin(str, Enum):
    """How the browser says this navigation started."""

    TYPED = "typed"          # the person typed the address themselves
    BOOKMARK = "bookmark"    # their own saved bookmark
    LINK = "link"            # they clicked something
    UNKNOWN = "unknown"      # no navigation record (fresh install, restored tab)


@dataclass(frozen=True)
class Provenance:
    """How the current page was reached, as the extension observed it."""

    origin: Origin = Origin.UNKNOWN
    source_host: Optional[str] = None   # the tab the link was clicked in
    at: Optional[datetime] = None       # when that navigation happened

    def age(self, now: datetime) -> Optional[timedelta]:
        return None if self.at is None else now - self.at

    def is_tainted(self, now: datetime, ttl: timedelta = TAINT_TTL) -> bool:
        """True when this page was reached by clicking a link in a messaging or
        webmail app, recently enough that the message is still driving."""
        if self.origin is not Origin.LINK or not self.source_host:
            return False
        if normalize_host(self.source_host) not in MESSAGING_HOSTS:
            return False
        age = self.age(now)
        return age is not None and timedelta(0) <= age <= ttl

    def describe(self, now: datetime) -> str:
        """The phrase the person reads on the block screen. Plain, specific and
        checkable against their own memory — 'you arrived here from WhatsApp 40
        seconds ago' is something they can verify, unlike a risk score."""
        if not self.is_tainted(now):
            return "you opened this page yourself"
        age = self.age(now) or timedelta(0)
        seconds = int(age.total_seconds())
        if seconds < 60:
            when = "1 second ago" if seconds == 1 else f"{seconds} seconds ago"
        else:
            minutes = seconds // 60
            when = "1 minute ago" if minutes == 1 else f"{minutes} minutes ago"
        return f"you arrived here from {pretty_source(self.source_host or '')} {when}"


def normalize_host(host_or_url: str) -> str:
    """Accept a bare host or a full URL; return a lowercase host[:port]."""
    value = (host_or_url or "").strip().lower()
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc
    return value.removeprefix("www.") if value.startswith("www.") and value != "www.messenger.com" else value


_PRETTY = {
    "web.whatsapp.com": "WhatsApp",
    "web.telegram.org": "Telegram",
    "messenger.com": "Messenger",
    "www.messenger.com": "Messenger",
    "mail.google.com": "Gmail",
    "outlook.live.com": "Outlook",
    "outlook.office.com": "Outlook",
    "outlook.office365.com": "Outlook",
    "mail.yahoo.com": "Yahoo Mail",
    "mail.proton.me": "Proton Mail",
    "web.skype.com": "Skype",
    "discord.com": "Discord",
    "localhost:8790": "Messages",
    "127.0.0.1:8790": "Messages",
}


def pretty_source(host: str) -> str:
    """'web.whatsapp.com' -> 'WhatsApp'. The person never sees a hostname."""
    return _PRETTY.get(normalize_host(host), normalize_host(host) or "another app")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
