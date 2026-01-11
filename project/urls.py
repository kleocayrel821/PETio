from django.contrib import admin
from django.urls import path, include
from accounts import views as accounts_views
from marketplace import views as marketplace_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('controller.urls')),
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
#if settings.DEBUG:
    #urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
