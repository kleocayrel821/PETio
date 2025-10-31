from django.conf import settings


def _device_api_key_valid(request):
    """Validate device API key from header X-API-Key against settings.PETIO_DEVICE_API_KEY if set.
    Returns True if no key is configured (development convenience).
    """
    expected = getattr(settings, 'PETIO_DEVICE_API_KEY', None)
    if not expected:
        return True
    supplied = request.headers.get('X-API-Key') or request.META.get('HTTP_X_API_KEY')
    return supplied == expected