# LEGACY / DEV-ONLY: this hand-rolled http.server backend predates the
# Django migration and is superseded by plec_project (Django). It only ever
# talks to a standalone local SQLite file (plec.db) and is completely
# disconnected from the production database, which is PostgreSQL configured
# via the DATABASE_URL environment variable (see plec_project/settings.py).
# Running this script does not read from, write to, or otherwise affect
# production data. Kept for historical reference only — do not deploy this.
import http.server
import socketserver
import os
import sys
import re
import json
import sqlite3

PORT      = int(os.environ.get("PORT", 5000))
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "challenge")
DB_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plec.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apps.assessment.scorer   import score_attempt
from apps.assessment.reviewer import generate_review

# Auto-create the database on first run (needed on Heroku ephemeral dynos)
if not os.path.exists(DB_PATH):
    import create_db
    create_db.build()


def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _ensure_results_table():
    """Add assessment_results table to existing databases that pre-date the CRUD feature."""
    con = _db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS assessment_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            level_key        TEXT NOT NULL,
            score            INTEGER NOT NULL,
            grade            TEXT NOT NULL,
            tier_label       TEXT NOT NULL,
            milestones_done  INTEGER NOT NULL,
            milestones_total INTEGER NOT NULL,
            efficiency_label TEXT NOT NULL,
            bonus_earned     INTEGER NOT NULL DEFAULT 0,
            note             TEXT NOT NULL DEFAULT '',
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    con.close()

_ensure_results_table()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/api/modules":
            self._handle_modules()
        elif path == "/api/results":
            self._handle_results_list()
        elif re.match(r"^/api/results/\d+$", path):
            rid = int(path.rsplit("/", 1)[-1])
            self._handle_results_get(rid)
        elif path.startswith("/api/tips/"):
            module_id = path[len("/api/tips/"):]
            self._handle_tips(module_id)
        else:
            super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/api/assess":
            self._handle_assess()
        elif path == "/api/results":
            self._handle_results_create()
        else:
            self.send_error(404)

    # ── PUT ──────────────────────────────────────────────────────────────────

    def do_PUT(self):
        m = re.match(r"^/api/results/(\d+)/?$", self.path)
        if not m:
            self.send_error(404)
            return
        self._handle_results_update(int(m.group(1)))

    # ── DELETE ───────────────────────────────────────────────────────────────

    def do_DELETE(self):
        m = re.match(r"^/api/results/(\d+)/?$", self.path)
        if not m:
            self.send_error(404)
            return
        self._handle_results_delete(int(m.group(1)))

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_assess(self):
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

    def _handle_results_list(self):
        try:
            con = _db()
            cur = con.cursor()
            cur.execute("""
                SELECT id, level_key, score, grade, tier_label,
                       milestones_done, milestones_total,
                       efficiency_label, bonus_earned, note, created_at
                FROM   assessment_results
                ORDER  BY id DESC
            """)
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            self._json(200, {"results": rows})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_results_get(self, rid):
        try:
            con = _db()
            cur = con.cursor()
            cur.execute("""
                SELECT id, level_key, score, grade, tier_label,
                       milestones_done, milestones_total,
                       efficiency_label, bonus_earned, note, created_at
                FROM   assessment_results
                WHERE  id = ?
            """, (rid,))
            row = cur.fetchone()
            con.close()
            if row is None:
                self._json(404, {"error": "Not found"})
            else:
                self._json(200, dict(row))
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_results_create(self):
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "Invalid JSON"})
            return

        required = ("level_key", "score", "grade", "tier_label",
                    "milestones_done", "milestones_total",
                    "efficiency_label")
        for field in required:
            if field not in body:
                self._json(400, {"error": f"Missing field: {field}"})
                return

        try:
            con = _db()
            cur = con.cursor()
            cur.execute("""
                INSERT INTO assessment_results
                    (level_key, score, grade, tier_label,
                     milestones_done, milestones_total,
                     efficiency_label, bonus_earned, note)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                str(body["level_key"]),
                int(body["score"]),
                str(body["grade"]),
                str(body["tier_label"]),
                int(body["milestones_done"]),
                int(body["milestones_total"]),
                str(body["efficiency_label"]),
                int(body.get("bonus_earned", 0)),
                str(body.get("note", "")),
            ))
            new_id = cur.lastrowid
            con.commit()

            cur.execute("SELECT * FROM assessment_results WHERE id = ?", (new_id,))
            row = dict(cur.fetchone())
            con.close()
            self._json(201, row)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_results_update(self, rid):
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            self._json(400, {"error": "Invalid JSON"})
            return

        note = str(body.get("note", ""))
        try:
            con = _db()
            cur = con.cursor()
            cur.execute(
                "UPDATE assessment_results SET note = ? WHERE id = ?",
                (note, rid)
            )
            if cur.rowcount == 0:
                con.close()
                self._json(404, {"error": "Not found"})
                return
            con.commit()
            cur.execute("SELECT * FROM assessment_results WHERE id = ?", (rid,))
            row = dict(cur.fetchone())
            con.close()
            self._json(200, row)
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_results_delete(self, rid):
        try:
            con = _db()
            cur = con.cursor()
            cur.execute("DELETE FROM assessment_results WHERE id = ?", (rid,))
            if cur.rowcount == 0:
                con.close()
                self._json(404, {"error": "Not found"})
                return
            con.commit()
            con.close()
            self._json(200, {"deleted": rid})
        except Exception as e:
            self._json(500, {"error": str(e)})

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
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

if __name__ == "__main__":
    with ReusableTCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"PLeC serving on port {PORT}")
        httpd.serve_forever()
