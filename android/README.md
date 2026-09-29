# NoScam Android Companion App

Native Android companion application that intercepts links tapped inside messaging apps (WhatsApp, SMS, Telegram) before navigation occurs.

---

## 1. Why this exists

As documented in `LIMITATIONS.md`, a browser extension is powerless when a victim taps a scam link inside native WhatsApp or Messages on Android.

This native companion registers as a handler for `http` and `https` `VIEW` intents:
1. **Intercepts the tap**: When a user taps a link in WhatsApp or SMS, Android routes the link to NoScam.
2. **Evaluates link signals on-device**:
   - Deceptive APK downloads (`.apk`).
   - Raw IP addresses instead of domains.
   - Punycode lookalike characters (`xn--`).
   - Known brand names in untrusted subdomains.
   - UPI collect request links disguised as refunds.
3. **Displays a plain explanation**:
   - Safe links are immediately forwarded to Chrome with zero friction.
   - Deceptive links display a warning explaining the risk with a safe **Cancel** button.
4. **No dangerous permissions**:
   - Does **not** request Accessibility Services or SMS reading permissions. This protects users from learning the dangerous habit of granting screen-reading privileges that malware exploits.

### Device-wide DNS Guardian (`NoScamDnsVpnService`)

For apps that do not respect browser intent delegation (such as embedded webviews inside messaging apps), NoScam provides a **local DNS-only loopback service**:
- Uses Android's native `VpnService` to intercept UDP port 53 DNS queries *only*.
- Normal web, banking, and application traffic is **not** routed through any VPN server; only DNS resolution runs through the local TUN interface.
- Evaluates domains against `DnsFilter`:
  - **Sinkholes (0.0.0.0)** lookalike brand domains (`sbi-kyc.xyz`, `paypal-verify.click`), punycode (`xn--`), raw numeric IPs, and remote-access software (`anydesk.com`, `teamviewer.com`).
  - Forwards clean queries to upstream encrypted DNS (`1.1.1.1`).
- Completely on-device and zero-knowledge: no browsing or DNS queries are ever logged to an external cloud.

### App files sent in chats

Spy and bank-theft apps mostly arrive as **files** in a chat — "Posting
list.pdf.apk", "Army welfare", "Traffic challan", "Wedding invitation" — not as
links. NoScam registers for `application/vnd.android.package-archive`, so the
first time one is tapped Android asks which app should open it. Choose
**NoScam → Always**, and from then on an app file from a chat opens NoScam
instead of the installer. It says who sent it, reads the file's manifest to
list what the app could do (read SMS codes, read notifications, record,
draw over your bank), calls out names built to look like documents, and does
**not** pass the file on. The way through is the Play Store, and the screen
says so.

### Apps already on the phone

**Check the apps on this phone** lists apps that were installed outside an app
store *and* can take the phone over — active accessibility service,
notification reader, device administrator, SMS or call-log access, drawing over
other apps — plus remote-control apps from anywhere. On Android 11+ it knows
which app started the install, so it can say "installed from a file sent on
WhatsApp". A background job checks for new installs about every 30 minutes and
sends a notification when one of them looks like a takeover.

#### Apps that hide

Spy apps rarely hide by not existing; they hide by not being noticed. The
package manager lists every installed app whether it has an icon or not, so
the check compares that list with what the launcher shows and calls out:

* **no icon** — the app removed its own launcher entry after first run (a
  common "this app is not compatible and was removed" trick);
* **a name like part of the phone** — "System Update", "Wi-Fi Service",
  "Google Services" — on an app that did not come from a store;
* **a package name reserved for Android or Google** (`com.android.…`) on an app
  that did not come from a store, which is always impersonation;
* **starts at boot**, when combined with any of the above;
* **can pretend to be a contactless card** (the NGate / SuperCard X "tap your
  card on your phone" theft).

What it still cannot see: apps in a work profile or Android 15's Private
Space (another user, invisible to ordinary apps), and anything with root or
firmware-level access, which no app can inspect — that needs a forensic tool
such as Amnesty's MVT, or a factory reset.

The rules are in `AppRisk.kt`, plain Kotlin with unit tests
(`./gradlew testDebugUnitTest`).

### What it cannot do

* **Block an install outright.** Only a device-owner (MDM) app can forbid
  installs on Android; that is the right tool for issued devices and a
  possible later mode. Someone who picks the system installer in the chooser,
  or installs from a file manager, gets through — and the installed-app check
  then catches it, within about half an hour.
* **See everything without QUERY_ALL_PACKAGES.** Google Play allows it for apps
  whose core purpose is scanning installed apps for security; declare it so.
* NoScam still does not use an accessibility service. It is the permission the
  apps it hunts ask for.

---

## 2. Building the App

### Prerequisites
* Android Studio (Meerkat or newer) OR the Android SDK with platform 36, and JDK 17+.
* The Gradle wrapper is committed; `./gradlew` downloads the right Gradle itself.

### Build Debug APK
```bash
cd android
./gradlew assembleDebug
```
The output APK will be located at:
`android/app/build/outputs/apk/debug/app-debug.apk`

---

## 3. Installing on a Device

1. Connect your Android phone with USB debugging enabled.
2. Install via ADB:
```bash
adb install android/app/build/outputs/apk/debug/app-debug.apk
```
3. Open NoScam and press **Check every link I tap**. Android asks whether to
   make NoScam the default browser app — say yes.

Why the default browser: since Android 12, a tapped web link goes straight to
the default browser unless an app has *verified* ownership of that domain, which
NoScam cannot do for every domain. There is no "Open with" prompt any more.
NoScam is not really a browser — it checks the link and hands it on to the
browser you actually use (Chrome, Samsung Internet, Firefox…), never back to
itself.

Without that step, **Share → NoScam** still checks any link from inside
WhatsApp.

### Release builds

```bash
export NOSCAM_KEYSTORE=/path/to/upload.jks NOSCAM_KEYSTORE_PASSWORD=… \
       NOSCAM_KEY_ALIAS=upload NOSCAM_KEY_PASSWORD=…
./gradlew bundleRelease     # app/build/outputs/bundle/release/app-release.aab for Play
```

The keystore never goes in the repository. CI builds the debug APK on every
release and signs the bundle only when these are set as secrets.

### Distribution notes

* Google Play: new personal developer accounts must run a closed test with
  12 testers opted in for 14 consecutive days before production access.
* Google Play requires `targetSdk 36` for new apps and updates from
  Aug 31, 2026 — already set.
* Sideloaded APKs: from Sept 30, 2026, certified Android devices in Brazil,
  Indonesia, Singapore and Thailand only install apps from verified developers,
  and this expands worldwide in 2027. Verify the developer account before
  handing out APKs.
