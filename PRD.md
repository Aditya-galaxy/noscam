# NoScam — product requirements

## The problem

Authorised-push-payment fraud is the largest and fastest-growing category of
consumer loss, and it is invisible to every control a bank has, because the
customer performs the transaction themselves after being instructed to.

- **$16B** reported lost to fraud in the US in 2025, a record; **$3.5B** to
  imposter scams, one in three fraud reports (FTC, June 2026).
- The costliest single script: a fake security alert, posing as the bank, that
  instructs the victim to move money to a "safe account".
- India: "digital arrest" calls, APKs disguised as wedding invites and traffic
  challans, and screen-sharing "verification" — RBI reports digital payment
  fraud up **34% year on year**.
- **$2.3B** taken from elderly Americans by AI voice cloning in 2026; a voice
  clones from three seconds of audio, so *hearing a familiar voice is no longer
  evidence of who is calling*.

The common structure: an instruction arrives through a trusted channel, urgency
suppresses verification, and the victim authorises an irreversible action —
a transfer, a one-time code, an install, a remote session.

## Who this is for

| | Who | What they need |
|---|---|---|
| **Primary** | The person on the call — often, though not only, an older parent, a first-time digital-payments user, someone alone at the moment of pressure. | To be stopped for long enough to check, without being made to feel stupid. |
| **Secondary** | The guardian — adult child, spouse, carer. | To be asked at the moment it matters, on their own device, with enough context to answer in ten seconds. |

## What it must do

1. **Recognise the small set of irreversible actions**: a payment (and whether
   the payee is new), a one-time code, a password, an install, a remote-access
   tool.
2. **Know how the person got there**: typed, bookmarked, or clicked from a
   messaging or webmail app, and how long ago.
3. **Decide deterministically.** No model input. Four outcomes: allow, wait,
   ask someone else, refuse.
4. **Explain in language the person can check** against their own memory, and
   never accuse them of anything.
5. **Ask a second device** for the cases that warrant it, bound to that one
   action, expiring in minutes.
6. **Always be overridable**, and record every override in a log that cannot be
   quietly edited.
7. **Check a link on demand** and name every reason, with reports shared across
   the household.
8. **Work with nothing configured**: no accounts, no cloud, no API key. State
   lives on the person's own machine.

## What it must not do

- Score a message for "scamminess" and decide from that. The attacker can
  rewrite the message; they cannot make the message stop being a message.
- Let a language model influence any decision.
- Send payment details, payees or limits anywhere.
- Block so much that the household turns it off — the measured cost of friction
  is a first-class number, not an afterthought.
- Claim protection it does not provide (see LIMITATIONS.md).

## How success is measured

| Metric | Today | Target |
|---|---|---|
| Scam scenarios stopped | 10/10 | stays 10/10 as rules change |
| Ordinary actions untouched | 8/10 | ≥ 8/10 |
| Ordinary actions wrongly stopped | 0/10 | 0 |
| Time from hold to guardian's answer | — | median under 60s in real use |
| Overrides per household per month | — | tracked; a rising number means the rules are wrong |

The last two need real households. Nothing in this repository has been used by
one yet, and the scorecard says so out loud.

## Scope for the hackathon build

**In:** the gate, provenance, household limits, out-of-band approval, the audit
chain, the link checker, the Chrome extension, the phone app, the stand-in
demo sites, the scorecard, the advice line.

**Out:** bank or UPI integration, OS-level phone protection, malware scanning,
accounts and multi-tenancy, real-site payment-form detection beyond the demo
pages, anything that clones or analyses a voice.

## What would come next

1. **Real-site coverage.** Payment-form detection across the top banking and
   UPI sites, which is unglamorous and necessary.
2. **SMS-side provenance on Android**, so a link that arrives by message is
   known to be a link that arrived by message.
3. **A household review**, weekly: what was held, what was overridden, what was
   reported — the artefact that makes the overrides meaningful.
4. **A study with real households**, measuring friction on people who did not
   choose to be in a demo. Until that exists, the accuracy claim stays small.
