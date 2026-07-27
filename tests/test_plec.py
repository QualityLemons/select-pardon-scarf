"""
PLeC Automated Test Suite
=========================
Covers: database integrity, scoring logic, review generation, and HTTP API endpoints.

LEGACY / DEV-ONLY: this suite predates the Django migration. `TestDatabase`
below builds and inspects a throwaway local SQLite file (test_plec.db, via
create_db.py) — it does not touch and is unrelated to the production
database, which is PostgreSQL configured via DATABASE_URL. It does not
exercise the Django views, auth, or /api/results endpoints; see
apps/accounts/tests.py for those.

Run from the project root:
    python -m pytest tests/ -v
    -- or --
    python -m unittest discover -s tests -v
"""

import sys
import os
import json
import sqlite3
import unittest
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import create_db
from apps.assessment.scorer   import score_attempt
from apps.assessment.reviewer import generate_review


# ── Helpers ─────────────────────────────────────────────────────────────────

TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_plec.db")


def _make_test_db():
    original = create_db.DB_PATH
    create_db.DB_PATH = TEST_DB
    create_db.build()
    create_db.DB_PATH = original
    return TEST_DB


def _db():
    con = sqlite3.connect(TEST_DB)
    con.row_factory = sqlite3.Row
    return con


# ══════════════════════════════════════════════════════════════════════════════
#  1. DATABASE INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabase(unittest.TestCase):
    """Verify the database is created correctly and contains expected data."""

    @classmethod
    def setUpClass(cls):
        _make_test_db()
        cls.con = _db()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        for suffix in ("", "-shm", "-wal", "-journal"):
            path = TEST_DB + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_all_tables_exist(self):
        """All six schema tables must be present after create_db.build()."""
        cur = self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        # sqlite_sequence is an SQLite internal table created by AUTOINCREMENT — exclude it
        tables = {r["name"] for r in cur.fetchall() if not r["name"].startswith("sqlite_")}
        expected = {
            "modules", "milestones", "efficiency_thresholds",
            "bonus_criteria", "supervisor_tips", "grade_descriptors",
            "assessment_results",
        }
        self.assertEqual(expected, tables)

    def test_module_count(self):
        """Database must contain exactly 11 modules."""
        count = self.con.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        self.assertEqual(11, count)

    def test_milestone_count(self):
        """Database must contain at least 38 milestones (6 challenge levels × 5-7 each)."""
        count = self.con.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]
        self.assertGreaterEqual(count, 38)

    def test_supervisor_tips_count(self):
        """Database must contain at least 56 supervisor tips."""
        count = self.con.execute("SELECT COUNT(*) FROM supervisor_tips").fetchone()[0]
        self.assertGreaterEqual(count, 56)

    def test_grade_descriptors_count(self):
        """All five grade bands (A-F) must be present."""
        count = self.con.execute("SELECT COUNT(*) FROM grade_descriptors").fetchone()[0]
        self.assertEqual(5, count)

    def test_all_modules_have_html_file(self):
        """Every module row must have a non-empty html_file value."""
        cur = self.con.execute("SELECT id, html_file FROM modules")
        for row in cur.fetchall():
            self.assertTrue(row["html_file"], f"Module '{row['id']}' has no html_file")

    def test_module_types_valid(self):
        """Every module type must be one of: challenge, lesson, tool."""
        valid = {"challenge", "lesson", "tool"}
        cur = self.con.execute("SELECT id, type FROM modules")
        for row in cur.fetchall():
            self.assertIn(row["type"], valid,
                          f"Module '{row['id']}' has invalid type '{row['type']}'")

    def test_supervisor_tip_variants_valid(self):
        """Every supervisor tip variant must be one of the five allowed values."""
        valid = {"default", "warn", "danger", "good", "purple"}
        cur = self.con.execute("SELECT id, variant FROM supervisor_tips")
        for row in cur.fetchall():
            self.assertIn(row["variant"], valid,
                          f"Tip {row['id']} has invalid variant '{row['variant']}'")

    def test_each_challenge_has_milestones(self):
        """All six challenge levels must have at least 5 milestones each."""
        challenge_ids = ["level1", "level2", "level3", "level4", "level5", "level6"]
        for level in challenge_ids:
            count = self.con.execute(
                "SELECT COUNT(*) FROM milestones WHERE module_id = ?", (level,)
            ).fetchone()[0]
            self.assertGreaterEqual(count, 5, f"{level} has fewer than 5 milestones")

    def test_efficiency_thresholds_present(self):
        """All six challenge levels must have efficiency thresholds."""
        count = self.con.execute(
            "SELECT COUNT(*) FROM efficiency_thresholds"
        ).fetchone()[0]
        self.assertEqual(6, count)

    def test_rebuild_is_idempotent(self):
        """Running create_db.build() twice must produce identical row counts."""
        original = create_db.DB_PATH
        create_db.DB_PATH = TEST_DB

        before = self.con.execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        create_db.build()
        after = _db().execute("SELECT COUNT(*) FROM modules").fetchone()[0]
        self.assertEqual(before, after)

        create_db.DB_PATH = original


# ══════════════════════════════════════════════════════════════════════════════
#  2. SCORING LOGIC
# ══════════════════════════════════════════════════════════════════════════════

class TestScorer(unittest.TestCase):
    """Verify scoring calculations for all grade bands."""

    def test_perfect_score_level1(self):
        """All milestones + exceptional scan count → score ≥ 90, grade A."""
        result = score_attempt(
            level_key="level1",
            milestones_done=["m1", "m2", "m3", "m4", "m5"],
            scan_count=50,
            elapsed_ms=10000,
        )
        self.assertGreaterEqual(result["score"], 90)
        self.assertEqual("A", result["grade"])

    def test_zero_milestones_gives_low_score(self):
        """No milestones completed must produce a score below 45 (grade F or D)."""
        result = score_attempt(
            level_key="level1",
            milestones_done=[],
            scan_count=5000,
            elapsed_ms=999999,
        )
        self.assertLess(result["score"], 45)

    def test_grade_boundaries(self):
        """Score-to-grade mapping must match documented boundaries."""
        cases = [
            (95, "A"), (90, "A"),
            (89, "B"), (75, "B"),
            (74, "C"), (60, "C"),
            (59, "D"), (45, "D"),
            (44, "F"), (0,  "F"),
        ]
        from apps.assessment.scorer import _grade
        for score, expected in cases:
            self.assertEqual(expected, _grade(score),
                             f"_grade({score}) should be {expected}")

    def test_score_capped_at_100(self):
        """Score must never exceed 100 regardless of input."""
        result = score_attempt(
            level_key="level1",
            milestones_done=["m1", "m2", "m3", "m4", "m5"],
            scan_count=1,
            elapsed_ms=100,
            bonus_flags={"all_fc": True, "fault_tested": True},
        )
        self.assertLessEqual(result["score"], 100)

    def test_unknown_level_returns_grade_f(self):
        """An unrecognised level key must return score=0 and grade=F."""
        result = score_attempt(
            level_key="nonexistent_level",
            milestones_done=["m1"],
            scan_count=100,
            elapsed_ms=5000,
        )
        self.assertEqual(0, result["score"])
        self.assertEqual("F", result["grade"])

    def test_bonus_score_capped_at_5(self):
        """Bonus score must not exceed 5 points even if multiple bonuses earned."""
        result = score_attempt(
            level_key="level3",
            milestones_done=[],
            scan_count=1,
            elapsed_ms=100,
            bonus_flags={"all_fc": True},
        )
        self.assertLessEqual(result["bonus_score"], 5)

    def test_milestone_detail_completeness(self):
        """milestone_detail must contain one entry per milestone in the level."""
        result = score_attempt(
            level_key="level1",
            milestones_done=["m1"],
            scan_count=300,
            elapsed_ms=60000,
        )
        self.assertEqual(5, len(result["milestone_detail"]))

    def test_partial_milestones_counted_correctly(self):
        """milestones_completed must exactly match number of valid IDs submitted."""
        result = score_attempt(
            level_key="level1",
            milestones_done=["m1", "m3"],
            scan_count=300,
            elapsed_ms=60000,
        )
        self.assertEqual(2, result["milestones_completed"])

    def test_all_levels_scoreable(self):
        """score_attempt must return a valid result for all six challenge levels."""
        levels = {
            "level1": ["m1", "m2", "m3", "m4", "m5"],
            "level2": ["m1", "m2", "m3", "m4", "m5"],
            "level3": ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
            "level4": ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
            "level5": ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
            "level6": ["m1", "m2", "m3", "m4", "m5", "m6", "m7"],
        }
        for level, milestones in levels.items():
            result = score_attempt(level, milestones, 100, 30000)
            self.assertIn("score", result, f"{level} result missing 'score' key")
            self.assertIn(result["grade"], "ABCDF",
                          f"{level} returned invalid grade '{result['grade']}'")

    def test_efficiency_labels(self):
        """Each efficiency band must return the correct label."""
        cases = [
            (50,   "Exceptional"),
            (400,  "Proficient"),
            (800,  "Satisfactory"),
            (1500, "Needs Improvement"),
            (9999, "Unsatisfactory"),
        ]
        for scans, expected_label in cases:
            result = score_attempt("level1", [], scans, 60000)
            self.assertEqual(expected_label, result["efficiency_label"],
                             f"scan_count={scans} should give '{expected_label}'")


# ══════════════════════════════════════════════════════════════════════════════
#  3. REVIEW GENERATION
# ══════════════════════════════════════════════════════════════════════════════

class TestReviewer(unittest.TestCase):
    """Verify the review text generator produces correctly shaped output."""

    def _review(self, level, milestones, scans, elapsed=60000, bonus=None):
        scoring = score_attempt(level, milestones, scans, elapsed, bonus or {})
        return generate_review(scoring)

    def test_review_has_required_keys(self):
        """generate_review must always return all five required keys."""
        review = self._review("level1", ["m1", "m2", "m3", "m4", "m5"], 100)
        for key in ("tier", "tier_label", "paragraph_1", "paragraph_2",
                    "paragraph_3", "summary_line"):
            self.assertIn(key, review, f"Review missing key: '{key}'")

    def test_exceptional_tier_label(self):
        """Score ≥ 90 must produce tier_label 'Exceptional'."""
        review = self._review("level1", ["m1", "m2", "m3", "m4", "m5"], 50)
        self.assertEqual("Exceptional", review["tier_label"])

    def test_fail_tier_label(self):
        """Score < 45 must produce tier_label 'Unsatisfactory'."""
        review = self._review("level1", [], 9999)
        self.assertEqual("Unsatisfactory", review["tier_label"])

    def test_paragraphs_are_non_empty_strings(self):
        """All three paragraphs must be non-empty strings for any valid input."""
        for level in ["level1", "level3", "level6"]:
            review = self._review(level, ["m1", "m2"], 500)
            for key in ("paragraph_1", "paragraph_2", "paragraph_3"):
                self.assertIsInstance(review[key], str)
                self.assertGreater(len(review[key]), 10,
                                   f"{key} is too short for {level}")

    def test_summary_line_contains_score(self):
        """summary_line must include the numeric score."""
        scoring = score_attempt("level1", ["m1", "m2", "m3", "m4", "m5"], 100, 20000)
        review = generate_review(scoring)
        self.assertIn(str(scoring["score"]), review["summary_line"])

    def test_all_tiers_reachable(self):
        """All five tier labels must be reachable through scoring inputs."""
        # Weights for level1: m1=15, m2=25, m3=15, m4=25, m5=20 (total 100)
        # milestone_score = round(earned/100 * 80); eff thresholds: exc≤300, prof≤600, sat≤1200, poor≤2400
        tiers_seen = set()
        test_cases = [
            # Exceptional  : all 5 milestones (ms=80) + exceptional eff (15) = 95
            ("level1", ["m1","m2","m3","m4","m5"], 50),
            # Proficient   : m1+m2+m3+m4=80 (ms=64) + proficient eff (11) = 75
            ("level1", ["m1","m2","m3","m4"],       400),
            # Satisfactory : m1+m2+m4=65 (ms=52) + proficient eff (11) = 63
            ("level1", ["m1","m2","m4"],             400),
            # Needs Improv : m1+m2+m3=55 (ms=44) + poor eff (3) = 47
            ("level1", ["m1","m2","m3"],             1500),
            # Unsatisfactory: no milestones, worst eff = 0
            ("level1", [],                           9999),
        ]
        for level, ms, scans in test_cases:
            review = self._review(level, ms, scans)
            tiers_seen.add(review["tier_label"])
        self.assertEqual(
            {"Exceptional","Proficient","Satisfactory","Needs Improvement","Unsatisfactory"},
            tiers_seen,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  4. HTTP API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIEndpoints(unittest.TestCase):
    """
    Start serve.py in a background thread and verify HTTP responses.
    Uses a temporary test database to avoid touching plec.db.
    """

    PORT = 15001

    @classmethod
    def setUpClass(cls):
        _make_test_db()

        import serve as serve_mod
        # Point the server at the test database
        serve_mod.DB_PATH = TEST_DB

        cls._server = serve_mod.ReusableTCPServer(("127.0.0.1", cls.PORT), serve_mod.Handler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def _get(self, path):
        url = f"http://127.0.0.1:{self.PORT}{path}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, json.loads(r.read())

    def _post(self, path, body):
        url  = f"http://127.0.0.1:{self.PORT}{path}"
        data = json.dumps(body).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())

    def _put(self, path, body):
        url  = f"http://127.0.0.1:{self.PORT}{path}"
        data = json.dumps(body).encode()
        req  = urllib.request.Request(url, data=data,
                                      headers={"Content-Type": "application/json"},
                                      method="PUT")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())

    def _delete(self, path):
        url = f"http://127.0.0.1:{self.PORT}{path}"
        req = urllib.request.Request(url, method="DELETE")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())

    _RESULT_BODY = {
        "level_key":        "level1",
        "score":            85,
        "grade":            "B",
        "tier_label":       "Proficient",
        "milestones_done":  4,
        "milestones_total": 5,
        "efficiency_label": "Exceptional",
        "bonus_earned":     0,
    }

    def test_modules_endpoint_returns_200(self):
        """/api/modules must respond with HTTP 200."""
        status, _ = self._get("/api/modules")
        self.assertEqual(200, status)

    def test_modules_endpoint_structure(self):
        """/api/modules must return a JSON object with a 'modules' list of 11 items."""
        _, data = self._get("/api/modules")
        self.assertIn("modules", data)
        self.assertEqual(11, len(data["modules"]))

    def test_modules_contain_required_fields(self):
        """Each module in /api/modules must include id, title, type, and html_file."""
        _, data = self._get("/api/modules")
        for mod in data["modules"]:
            for field in ("id", "title", "type", "html_file"):
                self.assertIn(field, mod, f"Module missing field '{field}'")

    def test_tips_endpoint_valid_module(self):
        """/api/tips/level1 must return HTTP 200 and a non-empty tips list."""
        status, data = self._get("/api/tips/level1")
        self.assertEqual(200, status)
        self.assertIn("tips", data)
        self.assertGreater(len(data["tips"]), 0)

    def test_tips_endpoint_invalid_module(self):
        """/api/tips/nonexistent must return HTTP 404."""
        url = f"http://127.0.0.1:{self.PORT}/api/tips/nonexistent"
        try:
            urllib.request.urlopen(url, timeout=5)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(404, e.code)

    def test_assess_endpoint_valid_submission(self):
        """/api/assess must return HTTP 200 with score and grade for a valid body."""
        status, data = self._post("/api/assess", {
            "level": "level1",
            "milestones_done": ["m1", "m2", "m3", "m4", "m5"],
            "scan_count": 200,
            "elapsed_ms": 45000,
        })
        self.assertEqual(200, status)
        self.assertIn("score", data)
        self.assertIn("grade", data)

    def test_assess_endpoint_score_range(self):
        """/api/assess score must be an integer between 0 and 100."""
        _, data = self._post("/api/assess", {
            "level": "level1",
            "milestones_done": ["m1", "m2"],
            "scan_count": 800,
            "elapsed_ms": 120000,
        })
        self.assertIsInstance(data["score"], int)
        self.assertGreaterEqual(data["score"], 0)
        self.assertLessEqual(data["score"], 100)

    def test_assess_endpoint_invalid_json(self):
        """/api/assess must return HTTP 400 when given malformed JSON."""
        url = f"http://127.0.0.1:{self.PORT}/api/assess"
        req = urllib.request.Request(url, data=b"not-json",
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(400, e.code)

    def test_assess_returns_review_paragraphs(self):
        """/api/assess response must include review paragraph_1."""
        _, data = self._post("/api/assess", {
            "level": "level1",
            "milestones_done": ["m1", "m2", "m3", "m4", "m5"],
            "scan_count": 100,
            "elapsed_ms": 20000,
        })
        self.assertIn("paragraph_1", data)
        self.assertGreater(len(data["paragraph_1"]), 0)

    def test_tips_each_level_has_tips(self):
        """Every challenge level and tool module must have at least one supervisor tip."""
        modules = ["level1","level2","level3","level4","level5","level6","multimeter"]
        for mod in modules:
            status, data = self._get(f"/api/tips/{mod}")
            self.assertEqual(200, status,    f"/api/tips/{mod} returned {status}")
            self.assertGreater(len(data["tips"]), 0, f"{mod} has no tips")

    # ── CRUD: CREATE ──────────────────────────────────────────────────────────

    def test_results_create_returns_201(self):
        """POST /api/results must return HTTP 201 with the new record including an id."""
        status, data = self._post("/api/results", self._RESULT_BODY)
        self.assertEqual(201, status)
        self.assertIn("id", data)
        self.assertIsInstance(data["id"], int)

    def test_results_create_persists_fields(self):
        """POST /api/results must persist all submitted fields and return them."""
        _, data = self._post("/api/results", self._RESULT_BODY)
        self.assertEqual("level1",     data["level_key"])
        self.assertEqual(85,           data["score"])
        self.assertEqual("B",          data["grade"])
        self.assertEqual("Proficient", data["tier_label"])
        self.assertEqual(4,            data["milestones_done"])
        self.assertEqual(5,            data["milestones_total"])

    def test_results_create_missing_field_returns_400(self):
        """POST /api/results without required fields must return HTTP 400."""
        url = f"http://127.0.0.1:{self.PORT}/api/results"
        req = urllib.request.Request(url,
                                     data=b'{"score":80}',
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(400, e.code)

    # ── CRUD: READ ────────────────────────────────────────────────────────────

    def test_results_list_returns_200(self):
        """GET /api/results must return HTTP 200 with a 'results' list."""
        status, data = self._get("/api/results")
        self.assertEqual(200, status)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_results_list_contains_created_record(self):
        """A result created via POST must appear in GET /api/results."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        new_id = created["id"]
        _, list_data = self._get("/api/results")
        ids = [r["id"] for r in list_data["results"]]
        self.assertIn(new_id, ids)

    def test_results_get_single_returns_200(self):
        """GET /api/results/:id must return HTTP 200 with the correct record."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        status, data = self._get(f"/api/results/{created['id']}")
        self.assertEqual(200, status)
        self.assertEqual(created["id"], data["id"])
        self.assertEqual(85, data["score"])

    def test_results_get_nonexistent_returns_404(self):
        """GET /api/results/999999 must return HTTP 404."""
        url = f"http://127.0.0.1:{self.PORT}/api/results/999999"
        try:
            urllib.request.urlopen(url, timeout=5)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(404, e.code)

    def test_results_list_ordered_newest_first(self):
        """GET /api/results must return records newest-first (higher id appears first)."""
        _, r1 = self._post("/api/results", self._RESULT_BODY)
        body2 = dict(self._RESULT_BODY)
        body2["score"] = 50
        _, r2 = self._post("/api/results", body2)
        # r2 has a higher id than r1 and must appear earlier in the list
        self.assertGreater(r2["id"], r1["id"])
        _, list_data = self._get("/api/results")
        ids = [r["id"] for r in list_data["results"]]
        self.assertLess(ids.index(r2["id"]), ids.index(r1["id"]))

    # ── CRUD: UPDATE ──────────────────────────────────────────────────────────

    def test_results_update_note_returns_200(self):
        """PUT /api/results/:id must return HTTP 200 with the updated note."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        rid = created["id"]
        status, data = self._put(f"/api/results/{rid}", {"note": "Good session."})
        self.assertEqual(200, status)
        self.assertEqual("Good session.", data["note"])

    def test_results_update_note_persists(self):
        """A note saved via PUT must be visible on subsequent GET."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        rid = created["id"]
        self._put(f"/api/results/{rid}", {"note": "Persisted note."})
        _, data = self._get(f"/api/results/{rid}")
        self.assertEqual("Persisted note.", data["note"])

    def test_results_update_nonexistent_returns_404(self):
        """PUT /api/results/999999 must return HTTP 404."""
        url = f"http://127.0.0.1:{self.PORT}/api/results/999999"
        req = urllib.request.Request(url,
                                     data=b'{"note":"x"}',
                                     headers={"Content-Type": "application/json"},
                                     method="PUT")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(404, e.code)

    # ── CRUD: DELETE ──────────────────────────────────────────────────────────

    def test_results_delete_returns_200(self):
        """DELETE /api/results/:id must return HTTP 200 with {'deleted': id}."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        rid = created["id"]
        status, data = self._delete(f"/api/results/{rid}")
        self.assertEqual(200, status)
        self.assertEqual(rid, data["deleted"])

    def test_results_delete_removes_record(self):
        """After DELETE, the record must no longer appear in GET /api/results."""
        _, created = self._post("/api/results", self._RESULT_BODY)
        rid = created["id"]
        self._delete(f"/api/results/{rid}")
        _, list_data = self._get("/api/results")
        ids = [r["id"] for r in list_data["results"]]
        self.assertNotIn(rid, ids)

    def test_results_delete_nonexistent_returns_404(self):
        """DELETE /api/results/999999 must return HTTP 404."""
        url = f"http://127.0.0.1:{self.PORT}/api/results/999999"
        req = urllib.request.Request(url, method="DELETE")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(404, e.code)


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
