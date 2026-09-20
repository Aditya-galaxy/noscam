// NoScam — the part of the extension that watches, remembers, and talks to
// the service.
//
// Two jobs live here rather than in the content script:
//
//   1. **Provenance.** Chrome will tell you how a navigation started
//      (`transitionType`) and, when a link opens a new tab, which tab it came
//      from (`sourceTabId`). Stitching those together is how NoScam can say
//      "you arrived here from WhatsApp forty seconds ago" instead of guessing.
//
//   2. **Talking to the service.** A content script running on an https page
//      cannot fetch http://127.0.0.1 — the browser blocks it as mixed content.
//      The service worker has no such problem, so every request goes through
//      here and the content script only sends messages.

const SERVICE = "http://127.0.0.1:8787";

// tabId -> { origin, source_host, at }   how this tab reached its current page
const provenance = new Map();
// tabId -> last committed URL, so a same-tab link click knows where it came from
const lastUrl = new Map();

function hostOf(url) {
  try {
    const parsed = new URL(url);
    return parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname;
  } catch {
    return "";
  }
}

function setProvenance(tabId, origin, sourceHost) {
  provenance.set(tabId, {
    origin,
    source_host: sourceHost || null,
    at: new Date().toISOString(),
  });
}

// A link opened in a *new* tab: the source tab is handed to us directly.
chrome.webNavigation.onCreatedNavigationTarget.addListener(async (details) => {
  const sourceUrl = lastUrl.get(details.sourceTabId) || "";
  setProvenance(details.tabId, "link", hostOf(sourceUrl));
});

chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0) return;

  const previous = lastUrl.get(details.tabId) || "";
  const transition = details.transitionType;

  if (transition === "typed" || transition === "generated" || transition === "keyword") {
    setProvenance(details.tabId, "typed", null);
  } else if (transition === "auto_bookmark") {
    setProvenance(details.tabId, "bookmark", null);
  } else if (transition === "link" || transition === "form_submit") {
    const previousHost = hostOf(previous);
    const existing = provenance.get(details.tabId);
    // Within one site, a click does not reset where the journey began: the scam
    // page redirects you onward, and the message is still what sent you.
    if (existing && previousHost && existing.source_host &&
        previousHost === hostOf(details.url)) {
      // same-site navigation — keep the original provenance
    } else if (existing && previousHost === existing.source_host) {
      // still one hop from the message
    } else if (previousHost) {
      setProvenance(details.tabId, "link", previousHost);
    }
  } else if (transition === "reload") {
    // keep whatever we knew
  } else if (!provenance.has(details.tabId)) {
    setProvenance(details.tabId, "unknown", null);
  }

  lastUrl.set(details.tabId, details.url);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  provenance.delete(tabId);
  lastUrl.delete(tabId);
});

async function ask(path, body) {
  const response = await fetch(`${SERVICE}${path}`, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`service said ${response.status}`);
  return response.json();
}

async function checkAction(tabId, action) {
  const where = provenance.get(tabId) || { origin: "unknown", source_host: null, at: null };
  return ask("/gate/check", { action, provenance: where });
}

// --- downloads -------------------------------------------------------------
// The one place NoScam stops something without asking anybody: software that
// hands live control of the machine to whoever is on the phone. `downloads.cancel`
// is available in MV3 and the file never lands.

const INSTALLER = /\.(apk|exe|msi|dmg|scr|bat|jar)(\?|$)/i;
const REMOTE_ACCESS = /(anydesk|teamviewer|quicksupport|ultraviewer|rustdesk|ammyy|logmein)/i;

chrome.downloads.onCreated.addListener(async (item) => {
  const name = item.filename || item.url || "";
  const isInstaller = INSTALLER.test(name) || INSTALLER.test(item.url || "");
  const isRemote = REMOTE_ACCESS.test(name) || REMOTE_ACCESS.test(item.url || "");
  if (!isInstaller && !isRemote) return;

  const tabId = item.tabId ?? -1;
  const action = {
    type: isRemote ? "remote_access_download" : "app_install_file",
    host: hostOf(item.url || ""),
    file_name: (name.split("/").pop() || name).split("\\").pop(),
  };

  let decision;
  try {
    decision = await checkAction(tabId, action);
  } catch (error) {
    return; // service not running: do not interfere with the person's browser
  }
  if (decision.disposition === "allow") return;

  try {
    await chrome.downloads.cancel(item.id);
    await chrome.downloads.erase({ id: item.id });
  } catch {
    // already finished; the overlay still explains what it is
  }
  if (tabId >= 0) {
    chrome.tabs.sendMessage(tabId, { kind: "noscam:blocked", decision }).catch(() => {});
  }
});

// --- content script bridge -------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const tabId = sender.tab ? sender.tab.id : -1;

  const handlers = {
    "noscam:check": () => checkAction(tabId, message.action),
    "noscam:hold": () => ask(`/holds/${message.holdId}`),
    "noscam:advice": () => ask(`/holds/${message.holdId}/advice`),
    "noscam:override": () =>
      ask(`/holds/${message.holdId}/override`, { reason: message.reason || "" }),
    "noscam:state": async () => ({
      provenance: provenance.get(tabId) || null,
      household: await ask("/household"),
    }),
  };

  const handler = handlers[message.kind];
  if (!handler) return false;

  handler()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
  return true;                       // keep the channel open for the async reply
});
