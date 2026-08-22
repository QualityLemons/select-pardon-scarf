"""Secure Stripe credential lookup for Replit and conventional deployments."""

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings


def get_stripe_credentials():
    """Return fresh Stripe credentials without storing them in source control.

    Heroku and other conventional deployments use their own config vars. In a
    Replit environment, credentials are fetched from the connected Stripe
    integration on each request so rotated credentials are picked up safely.
    """
    if settings.STRIPE_SECRET_KEY and settings.STRIPE_PUBLISHABLE_KEY:
        return {
            'secret_key': settings.STRIPE_SECRET_KEY,
            'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        }

    hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
    identity = os.environ.get('REPL_IDENTITY')
    renewal = os.environ.get('WEB_REPL_RENEWAL')
    if not hostname or not (identity or renewal):
        return {'secret_key': '', 'publishable_key': ''}

    token = 'repl ' + identity if identity else 'depl ' + renewal
    request = Request(
        'https://%s/api/v2/connection?include_secrets=true&connector_names=stripe' % hostname,
        headers={'Accept': 'application/json', 'X_REPLIT_TOKEN': token},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return {'secret_key': '', 'publishable_key': ''}

    items = payload.get('items') or []
    connection_settings = items[0].get('settings', {}) if items else {}
    return {
        'secret_key': connection_settings.get('secret', ''),
        'publishable_key': connection_settings.get('publishable', ''),
    }