import datetime
import json
import time

from axes.helpers import get_lockout_response
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse

import stripe

from .forms import EditProfileForm, RegistrationForm
from .stripe_client import get_stripe_credentials


def _post_login_url(user):
    """Staff go to the Django admin; regular learners go to the training game."""
    return '/admin/' if user.is_staff else '/'


def _get_cooloff_timedelta():
    """Return AXES_COOLOFF_TIME as a timedelta regardless of how it is configured."""
    raw = getattr(settings, 'AXES_COOLOFF_TIME', 1)
    if callable(raw):
        result = raw(None)
        if isinstance(result, datetime.timedelta):
            return result
        return datetime.timedelta(hours=result)
    if isinstance(raw, datetime.timedelta):
        return raw
    return datetime.timedelta(hours=raw)


def _format_timedelta(delta):
    """Format a timedelta as a human-readable string rounded to minutes."""
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60

    if hours == 0 and minutes == 0:
        return 'less than 1 minute'

    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return ' and '.join(parts)


def _cooldown_remaining(username=None):
    """
    Return (seconds_remaining, display_string) for the lockout cooldown.

    When a username is supplied we look up the most recent AccessAttempt and
    compute how much of the cooldown is actually left.  Falls back to the full
    configured duration when the attempt record is not found.
    """
    cooloff = _get_cooloff_timedelta()

    if username:
        attempt = (
            AccessAttempt.objects
            .filter(username=username)
            .order_by('-attempt_time')
            .first()
        )
        if attempt is not None:
            now = timezone.now()
            unlock_at = attempt.attempt_time + cooloff
            remaining = unlock_at - now
            if remaining.total_seconds() > 0:
                secs = int(remaining.total_seconds())
                return secs, _format_timedelta(remaining)

    secs = max(0, int(cooloff.total_seconds()))
    return secs, _format_timedelta(cooloff)


class LoginView(View):
    template_name = 'accounts/login.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(_post_login_url(request.user))
        form = AuthenticationForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        credentials = {'username': username, 'password': password}

        try:
            user = authenticate(request, username=username, password=password)
        except PermissionDenied:
            return get_lockout_response(request, credentials)

        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect(_post_login_url(user))

        form = AuthenticationForm(request, data=request.POST)
        return render(request, self.template_name, {'form': form, 'error': 'Invalid email or password.'})


class LockoutView(View):
    template_name = 'accounts/lockout.html'

    def get(self, request):
        cooldown_seconds, cooldown_display = _cooldown_remaining()
        return render(request, self.template_name, {
            'cooldown_display': cooldown_display,
            'cooldown_seconds': cooldown_seconds,
        })


class RegisterView(View):
    template_name = 'accounts/register.html'

    def get(self, request):
        if request.user.is_authenticated:
            return redirect('/')
        return render(request, self.template_name, {'form': RegistrationForm()})

    def post(self, request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            # form.save() silently no-ops (returns None) when the email is
            # already registered rather than disclosing the collision. We
            # deliberately do NOT log the caller in here, even for a newly
            # created account: doing so would make the response's
            # authentication side effects (session cookie issued vs. not)
            # an observable oracle for account existence. Instead every
            # valid submission gets the exact same response — redirect to
            # the login page, no session established — regardless of
            # whether an account was created or already existed.
            form.save()
            return redirect('/login/')
        return render(request, self.template_name, {'form': form})


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('/login/')


class RateLimitedPasswordResetView(auth_views.PasswordResetView):
    """
    Wraps Django's built-in PasswordResetView with email-keyed rate limiting.

    Uses the same failure limit and cooloff window as the login lockout
    (AXES_FAILURE_LIMIT / AXES_COOLOFF_TIME) so the policy is consistent
    across all authentication-related endpoints.  The counter is keyed on
    the submitted email address rather than IP address, matching the intent
    of the login lockout policy.
    """

    def _rate_limit_config(self):
        limit = getattr(settings, 'AXES_FAILURE_LIMIT', 5)
        window = int(_get_cooloff_timedelta().total_seconds())
        return limit, window

    def post(self, request, *args, **kwargs):
        email = request.POST.get('email', '').lower().strip()
        limit, window = self._rate_limit_config()

        if email:
            attempts_key = f'pwd_reset_attempts:{email}'
            start_key = f'pwd_reset_start:{email}'

            # cache.add only writes when the key is absent — this anchors the
            # window start time and initialises the counter atomically.
            cache.add(attempts_key, 0, window)
            cache.add(start_key, time.time(), window)

            count = cache.incr(attempts_key)

            if count > limit:
                start = cache.get(start_key, time.time() - window)
                elapsed = time.time() - start
                remaining_secs = max(0, int(window - elapsed))
                remaining_display = _format_timedelta(
                    datetime.timedelta(seconds=remaining_secs)
                )
                return render(
                    request,
                    'registration/password_reset_rate_limited.html',
                    {
                        'cooldown_display': remaining_display,
                        'cooldown_seconds': remaining_secs,
                    },
                    status=429,
                )

        return super().post(request, *args, **kwargs)


class EditProfileView(LoginRequiredMixin, View):
    template_name = 'accounts/edit_profile.html'
    login_url = '/login/'

    def get(self, request):
        form = EditProfileForm(
            user=request.user,
            initial={
                'first_name': request.user.first_name,
                'last_name':  request.user.last_name,
                'email':      request.user.email,
            },
        )
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = EditProfileForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect('/profile/edit/?saved=1')
        return render(request, self.template_name, {'form': form})


class DonateView(LoginRequiredMixin, TemplateView):
    template_name = 'challenge/donate.html'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stripe_publishable_key'] = get_stripe_credentials()['publishable_key']
        return context


class DonationPaymentIntentView(LoginRequiredMixin, View):
    """Create a Stripe PaymentIntent for an in-page PLeC donation."""

    login_url = '/login/'

    def post(self, request):
        credentials = get_stripe_credentials()
        if not credentials['secret_key'] or not credentials['publishable_key']:
            return JsonResponse(
                {'error': 'Donations are not configured yet. Please try again later.'},
                status=503,
            )

        try:
            payload = json.loads(request.body or '{}')
            amount = int(payload.get('amount', 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'error': 'Enter a valid donation amount.'}, status=400)

        # Stripe amounts are expressed in the smallest currency unit (pence).
        # Keep the donation range deliberately bounded for this public endpoint.
        if amount < 100 or amount > 100000:
            return JsonResponse(
                {'error': 'Choose an amount between £1 and £1,000.'},
                status=400,
            )

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount,
                currency='gbp',
                automatic_payment_methods={
                    'enabled': True,
                    'allow_redirects': 'never',
                },
                receipt_email=request.user.email,
                metadata={
                    'source': 'plec_donation',
                    'user_id': str(request.user.pk),
                },
                api_key=credentials['secret_key'],
            )
        except stripe.error.StripeError:
            return JsonResponse(
                {'error': 'Stripe could not start the payment. Please try again.'},
                status=502,
            )

        return JsonResponse({
            'client_secret': intent.client_secret,
            'publishable_key': credentials['publishable_key'],
        })
