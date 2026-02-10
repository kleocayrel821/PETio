"""
Development settings.
Extends base.py with development-friendly defaults.
"""
import os
from .base import *  # noqa
import dj_database_url

# -----------------------------
# Security settings
# -----------------------------
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-^l*57=_zqohgr5s=z+o2$lwqvp-4-q!m%(m%a6$(*j2bg41onx'
)

# DEBUG mode controlled via environment variable
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ALLOWED_HOSTS from environment variable; fallback to localhost
ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS',
    '127.0.0.1 localhost 192.168.18.9'
).split()


print("DEBUG:", DEBUG)
print("ALLOWED_HOSTS:", ALLOWED_HOSTS)


# -----------------------------
# Time zone
# -----------------------------
TIME_ZONE = 'Asia/Manila'

# -----------------------------
# Database configuration
# -----------------------------
# Default: SQLite for local development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Override with DATABASE_URL if present (e.g., on Render)
database_url = os.environ.get('DATABASE_URL')
if database_url:
    DATABASES['default'] = dj_database_url.parse(database_url)

# -----------------------------
# Email backend for dev
# -----------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# -----------------------------
# Cache for dev
# -----------------------------
CACHES['default']['LOCATION'] = 'petio-dev-cache'

# -----------------------------
# Celery dev mode
# -----------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# -----------------------------
# Device API key
# -----------------------------
PETIO_DEVICE_API_KEY = os.environ.get('51c1ebc55900af5273e5a43c2ba0c140')

# -----------------------------
# Development-only settings
# -----------------------------
DEV_ALLOW_REQUEST_PREVIEW = True  # Only for dev/testing
#MEDIA_URL = '/media/'
#MEDIA_ROOT = BASE_DIR / 'media'
