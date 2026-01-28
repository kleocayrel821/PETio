"""
URL patterns for accounts app: signup, profile, and activation.
"""
from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("password_reset/", views.CustomPasswordResetView.as_view(), name="password_reset"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("profile/", views.ProfileDetailView.as_view(), name="profile"),
    path("profile/edit/", views.ProfileUpdateView.as_view(), name="profile_edit"),
    path("activate/<uidb64>/<token>/", views.ActivationView.as_view(), name="activate"),
]
