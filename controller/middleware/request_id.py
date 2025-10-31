import uuid
import logging

logger = logging.getLogger(__name__)

class RequestIDMiddleware:
    """Attach a per-request UUID for traceability.
    - Accepts inbound X-Request-ID if provided, else generates a new UUID4.
    - Exposes the ID via request.META['REQUEST_ID'] and response header X-Request-ID.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID') or str(uuid.uuid4())
        request.META['REQUEST_ID'] = request_id
        try:
            logger.debug("request_id attached", extra={"request_id": request_id})
        except Exception:
            pass
        response = self.get_response(request)
        try:
            response['X-Request-ID'] = request_id
        except Exception:
            pass
        return response