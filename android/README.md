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
