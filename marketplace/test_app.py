"""
Marketplace unit tests covering core logic:
- Listing creation & validation
- Catalog filters
- Messaging thread creation (authenticated user)
- Transaction: marking a listing sold & decrementing quantity
- Reporting: report creation & auto-flagging to pending

Authentication-dependent behaviors now require login; tests log in users accordingly.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from .forms import ListingForm
from .models import (
    Category,
    Listing,
    ListingStatus,
    PurchaseRequest,
    PurchaseRequestStatus,
    MessageThread,
    Message,
    RequestMessage,
    Transaction,
    TransactionStatus,
    Report,
    ReportStatus,
    SellerRating,
    TransactionLog,
    LogAction,
)
import json
import unittest
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile


class TestOfflinePaymentFlow(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_pay", email="seller_pay@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_pay", email="buyer_pay@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Premium Kibble",
            description="High-protein",
            price=Decimal("25.00"),
            quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def test_full_payment_flow_reserve_sell_complete(self):
        # Buyer reserves the listing
        self.assertTrue(self.client.login(username="buyer_pay", password="pass"))
        url_reserve = reverse("marketplace:api_listing_reserve", args=[self.listing.id])
        resp_r = self.client.post(url_reserve, content_type="application/json")
        self.assertEqual(resp_r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.PENDING)
        txn = Transaction.objects.filter(listing=self.listing).order_by("-created_at").first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.status, TransactionStatus.AWAITING_PAYMENT)

        # Seller records payment (amount <= price)
        self.client.logout(); self.assertTrue(self.client.login(username="seller_pay", password="pass"))
        url_sell = reverse("marketplace:api_listing_sell", args=[self.listing.id])
        proof = SimpleUploadedFile("receipt.txt", b"paid")
        resp_s = self.client.post(url_sell, {
            "payment_method": "cash",
            "amount_paid": "20.00",
            "payment_proof": proof,
        })
        self.assertEqual(resp_s.status_code, 200)
        self.listing.refresh_from_db()
        txn.refresh_from_db()
        self.assertEqual(txn.status, TransactionStatus.PAID)
        self.assertEqual(txn.payment_method, "cash")
        self.assertEqual(txn.amount_paid, Decimal("20.00"))
        self.assertTrue(bool(txn.payment_proof))

        # Buyer completes the transaction
        self.client.logout(); self.assertTrue(self.client.login(username="buyer_pay", password="pass"))
        url_complete = reverse("marketplace:api_listing_complete", args=[self.listing.id])
        resp_c = self.client.post(url_complete, content_type="application/json")
        self.assertEqual(resp_c.status_code, 200)
        txn.refresh_from_db()
        self.assertEqual(txn.status, TransactionStatus.COMPLETED)

    def test_amount_validation_not_exceed_price(self):
        # Reserve first
        self.assertTrue(self.client.login(username="buyer_pay", password="pass"))
        url_reserve = reverse("marketplace:api_listing_reserve", args=[self.listing.id])
        self.client.post(url_reserve, content_type="application/json")
        self.client.logout(); self.assertTrue(self.client.login(username="seller_pay", password="pass"))
        # Attempt to record payment exceeding price
        url_sell = reverse("marketplace:api_listing_sell", args=[self.listing.id])
        resp = self.client.post(url_sell, {
            "payment_method": "cash",
            "amount_paid": "30.00",
        })
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content.decode("utf-8"))
        self.assertIn("field_errors", data)
        self.assertIn("amount_paid", data["field_errors"])

    def test_sell_requires_seller_and_awaiting_transaction(self):
        # Seller cannot sell without prior reserve
        self.assertTrue(self.client.login(username="seller_pay", password="pass"))
        url_sell = reverse("marketplace:api_listing_sell", args=[self.listing.id])
        resp = self.client.post(url_sell, {"payment_method": "cash", "amount_paid": "10.00"})
        self.assertEqual(resp.status_code, 400)
        # Buyer cannot call sell (only seller)
        self.client.logout(); self.assertTrue(self.client.login(username="buyer_pay", password="pass"))
        # First reserve to create txn
        self.client.post(reverse("marketplace:api_listing_reserve", args=[self.listing.id]), content_type="application/json")
        resp_b = self.client.post(url_sell, {"payment_method": "cash", "amount_paid": "10.00"})
        self.assertEqual(resp_b.status_code, 403)


class TestListingFormValidation(TestCase):
    """Unit tests for ListingForm field validations."""

    def test_price_must_be_positive(self):
        """Price must be greater than zero."""
        form = ListingForm(data={
            "title": "Test Item",
            "price": 0,
            "quantity": 1,
            "description": "desc",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_quantity_must_be_positive(self):
        """Quantity must be at least 1."""
        form = ListingForm(data={
            "title": "Test Item",
            "price": 10.00,
            "quantity": 0,
            "description": "desc",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("quantity", form.errors)

    def test_clean_main_image_rejects_large_file(self):
        """Image larger than 5MB should raise ValidationError."""
        class DummyFile:
            def __init__(self, size):
                self.size = size
        form = ListingForm()
        form.cleaned_data = {"main_image": DummyFile(size=5 * 1024 * 1024 + 1)}
        with self.assertRaises(ValidationError):
            form.clean_main_image()


class TestCatalogFilters(TestCase):
    """Integration tests for CatalogView filtering by status, query, and category."""

    def setUp(self):
        self.client = Client()
        self.cat_dog = Category.objects.create(name="Dog Supplies", slug="dog")
        self.cat_cat = Category.objects.create(name="Cat Supplies", slug="cat")
        User = get_user_model()
        seller = User.objects.create_user(username="seller", email="seller@example.com", password="pass")
        # Active listings
        self.l1 = Listing.objects.create(
            seller=seller, title="Dog Food", description="Good food", price=20, quantity=5,
            category=self.cat_dog, status=ListingStatus.ACTIVE,
        )
        self.l2 = Listing.objects.create(
            seller=seller, title="Cat Toy", description="Fun toy", price=10, quantity=3,
            category=self.cat_cat, status=ListingStatus.ACTIVE,
        )
        # Non-active listing should be excluded
        self.l3 = Listing.objects.create(
            seller=seller, title="Old Crate", description="", price=5, quantity=0,
            category=self.cat_dog, status=ListingStatus.ARCHIVED,
        )
        # Additional active listing for sorting/price range tests
        self.l4 = Listing.objects.create(
            seller=seller, title="Dog Bed", description="Comfy bed", price=30, quantity=2,
            category=self.cat_dog, status=ListingStatus.ACTIVE,
        )

    def test_home_shows_only_active_listings(self):
        """Root catalog route returns only active listings."""
        resp = self.client.get(reverse("marketplace:home"))
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        self.assertTrue(all(l.status == ListingStatus.ACTIVE for l in listings))
        self.assertIn(self.l1, listings)
        self.assertIn(self.l2, listings)
        self.assertNotIn(self.l3, listings)

    def test_query_filter_matches_title(self):
        """Query term filters by title/description (case-insensitive)."""
        url = reverse("marketplace:home") + "?q=Dog"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        self.assertIn(self.l1, listings)
        self.assertNotIn(self.l2, listings)

    def test_category_filter_matches_slug(self):
        """Category slug filters listings by category."""
        url = reverse("marketplace:home") + "?category=cat"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        self.assertIn(self.l2, listings)
        self.assertNotIn(self.l1, listings)

    def test_sort_by_price_ascending(self):
        url = reverse("marketplace:home")
        resp = self.client.get(url + "?sort=price_asc")
        self.assertEqual(resp.status_code, 200)
        prices = [l.price for l in resp.context["listings"]]
        # Should be ascending by price: 10, 20, 30 (only active listings)
        self.assertEqual(prices, sorted(prices))

    def test_sort_by_price_descending(self):
        url = reverse("marketplace:home")
        resp = self.client.get(url + "?sort=price_desc")
        self.assertEqual(resp.status_code, 200)
        prices = [l.price for l in resp.context["listings"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_price_min_filter(self):
        url = reverse("marketplace:home")
        resp = self.client.get(url, {"price_min": "15"})
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        self.assertTrue(all(l.price >= 15 for l in listings))
        # Should include 20 and 30, exclude 10
        self.assertIn(self.l1, listings)
        self.assertIn(self.l4, listings)


class TestManualPurchaseInitiationRules(TestCase):
    """Step 1: Buyer initiation rules for manual purchase requests."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_a", email="seller_a@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_a", email="buyer_a@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller, title="Kibble", description="Tasty", price=9.99, quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def test_self_purchase_forbidden(self):
        self.assertTrue(self.client.login(username="seller_a", password="pass"))
        url = reverse("marketplace:request_purchase", kwargs={"pk": self.listing.id})
        resp = self.client.post(url, {"message": "Please"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(PurchaseRequest.objects.count(), 0)

    def test_duplicate_pending_redirects_to_existing(self):
        self.assertTrue(self.client.login(username="buyer_a", password="pass"))
        url = reverse("marketplace:request_purchase", kwargs={"pk": self.listing.id})
        resp1 = self.client.post(url, {"message": "hi"})
        self.assertEqual(resp1.status_code, 302)
        self.assertEqual(PurchaseRequest.objects.count(), 1)
        existing = PurchaseRequest.objects.get()
        resp2 = self.client.post(url, {"message": "again"})
        self.assertEqual(resp2.status_code, 302)
        # Should redirect to existing request detail
        self.assertIn(reverse("marketplace:request_detail", kwargs={"pk": existing.id}), resp2.url)
        self.assertEqual(PurchaseRequest.objects.count(), 1)

    def test_invalid_listing_state_bad_request(self):
        self.assertTrue(self.client.login(username="buyer_a", password="pass"))
        self.listing.status = ListingStatus.SOLD
        self.listing.save(update_fields=["status"])
        url = reverse("marketplace:request_purchase", kwargs={"pk": self.listing.id})
        resp = self.client.post(url, {"message": "pls"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PurchaseRequest.objects.count(), 0)

    def test_out_of_stock_bad_request(self):
        self.assertTrue(self.client.login(username="buyer_a", password="pass"))
        self.listing.quantity = 0
        self.listing.save(update_fields=["quantity"])
        url = reverse("marketplace:request_purchase", kwargs={"pk": self.listing.id})
        resp = self.client.post(url, {"message": "pls"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PurchaseRequest.objects.count(), 0)

    def test_listing_detail_hides_form_for_seller(self):
        self.assertTrue(self.client.login(username="seller_a", password="pass"))
        url = reverse("marketplace:listing_detail", kwargs={"pk": self.listing.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"Request to Purchase", resp.content)

    def test_listing_detail_shows_existing_pending_link(self):
        # Create pending request
        PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )
        self.assertTrue(self.client.login(username="buyer_a", password="pass"))
        url = reverse("marketplace:listing_detail", kwargs={"pk": self.listing.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"View your pending request", resp.content)
        # Link should be present when a pending request exists for buyer
        # No catalog filter assertions here; only UI link presence

    # End of Step 1 listing detail tests


class TestCancelActions(TestCase):
    """Tests for buyer/seller cancellation of purchase requests."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_c", email="seller_c@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_c", email="buyer_c@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller, title="Chew Toy", description="Durable", price=12.00, quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def _make_request(self, status=PurchaseRequestStatus.PENDING):
        return PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=status,
        )

    def test_buyer_cancel_pending(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        self.assertTrue(self.client.login(username="buyer_c", password="pass"))
        url = reverse("marketplace:buyer_cancel_request", kwargs={"request_id": pr.id})
        resp = self.client.post(url, {"reason": "changed mind"})
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.CANCELED)
        self.assertEqual(pr.canceled_reason, "changed mind")

    def test_seller_cancel_negotiating(self):
        pr = self._make_request(PurchaseRequestStatus.NEGOTIATING)
        self.assertTrue(self.client.login(username="seller_c", password="pass"))
        url = reverse("marketplace:seller_cancel_request", kwargs={"request_id": pr.id})
        resp = self.client.post(url, {"reason": "cannot fulfill"})
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.CANCELED)
        self.assertEqual(pr.canceled_reason, "cannot fulfill")

    def test_cancel_forbidden_for_others(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        # Another user
        User = get_user_model()
        other = User.objects.create_user(username="other_c", email="other@example.com", password="pass")
        self.assertTrue(self.client.login(username="other_c", password="pass"))
        buyer_url = reverse("marketplace:buyer_cancel_request", kwargs={"request_id": pr.id})
        resp1 = self.client.post(buyer_url, {"reason": "nope"})
        self.assertEqual(resp1.status_code, 403)
        seller_url = reverse("marketplace:seller_cancel_request", kwargs={"request_id": pr.id})
        resp2 = self.client.post(seller_url, {"reason": "nope"})
        self.assertEqual(resp2.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.PENDING)

    def test_cancel_bad_status(self):
        pr = self._make_request(PurchaseRequestStatus.ACCEPTED)
        # Buyer cannot cancel accepted
        self.assertTrue(self.client.login(username="buyer_c", password="pass"))
        buyer_url = reverse("marketplace:buyer_cancel_request", kwargs={"request_id": pr.id})
        resp1 = self.client.post(buyer_url, {"reason": "late"})
        self.assertEqual(resp1.status_code, 400)
        # Seller cannot cancel accepted
        self.assertTrue(self.client.login(username="seller_c", password="pass"))
        seller_url = reverse("marketplace:seller_cancel_request", kwargs={"request_id": pr.id})
        resp2 = self.client.post(seller_url, {"reason": "late"})
        self.assertEqual(resp2.status_code, 400)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.ACCEPTED)


class TestCompletionActions(TestCase):
    """Tests for completion permissions and state transitions."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_x", email="seller_x@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_x", email="buyer_x@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller, title="Ball", description="Bouncy", price=5.00, quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def _make_request(self, status=PurchaseRequestStatus.PENDING):
        return PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=status,
        )

    def test_buyer_complete_after_accept(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        # Seller accepts
        self.assertTrue(self.client.login(username="seller_x", password="pass"))
        accept_url = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr.id})
        r1 = self.client.post(accept_url)
        self.assertEqual(r1.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.ACCEPTED)
        self.assertIsNotNone(pr.transaction)
        self.assertEqual(pr.transaction.status, TransactionStatus.CONFIRMED)
        # Buyer completes
        self.assertTrue(self.client.login(username="buyer_x", password="pass"))
        complete_url = reverse("marketplace:mark_request_completed", kwargs={"request_id": pr.id})
        r2 = self.client.post(complete_url, {"note": "met up and exchanged"})
        self.assertEqual(r2.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.COMPLETED)
        self.assertIsNotNone(pr.completed_at)
        pr.transaction.refresh_from_db()
        self.assertEqual(pr.transaction.status, TransactionStatus.COMPLETED)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.SOLD)

    def test_complete_requires_buyer_only(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        # Accept first
        self.assertTrue(self.client.login(username="seller_x", password="pass"))
        accept_url = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr.id})
        self.client.post(accept_url)
        pr.refresh_from_db()
        # Seller attempts to complete
        complete_url = reverse("marketplace:mark_request_completed", kwargs={"request_id": pr.id})
        r = self.client.post(complete_url)
        self.assertEqual(r.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.ACCEPTED)

    def test_complete_requires_accepted_status(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        self.assertTrue(self.client.login(username="buyer_x", password="pass"))
        complete_url = reverse("marketplace:mark_request_completed", kwargs={"request_id": pr.id})
        r = self.client.post(complete_url)
        self.assertEqual(r.status_code, 400)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.PENDING)

    def test_complete_requires_confirmed_transaction(self):
        # Accepted but no transaction
        pr = self._make_request(PurchaseRequestStatus.ACCEPTED)
        self.assertTrue(self.client.login(username="buyer_x", password="pass"))
        complete_url = reverse("marketplace:mark_request_completed", kwargs={"request_id": pr.id})
        r = self.client.post(complete_url)
        self.assertEqual(r.status_code, 400)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.ACCEPTED)


@unittest.skip("Skipping auth-dependent view test for anonymous listing creation")
class TestListingCreateAnonymous(TestCase):
    """CreateView should allow anonymous submission and assign a guest seller."""

    def setUp(self):
        self.client = Client()

    def test_anonymous_create_listing_assigns_guest_seller(self):
        """Posting to listing_create without login creates listing with 'guest' seller."""
        url = reverse("marketplace:listing_create")
        data = {
            "title": "My New Product",
            "price": 19.99,
            "quantity": 3,
            "description": "A nice thing",
        }
        resp = self.client.post(url, data=data)
        # Expect a redirect to detail page
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Listing.objects.filter(title="My New Product").exists())
        listing = Listing.objects.get(title="My New Product")
        self.assertEqual(listing.seller.username, "guest")


class TestMessagingThreadAuthenticated(TestCase):
    """Start or get a message thread with a logged-in buyer."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.buyer = User.objects.create_user(
            username="buyer", email="buyer@example.com", password="pass1234"
        )
        self.seller = User.objects.create_user(
            username="seller", email="seller@example.com", password="pass1234"
        )
        self.listing = Listing.objects.create(
            seller=self.seller, title="Test Listing", description="Desc", price=10.0,
            quantity=1, status=ListingStatus.ACTIVE,
        )

    def test_start_or_get_thread_requires_auth_and_uses_request_user(self):
        url = reverse("marketplace:api_start_or_get_thread")
        # Unauthenticated returns 403 JSON
        resp_anon = self.client.post(url, data=json.dumps({"listing_id": self.listing.id}), content_type="application/json")
        self.assertEqual(resp_anon.status_code, 403)
        # Login and try again
        self.client.login(username="buyer", password="pass1234")
        resp = self.client.post(url, data=json.dumps({"listing_id": self.listing.id}), content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("thread", data)
        self.assertEqual(data["thread"]["listing_id"], self.listing.id)
        self.assertEqual(data["thread"]["buyer_username"], "buyer")
        thread_id = data["thread"]["id"]
        self.assertTrue(MessageThread.objects.filter(pk=thread_id).exists())


class TestTransactionAndReportEndpoints(TestCase):
    """Tests for selling endpoints and reporting auto-flagging behavior."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(
            username="seller2", email="seller2@example.com", password="pass"
        )
        # Create a buyer account used for authenticated requests in tests
        self.buyer = User.objects.create_user(
            username="buyer2", email="buyer2@example.com", password="pass"
        )
        self.listing = Listing.objects.create(
            seller=self.seller, title="Bulk Kibble", description="Desc", price=30.0,
            quantity=2, status=ListingStatus.ACTIVE,
        )

    def test_sell_decrements_quantity_and_sets_sold_when_zero(self):
        sell_url = reverse("marketplace:api_listing_sell", kwargs={"listing_id": self.listing.id})
        # Unauthenticated -> 403
        resp_anon = self.client.post(sell_url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(resp_anon.status_code, 403)
        # Authenticated -> success
        self.client.login(username="buyer2", password="pass")
        # First sell: quantity 2 -> 1, status stays ACTIVE
        resp1 = self.client.post(sell_url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(resp1.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 1)
        self.assertEqual(self.listing.status, ListingStatus.ACTIVE)
        # Second sell: quantity 1 -> 0, status becomes SOLD
        resp2 = self.client.post(sell_url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(resp2.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)
        self.assertEqual(self.listing.status, ListingStatus.SOLD)

    def test_report_creation_and_auto_flagging_requires_auth(self):
        report_url = reverse("marketplace:api_listing_report", kwargs={"listing_id": self.listing.id})
        # Unauthenticated -> 403
        r0 = self.client.post(report_url, data=json.dumps({"reason": "spam"}), content_type="application/json")
        self.assertEqual(r0.status_code, 403)
        # Authenticated submissions below threshold
        self.client.login(username="buyer2", password="pass")
        r1 = self.client.post(report_url, data=json.dumps({"reason": "spam"}), content_type="application/json")
        self.assertEqual(r1.status_code, 200)
        r2 = self.client.post(report_url, data=json.dumps({"reason": "fake"}), content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.ACTIVE)
        # Threshold report triggers PENDING
        r3 = self.client.post(report_url, data=json.dumps({"reason": "scam"}), content_type="application/json")
        self.assertEqual(r3.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.PENDING)
        self.assertEqual(Report.objects.filter(listing=self.listing, status=ReportStatus.OPEN).count(), 3)


class TestListingModelCreation(TestCase):
    """Model-level creation tests that avoid auth-dependent view logic."""

    def setUp(self):
        User = get_user_model()
        self.seller = User.objects.create_user(
            username="seller_model", email="seller_model@example.com", password="pass"
        )
        self.category = Category.objects.create(name="General", slug="general")

    def test_create_listing_with_valid_fields(self):
        """Creating a listing via ORM assigns seller, category, and persists."""
        listing = Listing.objects.create(
            seller=self.seller,
            title="ORM Item",
            description="Desc",
            price=12.5,
            quantity=4,
            category=self.category,
            status=ListingStatus.ACTIVE,
        )
        self.assertTrue(Listing.objects.filter(pk=listing.pk).exists())
        self.assertEqual(listing.seller, self.seller)
        self.assertEqual(listing.category, self.category)
        self.assertEqual(listing.status, ListingStatus.ACTIVE)
        self.assertEqual(listing.quantity, 4)


class TestProtectedEndpointsAuth(TestCase):
    """Ensure protected HTML endpoints redirect to login and APIs return 403 when unauthenticated."""

    def setUp(self):
        self.client = Client()

    def test_html_views_redirect_to_login(self):
        # CBV create listing
        resp1 = self.client.get(reverse("marketplace:listing_create"))
        self.assertEqual(resp1.status_code, 302)
        self.assertIn(reverse("login"), resp1.headers.get("Location", ""))
        # FBV create listing (legacy/new-listing wireframe)
        resp2 = self.client.get(reverse("marketplace:create_listing"))
        self.assertEqual(resp2.status_code, 302)
        self.assertIn(reverse("login"), resp2.headers.get("Location", ""))
        # Messages page
        resp3 = self.client.get(reverse("marketplace:messages"))
        self.assertEqual(resp3.status_code, 302)
        self.assertIn(reverse("login"), resp3.headers.get("Location", ""))
        # Transactions page
        resp4 = self.client.get(reverse("marketplace:transactions"))
        self.assertEqual(resp4.status_code, 302)
        self.assertIn(reverse("login"), resp4.headers.get("Location", ""))

    def test_api_endpoints_forbid_unauthenticated(self):
        # Messaging JSON APIs
        start_url = reverse("marketplace:api_start_or_get_thread")
        r1 = self.client.post(start_url, data=json.dumps({"listing_id": 1}), content_type="application/json")
        self.assertEqual(r1.status_code, 403)

        fetch_url = reverse("marketplace:api_fetch_messages", kwargs={"thread_id": 1})
        r2 = self.client.get(fetch_url)
        self.assertEqual(r2.status_code, 403)

        post_url = reverse("marketplace:api_post_message", kwargs={"thread_id": 1})
        r3 = self.client.post(post_url, data=json.dumps({"content": "hi"}), content_type="application/json")
        self.assertEqual(r3.status_code, 403)

        # Transaction APIs
        reserve_url = reverse("marketplace:api_listing_reserve", kwargs={"listing_id": 1})
        sell_url = reverse("marketplace:api_listing_sell", kwargs={"listing_id": 1})
        complete_url = reverse("marketplace:api_listing_complete", kwargs={"listing_id": 1})
        r4 = self.client.post(reserve_url)
        r5 = self.client.post(sell_url)
        r6 = self.client.post(complete_url)
        self.assertEqual(r4.status_code, 403)
        self.assertEqual(r5.status_code, 403)
        self.assertEqual(r6.status_code, 403)


class TestAuthenticatedMarketplaceFlows(TestCase):
    """Authenticated users can create listings, message sellers, and checkout via APIs."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_u", email="seller_u@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_u", email="buyer_u@example.com", password="pass")
        self.category = Category.objects.create(name="General", slug="general")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Test Product",
            description="Nice",
            price=9.99,
            quantity=1,
            category=self.category,
            status=ListingStatus.ACTIVE,
        )

    def test_authenticated_can_create_listing(self):
        self.assertTrue(self.client.login(username="buyer_u", password="pass"))
        url = reverse("marketplace:listing_create")
        data = {
            "title": "New Listing",
            "price": 12.50,
            "quantity": 2,
            "description": "A description",
            # category optional; omit to use null
        }
        resp = self.client.post(url, data=data)
        self.assertEqual(resp.status_code, 302)
        # Follow redirect to detail
        follow = self.client.get(resp.headers.get("Location", ""))
        self.assertEqual(follow.status_code, 200)
        # Ensure listing exists and belongs to buyer
        created = Listing.objects.filter(title="New Listing", seller=self.buyer).first()
        self.assertIsNotNone(created)

    def test_messaging_thread_and_send_message(self):
        self.assertTrue(self.client.login(username="buyer_u", password="pass"))
        # Start or get thread
        start_url = reverse("marketplace:api_start_or_get_thread")
        r1 = self.client.post(start_url, data=json.dumps({"listing_id": self.listing.id}), content_type="application/json")
        self.assertEqual(r1.status_code, 200)
        payload = json.loads(r1.content.decode("utf-8"))
        thread_id = payload["thread"]["id"]
        # Send a message
        post_url = reverse("marketplace:api_post_message", kwargs={"thread_id": thread_id})
        r2 = self.client.post(post_url, data=json.dumps({"content": "Hello!"}), content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        # Fetch messages
        fetch_url = reverse("marketplace:api_fetch_messages", kwargs={"thread_id": thread_id})
        r3 = self.client.get(fetch_url)
        self.assertEqual(r3.status_code, 200)
        msgs = json.loads(r3.content.decode("utf-8"))
        self.assertGreaterEqual(msgs.get("count", 0), 1)

    def test_checkout_sell_endpoint(self):
        self.assertTrue(self.client.login(username="buyer_u", password="pass"))
        sell_url = reverse("marketplace:api_listing_sell", kwargs={"listing_id": self.listing.id})
        r = self.client.post(sell_url)
        self.assertEqual(r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.quantity, 0)
        self.assertEqual(self.listing.status, ListingStatus.SOLD)
        # Transaction exists for buyer
        txn_exists = Transaction.objects.filter(listing=self.listing, buyer=self.buyer, seller=self.seller).exists()
        self.assertTrue(txn_exists)


class MarketplaceDRFEndpointsTests(TestCase):
    """Minimal tests for marketplace DRF endpoints: threads/start, threads/{id}/send, listings/{id}/reserve."""

    def setUp(self):
        User = get_user_model()
        self.client = APIClient()
        self.buyer = User.objects.create_user(username="buyer_drf", email="buyer_drf@example.com", password="pass1234")
        self.seller = User.objects.create_user(username="seller_drf", email="seller_drf@example.com", password="pass1234")
        self.category = Category.objects.create(name="Food", slug="food")
        self.listing = Listing.objects.create(
            seller=self.seller,
            category=self.category,
            title="Kibble Pack",
            description="10kg dog food",
            price="19.99",
            quantity=2,
            status=ListingStatus.ACTIVE,
        )

    def test_start_thread_via_drf_and_send_message(self):
        # Login buyer
        self.client.login(username="buyer_drf", password="pass1234")
        # Start thread via DRF
        url_start = reverse("marketplace:marketplace-api-thread-start") if False else \
            "/marketplace/api/threads/start/"
        resp = self.client.post(url_start, data={"listing_id": self.listing.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        thread_id = resp.json()["thread"]["id"]
        # Send message via DRF action
        url_send = f"/marketplace/api/threads/{thread_id}/send/"
        resp2 = self.client.post(url_send, data={"content": "Hello via DRF"}, format="json")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertIn("message", resp2.json())

    def test_reserve_listing_via_drf_action(self):
        # Login buyer
        self.client.login(username="buyer_drf", password="pass1234")
        url_reserve = f"/marketplace/api/listings/{self.listing.id}/reserve/"
        resp = self.client.post(url_reserve, data={}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["listing"]["id"], self.listing.id)
        self.assertIn("transaction", body)


class TestRequestMessagingActions(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.buyer = User.objects.create_user(username="msg_buyer", email="msg_buyer@example.com", password="pass")
        self.seller = User.objects.create_user(username="msg_seller", email="msg_seller@example.com", password="pass")
        self.intruder = User.objects.create_user(username="msg_intruder", email="msg_intruder@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Msg Item",
            description="",
            price=10,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )
        self.pr = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )

    def test_buyer_can_post_message(self):
        self.assertTrue(self.client.login(username="msg_buyer", password="pass"))
        url = reverse("marketplace:request_message_post", args=[self.pr.id])
        r = self.client.post(url, data={"content": "Hello seller"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(RequestMessage.objects.filter(request=self.pr, author=self.buyer, content__icontains="Hello").exists())

    def test_seller_can_post_message(self):
        self.assertTrue(self.client.login(username="msg_seller", password="pass"))
        url = reverse("marketplace:request_message_post", args=[self.pr.id])
        r = self.client.post(url, data={"content": "Hello buyer"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(RequestMessage.objects.filter(request=self.pr, author=self.seller, content__icontains="Hello").exists())

    def test_forbidden_for_intruder(self):
        self.assertTrue(self.client.login(username="msg_intruder", password="pass"))
        url = reverse("marketplace:request_message_post", args=[self.pr.id])
        r = self.client.post(url, data={"content": "I should not post"})
        self.assertEqual(r.status_code, 403)

    def test_requires_content(self):
        self.assertTrue(self.client.login(username="msg_buyer", password="pass"))
        url = reverse("marketplace:request_message_post", args=[self.pr.id])
        r = self.client.post(url, data={"content": "   "})
        self.assertEqual(r.status_code, 400)

    def test_blocked_when_completed_or_canceled(self):
        # Completed
        self.pr.status = PurchaseRequestStatus.COMPLETED
        self.pr.save(update_fields=["status"])
        self.assertTrue(self.client.login(username="msg_buyer", password="pass"))
        url = reverse("marketplace:request_message_post", args=[self.pr.id])
        r1 = self.client.post(url, data={"content": "Nope"})
        self.assertEqual(r1.status_code, 400)
        # Canceled
        self.pr.status = PurchaseRequestStatus.CANCELED
        self.pr.save(update_fields=["status"])
        r2 = self.client.post(url, data={"content": "Still nope"})
        self.assertEqual(r2.status_code, 400)

    def test_messages_mark_read_on_view(self):
        # Seller sends a message to buyer
        m = RequestMessage.objects.create(request=self.pr, author=self.seller, content="Ping")
        self.assertIsNone(m.read_at)
        self.assertTrue(self.client.login(username="msg_buyer", password="pass"))
        detail_url = reverse("marketplace:request_detail", args=[self.pr.id])
        resp = self.client.get(detail_url)
        self.assertEqual(resp.status_code, 200)
        m.refresh_from_db()
        self.assertIsNotNone(m.read_at)


class TestSellerRatingActions(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.buyer = User.objects.create_user(username="rating_buyer", email="rating_buyer@example.com", password="pass")
        self.seller = User.objects.create_user(username="rating_seller", email="rating_seller@example.com", password="pass")
        self.intruder = User.objects.create_user(username="rating_intruder", email="rating_intruder@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Rated Widget",
            description="",
            price=100,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def _make_request(self, status):
        return PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=status,
        )

    def test_buyer_can_rate_on_completed_request(self):
        pr = self._make_request(PurchaseRequestStatus.COMPLETED)
        self.assertTrue(self.client.login(username="rating_buyer", password="pass"))
        resp = self.client.post(reverse("marketplace:post_seller_rating", args=[pr.id]), {"score": 5, "comment": "Great seller!"})
        self.assertEqual(resp.status_code, 302)
        rating = SellerRating.objects.get(purchase_request=pr)
        self.assertEqual(rating.score, 5)
        self.assertEqual(rating.comment, "Great seller!")
        self.assertEqual(rating.buyer_id, self.buyer.id)
        self.assertEqual(rating.seller_id, self.seller.id)

    def test_only_buyer_can_rate(self):
        pr = self._make_request(PurchaseRequestStatus.COMPLETED)
        # seller cannot rate
        self.assertTrue(self.client.login(username="rating_seller", password="pass"))
        resp = self.client.post(reverse("marketplace:post_seller_rating", args=[pr.id]), {"score": 5})
        self.assertEqual(resp.status_code, 403)
        # intruder cannot rate
        self.assertTrue(self.client.login(username="rating_intruder", password="pass"))
        resp = self.client.post(reverse("marketplace:post_seller_rating", args=[pr.id]), {"score": 4})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(SellerRating.objects.filter(purchase_request=pr).exists())

    def test_buyer_cannot_rate_twice(self):
        pr = self._make_request(PurchaseRequestStatus.COMPLETED)
        self.assertTrue(self.client.login(username="rating_buyer", password="pass"))
        first = self.client.post(reverse("marketplace:post_seller_rating", args=[pr.id]), {"score": 4, "comment": "Good"})
        self.assertEqual(first.status_code, 302)
        again = self.client.post(reverse("marketplace:post_seller_rating", args=[pr.id]), {"score": 5})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(SellerRating.objects.filter(purchase_request=pr, buyer_id=self.buyer.id).count(), 1)


class TestRatingAggregates(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="agg_seller", email="agg_seller@example.com", password="pass")
        self.buyer1 = User.objects.create_user(username="agg_buyer1", email="agg_buyer1@example.com", password="pass")
        self.buyer2 = User.objects.create_user(username="agg_buyer2", email="agg_buyer2@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Aggregate Widget",
            description="",
            price=50,
            quantity=3,
            status=ListingStatus.ACTIVE,
        )
        # Create ratings for seller
        SellerRating.objects.create(seller=self.seller, buyer=self.buyer1, score=5)
        SellerRating.objects.create(seller=self.seller, buyer=self.buyer2, score=3)

    def test_catalog_view_includes_seller_rating_aggregates(self):
        url = reverse("marketplace:catalog")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        # Find our listing in result; ensure annotations are present
        target = next((l for l in listings if l.id == self.listing.id), None)
        self.assertIsNotNone(target)
        # Average should be 4.0 across two ratings; count 2
        self.assertEqual(getattr(target, "seller_rating_count", 0), 2)
        self.assertAlmostEqual(float(getattr(target, "seller_avg_rating", 0.0)), 4.0, places=1)

    def test_listing_detail_has_rating_aggregates(self):
        url = reverse("marketplace:listing_detail", kwargs={"pk": self.listing.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx.get("seller_rating_count"), 2)
        self.assertAlmostEqual(float(ctx.get("seller_rating_avg", 0.0)), 4.0, places=1)


class TestMeetupActions(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.buyer = User.objects.create_user(username="meet_buyer", email="buyer@example.com", password="pass")
        self.seller = User.objects.create_user(username="meet_seller", email="seller@example.com", password="pass")
        self.intruder = User.objects.create_user(username="meet_intruder", email="intruder@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Meetup Item",
            description="",
            price=10,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )
        # Create accepted request and confirmed transaction via seller_accept_request
        self.pr = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )
        self.client.login(username="meet_seller", password="pass")
        accept_url = reverse("marketplace:seller_accept_request", kwargs={"request_id": self.pr.id})
        r = self.client.post(accept_url)
        self.assertEqual(r.status_code, 302)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.ACCEPTED)
        self.assertIsNotNone(self.pr.transaction)
        self.assertEqual(self.pr.transaction.status, TransactionStatus.CONFIRMED)

    def test_buyer_can_propose_meetup(self):
        self.client.login(username="meet_buyer", password="pass")
        propose_url = reverse("marketplace:propose_meetup", kwargs={"request_id": self.pr.id})
        dt = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(propose_url, {"meetup_time": dt, "meetup_place": "Central Park"})
        self.assertEqual(r.status_code, 302)
        self.pr.transaction.refresh_from_db()
        self.assertTrue(self.pr.transaction.meetup_place)
        self.assertIsNotNone(self.pr.transaction.meetup_time)
        # Log created
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.MEETUP_PROPOSED).first()
        self.assertIsNotNone(log)

    def test_update_meetup_requires_existing_details(self):
        # First propose
        self.client.login(username="meet_buyer", password="pass")
        propose_url = reverse("marketplace:propose_meetup", kwargs={"request_id": self.pr.id})
        dt1 = (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(propose_url, {"meetup_time": dt1, "meetup_place": "Cafe"})
        # Then update
        update_url = reverse("marketplace:update_meetup", kwargs={"request_id": self.pr.id})
        dt2 = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        r2 = self.client.post(update_url, {"meetup_time": dt2, "meetup_place": "Library"})
        self.assertEqual(r2.status_code, 302)
        self.pr.transaction.refresh_from_db()
        self.assertEqual(self.pr.transaction.meetup_place, "Library")
        # Log created
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.MEETUP_UPDATED).first()
        self.assertIsNotNone(log)

    def test_confirm_meetup_checks_future_time(self):
        # Propose with future time
        self.client.login(username="meet_buyer", password="pass")
        propose_url = reverse("marketplace:propose_meetup", kwargs={"request_id": self.pr.id})
        dt = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(propose_url, {"meetup_time": dt, "meetup_place": "Park"})
        # Confirm
        confirm_url = reverse("marketplace:confirm_meetup", kwargs={"request_id": self.pr.id})
        r = self.client.post(confirm_url)
        self.assertEqual(r.status_code, 302)
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.MEETUP_CONFIRMED).first()
        self.assertIsNotNone(log)

    def test_intruder_cannot_propose(self):
        self.client.login(username="meet_intruder", password="pass")
        propose_url = reverse("marketplace:propose_meetup", kwargs={"request_id": self.pr.id})
        dt = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(propose_url, {"meetup_time": dt, "meetup_place": "Somewhere"})
        self.assertEqual(r.status_code, 403)

    def test_past_time_rejected(self):
        self.client.login(username="meet_buyer", password="pass")
        propose_url = reverse("marketplace:propose_meetup", kwargs={"request_id": self.pr.id})
        dt = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(propose_url, {"meetup_time": dt, "meetup_place": "Old"})
        # Redirect with error message due to form invalid; status 302
        self.assertEqual(r.status_code, 302)
        # Ensure not set
        self.pr.transaction.refresh_from_db()
        self.assertFalse(self.pr.transaction.meetup_place)

    def test_confirm_requires_existing_details(self):
        self.client.login(username="meet_buyer", password="pass")
        # No details set yet; confirm should 400
        confirm_url = reverse("marketplace:confirm_meetup", kwargs={"request_id": self.pr.id})
        r = self.client.post(confirm_url)
        self.assertEqual(r.status_code, 400)


class TestModeratorReportActions(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.moderator = User.objects.create_user(username="mod", email="mod@example.com", password="pass")
        self.moderator.is_staff = True
        self.moderator.save(update_fields=["is_staff"])
        self.reporter = User.objects.create_user(username="rep", email="rep@example.com", password="pass")
        self.seller = User.objects.create_user(username="seller_mod", email="seller_mod@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Reported Item",
            description="",
            price=12,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )
        self.report = Report.objects.create(
            reporter=self.reporter,
            listing=self.listing,
            reason="fraud",
            details="",
            status=ReportStatus.OPEN,
        )

    def test_dashboard_shows_open_reports_for_moderator(self):
        self.assertTrue(self.client.login(username="mod", password="pass"))
        resp = self.client.get(reverse("marketplace:moderator_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("open_reports", resp.context)
        reports = list(resp.context["open_reports"])  # QuerySet to list
        self.assertTrue(any(r.id == self.report.id for r in reports))

    def test_non_moderator_cannot_close_report(self):
        self.assertTrue(self.client.login(username="rep", password="pass"))
        url = reverse("marketplace:moderator_close_report", args=[self.report.id])
        resp = self.client.post(url)
        # user_passes_test redirects to login for unauthorized
        self.assertEqual(resp.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatus.OPEN)

    def test_moderator_can_close_report(self):
        self.assertTrue(self.client.login(username="mod", password="pass"))
        url = reverse("marketplace:moderator_close_report", args=[self.report.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatus.CLOSED)


class TestStep7PermissionsStateGuards(TestCase):
    """Step 7: Permissions & Visibility — view restrictions and status guards."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller_z", email="seller_z@example.com", password="pass")
        self.buyer = User.objects.create_user(username="buyer_z", email="buyer_z@example.com", password="pass")
        self.intruder = User.objects.create_user(username="intruder_z", email="intruder_z@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Guarded Item",
            description="",
            price=50,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )

    def _make_request(self, status=PurchaseRequestStatus.PENDING):
        return PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=status,
        )

    def test_request_detail_forbidden_to_intruder(self):
        pr = self._make_request(PurchaseRequestStatus.PENDING)
        self.assertTrue(self.client.login(username="intruder_z", password="pass"))
        url = reverse("marketplace:request_detail", kwargs={"pk": pr.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_accept_requires_valid_status_and_listing_active(self):
        # Invalid status cannot be accepted
        pr_bad = self._make_request(PurchaseRequestStatus.REJECTED)
        self.assertTrue(self.client.login(username="seller_z", password="pass"))
        url_accept_bad = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr_bad.id})
        r_bad = self.client.post(url_accept_bad)
        self.assertEqual(r_bad.status_code, 400)
        pr_bad.refresh_from_db()
        self.assertEqual(pr_bad.status, PurchaseRequestStatus.REJECTED)

        # Valid pending can be accepted when listing is active
        pr_ok = self._make_request(PurchaseRequestStatus.PENDING)
        url_accept_ok = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr_ok.id})
        r_ok = self.client.post(url_accept_ok)
        self.assertEqual(r_ok.status_code, 302)
        pr_ok.refresh_from_db()
        self.assertEqual(pr_ok.status, PurchaseRequestStatus.ACCEPTED)

    def test_negotiate_only_from_pending(self):
        pr = self._make_request(PurchaseRequestStatus.ACCEPTED)
        self.assertTrue(self.client.login(username="seller_z", password="pass"))
        url_neg = reverse("marketplace:seller_negotiate_request", kwargs={"request_id": pr.id})
        r = self.client.post(url_neg)
        self.assertEqual(r.status_code, 400)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequestStatus.ACCEPTED)

    def test_prevent_second_accept_for_same_listing(self):
        pr1 = self._make_request(PurchaseRequestStatus.PENDING)
        pr2 = self._make_request(PurchaseRequestStatus.PENDING)
        self.assertTrue(self.client.login(username="seller_z", password="pass"))
        url1 = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr1.id})
        r1 = self.client.post(url1)
        self.assertEqual(r1.status_code, 302)
        pr1.refresh_from_db()
        self.assertEqual(pr1.status, PurchaseRequestStatus.ACCEPTED)
        # Listing now reserved — accepting pr2 should fail
        url2 = reverse("marketplace:seller_accept_request", kwargs={"request_id": pr2.id})
        r2 = self.client.post(url2)
        self.assertEqual(r2.status_code, 400)
        pr2.refresh_from_db()
        self.assertEqual(pr2.status, PurchaseRequestStatus.PENDING)


class TestNegotiationActions(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="neg_seller", email="seller@example.com", password="pass")
        self.buyer = User.objects.create_user(username="neg_buyer", email="buyer@example.com", password="pass")
        self.intruder = User.objects.create_user(username="neg_intruder", email="intruder@example.com", password="pass")
        self.listing = Listing.objects.create(
            seller=self.seller,
            title="Neg Item",
            description="",
            price=Decimal("25.00"),
            quantity=5,
            status=ListingStatus.ACTIVE,
        )
        self.pr = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )

    def test_buyer_submit_offer_sets_negotiating_logs_and_emails_seller(self):
        baseline = len(mail.outbox)
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        url = reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id})
        r = self.client.post(url, {"offer_price": "22.00", "quantity": 2})
        self.assertEqual(r.status_code, 302)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.NEGOTIATING)
        self.assertEqual(self.pr.offer_price, Decimal("22.00"))
        self.assertEqual(self.pr.quantity, 2)
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.OFFER_SUBMITTED).first()
        self.assertIsNotNone(log)
        self.assertGreater(len(mail.outbox), baseline)

    def test_intruder_cannot_submit_offer(self):
        self.assertTrue(self.client.login(username="neg_intruder", password="pass"))
        url = reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id})
        r = self.client.post(url, {"offer_price": "21.00", "quantity": 1})
        self.assertEqual(r.status_code, 403)

    def test_seller_counter_offer_logs_and_emails_buyer(self):
        # Buyer places initial offer
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        self.client.post(reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id}), {"offer_price": "22.00", "quantity": 1})
        # Seller counters
        baseline = len(mail.outbox)
        self.assertTrue(self.client.login(username="neg_seller", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "counter", "counter_offer": "24.00"})
        self.assertEqual(r.status_code, 302)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.counter_offer, Decimal("24.00"))
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.OFFER_COUNTERED).first()
        self.assertIsNotNone(log)
        self.assertGreater(len(mail.outbox), baseline)

    def test_seller_accept_creates_transaction_reserves_listing_logs_and_emails(self):
        # Initial offer
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        self.client.post(reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id}), {"offer_price": "22.00", "quantity": 1})
        # Accept
        baseline = len(mail.outbox)
        self.assertTrue(self.client.login(username="neg_seller", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "accept"})
        self.assertEqual(r.status_code, 302)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.ACCEPTED)
        self.assertIsNotNone(self.pr.transaction)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.RESERVED)
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.OFFER_ACCEPTED).first()
        self.assertIsNotNone(log)
        # Two emails (buyer and seller) may be sent
        self.assertGreaterEqual(len(mail.outbox), baseline + 2)

    def test_seller_reject_sets_status_logs_and_emails(self):
        # Initial offer
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        self.client.post(reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id}), {"offer_price": "22.00", "quantity": 1})
        # Reject
        baseline = len(mail.outbox)
        self.assertTrue(self.client.login(username="neg_seller", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "reject"})
        self.assertEqual(r.status_code, 302)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.REJECTED)
        log = TransactionLog.objects.filter(request=self.pr, action=LogAction.OFFER_REJECTED).first()
        self.assertIsNotNone(log)
        self.assertGreaterEqual(len(mail.outbox), baseline + 2)

    def test_intruder_cannot_respond(self):
        # Initial offer to move to negotiating
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        self.client.post(reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id}), {"offer_price": "22.00", "quantity": 1})
        # Intruder attempts to respond
        self.assertTrue(self.client.login(username="neg_intruder", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "reject"})
        self.assertEqual(r.status_code, 403)

    def test_cannot_respond_if_not_negotiating(self):
        self.assertTrue(self.client.login(username="neg_seller", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "reject"})
        self.assertEqual(r.status_code, 400)

    def test_accept_requires_active_listing(self):
        # Initial offer
        self.assertTrue(self.client.login(username="neg_buyer", password="pass"))
        self.client.post(reverse("marketplace:submit_offer", kwargs={"request_id": self.pr.id}), {"offer_price": "22.00", "quantity": 1})
        # Deactivate listing
        self.listing.status = ListingStatus.PENDING
        self.listing.save(update_fields=["status"])  # type: ignore[arg-type]
        self.assertTrue(self.client.login(username="neg_seller", password="pass"))
        r = self.client.post(reverse("marketplace:respond_offer", kwargs={"request_id": self.pr.id}), {"action": "accept"})
        self.assertEqual(r.status_code, 400)


class TestListingReservationAndCascade(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller", password="pass")
        self.buyer1 = User.objects.create_user(username="buyer1", password="pass")
        self.buyer2 = User.objects.create_user(username="buyer2", password="pass")
        self.cat = Category.objects.create(name="Cats")
        self.listing = Listing.objects.create(
            title="Cat Toy",
            description="Fun toy",
            category=self.cat,
            seller=self.seller,
            price=Decimal("10.00"),
            status=ListingStatus.ACTIVE,
            quantity=1,
        )
        # Create open request that should be auto-closed when stock hits zero
        self.req_buyer2 = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer2,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )

    def test_reserve_decrements_stock_and_cascade_closes_open_requests(self):
        self.client.login(username="buyer1", password="pass")
        url = reverse("marketplace:api_listing_reserve", args=[self.listing.id])
        resp = self.client.post(url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(resp.status_code, 200)
        self.listing.refresh_from_db()
        # Quantity goes to 0 and auto-hide sets status to archived after reservation
        self.assertEqual(self.listing.quantity, 0)
        self.assertEqual(self.listing.status, ListingStatus.ARCHIVED)
        # Open requests for this listing are auto-rejected
        self.req_buyer2.refresh_from_db()
        self.assertEqual(self.req_buyer2.status, PurchaseRequestStatus.REJECTED)


class TestPaymentTrackingSellFlow(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller", password="pass")
        self.buyer = User.objects.create_user(username="buyer", password="pass")
        self.cat = Category.objects.create(name="Dogs")
        self.listing = Listing.objects.create(
            title="Dog Leash",
            description="Strong leash",
            category=self.cat,
            seller=self.seller,
            price=Decimal("20.00"),
            status=ListingStatus.ACTIVE,
            quantity=1,
        )

    def test_sell_marks_paid_and_updates_stock(self):
        # Reserve first (buyer)
        self.client.login(username="buyer", password="pass")
        reserve_url = reverse("marketplace:api_listing_reserve", args=[self.listing.id])
        r = self.client.post(reserve_url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.PENDING)
        # Now seller records payment
        self.client.logout()
        self.client.login(username="seller", password="pass")
        sell_url = reverse("marketplace:api_listing_sell", args=[self.listing.id])
        payload = {"payment_method": "cash", "amount_paid": "20.00"}
        resp = self.client.post(sell_url, content_type="application/json", data=json.dumps(payload))
        self.assertEqual(resp.status_code, 200)
        self.listing.refresh_from_db()
        # Quantity hits zero -> status becomes sold
        self.assertEqual(self.listing.quantity, 0)
        self.assertEqual(self.listing.status, ListingStatus.SOLD)
        # Latest transaction is marked paid
        txn = Transaction.objects.filter(listing=self.listing).order_by("-created_at").first()
        self.assertIsNotNone(txn)
        self.assertEqual(txn.status, TransactionStatus.PAID)
        self.assertEqual(txn.payment_method, "cash")
        self.assertEqual(str(txn.amount_paid), "20.00")

    def test_non_seller_cannot_record_payment(self):
        # Reserve first (buyer)
        self.client.login(username="buyer", password="pass")
        reserve_url = reverse("marketplace:api_listing_reserve", args=[self.listing.id])
        r = self.client.post(reserve_url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(r.status_code, 200)
        self.client.logout()
        # Another buyer attempting to sell should be forbidden
        other = get_user_model().objects.create_user(username="intruder", password="pass")
        self.client.login(username="intruder", password="pass")
        sell_url = reverse("marketplace:api_listing_sell", args=[self.listing.id])
        resp = self.client.post(sell_url, content_type="application/json", data=json.dumps({"payment_method": "cash"}))
        self.assertEqual(resp.status_code, 403)


class TestMeetupSetAndConfirmJSON(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller", password="pass")
        self.buyer = User.objects.create_user(username="buyer", password="pass")
        self.cat = Category.objects.create(name="Fish")
        self.listing = Listing.objects.create(
            title="Fish Tank",
            description="Glass tank",
            category=self.cat,
            seller=self.seller,
            price=Decimal("50.00"),
            status=ListingStatus.ACTIVE,
            quantity=1,
        )
        # Create request and accept to generate transaction
        self.pr = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )
        self.listing.status = ListingStatus.ACTIVE
        self.listing.save(update_fields=["status"])  # ensure active prior to accept
        # Accept via JSON endpoint (seller)
        self.client.login(username="seller", password="pass")
        acc_url = reverse("marketplace:api_request_accept", args=[self.pr.id])
        acc_resp = self.client.post(acc_url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(acc_resp.status_code, 200)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.ACCEPTED)
        self.assertIsNotNone(self.pr.transaction)
        self.client.logout()

    def test_meetup_confirm_future_time_succeeds(self):
        # Buyer proposes meetup details
        self.client.login(username="buyer", password="pass")
        future_time = (timezone.now() + timedelta(hours=2)).isoformat()
        set_url = reverse("marketplace:api_request_meetup_set", args=[self.pr.id])
        payload = {"meetup_place": "Park", "meetup_time": future_time}
        r = self.client.post(set_url, content_type="application/json", data=json.dumps(payload))
        self.assertEqual(r.status_code, 200)
        # Seller confirms
        self.client.logout()
        self.client.login(username="seller", password="pass")
        conf_url = reverse("marketplace:api_request_meetup_confirm", args=[self.pr.id])
        c = self.client.post(conf_url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(c.status_code, 200)

    def test_meetup_confirm_past_time_fails(self):
        # Buyer proposes a past time
        self.client.login(username="buyer", password="pass")
        past_time = (timezone.now() - timedelta(hours=2)).isoformat()
        set_url = reverse("marketplace:api_request_meetup_set", args=[self.pr.id])
        payload = {"meetup_place": "Cafe", "meetup_time": past_time}
        r = self.client.post(set_url, content_type="application/json", data=json.dumps(payload))
        self.assertEqual(r.status_code, 200)
        # Confirm should fail
        self.client.logout()
        self.client.login(username="seller", password="pass")
        conf_url = reverse("marketplace:api_request_meetup_confirm", args=[self.pr.id])
        c = self.client.post(conf_url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(c.status_code, 400)


class TestRequestPermissionsJSON(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.seller = User.objects.create_user(username="seller", password="pass")
        self.buyer = User.objects.create_user(username="buyer", password="pass")
        self.intruder = User.objects.create_user(username="intruder", password="pass")
        self.cat = Category.objects.create(name="Birds")
        self.listing = Listing.objects.create(
            title="Bird Cage",
            description="Safe cage",
            category=self.cat,
            seller=self.seller,
            price=Decimal("30.00"),
            status=ListingStatus.ACTIVE,
            quantity=1,
        )
        self.pr = PurchaseRequest.objects.create(
            listing=self.listing,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
        )

    def test_only_seller_can_accept_request(self):
        # Intruder cannot accept
        self.client.login(username="intruder", password="pass")
        url = reverse("marketplace:api_request_accept", args=[self.pr.id])
        resp = self.client.post(url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(resp.status_code, 403)
        self.client.logout()
        # Buyer cannot accept
        self.client.login(username="buyer", password="pass")
        resp2 = self.client.post(url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(resp2.status_code, 403)
        self.client.logout()
        # Seller can accept
        self.client.login(username="seller", password="pass")
        resp3 = self.client.post(url, content_type="application/json", data=json.dumps({}))
        self.assertEqual(resp3.status_code, 200)
        self.pr.refresh_from_db()
        self.assertEqual(self.pr.status, PurchaseRequestStatus.ACCEPTED)


class TestDashboardsAndTransactionsIntegration(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="dash", password="pass")

    def test_buyer_and_seller_dashboards_load(self):
        self.client.login(username="dash", password="pass")
        buyer_url = reverse("marketplace:buyer_dashboard")
        seller_url = reverse("marketplace:seller_dashboard")
        rb = self.client.get(buyer_url)
        rs = self.client.get(seller_url)
        self.assertEqual(rb.status_code, 200)
        self.assertEqual(rs.status_code, 200)

    def test_transactions_view_groups_context(self):
        self.client.login(username="dash", password="pass")
        url = reverse("marketplace:transactions")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertIn("grouped", ctx)
        grouped = ctx["grouped"]
        # Ensure expected buckets exist
        self.assertIn("proposed", grouped)
        self.assertIn("confirmed", grouped)
        self.assertIn("completed", grouped)
        self.assertIn("canceled", grouped)


class TestModeratorDashboardTemplateInteractions(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        from .test_factories import make_user, make_category, make_listing, make_report
        self.make_user = make_user
        self.make_category = make_category
        self.make_listing = make_listing
        self.make_report = make_report
        self.mod = self.make_user("moderator", is_staff=True)
        self.cat = self.make_category("Moderation")
        self.pending_listing = self.make_listing(seller=self.mod, category=self.cat, title="Pending Item", status=ListingStatus.PENDING)
        # Create a report to appear on dashboard
        reporter = self.make_user("reporter")
        self.report = self.make_report(listing=self.pending_listing, reporter=reporter, reason="Test reason")

    def test_dashboard_renders_with_csrf_forms_and_lists(self):
        self.assertTrue(self.client.login(username="moderator", password="pass"))
        resp = self.client.get(reverse("marketplace:moderator_dashboard"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # Forms should include CSRF token
        self.assertIn("csrfmiddlewaretoken", html)
        # Pending listing title appears
        self.assertIn("Pending Item", html)
        # Reports table should show reporter username
        self.assertIn("reporter", html)

    def test_moderator_can_approve_and_reject_listing(self):
        self.assertTrue(self.client.login(username="moderator", password="pass"))
        # Seed CSRF by visiting dashboard
        dash = self.client.get(reverse("marketplace:moderator_dashboard"))
        self.assertEqual(dash.status_code, 200)
        csrf = self.client.cookies.get("csrftoken").value
        # Approve
        url_approve = reverse("marketplace:moderator_approve_listing", args=[self.pending_listing.id])
        r1 = self.client.post(url_approve, {"csrfmiddlewaretoken": csrf})
        self.assertEqual(r1.status_code, 302)
        self.pending_listing.refresh_from_db()
        self.assertEqual(self.pending_listing.status, ListingStatus.ACTIVE)
        # Reject
        url_reject = reverse("marketplace:moderator_reject_listing", args=[self.pending_listing.id])
        r2 = self.client.post(url_reject, {"reason": "Not suitable", "csrfmiddlewaretoken": csrf})
        self.assertEqual(r2.status_code, 302)
        self.pending_listing.refresh_from_db()
        self.assertEqual(self.pending_listing.status, ListingStatus.REJECTED)
        self.assertEqual(self.pending_listing.rejected_reason, "Not suitable")


class TestNotificationsTemplateInteractions(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        from .test_factories import make_user, make_notification
        self.user = make_user("notify_user")
        self.n1 = make_notification(user=self.user, title="Alert 1", unread=True)
        self.n2 = make_notification(user=self.user, title="Alert 2", unread=True)
        self.n3 = make_notification(user=self.user, title="Alert 3", unread=False)


class TestMarketplaceAdminAnalyticsDataEndpoint(TestCase):
    def setUp(self):
        from .test_factories import make_user, make_category, make_listing
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        from .models import Transaction, TransactionStatus
        from decimal import Decimal
        from django.utils import timezone

        self.client = Client()
        # Ensure Marketplace Admin group exists
        self.group, _ = Group.objects.get_or_create(name="Marketplace Admin")
        # Admin user and assign permission to view analytics
        self.admin = make_user("mp_admin")
        self.admin.groups.add(self.group)
        ct = ContentType.objects.get(app_label="marketplace", model="listing")
        perm = Permission.objects.get(content_type=ct, codename="can_view_analytics")
        self.admin.user_permissions.add(perm)
        self.admin.save()

        # Create categories, listings, and transactions across dates
        self.cat1 = make_category("Food")
        self.cat2 = make_category("Toys")
        seller = make_user("sellerX")
        buyer = make_user("buyerX")
        l1 = make_listing(seller=seller, category=self.cat1, title="Kibble", status="active")
        l2 = make_listing(seller=seller, category=self.cat2, title="Ball", status="active")

        # Two transactions: one last week (Food) and one today (Toys)
        last_week = timezone.now() - timezone.timedelta(days=7)
        t1 = Transaction.objects.create(
            listing=l1, buyer=buyer, seller=seller, status=TransactionStatus.PAID,
            amount_paid=Decimal("20.00"), created_at=last_week
        )
        t1.save(update_fields=["created_at"])  # persist custom created_at
        t2 = Transaction.objects.create(
            listing=l2, buyer=buyer, seller=seller, status=TransactionStatus.COMPLETED,
            amount_paid=Decimal("35.00")
        )

    def test_endpoint_returns_datasets(self):
        self.assertTrue(self.client.login(username="mp_admin", password="pass"))
        url = reverse("marketplace_admin:analytics_data")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Basic keys present
        for key in [
            "revenue_labels", "revenue_data", "categories_labels", "categories_data",
            "active_cat_labels", "active_cat_data", "user_labels", "user_data", "recent_transactions",
        ]:
            self.assertIn(key, data)
        # Revenue data should be non-empty given our fixtures
        self.assertTrue(len(data["revenue_labels"]) >= 1)

    def test_category_filter_limits_categories(self):
        self.assertTrue(self.client.login(username="mp_admin", password="pass"))
        url = reverse("marketplace_admin:analytics_data")
        resp = self.client.get(url, {"category": self.cat2.slug})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Only Toys category should appear for sales
        self.assertTrue(all(lbl == "Toys" for lbl in data["categories_labels"]))

    def test_permission_required(self):
        # Create another admin without the analytics permission
        from .test_factories import make_user
        bad_admin = make_user("mp_admin_no_perm")
        bad_admin.groups.add(self.group)
        self.assertTrue(self.client.login(username="mp_admin_no_perm", password="pass"))
        url = reverse("marketplace_admin:analytics_data")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_notifications_page_renders_and_shows_unread_count(self):
        self.assertTrue(self.client.login(username="notify_user", password="pass"))
        resp = self.client.get(reverse("marketplace:notifications"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("csrfmiddlewaretoken", html)  # mark-all form includes CSRF
        # Context unread count matches DB
        from .models import Notification
        unread_db = Notification.objects.filter(user=self.user, read_at__isnull=True).count()
        self.assertEqual(resp.context["unread_notifications"], unread_db)

    def test_toggle_notification_read_json(self):
        self.assertTrue(self.client.login(username="notify_user", password="pass"))
        page = self.client.get(reverse("marketplace:notifications"))
        self.assertEqual(page.status_code, 200)
        csrf = self.client.cookies.get("csrftoken").value
        # Toggle n1 to read
        url = reverse("marketplace:notification_toggle_read", args=[self.n1.id])
        r = self.client.post(url, {"csrfmiddlewaretoken": csrf})
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode())
        self.assertFalse(data["unread"])  # now read
        # Toggle back to unread
        r2 = self.client.post(url, {"csrfmiddlewaretoken": csrf})
        self.assertEqual(r2.status_code, 200)
        data2 = json.loads(r2.content.decode())
        self.assertTrue(data2["unread"])  # back to unread

    def test_mark_all_notifications_read(self):
        self.assertTrue(self.client.login(username="notify_user", password="pass"))
        page = self.client.get(reverse("marketplace:notifications"))
        self.assertEqual(page.status_code, 200)
        csrf = self.client.cookies.get("csrftoken").value
        url = reverse("marketplace:notifications_mark_all")
        r = self.client.post(url, {"csrfmiddlewaretoken": csrf})
        self.assertEqual(r.status_code, 302)
        # After redirect, all notifications should be read
        from .models import Notification
        for n in Notification.objects.filter(user=self.user):
            self.assertIsNotNone(n.read_at)
            self.assertFalse(n.unread)
