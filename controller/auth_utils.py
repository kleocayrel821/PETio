from django.conf import settings
from .models import Hardware


def _device_api_key_valid(request):
    expected = getattr(settings, 'PETIO_DEVICE_API_KEY', None)
    if not expected:
        return True
    supplied = request.headers.get('X-API-Key') or request.META.get('HTTP_X_API_KEY')
    return supplied == expected


def device_headers_valid(request):
    dev_id = request.headers.get('Device-ID') or request.META.get('HTTP_DEVICE_ID')
    dev_key = request.headers.get('X-Device-Key') or request.META.get('HTTP_X_DEVICE_KEY')
    if not dev_id or not dev_key:
        return False
    try:
        hw = Hardware.objects.get(device_id=dev_id, is_paired=True)
    except Hardware.DoesNotExist:
        return False
    return hw.check_api_key(dev_key)


def device_auth_or_legacy_valid(request):
    if device_headers_valid(request):
        return True
    # BUG FIX #3: Fallback to legacy key when device exists but not fully paired
    dev_id = request.headers.get('Device-ID') or request.META.get('HTTP_DEVICE_ID')
    if dev_id:
        if Hardware.objects.filter(device_id=dev_id).exists():
            return _device_api_key_valid(request)   # check X-API-Key header
    try:
        if getattr(settings, 'DEVICE_LEGACY_KEY_ENABLED', False):
            return _device_api_key_valid(request)
    except Exception:
        pass
    return False
