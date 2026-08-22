import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from axes.models import AccessAttempt

from apps.accounts.models import CustomUser
from apps.accounts.views import _format_timedelta, _get_cooloff_timedelta, _cooldown_remaining
from apps.assessment.models import MissionLogEntry

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


class DonationPaymentIntentTests(TestCase):
    URL = '/api/donations/payment-intent/'

    def setUp(self):
        self.user = _make_user('donor@example.com')

    def post_json(self, payload):
        return self.client.post(
            self.URL,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_payment_intent_requires_authentication(self):
        response = self.post_json({'amount': 500})

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    @patch('apps.accounts.views.get_stripe_credentials')
    def test_payment_intent_rejects_missing_stripe_configuration(self, credentials):
        credentials.return_value = {'secret_key': '', 'publishable_key': ''}
        self.client.force_login(self.user)

        response = self.post_json({'amount': 500})

        self.assertEqual(response.status_code, 503)
        self.assertIn('not configured', response.json()['error'])

    @patch('apps.accounts.views.get_stripe_credentials')
    def test_payment_intent_rejects_invalid_amount(self, credentials):
        credentials.return_value = {
            'secret_key': 'sk_test_example',
            'publishable_key': 'pk_test_example',
        }
        self.client.force_login(self.user)

        response = self.post_json({'amount': 99})

        self.assertEqual(response.status_code, 400)
        self.assertIn('between £1 and £1,000', response.json()['error'])

    @patch('apps.accounts.views.stripe.PaymentIntent.create')
    @patch('apps.accounts.views.get_stripe_credentials')
    def test_payment_intent_uses_stripe_and_returns_client_secret(
        self, credentials, create_intent
    ):
        credentials.return_value = {
            'secret_key': 'sk_test_example',
            'publishable_key': 'pk_test_example',
        }
        create_intent.return_value = SimpleNamespace(client_secret='pi_test_secret')
        self.client.force_login(self.user)

        response = self.post_json({'amount': 500})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'client_secret': 'pi_test_secret',
            'publishable_key': 'pk_test_example',
        })
        create_intent.assert_called_once_with(
            amount=500,
            currency='gbp',
            automatic_payment_methods={
                'enabled': True,
                'allow_redirects': 'never',
            },
            receipt_email=self.user.email,
            metadata={'source': 'plec_donation', 'user_id': str(self.user.pk)},
            api_key='sk_test_example',
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

    @override_settings(
        AXES_FAILURE_LIMIT=5,
        AXES_COOLOFF_TIME=datetime.timedelta(hours=1),
        AXES_LOCKOUT_PARAMETERS=['username'],
        AXES_USERNAME_FORM_FIELD='username',
        AXES_RESET_ON_SUCCESS=True,
        AXES_LOCKOUT_TEMPLATE='accounts/lockout.html',
        AXES_VERBOSE=False,
    )
    def test_lockout_resets_after_cooldown_expires(self):
        """A locked account must accept the correct password once AXES_COOLOFF_TIME has passed.

        Steps:
          1. Exhaust the failure limit to engage lockout.
          2. Confirm the account is locked (correct password still rejected).
          3. Backdate all AccessAttempt records beyond the cooloff window so that
             axes no longer counts them as active.
          4. Assert that a login attempt with the correct password now succeeds.
        """
        # Step 1 – trigger lockout.
        self._fail_login(times=5)

        # Step 2 – confirm the account is actually locked.
        locked_response = _post_login(self.client, self.user.email, CORRECT_PASSWORD)
        self.assertEqual(
            locked_response.status_code, self.LOCKOUT_STATUS,
            'Account must be locked after reaching the failure limit.',
        )

        # Step 3 – simulate the cooloff window expiring by backdating the
        # AccessAttempt records to two hours ago (beyond the 1-hour cooloff).
        two_hours_ago = timezone.now() - datetime.timedelta(hours=2)
        AccessAttempt.objects.all().update(attempt_time=two_hours_ago)

        # Step 4 – the account must now accept the correct password.
        response = _post_login(self.client, self.user.email, CORRECT_PASSWORD)
        self.assertIn(
            response.status_code, (200, 302),
            'Account must accept the correct password once the cooloff window has expired.',
        )

    @override_settings(
        AXES_FAILURE_LIMIT=5,
        AXES_COOLOFF_TIME=datetime.timedelta(hours=1),
        AXES_LOCKOUT_PARAMETERS=['username'],
        AXES_USERNAME_FORM_FIELD='username',
        AXES_RESET_ON_SUCCESS=True,
        AXES_LOCKOUT_TEMPLATE='accounts/lockout.html',
        AXES_VERBOSE=False,
    )
    def test_failure_counter_resets_to_zero_after_cooldown_expires(self):
        """After the cooldown expires, the failure counter restarts from zero.

        Steps:
          1. Exhaust the failure limit to engage lockout.
          2. Confirm the account is locked.
          3. Backdate all AccessAttempt records beyond the cooloff window.
          4. Log in successfully with the correct password.
          5. Make AXES_FAILURE_LIMIT - 1 more failed attempts.
          6. Assert the account is still accessible (not re-locked prematurely).
        """
        # Step 1 – trigger lockout.
        self._fail_login(times=5)

        # Step 2 – confirm the account is actually locked.
        locked_response = _post_login(self.client, self.user.email, CORRECT_PASSWORD)
        self.assertEqual(
            locked_response.status_code, self.LOCKOUT_STATUS,
            'Account must be locked after reaching the failure limit.',
        )

        # Step 3 – simulate the cooloff window expiring.
        two_hours_ago = timezone.now() - datetime.timedelta(hours=2)
        AccessAttempt.objects.all().update(attempt_time=two_hours_ago)

        # Step 4 – log in successfully; this should reset the failure counter.
        fresh_client = Client(enforce_csrf_checks=False)
        ok_response = _post_login(fresh_client, self.user.email, CORRECT_PASSWORD)
        self.assertIn(
            ok_response.status_code, (200, 302),
            'Account must accept the correct password once the cooloff window has expired.',
        )

        # Step 5 – make AXES_FAILURE_LIMIT - 1 failed attempts on a new client
        # (counter should now be at zero after the successful login above).
        another_client = Client(enforce_csrf_checks=False)
        self._fail_login(times=4, client=another_client)

        # Step 6 – the account must still be accessible after only 4 failures
        # because the counter reset to zero; reaching the limit again requires
        # a full AXES_FAILURE_LIMIT failures.
        still_accessible = _post_login(another_client, self.user.email, CORRECT_PASSWORD)
        self.assertIn(
            still_accessible.status_code, (200, 302),
            'After cooldown expiry and a successful login the failure counter must restart '
            'from zero; AXES_FAILURE_LIMIT - 1 new failures must not re-lock the account.',
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


class AdminPasswordChangeTests(TestCase):
    """
    Confirm that the admin 'Change password' action works correctly and that
    an admin who changes their own password is not locked out of the admin.

    Django's built-in user_change_password() view calls
    update_session_auth_hash() after a successful save, which re-signs the
    current session with the new password hash.  These tests verify that
    behaviour is present for both the "change another user's password" and
    "change own password" paths.
    """

    PASSWORD_CHANGE_URL_NAME = 'admin:accounts_customuser_password_change'
    NEW_PASSWORD = 'NewSecureP@ss99'
    ADMIN_PASSWORD = 'AdminP@ss1'

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.admin = CustomUser.objects.create_superuser(
            email='superadmin@example.com',
            password=self.ADMIN_PASSWORD,
        )
        self.other_user = CustomUser.objects.create_user(
            email='learner@example.com',
            password='LearnerP@ss1',
        )
        self.client.force_login(self.admin)

    def _password_change_url(self, user):
        return reverse(self.PASSWORD_CHANGE_URL_NAME, args=[user.pk])

    # ------------------------------------------------------------------
    # Changing another user's password
    # ------------------------------------------------------------------

    def test_admin_can_load_password_change_form_for_other_user(self):
        """GET the password-change form for a different user returns 200."""
        response = self.client.get(self._password_change_url(self.other_user))
        self.assertEqual(
            response.status_code, 200,
            'Admin must be able to load the password-change form for another user.',
        )

    def test_admin_can_change_another_users_password(self):
        """A valid POST changes the other user's password and redirects to their change page."""
        url = self._password_change_url(self.other_user)
        response = self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })
        self.assertIn(
            response.status_code, (301, 302),
            'Successful password change for another user must redirect.',
        )
        self.other_user.refresh_from_db()
        self.assertTrue(
            self.other_user.check_password(self.NEW_PASSWORD),
            "The other user's password must be updated in the database.",
        )

    def test_mismatched_passwords_are_rejected_for_other_user(self):
        """A POST with mismatched new passwords must fail and not change the password."""
        url = self._password_change_url(self.other_user)
        original_hash = self.other_user.password
        response = self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': 'DoesNotMatch99!',
        })
        self.assertEqual(
            response.status_code, 200,
            'Mismatched passwords must re-render the form (200), not redirect.',
        )
        self.other_user.refresh_from_db()
        self.assertEqual(
            self.other_user.password, original_hash,
            'Mismatched passwords must not alter the stored password hash.',
        )

    # ------------------------------------------------------------------
    # Admin changing their own password — session must stay valid
    # ------------------------------------------------------------------

    def test_admin_can_load_own_password_change_form(self):
        """GET the password-change form for the currently-logged-in admin returns 200."""
        response = self.client.get(self._password_change_url(self.admin))
        self.assertEqual(
            response.status_code, 200,
            'Admin must be able to load the password-change form for themselves.',
        )

    def test_admin_session_remains_valid_after_own_password_change(self):
        """
        After an admin changes their own password they must still be logged in.

        Django's user_change_password() calls update_session_auth_hash() so the
        session is re-signed with the new hash.  Without that call the session
        would be invalidated and the admin would be redirected to the login page
        on their next request — effectively locking themselves out.

        We verify this by checking that a subsequent request to a protected admin
        page returns 200 (still authenticated) rather than a redirect to /login/.
        """
        url = self._password_change_url(self.admin)
        response = self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })
        self.assertIn(
            response.status_code, (301, 302),
            'Successful self-password-change must redirect (form accepted).',
        )

        # The admin must still be authenticated — a protected admin page must
        # return 200, not redirect to the login page.
        admin_home = self.client.get('/admin/')
        self.assertEqual(
            admin_home.status_code, 200,
            'Admin must still be authenticated after changing their own password; '
            'session should remain valid via update_session_auth_hash().',
        )

    def test_admin_password_updated_in_db_after_self_change(self):
        """After a self-password-change the new password hash is persisted."""
        url = self._password_change_url(self.admin)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })
        self.admin.refresh_from_db()
        self.assertTrue(
            self.admin.check_password(self.NEW_PASSWORD),
            "Admin's new password must be stored in the database after self-change.",
        )

    def test_admin_cannot_change_password_with_weak_password(self):
        """A password that fails Django's validators must be rejected."""
        url = self._password_change_url(self.other_user)
        original_hash = self.other_user.password
        response = self.client.post(url, {
            'password1': '123',
            'password2': '123',
        })
        self.assertEqual(
            response.status_code, 200,
            'A weak password must re-render the form (200), not redirect.',
        )
        self.other_user.refresh_from_db()
        self.assertEqual(
            self.other_user.password, original_hash,
            'A weak/invalid password must not alter the stored password hash.',
        )

    def test_admin_cannot_change_password_with_common_password(self):
        """A common password ("password123") must be rejected by the CommonPasswordValidator.

        "password123" appears in Django's common-passwords list so the form must
        refuse it and re-render with a validation error rather than accepting it.
        """
        url = self._password_change_url(self.other_user)
        original_hash = self.other_user.password
        response = self.client.post(url, {
            'password1': 'password123',
            'password2': 'password123',
        })
        self.assertEqual(
            response.status_code, 200,
            'A common password must re-render the form (200), not redirect.',
        )
        self.other_user.refresh_from_db()
        self.assertEqual(
            self.other_user.password, original_hash,
            '"password123" must not alter the stored password hash.',
        )

    def test_common_password_rejection_shows_validation_error_in_response(self):
        """The form must display a visible validation error when a common password is submitted.

        Confirms the response body contains an error message so the admin
        understands why the submission was refused.
        """
        url = self._password_change_url(self.other_user)
        response = self.client.post(url, {
            'password1': 'password123',
            'password2': 'password123',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(
            'too common', content,
            'The form must render a "too common" validation error for "password123".',
        )

    def test_weak_numeric_password_rejection_shows_validation_error_in_response(self):
        """The form must display a visible validation error when a numeric-only password is submitted.

        Covers the NumericPasswordValidator and MinimumLengthValidator paths and
        confirms that at least one error message is rendered.
        """
        url = self._password_change_url(self.other_user)
        response = self.client.post(url, {
            'password1': '123',
            'password2': '123',
        })
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The form must show at least one validator error (short or numeric-only).
        has_error = ('too short' in content or 'entirely numeric' in content
                     or 'at least' in content)
        self.assertTrue(
            has_error,
            'The form must render a validation error message for a short numeric-only password.',
        )

    def test_auth_password_validators_configured(self):
        """settings.AUTH_PASSWORD_VALIDATORS must include all four expected validators.

        This guards against a misconfigured settings file silently accepting
        weak passwords via the admin change-password form.
        """
        from django.conf import settings
        validator_names = {v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS}
        expected = {
            'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
            'django.contrib.auth.password_validation.MinimumLengthValidator',
            'django.contrib.auth.password_validation.CommonPasswordValidator',
            'django.contrib.auth.password_validation.NumericPasswordValidator',
        }
        missing = expected - validator_names
        self.assertFalse(
            missing,
            f'AUTH_PASSWORD_VALIDATORS is missing required validators: {missing}',
        )

    # ------------------------------------------------------------------
    # Privilege-escalation guard: staff (non-superuser) vs superuser
    # ------------------------------------------------------------------

    def _make_staff_client(self):
        """Return a logged-in client for a staff-but-not-superuser account."""
        staff = CustomUser.objects.create_user(
            email='staffonly@example.com',
            password='StaffP@ss1',
            is_staff=True,
        )
        # Grant the generic 'change' permission on CustomUser so the staff
        # account can access the admin, but is_superuser remains False.
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(CustomUser)
        change_perm = Permission.objects.get(content_type=ct, codename='change_customuser')
        staff.user_permissions.add(change_perm)
        staff_client = Client(enforce_csrf_checks=False)
        staff_client.force_login(staff)
        return staff_client, staff

    def test_staff_cannot_load_password_change_form_for_superuser(self):
        """
        A staff account that is not a superuser must not be allowed to open
        the password-change form for a superuser (GET → 403).

        Without this guard a lower-privilege staff user could navigate to
        /admin/accounts/customuser/<superuser_pk>/password/ and take over a
        superuser account by setting a new password.
        """
        staff_client, _staff = self._make_staff_client()
        url = self._password_change_url(self.admin)  # self.admin is a superuser

        response = staff_client.get(url)

        self.assertEqual(
            response.status_code, 403,
            'A non-superuser staff account must receive 403 when loading the '
            'password-change form for a superuser.',
        )

    def test_staff_cannot_post_password_change_for_superuser(self):
        """
        A staff account that is not a superuser must receive 403 when POSTing
        a new password for a superuser.

        This ensures the protection is enforced on both the GET (form display)
        and the POST (form submission) paths so the restriction cannot be
        bypassed by crafting a direct POST request.
        """
        staff_client, _staff = self._make_staff_client()
        url = self._password_change_url(self.admin)
        original_hash = self.admin.password

        response = staff_client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        self.assertEqual(
            response.status_code, 403,
            'A non-superuser staff account must receive 403 when POSTing a '
            'password change for a superuser.',
        )
        self.admin.refresh_from_db()
        self.assertEqual(
            self.admin.password, original_hash,
            "A non-superuser staff account must not alter a superuser's "
            'password hash, even via a direct POST.',
        )

    def test_staff_can_load_password_change_form_for_regular_user(self):
        """
        A staff account with the 'change_customuser' permission may open the
        password-change form for a non-superuser (GET → 200).

        This confirms the restriction targets only superuser accounts and does
        not accidentally block all staff actions.
        """
        staff_client, _staff = self._make_staff_client()
        url = self._password_change_url(self.other_user)  # self.other_user is not a superuser

        response = staff_client.get(url)

        self.assertEqual(
            response.status_code, 200,
            'A staff account with change permission must be able to load the '
            'password-change form for a non-superuser user.',
        )

    # ------------------------------------------------------------------
    # Audit log — password-change entries
    # ------------------------------------------------------------------

    def test_audit_log_entry_created_after_admin_changes_another_users_password(self):
        """A LogEntry is written immediately when an admin successfully changes another user's password.

        The entry must record:
          - user_id  = the acting admin's pk
          - object_id = the target user's pk (as a string)
          - action_flag = CHANGE
          - change_message containing "Password changed"
        """
        from django.contrib.admin.models import LogEntry, CHANGE

        url = self._password_change_url(self.other_user)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        entry = LogEntry.objects.filter(
            user_id=self.admin.pk,
            object_id=str(self.other_user.pk),
            action_flag=CHANGE,
        ).order_by('-action_time').first()

        self.assertIsNotNone(
            entry,
            'A LogEntry must be created immediately after an admin changes another user\'s password.',
        )
        self.assertIn(
            'Password changed', entry.change_message,
            'The LogEntry change_message must contain "Password changed".',
        )

    def test_audit_log_entry_records_correct_user_id(self):
        """The LogEntry user_id must be the acting admin's pk, not the target user's pk."""
        from django.contrib.admin.models import LogEntry, CHANGE

        url = self._password_change_url(self.other_user)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        entry = LogEntry.objects.filter(
            object_id=str(self.other_user.pk),
            action_flag=CHANGE,
        ).order_by('-action_time').first()

        self.assertIsNotNone(entry, 'A LogEntry must exist after a password change.')
        self.assertEqual(
            entry.user_id, self.admin.pk,
            'LogEntry.user_id must be the acting admin\'s pk.',
        )

    def test_audit_log_entry_records_correct_object_id(self):
        """The LogEntry object_id must be the target user's pk (as a string)."""
        from django.contrib.admin.models import LogEntry, CHANGE

        url = self._password_change_url(self.other_user)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        entry = LogEntry.objects.filter(
            user_id=self.admin.pk,
            action_flag=CHANGE,
        ).order_by('-action_time').first()

        self.assertIsNotNone(entry, 'A LogEntry must exist after a password change.')
        self.assertEqual(
            entry.object_id, str(self.other_user.pk),
            'LogEntry.object_id must be the target user\'s pk (as a string).',
        )

    def test_audit_log_entry_uses_change_action_flag(self):
        """The LogEntry action_flag must be CHANGE, not ADD or DELETE."""
        from django.contrib.admin.models import LogEntry, CHANGE

        url = self._password_change_url(self.other_user)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        entry = LogEntry.objects.filter(
            user_id=self.admin.pk,
            object_id=str(self.other_user.pk),
        ).order_by('-action_time').first()

        self.assertIsNotNone(entry, 'A LogEntry must exist after a password change.')
        self.assertEqual(
            entry.action_flag, CHANGE,
            'LogEntry.action_flag must be CHANGE after an admin password reset.',
        )

    def test_audit_log_entry_contains_no_password_or_hash(self):
        """The LogEntry must not store any password or hash fragment.

        Neither the new plaintext password nor any portion of a password hash
        (indicated by common hash algorithm prefixes) must appear in the
        change_message or object_repr fields.
        """
        from django.contrib.admin.models import LogEntry, CHANGE

        url = self._password_change_url(self.other_user)
        self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        entry = LogEntry.objects.filter(
            user_id=self.admin.pk,
            object_id=str(self.other_user.pk),
            action_flag=CHANGE,
        ).order_by('-action_time').first()

        self.assertIsNotNone(entry, 'A LogEntry must exist after a password change.')

        # The plaintext password must not appear in any logged field.
        self.assertNotIn(
            self.NEW_PASSWORD, entry.change_message,
            'The new plaintext password must not appear in LogEntry.change_message.',
        )
        self.assertNotIn(
            self.NEW_PASSWORD, entry.object_repr,
            'The new plaintext password must not appear in LogEntry.object_repr.',
        )

        # Common hash algorithm prefixes used by Django's hashers must not appear.
        for hash_prefix in ('pbkdf2_sha256$', 'argon2$', 'bcrypt$', 'sha1$'):
            self.assertNotIn(
                hash_prefix, entry.change_message,
                f'Password hash prefix "{hash_prefix}" must not appear in LogEntry.change_message.',
            )
            self.assertNotIn(
                hash_prefix, entry.object_repr,
                f'Password hash prefix "{hash_prefix}" must not appear in LogEntry.object_repr.',
            )

    def test_failed_password_change_does_not_create_audit_log_entry(self):
        """A failed password-change POST (mismatched passwords) must not create a LogEntry.

        The audit log must only record successful changes.  A form validation
        failure that re-renders the page (200) must leave the LogEntry table
        unchanged.
        """
        from django.contrib.admin.models import LogEntry, CHANGE

        count_before = LogEntry.objects.filter(
            user_id=self.admin.pk,
            object_id=str(self.other_user.pk),
            action_flag=CHANGE,
        ).count()

        url = self._password_change_url(self.other_user)
        response = self.client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': 'DoesNotMatch99!',
        })

        self.assertEqual(
            response.status_code, 200,
            'Mismatched passwords must re-render the form (200), not redirect.',
        )

        count_after = LogEntry.objects.filter(
            user_id=self.admin.pk,
            object_id=str(self.other_user.pk),
            action_flag=CHANGE,
        ).count()

        self.assertEqual(
            count_before, count_after,
            'A failed password-change attempt must not create a new LogEntry.',
        )


class ReflectionEntriesSurvivePasswordChangeTests(TestCase):
    """
    Confirm that MissionLogEntry rows are not affected by a password change.

    MissionLogEntry.user uses on_delete=CASCADE, so the entries would only be
    lost if the user record itself were deleted and re-created.  A password
    change must update the existing row's password hash in-place; the PK must
    not change and all related rows must remain intact.

    Two password-change paths are exercised:

    1. Learner self-service — POST /password-change/ (Django's built-in
       PasswordChangeView wired in plec_project/urls.py).
    2. Admin-initiated change via the Django admin panel
       (admin:accounts_customuser_password_change).
    """

    OLD_PASSWORD = 'OldSecureP@ss1'
    NEW_PASSWORD = 'NewSecureP@ss99'
    ADMIN_PASSWORD = 'AdminP@ss1'

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.learner = CustomUser.objects.create_user(
            email='learner-reflect@example.com',
            password=self.OLD_PASSWORD,
        )
        # Create three reflection entries across two different levels.
        MissionLogEntry.objects.create(
            user=self.learner,
            level='level-1',
            skill='Skill A',
            notes='First reflection',
            rating=4,
        )
        MissionLogEntry.objects.create(
            user=self.learner,
            level='level-1',
            skill='Skill B',
            notes='Second reflection',
            rating=3,
        )
        MissionLogEntry.objects.create(
            user=self.learner,
            level='level-2',
            skill='Skill C',
            notes='Third reflection on level 2',
            rating=5,
        )

    # ------------------------------------------------------------------
    # Path 1: learner self-service /password-change/
    # ------------------------------------------------------------------

    def test_reflection_entries_survive_learner_self_password_change(self):
        """
        All MissionLogEntry rows must survive a learner changing their own
        password via POST /password-change/.

        Steps:
          1. Record the IDs and content of all existing reflection entries.
          2. Log in and POST the /password-change/ form with a valid new password.
          3. Confirm the change succeeded (redirect response).
          4. Assert every entry is still present with the same pk, level, notes,
             and user FK — no row was deleted or re-parented.
        """
        entries_before = list(
            MissionLogEntry.objects.filter(user=self.learner)
            .order_by('id')
            .values('id', 'level', 'skill', 'notes', 'rating', 'user_id')
        )
        self.assertEqual(len(entries_before), 3, 'Pre-condition: 3 entries must exist before the change.')

        self.client.force_login(self.learner)
        response = self.client.post('/password-change/', {
            'old_password': self.OLD_PASSWORD,
            'new_password1': self.NEW_PASSWORD,
            'new_password2': self.NEW_PASSWORD,
        })

        self.assertIn(
            response.status_code, (301, 302),
            'POST /password-change/ with valid credentials must redirect (indicating success).',
        )

        # Confirm the password was actually changed.
        self.learner.refresh_from_db()
        self.assertTrue(
            self.learner.check_password(self.NEW_PASSWORD),
            'Learner password must be updated in the database.',
        )

        # All three entries must still exist, owned by the same user.
        entries_after = list(
            MissionLogEntry.objects.filter(user=self.learner)
            .order_by('id')
            .values('id', 'level', 'skill', 'notes', 'rating', 'user_id')
        )
        self.assertEqual(
            entries_after, entries_before,
            'All reflection entries must be unchanged after a learner self-password-change; '
            'no entry must be deleted, re-parented, or have its content altered.',
        )

    def test_learner_user_pk_unchanged_after_self_password_change(self):
        """
        The learner's primary key must not change after a self-password-change.

        A PK change would indicate the user row was deleted and re-created,
        which would silently cascade-delete all MissionLogEntry rows.
        """
        pk_before = self.learner.pk

        self.client.force_login(self.learner)
        self.client.post('/password-change/', {
            'old_password': self.OLD_PASSWORD,
            'new_password1': self.NEW_PASSWORD,
            'new_password2': self.NEW_PASSWORD,
        })

        self.learner.refresh_from_db()
        self.assertEqual(
            self.learner.pk, pk_before,
            'Learner PK must be identical before and after a password change; '
            'a changed PK implies delete-and-recreate, which cascades to reflection entries.',
        )

    def test_entry_count_unchanged_after_self_password_change(self):
        """
        The total number of MissionLogEntry rows for the learner must not
        decrease after a self-password-change.
        """
        count_before = MissionLogEntry.objects.filter(user=self.learner).count()

        self.client.force_login(self.learner)
        self.client.post('/password-change/', {
            'old_password': self.OLD_PASSWORD,
            'new_password1': self.NEW_PASSWORD,
            'new_password2': self.NEW_PASSWORD,
        })

        count_after = MissionLogEntry.objects.filter(user=self.learner).count()
        self.assertEqual(
            count_after, count_before,
            f'Expected {count_before} reflection entries after password change, '
            f'but found {count_after}.',
        )

    # ------------------------------------------------------------------
    # Path 2: admin-initiated password change via the admin panel
    # ------------------------------------------------------------------

    def test_reflection_entries_survive_admin_password_change(self):
        """
        All MissionLogEntry rows must survive an admin changing the learner's
        password via the Django admin panel.

        Steps:
          1. Record the IDs and content of all existing entries.
          2. Log in as a superadmin and POST the admin password-change form.
          3. Confirm the change succeeded (redirect response).
          4. Assert every entry is still present, unchanged, and owned by the
             same user.
        """
        entries_before = list(
            MissionLogEntry.objects.filter(user=self.learner)
            .order_by('id')
            .values('id', 'level', 'skill', 'notes', 'rating', 'user_id')
        )
        self.assertEqual(len(entries_before), 3, 'Pre-condition: 3 entries must exist before the change.')

        admin = CustomUser.objects.create_superuser(
            email='superadmin-reflect@example.com',
            password=self.ADMIN_PASSWORD,
        )
        admin_client = Client(enforce_csrf_checks=False)
        admin_client.force_login(admin)

        url = reverse('admin:accounts_customuser_password_change', args=[self.learner.pk])
        response = admin_client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        self.assertIn(
            response.status_code, (301, 302),
            'Admin password-change POST with valid passwords must redirect (indicating success).',
        )

        # Confirm the password was actually changed.
        self.learner.refresh_from_db()
        self.assertTrue(
            self.learner.check_password(self.NEW_PASSWORD),
            "Learner's password must be updated in the database after admin change.",
        )

        # All three entries must still exist, owned by the same user.
        entries_after = list(
            MissionLogEntry.objects.filter(user=self.learner)
            .order_by('id')
            .values('id', 'level', 'skill', 'notes', 'rating', 'user_id')
        )
        self.assertEqual(
            entries_after, entries_before,
            'All reflection entries must be unchanged after an admin-initiated password-change; '
            'no entry must be deleted, re-parented, or have its content altered.',
        )

    def test_learner_user_pk_unchanged_after_admin_password_change(self):
        """
        The learner's primary key must not change after an admin changes their
        password via the admin panel.
        """
        pk_before = self.learner.pk

        admin = CustomUser.objects.create_superuser(
            email='superadmin-pk@example.com',
            password=self.ADMIN_PASSWORD,
        )
        admin_client = Client(enforce_csrf_checks=False)
        admin_client.force_login(admin)

        url = reverse('admin:accounts_customuser_password_change', args=[self.learner.pk])
        admin_client.post(url, {
            'password1': self.NEW_PASSWORD,
            'password2': self.NEW_PASSWORD,
        })

        self.learner.refresh_from_db()
        self.assertEqual(
            self.learner.pk, pk_before,
            'Learner PK must be identical before and after an admin-initiated password change.',
        )
