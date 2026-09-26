# Mozilla Firefox Add-ons (AMO) Submission Guide

This document outlines the submission process for publishing NoScam on the **Mozilla Add-on Developer Hub (AMO)**.

---

## 1. Extension Information

* **Name**: NoScam
* **Add-on ID**: `guardian@noscam.org` (configured in `manifest.json` under `browser_specific_settings.gecko.id`)
* **Category**: Privacy & Security
* **Summary**:
  > Refuses to let an instruction that arrived through a message authorise something irreversible.
* **Support / Source Code**: `https://github.com/Aditya-galaxy/noscam`
* **Privacy Policy URL**: `https://aditya-galaxy.github.io/noscam/privacy.html`
* **Upload Asset**: Upload `dist/noscam-extension-firefox.zip`. `python3 package.py` writes it with the Firefox manifest: `background.scripts` instead of Chrome's `service_worker`, the gecko add-on id, and a minimum of Firefox 121.
* **Host permissions are optional in Firefox MV3**: after installing, the user has to allow NoScam on all sites (Add-ons → NoScam → Permissions), or the content script will not run. Say this in the listing and the reviewer notes.

---

## 2. Mozilla Review Checklist

Mozilla has strict policies against obfuscated or remotely loaded code.

* **No Remote Code Execution**: NoScam does not use `eval()`, `new Function()`, or load remote scripts. All content scripts and background workers are bundled locally in the `.zip`.
* **Manifest V3 Compatibility**: The extension uses modern Manifest V3 standards supported in Firefox 115+.
* **Source Code Submission**: Because NoScam is written in plain, un-minified vanilla JavaScript without Webpack or Babel compilation, you **do not** need to submit separate build instructions or source archives to AMO. The zip is completely human-readable.

---

## 3. Submission Walkthrough

1. Go to the [Mozilla Add-on Developer Hub](https://addons.mozilla.org/developers/).
2. Log in with your Firefox Account.
3. Click **Submit a New Add-on** → Choose **On this site** (public listing).
4. Upload `dist/noscam-extension-firefox.zip`.
5. Automated linter checks will run; confirm 0 errors.
6. Provide the privacy policy URL and description.
7. Click **Submit**. Automated approval on AMO typically completes within a few hours.
