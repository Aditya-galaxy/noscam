"""
Start everything, with one command.

    python3 noscam.py

Judges, and anyone else who wants to see this work, should not have to run three
terminals and read a README first. This starts the gate, the stand-in demo
sites, seeds a household, prints the four links that matter, and opens the first
one. Ctrl-C stops all of it.

    --no-demo     just the gate and the phone app (for real use)
    --no-open     don't open a browser
    --port 8787   where the gate listens
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BANNER = """
  ███  NoScam
       A message cannot authorise your money.
"""


def start_gate(port: int, lan: bool = False) -> threading.Thread:
    import uvicorn

    from service.app import app

    config = uvicorn.Config(app, host="0.0.0.0" if lan else "127.0.0.1",  # noqa: S104
                            port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def start_demo_sites() -> None:
    from demo.serve import SITES, serve

    for port, directory in SITES.items():
        threading.Thread(target=serve, args=(port, directory), daemon=True).start()


def lan_address() -> str:
    """This machine's address on the local network, found by asking the routing
    table rather than by guessing at interface names."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))   # no packet is sent
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def wait_for(port: int, seconds: float = 10.0) -> bool:
    import socket

    deadline = time.time() + seconds
    while time.time() < deadline:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def seed(port: int) -> None:
    import json
    import urllib.request

    from demo.seed import KNOWN_PAYEES, LIMITS

    def call(method: str, path: str, body: dict | None = None) -> None:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                         method=method,
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=5).read()

    call("PUT", "/limits", LIMITS)
    call("POST", "/household/payees", {"payees": KNOWN_PAYEES})
    call("POST", "/household/reset")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start NoScam.")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-demo", action="store_true",
                        help="skip the stand-in messenger and bank")
    parser.add_argument("--no-open", action="store_true", help="don't open a browser")
    parser.add_argument("--lan", action="store_true",
                        help="let a phone on the same Wi-Fi reach this. Off by default: "
                             "loopback-only is the safer thing to be when nobody asked.")
    parser.add_argument("--tray", action="store_true",
                        help="run with a system tray/menu bar icon (requires pystray and pillow)")
    parser.add_argument("--headless", action="store_true",
                        help="force headless console mode without tray icon")
    args = parser.parse_args()

    print(BANNER)
    if args.lan:
        # The service must be told before it starts: from that moment, anything
        # arriving from another device has to prove it belongs here.
        os.environ["NOSCAM_LAN"] = "1"
    start_gate(args.port, lan=args.lan)
    if not wait_for(args.port):
        print(f"  The gate could not start on port {args.port}. Is something else using it?")
        return 1
    print(f"  gate            http://127.0.0.1:{args.port}")
    if args.lan:
        from service.app import household_token

        print(f"  phone / tablet  http://{lan_address()}:{args.port}"
              f"/app/?t={household_token()}")
        print("                  ^ open this on the phone, once. It is the only "
              "thing that lets another device answer.")
        print("                  If the phone cannot reach it, macOS is blocking "
              "incoming\n                  connections for Python: System Settings → "
              "Network →\n                  Firewall → Options → allow it. Windows asks "
              "the first time.")
    else:
        print(f"  phone / tablet  http://127.0.0.1:{args.port}/app/")
        print("                  (a real phone needs --lan)")

    if not args.no_demo:
        start_demo_sites()
        try:
            seed(args.port)
        except Exception as exc:                       # the demo is optional, the gate is not
            print(f"  (could not seed the demo household: {exc})")
        print("  the scam         http://localhost:8790   ← start here")
        print("  their own bank   http://localhost:8791")

    if os.environ.get("GEMINI_API_KEY"):
        print("\n  Advice line on (Gemini). The decision is still made without it.")
    else:
        print("\n  No GEMINI_API_KEY: the advice line is off and the deterministic\n"
              "  explanation is shown instead. Everything else works.")

    if not args.no_open:
        webbrowser.open("http://localhost:8790" if not args.no_demo
                        else f"http://127.0.0.1:{args.port}/app/")

    stop_event = threading.Event()
    is_frozen = getattr(sys, "frozen", False)
    use_tray = (args.tray or is_frozen) and not args.headless

    if use_tray:
        from service.tray import is_available, run_tray

        if is_available():
            print("  Running in system tray. Use tray menu to open dashboard or exit.\n")
            try:
                run_tray(args.port, on_quit=stop_event.set, lan=args.lan)
            except KeyboardInterrupt:
                pass
            print("\n  Stopped.")
            return 0
        elif args.tray:
            print("  Note: pystray or Pillow not installed. Running in console mode.")

    print("\n  Ctrl-C to stop.\n")
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
