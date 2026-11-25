"""Serve the local dashboard and its JSON endpoints."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import sys
from threading import Thread
from time import sleep

from monitor import INTERVAL, Monitor
from scheduler import compare

WEB = Path(__file__).with_name("web")
ASSETS = {"/": ("index.html", "text/html"), "/style.css": ("style.css", "text/css"),
          "/dashboard.js": ("dashboard.js", "text/javascript")}


class Handler(BaseHTTPRequestHandler):
    def reply(self, body, kind, status=200):
        self.send_response(status)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def json(self, payload, status=200):
        self.reply(json.dumps(payload).encode(), "application/json", status)

    def do_GET(self):
        if self.path == "/api/monitor":
            self.json(self.server.monitor.report())
        elif self.path in ASSETS:
            filename, kind = ASSETS[self.path]
            self.reply((WEB / filename).read_bytes(), kind)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/schedule":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16000:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a scheduling request object.")
            result = compare(payload.get("workload"), payload.get("quantum"))
        except (ValueError, UnicodeError) as error:
            self.json({"error": str(error)}, 400)
            return
        self.json(result)

    def log_message(self, *_):
        pass


def sample_forever(monitor):
    while True:
        try:
            monitor.sample()
        except OSError:
            logging.exception("Could not collect the current sample")
        sleep(INTERVAL)


def main():
    if not sys.platform.startswith("linux"):
        sys.exit("Run this project on Linux. Windows users can run it inside Ubuntu on WSL.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        server.monitor = Monitor()
        Thread(target=sample_forever, args=(server.monitor,), daemon=True).start()
        print(f"Open http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
