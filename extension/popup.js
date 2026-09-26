// The popup answers two questions and no others: is NoScam actually watching,
// and how does it think you reached the page you are on? The second one is what
// makes the product legible — if it ever says something the person knows is
// wrong, they should find out here rather than at the moment of a block.

const MESSAGING = {
  "web.whatsapp.com": "WhatsApp", "web.telegram.org": "Telegram",
  "mail.google.com": "Gmail", "outlook.live.com": "Outlook",
  "messenger.com": "Messenger", "www.messenger.com": "Messenger",
  "mail.yahoo.com": "Yahoo Mail", "discord.com": "Discord",
  "localhost:8790": "Messages", "127.0.0.1:8790": "Messages",
};

const money = (value) => `₹${Number(value || 0).toLocaleString("en-IN")}`;

chrome.runtime.sendMessage({ kind: "noscam:state" }, (reply) => {
  const dot = document.getElementById("dot");
  const status = document.getElementById("status");
  const arrival = document.getElementById("arrival");

  if (!reply || !reply.ok) {
    dot.className = "dot off";
    status.textContent = "Not protecting you yet";
    document.getElementById("sub").textContent = "the NoScam app isn't running";
    arrival.textContent = "This extension only watches. The decisions are made by the " +
                          "NoScam app on this computer, and it isn't running — so " +
                          "nothing is being checked right now.";
    const button = document.querySelector("a.button");
    button.href = "https://aditya-galaxy.github.io/noscam/#install";
    button.textContent = "Get or start the NoScam app";
    return;
  }

  const { household, provenance, version } = reply.data;
  if (version && version.update_available) {
    const note = document.createElement("a");
    note.href = version.url;
    note.target = "_blank";
    note.className = "update";
    note.textContent = `NoScam ${version.latest} is available (you have ${version.current}).`;
    document.querySelector("main").prepend(note);
  }
  dot.className = "dot on";
  status.textContent = "Watching this computer";
  document.getElementById("sub").textContent = `${household.limits.guardian_name} approves`;

  const source = provenance && provenance.source_host;
  const friendly = source && MESSAGING[source.toLowerCase()];
  if (provenance && provenance.origin === "link" && friendly) {
    arrival.className = "arrival";
    arrival.textContent = `You reached this page from ${friendly}. Payments and codes ` +
                          `here need a second pair of eyes.`;
  } else {
    arrival.className = "arrival clean";
    arrival.textContent = "You opened this page yourself, so nothing here is treated " +
                          "as someone else's instruction.";
  }

  document.getElementById("limits").innerHTML = `
    <div class="row"><span>One payment up to</span><b>${money(household.limits.per_transaction_cap)}</b></div>
    <div class="row"><span>Spent today</span><b>${money(household.spent_today)}</b></div>
    <div class="row"><span>New payee waits</span><b>${household.limits.new_payee_cooling_minutes} min</b></div>
    <div class="row"><span>Remote control</span><b>${household.limits.block_remote_access ? "Blocked" : "Allowed"}</b></div>`;
});
