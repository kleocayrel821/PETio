from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from marketplace.models import Category, Listing, ListingStatus, Report, ReportStatus, Notification
from marketplace.test_factories import make_user


@override_settings(ADMIN_SESSION_COOKIE_NAME="sessionid", ADMIN_SESSION_COOKIE_PATH="/")
class MarketplaceAdminRoleTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create Marketplace Admin group
        self.group, _ = Group.objects.get_or_create(name="Marketplace Admin")

        # Ensure permissions exist
        # marketplace.can_approve_listing
        ct_listing = ContentType.objects.get_for_model(Listing)
        self.perm_approve, _ = Permission.objects.get_or_create(
            codename="can_approve_listing",
            content_type=ct_listing,
            defaults={"name": "Can approve or reject listings"},
        )

        # marketplace.can_view_analytics
        self.perm_analytics, _ = Permission.objects.get_or_create(
            codename="can_view_analytics",
            content_type=ContentType.objects.get_for_model(Notification),  # use any marketplace model
            defaults={"name": "Can view marketplace analytics"},
        )

        # marketplace.can_broadcast_notifications
        self.perm_broadcast, _ = Permission.objects.get_or_create(
            codename="can_broadcast_notifications",
            content_type=ContentType.objects.get_for_model(Notification),
            defaults={"name": "Can broadcast notifications"},
        )

        # accounts.view_user and accounts.change_user
        from django.contrib.auth import get_user_model
        User = get_user_model()
        ct_user = ContentType.objects.get_for_model(User)
        self.perm_view_user, _ = Permission.objects.get_or_create(
            codename="view_user",
            content_type=ct_user,
            defaults={"name": "Can view user"},
        )
        self.perm_change_user, _ = Permission.objects.get_or_create(
            codename="change_user",
            content_type=ct_user,
            defaults={"name": "Can change user"},
        )

        # Create admin user and grant group + all perms
        self.admin = make_user("mp_admin", is_staff=True)
        self.admin.groups.add(self.group)
        self.admin.user_permissions.add(
            self.perm_approve, self.perm_analytics, self.perm_broadcast, self.perm_view_user, self.perm_change_user
        )

        # Create a non-admin user
        self.user = make_user("regular_user")

        # Create basic data
        self.seller = make_user("seller")
        self.category = Category.objects.create(name="Food", slug="food")
        self.listing = Listing.objects.create(
            seller=self.seller,
            category=self.category,
            title="Kibble",
            description="Tasty",
            price=10.0,
            quantity=1,
            status=ListingStatus.PENDING,
        )
        self.report = Report.objects.create(
            reporter=self.user,
            listing=self.listing,
            reason="Spam",
            status=ReportStatus.OPEN,
        )

    def test_admin_tabs_require_group_membership(self):
        # Regular user should get 403 on admin tabs
        self.client.login(username="regular_user", password="pass")
        for name in [
            "marketplace_admin:listings",
            "marketplace_admin:analytics",
            "marketplace_admin:users",
            "marketplace_admin:notifications",
            "marketplace_admin:reports",
        ]:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 403)

    def test_admin_tabs_require_specific_permissions(self):
        # Admin logs in
        self.client.login(username="mp_admin", password="pass")
        # Listings tab: requires approve perm
        r = self.client.get(reverse("marketplace_admin:listings"))
        self.assertEqual(r.status_code, 200)
        # Analytics tab: requires analytics perm
        r = self.client.get(reverse("marketplace_admin:analytics"))
        self.assertEqual(r.status_code, 200)
        # Users tab: requires accounts.view_user
        r = self.client.get(reverse("marketplace_admin:users"))
        self.assertEqual(r.status_code, 200)
        # Notifications tab: requires broadcast perm
        r = self.client.get(reverse("marketplace_admin:notifications"))
        self.assertEqual(r.status_code, 200)
        # Reports tab: requires moderate reports perm
        # Ensure permission exists on Report model
        ct_report = ContentType.objects.get_for_model(Report)
        perm_mod_reports, _ = Permission.objects.get_or_create(
            codename="can_moderate_reports",
            content_type=ct_report,
            defaults={"name": "Can handle user reports"},
        )
        self.admin.user_permissions.add(perm_mod_reports)
        r = self.client.get(reverse("marketplace_admin:reports"))
        self.assertEqual(r.status_code, 200)

    def test_action_approve_listing_requires_admin_and_perm(self):
        # Without login -> redirect to login due to @login_required
        url = reverse("marketplace_admin:approve_listing", kwargs={"listing_id": self.listing.id})
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        # Login as regular user -> 403 by admin check
        self.client.login(username="regular_user", password="pass")
        r = self.client.post(url)
        self.assertEqual(r.status_code, 403)
        # Login as admin without approve perm -> remove and expect 403
        self.client.login(username="mp_admin", password="pass")
        self.admin.user_permissions.remove(self.perm_approve)
        r = self.client.post(url)
        self.assertEqual(r.status_code, 403)
        # Grant approve perm and succeed
        self.admin.user_permissions.add(self.perm_approve)
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)

    def test_action_reject_listing_records_fields_and_notifies(self):
        self.client.login(username="mp_admin", password="pass")
        url = reverse("marketplace_admin:reject_listing", kwargs={"listing_id": self.listing.id})
        payload = {"reason": "Prohibited item", "reason_code": "prohibited_item"}
        r = self.client.post(url, data=payload)
        self.assertEqual(r.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, ListingStatus.REJECTED)
        self.assertEqual(self.listing.rejected_reason, "Prohibited item")
        self.assertEqual(self.listing.rejected_reason_code, "prohibited_item")
        # Seller receives a STATUS_CHANGED notification
        notes = Notification.objects.filter(user=self.seller)
        self.assertTrue(notes.exists())

    def test_admin_close_report_requires_permission(self):
        # Add moderate reports perm
        ct_report = ContentType.objects.get_for_model(Report)
        perm_mod_reports, _ = Permission.objects.get_or_create(
            codename="can_moderate_reports",
            content_type=ct_report,
            defaults={"name": "Can handle user reports"},
        )
        self.client.login(username="mp_admin", password="pass")
        # Remove perm to assert 403
        self.admin.user_permissions.remove(perm_mod_reports)
        url = reverse("marketplace_admin:close_report", kwargs={"report_id": self.report.id})
        r = self.client.post(url)
        self.assertEqual(r.status_code, 403)
        # Grant perm and succeed
        self.admin.user_permissions.add(perm_mod_reports)
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatus.CLOSED)

    def test_toggle_user_active_requires_permission(self):
        # Admin logs in but lacks change_user permission
        self.client.login(username="mp_admin", password="pass")
        self.admin.user_permissions.remove(self.perm_change_user)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        target = make_user("toggle_target")
        url = reverse("marketplace_admin:toggle_user_active", kwargs={"user_id": target.id})
        r = self.client.post(url)
        self.assertEqual(r.status_code, 403)
        # Grant permission and succeed
        self.admin.user_permissions.add(self.perm_change_user)
        r = self.client.post(url)
        self.assertEqual(r.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.is_active, False)

    def test_broadcast_requires_permission(self):
        # Admin logs in but lacks broadcast permission
        self.client.login(username="mp_admin", password="pass")
        self.admin.user_permissions.remove(self.perm_broadcast)
        url = reverse("marketplace_admin:notifications_broadcast")
        r = self.client.post(url, data={"title": "Test", "body": "Hello"})
        self.assertEqual(r.status_code, 403)
        # Grant permission and succeed
        self.admin.user_permissions.add(self.perm_broadcast)
        r = self.client.post(url, data={"title": "Test", "body": "Hello"})
        self.assertEqual(r.status_code, 302)