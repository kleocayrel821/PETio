from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'controller'

    def ready(self):
        # Import signals to wire model change broadcasts to Channels
        from . import signals  # noqa