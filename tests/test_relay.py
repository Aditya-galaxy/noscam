"""
Tests for NoScam Zero-Knowledge E2EE Relay and Pairing.
"""

import json
import os
import shutil
import tempfile
import pytest
from service.relay import (
    PairingManager,
    encrypt_payload,
    decrypt_payload,
)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_pairing_manager_creates_and_persists_credentials(temp_dir):
    mgr = PairingManager(data_dir=temp_dir)
    creds1 = mgr.get_credentials()
    assert "channel_id" in creds1
    assert "shared_key" in creds1
    assert len(creds1["channel_id"]) == 32  # 16 bytes hex
    assert len(creds1["shared_key"]) == 64  # 32 bytes hex

    # Second call should load same credentials
    mgr2 = PairingManager(data_dir=temp_dir)
    creds2 = mgr2.get_credentials()
    assert creds1["channel_id"] == creds2["channel_id"]
    assert creds1["shared_key"] == creds2["shared_key"]


def test_encrypt_decrypt_payload_roundtrip():
    key = os.urandom(32).hex()
    data = {
        "hold_id": "hld_test123",
        "payee": "Alice Smith",
        "amount": 1250.50,
        "reason": "new_payee_after_message",
    }

    ciphertext = encrypt_payload(key, data)
    assert isinstance(ciphertext, str)
    assert ciphertext != json.dumps(data)

    decrypted = decrypt_payload(key, ciphertext)
    assert decrypted == data


def test_decrypt_with_wrong_key_fails():
    key1 = os.urandom(32).hex()
    key2 = os.urandom(32).hex()
    data = {"secret": "confidential_hold"}

    ciphertext = encrypt_payload(key1, data)

    with pytest.raises(Exception):
        decrypt_payload(key2, ciphertext)


def test_tampered_ciphertext_fails():
    import base64

    key = os.urandom(32).hex()
    data = {"amount": 100}
    ciphertext = encrypt_payload(key, data)

    # Modify raw bytes
    raw = bytearray(base64.b64decode(ciphertext))
    raw[-1] ^= 0x01
    tampered = base64.b64encode(raw).decode("ascii")

    with pytest.raises(Exception):
        decrypt_payload(key, tampered)


def test_forward_secure_v2_and_v1_backward_compatibility():
    import base64
    key = os.urandom(32).hex()
    data = {"hold_id": "hld_v2_test", "amount": 5000}

    # 1. Forward-secure V2 format
    v2_wire = encrypt_payload(key, data, forward_secure=True)
    raw_v2 = base64.b64decode(v2_wire)
    assert raw_v2[0] == 2  # V2 magic byte
    assert len(raw_v2) >= 1 + 16 + 12 + 16

    decrypted_v2 = decrypt_payload(key, v2_wire)
    assert decrypted_v2 == data

    # 2. Legacy V1 format
    v1_wire = encrypt_payload(key, data, forward_secure=False)
    decrypted_v1 = decrypt_payload(key, v1_wire)
    assert decrypted_v1 == data


def test_node_webcrypto_interoperability():
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")

    key_hex = os.urandom(32).hex()
    original_data = {"hold_id": "hold_interop_99", "verdict": "approve"}

    # Python encrypts with V2 forward secrecy
    py_enc = encrypt_payload(key_hex, original_data, forward_secure=True)

    # Node decrypts py_enc, and encrypts response with forward secrecy
    node_script = f"""
    const {{ webcrypto }} = require('node:crypto');
    const crypto = webcrypto;

    async function deriveSessionKey(baseKeyBytes, saltBytes) {{
      const baseKey = await crypto.subtle.importKey(
        "raw", baseKeyBytes, "HKDF", false, ["deriveKey"]
      );
      return crypto.subtle.deriveKey(
        {{ name: "HKDF", hash: "SHA-256", salt: saltBytes, info: new TextEncoder().encode("noscam_hold_session") }},
        baseKey,
        {{ name: "AES-GCM", length: 256 }},
        false,
        ["encrypt", "decrypt"]
      );
    }}

    async function decryptRelayPayload(keyHex, base64Wire) {{
      const keyBytes = new Uint8Array(keyHex.match(/.{{1,2}}/g).map(byte => parseInt(byte, 16)));
      const wireBytes = Uint8Array.from(atob(base64Wire), c => c.charCodeAt(0));

      if (wireBytes.length >= 45 && wireBytes[0] === 0x02) {{
        const salt = wireBytes.slice(1, 17);
        const iv = wireBytes.slice(17, 29);
        const data = wireBytes.slice(29);
        const sessionKey = await deriveSessionKey(keyBytes, salt);
        const decrypted = await crypto.subtle.decrypt(
          {{ name: "AES-GCM", iv }}, sessionKey, data
        );
        return JSON.parse(new TextDecoder().decode(decrypted));
      }}

      const iv = wireBytes.slice(0, 12);
      const data = wireBytes.slice(12);
      const cryptoKey = await crypto.subtle.importKey(
        "raw", keyBytes, "AES-GCM", false, ["decrypt"]
      );
      const decrypted = await crypto.subtle.decrypt(
        {{ name: "AES-GCM", iv }}, cryptoKey, data
      );
      return JSON.parse(new TextDecoder().decode(decrypted));
    }}

    async function encryptRelayPayload(keyHex, obj) {{
      const keyBytes = new Uint8Array(keyHex.match(/.{{1,2}}/g).map(byte => parseInt(byte, 16)));
      const salt = crypto.getRandomValues(new Uint8Array(16));
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const dataBytes = new TextEncoder().encode(JSON.stringify(obj));

      const sessionKey = await deriveSessionKey(keyBytes, salt);
      const encrypted = await crypto.subtle.encrypt(
        {{ name: "AES-GCM", iv }}, sessionKey, dataBytes
      );

      const combined = new Uint8Array(1 + 16 + 12 + encrypted.byteLength);
      combined[0] = 0x02;
      combined.set(salt, 1);
      combined.set(iv, 17);
      combined.set(new Uint8Array(encrypted), 29);

      let binary = "";
      for (let i = 0; i < combined.byteLength; i++) {{
        binary += String.fromCharCode(combined[i]);
      }}
      return btoa(binary);
    }}

    (async () => {{
      const dec = await decryptRelayPayload("{key_hex}", "{py_enc}");
      if (dec.hold_id !== "{original_data['hold_id']}") process.exit(1);

      const nodeEnc = await encryptRelayPayload("{key_hex}", {{ verdict: "deny", hold_id: dec.hold_id }});
      process.stdout.write(nodeEnc);
    }})();
    """
    proc = subprocess.run([node, "-e", node_script], capture_output=True, text=True, check=True)
    node_b64 = proc.stdout.strip()

    # Python decrypts Node's ciphertext
    dec_from_node = decrypt_payload(key_hex, node_b64)
    assert dec_from_node == {"verdict": "deny", "hold_id": original_data["hold_id"]}


