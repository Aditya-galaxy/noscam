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
  const CURRENCY_AMOUNT = /([\$£€₹¥]\s*[\d,]+(\.\d+)?|\b[\d,]+(\.\d+)?\s*(usd|inr|eur|gbp|cad|aud)\b)/i;
  const PAYEE = /payee|beneficiary|recipient|to_?name|payto|upi|vpa/i;
  const OTP = /otp|one.?time|verification.?code|passcode|mfa|2fa/i;

  let overlayHost = null;
  let pollTimer = null;
  let countdownTimer = null;

  // Listen in the root window for delegation from nested payment iframes (Stripe, Razorpay, PayPal)
  if (typeof window !== "undefined" && window === window.top) {
    window.addEventListener("message", (event) => {
      if (!event.data || event.data.noscam !== true) return;
      if (event.data.kind === "noscam:child_hold") {
        const { requestId, decision } = event.data;
        showOverlay(decision, {
          onContinue: () => {
            try {
              event.source.postMessage({
                noscam: true,
                kind: "noscam:child_resume",
                requestId,
              }, "*");
            } catch {}
          },
        });
      }
    });
  }

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
    if (message.kind === "noscam:arrival") {
      const referrerHost = sourceHost;
      return { ok: true, data: await post("/gate/arrival", {
        url: message.url,
        provenance: {
          origin: referrerHost ? "link" : "typed",
          source_host: referrerHost,
          at: new Date(Date.now() - Math.round(performance.now())).toISOString(),
        },
      }) };
    }
    if (message.kind === "noscam:advice") {
      return { ok: true, data: await post(`/holds/${message.holdId}/advice`) };
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

  const fieldValue = (scope, pattern) => {
    const fields = [...scope.querySelectorAll("input, select")];
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
    if (overlayHost) {
      if (overlayHost.__noscamRemoveKeys) overlayHost.__noscamRemoveKeys();
      overlayHost.remove();
    }
    overlayHost = null;
  };

  const showOverlay = (decision, { onContinue }) => {
    closeOverlay();
    overlayHost = document.createElement("div");
    overlayHost.style.cssText = "all: initial; position: fixed; inset: 0; z-index: 2147483647;";
    // Closed: the page cannot query this shadow root, so it cannot read the card,
    // remove its buttons or dispatch a click on "Continue anyway". We keep the
    // reference ourselves, which is all our own focus handling needs.
    const root = overlayHost.attachShadow({ mode: "closed" });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .veil { position: fixed; inset: 0; background: rgba(0, 0, 0, .55);
                display: grid; place-items: center; padding: 20px;
                font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                      Helvetica, Arial, sans-serif; color: #000; }
        .card { width: min(480px, 100%); background: #fff; border-radius: 12px;
                box-shadow: 0 12px 40px rgba(0,0,0,.28); overflow: hidden; }
        .bar { display: flex; align-items: center; gap: 8px; padding: 14px 24px;
               border-bottom: 1px solid #eaeaea; font-size: 13px; color: #666; }
        .bar b { color: #000; font-weight: 600; }
        .body { padding: 24px; }
        h2 { font-size: 22px; line-height: 1.3; font-weight: 600; margin: 0 0 10px;
             letter-spacing: -.01em; }
        h2:focus { outline: none; }
        p { font-size: 16px; margin: 0 0 16px; color: #444; }
        .advice { background: #fafafa; border: 1px solid #eaeaea; border-radius: 8px;
                  padding: 14px 16px; margin: 0 0 16px; color: #000; font-size: 15px; }
        .row { display: flex; flex-direction: column; gap: 8px; margin-top: 20px; }
        button { font: 500 15px/1 inherit; padding: 14px 20px; border-radius: 8px;
                 border: 1px solid transparent; cursor: pointer; }
        .primary { background: #000; color: #fff; }
        .primary[disabled] { background: #fafafa; color: #999; border-color: #eaeaea;
                             cursor: default; }
        .secondary { background: #fff; color: #000; border-color: #eaeaea; }
        .secondary:hover { border-color: #999; }
        .quiet { background: none; border: 0; color: #666; font-size: 13px; padding: 8px;
                 text-decoration: underline; cursor: pointer; }
        .status { margin-top: 14px; font-size: 14px; color: #666; min-height: 20px; }
        .mark { margin: 18px 0 0; padding-top: 16px; border-top: 1px solid #eaeaea;
                font-size: 13px; color: #888; }
        button:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
        @media (prefers-contrast: more) { p, .status, .bar { color: #000; } }
      </style>
      <div class="veil">
        <div class="card" role="alertdialog" aria-modal="true"
             aria-labelledby="noscam-title" aria-describedby="noscam-detail">
          <div class="bar"><b>NoScam</b><span class="kind"></span></div>
          <div class="body">
            <h2 id="noscam-title" tabindex="-1"></h2>
            <p id="noscam-detail"></p>
            <div class="row">
              <button class="primary"></button>
              <button class="secondary">Cancel</button>
              <button class="quiet">Continue anyway</button>
            </div>
            <div class="status" role="status" aria-live="polite"></div>
            <p class="mark">Nothing has been sent.</p>
          </div>
        </div>
      </div>`;

    const kinds = { blocked: "stopped this", needs_approval: "paused this",
                    cool_off: "paused this" };
    root.querySelector(".kind").textContent = kinds[decision.disposition] || "on hold";
    root.querySelector("h2").textContent = decision.headline;
    root.querySelector("p").textContent = decision.detail;

    // Advice is fetched after the card is already up, so a slow model never
    // delays the thing that actually matters — stopping the action.
    if (decision.hold_id) {
      send({ kind: "noscam:advice", holdId: decision.hold_id }).then((reply) => {
        const advice = reply.ok && reply.data && reply.data.advice;
        if (!advice || !overlayHost) return;
        const line = document.createElement("p");
        line.className = "advice";
        line.textContent = advice;
        root.querySelector("p").after(line);
      });
    }
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

    // Keyboard and screen-reader behaviour. Someone who navigates by keyboard —
    // or who cannot see the card at all — must be able to understand it and get
    // out of it, and must not be able to tab past it onto the page underneath
    // and press the bank's own button.
    const focusables = [...root.querySelectorAll("button:not([disabled])")];
    const heading = root.querySelector("h2");
    heading.focus({ preventScroll: true });

    const onKey = (event) => {
      if (!overlayHost) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeOverlay();                      // Escape is "cancel", never "continue"
        return;
      }
      if (event.key !== "Tab") return;
      const live = focusables.filter((node) => !node.disabled);
      if (!live.length) return;
      const first = live[0];
      const last = live[live.length - 1];
      const active = root.activeElement;
      if (event.shiftKey && (active === first || active === heading)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      } else if (active === heading) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey, true);
    overlayHost.dataset.noscamKeyHandler = "1";
    overlayHost.__noscamRemoveKeys = () =>
      document.removeEventListener("keydown", onKey, true);
  };

  // --- interception --------------------------------------------------------

  const guard = async (action, proceed) => {
    const reply = await send({ kind: "noscam:check", action });
    if (!reply.ok) return proceed();          // service down: never break the page
    const decision = reply.data;
    if (decision.disposition === "allow") return proceed();

    // If running inside a child iframe, delegate the modal overlay to the top-level window
    // so it is not cramped or clipped inside a small checkout widget.
    if (typeof window !== "undefined" && window !== window.top) {
      const requestId = "req_" + Math.random().toString(36).slice(2);
      let resumed = false;

      const onResume = (event) => {
        if (!event.data || event.data.noscam !== true) return;
        if (event.data.kind === "noscam:child_resume" && event.data.requestId === requestId) {
          resumed = true;
          window.removeEventListener("message", onResume);
          proceed();
        }
      };
      window.addEventListener("message", onResume);

      try {
        window.top.postMessage({
          noscam: true,
          kind: "noscam:child_hold",
          requestId,
          decision,
        }, "*");

        // Fallback: If top window does not respond (e.g. strict sandbox), show locally after 1s
        setTimeout(() => {
          if (!resumed) {
            showOverlay(decision, { onContinue: proceed });
          }
        }, 1200);
        return;
      } catch {
        // window.top postMessage failed, fall back to local overlay
      }
    }

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
      if (passThrough) return;                 // decided a moment ago, as a click
      event.preventDefault();
      event.stopImmediatePropagation();

      const rawAmount = fieldValue(form, AMOUNT).replace(/[^\d.]/g, "");
      const payee = fieldValue(form, PAYEE);
      // What kind of money movement this really is. Both of these leave in a
      // way a bank cannot reverse, so they are not ordinary payments.
      let kind = "payment";
      const page = form.innerText + " " + document.title;
      if (CRYPTO_ADDRESS.test(payee) || CRYPTO_ADDRESS.test(form.innerText)) {
        kind = "crypto_transfer";
      } else if (GIFT_CARD_WORDS.test(page)) {
        kind = "gift_card_purchase";
      } else if (MANDATE_WORDS.test(page)) {
        // A standing instruction: the screen shows one debit, the approval
        // authorises every debit after it.
        kind = "upi_mandate_approval";
      } else if (COLLECT_WORDS.test(page) &&
                 (UPI_INTENT.test(payee) || UPI_INTENT.test(page))) {
        // Approving a request is paying, however the page words it.
        kind = "upi_collect_approval";
      }
      guard({
        type: kind,
        host: location.host,
        amount: rawAmount ? Number(rawAmount) : null,
        payee: payee || null,
        recurrence: (page.match(RECURRENCE) || [null])[0],
      }, () => {
        form.dataset.noscamCleared = "1";
        form.requestSubmit ? form.requestSubmit() : form.submit();
      });
    }, true);
  };

  // Real banking and payment pages usually do not submit a form at all — a
  // click runs fetch() and the money moves. Listening only for "submit" would
  // therefore miss almost every real payment, so the click itself is gated,
  // in the capture phase, before the page's own handler runs.
  const PAY_WORDS = /\b(pay|payment|transfer|send|remit|confirm|proceed|continue|authorise|authorize|approve|buy|subscribe|donate)\b/i;
  let passThrough = null;                 // the one click we have already decided

  const gateClicks = () => {
    document.addEventListener("click", (event) => {
      const button = event.target.closest &&
        event.target.closest("button, input[type=submit], input[type=button], [role=button], a.btn");
      if (!button || button === passThrough) {
        passThrough = null;
        return;
      }
      const label = (button.innerText || button.value || button.getAttribute("aria-label")
                     || button.getAttribute("title") || "");
      const form = button.closest("form");
      const scope = form || document;
      const hasAmountInput = [...scope.querySelectorAll("input")].some((input) =>
        AMOUNT.test(`${input.name} ${input.id} ${input.placeholder || ""}`) ||
        input.type === "number");
      const hasAmountInButton = CURRENCY_AMOUNT.test(label);
      const hasAmount = hasAmountInput || hasAmountInButton;
      if (!hasAmount) return;             // a "continue" button on an article is not a payment

      // The label is the usual signal, but plenty of real payment buttons are an
      // icon with no text at all. A submit button inside a form that takes an
      // amount is a payment button whatever it says, or doesn't.
      const submits = button.type === "submit" || button.tagName === "BUTTON" && form;
      if (!PAY_WORDS.test(label) && !(submits && !label.trim()) && !hasAmountInButton) return;

      event.preventDefault();
      event.stopImmediatePropagation();

      let rawAmount = fieldValue(scope, AMOUNT).replace(/[^\d.]/g, "");
      if (!rawAmount && hasAmountInButton) {
        const match = label.match(/[\$£€₹¥]\s*([\d,]+(\.\d+)?)|([\d,]+(\.\d+)?)\s*(usd|inr|eur|gbp|cad|aud)/i);
        if (match) rawAmount = (match[1] || match[3] || "").replace(/,/g, "");
      }
      const payee = fieldValue(scope, PAYEE);
      const page = (scope.innerText || "") + " " + document.title;
      let kind = "payment";
      if (CRYPTO_ADDRESS.test(payee) || CRYPTO_ADDRESS.test(page)) kind = "crypto_transfer";
      else if (GIFT_CARD_WORDS.test(page)) kind = "gift_card_purchase";
      else if (MANDATE_WORDS.test(page)) kind = "upi_mandate_approval";
      else if (COLLECT_WORDS.test(page) && UPI_INTENT.test(page + payee)) {
        kind = "upi_collect_approval";
      }

      guard({
        type: kind,
        host: location.host,
        amount: rawAmount ? Number(rawAmount) : null,
        payee: payee || null,
        recurrence: (page.match(RECURRENCE) || [null])[0],
      }, () => {
        // Replay the click we swallowed, once, and let it through.
        passThrough = button;
        if (form) form.dataset.noscamCleared = "1";
        button.click();
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

  // Things that cannot be reissued, changed or undone once they are on someone
  // else's server. The value never leaves the page: only the *kind* is sent to
  // the local service, so NoScam never learns anyone's card number.
  const luhn = (digits) => {
    let sum = 0;
    let double = false;
    for (let i = digits.length - 1; i >= 0; i -= 1) {
      let value = Number(digits[i]);
      if (double) { value *= 2; if (value > 9) value -= 9; }
      sum += value;
      double = !double;
    }
    return digits.length >= 13 && sum % 10 === 0;
  };

  const GIFT_CARD_WORDS = /(gift\s?card|e-?gift|apple\s?card|google\s?play\s?(card|code)|steam\s?(card|wallet)|amazon\s?(gift|claim\s?code)|itunes)/i;
  const UPI_INTENT = /upi:\/\/pay\?|[\w.\-]{3,}@(oksbi|okaxis|okhdfcbank|okicici|ybl|ibl|axl|paytm|upi)\b/i;
  const MANDATE_WORDS = /(autopay|auto-?debit|e-?mandate|\bmandate\b|standing instruction|recurring|subscribe|(each|every|per)\s(month|week|day|year)|monthly|weekly|annually|until cancelled)/i;
  const RECURRENCE = /\b(daily|weekly|fortnightly|monthly|quarterly|yearly|as presented)\b/i;
  const COLLECT_WORDS = /(collect\s?request|approve\s?(the\s?)?request|accept\s?(the\s?)?request|enter\s?(your\s?)?upi\s?pin|scan.{0,24}(receive|refund|prize|credit))/i;
  const CRYPTO_ADDRESS = /\b(0x[a-fA-F0-9]{40}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{25,62}|T[A-Za-z1-9]{33})\b/;

  const sensitiveKind = (raw) => {
    const value = String(raw || "").trim();
    const digits = value.replace(/[\s-]/g, "");
    if (/^\d{13,19}$/.test(digits) && luhn(digits)) return "card number";
    if (/^[2-9]\d{11}$/.test(digits)) return "Aadhaar number";
    if (/^[A-Z]{5}\d{4}[A-Z]$/.test(value.toUpperCase())) return "PAN";
    if (/^[A-Z]{4}0[A-Z0-9]{6}$/.test(value.toUpperCase())) return "bank IFSC code";
    // A gift card code read out over the phone is the whole theft.
    if (/^[A-Z0-9]{4}[- ]?[A-Z0-9]{4}[- ]?[A-Z0-9]{4}([- ]?[A-Z0-9]{4})?$/.test(value.toUpperCase())
        && /[A-Z]/.test(value.toUpperCase()) && value.length >= 14) return "gift card code";
    return null;
  };

  const wireSensitiveFields = (scope) => {
    for (const input of scope.querySelectorAll("input, textarea")) {
      if (input.dataset.noscamData) continue;
      input.dataset.noscamData = "1";
      const look = () => {
        if (input.dataset.noscamFlagged) return;
        const kind = sensitiveKind(input.value);
        if (!kind) return;
        input.dataset.noscamFlagged = "1";
        guard({ type: "sensitive_data_entry", host: location.host, data_kind: kind },
              () => {});
      };
      input.addEventListener("change", look);
      input.addEventListener("blur", look);
      input.addEventListener("paste", () => setTimeout(look, 0));
    }
  };

  // A page that is pretending to be a bank is worth saying so about the moment
  // it opens, rather than waiting for someone to type into it.
  const judgeThisPage = async () => {
    const reply = await send({ kind: "noscam:arrival", url: location.href });
    if (!reply.ok || !reply.data || reply.data.disposition === "allow") return;
    showOverlay(reply.data, { onContinue: () => {} });
  };

  const scan = () => {
    for (const form of document.querySelectorAll("form")) {
      if (looksLikePaymentForm(form)) wirePaymentForm(form);
    }
    wireSecretFields(document);
    wireSensitiveFields(document);
  };

  const start = () => {
    if (window.__noscamLoaded) return;      // never wire a page twice
    // The page's own copy stands down when the extension is installed, which
    // marks the page before any page script runs (marker.js).
    if (!inExtension && document.documentElement.getAttribute("data-noscam") === "extension") return;
    window.__noscamLoaded = inExtension ? "extension" : "page";
    scan();
    gateClicks();
    judgeThisPage();
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
