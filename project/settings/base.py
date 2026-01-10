"""
Base settings for the Petio Django project.
Shared configuration for dev and prod. Environment-specific overrides live in
`project/settings/dev.py` and `project/settings/prod.py`.
"""
import dj_database_url
from pathlib import Path
import os

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Core Django settings
INSTALLED_APPS = [
    'cloudinary',
    'cloudinary_storage',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'channels',
    # Local apps
    'accounts',
    'controller',
    'marketplace',
    'social',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'controller.middleware.request_id.RequestIDMiddleware',
]

ROOT_URLCONF = 'project.urls'
WSGI_APPLICATION = 'project.wsgi.application'
ASGI_APPLICATION = 'project.asgi.application'

# Templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'project.context_processors.device_id_context',
                'project.context_processors.app_context',
                'project.context_processors.unread_notifications_count',
            ],
        },
    }
]

# Database: leave to environment-specific files; default SQLite fallback
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DATABASES["default"] = dj_database_url.parse("postgresql://petio_django_render_user:dtYMRTtVzZ49QBqZLkTlBCvkYdoK6RM3@dpg-d5eemo2li9vc73dfn0d0-a.oregon-postgres.render.com/petio_django_render")


# Authentication
AUTH_USER_MODEL = 'accounts.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static & Media
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# DRF (keep simple defaults; apps enforce auth in views/tests)
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'feed_now': '2/minute',
        'device_status': '120/minute',
    },
}

# Cache: local memory by default; dev overrides LOCATION
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'petio-cache',
    }
}

# Channels: in-memory layer for local/dev usage
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# Celery configuration; dev may run tasks eagerly
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
CELERY_TASK_ROUTES = {
    'marketplace.tasks.send_notification_email': {'queue': 'notifications'},
}
# Device/API settings
PETIO_DEVICE_API_KEY = os.getenv('PETIO_DEVICE_API_KEY')
DEVICE_ID = os.getenv('DEVICE_ID', 'feeder-1')
DEVICE_HEARTBEAT_TTL = int(os.getenv('DEVICE_HEARTBEAT_TTL', '90'))

#MEDIA_URL = '/media/'