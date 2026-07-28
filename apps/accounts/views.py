import datetime

from axes.helpers import get_lockout_response
from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from .forms import RegistrationForm


def _post_login_url(user):
    """Staff go to the Django admin; regular learners go to the training game."""
    return '/admin/' if user.is_staff else '/'

    In LoginView.get, replace return redirect('admin:index') with:

return redirect(_post_login_url(request.user))

    In LoginView.post, replace return redirect('/admin/') with:

return redirect(_post_login_url(user))

plec_project/settings.py — one line:
LOGIN_REDIRECT_URL = '/'   # was '/admin/'

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
            return redirect('admin:index')
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
            return redirect('/admin/')

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
            return redirect('/challenge/')
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
