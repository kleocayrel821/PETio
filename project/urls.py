"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from accounts import views as accounts_views
from marketplace import views as marketplace_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('app.urls')),
    path('marketplace/', include(('marketplace.urls', 'marketplace'), namespace='marketplace')),
    # Marketplace Admin URLs under dedicated /admin/marketplace/ namespace
    path('admin/marketplace/', include(('marketplace.admin_urls', 'marketplace_admin'), namespace='marketplace_admin')),
    # Alias for admin notifications send endpoint
    path('marketplace-admin/notifications/send/', marketplace_views.admin_broadcast_notification),
    path('social/', include(('social.urls', 'social'), namespace='social')),
    # Override the default auth login to apply role-aware redirect
    path('accounts/login/', accounts_views.AdminAwareLoginView.as_view(), name='login'),
    path('accounts/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('accounts/', include('django.contrib.auth.urls')),  # Login, logout, password reset
    path('admin/', admin.site.urls),
]

# Serve media files from MEDIA_ROOT at MEDIA_URL in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
