from django.shortcuts import render
from django.db.models import Q
from django.views.generic import ListView, DetailView
from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation

from .models import Listing, Category
from .models import Transaction, Report, ListingStatus, TransactionStatus, ReportStatus
from .forms import ListingForm

# Configuration: threshold for auto-flagging a listing based on open reports
REPORT_THRESHOLD = 3

# New imports for JSON API endpoints
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator

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
          - price_min/price_max: decimal values, non-negative; if both provided and min > max, swap gracefully
        - Sorting:
          - sort: one of ["newest", "price_asc", "price_desc"]; defaults to "newest"
        """
        # Base queryset: active listings with related category and seller for efficiency
        qs = (
            Listing.objects.filter(status="active")
            .select_related("category", "seller")
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
        """Add current filters and categories to context for the template UI.
        Includes: q, category_slug, sort, price_min, price_max.
        """
        context = super().get_context_data(**kwargs)
        # Preserve the raw values the user provided; if invalid, they may be blank in UI
        context["q"] = self.request.GET.get("q", "")
        context["category_slug"] = self.request.GET.get("category", "")
        context["sort"] = self.request.GET.get("sort", "newest")
        context["price_min"] = self.request.GET.get("price_min", "")
        context["price_max"] = self.request.GET.get("price_max", "")
        context["categories"] = Category.objects.only("id", "name", "slug").order_by("name")
        return context


class ListingDetailView(DetailView):
    """Show a single listing detail page."""
    model = Listing
    template_name = "marketplace/listing_detail.html"
    context_object_name = "listing"


class ListingCreateView(LoginRequiredMixin, CreateView):
    """Create a new listing. Requires authentication.

    Validations are handled by ListingForm. The listing seller is set to the
    authenticated user. On success, redirect to the listing detail page.
    """

    model = Listing
    form_class = ListingForm
    template_name = "marketplace/create_listing.html"

    def form_valid(self, form):
        """Bind the listing to the currently authenticated user before saving."""
        listing = form.save(commit=False)
        listing.seller = self.request.user
        listing.save()
        self.object = listing
        return super().form_valid(form)

    def get_success_url(self):
        """Redirect to the newly created listing's detail page."""
        return reverse("marketplace:listing_detail", kwargs={"pk": self.object.pk})


# Render the marketplace home wireframe
# Updated to use the new catalog template for browsing
def marketplace_home(request):
    return render(request, "marketplace/catalog.html")

# Render a single listing detail wireframe
# listing_id: placeholder identifier for navigating to a specific listing page
# Updated to use the consolidated detail template
def listing_detail(request, listing_id):
    return render(request, "marketplace/detail.html", {"listing_id": listing_id})

# Render the create listing wireframe
# Updated to use the new listing submission template
@login_required
def create_listing(request):
    """Render the create listing page. Requires user login."""
    return render(request, "marketplace/new_listing.html")

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
        },
    )

# Render the transactions wireframe (placeholder template)
# Kept as a separate page to show person-to-person transactions overview
@login_required
@ensure_csrf_cookie
def transactions(request):
    return render(request, "marketplace/transactions.html")

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
        return ctx

# Render the admin review wireframe
# Updated to use the admin dashboard template
# def admin_review(request):
#     return render(request, "marketplace/admin_dashboard.html")


# -----------------------------
# JSON Messaging API Endpoints
# -----------------------------

from .models import MessageThread, Message  # placed here to avoid circular import warnings


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
        thread = MessageThread.objects.select_related("buyer", "seller").get(pk=thread_id)
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

    return JsonResponse({
        "thread_id": thread.id,
        "count": len(messages_list),
        "messages": messages_list,
        "server_time": timezone.now().isoformat(),
    })


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

    content = (payload.get("content") or "").strip()
    if not content:
        return HttpResponseBadRequest("Message content is required")
    if len(content) > 4000:
        content = content[:4000]

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
        defaults={"status": TransactionStatus.CONFIRMED}
    )
    if txn.status != TransactionStatus.CONFIRMED:
        txn.status = TransactionStatus.CONFIRMED
        txn.save(update_fields=["status"])

    # Decrement stock and move listing to 'pending' state
    listing.quantity = max(0, listing.quantity - 1)
    listing.status = ListingStatus.PENDING
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
        }
    })

@require_http_methods(["POST"])  # Sell one unit of a listing
def api_listing_sell(request, listing_id):
    """Mark a listing as sold by completing a Transaction and updating stock.

    Requires authentication. Listing must be in 'pending'. Uses request.user as buyer identity.
    After sale: if quantity hits 0 -> status 'sold', else -> back to 'active'.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=403)
    # Fetch listing and proceed
    try:
        listing = Listing.objects.select_related("seller").get(pk=listing_id)
    except Listing.DoesNotExist:
        return HttpResponseBadRequest("Listing not found")

    if listing.status != ListingStatus.PENDING:
        return HttpResponseBadRequest("Listing not pending")

    if listing.quantity <= 0:
        return HttpResponseBadRequest("Out of stock")

    buyer = request.user
    seller = listing.seller

    txn, _ = Transaction.objects.get_or_create(
        listing=listing,
        buyer=buyer,
        seller=seller,
        defaults={"status": TransactionStatus.COMPLETED}
    )
    if txn.status != TransactionStatus.COMPLETED:
        txn.status = TransactionStatus.COMPLETED
        txn.save(update_fields=["status"])

    listing.quantity = max(0, listing.quantity - 1)
    if listing.quantity == 0:
        listing.status = ListingStatus.SOLD
        listing.save(update_fields=["quantity", "status"])
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
        }
    })

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

    if listing.status != ListingStatus.SOLD:
        return HttpResponseBadRequest("Listing not sold")

    buyer = request.user
    seller = listing.seller

    txn, _ = Transaction.objects.get_or_create(
        listing=listing,
        buyer=buyer,
        seller=seller,
        defaults={"status": TransactionStatus.COMPLETED}
    )
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
            "buyer_id": buyer.id,
            "seller_id": seller.id,
        }
    })

# -----------------------------
# Reporting Endpoint
# -----------------------------

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

    reason = (payload.get("reason") or "").strip()
    details = (payload.get("details") or "").strip()
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
