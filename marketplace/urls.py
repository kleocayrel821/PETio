from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = "marketplace"

router = DefaultRouter()
router.register(r'categories', views.CategoryViewSet)
router.register(r'listings', views.ListingViewSet)
router.register(r'threads', views.MessageThreadViewSet)
router.register(r'messages', views.MessageViewSet, basename='message')
router.register(r'transactions', views.TransactionViewSet)
router.register(r'reports', views.ReportViewSet)

urlpatterns = [
    # Catalog: list active listings with search & category filter
    path("", views.CatalogView.as_view(), name="home"),
    # Alias for convenience/SEO: /marketplace/catalog/
    path("catalog/", views.CatalogView.as_view(), name="catalog"),

    # Listing detail by primary key (db pk)
    path("listing/<int:pk>/", views.ListingDetailView.as_view(), name="listing_detail"),

    # Create listing (CBV). Requires login.
    path("listing/new/", views.ListingCreateView.as_view(), name="listing_create"),

    # Dashboard and Transactions pages (missing before)
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("transactions/", views.transactions, name="transactions"),

    # Messaging page and JSON API endpoints (legacy FBV)
    path("messages/", views.messages, name="messages"),
    path("api/messages/thread/start/", views.api_start_or_get_thread, name="api_start_or_get_thread"),
    path("api/messages/thread/<int:thread_id>/messages/", views.api_fetch_messages, name="api_fetch_messages"),
    path("api/messages/thread/<int:thread_id>/send/", views.api_post_message, name="api_post_message"),

    # Transaction endpoints for listings (legacy FBV)
    path("api/listing/<int:listing_id>/reserve/", views.api_listing_reserve, name="api_listing_reserve"),
    path("api/listing/<int:listing_id>/sell/", views.api_listing_sell, name="api_listing_sell"),
    path("api/listing/<int:listing_id>/complete/", views.api_listing_complete, name="api_listing_complete"),

    # Reporting endpoints and minimal UI
    path("api/listing/<int:listing_id>/report/", views.api_listing_report, name="api_listing_report"),
    path("listing/<int:listing_id>/report/", views.report_listing, name="report_listing"),

    # DRF RESTful routes
    path('api/', include(router.urls)),
]