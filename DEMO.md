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

## Scene 4 — the other two endings (3:00)

- **Install**: back in the message, click `sbi-support.apk`. With the extension
  loaded, the download is cancelled before it lands.
- **Link check**: on the phone, paste
  `https://hdfcbank.secure-verify.example/login` → *"The name 'hdfcbank'
  appears in the address, but the real site is 'secure-verify.example'. Those
  are different companies."* → **Report this site** blocks it for everyone in
  the household.

## Scene 5 — the numbers and the limits (3:40)

```bash
python3 eval/score.py
```

Read the scorecard, including the two delayed cases. Then say what it does not
do: no OS-level protection on a phone, no help once a machine is compromised,
and an override that a determined person can always press.

## With the extension loaded

`chrome://extensions` → Developer mode → **Load unpacked** → `extension/`.
The difference: real provenance from the browser rather than the referrer, and
downloads actually cancelled. The demo pages work either way.
