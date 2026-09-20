# What NoScam does not do

Written before the demo video, so that nothing in the video is a surprise.

## It does not protect a phone at the OS level

A web app cannot read your SMS, cannot stop an APK from installing, and cannot
see what another app is doing. On a phone, NoScam does two honest things: it
checks a link you paste or share with it, and it is the second device that has
to approve something happening on the computer. Anything more would need a
native app with accessibility permissions — which is, incidentally, exactly what
the scam apps ask for.

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
