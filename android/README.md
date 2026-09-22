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
* Android Studio (Hedgehog or newer) OR Android SDK with JDK 17+.

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
3. On your phone, tap any link in WhatsApp or SMS.
4. When prompted by Android to "Open with", choose **NoScam** → **Always**.

From then on, links are checked by NoScam before they open in your browser.
