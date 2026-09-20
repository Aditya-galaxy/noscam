# Getting this to an actual household

An honest account of what stands between the current build and a parent in
another city running it without help. Nothing here is hand-waving: each step
says what exists, what it costs, and who has to do it.

## Where it is today

| Piece | State | What a user must do |
|---|---|---|
| The gate (Python service) | Works | Run one command, or double-click `Start NoScam.command` |
| Chrome extension | Works | Load unpacked in developer mode |
| Phone app | Works | Open a URL; optionally add to home screen |
| Setting limits and payees | Works, from the phone | Nothing technical |

So: usable today by someone comfortable with a terminal, and by a *household*
where one person is. That is a real audience — the adult child who sets things
up for a parent is exactly the guardian this product already assumes exists —
but it is not yet "download and go".

## The three things between here and that

### 1. The extension, without developer mode — about a week

Chrome Web Store: a **$5 one-time** developer fee, a privacy policy, a listing,
and review that takes days (longer for an extension requesting `downloads` and
broad host permissions, which this one does and cannot avoid).

What review will ask, and the honest answers:
- *Why `<all_urls>`?* Because a payment page can be any site.
- *Why `downloads`?* To cancel a remote-access installer before it lands.
- *What leaves the machine?* Nothing, except the optional advice line to Gemini,
  which is off without an API key.

Firefox is a second listing from the same source, and Safari needs a separate
Xcode project.

### 2. The service, without Python — about two days

Today it needs Python and four packages. Two real options:

- **`pipx install noscam`** — `pyproject.toml` already declares the entry point,
  so this works from the repository right now and would work from PyPI after a
  `twine upload`. Still a terminal, but one line and no clone.
- **A single binary.** `pyinstaller --onefile noscam.py` produces a ~15 MB
  executable per platform, plus a login item so it starts with the machine. On
  macOS it needs an Apple Developer ID ($99/year) and notarisation, or every
  user meets Gatekeeper. On Windows, unsigned binaries meet SmartScreen; a
  code-signing certificate is ~$200/year.

That cost is the honest reason this is not already a download.

### 3. The phone, past pasting — see LIMITATIONS.md

Android needs a small native app with an `http`/`https` `VIEW` intent-filter to
intercept the tap itself. iOS has no equivalent outside a Safari Web Extension.

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

The extension would auto-update through the store; the service would not, which
is the wrong way round for a security tool — so a released version needs a
version check and a plain "there is a newer NoScam" notice, never a silent
self-update. Nothing that can quietly change what the gate does should be able
to change it without the household noticing.

## What this costs to run

Nothing. There is no server, no database and no account system: the household's
data lives on their own machine. The only recurring costs are the developer
programmes above, which exist so the user does not have to click past a warning
to install a thing that protects them from warnings they should not click past.
