# Microsoft Store submission (Windows app)

The Store build is an **MSIX package**, made by `scripts/build_msix.py` from the
same PyInstaller app as the `.exe` installer. Two reasons it is worth doing:

- **The Store signs MSIX packages itself** after certification, so no
  code-signing certificate is needed and Store installs never meet a
  SmartScreen warning.
- **Individual developer accounts are free** (no fee since September 2025).

The browser extension is a separate listing on **Edge Add-ons**
(`dist/noscam-extension-chrome.zip`, same answers as `docs/CWS_SUBMISSION.md`).

## What the Store build does differently

| | `.exe` installer (GitHub) | Store (MSIX) |
|---|---|---|
| Start at login | Run registry key, installer checkbox | Startup task in the manifest; the person turns it off in Settings → Apps → Startup |
| Updates | Daily check, "newer version" notice | The Store updates it; the GitHub check is switched off |
| Opens the browser | Every manual start | Only on the very first run (setup) and when clicked while already running — never at login |
| Terminal | — | `noscam --demo` works (app execution alias) |
| Household data | `%APPDATA%\NoScam` | Same path, which Windows keeps inside the package; removed on uninstall |

All of this is detected at run time (`paths.is_store_package()`); there is one codebase.

## 1. Developer account (once)

1. Go to **storedeveloper.microsoft.com** and choose **Individual developer (free)**.
   Signing up through Partner Center directly can still show the old paid flow.
2. Verify with a government ID and a selfie. Approval is usually quick.

## 2. Reserve the name and copy the identity

1. Partner Center → **Apps and games → New product → MSIX or PWA app** → reserve
   **NoScam** (if it is taken: *NoScam Guard* or *NoScam – Scam Shield*).
2. Open the app → **Product management → Product identity**. Copy three values
   into GitHub repository **variables** (not secrets — they are public in the
   package anyway):

   ```bash
   gh variable set MSIX_IDENTITY_NAME --body "<Package/Identity/Name>"
   gh variable set MSIX_PUBLISHER --body "<Package/Identity/Publisher, starts with CN=>"
   gh variable set MSIX_PUBLISHER_DISPLAY_NAME --body "<Package/Properties/PublisherDisplayName>"
   ```

   The upload is rejected if any of these differ by a character.

## 3. Build the package

Run the release workflow (a `v*` tag, or **Actions → release → Run workflow**).
The Windows job uploads an artifact named **noscam-msix** containing
`NoScam-<version>-x64.msix`. It is deliberately unsigned; the Store signs it.

Each new submission needs a higher version (`service/__init__.py`); the
package version is that plus `.0`, since the Store reserves the fourth part.

## 4. Test it on a Windows PC before uploading (recommended)

An unsigned MSIX will not install, so sign a copy with a throwaway certificate
whose subject is exactly `MSIX_PUBLISHER`. In PowerShell, as yourself:

```powershell
$pub = "CN=<same as MSIX_PUBLISHER>"
$cert = New-SelfSignedCertificate -Type Custom -Subject $pub -KeyUsage DigitalSignature `
  -FriendlyName "NoScam test" -CertStoreLocation "Cert:\CurrentUser\My" `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
$pwd = ConvertTo-SecureString -String "test" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath noscam-test.pfx -Password $pwd
# Trust it (admin PowerShell): Import-PfxCertificate -FilePath noscam-test.pfx -CertStoreLocation Cert:\LocalMachine\TrustedPeople -Password $pwd
$env:MSIX_PFX = "noscam-test.pfx"; $env:MSIX_PFX_PASSWORD = "test"
python scripts/build_desktop.py; python scripts/build_msix.py
```

Then double-click the `.msix`, and check:

- [ ] The first launch opens the setup page; the tray icon appears.
- [ ] Sign out and in: NoScam starts with no browser window, tray icon present.
- [ ] Clicking NoScam in Start while it runs opens the app page.
- [ ] `noscam --demo` from a terminal starts the demo; a payment is held.
- [ ] Settings → Apps → Startup lists NoScam and can turn it off.
- [ ] Uninstall removes it cleanly.

This whole checklist except the sign-in step is automated: the
**windows-smoke** workflow installs the package on a Windows runner, runs 14
checks and the certification kit, and uploads a test-signed copy.

Optional but worth it: run the **Windows App Certification Kit** (installed with
the Windows SDK) against the package — it is the same automated test the Store runs.

Do **not** upload the test-signed copy; upload the unsigned artifact.

## 5. The submission

**Pricing and availability:** Free · all markets · public.

**Properties**
- Category: **Security** (subcategory none) — or *Utilities & tools*.
- Privacy policy URL: `https://aditya-galaxy.github.io/noscam/privacy.html`
- Website: `https://aditya-galaxy.github.io/noscam/`
- Support contact: `https://github.com/Aditya-galaxy/noscam/issues`
- "This product accesses, collects or transmits personal information": **Yes**
  (it handles payment details locally, and the optional relay and advice line
  transmit some — all in the privacy policy).
- System requirements: Windows 10 1809 or later, x64.

**Age ratings (IARC questionnaire):** category *Utility/productivity*; answer
**No** to violence, sexual content, gambling, user interaction/sharing and
location sharing. Expect a 3+ / Everyone rating.

**Packages:** upload `NoScam-<version>-x64.msix`.

**Store listing (English)**

- *Product name:* NoScam
- *Short description:*
  > Stops scam messages from authorising payments, one-time codes and remote-control installs.
- *Description:*
  > Scams that take the most money don't hack anything. A message says your
  > account is compromised, a caller says you are under "digital arrest", someone
  > needs you to install a support app — and you do it yourself.
  >
  > NoScam notices how you got to a page. If you arrived from a link in WhatsApp,
  > Telegram, email or SMS, it holds the things that cannot be undone — a payment
  > to someone new, a one-time code, a password, a gift card, crypto, a UPI
  > request, a remote-control download — and explains in one sentence why. A
  > held payment can wait for someone you trust to approve it on their phone.
  > You can always continue; it is a pause, not a lock.
  >
  > Runs on this PC. There is no account, and nothing about your money leaves it.
  > Add the free NoScam extension for Edge or Chrome so it can see the pages you
  > open. Open source.
- *What's new in this version:* First Microsoft Store release.
- *Product features* (one per line):
  > Holds payments, codes and passwords reached from a message
  > Refuses remote-control installs like AnyDesk during a scam call
  > Second-device approval the caller cannot press
  > Checks links: lookalike domains, fake UPI requests and AutoPay mandates
  > Tamper-evident history of everything it stopped
  > Runs locally — no account, no cloud
- *Screenshots (desktop, 1366×768 or larger):* `docs/store/windows-1.png`,
  `docs/store/windows-2.png` (1440×900).
- *Search terms (up to 7):* scam, fraud, phishing, UPI, digital arrest, OTP, security
- *Copyright:* © 2026 Aditya Kumar

**Submission options → Notes for certification:**

> NoScam is a local anti-fraud service with a tray icon. On first launch it opens
> its setup page at http://127.0.0.1:8787/app/ in the default browser; after that
> it runs from the tray and starts at login (startup task, user-controllable in
> Settings > Apps > Startup). To see it stop a scam, quit it from the tray, then
> run `noscam --demo` in a terminal: a stand-in messenger opens; click the link
> in the message and press "Transfer now" — the payment is held. The demo pages
> are local stand-ins and move no money. Full protection in other sites needs the
> NoScam browser extension (separate Edge Add-ons listing), which is not required
> for the app to function.
>
> Windows App Certification Kit: all required tests pass. The optional "Blocked
> executables" test reports string matches such as "cmd" inside the bundled
> Python runtime and OpenSSL libraries (python312.dll, ucrtbase.dll,
> libcrypto-3.dll); the app does not launch cmd, PowerShell or reg.

**Restricted capability justification (runFullTrust):**

> NoScam is a desktop (Win32) application packaged with the Desktop Bridge. It
> runs a local loopback service that the user's browser extension queries, shows
> a system-tray icon, and opens its settings page in the user's browser. These
> require full trust; it uses no other restricted capability.

## After submitting

Certification usually takes 1–3 business days. Common rejection reasons for this
kind of app, and the answer already in place: *app doesn't launch visibly*
(first run opens setup; later starts show the tray icon), *privacy policy
missing* (linked above), *startup without consent* (Store-disclosed startup task,
user-controllable).
