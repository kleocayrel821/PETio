"""Tests for the marketplace requests overview view.

Verifies access control and basic rendering of buyer and seller request lists.
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from marketplace.models import Listing, PurchaseRequest, ListingStatus, PurchaseRequestStatus


class RequestsOverviewTests(TestCase):
    """Minimal tests ensuring the overview page loads and shows expected data."""

    def setUp(self):
        """Create users, listings, and purchase requests for testing."""
        User = get_user_model()
        self.buyer = User.objects.create_user(username="buyer", password="pass12345")
        self.seller = User.objects.create_user(username="seller", password="pass12345")

        # Listing owned by seller; buyer will create a request on it
        self.listing1 = Listing.objects.create(
            seller=self.seller,
            title="Test Item 1",
            description="Desc",
            price=10,
            quantity=1,
            status=ListingStatus.ACTIVE,
        )
        # Listing owned by buyer; seller will create a request on it (incoming for buyer)
        self.listing2 = Listing.objects.create(
            seller=self.buyer,
            title="Test Item 2",
            description="Desc",
            price=20,
            quantity=2,
            status=ListingStatus.ACTIVE,
        )

        # Buyer-side request
        self.pr1 = PurchaseRequest.objects.create(
            listing=self.listing1,
            buyer=self.buyer,
            seller=self.seller,
            status=PurchaseRequestStatus.PENDING,
            message="Interested in Test Item 1",
        )
        # Incoming request for buyer (as seller)
        self.pr2 = PurchaseRequest.objects.create(
            listing=self.listing2,
            buyer=self.seller,
            seller=self.buyer,
            status=PurchaseRequestStatus.PENDING,
            message="Interested in Test Item 2",
        )

    def test_login_required(self):
        """Unauthenticated access should redirect to login."""
        url = reverse("marketplace:requests_overview")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_overview_renders_lists(self):
        """Authenticated user sees both buyer and seller request sections and items."""
        self.client.login(username="buyer", password="pass12345")
        url = reverse("marketplace:requests_overview")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        # Section headings
        self.assertIn("Your Purchase Requests", content)
        self.assertIn("Incoming Purchase Requests", content)
        # Listing titles present
        self.assertIn("Test Item 1", content)
        self.assertIn("Test Item 2", content)
        # Detail links present
        self.assertIn(f"/marketplace/request/{self.pr1.id}/", content)
        self.assertIn(f"/marketplace/request/{self.pr2.id}/", content)