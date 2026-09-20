// The phone half of NoScam.
//
// It does the one thing a phone can do that a compromised conversation cannot:
// be a *different* device, held by a different person, that has to say yes. The
// voice on the call can clone a relative, spoof a number and rush a decision —
// it cannot press this button.
//
// The link checker is here too, because on a phone that is the honest limit of
// what a web app may do: it cannot see your SMS or stop an install, but it can
// tell you what a link really is before you tap it.

// The token arrives once, in the link the phone opens, and is kept from then on.
// It is what distinguishes this household's phone from everything else on the
// same Wi-Fi, which the browser cannot tell apart on its own.
const token = (() => {
  const fromLink = new URLSearchParams(location.search).get("t");
  if (fromLink) {
    try { localStorage.setItem("noscam:token", fromLink); } catch { }
    history.replaceState(null, "", location.pathname);   // keep it out of the address bar
    return fromLink;
  }
  try { return localStorage.getItem("noscam:token") || ""; } catch { return ""; }
})();

const api = (path, body, method) =>
  fetch(path.startsWith("http") ? path : `..${path}`, {
    method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json",
               ...(token ? { "X-NoScam-Token": token } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  }).then((response) => response.json());

const $ = (id) => document.getElementById(id);
const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN")}`;

function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.classList.add("show");
  setTimeout(() => node.classList.remove("show"), 2200);
}

// --- tabs ------------------------------------------------------------------

for (const tab of document.querySelectorAll("nav button")) {
  tab.addEventListener("click", () => {
    for (const other of document.querySelectorAll("nav button")) {
      other.setAttribute("aria-selected", String(other === tab));
      $(`tab-${other.dataset.tab}`).hidden = other !== tab;
    }
    if (tab.dataset.tab === "limits") loadHousehold();
    if (tab.dataset.tab === "history") loadHistory();
  });
}

// --- approvals -------------------------------------------------------------

let lastSeen = "";

function renderApprovals(holds) {
  const box = $("approvals");
  const pending = holds.filter((hold) => hold.status === "pending");

  if (!pending.length) {
    // "Nothing waiting" on its own reads like a thing that is not working.
    // Say what it is doing instead, in the household's own numbers.
    box.innerHTML = "";
    $("all-well").hidden = false;
    return;
  }
  $("all-well").hidden = true;

  // Only redraw when something actually changed, so a countdown doesn't reset
  // under the thumb of someone about to press Approve.
  const signature = pending.map((h) => `${h.id}:${h.approvable}:${h.seconds_remaining > 0}`).join(",");
  if (signature === lastSeen) return;
  lastSeen = signature;

  box.innerHTML = pending.map((hold) => {
    const action = hold.action || {};
    const amount = action.amount ? money(action.amount) : "";
    const payee = action.payee ? ` → ${action.payee}` : "";
    const clock = `${Math.max(0, Math.floor(hold.seconds_remaining / 60))}:${String(
      Math.max(0, hold.seconds_remaining % 60)).padStart(2, "0")}`;
    // A refusal is something the household is told about, not asked about.
    // Offering "allow" on one would be inviting the next move in the scam.
    // A refusal is something the household is told about, not asked about.
    // Offering "allow" on one would be inviting the next move in the scam.
    const buttons = hold.approvable === false ? `
        <p class="meta">Already stopped. Nothing for you to do.</p>` : `
        <div class="row">
          <button class="action deny" data-verdict="deny">No, stop it</button>
          <button class="action approve" data-verdict="approve">Yes, allow</button>
        </div>`;
    const label = hold.approvable === false
      ? "Stopped on their computer"
      : `Waiting for you · ${clock} left`;
    return `
      <div class="card" data-id="${hold.id}">
        <span class="tag">${label}</span>
        <h2>${hold.decision.headline}</h2>
        <p>${hold.decision.detail}</p>
        <p class="meta">${amount ? amount + payee : action.file_name || action.type || ""}<br>
           ${action.host || "their computer"}</p>
        ${buttons}
      </div>`;
  }).join("");

  for (const button of box.querySelectorAll("button[data-verdict]")) {
    button.addEventListener("click", async () => {
      const id = button.closest(".card").dataset.id;
      const verdict = button.dataset.verdict;
      try {
        await api(`/holds/${id}/decision`, { verdict, by: guardianName });
        toast(verdict === "approve" ? "Allowed." : "Stopped.");
      } catch {
        toast("Couldn't reach the computer.");
      }
      lastSeen = "";
      refresh();
    });
  }
}

let guardianName = "Guardian";

async function refresh() {
  try {
    renderApprovals(await api("/holds?status=pending"));
  } catch {
    $("approvals").innerHTML =
      `<div class="empty"><strong>Not connected</strong>
       Start NoScam on the computer it protects.</div>`;
  }
}

// --- link check ------------------------------------------------------------

async function checkLink(raw) {
  const url = (raw || "").trim();
  if (!url) return;
  $("verdict").innerHTML = `<div class="verdict"><h3>Checking…</h3></div>`;
  let result;
  try {
    result = await api("/links/check", { url });
  } catch {
    $("verdict").innerHTML = `<div class="verdict suspicious"><h3>Couldn't check it</h3>
      <p>NoScam isn't reachable from this phone right now.</p></div>`;
    return;
  }
  if (result.detail) {
    $("verdict").innerHTML =
      `<div class="verdict suspicious"><h3>That doesn't look like a link</h3></div>`;
    return;
  }

  const signals = result.signals.length
    ? `<ul class="signals">${result.signals.map((s) => `<li>${s.plain}</li>`).join("")}</ul>`
    : `<p>No warning signs in the address itself. That is not the same as safe —
         if it arrived in a message asking for money, treat it as a scam.</p>`;
  const hops = result.chain.length > 1
    ? `<div class="chain">It goes: ${result.chain.join(" → ")}</div>` : "";

  $("verdict").innerHTML = `
    <div class="verdict ${result.verdict}">
      <h3>${result.headline}</h3>
      ${signals}
      ${hops}
    </div>
    <div class="row">
      <button class="action deny" id="report">Report this site</button>
    </div>`;

  $("report").addEventListener("click", async () => {
    await api("/links/report", { url: result.final_url || result.url });
    toast("Reported. Everyone at home is now warned.");
    loadHousehold();
  });
}

$("check").addEventListener("click", () => checkLink($("url").value));
$("url").addEventListener("keydown", (event) => {
  if (event.key === "Enter") checkLink($("url").value);
});

// Android share-sheet: the PWA registers as a share target, so a link can be
// sent straight here from WhatsApp. iOS has no equivalent, which is why pasting
// is the primary path rather than the fallback.
const shared = new URLSearchParams(location.search).get("url")
  || new URLSearchParams(location.search).get("text");
if (shared) {
  document.querySelector('nav button[data-tab="link"]').click();
  $("url").value = shared;
  checkLink(shared);
}

// --- what it has actually done ---------------------------------------------
// A hold vanishes after five minutes, which is right for a queue and wrong for
// everything else. Without this screen the overrides are logged for nobody, and
// nobody can judge whether the thing is worth keeping installed.

const OUTCOME_WORDS = {
  blocked: "Stopped", needs_approval: "Held for you", cool_off: "Paused",
  approved: "You allowed it", declined: "You stopped it",
  overridden: "Continued anyway", reported: "Reported",
};

function when(iso) {
  const then = new Date(iso);
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} hr ago`;
  return then.toLocaleDateString(undefined, { weekday: "short", hour: "numeric" });
}

async function loadHistory() {
  let data;
  try {
    data = await api("/history");
  } catch {
    $("history").innerHTML = `<div class="empty"><strong>Not connected</strong>
      Start NoScam on the computer it protects.</div>`;
    return;
  }

  const s = data.summary;
  $("history-summary").innerHTML = `
    <h2>This week</h2>
    <div class="counts">
      <div><b>${s.stopped}</b><span>stopped</span></div>
      <div><b>${s.approved}</b><span>you allowed</span></div>
      <div><b>${s.overridden}</b><span>continued anyway</span></div>
    </div>
    ${s.overridden ? `<p class="meta" style="margin-top:14px">Someone pressed
      "continue anyway" ${s.overridden} time${s.overridden === 1 ? "" : "s"}. That is
      always allowed, and always written down — worth a conversation, not an alarm.</p>` : ""}`;

  $("history").innerHTML = data.items.length
    ? `<div class="card">${data.items.map((item) => `
        <div class="event">
          <div class="when">${when(item.at)}</div>
          <div class="what">
            <b>${OUTCOME_WORDS[item.outcome] || item.outcome}</b>
            <span>${[item.what, item.host, item.amount ? money(item.amount) : "",
                     item.payee].filter(Boolean).join(" · ")}</span>
          </div>
        </div>`).join("")}</div>`
    : `<div class="empty"><strong>Nothing yet</strong>
         Everything NoScam does will be listed here.</div>`;
}

// --- getting the share sheet -----------------------------------------------
// Pasting works everywhere and needs no setup, so it stays the main path. But
// two taps from inside WhatsApp beats switching apps and pasting, and the only
// way to get there is for the person to add this to their home screen — which
// nobody discovers on their own.

(function offerInstall() {
  const card = $("install-card");
  const installed = window.matchMedia("(display-mode: standalone)").matches
    || window.navigator.standalone === true;
  let dismissed = false;
  try { dismissed = localStorage.getItem("noscam:install-dismissed") === "1"; } catch { }
  if (installed || dismissed) return;

  const android = /Android/i.test(navigator.userAgent);
  const ios = /iPhone|iPad|iPod/i.test(navigator.userAgent);
  const how = $("install-how");
  if (android) {
    how.textContent = "Chrome menu (⋮) → Add to Home screen.";
  } else if (ios) {
    // Safari has no share-target, so promising one would be a lie.
    how.textContent = "On iPhone: Share → Add to Home Screen. Apple doesn't let "
                    + "apps join the Share menu, so pasting stays the way in.";
  } else {
    return;                       // a desktop browser is not who this is for
  }
  card.hidden = false;
  $("install-dismiss").addEventListener("click", () => {
    card.hidden = true;
    try { localStorage.setItem("noscam:install-dismissed", "1"); } catch { }
  });
})();

// --- limits ----------------------------------------------------------------

// First run says nothing at all, which is the worst possible thing for a
// security tool to say: the person cannot tell it from broken. So until the
// household has answered two questions, that is what the first screen asks.
function offerSetup(household) {
  const unconfigured = !household.known_payees.length
    && household.limits.guardian_name === "your guardian";
  $("setup-card").hidden = !unconfigured;
  if (!unconfigured) return;
  $("setup-save").onclick = async () => {
    const guardian = $("setup-guardian").value.trim();
    const payees = $("setup-payees").value.split(/[,\n]/).map((n) => n.trim()).filter(Boolean);
    if (guardian) {
      await api("/limits", { ...household.limits, guardian_name: guardian }, "PUT");
    }
    if (payees.length) await api("/household/payees", { payees });
    toast("Set up.");
    loadHousehold();
  };
}

async function loadHousehold() {
  const household = await api("/household");
  const limits = household.limits;
  offerSetup(household);
  const wellLine = $("all-well-line");
  if (wellLine) {
    wellLine.textContent =
      `Payments over ${money(limits.per_transaction_cap)} need ${limits.guardian_name}. `
      + `${household.known_payees.length} people you already pay go through without asking. `
      + `Remote-control software is ${limits.block_remote_access ? "blocked" : "allowed"}.`;
  }
  guardianName = limits.guardian_name;
  $("household-line").textContent = `${limits.guardian_name} approves`;
  $("l-per").textContent = money(limits.per_transaction_cap);
  $("l-day").textContent = money(limits.daily_cap);
  $("l-spent").textContent = money(household.spent_today);
  $("l-cool").textContent = `${limits.new_payee_cooling_minutes} min`;
  $("l-remote").textContent = limits.block_remote_access ? "Blocked" : "Allowed";
  $("per").value = limits.per_transaction_cap;
  $("day").value = limits.daily_cap;
  $("guardian").value = limits.guardian_name;
  $("reported").textContent = household.reported_hosts.length
    ? household.reported_hosts.join(", ") : "None yet.";

  const payees = $("payees");
  payees.innerHTML = household.known_payees.length
    ? household.known_payees.map((name) => `
        <div class="payee"><span>${name}</span>
          <button data-payee="${encodeURIComponent(name)}">Remove</button></div>`).join("")
    : `<p class="meta">Nobody yet — so every payment will wait the first time.</p>`;
  for (const button of payees.querySelectorAll("button[data-payee]")) {
    button.addEventListener("click", async () => {
      await api(`/household/payees/${button.dataset.payee}`, null, "DELETE");
      toast("Removed.");
      loadHousehold();
    });
  }
}

$("add-payee").addEventListener("click", async () => {
  const name = $("new-payee").value.trim();
  if (!name) return;
  await api("/household/payees", { payees: [name] });
  $("new-payee").value = "";
  toast("Added.");
  loadHousehold();
});

$("save").addEventListener("click", async () => {
  const household = await api("/household");
  await api("/limits", {
    ...household.limits,
    per_transaction_cap: Number($("per").value),
    daily_cap: Number($("day").value),
    guardian_name: $("guardian").value || "your guardian",
  }, "PUT");
  toast("Saved.");
  loadHousehold();
});

// Text size, remembered. Nothing else about this app is stored in the browser.
const sizeButton = $("text-size");
const applySize = (large) => {
  document.body.classList.toggle("large", large);
  sizeButton.setAttribute("aria-pressed", String(large));
  sizeButton.textContent = large ? "Normal text" : "Bigger text";
};
try {
  applySize(localStorage.getItem("noscam:large") === "1");
} catch { /* private browsing: default size is fine */ }
sizeButton.addEventListener("click", () => {
  const large = !document.body.classList.contains("large");
  applySize(large);
  try { localStorage.setItem("noscam:large", large ? "1" : "0"); } catch { /* ignore */ }
});

loadHousehold();
refresh();
setInterval(refresh, 2000);
