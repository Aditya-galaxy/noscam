# What NoScam does not do

Written before the demo video, so that nothing in the video is a surprise.

## It does not intercept the tap on a phone

There are three levels of protection on a phone, and NoScam is at the first two:

| | What it does | Here? |
|---|---|---|
| **Paste a link** | check it before you tap | **yes**, any phone, no setup |
| **Share → NoScam** | two taps from inside WhatsApp | **yes** on Android Chrome, once added to the home screen — the app registers as a Web Share Target |
| **Intercept the tap itself** | Android offers NoScam when any link is tapped | **no** |

The third needs a native app. On Android it is small and entirely standard: an
activity with an `intent-filter` for `http`/`https` `VIEW` intents, so tapping a
link in any app offers NoScam alongside Chrome. NoScam runs the same gate,
then either hands the URL to the browser or refuses it. That app would also be
the place for SMS-side provenance and for cancelling an install — the two things
a web app fundamentally cannot see.

On **iOS there is no equivalent**. Apple does not let an app join the Share menu
as a link target or intercept a tap; the closest is a Safari Web Extension,
which runs our content script inside Safari only and requires Xcode and App
Store review. So on iPhone, pasting stays the way in, and the phone's real job
is being the second device that approves.

Two other device-wide options we have deliberately *not* taken:

- **An accessibility service** could read every screen and stop anything. It is
  also precisely the permission the scam apps ask for, and teaching people to
  grant it is teaching them the habit that gets them robbed.
- **A VPN or Private DNS filter** would block reported hosts on the whole device
  with no app at all, but it needs a hosted resolver and a domain, and it can
  only block by hostname — it cannot see a payment about to happen.

Neither is built. Both are honest roadmap, not claims.

A web app also cannot read your SMS, which is why a link that arrives by text
and is typed in by hand looks clean to the gate.

## A hostile page is a different problem from a mistake

This distinction decides what NoScam can honestly claim, so it is worth being
exact about.

**Against a cooperative page — which is every real bank, every real payment
form, and the case that actually matters —** the gate holds. The extension sees
the click before the page does, the payment does not leave, and the person gets
a sentence they can check. We tested this against a page with *no form and no
submit event*, posting with `fetch()` the way real banking sites do, and the
payment was stopped.

**Against a page that is actively fighting the extension**, a content script is
not a sandbox. The page can render its own fake "NoScam" card, or remove ours
from the DOM. Some of that we have closed — the card lives in a **closed** shadow
root, so the page cannot read it, delete its buttons or dispatch a click on
"Continue anyway" — but a page that controls its own JavaScript can always find
some way to send its own request.

That is less damaging than it sounds, because the hostile page is not the bank.
When the money actually moves, it moves on the person's *real* banking site,
which is cooperative. What the hostile page can do is collect a password, an OTP
or a card number — and those are refused earlier, on arrival and at the field,
before the page is asked to co-operate with anything.

## What we hardened after attacking our own build

- **A web page could drive the local service.** It listens on loopback, which is
  not the same as being private: every page in the browser can reach it. Before
  this, a scam page could approve the hold raised against itself, raise the
  household's limits, add itself as a known payee, blocklist the real bank, or
  read what you have spent today. Mutating endpoints now require a trusted
  Origin — the extension, or the phone app this service serves — which a page
  cannot forge. Checking an action and overriding your own hold stay open,
  because neither lets a page do anything it could not do by simply proceeding.
- **Only form submits were gated**, so any page posting with `fetch()` — most
  real payment pages — went straight through. Clicks are now gated in the
  capture phase, before the page's own handler runs.
- **The card was readable by the page**, in an open shadow root. It is closed now.
- **The approval queue could be flooded** to bury the one request that mattered.
  It is capped; past the cap the gate still refuses, it just stops queueing.

## It does not clean a machine that is already compromised

If remote-control software is already running, or an APK is already installed
with SMS permissions, the attacker is inside and NoScam is irrelevant. It is a
control on the moment *before* that happens.

## It can always be overridden

Every hold has "I'm sure, continue anyway". This is deliberate. A person who
cannot get past a control will uninstall the control, and then they are
protected by nothing at all. The override is logged, in a chain that cannot be
quietly edited, and shows up when someone reviews what happened.

A person under sustained pressure from a convincing caller *can* be talked into
pressing it. The design answer is that an approval on a second device cannot be
pressed by the caller, and the audit trail makes the override visible
afterwards. Neither is the same as making it impossible.

## The link checker visits the site from your computer

Checking a link means fetching it, from your machine, so the site learns your IP
address and that someone looked — the same as opening it, minus your cookies and
minus any JavaScript running. It is hardened against being turned into a way
into your own network (hosts resolved and refused if private or loopback, every
redirect hop re-checked, bodies capped), but it is not anonymous, and the phone
app should not imply that it is.

## Provenance has holes

- A link that arrives by **SMS** and is typed into a desktop browser by hand
  looks clean. The browser cannot see the SMS. This is why the phone-side link
  check exists.
- Taint expires after 15 minutes. A patient attacker who waits out the window
  gets a smaller set of controls: the caps, the new-payee wait, and the
  remote-access refusal still apply, but the "you arrived here from a message"
  reason does not.
- Outside the extension — in the hosted demo — provenance is reconstructed from
  the referrer, which a page can withhold. That mode exists so judges can try it
  without installing anything, not because it is as good.

## The link checker is signals, not truth

"Nothing obviously wrong" is not "safe". A brand-new domain with a clean address
and no password field will produce no signals and still be a scam. The checker
says what it found, names each finding, and refuses to give a score that would
imply more confidence than it has.

## The scorecard is twenty situations, not a study

They were written by the same person who wrote the rules, which is the weakest
possible form of evaluation and is the reason the ordinary half exists and the
delayed cases are printed by name. It is a regression test. A real number needs
real households, over months, with the friction measured on people who did not
choose to be in a demo.

## The mechanism is not novel

Provenance tracking and deterministic gates on untrusted-derived actions come
from the agent-security literature (CaMeL, FIDES, LlamaFirewall). The
contribution here is applying it to a person being socially engineered, and
reporting what it costs them when it is wrong.

## Not tested in a real bank

The demo runs against stand-in pages, deliberately. NoScam detects payment forms
by their shape, and real banking sites vary enormously — several use iframes,
custom widgets or canvas rendering that the current detector would miss
entirely. Making this work on the top twenty banking sites in one country is a
week of unglamorous work that has not been done.
