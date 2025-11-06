from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.conf import settings
from . import views

app_name = "marketplace"

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet)
router.register(r'listings', views.ListingViewSet)
router.register(r'threads', views.MessageThreadViewSet)
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'transactions', views.TransactionViewSet)
router.register(r'reports', views.ReportViewSet)

if getattr(settings, "MARKETPLACE_RESET", False):
    urlpatterns = [
        # Route all marketplace pages to a minimal reset placeholder
        path("", views.reset_placeholder, name="home"),
        path("catalog/", views.reset_placeholder, name="catalog"),
        path("listing/<int:pk>/", views.reset_placeholder, name="listing_detail"),
        path("listing/new/", views.reset_placeholder, name="listing_create"),
        # Legacy alias to create listing route (redirects in normal mode)
        path("listing/create/", views.reset_placeholder, name="create_listing"),
        path("dashboard/", views.reset_placeholder, name="dashboard"),
        path("transactions/", views.reset_placeholder, name="transactions"),
        path("messages/", views.reset_placeholder, name="messages"),
        # During reset, expose no API routes
    ]
else:
    urlpatterns = [
        # Home and catalog
        path("", views.CatalogView.as_view(), name="home"),
        path("catalog/", views.CatalogView.as_view(), name="catalog"),

        # Listing detail and manual purchase request
        path("listing/<int:pk>/", views.ListingDetailView.as_view(), name="listing_detail"),
        path("listing/<int:pk>/request/", views.request_to_purchase, name="request_purchase"),
        # Report listing HTML form (UI)
        path("listing/<int:listing_id>/report/", views.report_listing, name="report_listing"),

        # Purchase request detail and messaging
        path("request/<int:pk>/", views.RequestDetailView.as_view(), name="request_detail"),
        path("request/<int:pk>/meetup.ics", views.meetup_ics, name="request_meetup_ics"),
        path("request/<int:pk>/message/", views.post_request_message, name="request_message_post"),
        path("request/<int:request_id>/rate/", views.post_seller_rating, name="post_seller_rating"),

        # Listing create (seller)
        path("listing/new/", views.ListingCreateView.as_view(), name="listing_create"),
        # Legacy alias that redirects to the standard create view
        path("listing/create/", views.create_listing, name="create_listing"),

        # User dashboard and utility pages
        path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
        path("transactions/", views.transactions, name="transactions"),
        path("messages/", views.messages, name="messages"),
        path("notifications/", views.NotificationListView.as_view(), name="notifications"),
        path("notifications/mark-all/", views.mark_all_notifications_read, name="notifications_mark_all"),
        path("notifications/<int:notif_id>/toggle_read/", views.toggle_notification_read, name="notification_toggle_read"),
        path("notifications/<int:notif_id>/open/", views.open_notification, name="notification_open"),

        # Badge count endpoints
        path("notifications/count/", views.notifications_count, name="notifications_count"),
        path("messages/count/", views.messages_count, name="messages_count"),

        # Trust & Safety
        path("user/<int:user_id>/profile/", views.user_profile, name="user_profile"),
        path("verification/", views.verification_page, name="verification"),

        # Meetup safety helpers
        path("request/<int:pk>/suggest-locations/", views.suggest_safe_locations, name="suggest_locations"),
        path("request/<int:pk>/send-reminder/", views.send_meetup_reminder, name="send_reminder"),
        path("request/<int:pk>/report-no-show/", views.report_no_show, name="report_no_show"),

        # Dispute management
        path("request/<int:pk>/file-dispute/", views.file_dispute, name="file_dispute"),
        path("dispute/<int:dispute_id>/", views.dispute_detail, name="dispute_detail"),
        path("dispute/<int:dispute_id>/add-message/", views.add_dispute_message, name="add_dispute_message"),

        # Dashboards
        path("buyer/", views.BuyerDashboardView.as_view(), name="buyer_dashboard"),
        path("seller/", views.SellerDashboardView.as_view(), name="seller_dashboard"),
        # Requests overview
        path("requests/", views.RequestsOverviewView.as_view(), name="requests_overview"),
        # Legacy moderator route: temporarily redirect to unified admin dashboard
        path("moderator/", views.moderator_legacy_redirect, name="moderator_dashboard"),
        path("moderator/listing/<int:listing_id>/approve/", views.moderator_approve_listing, name="moderator_approve_listing"),
        path("moderator/listing/<int:listing_id>/reject/", views.moderator_reject_listing, name="moderator_reject_listing"),
        path("moderator/report/<int:report_id>/close/", views.moderator_close_report, name="moderator_close_report"),

        # Seller actions on requests
        path("seller/request/<int:request_id>/accept/", views.seller_accept_request, name="seller_accept_request"),
        path("seller/request/<int:request_id>/reject/", views.seller_reject_request, name="seller_reject_request"),
        path("seller/request/<int:request_id>/negotiate/", views.seller_negotiate_request, name="seller_negotiate_request"),
        path("seller/request/<int:request_id>/offer/respond/", views.respond_offer, name="respond_offer"),
        path("seller/request/<int:request_id>/cancel/", views.seller_cancel_request, name="seller_cancel_request"),

        # Buyer actions on requests
        path("buyer/request/<int:request_id>/offer/", views.submit_offer, name="submit_offer"),
        path("buyer/request/<int:request_id>/cancel/", views.buyer_cancel_request, name="buyer_cancel_request"),
        
        # Marketplace Admin dashboard moved to /admin/marketplace/ namespace

        # Completion endpoint
        path("request/<int:request_id>/complete/", views.mark_request_completed, name="mark_request_completed"),

        # Meetup & logistics endpoints
        path("request/<int:request_id>/meetup/propose/", views.propose_meetup, name="propose_meetup"),
        path("request/<int:request_id>/meetup/update/", views.update_meetup, name="update_meetup"),
        path("request/<int:request_id>/meetup/confirm/", views.confirm_meetup, name="confirm_meetup"),

        # Inline listing action endpoints used by Dashboard
        path("api/listings/<int:listing_id>/reserve/", views.api_listing_reserve, name="api_listing_reserve"),
        path("api/listings/<int:listing_id>/sell/", views.api_listing_sell, name="api_listing_sell"),
        path("api/listings/<int:listing_id>/buy-now/", views.api_listing_buy_now, name="api_listing_buy_now"),
        path("api/listings/<int:listing_id>/complete/", views.api_listing_complete, name="api_listing_complete"),
        path("api/listings/<int:listing_id>/report/", views.api_listing_report, name="api_listing_report"),

        # Messaging JSON API endpoints (explicit names used by tests)
        path("api/messages/thread/start/", views.api_start_or_get_thread, name="api_start_or_get_thread"),
        path("api/messages/thread/<int:thread_id>/messages/", views.api_fetch_messages, name="api_fetch_messages"),
        path("api/messages/thread/<int:thread_id>/post/", views.api_post_message, name="api_post_message"),

        # Purchase request JSON API endpoints
        path("api/requests/<int:listing_id>/create/", views.api_request_create, name="api_request_create"),
        path("api/requests/<int:request_id>/accept/", views.api_request_accept, name="api_request_accept"),
        path("api/requests/<int:request_id>/reject/", views.api_request_reject, name="api_request_reject"),
        path("api/requests/<int:request_id>/negotiate/", views.api_request_negotiate, name="api_request_negotiate"),
        path("api/requests/<int:request_id>/cancel/", views.api_request_cancel, name="api_request_cancel"),
        path("api/requests/<int:request_id>/meetup/set/", views.api_request_meetup_set, name="api_request_meetup_set"),
        path("api/requests/<int:request_id>/meetup/confirm/", views.api_request_meetup_confirm, name="api_request_meetup_confirm"),
        path("api/requests/<int:request_id>/payment/record/", views.api_request_record_payment, name="api_request_record_payment"),
        path("api/requests/<int:request_id>/complete/", views.api_request_complete, name="api_request_complete"),
        # Request-level messages polling
        path("api/requests/<int:request_id>/messages/", views.api_request_messages, name="api_request_messages"),

        # Include DRF router for RESTful endpoints
        path("api/", include(router.urls)),
    ]
