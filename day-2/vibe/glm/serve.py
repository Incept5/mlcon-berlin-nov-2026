#!/usr/bin/env python3
"""Serve the GDPR article explorer from ./site on port 7002.

    python3 serve.py                 # http://localhost:7002
    python3 serve.py --port 7003     # another port
    python3 serve.py --host 0.0.0.0  # share on the LAN (default is localhost only)
"""

import argparse
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "site"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always pick up a fresh gdpr.json
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}", flush=True)


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True  # restart straight after Ctrl-C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7002)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    with Server((args.host, args.port), Handler) as httpd:
        print(f"Serving {ROOT} → http://{args.host}:{args.port}  (Ctrl-C to stop)", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nBye")


if __name__ == "__main__":
    main()
