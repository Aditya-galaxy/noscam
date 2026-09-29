import time
import pytest
from service import vishing


def test_vishing_time_code_parity_and_drift():
    secret = bytes.fromhex("0123456789abcdef0123456789abcdef")
    t0 = 1700000000000

    code1 = vishing.generate_time_code(secret, timestamp_ms=t0, window_seconds=120)
    code2 = vishing.generate_time_code(secret, timestamp_ms=t0 + 30000, window_seconds=120)
    assert code1 == code2
    assert len(code1) == 7
    assert " " in code1

    # Next window
    code_next = vishing.generate_time_code(secret, timestamp_ms=t0 + 130000, window_seconds=120)
    assert code1 != code_next

    # Verification
    assert vishing.verify_time_code(secret, code1, timestamp_ms=t0, window_seconds=120)
    assert vishing.verify_time_code(secret, code1.replace(" ", ""), timestamp_ms=t0, window_seconds=120)
    assert vishing.verify_time_code(secret, code1, timestamp_ms=t0 + 100000, window_seconds=120, allowed_drift_windows=1)

    # Rejection
    assert not vishing.verify_time_code(secret, "999 999", timestamp_ms=t0, window_seconds=120)
    assert not vishing.verify_time_code(secret, "badcode", timestamp_ms=t0, window_seconds=120)


def test_vishing_challenge_response():
    secret = bytes.fromhex("0123456789abcdef0123456789abcdef")
    challenge = "492"

    resp = vishing.compute_challenge_response(secret, challenge)
    assert len(resp) == 3
    assert resp.isdigit()

    assert vishing.verify_challenge_response(secret, challenge, resp)
    assert not vishing.verify_challenge_response(secret, challenge, "000")
    assert not vishing.verify_challenge_response(secret, "493", resp)


def test_sas_derivation_from_session_key():
    session_key = bytes(range(1, 33))
    sas = vishing.derive_sas_from_session_key(session_key)
    assert len(sas) == 7
    assert sas.replace(" ", "").isdigit()


def test_random_seed_generation():
    seed = vishing.generate_random_seed()
    assert len(seed) == 16
    assert isinstance(seed, bytes)
