"""
The two demo sites, on two ports, because the whole point is that *where a link
came from* matters.

  http://localhost:8790  — "Messages", a stand-in for WhatsApp or SMS-on-desktop
  http://localhost:8791  — a stand-in bank, with both an honest page and the
                           fake "safe account" page a scam sends people to

Run:  python3 demo/serve.py
"""

from __future__ import annotations

import functools
import http.server
import os
import socketserver
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
SITES = {
    8790: os.path.join(HERE, "messages"),
    8791: os.path.join(HERE, "bank"),
    # The content script, served so the demo pages can run it without the
    # extension installed — the same file, not a copy.
    8792: os.path.join(os.path.dirname(HERE), "extension"),
}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:      # keep the terminal readable
        pass


def serve(port: int, directory: str) -> None:
    handler = functools.partial(Quiet, directory=directory)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
            httpd.serve_forever()
    except OSError:
        # Almost always a second copy already running. That is an ordinary
        # thing to do by accident, and the answer is one sentence — not the
        # twenty lines of traceback a thread prints when it dies.
        # One call, not two: three of these run on their own threads, and two
        # prints each interleave into something nobody can read.
        name = os.path.basename(directory)
        print(f"  Port {port} is in use, so the {name} page did not start — "
              f"another copy of NoScam is probably already running.")


def main() -> None:
    for port, directory in SITES.items():
        threading.Thread(target=serve, args=(port, directory), daemon=True).start()
        print(f"  http://localhost:{port}  ->  {os.path.relpath(directory, HERE)}")
    print("\nDemo sites running. Ctrl-C to stop.")
    threading.Event().wait()


if __name__ == "__main__":
    main()
