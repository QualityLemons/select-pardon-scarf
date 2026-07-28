import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

_secret_key = os.environ.get('DJANGO_SECRET_KEY', '')
if not _secret_key:
    raise RuntimeError(
        'DJANGO_SECRET_KEY environment variable is not set. '
        'Set it to a long random string before starting the server.'
    )
SECRET_KEY = _secret_key

DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'

_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'apps.accounts',
    'apps.assessment',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'plec_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'plec_project.wsgi.application'

# Candidate database URLs, in order of preference. DATABASE_URL first, then
# any Heroku colored attachment vars (e.g. HEROKU_POSTGRESQL_SILVER_URL),
# since Heroku sometimes attaches the add-on without promoting it to
# DATABASE_URL. A candidate is only accepted if it parses to a complete
# config (has a database NAME) — this skips empty or stub values like a
# bare "postgres://".
_db_config = None
_db_candidates = [('DATABASE_URL', os.environ.get('DATABASE_URL', ''))]
_heroku_pg_keys = sorted(
    _key for _key in os.environ
    if _key.startswith('HEROKU_POSTGRESQL_') and _key.endswith('_URL')
       and os.environ[_key]
)
if not _db_candidates[0][1] and len(_heroku_pg_keys) > 1:
    raise RuntimeError(
        'DATABASE_URL is not set and multiple HEROKU_POSTGRESQL_*_URL '
        'variables exist (%s). Refusing to guess which database to use — '
        'promote the correct one to DATABASE_URL.' % ', '.join(_heroku_pg_keys)
    )
_db_candidates += [(_key, os.environ[_key]) for _key in _heroku_pg_keys]
for _source_key, _candidate in _db_candidates:
    if not _candidate:
        continue
    _parsed = dj_database_url.parse(
        _candidate,
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
    if not (_parsed.get('ENGINE') and _parsed.get('NAME')):
        continue  # empty or stub value like a bare "postgres://"
    if not DEBUG and 'postgresql' not in _parsed['ENGINE']:
        raise RuntimeError(
            '%s points at a non-PostgreSQL database (%s), which is not '
            'allowed in production.' % (_source_key, _parsed['ENGINE'])
        )
    _db_config = _parsed
    print('Database configured from %s' % _source_key)
    break

if _db_config:
    DATABASES = {'default': _db_config}
elif DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'plec.db',
        }
    }
else:
    # Production without DATABASE_URL. Do NOT raise at import time — build
    # steps like `collectstatic` (e.g. Heroku's build phase) import settings
    # without database access. Instead, configure a dummy backend so any
    # actual database operation fails loudly at runtime with a clear error.
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.dummy',
        }
    }

AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

CHALLENGE_DIR = BASE_DIR / 'challenge'

STATICFILES_DIRS = [
    ('challenge', CHALLENGE_DIR),
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

APPEND_SLASH = False

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1
# Lock out on the (username, ip_address) combination rather than username
# alone. This still stops brute-force attempts from a single source, but
# prevents a remote attacker from remotely locking out a legitimate user's
# account by throwing bad passwords at it from an unrelated IP address.
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_USERNAME_FORM_FIELD = 'username'
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_URL = '/lockout/'
AXES_VERBOSE = False

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

_admins_raw = os.environ.get('DJANGO_ADMINS', '')
ADMINS = []
for entry in _admins_raw.split(','):
    entry = entry.strip()
    if ':' in entry:
        name, email = entry.split(':', 1)
        ADMINS.append((name.strip(), email.strip()))
    elif '@' in entry:
        ADMINS.append(('Admin', entry))

EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@plec.local')

SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# Heroku (and other reverse-proxy hosts) terminate SSL at the load balancer
# and forward requests to the dyno over plain HTTP. Tell Django to trust the
# X-Forwarded-Proto header so SECURE_SSL_REDIRECT does not cause an
# infinite redirect loop and so session/CSRF cookies are set correctly.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Django 4.0+ CSRF: origins that are allowed to POST forms. Populate via a
# comma-separated CSRF_TRUSTED_ORIGINS env var, e.g.:
#   CSRF_TRUSTED_ORIGINS=https://your-app.herokuapp.com,https://your-custom-domain.com
_csrf_origins = os.environ.get('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()]
