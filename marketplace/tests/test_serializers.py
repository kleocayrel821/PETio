"""
Unit tests for marketplace serializers related to Quick View.

Focus: ensure ListingSerializer exposes nested `category` details and seller summary
so the admin Quick View can render a filled-in preview without extra queries.
"""
from django.test import TestCase

from marketplace.serializers import ListingSerializer
from marketplace.test_factories import make_user, make_listing, make_category


class ListingSerializerTests(TestCase):
    """Validate ListingSerializer fields for admin Quick View rendering."""

    def setUp(self):
        # Create seller, category, and listing for serialization tests
        self.seller = make_user("seller", password="pass")
        self.category = make_category("Accessories")
        self.listing = make_listing(
            seller=self.seller,
            category=self.category,
            title="Cat Collar",
            description="Adjustable collar for cats",
            price=10.5,
            quantity=3,
        )

    def test_listing_serializer_includes_nested_category(self):
        """Serializer should include `category` object with `name` for Quick View."""
        data = ListingSerializer(self.listing).data
        self.assertIn("category", data)
        self.assertIsInstance(data["category"], dict)
        self.assertEqual(data["category"].get("name"), "Accessories")

    def test_listing_serializer_includes_seller_summary(self):
        """Serializer should include seller summary with username for Quick View."""
        data = ListingSerializer(self.listing).data
        self.assertIn("seller", data)
        self.assertIsInstance(data["seller"], dict)
        self.assertEqual(data["seller"].get("username"), "seller")

    def test_listing_serializer_basic_fields_present(self):
        """Serializer should expose core fields required by the Quick View UI."""
        data = ListingSerializer(self.listing).data
        for key in ("id", "title", "description", "price", "quantity", "status"):
            self.assertIn(key, data)