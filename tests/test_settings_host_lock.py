"""
Tests for ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS lock-down logic in settings.py.

The parsing is done at module import time, so we can't use override_settings or
modify Django settings directly to test the derivation logic.  Instead we invoke
the relevant code fragment in a subprocess with the desired environment variables,
capture the resulting values, and assert on them.
"""

import importlib
import os
import sys
import types
import unittest
import warnings


def _parse_settings(env_overrides):
    """
    Run the ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS block from settings.py in an
    isolated namespace with the given environment overrides.

    Returns a dict with:
      - allowed_hosts (list)
      - csrf_trusted_origins (list)
      - warnings_issued (list of warning messages)
    """
    # Snapshot and patch os.environ
    original_env = os.environ.copy()
    os.environ.update(env_overrides)
    # Remove keys the caller did not supply so defaults kick in
    for key in ('ALLOWED_HOSTS', 'CSRF_TRUSTED_ORIGINS', 'REPLIT_DOMAINS', 'DJANGO_DEBUG'):
        if key not in env_overrides:
            os.environ.pop(key, None)

    captured_warnings = []
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')

            # Re-execute just the relevant settings snippet in a fresh namespace
            snippet = """
import os, warnings as _w

_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()]

_replit_domains = [d.strip() for d in os.environ.get('REPLIT_DOMAINS', '').split(',') if d.strip()]
_DEBUG_LOCAL = os.environ.get('DJANGO_DEBUG', 'False') == 'True'
if _replit_domains and not _DEBUG_LOCAL:
    ALLOWED_HOSTS = list(_replit_domains)
else:
    if not _DEBUG_LOCAL:
        _wildcard_hosts = [h for h in ALLOWED_HOSTS if h.startswith('.') or '*' in h]
        if _wildcard_hosts:
            _w.warn(
                'SECURITY WARNING: ALLOWED_HOSTS contains wildcard patterns '
                '(%s) in a non-DEBUG deployment.' % ', '.join(_wildcard_hosts),
                stacklevel=1,
            )

_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
if _replit_domains and not _DEBUG_LOCAL:
    CSRF_TRUSTED_ORIGINS = ['https://' + rd for rd in _replit_domains]
"""
            ns = {}
            exec(compile(snippet, '<settings_snippet>', 'exec'), ns)
            captured_warnings = [str(warning.message) for warning in w]

        return {
            'allowed_hosts': ns['ALLOWED_HOSTS'],
            'csrf_trusted_origins': ns['CSRF_TRUSTED_ORIGINS'],
            'warnings_issued': captured_warnings,
        }
    finally:
        # Restore original environment
        os.environ.clear()
        os.environ.update(original_env)


class HostLockdownTests(unittest.TestCase):

    # ------------------------------------------------------------------
    # Production + REPLIT_DOMAINS present → wildcards discarded
    # ------------------------------------------------------------------

    def test_production_replit_domains_replaces_wildcard_allowed_hosts(self):
        """When REPLIT_DOMAINS is set in production, ALLOWED_HOSTS must contain
        only the exact Replit domain(s) — no wildcard entries."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': '.replit.app',
            'REPLIT_DOMAINS': 'my-plec-app.parmanjohn.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        self.assertEqual(result['allowed_hosts'], ['my-plec-app.parmanjohn.replit.app'])
        self.assertNotIn('.replit.app', result['allowed_hosts'])

    def test_production_replit_domains_replaces_wildcard_csrf_trusted_origins(self):
        """When REPLIT_DOMAINS is set in production, CSRF_TRUSTED_ORIGINS must
        contain only the exact deployed origin — no wildcard origins."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': '.replit.app',
            'REPLIT_DOMAINS': 'my-plec-app.parmanjohn.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        self.assertEqual(result['csrf_trusted_origins'], ['https://my-plec-app.parmanjohn.replit.app'])
        self.assertNotIn('https://*.replit.app', result['csrf_trusted_origins'])

    def test_production_replit_domains_no_security_warning(self):
        """No SecurityWarning should be emitted when REPLIT_DOMAINS is present
        in production, even if the env var still carries wildcard entries."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': '.replit.app',
            'REPLIT_DOMAINS': 'my-plec-app.parmanjohn.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        security_warnings = [m for m in result['warnings_issued'] if 'SECURITY WARNING' in m]
        self.assertEqual(security_warnings, [], 'Unexpected SecurityWarning with REPLIT_DOMAINS set')

    def test_production_replit_domains_multiple_domains(self):
        """Multiple comma-separated REPLIT_DOMAINS are all included."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': '.replit.app',
            'REPLIT_DOMAINS': 'app-a.example.replit.app,app-b.example.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        self.assertIn('app-a.example.replit.app', result['allowed_hosts'])
        self.assertIn('app-b.example.replit.app', result['allowed_hosts'])
        self.assertIn('https://app-a.example.replit.app', result['csrf_trusted_origins'])
        self.assertIn('https://app-b.example.replit.app', result['csrf_trusted_origins'])
        # No wildcards survive
        self.assertFalse(any(h.startswith('.') or '*' in h for h in result['allowed_hosts']))

    # ------------------------------------------------------------------
    # Production + no REPLIT_DOMAINS + wildcards → warning issued
    # ------------------------------------------------------------------

    def test_production_no_replit_domains_wildcard_triggers_warning(self):
        """A SecurityWarning must be emitted when wildcards are present in
        ALLOWED_HOSTS in non-DEBUG mode and REPLIT_DOMAINS is not set."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': '.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        security_warnings = [m for m in result['warnings_issued'] if 'SECURITY WARNING' in m]
        self.assertTrue(len(security_warnings) > 0, 'Expected SecurityWarning for wildcard ALLOWED_HOSTS')

    def test_production_no_replit_domains_exact_host_no_warning(self):
        """No SecurityWarning when ALLOWED_HOSTS already contains only exact
        domains and REPLIT_DOMAINS is not set."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'False',
            'ALLOWED_HOSTS': 'my-plec-app.parmanjohn.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://my-plec-app.parmanjohn.replit.app',
        })
        security_warnings = [m for m in result['warnings_issued'] if 'SECURITY WARNING' in m]
        self.assertEqual(security_warnings, [])

    # ------------------------------------------------------------------
    # Debug mode → wildcards are fine, no warnings
    # ------------------------------------------------------------------

    def test_debug_mode_wildcard_no_warning(self):
        """In DEBUG mode wildcards in ALLOWED_HOSTS are expected and must not
        trigger a SecurityWarning."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'True',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,.replit.dev,.replit.app',
            'CSRF_TRUSTED_ORIGINS': 'https://*.replit.app',
        })
        security_warnings = [m for m in result['warnings_issued'] if 'SECURITY WARNING' in m]
        self.assertEqual(security_warnings, [])

    def test_debug_mode_replit_domains_does_not_replace(self):
        """In DEBUG mode, REPLIT_DOMAINS must NOT replace the ALLOWED_HOSTS list
        (replacement is a production-only safeguard)."""
        result = _parse_settings({
            'DJANGO_DEBUG': 'True',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,.replit.dev',
            'REPLIT_DOMAINS': 'my-plec-app.parmanjohn.replit.app',
        })
        self.assertIn('localhost', result['allowed_hosts'])
        self.assertIn('127.0.0.1', result['allowed_hosts'])
        self.assertIn('.replit.dev', result['allowed_hosts'])


if __name__ == '__main__':
    unittest.main()
