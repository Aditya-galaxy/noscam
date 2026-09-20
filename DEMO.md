# Running the demo

Three terminals, then five scenes. Nothing here touches a real bank, a real
messaging account or a real payment.

## Start

```bash
python3 -m uvicorn service.app:app --port 8787   # the gate
python3 demo/serve.py                             # stand-in messenger + bank
python3 demo/seed.py                              # limits, payees, clean slate
```

`demo/seed.py` can be re-run between takes: it clears holds and today's
spending, and keeps the limits and payees.

For the advice line, start the service with `GEMINI_API_KEY` set. Without it,
everything still runs and the deterministic sentence shows instead.

Open the phone app on a second screen (or a phone on the same Wi-Fi):
**http://localhost:8787/app/**

## Scene 1 — the scam is stopped (0:50)

1. Open **http://localhost:8790** — the message from "SBI Bank Security".
2. Click the payment link. The fake "safe account" page opens.
3. Press **Transfer now**.

The card appears: *"You're about to send ₹18,000 to RBI Safe Custody A/C, who
you've never paid before — and you arrived here from Messages 8 seconds ago.
Nothing has been sent yet."* A moment later, the advice line.

Say out loud: the page is convincing, the urgency is real, and none of that
mattered — what mattered is that a message is what sent them here.

## Scene 1b — the page gives itself away (1:20)

Open the fake bank link again from the message. Before anything is typed, the
page is called out on arrival: *"This page is pretending to be someone else."*
On the phone it appears as **stopped for them** — with no approve button,
because a refusal is not a request.

## Scene 2 — the second device (1:40)

1. Press **Ask Priya to approve**.
2. On the phone, the request is waiting, with the amount, the site and how they
   got there. Press **Yes, allow** — or **No, stop it**.
3. The desktop card changes to **Continue**.

Say out loud: the voice on the phone can clone a relative and spoof a number.
It cannot press this button.

## Scene 3 — ordinary life is not obstructed (2:30)

1. Open **http://localhost:8791** directly — the person's own bank.
2. Pay **Landlord** ₹2,000. It goes straight through.

Say out loud: this is the half that decides whether anyone keeps it installed.

## Scene 4 — the other ways money leaves (3:00)

Pick two or three; they are fast, and the point is that a scam only has to find
one channel.

- **Gift cards**: back in the message, click the gift-card link and press *Buy
  gift card* → **"Nobody legitimate is ever paid in gift cards."** No tax
  office, bank, police force or utility takes payment this way.
- **Install**: click `sbi-support.apk`. With the extension loaded, the download
  is cancelled before it lands.
- **Identity numbers**: type a card or Aadhaar number into the fake page →
  refused, with the line that matters: unlike a password, you cannot change it
  afterwards. The number itself never leaves the page — only the *kind* is sent
  to the local service.
- **UPI collect request**: on the phone, paste
  `upi://pay?pa=refund.dept@okaxis&pn=HDFC%20Bank%20Refund&am=` →
  *"Approving this sends money from your account. Receiving money on UPI never
  needs your approval or your PIN."* Plus: the amount is blank, so the sender
  decides how much; and it says HDFC Bank while the money goes to an Axis
  handle.
- **Link check**: paste `https://hdfcbank.secure-verify.example/login` →
  *"The name 'hdfcbank' appears in the address, but the real site is
  'secure-verify.example'."* → **Report this site** blocks it for the household.

## Scene 5 — the numbers and the limits (3:40)

```bash
python3 eval/score.py
```

Read the scorecard, including the four cases it slowed down. Then say what it does not
do: no OS-level protection on a phone, no help once a machine is compromised,
and an override that a determined person can always press.

## With the extension loaded

`chrome://extensions` → Developer mode → **Load unpacked** → `extension/`.
The difference: real provenance from the browser rather than the referrer, and
downloads actually cancelled. The demo pages work either way.
