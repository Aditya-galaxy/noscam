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
