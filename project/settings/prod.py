"""
Production settings.
Extends base.py and reads secrets from environment.

Required environment variables (prod):
- DJANGO_SECRET_KEY
- DJANGO_ALLOWED_HOSTS (comma-separated)
- DJANGO_CSRF_TRUSTED_ORIGINS (comma-separated)
- POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT
- EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, DEFAULT_FROM_EMAIL
"""
from .base import *  # noqa
import os
from os import environ

DEBUG = False

# SECRET KEY from environment
SECRET_KEY = environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise RuntimeError('DJANGO_SECRET_KEY environment variable is required in production')

# Allowed hosts and CSRF trusted origins
ALLOWED_HOSTS = environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if environ.get('DJANGO_ALLOWED_HOSTS') else []
CSRF_TRUSTED_ORIGINS = environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if environ.get('DJANGO_CSRF_TRUSTED_ORIGINS') else []

# Database: PostgreSQL via environment
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': environ.get('POSTGRES_DB', ''),
        'USER': environ.get('POSTGRES_USER', ''),
        'PASSWORD': environ.get('POSTGRES_PASSWORD', ''),
        'HOST': environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': environ.get('POSTGRES_PORT', '5432'),
    }
}

# Email: SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_HOST_USER = environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = environ.get('DEFAULT_FROM_EMAIL', EMAIL_HOST_USER)

# Security headers and cookies
SECURE_SSL_REDIRECT = environ.get('SECURE_SSL_REDIRECT', 'true').lower() == 'true'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Additional hardening
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = int(environ.get('SECURE_HSTS_SECONDS', '3600'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = environ.get('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'true').lower() == 'true'
SECURE_HSTS_PRELOAD = environ.get('SECURE_HSTS_PRELOAD', 'true').lower() == 'true'

# Static files: optionally use WhiteNoise in prod
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Logging: more strict for Django, include request ID if using middleware later
LOGGING['loggers']['django']['level'] = 'ERROR'