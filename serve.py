import http.server
import socketserver
import os
import sys
import json
import sqlite3

PORT      = 5000
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "challenge")
DB_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plec.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apps.assessment.scorer   import score_attempt
from apps.assessment.reviewer import generate_review


def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/api/modules":
            self._handle_modules()
        elif path.startswith("/api/tips/"):
            module_id = path[len("/api/tips/"):]
            self._handle_tips(module_id)
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.rstrip("/") != "/api/assess":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)

        try:
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "Invalid JSON"})
            return

        level           = body.get("level", "")
        milestones_done = body.get("milestones_done", [])
        scan_count      = int(body.get("scan_count", 0))
        elapsed_ms      = int(body.get("elapsed_ms", 0))
        bonus_flags     = body.get("bonus_flags", {})

        scoring = score_attempt(
            level_key       = level,
            milestones_done = milestones_done,
            scan_count      = scan_count,
            elapsed_ms      = elapsed_ms,
            bonus_flags     = bonus_flags,
        )
        review = generate_review(scoring)
        result = {**scoring, **review}

        self._json(200, result)

    def _handle_modules(self):
        try:
            con = _db()
            cur = con.cursor()
            cur.execute("""
                SELECT m.id, m.title, m.type, m.html_file, m.difficulty,
                       m.description, m.role_title, m.sort_order,
                       COUNT(ms.id) AS milestone_count
                FROM   modules m
                LEFT JOIN milestones ms ON ms.module_id = m.id
                GROUP BY m.id
                ORDER BY m.sort_order
            """)
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            self._json(200, {"modules": rows})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_tips(self, module_id):
        try:
            con = _db()
            cur = con.cursor()
            cur.execute(
                "SELECT sort_order, icon, variant, tip_text FROM supervisor_tips "
                "WHERE module_id = ? ORDER BY sort_order",
                (module_id,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            if not rows:
                self._json(404, {"error": f"No tips found for module '{module_id}'"})
            else:
                self._json(200, {"module_id": module_id, "tips": rows})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    allow_reuse_port    = True

with ReusableTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"PLeC serving on port {PORT}")
    httpd.serve_forever()
