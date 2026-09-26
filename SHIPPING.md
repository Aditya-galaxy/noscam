# Getting this to an actual household

An honest account of what stands between the current build and a parent in
another city running it without help. Nothing here is hand-waving: each step
says what exists, what it costs, and who has to do it.

## Where it is today

| Piece | Built by | What a user gets |
|---|---|---|
| Desktop app, macOS | `release.yml` → `NoScam-macOS-arm64.dmg`, `NoScam-macOS-x86_64.dmg` | Menu-bar app, starts at login, no Python needed |
| Desktop app, Windows | `release.yml` → `NoScam-Setup.exe` (Inno Setup, per-user, no admin) | Tray app; start-at-login is an installer checkbox |
| `pipx install git+https://github.com/Aditya-galaxy/noscam` | built from the repository by pip; checked by the `wheel` CI job | One line, for people who own a terminal |
| Chrome / Edge extension | `package.py` → `noscam-extension-chrome.zip` | Shows a “!” and a download link until the app is running |
| Firefox extension | `package.py` → `noscam-extension-firefox.zip` | Same, with Firefox's manifest (`background.scripts`, gecko id, 121+) |
| Android companion | `release.yml` → debug APK; signed `.aab` when the keystore secret exists | Checks every tapped link once chosen as the default browser app |

An installed copy keeps the household in the platform's per-user app-data
folder (`~/Library/Application Support/NoScam`, `%APPDATA%\NoScam`,
`~/.local/share/noscam`), starts without the demo, and opens first-run setup.
A clone of the repository keeps the old behaviour: `data/` beside the code and
the demo on.

## What still costs money or a person

The pipeline is ready; each item below switches on when its secret is added to
the repository (the names are listed at the top of `release.yml`). Until then
the build says, in its log, that the output is unsigned.

| Step | Cost | Without it |
|---|---|---|
| Apple Developer ID + notarisation | $99/year | Gatekeeper refuses to open the app from a download |
| Windows signing — Azure Artifact Signing | ~$10/month (US/Canada individuals; elsewhere an OV certificate, ~$200–400/year) | SmartScreen warns on every download, until reputation builds |
| Chrome Web Store | $5 once, days of review | Developer-mode install only |
| Edge Add-ons, Firefox AMO | Free | — |
| Google Play | $25 once; 12 testers opted in for 14 days for a new personal account | APK only, and from Sept 30, 2026 unverified-developer APKs are blocked in BR/ID/SG/TH (worldwide in 2027) |

### Release checklist

1. Bump `service/__init__.py` and `extension/manifest.json` (CI refuses a tag
   that disagrees with either) and `versionName`/`versionCode` in
   `android/app/build.gradle`.
2. `git tag vX.Y.Z && git push --tags`.
3. Upload `noscam-extension-chrome.zip` and `-firefox.zip` from the release to
   the stores, with the reviewer notes in `docs/CWS_SUBMISSION.md`.
4. Installed copies see the new version within a day: a line in the phone app,
   the extension popup and the tray menu. Nothing updates itself.

## What we would *not* ship without

- **A weekly household summary.** Overrides are logged, and logging something
  nobody reads is theatre. The guardian should get "three payments held, one
  overridden, here's which" every Sunday.
- **Real-site coverage.** The detector is tested against the demo pages and one
  live third-party donation page. Before release it needs the top twenty
  banking and UPI sites in a target country, tested by hand, with the failures
  written down.
- **A study with real households.** Every number in this repository comes from
  scenarios written by the person who wrote the rules. That is a regression
  test, not evidence.

## Update and trust model

The extension auto-updates through the store; the service does not, which is
the wrong way round for a security tool — so the service checks GitHub for the
latest release once a day (`service/updates.py`) and says so plainly in the
phone app, the extension popup and the tray menu. It never updates itself. Nothing that can quietly change what the gate does should be able
to change it without the household noticing.

## What this costs to run

Nothing. There is no server, no database and no account system: the household's
data lives on their own machine. The only recurring costs are the developer
programmes above, which exist so the user does not have to click past a warning
to install a thing that protects them from warnings they should not click past.
