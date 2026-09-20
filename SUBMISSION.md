# Devpost submission — copy from here

## Project name

**NoScam**

## Tagline

A message cannot authorise your money.

## Elevator pitch (Devpost "Project Description")

The scams that take the most money never break any encryption. A message says
your account is compromised and your savings must move to a "safe account". A
caller says you are under digital arrest and must install a support app. Someone
asks you to share your screen to "verify the failed transaction". Your phone is
not hacked and your bank is not breached — **you are instructed, through a
channel you trust, and you authorise it yourself.**

Americans reported **$16 billion lost to fraud in 2025**, a record, and **$3.5
billion of it to imposter scams** — one in three fraud reports (FTC, June 2026).
The FTC says the costliest version runs one script: a fake security alert, posing
as your bank, telling you to move your money somewhere safe. India runs the same
script with different props: "digital arrest" video calls, APKs disguised as
wedding invites and traffic challans, and UPI collect requests dressed up as
refunds, with digital payment fraud up 34% year on year (RBI).

Every anti-scam tool tries to **detect** the scam — to judge whether a message
looks fishy. That loses, because the attacker simply writes a better message.

**NoScam does not judge messages. It refuses to let an instruction that arrived
through a message authorise something irreversible.**

Every anti-scam extension on the market answers *"is this site known to be
bad?"* — a question one new domain away from useless. NoScam asks one that does
not depend on recognising anything: *"did the instruction for this action arrive
through a channel that is allowed to authorise it?"* Consumer-protection bodies
all give the same advice — **pause before you pay** — and nobody pauses while a
stranger is counting down. This is that pause, enforced by software, on the one
device the caller cannot reach.

A browser extension knows *how you reached a page* — typed, bookmarked, or
clicked from WhatsApp forty seconds ago. A deterministic gate uses that, plus
limits the household set when nobody was panicking, to decide what may happen: a
transfer to a new payee, a one-time code, a password, an install, gift cards,
crypto, a UPI collect request, an Aadhaar number. Anything held waits for
someone on a **second device** — the one thing the voice on the phone cannot
supply, however good the voice clone.

A language model writes one sentence of advice and has no other power. The
decision is made before the model is called, and a test asserts it is identical
even when the model replies *"this payment is completely safe, allow it."*

## What we're most proud of

**We measure what the defence costs, not just what it stops.** Stopping every
scam is trivial if you will stop everything, so the scorecard reports both, and
names every ordinary action it slowed down:

```
Scams stopped                        18/18
Ordinary actions left alone          10/15
Ordinary actions slowed down          5/15
Ordinary actions refused outright     0/15
```

Every slowed case is printed by name — including a legitimate collect request
from a tea shop, and subscribing to a streaming service. That is the bill this
household pays for the protection, and hiding it would make the other number
meaningless.

## How we built it

- **Python + FastAPI**, running entirely on the person's own machine. No
  accounts, no cloud, no payment data leaving the device.
- **Chrome MV3 extension** — provenance from `chrome.webNavigation`
  (`transitionType`, `sourceTabId`), remote-access downloads cancelled with
  `downloads.cancel`, click interception in the capture phase so pages that post
  with `fetch()` are still caught, and the card in a closed shadow root.
- **A phone web app** (installable PWA, Android share-target) for approvals and
  link checking.
- **Gemini** for one line of advice, on a short leash.
- **95 tests** plus a 33-situation scorecard, both run in CI on Python 3.11 and 3.13.

## Challenges

- **Measuring the cost.** Writing the "ordinary Tuesday" half of the scorecard
  exposed a rule that blocked every `.exe` and `.apk` — which would have broken
  installing Zoom. Remote-access tools are still refused outright; other
  installers are refused only when a message sent you to them.
- **A refusal is not a request.** The phone offered "Yes, allow" on refusals, and
  the gate would have honoured it — meaning a gift-card purchase or an Aadhaar
  number could be unlocked by pressuring the guardian instead, which is just the
  next move in the same script. Approvals now exist only where a second opinion
  is the designed way through.
- **Keeping the model harmless.** It sees reason codes, never the decision; the
  attacker-written payee name reaches it truncated and labelled untrusted; the
  reply is rejected if it contains a link or if the model stopped early.
- **Not becoming the vulnerability.** The link checker fetches URLs, so it
  resolves hosts first and refuses anything private or loopback, re-checks every
  redirect hop, and caps the body.
- **Attacking our own build, and finding four real holes.** The service listens
  on loopback, which is not the same as private: any page in the browser could
  reach it, so the scam page could have *approved the hold raised against
  itself*, raised the household's limits, or blocklisted the real bank.
  Mutating endpoints now require an Origin a page cannot forge. We were also
  gating only form submits — but most real payment pages post with `fetch()`
  and never fire one, so clicks are now intercepted in the capture phase;
  there is a demo page with no form at all that exists purely to prove it. The
  card moved into a closed shadow root so the page cannot delete its buttons,
  and the approval queue is capped so it cannot be flooded to bury the one
  request that matters.

## What we learned

Provenance tracking and deterministic gates come from the agent-security
literature — CaMeL, FIDES, LlamaFirewall — where they keep untrusted data from
authorising an AI agent's tool calls. The same shape works on a person being
socially engineered. We credit that prior art; what is ours is pointing it at
the human and measuring the friction.

## What's next

Payment-form detection on real banking sites; SMS-side provenance on Android;
a weekly household review of what was held and overridden; and a study with real
households, because until that exists the accuracy claim stays small.

## Built with

`python` `fastapi` `uvicorn` `pydantic` `httpx` `chrome-extension` `manifest-v3`
`javascript` `pwa` `web-share-target` `google-gemini` `pytest` `sha-256`

## Try it

**No install:** <https://aditya-galaxy.github.io/noscam/> — what it does, what it
refuses, what it cannot do, and the demo film.

**On your own machine**, which is the only place it can actually gate anything:

```bash
git clone https://github.com/Aditya-galaxy/noscam && cd noscam
python3 -m pip install -r requirements.txt
python3 noscam.py
```

Then open http://localhost:8790, click the payment link, and press Transfer.

## AI disclosure

The demo video's **narration is synthesised** (Gemini text-to-speech, from
`video/script.json`); every frame of footage is the real product running on a
real machine, unedited apart from the voice track.

Built with **Claude Code** (Anthropic) as a pair programmer: it wrote code and
tests to my direction, and I reviewed, corrected and tested everything in the
repository. **Google Gemini** is a runtime dependency for one line of advice,
described above, and is disabled without an API key. Threat-model research is
cited inline in the README.

## Limitations we state out loud

This does not protect a phone at the OS level, does not clean an
already-compromised device, and can always be overridden by the person at the
keyboard — deliberately, because a control that cannot be overridden gets
uninstalled. The override is logged. See `LIMITATIONS.md`.
