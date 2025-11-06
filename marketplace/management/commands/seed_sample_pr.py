"""
Management command to seed a sample Purchase Request for UI preview.

This creates:
- Two users (`demo_buyer`, `demo_seller`)
- A sample listing owned by `demo_seller`
- A `PurchaseRequest` linking buyer and seller

Prints the created purchase request ID, so you can open:
  /marketplace/request/<ID>/

Development-only helper to support responsive UI verification.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from marketplace.models import Listing, PurchaseRequest, ListingStatus


class Command(BaseCommand):
    help = "Seed a sample Purchase Request for UI preview (dev only)."

    def handle(self, *args, **options):
        """Create demo buyer/seller, listing, and purchase request.

        Returns the new `PurchaseRequest` ID via stdout.
        """
        User = get_user_model()

        # Create or get demo users
        buyer, _ = User.objects.get_or_create(
            username="demo_buyer",
            defaults={
                "email": "demo_buyer@example.com",
                "is_active": True,
            },
        )
        seller, _ = User.objects.get_or_create(
            username="demo_seller",
            defaults={
                "email": "demo_seller@example.com",
                "is_active": True,
            },
        )

        # Ensure passwords for possible future login (non-interactive)
        if not buyer.has_usable_password():
            buyer.set_password("pass")
            buyer.save(update_fields=["password"])
        if not seller.has_usable_password():
            seller.set_password("pass")
            seller.save(update_fields=["password"])

        # Create or get a sample listing
        listing, _ = Listing.objects.get_or_create(
            title="PETio Sample Product",
            defaults={
                "description": "Demo listing for responsive UI preview",
                "price": 29.99,
                "status": ListingStatus.ACTIVE,
                "seller": seller,
            },
        )
        # If listing existed but was not ACTIVE, set ACTIVE
        if listing.status != ListingStatus.ACTIVE:
            listing.status = ListingStatus.ACTIVE
            listing.save(update_fields=["status"])

        # Create the purchase request
        pr = PurchaseRequest.objects.create(
            listing=listing,
            buyer=buyer,
            seller=seller,
            status="pending",
            message="Interested in purchasing this item.",
        )

        self.stdout.write(self.style.SUCCESS(f"Seeded PurchaseRequest id={pr.id}"))