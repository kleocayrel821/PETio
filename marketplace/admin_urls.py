from django.urls import path
from . import views

app_name = "marketplace_admin"

urlpatterns = [
    # Marketplace Admin dashboard and tools, namespaced under /admin/marketplace/
    path("dashboard/", views.AdminDashboardView.as_view(), name="dashboard"),
    path("dashboard/listings/", views.AdminListingsView.as_view(), name="listings"),
    path("dashboard/reports/", views.AdminReportsView.as_view(), name="reports"),
    path("dashboard/analytics/", views.AdminAnalyticsView.as_view(), name="analytics"),
    path("dashboard/analytics/data/", views.admin_analytics_data, name="analytics_data"),
    path("dashboard/users/", views.AdminUsersView.as_view(), name="users"),
    path("dashboard/notifications/", views.AdminNotificationsView.as_view(), name="notifications"),
    path("dashboard/notifications/broadcast/", views.admin_broadcast_notification, name="notifications_broadcast"),
    # Actions
    path("dashboard/listing/<int:listing_id>/approve/", views.admin_approve_listing, name="approve_listing"),
    path("dashboard/listing/<int:listing_id>/reject/", views.admin_reject_listing, name="reject_listing"),
    path("dashboard/report/<int:report_id>/close/", views.admin_close_report, name="close_report"),
    path("dashboard/user/<int:user_id>/toggle-active/", views.admin_toggle_user_active, name="toggle_user_active"),
    path("dashboard/transaction/<int:tx_id>/approve-refund/", views.admin_approve_refund, name="approve_refund"),
    path("dashboard/transaction/<int:tx_id>/cancel/", views.admin_cancel_transaction, name="cancel_transaction"),
]