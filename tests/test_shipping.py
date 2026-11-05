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


def test_custom_relay_url_travels_in_fragment_when_configured(tmp_path) -> None:
    custom_url = "https://relay.enterprise.internal"
    mgr = PairingManager(str(tmp_path), relay_url=custom_url)
    url = mgr.pairing_url()
    assert f"&s={custom_url}" in url
    assert "?s=" not in url


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


def test_not_a_store_package_off_windows() -> None:
    import os as _os
    if _os.name != "nt":
        assert paths.is_store_package() is False


def test_a_store_install_does_not_check_github_for_updates(monkeypatch) -> None:
    monkeypatch.delenv("NOSCAM_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(paths, "is_store_package", lambda: True)
    assert updates.enabled() is False
    monkeypatch.setattr(paths, "is_store_package", lambda: False)
    assert updates.enabled() is True


def test_msix_version_reserves_the_fourth_part_for_the_store() -> None:
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "build_msix", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_msix.py")
    build_msix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_msix)
    assert build_msix.store_version("1.2.1") == "1.2.1.0"
    assert build_msix.store_version("2.0") == "2.0.0.0"
    import xml.dom.minidom
    xml.dom.minidom.parseString(build_msix.manifest("A.B", "CN=X", "Me", "1.2.1.0"))


def test_a_windowed_app_with_no_console_gets_a_log_file(monkeypatch, tmp_path) -> None:
    """PyInstaller --noconsole starts with sys.stdout/sys.stderr = None, and
    uvicorn calls sys.stdout.isatty() while configuring logging — which killed
    the gate thread on Windows. attach_log must give both a real stream."""
    import sys
    import noscam

    monkeypatch.setenv("NOSCAM_DATA", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    noscam.attach_log()
    assert sys.stdout is not None and sys.stderr is not None
    assert sys.stdout.isatty() is False
    sys.stdout.flush()
    assert "started" in (tmp_path / "noscam.log").read_text()

    import uvicorn
    from uvicorn.config import Config
    Config(app="service.app:app", log_level="warning").configure_logging()   # the call that crashed


# --- the background guard -------------------------------------------------

def test_status_is_unprotected_until_the_extension_checks_in(monkeypatch) -> None:
    from service import guard
    monkeypatch.setattr(guard, "_extension_seen_at", None)
    monkeypatch.setattr(guard, "_remote_running", [])
    assert guard.status()["state"] == "unprotected"
    guard.saw_extension(now=1000.0)
    assert guard.status(now=1060.0)["state"] == "protected"
    # Quiet for longer than the extension's ping interval allows: say so.
    assert guard.status(now=1000.0 + guard.EXTENSION_FRESH_SECONDS + 1)["state"] == "unprotected"


def test_remote_control_tools_are_recognised_by_process_name() -> None:
    from service import guard
    names = ["explorer.exe", "anydesk.exe", "teamviewer_service.exe", "chrome.exe",
             "remoting_host.exe", "rustdesk", "notepad.exe"]
    assert guard.remote_access_in(names) == ["AnyDesk", "Chrome Remote Desktop", "RustDesk", "TeamViewer"]
    assert guard.remote_access_in(["code", "python3", "zoom.us"]) == []


def test_a_remote_tool_starting_alerts_once_and_changes_status(monkeypatch) -> None:
    from service import guard
    monkeypatch.setattr(guard, "_remote_running", [])
    monkeypatch.setattr(guard, "_last_alert", {})
    seen = []
    monkeypatch.setattr(guard, "_listeners", [lambda t, m: seen.append(t)])
    guard.check_remote_access(["anydesk.exe"])
    guard.check_remote_access(["anydesk.exe"])           # still running: no second alert
    assert seen == ["AnyDesk is running"]
    assert guard.status()["state"] == "warning"
    guard.check_remote_access([])
    assert guard.status()["remote_access_running"] == []


def test_alerts_describe_holds_and_ignore_allows() -> None:
    from service import guard
    assert guard.describe_decision({"type": "payment", "amount": 18000}, "allow", "x") is None
    title, msg = guard.describe_decision({"type": "payment", "amount": 18000, "host": "fake.example"},
                                         "needs_approval", "Paying someone new after a message")
    assert title == "NoScam held a ₹18,000 payment"
    assert "fake.example" in msg


def test_extension_check_in_and_status_endpoint(api) -> None:
    client, app_module = api
    from service import guard
    guard._extension_seen_at = None
    assert client.get("/status").json()["state"] in ("unprotected", "warning")
    client.get("/health?client=extension")
    assert client.get("/status").json()["extension_connected"] is True


def test_a_held_payment_raises_one_desktop_alert(api, monkeypatch) -> None:
    client, _ = api
    from datetime import datetime, timedelta, timezone
    from service import guard
    monkeypatch.setattr(guard, "_last_alert", {})
    seen = []
    monkeypatch.setattr(guard, "_listeners", [lambda t, m: seen.append(t)])
    at = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    payment = {"action": {"type": "payment", "host": "hdfc-secure.example", "amount": 18000,
                          "payee": "Rahul Verma"},
               "provenance": {"origin": "link", "source_host": "web.whatsapp.com", "at": at}}
    client.post("/gate/check", json=payment)
    client.post("/gate/check", json=payment)              # a retry: not a second pop-up
    assert seen == ["NoScam held a ₹18,000 payment"]
