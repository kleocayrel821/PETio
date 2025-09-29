"""
AppConfig for accounts app to ensure signals are registered.
"""
from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Import signals to ensure profile is created for custom User
        from . import signals  # noqa: F401