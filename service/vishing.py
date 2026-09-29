"""Anti-vishing and anti-deepfake mutual challenge-response protocol.

Defeats AI voice synthesis, caller-ID spoofing, and social engineering attacks
(e.g. fake CEO wire fraud, fake police/arrest extortion, fake bank OTP demands).

Invariant:
Human voice and caller ID can be synthetically replicated; shared ephemeral
cryptographic state cannot.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
import time

DEFAULT_WINDOW_SECONDS = 120


def generate_time_code(
    secret: bytes,
    timestamp_ms: int | None = None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> str:
    """Generate a 6-digit rolling mutual authentication code (e.g. '123 456')."""
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    window = timestamp_ms // 1000 // window_seconds
    buffer = struct.pack(">Q", window)
    h = hmac.new(secret, buffer, hashlib.sha256).digest()

    offset = h[-1] & 0x0F
    binary = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    code_int = binary % 1_000_000
    code_str = f"{code_int:06d}"
    return f"{code_str[:3]} {code_str[3:]}"


def verify_time_code(
    secret: bytes,
    candidate_code: str,
    timestamp_ms: int | None = None,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    allowed_drift_windows: int = 1,
) -> bool:
    """Verify candidate code allowing for configurable time drift windows."""
    candidate_clean = candidate_code.replace(" ", "").strip()
    if len(candidate_clean) != 6 or not candidate_clean.isdigit():
        return False

    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    current_window = timestamp_ms // 1000 // window_seconds
    for offset in range(-allowed_drift_windows, allowed_drift_windows + 1):
        window_ms = (current_window + offset) * window_seconds * 1000
        expected = generate_time_code(secret, window_ms, window_seconds).replace(" ", "")
        if hmac.compare_digest(candidate_clean, expected):
            return True
    return False


def compute_challenge_response(secret: bytes, challenge: str) -> str:
    """Compute a 3-digit cryptographic response from a verbal challenge."""
    clean = challenge.strip().encode("utf-8")
    h = hmac.new(secret, clean, hashlib.sha256).digest()
    binary = ((h[0] & 0x7F) << 16) | ((h[1] & 0xFF) << 8) | (h[2] & 0xFF)
    resp_int = binary % 1000
    return f"{resp_int:03d}"


def verify_challenge_response(secret: bytes, challenge: str, response: str) -> bool:
    """Verify that spoken verbal response matches the challenge."""
    expected = compute_challenge_response(secret, challenge)
    return hmac.compare_digest(response.strip(), expected)


def derive_sas_from_session_key(session_key: bytes) -> str:
    """Derive a Short Authentication String (SAS) from an E2EE session key."""
    h = hmac.new(session_key, b"noscam_sas_vishing_guard", hashlib.sha256).digest()
    offset = h[-1] & 0x0F
    binary = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    code_int = binary % 1_000_000
    code_str = f"{code_int:06d}"
    return f"{code_str[:3]} {code_str[3:]}"


def generate_random_seed() -> bytes:
    """Generate 16 cryptographically random bytes for shared seed enrollment."""
    return secrets.token_bytes(16)
