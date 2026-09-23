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

DEFAULT_RELAY_URL = "https://ntfy.sh"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(HERE)
DATA_DIR = os.environ.get("NOSCAM_DATA", os.path.join(ROOT_DIR, "data"))


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

    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "pairing.json")
        self._lock = threading.Lock()

    def get_credentials(self) -> dict:
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
        creds = self.get_credentials()
        prefix = base_url.rstrip("/") if base_url else ""
        return f"{prefix}/app/?r={creds['channel_id']}&k={creds['shared_key']}"


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
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def publish_hold(self, hold_data: dict) -> bool:
        """Encrypt and push a hold alert to the guardian's channel."""
        try:
            creds = self.pairing.get_credentials()
            channel_id = creds["channel_id"]
            shared_key = creds["shared_key"]

            ciphertext = encrypt_payload(shared_key, hold_data)
            topic = f"noscam_hold_{channel_id}"
            url = f"{self.relay_url}/{topic}"

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

    def _listen_loop(self) -> None:
        """Poll the reply topic for signed decisions from the paired guardian device."""
        creds = self.pairing.get_credentials()
        channel_id = creds["channel_id"]
        shared_key = creds["shared_key"]
        topic = f"noscam_reply_{channel_id}"
        poll_url = f"{self.relay_url}/{topic}/json?poll=1"

        seen_ids: set[str] = set()

        while self._running:
            try:
                with httpx.Client(timeout=8.0) as client:
                    resp = client.get(poll_url)
                    if resp.status_code == 200:
                        lines = resp.text.strip().split("\n")
                        for line in lines:
                            if not line:
                                continue
                            try:
                                msg = json.loads(line)
                                msg_id = msg.get("id")
                                if msg_id and msg_id in seen_ids:
                                    continue
                                raw_message = msg.get("message", "")
                                if raw_message:
                                    reply_data = decrypt_payload(shared_key, raw_message)
                                    hold_id = reply_data.get("hold_id")
                                    verdict = reply_data.get("verdict")
                                    if hold_id and verdict and self.on_verdict:
                                        self.on_verdict(hold_id, verdict)
                                if msg_id:
                                    seen_ids.add(msg_id)
                                    if len(seen_ids) > 1000:
                                        seen_ids.clear()
                            except Exception:
                                pass
            except Exception:
                pass
            time.sleep(2.0)
