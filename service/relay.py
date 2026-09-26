"""
Zero-Knowledge End-to-End Encrypted (E2EE) Remote Relay for NoScam.

Enables out-of-band guardian approvals across cellular/cross-network boundaries
via a stateless blind pub/sub relay (such as ntfy.sh or a self-hosted instance).

All sensitive financial data (payee names, amounts, hold reasons) is encrypted
on-device using AES-256-GCM before leaving the machine. The relay operator
never sees plaintext data.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time
from typing import Callable, Optional

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("noscam.relay")

# ntfy.sh by default; a household or an organisation that would rather not
# depend on a third party can point this at its own ntfy server.
DEFAULT_RELAY_URL = os.environ.get("NOSCAM_RELAY_URL", "https://ntfy.sh")


def encrypt_payload(key: bytes | str, data: dict) -> str:
    """Encrypt a dictionary payload with AES-256-GCM.
    Returns a base64 string with a 12-byte IV prepended to the ciphertext.
    """
    if isinstance(key, str):
        key = bytes.fromhex(key) if len(key) == 64 else key.encode("utf-8")
    if len(key) != 32:
        raise ValueError(f"AES-256 key must be exactly 32 bytes (got {len(key)})")

    nonce = secrets.token_bytes(12)
    payload_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, payload_bytes, None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_payload(key: bytes | str, wire_b64: str) -> dict:
    """Decrypt an AES-256-GCM base64 payload produced by encrypt_payload or WebCrypto."""
    if isinstance(key, str):
        key = bytes.fromhex(key) if len(key) == 64 else key.encode("utf-8")
    if len(key) != 32:
        raise ValueError(f"AES-256 key must be exactly 32 bytes (got {len(key)})")

    raw = base64.b64decode(wire_b64)
    if len(raw) < 12 + 16:
        raise ValueError("Ciphertext too short for AES-GCM IV and tag")

    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(decrypted_bytes.decode("utf-8"))


class PairingManager:
    """Manages persistent cryptographic pairing credentials for the household."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "pairing.json")
        self._lock = threading.Lock()

    def is_enabled(self) -> bool:
        """Remote approval is off until someone asks to pair a phone. Until then
        the service makes no outbound connection at all."""
        return os.path.exists(self.path)

    def disable(self) -> None:
        with self._lock:
            try:
                os.remove(self.path)
            except FileNotFoundError:
                pass

    def get_credentials(self) -> dict:
        """Read the pairing, creating one if there is none — so calling this is
        what turns remote approval on."""
        with self._lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, encoding="utf-8") as fh:
                        data = json.load(fh)
                    if "channel_id" in data and "shared_key" in data:
                        return data
                except Exception as exc:
                    logger.warning(f"Could not read pairing file: {exc}")

            # Generate new pairing credentials
            channel_id = secrets.token_hex(16)
            shared_key = secrets.token_hex(32)
            creds = {
                "channel_id": channel_id,
                "shared_key": shared_key,
                "created_at": time.time(),
            }
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(creds, fh, indent=2)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            return creds

    def pairing_url(self, base_url: str = "") -> str:
        # The key travels in the fragment, which a browser never sends to a
        # server, so it cannot end up in an access log or a proxy.
        creds = self.get_credentials()
        prefix = base_url.rstrip("/") if base_url else ""
        return f"{prefix}/app/#r={creds['channel_id']}&k={creds['shared_key']}"


class RelayClient:
    """Dispatches encrypted alerts and listens for remote guardian approvals."""

    def __init__(
        self,
        pairing_manager: PairingManager,
        relay_url: str = DEFAULT_RELAY_URL,
        on_verdict: Optional[Callable[[str, str], None]] = None,
    ):
        self.pairing = pairing_manager
        self.relay_url = relay_url.rstrip("/")
        self.on_verdict = on_verdict
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Listen for replies — only if a phone has been paired for remote use."""
        if self._running or not self.pairing.is_enabled():
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def publish_hold(self, hold_data: dict) -> bool:
        """Encrypt and push a hold alert to the guardian's channel."""
        if not self.pairing.is_enabled():
            return False
        try:
            creds = self.pairing.get_credentials()
            ciphertext = encrypt_payload(creds["shared_key"], hold_data)
            url = f"{self.relay_url}/noscam_hold_{creds['channel_id']}"
            with httpx.Client(timeout=4.0) as client:
                res = client.post(
                    url,
                    content=ciphertext,
                    headers={
                        "Title": "NoScam: Action Needs Approval",
                        "Priority": "urgent",
                        "Tags": "warning,shield",
                    },
                )
                return res.status_code in (200, 201)
        except Exception as exc:
            logger.debug(f"Failed to publish to remote relay (continuing locally): {exc}")
            return False

    def handle_line(self, line: str, shared_key: str) -> Optional[str]:
        """Apply one line of ntfy's JSON stream. Returns the message id, so a
        reconnect can resume after it instead of replaying the cache."""
        if not line.strip():
            return None
        try:
            msg = json.loads(line)
        except ValueError:
            return None
        if msg.get("event") != "message" or not msg.get("message"):
            return None                     # "open" and "keepalive" carry nothing
        try:
            reply = decrypt_payload(shared_key, msg["message"])
        except Exception:
            return msg.get("id")            # not ours, or tampered with: ignore it
        hold_id, verdict = reply.get("hold_id"), reply.get("verdict")
        if hold_id and verdict and self.on_verdict:
            self.on_verdict(hold_id, verdict)
        return msg.get("id")

    def _listen_loop(self) -> None:
        """Hold one streaming subscription open, rather than polling.

        Polling every couple of seconds would exceed ntfy's public rate limit
        within minutes. A stream is one request that stays open; ntfy sends
        keepalives, and on a dropped connection we back off and resume from the
        last message seen. `since` starts at the moment we started, so replies
        still cached on the relay from before a restart are not applied again —
        and a stale reply could only ever touch a hold that is still pending."""
        since = str(int(time.time()))
        backoff = 5.0
        while self._running and self.pairing.is_enabled():
            creds = self.pairing.get_credentials()
            url = f"{self.relay_url}/noscam_reply_{creds['channel_id']}/json"
            try:
                timeout = httpx.Timeout(10.0, read=90.0)   # keepalives arrive every ~45s
                with httpx.stream("GET", url, params={"since": since}, timeout=timeout) as resp:
                    if resp.status_code == 429:
                        raise RuntimeError("rate limited by relay")
                    resp.raise_for_status()
                    backoff = 5.0
                    for line in resp.iter_lines():
                        if not self._running:
                            return
                        last = self.handle_line(line, creds["shared_key"])
                        if last:
                            since = last
            except Exception as exc:
                logger.debug(f"Relay connection dropped ({exc}); retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300.0)
        self._running = False
