"""
What an installed copy depends on: where it keeps the household, that remote
approval makes no connection until asked, that a relay reply is applied only
through the same guards as a local one, and that the update check compares
versions rather than strings.
"""

from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from service import paths, updates
from service.relay import PairingManager, RelayClient, encrypt_payload


def test_data_dir_honours_the_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NOSCAM_DATA", str(tmp_path))
    assert paths.data_dir() == str(tmp_path)


def test_an_installed_copy_never_uses_the_working_directory(monkeypatch) -> None:
    monkeypatch.delenv("NOSCAM_DATA", raising=False)
    monkeypatch.setattr(paths, "is_checkout", lambda: False)
    monkeypatch.chdir("/")
    assert paths.data_dir() == paths.user_data_dir()
    assert not paths.data_dir().startswith("/data")


def test_the_phone_app_is_found() -> None:
    assert paths.resource("web", "index.html").endswith("index.html")
    import os
    assert os.path.exists(paths.resource("web", "index.html"))


def test_remote_approval_is_off_until_someone_asks(tmp_path) -> None:
    mgr = PairingManager(str(tmp_path))
    client = RelayClient(mgr)
    assert not mgr.is_enabled()
    client.start()
    assert client._thread is None                 # no connection was opened
    assert client.publish_hold({"id": "h"}) is False
    mgr.get_credentials()
    assert mgr.is_enabled()
    mgr.disable()
    assert not mgr.is_enabled()


def test_the_key_travels_in_the_fragment(tmp_path) -> None:
    url = PairingManager(str(tmp_path)).pairing_url()
    assert "#r=" in url and "?k=" not in url and "?r=" not in url


def test_relay_lines_apply_only_real_messages(tmp_path) -> None:
    seen = []
    mgr = PairingManager(str(tmp_path))
    key = mgr.get_credentials()["shared_key"]
    client = RelayClient(mgr, on_verdict=lambda h, v: seen.append((h, v)))

    assert client.handle_line(json.dumps({"event": "keepalive", "id": "k1"}), key) is None
    assert client.handle_line("not json", key) is None
    forged = encrypt_payload("00" * 32, {"hold_id": "h1", "verdict": "approve"})
    assert client.handle_line(json.dumps({"event": "message", "id": "m1",
                                          "message": forged}), key) == "m1"
    assert seen == []                             # wrong key: ignored, but resumable

    real = encrypt_payload(key, {"hold_id": "h1", "verdict": "approve"})
    assert client.handle_line(json.dumps({"event": "message", "id": "m2",
                                          "message": real}), key) == "m2"
    assert seen == [("h1", "approve")]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("NOSCAM_DATA", str(tmp_path))
    import service.app as app_module
    importlib.reload(app_module)
    monkeypatch.setattr(app_module.relay_client, "start", lambda: None)
    return TestClient(app_module.app), app_module


def test_pairing_is_switched_on_and_off_only_by_a_trusted_origin(api) -> None:
    client, app_module = api
    page = {"Origin": "https://scam.example"}
    assert client.post("/household/pairing", headers=page).status_code == 403
    assert client.get("/household/pairing/status").json()["enabled"] is False

    on = client.post("/household/pairing").json()
    assert on["pairing_url"].startswith("/app/#r=")
    assert client.get("/household/pairing/status").json()["enabled"] is True

    assert client.delete("/household/pairing", headers=page).status_code == 403
    client.delete("/household/pairing")
    assert client.get("/household/pairing/status").json()["enabled"] is False


def test_version_endpoint(api) -> None:
    client, _ = api
    body = client.get("/version").json()
    assert body["current"] == updates.__version__


@pytest.mark.parametrize("candidate,current,newer", [
    ("1.10.0", "1.9.9", True),
    ("v1.2.0", "1.1.0", True),
    ("1.1.0", "1.1.0", False),
    ("1.0.9", "1.1.0", False),
    ("garbage", "1.1.0", False),
])
def test_versions_compare_as_numbers(candidate, current, newer) -> None:
    assert updates.is_newer(candidate, current) is newer
