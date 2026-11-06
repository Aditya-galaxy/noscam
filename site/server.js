// noscam.kronagent.dev: the public front door for NoScam. Serves the landing page, sends download
// buttons to the latest GitHub release (counting them), and collects optional "get updates" signups
// into Firestore. Runs on Cloud Run (scales to zero); no framework, one dependency.
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FieldValue, Firestore } from "@google-cloud/firestore";

const PORT = Number(process.env.PORT ?? 8080);
// A dedicated Firestore database, so NoScam's signups are isolated from other apps in the project.
const DATABASE = process.env.FIRESTORE_DATABASE ?? "noscam";
const PUBLIC = path.join(path.dirname(fileURLToPath(import.meta.url)), "public");
const RELEASES = "https://github.com/Aditya-galaxy/noscam/releases/latest/download";

// Uses the Cloud Run service account; locally, Application Default Credentials (or set DRY_RUN=1).
const db = process.env.DRY_RUN ? null : new Firestore({ databaseId: DATABASE, ignoreUndefinedProperties: true });

// Download buttons point here, not at GitHub directly, so the page never hard-codes a version and
// we can count installs per platform. Release asset names are stable across versions.
const DOWNLOADS = {
  // Microsoft Store: signed by Microsoft (no SmartScreen warning) and updated by the Store.
  windows: "https://apps.microsoft.com/detail/9P3FWLQHJD1Z?mode=direct",
  "windows-exe": `${RELEASES}/NoScam-Setup.exe`,
  "mac-arm": `${RELEASES}/NoScam-macOS-arm64.dmg`,
  "mac-intel": `${RELEASES}/NoScam-macOS-x86_64.dmg`,
  android: `${RELEASES}/NoScam-Android-debug.apk`,
  chrome: `${RELEASES}/noscam-extension-chrome.zip`,
  firefox: `${RELEASES}/noscam-extension-firefox.zip`,
};

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
};

const SECURITY_HEADERS = {
  "Content-Security-Policy":
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  "Strict-Transport-Security": "max-age=31536000",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cross-Origin-Opener-Policy": "same-origin",
};

// Strip control characters so stored text can't carry terminal escapes.
const clean = (v, max) => String(v ?? "").replace(/[\x00-\x08\x0b-\x1f\x7f‪-‮⁦-⁩]/g, "").slice(0, max);
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,63}$/;

// The client's address as seen by Google's front end, which appends it as the LAST X-Forwarded-For
// entry. Earlier entries are whatever the client sent, so trusting the first lets anyone dodge limits.
const clientIp = (req) => {
  const hops = String(req.headers["x-forwarded-for"] ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return hops.at(-1) || req.socket.remoteAddress || "?";
};

// Per-instance fixed-window limiter; good enough to stop casual abuse of a signup form.
const hits = new Map();
function limited(key, limit = 5, windowMs = 10 * 60_000) {
  const now = Date.now();
  const h = hits.get(key);
  if (!h || h.reset < now) {
    hits.set(key, { n: 1, reset: now + windowMs });
    if (hits.size > 5000) for (const [k, v] of hits) if (v.reset < now) hits.delete(k);
    return false;
  }
  return ++h.n > limit;
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { ...SECURITY_HEADERS, ...headers });
  res.end(body);
}
const json = (res, status, obj) => send(res, status, JSON.stringify(obj), { "Content-Type": "application/json", "Cache-Control": "no-store" });

async function readBody(req, max = 4096) {
  let size = 0;
  const chunks = [];
  for await (const c of req) {
    size += c.length;
    if (size > max) throw new Error("too large");
    chunks.push(c);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function subscribe(req, res) {
  if (limited(clientIp(req))) return json(res, 429, { error: "Too many attempts. Try again in a few minutes." });
  let body;
  try {
    body = JSON.parse(await readBody(req));
  } catch {
    return json(res, 400, { error: "Bad request." });
  }
  if (body.website) return json(res, 200, { ok: true }); // honeypot: people never see this field

  const email = String(body.email ?? "").trim().toLowerCase();
  if (email.length > 254 || !EMAIL_RE.test(email)) return json(res, 400, { error: "Enter a valid email address." });

  const doc = {
    email,
    // Who it's for: a person protecting themselves or family, an organisation, or defence/government.
    interest: ["family", "business", "defence"].includes(body.interest) ? body.interest : "family",
    os: ["windows", "mac", "android", "iphone", "linux", "other"].includes(body.os) ? body.os : undefined,
    source: clean(body.source, 80) || undefined,
    referrer: clean(req.headers.referer, 300) || undefined,
    userAgent: clean(req.headers["user-agent"], 300) || undefined,
    lastSeenAt: FieldValue.serverTimestamp(),
    signups: FieldValue.increment(1),
  };
  try {
    if (db) {
      // One document per address (keyed by its hash), so repeat signups just update it.
      const ref = db.collection("signups").doc(createHash("sha256").update(email).digest("hex"));
      await db.runTransaction(async (tx) => {
        const snap = await tx.get(ref);
        tx.set(ref, snap.exists ? doc : { ...doc, createdAt: FieldValue.serverTimestamp() }, { merge: true });
      });
    } else {
      console.log("[dry-run] signup", email, doc.interest, doc.os ?? "");
    }
  } catch (err) {
    console.error("signup failed", err);
    return json(res, 500, { error: "Something went wrong. Please try again." });
  }
  return json(res, 200, { ok: true }); // same answer whether or not the address was already listed
}

function download(req, res, id) {
  const target = DOWNLOADS[id];
  if (!target) return send(res, 404, "Not found", { "Content-Type": "text/plain" });
  // Count it, but never make the person wait on the count. One per IP per platform per hour.
  if (db && !limited(`dl:${id}:${clientIp(req)}`, 1, 60 * 60_000)) {
    db.collection("downloads").doc(id)
      .set({ count: FieldValue.increment(1), lastAt: FieldValue.serverTimestamp() }, { merge: true })
      .catch((err) => console.error("download count failed", err));
  }
  send(res, 302, undefined, { Location: target, "Cache-Control": "no-store" });
}

async function serveStatic(req, res, pathname) {
  const file = pathname === "/" ? "index.html" : pathname.slice(1);
  const full = path.join(PUBLIC, path.normalize(file));
  if (!full.startsWith(PUBLIC + path.sep)) return send(res, 404, "Not found");
  try {
    const data = await readFile(full);
    const ext = path.extname(full);
    const cache = ext === ".html" ? "public, max-age=300" : "public, max-age=86400";
    send(res, 200, req.method === "HEAD" ? undefined : data, { "Content-Type": TYPES[ext] ?? "application/octet-stream", "Cache-Control": cache });
  } catch {
    send(res, 404, "Not found", { "Content-Type": "text/plain" });
  }
}

createServer(async (req, res) => {
  const { pathname } = new URL(req.url ?? "/", "http://x");
  try {
    if (pathname === "/api/subscribe" && req.method === "POST") return await subscribe(req, res);
    if (pathname === "/api/health") return json(res, 200, { ok: true });
    if (pathname.startsWith("/download/") && (req.method === "GET" || req.method === "HEAD"))
      return download(req, res, pathname.slice("/download/".length));
    if (req.method === "GET" || req.method === "HEAD") return await serveStatic(req, res, pathname);
    send(res, 405, "Method not allowed");
  } catch (err) {
    console.error(err);
    if (!res.headersSent) send(res, 500, "Server error");
  }
}).listen(PORT, () => console.log(`noscam-site listening on :${PORT}`));
