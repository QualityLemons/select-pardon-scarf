"""
Prerequisite Notice & Home Page Progression Tests
==================================================

Tests for the prerequisite-notice feature (Task #50):

1. HTML structure — level pages 2-6 carry the ``#prereq-notice-wrap``
   injection point; level 1 does not.

2. /api/results API — the endpoint that ``prereq-notice.js`` and
   ``applyProgressionState`` (index.html) query to decide whether to show
   the notice / dim the card.

3. Home-page progression state — after a learner saves a Level N result the
   API response exposes that level key so the JS can un-dim Level N+1 and
   suppress its prereq notice.

The prereq notice itself is injected by client-side JavaScript, so this
suite tests the *server-side contracts* the JS depends on; the JS logic is
covered by a separate frontend test.

Progress Count Update Tests (Task #56)
=======================================
4. Unique-level progress count — the intel bar stat on the home page is
   populated from GET /api/results.  After a learner completes a level via
   the full POST /api/assess → POST /api/results flow the count must
   increment.  Completing the *same* level a second time must NOT increase
   the unique-level count.
"""

import json
from html.parser import HTMLParser

from django.test import TestCase, Client

from apps.accounts.models import CustomUser
from apps.assessment.models import AssessmentResult, MissionLogEntry, PrereqDismissal

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_user(email='learner@example.com', password='TestP@ss1'):
    return CustomUser.objects.create_user(email=email, password=password)


def _login(client, user):
    """Force-login bypasses Axes, which requires a real request to authenticate()."""
    client.force_login(user)


def _save_result(user, level_key, grade='B', score=75):
    """Directly create an AssessmentResult row, bypassing the token flow."""
    return AssessmentResult.objects.create(
        user=user,
        level_key=level_key,
        score=score,
        grade=grade,
        tier_label='Proficient',
        milestones_done=4,
        milestones_total=5,
        efficiency_label='Proficient',
        bonus_earned=0,
    )


# ---------------------------------------------------------------------------
# 1. HTML structure – prereq-notice-wrap injection point
# ---------------------------------------------------------------------------

class TestPrereqNoticeWrapPresence(TestCase):
    """
    The ``#prereq-notice-wrap`` div must be present in level 2-6 templates
    so that prereq-notice.js has a mount point.  Level 1 has no prerequisite
    and must NOT have the element.
    """

    def setUp(self):
        self.client = Client()
        self.user = _make_user()
        _login(self.client, self.user)

    def _get_level(self, n):

        response = self.client.get(f'/challenge/level{n}/')
        self.assertEqual(200, response.status_code,
                         f'/challenge/level{n}/ returned {response.status_code}')
        return response.content.decode()

    def test_level1_has_no_prereq_wrap(self):
        """Level 1 has no prerequisite, so its page must NOT have prereq-notice-wrap."""
        html = self._get_level(1)
        self.assertNotIn('prereq-notice-wrap', html,
                         'Level 1 should not contain #prereq-notice-wrap')

    def test_levels_2_to_6_have_prereq_wrap(self):
        """Levels 2-6 must each contain the prereq-notice-wrap injection point."""
        for n in range(2, 7):
            with self.subTest(level=n):
                html = self._get_level(n)
                self.assertIn('prereq-notice-wrap', html,
                              f'Level {n} is missing #prereq-notice-wrap')

    def test_prereq_notice_js_loaded_on_level_pages(self):
        """Levels 2-6 must reference prereq-notice.js so the notice logic runs."""
        for n in range(2, 7):
            with self.subTest(level=n):
                html = self._get_level(n)
                self.assertIn('prereq-notice', html,
                              f'Level {n} page does not reference prereq-notice.js')


# ---------------------------------------------------------------------------
# 2. /api/results — drives prereq-notice.js decisions
# ---------------------------------------------------------------------------

class TestResultsAPIAuthentication(TestCase):
    """GET /api/results must return 401 for unauthenticated requests."""

    def setUp(self):
        self.client = Client()

    def test_unauthenticated_returns_401(self):
        response = self.client.get('/api/results')
        self.assertEqual(401, response.status_code)

    def test_unauthenticated_response_body(self):
        response = self.client.get('/api/results')
        data = json.loads(response.content)
        self.assertIn('error', data)


class TestResultsAPIPrereqLogic(TestCase):
    """
    GET /api/results must return the right results so prereq-notice.js
    can decide whether to show or hide the notice:

    • No level-N result → hasPrev is False → notice IS shown on level N+1
    • Has level-N result → hasPrev is True  → notice is NOT shown on level N+1
    """

    def setUp(self):
        self.client = Client()
        self.user = _make_user()
        _login(self.client, self.user)

    def _get_results(self):
        response = self.client.get('/api/results')
        self.assertEqual(200, response.status_code)
        return json.loads(response.content)['results']

    # -- fresh account --------------------------------------------------------

    def test_fresh_user_has_no_results(self):
        """A new learner has an empty results list — notice shows on all levels 2-6."""
        results = self._get_results()
        self.assertEqual([], results,
                         'Fresh user should have zero results')

    # -- after completing level 1 --------------------------------------------

    def test_level1_result_appears_in_list(self):
        """Completing Level 1 must add level1 to /api/results."""
        _save_result(self.user, 'level1')
        results = self._get_results()
        level_keys = [r['level_key'] for r in results]
        self.assertIn('level1', level_keys,
                      'level1 result missing from /api/results after save')

    def test_level1_result_suppresses_notice_signal_on_level2(self):
        """
        prereq-notice.js checks: results.some(r => r.level_key === 'level1')
        This must be True after the learner completes Level 1, so the notice
        is NOT shown on Level 2.
        """
        _save_result(self.user, 'level1')
        results = self._get_results()
        has_level1 = any(r['level_key'] == 'level1' for r in results)
        self.assertTrue(has_level1,
                        'level1 not found in results — notice would incorrectly appear on level2')

    def test_no_level1_result_shows_notice_signal_on_level2(self):
        """
        Without a Level 1 result the API returns no level1 entry, so
        prereq-notice.js will show the notice on Level 2.
        """
        results = self._get_results()
        has_level1 = any(r['level_key'] == 'level1' for r in results)
        self.assertFalse(has_level1,
                         'Unexpected level1 result — notice would be incorrectly hidden on level2')

    # -- chain: levels 2→3, 3→4 … -------------------------------------------

    def test_each_level_result_gates_next_level_notice(self):
        """
        For every consecutive pair (N, N+1) where N ∈ {1..5}:
        completing level N must place level N in the results list
        so the prereq notice on level N+1 is suppressed.
        """
        for n in range(1, 6):
            with self.subTest(completed_level=n, gated_level=n + 1):
                # Create a fresh user per sub-test to avoid cross-contamination
                email = f'chain{n}@example.com'
                u = CustomUser.objects.create_user(email=email, password='TestP@ss1')
                c = Client()
                c.force_login(u)

                # No result yet → level_n absent
                resp = c.get('/api/results')
                data = json.loads(resp.content)['results']
                self.assertFalse(
                    any(r['level_key'] == f'level{n}' for r in data),
                    f'Unexpected level{n} result before save',
                )

                # Save result → level_n present
                _save_result(u, f'level{n}')
                resp = c.get('/api/results')
                data = json.loads(resp.content)['results']
                self.assertTrue(
                    any(r['level_key'] == f'level{n}' for r in data),
                    f'level{n} absent after save — notice would show on level{n + 1}',
                )

    # -- result isolation between users ---------------------------------------

    def test_results_are_isolated_per_user(self):
        """
        A result saved for User A must not appear in User B's /api/results.
        If it did, User B would incorrectly skip the prereq notice.
        """
        user_b = _make_user(email='other@example.com')
        _save_result(user_b, 'level1')   # only User B has a result

        # User A (self.user) should still see an empty list
        results_a = self._get_results()
        self.assertEqual([], results_a,
                         "User A should not see User B's level1 result")


# ---------------------------------------------------------------------------
# 3. Home-page progression state (applyProgressionState data contract)
# ---------------------------------------------------------------------------

class TestHomePageProgressionState(TestCase):
    """
    The home page's applyProgressionState() reads /api/results and dims
    level cards whose prerequisite has not been attempted.  These tests
    verify the API provides the right data shape for that logic.
    """

    def setUp(self):
        self.client = Client()
        self.user = _make_user(email='progress@example.com')
        _login(self.client, self.user)

    def _get_results(self):
        resp = self.client.get('/api/results')
        self.assertEqual(200, resp.status_code)
        return json.loads(resp.content)['results']

    def test_home_page_loads(self):
        """The challenge home page (site root) must return 200."""
        resp = self.client.get('/')
        self.assertEqual(200, resp.status_code)

    def test_fresh_user_no_results_all_cards_dimmed(self):
        """
        With no results, applyProgressionState receives an empty list →
        levels 2-6 are dimmed (opacity 0.62).  The API must return [].
        """
        results = self._get_results()
        self.assertEqual([], results)

    def test_level1_completion_undims_level2_card(self):
        """
        After completing Level 1, attempted['level1'] is True in the JS,
        so the Level 2 card is un-dimmed.  The API must expose level1.
        """
        _save_result(self.user, 'level1')
        results = self._get_results()
        attempted_keys = {r['level_key'] for r in results}
        self.assertIn('level1', attempted_keys,
                      'level1 absent — Level 2 card would remain dimmed')

    def test_level2_completion_undims_level3_card(self):
        """Completing Level 2 must expose level2 so Level 3 is un-dimmed."""
        _save_result(self.user, 'level1')
        _save_result(self.user, 'level2')
        results = self._get_results()
        attempted_keys = {r['level_key'] for r in results}
        self.assertIn('level2', attempted_keys,
                      'level2 absent — Level 3 card would remain dimmed')

    def test_result_payload_contains_level_key_field(self):
        """
        applyProgressionState reads r.level_key from each result.
        The API must include that field.
        """
        _save_result(self.user, 'level1')
        results = self._get_results()
        self.assertGreater(len(results), 0, 'Expected at least one result')
        self.assertIn('level_key', results[0],
                      'level_key field missing from result payload')

    def test_completing_all_levels_undims_entire_track(self):
        """
        Completing all six levels must return all six level keys so the JS
        un-dims every card and adds a ✓ Attempted badge to each.
        """
        for n in range(1, 7):
            _save_result(self.user, f'level{n}')

        results = self._get_results()
        attempted_keys = {r['level_key'] for r in results}
        for n in range(1, 7):
            self.assertIn(f'level{n}', attempted_keys,
                          f'level{n} missing from results after completing all levels')


# ---------------------------------------------------------------------------
# 4. /profile/ view — result isolation between users
# ---------------------------------------------------------------------------

class TestProfileViewIsolation(TestCase):
    """
    /profile/ (ResultHistoryView) must only expose the requesting user's own
    assessment results.  A learner who guesses another learner's /profile/ URL
    must never see foreign data — because the view has a single, shared URL
    with no user-ID parameter, the only way to expose data is via an
    authentication or query-scope bug.
    """

    PROFILE_URL = '/profile/'

    def setUp(self):
        self.client = Client()
        self.user_a = _make_user(email='alice@example.com')
        self.user_b = _make_user(email='bob@example.com')

    # -- unauthenticated access -----------------------------------------------

    def test_unauthenticated_request_redirects_to_login(self):
        """An anonymous GET to /profile/ must redirect to /login/."""
        response = self.client.get(self.PROFILE_URL)
        self.assertIn(response.status_code, (301, 302),
                      f'Expected redirect for unauthenticated request, got {response.status_code}')
        self.assertIn('/login/', response['Location'],
                      'Unauthenticated /profile/ must redirect to /login/')

    # -- authenticated access: own results only -------------------------------

    def test_authenticated_user_sees_own_results(self):
        """An authenticated learner's /profile/ page must include their own result data."""
        _save_result(self.user_a, 'level1', grade='A', score=95)

        self.client.force_login(self.user_a)
        response = self.client.get(self.PROFILE_URL)

        self.assertEqual(200, response.status_code)
        # The rendered page must mention the level key that user_a completed
        content = response.content.decode()
        self.assertIn('level1', content,
                      "User A's /profile/ must display their own level1 result")

    def test_authenticated_user_cannot_see_other_users_results(self):
        """
        User B visiting /profile/ must NOT see User A's results.
        The view filters by request.user, so User B's queryset must be empty
        when only User A has results.
        """
        _save_result(self.user_a, 'level1', grade='A', score=95)

        # User B has no results; log in as User B
        self.client.force_login(self.user_b)
        response = self.client.get(self.PROFILE_URL)

        self.assertEqual(200, response.status_code)
        # The context queryset must be empty for User B
        results_qs = response.context.get('results') or response.context.get('object_list')
        self.assertIsNotNone(results_qs,
                             "Response context must contain a 'results' or 'object_list' key")
        self.assertEqual(
            0,
            results_qs.count(),
            "User B must not see User A's results — queryset should be empty",
        )

    def test_each_user_sees_only_their_own_results(self):
        """
        When both users have results, each one's /profile/ must show only their
        own rows — never the other user's.
        """
        _save_result(self.user_a, 'level1', grade='A', score=95)
        _save_result(self.user_b, 'level2', grade='B', score=75)

        # Check User A
        self.client.force_login(self.user_a)
        resp_a = self.client.get(self.PROFILE_URL)
        self.assertEqual(200, resp_a.status_code)
        qs_a = resp_a.context.get('results') or resp_a.context.get('object_list')
        self.assertEqual(1, qs_a.count(),
                         'User A should see exactly 1 result (their own level1)')
        self.assertEqual('level1', qs_a.first().level_key,
                         "User A's result must be level1")

        # Check User B
        self.client.logout()
        self.client.force_login(self.user_b)
        resp_b = self.client.get(self.PROFILE_URL)
        self.assertEqual(200, resp_b.status_code)
        qs_b = resp_b.context.get('results') or resp_b.context.get('object_list')
        self.assertEqual(1, qs_b.count(),
                         'User B should see exactly 1 result (their own level2)')
        self.assertEqual('level2', qs_b.first().level_key,
                         "User B's result must be level2")


# ---------------------------------------------------------------------------
# 4. Progress count updates immediately after a learner completes a level
# ---------------------------------------------------------------------------

class TestProgressCountUpdates(TestCase):
    """
    The intel bar on the home page shows a "levels completed" count derived
    from GET /api/results.  After a learner submits a result through the real
    API flow (POST /api/assess -> POST /api/results) the count must increment.
    Re-submitting the *same level* a second time must NOT increase the unique
    level count -- the intel bar must not double-count repeated attempts.

    These tests exercise the server-side contract that the client JS relies on.
    """

    def setUp(self):
        self.client = Client()
        self.user = _make_user(email='progress_count@example.com')
        self.client.force_login(self.user)

    def _assess(self, level_key='level1', milestones_done=None, scan_count=3,
                elapsed_ms=60000):
        """Call POST /api/assess and return the result_token from the response."""
        payload = {
            'level': level_key,
            'milestones_done': milestones_done or [],
            'scan_count': scan_count,
            'elapsed_ms': elapsed_ms,
        }
        resp = self.client.post(
            '/api/assess',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(200, resp.status_code,
                         f'POST /api/assess failed: {resp.content[:200]}')
        data = json.loads(resp.content)
        self.assertIn('result_token', data,
                      'POST /api/assess must return a result_token')
        return data['result_token']

    def _save_via_api(self, result_token, note=''):
        """Call POST /api/results with a result_token and return the HTTP response."""
        return self.client.post(
            '/api/results',
            data=json.dumps({'result_token': result_token, 'note': note}),
            content_type='application/json',
        )

    def _unique_level_count(self):
        """GET /api/results and return the number of distinct level_keys."""
        resp = self.client.get('/api/results')
        self.assertEqual(200, resp.status_code)
        results = json.loads(resp.content)['results']
        return len({r['level_key'] for r in results})

    def test_count_is_zero_before_any_submission(self):
        """A fresh learner has zero unique completed levels."""
        self.assertEqual(0, self._unique_level_count(),
                         'Fresh learner should have no completed levels')

    def test_count_increments_after_completing_a_level(self):
        """
        Submitting a result via the full API flow must increment the unique
        level count from 0 to 1 so the intel bar reflects the completion
        immediately on the next page load.
        """
        token = self._assess(level_key='level1')
        save_resp = self._save_via_api(token)
        self.assertEqual(201, save_resp.status_code,
                         f'POST /api/results must return 201: {save_resp.content[:200]}')

        self.assertEqual(
            1, self._unique_level_count(),
            'Unique level count must be 1 after completing level1',
        )

    def test_count_increments_for_each_distinct_level(self):
        """
        Completing two different levels must push the unique level count to 2,
        not 1 (no collapsing of distinct levels).
        """
        for level_key in ('level1', 'level2'):
            token = self._assess(level_key=level_key)
            resp = self._save_via_api(token)
            self.assertEqual(201, resp.status_code,
                             f'Failed to save {level_key}: {resp.content[:200]}')

        self.assertEqual(
            2, self._unique_level_count(),
            'Unique level count must be 2 after completing level1 and level2',
        )

    def test_count_does_not_increase_when_same_level_retaken(self):
        """
        If a learner retakes the same level (two separate POST /api/assess
        + POST /api/results round-trips), the unique level count must stay at 1 --
        the intel bar must not count the same level twice.

        Each token has a unique nonce so both persist as separate DB rows;
        the uniqueness constraint is on the *display count*, not on DB rows.
        """
        # First attempt
        token_a = self._assess(level_key='level1')
        self._save_via_api(token_a)
        self.assertEqual(1, self._unique_level_count(),
                         'Count should be 1 after first attempt')

        # Second attempt on the same level (new token, new nonce)
        token_b = self._assess(level_key='level1')
        resp_b = self._save_via_api(token_b)
        self.assertEqual(201, resp_b.status_code,
                         f'Second attempt save must succeed: {resp_b.content[:200]}')

        # Unique-level count must remain 1
        self.assertEqual(
            1, self._unique_level_count(),
            'Unique level count must stay at 1 when the same level is retaken '
            '(repeated attempts should not inflate the intel bar count)',
        )

    def test_used_token_cannot_be_replayed(self):
        """
        A result_token that has already been consumed must be rejected (409)
        on a second POST /api/results attempt, ensuring the intel bar count
        cannot be artificially inflated by replaying the same token.
        """
        token = self._assess(level_key='level1')
        first = self._save_via_api(token)
        self.assertEqual(201, first.status_code,
                         'First submission must succeed with 201')

        second = self._save_via_api(token)  # replay the same token
        self.assertEqual(409, second.status_code,
                         'Replaying a used token must return 409 Conflict')

    def test_results_available_on_next_get_after_post(self):
        """
        The result saved by POST /api/results must be immediately visible in
        the subsequent GET /api/results response (no caching or async lag)
        so the home-page intel bar reflects the completion on the very next
        page load.
        """
        token = self._assess(level_key='level1')
        self._save_via_api(token)

        resp = self.client.get('/api/results')
        self.assertEqual(200, resp.status_code)
        results = json.loads(resp.content)['results']
        level_keys = [r['level_key'] for r in results]
        self.assertIn(
            'level1', level_keys,
            'level1 must appear in GET /api/results immediately after POST /api/results',
        )

    def _delete_result(self, rid):
        """Call DELETE /api/results/<rid> and return the HTTP response."""
        return self.client.delete(f'/api/results/{rid}')

    def test_count_drops_to_zero_after_deleting_only_result(self):
        """
        When a learner deletes their only result for a level, the unique-level
        count visible to the intel bar must drop back to 0.

        Flow: save level1 result → assert count 1 → DELETE result → assert count 0.
        """
        result = _save_result(self.user, 'level1')
        self.assertEqual(
            1, self._unique_level_count(),
            'Unique level count must be 1 after saving the only level1 result',
        )

        del_resp = self._delete_result(result.id)
        self.assertEqual(
            200, del_resp.status_code,
            f'DELETE /api/results/{result.id} must return 200: {del_resp.content[:200]}',
        )

        self.assertEqual(
            0, self._unique_level_count(),
            'Unique level count must drop to 0 after the only level1 result is deleted',
        )

    def test_count_stays_at_one_after_deleting_one_of_two_results_for_same_level(self):
        """
        When a learner has two results for the same level and deletes one,
        the unique-level count must remain at 1 — the remaining row still
        covers that level and the intel bar must not under-report.

        Flow: save level1 twice → assert count 1 → DELETE first result
              → assert count still 1.
        """
        result_a = _save_result(self.user, 'level1', score=70)
        result_b = _save_result(self.user, 'level1', score=85)

        self.assertEqual(
            1, self._unique_level_count(),
            'Two results for the same level must count as 1 unique level',
        )

        del_resp = self._delete_result(result_a.id)
        self.assertEqual(
            200, del_resp.status_code,
            f'DELETE /api/results/{result_a.id} must return 200: {del_resp.content[:200]}',
        )

        self.assertEqual(
            1, self._unique_level_count(),
            'Unique level count must stay at 1 after deleting one of two level1 results — '
            'the remaining result still covers level1',
        )
        # Confirm the surviving result is still present
        resp = self.client.get('/api/results')
        remaining_ids = [r['id'] for r in json.loads(resp.content)['results']]
        self.assertIn(
            result_b.id, remaining_ids,
            'The non-deleted result must still be retrievable after deleting the other one',
        )

    def test_progress_count_is_isolated_per_user(self):
        """
        User A completes level1 via the full POST /api/assess → POST /api/results
        flow.  User B (a separate learner with their own session) must still see
        a unique-level count of 0 — the intel bar count must never bleed across
        user boundaries.

        This exercises ResultsListView's queryset scope end-to-end: if the
        filter(user=request.user) predicate were absent or wrong, User B's GET
        would return User A's row and the count would incorrectly show 1.
        """
        # --- User A completes level1 via the real API flow ---
        token = self._assess(level_key='level1')
        save_resp = self._save_via_api(token)
        self.assertEqual(
            201, save_resp.status_code,
            f'User A POST /api/results must return 201: {save_resp.content[:200]}',
        )

        # Sanity-check: User A's own count is 1
        self.assertEqual(
            1, self._unique_level_count(),
            'User A unique-level count must be 1 after completing level1',
        )

        # --- User B has a separate client and session ---
        user_b = _make_user(email='user_b_intel@example.com')
        client_b = Client()
        client_b.force_login(user_b)

        resp_b = client_b.get('/api/results')
        self.assertEqual(
            200, resp_b.status_code,
            f"User B GET /api/results must return 200: {resp_b.content[:200]}",
        )
        results_b = json.loads(resp_b.content)['results']
        unique_count_b = len({r['level_key'] for r in results_b})

        self.assertEqual(
            0,
            unique_count_b,
            'User B unique-level count must be 0 — User A\'s level1 result '
            'must not appear in a different user\'s GET /api/results response',
        )


# ---------------------------------------------------------------------------
# 5. Server-side prereq-dismissal endpoint  (Task #59)
# ---------------------------------------------------------------------------

class TestPrereqDismissalEndpoint(TestCase):
    """
    Confirms that GET/POST /api/prereq-dismissals/ correctly records and
    returns per-user dismissals, and that unauthenticated callers are refused.
    """

    URL = '/api/prereq-dismissals/'

    def setUp(self):
        self.client = Client()
        self.user = _make_user(email='dismisser@example.com')

    # -- GET: fresh user returns empty list -----------------------------------

    def test_get_returns_empty_list_for_fresh_user(self):
        """
        A brand-new authenticated user has no dismissals; GET must return
        an empty ``dismissed`` list, not an error.
        """
        _login(self.client, self.user)
        resp = self.client.get(self.URL)
        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.content)
        self.assertIn('dismissed', data)
        self.assertEqual([], data['dismissed'])

    # -- POST: creates a dismissal record ------------------------------------

    def test_post_with_valid_level_key_creates_record(self):
        """
        POST /api/prereq-dismissals/ with a valid ``level_key`` must return
        ``{dismissed: true}`` and persist the record to the database.
        """
        _login(self.client, self.user)
        resp = self.client.post(
            self.URL,
            data=json.dumps({'level_key': 'level3'}),
            content_type='application/json',
        )
        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.content)
        self.assertTrue(data.get('dismissed'), 'POST must return {dismissed: true}')

        # Verify the record was persisted
        from apps.assessment.models import PrereqDismissal
        self.assertTrue(
            PrereqDismissal.objects.filter(user=self.user, level_key='level3').exists(),
            'PrereqDismissal record must exist in the database after POST',
        )

    # -- GET: dismissed key appears after POST --------------------------------

    def test_get_includes_dismissed_key_after_post(self):
        """
        After posting a dismissal for ``level3``, a subsequent GET must include
        ``'level3'`` in the ``dismissed`` list — confirming the notice will be
        suppressed on a second browser/device.
        """
        _login(self.client, self.user)
        self.client.post(
            self.URL,
            data=json.dumps({'level_key': 'level3'}),
            content_type='application/json',
        )
        resp = self.client.get(self.URL)
        self.assertEqual(200, resp.status_code)
        dismissed = json.loads(resp.content).get('dismissed', [])
        self.assertIn(
            'level3',
            dismissed,
            "GET /api/prereq-dismissals/ must include 'level3' after it was POSTed",
        )

    # -- Idempotent POST ------------------------------------------------------

    def test_duplicate_post_does_not_create_duplicate_record(self):
        """
        Posting the same level_key twice must not raise an error or create
        duplicate rows (get_or_create semantics).
        """
        _login(self.client, self.user)
        for _ in range(2):
            resp = self.client.post(
                self.URL,
                data=json.dumps({'level_key': 'level2'}),
                content_type='application/json',
            )
            self.assertEqual(200, resp.status_code)

        from apps.assessment.models import PrereqDismissal
        count = PrereqDismissal.objects.filter(user=self.user, level_key='level2').count()
        self.assertEqual(1, count, 'Duplicate POSTs must not create duplicate rows')

    # -- Unauthenticated callers receive 401 ----------------------------------

    def test_unauthenticated_get_returns_401(self):
        """Unauthenticated GET must be refused with 401."""
        resp = self.client.get(self.URL)
        self.assertEqual(
            401, resp.status_code,
            'GET /api/prereq-dismissals/ must return 401 for unauthenticated callers',
        )

    def test_unauthenticated_post_returns_401(self):
        """Unauthenticated POST must be refused with 401."""
        resp = self.client.post(
            self.URL,
            data=json.dumps({'level_key': 'level3'}),
            content_type='application/json',
        )
        self.assertEqual(
            401, resp.status_code,
            'POST /api/prereq-dismissals/ must return 401 for unauthenticated callers',
        )

    # -- Dismissals are scoped per user --------------------------------------

    def test_dismissals_are_scoped_per_user(self):
        """
        User A's dismissal of level3 must not appear in User B's GET response,
        confirming that server-side storage is properly isolated.
        """
        user_b = _make_user(email='other@example.com')

        _login(self.client, self.user)
        self.client.post(
            self.URL,
            data=json.dumps({'level_key': 'level3'}),
            content_type='application/json',
        )

        self.client.logout()
        _login(self.client, user_b)
        resp = self.client.get(self.URL)
        dismissed = json.loads(resp.content).get('dismissed', [])
        self.assertNotIn(
            'level3',
            dismissed,
            "User B must not see User A's dismissal in GET /api/prereq-dismissals/",
        )


# ---------------------------------------------------------------------------
# 6. PrereqDismissal cascade-delete on user deletion
# ---------------------------------------------------------------------------

class TestPrereqDismissalCascadeDelete(TestCase):
    """
    Confirms that deleting a CustomUser removes all their PrereqDismissal rows
    via the CASCADE foreign-key constraint.  This prevents stale dismissal
    records from accumulating after a learner's account is removed.
    """

    def test_dismissals_deleted_when_user_is_deleted(self):
        """
        Creating two dismissal rows for a user and then deleting the user
        must leave zero PrereqDismissal rows for that user_id in the database.
        """
        user = _make_user(email='todelete@example.com')
        PrereqDismissal.objects.create(user=user, level_key='level2')
        PrereqDismissal.objects.create(user=user, level_key='level3')

        user_pk = user.pk
        user.delete()

        remaining = PrereqDismissal.objects.filter(user_id=user_pk).count()
        self.assertEqual(
            0,
            remaining,
            'All PrereqDismissal rows must be cascade-deleted when the owning user is deleted',
        )

    def test_other_users_dismissals_are_unaffected(self):
        """
        Deleting User A must not remove PrereqDismissal rows belonging to User B.
        """
        user_a = _make_user(email='usera@example.com')
        user_b = _make_user(email='userb@example.com')
        PrereqDismissal.objects.create(user=user_a, level_key='level2')
        PrereqDismissal.objects.create(user=user_b, level_key='level2')

        user_a.delete()

        self.assertTrue(
            PrereqDismissal.objects.filter(user=user_b, level_key='level2').exists(),
            "User B's dismissal must survive the deletion of User A",
        )


# ---------------------------------------------------------------------------
# 7. Home-page card-dimming DOM contract
# ---------------------------------------------------------------------------

class _MissionsGridParser(HTMLParser):
    """
    Minimal SAX-style parser that extracts the attributes of every ``<a>``
    element that is a *structural descendant* of the element carrying
    ``id="missions-grid"``.

    The parser tracks element nesting depth so it can detect when the grid
    element closes, even in the presence of other ``<div>`` children at
    arbitrary depth.
    """

    def __init__(self):
        super().__init__()
        # anchor attrs collected while inside #missions-grid
        self.grid_anchors = []   # list of dicts: {href, classes}
        self._in_grid = False
        self._depth = 0          # nesting depth of the *containing* element
        self._grid_tag = None    # tag name of the grid container

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if not self._in_grid:
            # Detect the missions-grid container (any block-level element)
            if attr_dict.get('id') == 'missions-grid':
                self._in_grid = True
                self._grid_tag = tag
                self._depth = 1   # we are now one level inside the grid
            return

        # We are inside the grid — track depth for ALL tags (void elements
        # like <br>, <input> do not get a handle_endtag, but they cannot
        # host id="missions-grid" so tracking them is harmless).
        self._depth += 1

        if tag == 'a':
            classes = attr_dict.get('class', '').split()
            self.grid_anchors.append({
                'href': attr_dict.get('href', ''),
                'classes': classes,
            })

    def handle_endtag(self, tag):
        if not self._in_grid:
            return
        self._depth -= 1
        if self._depth == 0:
            # Exited the missions-grid container
            self._in_grid = False


class TestMissionsGridDOMContract(TestCase):
    """
    applyProgressionState() in templates/challenge/index.html dims level cards
    by locating them with::

        grid.querySelector('a[href="/challenge/levelN/"]')

    inside ``#missions-grid``.  If the grid's id attribute or the anchor hrefs
    ever change, the dimming silently stops working.  These tests pin that
    contract so any breaking markup change is caught immediately.

    All assertions use a proper SAX-style HTML parser to check *structural
    containment* — not substring position — so they fail correctly when cards
    are moved outside the grid.
    """

    def setUp(self):
        self.client = Client()
        response = self.client.get('/')
        self.assertEqual(
            200, response.status_code,
            f'Home page / returned {response.status_code}',
        )
        html = response.content.decode()

        # Parse the full page and collect anchors that are structural
        # descendants of #missions-grid.
        parser = _MissionsGridParser()
        parser.feed(html)
        self.grid_anchors = parser.grid_anchors   # [{href, classes}, …]
        self.grid_found   = parser._grid_tag is not None or bool(parser.grid_anchors)
        # Re-check: grid_found is True if the parser ever entered the grid.
        # Use a flag set during parsing for reliability.
        parser2 = _MissionsGridParser()

        class _FlagParser(_MissionsGridParser):
            def __init__(self):
                super().__init__()
                self.grid_element_seen = False
            def handle_starttag(self, tag, attrs):
                attr_dict = dict(attrs)
                if attr_dict.get('id') == 'missions-grid':
                    self.grid_element_seen = True
                super().handle_starttag(tag, attrs)

        fp = _FlagParser()
        fp.feed(html)
        self.grid_element_seen = fp.grid_element_seen
        self.grid_anchors = fp.grid_anchors

    # -- Grid container -------------------------------------------------------

    def test_missions_grid_element_present(self):
        """
        applyProgressionState() opens with ``document.getElementById('missions-grid')``.
        An element with that id must exist in the rendered home page HTML.
        """
        self.assertTrue(
            self.grid_element_seen,
            'No element with id="missions-grid" found on the home page — '
            'applyProgressionState() will silently do nothing',
        )

    # -- Level anchors structurally inside the grid ---------------------------

    def test_all_six_level_anchors_are_inside_missions_grid(self):
        """
        applyProgressionState() uses ``grid.querySelector('a[href="/challenge/levelN/"]')``.
        All six level anchors must be *structural descendants* of #missions-grid,
        not merely present elsewhere on the page.
        """
        hrefs_in_grid = {a['href'] for a in self.grid_anchors}
        for n in range(1, 7):
            expected_href = f'/challenge/level{n}/'
            with self.subTest(level=n):
                self.assertIn(
                    expected_href,
                    hrefs_in_grid,
                    f'<a href="{expected_href}"> is not a structural descendant of '
                    f'#missions-grid — applyProgressionState() cannot locate the '
                    f'Level {n} card for dimming',
                )

    def test_level_card_anchors_carry_mission_card_class(self):
        """
        Each level card anchor inside #missions-grid must carry the
        ``mission-card`` CSS class.  applyProgressionState() applies opacity
        changes to these elements; the absence of the class signals that the
        card markup has changed in a way that may break dimming.
        """
        anchor_map = {a['href']: a['classes'] for a in self.grid_anchors}
        for n in range(1, 7):
            href = f'/challenge/level{n}/'
            with self.subTest(level=n):
                self.assertIn(
                    href, anchor_map,
                    f'<a href="{href}"> not found inside #missions-grid',
                )
                self.assertIn(
                    'mission-card',
                    anchor_map[href],
                    f'<a href="{href}"> inside #missions-grid is missing the '
                    f'"mission-card" class — card dimming may target the wrong element',
                )


# ---------------------------------------------------------------------------
# 8. Reflection entry ownership — cross-user isolation (Task #62)
# ---------------------------------------------------------------------------

def _make_entry(user, level='level1', skill='PLC basics', notes='Test note', rating=3):
    """Create a MissionLogEntry directly, bypassing the HTTP layer."""
    return MissionLogEntry.objects.create(
        user=user,
        level=level,
        skill=skill,
        notes=notes,
        rating=rating,
    )


class TestReflectionOwnershipIsolation(TestCase):
    """
    ReflectionUpdateView and ReflectionDeleteView scope every lookup to
    the requesting user via ``get_object_or_404(MissionLogEntry, pk=pk,
    user=request.user)``.  These tests confirm that a second learner (User B)
    cannot read, overwrite, or destroy User A's reflection entry — both GET
    and POST requests must return 404 when the entry belongs to a different
    user.
    """

    def setUp(self):
        self.client = Client()
        self.user_a = _make_user(email='alice_reflect@example.com')
        self.user_b = _make_user(email='bob_reflect@example.com')
        # Create one entry owned by User A
        self.entry_a = _make_entry(self.user_a)

    # -- Edit view: User B blocked ------------------------------------------

    def test_user_b_get_edit_returns_404(self):
        """
        User B's GET to /reflect/<pk>/edit/ for User A's entry must return 404
        — the entry is invisible to anyone other than its owner.
        """
        _login(self.client, self.user_b)
        resp = self.client.get(f'/reflect/{self.entry_a.pk}/edit/')
        self.assertEqual(
            404, resp.status_code,
            'User B must receive 404 on GET /reflect/<pk>/edit/ for another user\'s entry',
        )

    def test_user_b_post_edit_returns_404(self):
        """
        User B's POST to /reflect/<pk>/edit/ for User A's entry must return 404
        and must NOT update the entry in the database.
        """
        _login(self.client, self.user_b)
        original_notes = self.entry_a.notes
        resp = self.client.post(
            f'/reflect/{self.entry_a.pk}/edit/',
            data={
                'level': 'level2',
                'skill': 'Injected skill',
                'notes': 'Injected notes',
                'rating': 5,
            },
        )
        self.assertEqual(
            404, resp.status_code,
            'User B must receive 404 on POST /reflect/<pk>/edit/ for another user\'s entry',
        )
        # The entry must remain unchanged in the database
        self.entry_a.refresh_from_db()
        self.assertEqual(
            original_notes, self.entry_a.notes,
            'Entry notes must not change after a cross-user POST to the edit view',
        )

    # -- Delete view: User B blocked ----------------------------------------

    def test_user_b_get_delete_returns_404(self):
        """
        User B's GET to /reflect/<pk>/delete/ for User A's entry must return 404.
        """
        _login(self.client, self.user_b)
        resp = self.client.get(f'/reflect/{self.entry_a.pk}/delete/')
        self.assertEqual(
            404, resp.status_code,
            'User B must receive 404 on GET /reflect/<pk>/delete/ for another user\'s entry',
        )

    def test_user_b_post_delete_returns_404_and_entry_survives(self):
        """
        User B's POST to /reflect/<pk>/delete/ for User A's entry must return 404
        and the entry must still exist in the database afterwards.
        """
        _login(self.client, self.user_b)
        resp = self.client.post(f'/reflect/{self.entry_a.pk}/delete/')
        self.assertEqual(
            404, resp.status_code,
            'User B must receive 404 on POST /reflect/<pk>/delete/ for another user\'s entry',
        )
        self.assertTrue(
            MissionLogEntry.objects.filter(pk=self.entry_a.pk).exists(),
            'Entry must still exist after a cross-user POST to the delete view',
        )

    # -- Edit view: happy path (owner) --------------------------------------

    def test_owner_get_edit_returns_200(self):
        """The entry owner's GET to the edit view must succeed with 200."""
        _login(self.client, self.user_a)
        resp = self.client.get(f'/reflect/{self.entry_a.pk}/edit/')
        self.assertEqual(
            200, resp.status_code,
            'Entry owner must receive 200 on GET /reflect/<pk>/edit/',
        )

    def test_owner_post_edit_updates_entry(self):
        """The entry owner's POST to the edit view must update the entry and redirect."""
        _login(self.client, self.user_a)
        updated_notes = 'Updated notes with enough detail to pass validation check.'
        resp = self.client.post(
            f'/reflect/{self.entry_a.pk}/edit/',
            data={
                'level': 'level2',
                'skill': 'ladder_logic',
                'notes': updated_notes,
                'rating': 4,
            },
        )
        self.assertIn(
            resp.status_code, (301, 302),
            'Successful owner edit must redirect',
        )
        self.entry_a.refresh_from_db()
        self.assertEqual(updated_notes, self.entry_a.notes,
                         'Entry notes must reflect the owner\'s update')

    # -- Delete view: happy path (owner) ------------------------------------

    def test_owner_get_delete_returns_200(self):
        """The entry owner's GET to the delete confirmation view must succeed with 200."""
        _login(self.client, self.user_a)
        resp = self.client.get(f'/reflect/{self.entry_a.pk}/delete/')
        self.assertEqual(
            200, resp.status_code,
            'Entry owner must receive 200 on GET /reflect/<pk>/delete/',
        )

    def test_owner_post_delete_removes_entry(self):
        """The entry owner's POST to the delete view must remove the entry and redirect."""
        _login(self.client, self.user_a)
        pk = self.entry_a.pk
        resp = self.client.post(f'/reflect/{pk}/delete/')
        self.assertIn(
            resp.status_code, (301, 302),
            'Successful owner delete must redirect',
        )
        self.assertFalse(
            MissionLogEntry.objects.filter(pk=pk).exists(),
            'Entry must be removed from the database after the owner POSTs to the delete view',
        )

    # -- Unauthenticated access ---------------------------------------------

    def test_unauthenticated_get_edit_redirects_to_login(self):
        """An anonymous GET to /reflect/<pk>/edit/ must redirect to /login/."""
        resp = self.client.get(f'/reflect/{self.entry_a.pk}/edit/')
        self.assertIn(resp.status_code, (301, 302),
                      'Unauthenticated edit GET must redirect')
        self.assertIn('/login/', resp['Location'],
                      'Unauthenticated edit GET must redirect to /login/')

    def test_unauthenticated_post_delete_redirects_to_login(self):
        """An anonymous POST to /reflect/<pk>/delete/ must redirect to /login/."""
        resp = self.client.post(f'/reflect/{self.entry_a.pk}/delete/')
        self.assertIn(resp.status_code, (301, 302),
                      'Unauthenticated delete POST must redirect')
        self.assertIn('/login/', resp['Location'],
                      'Unauthenticated delete POST must redirect to /login/')

    # -- Create view: ownership spoofing blocked ----------------------------

    def test_create_ignores_spoofed_user_field(self):
        """
        POSTing to /reflect/ with an extra ``user`` field pointing at User B's
        pk must create the entry owned by the requesting user (User A), not
        User B.  ReflectionCreateView.post() always assigns ``request.user``,
        so the spoofed field must be silently ignored.
        """
        _login(self.client, self.user_a)
        count_before = MissionLogEntry.objects.filter(user=self.user_b).count()

        resp = self.client.post(
            '/reflect/',
            data={
                'level':  'level1',
                'skill':  'ladder_logic',
                'notes':  'Attempting to forge an entry under another account.',
                'rating': '3',
                # Spoofed field: attacker tries to claim ownership as User B
                'user':   self.user_b.pk,
            },
        )

        # The request must succeed (redirect on save) rather than error out
        self.assertIn(
            resp.status_code, (301, 302),
            f'POST /reflect/ should redirect after a valid submission, got {resp.status_code}',
        )

        # No new entry must have been created for User B
        count_after = MissionLogEntry.objects.filter(user=self.user_b).count()
        self.assertEqual(
            count_before, count_after,
            'No MissionLogEntry must be created for User B when User A posts with a spoofed user field',
        )

        # The newly created entry must belong to User A
        latest = MissionLogEntry.objects.filter(user=self.user_a).order_by('-created_at').first()
        self.assertIsNotNone(latest, 'A new entry must have been created for the requesting user (User A)')
        self.assertEqual(
            self.user_a, latest.user,
            'The created entry must be owned by the requesting user, not the spoofed target',
        )


# ---------------------------------------------------------------------------
# 9. Best-score summary accuracy after retakes (Task #67)
# ---------------------------------------------------------------------------

class TestBestScoreSummaryOnRetake(TestCase):
    """
    ResultHistoryView.get_context_data annotates each level_key with
    best_score=Max('score'), attempts=Count('id'), and best_grade via a
    correlated subquery ordered by -score.

    These tests verify that:
    - After a higher-scoring retake the summary row shows the new best score
      and the grade that belongs to that highest-scoring attempt.
    - After a lower-scoring retake the summary row is unchanged (still shows
      the earlier, higher score and its grade).
    - The attempt counter increments with every submission, regardless of
      whether the new score is higher or lower.
    """

    PROFILE_URL = '/profile/'

    def setUp(self):
        self.client = Client()
        self.user = _make_user(email='retake_test@example.com')
        self.client.force_login(self.user)

    def _best_scores(self):
        """Return the best_scores queryset from the /profile/ context as a list of dicts."""
        resp = self.client.get(self.PROFILE_URL)
        self.assertEqual(200, resp.status_code,
                         f'/profile/ returned {resp.status_code}')
        qs = resp.context['best_scores']
        return list(qs)

    def _row_for(self, level_key):
        """Return the summary row for the given level_key, or None if absent."""
        rows = self._best_scores()
        for row in rows:
            if row['level_key'] == level_key:
                return row
        return None

    # -- Single attempt -------------------------------------------------------

    def test_single_attempt_appears_in_summary(self):
        """
        After one submission the summary must contain exactly one row for
        that level with the submitted score, grade, and an attempt count of 1.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        row = self._row_for('level1')
        self.assertIsNotNone(row, 'level1 must appear in best_scores after one submission')
        self.assertEqual(55, row['best_score'],
                         'best_score must equal the single submitted score')
        self.assertEqual('C', row['best_grade'],
                         'best_grade must match the single submitted grade')
        self.assertEqual(1, row['attempts'],
                         'attempts must be 1 after a single submission')

    # -- Higher-scoring retake ------------------------------------------------

    def test_higher_scoring_retake_updates_best_score(self):
        """
        Submitting a second, higher-scoring attempt must update best_score to
        the new high score.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            95, row['best_score'],
            'best_score must reflect the higher score after a better retake',
        )

    def test_higher_scoring_retake_updates_best_grade(self):
        """
        The grade shown in the summary must be the grade from the
        highest-scoring attempt, not the first attempt.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            'A', row['best_grade'],
            'best_grade must be "A" (the grade of the highest-scoring attempt)',
        )

    def test_higher_scoring_retake_increments_attempt_count(self):
        """
        The attempt counter must be 2 after two submissions for the same level.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            2, row['attempts'],
            'attempts must be 2 after two submissions for the same level',
        )

    # -- Lower-scoring retake -------------------------------------------------

    def test_lower_scoring_retake_does_not_reduce_best_score(self):
        """
        Submitting a lower-scoring attempt must NOT lower the stored best_score.
        """
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level1', grade='C', score=55)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            95, row['best_score'],
            'best_score must remain 95 after a lower-scoring retake',
        )

    def test_lower_scoring_retake_does_not_change_best_grade(self):
        """
        After a lower-scoring retake the grade must still reflect the
        highest-scoring attempt, not the most recent one.
        """
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level1', grade='C', score=55)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            'A', row['best_grade'],
            'best_grade must stay "A" after a lower-scoring retake',
        )

    def test_lower_scoring_retake_still_increments_attempt_count(self):
        """
        Even a lower-scoring retake must increment the attempt counter —
        it still counts as a submission.
        """
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level1', grade='C', score=55)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            2, row['attempts'],
            'attempts must be 2 even when the second attempt scores lower',
        )

    # -- Multiple retakes -----------------------------------------------------

    def test_attempt_count_increments_for_every_submission(self):
        """
        Three separate submissions for the same level must produce an attempt
        count of 3.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level1', grade='B', score=75)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            3, row['attempts'],
            'attempts must be 3 after three submissions for the same level',
        )

    def test_best_score_is_the_global_max_across_all_retakes(self):
        """
        After three submissions the best_score must be the highest of the three
        scores regardless of the order in which they were submitted.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level1', grade='B', score=75)
        row = self._row_for('level1')
        self.assertIsNotNone(row)
        self.assertEqual(
            95, row['best_score'],
            'best_score must be 95 (the global maximum) after three submissions',
        )

    # -- Independent levels are not conflated --------------------------------

    def test_retake_of_one_level_does_not_affect_another_levels_summary(self):
        """
        Submitting multiple attempts for level1 must not affect the summary
        row for level2, which has only a single attempt.
        """
        _save_result(self.user, 'level1', grade='C', score=55)
        _save_result(self.user, 'level1', grade='A', score=95)
        _save_result(self.user, 'level2', grade='B', score=75)

        row2 = self._row_for('level2')
        self.assertIsNotNone(row2, 'level2 must appear in best_scores')
        self.assertEqual(75, row2['best_score'],
                         'level2 best_score must be 75, unaffected by level1 retakes')
        self.assertEqual('B', row2['best_grade'],
                         'level2 best_grade must be "B", unaffected by level1 retakes')
        self.assertEqual(1, row2['attempts'],
                         'level2 attempts must be 1, unaffected by level1 retakes')


# ---------------------------------------------------------------------------
# 10. best_scores summary isolation — only the requesting user's own bests
# ---------------------------------------------------------------------------

class TestBestScoresSummaryIsolation(TestCase):
    """
    ResultHistoryView.get_context_data builds ``best_scores`` from a queryset
    that is filtered to ``user=self.request.user``.  These tests confirm that
    the aggregate is isolated per user — a future refactor cannot inadvertently
    expose one learner's best scores to another learner.
    """

    PROFILE_URL = '/profile/'

    def setUp(self):
        self.client = Client()
        self.user_a = _make_user(email='alice_scores@example.com')
        self.user_b = _make_user(email='bob_scores@example.com')

    def _best_scores_for(self, user):
        """Force-login as *user*, GET /profile/, return best_scores as a list."""
        self.client.force_login(user)
        resp = self.client.get(self.PROFILE_URL)
        self.assertEqual(200, resp.status_code,
                         f'/profile/ returned {resp.status_code} for {user.email}')
        return list(resp.context['best_scores'])

    # -- Isolation: other user's results must not appear ----------------------

    def test_best_scores_empty_when_only_other_user_has_results(self):
        """
        When User B is the only one with assessment results, User A's
        best_scores summary must be empty — User A must not see User B's
        personal bests.
        """
        _save_result(self.user_b, 'level1', grade='A', score=92)

        rows_a = self._best_scores_for(self.user_a)
        self.assertEqual(
            [],
            rows_a,
            'best_scores must be empty for User A when only User B has results — '
            'cross-user data must never appear in the summary',
        )

    # -- Accuracy: own results are reflected correctly ------------------------

    def test_best_scores_reflects_correct_values_after_level_completion(self):
        """
        After a learner completes a level, their best_scores summary must
        contain exactly one row for that level with the correct best_score,
        best_grade, and an attempt count of 1.
        """
        _save_result(self.user_a, 'level1', grade='B', score=78)

        rows_a = self._best_scores_for(self.user_a)

        level1_rows = [r for r in rows_a if r['level_key'] == 'level1']
        self.assertEqual(
            1, len(level1_rows),
            'best_scores must contain exactly one row for level1 after one submission',
        )
        row = level1_rows[0]
        self.assertEqual(78, row['best_score'],
                         'best_score must equal the submitted score (78)')
        self.assertEqual('B', row['best_grade'],
                         'best_grade must match the submitted grade ("B")')
        self.assertEqual(1, row['attempts'],
                         'attempts must be 1 after a single submission')


# ---------------------------------------------------------------------------
# 11. Reflection delete isolation — deleting own entry leaves other users' entries intact
# ---------------------------------------------------------------------------

class TestReflectionDeleteIsolation(TestCase):
    """
    ReflectionDeleteView.post() fetches the entry with
    ``get_object_or_404(MissionLogEntry, pk=pk, user=request.user)`` and then
    calls ``entry.delete()``.  Because the lookup is already ownership-scoped,
    only the requesting user's row can be fetched and deleted.

    This test verifies the end-to-end guarantee: when User A deletes one of
    their own MissionLogEntry rows via POST /reflect/<pk>/delete/, every entry
    belonging to User B must remain intact in the database.  A scope bug such
    as an accidental bulk-delete keyed only on ``pk`` (without the ``user``
    filter) would wipe User B's row and fail this test.
    """

    def setUp(self):
        self.client = Client()
        self.user_a = _make_user(email='alice_del_iso@example.com')
        self.user_b = _make_user(email='bob_del_iso@example.com')

    def test_deleting_own_entry_does_not_remove_other_users_entries(self):
        """
        User A deletes their own reflection entry via POST /reflect/<pk>/delete/.
        User B's entry (same level, created independently) must still exist in
        the database after the deletion completes.
        """
        # Create one entry for each user
        entry_a = _make_entry(self.user_a, level='level1', notes='User A note')
        entry_b = _make_entry(self.user_b, level='level1', notes='User B note')

        # User A deletes their own entry
        _login(self.client, self.user_a)
        resp = self.client.post(f'/reflect/{entry_a.pk}/delete/')

        # Deletion must succeed (redirect)
        self.assertIn(
            resp.status_code, (301, 302),
            f'User A POST /reflect/{entry_a.pk}/delete/ must redirect, '
            f'got {resp.status_code}',
        )

        # User A's entry must be gone
        self.assertFalse(
            MissionLogEntry.objects.filter(pk=entry_a.pk).exists(),
            "User A's entry must be removed from the database after they delete it",
        )

        # User B's entry must be untouched
        self.assertTrue(
            MissionLogEntry.objects.filter(pk=entry_b.pk).exists(),
            "User B's entry must still exist after User A deletes their own entry — "
            "the delete must be scoped to the requesting user's row only",
        )


# ---------------------------------------------------------------------------
# Reflection log authentication & ownership enforcement (Task #96)
# ---------------------------------------------------------------------------

def _make_entry(user, level='level1', notes='Test note', rating=3):
    """Create a MissionLogEntry directly for the given user."""
    return MissionLogEntry.objects.create(
        user=user,
        level=level,
        skill='',
        notes=notes,
        rating=rating,
    )


class TestReflectionLogAuthenticationRequired(TestCase):
    """
    GET requests to every reflection route from an anonymous session must be
    redirected to /login/?next=<url> (HTTP 302).  A 200 or any other status
    would expose entry content to unauthenticated visitors.
    """

    def setUp(self):
        self.client = Client()
        # Create a user and an entry so the pk-parameterised URLs are valid.
        self.owner = _make_user(email='owner_auth@example.com')
        self.entry = _make_entry(self.owner)

    def _assert_redirects_to_login(self, url):
        response = self.client.get(url)
        self.assertIn(
            response.status_code, (301, 302),
            f'Anonymous GET {url} must redirect, got {response.status_code}',
        )
        location = response.get('Location', '')
        self.assertIn(
            '/login/', location,
            f'Anonymous GET {url} must redirect to /login/, got Location: {location}',
        )

    def test_reflect_index_redirects_anonymous(self):
        """GET /reflect/ must redirect an anonymous session to /login/."""
        self._assert_redirects_to_login('/reflect/')

    def test_reflect_index_next_param_is_correct(self):
        """The redirect for /reflect/ must include next=/reflect/ so the user
        is returned to the reflection log after logging in."""
        response = self.client.get('/reflect/')
        location = response.get('Location', '')
        self.assertIn(
            'next=', location,
            'Redirect from /reflect/ must include a ?next= parameter',
        )
        self.assertIn(
            '/reflect/', location,
            'The ?next= value must reference /reflect/',
        )

    def test_reflect_edit_redirects_anonymous(self):
        """GET /reflect/<pk>/edit/ must redirect an anonymous session to /login/."""
        self._assert_redirects_to_login(f'/reflect/{self.entry.pk}/edit/')

    def test_reflect_edit_next_param_is_correct(self):
        """The redirect for /reflect/<pk>/edit/ must include the edit URL in next=."""
        response = self.client.get(f'/reflect/{self.entry.pk}/edit/')
        location = response.get('Location', '')
        self.assertIn(
            'next=', location,
            'Redirect from reflect edit must include a ?next= parameter',
        )
        self.assertIn(
            '/reflect/', location,
            'The ?next= value must reference a /reflect/ URL',
        )

    def test_reflect_delete_redirects_anonymous(self):
        """GET /reflect/<pk>/delete/ must redirect an anonymous session to /login/."""
        self._assert_redirects_to_login(f'/reflect/{self.entry.pk}/delete/')

    def test_reflect_delete_next_param_is_correct(self):
        """The redirect for /reflect/<pk>/delete/ must include the delete URL in next=."""
        response = self.client.get(f'/reflect/{self.entry.pk}/delete/')
        location = response.get('Location', '')
        self.assertIn(
            'next=', location,
            'Redirect from reflect delete must include a ?next= parameter',
        )
        self.assertIn(
            '/reflect/', location,
            'The ?next= value must reference a /reflect/ URL',
        )

    def test_reflect_index_does_not_return_200_for_anonymous(self):
        """GET /reflect/ must never return 200 for an anonymous session."""
        response = self.client.get('/reflect/')
        self.assertNotEqual(
            200, response.status_code,
            'Anonymous GET /reflect/ must not return 200 — entry content would be exposed',
        )

    def test_reflect_edit_does_not_return_200_for_anonymous(self):
        """GET /reflect/<pk>/edit/ must never return 200 for an anonymous session."""
        response = self.client.get(f'/reflect/{self.entry.pk}/edit/')
        self.assertNotEqual(
            200, response.status_code,
            'Anonymous GET /reflect/<pk>/edit/ must not return 200',
        )

    def test_reflect_delete_does_not_return_200_for_anonymous(self):
        """GET /reflect/<pk>/delete/ must never return 200 for an anonymous session."""
        response = self.client.get(f'/reflect/{self.entry.pk}/delete/')
        self.assertNotEqual(
            200, response.status_code,
            'Anonymous GET /reflect/<pk>/delete/ must not return 200',
        )


class TestReflectionOwnershipEnforcement(TestCase):
    """
    A logged-in learner who knows another learner's entry pk must receive 404
    when attempting to access that entry's edit or delete URL.  The views use
    get_object_or_404(MissionLogEntry, pk=pk, user=request.user) to enforce
    this, so any pk belonging to a different user must produce a 404 rather
    than a 200 or a redirect.
    """

    def setUp(self):
        self.client = Client()
        self.owner = _make_user(email='entry_owner@example.com')
        self.other = _make_user(email='other_learner@example.com')
        self.entry = _make_entry(self.owner, notes='Private reflection')

    def test_other_learner_cannot_access_edit_url(self):
        """Learner B must receive 404 when GETting Learner A's edit URL."""
        _login(self.client, self.other)
        response = self.client.get(f'/reflect/{self.entry.pk}/edit/')
        self.assertEqual(
            404, response.status_code,
            f'Learner B must get 404 on GET /reflect/{self.entry.pk}/edit/ '
            f'(owned by Learner A), got {response.status_code}',
        )

    def test_other_learner_cannot_access_delete_url(self):
        """Learner B must receive 404 when GETting Learner A's delete URL."""
        _login(self.client, self.other)
        response = self.client.get(f'/reflect/{self.entry.pk}/delete/')
        self.assertEqual(
            404, response.status_code,
            f'Learner B must get 404 on GET /reflect/{self.entry.pk}/delete/ '
            f'(owned by Learner A), got {response.status_code}',
        )

    def test_owner_can_access_own_edit_url(self):
        """The entry owner must be able to GET their own edit URL (200)."""
        _login(self.client, self.owner)
        response = self.client.get(f'/reflect/{self.entry.pk}/edit/')
        self.assertEqual(
            200, response.status_code,
            f'Entry owner must get 200 on GET /reflect/{self.entry.pk}/edit/, '
            f'got {response.status_code}',
        )

    def test_owner_can_access_own_delete_url(self):
        """The entry owner must be able to GET their own delete URL (200)."""
        _login(self.client, self.owner)
        response = self.client.get(f'/reflect/{self.entry.pk}/delete/')
        self.assertEqual(
            200, response.status_code,
            f'Entry owner must get 200 on GET /reflect/{self.entry.pk}/delete/, '
            f'got {response.status_code}',
        )

    def test_other_learner_edit_does_not_expose_entry_content(self):
        """Learner B's 404 response must not contain Learner A's private notes."""
        _login(self.client, self.other)
        response = self.client.get(f'/reflect/{self.entry.pk}/edit/')
        self.assertNotIn(
            'Private reflection', response.content.decode(),
            "Learner B's 404 response must not leak Learner A's entry notes",
        )
