from django.urls import path
from . import views

app_name = "marketplace"

urlpatterns = [
    path("", views.marketplace_home, name="home"),
    path("listing/<int:listing_id>/", views.listing_detail, name="listing_detail"),
    path("listings/create/", views.create_listing, name="create_listing"),
    path("messages/", views.messages, name="messages"),
    path("transactions/", views.transactions, name="transactions"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("admin/review/", views.admin_review, name="admin_review"),
]