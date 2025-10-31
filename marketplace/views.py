from django.shortcuts import render
from django.shortcuts import get_object_or_404, redirect
from django.db.models import Q, Count, Avg, OuterRef, Subquery
from django.views.generic import ListView, DetailView
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.utils.http import urlencode

from .models import Listing, Category
from .models import (
    Transaction,
    Report,
    ListingStatus,
    TransactionStatus,
    ReportStatus,
    PurchaseRequest,
    PurchaseRequestStatus,
    TransactionLog,
    LogAction,
    RequestMessage,
    Message,
    Notification,
    NotificationType,
 )
from .forms import ListingForm, SellerRatingForm, MeetupProposalForm, OfferForm, RespondOfferForm

# Configuration: threshold for auto-flagging a listing based on open reports
REPORT_THRESHOLD = 3

# New imports for JSON API endpoints
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.core.mail import send_mail
import json
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.utils.decorators import method_decorator
from django.core.cache import cache
import re

# -----------------------------
# JSON Response Helpers (standardized for toast system)
# -----------------------------
def wants_json(request):
    """Detect if the client expects JSON (Accept header, X-Requested-With, or ?format=json)."""
    accept = request.headers.get("Accept", "")
    xrw = request.headers.get("X-Requested-With", "")
    fmt = (request.GET.get("format") or request.POST.get("format") or "").lower()
    return ("application/json" in accept) or (xrw == "XMLHttpRequest") or (fmt == "json")


def json_error(message, status=400, code=None, field_errors=None):
    """Standard JSON error shape consumed by frontend toast handler."""
    payload = {"status": "error", "message": str(message)}
    if code is not None:
        payload["code"] = code
    if field_errors:
        payload["field_errors"] = field_errors
    return JsonResponse(payload, status=status)


def json_ok(message="Success", data=None, status=200):
    """Standard JSON success shape consumed by frontend toast handler."""
    payload = {"status": "ok", "message": str(message)}
    if data is not None:
        payload["data"] = data
    return JsonResponse(payload, status=status)

# -----------------------------
# Text Sanitization Helper
# -----------------------------
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def sanitize_text(value, max_len=1000):
    s = (value or "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _CONTROL_RE.sub("", s)
    s = s.strip()
    if len(s) > max_len:
        s = s[:max_len]
    return s

# -----------------------------
# Simple Per-User Rate Limiting
# -----------------------------
def rate_limit(action_key, window_seconds=60, max_calls=5):
    def decorator(view_func):
        def _wrapped(request, *args, **kwargs):
            try:
                user = getattr(request, "user", None)
                if user is not None and getattr(user, "is_authenticated", False):
                    key = f"rl:{action_key}:{user.id}"
                    count = cache.get(key)
                    if count is None:
                        cache.set(key, 1, timeout=window_seconds)
                        count = 1
                    else:
                        try:
                            cache.incr(key)
                        except Exception:
                            cache.set(key, int(count) + 1, timeout=window_seconds)
                        count = cache.get(key)
                    if int(count or 0) > max_calls:
                        ct = (getattr(request, "content_type", "") or "").lower()
                        if ct.startswith("application/json"):
                            return json_error("Rate limit exceeded", status=429, code="rate_limited")
                        return HttpResponseBadRequest("Rate limit exceeded")
            except Exception:
                # Fail-open on rate limiter errors
                pass
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator

# -----------------------------
# In-app Notifications Helpers
# -----------------------------
def _notify(user, notif_type, request_obj=None, listing=None, message_text=None, send_email=False):
    """Create a simple in-app notification aligned with Notification model fields."""
    try:
        # Derive a friendly title
        if notif_type == NotificationType.REQUEST_CREATED:
            # Standardize wording to include buyer handle
            buyer_name = None
            try:
                if request_obj and getattr(request_obj, "buyer", None):
                    buyer = request_obj.buyer
                    buyer_name = getattr(buyer, "username", None) or getattr(buyer, "email", "")
            except Exception:
                buyer_name = None
            title = f"Purchase Request by @{buyer_name}" if buyer_name else "Purchase Request"
        elif notif_type == NotificationType.STATUS_CHANGED:
            title = "Request status updated"
        elif notif_type == NotificationType.MESSAGE_POSTED:
            title = "New message on request"
        else:
            title = "Marketplace notification"
        # For message notifications, do not include the full chat content in the notification body.
        # Keep notifications as pointers, not conversation logs.
        if notif_type == NotificationType.MESSAGE_POSTED:
            body_text = ""
        else:
            body_text = (message_text or "").strip()
        # Respect in-app notification preferences
        wants_global_inapp = getattr(user, "notify_marketplace_notifications", True)
        if notif_type == NotificationType.MESSAGE_POSTED:
            wants_inapp_type = getattr(user, "notify_on_messages", True)
        elif notif_type in (NotificationType.REQUEST_CREATED, NotificationType.STATUS_CHANGED):
            wants_inapp_type = getattr(user, "notify_on_request_updates", True)
        else:
            wants_inapp_type = True

        notif = None
        if wants_global_inapp and wants_inapp_type:
            notif = Notification.objects.create(
                user=user,
                type=notif_type,
                title=title,
                body=body_text,
                related_request=request_obj,
                related_listing=listing,
                unread=True,
            )
        # Optional email delivery is delegated to async task for retries
        if send_email:
            try:
                from .tasks import send_notification_email
                send_notification_email.delay(
                    notif_id=notif.id,
                    user_id=user.id,
                    notif_type=str(notif_type),
                    title=title,
                    message_text=(message_text or "").strip(),
                    listing_id=getattr(listing, "id", None),
                    request_id=getattr(request_obj, "id", None),
                )
            except Exception:
                # Fallback: best-effort inline email if Celery not available
                try:
                    wants_global = getattr(user, "email_marketplace_notifications", True)
                    email_addr = getattr(user, "email", None) or ""
                    if notif_type == NotificationType.MESSAGE_POSTED:
                        wants_type = getattr(user, "email_on_messages", True)
                    elif notif_type in (NotificationType.REQUEST_CREATED, NotificationType.STATUS_CHANGED):
                        wants_type = getattr(user, "email_on_request_updates", True)
                    else:
                        wants_type = True
                    if wants_global and wants_type and email_addr:
                        subject = f"{title}"
                        body = (message_text or "").strip()
                        if listing:
                            body = f"Listing: {getattr(listing, 'title', listing)}\n" + body
                        if request_obj:
                            body += f"\nRequest by @{getattr(request_obj.buyer, 'username', request_obj.buyer_id)}"
                        send_mail(
                            subject,
                            body,
                            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
                            [email_addr],
                            fail_silently=True,
                        )
                        notif.email_sent = True
                        notif.save(update_fields=["email_sent"])
                except Exception:
                    pass
    except Exception:
        # Best-effort; do not break primary flow
        pass

def _unread_count(user):
    try:
        # Prefer read_at semantics for unread
        return Notification.objects.filter(user=user, read_at__isnull=True).count()
    except Exception:
        return 0


# -----------------------------
# Lightweight count endpoints for badges
# -----------------------------
@login_required
@require_http_methods(["GET"])
def notifications_count(request):
    """Return unread marketplace notification count as { count: <number> }."""
    try:
        count = _unread_count(request.user)
    except Exception:
        count = 0
    return JsonResponse({"count": int(count)})


@login_required
@require_http_methods(["GET"])
def messages_count(request):
    """Return unread message count (thread messages + request messages) for current user.

    Unread criteria:
    - Message.read_at IS NULL and message is from the other party in a thread the user participates in
    - RequestMessage.read_at IS NULL and authored by the other party on a request where the user is buyer or seller
    """
    user = request.user
    try:
        unread_thread_msgs = (
            Message.objects
            .filter(read_at__isnull=True)
            .filter(Q(thread__buyer=user) | Q(thread__seller=user))
            .exclude(sender=user)
            .count()
        )
    except Exception:
        unread_thread_msgs = 0

    try:
        unread_req_msgs = (
            RequestMessage.objects
            .filter(read_at__isnull=True)
            .filter(Q(request__buyer=user) | Q(request__seller=user))
            .exclude(author=user)
            .count()
        )
    except Exception:
        unread_req_msgs = 0

    total = int(unread_thread_msgs) + int(unread_req_msgs)
    return JsonResponse({"count": total})

# DRF imports for RESTful Marketplace endpoints
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.decorators import action
from .serializers import (
    CategorySerializer,
    ListingSerializer,
    MessageThreadSerializer,
    MessageSerializer,
    TransactionSerializer,
    ReportSerializer,
)

# Marketplace wireframe views (frontend-only): each view renders a template skeleton for planning.

class CatalogView(ListView):
    """Browse active listings with optional search and category filtering.

    Query params:
    - q: search term (case-insensitive) in title or description
    - category: category slug to filter listings
    """
    model = Listing
    template_name = "marketplace/catalog.html"
    context_object_name = "listings"
    paginate_by = 24

    def get_queryset(self):
        """Return filtered queryset of active listings with search/category, price range, and sorting.
        - Filters:
          - q: case-insensitive search in title or description
          - category: category slug
          - condition: "new" or "used" (future field; ignored if unsupported)
          - brand: simple substring match on title/description (placeholder until field exists)
          - price_min/price_max: decimal values, non-negative; if both provided and min > max, swap gracefully
        - Sorting:
          - sort: one of ["newest", "price_asc", "price_desc"]; defaults to "newest"
        """
        # Base queryset: active listings with related category and seller for efficiency
        qs = (
            Listing.objects.filter(status="active")
            .select_related("category", "seller", "seller__profile")
            .prefetch_related("photos")
        )

        # Text search
        q = (self.request.GET.get("q", "") or "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

        # Category filter
        category_slug = (self.request.GET.get("category", "") or "").strip()
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        # Price range filtering with validation and graceful fallbacks
        price_min_raw = self.request.GET.get("price_min")
        price_max_raw = self.request.GET.get("price_max")

        def _parse_decimal(val):
            if val is None:
                return None
            try:
                d = Decimal(str(val).strip())
                # Ignore negative values
                if d < 0:
                    return None
                return d
            except (InvalidOperation, ValueError, TypeError):
                return None

        price_min = _parse_decimal(price_min_raw)
        price_max = _parse_decimal(price_max_raw)
        # If both are provided and min > max, swap to be helpful
        if price_min is not None and price_max is not None and price_min > price_max:
            price_min, price_max = price_max, price_min
        if price_min is not None:
            qs = qs.filter(price__gte=price_min)
        if price_max is not None:
            qs = qs.filter(price__lte=price_max)

        # Condition filter (placeholder: only applies if Listing has a 'condition' field)
        condition = (self.request.GET.get("condition", "") or "").strip().lower()
        if condition in {"new", "used"} and hasattr(Listing, "condition"):
            qs = qs.filter(condition=condition)

        # Brand filter (placeholder without dedicated field: naive match in title/description)
        brand = (self.request.GET.get("brand", "") or "").strip()
        if brand:
            qs = qs.filter(Q(title__icontains=brand) | Q(description__icontains=brand))

        # Near filter (approximate location match on seller profile location)
        near = (self.request.GET.get("near", "") or "").strip()
        if near:
            qs = qs.filter(seller__profile__location__icontains=near)

        # Seller rating aggregates (avg and count) annotated onto listings
        try:
            from .models import SellerRating
            avg_subq = (
                SellerRating.objects.filter(seller_id=OuterRef("seller_id"))
                .values("seller")
                .annotate(avg=Avg("score"))
                .values("avg")[:1]
            )
            cnt_subq = (
                SellerRating.objects.filter(seller_id=OuterRef("seller_id"))
                .values("seller")
                .annotate(cnt=Count("id"))
                .values("cnt")[:1]
            )
            qs = qs.annotate(
                seller_avg_rating=Subquery(avg_subq),
                seller_rating_count=Subquery(cnt_subq),
            )
        except Exception:
            # If annotations fail for any reason, proceed without them
            pass

        # Sorting
        sort = (self.request.GET.get("sort", "newest") or "newest").strip().lower()
        sort_map = {
            "newest": "-created_at",
            "price_asc": "price",
            "price_desc": "-price",
        }
        order_by = sort_map.get(sort, sort_map["newest"])  # default fallback
        qs = qs.order_by(order_by)
        return qs

    def get_context_data(self, **kwargs):
        """Expose current filters to template and build qs_no_page for pagination.
        Also provide categories for filter select.
        """
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q", "") or "").strip()
        ctx["category_slug"] = (self.request.GET.get("category", "") or "").strip()
        ctx["price_min"] = (self.request.GET.get("price_min", "") or "").strip()
        ctx["price_max"] = (self.request.GET.get("price_max", "") or "").strip()
        ctx["sort"] = (self.request.GET.get("sort", "newest") or "newest").strip().lower()
        ctx["brand"] = (self.request.GET.get("brand", "") or "").strip()
        ctx["condition"] = (self.request.GET.get("condition", "") or "").strip().lower()
        ctx["near"] = (self.request.GET.get("near", "") or "").strip()
        try:
            ctx["categories"] = Category.objects.all().only("name", "slug").order_by("name")
        except Exception:
            ctx["categories"] = []
        # Global marketplace stats for catalog quick stats cards
        try:
            from django.utils import timezone
            from datetime import timedelta
            start_week = timezone.now() - timedelta(days=7)
            active_listings_qs = Listing.objects.filter(status=ListingStatus.ACTIVE.value)
            total_products = active_listings_qs.count()
            new_products_week = active_listings_qs.filter(created_at__gte=start_week).count()
            active_sellers = active_listings_qs.values("seller_id").distinct().count()
            new_sellers_week = (
                Listing.objects.filter(created_at__gte=start_week)
                .values("seller_id")
                .distinct()
                .count()
            )
            categories_count = Category.objects.count()
            ctx["global_stats"] = {
                "total_products": total_products,
                "new_products_week": new_products_week,
                "active_sellers": active_sellers,
                "new_sellers_week": new_sellers_week,
                "categories": categories_count,
            }
        except Exception:
            ctx["global_stats"] = {
                "total_products": 0,
                "new_products_week": 0,
                "active_sellers": 0,
                "new_sellers_week": 0,
                "categories": 0,
            }
        # Build querystring without page for pagination links
        qd = self.request.GET.copy()
        if "page" in qd:
            qd.pop("page")
        ctx["qs_no_page"] = urlencode(qd, doseq=True)
        return ctx

    # Removed duplicate get_context_data (consolidated above)


class ListingDetailView(DetailView):
    """Show a single listing detail page."""
    model = Listing
    template_name = "marketplace/detail.html"
    context_object_name = "listing"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        listing = self.object
        user = self.request.user
        existing_pending = None
        can_request = False
        if user.is_authenticated:
            if user.id != getattr(listing.seller, "id", None):
                if listing.status == ListingStatus.ACTIVE and getattr(listing, "quantity", 0) > 0:
                    existing_pending = (
                        PurchaseRequest.objects.filter(
                            listing=listing,
                            buyer=user,
                            status=PurchaseRequestStatus.PENDING,
                        )
                        .only("id")
                        .first()
                    )
                    can_request = existing_pending is None
        ctx["can_request_purchase"] = can_request
        ctx["existing_pending_request"] = existing_pending
        # Seller rating aggregates for this listing's seller
        try:
            from .models import SellerRating
            agg = SellerRating.objects.filter(seller_id=listing.seller_id).aggregate(
                avg=Avg("score"), count=Count("id")
            )
            ctx["seller_rating_avg"] = agg.get("avg") or 0.0
            ctx["seller_rating_count"] = agg.get("count") or 0
        except Exception:
            ctx["seller_rating_avg"] = 0.0
            ctx["seller_rating_count"] = 0
        # Similar products: active listings in the same category, excluding current
        try:
            if getattr(listing, "category_id", None):
                similar_qs = (
                    Listing.objects.filter(
                        status=ListingStatus.ACTIVE,
                        category_id=listing.category_id,
                    )
                    .exclude(pk=listing.pk)
                    .select_related("category", "seller")
                    .only(
                        "id",
                        "title",
                        "price",
                        "quantity",
                        "main_image",
                        "category",
                        "seller",
                    )
                    .order_by("-created_at")[:4]
                )
            else:
                similar_qs = Listing.objects.none()
            ctx["similar_listings"] = list(similar_qs)
        except Exception:
            ctx["similar_listings"] = []
        return ctx


class ListingCreateView(LoginRequiredMixin, CreateView):
    """Create a new listing. Requires authentication.

    Validations are handled by ListingForm. The listing seller is set to the
    authenticated user. On success, redirect to the listing detail page.
    """

    model = Listing
    form_class = ListingForm
    template_name = "marketplace/create_listing.html"

    def form_valid(self, form):
        """Bind the listing to the currently authenticated user before saving.
        Returns JSON when requested to support unified toast feedback.
        """
        listing = form.save(commit=False)
        listing.seller = self.request.user
        listing.save()
        self.object = listing
        if wants_json(self.request):
            return json_ok("Listing created.", data={"listing_id": listing.pk})
        return super().form_valid(form)

    def form_invalid(self, form):
        """Return JSON errors when requested to support unified toast feedback."""
        if wants_json(self.request):
            return json_error("Invalid listing", status=400, field_errors=form.errors)
        return super().form_invalid(form)

    def get_success_url(self):
        """Redirect to the newly created listing's detail page."""
        return reverse("marketplace:listing_detail", kwargs={"pk": self.object.pk})


# Render the marketplace home wireframe
# Updated to use the new catalog template for browsing
def marketplace_home(request):
    if getattr(settings, "MARKETPLACE_RESET", False):
        return render(request, "marketplace/reset.html")
    return render(request, "marketplace/catalog.html")

# Render a single listing detail wireframe
# listing_id: placeholder identifier for navigating to a specific listing page
# Updated to use the consolidated detail template
def listing_detail(request, listing_id):
    return render(request, "marketplace/detail.html", {"listing_id": listing_id})

# Render the create listing wireframe
# Updated to redirect to the CreateView for consistency
@login_required
def create_listing(request):
    """Redirect to the standard ListingCreateView route."""
    return redirect("marketplace:listing_create")

# Render the messages wireframe
@login_required
@ensure_csrf_cookie
def messages(request):
    """Render the messaging/inbox page. Requires user login.

    Provides current user context to the template for client-side alignment and UX.
    """
    return render(
        request,
        "marketplace/messages.html",
        {
            "current_user_id": request.user.id,
            "current_username": getattr(request.user, "username", ""),
            "unread_notifications": _unread_count(request.user),
        },
    )

# Render the transactions wireframe (placeholder template)
# Kept as a separate page to show person-to-person transactions overview

# ------------------------------
# Manual Purchase Flow (New)
# ------------------------------

from django.contrib import messages as django_messages
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.views import redirect_to_login


@login_required
@require_POST
def request_to_purchase(request, pk):
    """Buyer initiates a manual purchase request on a listing.

    Creates PurchaseRequest, logs the action, and redirects to buyer dashboard.
    """
    listing = get_object_or_404(Listing, pk=pk)
    buyer = request.user
    seller = listing.seller

    # Block self-purchase
    if buyer.id == getattr(seller, "id", None):
        return HttpResponseForbidden("Cannot request your own listing")

    # Validate listing state and stock
    if listing.status != ListingStatus.ACTIVE:
        return HttpResponseBadRequest("Listing is not available for requests")
    if getattr(listing, "quantity", 0) <= 0:
        return HttpResponseBadRequest("Listing is out of stock")

    # Prevent duplicate pending request from same buyer for same listing
    existing = PurchaseRequest.objects.filter(
        listing=listing,
        buyer=buyer,
        status=PurchaseRequestStatus.PENDING,
    ).first()
    if existing:
        django_messages.info(request, "You already have a pending request for this listing.")
        return redirect("marketplace:request_detail", pk=existing.pk)

    note = (request.POST.get("message") or "").strip()
    pr = PurchaseRequest.objects.create(
        listing=listing,
        buyer=buyer,
        seller=seller,
        status=PurchaseRequestStatus.PENDING,
        message=note,
    )
    TransactionLog.objects.create(
        request=pr,
        actor=buyer,
        action=LogAction.BUYER_REQUEST,
        note=note,
    )
    # Notify buyer and seller
    _notify(seller, NotificationType.REQUEST_CREATED, request_obj=pr, listing=listing, message_text=note, send_email=True)
    _notify(buyer, NotificationType.REQUEST_CREATED, request_obj=pr, listing=listing, message_text=note, send_email=True)

    django_messages.success(request, "Purchase request sent to the seller.")
    # Redirect to request detail thread
    return redirect("marketplace:request_detail", pk=pr.pk)


class BuyerDashboardView(LoginRequiredMixin, ListView):
    model = PurchaseRequest
    template_name = "marketplace/buyer_dashboard.html"
    context_object_name = "requests"
    paginate_by = 20

    def get_queryset(self):
        return (
            PurchaseRequest.objects.filter(buyer=self.request.user)
            .select_related("listing", "seller")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_notifications"] = _unread_count(self.request.user)
        # Per-request unread message counts for this user
        try:
            for r in ctx.get("requests", []):
                count = RequestMessage.objects.filter(
                    request_id=r.id, read_at__isnull=True
                ).exclude(author_id=self.request.user.id).count()
                setattr(r, "unread_count", count)
        except Exception:
            pass
        return ctx


class SellerDashboardView(LoginRequiredMixin, ListView):
    model = PurchaseRequest
    template_name = "marketplace/seller_dashboard.html"
    context_object_name = "incoming"
    paginate_by = 20

    def get_queryset(self):
        return (
            PurchaseRequest.objects.filter(seller=self.request.user)
            .select_related("listing", "buyer")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_notifications"] = _unread_count(self.request.user)
        # Per-request unread message counts for this user
        try:
            for r in ctx.get("incoming", []):
                count = RequestMessage.objects.filter(
                    request_id=r.id, read_at__isnull=True
                ).exclude(author_id=self.request.user.id).count()
                setattr(r, "unread_count", count)
        except Exception:
            pass
        return ctx


class RequestDetailView(LoginRequiredMixin, DetailView):
    model = PurchaseRequest
    template_name = "marketplace/request_detail.html"
    context_object_name = "request_obj"

    def dispatch(self, request, *args, **kwargs):
        pr = get_object_or_404(PurchaseRequest, pk=kwargs.get("pk"))
        allowed = request.user.id in (pr.buyer_id, pr.seller_id) or _is_moderator(request.user)
        if not allowed:
            return HttpResponseForbidden("Not authorized to view this request")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pr = self.object
        thread_messages = (
            RequestMessage.objects.filter(request=pr)
            .select_related("author")
            .order_by("created_at")
        )
        ctx["thread_messages"] = thread_messages
        # Capture unread count before marking as read for display purposes
        try:
            ctx["thread_unread_count"] = RequestMessage.objects.filter(
                request=pr, read_at__isnull=True
            ).exclude(author_id=self.request.user.id).count()
        except Exception:
            ctx["thread_unread_count"] = 0
        # Auto-mark unread messages from the other party as read when viewing the thread
        try:
            unread_qs = RequestMessage.objects.filter(
                request=pr,
                read_at__isnull=True,
            ).exclude(author_id=self.request.user.id)
            if unread_qs.exists():
                unread_qs.update(read_at=timezone.now())
        except Exception:
            # Best-effort; do not block rendering on read-state updates
            pass
        # Rating context: allow buyer to rate seller when completed and not yet rated
        try:
            if self.request.user.id == pr.buyer_id and pr.status == PurchaseRequestStatus.COMPLETED:
                from .models import SellerRating
                existing_rating = SellerRating.objects.filter(purchase_request=pr, buyer_id=self.request.user.id).first()
                ctx["existing_rating"] = existing_rating
                ctx["can_rate"] = existing_rating is None
                ctx["rating_form"] = SellerRatingForm() if existing_rating is None else None
            else:
                ctx["existing_rating"] = None
                ctx["can_rate"] = False
                ctx["rating_form"] = None
        except Exception:
            ctx["existing_rating"] = None
            ctx["can_rate"] = False
            ctx["rating_form"] = None
        # Meetup context: expose current details and whether user can propose/update/confirm
        try:
            txn = getattr(pr, "transaction", None)
            has_txn = txn is not None
            has_details = has_txn and bool(getattr(txn, "meetup_time", None)) and bool(getattr(txn, "meetup_place", ""))
            is_active = pr.status not in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED)
            is_party = self.request.user.id in (pr.buyer_id, pr.seller_id)
            ctx["meetup_details"] = txn if has_txn else None
            ctx["can_propose_meetup"] = is_party and is_active and has_txn and not has_details
            ctx["can_update_meetup"] = is_party and is_active and has_txn and has_details
            ctx["can_confirm_meetup"] = is_party and is_active and has_txn and has_details
            initial = {}
            if has_details:
                initial = {
                    "meetup_time": txn.meetup_time,
                    "meetup_place": txn.meetup_place,
                }
            # Include optional timezone and reschedule reason in form initial
            if has_txn:
                initial.update({
                    "meetup_timezone": getattr(txn, "meetup_timezone", "") or "",
                    "reschedule_reason": getattr(txn, "reschedule_reason", "") or "",
                })
            ctx["meetup_form"] = MeetupProposalForm(initial=initial)
            # Meetup timeline logs and confirmation state
            meetup_logs = (
                TransactionLog.objects.filter(
                    request=pr,
                    action__in=[
                        LogAction.MEETUP_PROPOSED,
                        LogAction.MEETUP_UPDATED,
                        LogAction.MEETUP_CONFIRMED,
                    ],
                )
                .select_related("actor")
                .order_by("created_at")
            )
            ctx["meetup_logs"] = meetup_logs
            ctx["meetup_confirmed"] = TransactionLog.objects.filter(request=pr, action=LogAction.MEETUP_CONFIRMED).exists()
            # Show completion CTA only for buyer/moderator after meetup confirmed and payment recorded
            is_buyer_or_mod = self.request.user.id == pr.buyer_id or _is_moderator(self.request.user)
            txn_paid = has_txn and getattr(txn, "status", None) == TransactionStatus.PAID
            ctx["can_mark_completed"] = bool(
                is_buyer_or_mod and is_active and txn_paid and ctx.get("meetup_confirmed", False) and pr.status == PurchaseRequestStatus.ACCEPTED
            )
        except Exception:
            ctx["meetup_details"] = None
            ctx["can_propose_meetup"] = False
            ctx["can_update_meetup"] = False
            ctx["can_confirm_meetup"] = False
            ctx["meetup_form"] = MeetupProposalForm()
            ctx["meetup_logs"] = []
            ctx["meetup_confirmed"] = False
            ctx["can_mark_completed"] = False
        # Negotiation context: offer fields, permissions, and history
        try:
            is_buyer = self.request.user.id == pr.buyer_id
            is_seller = self.request.user.id == pr.seller_id
            is_moderator = _is_moderator(self.request.user)
            active = pr.status not in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED)
            can_submit_offer = (
                (is_buyer or is_moderator) and active and pr.listing.status == ListingStatus.ACTIVE and
                pr.status in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING)
            )
            can_respond_offer = (
                (is_seller or is_moderator) and active and pr.status == PurchaseRequestStatus.NEGOTIATING and
                (pr.offer_price is not None or pr.counter_offer is not None)
            )
            ctx["negotiation_enabled"] = True
            ctx["current_offer_price"] = pr.offer_price
            ctx["current_quantity"] = pr.quantity
            ctx["current_counter_offer"] = pr.counter_offer
            ctx["can_submit_offer"] = can_submit_offer
            ctx["can_respond_offer"] = can_respond_offer
            ctx["offer_form"] = OfferForm(listing=pr.listing)
            ctx["respond_offer_form"] = RespondOfferForm()
            ctx["negotiation_logs"] = (
                TransactionLog.objects.filter(
                    request=pr,
                    action__in=[
                        LogAction.SELLER_NEGOTIATE,
                        LogAction.OFFER_SUBMITTED,
                        LogAction.OFFER_COUNTERED,
                        LogAction.OFFER_ACCEPTED,
                        LogAction.OFFER_REJECTED,
                        LogAction.REQUEST_CANCELED,
                    ],
                )
                .select_related("actor")
                .order_by("created_at")
            )
        except Exception:
            ctx["negotiation_enabled"] = False
            ctx["current_offer_price"] = None
            ctx["current_quantity"] = None
            ctx["current_counter_offer"] = None
            ctx["can_submit_offer"] = False
            ctx["can_respond_offer"] = False
            ctx["offer_form"] = OfferForm()
            ctx["respond_offer_form"] = RespondOfferForm()
            ctx["negotiation_logs"] = []
        ctx["unread_notifications"] = _unread_count(self.request.user)
        return ctx

@login_required
@require_POST
def submit_offer(request, request_id):
    """Buyer submits an offer with price and quantity.

    Transitions request to negotiating (from pending) and logs the action.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id != pr.buyer_id and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING):
        return HttpResponseBadRequest("Cannot submit offer in current status")
    if pr.listing.status != ListingStatus.ACTIVE:
        return HttpResponseBadRequest("Listing not available for negotiation")
    form = OfferForm(request.POST, listing=pr.listing)
    if not form.is_valid():
        django_messages.error(request, "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()]))
        return redirect("marketplace:request_detail", pk=pr.pk)
    pr.offer_price = form.cleaned_data["offer_price"]
    pr.quantity = form.cleaned_data["quantity"]
    if pr.status == PurchaseRequestStatus.PENDING:
        pr.status = PurchaseRequestStatus.NEGOTIATING
    pr.save(update_fields=["offer_price", "quantity", "status", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.OFFER_SUBMITTED,
        note=f"{pr.quantity} @ {pr.offer_price}",
    )
    _notify(
        pr.seller,
        NotificationType.STATUS_CHANGED,
        request_obj=pr,
        listing=pr.listing,
        message_text="offer submitted",
        send_email=True,
    )
    django_messages.success(request, "Offer submitted.")
    return redirect("marketplace:request_detail", pk=pr.pk)


@login_required
@require_POST
def respond_offer(request, request_id):
    """Seller responds to an existing offer: accept / reject / counter.

    Accept mirrors seller_accept_request behavior; counter leaves status negotiating.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status != PurchaseRequestStatus.NEGOTIATING:
        return HttpResponseBadRequest("Cannot respond in current status")
    form = RespondOfferForm(request.POST)
    if not form.is_valid():
        django_messages.error(request, "; ".join([f"{k}: {','.join(v)}" for k, v in form.errors.items()]))
        return redirect("marketplace:request_detail", pk=pr.pk)
    act = form.cleaned_data["action"]
    if act == "accept":
        # Ensure listing is available and not reserved by another request
        if pr.listing.status != ListingStatus.ACTIVE:
            return HttpResponseBadRequest("Listing not available for acceptance")
        existing_accepted = (
            PurchaseRequest.objects
            .filter(listing=pr.listing, status=PurchaseRequestStatus.ACCEPTED)
            .exclude(pk=pr.id)
            .exists()
        )
        if existing_accepted:
            return HttpResponseBadRequest("Listing already reserved by another request")
        pr.status = PurchaseRequestStatus.ACCEPTED
        pr.accepted_at = timezone.now()
        txn = Transaction.objects.create(
            listing=pr.listing,
            buyer=pr.buyer,
            seller=pr.seller,
            status=TransactionStatus.CONFIRMED,
        )
        pr.transaction = txn
        pr.save(update_fields=["status", "accepted_at", "transaction", "updated_at"])
        pr.listing.status = ListingStatus.RESERVED
        pr.listing.save(update_fields=["status", "updated_at"])
        # Log acceptance with price/quantity context
        accepted_price = pr.counter_offer if pr.counter_offer is not None else pr.offer_price
        accepted_qty = pr.quantity or 1
        TransactionLog.objects.create(
            request=pr,
            actor=request.user,
            action=LogAction.OFFER_ACCEPTED,
            note=f"Accepted: {accepted_qty} × {accepted_price}",
        )
        _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="offer accepted", send_email=True)
        _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="offer accepted", send_email=True)
        django_messages.success(request, "Offer accepted. Listing reserved.")
        return redirect("marketplace:seller_dashboard")
    elif act == "reject":
        pr.status = PurchaseRequestStatus.REJECTED
        pr.save(update_fields=["status", "updated_at"])
        # Log rejection with current price/quantity context
        rejected_price = pr.offer_price if pr.offer_price is not None else pr.counter_offer
        rejected_qty = pr.quantity or 1
        TransactionLog.objects.create(
            request=pr,
            actor=request.user,
            action=LogAction.OFFER_REJECTED,
            note=f"Rejected: {rejected_qty} × {rejected_price}",
        )
        _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="offer rejected", send_email=True)
        _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="offer rejected", send_email=True)
        django_messages.info(request, "Offer rejected.")
        return redirect("marketplace:seller_dashboard")
    else:  # counter
        counter_offer = form.cleaned_data.get("counter_offer")
        pr.counter_offer = counter_offer
        pr.save(update_fields=["counter_offer", "updated_at"])
        TransactionLog.objects.create(
            request=pr,
            actor=request.user,
            action=LogAction.OFFER_COUNTERED,
            note=f"Counter: {pr.counter_offer}",
        )
        _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="counter offer sent", send_email=True)
        django_messages.success(request, "Counter offer sent.")
        return redirect("marketplace:request_detail", pk=pr.pk)


@login_required
@require_POST
@csrf_protect
def post_request_message(request, pk):
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    allowed = request.user.id in (pr.buyer_id, pr.seller_id) or _is_moderator(request.user)
    if not allowed:
        return HttpResponseForbidden("Not authorized to post in this thread")
    # Block posting when the request is completed or canceled
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return HttpResponseBadRequest("Cannot post messages on a closed request")
    content = sanitize_text(request.POST.get("content"), max_len=4000)
    if not content:
        return HttpResponseBadRequest("Message content is required")
    msg = RequestMessage.objects.create(request=pr, author=request.user, content=content)
    # Notify the other party
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.MESSAGE_POSTED, request_obj=pr, listing=pr.listing, message_text=content, send_email=True)
    django_messages.success(request, "Message posted.")
    return redirect("marketplace:request_detail", pk=pr.pk)


@login_required
@require_POST
@csrf_protect
def propose_meetup(request, request_id):
    """Propose initial meetup details for an accepted request.

    Requires that a Transaction exists for the request. Only buyer or seller may act.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return json_error("Request not active", status=400)
    if not pr.transaction:
        return json_error("No transaction for this request", status=400)
    if pr.transaction.meetup_time or pr.transaction.meetup_place:
        return json_error("Meetup already set; use update endpoint", status=400)
    form = MeetupProposalForm(request.POST)
    if not form.is_valid():
        return json_error("Invalid meetup details", status=400, field_errors=form.errors)
    pr.transaction.meetup_time = form.cleaned_data["meetup_time"]
    place = sanitize_text(form.cleaned_data["meetup_place"], max_len=200)
    pr.transaction.meetup_place = place
    tz_name = (form.cleaned_data.get("meetup_timezone") or "").strip() or timezone.get_current_timezone_name()
    pr.transaction.meetup_timezone = tz_name
    pr.transaction.save(update_fields=["meetup_time", "meetup_place", "meetup_timezone", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.MEETUP_PROPOSED,
        note=f"{pr.transaction.meetup_place} @ {pr.transaction.meetup_time} (TZ: {tz_name})",
    )
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="meetup proposed", send_email=True)
    return json_ok(
        "Meetup details proposed.",
        data={
            "request": {"id": pr.id, "status": pr.status},
            "transaction": {
                "id": pr.transaction.id,
                "meetup_place": pr.transaction.meetup_place,
                "meetup_time": pr.transaction.meetup_time.isoformat() if pr.transaction.meetup_time else None,
                "meetup_timezone": pr.transaction.meetup_timezone,
            },
        },
    )


@login_required
@require_POST
@csrf_protect
def update_meetup(request, request_id):
    """Update existing meetup details.

    Only buyer or seller, active request with transaction and existing details.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return json_error("Request not active", status=400)
    if not pr.transaction:
        return json_error("No transaction for this request", status=400)
    if not pr.transaction.meetup_time or not pr.transaction.meetup_place:
        return json_error("No existing meetup to update", status=400)
    form = MeetupProposalForm(request.POST)
    if not form.is_valid():
        return json_error("Invalid meetup details", status=400, field_errors=form.errors)
    pr.transaction.meetup_time = form.cleaned_data["meetup_time"]
    place = sanitize_text(form.cleaned_data["meetup_place"], max_len=200)
    pr.transaction.meetup_place = place
    tz_name = (form.cleaned_data.get("meetup_timezone") or "").strip() or timezone.get_current_timezone_name()
    pr.transaction.meetup_timezone = tz_name
    reason = sanitize_text((form.cleaned_data.get("reschedule_reason") or "").strip(), max_len=240)
    pr.transaction.reschedule_reason = reason
    pr.transaction.save(update_fields=["meetup_time", "meetup_place", "meetup_timezone", "reschedule_reason", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.MEETUP_UPDATED,
        note=f"{pr.transaction.meetup_place} @ {pr.transaction.meetup_time} (TZ: {tz_name})" + (f" | Reason: {reason}" if reason else ""),
    )
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="meetup updated", send_email=True)
    return json_ok(
        "Meetup details updated.",
        data={
            "request": {"id": pr.id, "status": pr.status},
            "transaction": {
                "id": pr.transaction.id,
                "meetup_place": pr.transaction.meetup_place,
                "meetup_time": pr.transaction.meetup_time.isoformat() if pr.transaction.meetup_time else None,
                "meetup_timezone": pr.transaction.meetup_timezone,
                "reschedule_reason": pr.transaction.reschedule_reason,
            },
        },
    )


@login_required
@require_POST
@csrf_protect
def confirm_meetup(request, request_id):
    """Confirm agreed meetup details.

    Only buyer or seller, active request and transaction with details present.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return HttpResponseBadRequest("Request not active")
    if not pr.transaction:
        return HttpResponseBadRequest("No transaction for this request")
    if not pr.transaction.meetup_time or not pr.transaction.meetup_place:
        return HttpResponseBadRequest("No meetup to confirm")
    # Ensure future time at confirmation moment
    mt = pr.transaction.meetup_time
    if timezone.is_naive(mt):
        mt = timezone.make_aware(mt, timezone.get_default_timezone())
    if mt <= timezone.now():
        if wants_json(request):
            return json_error("Meetup time must be in the future", status=400)
        return HttpResponseBadRequest("Meetup time is not in the future")
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.MEETUP_CONFIRMED,
        note=f"{pr.transaction.meetup_place} @ {pr.transaction.meetup_time} (TZ: {getattr(pr.transaction, 'meetup_timezone', timezone.get_current_timezone_name())})",
    )
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="meetup confirmed")
    if wants_json(request):
        return json_ok("Meetup confirmed.", data={"request_id": pr.pk})
    django_messages.success(request, "Meetup confirmed.")
    return redirect("marketplace:request_detail", pk=pr.pk)


@login_required
@require_http_methods(["GET"])  # Download ICS invite for confirmed meetup
def meetup_ics(request, pk):
    pr = get_object_or_404(PurchaseRequest, pk=pk)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    txn = getattr(pr, "transaction", None)
    if not txn or not txn.meetup_time or not txn.meetup_place:
        return HttpResponseBadRequest("No meetup details available")
    # Require that meetup has been confirmed before generating ICS
    confirmed = TransactionLog.objects.filter(request=pr, action=LogAction.MEETUP_CONFIRMED).exists()
    if not confirmed:
        return HttpResponseBadRequest("Meetup not confirmed")
    # Normalize to UTC for ICS
    mt = txn.meetup_time
    if timezone.is_naive(mt):
        mt = timezone.make_aware(mt, timezone.get_default_timezone())
    start_utc = mt.astimezone(timezone.utc)
    end_utc = (start_utc + timezone.timedelta(hours=1))
    def _fmt(dt):
        return dt.strftime("%Y%m%dT%H%M%SZ")
    uid = f"request-{pr.id}-txn-{txn.id}@petio"
    summary = f"PETio Meetup for Request #{pr.id}"
    description = f"Buyer: @{pr.buyer.username} | Seller: @{pr.seller.username} | Listing: {pr.listing.title}"
    location = txn.meetup_place
    ics = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//PETio Marketplace//Meetup//EN\n"
        "BEGIN:VEVENT\n"
        f"UID:{uid}\n"
        f"DTSTAMP:{_fmt(timezone.now().astimezone(timezone.utc))}\n"
        f"DTSTART:{_fmt(start_utc)}\n"
        f"DTEND:{_fmt(end_utc)}\n"
        f"SUMMARY:{summary}\n"
        f"DESCRIPTION:{description}\n"
        f"LOCATION:{location}\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    resp = HttpResponse(ics, content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f"attachment; filename=meetup-{pr.id}.ics"
    return resp


@login_required
@require_http_methods(["POST"])  # Submit a seller rating for a completed request
@csrf_protect
def post_seller_rating(request, request_id):
    """Allow the buyer to submit a rating for the seller once request is completed.

    Constraints:
    - Only the buyer of the request may rate.
    - Request must be in COMPLETED status.
    - One rating per buyer per purchase_request.
    """
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    user = request.user
    # Resolve actual authenticated user id from session to handle demo auth middleware
    effective_user_id = None
    try:
        uid = request.session.get("_auth_user_id")
        if uid:
            try:
                effective_user_id = int(uid)
            except (TypeError, ValueError):
                effective_user_id = None
    except Exception:
        effective_user_id = None
    if effective_user_id is None:
        effective_user_id = getattr(user, "id", None)
    if effective_user_id != pr.buyer_id and not _is_moderator(user):
        return HttpResponseForbidden("Only the buyer can rate the seller")
    if pr.status != PurchaseRequestStatus.COMPLETED:
        return HttpResponseBadRequest("Rating allowed only after completion")

    from .models import SellerRating
    # Prevent duplicates
    if SellerRating.objects.filter(purchase_request=pr, buyer_id=pr.buyer_id).exists():
        return HttpResponseBadRequest("You have already rated this request")

    form = SellerRatingForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("Invalid rating input")

    score = form.cleaned_data["score"]
    comment = sanitize_text(form.cleaned_data.get("comment"), max_len=1000)
    SellerRating.objects.create(
        seller_id=pr.seller_id,
        buyer_id=pr.buyer_id,
        purchase_request=pr,
        listing_id=pr.listing_id,
        score=score,
        comment=comment,
    )
    django_messages.success(request, "Thank you for rating the seller.")
    return redirect("marketplace:request_detail", pk=pr.id)


class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "marketplace/notifications.html"
    context_object_name = "notifications"

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["unread_notifications"] = _unread_count(self.request.user)
        return ctx


def _ensure_request_owner(req_obj, user):
    return req_obj.seller_id == user.id


@login_required
@require_POST
@csrf_protect
@rate_limit("accept", window_seconds=60, max_calls=5)
def seller_accept_request(request, request_id):
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    # Guard: only allow accept from pending or negotiating, and when listing is available
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING):
        return HttpResponseBadRequest("Cannot accept in current status")
    if pr.listing.status != ListingStatus.ACTIVE:
        return HttpResponseBadRequest("Listing not available for acceptance")
    # Prevent multiple active reservations for the same listing
    existing_accepted = (
        PurchaseRequest.objects
        .filter(listing=pr.listing, status=PurchaseRequestStatus.ACCEPTED)
        .exclude(pk=pr.id)
        .exists()
    )
    if existing_accepted:
        return HttpResponseBadRequest("Listing already reserved by another request")
    # Accept request, create confirmation Transaction, reserve listing
    pr.status = PurchaseRequestStatus.ACCEPTED
    pr.accepted_at = timezone.now()
    txn = Transaction.objects.create(
        listing=pr.listing,
        buyer=pr.buyer,
        seller=pr.seller,
        status=TransactionStatus.CONFIRMED,
    )
    pr.transaction = txn
    pr.save(update_fields=["status", "accepted_at", "transaction", "updated_at"])
    # Set listing reserved
    pr.listing.status = ListingStatus.RESERVED
    pr.listing.save(update_fields=["status", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_ACCEPT,
        note=sanitize_text(request.POST.get("note"), max_len=500),
    )
    # Notifications for status change
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="accepted", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="accepted", send_email=True)
    django_messages.success(request, "Request accepted. Listing reserved.")
    return redirect("marketplace:seller_dashboard")


@login_required
@require_POST
@csrf_protect
@rate_limit("reject", window_seconds=60, max_calls=5)
def seller_reject_request(request, request_id):
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    # Guard: only allow reject from pending or negotiating
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING):
        return HttpResponseBadRequest("Cannot reject in current status")
    pr.status = PurchaseRequestStatus.REJECTED
    pr.save(update_fields=["status", "updated_at"])
    # If listing was reserved for this request, release reservation back to active
    try:
        if pr.listing.status == ListingStatus.RESERVED:
            pr.listing.status = ListingStatus.ACTIVE
            pr.listing.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_REJECT,
        note=sanitize_text(request.POST.get("note"), max_len=500),
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="rejected", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="rejected", send_email=True)
    django_messages.info(request, "Request rejected.")
    return redirect("marketplace:seller_dashboard")


@login_required
@require_POST
def seller_negotiate_request(request, request_id):
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    # Guard: only allow negotiation from pending
    if pr.status != PurchaseRequestStatus.PENDING:
        return HttpResponseBadRequest("Cannot negotiate in current status")
    pr.status = PurchaseRequestStatus.NEGOTIATING
    pr.save(update_fields=["status", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_NEGOTIATE,
        note=(request.POST.get("note") or "").strip(),
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="negotiating")
    django_messages.success(request, "Negotiation started.")
    return redirect("marketplace:seller_dashboard")


@login_required
@require_POST
def buyer_cancel_request(request, request_id):
    """Buyer cancels a purchase request in pending or negotiating states."""
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id != pr.buyer_id and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING, PurchaseRequestStatus.ACCEPTED):
        return HttpResponseBadRequest("Cannot cancel in current status")
    pr.status = PurchaseRequestStatus.CANCELED
    pr.canceled_reason = (request.POST.get("reason") or "").strip()
    pr.save(update_fields=["status", "canceled_reason", "updated_at"])
    # If there is an associated transaction, mark it canceled as part of cascade
    try:
        if pr.transaction and pr.transaction.status not in (TransactionStatus.COMPLETED, TransactionStatus.CANCELED):
            pr.transaction.status = TransactionStatus.CANCELED
            pr.transaction.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    # Release reservation: restore listing to Active if it was Reserved
    try:
        if pr.listing.status == ListingStatus.RESERVED:
            pr.listing.status = ListingStatus.ACTIVE
            pr.listing.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.REQUEST_CANCELED,
        note=pr.canceled_reason,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    django_messages.info(request, "Request canceled.")
    return redirect("marketplace:buyer_dashboard")


@login_required
@require_POST
def seller_cancel_request(request, request_id):
    """Seller cancels a purchase request in pending or negotiating states."""
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING, PurchaseRequestStatus.ACCEPTED):
        return HttpResponseBadRequest("Cannot cancel in current status")
    pr.status = PurchaseRequestStatus.CANCELED
    pr.canceled_reason = (request.POST.get("reason") or "").strip()
    pr.save(update_fields=["status", "canceled_reason", "updated_at"])
    # If there is an associated transaction, mark it canceled as part of cascade
    try:
        if pr.transaction and pr.transaction.status not in (TransactionStatus.COMPLETED, TransactionStatus.CANCELED):
            pr.transaction.status = TransactionStatus.CANCELED
            pr.transaction.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    # Release reservation: restore listing to Active if it was Reserved
    try:
        if pr.listing.status == ListingStatus.RESERVED:
            pr.listing.status = ListingStatus.ACTIVE
            pr.listing.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.REQUEST_CANCELED,
        note=pr.canceled_reason,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    django_messages.info(request, "Request canceled.")
    return redirect("marketplace:seller_dashboard")


@login_required
@require_POST
def mark_request_completed(request, request_id):
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    # Buyer-only completion, requires accepted state and confirmed transaction
    if request.user.id != pr.buyer_id and not _is_moderator(request.user):
        return HttpResponseForbidden("Not authorized")
    if pr.status != PurchaseRequestStatus.ACCEPTED:
        return HttpResponseBadRequest("Cannot complete in current status")
    if not pr.transaction or pr.transaction.status != TransactionStatus.PAID:
        return HttpResponseBadRequest("Transaction not paid")
    pr.status = PurchaseRequestStatus.COMPLETED
    pr.completed_at = timezone.now()
    pr.save(update_fields=["status", "completed_at", "updated_at"])
    # Update transaction and listing
    pr.transaction.status = TransactionStatus.COMPLETED
    pr.transaction.save(update_fields=["status", "updated_at"])
    pr.listing.status = ListingStatus.SOLD
    pr.listing.save(update_fields=["status", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.REQUEST_COMPLETED,
        note=(request.POST.get("note") or "").strip(),
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="completed", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="completed", send_email=True)
    django_messages.success(request, "Transaction completed.")
    return redirect("marketplace:buyer_dashboard")


def _is_moderator(user):
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Only treat real User instances as moderators; ignore demo/placeholder users
        if not isinstance(user, User):
            return False
    except Exception:
        # Fallback: if user object is unexpected type, do not grant moderator
        return False
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


@login_required
@user_passes_test(_is_moderator)
def moderator_dashboard(request):
    # Pending listings for approvals
    pending_listings = (
        Listing.objects.filter(status=ListingStatus.PENDING)
        .select_related("seller", "category")
        .order_by("-created_at")
    )

    # Date filtering: quick ranges or custom
    from datetime import timedelta, datetime
    today = timezone.now().date()
    range_q = (request.GET.get("range") or "").strip()
    start_str = (request.GET.get("start") or "").strip()
    end_str = (request.GET.get("end") or "").strip()

    if range_q in {"7", "30"}:
        days = int(range_q)
        start_date = today - timedelta(days=days - 1)
        end_date = today
    else:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else today - timedelta(days=29)
        except ValueError:
            start_date = today - timedelta(days=29)
        try:
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date() if end_str else today
        except ValueError:
            end_date = today
        if start_date > end_date:
            start_date, end_date = end_date, start_date

    # Build date series
    date_cursor = start_date
    date_list = []
    while date_cursor <= end_date:
        date_list.append(date_cursor)
        date_cursor += timedelta(days=1)

    # Simple analytics (global counts)
    analytics = {
        "total_listings": Listing.objects.count(),
        "active_listings": Listing.objects.filter(status=ListingStatus.ACTIVE).count(),
        "pending_listings": pending_listings.count(),
        "total_requests": PurchaseRequest.objects.count(),
        "accepted_requests": PurchaseRequest.objects.filter(status=PurchaseRequestStatus.ACCEPTED).count(),
        "completed_requests": PurchaseRequest.objects.filter(status=PurchaseRequestStatus.COMPLETED).count(),
    }

    # Listings over time (created per day)
    listings_labels = [d.strftime("%Y-%m-%d") for d in date_list]
    listings_counts = [
        Listing.objects.filter(created_at__date=d).count() for d in date_list
    ]

    # Requests breakdown by status within range
    requests_in_range = PurchaseRequest.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
    status_counts = {
        PurchaseRequestStatus.PENDING: requests_in_range.filter(status=PurchaseRequestStatus.PENDING).count(),
        PurchaseRequestStatus.ACCEPTED: requests_in_range.filter(status=PurchaseRequestStatus.ACCEPTED).count(),
        PurchaseRequestStatus.REJECTED: requests_in_range.filter(status=PurchaseRequestStatus.REJECTED).count(),
        PurchaseRequestStatus.COMPLETED: requests_in_range.filter(status=PurchaseRequestStatus.COMPLETED).count(),
    }
    chart_requests_labels = [
        "Pending",
        "Accepted",
        "Rejected",
        "Completed",
    ]
    chart_requests_data = [
        status_counts[PurchaseRequestStatus.PENDING],
        status_counts[PurchaseRequestStatus.ACCEPTED],
        status_counts[PurchaseRequestStatus.REJECTED],
        status_counts[PurchaseRequestStatus.COMPLETED],
    ]

    # Top sellers (by completed requests in range)
    top_sellers = (
        PurchaseRequest.objects.filter(
            status=PurchaseRequestStatus.COMPLETED,
            completed_at__date__gte=start_date,
            completed_at__date__lte=end_date,
        )
        .values("seller_id", "seller__username")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    # Open reports for moderation
    open_reports = (
        Report.objects.filter(status=ReportStatus.OPEN)
        .select_related("listing", "reporter")
        .order_by("-created_at")[:50]
    )

    # JSON for charts
    import json as pyjson
    ctx = {
        "pending_listings": pending_listings,
        "open_reports": open_reports,
        "analytics": analytics,
        "filter": {
            "range": range_q,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        "top_sellers": top_sellers,
        "listings_labels_json": pyjson.dumps(listings_labels),
        "listings_data_json": pyjson.dumps(listings_counts),
        "requests_labels_json": pyjson.dumps(chart_requests_labels),
        "requests_data_json": pyjson.dumps(chart_requests_data),
        "unread_notifications": _unread_count(request.user),
    }
    return render(request, "marketplace/moderator_dashboard.html", ctx)

############################################
# Notifications: toggle, mark-all, and open
############################################

@login_required
@require_POST
@csrf_protect
def toggle_notification_read(request, notif_id):
    """Toggle read state of a single notification for current user."""
    notif = get_object_or_404(Notification, pk=notif_id, user=request.user)
    if notif.read_at:
        notif.mark_as_unread()
    else:
        notif.mark_as_read()
    notif.save(update_fields=["read_at", "unread", "updated_at"])
    return JsonResponse({
        "id": notif.id,
        "read_at": notif.read_at.isoformat() if notif.read_at else None,
        "unread": notif.unread,
    })


@login_required
@require_POST
@csrf_protect
def mark_all_notifications_read(request):
    """Mark all notifications for current user as read."""
    now = timezone.now()
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=now, unread=False)
    django_messages.success(request, "All notifications marked as read.")
    return redirect("marketplace:notifications")


@login_required
def open_notification(request, notif_id):
    """Mark a notification read and redirect to its related target."""
    notif = get_object_or_404(Notification, pk=notif_id, user=request.user)
    notif.mark_as_read()
    notif.save(update_fields=["read_at", "unread", "updated_at"])
    if notif.related_request_id:
        return redirect("marketplace:request_detail", pk=notif.related_request_id)
    if notif.related_listing_id:
        return redirect("marketplace:listing_detail", pk=notif.related_listing_id)
    return redirect("marketplace:notifications")


@login_required
@user_passes_test(_is_moderator)
@require_POST
@csrf_protect
def moderator_approve_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    listing.status = ListingStatus.ACTIVE
    listing.approved_by = request.user
    listing.approved_at = timezone.now()
    listing.rejected_reason = ""
    listing.save(update_fields=["status", "approved_by", "approved_at", "rejected_reason", "updated_at"])
    django_messages.success(request, "Listing approved and is now live.")
    return redirect("marketplace:moderator_dashboard")


@login_required
@user_passes_test(_is_moderator)
@require_POST
@csrf_protect
def moderator_reject_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    reason = sanitize_text((request.POST.get("reason") or "").strip(), max_len=500)
    listing.status = ListingStatus.REJECTED
    listing.rejected_reason = reason
    listing.approved_by = None
    listing.approved_at = None
    listing.save(update_fields=["status", "rejected_reason", "approved_by", "approved_at", "updated_at"])
    django_messages.info(request, "Listing rejected.")
    return redirect("marketplace:moderator_dashboard")


@login_required
@user_passes_test(_is_moderator)
@require_POST
@csrf_protect
def moderator_close_report(request, report_id):
    report = get_object_or_404(Report, pk=report_id)
    report.status = ReportStatus.CLOSED
    report.save(update_fields=["status", "updated_at"])
    django_messages.success(request, "Report closed.")
    return redirect("marketplace:moderator_dashboard")
@login_required
@ensure_csrf_cookie
def transactions(request):
    if getattr(settings, "MARKETPLACE_RESET", False):
        return render(request, "marketplace/reset.html")
    # Fetch all transactions involving the current user
    user = request.user
    # Guard against placeholder/disabled auth user objects which don't have an integer id
    user_id = getattr(user, "id", None)
    # Read filters from query string
    role = request.GET.get("role")  # buyer | seller | (None for all)
    status_filter = request.GET.get("status")  # proposed | confirmed | completed | canceled
    query = (request.GET.get("q") or "").strip()
    sort = request.GET.get("sort") or "newest"  # newest | oldest

    if not isinstance(user_id, int):
        base_qs = Transaction.objects.none()
    else:
        base_qs = (
            Transaction.objects
            .select_related("listing", "buyer", "seller")
            .filter(Q(buyer_id=user_id) | Q(seller_id=user_id))
        )

    # Apply role filter
    if role == "buyer":
        base_qs = base_qs.filter(buyer_id=user_id)
    elif role == "seller":
        base_qs = base_qs.filter(seller_id=user_id)

    # Apply text search across listing title and participant usernames
    if query:
        base_qs = base_qs.filter(
            Q(listing__title__icontains=query)
            | Q(buyer__username__icontains=query)
            | Q(seller__username__icontains=query)
        )

    # Apply sorting
    if sort == "oldest":
        base_qs = base_qs.order_by("created_at")
    else:
        base_qs = base_qs.order_by("-created_at")

    # Group transactions by major states for rendering
    grouped = {
        "proposed": base_qs.filter(status=TransactionStatus.PROPOSED),
        # Treat awaiting_payment and paid as part of the confirmed bucket
        "confirmed": base_qs.filter(status__in=[
            TransactionStatus.CONFIRMED,
            TransactionStatus.AWAITING_PAYMENT,
            TransactionStatus.PAID,
        ]),
        "completed": base_qs.filter(status=TransactionStatus.COMPLETED),
        "canceled": base_qs.filter(status=TransactionStatus.CANCELED),
    }

    counts = {k: grouped[k].count() for k in grouped}

    ctx = {
        "grouped": grouped,
        "counts": counts,
        "active_status": status_filter,
        "active_role": role,
        "query": query,
        "sort": sort,
        "unread_notifications": _unread_count(user),
    }
    return render(request, "marketplace/transactions.html", ctx)

# Render the user dashboard wireframe
# Staff users see the admin dashboard; regular users see their own listings dashboard
# template = "marketplace/admin_dashboard.html" if getattr(request.user, "is_staff", False) else "marketplace/dashboard.html"
# def dashboard(request):
#     """Render the user-facing marketplace dashboard view without any custom admin UI."""
#     return render(request, "marketplace/dashboard.html")

@method_decorator(ensure_csrf_cookie, name="dispatch")
class DashboardView(LoginRequiredMixin, ListView):
    """User Dashboard: list the current user's listings with status filters and pagination.

    Query params:
    - status: filter by ListingStatus ("draft", "pending", "active", "sold", "archived")
    - page: pagination page number
    """
    model = Listing
    template_name = "marketplace/dashboard.html"
    context_object_name = "my_listings"
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset().filter(seller=self.request.user).select_related("category")
        status_filter = self.request.GET.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        listings = ctx.get("my_listings", [])
        from .models import Transaction  # local import to avoid circular warnings
        for l in listings:
            latest_txn = Transaction.objects.filter(listing=l).order_by("-created_at").first()
            setattr(l, "latest_txn", latest_txn)
        return ctx

    def get_queryset(self):
        """Return only listings owned by the current user, optionally filtered by status."""
        qs = (
            Listing.objects.filter(seller=self.request.user)
            .select_related("category")
            .order_by("-created_at")
        )
        status_filter = (self.request.GET.get("status") or "").strip()
        valid_statuses = {s.value for s in ListingStatus}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        if getattr(settings, "MARKETPLACE_RESET", False):
            # Render placeholder if in reset mode
            return super().get_context_data(**kwargs)
        """Add status counts, current filter, and global marketplace stats to the context."""
        ctx = super().get_context_data(**kwargs)
        base_qs = Listing.objects.filter(seller=self.request.user)
        status_counts = {s.value: base_qs.filter(status=s.value).count() for s in ListingStatus}
        ctx["status_counts"] = status_counts
        ctx["status_filter"] = (self.request.GET.get("status") or "").strip()
        ctx["base_count"] = base_qs.count()

        # Global marketplace stats for dashboard metrics cards
        from django.utils import timezone
        from datetime import timedelta
        start_week = timezone.now() - timedelta(days=7)
        # Total products: active listings across marketplace
        active_listings_qs = Listing.objects.filter(status=ListingStatus.ACTIVE.value)
        total_products = active_listings_qs.count()
        new_products_week = active_listings_qs.filter(created_at__gte=start_week).count()
        # Active sellers: distinct sellers with at least one active listing
        active_sellers = active_listings_qs.values("seller_id").distinct().count()
        # New sellers this week: distinct sellers who created a listing in the past week
        new_sellers_week = (
            Listing.objects.filter(created_at__gte=start_week)
            .values("seller_id")
            .distinct()
            .count()
        )
        # Categories count
        categories_count = Category.objects.count()
        ctx["global_stats"] = {
            "total_products": total_products,
            "new_products_week": new_products_week,
            "active_sellers": active_sellers,
            "new_sellers_week": new_sellers_week,
            "categories": categories_count,
        }
        ctx["unread_notifications"] = _unread_count(self.request.user)
        return ctx

# Render the admin review wireframe
# Updated to use the admin dashboard template
# def admin_review(request):
#     return render(request, "marketplace/admin_dashboard.html")


# -----------------------------
# JSON Messaging API Endpoints
# -----------------------------

from .models import MessageThread, Message  # placed here to avoid circular import warnings


@csrf_protect
@require_http_methods(["POST"])  # Idempotent start-or-get behavior
def api_start_or_get_thread(request):
    """Start or fetch a message thread between users.

    Requires authentication. Returns 403 JSON if unauthenticated.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON body")

    listing_id = payload.get("listing_id")
    if not listing_id:
        return HttpResponseBadRequest("Missing listing_id")

    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id, status="active")
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found or inactive")

    buyer = request.user
    seller = listing.seller

    thread, created = MessageThread.objects.get_or_create(
        listing=listing, buyer=buyer, seller=seller,
        defaults={"last_message_at": timezone.now()}
    )

    # Prepare response data
    thread_data = {
        "id": thread.id,
        "listing_id": listing.id,
        "listing_title": listing.title,
        "buyer_id": buyer.id,
        "buyer_username": getattr(buyer, "username", str(buyer)),
        "seller_id": seller.id,
        "seller_username": getattr(seller, "username", str(seller)),
        "last_message_at": thread.last_message_at.isoformat(),
        "created": created,
    }

    # If there is an existing purchase request between these parties for this listing,
    # expose its id so the UI can cross-link from messages to the request detail.
    try:
        existing_request = (
            PurchaseRequest.objects.filter(listing=listing, buyer=buyer, seller=seller)
            .exclude(status=PurchaseRequestStatus.CANCELED)
            .order_by("-created_at")
            .only("id", "status")
            .first()
        )
    except Exception:
        existing_request = None
    thread_data["request_id"] = existing_request.id if existing_request else None

    recent_messages = (
        Message.objects.filter(thread=thread)
        .select_related("sender")
        .order_by("-id")[:20]
    )
    messages_list = [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_username": getattr(m.sender, "username", str(m.sender)),
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in reversed(list(recent_messages))
    ]

    return JsonResponse({"thread": thread_data, "messages": messages_list})

# Remove mock identity fallback by enforcing auth for messaging APIs
@require_http_methods(["GET"])  # Poll for new messages
def api_fetch_messages(request, thread_id):
    """Fetch messages for a thread with optional incremental polling.

    Requires authentication. Only buyer or seller in the thread may access.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Authentication required")
    try:
        thread = MessageThread.objects.select_related("buyer", "seller", "listing").get(pk=thread_id)
    except MessageThread.DoesNotExist:
        return HttpResponseBadRequest("Thread not found")

    user = request.user
    if user.id not in (thread.buyer_id, thread.seller_id):
        return HttpResponseForbidden("Not a participant in this thread")

    try:
        after_id = int(request.GET.get("after_id", 0))
    except (TypeError, ValueError):
        after_id = 0

    try:
        limit = int(request.GET.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    qs = Message.objects.filter(thread=thread)
    if after_id:
        qs = qs.filter(id__gt=after_id)
    qs = qs.select_related("sender").order_by("id")[:limit]

    messages_list = [
        {
            "id": m.id,
            "sender_id": m.sender_id,
            "sender_username": getattr(m.sender, "username", str(m.sender)),
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in qs
    ]

    # Lookup any related purchase request for this conversation participants/listing.
    try:
        existing_request = (
            PurchaseRequest.objects.filter(
                listing=thread.listing,
                buyer=thread.buyer,
                seller=thread.seller,
            )
            .exclude(status=PurchaseRequestStatus.CANCELED)
            .order_by("-created_at")
            .only("id", "status")
            .first()
        )
    except Exception:
        existing_request = None

    return JsonResponse({
        "thread_id": thread.id,
        "count": len(messages_list),
        "messages": messages_list,
        "server_time": timezone.now().isoformat(),
        "request_id": existing_request.id if existing_request else None,
    })


@csrf_protect
@require_http_methods(["POST"])  # Send a message to a thread
def api_post_message(request, thread_id):
    """Post a new message to a thread as JSON.

    Requires authentication. Only buyer or seller may post.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden("Authentication required")
    try:
        thread = MessageThread.objects.select_related("buyer", "seller").get(pk=thread_id)
    except MessageThread.DoesNotExist:
        return HttpResponseBadRequest("Thread not found")

    user = request.user
    if user.id not in (thread.buyer_id, thread.seller_id):
        return HttpResponseForbidden("Not a participant in this thread")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON body")

    content = sanitize_text((payload.get("content") or "").strip(), max_len=1000)
    if not content:
        return HttpResponseBadRequest("Message content is required")
    # content already trimmed by sanitize_text

    message = Message.objects.create(thread=thread, sender=user, content=content)

    MessageThread.objects.filter(pk=thread.pk).update(last_message_at=timezone.now())

    msg_json = {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_username": getattr(user, "username", str(user)),
        "content": message.content,
        "created_at": message.created_at.isoformat(),
    }

    return JsonResponse({"message": msg_json})

# -----------------------------
# Listing Transaction Endpoints
# -----------------------------

def _auto_hide_if_out_of_stock(listing):
    """Auto-hide listing when quantity reaches 0 by setting status to 'archived'.

    This helper should be used for non-finalized actions such as reservations.
    For explicit sales, the status will be set to 'sold' when quantity hits zero.
    """
    if listing.quantity <= 0:
        # Use ARCHIVED to hide from catalog (only 'active' listings are shown)
        if listing.status != ListingStatus.ARCHIVED:
            Listing.objects.filter(pk=listing.pk).update(status=ListingStatus.ARCHIVED)

def _cascade_close_open_requests_for_listing(listing, reason="out of stock"):
    """When stock becomes unavailable, close or update open requests for this listing.

    Marks all pending or negotiating requests as rejected and logs the action.
    """
    try:
        open_reqs = PurchaseRequest.objects.filter(
            listing=listing,
            status__in=[PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING],
        )
        # Bulk update statuses
        updated = open_reqs.update(status=PurchaseRequestStatus.REJECTED)
        # Best-effort logs and notifications per affected request
        for req in open_reqs:
            try:
                TransactionLog.objects.create(
                    request=req,
                    actor=None,
                    action=LogAction.SELLER_REJECT,
                    note=f"Auto-closed: {reason}",
                )
                # Notify buyer and seller about closure
                _notify(req.buyer, NotificationType.STATUS_CHANGED, request_obj=req, listing=listing, message_text="rejected", send_email=True)
                _notify(req.seller, NotificationType.STATUS_CHANGED, request_obj=req, listing=listing, message_text="rejected", send_email=True)
            except Exception:
                pass
    except Exception:
        pass

@csrf_protect
@require_http_methods(["POST"])  # Reserve one unit of a listing
def api_listing_reserve(request, listing_id):
    """Mark a listing as reserved by creating/updating a Transaction to 'confirmed'.

    Requires authentication. Buyer is request.user.
    After reservation, set listing.status to 'pending' to reflect the reservation state.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id, status=ListingStatus.ACTIVE)
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found or not active")

    if listing.quantity <= 0:
        return HttpResponseBadRequest("Out of stock")

    buyer = request.user
    seller = listing.seller

    txn, _ = Transaction.objects.get_or_create(
        listing=listing,
        buyer=buyer,
        seller=seller,
        defaults={"status": TransactionStatus.AWAITING_PAYMENT}
    )
    if txn.status != TransactionStatus.AWAITING_PAYMENT:
        txn.status = TransactionStatus.AWAITING_PAYMENT
        txn.save(update_fields=["status"])

    # Decrement stock and move listing to 'pending' state
    listing.quantity = max(0, listing.quantity - 1)
    listing.status = ListingStatus.PENDING
    listing.save(update_fields=["quantity", "status"])
    # If reservation exhausted stock, optionally auto-hide and cascade close open requests
    if listing.quantity <= 0:
        # Only auto-archive if there are other open requests to close; otherwise keep as 'pending'
        try:
            has_open_reqs = PurchaseRequest.objects.filter(
                listing=listing,
                status__in=[PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING],
            ).exists()
        except Exception:
            has_open_reqs = False

        if has_open_reqs:
            # Hide from catalog to reflect no available stock for other buyers
            listing.status = ListingStatus.ARCHIVED
            listing.save(update_fields=["status"])

        # Close open requests regardless since stock is exhausted
        _cascade_close_open_requests_for_listing(listing, reason="last unit reserved")

    return JsonResponse({
        "listing": {
            "id": listing.id,
            "title": listing.title,
            "quantity": listing.quantity,
            "status": listing.status,
        },
        "transaction": {
            "id": txn.id,
            "status": txn.status,
            "buyer_id": buyer.id,
            "seller_id": seller.id,
        }
    })

@csrf_protect
@require_http_methods(["POST"])  # Sell one unit of a listing
def api_listing_sell(request, listing_id):
    """Sell flow handler supporting two scenarios:

    - Direct checkout: for active listings, any authenticated buyer can purchase.
      Creates a transaction for the buyer, decrements stock, sets status to 'sold' when zero, else 'active'.
    - Payment recording: for reserved (pending) listings, only the seller can record payment
      against the awaiting transaction. Marks transaction as paid and updates listing status.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    # Fetch listing and proceed
    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id)
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found")

    seller = listing.seller

    # Branch on listing status
    if listing.status == ListingStatus.PENDING:
        # Payment recording by seller for a reserved listing
        if request.user.id != seller.id:
            return JsonResponse({"error": "Only the seller can record payment"}, status=403)

        # Use the latest awaiting-payment transaction for this listing
        txn = Transaction.objects.filter(listing=listing, status=TransactionStatus.AWAITING_PAYMENT).order_by("-created_at").first()
        if not txn:
            return JsonResponse({"error": "No awaiting-payment transaction found for this listing"}, status=400)

        # Capture payment details (JSON or form-data)
        payment_method = None
        amount_paid = None
        proof_file = None
        ct = (request.content_type or "").lower()
        if ct.startswith("application/json"):
            import json
            try:
                payload = json.loads(request.body or b"{}")
            except Exception:
                payload = {}
            payment_method = (payload.get("payment_method") or "").strip() or None
            amount_paid = payload.get("amount_paid")
        else:
            payment_method = (request.POST.get("payment_method") or "").strip() or None
            amount_paid = request.POST.get("amount_paid")
            proof_file = request.FILES.get("payment_proof")

        if amount_paid is not None:
            from decimal import Decimal
            try:
                amount_paid = Decimal(str(amount_paid))
            except Exception:
                amount_paid = None

        field_errors = {}
        valid_methods = {m.value for m in Transaction.PaymentMethod}
        if payment_method and payment_method not in valid_methods:
            field_errors["payment_method"] = "Invalid payment method"
        else:
            txn.payment_method = payment_method
        if amount_paid is not None:
            if amount_paid <= 0:
                field_errors["amount_paid"] = "Amount must be positive"
            elif listing.price and amount_paid > listing.price:
                field_errors["amount_paid"] = "Amount cannot exceed listing price"
            else:
                txn.amount_paid = amount_paid
        if proof_file is not None:
            txn.payment_proof = proof_file

        if field_errors:
            return JsonResponse({"error": "Validation failed", "field_errors": field_errors}, status=400)

        if txn.status != TransactionStatus.PAID:
            txn.status = TransactionStatus.PAID
        txn.save(update_fields=["status", "payment_method", "amount_paid", "payment_proof"])

        # Reservation already consumed stock; ensure status reflects final outcome
        listing.quantity = max(0, listing.quantity - 1)
        if listing.quantity == 0:
            listing.status = ListingStatus.SOLD
            listing.save(update_fields=["quantity", "status"])
            _cascade_close_open_requests_for_listing(listing, reason="sold out")
        else:
            listing.status = ListingStatus.ACTIVE
            listing.save(update_fields=["quantity", "status"])

        return JsonResponse({
            "listing": {
                "id": listing.id,
                "title": listing.title,
                "quantity": listing.quantity,
                "status": listing.status,
            },
            "transaction": {
                "id": txn.id,
                "status": txn.status,
                "buyer_id": txn.buyer_id,
                "seller_id": seller.id,
                "payment_method": txn.payment_method,
                "amount_paid": str(txn.amount_paid) if txn.amount_paid is not None else None,
            }
        })
    else:
        # Direct checkout purchase flow for active listings
        if listing.quantity <= 0:
            return HttpResponseBadRequest("Out of stock")

        buyer = request.user
        # Create or update a transaction for this buyer/listing to PAID
        txn, _ = Transaction.objects.get_or_create(
            listing=listing,
            buyer=buyer,
            seller=seller,
            defaults={"status": TransactionStatus.PAID}
        )
        if txn.status != TransactionStatus.PAID:
            txn.status = TransactionStatus.PAID
            txn.save(update_fields=["status"])

        listing.quantity = max(0, listing.quantity - 1)
        if listing.quantity == 0:
            listing.status = ListingStatus.SOLD
            listing.save(update_fields=["quantity", "status"])
            _cascade_close_open_requests_for_listing(listing, reason="sold out")
        else:
            listing.status = ListingStatus.ACTIVE
            listing.save(update_fields=["quantity", "status"])

        return JsonResponse({
            "listing": {
                "id": listing.id,
                "title": listing.title,
                "quantity": listing.quantity,
                "status": listing.status,
            },
            "transaction": {
                "id": txn.id,
                "status": txn.status,
                "buyer_id": buyer.id,
                "seller_id": seller.id,
                "payment_method": txn.payment_method,
                "amount_paid": str(txn.amount_paid) if txn.amount_paid is not None else None,
            }
        })

@csrf_protect
@require_http_methods(["POST"])  # Mark latest transaction as completed (without changing stock)
def api_listing_complete(request, listing_id):
    """Finalize a transaction for a listing by setting transaction status to 'completed'.

    Requires authentication. Listing must be 'sold'. Returns 403 JSON if unauthenticated.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id)
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found")

    seller = listing.seller
    # Allow either party to finalize a PAID transaction
    txn = Transaction.objects.filter(listing=listing, status=TransactionStatus.PAID).order_by("-created_at").first()
    if not txn:
        return JsonResponse({"error": "No paid transaction to complete"}, status=400)
    if request.user.id not in {txn.buyer_id, txn.seller_id}:
        return JsonResponse({"error": "Not authorized to complete this transaction"}, status=403)
    if txn.status != TransactionStatus.COMPLETED:
        txn.status = TransactionStatus.COMPLETED
        txn.save(update_fields=["status"])

    # Listing remains 'sold'
    listing.refresh_from_db(fields=["status", "quantity"])  # Keep current status

    return JsonResponse({
        "listing": {
            "id": listing.id,
            "title": listing.title,
            "quantity": listing.quantity,
            "status": listing.status,
        },
        "transaction": {
            "id": txn.id,
            "status": txn.status,
            "buyer_id": txn.buyer_id,
            "seller_id": seller.id,
        }
    })

# -----------------------------
# Reporting Endpoint
# -----------------------------

@csrf_protect
@require_http_methods(["POST"])  # File a report about a listing
def api_listing_report(request, listing_id):
    """File a report for a listing.

    Expected JSON body:
    - reason: short reason string (required)
    - details: optional text details

    Requires authentication. Auto-flag listing as 'pending' when open reports reach threshold.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON body")

    reason = sanitize_text((payload.get("reason") or "").strip(), max_len=200)
    details = sanitize_text((payload.get("details") or "").strip(), max_len=2000)
    if not reason:
        return HttpResponseBadRequest("Report 'reason' is required")

    try:
        listing = Listing.objects.get(pk=listing_id)
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found")

    reporter = request.user
    report = Report.objects.create(reporter=reporter, listing=listing, reason=reason, details=details)

    open_count = Report.objects.filter(listing=listing, status=ReportStatus.OPEN).count()
    flagged = False
    if open_count >= REPORT_THRESHOLD:
        if listing.status != ListingStatus.PENDING:
            listing.status = ListingStatus.PENDING
            listing.save(update_fields=["status"])
        flagged = True

    return JsonResponse({
        "report": {
            "id": report.id,
            "listing_id": listing.id,
            "reason": report.reason,
            "details": report.details,
            "status": report.status,
        },
        "open_report_count": open_count,
        "flagged": flagged,
        "listing_status": listing.status,
    })

# Minimal template view to submit a listing report via UI
@ensure_csrf_cookie
def report_listing(request, listing_id):
    """Render a minimal report submission page for a given listing id."""
    return render(request, "marketplace/report_listing.html", {"listing_id": listing_id})


def reset_placeholder(request):
    """Minimal placeholder view for marketplace reset mode."""
    return render(request, "marketplace/reset.html")

class CategoryViewSet(viewsets.ModelViewSet):
    """RESTful endpoints for categories."""
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class ListingViewSet(viewsets.ModelViewSet):
    """RESTful endpoints for listings with seller-bound create/update."""
    queryset = Listing.objects.all().order_by("-created_at")
    serializer_class = ListingSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        """Attach current user as seller when creating a listing."""
        serializer.save(seller=self.request.user)

    @action(detail=True, methods=["post"], url_path="reserve")
    def reserve(self, request, pk=None):
        """Reserve one unit of a listing; mirrors api_listing_reserve."""
        return api_listing_reserve(request._request, pk)

    @action(detail=True, methods=["post"], url_path="sell")
    def sell(self, request, pk=None):
        """Sell one unit of a listing; mirrors api_listing_sell."""
        return api_listing_sell(request._request, pk)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        """Finalize transaction for a listing; mirrors api_listing_complete."""
        return api_listing_complete(request._request, pk)

class MessageThreadViewSet(viewsets.ModelViewSet):
    """RESTful endpoints for message threads with custom start action."""
    queryset = MessageThread.objects.select_related("listing", "buyer", "seller").all()
    serializer_class = MessageThreadSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    @action(detail=False, methods=["post"], url_path="start")
    def start(self, request):
        """Start or get a thread; mirrors api_start_or_get_thread."""
        return api_start_or_get_thread(request._request)

    @action(detail=True, methods=["get"], url_path="messages")
    def messages(self, request, pk=None):
        """Fetch messages of a thread; mirrors api_fetch_messages."""
        return api_fetch_messages(request._request, pk)

    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        """Send a message to a thread; mirrors api_post_message."""
        return api_post_message(request._request, pk)

class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset to list messages globally or by thread."""
    serializer_class = MessageSerializer

    def get_queryset(self):
        qs = Message.objects.select_related("thread", "sender").all()
        thread_id = self.request.query_params.get("thread")
        if thread_id:
            qs = qs.filter(thread_id=thread_id)
        return qs.order_by("id")

class TransactionViewSet(viewsets.ModelViewSet):
    """RESTful endpoints for transactions."""
    queryset = Transaction.objects.select_related("listing", "buyer", "seller").all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

class ReportViewSet(viewsets.ModelViewSet):
    """RESTful endpoints for listing reports."""
    queryset = Report.objects.select_related("listing", "reporter").all()
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        """Set reporter to current user and apply auto-flag logic similar to FBV."""
        report = serializer.save(reporter=self.request.user)
        listing = report.listing
        open_count = Report.objects.filter(listing=listing, status=ReportStatus.OPEN).count()
        if open_count >= REPORT_THRESHOLD and listing.status != ListingStatus.PENDING:
            listing.status = ListingStatus.PENDING
            listing.save(update_fields=["status"])

# ---------------------------------------------
# Purchase Request JSON API Endpoints (Manual Flow)
# ---------------------------------------------

@csrf_protect
@require_http_methods(["POST"])  # Buyer creates a manual purchase request
def api_request_create(request, listing_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id)
    except Listing.DoesNotExist:
        return json_error("Listing not found", status=404)

    buyer = request.user
    seller = listing.seller

    if buyer.id == getattr(seller, "id", None):
        return json_error("Cannot request your own listing", status=403)
    if listing.status != ListingStatus.ACTIVE:
        return json_error("Listing is not available for requests", status=400)
    if getattr(listing, "quantity", 0) <= 0:
        return json_error("Listing is out of stock", status=400)

    existing = PurchaseRequest.objects.filter(
        listing=listing,
        buyer=buyer,
        status=PurchaseRequestStatus.PENDING,
    ).first()
    if existing:
        return json_error("You already have a pending request for this listing", status=400)

    note = ""
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        note = sanitize_text((payload.get("message") or "").strip(), max_len=1000)
    else:
        note = sanitize_text((request.POST.get("message") or "").strip(), max_len=1000)

    pr = PurchaseRequest.objects.create(
        listing=listing,
        buyer=buyer,
        seller=seller,
        status=PurchaseRequestStatus.PENDING,
        message=note,
    )
    TransactionLog.objects.create(
        request=pr,
        actor=buyer,
        action=LogAction.BUYER_REQUEST,
        note=note,
    )
    _notify(seller, NotificationType.REQUEST_CREATED, request_obj=pr, listing=listing, message_text=note, send_email=True)
    _notify(buyer, NotificationType.REQUEST_CREATED, request_obj=pr, listing=listing, message_text=note, send_email=True)

    return json_ok({
        "request": {
            "id": pr.id,
            "status": pr.status,
            "listing_id": listing.id,
            "buyer_id": buyer.id,
            "seller_id": seller.id,
            "message": pr.message,
        }
    }, status=201)

@csrf_protect
@rate_limit("request_accept")
@require_http_methods(["POST"])  # Seller accepts a request
def api_request_accept(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING):
        return json_error("Cannot accept in current status", status=400)
    if pr.listing.status != ListingStatus.ACTIVE:
        return json_error("Listing not available for acceptance", status=400)
    existing_accepted = (
        PurchaseRequest.objects
        .filter(listing=pr.listing, status=PurchaseRequestStatus.ACCEPTED)
        .exclude(pk=pr.id)
        .exists()
    )
    if existing_accepted:
        return json_error("Listing already reserved by another request", status=400)

    pr.status = PurchaseRequestStatus.ACCEPTED
    pr.accepted_at = timezone.now()
    txn = Transaction.objects.create(
        listing=pr.listing,
        buyer=pr.buyer,
        seller=pr.seller,
        status=TransactionStatus.CONFIRMED,
    )
    pr.transaction = txn
    pr.save(update_fields=["status", "accepted_at", "transaction", "updated_at"])
    pr.listing.status = ListingStatus.RESERVED
    pr.listing.save(update_fields=["status", "updated_at"])
    # Capture optional note from JSON or form
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        note = sanitize_text((payload.get("note") or payload.get("message") or "").strip(), max_len=500)
    else:
        note = sanitize_text((request.POST.get("note") or "").strip(), max_len=500)

    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_ACCEPT,
        note=note,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="accepted", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="accepted", send_email=True)

    return json_ok({
        "request": {
            "id": pr.id,
            "status": pr.status,
            "transaction_id": pr.transaction.id,
        },
        "listing": {
            "id": pr.listing.id,
            "status": pr.listing.status,
        }
    })

@csrf_protect
@rate_limit("request_reject")
@require_http_methods(["POST"])  # Seller rejects a request
def api_request_reject(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING):
        return json_error("Cannot reject in current status", status=400)
    pr.status = PurchaseRequestStatus.REJECTED
    pr.save(update_fields=["status", "updated_at"])
    try:
        if pr.listing.status == ListingStatus.RESERVED:
            pr.listing.status = ListingStatus.ACTIVE
            pr.listing.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    # Capture optional note from JSON or form
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        note = sanitize_text((payload.get("note") or payload.get("message") or "").strip(), max_len=500)
    else:
        note = sanitize_text((request.POST.get("note") or "").strip(), max_len=500)

    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_REJECT,
        note=note,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="rejected", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="rejected", send_email=True)
    return json_ok({"request": {"id": pr.id, "status": pr.status}})

@csrf_protect
@rate_limit("request_negotiate")
@require_http_methods(["POST"])  # Seller sets status to negotiating
def api_request_negotiate(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if not _ensure_request_owner(pr, request.user) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status != PurchaseRequestStatus.PENDING:
        return json_error("Cannot negotiate in current status", status=400)
    pr.status = PurchaseRequestStatus.NEGOTIATING
    pr.save(update_fields=["status", "updated_at"])
    # Capture optional note from JSON or form
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        note = sanitize_text((payload.get("note") or payload.get("message") or "").strip(), max_len=500)
    else:
        note = sanitize_text((request.POST.get("note") or "").strip(), max_len=500)

    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.SELLER_NEGOTIATE,
        note=note,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="negotiating")
    return json_ok({"request": {"id": pr.id, "status": pr.status}})

@csrf_protect
@rate_limit("request_cancel")
@require_http_methods(["POST"])  # Either party cancels
def api_request_cancel(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status not in (PurchaseRequestStatus.PENDING, PurchaseRequestStatus.NEGOTIATING, PurchaseRequestStatus.ACCEPTED):
        return json_error("Cannot cancel in current status", status=400)
    # Capture reason from JSON or form and sanitize
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        reason = sanitize_text((payload.get("reason") or "").strip(), max_len=500)
    else:
        reason = sanitize_text((request.POST.get("reason") or "").strip(), max_len=500)
    pr.status = PurchaseRequestStatus.CANCELED
    pr.canceled_reason = reason
    pr.save(update_fields=["status", "canceled_reason", "updated_at"])
    try:
        if pr.transaction and pr.transaction.status not in (TransactionStatus.COMPLETED, TransactionStatus.CANCELED):
            pr.transaction.status = TransactionStatus.CANCELED
            pr.transaction.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    try:
        if pr.listing.status == ListingStatus.RESERVED:
            pr.listing.status = ListingStatus.ACTIVE
            pr.listing.save(update_fields=["status", "updated_at"])
    except Exception:
        pass
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.REQUEST_CANCELED,
        note=reason,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="canceled", send_email=True)
    return json_ok({"request": {"id": pr.id, "status": pr.status, "canceled_reason": pr.canceled_reason}})

@csrf_protect
@require_http_methods(["POST"])  # Propose or update meetup
def api_request_meetup_set(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return json_error("Request not active", status=400)
    if not pr.transaction:
        return json_error("No transaction for this request", status=400)

    # Parse payload
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return json_error("Invalid JSON body")
        meetup_time = payload.get("meetup_time")
        meetup_place = sanitize_text((payload.get("meetup_place") or "").strip(), max_len=200)
        meetup_timezone = (payload.get("meetup_timezone") or "").strip()
        reschedule_reason = sanitize_text((payload.get("reschedule_reason") or "").strip(), max_len=240)
        # Parse ISO datetime string into aware datetime without external deps
        from django.utils.dateparse import parse_datetime
        mt = parse_datetime(meetup_time) if meetup_time else None
        if mt and timezone.is_naive(mt):
            mt = timezone.make_aware(mt, timezone.get_default_timezone())
    else:
        meetup_place = sanitize_text((request.POST.get("meetup_place") or "").strip(), max_len=200)
        meetup_timezone = (request.POST.get("meetup_timezone") or "").strip()
        reschedule_reason = sanitize_text((request.POST.get("reschedule_reason") or "").strip(), max_len=240)
        try:
            mt = request.POST.get("meetup_time")
            from django.utils.dateparse import parse_datetime
            mt = parse_datetime(mt) if mt else None
            if mt and timezone.is_naive(mt):
                mt = timezone.make_aware(mt, timezone.get_default_timezone())
        except Exception:
            mt = None

    field_errors = {}
    if not meetup_place:
        field_errors["meetup_place"] = "Meetup place is required"
    if not mt:
        field_errors["meetup_time"] = "Valid meetup_time is required"
    if field_errors:
        return json_error("Validation failed", field_errors=field_errors)

    is_update = bool(pr.transaction.meetup_time or pr.transaction.meetup_place)
    pr.transaction.meetup_time = mt
    pr.transaction.meetup_place = meetup_place
    tz_name = (meetup_timezone or "").strip() or timezone.get_current_timezone_name()
    pr.transaction.meetup_timezone = tz_name
    pr.transaction.reschedule_reason = reschedule_reason if is_update else ""
    pr.transaction.save(update_fields=["meetup_time", "meetup_place", "meetup_timezone", "reschedule_reason", "updated_at"])
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.MEETUP_UPDATED if is_update else LogAction.MEETUP_PROPOSED,
        note=f"{meetup_place} @ {mt} (TZ: {tz_name})" + (f" | Reason: {reschedule_reason}" if is_update and reschedule_reason else ""),
    )
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text=("meetup updated" if is_update else "meetup proposed"), send_email=True)

    return json_ok({
        "request": {"id": pr.id, "status": pr.status},
        "transaction": {
            "id": pr.transaction.id,
            "meetup_place": pr.transaction.meetup_place,
            "meetup_time": pr.transaction.meetup_time.isoformat() if pr.transaction.meetup_time else None,
            "meetup_timezone": pr.transaction.meetup_timezone,
            "reschedule_reason": pr.transaction.reschedule_reason,
        }
    })

@csrf_protect
@require_http_methods(["POST"])  # Confirm meetup
def api_request_meetup_confirm(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id not in (pr.buyer_id, pr.seller_id) and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status in (PurchaseRequestStatus.COMPLETED, PurchaseRequestStatus.CANCELED):
        return json_error("Request not active", status=400)
    if not pr.transaction:
        return json_error("No transaction for this request", status=400)
    if not pr.transaction.meetup_time or not pr.transaction.meetup_place:
        return json_error("No meetup to confirm", status=400)
    mt = pr.transaction.meetup_time
    if timezone.is_naive(mt):
        mt = timezone.make_aware(mt, timezone.get_default_timezone())
    if mt <= timezone.now():
        return json_error("Meetup time is not in the future")
    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.MEETUP_CONFIRMED,
        note=f"{pr.transaction.meetup_place} @ {pr.transaction.meetup_time}",
    )
    other = pr.seller if request.user.id == pr.buyer_id else pr.buyer
    _notify(other, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="meetup confirmed")
    return json_ok({
        "request": {"id": pr.id, "status": pr.status},
        "transaction": {
            "id": pr.transaction.id,
            "meetup_place": pr.transaction.meetup_place,
            "meetup_time": pr.transaction.meetup_time.isoformat() if pr.transaction.meetup_time else None,
        }
    })

@csrf_protect
@require_http_methods(["POST"])  # Buyer marks complete
def api_request_complete(request, request_id):
    if not request.user.is_authenticated:
        return json_error("Authentication required", status=403)
    pr = get_object_or_404(PurchaseRequest, pk=request_id)
    if request.user.id != pr.buyer_id and not _is_moderator(request.user):
        return json_error("Not authorized", status=403)
    if pr.status != PurchaseRequestStatus.ACCEPTED:
        return json_error("Cannot complete in current status", status=400)
    if not pr.transaction or pr.transaction.status != TransactionStatus.PAID:
        return json_error("Transaction not paid", status=400)
    pr.status = PurchaseRequestStatus.COMPLETED
    pr.completed_at = timezone.now()
    pr.save(update_fields=["status", "completed_at", "updated_at"])
    pr.transaction.status = TransactionStatus.COMPLETED
    pr.transaction.save(update_fields=["status", "updated_at"])
    pr.listing.status = ListingStatus.SOLD
    pr.listing.save(update_fields=["status", "updated_at"])
    # Optional note from JSON or form
    ct = (request.content_type or "").lower()
    if ct.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        note = sanitize_text((payload.get("note") or payload.get("message") or "").strip(), max_len=500)
    else:
        note = sanitize_text((request.POST.get("note") or "").strip(), max_len=500)

    TransactionLog.objects.create(
        request=pr,
        actor=request.user,
        action=LogAction.REQUEST_COMPLETED,
        note=note,
    )
    _notify(pr.buyer, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="completed", send_email=True)
    _notify(pr.seller, NotificationType.STATUS_CHANGED, request_obj=pr, listing=pr.listing, message_text="completed", send_email=True)
    return json_ok({
        "request": {"id": pr.id, "status": pr.status, "completed_at": pr.completed_at.isoformat()},
        "listing": {"id": pr.listing.id, "status": pr.listing.status},
        "transaction": {"id": pr.transaction.id, "status": pr.transaction.status},
    })
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate

# -----------------------------
# Marketplace Admin role helpers
# -----------------------------

def _is_marketplace_admin(user):
    """Return True if user belongs to the 'Marketplace Admin' group or is superuser."""
    if not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(name="Marketplace Admin").exists()


# -----------------------------
# Legacy moderator route redirect
# -----------------------------
def moderator_legacy_redirect(request):
    """Temporary redirect for legacy moderator dashboard.

    - Unauthenticated users: redirect to login with next set.
    - Marketplace admins: 302 redirect to unified admin home.
    - Authenticated non-admins: 403 Forbidden.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    if _is_marketplace_admin(user):
        # Temporary: use 302 to allow QA; later remove route entirely.
        return redirect("marketplace_admin:dashboard")

    return render(
        request,
        "marketplace/403.html",
        {"message": "Marketplace admin access required"},
        status=403,
    )


class MarketplaceAdminRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return _is_marketplace_admin(self.request.user)

    def handle_no_permission(self):
        from django.shortcuts import render
        response = render(
            self.request,
            "marketplace/403.html",
            {"message": "Marketplace Admins only"},
        )
        response.status_code = 403
        return response

class MarketplaceAdminPermRequiredMixin(MarketplaceAdminRequiredMixin):
    """Extends admin gating with per-view model permission checks."""
    required_perms = []

    def test_func(self):
        if not super().test_func():
            return False
        user = self.request.user
        for p in getattr(self, "required_perms", []) or []:
            if not user.has_perm(p):
                return False
        return True


class AdminDashboardView(LoginRequiredMixin, MarketplaceAdminRequiredMixin, TemplateView):
    """Top-level admin dashboard view that dispatches to analytics by default."""
    template_name = "marketplace/admin/admin_dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Default to analytics tab when hitting /admin-dashboard/
        ctx["active_tab"] = "analytics"
        # Minimal context; subviews provide detailed data.
        return ctx


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AdminListingsView(LoginRequiredMixin, MarketplaceAdminPermRequiredMixin, ListView):
    model = Listing
    template_name = "marketplace/admin/admin_dashboard.html"
    context_object_name = "pending_listings"
    required_perms = ["marketplace.can_approve_listing"]

    def get_queryset(self):
        return (
            Listing.objects.filter(status=ListingStatus.PENDING)
            .select_related("seller", "category")
            .order_by("-created_at")
        )

    def render_to_response(self, context, **response_kwargs):
        # Support JSON output for AJAX table refresh
        if wants_json(self.request):
            listings = []
            for l in context.get("pending_listings", []):
                listings.append({
                    "id": l.id,
                    "title": l.title,
                    "seller": getattr(l.seller, "username", str(l.seller)),
                    "price": float(l.price or 0),
                    "submitted": l.created_at.strftime("%Y-%m-%d %H:%M"),
                })
            return JsonResponse({
                "status": "ok",
                "count": len(listings),
                "listings": listings,
            })
        return super().render_to_response(context, **response_kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "listings"
        try:
            from .models import Listing as ListingModel
            field = ListingModel._meta.get_field("rejected_reason_code")
            ctx["rejection_reason_choices"] = getattr(field, "choices", [])
        except Exception:
            ctx["rejection_reason_choices"] = []
        return ctx


class AdminAnalyticsView(LoginRequiredMixin, MarketplaceAdminPermRequiredMixin, TemplateView):
    template_name = "marketplace/admin/admin_dashboard.html"
    required_perms = ["marketplace.can_view_analytics"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "analytics"

        from .models import Transaction, Category, Listing
        from django.contrib.auth import get_user_model

        # Revenue trends (daily) from paid or completed transactions
        revenue_qs = (
            Transaction.objects.filter(status__in=[TransactionStatus.PAID, TransactionStatus.COMPLETED])
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(total=Sum("amount_paid"))
            .order_by("day")
        )
        revenue_labels = [r["day"].strftime("%Y-%m-%d") for r in revenue_qs]
        revenue_data = [float(r["total"] or 0) for r in revenue_qs]

        # Top categories by total sales amount
        top_categories_sales = (
            Transaction.objects.filter(status__in=[TransactionStatus.PAID, TransactionStatus.COMPLETED])
            .values("listing__category__name")
            .annotate(total_sales=Sum("amount_paid"))
            .order_by("-total_sales")[:10]
        )
        cat_labels = [c["listing__category__name"] or "Uncategorized" for c in top_categories_sales]
        cat_data = [float(c["total_sales"] or 0) for c in top_categories_sales]

        # Top categories by active listings
        active_by_category = (
            Listing.objects.filter(status=ListingStatus.ACTIVE)
            .values("category__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )
        active_cat_labels = [c["category__name"] or "Uncategorized" for c in active_by_category]
        active_cat_data = [int(c["count"] or 0) for c in active_by_category]

        # User growth by date joined
        User = get_user_model()
        user_growth = (
            User.objects.all()
            .annotate(day=TruncDate("date_joined"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        user_labels = [u["day"].strftime("%Y-%m-%d") for u in user_growth]
        user_data = [int(u["count"] or 0) for u in user_growth]

        # Recent transactions for quick actions table
        recent_transactions = (
            Transaction.objects.filter(status__in=[TransactionStatus.PAID, TransactionStatus.COMPLETED])
            .select_related("listing", "buyer", "seller")
            .order_by("-created_at")[:10]
        )

        # Categories list for filter dropdown
        categories = Category.objects.order_by("name")

        # --- KPI Cards ---
        total_listings = Listing.objects.count()
        approved_listings = Listing.objects.filter(status__in=[ListingStatus.ACTIVE, ListingStatus.SOLD, ListingStatus.RESERVED]).count()
        rejected_listings = Listing.objects.filter(status=ListingStatus.REJECTED).count()
        active_users = User.objects.filter(is_active=True).count()
        transactions_completed = Transaction.objects.filter(status=TransactionStatus.COMPLETED).count()

        ctx.update(
            {
                "revenue_labels_json": json.dumps(revenue_labels),
                "revenue_data_json": json.dumps(revenue_data),
                "categories_labels_json": json.dumps(cat_labels),
                "categories_data_json": json.dumps(cat_data),
                "active_cat_labels_json": json.dumps(active_cat_labels),
                "active_cat_data_json": json.dumps(active_cat_data),
                "user_labels_json": json.dumps(user_labels),
                "user_data_json": json.dumps(user_data),
                "recent_transactions": recent_transactions,
                "categories": categories,
                "kpi_total_listings": total_listings,
                "kpi_approved_listings": approved_listings,
                "kpi_rejected_listings": rejected_listings,
                "kpi_active_users": active_users,
                "kpi_transactions_completed": transactions_completed,
            }
        )
        return ctx


class AdminUsersView(LoginRequiredMixin, MarketplaceAdminPermRequiredMixin, ListView):
    template_name = "marketplace/admin/admin_dashboard.html"
    context_object_name = "users"
    required_perms = ["accounts.view_user"]

    def get_queryset(self):
        from django.contrib.auth import get_user_model
        from django.db.models import Exists
        User = get_user_model()

        role = (self.request.GET.get("role") or "").strip().lower()
        q = (self.request.GET.get("q") or "").strip()

        # Annotate marketplace activity booleans to infer role
        seller_listing_exists = Exists(Listing.objects.filter(seller_id=OuterRef("pk")))
        seller_sales_exists = Exists(Transaction.objects.filter(seller_id=OuterRef("pk")))
        seller_pr_exists = Exists(PurchaseRequest.objects.filter(seller_id=OuterRef("pk")))
        seller_threads_exists = Exists(MessageThread.objects.filter(seller_id=OuterRef("pk")))

        buyer_purchases_exists = Exists(Transaction.objects.filter(buyer_id=OuterRef("pk")))
        buyer_pr_exists = Exists(PurchaseRequest.objects.filter(buyer_id=OuterRef("pk")))
        buyer_threads_exists = Exists(MessageThread.objects.filter(buyer_id=OuterRef("pk")))

        qs = (
            User.objects
            .annotate(
                has_seller_listings=seller_listing_exists,
                has_seller_sales=seller_sales_exists,
                has_seller_requests=seller_pr_exists,
                has_seller_threads=seller_threads_exists,
                has_buyer_purchases=buyer_purchases_exists,
                has_buyer_requests=buyer_pr_exists,
                has_buyer_threads=buyer_threads_exists,
            )
            .order_by("-date_joined")
        )

        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))

        # Filter by inferred role if provided; otherwise include users with any role activity
        if role == "seller":
            qs = qs.filter(
                Q(has_seller_listings=True)
                | Q(has_seller_sales=True)
                | Q(has_seller_requests=True)
                | Q(has_seller_threads=True)
            )
        elif role == "buyer":
            qs = qs.filter(
                Q(has_buyer_purchases=True)
                | Q(has_buyer_requests=True)
                | Q(has_buyer_threads=True)
            )
        else:
            qs = qs.filter(
                Q(has_seller_listings=True)
                | Q(has_seller_sales=True)
                | Q(has_seller_requests=True)
                | Q(has_seller_threads=True)
                | Q(has_buyer_purchases=True)
                | Q(has_buyer_requests=True)
                | Q(has_buyer_threads=True)
            )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "users"
        # Preserve filters for template
        ctx["users_search_query"] = (self.request.GET.get("q") or "").strip()
        ctx["users_role"] = (self.request.GET.get("role") or "").strip().lower()
        return ctx

    def render_to_response(self, context, **response_kwargs):
        # Support JSON output for AJAX table refresh
        if wants_json(self.request):
            users_payload = []
            for u in context.get("users", []):
                is_seller = (
                    getattr(u, "has_seller_listings", False)
                    or getattr(u, "has_seller_sales", False)
                    or getattr(u, "has_seller_requests", False)
                    or getattr(u, "has_seller_threads", False)
                )
                is_buyer = (
                    getattr(u, "has_buyer_purchases", False)
                    or getattr(u, "has_buyer_requests", False)
                    or getattr(u, "has_buyer_threads", False)
                )
                role = "seller" if is_seller else ("buyer" if is_buyer else "")
                users_payload.append(
                    {
                        "id": u.id,
                        "username": u.username,
                        "role": role,
                        "active": bool(u.is_active),
                    }
                )
            return JsonResponse({
                "status": "ok",
                "count": len(users_payload),
                "users": users_payload,
            })
        return super().render_to_response(context, **response_kwargs)


# --- Analytics JSON endpoint for filters ---
@login_required
@user_passes_test(_is_marketplace_admin)
@require_http_methods(["GET"])
def admin_analytics_data(request):
    """Return analytics datasets filtered by date range and category.

    Query params:
    - start: YYYY-MM-DD (optional; default 30 days ago)
    - end: YYYY-MM-DD (optional; default today)
    - category: category slug (optional)
    """
    if not request.user.has_perm("marketplace.can_view_analytics"):
        return HttpResponseForbidden("Insufficient permissions for analytics")

    from django.utils.dateparse import parse_date
    from datetime import timedelta

    today = timezone.localdate()
    start_raw = (request.GET.get("start") or "").strip()
    end_raw = (request.GET.get("end") or "").strip()
    category_slug = (request.GET.get("category") or "").strip()

    start = parse_date(start_raw) or (today - timedelta(days=30))
    end = parse_date(end_raw) or today
    if end < start:
        start, end = end, start

    # Build filters
    tx_base_filter = Q(status__in=[TransactionStatus.PAID, TransactionStatus.COMPLETED]) & Q(
        created_at__date__gte=start, created_at__date__lte=end
    )
    if category_slug:
        tx_base_filter &= Q(listing__category__slug=category_slug)

    # Revenue trends (daily)
    revenue_qs = (
        Transaction.objects.filter(tx_base_filter)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("amount_paid"))
        .order_by("day")
    )
    revenue_labels = [r["day"].strftime("%Y-%m-%d") for r in revenue_qs]
    revenue_data = [float(r["total"] or 0) for r in revenue_qs]

    # Top categories by total sales amount within range
    cat_qs = (
        Transaction.objects.filter(tx_base_filter)
        .values("listing__category__name")
        .annotate(total_sales=Sum("amount_paid"))
        .order_by("-total_sales")[:10]
    )
    categories_labels = [c["listing__category__name"] or "Uncategorized" for c in cat_qs]
    categories_data = [float(c["total_sales"] or 0) for c in cat_qs]

    # Active listings by category (global, not date-bound)
    active_cat_qs = (
        Listing.objects.filter(status=ListingStatus.ACTIVE)
        .values("category__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    active_cat_labels = [c["category__name"] or "Uncategorized" for c in active_cat_qs]
    active_cat_data = [int(c["count"] or 0) for c in active_cat_qs]

    # User growth by date joined within range
    User = get_user_model()
    user_qs = (
        User.objects.filter(date_joined__date__gte=start, date_joined__date__lte=end)
        .annotate(day=TruncDate("date_joined"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    user_labels = [u["day"].strftime("%Y-%m-%d") for u in user_qs]
    user_data = [int(u["count"] or 0) for u in user_qs]

    # Recent transactions list
    recent_qs = (
        Transaction.objects.filter(tx_base_filter)
        .select_related("listing", "buyer", "seller")
        .order_by("-created_at")[:10]
    )
    recent_transactions = [
        {
            "id": tx.id,
            "listing_title": tx.listing.title,
            "buyer": tx.buyer.username,
            "seller": tx.seller.username,
            "status": tx.status,
            "amount_paid": float(tx.amount_paid or 0),
            "created": tx.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for tx in recent_qs
    ]

    # KPI metrics (global)
    total_listings = Listing.objects.count()
    approved_listings = Listing.objects.filter(status__in=[ListingStatus.ACTIVE, ListingStatus.SOLD, ListingStatus.RESERVED]).count()
    rejected_listings = Listing.objects.filter(status=ListingStatus.REJECTED).count()
    User = get_user_model()
    active_users = User.objects.filter(is_active=True).count()
    transactions_completed = Transaction.objects.filter(status=TransactionStatus.COMPLETED).count()

    return JsonResponse(
        {
            "revenue_labels": revenue_labels,
            "revenue_data": revenue_data,
            "categories_labels": categories_labels,
            "categories_data": categories_data,
            "active_cat_labels": active_cat_labels,
            "active_cat_data": active_cat_data,
            "user_labels": user_labels,
            "user_data": user_data,
            "recent_transactions": recent_transactions,
            "kpi": {
                "total_listings": total_listings,
                "approved_listings": approved_listings,
                "rejected_listings": rejected_listings,
                "active_users": active_users,
                "transactions_completed": transactions_completed,
            },
        }
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "users"
        return ctx


class AdminNotificationsView(LoginRequiredMixin, MarketplaceAdminPermRequiredMixin, TemplateView):
    template_name = "marketplace/admin/admin_dashboard.html"
    required_perms = ["marketplace.can_broadcast_notifications"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "notifications"
        # Build recent broadcast history (deduplicated by title/body)
        recent = Notification.objects.filter(type=NotificationType.SYSTEM_BROADCAST).order_by("-created_at")[:200]
        seen_keys = set()
        history = []
        for n in recent:
            key = (n.title.strip(), (n.body or "").strip())
            if key in seen_keys:
                continue
            seen_keys.add(key)
            history.append({
                "title": n.title,
                "body": n.body or "",
                "created_at": n.created_at,
            })
            if len(history) >= 10:
                break
        ctx["recent_broadcasts"] = history
        return ctx

@method_decorator(ensure_csrf_cookie, name="dispatch")
class AdminReportsView(LoginRequiredMixin, MarketplaceAdminPermRequiredMixin, ListView):
    """Reports moderation tab listing open reports."""
    template_name = "marketplace/admin/admin_dashboard.html"
    context_object_name = "reports"
    required_perms = ["marketplace.can_moderate_reports"]

    def get_queryset(self):
        from .models import Report, ReportStatus
        return (
            Report.objects.filter(status=ReportStatus.OPEN)
            .select_related("listing", "reporter")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["active_tab"] = "reports"
        return ctx

    def render_to_response(self, context, **response_kwargs):
        # Support JSON output for AJAX table refresh
        if wants_json(self.request):
            reports = []
            for r in context.get("reports", []):
                reports.append({
                    "id": r.id,
                    "type": "Listing",
                    "target": f"Listing #{r.listing_id}",
                    "submitted": r.created_at.strftime("%Y-%m-%d %H:%M"),
                })
            return JsonResponse({
                "status": "ok",
                "count": len(reports),
                "reports": reports,
            })
        return super().render_to_response(context, **response_kwargs)


# -----------------------------
# Marketplace Admin actions
# -----------------------------
from .mixins import marketplace_admin_required

@login_required
@marketplace_admin_required(required_permission="marketplace.can_approve_listing")
@require_POST
@csrf_protect
def admin_approve_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    listing.status = ListingStatus.ACTIVE
    listing.approved_by = request.user
    listing.approved_at = timezone.now()
    listing.rejected_reason = ""
    listing.save(update_fields=["status", "approved_by", "approved_at", "rejected_reason", "updated_at"])
    django_messages.success(request, "Listing approved and is now live.")
    if wants_json(request):
        return json_ok("Listing approved", data={"listing_id": listing.id, "status": listing.status})
    return redirect("marketplace_admin:listings")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_reject_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    if not request.user.has_perm("marketplace.can_approve_listing"):
        if wants_json(request):
            return json_error("Missing permission: can_approve_listing", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: can_approve_listing"}, status=403)
    reason = sanitize_text((request.POST.get("reason") or "").strip(), max_len=500)
    reason_code = (request.POST.get("reason_code") or "").strip()
    listing.status = ListingStatus.REJECTED
    listing.rejected_reason = reason
    listing.rejected_reason_code = reason_code
    listing.rejected_by = request.user
    listing.rejected_at = timezone.now()
    listing.approved_by = None
    listing.approved_at = None
    listing.save(update_fields=[
        "status",
        "rejected_reason",
        "rejected_reason_code",
        "rejected_by",
        "rejected_at",
        "approved_by",
        "approved_at",
        "updated_at",
    ])
    # Notify seller (in-app)
    _notify(
        user=listing.seller,
        notif_type=NotificationType.STATUS_CHANGED,
        request_obj=None,
        listing=listing,
        message_text=(f"Listing '{listing.title}' was rejected. Reason: {reason}" if reason else f"Listing '{listing.title}' was rejected."),
        send_email=True,
    )
    django_messages.success(request, "Listing rejected and seller notified.")
    if wants_json(request):
        return json_ok("Listing rejected", data={"listing_id": listing.id, "status": listing.status})
    return redirect("marketplace_admin:listings")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_toggle_user_active(request, user_id):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not request.user.has_perm("accounts.change_user"):
        if wants_json(request):
            return json_error("Missing permission: change_user", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: change_user"}, status=403)
    target = get_object_or_404(User, pk=user_id)
    target.is_active = not bool(target.is_active)
    target.save(update_fields=["is_active", "updated_at"] if hasattr(target, "updated_at") else ["is_active"])
    # Return JSON for AJAX; otherwise redirect back to Users tab
    if wants_json(request):
        return json_ok(
            "User active status updated",
            data={"user_id": target.id, "is_active": bool(target.is_active)},
        )
    return redirect("marketplace_admin:users")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_close_report(request, report_id):
    if not request.user.has_perm("marketplace.can_moderate_reports"):
        if wants_json(request):
            return json_error("Missing permission: can_moderate_reports", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: can_moderate_reports"}, status=403)
    report = get_object_or_404(Report, pk=report_id)
    report.status = ReportStatus.CLOSED
    report.save(update_fields=["status", "updated_at"])
    django_messages.success(request, "Report closed.")
    if wants_json(request):
        return json_ok("Report closed", data={"report_id": report.id, "status": report.status})
    return redirect("marketplace_admin:reports")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_approve_refund(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)
    if not request.user.has_perm("marketplace.can_manage_transactions"):
        if wants_json(request):
            return json_error("Missing permission: can_manage_transactions", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: can_manage_transactions"}, status=403)
    tx.status = TransactionStatus.CANCELED
    tx.save(update_fields=["status", "updated_at"])
    TransactionLog.objects.create(request=tx.purchase_request, actor=request.user, action=LogAction.DISPUTE_RESOLVED, note="Refund approved by Marketplace Admin")
    django_messages.success(request, "Refund approved and transaction canceled.")
    return redirect("marketplace_admin:analytics")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_cancel_transaction(request, tx_id):
    tx = get_object_or_404(Transaction, pk=tx_id)
    if not request.user.has_perm("marketplace.can_manage_transactions"):
        if wants_json(request):
            return json_error("Missing permission: can_manage_transactions", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: can_manage_transactions"}, status=403)
    tx.status = TransactionStatus.CANCELED
    tx.save(update_fields=["status", "updated_at"])
    TransactionLog.objects.create(request=tx.purchase_request, actor=request.user, action=LogAction.REQUEST_CANCELED, note="Transaction canceled by Marketplace Admin")
    django_messages.success(request, "Transaction canceled.")
    return redirect("marketplace_admin:analytics")


@login_required
@user_passes_test(_is_marketplace_admin)
@require_POST
@csrf_protect
def admin_broadcast_notification(request):
    if not request.user.has_perm("marketplace.can_broadcast_notifications"):
        # JSON for AJAX, otherwise render 403 template
        if wants_json(request):
            return json_error("Missing permission: can_broadcast_notifications", status=403)
        from django.shortcuts import render
        return render(request, "marketplace/403.html", {"message": "Missing permission: can_broadcast_notifications"}, status=403)
    title = sanitize_text((request.POST.get("title") or "").strip(), max_len=200)
    body = sanitize_text((request.POST.get("body") or "").strip(), max_len=2000)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(is_active=True)
    created = 0
    for u in users:
        # Create broadcast notifications directly to allow custom title/body
        notif = Notification.objects.create(
            user=u,
            type=NotificationType.SYSTEM_BROADCAST,
            title=title or "Announcement",
            body=body,
            unread=True,
        )
        # Attempt to send email asynchronously
        try:
            from .tasks import send_notification_email
            send_notification_email.delay(
                notif_id=notif.id,
                user_id=u.id,
                notif_type=str(NotificationType.SYSTEM_BROADCAST),
                title=title or "Announcement",
                message_text=body,
            )
        except Exception:
            pass
        created += 1
    if wants_json(request):
        return json_ok("Notification sent", data={"count": created})
    django_messages.success(request, f"Broadcast sent to {created} active users.")
    return redirect("marketplace_admin:notifications")
