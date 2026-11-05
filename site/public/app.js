// The landing page's only script: pick the right download for this device, and send the
// optional "get updates" form. No trackers, no third parties.

const ua = navigator.userAgent;
const platform = navigator.userAgentData?.platform ?? navigator.platform ?? "";

function detectOs() {
  if (/android/i.test(ua)) return "android";
  if (/iphone|ipad|ipod/i.test(ua) || (platform === "MacIntel" && navigator.maxTouchPoints > 1)) return "iphone";
  if (/win/i.test(platform) || /windows/i.test(ua)) return "windows";
  if (/mac/i.test(platform) || /mac os x/i.test(ua)) return "mac";
  if (/linux/i.test(platform)) return "linux";
  return "other";
}

// Browsers report every Mac as "MacIntel". The GPU name tells Apple silicon from Intel.
function isIntelMac() {
  try {
    const gl = document.createElement("canvas").getContext("webgl");
    const ext = gl && gl.getExtension("WEBGL_debug_renderer_info");
    const gpu = ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "";
    return /intel/i.test(gpu) && !/apple/i.test(gpu);
  } catch {
    return false;
  }
}

const os = detectOs();
const primary = document.getElementById("primary-download");
const note = document.getElementById("primary-note");
const intel = os === "mac" && isIntelMac();

const choice = {
  windows: ["/download/windows", "Download for Windows", "Free · Windows 10 and 11"],
  mac: intel ? ["/download/mac-intel", "Download for Mac", "Free · macOS on Intel"]
             : ["/download/mac-arm", "Download for Mac", "Free · macOS on Apple silicon"],
  android: ["/download/android", "Download for Android", "Free · Android 7 and later · test build"],
  iphone: ["#download", "See how it works on iPhone", "On iPhone, NoScam is the phone that approves"],
  linux: ["#download", "All platforms", "Linux: run from source — see GitHub"],
  other: ["#download", "All platforms", "Windows · macOS · Android · Chrome, Edge and Firefox"],
}[os];

if (primary && choice) {
  primary.href = choice[0];
  primary.textContent = choice[1];
  note.textContent = choice[2];
}

// Highlight this device's card, and switch the Mac card to Intel if that's what this is.
const mine = document.querySelector(`.dl-card[data-os="${os}"]`);
if (mine) mine.classList.add("mine");
if (intel) {
  const card = document.getElementById("mac-card");
  card.href = "/download/mac-intel";
  document.getElementById("mac-detail").textContent = "Intel Mac · 27 MB";
}

// "Download for Intel" lives inside the Mac card's link; follow it without following the card.
for (const el of document.querySelectorAll(".linkish[data-href]")) {
  el.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    location.href = el.dataset.href;
  });
}

// Optional updates signup.
const form = document.getElementById("signup");
const msg = document.getElementById("signup-msg");
form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  const data = Object.fromEntries(new FormData(form));
  msg.className = "fine";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(data.email || "").trim())) {
    msg.textContent = "Enter a valid email address.";
    msg.className = "fine err";
    return;
  }
  button.disabled = true;
  try {
    const res = await fetch("/api/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...data, os, source: "landing" }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || "Something went wrong. Please try again.");
    form.reset();
    msg.textContent = "Thanks — you'll hear from us when there's something worth telling.";
    msg.className = "fine ok";
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "fine err";
  } finally {
    button.disabled = false;
  }
});
