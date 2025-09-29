"""
Management command: smoke_messages

Runs end-to-end smoke tests for messaging APIs (FBV and DRF) using Django's
built-in test client. Validates:
- Start or get thread for a listing
- Fetch messages (empty, then after sending)
- Send message
- Permission checks: intruder cannot access thread messages
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction, connection
from django.db.models.signals import post_save
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from marketplace.models import Listing, ListingStatus, MessageThread
# NOTE: We avoid importing Profile to prevent triggering FK issues in dev DB
# from accounts.models import Profile
import accounts.signals as account_signals

User = get_user_model()


@dataclass
class SmokeResult:
    label: str
    ok: bool
    detail: str


class Command(BaseCommand):
    help = "Run messaging smoke tests for FBV and DRF endpoints"

    def handle(self, *args, **options):
        results: list[SmokeResult] = []
        client = Client()

        # Temporarily disconnect profile signals to avoid FK constraint mismatch in dev DB
        disconnected = []
        try:
            post_save.disconnect(account_signals.create_user_profile, sender=User)
            disconnected.append("create_user_profile")
        except Exception:
            pass
        try:
            post_save.disconnect(account_signals.save_user_profile, sender=User)
            disconnected.append("save_user_profile")
        except Exception:
            pass

        # Setup users and listing with granular diagnostics
        try:
            self.stdout.write("[setup] creating/ensuring users ...")
            seller = self._ensure_user("smoke_seller", "seller_smoke@example.com")
            fbv_buyer = self._ensure_user("smoke_buyer_fbv", "buyer_fbv_smoke@example.com")
            drf_buyer = self._ensure_user("smoke_buyer_drf", "buyer_drf_smoke@example.com")
            intruder = self._ensure_user("smoke_intruder", "intruder_smoke@example.com")
            self.stdout.write(f"[setup] users ok: seller={seller.id} fbv_buyer={fbv_buyer.id} drf_buyer={drf_buyer.id} intruder={intruder.id}")

            # DB diagnostics before creating listing
            try:
                with connection.cursor() as cur:
                    cur.execute('PRAGMA foreign_key_list(marketplace_listing)')
                    fk_listing = cur.fetchall()
                    cur.execute('PRAGMA foreign_key_list(accounts_profile)')
                    fk_profile = cur.fetchall()
                    cur.execute('SELECT COUNT(*) FROM accounts_user')
                    accounts_user_count = cur.fetchone()[0]
                    auth_user_count = None
                    try:
                        cur.execute('SELECT COUNT(*) FROM auth_user')
                        auth_user_count = cur.fetchone()[0]
                    except Exception:
                        auth_user_count = 'N/A'
                self.stdout.write(f"[diag] PRAGMA fk marketplace_listing: {fk_listing}")
                self.stdout.write(f"[diag] PRAGMA fk accounts_profile: {fk_profile}")
                self.stdout.write(f"[diag] rows: accounts_user={accounts_user_count}, auth_user={auth_user_count}")
            except Exception as diag_err:
                self.stdout.write(f"[diag] pre-listing diagnostics failed: {diag_err}")

            self.stdout.write("[setup] creating listing ...")
            listing = self._ensure_listing(seller)
            self.stdout.write(f"[setup] listing ok: id={listing.id} seller_id={listing.seller_id}")
        except Exception as e:
            raise CommandError(f"Setup failed: {e}") from e
        finally:
            # Reconnect signals after setup
            try:
                if "create_user_profile" in disconnected:
                    post_save.connect(account_signals.create_user_profile, sender=User)
                if "save_user_profile" in disconnected:
                    post_save.connect(account_signals.save_user_profile, sender=User)
            except Exception:
                pass

        # FBV messaging flow
        results.append(self._smoke_fbv_flow(client, fbv_buyer, listing, intruder))
        # DRF messaging flow
        results.append(self._smoke_drf_flow(client, drf_buyer, listing, intruder))

        ok = all(r.ok for r in results)
        for r in results:
            self.stdout.write(f"{'PASS' if r.ok else 'FAIL'} - {r.label}: {r.detail}")
        if not ok:
            raise CommandError("One or more messaging smoke tests failed")
        self.stdout.write(self.style.SUCCESS("Messaging smoke tests passed."))

    # ---- Helpers ----
    def _ensure_user(self, username: str, email: str) -> User:
        try:
            with transaction.atomic():
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={"email": email, "is_active": True, "date_joined": timezone.now()},
                )
                if not user.email:
                    user.email = email
                    user.save(update_fields=["email"])  # type: ignore[arg-type]
                if not user.is_active:
                    user.is_active = True
                    user.save(update_fields=["is_active"])  # type: ignore[arg-type]
                return user
        except IntegrityError:
            # Fallback: use timestamped email to avoid uniqueness collisions
            fallback_email = f"{username}.{int(timezone.now().timestamp())}@example.com"
            user = User.objects.filter(username=username).first()
            if user:
                return user
            user = User.objects.create(
                username=username,
                email=fallback_email,
                is_active=True,
                date_joined=timezone.now(),
            )
            return user

    def _ensure_listing(self, seller: User) -> Listing:
        try:
            return Listing.objects.create(
                seller=seller,
                title=f"Messaging Smoke Listing @ {timezone.now():%Y-%m-%d %H:%M:%S}",
                description="Auto-generated listing for messaging tests",
                price="1.00",
                quantity=1,
                status=ListingStatus.ACTIVE,
            )
        except IntegrityError as ie:
            # Deep diagnostics for FK failures
            with connection.cursor() as cur:
                cur.execute('PRAGMA foreign_key_list(marketplace_listing)')
                fk_listing = cur.fetchall()
                cur.execute('SELECT COUNT(*) FROM marketplace_category')
                cat_count = cur.fetchone()[0]
                cur.execute('SELECT COUNT(*) FROM accounts_user')
                usr_count = cur.fetchone()[0]
                try:
                    cur.execute('SELECT COUNT(*) FROM auth_user')
                    auth_usr_count = cur.fetchone()[0]
                except Exception:
                    auth_usr_count = 'N/A'
            raise IntegrityError(f"Listing create failed. FK listing={fk_listing}, counts: category={cat_count}, accounts_user={usr_count}, auth_user={auth_usr_count}; original={ie}")

    def _smoke_fbv_flow(self, client: Client, buyer: User, listing: Listing, intruder: User) -> SmokeResult:
        try:
            client.force_login(buyer)
            # Start thread
            start_url = reverse("marketplace:api_start_or_get_thread")
            r = client.post(start_url, data=json.dumps({"listing_id": listing.id}), content_type="application/json")
            self._assert_json_ok(r, "FBV start thread")
            start_data = r.json()
            thread_id = start_data["thread"]["id"]
            # Idempotency: starting thread again should return same thread
            r2 = client.post(start_url, data=json.dumps({"listing_id": listing.id}), content_type="application/json")
            self._assert_json_ok(r2, "FBV start thread idempotent")
            start_data_2 = r2.json()
            self._expect(start_data_2["thread"]["id"] == thread_id, "Start thread should be idempotent and return same thread id")
            # Fetch messages (should be empty)
            fetch_url = reverse("marketplace:api_fetch_messages", args=[thread_id])
            r = client.get(fetch_url)
            self._assert_json_ok(r, "FBV fetch messages initial")
            data = r.json()
            self._expect(data["count"] == 0, "Initial messages count should be 0")
            self._expect(len(data.get("messages", [])) == 0, "Initial messages list should be empty")
            # Send message
            send_url = reverse("marketplace:api_post_message", args=[thread_id])
            msg_content = "Hello from buyer"
            r = client.post(send_url, data=json.dumps({"content": msg_content}), content_type="application/json")
            self._assert_json_ok(r, "FBV send message")
            sent = r.json()["message"]
            self._expect(sent["content"] == msg_content, "Sent message content should match")
            first_id = sent.get("id")
            # Send second message and test after_id incremental fetch
            second_content = "Second hello from buyer"
            r = client.post(send_url, data=json.dumps({"content": second_content}), content_type="application/json")
            self._assert_json_ok(r, "FBV send second message")
            second = r.json()["message"]
            self._expect(second["content"] == second_content, "Second message content should match")
            # Fetch messages after sending
            r = client.get(fetch_url)
            self._assert_json_ok(r, "FBV fetch messages after send")
            data = r.json()
            self._expect(data["count"] >= 1, "Messages count should be >= 1 after sending")
            # Incremental fetch after first_id should return at least the second message
            r = client.get(f"{fetch_url}?after_id={first_id}")
            self._assert_json_ok(r, "FBV fetch messages after_id")
            data_after = r.json()
            self._expect(data_after["count"] >= 1 and any(m.get("id") != first_id for m in data_after.get("messages", [])), "After_id fetch should return newer messages only")
            # Limit param should cap returned messages length
            r = client.get(f"{fetch_url}?limit=1")
            self._assert_json_ok(r, "FBV fetch messages with limit=1")
            data_lim = r.json()
            self._expect(len(data_lim.get("messages", [])) <= 1, "Limit=1 should cap the messages list length")
            # Permission check: intruder should be forbidden
            client.force_login(intruder)
            r = client.get(fetch_url)
            self._expect(r.status_code == 403, "Intruder fetch should be forbidden (403)")
            # Intruder should also be forbidden to post
            r = client.post(send_url, data=json.dumps({"content": "You shall not pass"}), content_type="application/json")
            self._expect(r.status_code == 403, "Intruder send should be forbidden (403)")
            return SmokeResult("FBV messaging flow", True, "start->send->fetch with permissions OK")
        except Exception as e:
            return SmokeResult("FBV messaging flow", False, str(e))

    def _smoke_drf_flow(self, client: Client, buyer: User, listing: Listing, intruder: User) -> SmokeResult:
         try:
             client.force_login(buyer)
             # Start thread via DRF
             start_url = "/marketplace/api/threads/start/"
             r = client.post(start_url, data=json.dumps({"listing_id": listing.id}), content_type="application/json")
             self._assert_json_ok(r, "DRF start thread")
             start_data = r.json()
             thread_id = start_data["thread"]["id"]
             # Idempotency: starting thread again should return same thread
             r2 = client.post(start_url, data=json.dumps({"listing_id": listing.id}), content_type="application/json")
             self._assert_json_ok(r2, "DRF start thread idempotent")
             start_data_2 = r2.json()
             self._expect(start_data_2["thread"]["id"] == thread_id, "DRF start thread should be idempotent and return same thread id")
 
             # Fetch messages
             fetch_url = f"/marketplace/api/threads/{thread_id}/messages/"
             r = client.get(fetch_url)
             self._assert_json_ok(r, "DRF fetch messages initial")
             data = r.json()
             self._expect(data["count"] == 0, "Initial messages count should be 0")
             self._expect(len(data.get("messages", [])) == 0, "Initial messages list should be empty")
 
             # Send message
             send_url = f"/marketplace/api/threads/{thread_id}/send/"
             msg_content = "Hello via DRF"
             r = client.post(send_url, data=json.dumps({"content": msg_content}), content_type="application/json")
             self._assert_json_ok(r, "DRF send message")
             sent = r.json()["message"]
             self._expect(sent["content"] == msg_content, "Sent message content should match")
             first_id = sent.get("id")
             # Send second message and test after_id
             second_content = "Second hello via DRF"
             r = client.post(send_url, data=json.dumps({"content": second_content}), content_type="application/json")
             self._assert_json_ok(r, "DRF send second message")
             second = r.json()["message"]
             self._expect(second["content"] == second_content, "Second DRF message content should match")
 
             # Fetch messages after sending
             r = client.get(fetch_url)
             self._assert_json_ok(r, "DRF fetch messages after send")
             data = r.json()
             self._expect(data["count"] >= 1, "Messages count should be >= 1 after sending")
             # After_id incremental fetch
             r = client.get(f"{fetch_url}?after_id={first_id}")
             self._assert_json_ok(r, "DRF fetch messages after_id")
             data_after = r.json()
             self._expect(data_after["count"] >= 1 and all(m.get("id") != first_id for m in data_after.get("messages", [])), "DRF after_id fetch should return newer messages only")
             # Limit param
             r = client.get(f"{fetch_url}?limit=1")
             self._assert_json_ok(r, "DRF fetch messages with limit=1")
             data_lim = r.json()
             self._expect(len(data_lim.get("messages", [])) <= 1, "DRF limit=1 should cap the messages list length")
 
             # Permission check
             client.force_login(intruder)
             r = client.get(fetch_url)
             self._expect(r.status_code == 403, "Intruder fetch should be forbidden (403)")
             r = client.post(send_url, data=json.dumps({"content": "Nope"}), content_type="application/json")
             self._expect(r.status_code == 403, "Intruder send should be forbidden (403)")
 
             return SmokeResult("DRF messaging flow", True, "start->send->fetch with permissions OK")
         except Exception as e:
             return SmokeResult("DRF messaging flow", False, str(e))

    # ---- Assertions ----
    def _assert_json_ok(self, response, step: str) -> None:
        if response.status_code != 200:
            try:
                body = response.content.decode("utf-8")
            except Exception:
                body = str(response.content)
            raise AssertionError(f"{step} failed: HTTP {response.status_code} Body={body[:300]}")
        try:
            _ = response.json()
        except Exception as e:
            raise AssertionError(f"{step} returned invalid JSON: {e}") from e

    def _expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)