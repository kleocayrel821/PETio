from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from .models import Notification, Listing, PurchaseRequest, NotificationType


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email(self, *, notif_id: int, user_id: int, notif_type: str, title: str, message_text: str = "", listing_id: int = None, request_id: int = None):
    """
    Async email delivery for notifications with retries.

    Respects user preference flags and marks Notification.email_sent on success.
    """
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return

    # Respect user email preferences
    wants_global = getattr(user, "email_marketplace_notifications", True)
    email_addr = getattr(user, "email", None) or ""

    if notif_type == NotificationType.MESSAGE_POSTED:
        wants_type = getattr(user, "email_on_messages", True)
    elif notif_type in (NotificationType.REQUEST_CREATED, NotificationType.STATUS_CHANGED):
        wants_type = getattr(user, "email_on_request_updates", True)
    else:
        wants_type = True

    if not (wants_global and wants_type and email_addr):
        return

    # Build body
    body = (message_text or "").strip()
    if listing_id:
        try:
            listing = Listing.objects.get(pk=listing_id)
            body = f"Listing: {getattr(listing, 'title', listing)}\n" + body
        except Listing.DoesNotExist:
            pass
    if request_id:
        try:
            req = PurchaseRequest.objects.select_related("buyer").get(pk=request_id)
            buyer_name = getattr(req.buyer, "username", req.buyer_id)
            body += f"\nRequest by @{buyer_name}"
        except PurchaseRequest.DoesNotExist:
            pass

    try:
        send_mail(
            subject=title,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[email_addr],
            fail_silently=False,
        )
        try:
            notif = Notification.objects.get(pk=notif_id)
            notif.email_sent = True
            notif.save(update_fields=["email_sent"])
        except Notification.DoesNotExist:
            pass
    except Exception as exc:
        raise self.retry(exc=exc)