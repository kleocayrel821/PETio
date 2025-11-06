"""
Development settings.
Extends base.py with development-friendly defaults.
"""
from .base import *  # noqa
import os

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-^l*57=_zqohgr5s=z+o2$lwqvp-4-q!m%(m%a6$(*j2bg41onx'

DEBUG = True

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '192.168.1.14',
    '192.168.18.114',
    '192.168.1.8',
    '*',
]

# SQLite for dev
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Email backend for dev (prints emails to console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Dev cache location
CACHES['default']['LOCATION'] = 'petio-dev-cache'

# Run Celery tasks eagerly in dev to simplify local testing
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Device API key used by controller/device_api.py to authenticate firmware requests
PETIO_DEVICE_API_KEY = os.getenv('PETIO_DEVICE_API_KEY', 'petio_secure_key_2025')

# Development-only: allow anonymous UI preview of request detail page
# This MUST stay disabled in production.
DEV_ALLOW_REQUEST_PREVIEW = True