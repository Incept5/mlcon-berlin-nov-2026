"""Serve the GDPR explorer:  python server.py   ->  http://localhost:7003"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

HERE = Path(__file__).parent
PORT = 7003
FILES = {"/": ("index.html", "text/html; charset=utf-8"),
         "/index.html": ("index.html", "text/html; charset=utf-8"),
         "/gdpr.json": ("gdpr.json", "application/json; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        entry = FILES.get(self.path.split("?")[0])
        if not entry or not (HERE / entry[0]).exists():
            self.send_error(404)
            return
        body = (HERE / entry[0]).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", entry[1])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"GDPR explorer on http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
