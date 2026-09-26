# Chrome Web Store submission

Everything the Developer Dashboard asks for, in the order it asks, ready to paste.
The same zip is accepted by Microsoft Edge Add-ons (free, no fee).

## Before you start

- A Google account with **2-Step Verification on** (the dashboard requires it).
- The one-time **$5 registration fee**, paid by you in the dashboard.
- The package: `python3 package.py` → `dist/noscam-extension-chrome.zip`.
- The images, made from the demo with the bank's real name removed:
  `docs/store/screenshot-1.png`, `docs/store/screenshot-2.png` (1280×800) and
  `docs/store/promo-small-440x280.png`.

## Account

- **Publisher name:** NoScam (or your own name).
- **Trader / non-trader declaration** (EU Digital Services Act): choose
  **non-trader** if you are publishing this free, personally and not as a
  business. A trader must publish a verified address and phone number.
- Verify the contact email.

## Package

**Add new item** → upload `noscam-extension-chrome.zip`. The name, version,
summary and icon come from `manifest.json` and cannot be edited in the
dashboard — change the manifest and re-upload instead.

## Store listing

- **Description:**

  > Scams that take the most money don't break anything. They get you to do it
  > yourself: a message says your account is compromised, a caller says you're
  > under "digital arrest", someone needs you to install a support app.
  >
  > NoScam notices *how you got to a page*. If you arrived by clicking a link in
  > WhatsApp, Telegram, Gmail or another messenger, it holds the things that
  > can't be undone — a payment to someone new, a one-time code, a password, a
  > gift card, crypto, a UPI collect request or AutoPay mandate, a remote-control
  > app — and explains in one plain sentence why: "you arrived here from WhatsApp
  > 40 seconds ago, and you've never paid this person before."
  >
  > A payment can wait for a second person to approve it on their phone. You can
  > always continue anyway; it's a pause, not a lock.
  >
  > Requires the free NoScam app on the same computer, which makes every
  > decision locally: https://github.com/Aditya-galaxy/noscam/releases/latest
  > Without it, the extension shows that it isn't protecting you yet.
  >
  > What it doesn't do: it doesn't read your passwords or card numbers, doesn't
  > send your browsing anywhere, and can't protect a phone or an already-infected
  > computer. Open source, MIT licensed.

- **Category:** Privacy & Security
- **Language:** English
- **Screenshots:** `docs/store/screenshot-1.png` (payment held), `docs/store/screenshot-2.png`
  (gift cards refused).
- **Small promo tile:** `docs/store/promo-small-440x280.png`
- **Official URL:** none. **Homepage URL:** `https://aditya-galaxy.github.io/noscam/`
- **Support URL:** `https://github.com/Aditya-galaxy/noscam/issues`

## Privacy practices

**Single purpose**

> Pauses irreversible actions — payments, one-time codes, passwords,
> remote-access installs — when the page was reached from a link in a message,
> and explains why, so a person being scammed gets a moment to stop.

**Permission justifications**

| Permission | Justification |
|---|---|
| Host access (content scripts on `http://*/*`, `https://*/*`) | Scam payment and login pages can be on any domain, including ones registered minutes ago, so the content script must run on every page to notice a payment, one-time-code or password field and hold it. It reads the kind of field and the payee name and amount on screen, never a password or code value. |
| Host access (`127.0.0.1:8787`) | The only server the extension talks to: the NoScam desktop app on the same computer, which makes every decision. |
| `webNavigation` | To know how a tab was reached — typed or bookmarked versus a link clicked in a messaging tab (`onCommitted` transition type, `onCreatedNavigationTarget` source tab). This is the whole basis of a decision. Kept in session storage and discarded when the tab closes. |
| `downloads` | To cancel remote-control installers (AnyDesk, TeamViewer, RustDesk, QuickSupport) and APKs downloaded right after a message link, which is how "support" scammers take over a computer. Uses `downloads.onCreated`, `cancel` and `erase` only. |
| `storage` | `storage.session` keeps each tab's navigation origin while the MV3 service worker is suspended. Nothing is stored persistently. |
| `alarms` | Checks once a minute whether the NoScam desktop app is running, so the toolbar icon can warn the person when they are not protected. |

**Remote code:** No, I am not using remote code. (All JavaScript is in the
package; nothing is fetched and evaluated.)

**Data usage.** Collection, for the Web Store, means data sent off the device.
The extension sends nothing off the device: it talks only to the desktop app on
`127.0.0.1`. Tick these anyway, because the desktop app's optional features can
send some of it, and over-disclosing is safer than a rejection:

- [x] **Financial and payment information** — payee name and amount shown on a
  payment page are passed to the local app. Only if the person turns on
  approval from another phone are held payments sent, end-to-end encrypted,
  through a relay.
- [x] **Website content** — the kind of form fields on a page.
- [ ] Personally identifiable information, health, authentication information,
  personal communications, location, web history, user activity — **not ticked**.
  Navigation origin is kept per tab in session memory and never leaves the
  computer.

Then tick all three certifications (not sold to third parties; not used for
unrelated purposes; not used for creditworthiness or lending).

**Privacy policy URL:** `https://aditya-galaxy.github.io/noscam/privacy.html`

## Distribution

- **Visibility:** Public (or Unlisted for a first round with testers).
- **Regions:** All.

## Notes for the reviewer

The extension does nothing on its own, which looks like a broken build unless
the reviewer is told. Paste this into **Test instructions**:

> NoScam is the companion to a free desktop app that makes every decision
> locally. Without the app, the toolbar icon shows "!" and the popup says
> "Not protecting you yet" — that is expected.
>
> To see it work (any OS with Python 3.11+):
>
>     pipx install git+https://github.com/Aditya-galaxy/noscam
>     noscam --demo
>
> (or the desktop app from https://github.com/Aditya-galaxy/noscam/releases/latest,
> started from a terminal with `--demo`). Then open http://localhost:8790 — a
> stand-in messenger — and click the link in the message. On the page it opens,
> press "Transfer now": the payment is held with an explanation. Typing the same
> bank address (http://localhost:8791) yourself and paying a known payee is not
> held. No real money or bank is involved.

## After submitting

Review usually takes a few days; extensions with host access to every site and
`downloads` can take longer. If it is rejected, the email names the policy —
usually a permission justification that needs to be more specific.
