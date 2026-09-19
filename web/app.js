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

const api = (path, body, method) =>
  fetch(path.startsWith("http") ? path : `..${path}`, {
    method: method || (body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json" },
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
  });
}

// --- approvals -------------------------------------------------------------

let lastSeen = "";

function renderApprovals(holds) {
  const box = $("approvals");
  const pending = holds.filter((hold) => hold.status === "pending");

  if (!pending.length) {
    box.innerHTML = `
      <div class="empty">
        <strong>Nothing waiting</strong>
        You'll see a card here the moment something is held.
      </div>`;
    return;
  }

  // Only redraw when something actually changed, so a countdown doesn't reset
  // under the thumb of someone about to press Approve.
  const signature = pending.map((h) => `${h.id}:${h.seconds_remaining > 0}`).join(",");
  if (signature === lastSeen) return;
  lastSeen = signature;

  box.innerHTML = pending.map((hold) => {
    const action = hold.action || {};
    const amount = action.amount ? money(action.amount) : "";
    const payee = action.payee ? ` to ${action.payee}` : "";
    return `
      <div class="card" data-id="${hold.id}">
        <span class="badge">Waiting for you</span>
        <h2>${hold.decision.headline}</h2>
        <p>${hold.decision.detail}</p>
        <p class="meta">${amount ? amount + payee : action.file_name || ""}<br>
           On ${action.host || "their computer"} · expires in
           ${Math.max(0, Math.floor(hold.seconds_remaining / 60))}:${String(
             Math.max(0, hold.seconds_remaining % 60)).padStart(2, "0")}</p>
        <div class="row">
          <button class="action deny" data-verdict="deny">No, stop it</button>
          <button class="action approve" data-verdict="approve">Yes, allow</button>
        </div>
      </div>`;
  }).join("");

  for (const button of box.querySelectorAll("button[data-verdict]")) {
    button.addEventListener("click", async () => {
      const id = button.closest(".card").dataset.id;
      const verdict = button.dataset.verdict;
      try {
        await api(`/holds/${id}/decision`, { verdict, by: guardianName });
        toast(verdict === "approve" ? "Allowed" : "Stopped");
      } catch {
        toast("Couldn't reach the household");
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
       Make sure NoScam is running on the computer.</div>`;
  }
}

// --- link check ------------------------------------------------------------

async function checkLink(raw) {
  const url = (raw || "").trim();
  if (!url) return;
  $("verdict").innerHTML = `<div class="verdict no_signals"><h3>Checking…</h3></div>`;
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
    toast("Reported — the whole household is now warned");
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

// --- limits ----------------------------------------------------------------

async function loadHousehold() {
  const household = await api("/household");
  const limits = household.limits;
  guardianName = limits.guardian_name;
  $("household-line").textContent = `${household.name} · ${limits.guardian_name} approves`;
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
}

$("save").addEventListener("click", async () => {
  const household = await api("/household");
  await api("/limits", {
    ...household.limits,
    per_transaction_cap: Number($("per").value),
    daily_cap: Number($("day").value),
    guardian_name: $("guardian").value || "your guardian",
  }, "PUT");
  toast("Limits saved");
  loadHousehold();
});

loadHousehold();
refresh();
setInterval(refresh, 2000);
