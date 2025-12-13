"""
Management command: smoke_marketplace

Runs end-to-end smoke tests against the marketplace FBV and DRF endpoints using
Django's test client within a live project context. This avoids external shell
quirks and ensures URLs and auth work as defined in the project.

Scenarios covered:
- FBV transaction flow: reserve -> sell -> complete
- DRF transaction flow: reserve -> sell -> complete

It creates a temporary active user and two listings owned by that user (with
quantity=2) to exercise transitions to SOLD. It forces login via the test
client to bypass activation and CSRF concerns.

On success, exits with code 0. On failure, raises CommandError.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

from django.contrib.auth import get_user_model
from django.conf import settings
import os
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from marketplace.models import Listing, ListingStatus

User = get_user_model()


@dataclass
class SmokeResult:
    label: str
    ok: bool
    detail: str


class Command(BaseCommand):
    help = "Run marketplace smoke tests for FBV and DRF endpoints"

    def handle(self, *args, **options):  # noqa: D401
        """Execute the smoke tests and report results."""
        if not (getattr(settings, "SMOKE_ENABLED", False) or str(os.getenv("SMOKE_ENABLED", "")).lower() in {"1", "true", "yes"}):
            self.stdout.write("Smoke testing disabled.")
            return
        results: list[SmokeResult] = []
        client = Client()

        # 1) Prepare a test user and two fresh listings
        try:
            user = self._ensure_user()
            client.force_login(user)
            fbv_listing = self._ensure_listing(user, title_prefix="FBV Smoke Listing")
            drf_listing = self._ensure_listing(user, title_prefix="DRF Smoke Listing")
        except Exception as e:  # pragma: no cover - defensive
            raise CommandError(f"Setup failed: {e}") from e

        # 2) FBV flow
        results.append(self._smoke_fbv_flow(client, fbv_listing))

        # 3) DRF flow
        results.append(self._smoke_drf_flow(client, drf_listing))

        # Summarize
        ok_overall = all(r.ok for r in results)
        for r in results:
            status = "PASS" if r.ok else "FAIL"
            self.stdout.write(f"[{status}] {r.label}: {r.detail}")

        if not ok_overall:
            raise CommandError("One or more smoke tests failed")

        self.stdout.write(self.style.SUCCESS("All marketplace smoke tests passed."))

    # ---------- Helpers ----------
    def _ensure_user(self) -> User:
        """Create or get a local smoke-test user with a known password.

        We mark the user active to bypass activation flow, and use force_login.
        """
        username = "smoke_tester"
        email = "smoke_tester@example.com"
        password = "Passw0rd!smoke"
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_active": True,
                "date_joined": timezone.now(),
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])  # type: ignore[arg-type]
        elif not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])  # type: ignore[arg-type]
        return user

    def _ensure_listing(self, user: User, title_prefix: str) -> Listing:
        """Create a fresh active listing with quantity=2 for the given user."""
        listing = Listing.objects.create(
            seller=user,
            title=f"{title_prefix} @ {timezone.now():%Y-%m-%d %H:%M:%S}",
            description="Auto-generated listing for smoke tests",
            price="9.99",
            quantity=2,
            status=ListingStatus.ACTIVE,
        )
        return listing

    def _smoke_fbv_flow(self, client: Client, listing: Listing) -> SmokeResult:
        """Smoke the legacy FBV endpoints: reserve -> sell -> complete."""
        base = "marketplace:"
        try:
            # Reserve
            reserve_url = reverse(base + "api_listing_reserve", args=[listing.id])
            r = client.post(reserve_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="FBV reserve")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.PENDING,
                         "FBV reserve should set status to pending")
            self._expect(data["listing"]["quantity"] == 1,
                         "FBV reserve should decrement quantity to 1")

            # Sell
            sell_url = reverse(base + "api_listing_sell", args=[listing.id])
            r = client.post(sell_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="FBV sell")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.SOLD,
                         "FBV sell should set status to sold when quantity hits 0")
            self._expect(data["listing"]["quantity"] == 0,
                         "FBV sell should decrement quantity to 0")

            # Complete
            complete_url = reverse(base + "api_listing_complete", args=[listing.id])
            r = client.post(complete_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="FBV complete")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.SOLD,
                         "FBV complete should keep status sold")
            return SmokeResult("FBV flow", True, "reserve->sell->complete OK")
        except Exception as e:
            return SmokeResult("FBV flow", False, str(e))

    def _smoke_drf_flow(self, client: Client, listing: Listing) -> SmokeResult:
        """Smoke the DRF endpoints: reserve -> sell -> complete."""
        try:
            # Reserve via DRF: /marketplace/api/listings/<id>/reserve/
            reserve_url = f"/marketplace/api/listings/{listing.id}/reserve/"
            r = client.post(reserve_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="DRF reserve")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.PENDING,
                         "DRF reserve should set status to pending")
            self._expect(data["listing"]["quantity"] == 1,
                         "DRF reserve should decrement quantity to 1")

            # Sell via DRF
            sell_url = f"/marketplace/api/listings/{listing.id}/sell/"
            r = client.post(sell_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="DRF sell")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.SOLD,
                         "DRF sell should set status to sold when quantity hits 0")
            self._expect(data["listing"]["quantity"] == 0,
                         "DRF sell should decrement quantity to 0")

            # Complete via DRF
            complete_url = f"/marketplace/api/listings/{listing.id}/complete/"
            r = client.post(complete_url, data=json.dumps({}), content_type="application/json")
            self._assert_json_ok(r, step="DRF complete")
            data = r.json()
            self._expect(data["listing"]["status"] == ListingStatus.SOLD,
                         "DRF complete should keep status sold")
            return SmokeResult("DRF flow", True, "reserve->sell->complete OK")
        except Exception as e:
            return SmokeResult("DRF flow", False, str(e))

    # ---------- Assertions ----------
    def _assert_json_ok(self, response, step: str) -> None:
        """Ensure HTTP 200 and a JSON response body."""
        if response.status_code != 200:
            try:
                body = response.content.decode("utf-8")
            except Exception:  # pragma: no cover - defensive
                body = str(response.content)
            raise AssertionError(f"{step} failed: HTTP {response.status_code} Body={body[:300]}")
        # Validate JSON
        try:
            _ = response.json()
        except Exception as e:  # pragma: no cover - defensive
            raise AssertionError(f"{step} returned invalid JSON: {e}") from e

    def _expect(self, condition: bool, message: str) -> None:
        """Raise AssertionError if condition is False."""
        if not condition:
            raise AssertionError(message)
