import datetime

from django.test import TestCase, Client, override_settings
from django.utils import timezone

from axes.models import AccessAttempt

from apps.accounts.models import CustomUser
from apps.accounts.views import _format_timedelta, _get_cooloff_timedelta, _cooldown_remaining

LOGIN_URL = '/login/'
CORRECT_PASSWORD = 'CorrectP@ss1'


def _make_user(email='brute@example.com', password=CORRECT_PASSWORD):
    return CustomUser.objects.create_user(email=email, password=password)


def _post_login(client, username, password):
    return client.post(
        LOGIN_URL,
        data={'username': username, 'password': password},
        HTTP_X_FORWARDED_FOR='1.2.3.4',
        REMOTE_ADDR='1.2.3.4',
    )


@override_settings(
    AXES_FAILURE_LIMIT=5,
    AXES_COOLDOWN_TIME=1,
    AXES_LOCKOUT_PARAMETERS=['username'],
    AXES_USERNAME_FORM_FIELD='username',
    AXES_RESET_ON_SUCCESS=True,
    AXES_LOCKOUT_TEMPLATE='accounts/lockout.html',
    AXES_VERBOSE=False,
)
class LoginLockoutTests(TestCase):

    def setUp(self):
        AccessAttempt.objects.all().delete()
        self.client = Client(enforce_csrf_checks=False)
        self.user = _make_user()

    def tearDown(self):
        AccessAttempt.objects.all().delete()

    def _fail_login(self, times=1, username=None, client=None):
        c = client or self.client
        email = username or self.user.email
        response = None
        for _ in range(times):
            response = _post_login(c, email, 'WrongPassword!')
        return response

    LOCKOUT_STATUS = 429

    def test_lockout_engages_after_five_failures(self):
        """After AXES_FAILURE_LIMIT failed attempts the next attempt returns the lockout status."""
        self._fail_login(times=5)

        response = _post_login(self.client, self.user.email, 'WrongPassword!')

        self.assertEqual(
            response.status_code, self.LOCKOUT_STATUS,
            f'Expected {self.LOCKOUT_STATUS} lockout response after exceeding the failure limit.',
        )

    def test_locked_account_rejects_correct_password(self):
        """A locked account returns the lockout status even when the correct password is supplied."""
        self._fail_login(times=5)

        response = _post_login(self.client, self.user.email, CORRECT_PASSWORD)

        self.assertEqual(
            response.status_code, self.LOCKOUT_STATUS,
            'Locked account must not authenticate even with the correct password.',
        )

    def test_successful_login_resets_failure_counter(self):
        """A successful login resets the failure counter so the user can fail again from zero."""
        self._fail_login(times=4)

        ok = _post_login(self.client, self.user.email, CORRECT_PASSWORD)
        self.assertIn(ok.status_code, (200, 302),
                      'Login with correct credentials should succeed after 4 failures.')

        fresh_client = Client(enforce_csrf_checks=False)
        self._fail_login(times=5, client=fresh_client)

        locked_response = _post_login(fresh_client, self.user.email, CORRECT_PASSWORD)
        self.assertEqual(
            locked_response.status_code, self.LOCKOUT_STATUS,
            'After successful login the counter must restart; 5 new failures should lock again.',
        )

    def test_four_failures_do_not_trigger_lockout(self):
        """Fewer than AXES_FAILURE_LIMIT failures must not lock the account."""
        self._fail_login(times=4)

        response = _post_login(self.client, self.user.email, CORRECT_PASSWORD)

        self.assertIn(
            response.status_code, (200, 302),
            'Account must still be accessible when below the failure limit.',
        )

    def test_lockout_is_per_username(self):
        """Exhausting failures for one username must not lock a different username."""
        other = _make_user(email='innocent@example.com')
        self._fail_login(times=5, username=self.user.email)

        response = _post_login(self.client, other.email, CORRECT_PASSWORD)

        self.assertIn(
            response.status_code, (200, 302),
            "Another user's lockout must not affect this account.",
        )

    def test_lockout_response_renders_lockout_template(self):
        """The lockout response body must render the lockout template, not a raw error page."""
        self._fail_login(times=5)

        response = _post_login(self.client, self.user.email, 'WrongPassword!')

        self.assertEqual(response.status_code, self.LOCKOUT_STATUS)
        content = response.content.decode()
        self.assertIn('Account Temporarily Locked', content,
                      'Lockout page must show the "Account Temporarily Locked" heading.')
        self.assertIn('Too many failed login attempts', content,
                      'Lockout page must explain that too many failed attempts triggered the lockout.')

    def test_ip_rotation_does_not_reset_lockout_counter(self):
        """Rotating REMOTE_ADDR between failed attempts must not reset the failure counter.

        With AXES_LOCKOUT_PARAMETERS=['username'] the lockout key is the username
        alone, so an attacker who changes their IP address mid-attack cannot
        escape the lockout window.
        """
        email = self.user.email

        for i in range(5):
            ip = f'10.0.0.{i + 1}'
            self.client.post(
                LOGIN_URL,
                data={'username': email, 'password': 'WrongPassword!'},
                HTTP_X_FORWARDED_FOR=ip,
                REMOTE_ADDR=ip,
            )

        response = self.client.post(
            LOGIN_URL,
            data={'username': email, 'password': 'WrongPassword!'},
            HTTP_X_FORWARDED_FOR='192.168.99.99',
            REMOTE_ADDR='192.168.99.99',
        )

        self.assertEqual(
            response.status_code, self.LOCKOUT_STATUS,
            'Rotating IP addresses must not reset the failure counter; account must remain locked.',
        )


class FormatTimedeltaTests(TestCase):
    """Unit tests for the _format_timedelta helper."""

    def test_exactly_one_hour(self):
        result = _format_timedelta(datetime.timedelta(hours=1))
        self.assertEqual(result, '1 hour')

    def test_plural_hours(self):
        result = _format_timedelta(datetime.timedelta(hours=3))
        self.assertEqual(result, '3 hours')

    def test_minutes_only(self):
        result = _format_timedelta(datetime.timedelta(minutes=30))
        self.assertEqual(result, '30 minutes')

    def test_one_minute(self):
        result = _format_timedelta(datetime.timedelta(minutes=1))
        self.assertEqual(result, '1 minute')

    def test_hours_and_minutes(self):
        result = _format_timedelta(datetime.timedelta(hours=2, minutes=15))
        self.assertEqual(result, '2 hours and 15 minutes')

    def test_one_hour_and_one_minute(self):
        result = _format_timedelta(datetime.timedelta(hours=1, minutes=1))
        self.assertEqual(result, '1 hour and 1 minute')

    def test_zero_duration(self):
        result = _format_timedelta(datetime.timedelta(0))
        self.assertEqual(result, 'less than 1 minute')

    def test_sub_minute_duration(self):
        result = _format_timedelta(datetime.timedelta(seconds=45))
        self.assertEqual(result, 'less than 1 minute')

    def test_negative_duration_treated_as_zero(self):
        result = _format_timedelta(datetime.timedelta(seconds=-60))
        self.assertEqual(result, 'less than 1 minute')

    def test_seconds_are_truncated_not_rounded(self):
        result = _format_timedelta(datetime.timedelta(hours=1, minutes=59, seconds=59))
        self.assertEqual(result, '1 hour and 59 minutes')


class GetCooloffTimedeltaTests(TestCase):
    """Unit tests for _get_cooloff_timedelta — covers all supported AXES_COOLOFF_TIME shapes."""

    @override_settings(AXES_COOLOFF_TIME=1)
    def test_integer_one_hour(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(hours=1))

    @override_settings(AXES_COOLOFF_TIME=2)
    def test_integer_two_hours(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(hours=2))

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(minutes=45))
    def test_timedelta_45_minutes(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(minutes=45))

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=3, minutes=30))
    def test_timedelta_hours_and_minutes(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(hours=3, minutes=30))

    @override_settings(AXES_COOLOFF_TIME=lambda req: 4)
    def test_callable_returning_int(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(hours=4))

    @override_settings(AXES_COOLOFF_TIME=lambda req: datetime.timedelta(minutes=90))
    def test_callable_returning_timedelta(self):
        self.assertEqual(_get_cooloff_timedelta(), datetime.timedelta(minutes=90))


class LockoutPageTests(TestCase):
    """Integration tests for the /lockout/ view and its cooldown display."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)

    def _get_lockout(self, **extra_settings):
        with self.settings(**extra_settings):
            return self.client.get('/lockout/')

    @override_settings(AXES_COOLOFF_TIME=1)
    def test_lockout_page_returns_200(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)

    @override_settings(AXES_COOLOFF_TIME=1)
    def test_lockout_page_contains_formatted_duration_int_one_hour(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('1 hour', content,
                      'Lockout page must show "1 hour" when AXES_COOLOFF_TIME=1.')

    @override_settings(AXES_COOLOFF_TIME=2)
    def test_lockout_page_contains_formatted_duration_int_two_hours(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('2 hours', content,
                      'Lockout page must show "2 hours" when AXES_COOLOFF_TIME=2.')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(minutes=30))
    def test_lockout_page_contains_formatted_duration_timedelta_30min(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('30 minutes', content,
                      'Lockout page must show "30 minutes" when AXES_COOLOFF_TIME=timedelta(minutes=30).')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=1, minutes=30))
    def test_lockout_page_contains_formatted_duration_timedelta_90min(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('1 hour', content)
        self.assertIn('30 minutes', content)

    @override_settings(AXES_COOLOFF_TIME=lambda req: 3)
    def test_lockout_page_contains_formatted_duration_callable_returning_int(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('3 hours', content,
                      'Lockout page must show "3 hours" when AXES_COOLOFF_TIME is a callable returning 3.')

    @override_settings(AXES_COOLOFF_TIME=lambda req: datetime.timedelta(minutes=45))
    def test_lockout_page_contains_formatted_duration_callable_returning_timedelta(self):
        response = self.client.get('/lockout/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('45 minutes', content,
                      'Lockout page must show "45 minutes" when AXES_COOLOFF_TIME callable returns timedelta(minutes=45).')

    @override_settings(AXES_COOLOFF_TIME=1)
    def test_lockout_page_contains_wait_instruction(self):
        response = self.client.get('/lockout/')
        content = response.content.decode()
        self.assertIn('Please wait', content,
                      'Lockout page must contain the "Please wait" instruction.')

    @override_settings(AXES_COOLOFF_TIME=1)
    def test_lockout_page_contains_account_locked_heading(self):
        response = self.client.get('/lockout/')
        content = response.content.decode()
        self.assertIn('Account Temporarily Locked', content,
                      'Lockout page must display the "Account Temporarily Locked" heading.')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=2))
    def test_lockout_view_renders_updated_db_attempt_time_after_restart(self):
        """The /lockout/ view must always show the full configured cooloff, not a mid-countdown remainder.

        The view no longer passes the username to _cooldown_remaining, so it always
        renders the full configured duration regardless of how far through the
        cooldown the account actually is.  Both visits must show "2 hours".

        Scenario (2-hour cooloff):
          Visit #1 — attempt_time = now → page shows "2 hours" (full cooloff).
          DB update — attempt_time moved to 90 minutes ago (simulates 90 min passing).
          Visit #2 — page must still show "2 hours" (full cooloff), NOT "30 minutes",
                      because the view intentionally hides per-account timing to
                      prevent account-existence enumeration.
        """
        AccessAttempt.objects.all().delete()
        username = 'viewrestartuser@example.com'
        attempt = AccessAttempt.objects.create(
            username=username,
            ip_address='1.2.3.4',
            user_agent='test-agent',
            path_info='/login/',
            http_accept='text/html',
            failures_since_start=5,
        )
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=timezone.now())

        response_1 = self.client.get(f'/lockout/?username={username}')
        self.assertEqual(response_1.status_code, 200)
        content_1 = response_1.content.decode()
        self.assertIn('2 hours', content_1,
                      'Visit #1: page must show the full 2-hour cooloff, not a shorter remainder.')

        ninety_minutes_ago = timezone.now() - datetime.timedelta(minutes=90)
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=ninety_minutes_ago)

        response_2 = self.client.get(f'/lockout/?username={username}')
        self.assertEqual(response_2.status_code, 200)
        content_2 = response_2.content.decode()
        self.assertIn('2 hours', content_2,
                      'Visit #2 (90 min later): page must still show the full 2-hour cooloff.')
        self.assertNotIn('minutes', content_2,
                         'Visit #2 must not show a minutes-only countdown; '
                         'that would reveal that the account is mid-cooldown.')

        AccessAttempt.objects.all().delete()

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=1))
    def test_locked_and_unknown_accounts_show_same_duration_on_lockout_page(self):
        """A locked account and an unknown account must show the same duration on /lockout/.

        An attacker who probes /lockout/?username=X must not be able to learn
        whether X is actively locked by comparing displayed durations.  Both a
        currently-locked account and a completely unknown username must render
        the full configured cooloff.
        """
        AccessAttempt.objects.all().delete()
        locked_username = 'activelylockeduser@example.com'
        attempt = AccessAttempt.objects.create(
            username=locked_username,
            ip_address='1.2.3.4',
            user_agent='test-agent',
            path_info='/login/',
            http_accept='text/html',
            failures_since_start=5,
        )
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=timezone.now())

        response_locked = self.client.get(f'/lockout/?username={locked_username}')
        response_unknown = self.client.get('/lockout/?username=nosuchemail@example.com')

        self.assertEqual(response_locked.status_code, 200)
        self.assertEqual(response_unknown.status_code, 200)

        content_locked = response_locked.content.decode()
        content_unknown = response_unknown.content.decode()

        self.assertIn('1 hour', content_locked,
                      'Actively-locked account page must show the full configured cooloff.')
        self.assertIn('1 hour', content_unknown,
                      'Unknown account page must show the full configured cooloff.')
        self.assertNotIn('minutes', content_locked,
                         'Locked account page must not show a shorter mid-countdown duration.')

        AccessAttempt.objects.filter(pk=attempt.pk).delete()


class CooldownDisplayTests(TestCase):
    """Unit tests for the _cooldown_remaining helper."""

    def setUp(self):
        AccessAttempt.objects.all().delete()

    def tearDown(self):
        AccessAttempt.objects.all().delete()

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=2))
    def test_mid_countdown_shows_shorter_duration_than_full_cooloff(self):
        """A visit partway through the cooldown must show less than the full configured duration.

        With a 2-hour cooloff and attempt_time set to 1 hour ago the remaining
        time is ~1 hour, which is shorter than the full 2-hour setting.
        """
        attempt = AccessAttempt.objects.create(
            username='testuser@example.com',
            ip_address='1.2.3.4',
            user_agent='test-agent',
            path_info='/login/',
            http_accept='text/html',
            failures_since_start=5,
        )
        one_hour_ago = timezone.now() - datetime.timedelta(hours=1)
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=one_hour_ago)

        _secs, result = _cooldown_remaining(username='testuser@example.com')

        self.assertNotIn('2 hours', result,
                         'Mid-countdown display must not show the full 2-hour cooloff.')
        self.assertNotEqual(result, '',
                            'Mid-countdown display must not be empty.')
        self.assertNotIn('-', result,
                         'Mid-countdown display must not show a negative duration.')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=1))
    def test_expired_cooloff_falls_back_to_full_configured_duration(self):
        """A visit after the cooloff has already expired must fall back to the full configured duration.

        When attempt_time is older than the cooloff window, remaining time is
        negative so _cooldown_display must return the full cooloff, not an empty
        string or a negative value.
        """
        attempt = AccessAttempt.objects.create(
            username='expireduser@example.com',
            ip_address='1.2.3.4',
            user_agent='test-agent',
            path_info='/login/',
            http_accept='text/html',
            failures_since_start=5,
        )
        two_hours_ago = timezone.now() - datetime.timedelta(hours=2)
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=two_hours_ago)

        _secs, result = _cooldown_remaining(username='expireduser@example.com')

        self.assertEqual(result, '1 hour',
                         'Expired cooloff must fall back to the full configured duration ("1 hour").')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(minutes=45))
    def test_no_username_shows_full_configured_cooloff(self):
        """Omitting the username must always return the full configured cooloff duration.

        There is no AccessAttempt to look up, so the function cannot compute a
        remaining time and must fall back to the full setting.
        """
        _secs, result = _cooldown_remaining()

        self.assertEqual(result, '45 minutes',
                         'Without a username the full configured cooloff ("45 minutes") must be shown.')

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(minutes=45))
    def test_unknown_username_returns_same_duration_as_never_locked_username(self):
        """An unknown username must return the same full cooloff as a never-locked known username.

        The lockout page accepts a ?username= query parameter.  An attacker who
        probes /lockout/?username=X must not be able to distinguish "X does not
        exist" from "X exists but has never triggered a lockout" by comparing the
        displayed duration — both must show the full configured cooloff.
        """
        never_locked_user = CustomUser.objects.create_user(
            email='neverlocked@example.com', password='SomeP@ss1'
        )

        secs_unknown, display_unknown = _cooldown_remaining(username='nosuchemail@example.com')
        secs_never_locked, display_never_locked = _cooldown_remaining(username=never_locked_user.email)

        self.assertEqual(
            display_unknown, '45 minutes',
            'Unknown username must show the full configured cooloff, not a different duration.',
        )
        self.assertEqual(
            display_unknown, display_never_locked,
            'Unknown username and never-locked known username must show the same cooloff duration, '
            'so an attacker cannot distinguish account existence from the lockout page.',
        )
        self.assertEqual(
            secs_unknown, secs_never_locked,
            'Cooldown seconds for unknown username must equal those for a never-locked username.',
        )

    @override_settings(AXES_COOLOFF_TIME=datetime.timedelta(hours=2))
    def test_reads_attempt_time_fresh_from_db_on_every_call(self):
        """_cooldown_remaining must query the DB on every call, not cache attempt_time in memory.

        This simulates a server restart mid-cooldown: the AccessAttempt already
        exists in the database when the (new) process calls _cooldown_remaining.
        The function must reflect the stored attempt_time, not any in-memory state
        from a previous call.

        Scenario (2-hour cooloff):
          Call #1 — attempt_time = now (just locked).
                    Remaining ≈ 7200 s.  Bounded assertion: 7100 ≤ seconds_1 ≤ 7200.
          DB update — attempt_time moved to 90 minutes ago (simulates 90 min
                      elapsing, as the DB record would show after a server restart).
          Call #2 — remaining ≈ 1800 s (30 min left).
                    Bounded assertion: 1700 ≤ seconds_2 ≤ 1900.

        An implementation that caches attempt_time from call #1 (now) would
        compute ~7200 s on call #2 as well, violating the upper bound of 1900 s
        and proving that the cached value was used.  Only a fresh DB read can
        return ~1800 s on call #2.
        """
        username = 'restartuser@example.com'
        attempt = AccessAttempt.objects.create(
            username=username,
            ip_address='1.2.3.4',
            user_agent='test-agent',
            path_info='/login/',
            http_accept='text/html',
            failures_since_start=5,
        )
        AccessAttempt.objects.filter(pk=attempt.pk).update(
            attempt_time=timezone.now()
        )

        seconds_1, _display_1 = _cooldown_remaining(username=username)

        self.assertGreaterEqual(seconds_1, 7100,
                                'Call #1 (just locked): remaining must be ≥ 7100 s for a 2-hour cooloff.')
        self.assertLessEqual(seconds_1, 7200,
                             'Call #1 (just locked): remaining must not exceed the 7200 s cooloff.')

        ninety_minutes_ago = timezone.now() - datetime.timedelta(minutes=90)
        AccessAttempt.objects.filter(pk=attempt.pk).update(attempt_time=ninety_minutes_ago)

        seconds_2, display_2 = _cooldown_remaining(username=username)

        self.assertGreaterEqual(seconds_2, 1700,
                                'Call #2 (90 min later): remaining must be ≥ 1700 s (≈30 min).')
        self.assertLessEqual(seconds_2, 1900,
                             'Call #2 (90 min later): remaining must be ≤ 1900 s; '
                             'a cached attempt_time from call #1 would give ~7200 s.')
        self.assertNotIn(
            '-', display_2,
            'Display string must not contain a negative duration.',
        )
