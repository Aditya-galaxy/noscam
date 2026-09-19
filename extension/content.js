// NoScam — the part the person actually sees.
//
// It watches for the small set of moments that cannot be undone (sending money,
// typing a one-time code or a password) and, when the gate says to, puts a plain
// explanation in front of the action instead of letting it happen.
//
// Design rules, in order of importance:
//   * Never silently break a page. If the service is down, everything works as
//     it did before — a security tool that makes the web feel broken is a
//     security tool that gets uninstalled.
//   * Say what is happening and why, in words the person can check against
//     their own memory ("you arrived here from WhatsApp 40 seconds ago").
//   * Always leave a way through, and make it honest rather than hidden.

(() => {
  const AMOUNT = /amount|value|sum|rupees|inr|usd/i;
  const PAYEE = /payee|beneficiary|recipient|to_?name|payto|upi|vpa/i;
  const OTP = /otp|one.?time|verification.?code|passcode|mfa|2fa/i;

  let overlayHost = null;
  let pollTimer = null;
  let countdownTimer = null;

  // The same file runs in two places. Inside the extension it messages the
  // service worker, which holds the real provenance. Loaded straight into a page
  // (the hosted demo, for anyone who won't install an unpacked extension) it
  // talks to the service itself and reconstructs provenance from the referrer —
  // weaker, because a referrer can be withheld, but enough to show the gate.
  const inExtension = typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id;
  const SERVICE = "http://127.0.0.1:8787";

  const post = async (path, body) => {
    const response = await fetch(`${SERVICE}${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    return response.json();
  };

  const simulated = async (message) => {
    const referrer = document.referrer ? new URL(document.referrer) : null;
    const sourceHost = referrer
      ? (referrer.port ? `${referrer.hostname}:${referrer.port}` : referrer.hostname)
      : null;
    if (message.kind === "noscam:check") {
      return { ok: true, data: await post("/gate/check", {
        action: message.action,
        provenance: {
          origin: sourceHost ? "link" : "typed",
          source_host: sourceHost,
          // When this page was opened, not when the button was pressed: the
          // gate measures how long ago the message sent you here.
          at: new Date(Date.now() - Math.round(performance.now())).toISOString(),
        },
      }) };
    }
    if (message.kind === "noscam:hold") {
      return { ok: true, data: await post(`/holds/${message.holdId}`) };
    }
    if (message.kind === "noscam:override") {
      return { ok: true, data: await post(`/holds/${message.holdId}/override`,
                                          { reason: message.reason || "" }) };
    }
    return { ok: false };
  };

  const send = (message) =>
    new Promise((resolve) => {
      if (!inExtension) {
        simulated(message).then(resolve).catch(() => resolve({ ok: false }));
        return;
      }
      try {
        chrome.runtime.sendMessage(message, (reply) => {
          if (chrome.runtime.lastError) return resolve({ ok: false });
          resolve(reply || { ok: false });
        });
      } catch {
        resolve({ ok: false });
      }
    });

  const fieldValue = (form, pattern) => {
    const fields = [...form.querySelectorAll("input, select")];
    const match = fields.find((field) =>
      pattern.test(`${field.name} ${field.id} ${field.placeholder || ""}`));
    return match ? String(match.value || "").trim() : "";
  };

  const looksLikePaymentForm = (form) => {
    if (form.dataset.noscamAction === "payment") return true;
    const text = form.innerText.toLowerCase();
    const hasAmount = [...form.querySelectorAll("input")].some((input) =>
      AMOUNT.test(`${input.name} ${input.id} ${input.placeholder || ""}`) ||
      input.type === "number");
    const hasIntent = /(pay|transfer|send money|remit)/.test(text);
    return hasAmount && hasIntent;
  };

  // --- overlay -------------------------------------------------------------

  const closeOverlay = () => {
    clearInterval(pollTimer);
    clearInterval(countdownTimer);
    if (overlayHost) overlayHost.remove();
    overlayHost = null;
  };

  const showOverlay = (decision, { onContinue }) => {
    closeOverlay();
    overlayHost = document.createElement("div");
    overlayHost.style.cssText = "all: initial; position: fixed; inset: 0; z-index: 2147483647;";
    const root = overlayHost.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .veil { position: fixed; inset: 0; background: rgba(12, 18, 28, .72);
                display: grid; place-items: center; padding: 24px;
                font: 16px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif; }
        .card { width: min(520px, 100%); background: #fff; border-radius: 16px;
                padding: 28px; box-shadow: 0 20px 60px rgba(0,0,0,.35); color: #16202e; }
        .badge { display: inline-flex; align-items: center; gap: 8px; font-size: 13px;
                 font-weight: 700; letter-spacing: .4px; text-transform: uppercase;
                 color: #8a5a00; background: #fff4d6; padding: 6px 12px; border-radius: 999px; }
        h2 { font-size: 24px; line-height: 1.25; margin: 16px 0 10px; }
        p { font-size: 17px; margin: 0 0 18px; color: #2a3646; }
        .row { display: flex; flex-direction: column; gap: 10px; margin-top: 22px; }
        button { font: inherit; font-size: 17px; font-weight: 600; padding: 14px 18px;
                 border-radius: 10px; border: 0; cursor: pointer; }
        .primary { background: #0b5cff; color: #fff; }
        .primary[disabled] { background: #c8d4ea; cursor: default; }
        .secondary { background: #eef1f6; color: #16202e; }
        .quiet { background: transparent; color: #6b7686; font-size: 14px;
                 font-weight: 500; text-decoration: underline; padding: 6px; }
        .status { margin-top: 16px; font-size: 15px; color: #45566c; min-height: 22px; }
        .mark { font-size: 13px; color: #8a94a3; margin-top: 18px; }
      </style>
      <div class="veil">
        <div class="card" role="alertdialog" aria-modal="true">
          <span class="badge">NoScam · on hold</span>
          <h2></h2>
          <p></p>
          <div class="row">
            <button class="primary"></button>
            <button class="secondary">Cancel — don't do this</button>
            <button class="quiet">I'm sure. Continue anyway</button>
          </div>
          <div class="status"></div>
          <div class="mark">Nothing has been sent. This was decided on your own
            computer, and written down so you can check it later.</div>
        </div>
      </div>`;

    root.querySelector("h2").textContent = decision.headline;
    root.querySelector("p").textContent = decision.detail;
    const primary = root.querySelector(".primary");
    const status = root.querySelector(".status");
    primary.textContent = decision.button || "OK";

    root.querySelector(".secondary").addEventListener("click", () => {
      closeOverlay();
    });

    root.querySelector(".quiet").addEventListener("click", async () => {
      if (decision.hold_id) {
        await send({ kind: "noscam:override", holdId: decision.hold_id,
                     reason: "continued at the keyboard" });
      }
      closeOverlay();
      onContinue();
    });

    if (decision.release === "approval" && decision.hold_id) {
      primary.addEventListener("click", () => {
        primary.disabled = true;
        primary.textContent = `Waiting for ${decision.guardian}…`;
        status.textContent = "Ask them to open NoScam on their phone.";
        pollTimer = setInterval(async () => {
          const reply = await send({ kind: "noscam:hold", holdId: decision.hold_id });
          if (!reply.ok) return;
          const state = reply.data.status;
          if (state === "approved") {
            clearInterval(pollTimer);
            status.textContent = "Approved.";
            primary.disabled = false;
            primary.textContent = "Continue";
            primary.onclick = () => { closeOverlay(); onContinue(); };
          } else if (state === "denied") {
            clearInterval(pollTimer);
            status.textContent = `${decision.guardian} said no.`;
            primary.textContent = "Declined";
          } else if (state === "expired") {
            clearInterval(pollTimer);
            status.textContent = "The request expired. Try again if you still want to.";
            primary.disabled = false;
            primary.textContent = decision.button;
          }
        }, 2000);
      });
    } else if (decision.release === "wait" && decision.wait_seconds) {
      let remaining = decision.wait_seconds;
      const tick = () => {
        const minutes = Math.floor(remaining / 60);
        const seconds = String(remaining % 60).padStart(2, "0");
        primary.textContent = `Wait ${minutes}:${seconds}`;
        primary.disabled = remaining > 0;
        if (remaining <= 0) {
          clearInterval(countdownTimer);
          primary.textContent = "Continue";
          primary.onclick = () => { closeOverlay(); onContinue(); };
        }
        remaining -= 1;
      };
      tick();
      countdownTimer = setInterval(tick, 1000);
    } else {
      primary.textContent = "Go back to safety";
      primary.addEventListener("click", () => {
        closeOverlay();
        if (history.length > 1) history.back();
      });
    }

    document.documentElement.appendChild(overlayHost);
  };

  // --- interception --------------------------------------------------------

  const guard = async (action, proceed) => {
    const reply = await send({ kind: "noscam:check", action });
    if (!reply.ok) return proceed();          // service down: never break the page
    const decision = reply.data;
    if (decision.disposition === "allow") return proceed();
    showOverlay(decision, { onContinue: proceed });
  };

  const wirePaymentForm = (form) => {
    if (form.dataset.noscamWired) return;
    form.dataset.noscamWired = "1";

    form.addEventListener("submit", (event) => {
      if (form.dataset.noscamCleared === "1") {
        form.dataset.noscamCleared = "";
        return;                                // already decided; let it through
      }
      event.preventDefault();
      event.stopImmediatePropagation();

      const rawAmount = fieldValue(form, AMOUNT).replace(/[^\d.]/g, "");
      guard({
        type: "payment",
        host: location.host,
        amount: rawAmount ? Number(rawAmount) : null,
        payee: fieldValue(form, PAYEE) || null,
      }, () => {
        form.dataset.noscamCleared = "1";
        form.requestSubmit ? form.requestSubmit() : form.submit();
      });
    }, true);
  };

  const wireSecretFields = (scope) => {
    const secrets = [...scope.querySelectorAll("input")].filter((input) =>
      input.type === "password" ||
      OTP.test(`${input.name} ${input.id} ${input.placeholder || ""}`));
    for (const input of secrets) {
      if (input.dataset.noscamWired) continue;
      input.dataset.noscamWired = "1";
      // Checked on focus, before a single character is typed: by the time a
      // one-time code has been entered on a fake page, it is already gone.
      input.addEventListener("focus", () => {
        const isOtp = input.type !== "password";
        guard({ type: isOtp ? "otp_entry" : "credential_entry", host: location.host },
              () => {});
        if (overlayHost) input.blur();
      }, { once: true });
    }
  };

  const scan = () => {
    for (const form of document.querySelectorAll("form")) {
      if (looksLikePaymentForm(form)) wirePaymentForm(form);
    }
    wireSecretFields(document);
  };

  const start = () => {
    if (window.__noscamLoaded) return;      // never wire a page twice
    window.__noscamLoaded = inExtension ? "extension" : "page";
    scan();
    new MutationObserver(scan).observe(document.documentElement,
                                       { childList: true, subtree: true });

    if (inExtension) {
      // A blocked download is announced by the service worker, which has already
      // cancelled it; the page just has to explain what happened.
      chrome.runtime.onMessage.addListener((message) => {
        if (message.kind === "noscam:blocked") {
          showOverlay(message.decision, { onContinue: () => {} });
        }
      });
    }
  };

  // The extension wins if it is installed: it knows how the tab was really
  // reached. The page copy waits a moment to find out whether it is needed.
  if (inExtension) start();
  else setTimeout(start, 400);
})();
