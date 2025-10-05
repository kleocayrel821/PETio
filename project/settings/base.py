"""
Base settings shared by all environments.
Import this module in dev.py/prod.py and override environment-specific values.
"""
from pathlib import Path
import os

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Core Django settings
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'app',
    'marketplace',
    'social',
    'rest_framework',
    'accounts.apps.AccountsConfig',
]

MIDDLEWARE = [
    'project.middleware.AdminSessionCookieMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'project.middleware.DisableAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'project.context_processors.resolve_logout_url_name',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'
ASGI_APPLICATION = 'project.asgi.application'

# Channels (in-memory by default; dev overrides may keep this)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# Static & media
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Auth & defaults
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# Caches (simple default; dev can keep locmem)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'petio-cache',
    }
}

# Logging (baseline)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'app': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'app.views': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
    },
}

# Authentication redirects
LOGIN_REDIRECT_URL = 'accounts:profile'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'login'

# Feature flags
# Disable authentication globally when set in environment (for demos/tests only)
DISABLE_AUTH = os.environ.get('DJANGO_DISABLE_AUTH', 'false').lower() == 'true'
 
# Admin session isolation (used by AdminSessionCookieMiddleware)
# These control the separate cookie used only for /admin/ paths in dev.
ADMIN_SESSION_COOKIE_NAME = os.environ.get('DJANGO_ADMIN_SESSION_COOKIE_NAME', 'adminid')
ADMIN_SESSION_COOKIE_PATH = os.environ.get('DJANGO_ADMIN_SESSION_COOKIE_PATH', '/admin')

# Account activation requirement (email confirmation)
# In dev, default to False so users can log in immediately after signup.
ACCOUNT_ACTIVATION_REQUIRED = os.environ.get('DJANGO_ACCOUNT_ACTIVATION_REQUIRED', 'false').lower() == 'true'
MARKETPLACE_RESET = os.environ.get('MARKETPLACE_RESET', 'false').lower() == 'true'

# Celery configuration (defaults suitable for local dev; override via env)
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TASK_ROUTES = {
    'marketplace.tasks.send_notification_email': {'queue': 'notifications'},
}
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_ANNOTATIONS = {'*': {'rate_limit': '10/s'}}