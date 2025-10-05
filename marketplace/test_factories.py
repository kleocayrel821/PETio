from decimal import Decimal
from django.contrib.auth import get_user_model


def make_user(username: str, password: str = "pass", *, is_staff: bool = False, is_superuser: bool = False, email: str | None = None):
    User = get_user_model()
    email = email or f"{username}@example.com"
    return User.objects.create_user(username=username, password=password, is_staff=is_staff, is_superuser=is_superuser, email=email)


def make_category(name: str = "General"):
    from .models import Category
    return Category.objects.create(name=name)


def make_listing(*, seller, category=None, title: str = "Item", description: str = "", price: Decimal = Decimal("10.00"), status: str = None, quantity: int = 1):
    from .models import Listing, ListingStatus
    status = status or ListingStatus.PENDING
    category = category or make_category()
    return Listing.objects.create(
        title=title,
        description=description,
        category=category,
        seller=seller,
        price=price,
        status=status,
        quantity=quantity,
    )


def make_request(*, listing, buyer, seller, status: str = None):
    from .models import PurchaseRequest, PurchaseRequestStatus
    status = status or PurchaseRequestStatus.PENDING
    return PurchaseRequest.objects.create(listing=listing, buyer=buyer, seller=seller, status=status)


def make_notification(*, user, title: str = "Note", body: str = "", unread: bool = True, related_listing=None, related_request=None):
    from .models import Notification
    return Notification.objects.create(
        user=user,
        title=title,
        body=body,
        unread=unread,
        related_listing=related_listing,
        related_request=related_request,
    )


def make_report(*, listing, reporter, reason: str = "Issue", status: str = None):
    from .models import Report, ReportStatus
    status = status or ReportStatus.OPEN
    return Report.objects.create(listing=listing, reporter=reporter, reason=reason, status=status)


def make_user(username: str, password: str = "pass", is_staff: bool = False, is_superuser: bool = False, email: str = None):
    """Create and return a User suitable for tests.

    Defaults:
    - `password` set to "pass"
    - `email` derived from username when not provided
    - optional `is_staff` and `is_superuser`
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    email = email or f"{username}@example.com"
    user = User.objects.create_user(username=username, email=email, password=password)
    user.is_staff = bool(is_staff)
    user.is_superuser = bool(is_superuser)
    user.save(update_fields=["is_staff", "is_superuser"])
    return user