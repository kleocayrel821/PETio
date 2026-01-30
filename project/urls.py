from django.contrib import admin
from django.urls import path, include
from accounts import views as accounts_views
from marketplace import views as marketplace_views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import PasswordResetView

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
    # Harden password reset route: explicitly bind template names to avoid missing-template issues
    path(
        'accounts/password_reset/',
        PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            html_email_template_name='registration/password_reset_email.html',
        ),
        name='password_reset',
    ),
    path('accounts/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('accounts/', include('django.contrib.auth.urls')),  # Login, logout, password reset
    path('admin/', admin.site.urls),
]

# Serve media files from MEDIA_ROOT at MEDIA_URL in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
