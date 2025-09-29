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

from .forms import ListingForm
from .models import (
    Category,
    Listing,
    ListingStatus,
    MessageThread,
    Message,
    Transaction,
    Report,
    ReportStatus,
)
import json
import unittest
from rest_framework.test import APIClient
from rest_framework import status


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
        self.assertNotIn(self.l2, listings)

    def test_price_max_filter(self):
        url = reverse("marketplace:home")
        resp = self.client.get(url, {"price_max": "20"})
        self.assertEqual(resp.status_code, 200)
        listings = resp.context["listings"]
        self.assertTrue(all(l.price <= 20 for l in listings))
        # Should include 10 and 20, exclude 30
        self.assertIn(self.l1, listings)
        self.assertIn(self.l2, listings)
        self.assertNotIn(self.l4, listings)

    def test_price_min_greater_than_max_swaps_gracefully(self):
        url = reverse("marketplace:home")
        # min=30, max=10 should swap to [10,30]
        resp = self.client.get(url, {"price_min": "30", "price_max": "10"})
        self.assertEqual(resp.status_code, 200)
        listings = list(resp.context["listings"])
        # Active listings in range [10,30] are l2(10), l1(20), l4(30)
        self.assertIn(self.l2, listings)
        self.assertIn(self.l1, listings)
        self.assertIn(self.l4, listings)

    def test_invalid_price_params_are_ignored(self):
        url = reverse("marketplace:home")
        resp = self.client.get(url, {"price_min": "abc", "price_max": "-5"})
        self.assertEqual(resp.status_code, 200)
        listings = list(resp.context["listings"])
        # Both invalid -> no price filtering; ensure both active listings are present
        self.assertIn(self.l1, listings)
        self.assertIn(self.l2, listings)
        self.assertIn(self.l4, listings)


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
